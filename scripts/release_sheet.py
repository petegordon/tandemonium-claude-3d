"""Release sheet: both dressed geese -- garments on their own, the game viewer's pose sheet (three.js r161) and
colour samples -> docs/img/p3_release_sheet.png (+ a smaller preview for the release card).

  python -I scripts/release_sheet.py

Inputs (made beforehand): renders/<c>_garments_sheet.png (garment_sheet.py), renders/<c>_threejs_check_poses.png
(tools/threejs_check/check.mjs), renders/<c>_closeup_col0..2.png (dressed_closeup.py --tint).
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "renders"
OUT = ROOT / "docs" / "img"
W = 2400
BG = (238, 236, 232)
INK = (30, 30, 30)
F = lambda s: ImageFont.truetype("arialbd.ttf" if s > 34 else "arial.ttf", s)  # noqa: E731
NAMES = {"outfit_male": ["hat", "bow tie", "shirt + collar", "vest", "jacket", "glove", "breeches", "boots"],
         "outfit_female": ["hat", "collar + brooch", "bodice + bib", "skirt + bustle", "lace cuff", "glove", "boots"]}
TINTS = {"outfit_male": ["brown jacket / burgundy vest / tan breeches", "navy / grey / olive", "grey / tan / navy"],
         "outfit_female": ["burgundy", "plum", "green"]}


def fit(im, w):
    return im.resize((w, int(im.height * w / im.width)), Image.LANCZOS)


def title(text, size=44, pad=18):
    im = Image.new("RGB", (W, size + 2 * pad), BG)
    ImageDraw.Draw(im).text((30, pad), text, fill=INK, font=F(size))
    return im


def labels(names, h=46):
    im = Image.new("RGB", (W, h), BG)
    d = ImageDraw.Draw(im)
    cw = W / len(names)
    for i, n in enumerate(names):
        d.text((int(cw * i + cw / 2), h // 2), n, fill=INK, font=F(26), anchor="mm")
    return im


blocks = [title("Tandemonium geese -- P3 dressed outfits (designed, reusable, recolourable garments)", 50, 26)]
for c, label in (("outfit_male", "Male"), ("outfit_female", "Female")):
    g = Image.open(R / f"{c}_garments_sheet.png").convert("RGB")
    rows = g.height // 3
    g = g.crop((0, 0, g.width, rows * 2))              # front + side rows
    blocks += [title(f"{label}: garments on their own (front, side)", 38), labels(NAMES[c]), fit(g, W)]
    p = Image.open(R / f"{c}_threejs_check_poses.png").convert("RGB")
    p = p.crop((0, 0, p.width, p.height // 3))          # front row of every pose
    blocks += [title(f"{label}: poses in the game's three.js viewer (rest, T, A, riding, neck, honk)", 38), fit(p, W)]
    cols = []
    for i in range(3):
        im = Image.open(R / f"{c}_closeup_col{i}.png").convert("RGB")
        cols.append(im)
    strip = Image.new("RGB", (sum(x.width for x in cols), cols[0].height), BG)
    x = 0
    for im in cols:
        strip.paste(im, (x, 0))
        x += im.width
    blocks += [title(f"{label}: colour samples (one baseColorFactor per garment)", 38), labels(TINTS[c]), fit(strip, W)]
H = sum(b.height for b in blocks)
sheet = Image.new("RGB", (W, H), BG)
y = 0
for b in blocks:
    sheet.paste(b, (0, y))
    y += b.height
OUT.mkdir(parents=True, exist_ok=True)
sheet.save(OUT / "p3_release_sheet.png", optimize=True)
fit(sheet, 1200).save(OUT / "p3_release_sheet_small.jpg", quality=88)
print("SHEET", sheet.size, OUT / "p3_release_sheet.png")
