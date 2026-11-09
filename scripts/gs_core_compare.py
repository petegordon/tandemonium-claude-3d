"""Gold Standard core close-up: Pete's side ref cropped to the frame's core (top tube, crown plate, lower sweep) above
the model's `core` render -> renders/gold_standard/compare_core.png.

  blender -b --factory-startup --python scripts/gs_core_compare.py
"""
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REN = ROOT / "renders" / "gold_standard"


def load(p):
    im = bpy.data.images.load(str(p))
    w, h = im.size
    return np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1]      # row 0 = top


ref = load(ROOT / "refs/gold_standard/pete_refs/side.png")[..., :3]
import sys
src = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "gs_core_ref.png"
mod = load(REN / src)[..., :3]
H, W = mod.shape[:2]
# the core view is 1.45 m wide at the ref's 1.627 mm/px -> ~890 px of the ref; centre it on the plate's tail
x0, y0 = 340, 92
cw, ch = 900, int(900 * H / W)
crop = ref[y0:y0 + ch, x0:x0 + cw]
mx, mn = crop.max(2), crop.min(2)
bg = ((mx - mn) / np.maximum(mx, 1e-4)) < 0.10                                 # the baked checkerboard -> grey
crop = np.where(bg[..., None], np.array([0.74, 0.74, 0.76], np.float32), crop)
yi = (np.arange(H) * ch / H).astype(int).clip(0, ch - 1)
xi = (np.arange(W) * cw / W).astype(int).clip(0, cw - 1)
top = crop[yi][:, xi]
bar = np.full((8, W, 3), 0.3, np.float32)
out = np.concatenate([top, bar, mod], 0)
h, w = out.shape[:2]
im = bpy.data.images.new("o", w, h)
im.pixels[:] = np.concatenate([out[::-1], np.ones((h, w, 1), np.float32)], 2).ravel()
im.filepath_raw = str(REN / "compare_core.png")
im.file_format = "PNG"
im.save()
print("WROTE", REN / "compare_core.png")
