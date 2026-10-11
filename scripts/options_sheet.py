"""P4.2 options sheet: A (small bike), B (bigger bike + riding-only leg stretch), C (permanently longer legs).

  .venv python scripts/options_sheet.py   (after ride_fit.py --tag optA / --tag optB --stretch auto --standing)
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / "renders" / "_tmp"
TW, TH = 540, 420
font, small = ImageFont.truetype("arial.ttf", 22), ImageFont.truetype("arial.ttf", 17)
A = json.loads((ROOT / "out/bike/fit_outfit_male_Captain_optA.json").read_text(encoding="utf-8"))
B = json.loads((ROOT / "out/bike/fit_outfit_male_Captain_optB.json").read_text(encoding="utf-8"))
ka, kb = next(k for k in A if not k.startswith("stand")), next(k for k in B if not k.startswith("stand"))
f = B[kb]["leg_stretch"]
VIEWS = ("side", "front", "q34", "rq34", "top")


def tile(p):
    return Image.open(p).convert("RGB").resize((TW, TH))


rows = [
    (f"A. small bike k={ka}: wheel {A[ka]['wheel_m'] * 100:.0f} cm, bike {A[ka]['bike_length_m']:.2f} m, "
     f"bars raised {A[ka]['bar_raise_m'] * 100:.0f} cm. Legs as built.",
     [tile(TMP / f"fit_optA_{ka}_{v}.png") for v in VIEWS]),
    (f"B. bike k={kb}: wheel {B[kb]['wheel_m'] * 100:.0f} cm, bike {B[kb]['bike_length_m']:.2f} m, bars raised "
     f"{B[kb]['bar_raise_m'] * 100:.0f} cm. Thigh+shin stretched x{f:.2f} only while riding.",
     [tile(TMP / f"fit_optB_{kb}_{v}.png") for v in VIEWS]),
    (f"C. same bike as B, legs permanently x{f:.2f}: rides exactly like B; standing he grows "
     f"{(B[f'stand_{f:.2f}']['head_top_z_m'] - B['stand_1.00']['head_top_z_m']) * 100:.0f} cm. "
     f"Standing: today | C (front, side)",
     [tile(TMP / "stand_optB_1.00_front.png"), tile(TMP / f"stand_optB_{f:.2f}_front.png"),
      tile(TMP / "stand_optB_1.00_side.png"), tile(TMP / f"stand_optB_{f:.2f}_side.png"),
      tile(TMP / f"fit_optB_{kb}_q34.png")]),
]
sheet = Image.new("RGB", (TW * 5, (TH + 44) * len(rows)), "white")
d = ImageDraw.Draw(sheet)
for i, (label, tiles) in enumerate(rows):
    y = i * (TH + 44)
    d.text((10, y + 10), label, fill="black", font=font)
    for j, t in enumerate(tiles):
        sheet.paste(t, (TW * j, y + 44))
out = ROOT / "docs" / "img" / "p42_options.png"
sheet.save(out)
print("SHEET", out)
