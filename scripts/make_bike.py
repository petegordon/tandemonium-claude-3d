"""P4.1: prepare and rig the game's tandem (D13-D18).

  blender -b --factory-startup --python scripts/make_bike.py -- [--wheel-m 0.7112] [--budget 28000] [--no-renders]
      [--fit out/fit/frame_goosefit_24in.json --tag goosefit24]

Source: ../tandemonium/tandem-3d/tandem_bicycle.glb (read only; CC-BY-4.0 Sameer.Rayeen).
1. Import, bake every mesh to world space, drop the Sketchfab empties. Mesh object names are kept exactly
   (the game's colour presets and bike-model.js key on them; three.js strips the dots).
2. Metres (wheel outer diameter = --wheel-m), forward -Y, ground z = 0, centred between the axles.
3. Stoker crankset turned half a turn in the rest pose (D15: captain theta, stoker theta + pi).
3b. --fit: goose-fit reshape (goosefit_bike.py, docs/goose-fit-tandem.md); outputs carry --tag.
4. Pivots + sockets measured from the full-resolution geometry.
5. Decimate each mesh in place to the --budget (D18); meshes under KEEP_TRIS untouched; deviation reported.
6. Armature `bike_rig`; every mesh parented to one bone (rigid, stays a plain Mesh in three.js).
   Sockets are non-deforming bones pointing up with roll 0, i.e. identity rotation in bike space
   (glTF: +Y up, +Z forward). L = rider's left = +X (Blender) / +X (glTF).
7. Clips (NLA tracks, 24 fps): Pedal (one forward crank revolution, pedals stay level) and
   WheelSpin (one wheel revolution). Bars fixed (D16): the Steer bone exists but has no clip.
Writes out/bike/bike_rigged.glb + .blend + bike_rig.json, renders/bike_p41_*.png.
"""
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
SRC = Path(arg("--src", str(ROOT.parent / "tandemonium" / "tandem-3d" / "tandem_bicycle.glb")))
OUT = ROOT / "out" / "bike"
REN = ROOT / "renders"
TMP = REN / "_tmp"
WHEEL_M = arg("--wheel-m", 0.7112)           # 28 in wheel, outer tyre diameter (of the source, before --fit)
FIT = arg("--fit", "")
TAG = arg("--tag", "")
SFX = f"_{TAG}" if TAG else ""                # bike_rigged<SFX>.glb / bike_rig<SFX>.json / bike_<TAG or p41>_*.png
RTAG = TAG or "p41"
BUDGET = arg("--budget", 28000)              # D18: < 30k, with margin
KEEP_TRIS = 300                              # spokes, tiny bits: never decimated
TOL_M = 0.004                                # max surface deviation a decimated mesh may have
RENDERS = "--no-renders" not in argv
FPS = 24
N = 24                                       # frames per revolution
OUT.mkdir(parents=True, exist_ok=True)
TMP.mkdir(parents=True, exist_ok=True)

