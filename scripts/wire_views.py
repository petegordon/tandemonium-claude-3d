"""Shaded + wireframe overlay renders of a GLB (topology review).

  blender -b --factory-startup --python scripts/wire_views.py -- <in.glb> <out.png> [yaw:zc:scale,...]
"""
import math
import sys

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
SRC, OUT = argv[0], argv[1]
SHOTS = [tuple(map(float, s.split(":"))) for s in (argv[2] if len(argv) > 2 else "0:0.5:1.1,90:0.5:1.1,35:0.85:0.35,30:0.45:0.4").split(",")]
RES = 900

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
ob = next(o for o in bpy.context.scene.objects if o.type == "MESH")
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
H = max(v.co.z for v in ob.data.vertices)
wire = ob.copy()
wire.data = ob.data.copy()
bpy.context.scene.collection.objects.link(wire)
m = wire.modifiers.new("w", "WIREFRAME")
m.thickness = 0.0012 * H
m.use_replace = True
mat = bpy.data.materials.new("wire")
mat.use_nodes = True
p = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
p.inputs["Base Color"].default_value = (0.02, 0.05, 0.12, 1)
wire.data.materials.clear()
wire.data.materials.append(mat)
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = RES
sc.view_settings.view_transform = "Standard"
sc.world = bpy.data.worlds.new("w")
sc.world.color = (0.9, 0.9, 0.9)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
cam.data.type = "ORTHO"
sc.collection.objects.link(cam)
sc.camera = cam
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", "SUN"))
sun.data.energy = 3
sc.collection.objects.link(sun)
paths = []
for i, (yaw, zc, scale) in enumerate(SHOTS):
    y = math.radians(yaw)
    cam.location = Vector((5 * math.sin(y), -5 * math.cos(y), zc * H))
    cam.rotation_euler = (Vector((0, 0, zc * H)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = scale * H
    sun.rotation_euler = cam.rotation_euler
    sc.render.filepath = OUT.replace(".png", f"_{i}.png")
    bpy.ops.render.render(write_still=True)
    paths.append(sc.render.filepath)
imgs = [bpy.data.images.load(pth) for pth in paths]
w = RES * len(imgs)
canvas = np.zeros((RES, w, 4), np.float32)
for i, im in enumerate(imgs):
    canvas[:, i * RES:(i + 1) * RES] = np.array(im.pixels[:]).reshape(RES, RES, 4)
out = bpy.data.images.new("o", w, RES)
out.pixels.foreach_set(canvas.ravel())
out.filepath_raw = OUT
out.file_format = "PNG"
out.save()
