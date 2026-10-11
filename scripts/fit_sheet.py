"""P4.2 gate sheet: ride_fit.py renders per bike scale, with the assembly sheet's left view for comparison.

  .venv python scripts/fit_sheet.py --tag p42 --char outfit_male --seat Captain --out docs/img/p42_fit.png
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

argv = sys.argv[1:]


def arg(name, default):
    return argv[argv.index(name) + 1] if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
TAG, CHAR, SEAT = arg("--tag", "p42"), arg("--char", "outfit_male"), arg("--seat", "Captain")
OUT = ROOT / arg("--out", f"docs/img/{TAG}_fit.png")
rep = json.loads((ROOT / "out" / "bike" / f"fit_{CHAR}_{SEAT}_{TAG}.json").read_text(encoding="utf-8"))
TW, TH = 600, 467
try:
    font = ImageFont.truetype("arial.ttf", 20)
    small = ImageFont.truetype("arial.ttf", 16)
except OSError:
    font = small = ImageFont.load_default()
ref = Image.open(ROOT / "refs" / "v2" / "assembly-turnaround.png").convert("RGB").crop((0, 30, 545, 495))
ref = ref.resize((TW, int(TW * ref.height / ref.width)))
rows = []
for k, r in rep.items():
    tiles = [Image.open(ROOT / "renders" / "_tmp" / f"fit_{TAG}_{k}_{v}.png").convert("RGB").resize((TW, TH))
             for v in ("side", "front", "q34")]
    row = Image.new("RGB", (TW * 4, TH + 60), "white")
    row.paste(ref.crop((0, 0, TW, min(TH, ref.height))), (0, 60))
    for i, t in enumerate(tiles):
        row.paste(t, (TW * (i + 1), 60))
    d = ImageDraw.Draw(row)
    legs = f"leg reach at the bottom {r['leg_R']:.2f}" + ("" if r["foot_err_mm_R"] < 1 else
                                                          f" -> foot misses the pedal by {r['foot_err_mm_R'] / 10:.0f} cm")
    d.text((10, 6), f"bike scale k = {k}: wheel {r['wheel_m'] * 100:.0f} cm ({r['wheel_m'] / 0.0254:.0f} in), "
                    f"bike {r['bike_length_m']:.2f} m, saddle {r['saddle_top_m']:.2f} m, grips {r['grip_z_m']:.2f} m "
                    f"(bars raised {r['bar_raise_m'] * 100:.0f} cm), lean {r['lean_deg']:.0f} deg", fill="black", font=font)
    d.text((10, 32), legs + f"; arm reach {r['arm_L']:.2f}   |   left: assembly sheet (wheel ~ 71 cm at goose scale)",
           fill=(120, 0, 0) if r["foot_err_mm_R"] >= 1 else (0, 90, 0), font=small)
    rows.append(row)
sheet = Image.new("RGB", (TW * 4, sum(r.height for r in rows)), "white")
y = 0
for r in rows:
    sheet.paste(r, (0, y))
    y += r.height
OUT.parent.mkdir(parents=True, exist_ok=True)
sheet.save(OUT)
print("SHEET", OUT)