# ---- part groups (Blender names + "_cycle_0"; three.js drops the dots) -----------------------------
GROUPS = {
    "Wheel_F": ["Cylinder.035", "Cylinder.004", "tyre_rear_low", "rear_wheel_joint_low.002",
                "rear_wheel_joint_2_low.002"],                       # spokes, rim, tyre (sic), hub
    "Wheel_R": ["Cylinder.024", "Cylinder.007", "Cylinder.008", "rear_wheel_joint_low.001",
                "rear_wheel_joint_2_low.001", "Gear.004"],           # + rear sprocket
    "Steer": ["NurbsPath.001", "NurbsPath.005", "Cylinder.006", "Cylinder.002", "Cylinder.003",
              "NurbsPath.004", "Cylinder.011", "NurbsPath", "Cylinder.012", "Tee Joint",
              "Tee Joint.001", "Cylinder.017"],                      # fork, stays, mudguard, lamp, bar, grips, headset, stem
    "Crank_F": ["Gear.001", "Cylinder.013", "pedal_rod_low", "pedal_rod_low.001", "chain_rod_low"],
    "Crank_R": ["Gear.002", "Gear.003", "Cylinder.014", "Cylinder.015", "pedal_rod_low.002",
                "pedal_rod_low.003", "chain_rod_low.001"],
    "Pedal_FL": ["pedal_low.001"], "Pedal_FR": ["pedal_low"],
    "Pedal_RL": ["pedal_low.002"], "Pedal_RR": ["pedal_low.003"],
    "Bike_root": ["Cylinder", "Cylinder.001", "wainframe_joint_low", "wainframe_joint_low.001",
                  "NurbsPath.002", "NurbsPath.003", "NurbsPath.006", "NurbsPath.014", "NurbsPath.015",
                  "Cylinder.009", "Cube", "Cube.002", "Cylinder.016", "NurbsPath.009", "Cylinder.019",
                  "seat", "seat.001", "NurbsPath.010", "NurbsPath.011", "Circle", "Circle.001",
                  "Cylinder.010", "Cylinder.020", "Cylinder.021", "Cylinder.023",
                  "NurbsPath.007", "NurbsPath.008"],                 # frame, rack, rear mudguard, saddles, rear bar, chains
}
GROUP_COLOURS = {"Bike_root": (0.55, 0.55, 0.55), "Steer": (0.2, 0.45, 0.95), "Wheel_F": (0.1, 0.75, 0.3),
                 "Wheel_R": (0.1, 0.6, 0.6), "Crank_F": (0.95, 0.55, 0.1), "Crank_R": (0.9, 0.2, 0.2),
                 "Pedal_FL": (0.95, 0.9, 0.1), "Pedal_FR": (0.95, 0.9, 0.1),
                 "Pedal_RL": (0.8, 0.3, 0.9), "Pedal_RR": (0.8, 0.3, 0.9)}


def obj(n):
    return bpy.data.objects[n + "_cycle_0"]


def world_verts(o):
    return np.array([v.co[:] for v in o.data.vertices])       # meshes are baked: local == world


def bbox(objs):
    v = np.vstack([world_verts(o) for o in objs])
    return v.min(0), v.max(0)


def centre(names_):
    a, b = bbox([obj(n) for n in names_])
    return Vector(((a + b) / 2).tolist())


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def r3(v):
    return [round(float(x), 4) for x in v]


# ---- 1. import + bake ------------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(SRC))
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
for o in meshes:
    if o.data.users > 1:
        o.data = o.data.copy()
    mw = o.matrix_world.copy()
    o.data.transform(mw)
    if mw.determinant() < 0:
        o.data.flip_normals()
    o.parent = None
    o.matrix_world = Matrix.Identity(4)
for o in [o for o in bpy.data.objects if o.type != "MESH"]:
    bpy.data.objects.remove(o)
names = {o.name for o in meshes}
grouped = [n + "_cycle_0" for g in GROUPS.values() for n in g]
assert len(grouped) == len(set(grouped)), "mesh in two groups"
assert set(grouped) == names, f"unclassified {names - set(grouped)} / missing {set(grouped) - names}"
src_tris = {o.name: tris(o) for o in meshes}

# ---- 2. metres, ground, centre ---------------------------------------------------------------------
lo, hi = bbox([obj("tyre_rear_low")])
s = WHEEL_M / (hi[2] - lo[2])
lo_r, hi_r = bbox([obj("Cylinder.008")])
y_mid = ((lo[1] + hi[1]) / 2 + (lo_r[1] + hi_r[1]) / 2) / 2
T = Matrix.Scale(s, 4) @ Matrix.Translation((0, -y_mid, -min(lo[2], lo_r[2])))
for o in meshes:
    o.data.transform(T)
print(f"SCALE {s:.5f} m/unit")

# ---- 3. D15: stoker crankset half a turn (arms + rings rotate about the axle, pedals translate) -----
hub_F = centre(["tyre_rear_low"]); hub_F.x = 0
hub_R = centre(["Cylinder.008"]); hub_R.x = 0
crank_F = centre(["Gear.001"]); crank_F.x = 0
crank_R = centre(["Gear.002"]); crank_R.x = 0
R180 = Matrix.Translation(crank_R) @ Matrix.Rotation(math.pi, 4, "X") @ Matrix.Translation(-crank_R)
for n in GROUPS["Crank_R"]:
    obj(n).data.transform(R180)
