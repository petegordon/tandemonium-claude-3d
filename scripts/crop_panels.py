"""Phase 1: crop one character's row of panels from the character turnaround sheet.

Finds figure bounding boxes by thresholding against the off-white background,
excluding the label text under each panel. Writes raw crops to refs/male/.
Run: <ComfyUI-claude venv python> scripts/crop_panels.py [male|female]
(top row = male, bottom row = female)
"""
import sys
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SHEET = ROOT / "refs" / "characters-turnaround.png"
CHAR = sys.argv[1] if len(sys.argv) > 1 else "male"
OUT = ROOT / "refs" / CHAR
OUT.mkdir(parents=True, exist_ok=True)
NAMES = ["front", "left", "rear", "riding"]

img = np.asarray(Image.open(SHEET).convert("RGB")).astype(np.float32)
h, w, _ = img.shape
bg = np.median(img[:20, :20].reshape(-1, 3), axis=0)
fg = np.abs(img - bg).max(axis=2) > 28

# Top row = male, bottom row = female. Split rows on the largest empty horizontal band near the middle.
rows = fg.sum(axis=1)
mid = slice(h // 3, 2 * h // 3)
empty = np.where(rows[mid] == 0)[0] + h // 3
split = int(np.median(empty)) if len(empty) else h // 2
row0 = 0 if CHAR == "male" else split
top = fg[row0:] if CHAR != "male" else fg[:split]

cols = top.sum(axis=0) > 0
spans, start = [], None
for x, c in enumerate(np.append(cols, False)):
    if c and start is None:
        start = x
    elif not c and start is not None:
        if x - start > 40:
            spans.append((start, x))
        start = None
print(CHAR, "sheet", w, h, "row split", split, "panels", spans)
assert len(spans) == 4, spans

for name, (x0, x1) in zip(NAMES, spans):
    band = top[:, x0:x1]
    r = np.where(band.sum(axis=1) > 0)[0]
    # Drop the label: the last vertical run of foreground rows separated by a gap.
    runs, s = [], r[0]
    for a, b in zip(r[:-1], r[1:]):
        if b - a > 6:
            runs.append((s, a)); s = b
    runs.append((s, r[-1]))
    fig = max(runs, key=lambda t: t[1] - t[0])
    y0, y1 = fig[0], fig[1] + 1
    xs = np.where(band[y0:y1].sum(axis=0) > 0)[0]
    bx0, bx1 = x0 + xs[0], x0 + xs[-1] + 1
    pad = 6
    y0, y1 = y0 + row0, y1 + row0
    box = (max(bx0 - pad, 0), max(y0 - pad, 0), min(bx1 + pad, w), min(y1 + pad, h))
    Image.open(SHEET).convert("RGB").crop(box).save(OUT / f"{name}_raw.png")
    print(name, "box", box, "size", box[2] - box[0], "x", box[3] - box[1])
