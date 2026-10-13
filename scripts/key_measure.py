"""Measure a garment from Pete's dressed key-colour images (the blue base-goose mannequin with one garment added).

  blender -b --factory-startup --python scripts/key_measure.py -- --garment jacket
      [--images refs/outfit_male_victorian/keyed/<g>]   (pair_front_left.png, pair_rear_right.png)
      [--key refs/key_views] [--worn out/outfit_male_victorian/worn/<g>/aligned.glb | none] [--out out/...]

The undressed pairs (refs/key_views/pair_*.png) and cameras.json are the calibration: orthographic cameras on OUR
base body, px_per_m known. Per figure (slot) of each dressed pair:
1. register: a small shift + scale (the generator may nudge the figure) that best fits the undressed body mask to the
   dressed blue (score: dressed-blue pixels on the body minus undressed-body pixels that became background);
2. key: blue = hue 185-215 deg, saturation > 0.35; background = the slot's corner grey (and the pad grey);
   garment = neither, within 0.25 m of the body and connected to it;
3. coverage: every body vertex is cast into each view where it is visible (first hit of a ray from the camera side);
   a vertex is covered when its visible views vote garment. Per body region (align_worn.py's _regions.npz):
   cover fraction and covered z range;
4. ease per body vertex: a covered vertex on a view's outline (normal across the view) walks outward along its
   projected normal over garment pixels until the background -> ease (m); walks that meet blue (another body part,
   e.g. an arm) or exceed 0.10 m are dropped. Per region: p10 / p50 / p90 and count (all views together);
5. accessories (hat, bow tie): the garment's 3D box (front gives x / z, side gives y / z);
6. metric check (Pete): the same outline widths of the aligned worn 3D model (vertices splatted into the same
   cameras); differences > 25 mm are flagged.
Writes <out>/<g>_key_measure.json and renders/keyed_<g>.png (dressed | garment mask over the body | outlines).
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
G = opt("--garment", "jacket")
IMG = ROOT / opt("--images", f"refs/outfit_male_victorian/keyed/{G}")
KEYD = ROOT / opt("--key", "refs/key_views")
WORN = opt("--worn", f"out/outfit_male_victorian/worn/{G}/aligned.glb")
OUT = ROOT / opt("--out", "out/outfit_male_victorian/keyed")
OUT.mkdir(parents=True, exist_ok=True)
REGF = ROOT / "out" / "outfit_male_victorian" / "worn" / "_regions.npz"
CAM = json.loads((KEYD / "cameras.json").read_text(encoding="utf-8"))
PAIRS = CAM["pairs"]
K = PAIRS["scale_from_view"]
PPM = PAIRS["px_per_m"]
W0, H0 = CAM["size_px"]
TGT = np.array(CAM["target"])
HEIGHTS = {"neck": 1.30, "chest": 1.15, "waist": 1.00, "hips": 0.85, "thigh": 0.65, "knee": 0.40, "shin": 0.25}
FLAG_MM = 25.0


def load_png(path):
    im = bpy.data.images.load(str(path))
    w, h = im.size
    px = np.array(im.pixels[:]).reshape(h, w, -1)[::-1, :, :3]
    bpy.data.images.remove(im)
    return px


def hsv(rgb):
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn + 1e-9
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.where(mx == r, (g - b) / d % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    return h, d / (mx + 1e-9), mx


def is_blue(rgb):
    h, s, v = hsv(rgb)
    return (h > 185) & (h < 215) & (s > 0.35) & (v > 0.25)


def project(p, view):
    """World point(s) -> pair-image pixel (x, y) for the view (its slot), y down."""
    c = CAM["views"][view]
    R, U = np.array(c["right"]), np.array(c["up"])
    rel = np.atleast_2d(p) - TGT
    x = W0 / 2 + rel @ R * CAM["px_per_m"]
    y = H0 / 2 - rel @ U * CAM["px_per_m"]
    pair = next(n for n, vs in PAIRS["slots"].items() if view in vs)
    slot = PAIRS["slots"][pair].index(view)
    return PAIRS["slot_offset_x_px"][slot] + x * K, y * K, pair, slot


def shift_mask(m, dx, dy, s, cx, cy):
    """Resample mask (or image) m under x' = cx + s (x - cx) + dx (same for y): nearest neighbour."""
    h, w = m.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    sx = np.round((xx - dx - cx) / s + cx).astype(int)
    sy = np.round((yy - dy - cy) / s + cy).astype(int)
    ok = (sx >= 0) & (sx < w) & (sy >= 0) & (sy < h)
    out = np.zeros_like(m)
    out[ok] = m[sy[ok], sx[ok]]
    return out


