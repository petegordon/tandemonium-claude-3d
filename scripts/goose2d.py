"""Shared 2D helpers for the drawn-goose <-> blue-mannequin tools (ref_dress.py, draw_parts.py): calibrated cameras,
mattes of drawn figures, and silhouette registration (similarity)."""
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
KEYD = ROOT / "refs" / "key_views"
WORN = ROOT / "refs" / "outfit_male_victorian" / "worn"
CAM = json.loads((KEYD / "cameras.json").read_text(encoding="utf-8"))
JS = json.loads((KEYD / "joints.json").read_text(encoding="utf-8"))
J = {k: np.array(v["head"]) for k, v in JS.items()}
T = {k: np.array(v["tail"]) for k, v in JS.items()}
W0, H0 = CAM["size_px"]
PPM = CAM["px_per_m"]
TGT = np.array(CAM["target"])
PARTS = json.loads((KEYD / "parts.json").read_text(encoding="utf-8"))


def matte(img):
    """Drawn figure on its panel grey. The background is taken per ROW from the row's own left and right edges (6 px
    each; per row the side closer to the panel grey, since a hand can reach one side), median-smoothed down the image, so vertical shading is followed.
    (Per-column estimates failed: a narrow side figure fills its columns, and the head can touch the crop's top.)"""
    im = img.astype(np.int16)
    left, right = np.median(im[:, :6], axis=1), np.median(im[:, -6:], axis=1)
    grey = np.median(np.concatenate([im[:, :6], im[:, -6:]], axis=1).reshape(-1, 3), axis=0)
    # per row, the edge closer to the panel's overall grey (a hand or foot can reach one side of the crop)
    use_left = np.abs(left - grey).max(-1) <= np.abs(right - grey).max(-1)
    bg = np.where(use_left[:, None], left, right)
    k = 21
    pad = np.pad(bg, ((k // 2, k // 2), (0, 0)), mode="edge")
    bg = np.stack([np.median(pad[r:r + k], axis=0) for r in range(len(bg))])
    m = np.abs(im - bg[:, None]).max(-1) > 28
    from scipy import ndimage                           # (venv only) bright highlights leave holes: fill them
    return ndimage.binary_fill_holes(m)


def mannequin(view):
    im = np.asarray(Image.open(KEYD / f"{view}.png").convert("RGB")).astype(np.int16)
    return im, np.abs(im - im[5, 5]).max(-1) > 10


def part_map(view):
    """Our body's part label per view pixel (-1 = background), from part_views.py's flat-colour render."""
    im = np.asarray(Image.open(KEYD / f"parts_{view}.png").convert("RGB")).astype(float) / 255
    names = PARTS["parts"]
    lin = np.array([PARTS["colors"][n] for n in names])
    cols = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)   # rendered in sRGB
    d = np.abs(im[..., None, :] - cols[None, None]).max(-1)
    lab = d.argmin(-1)
    lab[d.min(-1) > 0.08] = -1
    return lab, names


def to_px(p, view):
    c = CAM["views"][view]
    rel = np.atleast_2d(p) - TGT
    return np.stack([W0 / 2 + rel @ np.array(c["right"]) * PPM, H0 / 2 - rel @ np.array(c["up"]) * PPM], -1)


def z_to_row(z):
    return H0 / 2 - (z - TGT[2]) * PPM


def warp_sim(mask, s, tx, ty, shape, step=1):
    ys, xs = np.mgrid[0:shape[0]:step, 0:shape[1]:step]
    u = np.round((xs - tx) / s).astype(int)
    v = np.round((ys - ty) / s).astype(int)
    ok = (u >= 0) & (u < mask.shape[1]) & (v >= 0) & (v < mask.shape[0])
    out = np.zeros(xs.shape, mask.dtype)
    out[ok] = mask[v[ok], u[ok]]
    return out


def init_of(ref_m, man_m):
    ys, xs = np.where(ref_m)
    my, mx = np.where(man_m)
    s = (my.max() - my.min()) / (ys.max() - ys.min())
    return s, mx.mean() - s * xs.mean(), my.max() - s * ys.max()


def fit_sim(ref_m, man_m, rows_ok=None, s_range=None, init=None):
    """Similarity (s, tx, ty) maximising silhouette IoU (inside rows_ok), coarse grid then 1 px refine."""
    rows_ok = np.ones(man_m.shape[0], bool) if rows_ok is None else rows_ok
    s0, tx0, ty0 = init or init_of(ref_m, man_m)
    s_range = np.linspace(s0 * 0.94, s0 * 1.06, 13) if s_range is None else s_range
    best = (-1, s0, tx0, ty0)
    tgt4 = man_m[::4, ::4] & rows_ok[::4, None]
    for s in s_range:
        for dty in range(-60, 61, 6):
            for dtx in range(-60, 61, 6):
                w = warp_sim(ref_m, s, tx0 + dtx, ty0 + dty, man_m.shape, 4) & rows_ok[::4, None]
                iou = (w & tgt4).sum() / max(1, (w | tgt4).sum())
                if iou > best[0]:
                    best = (iou, s, tx0 + dtx, ty0 + dty)
    _, s, tx, ty = best
    tgt2 = man_m[::2, ::2] & rows_ok[::2, None]
    for dty in range(-6, 7):
        for dtx in range(-6, 7):
            w = warp_sim(ref_m, s, tx + dtx, ty + dty, man_m.shape, 2) & rows_ok[::2, None]
            iou = (w & tgt2).sum() / max(1, (w | tgt2).sum())
            if iou > best[0]:
                best = (iou, s, tx + dtx, ty + dty)
    return best
