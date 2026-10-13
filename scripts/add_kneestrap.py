"""Buckled leather straps round the plus-fours' knee bands (1920s cyclist), joined into the breeches shell as their own
material slots (leather, brass), so dress_goose.py skins them with the garment.

  blender -b --factory-startup --python scripts/add_kneestrap.py -- --char outfit_male_cyclist [--piece breeches]

Recipe chars json "kneestrap": z (strap centre height), h (strap height), t (thickness), off (clearance off the cloth),
buckle_az (degrees from the front toward the outside of each leg), buckle_w / buckle_h, leather / brass colours.
Per leg the cloth's radius is ray-cast from the leg's own centre (the slice of the shell at that height) every 7.5 deg.
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
CHAR = opt("--char", "outfit_male_cyclist")
PIECE = opt("--piece", "breeches")
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
K = cfg["kneestrap"]
GLB = ROOT / "out" / f"{CHAR}-goose" / "shells" / f"{PIECE}.glb"


def srgb(c):
    c = np.array(c[:3]) / 255.0
    return tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)


def material(name, col, rough, metal):
    m = bpy.data.materials.new(f"{CHAR}_{PIECE}_{name}")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = srgb(col)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def box_ring(bm, pts_in, pts_out, h, zc, closed=True):
    """A band of rectangular section: inner / outer rings (N, 2 xy) at zc +- h/2."""
    n = len(pts_in)
    rings = []
    for (pi, po) in zip(pts_in, pts_out):
        rings.append([bm.verts.new((pi[0], pi[1], zc - h / 2)), bm.verts.new((po[0], po[1], zc - h / 2)),
                      bm.verts.new((po[0], po[1], zc + h / 2)), bm.verts.new((pi[0], pi[1], zc + h / 2))])
    for i in range(n if closed else n - 1):
        a, b = rings[i], rings[(i + 1) % n]
        for k in range(4):
            bm.faces.new((a[k], b[k], b[(k + 1) % 4], a[(k + 1) % 4]))
    if not closed:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
shell = next(o for o in bpy.context.scene.objects if o.type == "MESH")
bvh = BVHTree.FromObject(shell, bpy.context.evaluated_depsgraph_get())
V = np.array([(shell.matrix_world @ v.co)[:] for v in shell.data.vertices])
zc = K["z"]
leather = material("strap", K.get("leather", [92, 52, 28]), 0.45, 0.0)
brass = material("buckle", K.get("brass", [178, 136, 64]), 0.3, 1.0)
new_obs = []
for sx in (1, -1):
    sl = V[(np.abs(V[:, 2] - zc) < 0.01) & (V[:, 0] * sx > 0.02)]
    cx, cy = float((sl[:, 0].min() + sl[:, 0].max()) / 2), float((sl[:, 1].min() + sl[:, 1].max()) / 2)
    NA = 48
    ths = np.linspace(0, 2 * math.pi, NA, endpoint=False)
    rr = []
    for th in ths:
        d = np.array([math.sin(th) * sx, -math.cos(th), 0.0])     # th 0 = front, + = toward the outside of the leg
        best = 0.0
        for dz in (-K["h"] / 2, 0.0, K["h"] / 2):                 # the widest of the strap's height
            o = np.array([cx, cy, zc + dz])
            hit = bvh.ray_cast(Vector(o), Vector(d), 0.15)        # from inside the leg: its own cloth first
            if hit[0] is not None:
                best = max(best, float(np.linalg.norm((np.array(hit[0]) - o)[:2])))
        rr.append(best if best > 0 else 0.07)
    rr = np.array(rr)
    for _ in range(3):
        rr = np.maximum(rr, 0.25 * np.roll(rr, 1) + 0.5 * rr + 0.25 * np.roll(rr, -1))
    r_in = rr + K.get("off", 0.002)
    r_out = r_in + K.get("t", 0.003)
    D = np.stack([np.sin(ths) * sx, -np.cos(ths)], 1)
    C = np.array([cx, cy])
    bm = bmesh.new()
    box_ring(bm, C + D * r_in[:, None], C + D * r_out[:, None], K["h"], zc)
    me = bpy.data.meshes.new("strap")
    bm.to_mesh(me)
    bm.free()
    so = bpy.data.objects.new("strap", me)
    bpy.context.scene.collection.objects.link(so)
    me.materials.append(leather)
    new_obs.append(so)
    # buckle: a brass rectangular frame + centre bar standing on the strap at buckle_az, the strap's free end beyond it
    az = math.radians(K.get("buckle_az", 70))
    i0 = int(round(az / (2 * math.pi) * NA)) % NA
    n_ = np.array([math.sin(az) * sx, -math.cos(az), 0.0])
    tng = np.array([math.cos(az) * sx, math.sin(az), 0.0])           # along the strap (toward the back)
    base = np.array([cx, cy, zc]) + n_ * (r_out[i0] + 0.0008)
    bw, bh, bt = K.get("buckle_w", 0.022), K.get("buckle_h", 0.026), K.get("buckle_t", 0.003)
    bb = bmesh.new()
    up = np.array([0, 0, 1.0])
    bars = [((-bw / 2, -bh / 2), (bw / 2, -bh / 2)), ((-bw / 2, bh / 2), (bw / 2, bh / 2)),
            ((-bw / 2, -bh / 2), (-bw / 2, bh / 2)), ((bw / 2, -bh / 2), (bw / 2, bh / 2)),
            ((0.0, -bh / 2), (0.0, bh / 2))]
    for (a0, a1), (b0, b1) in bars:
        p0 = base + tng * a0 + up * a1
        p1 = base + tng * b0 + up * b1
        ax = p1 - p0
        L = np.linalg.norm(ax)
        ax /= L
        side = np.cross(ax, n_)
        side /= np.linalg.norm(side)
        vs = []
        for p in (p0 - ax * bt / 2, p1 + ax * bt / 2):
            for su, sn in ((-1, 0), (1, 0), (1, 1), (-1, 1)):
                vs.append(bb.verts.new(tuple(p + side * su * bt / 2 + n_ * sn * bt)))
        for k in range(4):
            bb.faces.new((vs[k], vs[(k + 1) % 4], vs[4 + (k + 1) % 4], vs[4 + k]))
        bb.faces.new(vs[3::-1])
        bb.faces.new(vs[4:])
    bme = bpy.data.meshes.new("buckle")
    bb.to_mesh(bme)
    bb.free()
    bo = bpy.data.objects.new("buckle", bme)
    bpy.context.scene.collection.objects.link(bo)
    bme.materials.append(brass)
    new_obs.append(bo)
    # free end: a short tab beyond the buckle, lying on the strap
    j = [(i0 + k) % NA for k in range(0, 4)]
    tb = bmesh.new()
    pin = [C + D[k] * (r_out[k] + 0.0005) for k in j]
    pout = [C + D[k] * (r_out[k] + 0.0005 + K.get("t", 0.003)) for k in j]
    box_ring(tb, pin, pout, K["h"] * 0.8, zc, closed=False)
    tme = bpy.data.meshes.new("tab")
    tb.to_mesh(tme)
    tb.free()
    to = bpy.data.objects.new("tab", tme)
    bpy.context.scene.collection.objects.link(to)
    tme.materials.append(leather)
    new_obs.append(to)
    print("STRAP", "L" if sx > 0 else "R", "centre", round(cx, 3), round(cy, 3), "r mm", round(float(rr.min()) * 1000),
          round(float(rr.max()) * 1000))
# strap UVs: one small strip (plain colours, no texture), then join into the shell
for o in new_obs:
    o.data.uv_layers.new(name="UVMap")
    for pg in o.data.polygons:          # leather edges read rounded; the faceted ring showed every segment
        pg.use_smooth = True
bpy.ops.object.select_all(action="DESELECT")
for o in new_obs:
    o.select_set(True)
shell.select_set(True)
bpy.context.view_layer.objects.active = shell
bpy.ops.object.join()
bpy.ops.export_scene.gltf(filepath=str(GLB), use_selection=True, export_format="GLB")
print("STRAP ->", GLB)
