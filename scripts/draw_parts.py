"""Name the body parts of the DRAWN naked goose (Pete's worn sheets, bare figure) to match our mannequin's part map.

  .venv python -I scripts/draw_parts.py [--figure bow_tie] [--model facebook/sam2.1-hiera-large]

Per view (front / left from sheet_front_side, rear from sheet_rear_right_v2; right = the left mirrored):
1. matte the drawn figure; register it onto our mannequin view by silhouette (similarity, goose2d.fit_sim);
2. seed points per part, placed on the DRAWING's own anatomy, not just our landmarks mapped over:
   - front / rear arms: the arm hangs clear of the body, so on each row the outer silhouette run is the arm; its
     centreline from our shoulder (mapped) to the lowest arm run (the hand tip) carries upper-arm / forearm / hand seeds
     at our rig's shoulder -> elbow -> wrist -> hand-tip proportions;
   - front / rear legs: below the crotch the two inner runs are the legs; thigh / shin / foot seeds sit on each leg's
     centreline at our hip / knee / ankle / toe heights (mapped);
   - side views: arms overlap the torso, so seeds come from our landmarks mapped over, and the dark parts (hand, shin,
     foot are black in the drawing; thighs are brown) snap to the nearest dark pixels;
   - head / neck / torso / tail: our landmarks mapped over;
3. SAM 2.1, every part an object; each figure pixel takes the part with the highest logit (> 0), the rest the nearest
   labelled part. Writes refs/outfit_male_victorian/worn/parts/<view>_labels.npy (drawing px, -1 = background),
   <view>_reg.json (similarity, seeds) and renders/drawn_parts.png: drawing tinted by part + seeds | our part map.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))
import goose2d as g2  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--figure", default="bow_tie")
ap.add_argument("--model", default="facebook/sam2.1-hiera-large")
a = ap.parse_args()
OUT = g2.WORN / "parts"
OUT.mkdir(parents=True, exist_ok=True)
J, T = g2.J, g2.T
NAMES = g2.PARTS["parts"]
COL = {n: np.array(g2.PARTS["colors"][n]) for n in NAMES}


def src(view):
    if view == "rear":
        return g2.WORN / a.figure / "rear_v2_raw.png"
    return g2.WORN / a.figure / f"{view}_raw.png"


chain = [J["LeftArm"], J["LeftForeArm"], J["LeftHand"], T["LeftHand"]]
seg = [np.linalg.norm(chain[i + 1] - chain[i]) for i in range(3)]
F_E, F_W = seg[0] / sum(seg), (seg[0] + seg[1]) / sum(seg)
ARM_SEEDS = {"upper_arm": [0.30 * F_E, 0.70 * F_E], "forearm": [F_E + 0.3 * (F_W - F_E), F_E + 0.7 * (F_W - F_E)],
             "hand": [F_W + 0.45 * (1 - F_W), F_W + 0.8 * (1 - F_W)]}

from transformers import Sam2Model, Sam2Processor  # noqa: E402
dev = "cuda" if torch.cuda.is_available() else "cpu"
proc = Sam2Processor.from_pretrained(a.model)
model = Sam2Model.from_pretrained(a.model, torch_dtype=torch.float32).to(dev).eval()

tiles = []
for view in ("front", "left", "rear"):
    ref = np.asarray(Image.open(src(view)).convert("RGB"))
    rm = g2.matte(ref)
    man, mm = g2.mannequin(view)
    iou, s, tx, ty = g2.fit_sim(rm, mm)
    to_d = lambda xy: ((xy[0] - tx) / s, (xy[1] - ty) / s)  # noqa: E731  view px -> drawing px
    mapped = lambda p: to_d(g2.to_px(p, view)[0])  # noqa: E731
    lum = ref.mean(-1) / 255
    dark = rm & (lum < 0.22)
    fy, fx = np.where(rm)
    dy_, dx_ = np.where(dark)
    seeds = {}

    def add(part, uv, snap_dark=False):
        u, v = uv
        if snap_dark and len(dx_):
            d = np.hypot(dx_ - u, dy_ - v)
            if d.min() < 40:
                u, v = dx_[d.argmin()], dy_[d.argmin()]
        elif not (0 <= int(v) < rm.shape[0] and 0 <= int(u) < rm.shape[1] and rm[int(v), int(u)]):
            d = np.hypot(fx - u, fy - v)
            if d.min() > 15:
                return
            u, v = fx[d.argmin()], fy[d.argmin()]
        seeds.setdefault(part, []).append((float(u), float(v)))

    add("head", mapped(J["Neck3"] + np.array([0, -0.06, 0.10])))
    add("head", mapped(J["Neck3"] + np.array([0, -0.04, 0.16])))
    if view != "rear":
        add("head", mapped(J["Head"] + np.array([0, -0.05, 0])))
    for b in ("Neck", "Neck1", "Neck2", "Neck3"):
        add("neck", mapped(J[b] + np.array([0, 0, 0.01])))
    for b in ("Spine", "Spine1", "Spine2"):
        add("torso", mapped(J[b]))
    if view in ("rear", "left"):
        add("tail", mapped(J["Hips"] + np.array([0, 0.20, -0.10])))
    sides = ("L", "R") if view in ("front", "rear") else ("L",)
    centre_u = mapped(np.array([0, 0, 1.0]))[0]
    for k in sides:
        sname = "Left" if k == "L" else "Right"
        if view in ("front", "rear"):
            pv = mapped(J[f"{sname}Arm"])
            sd = 1 if mapped(T[f"{sname}Hand"])[0] > centre_u else -1
            # follow ONE continuous arm run downward: once it has started, stop when the separate outer run ends
            # (or jumps sideways) -- below the hand the thighs must not be taken for the arm
            pts, miss = [], 0
            v_lo = int(mapped(np.array([0, 0, 0.45]))[1])
            for r in range(int(pv[1]) + 5, min(v_lo, rm.shape[0])):
                xs = np.where(rm[r])[0]
                xs = xs[sd * (xs - centre_u) > 0]
                found = None
                if len(xs) >= 2:
                    xs = np.sort(xs) if sd > 0 else np.sort(xs)[::-1]
                    gaps = np.where(np.abs(np.diff(xs)) > 2)[0]
                    if len(gaps):
                        outer = xs[gaps[-1] + 1:]
                        # start on a real arm (>= 8 px wide), then follow it (<= 12 px drift per row)
                        if (pts and abs(outer.mean() - pts[-1][0]) < 12) or (not pts and len(outer) >= 8):
                            found = (outer.mean(), r)
                if found:
                    pts.append(found)
                    miss = 0
                elif pts:
                    miss += 1
                    if miss > 4:
                        if len(pts) < 15:          # a false start (a feather notch by the shoulder): search on
                            pts, miss = [], 0
                            continue
                        break
            if pts:
                poly = np.array([pv] + pts + [(pts[-1][0], pts[-1][1] + 4)])
                L = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(poly, axis=0).T))])
                for part, fr in ARM_SEEDS.items():
                    for f in fr:
                        t = f * L[-1]
                        i = min(np.searchsorted(L, t), len(L) - 1)
                        add(f"{part}_{k}", tuple(poly[i]))
            # legs: inner runs below the crotch
            for part, (b0, b1, fs) in {"thigh": ("UpLeg", "Leg", (0.25, 0.5, 0.8)), "shin": ("Leg", "Foot", (0.3, 0.7)),
                                       "foot": ("Foot", "ToeBase", (0.6,))}.items():
                for f in fs:
                    p = J[f"{sname}{b0}"] + f * (J[f"{sname}{b1}"] - J[f"{sname}{b0}"])
                    u, v = mapped(p)
                    r = int(round(v))
                    if not (0 <= r < rm.shape[0]):
                        continue
                    xs = np.where(rm[r])[0]
                    runs = np.split(xs, np.where(np.diff(xs) > 2)[0] + 1) if len(xs) else []
                    runs = [q for q in runs if len(q) and sd * (q.mean() - centre_u) > 0]
                    if runs:
                        inner = min(runs, key=lambda q: abs(q.mean() - centre_u))
                        add(f"{part}_{k}", (inner.mean(), r))
        else:                                   # side view: mapped landmarks, dark parts snap to dark pixels
            for part, fr in ARM_SEEDS.items():
                for f in fr:
                    segs = np.cumsum([0] + seg) / sum(seg)
                    i = min(np.searchsorted(segs, f) - 1, 2)
                    t = (f - segs[i]) / (segs[i + 1] - segs[i])
                    p = chain[i] + t * (chain[i + 1] - chain[i])
                    add(f"{part}_{k}", mapped(p), snap_dark=(part == "hand"))
            for part, (b0, b1, fs) in {"thigh": ("UpLeg", "Leg", (0.25, 0.5, 0.8)), "shin": ("Leg", "Foot", (0.3, 0.7)),
                                       "foot": ("Foot", "ToeBase", (0.6,))}.items():
                for f in fs:
                    p = J[f"{sname}{b0}"] + f * (J[f"{sname}{b1}"] - J[f"{sname}{b0}"])
                    add(f"{part}_{k}", mapped(p), snap_dark=(part in ("shin", "foot")))
    # SAM: every seeded part an object (its seeds positive, a few seeds of other parts negative)
    up = 2.5
    objs = [n for n in NAMES if n in seeds]
    allp = [(n, p) for n in objs for p in seeds[n]]
    pts_all, lbl_all = [], []
    for n in objs:
        pos = seeds[n]
        neg = [p for m_, p in allp if m_ != n]
        pts_all.append([[u * up, v * up] for u, v in pos + neg])
        lbl_all.append([1] * len(pos) + [0] * len(neg))
    kmax = max(len(p) for p in pts_all)
    for p, lb in zip(pts_all, lbl_all):
        while len(p) < kmax:
            p.append([0.0, 0.0])
            lb.append(-10)
    big = Image.fromarray(ref).resize((int(ref.shape[1] * up), int(ref.shape[0] * up)), Image.LANCZOS)
    inputs = proc(images=big, input_points=[pts_all], input_labels=[lbl_all], return_tensors="pt").to(dev)
    with torch.no_grad():
        out = model(**inputs, multimask_output=False)
    lg = proc.post_process_masks(out.pred_masks.cpu(), inputs["original_sizes"].cpu(), binarize=False)[0][:, 0].numpy()
    lg = np.stack([np.asarray(Image.fromarray(x).resize((ref.shape[1], ref.shape[0]), Image.BILINEAR)) for x in lg])
    best = lg.argmax(0)
    lab = np.where(rm & (lg.max(0) > 0), np.array([NAMES.index(n) for n in objs])[best], -1)
    miss = rm & (lab < 0)
    if miss.any() and (lab >= 0).any():
        _, (iy, ix) = ndimage.distance_transform_edt(lab < 0, return_indices=True)
        lab[miss] = lab[iy[miss], ix[miss]]
    np.save(OUT / f"{view}_labels.npy", lab)
    (OUT / f"{view}_reg.json").write_text(json.dumps({"src": str(src(view).relative_to(g2.ROOT)), "iou": round(float(iou), 3),
                                                      "s": float(s), "tx": float(tx), "ty": float(ty),
                                                      "seeds": seeds}, indent=1), encoding="utf-8")
    if view == "left":
        np.save(OUT / "right_labels.npy", lab[:, ::-1])
    # tile: drawing tinted by part + seeds | our part map in the same frame
    t = ref.astype(float) / 255
    for i, n in enumerate(NAMES):
        m = lab == i
        t[m] = t[m] * 0.35 + COL[n] * 0.65
    ti = Image.fromarray((t * 255).astype(np.uint8)).resize((ref.shape[1] * 2, ref.shape[0] * 2), Image.NEAREST)
    dr = ImageDraw.Draw(ti)
    for n, ps in seeds.items():
        for u, v in ps:
            dr.ellipse([u * 2 - 5, v * 2 - 5, u * 2 + 5, v * 2 + 5], fill=tuple(int(c * 255) for c in COL[n]), outline="white")
    pl, _ = g2.part_map(view)
    ys, xs = np.mgrid[0:ref.shape[0], 0:ref.shape[1]]
    vx = np.clip(np.round(xs * s + tx).astype(int), 0, g2.W0 - 1)
    vy = np.clip(np.round(ys * s + ty).astype(int), 0, g2.H0 - 1)
    ours = pl[vy, vx]
    o = np.zeros(ref.shape, float)
    for i, n in enumerate(NAMES):
        o[ours == i] = COL[n]
    oi = Image.fromarray((o * 255).astype(np.uint8)).resize(ti.size, Image.NEAREST)
    tiles += [ti, oi]
    print("VIEW", view, "iou", round(float(iou), 3), {n: len(p) for n, p in seeds.items()}, flush=True)
h = max(x.height for x in tiles)
sheet = Image.new("RGB", (sum(x.width for x in tiles) + 10 * len(tiles), h), "white")
x = 0
for t_ in tiles:
    sheet.paste(t_, (x, 0))
    x += t_.width + 10
sheet.save(g2.ROOT / "renders" / "drawn_parts.png")
print("SHEET", g2.ROOT / "renders" / "drawn_parts.png")
