"""P0.1: crop per-view images out of a labelled grid reference sheet (refs/v2/*.png).

  <ComfyUI-claude venv python> scripts/crop_sheet.py <char>

Cell boundaries snap to drawn divider lines when present. Reads chars/<char>.json "sheet": {"file": "refs/v2/...png", "grid": [cols, rows],
"views": {"front": 0, "left": 1, "rear": 3, "right_drawn": 2}} (cell index row-major).
Each cell's figure = union of foreground components bigger than MIN_FRAC of the cell (drops
the small label letters), padded; written to refs/<char>/<view>_raw.png. Prints per-view figure
height and a front-view left/right symmetry score so drifting panels show up before any 3D run.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
MIN_FRAC = 0.002
PAD = 8


def _bounds(a, n, axis):
    """Cell boundaries along one axis: a drawn divider line near each nominal split if there is
    one (generated sheets put them a few px off-centre), else the even split."""
    size = a.shape[1] if axis == 1 else a.shape[0]
    dark = (a.max(-1) < 70).mean(axis=0 if axis == 1 else 1)   # fraction of the line that is dark
    out = [0]
    for k in range(1, n):
        c = int(k * size / n)
        lo, hi = c - int(0.06 * size), c + int(0.06 * size)
        seg = dark[lo:hi]
        out.append(lo + int(np.argmax(seg)) if seg.max() > 0.9 else c)
    return out + [size]


def figure_box(fg):
    lab, n = ndimage.label(fg)
    if n == 0:
        raise ValueError("empty cell")
    sizes = ndimage.sum(fg, lab, range(1, n + 1))
    h = fg.shape[0]
    ok = []
    for i, sl in enumerate(ndimage.find_objects(lab)):
        label_text = sl[0].start < 0.1 * h and (sl[0].stop - sl[0].start) < 0.08 * h   # panel caption
        if sizes[i] > MIN_FRAC * fg.size and not label_text:
            ok.append(i + 1)
    keep = np.isin(lab, ok)
    ys, xs = np.where(keep)
    return keep, (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)


def main(char):
    cfg = json.loads((ROOT / "chars" / f"{char}.json").read_text())["sheet"]
    img = Image.open(ROOT / cfg["file"]).convert("RGB")
    a = np.asarray(img).astype(np.float32)
    h, w, _ = a.shape
    cols, rows = cfg["grid"]
    xs, ys = _bounds(a, cols, 1), _bounds(a, rows, 0)
    out = ROOT / "refs" / char
    out.mkdir(parents=True, exist_ok=True)
    report = {}
    for view, cell in cfg["views"].items():
        cx, cy = cell % cols, cell // cols
        x0, y0 = xs[cx] + 6, ys[cy] + 6                    # skip gutters / drawn divider lines
        x1, y1 = xs[cx + 1] - 6, ys[cy + 1] - 6
        c = a[y0:y1, x0:x1]
        bg = np.median(np.concatenate([c[:, -6:].reshape(-1, 3), c[-6:].reshape(-1, 3)]), 0)
        fg = np.abs(c - bg).max(-1) > 30
        fg = ndimage.binary_closing(fg, iterations=2)
        keep, (bx0, by0, bx1, by1) = figure_box(fg)
        box = (max(x0 + bx0 - PAD, x0), max(y0 + by0 - PAD, y0), min(x0 + bx1 + PAD, x1), min(y0 + by1 + PAD, y1))
        # paint dropped components (caption text, specks) with the backdrop colour
        clean = a.copy()
        drop = ndimage.binary_dilation(fg & ~keep, iterations=3) & ~ndimage.binary_dilation(keep, iterations=2)
        clean[y0:y1, x0:x1][drop] = bg
        Image.fromarray(clean.astype(np.uint8)).crop(box).save(out / f"{view}_raw.png")
        m = keep[by0:by1, bx0:bx1]
        report[view] = {"box": [int(v) for v in box], "fig_h": int(by1 - by0), "fig_w": int(bx1 - bx0),
                        "touches_edge": bool(bx0 <= 1 or by0 <= 1 or bx1 >= keep.shape[1] - 1 or by1 >= keep.shape[0] - 1)}
        if view == "front":
            report[view]["lr_symmetry_iou"] = round(float((m & m[:, ::-1]).sum() / max((m | m[:, ::-1]).sum(), 1)), 3)
    hs = [r["fig_h"] for r in report.values()]
    report["_height_spread_pct"] = round(100 * (max(hs) - min(hs)) / max(hs), 1)
    print(json.dumps(report, indent=1))
    (out / "crop_report.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