def dilate(m, it=1):
    """Binary dilation (8-neighbour) by array shifts (Blender ships no scipy)."""
    for _ in range(it):
        o = m.copy()
        o[1:] |= m[:-1]
        o[:-1] |= m[1:]
        o[:, 1:] |= m[:, :-1]
        o[:, :-1] |= m[:, 1:]
        o[1:, 1:] |= m[:-1, :-1]
        o[:-1, :-1] |= m[1:, 1:]
        o[1:, :-1] |= m[:-1, 1:]
        o[:-1, 1:] |= m[1:, :-1]
        m = o
    return m


def erode(m, it=1):
    return ~dilate(~m, it)


def grow_within(seed, allowed):
    """Geodesic reconstruction: the parts of `allowed` connected to `seed`."""
    cur = seed & allowed
    while True:
        nxt = dilate(cur, 4) & allowed
        if nxt.sum() == cur.sum():
            return nxt
        cur = nxt


def register(body0, blue1, bg1, cx, cy):
    best = (-1e18, 0, 0, 1.0)
    sub = (slice(None, None, 2), slice(None, None, 2))
    b0, bl, bgm = body0[sub], blue1[sub], bg1[sub]
    for s in np.arange(0.97, 1.0301, 0.01):
        for dy in range(-16, 17, 2):
            for dx in range(-16, 17, 2):
                t = shift_mask(b0, dx / 2, dy / 2, s, cx / 2, cy / 2)
                sc = (t & bl).sum() - 3 * (t & bgm).sum() - (bl & ~t).sum()
                if sc > best[0]:
                    best = (sc, dx, dy, s)
    return best[1:]


# ---- body ------------------------------------------------------------------------------------------------------
bpy.ops.wm.open_mainfile(filepath=str(ROOT / "out" / "base-goose" / "base_goose.blend"))
body = bpy.data.objects["base_goose_game"]
BV = np.array([v.co[:] for v in body.data.vertices])
BVH = BVHTree.FromPolygons([Vector(v) for v in BV], [tuple(p.vertices) for p in body.data.polygons])
REG = np.load(REGF)["reg"]

# ---- images ----------------------------------------------------------------------------------------------------
res = {"garment": G, "images": str(IMG.relative_to(ROOT)), "views": {}}
masks = {}
for pair, views in PAIRS["slots"].items():
    f = IMG / f"{pair}.png"
    if not f.exists():
        continue
    dressed = load_png(f)
    undressed = load_png(KEYD / f"{pair}.png")
    hP, wP = dressed.shape[:2]
    blue1 = is_blue(dressed)
    body0 = is_blue(undressed)
    bg0 = np.abs(undressed - undressed[5, 5]).max(-1) < 0.04
    other0 = ~bg0 & ~body0                     # the mannequin's own non-blue pixels (eyes, dark bill, anti-aliased rim)
    for slot, view in enumerate(views):
        x0 = slot * 768
        sl = np.s_[:, x0:x0 + 768]
        corner = np.median(np.concatenate([dressed[5:40, x0 + 5:x0 + 40].reshape(-1, 3),
                                           dressed[5:40, x0 + 728:x0 + 763].reshape(-1, 3)]), axis=0)
        bg1 = (np.abs(dressed[sl] - corner).max(-1) < 0.07) | \
              (np.abs(dressed[sl] - 140 / 255).max(-1) < 0.04)
        cx, cy = 384, 512
        dx, dy, s = register(body0[sl], blue1[sl], bg1, cx, cy)
        b0 = shift_mask(body0[sl], dx, dy, s, cx, cy)
        near = np.zeros_like(b0)
        rad = int(0.25 * PPM)
        ys, xs = np.where(b0)
        ylo, yhi = max(0, ys.min() - rad), min(hP, ys.max() + rad)
        xlo, xhi = max(0, xs.min() - rad), min(768, xs.max() + rad)
        near[ylo:yhi, xlo:xhi] = True
        # ... are garment only where the dressed image changed there (change detection against the registered mannequin)
        und = shift_mask(undressed[sl], dx, dy, s, cx, cy)
        changed = np.abs(dressed[sl] - und).max(-1) > 0.12
        o0 = shift_mask(other0[sl], dx, dy, s, cx, cy)
        real = dilate(erode(changed & o0, 2), 2)      # resampling slivers at eye / bill edges are not garment
        garm = ~blue1[sl] & ~bg1 & near & ~(o0 & ~real)
        garm = dilate(erode(garm, 2), 2) & garm         # no 1-2 px slivers (resampled outline halo)
        garm = grow_within(dilate(b0, 3), garm)          # only parts connected to the body
        masks[view] = {"garm": garm, "body": b0, "blue": blue1[sl], "reg": (dx, dy, s), "x0": x0}
        res["views"][view] = {"shift_px": [int(dx), int(dy)], "scale": round(float(s), 3),
                              "garment_px": int(garm.sum())}

