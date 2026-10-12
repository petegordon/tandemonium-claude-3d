"""Crop a garment reference sheet (one column per garment, front view above side view) into per-garment views.

  .venv python scripts/crop_garment_sheet.py <sheet.png> <set_dir> --names hat,bow_tie,... [--panel y0,y1]

The top panel (rows --panel, default: auto from the sheet's grey) is split at its light vertical separators into
one column per name. In each column the foreground (colour distance from the panel grey) splits at its largest
empty horizontal gap into the front view (upper) and side view (lower; drawn facing image-left = our "left" view).
Writes <set_dir>/<name>/front_raw.png, left_raw.png (padded crops on the sheet's grey) and <set_dir>/crop_report.json
plus <set_dir>/crops_contact.png.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

argv = sys.argv[1:]
SHEET, SET = Path(argv[0]), Path(argv[1])
NAMES = argv[argv.index("--names") + 1].split(",")
im = np.asarray(Image.open(SHEET).convert("RGB")).astype(np.int16)
H, W, _ = im.shape

# panel grey: the commonest colour of the sheet's middle-left region, quantised
mid = im[H // 4:H // 2, :W // 3].reshape(-1, 3) // 4 * 4
vals, counts = np.unique(mid, axis=0, return_counts=True)
grey = vals[counts.argmax()] + 2
is_grey = np.abs(im - grey).max(axis=2) < 14
if "--panel" in argv:
    y0, y1 = (int(v) for v in argv[argv.index("--panel") + 1].split(","))
else:                                           # first run of rows that are mostly grey
    rows = is_grey.mean(axis=1) > 0.35
    y0 = int(np.argmax(rows))
    y1 = y0 + int(np.argmax(~rows[y0:]))
panel = im[y0:y1]
sep = np.where((panel.mean(axis=2) > 185).mean(axis=0) > 0.85)[0]   # separators: thin light lines top to bottom
cuts = [0]
for x in sep:
    if x - cuts[-1] > 20:
        cuts.append(int(x))
cuts.append(W)
cols = [(a, b) for a, b in zip(cuts[:-1], cuts[1:]) if b - a > 40]
assert len(cols) == len(NAMES), (len(cols), cols)

report = {"sheet": str(SHEET.name), "size": [W, H], "panel_y": [y0, y1], "grey": grey.tolist(), "garments": {}}
crops = []
for name, (xa, xb) in zip(NAMES, cols):
    xa, xb = xa + 3, xb - 3
    sub = panel[:, xa:xb]
    q = sub.reshape(-1, 3) // 4 * 4                  # each column has its own grey
    v_, c_ = np.unique(q, axis=0, return_counts=True)
    cgrey = v_[c_.argmax()] + 2
    fg = np.abs(sub - cgrey).max(axis=2) > 22
    rows_fg = fg.sum(axis=1) > 2
    ys = np.where(rows_fg)[0]
    # largest empty gap between the first and last foreground rows splits front / side
    gaps = np.diff(ys)
    k = int(gaps.argmax())
    parts = {"front": ys[:k + 1], "left": ys[k + 1:]}
    split = (int(ys[k]) + int(ys[k + 1])) // 2       # padding never crosses into the other view
    lim = {"front": (0, split), "left": (split, len(sub))}
    rep = {"col": [int(xa), int(xb)], "grey": cgrey.tolist()}
    for view, yy in parts.items():
        ya, yb = int(yy.min()), int(yy.max()) + 1
        cx = np.where(fg[ya:yb].sum(axis=0) > 1)[0]
        xa2, xb2 = int(cx.min()), int(cx.max()) + 1
        pad = int(0.08 * max(yb - ya, xb2 - xa2))
        lo, hi = lim[view]
        box = [max(xa, xa + xa2 - pad), y0 + max(lo, ya - pad), min(xb, xa + xb2 + pad), y0 + min(hi, yb + pad)]
        crop = Image.fromarray(im[box[1]:box[3], box[0]:box[2]].astype(np.uint8))
        out = SET / name / f"{view}_raw.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        crop.save(out)
        crops.append(crop)
        rep[view] = {"box": box, "size": [box[2] - box[0], box[3] - box[1]],
                     "touches_column_edge": bool(xa2 < 2 or xb2 > xb - xa - 2)}
    report["garments"][name] = rep
(SET / "crop_report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
cw = max(c.width for c in crops)
ch = max(c.height for c in crops)
sheet = Image.new("RGB", (cw * len(NAMES), ch * 2), "white")
for i, c in enumerate(crops):
    sheet.paste(c, ((i // 2) * cw, (i % 2) * ch))
sheet.save(SET / "crops_contact.png")
print(json.dumps({n: {v: r[v]["size"] for v in ("front", "left")} for n, r in report["garments"].items()}))
