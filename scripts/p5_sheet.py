"""P5 gate sheet: both geese playing their baked Pedal clips with the bike's Pedal clip (one crank turn), close side
views from the left and the right, 8 crank angles; plus Lean_L / Ride / Lean_R from the front.

  blender -b --factory-startup --python scripts/p5_sheet.py -- [--scene out/bike/fit_outfit_female_Stoker_p5.blend]

Writes docs/img/p5_pedal_cycle.png and docs/img/p5_lean.png.
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ROOT = Path(__file__).resolve().parents[1]
SCENE = argv[argv.index("--scene") + 1] if "--scene" in argv else "out/bike/fit_outfit_female_Stoker_p5.blend"
bpy.ops.wm.open_mainfile(filepath=str(ROOT / SCENE))
sc = bpy.context.scene
bike = bpy.data.objects["bike_rig"]
rigs = {}
for o in bpy.data.objects:
    if o.type == "ARMATURE" and o is not bike and o.animation_data:
        for t in o.animation_data.nla_tracks:
            if t.name.startswith("Pedal_"):
                rigs[t.name.split("_")[1]] = o
print("RIDERS", {k: v.name for k, v in rigs.items()})
bike.animation_data.action = bpy.data.actions["Pedal"]
for seat, r in rigs.items():
    r.animation_data.action = bpy.data.actions[f"Pedal_{seat}"]
for o in sc.objects:
    if o.name.startswith("riser_"):
        o.hide_render = True
cam = bpy.data.objects["cam"]
W, H = 700, 520
sc.render.resolution_x, sc.render.resolution_y = W, H
TMP = ROOT / "renders" / "_tmp"


def shoot(path, az, el, span, tgt):
    a, e = math.radians(az), math.radians(el)
    d = Vector((math.cos(e) * math.sin(a), -math.cos(e) * math.cos(a), math.sin(e)))
    cam.location = tgt + d * 12
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = span
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return str(path)


def sheet(grid, out, labels):
    rows, cols = len(grid), max(len(r) for r in grid)
    canvas = np.ones((H * rows, W * cols, 4), np.float32)
    for ri, row in enumerate(grid):
        for ci, p in enumerate(row):
            canvas[(rows - 1 - ri) * H:(rows - ri) * H, ci * W:(ci + 1) * W] = \
                np.array(bpy.data.images.load(p).pixels[:], np.float32).reshape(H, W, 4)
    img = bpy.data.images.new("sheet", W * cols, H * rows)
    img.pixels.foreach_set(canvas.ravel())
    img.filepath_raw = str(out)
    img.file_format = "PNG"
    img.save()
    print("SHEET", out, labels)


tgt = Vector((0, 0.15, 0.95))
grid = []
for az, side in ((90, "L"), (-90, "R")):
    row = []
    for i in range(8):
        sc.frame_set(i * 3)                       # 24 frames per turn: 45 deg steps
        row.append(shoot(TMP / f"p5_cyc_{side}_{i}.png", az, 4, 2.75, tgt))
    grid.append(row)
sheet(grid, ROOT / "docs" / "img" / "p5_pedal_cycle.png", "rows: left side, right side; crank 0..315 by 45")

grid = [[], []]
sc.frame_set(0)
for clip in ("Lean_L", "Ride", "Lean_R"):
    for seat, r in rigs.items():
        r.animation_data.action = bpy.data.actions[f"{clip}_{seat}"]
    bpy.context.view_layer.update()
    sc.frame_set(0)
    grid[0].append(shoot(TMP / f"p5_lean_{clip}_front.png", 0, 6, 2.6, Vector((0, 0.3, 1.0))))
    grid[1].append(shoot(TMP / f"p5_lean_{clip}_rear.png", 180, 12, 2.6, Vector((0, 0.3, 1.0))))
sheet(grid, ROOT / "docs" / "img" / "p5_lean.png", "Lean_L, Ride, Lean_R; front / rear (rider poses only: the game tilts the bike too)")
