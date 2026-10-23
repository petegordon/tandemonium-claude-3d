"""A crocheted shawl's front knot (Grandma): the two front ends tied in a soft knot, with two wide crochet ends hanging
from it over the bodice -- in open-work crochet like the shawl (a tiling one-cell crochet texture with alpha-clipped
holes), joined into the shawl shell.

  blender -b --factory-startup --python scripts/add_shawl_knot.py -- --char outfit_grandma

Recipe chars json "shawl_knot" (BUILD frame): {piece (shawl), x, z (knot centre on the shell's front), knot: [w, h, d],
end_len, end_w: [top, bottom], end_deg (spread of each end from vertical), end_gap (between the ends at the knot),
end_off (stand-off over what is under them), over: [pieces the ends lie on, e.g. jacket], pitch, hole, color}.
Run after the shell's pattern_paint (build_cyclist.sh runs it when the recipe has "shawl_knot" for that piece).
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
CHAR = opt("--char", "outfit_grandma")
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
K = cfg["shawl_knot"]
PIECE = K.get("piece", "shawl")
D = ROOT / "out" / f"{CHAR}-goose" / "shells"
GLB = D / f"{PIECE}.glb"


def lin(c):
    c = np.array(c[:3]) / 255.0
    return np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
gar = next(o for o in bpy.data.objects if o.type == "MESH")
trees = []


def tree_of(o):
    M = o.matrix_world
    return BVHTree.FromPolygons([M @ v.co for v in o.data.vertices], [tuple(p.vertices) for p in o.data.polygons])


trees.append(tree_of(gar))
under = []
for pc in K.get("over", ["jacket"]):              # what the hanging ends lie on (the bodice)
    if (D / f"{pc}.glb").exists():
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(D / f"{pc}.glb"))
        for o in set(bpy.data.objects) - before:
            if o.type == "MESH":
                under.append(tree_of(o))
                o.hide_render = True
                o["__drop"] = 1


def front_hit(x, z, ts):
    best = None
    for t in ts:
        loc, nrm, _, _ = t.ray_cast(Vector((x, -0.6, z)), Vector((0, 1, 0)), 2.0)
        if loc is not None and (best is None or loc.y < best[0].y):
            n_ = -nrm if nrm.y > 0 else nrm
            best = (loc, n_)
    return best


X, Z = K.get("x", 0.0), K["z"]
hit = front_hit(X, Z, trees)
assert hit, "no shell at the knot"
c0, n0 = hit
n0 = Vector((0, -1, 0)).lerp(n0, 0.3).normalized()
side = Vector((0, 0, 1)).cross(n0).normalized()
up = n0.cross(side).normalized()
kw, kh, kd = K.get("knot", [0.05, 0.032, 0.022])
kc = c0 + n0 * (kd * 0.5 + K.get("knot_off", 0.002))
P = K.get("pitch", 0.012)
bm = bmesh.new()
uvl = bm.loops.layers.uv.new("UVMap")


def face(vs, uvs, mat):
    f = bm.faces.new(vs)
    f.material_index = mat
    for lp, uv in zip(f.loops, uvs):
        lp[uvl].uv = uv
    return f


# the knot: a soft cushion, gathered (waisted) across the middle where it wraps the ends; its UVs run round it
NU, NV = 28, 14
rows = []
for i in range(NV + 1):
    ph = math.pi * i / NV - math.pi / 2
    row = []
    for k in range(NU):
        th = 2 * math.pi * k / NU
        xs_ = math.cos(ph) * math.cos(th)                     # -1..1 across the knot
        waist = 1 - K.get("pinch", 0.3) * math.exp(-(xs_ / 0.22) ** 2)   # pinched in the middle where it wraps
        lump = 1 + 0.07 * math.sin(5 * th + 2.0 * xs_ + 1.3) * math.cos(ph)   # twisted folds of the yarn
        p = (kc + side * (kw / 2) * xs_ * lump
             + up * (kh / 2) * math.sin(ph) * waist + n0 * (kd / 2) * math.cos(ph) * math.sin(th) * lump * waist)
        row.append((bm.verts.new(p), (th * kw / 2 / P, (ph + math.pi / 2) * kh / 2 / P)))
    rows.append(row)
for i in range(NV):
    for k in range(NU):
        k2 = (k + 1) % NU
        a, b, c, d = rows[i][k], rows[i][k2], rows[i + 1][k2], rows[i + 1][k]
        ub = b[1][0] if k2 else a[1][0] + 2 * math.pi * kw / 2 / P / NU
        uc = c[1][0] if k2 else d[1][0] + 2 * math.pi * kw / 2 / P / NU
        face([a[0], b[0], c[0], d[0]], [a[1], (ub, b[1][1]), (uc, c[1][1]), d[1]], 1)
# the two hanging ends: from under the knot, fanning out, lying on what is below (a double layer: the holes see through)
EL = K.get("end_len", 0.11)
EW0, EW1 = K.get("end_w", [0.03, 0.04])
NSL, NSW = 24, 8
for sg in (1, -1):
    ang = math.radians(K.get("end_deg", 10)) * sg
    x0 = X + sg * K.get("end_gap", 0.006)
    pts, nrms = [], []
    for i in range(NSL + 1):
        t = i / NSL
        L_ = EL * t
        xc = x0 + math.sin(ang) * L_
        zc = Z - kh * 0.25 - math.cos(ang) * L_
        h_ = front_hit(xc, zc, trees[1:] + under) or front_hit(xc, zc, trees)
        if h_ is None:
            pts.append(pts[-1] + (pts[-1] - pts[-2]) if len(pts) > 1 else Vector((xc, -0.2, zc)))
            nrms.append(nrms[-1] if nrms else Vector((0, -1, 0)))
            continue
        pts.append(h_[0] + h_[1] * (K.get("end_off", 0.006) + 0.004 * math.sin(math.pi * t)))
        nrms.append(h_[1])
    for _ in range(4):                       # smooth the run (the bodice's folds)
        pts = [pts[0]] + [(pts[i - 1] + pts[i] * 2 + pts[i + 1]) / 4 for i in range(1, NSL)] + [pts[-1]]
    grid = []
    for i in range(NSL + 1):
        t = i / NSL
        tng = (pts[min(i + 1, NSL)] - pts[max(i - 1, 0)]).normalized()
        wd = nrms[i].cross(tng).normalized()
        w_ = EW0 + (EW1 - EW0) * t ** 0.7
        row = []
        for j in range(NSW + 1):
            s = j / NSW - 0.5
            ripple = 0.0025 * math.sin(2 * math.pi * (t * 2.2 + s * 0.8)) * t
            p = pts[i] + wd * (s * w_) + nrms[i] * ripple
            row.append(p)
        grid.append(row)
    TH = K.get("end_thick", 0.0025)
    for layer, off in (((0, 0.0),) if TH <= 0 else ((0, TH / 2), (1, -TH / 2))):   # end_thick 0: one double-sided layer
        vv = [[bm.verts.new(grid[i][j] + nrms[i] * off) for j in range(NSW + 1)] for i in range(NSL + 1)]
        for i in range(NSL):
            for j in range(NSW):
                q = [vv[i][j], vv[i][j + 1], vv[i + 1][j + 1], vv[i + 1][j]]
                u0, u1 = (j / NSW - 0.5) * EW1 / P, ((j + 1) / NSW - 0.5) * EW1 / P
                v0, v1 = -(i / NSL) * EL / P, -((i + 1) / NSL) * EL / P
                uv = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
                if layer:
                    q, uv = q[::-1], uv[::-1]
                face(q, uv, 0)
me = bpy.data.meshes.new("knot")
bm.to_mesh(me)
bm.free()
ko = bpy.data.objects.new("shawl_knot", me)
bpy.context.scene.collection.objects.link(ko)

# one crochet cell, tiled: yarn round a rounded-square hole (alpha 0 in the hole for the ends; the knot is solid)
T = 64
yy, xx = np.mgrid[0:T, 0:T]
fu, fv = (xx + 0.5) / T - 0.5, (yy + 0.5) / T - 0.5
h = K.get("hole", 0.21)
e = (np.abs(fu) ** 4 + np.abs(fv) ** 4) ** 0.25
bu = np.clip((0.5 - np.abs(fu)) / (0.5 - h), 0, 1)
bv = np.clip((0.5 - np.abs(fv)) / (0.5 - h), 0, 1)
tube = np.cos(np.minimum(bu, bv) * np.pi / 2) ** 0.6
tw = 0.5 + 0.5 * np.cos(2 * np.pi * (fu + fv) * 3)
base = np.array(K.get("color", [236, 226, 196]), float) / 255.0     # (image pixels are sRGB)
shade = (0.82 + 0.18 * tube) * (0.9 + 0.1 * tw) * (1 - 0.15 * np.clip(1 - (e - h) / 0.12, 0, 1) * (e >= h - 0.02))
col = base[None, None, :] * shade[..., None]
alpha = (e > h).astype(np.float32)


def make_img(name, a):
    im = bpy.data.images.new(name, T, T, alpha=True)
    im.pixels = np.concatenate([col, a[..., None]], -1).astype(np.float32).ravel().tolist()
    im.pack()
    return im


img_ends = make_img(f"{CHAR}_{PIECE}_knot_ends", alpha)
col = np.where((alpha < 0.5)[..., None], np.array(K.get("hole_color", [70, 22, 52]), float)[None, None] / 255.0, col)
imgs = [img_ends, make_img(f"{CHAR}_{PIECE}_knot_wrap", np.ones_like(alpha))]   # (the knot: solid, its holes painted dark)
for nm, im, clip in (("ends", imgs[0], True), ("wrap", imgs[1], False)):
    m = bpy.data.materials.new(f"{CHAR}_{PIECE}_knot_{nm}")
    m.use_nodes = True
    nt = m.node_tree
    bs = nt.nodes["Principled BSDF"]
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = im
    nt.links.new(tx.outputs["Color"], bs.inputs["Base Color"])
    bs.inputs["Roughness"].default_value = 0.95
    if clip:
        rd = nt.nodes.new("ShaderNodeMath")
        rd.operation = "ROUND"
        nt.links.new(tx.outputs["Alpha"], rd.inputs[0])
        nt.links.new(rd.outputs[0], bs.inputs["Alpha"])
        m.use_backface_culling = False
    me.materials.append(m)
for pg in me.polygons:
    pg.use_smooth = True
for o in list(bpy.data.objects):
    if o.get("__drop"):
        bpy.data.objects.remove(o)
for o in bpy.data.objects:
    o.select_set(False)
ko.select_set(True)
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.object.join()
bpy.ops.export_scene.gltf(filepath=str(GLB), use_selection=True, export_format="GLB")
print("KNOT", json.dumps({"piece": PIECE, "z": Z, "ends": EL, "tris": len(me.polygons)}))
