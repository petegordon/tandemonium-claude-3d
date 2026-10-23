"""Carry a shell built on the BASE goose (hats: make_cap / make_cloche / make_hat fit the base head) onto a slider-shaped
character's body, in its build frame, by one bone's slider map (bodyshape.slider_transforms: p -> head + A (p - head0)).

  blender -b --factory-startup --python scripts/shell_to_shape.py -- --char outfit_grandpa --piece hat [--bone Head]

For a "height" != 1 character the head is the base head scaled about the origin (Head's A = height * I), so a hat
fitted to the base head fits the shaped head exactly after this. Rewrites out/<char>-goose/shells/<piece>.glb
(the first run keeps the base-fitted original as shells/_basefit/<piece>.glb and always starts from it).
"""
import shutil
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).parent))
import bodyshape  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]


def opt(n, d):
    return argv[argv.index(n) + 1] if n in argv else d


ROOT = Path(__file__).resolve().parents[1]
CHAR, PIECE, BONE = opt("--char", ""), opt("--piece", "hat"), opt("--bone", "Head")
SH = ROOT / "out" / f"{CHAR}-goose" / "shells"
src, base = SH / f"{PIECE}.glb", SH / "_basefit" / f"{PIECE}.glb"     # (a subfolder: dress_goose loads every shells/*.glb)
base.parent.mkdir(exist_ok=True)
if "--fresh" in argv or not base.exists():        # (--fresh: the builder just rewrote <piece>.glb on the base head)
    shutil.copy(src, base)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ROOT / "out" / "base-goose" / "base_goose_rigged.glb"))
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
T = bodyshape.body_transforms(ROOT, CHAR, rig)[BONE]
h0 = np.array(rig.matrix_world @ rig.data.bones[BONE].head_local)
A, h = np.array(T["A"]), np.array(T["head"])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(base))
n = 0
for o in [o for o in bpy.data.objects if o.type == "MESH"]:
    mw = o.matrix_world.copy()
    inv = mw.inverted()
    for v in o.data.vertices:
        p = np.array(mw @ v.co)
        v.co = inv @ Vector(h + A @ (p - h0))
        n += 1
    o.data.update()
bpy.ops.export_scene.gltf(filepath=str(src), export_format="GLB", export_animations=False)
print("SHAPED", PIECE, "by", BONE, "verts", n, "A diag", np.round(np.diag(A), 3).tolist(), "->", src)
