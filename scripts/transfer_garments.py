"""P3.4 step 1 (D9): carry each garment piece of an aligned outfit onto the base goose's rest pose.

  blender -b --factory-startup --python scripts/transfer_garments.py -- --char outfit_male [--no-render]

rig_fit.py maps the base body onto the outfit per bone: p -> h_b + A_b (p - h0_b). Here every outfit
vertex takes skin weights from its K nearest vertices of that fitted base body (inverse-distance
blend) and goes through the blended inverses h0_b + A_b^-1 (x - h_b): the garment lands on the base
body as if the base had worn it. Splits by piece (<char>_garments.npz "piece") and writes
out/<char>-goose/pieces/<piece>.glb (UVs + texture kept), <char>_outfit_on_base.glb (all pieces),
<char>_transfer.json (poke-through of the base body through the transferred outfit, by region) and
renders/<char>_transfer_overlay.png (base body green + transferred outfit).
chars/<char>.json "body_shape": "base" (default, D1: clothes move onto the shared base body) or
"fitted" (D11: the character wears its rig-fit body; clothes stay where they are) or "sliders"
(bodyshape.py: clothes go inverse rig-fit -> base rest -> forward slider shape).
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

sys.path.insert(0, str(Path(__file__).parent))
import bodyshape  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1]
RENDER = "--no-render" not in argv
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{CHAR}-goose"
RENDERS = ROOT / "renders"
K = 4
LOOSE_D0, LOOSE_D1 = 0.015, 0.035
RES = 640


def load(path):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [o for o in bpy.context.scene.objects if o not in before]


bpy.ops.wm.read_factory_settings(use_empty=True)
rig = load(ROOT / "out" / "base-goose" / "base_goose_rigged.glb")
arm = next(o for o in rig if o.type == "ARMATURE")
body = next(o for o in rig if o.type == "MESH" and o.name.startswith("base_goose_game"))
names = [g.name for g in body.vertex_groups]
V = np.array([body.matrix_world @ v.co for v in body.data.vertices])
NRM = np.array([(body.matrix_world.to_3x3() @ v.normal).normalized() for v in body.data.vertices])
W = np.zeros((len(V), len(names)))
for v in body.data.vertices:
    for g in v.groups:
        W[v.index, g.group] = g.weight
W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
H = V[:, 2].max()
FITS = json.loads((D / f"{CHAR}_rigfit.json").read_text())["transforms"]
H0 = {n: np.array(arm.matrix_world @ arm.data.bones[n].head_local) for n in names}
fitted_idx = [i for i, n in enumerate(names) if n in FITS]
HN = {n: np.array(FITS[n]["head"]) for n in FITS}
AA = {n: np.array(FITS[n]["A"]) for n in FITS}
AI = {n: np.linalg.inv(AA[n]) for n in FITS}

# fitted base body (forward map) for the weight lookup
F = V.copy()
for i in fitted_idx:
    n = names[i]
    m = W[:, i] > 0
    F[m] += W[m, i, None] * ((HN[n] + (V[m] - H0[n]) @ AA[n].T) - V[m])

outfit = next(o for o in load(D / f"{CHAR}_goose_aligned.glb") if o.type == "MESH")
bpy.context.view_layer.objects.active = outfit
outfit.select_set(True)
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = outfit.data
X = np.empty(len(me.vertices) * 3)
me.vertices.foreach_get("co", X)
X = X.reshape(-1, 3)

kd = KDTree(len(F))
for i, c in enumerate(F):
    kd.insert(c, i)
kd.balance()
Wo = np.zeros((len(X), len(names)))
dmin = np.zeros(len(X))
for i, x in enumerate(X):
    hits = kd.find_n(x, K)
    w = np.array([1.0 / max(d, 1e-4) for _, _, d in hits])
    Wo[i] = (w[:, None] * W[[j for _, j, _ in hits]]).sum(0) / w.sum()
    dmin[i] = hits[0][2]
# loose cloth (skirt, bustle, coat tails) hangs from the pelvis, not the legs: weights blend to Hips
# from LOOSE_D0 to LOOSE_D1 off the body (leg weights round-tripped through two leg maps flared the hem)
leg = np.array([n.endswith(("UpLeg", "Leg", "Foot", "ToeBase")) for n in names])
tl = np.clip((dmin - LOOSE_D0) / (LOOSE_D1 - LOOSE_D0), 0, 1) * (Wo[:, leg].sum(1) > 0.5)
hips = np.zeros(len(names))
hips[names.index("Hips")] = 1.0
Wo = (1 - tl)[:, None] * Wo + tl[:, None] * hips
print("LOOSE verts on Hips", round(float((tl > 0.5).mean()), 3))

SHAPE = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text()).get("body_shape", "base")
Xr = X.copy()
for i in (fitted_idx if SHAPE != "fitted" else []):   # "fitted": the character wears its own rig-fit body
    n = names[i]
    m = Wo[:, i] > 0
    Xr[m] += Wo[m, i, None] * ((H0[n] + (X[m] - HN[n]) @ AI[n].T) - X[m])
WORN = bodyshape.body_transforms(ROOT, CHAR, arm)
if SHAPE == "sliders":                                  # then onto the slider body, same skin weights
    Xr = bodyshape.deform(Xr, Wo, names, arm, WORN)
me.vertices.foreach_set("co", Xr.ravel())
me.update()
moved = np.linalg.norm(Xr - X, axis=1)
print("MOVED median/p90/max mm", np.round(np.percentile(moved, [50, 90, 100]) * 1000, 1).tolist())

G = np.load(D / f"{CHAR}_garments.npz")
piece, pnames = G["piece"], [str(n) for n in G["piece_names"]]
assert len(piece) == len(me.polygons)

if SHAPE != "base":                            # the body the clothes sit on: fitted / slider shape
    V = bodyshape.deform(V, W, names, arm, WORN)
    me_b = body.data
    me_b.vertices.foreach_set("co", (V @ np.linalg.inv(np.array(body.matrix_world.to_3x3())).T).ravel())
    me_b.update()
    NRM = np.array([(body.matrix_world.to_3x3() @ v.normal).normalized() for v in me_b.vertices])
# poke-through of the base body through the whole transferred outfit (same metric as rig_fit.py)
bvh = BVHTree.FromObject(outfit, bpy.context.evaluated_depsgraph_get())
x_abs, z_rel = np.abs(V[:, 0]), V[:, 2] / H
regions = {"feet": z_rel < .06, "boots_shins": (z_rel >= .06) & (z_rel < .25),
           "thighs_hips": (z_rel >= .25) & (z_rel < .48) & (x_abs < .15),
           "hands_forearms": (x_abs >= .15) & (z_rel < .80), "torso": (z_rel >= .48) & (z_rel < .80) & (x_abs < .15),
           "head_neck": z_rel >= .80}
out_mask = np.zeros(len(V), bool)
depth = np.zeros(len(V))
for i, (p, n) in enumerate(zip(V, NRM)):
    if bvh.ray_cast(Vector(p), Vector(n), 0.3)[0] is None:
        out_mask[i] = True
        hit = bvh.ray_cast(Vector(p), Vector(-n), 0.15)[0]
        depth[i] = np.linalg.norm(np.array(hit) - p) * 1000 if hit is not None else 150.0
poke = {}
for k, m in regions.items():
    po = depth[m & out_mask]
    po = po[po > 3]
    poke[k] = {"outside_gt3mm": round(float(len(po) / max(1, m.sum())), 3),
               "poke_median_mm": round(float(np.median(po)), 1) if len(po) else 0.0}
report = {"char": CHAR, "body_shape": SHAPE, "moved_mm": np.round(np.percentile(moved, [50, 90, 100]) * 1000, 1).tolist(),
          "poke_base_through_outfit": poke}
(D / f"{CHAR}_transfer.json").write_text(json.dumps(report, indent=1))
print("TRANSFER", json.dumps(report))

# exports: whole outfit + one GLB per piece
bpy.ops.object.select_all(action="DESELECT")
outfit.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(D / f"{CHAR}_outfit_on_base.glb"), use_selection=True, export_format="GLB")
(D / "pieces").mkdir(exist_ok=True)
for pi, pn in enumerate(pnames):
    if pn in ("other", "body") or not (piece == pi).any():
        continue
    ob = outfit.copy()
    ob.data = me.copy()
    bpy.context.scene.collection.objects.link(ob)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if piece[f.index] != pi], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(ob.data)
    bm.free()
    ob.name = pn
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(D / "pieces" / f"{pn}.glb"), use_selection=True, export_format="GLB")
    print("PIECE", pn, len(ob.data.polygons), "faces")
    bpy.data.objects.remove(ob)

if RENDER:
    arm.hide_render = True
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
    green = bpy.data.materials.new("green")
    green.use_nodes = True
    green.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.1, 0.9, 0.2, 1)
    body.data.materials.clear()
    body.data.materials.append(green)
    for o in sc.objects:
        if o.type == "MESH" and o not in (body, outfit):
            o.hide_render = True
    shots = []
    tmp = RENDERS / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    for j, yaw in enumerate((0, 90, 180, 35)):
        y = math.radians(yaw)
        cam.ortho_scale = H * 1.12
        co.location = Vector((5 * math.sin(y), -5 * math.cos(y), H / 2))
        co.rotation_euler = (Vector((0, 0, H / 2)) - co.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = str(tmp / f"tr_{j}.png")
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(sc.render.filepath)
        shots.append(np.array(img.pixels[:]).reshape(RES, RES, 4)[::-1, :, :3])
        bpy.data.images.remove(img)
    row = np.concatenate(shots, 1)
    h, w_, _ = row.shape
    img = bpy.data.images.new("sheet", w_, h)
    img.pixels = np.concatenate([row[::-1], np.ones((h, w_, 1))], -1).ravel().tolist()
    img.filepath_raw = str(RENDERS / f"{CHAR}_transfer_overlay.png")
    img.file_format = "PNG"
    img.save()
    print("RENDER", img.filepath_raw)
