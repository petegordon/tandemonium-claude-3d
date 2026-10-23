"""Pocket-watch dial texture for add_trims.py --kind fob ("face": true): cream enamel, black Roman numerals, minute
track, a small seconds sub-dial and blued spade hands at ten past ten. Plain PIL (run with the ComfyUI venv python).

  python scripts/make_watch_face.py [--out refs/textures/watch_face.png] [--px 512]
"""
import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ap = argparse.ArgumentParser()
ap.add_argument("--out", default="refs/textures/watch_face.png")
ap.add_argument("--px", type=int, default=512)
a = ap.parse_args()
ROOT = Path(__file__).resolve().parents[1]
S = a.px * 2                                     # drawn at 2x, downsampled (smooth edges)
im = Image.new("RGB", (S, S), (236, 228, 206))
d = ImageDraw.Draw(im)
c = S / 2
R = S / 2
ink = (22, 20, 18)
d.ellipse([c - R * 0.99, c - R * 0.99, c + R * 0.99, c + R * 0.99], outline=(170, 150, 110), width=int(S * 0.012))
for m in range(60):                              # minute track: two rings + ticks
    ang = math.radians(m * 6)
    r0, r1 = R * (0.86 if m % 5 else 0.81), R * 0.92
    w = int(S * (0.011 if m % 5 == 0 else 0.004))
    d.line([c + r0 * math.sin(ang), c - r0 * math.cos(ang), c + r1 * math.sin(ang), c - r1 * math.cos(ang)], fill=ink, width=w)
for rr in (0.86, 0.92):
    d.ellipse([c - R * rr, c - R * rr, c + R * rr, c + R * rr], outline=ink, width=int(S * 0.004))
try:
    font = ImageFont.truetype("timesbd.ttf", int(S * 0.115))
except OSError:
    font = ImageFont.truetype("arialbd.ttf", int(S * 0.105))
NUM = ["XII", "I", "II", "III", "IIII", "V", "VI", "VII", "VIII", "IX", "X", "XI"]
for h, txt in enumerate(NUM):
    if h == 6:
        continue                                 # the seconds sub-dial sits at VI
    ang = math.radians(h * 30)
    rr = R * 0.66
    x, y = c + rr * math.sin(ang), c - rr * math.cos(ang)
    tw = d.textbbox((0, 0), txt, font=font)
    layer = Image.new("RGBA", (tw[2] - tw[0] + 8, tw[3] - tw[1] + 8), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text((4 - tw[0], 4 - tw[1]), txt, font=font, fill=ink + (255,))
    layer = layer.rotate(-h * 30, resample=Image.BICUBIC, expand=True)   # numerals radial, as on a real dial
    im.paste(layer, (int(x - layer.width / 2), int(y - layer.height / 2)), layer)
sc = (c, c + R * 0.42)                           # seconds sub-dial
sr = R * 0.17
d.ellipse([sc[0] - sr, sc[1] - sr, sc[0] + sr, sc[1] + sr], outline=ink, width=int(S * 0.004))
for k in range(12):
    ang = math.radians(k * 30)
    d.line([sc[0] + sr * 0.75 * math.sin(ang), sc[1] - sr * 0.75 * math.cos(ang), sc[0] + sr * math.sin(ang),
            sc[1] - sr * math.cos(ang)], fill=ink, width=int(S * 0.004))
d.line([sc[0], sc[1], sc[0] + sr * 0.85 * math.sin(math.radians(130)), sc[1] - sr * 0.85 * math.cos(math.radians(130))],
       fill=ink, width=int(S * 0.005))
blue = (28, 40, 92)


def hand(deg, length, width, spade):
    ang = math.radians(deg)
    ux, uy = math.sin(ang), -math.cos(ang)
    px, py = -uy, ux
    tail = -length * 0.18
    pts = [(c + ux * tail + px * width * 0.6, c + uy * tail + py * width * 0.6), (c + ux * length * 0.7 + px * width * 0.35,
           c + uy * length * 0.7 + py * width * 0.35)]
    if spade:                                    # a spade (Breguet-ish) widening near the tip
        pts += [(c + ux * length * 0.74 + px * width * 1.6, c + uy * length * 0.74 + py * width * 1.6)]
    pts += [(c + ux * length, c + uy * length)]
    if spade:
        pts += [(c + ux * length * 0.74 - px * width * 1.6, c + uy * length * 0.74 - py * width * 1.6)]
    pts += [(c + ux * length * 0.7 - px * width * 0.35, c + uy * length * 0.7 - py * width * 0.35),
            (c + ux * tail - px * width * 0.6, c + uy * tail - py * width * 0.6)]
    d.polygon(pts, fill=blue)


hand(10 * 30 + 10 * 0.5, R * 0.5, S * 0.016, True)      # hour hand at ten past ten
hand(10 * 6, R * 0.76, S * 0.011, True)                  # minute hand
d.ellipse([c - S * 0.03, c - S * 0.03, c + S * 0.03, c + S * 0.03], fill=blue)
out = ROOT / a.out
out.parent.mkdir(parents=True, exist_ok=True)
im.resize((a.px, a.px), Image.LANCZOS).save(out)
print("WATCH face", out)
