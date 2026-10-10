"""Out-of-Blender helper for trim_fins (needs scipy; run via `uv run --with scipy`).

  python volume_helper.py <in.npz> <out.npz>

in.npz : points (N,3) surface samples, verts (M,3) region vertices, voxel, radius, lo
out.npz: dist (M,) metres from each vertex to the morphologically OPENED solid.

Solid = surface voxels (dilated 1 to close gaps), hollows filled per Z slice in 2D (the
region is cut open at its top, so a 3D fill would leak). Opening with a ball of `radius`
removes anything thinner than ~2*radius (fins) while keeping bulky parts (boot body).
"""
import sys

import numpy as np
from scipy import ndimage


def ball(r):
    k = int(np.ceil(r))
    g = np.mgrid[-k:k + 1, -k:k + 1, -k:k + 1]
    return (g ** 2).sum(0) <= r * r + 1e-6


def main(src, dst):
    d = np.load(src)
    pts, verts, vox, radius = d["points"], d["verts"], float(d["voxel"]), float(d["radius"])
    lo = pts.min(0) - 4 * vox
    hi = pts.max(0) + 4 * vox
    shape = np.ceil((hi - lo) / vox).astype(int) + 1
    surf = np.zeros(shape, bool)
    idx = np.floor((pts - lo) / vox).astype(int)
    surf[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    surf = ndimage.binary_dilation(surf, iterations=1)
    solid = surf.copy()
    for z in range(shape[2]):
        solid[:, :, z] = ndimage.binary_fill_holes(surf[:, :, z])
    opened = ndimage.binary_opening(solid, structure=ball(radius / vox))
    dist = ndimage.distance_transform_edt(~opened) * vox
    vi = np.clip(np.floor((verts - lo) / vox).astype(int), 0, shape - 1)
    out = dist[vi[:, 0], vi[:, 1], vi[:, 2]].astype(np.float32)
    np.savez(dst, dist=out, solid_voxels=int(solid.sum()), opened_voxels=int(opened.sum()),
             grid=np.array(shape))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
