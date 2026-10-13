"""Colour-change review sheet: rows = pairs (refs/colourways.json), columns = the pair's own colours + each colourway;
each cell = captain + stoker (3/4 view, renders/colourways/ from colourway_renders.py), all at one scale.

  python -I scripts/colourway_sheet.py --out docs/img/colourways.jpg
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
argv = sys.argv[1:]
OUT = ROOT / (argv[argv.index("--out") + 1] if "--out" in argv else "docs/img/colourways.jpg")
W = json.loads((ROOT / "refs" / "colourways.json").read_text(encoding="utf-8"))
R = ROOT / "renders" / "colourways"


def font(px, bold=False):
    for n in (("arialbd.ttf",) if bold else ("arial.ttf",)):
        try:
            return ImageFont.truetype(n, px)
        except OSError:
            pass
    return ImageFont.load_default()


def bbox(im):
    a = np.asarray(im.convert("RGB")).astype(int)
    bg = a[:, :8].mean(1, keepdims=True)
    ys, xs = np.where(np.abs(a - bg).sum(2) > 90)
    return xs.min(), ys.min(), xs.max(), ys.max()


cells = {}
for pk, p in W["pairs"].items():
    for way in ["default"] + list(p["ways"]):
        cells[(pk, way)] = [Image.open(R / f"_{pk}_{way}_{s}_q34.png").convert("RGB") for s in ("captain", "stoker")]
boxes = {k: [bbox(i) for i in v] for k, v in cells.items()}
y0 = max(0, min(b[1] for bs in boxes.values() for b in bs) - 12)
y1 = min(min(i.height for v in cells.values() for i in v), max(b[3] for bs in boxes.values() for b in bs) + 12)
H = 560
tiles = {}
for k, ims in cells.items():
    parts = []
    for im, b in zip(ims, boxes[k]):
        c = im.crop((max(0, b[0] - 14), y0, min(im.width, b[2] + 14), y1))
        parts.append(c.resize((round(c.width * H / c.height), H), Image.LANCZOS))
    t = Image.new("RGB", (sum(x.width for x in parts), H), (232, 232, 232))
    x = 0
    for q in parts:
        t.paste(q, (x, 0))
        x += q.width
    tiles[k] = t
ncol = max(len(p["ways"]) + 1 for p in W["pairs"].values())
cw = max(t.width for t in tiles.values())
M, GAP, LAB, ROWLAB = 30, 18, 44, 190
Wd = M * 2 + ROWLAB + ncol * cw + (ncol - 1) * GAP
Ht = 100 + len(W["pairs"]) * (H + LAB + GAP) + M
sheet = Image.new("RGB", (Wd, Ht), (246, 246, 244))
d = ImageDraw.Draw(sheet)
d.text((M, 28), "Goose outfit pairs - colour changes (captain + stoker)", fill=(30, 30, 30), font=font(42, True))
y = 100
for pk, p in W["pairs"].items():
    d.text((M, y + LAB + H // 2), p["label"], fill=(30, 30, 30), font=font(34, True), anchor="lm")
    for ci, way in enumerate(["default"] + list(p["ways"])):
        x = M + ROWLAB + ci * (cw + GAP)
        lab = "current colours" if way == "default" else p["ways"][way]["label"]
        d.text((x + cw // 2, y + LAB // 2), lab, fill=(40, 40, 40), font=font(26), anchor="mm")
        t = tiles[(pk, way)]
        sheet.paste(t, (x + (cw - t.width) // 2, y + LAB))
    y += H + LAB + GAP
OUT.parent.mkdir(parents=True, exist_ok=True)
sheet.save(OUT, quality=90)
print("SHEET", OUT, sheet.size)
