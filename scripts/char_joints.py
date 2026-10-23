"""Write a slider-shaped character's joints (bone heads / tails) in its BUILD frame -- the slider body before
dress_goose.py lifts the soles to the floor -- as out/<char>-goose/joints.json (the chars json "joints_file" that
pattern_paint.py and friends read), and print the landmark heights in both frames.

  blender -b --factory-startup --python scripts/char_joints.py -- --char outfit_grandpa [--lift -0.0829]

--lift: dress_goose's FLOOR lift (printed in its log); dressed z = build z + lift.
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import bodyshape  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1]
LIFT = float(argv[argv.index("--lift") + 1]) if "--lift" in argv else 0.0
ROOT = Path(__file__).resolve().parents[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ROOT / "out" / "base-goose" / "base_goose_rigged.glb"))
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
T = bodyshape.body_transforms(ROOT, CHAR, rig)
out = {}
for b in rig.data.bones:
    h0 = np.array(rig.matrix_world @ b.head_local)
    t0 = np.array(rig.matrix_world @ b.tail_local)
    if T and b.name in T:
        h = np.array(T[b.name]["head"])
        t = h + np.array(T[b.name]["A"]) @ (t0 - h0)
    else:
        h, t = h0, t0
    out[b.name] = {"head": h.tolist(), "tail": t.tolist()}
D = ROOT / "out" / f"{CHAR}-goose"
D.mkdir(parents=True, exist_ok=True)
(D / "joints.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
for n in ("Hips", "Spine", "Spine1", "Spine2", "Neck", "Head", "LeftShoulder", "LeftArm", "LeftForeArm", "LeftHand",
          "LeftUpLeg", "LeftLeg", "LeftFoot", "LeftToeBase"):
    if n in out:
        h = out[n]["head"]
        print(f"JOINT {n:14s} build x {h[0]:+.3f} y {h[1]:+.3f} z {h[2]:.3f}   dressed z {h[2] + LIFT:.3f}")
print("wrote", D / "joints.json")
