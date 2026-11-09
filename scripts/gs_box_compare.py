"""Ref box (x0,y0,x1,y1 px) beside the model's `refbox` render (make_gold_standard.py --nowarp --sheet --views refbox
--refbox ...) -> renders/gold_standard/compare_box.png. Side by side, with a 10 px grid on both.

  blender -b --factory-startup --python scripts/gs_box_compare.py -- x0,y0,x1,y1
"""
import sys
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REN = ROOT / "renders" / "gold_standard"


def load(p):
    im = bpy.data.images.load(str(p))
    w, h = im.size
    return np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1][..., :3]


x0, y0, x1, y1 = map(int, sys.argv[sys.argv.index("--") + 1].split(","))
ref = load(ROOT / "refs/gold_standard/pete_refs/side.png")[y0:y1, x0:x1]
mx, mn = ref.max(2), ref.min(2)
bg = ((mx - mn) / np.maximum(mx, 1e-4)) < 0.10
ref = np.where(bg[..., None], np.array([0.74, 0.74, 0.76], np.float32), ref)
mod = load(REN / "gs_refbox.png")
H, W = mod.shape[:2]
yi = (np.arange(H) * (y1 - y0) / H).astype(int)
xi = (np.arange(W) * (x1 - x0) / W).astype(int)
top = ref[yi][:, xi].copy()
k = W / (x1 - x0)
for img in (top, mod):
    for gx in range((x0 // 10 + 1) * 10, x1, 10):
        c = int((gx - x0) * k)
        img[:, c] = img[:, c] * 0.5 + (np.array([1, 0, 0]) if gx % 50 == 0 else np.array([1, .6, .6])) * 0.5
    for gy in range((y0 // 10 + 1) * 10, y1, 10):
        r = int((gy - y0) * k)
        img[r] = img[r] * 0.5 + (np.array([0, 0, 1]) if gy % 50 == 0 else np.array([.6, .6, 1])) * 0.5
bar = np.full((H, 8, 3), 0.3, np.float32)
out = np.concatenate([top, bar, mod], 1)
h, w = out.shape[:2]
im = bpy.data.images.new("o", w, h)
im.pixels[:] = np.concatenate([out[::-1], np.ones((h, w, 1), np.float32)], 2).ravel()
im.filepath_raw = str(REN / "compare_box.png")
im.file_format = "PNG"
im.save()
print("WROTE", REN / "compare_box.png")
