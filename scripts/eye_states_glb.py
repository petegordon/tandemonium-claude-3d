"""Render eye states on a finished game GLB (eyes attached by the eye_sockets fix).

  blender -b --factory-startup --python scripts/eye_states_glb.py -- --char base

Poses the attached eye objects about their own origins (= eye centres): eyeball yaw/pitch,
lid rotations from assets/goose_eye/goose_eye.json. Writes renders/<char>_eye_states_final.png
(row 1: left-eye close-up, row 2: head 3/4).
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1] if "--char" in argv else "base"
ROOT = Path(__file__).resolve().parents[1]
META = json.loads((ROOT / "assets" / "goose_eye" / "goose_eye.json").read_text())
CLOSED = META["blink_closed_deg"]
RES = 600

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_goose_game.glb"))
obs = {o.name: o for o in bpy.context.scene.objects}
rest = {n: o.matrix_world.copy() for n, o in obs.items()}
head = next(o for o in obs.values() if o.type == "MESH" and not o.name.split("_")[0] in ("eyeball", "lid", "catchlight"))
eye_l = obs["eyeball_L"].matrix_world.translation.copy()


def pose(look_az=0.0, look_el=0.0, blink=0.0):
    for side, sgn in (("L", 1), ("R", -1)):          # right eye mesh is mirrored: yaw flips
        e = obs[f"eyeball_{side}"]
        e.matrix_world = rest[e.name] @ (Matrix.Rotation(math.radians(sgn * look_az), 4, "Z")
                                          @ Matrix.Rotation(math.radians(-look_el), 4, "X"))
        for lid, ang in (("lid_upper", CLOSED["lid_upper"]), ("lid_lower", CLOSED["lid_lower"])):
            o = obs[f"{lid}_{side}"]
            o.matrix_world = rest[o.name] @ Matrix.Rotation(math.radians(ang * blink - 0.35 * look_el), 4, "X")


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
n = (eye_l - Vector((0, eye_l.y, eye_l.z))).normalized()


def shot(target, d, span, path):
    cam.location = target + d.normalized() * 1.0
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = span
    sun.rotation_euler = cam.rotation_euler
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return str(path)


states = [("rest", {}), ("look_bill", {"look_az": 15}), ("look_back", {"look_az": -8}), ("look_up", {"look_el": 8}),
          ("look_down", {"look_el": -8}), ("half_blink", {"blink": 0.5}), ("closed", {"blink": 1.0})]
tmp = ROOT / "renders" / "_tmp"
rows = [[], []]
for name, kw in states:
    pose(**kw)
    rows[0].append(shot(eye_l, Vector((1, -0.55, 0.15)), 0.06, tmp / f"fs_{name}_eye.png"))
    rows[1].append(shot(Vector((0, eye_l.y - 0.02, eye_l.z - 0.01)), Vector((0.6, -0.85, 0.1)), 0.19,
                        tmp / f"fs_{name}_head.png"))
canvas = np.ones((RES * 2, RES * len(states), 4), np.float32)
for ri, row in enumerate(rows):
    for ci, pth in enumerate(row):
        canvas[(1 - ri) * RES:(2 - ri) * RES, ci * RES:(ci + 1) * RES] = \
            np.array(bpy.data.images.load(pth).pixels[:], np.float32).reshape(RES, RES, 4)
out = bpy.data.images.new("o", RES * len(states), RES * 2)
out.pixels.foreach_set(canvas.ravel())
out.filepath_raw = str(ROOT / "renders" / f"{CHAR}_eye_states_final.png")
out.file_format = "PNG"
out.save()
print("STATES", out.filepath_raw)
