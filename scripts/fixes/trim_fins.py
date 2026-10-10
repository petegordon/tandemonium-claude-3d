"""Delete thin sheet "fins" (generator debris) sticking out of bulky parts, e.g. boot toes.

Local thickness can't find them: generated surfaces are ~5 mm double-walled shells, so a
boot wall and a fin measure the same. Instead, in a height band, the region is voxelized,
hollows are filled per slice, and a morphological opening (ball of `radius`) erases
everything thinner than ~2*radius. Vertices far from the opened solid are fin candidates:
seeds at > seed_mm, grown through connected vertices > grow_mm (to take the fin's base),
and only connected patches with area >= min_area_cm2 are deleted (keeps buttons, welts).
dry_run=True paints candidates red in the base colour instead of deleting (for review).
The volume math runs out-of-Blender via `uv run --with scipy` (_volume_helper.py).
"""
import subprocess
import tempfile
from pathlib import Path

import bmesh
import numpy as np

from .common import input_image, read_pixels, texel_mask, write_pixels

NAME = "trim_fins"
STAGE = "hi"
DEFAULTS = {
    "label": "",
    "z_frac": [0.0, 0.06],   # height band, fraction of model height
    "x_max": None,
    "y_range": None,
    "voxel_mm": 1.5,
    "radius_mm": 4.0,        # opening ball radius: erases parts thinner than ~8 mm
    "seed_mm": 6.0,          # a fin must reach this far out of the opened solid
    "grow_mm": 2.0,          # ... and is grown down to here to remove its base
    "min_area_cm2": 1.5,     # patches smaller than this are kept (buttons, welt bumps)
    "dry_run": False,
}
HELPER = Path(__file__).with_name("_volume_helper.py")


def _sample_triangles(tris, spacing):
    """Uniform-ish surface samples: per triangle, a barycentric grid fine enough for spacing."""
    a, b, c = tris[:, 0], tris[:, 1], tris[:, 2]
    longest = np.maximum.reduce([np.linalg.norm(b - a, axis=1), np.linalg.norm(c - b, axis=1),
                                 np.linalg.norm(a - c, axis=1)])
    out = [a, b, c]
    for n in np.unique(np.clip(np.ceil(longest / spacing).astype(int), 1, 64)):
        sel = np.ceil(longest / spacing).clip(1, 64).astype(int) == n
        if n <= 1:
            continue
        for i in range(n + 1):
            for j in range(n + 1 - i):
                u, v = i / n, j / n
                out.append(a[sel] + u * (b[sel] - a[sel]) + v * (c[sel] - a[sel]))
    return np.concatenate(out)


def apply(ctx, label, z_frac, x_max, y_range, voxel_mm, radius_mm, seed_mm, grow_mm, min_area_cm2, dry_run):
    me = ctx.ob.data
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    z = co[:, 2] / ctx.height
    inreg = (z >= z_frac[0]) & (z <= z_frac[1])
    if x_max is not None:
        inreg &= np.abs(co[:, 0]) <= x_max
    if y_range is not None:
        inreg &= (co[:, 1] >= y_range[0]) & (co[:, 1] <= y_range[1])
    reg = np.where(inreg)[0]
    if len(reg) == 0:
        return {"label": label, "note": "empty region"}

    # Voxelize a slightly taller band so the region's edges see real context.
    me.calc_loop_triangles()
    tv = np.empty(len(me.loop_triangles) * 3, np.int32)
    me.loop_triangles.foreach_get("vertices", tv)
    tv = tv.reshape(-1, 3)
    pad = 6 * radius_mm / 1000 / ctx.height
    zt = co[tv, 2].mean(1) / ctx.height
    band = (zt >= z_frac[0] - pad) & (zt <= z_frac[1] + pad)
    pts = _sample_triangles(co[tv[band]], voxel_mm / 1000 * 0.7)

    with tempfile.TemporaryDirectory() as td:
        src, dst = Path(td) / "in.npz", Path(td) / "out.npz"
        np.savez(src, points=pts, verts=co[reg], voxel=voxel_mm / 1000, radius=radius_mm / 1000)
        subprocess.run(["uv", "run", "--no-project", "--quiet", "--with", "scipy", "--with", "numpy",
                        "python", "-I", str(HELPER), str(src), str(dst)], check=True)
        with np.load(dst) as res:  # NpzFile holds the file open; Windows can't rmtree otherwise
            dist = res["dist"]
            grid = res["grid"].tolist()
            vox_counts = [int(res["solid_voxels"]), int(res["opened_voxels"]), int(np.prod(res["grid"]))]

    far = np.zeros(len(co), bool)
    far[reg] = dist > grow_mm / 1000
    seed = np.zeros(len(co), bool)
    seed[reg] = dist > seed_mm / 1000

    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    # Grow from seeds through 'far' verts; collect connected patches.
    label_of = np.full(len(co), -1, np.int64)
    patches = []
    for s in np.where(seed)[0]:
        if label_of[s] >= 0:
            continue
        pid = len(patches)
        stack, comp = [int(s)], []
        label_of[s] = pid
        while stack:
            i = stack.pop()
            comp.append(i)
            for e in bm.verts[i].link_edges:
                j = e.other_vert(bm.verts[i]).index
                if far[j] and label_of[j] < 0:
                    label_of[j] = pid
                    stack.append(j)
        patches.append(comp)
    kill_faces, kept, removed = [], [], []
    for pid, comp in enumerate(patches):
        cs = set(comp)
        faces = {f for i in comp for f in bm.verts[i].link_faces if all(v.index in cs for v in f.verts)}
        area_cm2 = sum(f.calc_area() for f in faces) * 1e4
        info = {"verts": len(comp), "area_cm2": round(area_cm2, 2),
                "center_m": np.round(co[comp].mean(0), 3).tolist()}
        (removed if area_cm2 >= min_area_cm2 else kept).append(info)
        if area_cm2 >= min_area_cm2:
            kill_faces.extend(faces)

    stats = {"label": label, "region_verts": int(len(reg)), "grid": grid,
             "voxels_solid_opened_total": vox_counts, "sample_points": int(len(pts)),
             "dist_mm_p50_90_99_max": np.round(np.r_[np.percentile(dist, [50, 90, 99]), dist.max()] * 1000, 1).tolist(),
             "verts_over_grow": int((dist > grow_mm / 1000).sum()), "verts_over_seed": int((dist > seed_mm / 1000).sum()),
             "patches_removed": removed, "patches_kept_small": len(kept),
             "faces_removed": len(kill_faces), "dry_run": dry_run}
    if dry_run:
        # Paint the to-be-removed patches red so a render shows exactly what would go.
        fi = {f.index for f in kill_faces}
        bm.free()
        img = input_image(ctx.ob, "Base Color")
        px = read_pixels(img)
        h, w = px.shape[:2]
        me.calc_loop_triangles()
        tri_poly = np.empty(len(me.loop_triangles), np.int32)
        me.loop_triangles.foreach_get("polygon_index", tri_poly)
        sel_tri = np.isin(tri_poly, list(fi))
        mask = texel_mask(ctx.ob, w, h, lambda c: sel_tri)
        px[mask, :3] = (1.0, 0.0, 0.0)
        write_pixels(img, px)
        return stats
    bmesh.ops.delete(bm, geom=list(set(kill_faces)), context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context="VERTS")
    bm.to_mesh(me)
    bm.free()
    me.update()
    return stats
