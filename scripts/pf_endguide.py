"""Edge-on end-view guide for the symmetric Penny-Farthing tandem, drawn at the side view's pixel scale.
Then Qwen repaints it in the side view's style (picture 1 = guide, picture 2 = side view).
  python scripts/pf_endguide.py --dir refs/pf_tandem_v5 [--render --seeds 7,21,42]
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ap = argparse.ArgumentParser()
ap.add_argument("--dir", required=True)
ap.add_argument("--render", action="store_true")
ap.add_argument("--seeds", default="7,21,42")
ap.add_argument("--extra", default="")
ap.add_argument("--tag", default="edge")
a = ap.parse_args()
D = Path(a.dir)

W, H, C = 1565, 1173, 782
BG, TYRE, BRASS, BLACK, LEATHER, WOOD = (214, 214, 214), (30, 30, 30), (222, 160, 30), (25, 22, 20), (150, 70, 45), (120, 55, 35)
im = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(im)
HUB, TOP, BOT = 680, 472, 882
# far-end parts peeking out: support wheel leg + saddle behind (drawn first)
d.rounded_rectangle([C - 70, 420, C + 70, 470], 20, fill=LEATHER, outline=(90, 40, 25), width=3)       # saddle, nose to camera
d.rectangle([C - 8, 470, C + 8, 520], fill=BRASS)                                                      # saddle post/spring
# tyre edge-on: tall narrow rounded strip
d.rounded_rectangle([C - 20, TOP, C + 20, BOT], 20, fill=TYRE)
d.rounded_rectangle([C - 9, TOP + 14, C + 9, BOT - 14], 9, fill=BRASS)                                 # rim glint between tyre walls
# fender: wider cap over the top of the tyre
d.rounded_rectangle([C - 32, TOP - 12, C + 32, 600], 30, fill=BLACK, outline=BRASS, width=4)
# hub axle and fork legs either side of the tyre
d.rectangle([C - 62, HUB - 14, C + 62, HUB + 14], fill=BRASS)
d.ellipse([C - 28, HUB - 28, C + 28, HUB + 28], fill=BRASS, outline=(160, 110, 20), width=3)
for s in (-1, 1):
    d.polygon([(C + s * 48, HUB), (C + s * 62, HUB), (C + s * 40, 440), (C + s * 28, 440)], fill=BLACK)
    d.line([(C + s * 55, HUB), (C + s * 34, 440)], fill=BRASS, width=2)
    # crank arm hanging down, pedal sticking out sideways
    d.rectangle([C + s * 62 - 9, HUB, C + s * 62 + 9, HUB + 85], fill=BRASS)
    x0, x1 = sorted((C + s * 70, C + s * 150))
    d.rounded_rectangle([x0, HUB + 72, x1, HUB + 98], 8, fill=BLACK, outline=BRASS, width=3)
# fork crown, steering head, stem
d.rounded_rectangle([C - 46, 425, C + 46, 450], 10, fill=BRASS)
d.rectangle([C - 14, 330, C + 14, 430], fill=BLACK)
d.ellipse([C - 24, 300, C + 24, 348], fill=BRASS)
# moustache handlebar with wooden grips
d.line([(C, 322), (C - 70, 312), (C - 120, 290)], fill=BRASS, width=16, joint="curve")
d.line([(C, 322), (C + 70, 312), (C + 120, 290)], fill=BRASS, width=16, joint="curve")
for s in (-1, 1):
    x0, x1 = sorted((C + s * 115, C + s * 205))
    d.rounded_rectangle([x0, 268, x1, 308], 18, fill=WOOD)
# one bell beside the stem
d.ellipse([C + 22, 368, C + 52, 398], fill=BRASS)
out = D / "end_edge_guide.png"
im.save(out)
print("[pf_endguide]", out, flush=True)
if not a.render:
    sys.exit(0)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfy_job import preflight, run, upload  # noqa: E402
from t2i_outfit import first_image, graph  # noqa: E402

preflight(7.0)
names = [upload(out, f"pfg_{D.name}_guide.png")]
p = ("Picture 1 is a rough flat drawing of a steampunk penny-farthing bicycle seen exactly END-ON, looking straight "
     "along its length, so the big wheel is seen edge-on as a thin tall vertical black tyre with a black-and-brass "
     "fender over its top; the brass hub axle crosses it, a black fork leg rises on each side of the tyre, a brass crank "
     "hangs down on each side with a pedal sticking out sideways, a brass moustache handlebar with two wooden grips "
     "spreads across the top with a small brass bell beside the stem, and the brown leather saddle peeks out behind "
     "the handlebar. Repaint picture 1 as a polished realistic 3D render "
     "with ornate Victorian materials (polished gold brass, black lacquer, studded brown leather, ribbed "
     "wooden grips). Keep the composition, scale and every part's position from picture 1 exactly; the wheel stays a "
     "thin edge-on strip, NOT a round wheel; no spokes visible. Left-right symmetrical, orthographic. Plain flat "
     "light-grey background, soft even studio light, no shadow, no text. " + a.extra)
for s in a.seeds.split(","):
    outs, dt, _ = run(graph(names, p, int(s), 4, f"t2i/pfg_{D.name}_{a.tag}_s{s}"))
    o = D / "views" / f"{a.tag}_s{s}.png"
    Image.open(first_image(outs)).convert("RGB").save(o)
    print("[pf_endguide]", o, f"{dt:.0f}s", flush=True)
