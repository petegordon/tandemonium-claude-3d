"""Standing collar on a coat: a band rising from the coat's neckline at the back and sides, round to the lapel
notches, in the coat's cloth (flat burgundy) with gold piping along its top edge. The drawing's rear view has one;
the built coat ended at a bare, ragged neckline.

  blender -b --factory-startup --python scripts/add_collar.py -- [--piece coat] [--char outfit_male_victorian]
      [--h 0.04] [--flare 0.008] [--z-min 1.2] [--front-y -0.03] [--color 120,34,40] [--pipe-r 0.0022]
      [--glb shells/coat.glb] [--out shells/coat.glb]

Neckline = the coat's open boundary edges above --z-min (found by position: the glTF stays split along UV seams),
behind --front-y (the lapels stay as they are). Each neckline point rises --h straight up, leaning out by --flare;
the band is solidified 2.5 mm. Joined into the shell (collar material + piping material).
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_victorian")
PIECE = opt("--piece", "coat")
D = ROOT / "out" / f"{CHAR}-goose"
GLB = D / opt("--glb", f"shells/{PIECE}.glb")
OUT = D / opt("--out", f"shells/{PIECE}.glb")
H, FLARE, ZMIN, FY = opt("--h", 0.04), opt("--flare", 0.008), opt("--z-min", 1.2), opt("--front-y", -0.03)
COL = [int(x) for x in opt("--color", "120,34,40").split(",")]
PR = opt("--pipe-r", 0.0022)


def lin(c):
    c = np.array(c) / 255.0
    return tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
gar = next(o for o in bpy.data.objects if o.type == "MESH")
M = gar.matrix_world
bm = bmesh.new()
bm.from_mesh(gar.data)


def key(v):
    return tuple(np.round(np.array((M @ v.co)[:]), 5))


cand = [e for e in bm.edges if len([f for f in e.link_faces if f.material_index == 0]) == 1]
count = {}
for e in cand:
    k_ = frozenset((key(e.verts[0]), key(e.verts[1])))
    count[k_] = count.get(k_, 0) + 1
adj = {}
for e in cand:
    a, b = key(e.verts[0]), key(e.verts[1])
    if count[frozenset((a, b))] != 1:
        continue
    if min(a[2], b[2]) < ZMIN or max(a[1], b[1]) < FY:
        continue
    adj.setdefault(a, []).append(b)
    adj.setdefault(b, []).append(a)
bm.free()
if not adj:
    raise SystemExit("no neckline found")
# the longest chain through the neckline edges
seen = set()
best = []
for start in [k for k, v in adj.items() if len(v) == 1] or list(adj):
    if start in seen:
        continue
    ch = [start]
    seen.add(start)
    while True:
        nxt = [n for n in adj[ch[-1]] if n not in seen]
        if not nxt:
            break
        ch.append(nxt[0])
        seen.add(nxt[0])
    if len(ch) > len(best):
        best = ch
pts = np.array(best)
# resample evenly (5 mm) and smooth (the neckline was ragged)
seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
n = max(8, int(seg[-1] / 0.005))
t = np.linspace(0, seg[-1], n)
P = np.stack([np.interp(t, seg, pts[:, i]) for i in range(3)], 1)
for _ in range(20):
    P[1:-1] = P[1:-1] * 0.5 + (P[:-2] + P[2:]) * 0.25
cx, cy = P[:, 0].mean(), P[:, 1].mean()
cb = bmesh.new()
lo, hi = [], []
for p in P:
    d = np.array([p[0] - cx, p[1] - cy, 0.0])
    d /= np.linalg.norm(d) + 1e-9
    base = p - np.array([0, 0, 0.006])                       # tucked a little into the coat
    top = p + np.array([0, 0, H]) + d * FLARE
    lo.append(cb.verts.new(base))
    hi.append(cb.verts.new(top))
for i in range(len(P) - 1):
    cb.faces.new((lo[i], lo[i + 1], hi[i + 1], hi[i]))
bmesh.ops.recalc_face_normals(cb, faces=cb.faces[:])
# outward normals: away from the neck axis
f0 = cb.faces[0]
f0.normal_update()
if np.dot(np.array(f0.normal[:]), np.array([P[0][0] - cx, P[0][1] - cy, 0])) < 0:
    bmesh.ops.reverse_faces(cb, faces=cb.faces[:])
cme = bpy.data.meshes.new("collar")
cb.to_mesh(cme)
cb.free()
co = bpy.data.objects.new("collar", cme)
bpy.context.scene.collection.objects.link(co)
cm = bpy.data.materials.new(f"{CHAR}_{PIECE}_collar")
cm.use_nodes = True
bs = cm.node_tree.nodes["Principled BSDF"]
bs.inputs["Base Color"].default_value = lin(COL)
bs.inputs["Roughness"].default_value = 0.85
cme.materials.append(cm)
bpy.ops.object.select_all(action="DESELECT")
co.select_set(True)
bpy.context.view_layer.objects.active = co
sol = co.modifiers.new("sol", "SOLIDIFY")
sol.thickness = 0.0025
sol.offset = -1.0
bpy.ops.object.modifier_apply(modifier=sol.name)
for p_ in cme.polygons:
    p_.use_smooth = True
# gold piping along the top edge
pb = bmesh.new()
rings = []
NS = 8
for i in range(len(P)):
    d = np.array([P[i][0] - cx, P[i][1] - cy, 0.0])
    d /= np.linalg.norm(d) + 1e-9
    c = P[i] + np.array([0, 0, H]) + d * FLARE
    tng = P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]
    tng /= np.linalg.norm(tng) + 1e-9
    u = np.cross(tng, [0, 0, 1.0])
    u /= np.linalg.norm(u) + 1e-9
    w = np.cross(u, tng)
    rings.append([pb.verts.new(c + PR * (math.cos(2 * math.pi * k / NS) * u + math.sin(2 * math.pi * k / NS) * w))
                  for k in range(NS)])
for i in range(len(rings) - 1):
    for k in range(NS):
        pb.faces.new((rings[i][k], rings[i][(k + 1) % NS], rings[i + 1][(k + 1) % NS], rings[i + 1][k]))
pme = bpy.data.meshes.new("collar_piping")
pb.to_mesh(pme)
pb.free()
for p_ in pme.polygons:
    p_.use_smooth = True
pm = bpy.data.materials.new(f"{CHAR}_{PIECE}_collar_piping")
pm.use_nodes = True
b2 = pm.node_tree.nodes["Principled BSDF"]
b2.inputs["Base Color"].default_value = lin([196, 146, 62])
b2.inputs["Metallic"].default_value = 0.85
b2.inputs["Roughness"].default_value = 0.35
pme.materials.append(pm)
po = bpy.data.objects.new("collar_piping", pme)
bpy.context.scene.collection.objects.link(po)
bpy.ops.object.select_all(action="DESELECT")
for o in (co, po, gar):
    o.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.object.join()
bpy.ops.export_scene.gltf(filepath=str(OUT), export_format="GLB", use_selection=True, export_tangents=True)
print("COLLAR", PIECE, "points", len(P), "length_m", round(float(seg[-1]), 3),
      "z", round(float(P[:, 2].min()), 3), round(float(P[:, 2].max()), 3))
