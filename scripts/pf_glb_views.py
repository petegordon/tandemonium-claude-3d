"""Render a GLB (bike-shaped, wider than tall) full-frame: side, end, 3/4 front, 3/4 high, top -> one sheet.

  blender -b --factory-startup --python scripts/pf_glb_views.py -- <in.glb> <out.png>
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
GLB, OUT = Path(argv[0]).resolve(), Path(argv[1]).resolve()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector([min(p[i] for p in pts) for i in range(3)])
hi = Vector([max(p[i] for p in pts) for i in range(3)])
ctr, size = (lo + hi) / 2, hi - lo
long_axis = 0 if size.x >= size.y else 1
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y = 1200, 800
sc.render.film_transparent = False
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.85, 0.85, 0.85, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 1.2
for rot, e in (((0.8, 0.2, 0.6), 3.0), ((-0.6, 0.4, -2.2), 1.5)):
    ld = bpy.data.lights.new("sun", "SUN"); ld.energy = e
    lo_ = bpy.data.objects.new("sun", ld); lo_.rotation_euler = rot; sc.collection.objects.link(lo_)
cam_d = bpy.data.cameras.new("cam"); cam_d.type = "ORTHO"
cam = bpy.data.objects.new("cam", cam_d); sc.collection.objects.link(cam); sc.camera = cam
R = max(size) * 3
side = Vector((0, 1, 0)) if long_axis == 0 else Vector((1, 0, 0))
endv = Vector((1, 0, 0)) if long_axis == 0 else Vector((0, 1, 0))
views = {"side": side, "end": endv, "q34": (side + endv * 0.8 + Vector((0, 0, 0.35))).normalized(),
         "q34_high": (side * 0.6 - endv + Vector((0, 0, 0.9))).normalized(), "top": Vector((0, 0.001, 1))}
tmp = OUT.parent / "_views"; tmp.mkdir(parents=True, exist_ok=True)
files = []
for name, d in views.items():
    cam.location = ctr + d * R
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam_d.ortho_scale = max(size) * 1.1
    cam_d.clip_end = R * 3
    sc.render.filepath = str(tmp / f"{name}.png"); bpy.ops.render.render(write_still=True)
    files.append(tmp / f"{name}.png")
import numpy as np
imgs = []
for f in files:
    im = bpy.data.images.load(str(f)); a = np.array(im.pixels[:]).reshape(800, 1200, 4)[::-1]; imgs.append(a)
grid = np.ones((1600, 3600, 4))
for i, a in enumerate(imgs):
    r, c = divmod(i, 3); grid[r*800:(r+1)*800, c*1200:(c+1)*1200] = a
img = bpy.data.images.new("sheet", 3600, 1600); img.pixels = grid[::-1].ravel()
img.filepath_raw = str(OUT); img.file_format = "PNG"; img.save()
print("SIZE m", tuple(round(s, 3) for s in size), "->", OUT)
