"""Crop a "goose wearing each garment" sheet: a 4 x 2 grid of panels, each with two figures side by side.

  .venv python scripts/crop_worn_sheet.py <sheet.png> <set_dir> --views front,left [--names hat,bow_tie,...]

Panels: 4 equal columns; the two panel rows lie between the light header strips (the numbered titles). Inside a
panel the background is taken per pixel column (its commonest colour: the second sheet shades each panel's halves
differently), foreground = colour distance > 28 from it, the label strip at the top skipped. The two figures split
at the empty column run nearest the panel centre; each is cropped to its foreground box (+6% pad, inside the
panel) -> <set_dir>/<name>/<view>_raw.png, plus worn_crop_report_<views>.json and worn_contact_<views>.png.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

argv = sys.argv[1:]
SHEET, SET = Path(argv[0]), Path(argv[1])
VIEWS = argv[argv.index("--views") + 1].split(",")
NAMES = (argv[argv.index("--names") + 1] if "--names" in argv else
         "hat,bow_tie,shirt,vest,jacket,glove,breeches,boots").split(",")
im = np.asarray(Image.open(SHEET).convert("RGB")).astype(np.int16)
H, W, _ = im.shape
lum = im.mean(axis=2)


def runs(mask, min_len=1):
    out, start = [], None
    for i, m in enumerate(list(mask) + [False]):
        if m and start is None:
            start = i
        elif not m and start is not None:
            if i - start >= min_len:
                out.append((start, i))
            start = None
    return out


header = (lum > 215).mean(axis=1) > 0.85                    # light title strips across the sheet
strips = runs(header, 8)
bounds = [b for _, b in strips] + [H]
rows = [(bounds[i], (strips[i + 1][0] if i + 1 < len(strips) else H)) for i in range(len(strips))]
rows = [r for r in rows if r[1] - r[0] > 200]
assert len(rows) == 2, (strips, rows)
PW = W // 4
report, crops = {"sheet": SHEET.name, "views": VIEWS, "rows": rows, "garments": {}}, []
k = 0
for (y0, y1) in rows:
    for p in range(4):
        x0, x1 = p * PW + 3, (p + 1) * PW - 3
        name = NAMES[k]
        k += 1
        sub = im[y0:y1, x0:x1]
        q = sub // 4 * 4
        bg = np.empty((sub.shape[1], 3))
        for x in range(sub.shape[1]):                          # per-column background
            vv, cc = np.unique(q[:, x], axis=0, return_counts=True)
            bg[x] = vv[cc.argmax()] + 2
        fg = np.abs(sub - bg[None]).max(axis=2) > 28
        fg[:int(0.09 * len(sub))] = False                     # "FRONT" / "SIDE" labels
        colfg = fg.sum(axis=0) > 2
        gaps = [g for g in runs(~colfg, 3) if g[0] > 10 and g[1] < len(colfg) - 10]
        mid = len(colfg) / 2
        g = min(gaps, key=lambda g: abs((g[0] + g[1]) / 2 - mid))
        split = (g[0] + g[1]) // 2
        rep = {"panel": [int(x0), int(y0), int(x1), int(y1)], "split": int(x0 + split)}
        for view, (a, b) in zip(VIEWS, ((0, split), (split, len(colfg)))):
            m = fg[:, a:b]
            ys, xs = np.where(m)
            ya, yb, xa, xb = ys.min(), ys.max() + 1, a + xs.min(), a + xs.max() + 1
            pad = int(0.06 * (yb - ya))
            bx = [max(a, xa - pad), max(int(0.07 * len(sub)), ya - pad), min(b, xb + pad), min(len(sub), yb + pad)]
            crop = Image.fromarray(sub[bx[1]:bx[3], bx[0]:bx[2]].astype(np.uint8))
            out = SET / name / f"{view}_raw.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            crop.save(out)
            crops.append(crop)
            rep[view] = {"box": [int(x0 + bx[0]), int(y0 + bx[1]), int(x0 + bx[2]), int(y0 + bx[3])],
                         "size": list(crop.size), "touches_split": bool(xa - a < 2 or b - xb < 2)}
        report["garments"][name] = rep
tag = "_".join(VIEWS)
(SET / f"worn_crop_report_{tag}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
h = max(c.height for c in crops)
sheet = Image.new("RGB", (sum(c.width for c in crops) + 4 * len(crops), h), "white")
x = 0
for c in crops:
    sheet.paste(c, (x, 0))
    x += c.width + 4
sheet.save(SET / f"worn_contact_{tag}.png")
print(json.dumps({n: {v: r[v]["size"] + (["EDGE"] if r[v]["touches_split"] else []) for v in VIEWS}
                  for n, r in report["garments"].items()}))
