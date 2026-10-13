"""Dress the blue mannequin with a garment cut from Pete's reference DRAWINGS (no 3D model in between).

  .venv python -I scripts/ref_dress.py --garment jacket [--model facebook/sam2.1-hiera-large]

Per view (front / left from sheet_front_side, rear from sheet_rear_right_v2 -- bow tie + breeches: the squeezed
fix-sheet rears; right = the left result mirrored):
1. matte the drawn figure (colour distance from each pixel column's commonest grey, as crop_worn_sheet.py);
2. register it onto the mannequin's view (refs/key_views/<view>.png): similarity x = s u + tx, y = s v + ty. The scale
   s comes from the bare glove panel of the same sheet and view (silhouette IoU over the whole figure), then each
   garment's figure is placed by IoU over its TRUST bands (rows the garment never reaches: head, legs, ...);
3. SAM 2.1 on the drawing (upscaled x2.5): positives / negatives = OUR body landmarks (garment_prompts.PROMPTS)
   projected through the calibrated camera and mapped into the drawing, snapped to the figure (<= 20 px);
   the mask keeps the parts that hold a positive point, inside the figure;
   (front / rear: the drawn arms hang steeper than ours. The angle is measured once per sheet / view on the bare
   glove figure (its hand tips are clear), then only a band along the drawn arm (shoulder -> hand, radius ARM_R) is
   turned about OUR shoulder joint, blended in over the top of the arm -- the sleeve lands on our arm, the coat
   skirt stays put);
4. composite: the mannequin view with the drawing's pixels where the warped mask is -> out/<set>/dressed/<g>/<view>.png
   (+ cameras.json, pairs via key_pairs.py) for key_measure.py; and renders/refdress_<g>.png: drawing + mask + prompts
   | composite, per view.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from garment_prompts import LM, TRUST, prompts_for  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--garment", required=True)
ap.add_argument("--model", default="facebook/sam2.1-hiera-large")
a = ap.parse_args()
G = a.garment
ROOT = Path(__file__).resolve().parents[1]
W = ROOT / "refs" / "outfit_male_victorian" / "worn"
KEYD = ROOT / "refs" / "key_views"
OUT = ROOT / "out" / "outfit_male_victorian" / "dressed" / G
OUT.mkdir(parents=True, exist_ok=True)
CAM = json.loads((KEYD / "cameras.json").read_text(encoding="utf-8"))
JS = json.loads((KEYD / "joints.json").read_text(encoding="utf-8"))
J = {k: np.array(v["head"]) for k, v in JS.items()}
T = {k: np.array(v["tail"]) for k, v in JS.items()}
W0, H0 = CAM["size_px"]
PPM = CAM["px_per_m"]
TGT = np.array(CAM["target"])
REAR_FIX = {"bow_tie", "breeches"}


def src_of(g, view):
    if view == "rear":
        return W / g / ("rear_raw.png" if g in REAR_FIX else "rear_v2_raw.png")
    return W / g / f"{view}_raw.png"


def matte(img):
    q = (img // 4 * 4).astype(np.int16)
    bg = np.empty((img.shape[1], 3))
    for x in range(img.shape[1]):
        vv, cc = np.unique(q[:, x], axis=0, return_counts=True)
        bg[x] = vv[cc.argmax()] + 2
    return np.abs(img.astype(np.int16) - bg[None]).max(-1) > 28


def mannequin(view):
    im = np.asarray(Image.open(KEYD / f"{view}.png").convert("RGB")).astype(np.int16)
    return im, np.abs(im - im[5, 5]).max(-1) > 10


def to_px(p, view):
    c = CAM["views"][view]
    rel = np.atleast_2d(p) - TGT
    return np.stack([W0 / 2 + rel @ np.array(c["right"]) * PPM, H0 / 2 - rel @ np.array(c["up"]) * PPM], -1)


def z_to_row(z):
    return H0 / 2 - (z - TGT[2]) * PPM


ARMS = []          # [(pivot_x, pivot_y, angle, our tip x, our tip y)] for the current view: view-space arm turns
ARM_DBG = []
ARM_R = 0.09       # m: band around the arm axis that turns with it


def src_xy(xs, ys, s, tx, ty):
    """View pixel -> drawing pixel: undo the arm turns (only near OUR arm axis, blended), then the similarity."""
    x, y = xs.astype(float), ys.astype(float)
    for px, py, ang, ex, ey in ARMS:
        ax, ay = ex - px, ey - py
        L2 = ax * ax + ay * ay
        t = np.clip(((x - px) * ax + (y - py) * ay) / L2, 0, 1.15)
        d = np.hypot(x - (px + t * ax), y - (py + t * ay))
        w = np.clip(1 - (d - ARM_R * PPM) / (0.03 * PPM), 0, 1) * np.clip(t / 0.25, 0, 1)
        c, sn = np.cos(-ang * w), np.sin(-ang * w)
        dx, dy = x - px, y - py
        x, y = px + c * dx - sn * dy, py + sn * dx + c * dy
    return (x - tx) / s, (y - ty) / s


def warp(mask, s, tx, ty, shape, step=1):
    """Ref mask -> view grid (every `step` px): view (x, y) samples the drawing through src_xy."""
    ys, xs = np.mgrid[0:shape[0]:step, 0:shape[1]:step]
    uf, vf = src_xy(xs, ys, s, tx, ty)
    u = np.round(uf).astype(int)
    v = np.round(vf).astype(int)
    ok = (u >= 0) & (u < mask.shape[1]) & (v >= 0) & (v < mask.shape[0])
    out = np.zeros(xs.shape, bool)
    out[ok] = mask[v[ok], u[ok]]
    return out


def fit(ref_m, man_m, s_range, rows_ok, init):
    """Grid search (s, tx, ty) maximising IoU inside rows_ok (view rows), at 1/4 resolution then refined."""
    step = 4
    tgt = man_m[::step, ::step] & rows_ok[::step, None]
    best = (-1, *init)
    s0, tx0, ty0 = init
    for s in s_range:
        for dty in range(-60, 61, 6):
            for dtx in range(-60, 61, 6):
                w = warp(ref_m, s, tx0 + dtx, ty0 + dty, man_m.shape, step) & rows_ok[::step, None]
                iou = (w & tgt).sum() / max(1, (w | tgt).sum())
                if iou > best[0]:
                    best = (iou, s, tx0 + dtx, ty0 + dty)
    _, s, tx, ty = best
    for dty in range(-6, 7, 1):
        for dtx in range(-6, 7, 1):
            w = warp(ref_m, s, tx + dtx, ty + dty, man_m.shape, 2) & rows_ok[::2, None]
            t2 = man_m[::2, ::2] & rows_ok[::2, None]
            iou = (w & t2).sum() / max(1, (w | t2).sum())
            if iou > best[0]:
                best = (iou, s, tx + dtx, ty + dty)
    return best


def init_of(ref_m, man_m):
    ys, xs = np.where(ref_m)
    my, mx = np.where(man_m)
    s = (my.max() - my.min()) / (ys.max() - ys.min())
    tx = mx.mean() - s * xs.mean()
    ty = my.max() - s * ys.max()
    return s, tx, ty


from transformers import Sam2Model, Sam2Processor  # noqa: E402
dev = "cuda" if torch.cuda.is_available() else "cpu"
proc = Sam2Processor.from_pretrained(a.model)
model = Sam2Model.from_pretrained(a.model, torch_dtype=torch.float32).to(dev).eval()

report = {"garment": G, "views": {}}
tiles = []
def keep_seeded(mask, seeds):
    """Only the connected parts of mask that hold a positive seed (drawing px)."""
    from scipy import ndimage
    lab, n = ndimage.label(mask)
    keep = {lab[int(v), int(u)] for u, v in seeds if 0 <= int(v) < mask.shape[0] and 0 <= int(u) < mask.shape[1]}
    keep.discard(0)
    return np.isin(lab, list(keep)) if keep else np.zeros_like(mask)


for view in ("front", "left", "rear"):
    ARMS.clear()
    ARM_DBG.clear()
    ref = np.asarray(Image.open(src_of(G, view)).convert("RGB"))
    rm = matte(ref)
    man, mm = mannequin(view)
    all_rows = np.ones(H0, bool)
    # scale from the bare glove figure of the same sheet / view (the fix-sheet rears have their own scale)
    sref = src_of("glove", view) if not (view == "rear" and G in REAR_FIX) else src_of(G, view)
    gm = matte(np.asarray(Image.open(sref).convert("RGB")))
    s0, tx0, ty0 = init_of(gm, mm)
    _, s_fit, _, _ = fit(gm, mm, np.linspace(s0 * 0.94, s0 * 1.06, 13), all_rows, (s0, tx0, ty0))
    trust = np.zeros(H0, bool)
    for lo, hi in TRUST[G]:
        r0, r1 = int(max(0, z_to_row(hi))), int(min(H0, z_to_row(lo)))
        trust[r0:r1] = True
    s_i, tx_i, ty_i = init_of(rm, mm)
    iou, s, tx, ty = fit(rm, mm, [s_fit], trust, (s_fit, tx_i + (s_i - s_fit) * 0, ty_i))
    if view in ("front", "rear"):                        # turn each drawn arm onto ours
        # arm angle from the bare glove figure (registered with its own fit): its hand tips are unambiguous
        gi, gs_, gtx, gty = fit(gm, mm, [s_fit], np.ones(H0, bool), init_of(gm, mm))
        fw = warp(gm, gs_, gtx, gty, mm.shape)
        cx = W0 / 2
        yy, xx = np.where(fw)
        for sd_name in ("Left", "Right"):
            P = to_px(J[f"{sd_name}Arm"], view)[0]
            tip = to_px(T[f"{sd_name}Hand"], view)[0]
            sd = 1 if tip[0] > cx else -1
            # the hand: the arm hangs clear of the body, so on rows where this side has two separate silhouette
            # runs the outer one is the arm; the lowest such row (elbow -> hips) is the hand tip
            dtip = None
            for r in range(int(z_to_row(1.0)), int(z_to_row(0.5))):
                row = fw[r]
                xs_ = np.where(row)[0]
                xs_ = xs_[sd * (xs_ - cx) > 0]
                if len(xs_) == 0:
                    continue
                xs_ = np.sort(xs_) if sd > 0 else np.sort(xs_)[::-1]
                gaps = np.where(np.abs(np.diff(xs_)) > 3)[0]
                if len(gaps):
                    outer = xs_[gaps[-1] + 1:]
                    dtip = np.array([outer.mean(), r])
            if dtip is None:
                continue
            ang = np.arctan2(tip[1] - P[1], tip[0] - P[0]) - np.arctan2(dtip[1] - P[1], dtip[0] - P[0])
            ARMS.append((P[0], P[1], float(ang), tip[0], tip[1]))
            ARM_DBG.append({"side": sd_name, "pivot": [round(float(v), 1) for v in P], "our_tip": [round(float(v), 1) for v in tip],
                            "drawn_tip": [int(v) for v in dtip], "glove_fit_iou": round(float(gi), 3)})
    # prompts: OUR landmarks -> view px -> drawing px (snapped onto the figure)
    pos, neg = prompts_for(G, view)
    up = 2.5
    pts, lbl, names = [], [], []
    fy, fx = np.where(rm)
    for nlist, lab in ((pos, 1), (neg, 0)):
        for n in nlist:
            x, y = to_px(LM[n][0](J, T), view)[0]
            uu, vv = src_xy(np.array([x]), np.array([y]), s, tx, ty)
            u, v = float(uu[0]), float(vv[0])
            if not (0 <= u < rm.shape[1] and 0 <= v < rm.shape[0]):
                continue
            if not rm[int(v), int(u)]:
                d = np.hypot(fx - u, fy - v)
                if d.min() > 20:
                    continue
                u, v = fx[d.argmin()], fy[d.argmin()]
            pts.append([u * up, v * up])
            lbl.append(lab)
            names.append(n)
    big = Image.fromarray(ref).resize((int(ref.shape[1] * up), int(ref.shape[0] * up)), Image.LANCZOS)
    if sum(lbl) == 0:
        mask = np.zeros_like(rm)
        score = 0.0
    else:
        inputs = proc(images=big, input_points=[[pts]], input_labels=[[lbl]], return_tensors="pt").to(dev)
        with torch.no_grad():
            out = model(**inputs, multimask_output=False)
        lg = proc.post_process_masks(out.pred_masks.cpu(), inputs["original_sizes"].cpu(), binarize=False)[0][0, 0]
        mbig = lg.numpy() > 0
        mask = np.asarray(Image.fromarray(mbig).resize((ref.shape[1], ref.shape[0]), Image.NEAREST)) & rm
        mask = keep_seeded(mask, [(px / up, py / up) for (px, py), lb in zip(pts, lbl) if lb])
        score = float(out.iou_scores.cpu().numpy().ravel()[0])
    # composite onto the mannequin
    wm = warp(mask, s, tx, ty, mm.shape)
    ys, xs = np.where(wm)
    uf, vf = src_xy(xs, ys, s, tx, ty)
    u = np.clip(np.round(uf).astype(int), 0, ref.shape[1] - 1)
    v = np.clip(np.round(vf).astype(int), 0, ref.shape[0] - 1)
    comp = man.copy().astype(np.uint8)
    comp[ys, xs] = ref[v, u]
    Image.fromarray(comp).save(OUT / f"{view}.png")
    if view == "left":
        Image.fromarray(comp[:, ::-1]).save(OUT / "right.png")
    report["views"][view] = {"src": str(src_of(G, view).relative_to(ROOT)), "scale": round(float(s), 4),
                             "tx": round(float(tx), 1), "ty": round(float(ty), 1), "trust_iou": round(float(iou), 3),
                             "prompts": dict(zip(names, lbl)), "sam_iou_pred": round(score, 3),
                             "arm_turn_deg": [round(float(np.degrees(a_)), 1) for _, _, a_, _, _ in ARMS],
                             "arm_debug": list(ARM_DBG),
                             "mask_px": int(mask.sum())}
    # tile: drawing + mask tint + prompts | composite
    t = ref.astype(float).copy()
    t[mask] = t[mask] * 0.45 + np.array([255, 60, 0]) * 0.55
    ti = Image.fromarray(t.astype(np.uint8)).resize((int(ref.shape[1] * 2), int(ref.shape[0] * 2)), Image.NEAREST)
    dr = ImageDraw.Draw(ti)
    for (px, py), lb in zip(pts, lbl):
        px, py = px / up * 2, py / up * 2
        dr.ellipse([px - 5, py - 5, px + 5, py + 5], fill=(0, 200, 0) if lb else (220, 0, 0), outline="white")
    ci = Image.fromarray(comp).resize((int(W0 * ti.height / H0), ti.height))
    tiles += [ti, ci]
    print("VIEW", view, json.dumps(report["views"][view]), flush=True)

shutil.copy(KEYD / "cameras.json", OUT / "cameras.json")
subprocess.run([sys.executable, str(ROOT / "scripts" / "key_pairs.py"), str(OUT)], check=True)
(OUT / "ref_dress.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
h = max(t.height for t in tiles)
sheet = Image.new("RGB", (sum(t.width for t in tiles) + 8 * len(tiles), h), "white")
x = 0
for t in tiles:
    sheet.paste(t, (x, 0))
    x += t.width + 8
sheet.save(ROOT / "renders" / f"refdress_{G}.png")
print("SHEET", ROOT / "renders" / f"refdress_{G}.png")
