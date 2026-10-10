"""Delete faces inside an explicit box (metres, model space: faces -Y, Z up), optionally
only where the base colour matches an HSV window. Escape hatch for one-off generator
debris that automatic filters (trim_fins, silhouette_carve) can't isolate.
Use dry_run=True first: it paints the selection red for a review render.
"""
import bmesh
import numpy as np

from .common import face_centroids, input_image, read_pixels, rgb_to_hsv, texel_mask, write_pixels

NAME = "region_delete"
STAGE = "hi"
DEFAULTS = {
    "label": "",
    "x": [-10.0, 10.0], "y": [-10.0, 10.0], "z": [-10.0, 10.0],   # metres
    "hue_deg": [0, 360], "sat": [0.0, 1.0], "val": [0.0, 1.0],     # base colour window
    "dry_run": False,
}


def apply(ctx, label, x, y, z, hue_deg, sat, val, dry_run):
    me = ctx.ob.data
    cent, tri_loops = face_centroids(ctx.ob)
    img = input_image(ctx.ob, "Base Color")
    px = read_pixels(img)
    h, w = px.shape[:2]
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)[tri_loops].mean(1)
    rgb = px[np.clip((uv[:, 1] * h).astype(int), 0, h - 1), np.clip((uv[:, 0] * w).astype(int), 0, w - 1), :3]
    hsv = rgb_to_hsv(rgb)
    hue = hsv[:, 0] * 360
    sel = ((cent[:, 0] >= x[0]) & (cent[:, 0] <= x[1]) & (cent[:, 1] >= y[0]) & (cent[:, 1] <= y[1])
           & (cent[:, 2] >= z[0]) & (cent[:, 2] <= z[1]) & (hue >= hue_deg[0]) & (hue <= hue_deg[1])
           & (hsv[:, 1] >= sat[0]) & (hsv[:, 1] <= sat[1]) & (hsv[:, 2] >= val[0]) & (hsv[:, 2] <= val[1]))
    tri_poly = np.empty(len(me.loop_triangles), np.int32)
    me.loop_triangles.foreach_get("polygon_index", tri_poly)
    polys = np.unique(tri_poly[sel])
    stats = {"label": label, "faces": int(len(polys)), "dry_run": dry_run,
             "bbox_min": np.round(cent[sel].min(0), 3).tolist() if sel.any() else None,
             "bbox_max": np.round(cent[sel].max(0), 3).tolist() if sel.any() else None}
    if dry_run:
        m = texel_mask(ctx.ob, w, h, lambda c: sel)
        px[m, :3] = (1.0, 0.0, 0.0)
        write_pixels(img, px)
        return stats
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in polys], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(me)
    bm.free()
    me.update()
    return stats
