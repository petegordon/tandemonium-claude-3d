"""Cream lace frills at the bodice sleeve ends (female outfit, refs/v3).

  blender -b --factory-startup --python scripts/make_cuffs.py -- --char outfit_female [--from bodice]

Finds the sleeve-end boundary loops of shells/<from>.glb, and on each builds a short flared frill: from the
loop (tucked 4 mm inside the sleeve) out along the forearm axis toward the hand, flaring, with a scalloped,
gently waved edge. One cream material. Writes shells/cuffs.glb + .json (dress_goose.py skins it like the
other modelled pieces).
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]


def opt(name, default):
    return argv[argv.index(name) + 1] if name in argv else default


CHAR = opt("--char", "outfit_female")
SRC = opt("--from", "bodice")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / f"{CHAR}-goose" / "shells"
C = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8")).get("cuff_design", {})

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(OUT / f"{SRC}.glb"))
src = next(o for o in bpy.context.scene.objects if o.type == "MESH")
bm0 = bmesh.new()
bm0.from_mesh(src.data)
bmesh.ops.remove_doubles(bm0, verts=bm0.verts[:], dist=1e-5)
bnd = [e for e in bm0.edges if e.is_boundary]
loops, used = [], set()
for e in bnd:
    if e in used:
        continue
    st, lp = [e], set([e])
    used.add(e)
    while st:
        x = st.pop()
        for v in x.verts:
            for y in v.link_edges:
                if y.is_boundary and y not in used:
                    used.add(y)
                    lp.add(y)
                    st.append(y)
    vs = {v for ed in lp for v in ed.verts}
    P = np.array([src.matrix_world @ v.co for v in vs])
    if abs(P[:, 0].mean()) > 0.25:
        loops.append(P)
print("SLEEVE ENDS", [len(p) for p in loops])
bm = bmesh.new()
NA, NU = C.get("na", 36), C.get("nu", 5)
for P in loops:
    c0 = P.mean(0)
    _, _, VT = np.linalg.svd(P - c0)
    ax = VT[2]
    if ax[2] > 0:                                   # point down the arm (toward the hand)
        ax = -ax
    u1 = VT[0]
    u2 = np.cross(ax, u1)
    rel = P - c0
    r0 = float(np.median(np.linalg.norm(rel - np.outer(rel @ ax, ax), axis=1)))
    L, flare = C.get("length", 0.02), C.get("flare", 1.3)
    grid = []
    for i in range(NA):
        a = 2 * math.pi * i / NA
        d = u1 * math.cos(a) + u2 * math.sin(a)
        row = []
        for j, t in enumerate(np.linspace(0, 1, NU)):
            scal = C.get("scallop", 0.004) * (0.5 + 0.5 * math.cos(a * C.get("n_sc", 12))) * (t ** 2)
            wave = C.get("wave", 0.003) * math.sin(a * C.get("n_wave", 18)) * t
            rr = r0 * (1 - 0.06 + (flare - 1 + 0.06) * t ** 1.5) + wave
            row.append(c0 - ax * 0.004 + ax * (L * t + scal) + d * rr)
        grid.append([bm.verts.new(tuple(p)) for p in row])
    for i in range(NA):
        i2 = (i + 1) % NA
        for j in range(NU - 1):
            bm.faces.new([grid[i][j], grid[i2][j], grid[i2][j + 1], grid[i][j + 1]])
bpy.data.objects.remove(src)
me = bpy.data.meshes.new("cuffs_shell")
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bm.to_mesh(me)
bm.free()
o = bpy.data.objects.new("cuffs_shell", me)
bpy.context.scene.collection.objects.link(o)
m = bpy.data.materials.new(f"{CHAR}_cuffs_lace")
m.use_nodes = True
col = np.array(C.get("color", [232, 216, 192])) / 255.0
lin = np.where(col > 0.04045, ((col + 0.055) / 1.055) ** 2.4, col / 12.92)
m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = tuple(lin) + (1.0,)
m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8
m.use_backface_culling = False
me.materials.append(m)
bpy.context.view_layer.objects.active = o
o.select_set(True)
bpy.ops.object.shade_smooth()
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.01)
bpy.ops.object.mode_set(mode="OBJECT")
tris = sum(len(p.vertices) - 2 for p in me.polygons)
bpy.ops.export_scene.gltf(filepath=str(OUT / "cuffs.glb"), use_selection=True, export_format="GLB")
(OUT / "cuffs.json").write_text(json.dumps({"char": CHAR, "piece": "cuffs", "tris": tris, "source": "make_cuffs.py (modelled)"}, indent=1),
                                encoding="utf-8")
print("SHELL cuffs", tris)
