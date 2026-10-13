"""Bow tie texture from the product shot: crop the bow (anything unlike the grey backdrop), grow its colours out over
the backdrop (no grey at the rounded corners), save as a texture the bow wings take by front projection.

  .venv python -I scripts/prep_bow_texture.py [--src refs/outfit_male_victorian/bow_tie/prepped/front_up4x.png]
      [--out refs/outfit_male_victorian/bow_tie/prepped/bow_texture.png]

Writes <out> and <out>.json {"bbox": [x0, y0, x1, y1] of the bow in the source, "size": [w, h]}.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

argv = sys.argv[1:]


def opt(name, default):
    return argv[argv.index(name) + 1] if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / opt("--src", "refs/outfit_male_victorian/bow_tie/prepped/front_up4x.png")
OUT = ROOT / opt("--out", "refs/outfit_male_victorian/bow_tie/prepped/bow_texture.png")

im = np.asarray(Image.open(SRC).convert("RGB")).astype(float)
h, w, _ = im.shape
edge = np.concatenate([im[0], im[-1], im[:, 0], im[:, -1]])
bg = np.median(edge, 0)
diff = np.linalg.norm(im - bg, axis=2)
sat = im.max(2) - im.min(2)
mask = (diff > 28) & (sat > 18)                     # the bow is saturated burgundy / gold; the backdrop is grey
mask = ndimage.binary_opening(mask, iterations=2)
lab, n = ndimage.label(mask)
keep = np.argmax(np.bincount(lab.ravel())[1:]) + 1
mask = ndimage.binary_fill_holes(lab == keep)
ys, xs = np.where(mask)
x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
crop, m = im[y0:y1, x0:x1], ndimage.binary_erosion(mask[y0:y1, x0:x1], iterations=3)   # (edge pixels mix in grey)
# backdrop pixels take the nearest bow pixel's colour
_, (iy, ix) = ndimage.distance_transform_edt(~m, return_indices=True)
filled = crop[iy, ix]
Image.fromarray(filled.clip(0, 255).astype(np.uint8)).save(OUT)
OUT.with_suffix(".json").write_text(json.dumps({"src": str(SRC.relative_to(ROOT)), "bbox": [int(x0), int(y0), int(x1), int(y1)],
                                                "size": [int(x1 - x0), int(y1 - y0)], "aspect_w_h": round((x1 - x0) / (y1 - y0), 3)},
                                               indent=1), encoding="utf-8")
print("BOW TEXTURE", OUT, (x0, y0, x1, y1))