# ---- coverage ------------------------------------------------------------------------------------------------
votes = np.zeros(len(BV))
seen = np.zeros(len(BV))
for view, m in masks.items():
    c = CAM["views"][view]
    back = np.array(c["back"])                                   # camera +Z: from the target toward the camera
    x, y, pair, slot = project(BV, view)
    dx, dy, s = m["reg"]
    xs = np.round(384 + s * (x - m["x0"] - 384) + dx).astype(int)
    ys = np.round(512 + s * (y - 512) + dy).astype(int)
    for i, p in enumerate(BV):
        o = Vector(p + back * 3.0)
        hit = BVH.ray_cast(o, Vector(-back), 3.1)
        if hit[0] is None or (Vector(p) - hit[0]).length > 0.004:
            continue
        if 0 <= ys[i] < m["garm"].shape[0] and 0 <= xs[i] < 768:
            seen[i] += 1
            votes[i] += m["garm"][ys[i], xs[i]]
cov = (seen > 0) & (votes / np.maximum(seen, 1) >= 0.5)
regions = {}
for r in sorted(set(REG)):
    mr = REG == r
    vis = mr & (seen > 0)
    if vis.sum() == 0:
        continue
    frac = float((cov & mr).sum() / vis.sum())
    if frac >= 0.05:
        regions[r] = {"cover": round(frac, 2), "z_m": [round(float(BV[cov & mr, 2].min()), 3),
                                                       round(float(BV[cov & mr, 2].max()), 3)]}
res["regions"] = regions
res["covered_z_m"] = [round(float(BV[cov, 2].min()), 3), round(float(BV[cov, 2].max()), 3)] if cov.any() else None
# ---- ease per outline vertex -------------------------------------------------------------------------------
BN = np.array([v.normal[:] for v in body.data.vertices])
ease_v = np.full(len(BV), np.nan)
MAXW = 0.10
for view, m in masks.items():
    c = CAM["views"][view]
    back, R, U = np.array(c["back"]), np.array(c["right"]), np.array(c["up"])
    x, y, _, _ = project(BV, view)
    dx, dy, s_ = m["reg"]
    xs = 384 + s_ * (x - m["x0"] - 384) + dx
    ys = 512 + s_ * (y - 512) + dy
    rim = cov & (np.abs(BN @ back) < 0.25)
    garm, blue = m["garm"], m["blue"]
    h, w = garm.shape
    step_max = int(MAXW * PPM * s_)
    for i in np.where(rim)[0]:
        d2 = np.array([BN[i] @ R, -(BN[i] @ U)])
        nn = np.linalg.norm(d2)
        if nn < 0.5:
            continue
        d2 /= nn
        k, inside, hit_blue = 1, 0, False
        while k <= step_max:
            px, py = int(round(xs[i] + d2[0] * k)), int(round(ys[i] + d2[1] * k))
            if not (0 <= px < w and 0 <= py < h):
                break
            if garm[py, px]:
                inside = k
            elif blue[py, px] and k > 3:
                hit_blue = True
                break
            elif k > 3 and not garm[py, px]:
                break
            k += 1
        if hit_blue or k > step_max or inside == 0:
            continue
        e = inside / (PPM * s_)
        ease_v[i] = e if np.isnan(ease_v[i]) else max(ease_v[i], e)
for r, d in regions.items():
    e = ease_v[(REG == r) & ~np.isnan(ease_v)] * 1000
    if len(e) >= 5:
        d["ease_mm_p10_50_90"] = np.percentile(e, [10, 50, 90]).round(1).tolist()
        d["ease_n"] = int(len(e))
np.savez_compressed(OUT / f"{G}_coverage.npz", covered=cov, votes=votes, seen=seen, ease=ease_v)


# ---- outlines / ease -------------------------------------------------------------------------------------------
def row_of(z, view):
    _, y, _, _ = project(np.array([[0, 0, z]]), view)
    dx, dy, s = masks[view]["reg"]
    return int(round(512 + s * (y[0] - 512) + dy))


def centre_x(view):
    x, _, _, _ = project(np.array([[0, 0.02, 1.0]]), view)
    dx, dy, s = masks[view]["reg"]
    return int(round(384 + s * (x[0] - masks[view]["x0"] - 384) + dx))


def run_around(row, cx):
    if not row[cx]:
        return None
    a = cx
    while a > 0 and row[a - 1]:
        a -= 1
    b = cx
    while b < len(row) - 1 and row[b + 1]:
        b += 1
    return a, b


