"""P1.6: build the shared goose eye asset (eyeball + upper/lower lids + catchlight).

  blender -b --factory-startup --python scripts/make_eye_asset.py -- [--render]

Writes assets/goose_eye/{goose_eye.blend, goose_eye.glb, goose_eye_iris.png} and, with
--render, renders/eye_asset_review.png (open, 3/4, half-blink, closed).

Canonical frame (one LEFT eye; the right eye is its mirror): centre at the origin, look axis
-Y, up +Z, anterior (toward the bill) +X. Lids are spherical shells concentric with the
eyeball, so a blink is a pure rotation of the upper (and lower) lid about the X axis through
the centre: rig with one eye bone (eyeball) + two lid bones, all pivoting at the origin.
The catchlight is its own static object (parent it to the head bone) so it stays put while
the eyeball looks around and the lids blink. blink_angles() gives the closed-lid rotations.
All numbers live in SPEC (sizes in metres for a 1.65 m goose, taken from refs/v3). The sphere is
large relative to the visible opening so the eye sits nearly flush with the head surface.
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "goose_eye"
SPEC = {
    "eyeball_radius": 0.0240,           # large, flat sphere: the eye hugs the head surface
    "lid_radius_scale": 1.04,          # lid shell radius / eyeball radius
    "opening_half_angle_deg": [40, 26, 21],   # anterior-horizontal, posterior-horizontal, vertical
    "opening_power": [1.5, 2.4],      # superellipse exponent anterior / posterior (<2 = pointed almond corner)
    "gaze_rest_az_deg": -8,           # eyeball rest rotation: iris turned back, cream shows toward the bill
    "lid_coverage_deg": [54, 45],      # upper, lower: how far back each shell reaches (hidden in the head)
    "close_el_deg": -6,                # where the lids meet when closed (below centre, like a bird)
    "iris_deg": 19.5, "pupil_deg": 10, "limbal_deg": 2.0, "sclera_ring_deg": 30,
    "iris_rgb": [[0.62, 0.36, 0.10], [0.42, 0.20, 0.05]],   # inner -> outer (sRGB)
    "limbal_rgb": [0.10, 0.05, 0.02], "pupil_rgb": [0.015, 0.012, 0.01],
    "sclera_rgb": [0.90, 0.86, 0.76], "lid_rgb": [0.045, 0.040, 0.036], "rim_rgb": [0.02, 0.018, 0.016],
    "catchlight": {"az_deg": 1, "el_deg": 9, "radius": 0.0013},
    "eyeball_segments": [20, 12], "lid_segments": [40, 7], "tex": 512,
}


def _iris_texture(path):
    """Planar projection of the front hemisphere: pixel (u, v) -> angle from the look axis."""
    n = SPEC["tex"]
    u, v = np.meshgrid((np.arange(n) + 0.5) / n * 2 - 1, (np.arange(n) + 0.5) / n * 2 - 1)
    r = np.clip(np.hypot(u, v), 0, 1)
    th = np.degrees(np.arcsin(r))
    ang = np.arctan2(v, u)
    rng = np.random.default_rng(3)
    fib = np.zeros_like(r)
    for k, a in zip(rng.integers(30, 90, 6), rng.random(6) * 6.28):   # radial iris fibres
        fib += np.cos(k * ang + a) * 0.5
    fib = 1 + 0.06 * fib / 6 * 6
    i0, i1 = np.array(SPEC["iris_rgb"])
    t = np.clip((th - SPEC["pupil_deg"]) / (SPEC["iris_deg"] - SPEC["pupil_deg"]), 0, 1)[..., None]
    col = (i0 * (1 - t) + i1 * t) * fib[..., None]
    lim = np.clip((th - (SPEC["iris_deg"] - SPEC["limbal_deg"])) / SPEC["limbal_deg"], 0, 1)[..., None]
    col = col * (1 - lim) + np.array(SPEC["limbal_rgb"]) * lim
    col = np.where((th < SPEC["pupil_deg"])[..., None], SPEC["pupil_rgb"], col)
    edge = np.clip((th - SPEC["pupil_deg"]) / 1.2, 0, 1)[..., None]       # soft pupil edge
    col = np.array(SPEC["pupil_rgb"]) * (1 - edge) + col * edge
    scl = np.clip((th - SPEC["iris_deg"]) / 1.0, 0, 1)[..., None]
    col = col * (1 - scl) + np.array(SPEC["sclera_rgb"]) * scl
    back = np.clip((th - SPEC["iris_deg"] - SPEC["sclera_ring_deg"]) / 3.0, 0, 1)[..., None]
    col = col * (1 - back) + np.array(SPEC["lid_rgb"]) * back       # dark beyond the visible ring
    img = bpy.data.images.new("goose_eye_iris", n, n, alpha=False)
    px = np.concatenate([col, np.ones((n, n, 1))], -1).astype(np.float32)
    img.pixels.foreach_set(px.ravel())
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()
    img.pack()
    return img


def _material(name, rgb=None, image=None, rough=0.5, emit=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = next(nd for nd in m.node_tree.nodes if nd.type == "BSDF_PRINCIPLED")
    p.inputs["Roughness"].default_value = rough
    if image is not None:
        t = m.node_tree.nodes.new("ShaderNodeTexImage")
        t.image = image
        m.node_tree.links.new(t.outputs[0], p.inputs["Base Color"])
    elif rgb is not None:
        p.inputs["Base Color"].default_value = (*[c ** 2.2 for c in rgb], 1)    # sRGB -> linear
    if emit is not None:
        p.inputs["Emission Color"].default_value = (*emit, 1)
        p.inputs["Emission Strength"].default_value = 1.0
    return m


def _obj(name, bm, mat):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    for poly in me.polygons:
        poly.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _dir(az, el):
    """Unit vector: az (deg, + toward anterior +X) and el (deg, + up) away from the look axis -Y."""
    a, e = math.radians(az), math.radians(el)
    return Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))


def build_eyeball(img):
    R = SPEC["eyeball_radius"]
    bm = bmesh.new()
    seg, ring = SPEC["eyeball_segments"]
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=ring, radius=R)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Euler((math.radians(90), 0, 0)).to_matrix())
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:                                   # planar projection along the look axis
        for lp in f.loops:
            c = lp.vert.co / R
            lp[uvl].uv = (0.5 + 0.5 * c.x, 0.5 + 0.5 * c.z) if c.y < 0.05 else (0.01, 0.01)  # back = dark
    ob = _obj("eyeball", bm, _material("goose_eye", image=img, rough=0.06))
    ob.rotation_euler = (0, 0, math.radians(SPEC["gaze_rest_az_deg"]))    # rest gaze (rig: eye bone rest); - = toward the back
    return ob


def _inside_opening(az, el):
    ha = SPEC["opening_half_angle_deg"]
    h = ha[0] if az >= 0 else ha[1]
    p = SPEC["opening_power"][0 if az >= 0 else 1]
    return (abs(az) / h) ** p + (abs(el) / ha[2]) ** p < 1.0


def _opening_radius(phi):
    """Angular distance (deg) from the look axis to the opening curve in direction phi
    (phi measured in the az/el plane: 0 = anterior, 90 = up)."""
    ha = SPEC["opening_half_angle_deg"]
    c, s = math.cos(phi), math.sin(phi)
    h = ha[0] if c >= 0 else ha[1]
    p = SPEC["opening_power"][0 if c >= 0 else 1]
    return 1.0 / ((abs(c) / h) ** p + (abs(s) / ha[2]) ** p) ** (1.0 / p)


def build_lid(upper):
    """Lid shell made of concentric loops that follow the almond opening outward to the
    coverage limit (clean rim, edge loops for blink), plus a rim loop tucked against the
    eyeball for edge thickness. Upper = phi 0..180 deg, lower = 180..360 deg."""
    R = SPEC["eyeball_radius"] * SPEC["lid_radius_scale"]
    na, nr = SPEC["lid_segments"]
    cov = SPEC["lid_coverage_deg"][0 if upper else 1]
    n = na // 2
    phis = np.linspace(0, math.pi, n + 1) if upper else np.linspace(math.pi, 2 * math.pi, n + 1)
    bm = bmesh.new()
    rows = []
    tuck = [bm.verts.new(_dir(_opening_radius(f) * math.cos(f), _opening_radius(f) * math.sin(f))
                         * SPEC["eyeball_radius"] * 1.015) for f in phis]
    rows.append(tuck)
    for k in range(nr + 1):
        t = (k / nr) ** 1.4                       # denser loops near the rim
        row = []
        for f in phis:
            r0 = _opening_radius(f)
            r = r0 + (cov - r0) * t
            row.append(bm.verts.new(_dir(r * math.cos(f), r * math.sin(f)) * R))
        rows.append(row)
    for i in range(len(rows) - 1):
        for j in range(n):
            f = bm.faces.new([rows[i][j], rows[i][j + 1], rows[i + 1][j + 1], rows[i + 1][j]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces:                             # outward = away from the eye centre
        if f.normal.dot(f.calc_center_median()) < 0:
            f.normal_flip()
    return _obj("lid_upper" if upper else "lid_lower", bm, _material("goose_lid", rgb=SPEC["lid_rgb"], rough=0.85))


def build_catchlight():
    c = SPEC["catchlight"]
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, segments=10, radius=c["radius"])
    d = _dir(c["az_deg"], c["el_deg"])
    rot = d.to_track_quat("Z", "Y").to_matrix()
    bmesh.ops.transform(bm, verts=bm.verts, matrix=rot.to_4x4())
    bmesh.ops.translate(bm, verts=bm.verts, vec=d * SPEC["eyeball_radius"] * 1.012)
    return _obj("catchlight", bm, _material("goose_catchlight", rgb=[1, 1, 1], rough=0.3, emit=(1, 1, 1)))


def blink_angles():
    """Closed-eye lid rotations (deg about +X): upper lid down, lower lid up, meeting at close_el."""
    v = SPEC["opening_half_angle_deg"][2]
    return v - SPEC["close_el_deg"] + 2, v + SPEC["close_el_deg"] + 2      # +2 deg overlap


def render_review(objs):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = sc.render.resolution_y = 600
    sc.view_settings.view_transform = "Standard"
    sc.world = bpy.data.worlds.new("w")
    sc.world.color = (0.25, 0.25, 0.25)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 0.06
    sc.collection.objects.link(cam)
    sc.camera = cam
    key = bpy.data.objects.new("key", bpy.data.lights.new("key", "SUN"))
    key.data.energy = 3.0
    key.rotation_euler = Euler((math.radians(60), 0, math.radians(-30)))
    sc.collection.objects.link(key)
    up, low = objs["lid_upper"], objs["lid_lower"]
    shots = [("open", (0, -0.3, 0), 0), ("three_quarter", (0.2, -0.22, 0.04), 0),
             ("half_blink", (0, -0.3, 0), 0.5), ("closed", (0, -0.3, 0), 1.0)]
    paths = []
    for name, loc, blink in shots:
        up.rotation_euler = (math.radians(blink_angles()[0]) * blink, 0, 0)
        low.rotation_euler = (-math.radians(blink_angles()[1]) * blink, 0, 0)
        cam.location = loc
        cam.rotation_euler = (Vector((0, 0, 0)) - Vector(loc)).to_track_quat("-Z", "Z").to_euler()
        sc.render.filepath = str(ROOT / "renders" / "_tmp" / f"eye_{name}.png")
        bpy.ops.render.render(write_still=True)
        paths.append(sc.render.filepath)
    up.rotation_euler = low.rotation_euler = (0, 0, 0)
    imgs = [bpy.data.images.load(p) for p in paths]
    w = 600 * len(imgs)
    canvas = np.zeros((600, w, 4), np.float32)
    for i, im in enumerate(imgs):
        canvas[:, i * 600:(i + 1) * 600] = np.array(im.pixels[:]).reshape(600, 600, 4)
    out = bpy.data.images.new("review", w, 600)
    out.pixels.foreach_set(canvas.ravel())
    out.filepath_raw = str(ROOT / "renders" / "eye_asset_review.png")
    out.file_format = "PNG"
    out.save()


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    OUT.mkdir(parents=True, exist_ok=True)
    img = _iris_texture(OUT / "goose_eye_iris.png")
    objs = {"eyeball": build_eyeball(img), "lid_upper": build_lid(True), "lid_lower": build_lid(False)}
    objs["catchlight"] = build_catchlight()
    stats = {k: sum(len(p.vertices) - 2 for p in o.data.polygons) for k, o in objs.items()}
    stats["total_tris_one_eye"] = sum(stats.values())
    if "--render" in sys.argv:
        render_review(objs)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.export_scene.gltf(filepath=str(OUT / "goose_eye.glb"), export_format="GLB", use_selection=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "goose_eye.blend"))
    (OUT / "goose_eye.json").write_text(json.dumps({"spec": SPEC, "tris": stats,
                                                    "blink_closed_deg": {"lid_upper": blink_angles()[0],
                                                                         "lid_lower": -blink_angles()[1]}}, indent=1))
    print("EYE", json.dumps(stats))


main()
