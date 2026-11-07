"""Two back-to-back penny-farthing halves joined by one STRAIGHT decorative cross bar, drawn in code
(exactly level, exactly symmetric). Bar sits under the halves; gold collars clamp it to each backbone.
  python scripts/pf_crossbar.py --dir refs/pf_tandem_v6 --gap 30 --y 560 --out views/bar_mid.png
--y is the bar's centre row in half_rgba.png coordinates.
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ap = argparse.ArgumentParser()
ap.add_argument("--dir", required=True)
ap.add_argument("--gap", type=int, default=30)
ap.add_argument("--y", type=int, required=True)
ap.add_argument("--thick", type=int, default=44)
ap.add_argument("--out", required=True)
a = ap.parse_args()
D = Path(a.dir)
BG = 213
half = Image.open(D / "half_rgba.png")
w, h = half.size
al = np.asarray(half)[..., 3] > 128
W = 2 * w + a.gap + 240
H = round(max(h + 240, W / 1.5)); W = round(H * 1.5)
C, TOP = W // 2, (H - h) // 2
bx = int(np.where(al[a.y])[0][0])            # backbone inner edge in half coords
xr = C + a.gap // 2 + bx + 14                # bar ends tucked under the backbones
xl = W - xr
yc = TOP + a.y
t = a.thick
S = 4                                        # supersample
bar = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
d = ImageDraw.Draw(bar)
def R(x0, y0, x1, y1): return [x0 * S, y0 * S, x1 * S, y1 * S]
GOLD, GOLD_D, GOLD_L, BLK = (214, 160, 40), (150, 100, 20), (255, 222, 120), (18, 16, 15)
# lacquered beam with vertical shading
for i in range(t * S):
    f = i / (t * S)
    v = int(14 + 70 * max(0, 1 - abs(f - 0.28) / 0.28) ** 2)   # highlight band near the top
    d.line([(xl * S, (yc - t / 2) * S + i), (xr * S, (yc - t / 2) * S + i)], fill=(v, v - 2, v - 4, 255))
# gold edging + pinstripes
for y0, hh, col in ((yc - t / 2, 4, GOLD), (yc + t / 2 - 4, 4, GOLD_D), (yc - t / 2 + 9, 1.5, GOLD), (yc + t / 2 - 10.5, 1.5, GOLD)):
    d.rectangle(R(xl, y0, xr, y0 + hh), fill=col)
# gold scrollwork along each side of the medallion
span = (xr - xl) / 2 - 60
for sgn in (-1, 1):
    n = max(1, int(span // 46))
    for k in range(n):
        cx = C + sgn * (62 + 23 + k * 46)
        up = (k % 2 == 0)
        box = R(cx - 16, yc - 12, cx + 16, yc + 12)
        d.arc(box, 200 if up else 20, 520 if up else 340, fill=GOLD, width=3 * S)
        d.ellipse(R(cx - 3, yc - 3, cx + 3, yc + 3), fill=GOLD_L)
# central medallion
r = t * 0.95
d.ellipse(R(C - r - 4, yc - r - 4, C + r + 4, yc + r + 4), fill=GOLD_D)
d.ellipse(R(C - r, yc - r, C + r, yc + r), fill=GOLD)
d.ellipse(R(C - r * 0.78, yc - r * 0.78, C + r * 0.78, yc + r * 0.78), fill=BLK)
d.ellipse(R(C - r * 0.55, yc - r * 0.62, C + r * 0.55, yc + r * 0.48), fill=GOLD)        # goose body hint
d.ellipse(R(C - r * 0.38, yc - r * 0.85, C - r * 0.05, yc - r * 0.45), fill=GOLD)        # head
d.ellipse(R(C - r * 0.2, yc - r * 0.42, C + r * 0.2, yc - r * 0.3), fill=GOLD_L)
bar = bar.resize((W, H), Image.LANCZOS)
canvas = Image.new("RGBA", (W, H), (BG, BG, BG, 255))
canvas.alpha_composite(bar)
canvas.alpha_composite(half, (C + a.gap // 2, TOP))
canvas.alpha_composite(half.transpose(Image.FLIP_LEFT_RIGHT), (C - a.gap // 2 - w, TOP))
# gold collars clamping the bar to each backbone (on top)
col = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
dc = ImageDraw.Draw(col)
for sgn in (-1, 1):
    x = C + sgn * (a.gap // 2 + bx + 18)
    dc.rounded_rectangle(R(x - 13, yc - t / 2 - 7, x + 13, yc + t / 2 + 7), 6 * S, fill=GOLD, outline=GOLD_D, width=2 * S)
    dc.rectangle(R(x - 13, yc - 3, x + 13, yc + 3), fill=GOLD_L)
canvas.alpha_composite(col.resize((W, H), Image.LANCZOS))
canvas.convert("RGB").save(D / a.out)
print("[pf_crossbar]", D / a.out, "bar", xl, "->", xr, "y", yc)