for n in GROUPS["Pedal_RL"] + GROUPS["Pedal_RR"]:
    p = centre([n])
    obj(n).data.transform(Matrix.Translation(R180 @ p - p))

# ---- 3b. goose-fit reshape --------------------------------------------------------------------------
FIT_INFO = None
if FIT:
    sys.path.insert(0, str(Path(__file__).parent))
    import goosefit_bike  # noqa: E402
    spec = json.loads((ROOT / FIT).read_text(encoding="utf-8"))
    FIT_INFO = goosefit_bike.reshape(spec, GROUPS)
    WHEEL_M = spec["wheel_m"]
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    for o in meshes:
        src_tris.setdefault(o.name, tris(o))
    hub_F = centre(["tyre_rear_low"]); hub_F.x = 0
    hub_R = centre(["Cylinder.008"]); hub_R.x = 0
    crank_F = centre(["Gear.001"]); crank_F.x = 0
    crank_R = centre(["Gear.002"]); crank_R.x = 0
    print("FIT", json.dumps(FIT_INFO))

# ---- 4. pivots + sockets (full-resolution geometry) ------------------------------------------------
pedal_c = {g: centre(GROUPS[g]) for g in ("Pedal_FL", "Pedal_FR", "Pedal_RL", "Pedal_RR")}
pedal_top = {g: float(bbox([obj(GROUPS[g][0])])[1][2]) for g in pedal_c}
crank_len = {g: (pedal_c[g].yz - (crank_F if g[6] == "F" else crank_R).yz).length for g in pedal_c}

hv = world_verts(obj("Tee Joint"))                 # headset: top + bottom cup -> steer axis
zmid = (hv[:, 2].min() + hv[:, 2].max()) / 2
ring_lo = Vector(hv[hv[:, 2] < zmid].mean(0).tolist()); ring_lo.x = 0
ring_hi = Vector(hv[hv[:, 2] >= zmid].mean(0).tolist()); ring_hi.x = 0
steer_dir = (ring_hi - ring_lo).normalized()


def seat_point(n):
    """Sit-bone point: top of the saddle, at the mean y of its widest top band."""
    v = world_verts(obj(n))
    top = v[v[:, 2] > v[:, 2].max() - 0.015]
    wide = top[np.abs(top[:, 0]) > 0.6 * np.abs(top[:, 0]).max()]
    return Vector((0.0, float(wide[:, 1].mean()), float(v[:, 2].max())))


def grips(n):
    v = world_verts(obj(n))
    return Vector(v[v[:, 0] > 0].mean(0).tolist()), Vector(v[v[:, 0] < 0].mean(0).tolist())


grip_CL, grip_CR = grips("Cylinder.012")
grip_SL, grip_SR = grips("Cylinder.019")
sockets = {"Seat_Captain": (seat_point("seat"), "Bike_root"), "Seat_Stoker": (seat_point("seat.001"), "Bike_root"),
           "Grip_C_L": (grip_CL, "Steer"), "Grip_C_R": (grip_CR, "Steer"),
           "Grip_S_L": (grip_SL, "Bike_root"), "Grip_S_R": (grip_SR, "Bike_root")}
for g in pedal_c:
    sockets["PedalPin_" + g[6:]] = (Vector((pedal_c[g].x, pedal_c[g].y, pedal_top[g])), g)

# ---- render helpers --------------------------------------------------------------------------------
sc = bpy.context.scene
sc.render.engine = "BLENDER_WORKBENCH"
sc.display.shading.light = "STUDIO"
sc.display.shading.show_cavity = True
sc.world = bpy.data.worlds.new("w")
sc.world.color = (1, 1, 1)
sc.view_settings.view_transform = "Standard"
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
sc.collection.objects.link(cam)
sc.camera = cam
CTR = Vector((0, 0, 0.55))
W, H = 640, 400


