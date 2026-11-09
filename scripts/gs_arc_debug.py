"""Gold Standard core tubes: the measured stroke (red) vs the fitted smooth arc (cyan, with its radius as thin lines)
over Pete's side ref, plus each tube's bend (curvature) along its length -> renders/gold_standard/arc_debug.png.
Run make_gold_standard.py with --arc-debug first.

  blender -b --factory-startup --python scripts/gs_arc_debug.py
"""
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REN = ROOT / "renders" / "gold_standard"
im = bpy.data.images.load(str(ROOT / "refs/gold_standard/pete_refs/side.png"))
w, h = im.size
ref = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1, :, :3].copy()
x0, y0, x1, y1 = 180, 200, 1260, 580
S = 2
crop = ref[y0:y1, x0:x1]
crop = crop.repeat(S, 0).repeat(S, 1) * 0.55 + 0.25


def dot(img, x, y, col, rad=1):
    X, Y = int(round((x - x0) * S)), int(round((y - y0) * S))
    img[max(Y - rad, 0):Y + rad + 1, max(X - rad, 0):X + rad + 1] = col


for nm in ("TUBE1", "TUBE2"):
    f = REN / f"arc_{nm}.npz"
    if not f.exists():
        continue
    d = np.load(f)
    for x, y in d["raw"]:
        dot(crop, x, y, (1, 0.1, 0.1), 1)
    Sx = d["S"]
    T = np.gradient(Sx, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    N = np.stack([-T[:, 1], T[:, 0]], 1)
    for (x, y), r, n in zip(Sx, d["r"], N):
        dot(crop, x, y, (0, 1, 1), 0)
        dot(crop, x + n[0] * r, y + n[1] * r, (0.2, 1, 0.3), 0)
        dot(crop, x - n[0] * r, y - n[1] * r, (0.2, 1, 0.3), 0)
    for x, y in d["cp"]:
        dot(crop, x, y, (1, 1, 0), 3)

# curvature strips: one per tube, 1/m, centre line = 0, +-10 1/m full height
strips = []
for nm in ("TUBE1", "TUBE2"):
    f = REN / f"bend_{nm}.npz"
    pane = np.full((160, crop.shape[1], 3), 0.12, np.float32)
    pane[80] = 0.4
    for kk in (2.0, 5.0):
        pane[int(80 - kk * 7)] = 0.25
        pane[int(80 + kk * 7)] = 0.25
    if f.exists():
        k = np.load(f)["k"]
        xs = np.linspace(0, crop.shape[1] - 1, len(k)).astype(int)
        ys = np.clip(80 - k * 7, 0, 159).astype(int)
        col = (1, 0.8, 0.2) if nm == "TUBE1" else (0.3, 0.8, 1)
        for x, y in zip(xs, ys):
            pane[max(y - 1, 0):y + 2, x] = col
    strips.append(pane)
out = np.concatenate([crop] + strips, 0)
H, W = out.shape[:2]
o = bpy.data.images.new("o", W, H)
o.pixels[:] = np.concatenate([out[::-1], np.ones((H, W, 1), np.float32)], 2).ravel()
o.filepath_raw = str(REN / "arc_debug.png")
o.file_format = "PNG"
o.save()
print("WROTE", REN / "arc_debug.png")
