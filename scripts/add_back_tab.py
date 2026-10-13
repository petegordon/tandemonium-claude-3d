"""Half-belt tab across the back waist of a coat (the drawing's rear view: a burgundy tab, gold-piped, carrying the two
back buttons) -- a strip following the coat's back, a little proud of it, with piping round its edge and two domed
brass buttons.

  blender -b --factory-startup --python scripts/add_back_tab.py -- [--piece coat] [--char outfit_male_victorian]
      [--x 0.11] [--z 0.975,1.015] [--buttons 0.065] [--button-r 0.011] [--color 90,28,32]
      [--glb shells/coat.glb] [--out shells/coat.glb]

The strip spans |x| < --x between the --z heights; each point is the coat's back surface seen from behind (+y), 3 mm
out along its normal; solidified 3 mm. Piping r 2.2 mm round the outline; buttons at x = +-(--buttons), mid-height.
"""
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_victorian")
PIECE = opt("--piece", "coat")
D = ROOT / "out" / f"{CHAR}-goose"
GLB = D / opt("--glb", f"shells/{PIECE}.glb")
OUT = D / opt("--out", f"shells/{PIECE}.glb")
XW = opt("--x", 0.11)
Z0, Z1 = (float(z) for z in opt("--z", "0.975,1.015").split(","))
BX, BR = opt("--buttons", 0.065), opt("--button-r", 0.011)
COL = [int(c) for c in opt("--color", "90,28,32").split(",")]
NX, NZ = 40, 5


def lin(c):
    c = np.array(c) / 255.0
    return tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
gar = next(o for o in bpy.data.objects if o.type == "MESH")
M = gar.matrix_world
cloth = [p for p in gar.data.polygons if p.material_index == 0]
GB = BVHTree.FromPolygons([M @ v.co for v in gar.data.vertices], [tuple(p.vertices) for p in cloth])


def back_point(x, z):
    h = GB.ray_cast(Vector((x, 0.6, z)), Vector((0, -1, 0)), 1.0)
    if h[0] is None:
        return None, None
    n = np.array(h[1][:])
    if n[1] < 0:
        n = -n
    return np.array(h[0][:]), n


grid = [[back_point(x, z) for z in np.linspace(Z0, Z1, NZ)] for x in np.linspace(-XW, XW, NX)]
bm = bmesh.new()
vs = [[bm.verts.new(p + n * 0.003) if p is not None else None for p, n in col] for col in grid]
for i in range(NX - 1):
    for j in range(NZ - 1):
        q = (vs[i][j], vs[i + 1][j], vs[i + 1][j + 1], vs[i][j + 1])
        if all(q):
            bm.faces.new(q)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
tme = bpy.data.meshes.new("back_tab")
bm.to_mesh(tme)
bm.free()
tab = bpy.data.objects.new("back_tab", tme)
bpy.context.scene.collection.objects.link(tab)
m0 = bpy.data.materials.new(f"{CHAR}_{PIECE}_back_tab")
m0.use_nodes = True
b0 = m0.node_tree.nodes["Principled BSDF"]
b0.inputs["Base Color"].default_value = lin(COL)
b0.inputs["Roughness"].default_value = 0.85
tme.materials.append(m0)
bpy.ops.object.select_all(action="DESELECT")
tab.select_set(True)
bpy.context.view_layer.objects.active = tab
sol = tab.modifiers.new("sol", "SOLIDIFY")
sol.thickness = 0.003
sol.offset = -1.0
bpy.ops.object.modifier_apply(modifier=sol.name)
for p in tme.polygons:
    p.use_smooth = True
# piping round the outline + the two buttons
pb = bmesh.new()
outline = [grid[i][0] for i in range(NX)] + [grid[NX - 1][j] for j in range(1, NZ)] + \
          [grid[i][NZ - 1] for i in range(NX - 2, -1, -1)] + [grid[0][j] for j in range(NZ - 2, 0, -1)]
outline = [(p + n * 0.0045) for p, n in outline if p is not None]
NS, PR = 8, 0.0022
rings = []
N = len(outline)
for i in range(N):
    t = outline[(i + 1) % N] - outline[i - 1]
    t /= np.linalg.norm(t) + 1e-9
    u = np.cross(t, [0, 1.0, 0])
    u /= np.linalg.norm(u) + 1e-9
    w = np.cross(u, t)
    rings.append([pb.verts.new(outline[i] + PR * (math.cos(2 * math.pi * k / NS) * u + math.sin(2 * math.pi * k / NS) * w))
                  for k in range(NS)])
for i in range(N):
    for k in range(NS):
        pb.faces.new((rings[i][k], rings[i][(k + 1) % NS], rings[(i + 1) % N][(k + 1) % NS], rings[(i + 1) % N][k]))
for i in range(len(pb.faces)):
    pass
pme = bpy.data.meshes.new("tab_piping")
pb.to_mesh(pme)
pb.free()
bb = bmesh.new()
for sx in (1, -1):
    p, n = back_point(sx * BX, (Z0 + Z1) / 2)
    g = bmesh.ops.create_uvsphere(bb, u_segments=16, v_segments=10, radius=1.0)
    rot = Vector((0, 0, 1)).rotation_difference(Vector(n)).to_matrix().to_4x4()
    bmesh.ops.transform(bb, matrix=Matrix.Translation(Vector(p + n * 0.0065)) @ rot @ Matrix.Diagonal((BR, BR, BR * 0.5, 1.0)),
                        verts=g["verts"])
bme = bpy.data.meshes.new("tab_buttons")
bb.to_mesh(bme)
bb.free()
gold = bpy.data.materials.new(f"{CHAR}_{PIECE}_tab_gold")
gold.use_nodes = True
bg = gold.node_tree.nodes["Principled BSDF"]
bg.inputs["Base Color"].default_value = lin([196, 146, 62])
bg.inputs["Metallic"].default_value = 0.9
bg.inputs["Roughness"].default_value = 0.3
objs = []
for nm, me_ in (("tab_piping", pme), ("tab_buttons", bme)):
    me_.materials.append(gold)
    for p in me_.polygons:
        p.use_smooth = True
    o = bpy.data.objects.new(nm, me_)
    bpy.context.scene.collection.objects.link(o)
    objs.append(o)
bpy.ops.object.select_all(action="DESELECT")
for o in [tab] + objs + [gar]:
    o.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.object.join()
bpy.ops.export_scene.gltf(filepath=str(OUT), export_format="GLB", use_selection=True, export_tangents=True)
print("BACK TAB", PIECE, "outline", N)