def shoot(path, az, el, span, tgt=CTR):
    """az 0 = from the front (-Y), 90 = from the rider's left (+X)."""
    a, e = math.radians(az), math.radians(el)
    d = Vector((math.cos(e) * math.sin(a), -math.cos(e) * math.cos(a), math.sin(e)))
    cam.location = tgt + d * 10
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = span
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return str(path)


def sheet(grid, out):
    rows, cols = len(grid), max(len(r) for r in grid)
    canvas = np.ones((H * rows, W * cols, 4), np.float32)
    for ri, row in enumerate(grid):
        for ci, p in enumerate(row):
            canvas[(rows - 1 - ri) * H:(rows - ri) * H, ci * W:(ci + 1) * W] = \
                np.array(bpy.data.images.load(p).pixels[:], np.float32).reshape(H, W, 4)
    img = bpy.data.images.new("sheet", W * cols, H * rows)
    img.pixels.foreach_set(canvas.ravel())
    img.filepath_raw = str(out)
    img.file_format = "PNG"
    img.save()
    print("SHEET", out)


CLOSE = [("full", 90, 0, 3.0, CTR), ("frontwheel", 70, 10, 0.95, hub_F + Vector((0, 0, 0.1))),
         ("crank", 60, 15, 0.7, crank_F), ("saddle", 60, 20, 0.6, sockets["Seat_Stoker"][0]),
         ("lamp_bar", 30, 15, 0.8, ring_hi + Vector((0, -0.1, 0.05)))]
if RENDERS:
    sc.display.shading.color_type = "TEXTURE"
    before = [shoot(TMP / f"bike_before_{c[0]}.png", *c[1:4], tgt=c[4]) for c in CLOSE]


# ---- 5. decimate in place --------------------------------------------------------------------------
def decimate(o, ratio):
    orig = world_verts(o)
    m = o.modifiers.new("dec", "DECIMATE")
    m.ratio = ratio
    m.use_collapse_triangulate = True
    with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o]):
        bpy.ops.object.modifier_apply(modifier=m.name)
        if o.data.has_custom_normals:
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
    bm = bmesh.new()
    bm.from_mesh(o.data)
    big = [f for f in bm.faces if len(f.verts) > 4]                     # n-gons drop tangents (gotcha)
    if big:
        bmesh.ops.triangulate(bm, faces=big)
    bm.to_mesh(o.data)
    bm.free()
    o.data.shade_smooth()
    o.data.set_sharp_from_angle(angle=math.radians(40))
    bvh = BVHTree.FromObject(o, bpy.context.evaluated_depsgraph_get())
    d = np.array([(bvh.find_nearest(Vector(p))[0] - Vector(p)).length for p in orig])
    return float(d.max()), float(np.percentile(d, 95))


# Each mesh: the global ratio, else gentler steps, else untouched -- whichever first stays within TOL_M.
# Thin curved parts (chains, stays) collapse badly and end up kept; the global ratio drops to pay for them.
originals = {o.name: o.data.copy() for o in meshes}
ratio = (BUDGET - sum(t for t in src_tris.values() if t < KEEP_TRIS)) / \
    sum(t for t in src_tris.values() if t >= KEEP_TRIS)
for attempt in range(12):
    dec_report = {}
    for o in meshes:
        if src_tris[o.name] < KEEP_TRIS:
            continue
        for r in sorted({ratio, min(1.0, ratio * 1.5), 0.85, 1.0}):
            dname = o.data.name
            o.data = originals[o.name].copy()
            o.data.name = dname
            if r >= 1.0:
                dec_report[o.name] = {"tris": [src_tris[o.name]] * 2, "ratio": 1.0, "kept": True}
                break
            mx, p95 = decimate(o, r)
            if mx <= TOL_M:
                dec_report[o.name] = {"tris": [src_tris[o.name], tris(o)], "ratio": round(r, 3),
                                      "dev_mm_max": round(mx * 1000, 1), "dev_mm_p95": round(p95 * 1000, 1)}
                break
    total = sum(tris(o) for o in meshes)
    print(f"DECIMATE pass {attempt}: ratio {ratio:.3f} -> {total} tris")
    if total <= BUDGET:
        break
    ratio *= 0.92
