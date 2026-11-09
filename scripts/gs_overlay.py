"""Overlay a side render on Pete's side ref (same framing): renders/gold_standard/gs_side_ref.png over
refs/gold_standard/pete_refs/side.png -> renders/gold_standard/overlay.png (ref in red/orange, render in cyan).

  blender -b --factory-startup --python scripts/gs_overlay.py
"""
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load(p):
    im = bpy.data.images.load(str(p))
    w, h = im.size
    return np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)


ref = load(ROOT / "refs/gold_standard/pete_refs/side.png")[..., :3]
ren = load(ROOT / "renders/gold_standard/gs_side_ref.png")
mx, mn = ref.max(2), ref.min(2)
ref_fg = ((mx - mn) / np.maximum(mx, 1e-4)) > 0.13                    # the ref's checkerboard is neutral
bgc = ren[4, 4, :3]
ren_fg = np.abs(ren[..., :3] - bgc).sum(2) > 0.06
out = np.ones(ref.shape, np.float32) * 0.96
out[ref_fg] = [0.95, 0.45, 0.2]
out[ren_fg] = [0.2, 0.7, 0.95]
out[ref_fg & ren_fg] = [0.25, 0.25, 0.3]
h, w = out.shape[:2]
im = bpy.data.images.new("o", w, h)
im.pixels[:] = np.concatenate([out, np.ones((h, w, 1), np.float32)], 2).ravel()
im.filepath_raw = str(ROOT / "renders/gold_standard/overlay.png")
im.file_format = "PNG"
im.save()
print("OVERLAY ok: dark = both, orange = ref only, blue = model only")
