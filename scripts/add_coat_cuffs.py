"""Modelled turn-back cuffs on a coat's sleeves, wrapped in the drawing's cuff brocade: a raised band at each sleeve
end (the projected embroidery broke into scraps where the built sleeve and the drawn one differ in length), gold
piping along its top edge, a burgundy rim at the bottom.

  blender -b --factory-startup --python scripts/add_coat_cuffs.py -- [--piece coat] [--char outfit_male_victorian]
      [--h 0.055] [--ease 0.004] [--tex refs/outfit_male_victorian/jacket/prepped/cuff_texture.png] [--repeat 2]
      [--glb shells/coat.glb] [--out shells/coat.glb]

Per arm: the sleeve end = the farthest point of the coat along the forearm axis (ForeArm -> Hand joints) near that
hand; rings around the axis from the end up --h; each ring's radius per angle = the coat under it (ray from the axis)
+ --ease, so the band follows the sleeve. UV u = angle (x --repeat round the cuff), v = height: the texture (a
seamless strip, mirrored copy of the drawing's cuff band) wraps it.
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
CHAR = opt("--char", "outfit_male_victorian")
PIECE = opt("--piece", "coat")
D = ROOT / "out" / f"{CHAR}-goose"
GLB = D / opt("--glb", f"shells/{PIECE}.glb")
OUT = D / opt("--out", f"shells/{PIECE}.glb")
HC, EASE, REP = opt("--h", 0.055), opt("--ease", 0.004), opt("--repeat", 2.0)
TEX = ROOT / opt("--tex", "refs/outfit_male_victorian/jacket/prepped/cuff_texture.png")
J = {k: np.array(v["head"]) for k, v in json.loads((ROOT / "refs" / "key_views" / "joints.json").read_text(encoding="utf-8")).items()}
NA, NR = 48, 8


def lin(c):
    c = np.array(c) / 255.0
    return tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
gar = next(o for o in bpy.data.objects if o.type == "MESH")
M = gar.matrix_world
cloth_polys = [p for p in gar.data.polygons if p.material_index == 0]
V = [M @ v.co for v in gar.data.vertices]
GB = BVHTree.FromPolygons(V, [tuple(p.vertices) for p in cloth_polys])
VP = np.array([v[:] for v in V])
# --over gloves[,..]: the cuff also clears these shells (the glove's gauntlet cuff tucks up inside it)
OVERS = []
for nm in [x for x in opt("--over", "").split(",") if x]:
    seen = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(D / "shells" / f"{nm}.glb"))
    for o_ in [o_ for o_ in bpy.data.objects if o_ not in seen and o_.type == "MESH"]:
        Mo = o_.matrix_world
        OVERS.append(BVHTree.FromPolygons([Mo @ v.co for v in o_.data.vertices], [tuple(p.vertices) for p in o_.data.polygons]))
        bpy.data.objects.remove(o_)
bm = bmesh.new()
uvl = bm.loops.layers.uv.new("UVMap")
pipes = []
for side in ("Left", "Right"):
    e, w = J[f"{side}ForeArm"], J[f"{side}Hand"]
    ax = (w - e) / np.linalg.norm(w - e)                # toward the hand
    near = VP[np.linalg.norm(VP - w, axis=1) < 0.12]
    t_end = float(((near - e) @ ax).max())             # sleeve end along the axis
    ref = np.array([0, -1.0, 0]) - ax * (-ax[1])
    ref /= np.linalg.norm(ref)
    sv = np.cross(ax, ref)
    rings = []
    for k in range(NR):
        t = t_end - 0.003 - HC * k / (NR - 1)
        c = e + ax * t
        ring = []
        for i in range(NA + 1):                         # (seam column duplicated for the UV wrap)
            a = 2 * math.pi * (i % NA) / NA
            d = math.cos(a) * ref + math.sin(a) * sv
            h = GB.ray_cast(Vector(c + d * 0.15), Vector(-d), 0.15)
            r = (0.15 - h[3]) if h[0] is not None else 0.04
            for ob_ in OVERS:
                ho = ob_.ray_cast(Vector(c + d * 0.15), Vector(-d), 0.15)
                if ho[0] is not None and (0.15 - ho[3]) < 0.1:
                    r = max(r, 0.15 - ho[3])
            ring.append((c + d * (r + EASE), (i / NA * REP, k / (NR - 1))))
        rings.append(ring)
    vs = [[bm.verts.new(p) for p, _ in ring] for ring in rings]
    for k in range(NR - 1):
        for i in range(NA):
            q = (vs[k][i], vs[k][i + 1], vs[k + 1][i + 1], vs[k + 1][i])
            uvs = (rings[k][i][1], rings[k][i + 1][1], rings[k + 1][i + 1][1], rings[k + 1][i][1])
            f = bm.faces.new(q)
            for lp, uv in zip(f.loops, uvs):
                lp[uvl].uv = uv
    for k, mat in ((NR - 1, 2), (0, 3)):                # gold piping on top, burgundy rim at the end
        pipes.append(([np.array(p) for p, _ in rings[k][:NA]], ax, mat))
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
for f in bm.faces:
    f.material_index = 0
NS = 8
for ring, ax, mat in pipes:
    rad = 0.0024 if mat == 2 else 0.0035
    rs = []
    N = len(ring)
    for i in range(N):
        tng = ring[(i + 1) % N] - ring[i - 1]
        tng /= np.linalg.norm(tng) + 1e-9
        u = np.cross(tng, ax)
        u /= np.linalg.norm(u) + 1e-9
        c = ring[i]
        rs.append([bm.verts.new(c + rad * (math.cos(2 * math.pi * k / NS) * u + math.sin(2 * math.pi * k / NS) * ax))
                   for k in range(NS)])
    for i in range(N):
        for k in range(NS):
            f = bm.faces.new((rs[i][k], rs[i][(k + 1) % NS], rs[(i + 1) % N][(k + 1) % NS], rs[(i + 1) % N][k]))
            f.material_index = 1 if mat == 2 else 2
me = bpy.data.meshes.new("coat_cuffs")
bm.to_mesh(me)
bm.free()
for p in me.polygons:
    p.use_smooth = True
co = bpy.data.objects.new("coat_cuffs", me)
bpy.context.scene.collection.objects.link(co)
m0 = bpy.data.materials.new(f"{CHAR}_{PIECE}_cuff")
m0.use_nodes = True
nt = m0.node_tree
bs = nt.nodes["Principled BSDF"]
bs.inputs["Roughness"].default_value = 0.6
tx = nt.nodes.new("ShaderNodeTexImage")
tx.image = bpy.data.images.load(str(TEX))
tx.image.pack()
nt.links.new(tx.outputs["Color"], bs.inputs["Base Color"])
m1 = bpy.data.materials.new(f"{CHAR}_{PIECE}_cuff_piping")
m1.use_nodes = True
b1 = m1.node_tree.nodes["Principled BSDF"]
b1.inputs["Base Color"].default_value = lin([196, 146, 62])
b1.inputs["Metallic"].default_value = 0.85
b1.inputs["Roughness"].default_value = 0.35
m2 = bpy.data.materials.new(f"{CHAR}_{PIECE}_cuff_rim")
m2.use_nodes = True
b2 = m2.node_tree.nodes["Principled BSDF"]
b2.inputs["Base Color"].default_value = lin([92, 30, 34])
b2.inputs["Roughness"].default_value = 0.85
for m in (m0, m1, m2):
    me.materials.append(m)
bpy.ops.object.select_all(action="DESELECT")
co.select_set(True)
bpy.context.view_layer.objects.active = co
sol = co.modifiers.new("sol", "SOLIDIFY")
sol.thickness = 0.002
sol.offset = -1.0
bpy.ops.object.modifier_apply(modifier=sol.name)
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.object.join()
bpy.ops.export_scene.gltf(filepath=str(OUT), export_format="GLB", use_selection=True, export_tangents=True)
print("COAT CUFFS", PIECE, "height", HC)
