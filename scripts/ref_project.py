"""P3.3 ref masks, step 1 (Blender): where each face of an outfit lands in each prepped reference view.

  blender -b --factory-startup --python scripts/ref_project.py -- --char outfit_male

Uses the cleaned hi mesh (<char>_goose_hi.glb: the generator's own frame, facing -Y, same face order
as the aligned mesh the labels live on). Per view (front/left/back/right, yaws as review_candidate.py):
orthographic projection u = p . right, v = z; visible = a ray from the camera side hits this face
first; image position uses review_candidate's normalisation (silhouette scaled by height, bottom-
aligned, centred on silhouette mass) applied to both the mesh and refs/<char>/prepped/<view>_black.png.
Writes out/<char>-goose/<char>_refproj.npz: per view row/col (pixels, top-left origin), visible mask,
facing weight (|cos| between face normal and view direction).
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1]
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{CHAR}-goose"
REF = ROOT / "refs" / CHAR / "prepped"
VIEWS = {"front": 0, "left": 90, "back": 180, "right": -90}
VIS_TOL = 0.004   # a hit up to 4 mm in front still counts (1 mm hid crease faces behind their own fold)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(D / f"{CHAR}_goose_hi.glb"))
ob = next(o for o in bpy.context.scene.objects if o.type == "MESH")
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = ob.data
nf = len(me.polygons)
cen = np.empty(nf * 3)
me.polygons.foreach_get("center", cen)
cen = cen.reshape(-1, 3)
nrm = np.empty(nf * 3)
me.polygons.foreach_get("normal", nrm)
nrm = nrm.reshape(-1, 3)
area = np.empty(nf)
me.polygons.foreach_get("area", area)
vco = np.array([v.co[:] for v in me.vertices])
bvh = BVHTree.FromObject(ob, bpy.context.evaluated_depsgraph_get())


def ref_mask(view):
    img = bpy.data.images.load(str(REF / f"{view}_black.png"))
    w, h = img.size
    px = np.array(img.pixels[:]).reshape(h, w, 4)[::-1]       # row 0 = top
    bpy.data.images.remove(img)
    return px[..., :3].max(-1) > 0.02


out = {}
for view, yaw_deg in VIEWS.items():
    y = math.radians(yaw_deg)
    fwd = np.array([-math.sin(y), math.cos(y), 0.0])          # camera looks along +fwd
    right = np.array([math.cos(y), math.sin(y), 0.0])
    u, v = cen @ right, cen[:, 2]
    vis = np.zeros(nf, bool)
    for i in range(nf):
        o = Vector(cen[i] - fwd * 3.0)
        hit = bvh.ray_cast(o, Vector(fwd), 3.01)
        if hit[0] is not None and (hit[2] == i or (np.array(hit[0]) - cen[i]) @ fwd > -VIS_TOL):
            vis[i] = True
    facing = np.abs(nrm @ fwd)
    # mesh silhouette: height from all verts, mass centre from visible projected area
    vu, vv = vco @ right, vco[:, 2]
    w = area * facing * vis
    ucen = float((u * w).sum() / w.sum())
    m = ref_mask(view)
    ys, xs = np.nonzero(m)
    s = (ys.max() - ys.min()) / (vv.max() - vv.min())
    cx = xs.mean()
    out[f"{view}_row"] = (ys.max() - (v - vv.min()) * s).astype(np.float32)
    out[f"{view}_col"] = (cx + (u - ucen) * s).astype(np.float32)
    out[f"{view}_vis"] = vis
    out[f"{view}_facing"] = facing.astype(np.float32)
    # silhouette check: share of visible projected faces landing on the reference matte
    r = np.clip(out[f"{view}_row"].astype(int), 0, m.shape[0] - 1)
    c = np.clip(out[f"{view}_col"].astype(int), 0, m.shape[1] - 1)
    on = float((m[r[vis], c[vis]] * area[vis]).sum() / area[vis].sum())
    print(f"PROJ {view}: visible {vis.mean():.1%} of faces, {on:.1%} of visible area lands on the matte")
np.savez_compressed(D / f"{CHAR}_refproj.npz", **out)
print("WROTE", D / f"{CHAR}_refproj.npz")
