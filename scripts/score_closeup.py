"""Close-up strip of a scored garment version: its full renders (garment_score.py) cropped to a height band.

  .venv python scripts/score_closeup.py <piece> <tag> <z_lo> <z_hi> [views...]   -> renders/score/<piece>_<tag>_close.png
"""
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
piece, tag, z0, z1 = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
views = sys.argv[5:] or ["front", "left", "rear", "right", "q34"]
cam = json.loads((ROOT / "refs" / "key_views" / "cameras.json").read_text(encoding="utf-8"))
H0, ppm, tz = cam["size_px"][1], cam["px_per_m"], cam["target"][2]
SD = ROOT / "renders" / "score"
tiles = []
for v in views:
    f = SD / f"_{piece}_{tag}_{v}_full.png" if v != "q34" else SD / f"_{piece}_{tag}_q34.png"
    im = Image.open(f).convert("RGB")
    k = im.height / H0
    r0 = int((H0 / 2 - (z1 - tz) * ppm) * k)
    r1 = int((H0 / 2 - (z0 - tz) * ppm) * k)
    t = im.crop((0, max(0, r0), im.width, min(im.height, r1)))
    # trim empty side margins
    tiles.append(t.crop((int(t.width * 0.15), 0, int(t.width * 0.85), t.height)))
h = max(t.height for t in tiles)
out = Image.new("RGB", (sum(t.width for t in tiles), h), (200, 200, 200))
x = 0
for t in tiles:
    out.paste(t, (x, 0))
    x += t.width
out.save(SD / f"{piece}_{tag}_close.png")
print(SD / f"{piece}_{tag}_close.png", out.size)
