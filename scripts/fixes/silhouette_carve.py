"""Carve geometry that sticks out of the reference silhouettes (e.g. flared boot "wings").

For each chosen view, every vertex is projected orthographically and the model's projected
bounding box (all vertices) is mapped onto the reference matte's bounding box (prep framed
each view by its mask bbox, so this is the same normalisation). Faces in the height band
whose vertices ALL fall outside the matte (dilated by margin_px) in ANY view are deleted.
Model convention: faces -Y, Z up. Image right = +X (front), -X (back), +Y (left), -Y (right).
dry_run=True paints the faces red instead of deleting.
"""
import bmesh
import numpy as np

from .common import input_image, load_ref, read_pixels, texel_mask, write_pixels

NAME = "silhouette_carve"
STAGE = "hi"
DEFAULTS = {
    "label": "",
    "z_frac": [0.0, 0.06],
    "views": ["front", "back", "left", "right"],
    "margin_px": 4,          # matte dilation; prepped mattes are 1024 px for ~1.1x model height
    "dry_run": False,
}
# view -> (axis index for image-right, sign)
AXES = {"front": (0, 1), "back": (0, -1), "left": (1, 1), "right": (1, -1)}


def _dilate(m, n):
    for _ in range(n):
        d = m.copy()
        d[1:] |= m[:-1]
        d[:-1] |= m[1:]
        d[:, 1:] |= m[:, :-1]
        d[:, :-1] |= m[:, 1:]
        m = d
    return m


def apply(ctx, label, z_frac, views, margin_px, dry_run):
    me = ctx.ob.data
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    outside_any = np.zeros(len(co), bool)
    per_view = {}
    for view in views:
        ref = load_ref(ctx.ref_dir / f"{view}_white.png")[..., :3]
        mask = ref.min(-1) < 0.92                      # matte on white; boots are dark
        rows, cols = np.where(mask.any(1))[0], np.where(mask.any(0))[0]
        r0, r1, c0, c1 = rows[0], rows[-1], cols[0], cols[-1]
        mask = _dilate(mask, margin_px)
        axis, sign = AXES[view]
        u = co[:, axis] * sign
        z = co[:, 2]
        # model bbox -> mask bbox (image rows grow downward)
        col = c0 + (u - u.min()) / (u.max() - u.min()) * (c1 - c0)
        row = r1 - (z - z.min()) / (z.max() - z.min()) * (r1 - r0)
        ci = np.clip(np.round(col).astype(int), 0, mask.shape[1] - 1)
        ri = np.clip(np.round(row).astype(int), 0, mask.shape[0] - 1)
        out = ~mask[ri, ci]
        per_view[view] = int(out.sum())
        outside_any |= out
    zf = co[:, 2] / ctx.height
    cand = outside_any & (zf >= z_frac[0]) & (zf <= z_frac[1])

    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    kill = [f for f in bm.faces if all(cand[v.index] for v in f.verts)]
    area_cm2 = sum(f.calc_area() for f in kill) * 1e4
    stats = {"label": label, "verts_outside_per_view": per_view, "candidate_verts": int(cand.sum()),
             "faces_removed": len(kill), "area_cm2": round(area_cm2, 1), "dry_run": dry_run}
    if dry_run:
        fi = np.zeros(len(me.polygons), bool)
        fi[[f.index for f in kill]] = True
        bm.free()
        img = input_image(ctx.ob, "Base Color")
        px = read_pixels(img)
        me.calc_loop_triangles()
        tri_poly = np.empty(len(me.loop_triangles), np.int32)
        me.loop_triangles.foreach_get("polygon_index", tri_poly)
        sel = fi[tri_poly]
        m = texel_mask(ctx.ob, px.shape[1], px.shape[0], lambda c: sel)
        px[m, :3] = (1.0, 0.0, 0.0)
        write_pixels(img, px)
        return stats
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(me)
    bm.free()
    me.update()
    return stats
