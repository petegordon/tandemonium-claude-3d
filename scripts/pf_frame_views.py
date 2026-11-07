"""Penny-Farthing tandem: put the prepped views on one shared scale before Pixal3D multi-view.

comfy_job.py prep crops each view square to its own mask, so the wide side view is scaled by the bike's LENGTH and
the narrow end view by its HEIGHT: the two disagree by ~2x and Pixal3D gets an inconsistent object. This rescales
the end views (front/back) so their content height equals the side view's content height and their bottom (the
tyre contact) sits on the same row. Side views are left alone.

  python scripts/pf_frame_views.py [--set pf_tandem/mesh]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
argv = sys.argv[1:]
SET = argv[argv.index("--set") + 1] if "--set" in argv else "pf_tandem/mesh"
D = ROOT / "refs" / SET / "prepped"


def bbox(im, bg):
    a = np.asarray(im.convert("RGB")).astype(int)
    diff = np.abs(a - np.array(bg)).sum(-1) > 40
    ys, xs = np.nonzero(diff)
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


for bg_name, bg in (("black", (0, 0, 0)), ("white", (255, 255, 255))):
    side = Image.open(D / f"left_{bg_name}.png")
    sx0, sy0, sx1, sy1 = bbox(side, bg)
    print(bg_name, "side content", sx1 - sx0, "x", sy1 - sy0, "bottom", sy1)
    for v in ("front", "back"):
        src = D / f"{v}_{bg_name}.png"
        orig = D / f"{v}_{bg_name}_unframed.png"
        if not orig.exists():
            Image.open(src).save(orig)
        im = Image.open(orig).convert("RGB")
        x0, y0, x1, y1 = bbox(im, bg)
        crop = im.crop((x0, y0, x1, y1))
        k = (sy1 - sy0) / (y1 - y0)
        crop = crop.resize((max(1, round(crop.width * k)), sy1 - sy0), Image.LANCZOS)
        out = Image.new("RGB", side.size, bg)
        out.paste(crop, ((side.width - crop.width) // 2, sy0))
        out.save(src)
        print(f"  {v}: content {x1-x0}x{y1-y0} -> {crop.width}x{crop.height} (k={k:.3f})")
