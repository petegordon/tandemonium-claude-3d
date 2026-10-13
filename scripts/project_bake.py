"""Texture a built garment from Pete's drawings: bake the four calibrated reference views onto the garment's UVs.

  blender -b --factory-startup --python scripts/project_bake.py -- --piece breeches [--ref breeches]
      [--char outfit_male_victorian] [--tex 2048] [--tag v1] [--power 2.0]

Inputs: out/<char>-goose/shells/<piece>.glb (built by make_garment & co., UV-unwrapped), the reference views
out/outfit_male_victorian/dressed/<ref>/<view>_garment.png (RGBA: alpha = garment, drawn pixels warped part by part
onto OUR body, refs/key_views/cameras.json cameras). Per vertex and view: weight = max(0, n . to-camera)^power x
visible (a ray toward the camera meets neither the base body nor the garment itself); each view's UVs = the vertex's
pixel in that view. A Cycles emission bake blends sum(w x alpha x colour) / sum(w x alpha) into the garment's own UVs;
a second bake keeps the weight sum (coverage). Texels no view covers are filled from their neighbours (push-pull).
The result replaces the garment's base colour (its normal map stays): out/<char>-goose/versions/<piece>_<tag>.glb and
its texture <piece>_<tag>_albedo.png; also out/<char>-goose/shells/<piece>.glb unless --no-install.
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_victorian")
PIECE = opt("--piece", "breeches")
REF = opt("--ref", {"waistcoat": "vest", "coat": "jacket", "gloves": "glove", "bowtie": "bow_tie"}.get(PIECE, PIECE))
TEX = opt("--tex", 2048)
TAG = opt("--tag", "v1")
POWER = opt("--power", 2.0)
INSTALL = "--no-install" not in argv
D = ROOT / "out" / f"{CHAR}-goose"
RD = ROOT / "out" / "outfit_male_victorian" / "dressed" / REF
VD = D / "versions"
VD.mkdir(parents=True, exist_ok=True)
CAM = json.loads((ROOT / "refs" / "key_views" / "cameras.json").read_text(encoding="utf-8"))
W0, H0 = CAM["size_px"]
PPM = CAM["px_per_m"]
TGT = np.array(CAM["target"])
VIEWS = [v for v in ("front", "left", "rear", "right") if (RD / f"{v}_garment.png").exists()]

bpy.ops.wm.read_factory_settings(use_empty=True)
# (an empty scene + the body appended: baking in the opened base_goose.blend scene fails "No valid selected objects")
with bpy.data.libraries.load(str(ROOT / "out" / "base-goose" / "base_goose.blend")) as (src, dst):
    dst.objects = ["base_goose_game"]
body = dst.objects[0]
bpy.context.scene.collection.objects.link(body)
for m in list(body.modifiers):
    body.modifiers.remove(m)
body.parent = None
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(D / "shells" / f"{PIECE}.glb"))
gar = next(o for o in bpy.data.objects if o not in before and o.type == "MESH")
bpy.ops.object.select_all(action="DESELECT")
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = gar.data
base_uv = me.uv_layers.active.name

# occluders: the base body and the garment itself
BV = [v.co.copy() for v in body.data.vertices]
GV = [v.co.copy() for v in me.vertices]
polys = [tuple(p.vertices) for p in body.data.polygons] + [tuple(i + len(BV) for i in p.vertices) for p in me.polygons]
OCC = BVHTree.FromPolygons(BV + GV, polys)
P = np.array([v.co[:] for v in me.vertices])
N = np.array([v.normal[:] for v in me.vertices])
loops_v = np.array([l.vertex_index for l in me.loops])
cover_stats = {}
for view in VIEWS:
    c = CAM["views"][view]
    R, U, B = np.array(c["right"]), np.array(c["up"]), np.array(c["back"])
    facing = np.clip(N @ B, 0, 1) ** POWER
    vis = np.zeros(len(P))
    for i in np.where(facing > 1e-4)[0]:
        o = Vector(P[i] + N[i] * 0.003 + B * 0.001)
        hit = OCC.ray_cast(o, Vector(B), 5.0)
        vis[i] = 0.0 if hit[0] is not None else 1.0
    w = facing * vis
    cover_stats[view] = round(float((w > 0.05).mean()), 3)
    rel = P - TGT
    x = W0 / 2 + rel @ R * PPM
    y = H0 / 2 - rel @ U * PPM
    uv = np.stack([x / W0, 1 - y / H0], 1)
    lay = me.uv_layers.new(name=f"pv_{view}")
    lay.data.foreach_set("uv", uv[loops_v].ravel())
    att = me.color_attributes.new(f"w_{view}", "FLOAT_COLOR", "POINT")
    att.data.foreach_set("color", np.repeat(w[:, None], 4, 1).ravel())
me.uv_layers.active = me.uv_layers[base_uv]
for i, l in enumerate(me.uv_layers):
    l.active_render = (l.name == base_uv)
print("COVER (verts seen > 0.05)", cover_stats, flush=True)

# bake material: sum_v w_v * a_v * rgb_v  and  sum_v w_v * a_v
mat = bpy.data.materials.new("projbake")
mat.use_nodes = True
nt = mat.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
out = nt.nodes.new("ShaderNodeOutputMaterial")
em = nt.nodes.new("ShaderNodeEmission")
nt.links.new(em.outputs[0], out.inputs[0])
acc_c, acc_w = None, None
for view in VIEWS:
    img = bpy.data.images.load(str(RD / f"{view}_garment.png"))
    img.colorspace_settings.name = "sRGB"
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = img
    tx.interpolation = "Closest"
    tx.extension = "CLIP"
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = f"pv_{view}"
    nt.links.new(uvn.outputs[0], tx.inputs[0])
    at = nt.nodes.new("ShaderNodeVertexColor")
    at.layer_name = f"w_{view}"
    wv = nt.nodes.new("ShaderNodeMath")
    wv.operation = "MULTIPLY"
    nt.links.new(at.outputs["Color"], wv.inputs[0])
    nt.links.new(tx.outputs["Alpha"], wv.inputs[1])
    cw = nt.nodes.new("ShaderNodeMixRGB")
    cw.blend_type = "MULTIPLY"
    cw.inputs[0].default_value = 1.0
    nt.links.new(tx.outputs["Color"], cw.inputs[1])
    nt.links.new(wv.outputs[0], cw.inputs[2])
    if acc_c is None:
        acc_c, acc_w = cw.outputs[0], wv.outputs[0]
    else:
        ac = nt.nodes.new("ShaderNodeMixRGB")
        ac.blend_type = "ADD"
        ac.inputs[0].default_value = 1.0
        nt.links.new(acc_c, ac.inputs[1])
        nt.links.new(cw.outputs[0], ac.inputs[2])
        aw = nt.nodes.new("ShaderNodeMath")
        aw.operation = "ADD"
        nt.links.new(acc_w, aw.inputs[0])
        nt.links.new(wv.outputs[0], aw.inputs[1])
        acc_c, acc_w = ac.outputs[0], aw.outputs[0]
sel = nt.nodes.new("ShaderNodeMixRGB")          # colour pass / weight pass switch
sel.blend_type = "MIX"
nt.links.new(acc_c, sel.inputs[1])
gw = nt.nodes.new("ShaderNodeCombineColor")
nt.links.new(acc_w, gw.inputs[0])
nt.links.new(acc_w, gw.inputs[1])
nt.links.new(acc_w, gw.inputs[2])
nt.links.new(gw.outputs[0], sel.inputs[2])
nt.links.new(sel.outputs[0], em.inputs["Color"])
old_mats = [s.material for s in gar.material_slots]
gar.data.materials.clear()
gar.data.materials.append(mat)
tgt = nt.nodes.new("ShaderNodeTexImage")
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = 1
sc.cycles.device = "CPU"
res = {}
for pas, fac in (("color", 0.0), ("weight", 1.0)):
    sel.inputs[0].default_value = fac
    im = bpy.data.images.new(f"bake_{pas}", TEX, TEX, alpha=False, float_buffer=True)
    im.colorspace_settings.name = "Non-Color"
    tgt.image = im
    nt.nodes.active = tgt
    bpy.ops.object.select_all(action="DESELECT")
    gar.select_set(True)
    bpy.context.view_layer.objects.active = gar
    bpy.ops.object.bake(type="EMIT", margin=0, use_clear=True)
    res[pas] = np.array(im.pixels[:]).reshape(TEX, TEX, 4)[..., :3]
wsum = res["weight"][..., 0]
covered = wsum > 0.02
col = np.where(covered[..., None], res["color"] / np.maximum(wsum[..., None], 1e-6), 0)
# the bake ran on sRGB-decoded (linear) texels; keep linear for the image we write as linear float, then encode
# push-pull fill of the uncovered texels (coarse-to-fine averages of the covered ones)


def pushpull(c, m):
    if c.shape[0] <= 4 or m.all():
        return np.where(m[..., None], c, c[m].mean(0) if m.any() else 0)
    h, w = c.shape[0] // 2, c.shape[1] // 2
    cs = (c[:2 * h:2, :2 * w:2] * m[:2 * h:2, :2 * w:2, None] + c[1:2 * h:2, :2 * w:2] * m[1:2 * h:2, :2 * w:2, None] +
          c[:2 * h:2, 1:2 * w:2] * m[:2 * h:2, 1:2 * w:2, None] + c[1:2 * h:2, 1:2 * w:2] * m[1:2 * h:2, 1:2 * w:2, None])
    ms = (m[:2 * h:2, :2 * w:2].astype(float) + m[1:2 * h:2, :2 * w:2] + m[:2 * h:2, 1:2 * w:2] + m[1:2 * h:2, 1:2 * w:2])
    coarse = pushpull(np.where(ms[..., None] > 0, cs / np.maximum(ms[..., None], 1e-9), 0), ms > 0)
    up = np.repeat(np.repeat(coarse, 2, 0), 2, 1)
    up = np.pad(up, ((0, c.shape[0] - up.shape[0]), (0, c.shape[1] - up.shape[1]), (0, 0)), mode="edge")
    return np.where(m[..., None], c, up)


fill = pushpull(col, covered)
out_img = bpy.data.images.new(f"{PIECE}_{TAG}_albedo", TEX, TEX, alpha=False)
lin = np.clip(fill, 0, 1)
srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)
out_img.pixels = np.dstack([srgb, np.ones((TEX, TEX))]).ravel().tolist()
out_img.filepath_raw = str(VD / f"{PIECE}_{TAG}_albedo.png")
out_img.file_format = "PNG"
out_img.save()
cov_frac = float(covered.mean())

# put the garment's own material back, base colour = the baked albedo (normal map etc. kept)
gar.data.materials.clear()
for m in old_mats:
    gar.data.materials.append(m)
for v in VIEWS:
    me.uv_layers.remove(me.uv_layers[f"pv_{v}"])
    me.color_attributes.remove(me.color_attributes[f"w_{v}"])
alb = bpy.data.images.load(str(VD / f"{PIECE}_{TAG}_albedo.png"))
for m in old_mats:
    if not (m and m.use_nodes):
        continue
    bs = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bs is None:
        continue
    for l in list(bs.inputs["Base Color"].links):
        m.node_tree.links.remove(l)
    t = m.node_tree.nodes.new("ShaderNodeTexImage")
    t.image = alb
    m.node_tree.links.new(t.outputs[0], bs.inputs["Base Color"])
    break                                           # (first material = the cloth; trims / linings keep theirs)
bpy.ops.object.select_all(action="DESELECT")
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
outs = [VD / f"{PIECE}_{TAG}.glb"] + ([D / "shells" / f"{PIECE}.glb"] if INSTALL else [])
for f in outs:
    bpy.ops.export_scene.gltf(filepath=str(f), export_format="GLB", use_selection=True, export_tangents=True)
print("BAKED", json.dumps({"piece": PIECE, "tag": TAG, "views": VIEWS, "texel_cover": round(cov_frac, 3),
                           "verts_seen": cover_stats, "out": [str(f) for f in outs]}))
