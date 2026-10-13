"""Lapel facings in the drawing's brocade: the coat's cloth faces along the open front above the break (the
projection laid one lapel's brocade and gold edge scattered across the shoulder) take their own material -- a seamless
tile cut from the drawn lapel, planar-mapped -- so both lapels match. The gold edge is add_piping.py's cord.

  blender -b --factory-startup --python scripts/add_lapels.py -- [--piece coat] [--char outfit_male_victorian]
      [--z 0.99,1.27] [--w 0.045] [--front-y 0.0] [--scale 0.07]
      [--tex refs/outfit_male_victorian/jacket/prepped/lapel_texture.png] [--glb shells/coat.glb] [--out shells/coat.glb]

Lapel = cloth faces whose centre lies within --w of the coat's open front edge (boundary edges, found by position:
the glTF stays split along UV seams) between the --z heights, in front of --front-y. UVs: (x, z) / --scale.
"""
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils.kdtree import KDTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_victorian")
PIECE = opt("--piece", "coat")
D = ROOT / "out" / f"{CHAR}-goose"
GLB = D / opt("--glb", f"shells/{PIECE}.glb")
OUT = D / opt("--out", f"shells/{PIECE}.glb")
Z0, Z1 = (float(z) for z in opt("--z", "0.99,1.27").split(","))
W, FY, SCALE = opt("--w", 0.045), opt("--front-y", 0.0), opt("--scale", 0.07)
W_TOP = opt("--w-top", W)        # lapel width at --z top (linear from --w at the break): wide, pointed lapels
TEX = ROOT / opt("--tex", "refs/outfit_male_victorian/jacket/prepped/lapel_texture.png")

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
gar = next(o for o in bpy.data.objects if o.type == "MESH")
bpy.ops.object.select_all(action="DESELECT")
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = gar.data
bm = bmesh.new()
bm.from_mesh(me)


def key(v):
    return tuple(np.round(np.array(v.co[:]), 5))


cand = [e for e in bm.edges if len([f for f in e.link_faces if f.material_index == 0]) == 1]
count = {}
for e in cand:
    k_ = frozenset((key(e.verts[0]), key(e.verts[1])))
    count[k_] = count.get(k_, 0) + 1
edge_pts = []
for e in cand:
    a, b = np.array(key(e.verts[0])), np.array(key(e.verts[1]))
    if count[frozenset((tuple(a), tuple(b)))] != 1:
        continue
    for t in np.linspace(0, 1, 5):
        p = a * (1 - t) + b * t
        if Z0 <= p[2] <= Z1 and p[1] < FY:
            edge_pts.append(p)
kd = KDTree(len(edge_pts))
for i, p in enumerate(edge_pts):
    kd.insert(p, i)
kd.balance()
mat = bpy.data.materials.new(f"{CHAR}_{PIECE}_lapel")
mat.use_nodes = True
nt = mat.node_tree
bs = nt.nodes["Principled BSDF"]
bs.inputs["Roughness"].default_value = 0.6
tx = nt.nodes.new("ShaderNodeTexImage")
tx.image = bpy.data.images.load(str(TEX))
tx.image.pack()
tx.extension = "REPEAT"
nt.links.new(tx.outputs["Color"], bs.inputs["Base Color"])
me.materials.append(mat)
li = len(me.materials) - 1
uvl = bm.loops.layers.uv.active


def field(co):
    """< 0 inside the lapel: distance to the front edge minus the lapel width there (and only in the band)."""
    c = np.array(co[:])
    if not (Z0 - 0.01 <= c[2] <= Z1 + 0.01) or c[1] > FY:
        return 1.0
    t = np.clip((c[2] - Z0) / max(Z1 - Z0, 1e-6), 0, 1)
    return kd.find(c)[2] - (W + (W_TOP - W) * t)


# exact outline: split each cloth edge where the field changes sign, connect the split points across each face
cloth_f = [f for f in bm.faces if f.material_index == 0]
fv = {v: field(v.co) for f in cloth_f for v in f.verts}
newv = set()
for e in list({e for f in cloth_f for e in f.edges}):
    a_, b_ = e.verts
    da, db = fv.get(a_, 1.0), fv.get(b_, 1.0)
    if da * db < 0:
        t = da / (da - db)
        if 0.02 < t < 0.98:
            ne, nv_ = bmesh.utils.edge_split(e, a_, t)
            fv[nv_] = 0.0
            newv.add(nv_)
for f in [f for f in bm.faces if f.material_index == 0]:
    vs = [v for v in f.verts if v in newv]
    if len(vs) == 2 and vs[1] not in [e.other_vert(vs[0]) for e in vs[0].link_edges]:
        try:
            bmesh.ops.connect_verts(bm, verts=vs)
        except Exception:
            pass
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
n = 0
for f in bm.faces:
    if f.material_index != 0:
        continue
    if max(fv.get(v, field(v.co)) for v in f.verts) > 1e-6:
        continue
    f.material_index = li
    for lp in f.loops:
        p = lp.vert.co
        lp[uvl].uv = (p.x / SCALE, p.z / SCALE)
    n += 1
bm.to_mesh(me)
bm.free()
me.update()
bpy.ops.export_scene.gltf(filepath=str(OUT), export_format="GLB", use_selection=True, export_tangents=True)
print("LAPELS", PIECE, n, "faces", "edge points", len(edge_pts))
