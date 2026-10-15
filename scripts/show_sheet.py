"""Contact sheet of show_clips.py --render frames: one row per clip x view, 6 frames each.
  python scripts/show_sheet.py <name> [clip,clip...] -> renders/show/<name>_sheet.jpg"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parents[1]
name = sys.argv[1]
d = ROOT / "renders" / "show"
clips = sys.argv[2].split(",") if len(sys.argv) > 2 else sorted({p.name[len(name) + 1:].rsplit("_", 2)[0] for p in d.glob(f"{name}_*_0.png")})
rows = [(c, v) for c in clips for v in ("side", "front") if (d / f"{name}_{c}_{v}_0.png").exists()]
w, h = 180, 240
sheet = Image.new("RGB", (110 + 6 * w, len(rows) * h), "white")
dr = ImageDraw.Draw(sheet)
for r, (c, v) in enumerate(rows):
    dr.text((4, r * h + h // 2), f"{c}\n{v}", fill="black")
    for j in range(6):
        im = Image.open(d / f"{name}_{c}_{v}_{j}.png").convert("RGB").resize((w, h))
        sheet.paste(im, (110 + j * w, r * h))
out = d / f"{name}_sheet.jpg"
sheet.save(out, quality=85)
print(out, sheet.size)
