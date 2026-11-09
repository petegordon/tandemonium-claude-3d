"""Gold Standard frame mask: the gold frame's silhouette cut out of Pete's side ref, for make_gold_standard.py.

  blender -b --factory-startup --python scripts/gs_frame_mask.py -- [--debug]

refs/gold_standard/pete_refs/side.png has its transparency checkerboard baked into the pixels, so gold is found by
colour (saturated, gold/orange hue) and everything that is not frame is cut away with shapes drawn in the ref's own
pixel coordinates (wheels, guards, saddles, bars, lamp, fork, chainrings, cranks, pedals, chain).
Writes refs/gold_standard/frame_mask.png (white = frame) and with --debug frame_mask_overlay.png.
"""
import sys
from pathlib import Path

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SRC = ROOT / "refs" / "gold_standard" / "pete_refs" / "side.png"
OUT = ROOT / "refs" / "gold_standard"

HUB_R, HUB_F = (212, 520), (1322, 537)
BB_R, BB_F = (458, 543), (865, 553)


def load(p):
    im = bpy.data.images.load(str(p))
    w, h = im.size
    a = np.array(im.pixels[:], dtype=np.float32).reshape(h, w, 4)[::-1]     # row 0 = top, like the ref's pixels
    return a


def save(a, p):
    h, w = a.shape[:2]
    if a.ndim == 2:
        a = np.stack([a, a, a, np.ones_like(a)], 2)
    elif a.shape[2] == 3:
        a = np.concatenate([a, np.ones((h, w, 1), np.float32)], 2)
    im = bpy.data.images.new("o", w, h, alpha=True)
    im.pixels[:] = a[::-1].ravel()
    im.filepath_raw = str(p)
    im.file_format = "PNG"
    im.save()


def poly_mask(shape, pts):
    """Filled polygon (even-odd) in pixel coords."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    inside = np.zeros(shape, bool)
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        if y0 == y1:
            continue
        cond = ((yy >= min(y0, y1)) & (yy < max(y0, y1)))
        xint = x0 + (yy - y0) * (x1 - x0) / (y1 - y0)
        inside ^= cond & (xx < xint)
    return inside


def disc(shape, c, r):
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    return (xx - c[0]) ** 2 + (yy - c[1]) ** 2 <= r * r


def annulus_sector(shape, c, r0, r1, a0, a1):
    """Ring between radii r0..r1, angles a0..a1 in degrees measured from forward (+x in the ref) towards up."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    dx, dy = xx - c[0], c[1] - yy
    rr = np.hypot(dx, dy)
    ang = np.degrees(np.arctan2(dy, dx)) % 360
    return (rr >= r0) & (rr <= r1) & (ang >= a0) & (ang <= a1)


def erode(m, n=1):
    for _ in range(n):
        e = m.copy()
        e[1:] &= m[:-1]
        e[:-1] &= m[1:]
        e[:, 1:] &= m[:, :-1]
        e[:, :-1] &= m[:, 1:]
        m = e
    return m


def dilate(m, n=1):
    for _ in range(n):
        d = m.copy()
        d[1:] |= m[:-1]
        d[:-1] |= m[1:]
        d[:, 1:] |= m[:, :-1]
        d[:, :-1] |= m[:, 1:]
        m = d
    return m


def largest_components(m, min_px=1500):
    """Keep the connected blobs of at least min_px pixels (4-connected flood fill)."""
    h, w = m.shape
    lab = np.zeros((h, w), np.int32)
    sizes = []
    cur = 0
    ys, xs = np.nonzero(m)
    for y0, x0 in zip(ys, xs):
        if lab[y0, x0]:
            continue
        cur += 1
        stack = [(y0, x0)]
        lab[y0, x0] = cur
        n = 0
        while stack:
            y, x = stack.pop()
            n += 1
            for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if 0 <= yy < h and 0 <= xx < w and m[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = cur
                    stack.append((yy, xx))
        sizes.append(n)
    keep = [i + 1 for i, n in enumerate(sizes) if n >= min_px]
    return np.isin(lab, keep)


def frame_mask():
    a = load(SRC)
    rgb = a[..., :3]
    mx, mn = rgb.max(2), rgb.min(2)
    sat = (mx - mn) / np.maximum(mx, 1e-4)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    hue = np.degrees(np.arctan2(np.sqrt(3) * (g - b), 2 * r - g - b)) % 360
    # the baked checkerboard is neutral grey/white; gold, even its pale highlights, is not
    gold = (sat > 0.13) & (mx > 0.12) & (hue > 14) & (hue < 70)
    sh = gold.shape
    cut = np.zeros(sh, bool)
    # wheels: everything inside the tyres, plus the tyres (frame inside them is rebuilt as splayed stays)
    cut |= disc(sh, HUB_R, 212)
    cut |= disc(sh, HUB_F, 214)
    # guards
    cut |= annulus_sector(sh, HUB_R, 190, 250, 50, 215)
    cut |= annulus_sector(sh, HUB_F, 190, 252, 60, 215)
    # saddles, saddle clamps, stoker bars, captain bars + stem, lamp
    cut |= poly_mask(sh, [(160, 100), (440, 100), (440, 232), (160, 232)])                 # stoker saddle
    cut |= poly_mask(sh, [(620, 100), (910, 100), (910, 228), (620, 228)])                 # captain saddle
    cut |= poly_mask(sh, [(420, 100), (640, 100), (640, 240), (600, 240), (420, 170)])      # stoker bars
    cut |= poly_mask(sh, [(980, 40), (1350, 40), (1350, 205), (1195, 205), (980, 120)])     # captain bars
    cut |= poly_mask(sh, [(1255, 135), (1470, 135), (1470, 310), (1255, 310)])              # lamp + bracket
    # fork + steerer below the head tube
    cut |= poly_mask(sh, [(1228, 330), (1290, 330), (1345, 560), (1290, 560)])
    # chainrings, cranks, pedals
    cut |= disc(sh, BB_R, 66)
    cut |= disc(sh, BB_F, 66)
    for cx, (y0, y1) in ((462, (440, 670)), (880, (450, 680))):                             # crank arms
        cut |= poly_mask(sh, [(cx - 13, y0), (cx + 13, y0), (cx + 13, y1), (cx - 13, y1)])
    cut |= poly_mask(sh, [(445, 432), (535, 432), (535, 468), (445, 468)])                  # pedals
    cut |= poly_mask(sh, [(380, 636), (480, 636), (480, 676), (380, 676)])
    cut |= poly_mask(sh, [(866, 444), (955, 444), (955, 480), (866, 480)])
    cut |= poly_mask(sh, [(780, 650), (895, 650), (895, 695), (780, 695)])
    m = gold & ~cut
    # chains and hairlines out: an opening removes anything thinner than ~8 px; then fill pin-holes
    # close first (the white specular band along a tube's top reads as checkerboard), then open (drops the chains)
    m = erode(dilate(m, 3), 3) & ~cut
    m = dilate(erode(m, 6), 6) & ~cut
    m = largest_components(m)
    # fill enclosed highlight holes (background blobs that don't reach the border and are small)
    bg = largest_components(~m, 400)        # background blobs under 400 px are highlight holes
    m = ~bg & ~cut
    return a, m


if __name__ == "__main__":
    a, m = frame_mask()
    save(m.astype(np.float32), OUT / "frame_mask.png")
    if "--debug" in argv:
        rgb = a[..., :3].copy()
        rgb[m] = rgb[m] * 0.35 + np.array([0.0, 0.65, 1.0]) * 0.65
        save(rgb, OUT / "frame_mask_overlay.png")
    print("MASK", int(m.sum()), "px")
