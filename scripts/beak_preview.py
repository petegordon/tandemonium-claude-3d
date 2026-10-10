"""Honk preview: open the lower bill (vertex group beak_lower) about the beak hinge.

  blender -b --factory-startup --python scripts/beak_preview.py -- --char base       [--poses jaw:lift:out,...]      (jaw / tongue-lift in degrees, tongue-out in metres)

Uses the .blend game object (vertex groups don't survive a static GLB). Tongue moves first in
the jaw's rest frame (lift = curl about its root, weighted by group "tongue"; out = slide along
its axis), then the jaw opens about the hinge (group "beak_lower"). Writes
renders/<char>_beak_preview.png (rows: side, front 3/4 from below, into the mouth; columns: poses).
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1] if "--char" in argv else "base"
POSES = [tuple(float(x) for x in p.split(":")) for p in
         (argv[argv.index("--poses") + 1] if "--poses" in argv else "0:0:0,28:0:0,28:30:0,28:0:0.03").split(",")]
ROOT = Path(__file__).resolve().parents[1]
RES = 600

bpy.ops.wm.open_mainfile(filepath=str(ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_goose.blend"))
g = bpy.data.objects[f"{CHAR}_goose_game"]
for o in bpy.data.objects:
    o.hide_render = not (o is g or o.parent is g)
hinge = Vector(g["beak_hinge_point"])
def group_weights(name):
    idx = g.vertex_groups[name].index
    out = np.zeros(len(g.data.vertices), np.float32)
    for v in g.data.vertices:
        for ge in v.groups:
            if ge.group == idx:
                out[v.index] = ge.weight
    return out


w = group_weights("beak_lower")
wt = group_weights("tongue") if "tongue" in g.vertex_groups else np.zeros_like(w)
t_root = np.array(g.get("tongue_root", hinge))
t_axis = np.array(g.get("tongue_axis", [0, -1, 0]))
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
views = [(Vector((1, 0, 0.05)), 0.24, target), (Vector((0.6, -0.8, -0.25)), 0.24, target),
         (Vector((0.15, -1, -0.35)), 0.11, Vector((0, hinge.y - 0.05, hinge.z - 0.012)))]
tmp = ROOT / "renders" / "_tmp"
grid = []
def rot_x(pts, origin, ang):
    rel = pts - origin
    c, s = np.cos(ang), np.sin(ang)
    return np.stack([rel[:, 0], rel[:, 1] * c - rel[:, 2] * s, rel[:, 1] * s + rel[:, 2] * c], 1) + origin


for vi, (d, span, tgt) in enumerate(views):
    row = []
    for jaw, lift, out in POSES:
        pts = rest.copy()
        if lift or out:                                    # tongue in the jaw's rest frame
            tm = wt > 0
            pts[tm] = pts[tm] + t_axis * out * wt[tm][:, None]
            for k in np.where(tm)[0]:                        # per-vertex curl (weight ramps to the tip)
                pts[k] = rot_x(pts[k:k + 1], t_root, -np.radians(lift) * wt[k])[0]
        rel = pts - np.array(hinge)
        th = np.radians(jaw) * w
        c, s = np.cos(th), np.sin(th)
        y = rel[:, 1] * c - rel[:, 2] * s
        z = rel[:, 1] * s + rel[:, 2] * c
        new = np.stack([rel[:, 0], y, z], 1) + np.array(hinge)
        g.data.vertices.foreach_set("co", new.ravel())
        g.data.update()
        cam.location = tgt + d.normalized()
        cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.data.ortho_scale = span
        sun.rotation_euler = cam.rotation_euler
        sc.render.filepath = str(tmp / f"beak_{vi}_{int(jaw)}_{int(lift)}_{int(out * 1000)}.png")
        bpy.ops.render.render(write_still=True)
        row.append(sc.render.filepath)
    grid.append(row)
canvas = np.ones((RES * len(grid), RES * len(POSES), 4), np.float32)
for ri, row in enumerate(grid):
    for ci, pth in enumerate(row):
        canvas[(len(grid) - 1 - ri) * RES:(len(grid) - ri) * RES, ci * RES:(ci + 1) * RES] = \
            np.array(bpy.data.images.load(pth).pixels[:], np.float32).reshape(RES, RES, 4)
out = bpy.data.images.new("o", RES * len(POSES), RES * len(grid))
out.pixels.foreach_set(canvas.ravel())
out.filepath_raw = str(ROOT / "renders" / f"{CHAR}_beak_preview.png")
out.file_format = "PNG"
out.save()
print("BEAK", out.filepath_raw)
