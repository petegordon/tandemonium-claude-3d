"""Clean a baked garment base-colour texture (called by build_shell.py; scripts venv: numpy, scipy, PIL).

  python -I scripts/tex_clean.py raw.png out.png --uv-tris tris.npy [--key 0,0,0] [--opts '{...}']

raw.png: the Cycles bake; texels the bake missed (holes where fragments went to other pieces, filler
geometry) come out --key (pure black). tris.npy: the shell's UV triangles (N, 3, 2) -> which texels are on the mesh.
1. misses: texels on the mesh that hold the key colour.
2. foreign colour (opts "own" / "foreign": median Lab of this piece's garments / of the garments whose
   colour leaks in, filled by build_shell.py from <char>_faces.npz; "wL": weight of lightness in the
   distance, "margin"): texels nearer a foreign colour than an own one are repainted, except compact round
   blobs of "keep_round" [min, max] px (buttons).
3. repaint: inside a UV island, from the nearest good texel of the same island, blurred over the
   repainted area; islands with no good texel take the garment colour plus noise of the garment's own
   spread; everything off the mesh is padded from the nearest texel (bake margin).
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
isl, n_isl = ndimage.label(ndimage.binary_dilation(cov, iterations=1))
spread = img[good2].std(0) if good2.any() else np.zeros(3)
med_rgb = np.median(img[good2], 0) if good2.any() else np.full(3, 128.0)
rng = np.random.default_rng(0)
noise = ndimage.gaussian_filter(rng.standard_normal((H, W)), 1.2)
noise /= max(noise.std(), 1e-9)
for i in range(1, n_isl + 1):
    m = isl == i
    f = fix & m
    if not f.any():
        continue
    src = good2 & m
    if src.sum() >= 20:
        _, idx = ndimage.distance_transform_edt(~src, return_indices=True)
        filled = img[idx[0], idx[1]]
        out[f] = filled[f]
    else:
        out[f] = med_rgb + noise[f][:, None] * spread * 0.6
# soften the repainted texels (nearest-fill streaks), keep good texels
blur = np.stack([ndimage.gaussian_filter(out[..., c], 2.0) for c in range(3)], -1)
wt = ndimage.gaussian_filter(good2.astype(float), 2.0)
sm = np.stack([ndimage.gaussian_filter(out[..., c] * good2, 2.0) for c in range(3)], -1) / np.maximum(wt, 1e-6)[..., None]
out[fix] = np.where(wt[fix][:, None] > 0.05, 0.5 * sm[fix] + 0.5 * blur[fix], blur[fix])
# bake margin: pad off-mesh texels from the nearest mesh texel
_, idx = ndimage.distance_transform_edt(~cov, return_indices=True)
out[~cov] = out[idx[0], idx[1]][~cov]
Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(a.out)
n_cov = max(int(cov.sum()), 1)
print(json.dumps({"texels_on_mesh": n_cov, "miss": round(float(miss.sum()) / n_cov, 3),
                  "outlier": round(float(outl.sum()) / n_cov, 3), "garment_lab": np.round(ref, 1).tolist(),
                  "opts": opts}))
