"""Small modelled trims joined into a garment shell as their own material slots (so dress_goose.py skins them with it,
by the nearest body weights), like add_kneestrap.py:

  blender -b --factory-startup --python scripts/add_trims.py -- --char outfit_grandpa --kind fob
  blender -b --factory-startup --python scripts/add_trims.py -- --char outfit_grandpa --kind braces

fob (chars json "fob"): a pocket watch (gold case + crown + bow) lying on the garment's front, its chain sagging to the
  watch pocket.  {piece: "waistcoat", watch: [x, z], watch_r, watch_t, chain_to: [x, z], chain_sag, chain_r, gold: rgb}
braces (chars json "braces"): dropped braces -- per side one strap from a clip on the front waistband, down round the
  outside of the thigh and up to a clip on the back waistband (worn off the shoulders, hanging in a loop).
  {piece: "breeches", w, t, off, color: rgb, clip: rgb, path: [[azimuth_deg, z], ...]} -- azimuth 0 = centre front,
  90 = the side, 180 = centre back (mirrored for the right side); each point is ray-cast from outside onto the shell.
Heights are in the character's build frame. Run right after the shell is (re)built: it adds geometry every time.
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
    return argv[argv.index(name) + 1] if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR, KIND = opt("--char", ""), opt("--kind", "fob")
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
K = cfg[KIND]
PIECE = K.get("piece", "waistcoat" if KIND == "fob" else "breeches")
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


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
shell = next(o for o in bpy.context.scene.objects if o.type == "MESH")
dg = bpy.context.evaluated_depsgraph_get()
me_ = shell.evaluated_get(dg).to_mesh()
bvh = BVHTree.FromPolygons([tuple(shell.matrix_world @ v.co) for v in me_.vertices], [tuple(p.vertices) for p in me_.polygons])
V = np.array([(shell.matrix_world @ v.co)[:] for v in shell.data.vertices])


def onto(o, d, far=0.6):
    """First shell hit from o along d: (point, outward normal)."""
    h = bvh.ray_cast(Vector(o), Vector(d), far)
    if h[0] is None:
        return None
    n = np.array(h[1])
    if n @ np.array(d) > 0:
        n = -n
    return np.array(h[0]), n / np.linalg.norm(n)


def front_hit(x, z):
    return onto(np.array([x, -0.6, z]), (0, 1.0, 0))


def ribbon(bm, pts, nrm, w, t):
    """A flat strap of width w, thickness t along pts (lying on normals nrm)."""
    rings = []
    for i, (p, n) in enumerate(zip(pts, nrm)):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, len(pts) - 1)]
        tg = (b - a) / max(np.linalg.norm(b - a), 1e-9)
        s = np.cross(tg, n)
        s /= max(np.linalg.norm(s), 1e-9)
        rings.append([bm.verts.new(tuple(p + s * sx * w / 2 + n * nz * t)) for sx, nz in ((-1, 0), (1, 0), (1, 1), (-1, 1))])
    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        for k in range(4):
            bm.faces.new((r0[k], r1[k], r1[(k + 1) % 4], r0[(k + 1) % 4]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])


def tube(bm, pts, r, seg=8):
    rings = []
    for i, p in enumerate(pts):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, len(pts) - 1)]
        tg = (b - a) / max(np.linalg.norm(b - a), 1e-9)
        ref = np.array([0, 0, 1.0]) if abs(tg[2]) < 0.9 else np.array([1.0, 0, 0])
        x = np.cross(tg, ref)
        x /= np.linalg.norm(x)
        y = np.cross(tg, x)
        rings.append([bm.verts.new(tuple(p + r * (math.cos(q) * x + math.sin(q) * y))) for q in np.linspace(0, 2 * math.pi, seg, endpoint=False)])
    for i in range(len(rings) - 1):
        for k in range(seg):
            bm.faces.new((rings[i][k], rings[i + 1][k], rings[i + 1][(k + 1) % seg], rings[i][(k + 1) % seg]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])


def disc(bm, c, n, r, t, seg=28):
    u = np.cross(n, [0, 0, 1.0])
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    ring = lambda off, rr: [bm.verts.new(tuple(c + n * off + rr * (math.cos(a) * u + math.sin(a) * v))) for a in np.linspace(0, 2 * math.pi, seg, endpoint=False)]
    r0, r1, r2 = ring(0.0, r * 0.96), ring(t * 0.6, r), ring(t, r * 0.88)        # a domed case
    for A, B in ((r0, r1), (r1, r2)):
        for k in range(seg):
            bm.faces.new((A[k], B[k], B[(k + 1) % seg], A[(k + 1) % seg]))
    bm.faces.new(r0[::-1])
    bm.faces.new(r2)
    return u, v


def finish(objs_mats):
    new = []
    for name, bm, mat in objs_mats:
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(o)
        me.materials.append(mat)
        me.uv_layers.new(name="UVMap")
        for pg in me.polygons:
            pg.use_smooth = True
        new.append(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in new:
        o.select_set(True)
    shell.select_set(True)
    bpy.context.view_layer.objects.active = shell
    bpy.ops.object.join()
    bpy.ops.export_scene.gltf(filepath=str(GLB), use_selection=True, export_format="GLB")


if KIND == "fob":
    gold = material("watch_gold", K.get("gold", [200, 160, 76]), 0.28, 1.0)
    wx, wz = K["watch"]
    p, n = front_hit(wx, wz)
    r, t = K.get("watch_r", 0.014), K.get("watch_t", 0.005)
    c = p + n * 0.0015
    bmw = bmesh.new()
    u, v = disc(bmw, c, n, r, t)
    up = np.array([0, 0, 1.0])
    top = c + up * r + n * t * 0.5
    tube(bmw, [top - up * 0.002, top + up * 0.004], 0.0022)                       # crown
    bow = [top + up * 0.004 + 0.0045 * (math.cos(a) * np.array([1.0, 0, 0]) + math.sin(a) * up) + up * 0.0045
           for a in np.linspace(-math.pi * 0.5, math.pi * 1.5, 14)]                 # bow ring
    tube(bmw, bow, 0.0009, seg=6)
    # chain: from the bow, sagging, to the pocket -- lying just off the cloth
    cx, cz = K["chain_to"]
    a3 = np.array([wx, wz + r + 0.01])
    b3 = np.array([cx, cz])
    pts = []
    for s in np.linspace(0, 1, 22):
        xz = a3 + (b3 - a3) * s
        xz[1] -= K.get("chain_sag", 0.02) * 4 * s * (1 - s)
        h = front_hit(xz[0], xz[1])
        if h:
            pts.append(h[0] + h[1] * 0.0028)
    bmc = bmesh.new()
    tube(bmc, pts, K.get("chain_r", 0.0011), seg=6)
    finish([("watch", bmw, gold), ("chain", bmc, gold)])
    print("FOB watch", np.round(c, 3).tolist(), "chain pts", len(pts), "->", GLB)
else:
    strap = material("braces", K.get("color", [170, 30, 34]), 0.6, 0.0)
    clipm = material("clip", K.get("clip", [190, 190, 196]), 0.3, 1.0)
    w, t, off = K.get("w", 0.024), K.get("t", 0.0025), K.get("off", 0.002)
    out = []
    for sg in (1, -1):
        pts, nrm = [], []
        path = np.array(K["path"], float)
        az = np.interp(np.linspace(0, len(path) - 1, 60), np.arange(len(path)), path[:, 0])
        zz = np.interp(np.linspace(0, len(path) - 1, 60), np.arange(len(path)), path[:, 1])
        for a_, z_ in zip(az, zz):
            th = math.radians(a_)
            sl = V[np.abs(V[:, 2] - z_) < 0.01]
            half = sl[sl[:, 0] * sg > 0.0] if z_ < K.get("crotch_z", 0.62) else sl          # below the crotch: the leg
            ctr = np.array([(half[:, 0].min() + half[:, 0].max()) / 2 if z_ < K.get("crotch_z", 0.62) else 0.0,
                            (half[:, 1].min() + half[:, 1].max()) / 2, z_])
            d = np.array([math.sin(th) * sg, -math.cos(th), 0.0])
            h = onto(ctr + d * 0.5, -d)
            if h:
                pts.append(h[0] + h[1] * off)
                nrm.append(h[1])
        pts = np.array(pts)
        for _ in range(3):                                     # a strap bridges small dips
            pts[1:-1] = 0.25 * pts[:-2] + 0.5 * pts[1:-1] + 0.25 * pts[2:]
        bm = bmesh.new()
        ribbon(bm, list(pts), nrm, w, t)
        out.append((f"brace_{sg}", bm, strap))
        for i in (0, len(pts) - 1):                            # a metal clip at each end
            bc = bmesh.new()
            p, n = pts[i], nrm[i]
            q = np.cross(n, [0, 0, 1.0])
            q /= np.linalg.norm(q)
            for dz in (-0.012, 0.012):
                pass
            tube(bc, [p + n * t - np.array([0, 0, 0.01]), p + n * t + np.array([0, 0, 0.012])], 0.0035, seg=6)
            out.append((f"clip_{sg}_{i}", bc, clipm))
    finish(out)
    print("BRACES", len(out), "parts ->", GLB)
