"""Gold piping along a garment shell's open edges (the jacket's front edges, hem, tails and vent): a round cord
following each boundary loop of the cloth faces, joined into the shell in its own metallic material.

  blender -b --factory-startup --python scripts/add_piping.py -- --piece coat [--char outfit_male_victorian]
      [--r 0.0024] [--color 196,146,62] [--zmin -9] [--zmax 1.2] [--min-len 0.08] [--skip-cuffs]
      [--glb shells/coat.glb] [--out shells/coat.glb]

Boundary edges of the first material's faces only (run before add_lining.py, whose copy has its own boundaries).
An edge is piped when its midpoint lies between --zmin and --zmax (default: everything below the neckline); chains
shorter than --min-len are dropped (slivers). --skip-cuffs leaves the sleeve ends bare (edges near a wrist joint).
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_victorian")
PIECE = opt("--piece", "coat")
D = ROOT / "out" / f"{CHAR}-goose"
GLB = D / opt("--glb", f"shells/{PIECE}.glb")
OUT = D / opt("--out", f"shells/{PIECE}.glb")
RAD, ZMIN, ZMAX, MINLEN = opt("--r", 0.0024), opt("--zmin", -9.0), opt("--zmax", 1.2), opt("--min-len", 0.08)
COL = [int(x) for x in opt("--color", "196,146,62").split(",")]
J = json.loads((ROOT / "refs" / "key_views" / "joints.json").read_text(encoding="utf-8"))
WRISTS = [np.array(J[k]["head"]) for k in ("LeftHand", "RightHand")]
NSEG = 8

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB), merge_vertices=True)
gar = next(o for o in bpy.data.objects if o.type == "MESH")
M = gar.matrix_world
bm = bmesh.new()
bm.from_mesh(gar.data)
bm.normal_update()
# boundary by POSITION: the glTF mesh stays split along UV seams, so a seam edge is "open" in the topology but has
# a twin at the same place; a true boundary edge's position pair occurs once
def key(v):
    return tuple(np.round(np.array((M @ v.co)[:]), 5))


cand = [e for e in bm.edges if len([f for f in e.link_faces if f.material_index == 0]) == 1]
count = {}
for e in cand:
    k_ = frozenset((key(e.verts[0]), key(e.verts[1])))
    count[k_] = count.get(k_, 0) + 1
pos, nrm_of = {}, {}
adj = {}
n_edges = 0
for e in cand:
    a, b = key(e.verts[0]), key(e.verts[1])
    if count[frozenset((a, b))] != 1:
        continue
    mid = (np.array(a) + np.array(b)) / 2
    if not (ZMIN < mid[2] < ZMAX):
        continue
    if "--skip-cuffs" in argv and min(np.linalg.norm(mid - w) for w in WRISTS) < 0.09:
        continue
    for v in e.verts:
        pos[key(v)] = np.array(key(v))
        nrm_of.setdefault(key(v), []).append(np.array((M.to_3x3() @ v.normal)[:]))
    adj.setdefault(a, []).append(b)
    adj.setdefault(b, []).append(a)
    n_edges += 1
seen_e = set()
chains = []
for start in list(adj):
    for nb in adj[start]:
        if frozenset((start, nb)) in seen_e:
            continue
        chain = [start, nb]
        seen_e.add(frozenset((start, nb)))
        while True:
            cur, prev = chain[-1], chain[-2]
            nxt = [n for n in adj[cur] if n != prev and frozenset((cur, n)) not in seen_e]
            if not nxt:
                break
            seen_e.add(frozenset((cur, nxt[0])))
            chain.append(nxt[0])
            if nxt[0] == chain[0]:
                break
        chains.append(chain)
pb = bmesh.new()
n_pipe = 0
for ch in chains:
    pts = [pos[k_] for k_ in ch]
    nrm = []
    for k_ in ch:
        n_ = np.mean(nrm_of[k_], 0)
        nrm.append(n_ / (np.linalg.norm(n_) + 1e-12))
    L = sum(np.linalg.norm(pts[i + 1] - pts[i]) for i in range(len(pts) - 1))
    if L < MINLEN:
        continue
    rings = []
    for i, (p, n) in enumerate(zip(pts, nrm)):
        t = pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]
        t /= np.linalg.norm(t) + 1e-12
        u = np.cross(t, n)
        u /= np.linalg.norm(u) + 1e-12
        w = np.cross(u, t)
        c = p + n * RAD * 0.6                       # sits on the edge, a little proud of the cloth
        rings.append([pb.verts.new(c + RAD * (math.cos(2 * math.pi * k / NSEG) * u + math.sin(2 * math.pi * k / NSEG) * w))
                      for k in range(NSEG)])
    for i in range(len(rings) - 1):
        for k in range(NSEG):
            pb.faces.new((rings[i][k], rings[i][(k + 1) % NSEG], rings[i + 1][(k + 1) % NSEG], rings[i + 1][k]))
    n_pipe += 1
bm.free()
pm = bpy.data.meshes.new("piping")
pb.to_mesh(pm)
pb.free()
for p in pm.polygons:
    p.use_smooth = True
po = bpy.data.objects.new("piping", pm)
bpy.context.scene.collection.objects.link(po)
mat = bpy.data.materials.new(f"{CHAR}_{PIECE}_piping")
mat.use_nodes = True
bs = mat.node_tree.nodes["Principled BSDF"]
c = np.array(COL) / 255.0
bs.inputs["Base Color"].default_value = tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)
bs.inputs["Metallic"].default_value = 0.85
bs.inputs["Roughness"].default_value = 0.35
pm.materials.append(mat)
bpy.ops.object.select_all(action="DESELECT")
po.select_set(True)
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.object.join()
bpy.ops.export_scene.gltf(filepath=str(OUT), export_format="GLB", use_selection=True, export_tangents=True)
print("PIPING", PIECE, n_pipe, "chains of", len(chains), "edges", n_edges)
