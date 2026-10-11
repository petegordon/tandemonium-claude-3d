"""P3.4 check: the body + every game shell of an outfit, rendered together.

  blender -b --factory-startup --python scripts/assemble_outfit.py -- --char outfit_male [--green]

Body = base game mesh (or the fitted shape, chars json "body_shape"), textured as the base goose,
or flat green with --green (green on the outfit = body showing through). Shells from
out/<char>-goose/shells/*.glb. Writes renders/<char>_assembled[_green].png (4 views + head/chest,
hands, back-hem close-ups) and prints the triangle total.
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Euler, Vector

sys.path.insert(0, str(Path(__file__).parent))
import bodyshape  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1]
GREEN = "--green" in argv
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{CHAR}-goose"
RES = 640


def load(path):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [o for o in bpy.context.scene.objects if o not in before]


bpy.ops.wm.read_factory_settings(use_empty=True)
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text())
rig = load(ROOT / "out" / "base-goose" / "base_goose_rigged.glb")
arm = next(o for o in rig if o.type == "ARMATURE")
body = next(o for o in rig if o.type == "MESH" and o.name.startswith("base_goose_game"))
if cfg.get("body_shape", "base") != "base":
    names = [g.name for g in body.vertex_groups]
    V = np.array([v.co[:] for v in body.data.vertices])
    W = np.zeros((len(V), len(names)))
    for v in body.data.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
    body.data.vertices.foreach_set("co", bodyshape.deform(V, W, names, arm, bodyshape.body_transforms(ROOT, CHAR, arm)).ravel())
    body.data.update()
for m in list(body.modifiers):
    body.modifiers.remove(m)
if GREEN:
    g = bpy.data.materials.new("green")
    g.use_nodes = True
    g.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.1, 0.9, 0.2, 1)
    body.data.materials.clear()
    body.data.materials.append(g)
tris = 0
for f in sorted((D / "shells").glob("*.glb")):
    for o in load(f):
        if o.type == "MESH":
            tris += sum(len(p.vertices) - 2 for p in o.data.polygons)
body_tris = sum(len(p.vertices) - 2 for p in body.data.polygons)
print("TRIS shells", tris, "body", body_tris)

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
H = 1.65
tmp = ROOT / "renders" / "_tmp"
tmp.mkdir(parents=True, exist_ok=True)


def shot(yaw, zc, scale, xc=0.0):
    y = math.radians(yaw)
    cam.ortho_scale = scale
    side = Vector((math.cos(y), math.sin(y), 0)) * xc
    co.location = Vector((5 * math.sin(y), -5 * math.cos(y), zc)) + side
    co.rotation_euler = (Vector((0, 0, zc)) + side - co.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = str(tmp / "as.png")
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(sc.render.filepath)
    px = np.array(img.pixels[:]).reshape(RES, RES, 4)[::-1, :, :3]
    bpy.data.images.remove(img)
    return px


row1 = np.concatenate([shot(y, H / 2, H * 1.1) for y in (0, 90, 180, 35)], 1)
row2 = np.concatenate([shot(35, 1.35, 0.5), shot(0, 1.1, 0.5), shot(0, 0.8, 0.32, xc=-0.36),
                       shot(180, 0.65, 0.5)], 1)
sheet = np.concatenate([row1, row2], 0)
h, w_, _ = sheet.shape
img = bpy.data.images.new("sheet", w_, h)
img.pixels = np.concatenate([sheet[::-1], np.ones((h, w_, 1))], -1).ravel().tolist()
img.filepath_raw = str(ROOT / "renders" / f"{CHAR}_assembled{'_green' if GREEN else ''}.png")
img.file_format = "PNG"
img.save()
print("RENDER", img.filepath_raw)
