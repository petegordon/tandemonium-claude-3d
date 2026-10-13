"""Beauty renders of a dressed goose (dress_goose.py output): front, 3/4, side, rear, 3/4 back -- one sheet.

  blender -b --factory-startup --python scripts/outfit_beauty.py -- --glb out/<char>-goose/<char>_<tag>_dressed.glb
      --out renders/outfits/<name>.png [--title "..."] [--px 900]

Perspective camera (50 mm) at eye level, three-point lighting (key, fill, rim) on a soft grey studio floor and backdrop,
Filmic-ish "AgX" view transform, EEVEE with soft shadows. Each tile frames the whole goose (hat to boots).
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
GLB = ROOT / opt("--glb", "")
OUT = ROOT / opt("--out", "renders/outfits/outfit.png")
PX = opt("--px", 900)
OUT.parent.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
for o in meshes:                      # as the game shows a fully worn outfit: layered sub-meshes (the body parts a
    if "__" in o.name:                # garment covers, e.g. "body__breeches") are hidden
        o.hide_render = o.hide_viewport = True
pts = np.concatenate([np.array([(o.matrix_world @ v.co)[:] for v in list(o.data.vertices)[::7]]) for o in meshes if o.visible_get() and len(o.data.vertices)])
lo, hi = pts.min(0), pts.max(0)
H = hi[2] - lo[2]
ctr = Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2] + H * 0.5))
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
try:
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
except TypeError:
    sc.view_settings.view_transform = "Filmic"
sc.render.resolution_x, sc.render.resolution_y = int(PX * 0.62), PX
wd = bpy.data.worlds.new("w")
wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.56, 0.58, 1)
wd.node_tree.nodes["Background"].inputs[1].default_value = 0.5
sc.world = wd
bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, lo[2] - 0.001))
floor = bpy.context.object
fm = bpy.data.materials.new("floor")
fm.use_nodes = True
fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.36, 0.35, 0.34, 1)
fm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.85
floor.data.materials.append(fm)


def light(name, kind, energy, loc, size=1.0, color=(1, 1, 1)):
    L = bpy.data.lights.new(name, kind)
    L.energy = energy
    L.color = color
    if kind == "AREA":
        L.size = size
    o = bpy.data.objects.new(name, L)
    o.location = loc
    o.rotation_euler = (ctr - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(o)
    return o


cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.lens = 50
sc.collection.objects.link(cam)
sc.camera = cam
dist = H * 1.75
tiles = []
for name, az in (("front", 0), ("q34", 35), ("side", 90), ("rear", 180), ("q34b", 215)):
    for o in [o for o in sc.objects if o.type == "LIGHT"]:
        bpy.data.objects.remove(o)
    a = math.radians(az)
    d = Vector((math.sin(a), -math.cos(a), 0.0))
    side = Vector((math.cos(a), math.sin(a), 0.0))
    light("key", "AREA", 900, tuple(ctr + d * 3 + side * 2.2 + Vector((0, 0, 2.2))), 2.0, (1.0, 0.96, 0.9))
    light("fill", "AREA", 300, tuple(ctr + d * 3 - side * 2.5 + Vector((0, 0, 0.6))), 3.0, (0.9, 0.94, 1.0))
    light("rim", "AREA", 700, tuple(ctr - d * 3 + side * 0.8 + Vector((0, 0, 2.0))), 1.5)
    cam.location = ctr + d * dist + Vector((0, 0, 0.12))
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
    p = OUT.parent / f"_{OUT.stem}_{name}.png"
    sc.render.filepath = str(p)
    bpy.ops.render.render(write_still=True)
    tiles.append(p)
imgs = [bpy.data.images.load(str(p)) for p in tiles]
w, h = imgs[0].size
sheet = np.zeros((h, w * len(imgs), 4))
for i, im in enumerate(imgs):
    sheet[:, i * w:(i + 1) * w] = np.array(im.pixels[:]).reshape(h, w, 4)
out = bpy.data.images.new("sheet", w * len(imgs), h)
out.pixels = sheet.ravel().tolist()
out.filepath_raw = str(OUT)
out.file_format = "PNG"
out.save()
print("BEAUTY", OUT)
