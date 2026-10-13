"""Erase the drawn buttons from a garment's reference views before baking, once they are modelled in brass
(add_buttons.py): otherwise the painted button shows beside the real one and the front reads doubled.

  .venv python -I scripts/erase_ref_buttons.py --ref jacket [--views front,left,right] [--min-px 12] [--max-px 260]
      [--grow 3] [--preview out.png]

Blobs as add_buttons.py finds them (brass-coloured, round, compact, isolated) in out/outfit_male_victorian/dressed/
<ref>/<view>_garment.png and _garment_soft.png are filled with the cloth around them (each hole pixel takes the mean
of the cloth in a ring 2-6 px outside the blob, plus the ring's own fine texture copied from just above it).
Originals are kept once as <view>_garment.orig.png / _garment_soft.orig.png (re-runs start from them).
"""
import argparse
import shutil
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ap = argparse.ArgumentParser()
ap.add_argument("--ref", required=True)
ap.add_argument("--char", default="outfit_male_victorian")
ap.add_argument("--views", default="front,left,right")
ap.add_argument("--min-px", type=int, default=12)
ap.add_argument("--max-px", type=int, default=260)
ap.add_argument("--grow", type=int, default=3)
ap.add_argument("--preview", default="")
ap.add_argument("--zone", default="", help="xmin,xmax,zmin,zmax (m, |x| mirrored): the button panel on the body; inside "
                "it every compact brass blob goes (no isolation test: double-breasted rows sit close together); outside "
                "it nothing is erased")
a = ap.parse_args()
ROOT = Path(__file__).resolve().parents[1]
RD = ROOT / "out" / a.char / "dressed" / a.ref
import json
CAM = json.loads((RD / "cameras.json").read_text(encoding="utf-8"))


def zone_mask(view, shape):
    """Image pixels of the --zone box (both sides) seen from this view."""
    if not a.zone:
        return np.ones(shape, bool)
    x0, x1, z0, z1 = (float(t) for t in a.zone.split(","))
    c = CAM["views"][view]
    R, U = np.array(c["right"]), np.array(c["up"])
    T, ppm = np.array(CAM["target"]), CAM["px_per_m"]
    W0, H0 = CAM["size_px"]
    m = np.zeros(shape, bool)
    for sx in (1, -1):
        pts = []
        for x in (x0, x1):
            for z in (z0, z1):
                for y in (-0.3, 0.3):
                    p = np.array([sx * x, y, z]) - T
                    pts.append((W0 / 2 + p @ R * ppm, H0 / 2 - p @ U * ppm))
        pts = np.array(pts)
        if c["back"][1] > 0 or abs(c["back"][0]) > 0.9:                 # side / rear views: only the facing side
            pass
        xa, xb = int(max(pts[:, 0].min(), 0)), int(min(pts[:, 0].max(), shape[1]))
        ya, yb = int(max(pts[:, 1].min(), 0)), int(min(pts[:, 1].max(), shape[0]))
        m[ya:yb, xa:xb] = True
    return m


def find_buttons(px, zone):
    r, g, b, al = (px[..., i] for i in range(4))
    brass = (al > 0.5) & (r > 0.55) & (r - b > 0.25) & (g > 0.35) & (g < r)
    if a.zone:                     # inside the zone: shaded buttons too
        brass |= (al > 0.5) & (r > 0.40) & (r - b > 0.18) & (g > 0.25) & (g < r) & (g > 0.45 * r) & zone
    lab, n = ndimage.label(brass)
    out = np.zeros(brass.shape, bool)
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        comp = lab[sl] == i
        npx = int(comp.sum())
        if not (a.min_px <= npx <= (a.max_px * 4 if a.zone else a.max_px)):
            continue
        hh, ww = comp.shape
        cy, cx = (sl[0].start + sl[0].stop) // 2, (sl[1].start + sl[1].stop) // 2
        if zone[cy, cx] and a.zone:
            # in the button panel a button may touch the gold edge trim: keep only the blob's round core (an
            # opening of the component removes the thin trim line it is joined to)
            core = ndimage.binary_opening(comp, iterations=2)
            if core.sum() >= a.min_px:
                out[sl] |= core
            continue
        if max(hh, ww) > 1.7 * min(hh, ww) or npx < 0.55 * hh * ww:       # round and compact
            continue
        rr = int(max(hh, ww) * 1.6)
        win = brass[max(0, cy - rr):cy + rr + 1, max(0, cx - rr):cx + rr + 1]
        if zone[cy, cx]:
            out[sl] |= comp
            continue
        if a.zone or win.sum() > 2.2 * npx:                                # isolated (not trim / brocade)
            continue
        out[sl] |= comp
    return out


total = 0
pv = []
for view in a.views.split(","):
    for suf in ("_garment", "_garment_soft"):
        f = RD / f"{view}{suf}.png"
        if not f.exists():
            continue
        orig = RD / f"{view}{suf}.orig.png"
        if not orig.exists():
            shutil.copy(f, orig)
        im = np.asarray(Image.open(orig).convert("RGBA")).astype(float) / 255
        if suf == "_garment":
            holes = find_buttons(im, zone_mask(view, im.shape[:2]))
            holes = ndimage.binary_dilation(holes, iterations=a.grow)
            ring = ndimage.binary_dilation(holes, iterations=6) & ~ndimage.binary_dilation(holes, iterations=2) & (im[..., 3] > 0.5)
            lab, n = ndimage.label(holes)
            total += n
        out = im.copy()
        for i in range(1, n + 1):
            h_ = lab == i
            rg = ndimage.binary_dilation(h_, iterations=6) & ring
            if not rg.any():
                continue
            mean = im[rg][:, :3].mean(0)
            ys, xs = np.where(h_)
            # fine texture: the pixels a blob-height above, minus their own mean, on top of the ring mean
            dy = int(np.ptp(ys)) + 4
            sy = np.clip(ys - dy, 0, im.shape[0] - 1)
            src = im[sy, xs, :3]
            out[ys, xs, :3] = mean + (src - src.mean(0)) * 0.6
        Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8)).save(f)
        if suf == "_garment" and a.preview:
            vis = im[..., :3].copy()
            vis[holes] = [1, 0, 1]
            pv.append(np.concatenate([vis, out[..., :3]], 1))
    print("ERASED", view, n, "buttons")
if a.preview and pv:
    Image.fromarray((np.concatenate(pv, 0) * 255).astype(np.uint8)).resize(
        (pv[0].shape[1] // 2, pv[0].shape[0] * len(pv) // 2)).save(a.preview)
print("TOTAL", total)
