"""Review sheet for an outfit made from text-to-image reference views: the reference (top) over our dressed goose
rendered from the SAME calibrated key cameras (bottom), front / left / rear, plus a row of close-ups.

  python scripts/review_pack.py --ref refs/outfit_male_cyclist/t2i/key1 --ours renders/cyclist/_key_<tag>_{view}.png
      --close renders/cyclist/close_<tag>.png --out renders/cyclist/review_<tag>.png

(our key-camera tiles: outfit_beauty.py --cams refs/key_views/cameras.json --views front:0,left:90,rear:180)
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ap = argparse.ArgumentParser()
ap.add_argument("--ref", required=True)
ap.add_argument("--ours", required=True)
ap.add_argument("--close", default="")
ap.add_argument("--out", required=True)
a = ap.parse_args()
H = 900
try:
    font = ImageFont.truetype("arial.ttf", 28)
except OSError:
    font = ImageFont.load_default()
rows = []
for label, fmt in (("reference (text-to-image)", str(ROOT / a.ref / "{view}.png")), ("ours (3D, same cameras)", str(ROOT / a.ours))):
    tiles = [Image.open(fmt.format(view=v)).convert("RGB") for v in ("front", "left", "rear")]
    tiles = [t.resize((round(t.width * H / t.height), H)) for t in tiles]
    row = Image.new("RGB", (sum(t.width for t in tiles), H + 44), (34, 34, 36))
    x = 0
    for v, t in zip(("front", "left", "rear"), tiles):
        row.paste(t, (x, 44))
        ImageDraw.Draw(row).text((x + 12, 8), f"{label} - {v}", fill=(235, 230, 220), font=font)
        x += t.width
    rows.append(row)
if a.close:
    c = Image.open(ROOT / a.close).convert("RGB")
    w = rows[0].width
    rows.append(c.resize((w, round(c.height * w / c.width))))
W = max(r.width for r in rows)
sheet = Image.new("RGB", (W, sum(r.height for r in rows)), (34, 34, 36))
y = 0
for r in rows:
    sheet.paste(r, (0, y))
    y += r.height
sheet.save(ROOT / a.out)
print("REVIEW", ROOT / a.out)
