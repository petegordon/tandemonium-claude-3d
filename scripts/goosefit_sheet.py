"""Goose-fit tandem gate sheet: both geese on the 24 in and 26 in bikes, five views each.

  .venv python scripts/goosefit_sheet.py      (after make_bike.py --fit ... --tag goosefit<n> and ride_fit.py --tag gf<n>)
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "renders" / "_tmp"
TW, TH = 600, 467
VIEWS = ("side", "q34", "front", "rq34", "top")
font, small = ImageFont.truetype("arial.ttf", 24), ImageFont.truetype("arial.ttf", 18)
rows = []
for w in (24, 26):
    bike = json.loads((ROOT / f"out/bike/bike_rig_goosefit{w}.json").read_text(encoding="utf-8"))
    cap = json.loads((ROOT / f"out/bike/fit_outfit_male_Captain_gfC{w}.json").read_text(encoding="utf-8"))["1.0"]
    sto = json.loads((ROOT / f"out/bike/fit_outfit_female_Stoker_gf{w}.json").read_text(encoding="utf-8"))["1.0"]
    row = Image.new("RGB", (TW * len(VIEWS), TH + 70), "white")
    for i, v in enumerate(VIEWS):
        row.paste(Image.open(TMP / f"fit_gf{w}_1.0_{v}.png").convert("RGB").resize((TW, TH)), (TW * i, 70))
    d = ImageDraw.Draw(row)
    d.text((12, 8), f"{w} in wheels: bike {bike['length_m']:.2f} m long, wheelbase {bike['pivots']['wheelbase_m']:.2f} m, "
                    f"{bike['tris']['out']} tris, crank {bike['pivots']['crank_len_m']['Pedal_FL'] * 1000:.0f} mm",
           fill="black", font=font)
    d.text((12, 40), f"captain: saddle {cap['saddle_top_m']:.2f} m, grips {cap['grip_z_m']:.2f} m, leg reach {cap['leg_R']:.2f}, "
                     f"arm reach {cap['arm_L']:.2f}   |   stoker: saddle {sto['saddle_top_m']:.2f} m, grips "
                     f"{sto['grip_z_m']:.2f} m, leg reach {sto['leg_L']:.2f}, arm reach {sto['arm_L']:.2f}   |   "
                     f"feet / hands on the contacts: {max(cap['foot_err_mm_R'], sto['foot_err_mm_L'], cap['grip_err_mm_L'], sto['grip_err_mm_L']):.0f} mm",
           fill=(0, 90, 0), font=small)
    rows.append(row)
sheet = Image.new("RGB", (rows[0].width, sum(r.height for r in rows)), "white")
y = 0
for r in rows:
    sheet.paste(r, (0, y))
    y += r.height
out = ROOT / "docs" / "img" / "goosefit_24_26.png"
sheet.save(out)
print("SHEET", out)
