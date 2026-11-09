"""Ref-vs-model sheet: Pete's side ref (checkerboard keyed to grey) above the model's side render, same scale.

  blender -b --factory-startup --python scripts/gs_compare.py      -> renders/gold_standard/compare_side.png
"""
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load(p):
    im = bpy.data.images.load(str(p))
    w, h = im.size
    return np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[..., :3]


ref = load(ROOT / "refs/gold_standard/pete_refs/side.png")
mx, mn = ref.max(2), ref.min(2)
bgm = ((mx - mn) / np.maximum(mx, 1e-4)) < 0.03                      # the baked checkerboard
ref[bgm] = [0.74, 0.74, 0.76]
ren = load(ROOT / "renders/gold_standard/gs_side.png")
gap = np.full((12, ref.shape[1], 3), 0.3, np.float32)
out = np.concatenate([ren, gap, ref], 0)                              # (rows are bottom-up: model ends up below)
h, w = out.shape[:2]
im = bpy.data.images.new("o", w, h)
im.pixels[:] = np.concatenate([out, np.ones((h, w, 1), np.float32)], 2).ravel()
im.filepath_raw = str(ROOT / "renders/gold_standard/compare_side.png")
im.file_format = "PNG"
im.save()
print("COMPARE ok")
