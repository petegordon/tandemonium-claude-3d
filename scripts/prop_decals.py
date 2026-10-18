"""Prop texture sources from the clean reference views (prop_views.py): per view, the object's pixel bbox, a label
decal (RGBA, alpha = label), the cap line and the plastic colour. Read by prop_lowpoly.py.

  python scripts/prop_decals.py --prop ketchup [--tag v1] [--views front,rear]

Writes refs/<prop>/decals/<view>_label.png + decals.json (+ <view>_check.png overlays to eyeball).
"""
import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[1]


def largest(m):
    lab, n = ndi.label(m)
    if n == 0:
        return m
    sizes = ndi.sum(m, lab, range(1, n + 1))
    return lab == (1 + int(np.argmax(sizes)))


def analyse(img):
    a = np.asarray(img.convert("RGB")).astype(np.float32)
    h, w, _ = a.shape
    border = np.concatenate([a[:8].reshape(-1, 3), a[-8:].reshape(-1, 3), a[:, :8].reshape(-1, 3), a[:, -8:].reshape(-1, 3)])
    bg = np.median(border, 0)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(2), a.min(2)
    sat = (mx - mn) / np.maximum(mx, 1)
    shadow = (sat < 0.12) & (mx > 95)                     # grey contact shadow on the floor is not the object
    obj = largest(ndi.binary_fill_holes((np.linalg.norm(a - bg, axis=2) > 28) & ~shadow))
    obj = ndi.binary_opening(obj, iterations=2)
    ys, xs = np.nonzero(obj)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    # label: cream paper (bright, low saturation, warm) -> largest blob, holes (text, art) filled
    cream = obj & (mn > 120) & (sat < 0.35) & (r >= b)
    lab, n = ndi.label(ndi.binary_fill_holes(ndi.binary_closing(cream, iterations=4)))
    sizes = ndi.sum(lab > 0, lab, range(1, n + 1))
    label = np.isin(lab, 1 + np.nonzero(sizes > 0.05 * sizes.max())[0])   # main label + stickers (barcode)
    label = ndi.binary_erosion(label, iterations=2)       # keep the red bottle edge out of the decal
    # cap: dark rows at the bottom; cap line = top of the contiguous run of mostly-dark rows
    dark = obj & (mx < 70)
    cap_top, seen = y1, False
    for y in range(y1, y0, -1):
        row = obj[y]
        if row.sum() and dark[y].sum() / row.sum() > 0.55:
            cap_top, seen = y, True
        elif seen:
            break
    plastic = obj & ~ndi.binary_dilation(label, iterations=6) & (np.arange(h)[:, None] < cap_top - 6) & (sat > 0.6) & (r > 60)
    capm = dark & (np.arange(h)[:, None] > cap_top + 4)
    return {"bbox": [int(x0), int(x1), int(y0), int(y1)], "size": [w, h], "cap_top_row": int(cap_top),
            "cap_frac": float((y1 - cap_top) / (y1 - y0)),
            "aspect_w_over_h": float((x1 - x0) / (y1 - y0)),
            "plastic_rgb": np.percentile(a[plastic], 80, axis=0).round().tolist(),
            "cap_rgb": np.median(a[capm], 0).round().tolist() if capm.any() else [25, 25, 27]}, label, a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prop", required=True)
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--views", default="front,rear")
    a = ap.parse_args()
    src = ROOT / "refs" / a.prop / "t2i" / a.tag
    dest = ROOT / "refs" / a.prop / "decals"
    dest.mkdir(parents=True, exist_ok=True)
    out = {}
    for v in a.views.split(","):
        info, label, rgb = analyse(Image.open(src / f"{v}.png"))
        soft = ndi.gaussian_filter(label.astype(np.float32), 0.8)
        rgba = np.dstack([rgb, soft * 255]).clip(0, 255).astype(np.uint8)
        Image.fromarray(rgba, "RGBA").save(dest / f"{v}_label.png")
        chk = rgb.copy()
        chk[label] = chk[label] * 0.5 + np.array([0, 255, 0]) * 0.5
        x0, x1, y0, y1 = info["bbox"]
        chk[info["cap_top_row"], x0:x1] = [0, 120, 255]
        chk[y0:y1, [x0, x1]] = [255, 255, 0]
        chk[[y0, y1], x0:x1] = [255, 255, 0]
        Image.fromarray(chk.clip(0, 255).astype(np.uint8)).save(dest / f"{v}_check.png")
        info["label"] = f"{v}_label.png"
        out[v] = info
        print(v, json.dumps(info))
    (dest / "decals.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
