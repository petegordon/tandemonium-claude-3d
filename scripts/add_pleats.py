"""Pin-tuck pleats on a shirt front: thin raised vertical ridges either side of the button placket, following the
shirt's surface, joined into the shell in the shirt's cloth material.

  blender -b --factory-startup --python scripts/add_pleats.py -- [--piece shirt] [--char outfit_male_victorian]
      [--xs 0.016,0.026,0.036,0.046] [--z 1.0,1.21] [--r 0.0016] [--glb shells/shirt.glb] [--out shells/shirt.glb]

Each pleat (x = +-each of --xs) is a half-tube: points every 5 mm from z0 to z1, each found by a ray from the front
(-y) onto the shirt, raised 0.6 r along the surface normal; the ends taper into the cloth. The ridges reuse the
shirt's first material, so they take its colour and catch the light as stitched tucks.
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_victorian")
PIECE = opt("--piece", "shirt")
D = ROOT / "out" / f"{CHAR}-goose"
GLB = D / opt("--glb", f"shells/{PIECE}.glb")
OUT = D / opt("--out", f"shells/{PIECE}.glb")
XS = [float(x) for x in opt("--xs", "0.016,0.026,0.036,0.046").split(",")]
Z0, Z1 = (float(z) for z in opt("--z", "1.0,1.21").split(","))
RAD = opt("--r", 0.0016)
NSEG = 8

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
gar = next(o for o in bpy.data.objects if o.type == "MESH")
M = gar.matrix_world
GB = BVHTree.FromPolygons([M @ v.co for v in gar.data.vertices], [tuple(p.vertices) for p in gar.data.polygons])
# --clear-of waistcoat[,..]: no tuck where one of these shells lies in front of the shirt (the tucks poked through
# the vest beside its V): the pleat runs are split there
CLEAR = []
for nm in [x for x in opt("--clear-of", "").split(",") if x]:
    seen = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(D / "shells" / f"{nm}.glb"))
    for o_ in [o_ for o_ in bpy.data.objects if o_ not in seen and o_.type == "MESH"]:
        Mo = o_.matrix_world
        CLEAR.append(BVHTree.FromPolygons([Mo @ v.co for v in o_.data.vertices], [tuple(q.vertices) for q in o_.data.polygons]))
        bpy.data.objects.remove(o_)
bm = bmesh.new()


def build_pleat(pts, nrms):
    rings = []
    N = len(pts)
    for i, (p, n) in enumerate(zip(pts, nrms)):
        t = pts[min(i + 1, N - 1)] - pts[max(i - 1, 0)]
        t /= np.linalg.norm(t) + 1e-12
        u = np.cross(t, n)
        u /= np.linalg.norm(u) + 1e-12
        taper = min(1.0, i / 3, (N - 1 - i) / 3) * 0.85 + 0.15
        r = RAD * taper
        c = p + n * (r * 0.6 - 0.0004)
        ring = []
        for k in range(NSEG + 1):                      # half-tube: from one side, over the top, to the other
            a = math.pi * k / NSEG
            ring.append(bm.verts.new(c + r * (math.cos(a) * u + math.sin(a) * n)))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for k in range(NSEG):
            bm.faces.new((rings[i][k], rings[i][k + 1], rings[i + 1][k + 1], rings[i + 1][k]))
    return 1


n_pleats = 0
for sx in (1, -1):
    for x in XS:
        runs, pts, nrms = [], [], []
        for z in np.arange(Z0, Z1 + 1e-6, 0.005):
            hit = GB.ray_cast(Vector((sx * x, -0.5, z)), Vector((0, 1, 0)), 1.0)
            ok = hit[0] is not None and hit[1].y < -0.2      # hit, on a face toward the front
            if ok:
                for cb in CLEAR:
                    hc = cb.ray_cast(Vector((sx * x, -0.5, z)), Vector((0, 1, 0)), 1.0)
                    if hc[0] is not None and hc[0].y < hit[0].y + 0.012:
                        ok = False
            if ok:
                pts.append(np.array(hit[0][:]))
                nrms.append(np.array(hit[1][:]))
            elif pts:
                runs.append((pts, nrms))
                pts, nrms = [], []
        if pts:
            runs.append((pts, nrms))
        for pts, nrms in runs:
            if len(pts) >= 6:
                n_pleats += build_pleat(pts, nrms)
me = bpy.data.meshes.new("pleats")
bm.to_mesh(me)
bm.free()
for p in me.polygons:
    p.use_smooth = True
po = bpy.data.objects.new("pleats", me)
bpy.context.scene.collection.objects.link(po)
me.materials.append(gar.data.materials[0])
uv = me.uv_layers.new(name=gar.data.uv_layers[0].name if gar.data.uv_layers else "UVMap")
# UVs: each pleat vertex samples the shirt texture at the nearest shirt point's UV (so the colour matches)
guv = gar.data.uv_layers[0].data if gar.data.uv_layers else None
if guv is not None:
    loop_of = {}
    for lp in gar.data.loops:
        loop_of.setdefault(lp.vertex_index, lp.index)
    GV = np.array([(M @ v.co)[:] for v in gar.data.vertices])
    from mathutils.kdtree import KDTree
    kd = KDTree(len(GV))
    for i, q in enumerate(GV):
        kd.insert(q, i)
    kd.balance()
    for lp in me.loops:
        _, j, _ = kd.find(me.vertices[lp.vertex_index].co)
        uv.data[lp.index].uv = guv[loop_of[j]].uv
bpy.ops.object.select_all(action="DESELECT")
po.select_set(True)
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.object.join()
bpy.ops.export_scene.gltf(filepath=str(OUT), export_format="GLB", use_selection=True, export_tangents=True)
print("PLEATS", PIECE, n_pleats)
