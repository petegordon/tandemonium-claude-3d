"""Align the "goose wearing one garment" models to the base goose and measure each garment as an ease field.

  blender -b --factory-startup --python scripts/align_worn.py -- [--set outfit_male_victorian/worn]
      [--garments hat,bow_tie,...] [--baseline hat] [--trim 0.4]

Input: out/<set>/<g>/candidate_s42.glb (Pixal3D of Pete's worn sheets), facing from renders/mvicw_<g>_s42.json.
1. Align (similarity: uniform scale + rotation + translation) base -> worn by trimmed ICP: init by height and floor,
   then N base surface points -> nearest worn surface, the worst --trim fraction dropped each round (the garment
   stands off the body there); the worn model is moved into the base frame -> out/<set>/<g>/aligned.glb.
2. Ease field on the game body (base_goose_game, 19k verts): per vertex, a ray from 0.15 m outside along the vertex
   normal, inward; the first hit is the worn model's OUTER surface: ease = offset of that hit from the body (+ out).
   The texel colour there is kept too.
3. The generated goose is not exactly our base goose, so the --baseline panel (hat: the body is bare below the head)
   is subtracted: delta = ease_g - ease_baseline cancels the body-shape mismatch. Covered = delta > 6 mm or the
   colour differs from the baseline's by > 0.18 (and the vertex is in the garment's body regions).
4. Per garment, per body region (torso front / back / side, upper arm, forearm, hand, thigh, shin, foot, neck):
   coverage fraction, delta ease p50 / p90 mm, covered z range; accessories (hat, bow tie) get the box of the worn
   points > 1 cm off the body in their zone. -> out/<set>/measure.json, <g>_ease.npz, and
   renders/mvicw_measure.png (body coloured by delta ease where covered: front / side / back per garment).
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
SET = opt("--set", "outfit_male_victorian/worn")
GS = opt("--garments", "hat,bow_tie,shirt,vest,jacket,glove,breeches,boots").split(",")
BASELINE = opt("--baseline", "hat")
TRIM = opt("--trim", 0.4)
D = ROOT / "out" / SET
N_ICP = 15000
RAY0 = 0.15
COVER_MM = 6.0
COVER_RGB = 0.18
ZONES = {"hat": ("head", 0.0), "bow_tie": ("neck", 0.0)}      # accessories: measured as boxes

bpy.ops.wm.open_mainfile(filepath=str(ROOT / "out" / "base-goose" / "base_goose.blend"))
for o in list(bpy.data.objects):
    if o.type == "MESH" and o.name not in ("base_goose_game", "base_goose_hi"):
        bpy.data.objects.remove(o)
body = bpy.data.objects["base_goose_game"]
hi = bpy.data.objects["base_goose_hi"]
dg = bpy.context.evaluated_depsgraph_get()


def getV(o):
    a = np.empty(len(o.data.vertices) * 3)
    o.data.vertices.foreach_get("co", a)
    return a.reshape(-1, 3)


BV = getV(body)
BN = np.array([v.normal[:] for v in body.data.vertices])
HV = getV(hi)
H = HV[:, 2].max()
gname = {g.index: g.name for g in body.vertex_groups}


def region(i, v):
    best, w = None, -1
    for g in body.data.vertices[i].groups:
        if g.weight > w:
            best, w = gname[g.group], g.weight
    b = best or "Hips"
    side = "L" if v[0] > 0 else "R"
    if "Hand" in b:
        return "hand"
    if "ForeArm" in b:
        return "forearm"
    if "Arm" in b or "Shoulder" in b:
        return "upper_arm"
    if "UpLeg" in b:
        return "thigh"
    if b.endswith("Leg"):
        return "shin"
    if "Foot" in b or "Toe" in b:
        return "foot"
    if "Neck" in b:
        return "neck"
    if b in ("Head", "Jaw", "Tongue", "beak_lower", "tongue"):
        return "head"
    n = BN[i]
    if abs(n[0]) > 0.7:
        return "torso_side"
    return "torso_front" if n[1] < 0 else "torso_back"


REG = np.array([region(i, v) for i, v in enumerate(BV)])
D.mkdir(parents=True, exist_ok=True)
np.savez_compressed(D / "_regions.npz", reg=REG, co=BV, nrm=BN)
if "--regions-only" in argv:
    print("REGIONS", {r: int((REG == r).sum()) for r in sorted(set(REG))})
    sys.exit(0)
REGIONS = ["head", "neck", "torso_front", "torso_side", "torso_back", "upper_arm", "forearm", "hand", "thigh", "shin",
           "foot"]


def import_glb(path, name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for o in new:
        if o != ob and o.name in bpy.data.objects:
            bpy.data.objects.remove(o)
    ob.name = name
    return ob


def bvh_of(o):
    return BVHTree.FromPolygons([Vector(v) for v in getV(o)], [tuple(p.vertices) for p in o.data.polygons])


def umeyama(p, q):
    mp, mq = p.mean(0), q.mean(0)
    P, Q = p - mp, q - mq
    U, S, Vt = np.linalg.svd(Q.T @ P / len(p))
    Dm = np.eye(3)
    Dm[2, 2] = np.sign(np.linalg.det(U @ Vt))
    R = U @ Dm @ Vt
    s = (S * np.diag(Dm)).sum() / (P ** 2).sum(1).mean()
    return s, R, mq - s * R @ mp


def mat4(s, R, t):
    M = np.eye(4)
    M[:3, :3] = s * R
    M[:3, 3] = t
    return M


def apply(M, p):
    return p @ M[:3, :3].T + M[:3, 3]


def base_image(o):
    for slot in o.material_slots:
        m = slot.material
        if m and m.use_nodes:
            for n in m.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED" and n.inputs["Base Color"].links:
                    src = n.inputs["Base Color"].links[0].from_node
                    if src.type == "TEX_IMAGE" and src.image:
                        return src.image
    return None


rng = np.random.default_rng(0)
P = HV[rng.choice(len(HV), N_ICP, replace=False)]
fields, meas = {}, {}
for g in GS:
    rev = json.loads((ROOT / "renders" / f"mvicw_{g}_s42.json").read_text())
    w = import_glb(D / g / "candidate_s42.glb", f"worn_{g}")
    w.data.transform(Matrix.Rotation(math.radians(90 * rev["yaw_steps"]), 4, "Z"))
    W_ = getV(w)
    # init: base -> worn by height about the floor, centred in x / y
    s0 = (W_[:, 2].max() - W_[:, 2].min()) / H
    c_w = np.array([(W_[:, 0].min() + W_[:, 0].max()) / 2, (W_[:, 1].min() + W_[:, 1].max()) / 2, W_[:, 2].min()])
    c_b = np.array([(HV[:, 0].min() + HV[:, 0].max()) / 2, (HV[:, 1].min() + HV[:, 1].max()) / 2, 0.0])
    M = mat4(s0, np.eye(3), c_w - s0 * c_b)
    wb = bvh_of(w)
    hist = []
    for it in range(40):
        X = apply(M, P)
        Q = np.array([wb.find_nearest(Vector(x))[0][:] for x in X])
        d = np.linalg.norm(Q - X, axis=1)
        keep = d <= np.quantile(d, 1 - TRIM)
        s, R, t = umeyama(P[keep], Q[keep])
        Mn = mat4(s, R, t)
        step = np.abs(apply(Mn, P) - X).max()
        M = Mn
        hist.append(float(np.median(d[keep]) * 1000))
        if step < 2e-5:
            break
    Minv = np.linalg.inv(M)
    w.data.transform(Matrix(Minv.tolist()))
    w.data.update()
    bpy.ops.object.select_all(action="DESELECT")
    w.select_set(True)
    bpy.context.view_layer.objects.active = w
    bpy.ops.export_scene.gltf(filepath=str(D / g / "aligned.glb"), export_format="GLB", use_selection=True,
                              export_yup=True)
    wb = bvh_of(w)
    img = base_image(w)
    px = None
    if img is not None:
        iw, ih = img.size
        px = np.array(img.pixels[:]).reshape(ih, iw, -1)[..., :3]
    uvl = w.data.uv_layers.active.data if w.data.uv_layers.active else None
    ease = np.full(len(BV), np.nan)
    rgb = np.full((len(BV), 3), np.nan)
    for i, (v, n) in enumerate(zip(BV, BN)):
        o = Vector(v + n * RAY0)
        hit, hn, fi, dist = wb.ray_cast(o, Vector(-n), RAY0 + 0.05)
        if hit is None:
            continue
        ease[i] = RAY0 - dist
        if px is not None and uvl is not None:
            poly = w.data.polygons[fi]
            uv = np.mean([uvl[li].uv[:] for li in poly.loop_indices], axis=0)
            rgb[i] = px[min(ih - 1, max(0, int(uv[1] * ih))), min(iw - 1, max(0, int((uv[0] % 1) * iw)))]
    fields[g] = (ease, rgb)
    np.savez_compressed(D / f"{g}_ease.npz", ease=ease, rgb=rgb)
    scale = float(np.cbrt(np.linalg.det(Minv[:3, :3])))
    meas[g] = {"align": {"iterations": len(hist), "median_mm_kept": round(hist[-1], 2), "scale_to_base": round(scale, 4),
                         "rot_deg": [round(math.degrees(a), 2) for a in Matrix(Minv.tolist()).to_euler()]}}
    WA = getV(w)
    if g in ZONES:                              # accessories: worn points well off the body, in the zone
        bb = bvh_of(body)
        off = np.array([bb.find_nearest(Vector(p))[3] for p in WA])
        if g == "hat":
            zmask = WA[:, 2] > H * 0.86
        else:
            zmask = (WA[:, 2] > H * 0.72) & (WA[:, 2] < H * 0.84) & (WA[:, 1] < 0.0)
        pts = WA[zmask & (off > 0.01)]
        if len(pts):
            lo, hi_ = pts.min(0), pts.max(0)
            meas[g]["box_m"] = [lo.round(3).tolist(), hi_.round(3).tolist()]
            meas[g]["size_m"] = (hi_ - lo).round(3).tolist()
            meas[g]["points"] = int(len(pts))
    bpy.data.objects.remove(w)
    print("ALIGNED", g, json.dumps(meas[g]["align"]), flush=True)

# ---- garment = difference from the baseline panel ---------------------------------------------------------
eb, cb = fields[BASELINE]
summary = {}
for g in GS:
    if g == BASELINE:
        continue
    e, c = fields[g]
    delta = e - eb
    cdist = np.abs(c - cb).max(axis=1)
    cov = ((delta > COVER_MM / 1000) | (cdist > COVER_RGB)) & ~np.isnan(delta)
    regs = {}
    for r in REGIONS:
        m = REG == r
        if not m.any():
            continue
        mc = m & cov
        frac = float(mc.sum() / m.sum())
        if frac < 0.05:
            continue
        dd = delta[mc] * 1000
        regs[r] = {"cover": round(frac, 2), "ease_mm_p50": round(float(np.nanpercentile(dd, 50)), 1),
                   "ease_mm_p90": round(float(np.nanpercentile(dd, 90)), 1),
                   "z_m": [round(float(BV[mc, 2].min()), 3), round(float(BV[mc, 2].max()), 3)]}
    meas[g]["regions"] = regs
    meas[g]["covered_z_m"] = [round(float(BV[cov, 2].min()), 3), round(float(BV[cov, 2].max()), 3)] if cov.any() else None
    np.savez_compressed(D / f"{g}_garment.npz", delta=delta, covered=cov, rgb=c)
    summary[g] = (delta, cov)
    print("MEASURE", g, json.dumps({k: v for k, v in meas[g].items() if k != "align"}), flush=True)
(D / "measure.json").write_text(json.dumps(meas, indent=1), encoding="utf-8")

# ---- sheet: body coloured by delta ease where covered ---------------------------------------------------------
bpy.data.objects.remove(hi)
me = body.data
if "ease" not in me.color_attributes:
    me.color_attributes.new("ease", "FLOAT_COLOR", "POINT")
attr = me.color_attributes["ease"]
mat = bpy.data.materials.new("ease")
mat.use_nodes = True
nt = mat.node_tree
ca = nt.nodes.new("ShaderNodeVertexColor")
ca.layer_name = "ease"
bs = nt.nodes["Principled BSDF"]
nt.links.new(ca.outputs["Color"], bs.inputs["Base Color"])
body.data.materials.clear()
body.data.materials.append(mat)
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x, sc.render.resolution_y = 300, 520
wd = bpy.data.worlds.new("w")
wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.9, 0.9, 1)
sc.world = wd
for i, (rot, en) in enumerate([((50, 0, 30), 3.0), ((60, 0, 200), 1.5)]):
    L = bpy.data.objects.new(f"l{i}", bpy.data.lights.new(f"l{i}", "SUN"))
    L.data.energy = en
    L.rotation_euler = [math.radians(a) for a in rot]
    sc.collection.objects.link(L)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = 1.9
sc.collection.objects.link(cam)
sc.camera = cam


def ramp(x):                                   # 0 -> blue, 25 mm -> green, 50+ mm -> red
    t = min(1.0, max(0.0, x / 0.05))
    return (t * 2 - 1 if t > 0.5 else 0.0, 1 - abs(t - 0.5) * 2, 1 - 2 * t if t < 0.5 else 0.0)


tiles = []
for g, (delta, cov) in summary.items():
    cols = np.zeros((len(BV), 4))
    cols[:] = (0.55, 0.55, 0.55, 1)
    for i in np.where(cov)[0]:
        cols[i, :3] = ramp(max(0.0, float(np.nan_to_num(delta[i]))))
    attr.data.foreach_set("color", cols.ravel())
    for view, az in (("front", 0), ("side", 90), ("back", 180)):
        a = math.radians(az)
        d = Vector((math.sin(a), -math.cos(a), 0.05)).normalized()
        cam.location = Vector((0, 0, 0.85)) + d * 6
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        p = ROOT / "renders" / "_tmp" / f"mvicw_measure_{g}_{view}.png"
        sc.render.filepath = str(p)
        bpy.ops.render.render(write_still=True)
        tiles.append(p)
print("TILES", json.dumps([str(t) for t in tiles]))
