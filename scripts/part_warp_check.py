"""Check the part warp on the body model itself: the glove figure warped onto our mannequin, per view.

  .venv python -I scripts/part_warp_check.py
Prints silhouette IoU (global similarity only vs the part warp) and writes renders/part_warp_check.png:
per view, the warped drawing over our silhouette outline, with the control points (ours green, drawing red -> ours).
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import goose2d as g2  # noqa: E402
import part_warp as pw  # noqa: E402

tiles = []
for view in ("front", "left", "rear"):
    bm = pw.body_model(view)
    man, mm = g2.mannequin(view)
    s, tx, ty = bm["cp"]["sim"]
    glob = g2.warp_sim(bm["matte"], s, tx, ty, mm.shape)
    rgb, ok = pw.sample(bm["ref"], bm["u"], bm["v"])
    wm, _ = pw.sample(bm["matte"].astype(np.uint8), bm["u"], bm["v"])
    wm = wm.astype(bool) & ok
    iou_g = (glob & mm).sum() / (glob | mm).sum()
    iou_w = (wm & mm).sum() / (wm | mm).sum()
    print(view, "IoU global", round(float(iou_g), 3), "part warp", round(float(iou_w), 3),
          "controls", len(bm["cp"]["names"]))
    t = np.where(wm[..., None], rgb, 200).astype(np.uint8)
    edge = mm & ~np.roll(mm, 1, 0) | mm & ~np.roll(mm, 1, 1) | mm & ~np.roll(mm, -1, 0) | mm & ~np.roll(mm, -1, 1)
    t[edge] = (0, 140, 255)
    im = Image.fromarray(t)
    dr = ImageDraw.Draw(im)
    for o, n in zip(bm["cp"]["ours"], bm["cp"]["names"]):
        if n != "corner":
            dr.ellipse([o[0] - 6, o[1] - 6, o[0] + 6, o[1] + 6], outline=(0, 200, 0), width=3)
    tiles.append(im.resize((g2.W0 // 2, g2.H0 // 2)))
sheet = Image.new("RGB", (sum(t.width for t in tiles), tiles[0].height), "white")
x = 0
for t in tiles:
    sheet.paste(t, (x, 0))
    x += t.width
sheet.save(g2.ROOT / "renders" / "part_warp_check.png")
