"""Modelled ribbon bows on a garment (a stomacher's echelle of bows down the bodice front): each bow = two puffed satin
loops, a knot, two short tails and an optional faceted jewel in a gilt setting on the knot, sitting on the shell's
surface; joined into the shell in their own materials (satin, gilt, jewel).

  blender -b --factory-startup --python scripts/add_bows.py -- --char outfit_female_georgian [--piece jacket]

Recipe chars json "bow_trims" {piece, x, z: [..] (top to bottom), w, h, scale_step (each bow down is this much
smaller / larger), color, rough, tail_len, jewel: {r, color, setting}}. Placement: a ray from the front (-y) onto the
shell at (x, z); the bow lies in the surface's tangent plane there, 2 mm proud.
"""
import json
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
CHAR = opt("--char", "outfit_female_georgian")
BT = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))["bow_trims"]
if isinstance(BT, list):              # several bow sets, one per piece (an apron's tie + a shawl's knot): --piece picks
    BT = next(b for b in BT if b.get("piece", "jacket") == opt("--piece", BT[0].get("piece", "jacket")))
PIECE = opt("--piece", BT.get("piece", "jacket"))
GLB = ROOT / "out" / f"{CHAR}-goose" / "shells" / f"{PIECE}.glb"


def lin(c):
    c = np.array(c[:3]) / 255.0
    return tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
gar = next(o for o in bpy.data.objects if o.type == "MESH")
M = gar.matrix_world
bvh = BVHTree.FromPolygons([M @ v.co for v in gar.data.vertices], [tuple(p.vertices) for p in gar.data.polygons])
bm = bmesh.new()
uvl = bm.loops.layers.uv.new("UVMap")


def strip(path, widths, wdir, mat, thick=0.0010):
    rows = []
    n_ = len(path)
    for i in range(n_):
        t_ = (path[min(i + 1, n_ - 1)] - path[max(i - 1, 0)]).normalized()
        nn = t_.cross(wdir[i]).normalized() * thick
        a, b = path[i] + wdir[i] * widths[i], path[i] - wdir[i] * widths[i]
        rows.append([bm.verts.new(a + nn), bm.verts.new(b + nn), bm.verts.new(b - nn), bm.verts.new(a - nn)])
    for i in range(n_ - 1):
        for k in range(4):
            f = bm.faces.new([rows[i][k], rows[i][(k + 1) % 4], rows[i + 1][(k + 1) % 4], rows[i + 1][k]])
            f.material_index = mat
    for r_ in (rows[0], rows[-1][::-1]):
        bm.faces.new(r_).material_index = mat


def ellipsoid(c, ax, r3, mat, nu=12, nv=6):
    a1, a2, a3 = ax
    rows = []
    for i in range(nv + 1):
        ph = math.pi * i / nv - math.pi / 2
        rows.append([bm.verts.new(c + a1 * r3[0] * math.cos(ph) * math.cos(2 * math.pi * k / nu)
                                  + a2 * r3[1] * math.cos(ph) * math.sin(2 * math.pi * k / nu) + a3 * r3[2] * math.sin(ph))
                     for k in range(nu)])
    for i in range(nv):
        for k in range(nu):
            f = bm.faces.new([rows[i][k], rows[i][(k + 1) % nu], rows[i + 1][(k + 1) % nu], rows[i + 1][k]])
            f.material_index = mat


placed = 0
zs = BT["z"]
for bi, z in enumerate(zs):
    sc = 1.0 + BT.get("scale_step", 0.0) * bi
    back_ = BT.get("from") == "back"                        # "from": "back": a bow on the back (an apron's tie)
    loc, nrm, _, _ = bvh.ray_cast(Vector((BT.get("x", 0.0), 0.6 if back_ else -0.6, z)), Vector((0, -1 if back_ else 1, 0)), 2.0)
    if loc is None:
        continue
    n = ((nrm if nrm.y > 0 else -nrm) if back_ else (-nrm if nrm.y > 0 else nrm)).normalized()   # outward (toward the viewer)
    if BT.get("axis_normal"):          # face straight along the body axis (a fold / crease at the spot tilts the face normal)
        n = Vector((0, 1 if back_ else -1, 0))
    up = Vector((0, 0, 1))
    side = up.cross(n).normalized()
    up = n.cross(side).normalized()
    W, H = BT.get("w", 0.04) * sc, BT.get("h", 0.022) * sc
    c0 = loc + n * 0.002
    NS = 24
    for k in (1, -1):
        path, wd, ws = [], [], []
        for i in range(NS + 1):
            t = 2 * math.pi * i / NS
            path.append(c0 + side * (k * W / 4 * (1 - math.cos(t))) + n * (BT.get("puff", 0.006) * sc * math.sin(t) + 0.003)
                        + up * (0.08 * H * math.sin(t)))
            wd.append(up)
            ws.append(H / 2 * (0.4 + 0.6 * math.sin(t / 2) ** 2))
        strip(path, ws, wd, 0)
    for k in (1, -1):
        a_ = math.radians(BT.get("tail_deg", 22)) * k
        dv = (-up * math.cos(a_) + side * math.sin(a_)).normalized()
        L = BT.get("tail_len", 0.022) * sc
        path = [c0 + n * 0.003 + dv * (L * i / 6) for i in range(7)]
        strip(path, [H * 0.18 * (1 + 0.3 * i / 6) for i in range(7)], [n.cross(dv).normalized()] * 7, 0)
    ellipsoid(c0 + n * 0.005, (side, up, n), (W * 0.11, H * 0.3, 0.0035 * sc), 0)        # the knot
    JW = BT.get("jewel")
    if JW:
        jr = JW.get("r", 0.004) * sc
        ellipsoid(c0 + n * 0.0085, (side, up, n), (jr * 1.35, jr * 1.35, jr * 0.45), 1, 16, 4)          # gilt setting
        ellipsoid(c0 + n * (0.0085 + jr * 0.3), (side, up, n), (jr, jr, jr * 0.6), 2, 8, 4)              # faceted stone
    placed += 1

me = bpy.data.meshes.new("bows")
bm.to_mesh(me)
bm.free()
bo = bpy.data.objects.new("bows", me)
bpy.context.scene.collection.objects.link(bo)
for nm, col, rough, metal in (("satin", BT.get("color", [176, 196, 228]), BT.get("rough", 0.3), 0.0),
                              ("gilt", (BT.get("jewel") or {}).get("setting", [214, 174, 90]), 0.25, 1.0),
                              ("jewel", (BT.get("jewel") or {}).get("color", [228, 234, 246]), 0.05, 0.7)):
    m = bpy.data.materials.new(f"{CHAR}_{PIECE}_bow_{nm}")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = lin(col)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    me.materials.append(m)
for pg in me.polygons:
    pg.use_smooth = pg.material_index != 2                  # the stone stays faceted
bm2 = bmesh.new()
bm2.from_mesh(me)
bmesh.ops.triangulate(bm2, faces=bm2.faces[:])
bm2.to_mesh(me)
bm2.free()
me.uv_layers.new(name=gar.data.uv_layers[0].name if gar.data.uv_layers else "UVMap")
for o in bpy.data.objects:
    o.select_set(False)
bo.select_set(True)
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.object.join()
bpy.ops.export_scene.gltf(filepath=str(GLB), use_selection=True, export_format="GLB", export_tangents=True)
print("BOWS", json.dumps({"piece": PIECE, "n": placed}))