def outline(view, z, union_mask):
    m = masks[view]
    r = row_of(z, view)
    if not (0 <= r < m["body"].shape[0]):
        return None
    cx = centre_x(view)
    rb = run_around(m["body"][r], cx)
    ru = run_around(union_mask[r], cx)
    if rb is None or ru is None:
        return None
    cap = int(0.10 * PPM * m["reg"][2])               # never more than 10 cm past the body: keeps the arms out
    ru = (max(ru[0], rb[0] - cap), min(ru[1], rb[1] + cap))
    return rb, ru, r


ease = {}
for view in ("front", "left", "rear", "right"):
    if view not in masks:
        continue
    m = masks[view]
    union = m["body"] | m["garm"]
    ease[view] = {}
    for name, z in HEIGHTS.items():
        o = outline(view, z, union)
        if o is None:
            continue
        (a, b), (ua, ub), r = o
        e = {}
        if m["garm"][r, ua]:
            e["side_a_mm"] = round((a - ua) / (PPM * m["reg"][2]) * 1000, 1)
        if m["garm"][r, ub]:
            e["side_b_mm"] = round((ub - b) / (PPM * m["reg"][2]) * 1000, 1)
        e["outer_width_mm"] = round((ub - ua) / (PPM * m["reg"][2]) * 1000, 1)
        ease[view][name] = e
res["outline"] = ease
res["outline_note"] = ("front/rear: side_a / side_b = the figure's image-left / image-right outline; left/right "
                       "views: image-left = the goose's front (left view) or back (right view)")

# garment extent per view (z range of garment pixels), e.g. coat tails below the hips
ext = {}
for view, m in masks.items():
    ys = np.where(m["garm"].any(axis=1))[0]
    if len(ys) == 0:
        continue
    s = m["reg"][2]
    _, y_floor, _, _ = project(np.array([[0, 0, 0.0]]), view)
    zf = lambda yy: (y_floor[0] - (yy - m["reg"][1] - 512) / s - 512) / PPM  # noqa: E731
    ext[view] = {"z_top_m": round(float(zf(ys.min())), 3), "z_bottom_m": round(float(zf(ys.max())), 3)}
res["garment_z_extent"] = ext

# ---- metric check against the aligned worn 3D model -----------------------------------------------------------
if WORN != "none" and (ROOT / WORN).exists():
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(ROOT / WORN))
    wv = np.concatenate([np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices])
                         for o in bpy.data.objects if o not in before and o.type == "MESH"])
    check = {}
    for view in ease:
        m = masks[view]
        x, y, _, _ = project(wv, view)
        dx, dy, s = m["reg"]
        xs = np.round(384 + s * (x - m["x0"] - 384) + dx).astype(int)
        ys = np.round(512 + s * (y - 512) + dy).astype(int)
        sil = np.zeros_like(m["body"])
        ok = (xs >= 0) & (xs < 768) & (ys >= 0) & (ys < sil.shape[0])
        sil[ys[ok], xs[ok]] = True
        sil = erode(dilate(dilate(sil, 1), 2), 2)          # splatted points -> a closed silhouette
        check[view] = {}
        for name in ease[view]:
            o = outline(view, HEIGHTS[name], sil)
            if o is None:
                continue
            _, (ua, ub), _ = o
            w3d = round((ub - ua) / (PPM * s) * 1000, 1)
            wk = ease[view][name]["outer_width_mm"]
            check[view][name] = {"key_mm": wk, "worn3d_mm": w3d, "diff_mm": round(w3d - wk, 1),
                                 "flag": bool(abs(w3d - wk) > FLAG_MM)}
    res["metric_check"] = check
    res["metric_flags"] = [f"{v}/{n}" for v, d in check.items() for n, e in d.items() if e["flag"]]

(OUT / f"{G}_key_measure.json").write_text(json.dumps(res, indent=1), encoding="utf-8")

# ---- overlay sheet ----------------------------------------------------------------------------------------------
tiles = []
for view, m in masks.items():
    h = m["body"].shape[0]
    t = np.ones((h, 768, 3)) * 0.85
    t[m["body"]] = (0.55, 0.75, 0.95)
    t[m["garm"]] = (0.9, 0.35, 0.1)
    t[m["garm"] & m["body"]] = (0.75, 0.2, 0.1)
    for name, z in HEIGHTS.items():
        r = row_of(z, view)
        if 0 <= r < h:
            t[r, :, :] = (0.2, 0.2, 0.2)
    tiles.append(t)
sheet = np.concatenate(tiles, axis=1)
im = bpy.data.images.new("ov", sheet.shape[1], sheet.shape[0])
im.pixels = np.concatenate([sheet[::-1], np.ones(sheet.shape[:2] + (1,))], -1).ravel().tolist()
im.filepath_raw = str(ROOT / "renders" / f"keyed_{G}.png")
im.file_format = "PNG"
im.save()
print("KEYMEASURE", json.dumps({k: v for k, v in res.items() if k in ("views", "regions", "garment_z_extent",
                                                                     "metric_flags")}))
