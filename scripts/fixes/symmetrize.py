"""Make the hi-poly mirror-symmetric across the character's centre plane (PLAN P1.4).

1. Find the mirror plane: search a small yaw (about Z) and X offset that minimises the
   distance between the surface and its own mirror image (sampled points, KD-tree).
2. Report the left/right deviation before the fix (mm, p50/p95/max) per height band.
3. Rotate/shift the mesh so that plane is X=0, then copy one half onto the other with
   Blender's Symmetrize (UVs are copied, so the texture mirrors too).

keep: "+X" or "-X" = which half survives (character faces -Y: +X is its LEFT side).
"""
import bpy
import numpy as np
from mathutils import Matrix
from mathutils.kdtree import KDTree

NAME = "symmetrize"
STAGE = "hi"
DEFAULTS = {
    "keep": "+X",
    "yaw_range_deg": 4.0,
    "offset_range_m": 0.02,
    "samples": 20000,
    "threshold_m": 0.0005,     # weld distance at the seam
    "measure_only": False,
}


def _mirror_error(pts, kd, yaw, off):
    c, s = np.cos(yaw), np.sin(yaw)
    x = c * pts[:, 0] - s * pts[:, 1] + off           # into the candidate plane frame
    y = s * pts[:, 0] + c * pts[:, 1]
    mx = -x - off                                      # mirror, back to object frame
    bx = c * mx + s * y
    by = -s * mx + c * y
    q = np.stack([bx, by, pts[:, 2]], 1)
    return np.array([kd.find(p)[2] for p in q])


def apply(ctx, keep, yaw_range_deg, offset_range_m, samples, threshold_m, measure_only):
    ob, me = ctx.ob, ctx.ob.data
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    kd = KDTree(len(co))
    for i, p in enumerate(co):
        kd.insert(p, i)
    kd.balance()
    rng = np.random.default_rng(0)
    pts = co[rng.choice(len(co), min(samples, len(co)), replace=False)]

    best = (np.inf, 0.0, 0.0)
    for step in (1.0, 0.25):                            # coarse, then fine around the best
        yaws = np.radians(np.arange(-yaw_range_deg, yaw_range_deg + 1e-9, step)) if step == 1.0 else \
            best[1] + np.radians(np.arange(-1, 1.01, step))
        offs = np.linspace(-offset_range_m, offset_range_m, 9) if step == 1.0 else \
            best[2] + np.linspace(-offset_range_m / 4, offset_range_m / 4, 9)
        sub = pts[:4000]
        for yw in yaws:
            for of in offs:
                e = float(np.mean(_mirror_error(sub, kd, yw, of)))
                if e < best[0]:
                    best = (e, float(yw), float(of))
    _, yaw, off = best
    err = _mirror_error(pts, kd, yaw, off) * 1000
    zf = pts[:, 2] / ctx.height
    bands = {}
    for lo, hi, name in ((0, 0.12, "feet"), (0.12, 0.45, "legs_hips"), (0.45, 0.75, "torso_arms"),
                         (0.75, 1.01, "neck_head")):
        m = (zf >= lo) & (zf < hi)
        if m.any():
            bands[name] = [round(float(np.percentile(err[m], q)), 1) for q in (50, 95)] + [round(float(err[m].max()), 1)]
    stats = {"plane_yaw_deg": round(float(np.degrees(yaw)), 2), "plane_offset_mm": round(off * 1000, 1),
             "deviation_mm_p50_p95_max": [round(float(np.percentile(err, 50)), 1),
                                          round(float(np.percentile(err, 95)), 1), round(float(err.max()), 1)],
             "by_band_p50_p95_max": bands, "kept": keep, "measure_only": measure_only}
    if measure_only:
        return stats

    # align the plane to X=0 (rotate about Z through the origin, then shift)
    ob.data.transform(Matrix.Translation((off, 0, 0)) @ Matrix.Rotation(yaw, 4, "Z"))
    me.update()
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.symmetrize(direction="POSITIVE_X" if keep == "+X" else "NEGATIVE_X", threshold=threshold_m)
    bpy.ops.object.mode_set(mode="OBJECT")
    stats["verts_after"] = len(me.vertices)
    return stats