kept = [n for n, r in dec_report.items() if r.get("kept")]
gentle = [n for n, r in dec_report.items() if not r.get("kept") and r["ratio"] > ratio + 1e-6]
print(f"DECIMATE {sum(src_tris.values())} -> {total} tris; kept {kept}; gentler {gentle}")
for n, r in sorted(dec_report.items(), key=lambda kv: -kv[1].get("dev_mm_max", 0))[:6]:
    print("  DEV", n, r)

# ---- 6. armature + rigid parenting -----------------------------------------------------------------
X = Vector((1, 0, 0))
Z = Vector((0, 0, 1))
BONES = [  # name, head, tail offset, parent, deform
    ("Bike_root", Vector((0, 0, 0)), Z * 0.3, None, True),
    ("Steer", ring_lo, steer_dir * 0.25, "Bike_root", True),
    ("Wheel_F", hub_F, X * 0.12, "Steer", True),
    ("Wheel_R", hub_R, X * 0.12, "Bike_root", True),
    ("Crank_F", crank_F, X * 0.1, "Bike_root", True),
    ("Crank_R", crank_R, X * 0.1, "Bike_root", True),
] + [(g, pedal_c[g], X * 0.06, "Crank_" + g[6], True) for g in pedal_c] \
  + [(n, p, Z * 0.05, par, False) for n, (p, par) in sockets.items()]

arm = bpy.data.armatures.new("bike_rig")
rig = bpy.data.objects.new("bike_rig", arm)
sc.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
for n, h, d, par, deform in BONES:
    eb = arm.edit_bones.new(n)
    eb.head, eb.tail = h, h + d
    eb.roll = 0
    eb.use_deform = deform
    if par:
        eb.parent = arm.edit_bones[par]
bpy.ops.object.mode_set(mode="OBJECT")
for g, ns in GROUPS.items():
    for n in ns:
        o = obj(n)
        o.parent = rig
        o.parent_type = "BONE"
        o.parent_bone = g
        o.matrix_world = Matrix.Identity(4)
bpy.context.view_layer.update()

# ---- 7. clips --------------------------------------------------------------------------------------
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 0, N                 # clip time 0 = frame 0: exactly one revolution per second
bpy.context.preferences.edit.keyframe_new_interpolation_type = "LINEAR"
rig.animation_data_create()
for pb in rig.pose.bones:
    pb.rotation_mode = "XYZ"


def clip(name, spins):
    """spins: {bone: turns per clip}; forward = +rotation about the bone's Y (= world +X)."""
    act = bpy.data.actions.new(name)
    rig.animation_data.action = act
    for f in range(N + 1):
        for b, turns in spins.items():
            pb = rig.pose.bones[b]
            pb.rotation_euler = (0, 2 * math.pi * turns * f / N, 0)
            pb.keyframe_insert("rotation_euler", frame=f, group=b)
    act.use_fake_user = True
    tr = rig.animation_data.nla_tracks.new()
    tr.name = name
    st = tr.strips.new(name, 0, act)
    st.extrapolation = "NOTHING"
    tr.mute = True
    rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.rotation_euler = (0, 0, 0)


clip("Pedal", {"Crank_F": 1, "Crank_R": 1, "Pedal_FL": -1, "Pedal_FR": -1, "Pedal_RL": -1, "Pedal_RR": -1})
clip("WheelSpin", {"Wheel_F": 1, "Wheel_R": 1})

