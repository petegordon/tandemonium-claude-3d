"""P3.3 ref masks, step 2 (ComfyUI venv python, GPU): SAM 2 garment masks on the clean reference views,
seeded from the rule labels, turned into per-face votes.

  /c/Users/pete/ComfyUI-claude/.venv/Scripts/python.exe -I scripts/sam_masks.py --char outfit_male

Inputs: out/<char>-goose/<char>_refproj.npz (ref_project.py), <char>_garments.npz (extract_garments.py
rule labels), refs/<char>/prepped/<view>_white.png. Per view:
  1. splat the visible faces' rule labels into a label image (most frontal face wins), fill gaps
     inside the matte from the nearest label;
  2. per garment: up to N_POS interior seed points (farthest-point sampling where the distance to the
     garment's edge >= MIN_DEPTH px) + N_NEG negatives from neighbouring garments;
  3. one SAM 2.1 call per view with every garment as its own object; each pixel of the matte takes the
     object with the highest mask logit (> 0);
  4. faces visible in the view vote for the SAM label at their pixel, weighted by facing.
Writes <char>_refvotes.npz (votes[face, garment], names) and renders/<char>_sam_<view>.png
(reference | rule-label splat + seeds | SAM labels).
"""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw
from scipy import ndimage

ap = argparse.ArgumentParser()
ap.add_argument("--char", required=True)
ap.add_argument("--model", default="facebook/sam2.1-hiera-large")
args = ap.parse_args()
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{args.char}-goose"
REF = ROOT / "refs" / args.char / "prepped"
VIEWS = ["front", "left", "back", "right"]
N_POS, N_NEG, MIN_DEPTH = 6, 6, 6
PALETTE = np.array([[.55, .55, .55], [.9, .15, .15], [.15, .55, .95], [.95, .75, .1], [.2, .8, .3],
                    [.7, .25, .85], [.95, .45, .1], [.1, .85, .8], [.95, .45, .7], [.55, .35, .15],
                    [.25, .25, .9], [.7, .9, .2], [.1, .1, .1], [1, 1, 1]])

P = np.load(D / f"{args.char}_refproj.npz")
G = np.load(D / f"{args.char}_garments.npz")
label, names = G["label"], [str(n) for n in G["names"]]
nl, nf = len(names), len(label)
OTHER = names.index("other")

from transformers import Sam2Model, Sam2Processor  # noqa: E402
dev = "cuda" if torch.cuda.is_available() else "cpu"
proc = Sam2Processor.from_pretrained(args.model)
model = Sam2Model.from_pretrained(args.model, torch_dtype=torch.float32).to(dev).eval()


def fps(pts, k, rng):
    """Farthest-point sampling of up to k points (row, col)."""
    if len(pts) <= k:
        return pts
    sel = [pts[rng.integers(len(pts))]]
    d = np.linalg.norm(pts - sel[0], axis=1)
    for _ in range(k - 1):
        sel.append(pts[d.argmax()])
        d = np.minimum(d, np.linalg.norm(pts - sel[-1], axis=1))
    return np.array(sel)


