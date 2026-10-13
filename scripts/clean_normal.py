"""Flatten the steep texels of a garment shell's normal map (fold marks left in it from geometry that was since relaxed:
the jacket's armpit crumples printed dark slashes on the smooth back).

  blender -b --factory-startup --python scripts/clean_normal.py -- --piece coat [--char outfit_male_victorian]
      [--max-tilt 25] [--glb shells/coat.glb] [--out shells/coat.glb]

Every normal map in the shell's materials: texels tilted more than --max-tilt degrees from flat are blended back to flat
(fully at 1.5 x the limit), with a 2-texel feather; the weave (a few degrees) is left as it is. Writes the shell back.
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_victorian")
PIECE = opt("--piece", "coat")
D = ROOT / "out" / f"{CHAR}-goose"
GLB = D / opt("--glb", f"shells/{PIECE}.glb")
OUT = D / opt("--out", f"shells/{PIECE}.glb")
TILT = math.radians(opt("--max-tilt", 25.0))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
gar = next(o for o in bpy.data.objects if o.type == "MESH")
done = set()
for m in gar.data.materials:
    if not (m and m.node_tree):
        continue
    for nm in [n for n in m.node_tree.nodes if n.type == "NORMAL_MAP"]:
        tex = next((l.from_node for l in m.node_tree.links if l.to_node == nm and l.from_node.type == "TEX_IMAGE"), None)
        if tex is None or tex.image.name in done:
            continue
        im = tex.image
        w, h = im.size
        px = np.array(im.pixels[:]).reshape(h, w, 4)
        n = px[..., :3] * 2 - 1
        n /= np.linalg.norm(n, axis=2, keepdims=True) + 1e-9
        tilt = np.arccos(np.clip(n[..., 2], -1, 1))
        a = np.clip((tilt - TILT) / (0.5 * TILT), 0, 1)
        for _ in range(2):                                  # feather
            a = np.maximum(a, (np.roll(a, 1, 0) + np.roll(a, -1, 0) + np.roll(a, 1, 1) + np.roll(a, -1, 1)) / 4)
        flat = np.array([0.5, 0.5, 1.0])
        px[..., :3] = px[..., :3] * (1 - a[..., None]) + flat * a[..., None]
        im.pixels = px.ravel().tolist()
        im.pack()
        done.add(im.name)
        print("NORMAL", m.name, im.name, f"{w}x{h}", "flattened texels", int((a > 0.5).sum()),
              "tilt p50/p99 deg", np.round(np.degrees(np.percentile(tilt, [50, 99])), 1).tolist())
bpy.ops.object.select_all(action="DESELECT")
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.export_scene.gltf(filepath=str(OUT), export_format="GLB", use_selection=True, export_tangents=True)
print("CLEAN", OUT)
