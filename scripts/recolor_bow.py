"""Deepen the bow-tie texture toward the drawing's burgundy: at full-body size the prepped product shot's heavy gold
scrollwork averaged to orange. The gold is thinned (only its core kept: a 1-texel erosion) and slightly darkened;
the cloth is pulled toward a deep burgundy keeping its light / dark shading.

  python -I scripts/recolor_bow.py [--tex refs/outfit_male_victorian/bow_tie/prepped/bow_texture.png]
      [--cloth 70,20,28] [--gold-scale 0.9] [--erode 1]

The first run keeps the input as <name>.orig.png and always works from that copy.
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

argv = sys.argv[1:]


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
TEX = ROOT / opt("--tex", "refs/outfit_male_victorian/bow_tie/prepped/bow_texture.png")
ORIG = TEX.with_name(TEX.stem + ".orig.png")
if not ORIG.exists():
    shutil.copy(TEX, ORIG)
CLOTH = np.array([float(c) for c in opt("--cloth", "70,20,28").split(",")])
GS, ER = opt("--gold-scale", 0.9), opt("--erode", 1)

a = np.array(Image.open(ORIG).convert("RGBA")).astype(float)
rgb = a[..., :3]
r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
# gold: warm and yellow (green well above blue, a good part of red)
gold = (g > 0.55 * r) & (g > b * 1.35) & (r > 90)
core = ndimage.binary_erosion(gold, iterations=ER) if ER > 0 else gold
soft = ndimage.gaussian_filter(core.astype(float), 0.7)
lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
cloth_lum = np.median(lum[~gold & (a[..., 3] > 128)])
shade = np.clip(lum / max(cloth_lum, 1e-3), 0.35, 1.5)[..., None]
cloth = CLOTH[None, None, :] * shade
goldc = rgb * GS
out = cloth * (1 - soft[..., None]) + goldc * soft[..., None]
a[..., :3] = np.clip(out, 0, 255)
Image.fromarray(a.astype(np.uint8)).save(TEX)
print("BOW gold texels", int(gold.sum()), "kept", int(core.sum()), "cloth lum", round(float(cloth_lum), 1))
