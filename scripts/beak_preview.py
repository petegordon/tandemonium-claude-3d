"""Honk preview: open the lower bill (vertex group beak_lower) about the beak hinge.

  blender -b --factory-startup --python scripts/beak_preview.py -- --char base [--angles 0,14,28]

Uses the .blend game object (vertex groups don't survive a static GLB). Writes
renders/<char>_beak_preview.png (rows: side, front 3/4 from below, front 3/4 from above; columns: angles).
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1] if "--char" in argv else "base"
ANGLES = [float(a) for a in (argv[argv.index("--angles") + 1] if "--angles" in argv else "0,14,28").split(",")]
ROOT = Path(__file__).resolve().parents[1]
RES = 600

bpy.ops.wm.open_mainfile(filepath=str(ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_goose.blend"))
g = bpy.data.objects[f"{CHAR}_goose_game"]
for o in bpy.data.objects:
    o.hide_render = not (o is g or o.parent is g)
hinge = Vector(g["beak_hinge_point"])
vg = g.vertex_groups["beak_lower"].index
w = np.zeros(len(g.data.vertices), np.float32)
for v in g.data.vertices:
    for ge in v.groups:
        if ge.group == vg:
            w[v.index] = ge.weight
rest = np.array([v.co[:] for v in g.data.vertices], np.float32)
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = RES
sc.view_settings.view_transform = "Standard"
sc.world = bpy.data.worlds.new("w")
sc.world.color = (0.85, 0.85, 0.85)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
sc.collection.objects.link(cam)
sc.camera = cam
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.5
sc.collection.objects.link(sun)
target = Vector((0, hinge.y - 0.06, hinge.z))
views = [Vector((1, 0, 0.05)), Vector((0.6, -0.8, -0.25)), Vector((0.35, -0.8, 0.5))]
tmp = ROOT / "renders" / "_tmp"
grid = []
for vi, d in enumerate(views):
    row = []
    for a in ANGLES:
        rel = rest - np.array(hinge)
        th = np.radians(a) * w
        c, s = np.cos(th), np.sin(th)
        y = rel[:, 1] * c - rel[:, 2] * s
        z = rel[:, 1] * s + rel[:, 2] * c
        new = np.stack([rel[:, 0], y, z], 1) + np.array(hinge)
        g.data.vertices.foreach_set("co", new.ravel())
        g.data.update()
        cam.location = target + d.normalized()
        cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.data.ortho_scale = 0.24
        sun.rotation_euler = cam.rotation_euler
        sc.render.filepath = str(tmp / f"beak_{vi}_{int(a)}.png")
        bpy.ops.render.render(write_still=True)
        row.append(sc.render.filepath)
    grid.append(row)
canvas = np.ones((RES * len(grid), RES * len(ANGLES), 4), np.float32)
for ri, row in enumerate(grid):
    for ci, pth in enumerate(row):
        canvas[(len(grid) - 1 - ri) * RES:(len(grid) - ri) * RES, ci * RES:(ci + 1) * RES] = \
            np.array(bpy.data.images.load(pth).pixels[:], np.float32).reshape(RES, RES, 4)
out = bpy.data.images.new("o", RES * len(ANGLES), RES * len(grid))
out.pixels.foreach_set(canvas.ravel())
out.filepath_raw = str(ROOT / "renders" / f"{CHAR}_beak_preview.png")
out.file_format = "PNG"
out.save()
print("BEAK", out.filepath_raw)
