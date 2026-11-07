"""Join two copies of one penny-farthing side view back to back (riders facing away from each other).
  python scripts/pf_join.py --src refs/pf_tandem_v6/half_src.jpg --dir refs/pf_tandem_v6 [--gap 30]
Writes <dir>/half_rgba.png (keyed, faces right), <dir>/joined_raw.png (no connector yet).
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image

ap = argparse.ArgumentParser()
ap.add_argument("--src", required=True)
ap.add_argument("--dir", required=True)
ap.add_argument("--gap", type=int, default=30, help="px between the two small rear wheels")
ap.add_argument("--tag", default="")
a = ap.parse_args()
D = Path(a.dir)
BG = 213
im = np.asarray(Image.open(a.src).convert("RGB")).astype(np.float32)
diff = np.abs(im - BG).max(axis=2)
sat = im.max(axis=2) - im.min(axis=2)
alpha = np.clip((np.maximum(diff, sat * 1.5) - 10) / 18, 0, 1)
half = np.dstack([im, alpha * 255]).astype(np.uint8)
hi = Image.fromarray(half, "RGBA")
bb = hi.getchannel("A").point(lambda v: 255 if v > 128 else 0).getbbox()
hi = hi.crop(bb)
hi.save(D / "half_rgba.png")
w, h = hi.size
W = 2 * w + a.gap + 240
H = max(h + 240, round(W / 1.5))
W = round(H * 1.5)
TOP = (H - h) // 2
C = W // 2
canvas = Image.new("RGBA", (W, H), (BG, BG, BG, 255))
canvas.alpha_composite(hi, (C + a.gap // 2, TOP))                                   # faces right
canvas.alpha_composite(hi.transpose(Image.FLIP_LEFT_RIGHT), (C - a.gap // 2 - w, TOP))  # faces left
canvas.convert("RGB").save(D / f"joined_raw{a.tag}.png")
lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
lay.alpha_composite(hi, (C + a.gap // 2, TOP))
lay.alpha_composite(hi.transpose(Image.FLIP_LEFT_RIGHT), (C - a.gap // 2 - w, TOP))
lay.save(D / f"halves{a.tag}.png")
print("[pf_join] half", hi.size, "canvas", (W, H), "centre", C)
