"""Dress the blue mannequin with a garment cut from Pete's reference DRAWINGS, through the part-to-part warp.

  .venv python -I scripts/ref_dress.py --garment jacket [--model facebook/sam2.1-hiera-large]

Per view (front / left from sheet_front_side, rear from sheet_rear_right_v2 -- bow tie + breeches: the squeezed
fix-sheet rears; right = the left result mirrored):
1. body model (part_warp.body_model): the sheet's bare glove figure, warped part by part onto OUR mannequin view
   (MLS from body control points: arms tracked, legs, torso edges, head);
2. the garment's figure is lined up with that glove figure on the rows the garment never reaches (TRUST): same sheet
   = same scale, a shift only; the fix-sheet rears also get a scale;
3. view px -> glove figure px (part warp) -> garment figure px;
4. SAM 2.1 on the garment drawing (x2.5): prompts = OUR landmarks (garment_prompts.prompts_for) pushed through that
   same map, snapped onto the figure; the mask keeps the parts holding a positive point;
5. composite: the mannequin view with the drawing's garment pixels -> out/<set>/dressed/<g>/<view>.png (+ cameras.json,
   pairs via key_pairs.py) for key_measure.py; renders/refdress_<g>.png: drawing + mask + prompts | composite, per view.
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
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))
import goose2d as g2  # noqa: E402
import part_warp as pw  # noqa: E402
from garment_prompts import LM, TRUST, prompts_for  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--garment", required=True)
ap.add_argument("--model", default="facebook/sam2.1-hiera-large")
a = ap.parse_args()
G = a.garment
OUT = g2.ROOT / "out" / "outfit_male_victorian" / "dressed" / G
OUT.mkdir(parents=True, exist_ok=True)
REAR_FIX = {"bow_tie", "breeches"}


def src_of(g, view):
    if view == "rear":
        return g2.WORN / g / ("rear_raw.png" if g in REAR_FIX else "rear_v2_raw.png")
    return g2.WORN / g / f"{view}_raw.png"


def keep_seeded(mask, seeds):
    lab, n = ndimage.label(mask)
    keep = {lab[int(v), int(u)] for u, v in seeds if 0 <= int(v) < mask.shape[0] and 0 <= int(u) < mask.shape[1]}
    keep.discard(0)
    return np.isin(lab, list(keep)) if keep else np.zeros_like(mask)


from transformers import Sam2Model, Sam2Processor  # noqa: E402
dev = "cuda" if torch.cuda.is_available() else "cpu"
proc = Sam2Processor.from_pretrained(a.model)
model = Sam2Model.from_pretrained(a.model, torch_dtype=torch.float32).to(dev).eval()

report = {"garment": G, "views": {}}
tiles = []
for view in ("front", "left", "rear"):
    bm = pw.body_model(view)
    s0, tx0, ty0 = bm["cp"]["sim"]
    ref = np.asarray(Image.open(src_of(G, view)).convert("RGB"))
    rm = g2.matte(ref)
    gm = bm["matte"]
    # garment figure -> glove figure: rows the garment never reaches, in glove-figure rows
    trust = np.zeros(gm.shape[0], bool)
    for lo, hi in TRUST[G]:
        r0 = int(max(0, (g2.z_to_row(hi) - ty0) / s0))
        r1 = int(min(gm.shape[0], (g2.z_to_row(lo) - ty0) / s0))
        trust[r0:r1] = True
    fix = view == "rear" and G in REAR_FIX
    ys, xs = np.where(rm)
    yg, xg = np.where(gm)
    init = (1.0, xg.mean() - xs.mean(), yg.max() - ys.max())
    if fix:
        si = (yg.max() - yg.min()) / (ys.max() - ys.min())
        init = (si, xg.mean() - si * xs.mean(), yg.max() - si * ys.max())
    s_range = np.linspace(init[0] * 0.88, init[0] * 1.12, 13) if fix else [1.0]
    giou, sg, txg, tyg = g2.fit_sim(rm, gm, trust, s_range=s_range, init=init)
    gu = (bm["u"] - txg) / sg                       # view px -> garment figure px
    gv = (bm["v"] - tyg) / sg

    def view_to_garment(xy):
        x, y = int(round(xy[0])), int(round(xy[1]))
        x, y = min(max(x, 0), g2.W0 - 1), min(max(y, 0), g2.H0 - 1)
        return gu[y, x], gv[y, x]

    pos, neg = prompts_for(G, view)
    up = 2.5
    pts, lbl, names = [], [], []
    fy, fx = np.where(rm)
    for nlist, lab_ in ((pos, 1), (neg, 0)):
        for n in nlist:
            u, v = view_to_garment(g2.to_px(LM[n][0](g2.J, g2.T), view)[0])
            if not (0 <= int(v) < rm.shape[0] and 0 <= int(u) < rm.shape[1] and rm[int(v), int(u)]):
                d = np.hypot(fx - u, fy - v)
                if d.min() > 15:
                    continue
                u, v = fx[d.argmin()], fy[d.argmin()]
            pts.append([float(u) * up, float(v) * up])
            lbl.append(lab_)
            names.append(n)
    big = Image.fromarray(ref).resize((int(ref.shape[1] * up), int(ref.shape[0] * up)), Image.LANCZOS)
    if sum(lbl):
        inputs = proc(images=big, input_points=[[pts]], input_labels=[[lbl]], return_tensors="pt").to(dev)
        with torch.no_grad():
            out = model(**inputs, multimask_output=False)
        lg = proc.post_process_masks(out.pred_masks.cpu(), inputs["original_sizes"].cpu(), binarize=False)[0][0, 0]
        mask = np.asarray(Image.fromarray(lg.numpy() > 0).resize((ref.shape[1], ref.shape[0]), Image.NEAREST)) & rm
        mask = keep_seeded(mask, [(p[0] / up, p[1] / up) for p, lb in zip(pts, lbl) if lb])
        score = float(out.iou_scores.cpu().numpy().ravel()[0])
    else:
        mask, score = np.zeros_like(rm), 0.0
    man, mm = g2.mannequin(view)
    col, ok = pw.sample(ref, gu, gv)
    msk, _ = pw.sample(mask.astype(np.uint8), gu, gv)
    on = msk.astype(bool) & ok
    comp = man.astype(np.uint8).copy()
    comp[on] = col[on]
    Image.fromarray(comp).save(OUT / f"{view}.png")
    if view == "left":
        Image.fromarray(comp[:, ::-1]).save(OUT / "right.png")
    report["views"][view] = {"src": str(src_of(G, view).relative_to(g2.ROOT)), "to_body_model": [round(float(sg), 4),
                             round(float(txg), 1), round(float(tyg), 1)], "trust_iou": round(float(giou), 3),
                             "body_model_iou_global": round(float(bm["cp"]["iou"]), 3),
                             "prompts": dict(zip(names, lbl)), "sam_iou_pred": round(score, 3),
                             "mask_px": int(mask.sum()), "on_mannequin_px": int(on.sum())}
    t = ref.astype(float).copy()
    t[mask] = t[mask] * 0.45 + np.array([255, 60, 0]) * 0.55
    ti = Image.fromarray(t.astype(np.uint8)).resize((ref.shape[1] * 2, ref.shape[0] * 2), Image.NEAREST)
    dr = ImageDraw.Draw(ti)
    for (px, py), lb in zip(pts, lbl):
        px, py = px / up * 2, py / up * 2
        dr.ellipse([px - 5, py - 5, px + 5, py + 5], fill=(0, 200, 0) if lb else (220, 0, 0), outline="white")
    ci = Image.fromarray(comp).resize((int(g2.W0 * ti.height / g2.H0), ti.height))
    tiles += [ti, ci]
    print("VIEW", view, json.dumps({k: v for k, v in report["views"][view].items() if k != "prompts"}), flush=True)

shutil.copy(g2.KEYD / "cameras.json", OUT / "cameras.json")
subprocess.run([sys.executable, str(g2.ROOT / "scripts" / "key_pairs.py"), str(OUT)], check=True)
(OUT / "ref_dress.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
h = max(t.height for t in tiles)
sheet = Image.new("RGB", (sum(t.width for t in tiles) + 8 * len(tiles), h), "white")
x = 0
for t in tiles:
    sheet.paste(t, (x, 0))
    x += t.width + 8
sheet.save(g2.ROOT / "renders" / f"refdress_{G}.png")
print("SHEET", g2.ROOT / "renders" / f"refdress_{G}.png")
