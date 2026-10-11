"""P3.2b (D9): fit the base goose rig bone-by-bone to an aligned outfit.

  blender -b --factory-startup --python scripts/rig_fit.py -- --char outfit_male [--no-render]

Input: out/base-goose/base_goose_rigged.glb (skinned game mesh, rest = bind pose) and
out/<char>-goose/<char>_goose_aligned.glb (align_outfit.py: outfit in the base frame, head fitted).
Inequality ICP down each chain. Per bone: base verts it dominates (weight > W_DOM) correspond
along their normal (the generated meshes are ~5 mm double-walled shells, so nearest-point snaps to
the wrong wall): a ray outward that hits the outfit within D_MAX = covered, target = that hit;
else a ray inward = poking out, target = the outfit surface below. Inliers = hit within D_MAX,
worst TRIM dropped; a fit is kept only if it beats identity; linear least squares for the 3x3 map
about the (parent-driven) bone head, then projected to rotation x (girth, length, girth) in the bone
frame and clamped. Per bone kind:
  torso (Hips/Spine*)  girth only (X and Y separately), joints stay put so the head fit holds;
  limbs (arms, legs)   rotation + length + one girth, head follows the parent's tail;
  legs                 after the fit, the boot landmark (near-black albedo: sole height + ankle-shaft
                       centre) moves the ankle; UpLeg+Leg are aimed/stretched about the hip to reach it
                       (the female's boots sit 8.5 cm below the base feet; the inequality alone never
                       pulls a covered foot down).
Tail: limb fit (tucked inside the coat/skirt; masked later, P3.5). Neck/head/face/shoulders keep identity.
The base->outfit maps shrink the base onto the outfit; the inverse carries garments onto the base.

Writes out/<char>-goose/<char>_rigfit.json (per bone: rot, length, girth, inliers, residual;
poke-through before/after by region), <char>_base_fitted.glb (base deformed onto the outfit) and
renders/<char>_rigfit_overlay.png (fitted base in green + outfit).
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).parent))
from fixes.common import input_image, read_pixels  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1]
RENDER = "--no-render" not in argv
ROOT = Path(__file__).resolve().parents[1]
RIGGED = ROOT / "out" / "base-goose" / "base_goose_rigged.glb"
OUTFIT = ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_goose_aligned.glb"
OUT_JSON = OUTFIT.with_name(f"{CHAR}_rigfit.json")
OUT_GLB = OUTFIT.with_name(f"{CHAR}_base_fitted.glb")
RENDERS = ROOT / "renders"

W_DOM = 0.6
W_DOM_TORSO = 0.35     # spine bones share the torso; few verts are > 0.6 on one of them
D_MAX = 0.04
TRIM = 0.1
MARGIN = 0.002
MIN_OBS = 0.3
ITERS = 15
MAX_ROT = math.radians(15)
LEN_RANGE = (0.8, 1.25)
GIRTH_RANGE = (0.55, 1.0)
BOOT_VAL = 0.2        # near-black albedo = boots
SOLE = 0.0075         # boot sole thickness under the base foot (male fit)
BOOT_MIN = 0.005      # only re-aim legs for a boot offset above this
RES = 640

TORSO = ["Hips", "Spine", "Spine1", "Spine2"]
CHAINS = [[f"{s}{b}" for b in ("Arm", "ForeArm", "Hand")] for s in ("Left", "Right")]
LEGS = [[f"{s}{b}" for b in ("UpLeg", "Leg", "Foot", "ToeBase")] for s in ("Left", "Right")]


def load_glb(path):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [o for o in bpy.context.scene.objects if o not in before]


bpy.ops.wm.read_factory_settings(use_empty=True)
new = load_glb(RIGGED)
arm = next(o for o in new if o.type == "ARMATURE")
body = next(o for o in new if o.type == "MESH" and o.name.startswith("base_goose_game"))
for o in new:
    if o not in (arm, body):
        bpy.data.objects.remove(o)
NAMES = [b.name for b in arm.data.bones]
BI = {n: i for i, n in enumerate(NAMES)}
HEAD0 = {b.name: np.array(arm.matrix_world @ b.head_local) for b in arm.data.bones}
TAIL0 = {b.name: np.array(arm.matrix_world @ b.tail_local) for b in arm.data.bones}
PARENT = {b.name: (b.parent.name if b.parent else None) for b in arm.data.bones}

V = np.array([body.matrix_world @ v.co for v in body.data.vertices])
NRM = np.array([(body.matrix_world.to_3x3() @ v.normal).normalized() for v in body.data.vertices])
W = np.zeros((len(V), len(NAMES)))
gidx = {g.index: g.name for g in body.vertex_groups}
for v in body.data.vertices:
    for g in v.groups:
        W[v.index, BI[gidx[g.group]]] = g.weight
W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
H = V[:, 2].max()

out_objs = [o for o in load_glb(OUTFIT) if o.type == "MESH"]
outfit = out_objs[0]
bvh = BVHTree.FromObject(outfit, bpy.context.evaluated_depsgraph_get())


def nearest(pts):
    loc = np.empty_like(pts)
    nrm = np.empty_like(pts)
    for i, p in enumerate(pts):
        l, n, _, _ = bvh.find_nearest(Vector(p))
        loc[i], nrm[i] = l, n
    return loc, nrm


def ray_target(X, N, dmax):
    """Signed offset along the normal to the outfit: + = covered (outfit outside), - = poking out."""
    s = np.full(len(X), np.nan)
    for i, (x, n) in enumerate(zip(X, N)):
        hit = bvh.ray_cast(Vector(x), Vector(n), dmax)[0]
        if hit is not None:
            s[i] = (np.array(hit) - x) @ n
            continue
        hit = bvh.ray_cast(Vector(x), Vector(-n), dmax)[0]
        if hit is not None:
            s[i] = (np.array(hit) - x) @ n
    return s


def frame(name):
    """Columns: x, y = bone axis, z (orthonormal)."""
    y = TAIL0[name] - HEAD0[name]
    y /= np.linalg.norm(y)
    ref = np.array([0.0, 0.0, 1.0]) if abs(y[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    x = np.cross(y, ref)
    x /= np.linalg.norm(x)
    return np.stack([x, y, np.cross(x, y)], 1)


def rot_clamp(R):
    ang = math.acos(np.clip((np.trace(R) - 1) / 2, -1, 1))
    if ang <= MAX_ROT:
        return R
    return np.array(Matrix(R.tolist()).to_quaternion().slerp(Matrix.Identity(3).to_quaternion(),
                                                            1 - MAX_ROT / ang).to_matrix())


def polar(A):
    U, S, Vt = np.linalg.svd(A)
    R = U @ Vt
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1
        R = U @ Vt
    return R, Vt.T @ np.diag(S) @ Vt


# fitted transform per bone: p -> head_new + A (p - head0)
FIT = {n: {"head": HEAD0[n].copy(), "A": np.eye(3)} for n in NAMES}
REPORT = {}


def apply_bone(n, p):
    return FIT[n]["head"] + (p - HEAD0[n]) @ FIT[n]["A"].T


def samples(n):
    m = W[:, BI[n]] > (W_DOM_TORSO if n in TORSO else W_DOM)
    return V[m], NRM[m]


def correspond(n, A, head):
    P, N0 = samples(n)
    X = head + (P - HEAD0[n]) @ A.T
    N = N0 @ np.linalg.inv(A)
    N /= np.linalg.norm(N, axis=1, keepdims=True)
    s = ray_target(X, N, D_MAX)
    ok = ~np.isnan(s)
    # inequality: the hidden body under a loose garment is unknown, so covered points stay put;
    # points poking out (or within MARGIN of the garment) move to MARGIN inside it
    o = np.minimum(0.0, np.nan_to_num(s) - MARGIN)
    d = np.where(ok, -o, np.inf)
    if ok.sum() > 10:
        ok &= d <= np.quantile(d[ok], 1 - TRIM)
    Q = X + N * o[:, None]
    return P, Q, d, ok


def fit_bone(n, kind, free_head=False):
    F = frame(n)
    A, head = np.eye(3), FIT[n]["head"].copy()
    P, _ = samples(n)
    if len(P) < 20:
        REPORT[n] = {"kind": kind, "observed": False, "samples": int(len(P))}
        return False
    for _ in range(ITERS):
        P, Q, d, ok = correspond(n, A, head)
        if ok.mean() < MIN_OBS:
            REPORT[n] = {"kind": kind, "observed": False, "samples": int(len(P)),
                         "inliers": round(float(ok.mean()), 3)}
            return False
        Pc = P[ok] - HEAD0[n]
        Qc = Q[ok]
        if free_head:
            X1 = np.hstack([Pc, np.ones((len(Pc), 1))])
            sol = np.linalg.lstsq(X1, Qc, rcond=None)[0]
            M, head = sol[:3].T, sol[3]
        else:
            M = np.linalg.lstsq(Pc, Qc - head, rcond=None)[0].T
        R, S = polar(M)
        s = np.diag(F.T @ S @ F).copy()
        if kind == "torso":
            R = np.eye(3)
            s[1] = 1.0
        else:
            s[0] = s[2] = (s[0] + s[2]) / 2
        s[1] = np.clip(s[1], *LEN_RANGE)
        s[[0, 2]] = np.clip(s[[0, 2]], *GIRTH_RANGE)
        A = rot_clamp(R) @ F @ np.diag(s) @ F.T
    base_head = FIT[n]["head"].copy()
    _, _, d0, ok0 = correspond(n, np.eye(3), base_head)
    P, Q, d, ok = correspond(n, A, head)
    score = lambda dd: float(np.mean(dd[np.isfinite(dd)]))     # mean push needed (poke + margin)
    if score(d) >= 0.95 * score(d0):
        REPORT[n] = {"kind": kind, "observed": True, "kept_identity": True, "samples": int(len(P)),
                     "inliers": round(float(ok0.mean()), 3),
                     "residual_mm": round(float(np.median(d0[ok0]) * 1000), 1)}
        return True
    FIT[n].update(head=head, A=A)
    R, S = polar(A)
    s = np.diag(F.T @ S @ F)
    REPORT[n] = {"kind": kind, "observed": True, "samples": int(len(P)),
                 "inliers": round(float(ok.mean()), 3),
                 "residual_mm": round(float(np.median(d[ok]) * 1000), 1),
                 "rot_deg": round(math.degrees(math.acos(np.clip((np.trace(R) - 1) / 2, -1, 1))), 1),
                 "length": round(float(s[1]), 3), "girth": [round(float(s[0]), 3), round(float(s[2]), 3)]}
    return True


def chain_head(n):
    p = PARENT[n]
    return apply_bone(p, HEAD0[n]) if p in FIT else HEAD0[n]   # rest head carried by the parent (bones may be unconnected)


for n in TORSO:
    fit_bone(n, "torso")
FIT["Tail"]["head"] = chain_head("Tail")
fit_bone("Tail", "limb")          # tuck the tail inside the coat / skirt (masked later, P3.5)
for chain in CHAINS:
    for n in chain:
        FIT[n]["head"] = chain_head(n)
        fit_bone(n, "limb")
def boot_landmark(side):
    """Outfit boot on one side (near-black albedo low on the leg): sole z + ankle-shaft centre,
    vs the same on the base foot -> translation for the Foot bone."""
    sgn = 1 if side == "Left" else -1
    m = (oco[:, 2] < 0.25) & (sgn * oco[:, 0] > 0.02) & (ovalue < BOOT_VAL)
    if m.sum() < 50:
        return None
    sole = oco[m, 2].min()
    band = m & (oco[:, 2] > sole + 0.08) & (oco[:, 2] < sole + 0.13)
    bm = ((W[:, BI[f"{side}Foot"]] + W[:, BI[f"{side}Leg"]]) > 0.5) & (V[:, 2] > 0.08) & (V[:, 2] < 0.13)
    if band.sum() < 20 or bm.sum() < 10:
        return None
    t = np.r_[oco[band, :2].mean(0) - V[bm, :2].mean(0), sole + SOLE - V[(W[:, BI[f"{side}Foot"]] +
                                                                         W[:, BI[f"{side}ToeBase"]]) > 0.5, 2].min()]
    return t


img = input_image(outfit)
px = read_pixels(img)
th, tw = px.shape[:2]
uvl = outfit.data.uv_layers.active.data
uv = np.empty(len(uvl) * 2)
uvl.foreach_get("uv", uv)
uv = uv.reshape(-1, 2)
lv = np.empty(len(outfit.data.loops), int)
outfit.data.loops.foreach_get("vertex_index", lv)
lval = px[np.clip((uv[:, 1] % 1) * th, 0, th - 1).astype(int),
          np.clip((uv[:, 0] % 1) * tw, 0, tw - 1).astype(int), :3].max(1)
ovalue = np.ones(len(outfit.data.vertices))
np.minimum.at(ovalue, lv, lval)
oco = np.array([outfit.matrix_world @ v.co for v in outfit.data.vertices])

for chain in LEGS:
    up, leg, foot, toe = chain
    side = "Left" if up.startswith("Left") else "Right"
    for n in (up, leg):
        FIT[n]["head"] = chain_head(n)
        fit_bone(n, "limb")
    t = boot_landmark(side)
    REPORT[f"{side}Boot"] = {"translation_mm": None if t is None else [round(float(x) * 1000, 1) for x in t]}
    if t is not None and np.linalg.norm(t) > BOOT_MIN:
        # aim + stretch the fitted leg about the hip so the ankle reaches the boot
        hip = HEAD0[up]
        a = chain_head(foot) - hip
        b = HEAD0[foot] + t - hip
        Rm = np.array(Vector(a).rotation_difference(Vector(b)).to_matrix())
        k = np.linalg.norm(b) / np.linalg.norm(a)
        ah = a / np.linalg.norm(a)
        G = Rm @ (np.eye(3) + (k - 1) * np.outer(ah, ah))
        for n in (up, leg):
            FIT[n]["A"] = G @ FIT[n]["A"]
            FIT[n]["head"] = hip + G @ (FIT[n]["head"] - hip)
            REPORT[n].update(aimed_at_boot=True, leg_stretch=round(float(k), 3),
                             leg_aim_deg=round(math.degrees(Vector(a).angle(Vector(b))), 1))
    for n in (foot, toe):
        FIT[n]["head"] = chain_head(n)
        fit_bone(n, "limb")

# children of fitted bones that were not fitted themselves follow rigidly (none of the face/neck)


def deform(P, Wt):
    out = np.zeros_like(P)
    for n, i in BI.items():
        w = Wt[:, i]
        m = w > 0
        if m.any():
            out[m] += w[m, None] * apply_bone(n, P[m])
    return out


def vertex_normals(P):
    me = bpy.data.meshes.new("tmp")
    me.from_pydata(P.tolist(), [], [list(p.vertices) for p in body.data.polygons])
    me.update()
    N = np.array([v.normal[:] for v in me.vertices])
    bpy.data.meshes.remove(me)
    return N


def poke_table(P):
    """Per region: share of body points poking out of the outfit (no outfit within 0.3 m along
    the outward normal) and their depth (inward ray to the outfit, cap 0.15 m)."""
    N = vertex_normals(P)
    out = np.zeros(len(P), bool)
    depth = np.full(len(P), np.nan)
    for i, (x, n) in enumerate(zip(P, N)):
        if bvh.ray_cast(Vector(x), Vector(n), 0.3)[0] is None:
            out[i] = True
            hit = bvh.ray_cast(Vector(x), Vector(-n), 0.15)[0]
            depth[i] = np.linalg.norm(np.array(hit) - x) * 1000 if hit is not None else 150.0
    x, z = np.abs(V[:, 0]), V[:, 2] / H
    regions = {"feet": z < .06, "boots_shins": (z >= .06) & (z < .25),
               "thighs_hips": (z >= .25) & (z < .48) & (x < .15 * H / 1.65),
               "hands_forearms": (x >= .15 * H / 1.65) & (z < .80), "torso": (z >= .48) & (z < .80) & (x < .15 * H / 1.65),
               "head_neck": z >= .80}
    res = {}
    for k, m in regions.items():
        po = depth[m & out]
        po = po[po > 3]
        res[k] = {"outside_gt3mm": round(float(len(po) / max(1, m.sum())), 3),
                  "poke_median_mm": round(float(np.median(po)), 1) if len(po) else 0.0,
                  "poke_p90_mm": round(float(np.percentile(po, 90)), 1) if len(po) else 0.0}
    return res


before = poke_table(V)
Vf = deform(V, W)
after = poke_table(Vf)
report = {"char": CHAR, "bones": REPORT, "poke_before": before, "poke_after": after,
          "transforms": {n: {"head": [round(float(x), 5) for x in FIT[n]["head"]],
                             "A": [[round(float(x), 6) for x in r] for r in FIT[n]["A"]]}
                         for n in NAMES if not np.allclose(FIT[n]["A"], np.eye(3)) or
                         not np.allclose(FIT[n]["head"], HEAD0[n])}}
OUT_JSON.write_text(json.dumps(report, indent=1))
print("RIGFIT", json.dumps({k: report[k] for k in ("bones", "poke_before", "poke_after")}))

# fitted base mesh
me = bpy.data.meshes.new("base_fitted")
me.from_pydata(Vf.tolist(), [], [list(p.vertices) for p in body.data.polygons])
fitted = bpy.data.objects.new("base_fitted", me)
bpy.context.scene.collection.objects.link(fitted)
bpy.ops.object.select_all(action="DESELECT")
fitted.select_set(True)
bpy.context.view_layer.objects.active = fitted
bpy.ops.export_scene.gltf(filepath=str(OUT_GLB), use_selection=True, export_format="GLB")

if RENDER:
    for o in (arm, body):
        o.hide_render = True
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.view_settings.view_transform = "Standard"
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.92, 0.92, 0.92, 1)
    sc.world = w
    for i, (r, e) in enumerate([((50, 0, 30), 3.0), ((60, 0, 200), 1.5)]):
        L = bpy.data.lights.new(f"l{i}", "SUN")
        L.energy = e
        lo = bpy.data.objects.new(f"l{i}", L)
        lo.rotation_euler = Euler([math.radians(a) for a in r])
        sc.collection.objects.link(lo)
    cam = bpy.data.cameras.new("cam")
    cam.type = "ORTHO"
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    green = bpy.data.materials.new("body_green")
    green.use_nodes = True
    green.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.1, 0.9, 0.2, 1)
    fitted.data.materials.append(green)
    bpy.ops.object.shade_smooth()
    rows = []
    tmp = RENDERS / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    for j, yaw in enumerate((0, 90, 180, 35)):
        y = math.radians(yaw)
        cam.ortho_scale = H * 1.1
        co.location = Vector((5 * math.sin(y), -5 * math.cos(y), H / 2))
        co.rotation_euler = (Vector((0, 0, H / 2)) - co.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = str(tmp / f"rf_{j}.png")
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(sc.render.filepath)
        rows.append(np.array(img.pixels[:]).reshape(RES, RES, 4)[::-1, :, :3])
        bpy.data.images.remove(img)
    row = np.concatenate(rows, 1)
    h, w_, _ = row.shape
    img = bpy.data.images.new("sheet", w_, h)
    img.pixels = np.concatenate([row[::-1], np.ones((h, w_, 1))], -1).ravel().tolist()
    img.filepath_raw = str(RENDERS / f"{CHAR}_rigfit_overlay.png")
    img.file_format = "PNG"
    img.save()
    print("RENDER", img.filepath_raw)
