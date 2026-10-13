"""Pack key_views.py's four 1024x1536 views into the two 1536x1024 pairs Pete dresses (front|left, rear|right).

  .venv python scripts/key_pairs.py <dir>     (reads <dir>/{front,left,rear,right}.png, writes <dir>/pair_*.png and the
                                              "pairs" block of <dir>/cameras.json)
"""
import json
import sys
from pathlib import Path

from PIL import Image

D = Path(sys.argv[1])
cams = json.loads((D / "cameras.json").read_text(encoding="utf-8"))
W0, H0 = cams["size_px"]
k = 1024 / H0
w = round(W0 * k)
off = (768 - w) // 2
SLOTS = {"pair_front_left": ["front", "left"], "pair_rear_right": ["rear", "right"]}
for name, views in SLOTS.items():
    bg = Image.open(D / f"{views[0]}.png").convert("RGB").getpixel((2, 2))   # pad with the render's own grey
    c = Image.new("RGB", (1536, 1024), bg)
    for i, v in enumerate(views):
        im = Image.open(D / f"{v}.png").convert("RGB").resize((w, 1024), Image.LANCZOS)
        c.paste(im, (i * 768 + off, 0))
    c.save(D / f"{name}.png")
cams["pairs"] = {"size_px": [1536, 1024], "scale_from_view": k, "slots": SLOTS, "slot_offset_x_px": [off, 768 + off],
                 "slot_w_px": w, "px_per_m": cams["px_per_m"] * k}
(D / "cameras.json").write_text(json.dumps(cams, indent=1), encoding="utf-8")
print("pairs", D)
