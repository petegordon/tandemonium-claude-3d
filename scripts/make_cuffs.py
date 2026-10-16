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
NAME = opt("--name", "cuffs")          # a second frill (e.g. lace under a silk flounce): --name lace, recipe "lace_design"
C = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8")).get("cuff_design" if NAME == "cuffs" else f"{NAME}_design", {})

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
for P, tier in [(P_, k_) for P_ in loops for k_ in range(C.get("tiers", 1))]:
    c0 = P.mean(0)
    _, _, VT = np.linalg.svd(P - c0)
    ax = VT[2]
    if ax[2] > 0:                                   # point down the arm (toward the hand)
        ax = -ax
    u1 = VT[0]
    u2 = np.cross(ax, u1)
    rel = P - c0
    r0 = float(np.median(np.linalg.norm(rel - np.outer(rel @ ax, ax), axis=1)))
    L, flare = C.get("length", 0.02) * (1 - 0.2 * tier), C.get("flare", 1.3) * (1 - 0.08 * tier)
    c0 = c0 - ax * C.get("tier_step", 0.02) * tier
    grid = []
    for i in range(NA):
        a = 2 * math.pi * i / NA
        d = u1 * math.cos(a) + u2 * math.sin(a)
        row = []
        for j, t in enumerate(np.linspace(0, 1, NU)):
            scal = C.get("scallop", 0.004) * (0.5 + 0.5 * math.cos(a * C.get("n_sc", 12))) * (t ** 2)
            wave = C.get("wave", 0.003) * math.sin(a * C.get("n_wave", 18)) * t
            rr = r0 * (1 - 0.06 + (flare - 1 + 0.06) * t ** 1.5) + wave
            row.append(c0 - ax * C.get("tuck", 0.004) + ax * (L * t + scal) + d * rr)
        grid.append([bm.verts.new(tuple(p)) for p in row])
    for i in range(NA):
        i2 = (i + 1) % NA
        for j in range(NU - 1):
            bm.faces.new([grid[i][j], grid[i2][j], grid[i2][j + 1], grid[i][j + 1]])
bpy.data.objects.remove(src)
me = bpy.data.meshes.new(f"{NAME}_shell")
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bm.to_mesh(me)
bm.free()
o = bpy.data.objects.new(f"{NAME}_shell", me)
bpy.context.scene.collection.objects.link(o)
m = bpy.data.materials.new(f"{CHAR}_{NAME}_lace")
m.use_nodes = True
col = np.array(C.get("color", [232, 216, 192])) / 255.0
lin = np.where(col > 0.04045, ((col + 0.055) / 1.055) ** 2.4, col / 12.92)
m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = tuple(lin) + (1.0,)
if C.get("lace_tex"):                      # lace: a net of small holes, flower motifs and eyelets painted in
    W_ = 512
    yy, xx = np.mgrid[0:W_, 0:W_] / W_
    tx = np.ones((W_, W_, 3)) * col
    net = (np.sin(xx * 2 * np.pi * 90) * np.sin(yy * 2 * np.pi * 90)) > 0.5
    tx[net] *= 0.8
    fl_ = np.hypot((xx * 16) % 1 - 0.5, (yy * 12) % 1 - 0.5)
    tx[(fl_ < 0.2) & (fl_ > 0.11)] *= 0.7
    tx[fl_ < 0.05] *= 0.75
    im_ = bpy.data.images.new(f"{CHAR}_{NAME}_lace_tex", W_, W_, alpha=False)
    im_.pixels = np.concatenate([tx[::-1], np.ones((W_, W_, 1))], -1).ravel().tolist()
    im_.pack()
    tn_ = m.node_tree.nodes.new("ShaderNodeTexImage")
    tn_.image = im_
    m.node_tree.links.new(tn_.outputs["Color"], m.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
m.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.8
m.use_backface_culling = False
me.materials.append(m)
bpy.context.view_layer.objects.active = o
o.select_set(True)
if C.get("thick"):                       # a solid frill (opaque, no see-through paper look)
    sol = o.modifiers.new("sol", "SOLIDIFY")
    sol.thickness = C["thick"]
    sol.offset = 0.0
    bpy.ops.object.modifier_apply(modifier="sol")
bpy.ops.object.shade_smooth()
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.01)
bpy.ops.object.mode_set(mode="OBJECT")
tris = sum(len(p.vertices) - 2 for p in me.polygons)
bpy.ops.export_scene.gltf(filepath=str(OUT / f"{NAME}.glb"), use_selection=True, export_format="GLB")
(OUT / f"{NAME}.json").write_text(json.dumps({"char": CHAR, "piece": NAME, "tris": tris, "source": "make_cuffs.py (modelled)"}, indent=1),
                                encoding="utf-8")
print("SHELL", NAME, tris)