# ---- report + export -------------------------------------------------------------------------------
lo_all, hi_all = bbox(meshes)
report = {
    "source": str(SRC), "scale_m_per_unit": round(s, 6), "wheel_m": WHEEL_M,
    "length_m": round(float(hi_all[1] - lo_all[1]), 3), "height_m": round(float(hi_all[2]), 3),
    "width_m": round(float(hi_all[0] - lo_all[0]), 3),
    "tris": {"source": sum(src_tris.values()), "out": total, "decimate_ratio": round(ratio, 3)},
    "pivots": {"hub_F": r3(hub_F), "hub_R": r3(hub_R), "wheelbase_m": round(hub_R.y - hub_F.y, 3),
               "crank_F": r3(crank_F), "crank_R": r3(crank_R), "steer_lo": r3(ring_lo), "steer_hi": r3(ring_hi),
               "head_angle_deg": round(math.degrees(math.atan2(steer_dir.z, steer_dir.y)), 1),
               "crank_len_m": {k: round(v, 4) for k, v in crank_len.items()}},
    "sockets": {n: {"pos": r3(p), "parent": par} for n, (p, par) in sockets.items()},
    "groups": GROUPS,
    "clips": {"Pedal": f"1 forward crank turn, {N + 1} keys @ {FPS} fps; clip time = (crankAngle / 2pi) * duration",
              "WheelSpin": "1 wheel turn; clip time = (distance / (pi * wheel_m) mod 1) * duration"},
    "phase": "rest: captain left (+X) pedal up, stoker left pedal down (D15)",
    "fit": {"spec": FIT, **FIT_INFO} if FIT_INFO else None,
    "decimation": dec_report,
}
(OUT / f"bike_rig{SFX}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
print("REPORT", json.dumps({k: report[k] for k in ("scale_m_per_unit", "length_m", "height_m", "tris", "pivots")}))

bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"bike_rigged{SFX}.blend"), compress=True)
bpy.ops.object.select_all(action="DESELECT")
rig.select_set(True)
for o in meshes:
    o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(OUT / f"bike_rigged{SFX}.glb"), export_format="GLB", use_selection=True,
                          export_animations=True, export_animation_mode="NLA_TRACKS", export_yup=True,
                          export_def_bones=False, export_tangents=True)
sys.path.insert(0, str(Path(__file__).parent))
from glb_fix_tangents import main as fix_tangents  # noqa: E402
fix_tangents(str(OUT / f"bike_rigged{SFX}.glb"))
print("EXPORT", OUT / f"bike_rigged{SFX}.glb")
if not RENDERS:
    sys.exit(0)

# ---- renders ---------------------------------------------------------------------------------------
after = [shoot(TMP / f"bike_after_{c[0]}.png", *c[1:4], tgt=c[4]) for c in CLOSE]
sheet([before, after], REN / f"bike_{RTAG}_decimation.png")

rig.animation_data.action = bpy.data.actions["Pedal"]
sc.display.shading.color_type = "OBJECT"         # side colours: L pedal yellow, R navy (D15 phase)
for g, ns in GROUPS.items():
    for n in ns:
        obj(n).color = (*GROUP_COLOURS[g], 1)
for g in pedal_c:
    obj(GROUPS[g][0]).color = (1, 0.85, 0, 1) if g.endswith("L") else (0.05, 0.1, 0.45, 1)
cyc = []
for k in range(8):
    sc.frame_set(k * N // 8)
    cyc.append(shoot(TMP / f"bike_cycle_{k}.png", 90, 3, 1.5, tgt=(crank_F + crank_R) / 2 + Vector((0, 0, 0.1))))
rig.animation_data.action = None
for pb in rig.pose.bones:                     # clearing the action leaves the last pose behind
    pb.rotation_euler = (0, 0, 0)
sc.frame_set(0)

sheet([cyc[:4], cyc[4:]], REN / f"bike_{RTAG}_crank_cycle.png")
for n, (p, par) in sockets.items():
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.02, location=p)
    bpy.context.active_object.color = (1, 0, 1, 1) if n.startswith(("Seat", "Grip")) else (0, 0, 0, 1)
for p in (hub_F, hub_R, crank_F, crank_R, ring_lo, ring_hi):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.025, location=p)
    bpy.context.active_object.color = (1, 1, 1, 1)
VIEWS = [("side_L", 90, 0, 3.0), ("side_R", -90, 0, 3.0), ("front", 0, 0, 1.6),
         ("top", 90, 89, 3.0), ("q34", 35, 22, 3.0), ("rear_q", 150, 22, 3.0)]
g1 = [shoot(TMP / f"bike_groups_{v[0]}.png", *v[1:]) for v in VIEWS]
sheet([g1[:3], g1[3:]], REN / f"bike_{RTAG}_groups.png")
print("RENDERS done")