votes = np.zeros((nf, nl), np.float32)
report = {}
rng = np.random.default_rng(0)
for view in VIEWS:
    img = Image.open(REF / f"{view}_white.png").convert("RGB")
    H, W = img.height, img.width
    blk = np.asarray(Image.open(REF / f"{view}_black.png").convert("RGB"), np.float32) / 255
    matte = blk.max(-1) > 0.02
    row, col = P[f"{view}_row"], P[f"{view}_col"]
    vis, facing = P[f"{view}_vis"], P[f"{view}_facing"]
    idx = np.flatnonzero(vis & (label != OTHER))
    idx = idx[np.argsort(facing[idx])]                       # most frontal written last
    r = np.clip(row[idx].round().astype(int), 0, H - 1)
    c = np.clip(col[idx].round().astype(int), 0, W - 1)
    lab_img = np.full((H, W), -1, int)
    lab_img[r, c] = label[idx]
    known = lab_img >= 0
    _, (ir, ic) = ndimage.distance_transform_edt(~known, return_indices=True)
    lab_img = np.where(matte, lab_img[ir, ic], -1)

    objs, pts_all, lbl_all = [], [], []
    for g in range(nl):
        if g == OTHER:
            continue
        m = lab_img == g
        if m.sum() < 50:
            continue
        depth = ndimage.distance_transform_edt(m)
        cand = np.argwhere(depth >= MIN_DEPTH)
        if len(cand) == 0:
            continue
        pos = fps(cand.astype(float), N_POS, rng)
        # negatives: interior points of other garments within the garment's grown bbox
        r0, c0 = np.argwhere(m).min(0) - 30
        r1, c1 = np.argwhere(m).max(0) + 30
        win = np.zeros_like(m)
        win[max(0, r0):r1, max(0, c0):c1] = True
        other = (lab_img >= 0) & ~m & win
        od = ndimage.distance_transform_edt(other)
        ocand = np.argwhere(od >= MIN_DEPTH)
        neg = fps(ocand.astype(float), N_NEG, rng) if len(ocand) else np.zeros((0, 2))
        pts = np.concatenate([pos, neg])[:, ::-1]             # SAM wants (x, y)
        objs.append(g)
        pts_all.append(pts.tolist())
        lbl_all.append([1] * len(pos) + [0] * len(neg))
    # pad to a common point count per object (label -10 = padding)
    k = max(len(p) for p in pts_all)
    for p, lb in zip(pts_all, lbl_all):
        while len(p) < k:
            p.append([0.0, 0.0])
            lb.append(-10)
    inputs = proc(images=img, input_points=[pts_all], input_labels=[lbl_all], return_tensors="pt").to(dev)
    with torch.no_grad():
        out = model(**inputs, multimask_output=False)
    logits = proc.post_process_masks(out.pred_masks.cpu(), inputs["original_sizes"].cpu(), binarize=False)[0]
    logits = logits[:, 0].numpy()                             # (objects, H, W)
    best = logits.argmax(0)
    sam = np.where(matte & (logits.max(0) > 0), np.array(objs)[best], -1)
    scores = out.iou_scores.cpu().numpy().reshape(len(objs), -1)[:, 0]
    report[view] = {names[g]: {"seeds": int(sum(1 for x in lb if x == 1)), "iou_pred": round(float(s), 3),
                               "px": int((sam == g).sum())} for g, lb, s in zip(objs, lbl_all, scores)}
    # votes
    fi = np.flatnonzero(vis)
    r = np.clip(row[fi].round().astype(int), 0, H - 1)
    c = np.clip(col[fi].round().astype(int), 0, W - 1)
    s = sam[r, c]
    ok = s >= 0
    np.add.at(votes, (fi[ok], s[ok]), facing[fi[ok]])
    # preview: reference | splat + seeds | SAM labels
    def colour(li):
        o = np.ones((H, W, 3)) * 0.95
        o[li >= 0] = PALETTE[li[li >= 0] % len(PALETTE)]
        return Image.fromarray((o * 255).astype(np.uint8))
    a, b = colour(lab_img), colour(sam)
    dr = ImageDraw.Draw(a)
    for p, lb in zip(pts_all, lbl_all):
        for (x, y), l in zip(p, lb):
            if l == 1:
                dr.ellipse([x - 5, y - 5, x + 5, y + 5], fill=(0, 0, 0))
            elif l == 0:
                dr.ellipse([x - 4, y - 4, x + 4, y + 4], outline=(255, 255, 255), width=2)
    sheet = Image.new("RGB", (W * 3, H), (240, 240, 240))
    for i, im in enumerate((img, a, b)):
        sheet.paste(im, (i * W, 0))
    sheet.resize((W * 3 // 2, H // 2)).save(ROOT / "renders" / f"{args.char}_sam_{view}.png")
    print("VIEW", view, json.dumps(report[view]))
np.savez_compressed(D / f"{args.char}_refvotes.npz", votes=votes, names=np.array(names))
print("VOTED faces", int((votes.sum(1) > 0).sum()), "of", nf)
