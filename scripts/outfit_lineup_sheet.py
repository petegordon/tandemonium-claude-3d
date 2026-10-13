"""Display sheet: every dressed goose standing (front + 3/4) and the three in-game pairings on the tandem.

  python -I scripts/outfit_lineup_sheet.py --out docs/img/outfit_lineup.png

Inputs (rendered first):
  renders/lineup/_<key>_{front,q34}.png   outfit_beauty.py --views front:0,q34:35 per dressed goose
  renders/_tmp/fit_<tag>_1.0_{q34,side}.png   ride_fit.py stoker scenes (captain + stoker on goosefit26)
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
argv = sys.argv[1:]
OUT = ROOT / (argv[argv.index("--out") + 1] if "--out" in argv else "docs/img/outfit_lineup.png")

GEESE = [("m_orig", "Male - original"), ("m_vic", "Male - fancy (Victorian)"), ("m_cyc", "Male - 1920s cyclist"),
         ("f_orig", "Female - original"), ("f_cyc", "Female - 1920s lady cyclist")]
PAIRS = [("hpS", "Original", "original male + original female"),
         ("rideS", "Cyclist", "male cyclist + lady cyclist"),
         ("fancyS", "Fancy", "Victorian male + original female")]
BG = (232, 232, 232)


def font(px, bold=False):
    for name in (("arialbd.ttf", "segoeuib.ttf") if bold else ("arial.ttf", "segoeui.ttf")):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            pass
    return ImageFont.load_default()


def bbox(im):
    """Content box: pixels that differ from their row's background (the studio floor is a vertical gradient)."""
    a = np.asarray(im.convert("RGB")).astype(int)
    bg = a[:, :8].mean(1, keepdims=True)
    m = np.abs(a - bg).sum(2) > 90   # (the soft key-light spot on the backdrop stays under this)
    ys, xs = np.where(m)
    return xs.min(), ys.min(), xs.max(), ys.max()


def crop_group(ims, pad=16):
    """Crop a set of same-size renders to their shared content height (same scale), each to its own width."""
    boxes = [bbox(im) for im in ims]
    y0 = max(0, min(b[1] for b in boxes) - pad)
    y1 = min(ims[0].height, max(b[3] for b in boxes) + pad)
    return [im.crop((max(0, b[0] - pad), y0, min(im.width, b[2] + pad), y1)) for im, b in zip(ims, boxes)]


def tile(im, h):
    return im.resize((round(im.width * h / im.height), h), Image.LANCZOS)


H1 = 760
raw = [[Image.open(ROOT / "renders/lineup" / f"_{key}_{v}.png") for v in ("front", "q34")] for key, _ in GEESE]
crops = crop_group([im for pair in raw for im in pair])          # one vertical crop for all: heights compare
cells = []
for i, (key, label) in enumerate(GEESE):
    f, q = (tile(im, H1) for im in crops[2 * i:2 * i + 2])
    c = Image.new("RGB", (f.width + q.width, H1), BG)
    c.paste(f, (0, 0))
    c.paste(q, (f.width, 0))
    cells.append((c, label))
H2 = 640
bikes = []
for tag, name, sub in PAIRS:
    q, s_ = (tile(im, H2) for im in crop_group([Image.open(ROOT / "renders/_tmp" / f"fit_{tag}_1.0_{v}.png")
                                                 for v in ("q34", "side")]))
    c = Image.new("RGB", (q.width + s_.width, H2), BG)
    c.paste(q, (0, 0))
    c.paste(s_, (q.width, 0))
    bikes.append((c, name, sub))

GAP, M, LAB = 24, 40, 56
w1 = sum(c.width for c, _ in cells) + GAP * (len(cells) - 1)
w2 = sum(c.width for c, _, _ in bikes) + GAP * (len(bikes) - 1)
W = max(w1, w2) + 2 * M
TITLE = 90
HDR = 64
Ht = TITLE + HDR + LAB + H1 + 40 + HDR + LAB + H2 + M
sheet = Image.new("RGB", (W, Ht), (246, 246, 244))
d = ImageDraw.Draw(sheet)
d.text((M, 26), "Tandemonium geese - outfits", fill=(30, 30, 30), font=font(46, True))
y = TITLE
d.text((M, y + 10), "Dressed geese (front, 3/4)", fill=(60, 60, 60), font=font(34, True))
y += HDR
x = M + (W - 2 * M - w1) // 2
for c, label in cells:
    d.text((x + c.width // 2, y + 22), label, fill=(30, 30, 30), font=font(28), anchor="mm")
    sheet.paste(c, (x, y + LAB))
    x += c.width + GAP
y += LAB + H1 + 40
d.text((M, y + 10), "In-game pairings on the tandem (captain + stoker): the Outfits setting",
       fill=(60, 60, 60), font=font(34, True))
y += HDR
x = M + (W - 2 * M - w2) // 2
for c, name, sub in bikes:
    d.text((x + c.width // 2, y + 22), f"{name}: {sub}", fill=(30, 30, 30), font=font(28), anchor="mm")
    sheet.paste(c, (x, y + LAB))
    x += c.width + GAP
OUT.parent.mkdir(parents=True, exist_ok=True)
sheet.save(OUT)
print("SHEET", OUT, sheet.size)
