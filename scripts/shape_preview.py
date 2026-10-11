"""Preview a character's slider body shape (bodyshape.py) against the base body and its rig-fit.

  blender -b --factory-startup --python scripts/shape_preview.py -- --char outfit_female

Row 1: base | rig-fit | sliders, front and side (flat grey). Row 2: slider body (green) inside the
aligned outfit, 4 views. Prints poke-through of the slider body through the outfit by region (the
rig_fit.py metric: no outfit within 0.3 m along the outward normal), comparable with <char>_rigfit.json.
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Euler, Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).parent))
import bodyshape  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1]
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{CHAR}-goose"
RES = 512


def load(path):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [o for o in bpy.context.scene.objects if o not in before]


bpy.ops.wm.read_factory_settings(use_empty=True)
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text())
rig = load(ROOT / "out" / "base-goose" / "base_goose_rigged.glb")
arm = next(o for o in rig if o.type == "ARMATURE")
body = next(o for o in rig if o.type == "MESH" and o.name.startswith("base_goose_game"))
for o in rig:
    if o not in (arm, body):
        bpy.data.objects.remove(o)
for m in list(body.modifiers):
    body.modifiers.remove(m)
names = [g.name for g in body.vertex_groups]
V = np.array([v.co[:] for v in body.data.vertices])
W = np.zeros((len(V), len(names)))
for v in body.data.vertices:
    for g in v.groups:
        W[v.index, g.group] = g.weight
W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
fits = json.loads((D / f"{CHAR}_rigfit.json").read_text())["transforms"]
sl = bodyshape.slider_transforms(arm, cfg.get("shape", {}))
shapes = {"base": V, "rigfit": bodyshape.deform(V, W, names, arm, fits), "sliders": bodyshape.deform(V, W, names, arm, sl)}
H = V[:, 2].max()

outfit = next(o for o in load(D / f"{CHAR}_goose_aligned.glb") if o.type == "MESH")
bvh = BVHTree.FromObject(outfit, bpy.context.evaluated_depsgraph_get())


def set_body(P):
    body.data.vertices.foreach_set("co", P.ravel())
    body.data.update()


def poke(P):
    set_body(P)
    N = np.array([v.normal[:] for v in body.data.vertices])
    x, z = np.abs(V[:, 0]), V[:, 2] / H
    regions = {"feet": z < .06, "boots_shins": (z >= .06) & (z < .25),
               "thighs_hips": (z >= .25) & (z < .48) & (x < .15), "hands_forearms": (x >= .15) & (z < .80),
               "torso": (z >= .48) & (z < .80) & (x < .15), "head_neck": z >= .80}
    out = np.array([bvh.ray_cast(Vector(p), Vector(n), 0.3)[0] is None for p, n in zip(P, N)])
    return {k: round(float((out & m).sum() / m.sum()), 3) for k, m in regions.items()}


report = {"shape": cfg.get("shape", {}), "outside_share": {k: poke(P) for k, P in shapes.items()}}
print("SHAPE", json.dumps(report))

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
arm.hide_render = True
tmp = ROOT / "renders" / "_tmp"
tmp.mkdir(parents=True, exist_ok=True)


def shot(yaw):
    y = math.radians(yaw)
    cam.ortho_scale = H * 1.15
    co.location = Vector((5 * math.sin(y), -5 * math.cos(y), H / 2))
    co.rotation_euler = (Vector((0, 0, H / 2)) - co.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = str(tmp / "sp.png")
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(sc.render.filepath)
    px = np.array(img.pixels[:]).reshape(RES, RES, 4)[::-1, :, :3]
    bpy.data.images.remove(img)
    return px


grey = bpy.data.materials.new("grey")
grey.use_nodes = True
grey.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.6, 0.6, 0.62, 1)
body.data.materials.clear()
body.data.materials.append(grey)
outfit.hide_render = True
row1 = []
for k in ("base", "rigfit", "sliders"):
    set_body(shapes[k])
    row1 += [shot(0), shot(90)]
row1 = np.concatenate(row1, 1)
green = grey.node_tree.nodes["Principled BSDF"].inputs["Base Color"]
green.default_value = (0.1, 0.9, 0.2, 1)
outfit.hide_render = False
set_body(shapes["sliders"])
row2 = np.concatenate([shot(y) for y in (0, 90, 180, 35)], 1)
pad = np.ones((RES, row1.shape[1] - row2.shape[1], 3)) * 0.92
sheet = np.concatenate([row1, np.concatenate([row2, pad], 1)], 0)
h, w_, _ = sheet.shape
img = bpy.data.images.new("sheet", w_, h)
img.pixels = np.concatenate([sheet[::-1], np.ones((h, w_, 1))], -1).ravel().tolist()
img.filepath_raw = str(ROOT / "renders" / f"{CHAR}_shape_preview.png")
img.file_format = "PNG"
img.save()
print("RENDER", img.filepath_raw)
