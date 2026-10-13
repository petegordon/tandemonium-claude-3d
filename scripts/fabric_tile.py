"""Cut a seamless fabric tile from a garment's reference view (Pete's drawing on our body), for project_bake.py.

  .venv python scripts/fabric_tile.py --ref breeches [--view front] [--size 0.10] [--band 0.55,0.80]

Searches the reference's garment pixels (out/outfit_male_victorian/dressed/<ref>/<view>_garment.png) for the square
patch (--size metres, at the calibrated px_per_m) that is fully garment, closest to the garment's dominant colour (no
buttons / trims) and flattest in low-frequency shading, inside the height band --band (z, metres; default: the whole
garment). The patch's slow shading is divided out, then it is made seamless (offset by half, cross-faded into the
original along a soft cross). Writes <dir>/fabric_tile.png and <dir>/fabric_tile.json {size_m, source box, mean colour}.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ap = argparse.ArgumentParser()
ap.add_argument("--ref", required=True)
ap.add_argument("--view", default="front")
ap.add_argument("--size", type=float, default=0.10)
ap.add_argument("--band", default="")
ap.add_argument("--hires", action="store_true", help="cut from the 4x-upscaled drawing (prepped/<view>_up4x.png)")
a = ap.parse_args()
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / "outfit_male_victorian" / "dressed" / a.ref
CAM = json.loads((ROOT / "refs" / "key_views" / "cameras.json").read_text(encoding="utf-8"))
W0, H0 = CAM["size_px"]
PPM = CAM["px_per_m"]
TZ = CAM["target"][2]
im = np.asarray(Image.open(D / f"{a.view}_garment.png").convert("RGBA")).astype(float) / 255
rgb, m = im[..., :3], im[..., 3] > 0.5
S = int(round(a.size * PPM))
if a.hires:
    # the drawing itself, 4x upscaled: its own garment mask (ref_dress.py) and scale (view px per drawing px)
    G = {"vest": "vest", "jacket": "jacket"}.get(a.ref, a.ref)
    rep = json.loads((D / "ref_dress.json").read_text(encoding="utf-8"))["views"][a.view]
    k = rep["view_px_per_drawing_px"]
    up = np.asarray(Image.open(ROOT / "refs" / "outfit_male_victorian" / "worn" / G / "prepped" / f"{a.view}_up4x.png")
                    .convert("RGB")).astype(float) / 255
    dm = np.load(D / f"{a.view}_drawmask.npy")
    m = np.repeat(np.repeat(dm, 4, 0), 4, 1)[:up.shape[0], :up.shape[1]]
    rgb = up
    S = int(round(a.size * PPM / k * 4))
    H0, W0 = rgb.shape[:2]
    a.band = ""                                        # (heights are in view space; not used on the drawing)
dom = np.median(rgb[m], axis=0)
dist = np.sqrt(((rgb - dom) ** 2).sum(-1))
lo_freq = ndimage.uniform_filter(rgb.mean(-1), S // 2)
rows = np.arange(H0)
z_of = TZ - (rows - H0 / 2) / PPM
band = np.ones(H0, bool)
if a.band:
    z0, z1 = (float(x) for x in a.band.split(","))
    band = (z_of >= z0) & (z_of <= z1)
best = None
STEP = 8 if a.hires else 4
for y in range(0, H0 - S, STEP):
    if not band[y:y + S].all():
        continue
    for x in range(0, W0 - S, STEP):
        win = m[y:y + S, x:x + S]
        if not win.all():
            continue
        d = dist[y:y + S, x:x + S]
        if (d > (0.40 if a.hires else 0.25)).mean() > (0.03 if a.hires else 0.01):   # buttons / trims inside
            continue
        lf = lo_freq[y:y + S, x:x + S]
        score = d.mean() + 2.0 * (lf.max() - lf.min())
        if best is None or score < best[0]:
            best = (score, x, y)
if best is None:
    raise SystemExit(f"no clean {S}px patch in {a.ref}/{a.view}: try a smaller --size or another band")
_, x, y = best
patch = rgb[y:y + S, x:x + S].copy()
shade = ndimage.gaussian_filter(patch, (S / 3, S / 3, 0))
patch = np.clip(patch / np.maximum(shade, 1e-3) * patch.reshape(-1, 3).mean(0), 0, 1)   # flatten slow shading
off = np.roll(np.roll(patch, S // 2, 0), S // 2, 1)
yy, xx = np.mgrid[0:S, 0:S]
wv = np.minimum(np.abs(yy - S / 2), np.abs(xx - S / 2)) / (S / 2)
wv = np.clip(1 - wv / 0.35, 0, 1)[..., None]                      # the cross through the middle takes the original
tile = off * (1 - wv) + patch * wv
Image.fromarray((tile * 255).astype(np.uint8)).save(D / "fabric_tile.png")
info = {"size_m": a.size, "px": S, "box_view_px": [int(x), int(y), int(x + S), int(y + S)], "view": a.view,
        "z_center_m": round(float(TZ - (y + S / 2 - H0 / 2) / PPM), 3), "mean_rgb": (tile.reshape(-1, 3).mean(0) * 255).round().tolist()}
(D / "fabric_tile.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
print("TILE", json.dumps(info))
