"""Clean a baked garment base-colour texture (called by build_shell.py; scripts venv: numpy, scipy, PIL).

  python -I scripts/tex_clean.py raw.png out.png --uv-tris tris.npy [--key 0,0,0] [--opts '{...}']

raw.png: the Cycles bake; texels the bake missed (holes where fragments went to other pieces, filler
geometry) come out --key (pure black). tris.npy: the shell's UV triangles (N, 3, 2) -> which texels are on the mesh.
1. misses: texels on the mesh that hold the key colour.
2. foreign colour (opts "own" / "foreign": median Lab of this piece's garments / of the garments whose
   colour leaks in, filled by build_shell.py from <char>_faces.npz; "wL": weight of lightness in the
   distance, "margin"): texels nearer a foreign colour than an own one are repainted, except compact round
   blobs of "keep_round" [min, max] px (buttons).
3. repaint: thin gaps from the nearest good texel of the same UV island; wider areas (rebuilt / filled
   geometry) from a fabric swatch (the largest clean square of the garment, mean removed, tiled) over the
   island's median colour; seams softened; everything off the mesh is padded from the nearest texel.
Prints one JSON line with texel shares.
"""
import argparse
import json

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ap = argparse.ArgumentParser()
ap.add_argument("raw")
ap.add_argument("out")
ap.add_argument("--uv-tris", required=True)
ap.add_argument("--key", default="0,0,0")
ap.add_argument("--opts", default="{}")
a = ap.parse_args()
opts = json.loads(a.opts)
key = np.array([int(x) for x in a.key.split(",")])

img = np.array(Image.open(a.raw).convert("RGB")).astype(np.float64)
H, W, _ = img.shape
tris = np.load(a.uv_tris)
cov_img = Image.new("L", (W, H), 0)
dr = ImageDraw.Draw(cov_img)
for t in tris:
    dr.polygon([(u * W, (1 - v) * H) for u, v in t], fill=255)
cov = np.array(cov_img) > 0

miss = cov & (np.abs(img - key).max(2) < 2)
good = cov & ~miss


def lab(rgb):
    c = rgb / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


L = lab(img)
ref = np.median(L[good], 0) if good.any() else np.zeros(3)
outl = np.zeros_like(good)
if opts.get("foreign") and good.any():
    wl = np.array([opts.get("wL", 0.5), 1.0, 1.0])

    def dist(cols):
        return np.min([np.linalg.norm((L - np.array(c)) * wl, axis=2) for c in cols], 0)

    far = good & (dist(opts["foreign"]) + opts.get("margin", 3.0) < dist(opts["own"]))
    far = ndimage.binary_opening(far, iterations=1)
    lab_, n = ndimage.label(far)
    if n:
        sl = ndimage.find_objects(lab_)
        size = ndimage.sum(far, lab_, range(1, n + 1))
        k0, k1 = opts.get("keep_round", [0, 0])
        keep = []
        for j, s in enumerate(sl):
            h_, w_ = s[0].stop - s[0].start, s[1].stop - s[1].start
            round_ = size[j] / max(h_ * w_, 1) > 0.6 and max(h_, w_) / max(min(h_, w_), 1) < 1.6
            if k0 <= size[j] <= k1 and round_:
                keep.append(j + 1)
        outl = far & ~np.isin(lab_, keep)
        outl = ndimage.binary_dilation(outl, iterations=2) & good
good2 = good & ~outl
fix = cov & ~good2

out = img.copy()
# fabric swatch: the largest clean square of the garment (distance transform peak), tiled over the texture
dgood = ndimage.distance_transform_edt(good2)
cy, cx = np.unravel_index(np.argmax(dgood), dgood.shape)
half = int(max(4, min(dgood[cy, cx] * 0.7, 96)))
sw = img[cy - half:cy + half, cx - half:cx + half]
sw = sw - sw.reshape(-1, 3).mean(0)                       # texture only; the colour comes from the island
reps = (H // sw.shape[0] + 2, W // sw.shape[1] + 2, 1)
tile = np.tile(np.concatenate([sw, sw[:, ::-1]], 1), (reps[0], reps[1] // 2 + 1, 1))[:H, :W]
isl, n_isl = ndimage.label(ndimage.binary_dilation(cov, iterations=1))
med_rgb = np.median(img[good2], 0) if good2.any() else np.full(3, 128.0)
dist_fix, idx_all = ndimage.distance_transform_edt(~good2, return_indices=True)
for i in range(1, n_isl + 1):
    m = isl == i
    f = fix & m
    if not f.any():
        continue
    src = good2 & m
    base = np.median(img[src], 0) if src.sum() >= 50 else med_rgb
    if src.sum() >= 20:
        _, idx = ndimage.distance_transform_edt(~src, return_indices=True)
        near = img[idx[0], idx[1]][f]
        dd = ndimage.distance_transform_edt(~src)[f]
    else:
        near, dd = np.tile(base, (int(f.sum()), 1)), np.full(int(f.sum()), 99.0)
    w = np.clip((dd - 2) / 8, 0, 1)[:, None]                 # thin gaps: nearest texel; wide areas: swatch
    out[f] = (1 - w) * near + w * (base + tile[f])
# soften the seam between kept and repainted texels
blur = np.stack([ndimage.gaussian_filter(out[..., c], 1.2) for c in range(3)], -1)
seam = fix & (dist_fix < 4)
out[seam] = blur[seam]
# bake margin: pad off-mesh texels from the nearest mesh texel
_, idx = ndimage.distance_transform_edt(~cov, return_indices=True)
out[~cov] = out[idx[0], idx[1]][~cov]
Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(a.out)
n_cov = max(int(cov.sum()), 1)
print(json.dumps({"texels_on_mesh": n_cov, "miss": round(float(miss.sum()) / n_cov, 3),
                  "outlier": round(float(outl.sum()) / n_cov, 3), "garment_lab": np.round(ref, 1).tolist(),
                  "opts": opts}))
