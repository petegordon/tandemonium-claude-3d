"""Shorten (or lengthen) a garment shell by squashing the band of it between two heights: every vertex above --z0 is
moved to z0 + (z - z0) * (new_top - z0) / (old_top - z0). Texture, UVs, buttons and materials ride along; the top
edge lands at --new-top. Used to lower the riding boots' shaft top without rebuilding / re-baking them.

  blender -b --factory-startup --python scripts/squash_band.py -- --piece boots --z0 0.22 --old-top 0.475
      --new-top 0.435 [--char outfit_male_victorian] [--glb shells/boots.glb] [--out shells/boots.glb]
"""
import sys
from pathlib import Path

import bpy

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_victorian")
PIECE = opt("--piece", "boots")
D = ROOT / "out" / f"{CHAR}-goose"
GLB = D / opt("--glb", f"shells/{PIECE}.glb")
OUT = D / opt("--out", f"shells/{PIECE}.glb")
Z0, OLD, NEW = opt("--z0", 0.22), opt("--old-top", 0.475), opt("--new-top", 0.435)
s = (NEW - Z0) / (OLD - Z0)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
objs = [o for o in bpy.data.objects if o.type == "MESH"]
top = -1e9
for o in objs:
    M, Mi = o.matrix_world, o.matrix_world.inverted()
    for v in o.data.vertices:
        w = M @ v.co
        if w.z > Z0:
            w.z = Z0 + (w.z - Z0) * s
            v.co = Mi @ w
        top = max(top, w.z)
bpy.ops.object.select_all(action="DESELECT")
for o in objs:
    o.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
bpy.ops.export_scene.gltf(filepath=str(OUT), export_format="GLB", use_selection=True, export_tangents=True)
print("SQUASH", PIECE, "scale", round(s, 3), "top now", round(top, 4))
