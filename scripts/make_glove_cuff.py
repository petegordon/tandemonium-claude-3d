"""Add Pete's cream turn-back cuffs (with a brass button) to the built gloves.

  blender -b --factory-startup --python scripts/make_glove_cuff.py -- [--char outfit_male_victorian]
      [--height 0.03] [--below 0.006] [--ease 0.004] [--flare 0.004] [--button-r 0.0065] [--glb shells/gloves.glb]

Per hand: rings around the forearm axis (ForeArm -> Hand joints) from --below past the wrist joint up --height toward
the elbow; each ring's radius per angle = the glove (or, above it, the forearm body) under it + --ease, flaring by
--flare at the top; solidified 2.5 mm; cream cloth (fine weave bump) as its own material; one domed brass button on the
outer side, mid-band. Joined into the gloves shell (gloves material first, so nothing re-colours the cuff).
"""
import json
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
D = ROOT / "out" / f"{CHAR}-goose"
GLB = D / opt("--glb", "shells/gloves.glb")
HT, BELOW, EASE, FLARE = opt("--height", 0.03), opt("--below", 0.006), opt("--ease", 0.004), opt("--flare", 0.004)
BR = opt("--button-r", 0.0065)       # brass button radius
BFRONT = opt("--button-front", 0.0)  # 0: on the outer side; 1: halfway round to the front
JS = json.loads((ROOT / "refs" / "key_views" / "joints.json").read_text(encoding="utf-8"))
J = {k: np.array(v["head"]) for k, v in JS.items()}
NA, NR = 48, 7

bpy.ops.wm.read_factory_settings(use_empty=True)
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(GLB))
glo = next(o for o in bpy.data.objects if o not in before and o.type == "MESH")
bpy.ops.object.select_all(action="DESELECT")
glo.select_set(True)
bpy.context.view_layer.objects.active = glo
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
GB = BVHTree.FromPolygons([v.co.copy() for v in glo.data.vertices], [tuple(p.vertices) for p in glo.data.polygons])
with bpy.data.libraries.load(str(ROOT / "out" / "base-goose" / "base_goose.blend")) as (src, dst):
    dst.objects = ["base_goose_game"]
body = dst.objects[0]
BB = BVHTree.FromPolygons([v.co.copy() for v in body.data.vertices], [tuple(p.vertices) for p in body.data.polygons])

bm = bmesh.new()
buttons = []
for side, sx in (("Left", 1), ("Right", -1)):
    w = J[f"{side}Hand"]
    e = J[f"{side}ForeArm"]
    up = (e - w) / np.linalg.norm(e - w)                 # toward the elbow
    ref = np.array([0, -1.0, 0]) - up * (-up[1])
    ref /= np.linalg.norm(ref)
    side_v = np.cross(up, ref)
    rings = []
    for k in range(NR):
        t = -BELOW + (HT + BELOW) * k / (NR - 1)
        c = w + up * t
        ring = []
        for a in np.linspace(0, 2 * math.pi, NA, endpoint=False):
            d = math.cos(a) * ref + math.sin(a) * side_v
            o = Vector(c + d * 0.12)
            h = GB.ray_cast(o, Vector(-d), 0.12)          # the glove's outer surface along this direction
            if h[0] is None:
                h = BB.ray_cast(o, Vector(-d), 0.12)      # above the glove: the forearm
            r = (0.12 - h[3]) if h[0] is not None else 0.03
            r += EASE + FLARE * (k / (NR - 1)) ** 2
            ring.append(bm.verts.new(tuple(c + d * r)))
        rings.append(ring)
    for r0, r1 in zip(rings[:-1], rings[1:]):
        for i in range(NA):
            bm.faces.new((r0[i], r0[(i + 1) % NA], r1[(i + 1) % NA], r1[i]))
    # button: outer side (away from the body, +x for the left hand), mid-band
    out_dir = np.array([sx * 1.0, -BFRONT, 0])          # outer side, turned toward the front (ref)
    out_dir = out_dir - up * (up @ out_dir)
    out_dir /= np.linalg.norm(out_dir)
    c = w + up * (HT / 2 - BELOW / 2)
    h = GB.ray_cast(Vector(c + out_dir * 0.12), Vector(-out_dir), 0.12)
    r = (0.12 - h[3] if h[0] is not None else 0.03) + EASE + 0.004
    buttons.append((c + out_dir * r, out_dir))
me = bpy.data.meshes.new("cuffs")
bm.to_mesh(me)
bm.free()
cuff = bpy.data.objects.new("cuffs", me)
bpy.context.scene.collection.objects.link(cuff)
sol = cuff.modifiers.new("sol", "SOLIDIFY")
sol.thickness = 0.0025
sol.offset = -1.0
bpy.context.view_layer.objects.active = cuff
bpy.ops.object.select_all(action="DESELECT")
cuff.select_set(True)
bpy.ops.object.modifier_apply(modifier=sol.name)
for p in me.polygons:
    p.use_smooth = True
cm = bpy.data.materials.new("gloves_cuff_cream")
cm.use_nodes = True
nt = cm.node_tree
bs = nt.nodes["Principled BSDF"]
bs.inputs["Base Color"].default_value = (0.62, 0.50, 0.33, 1)     # cream (linear; the old value rendered white)
bs.inputs["Roughness"].default_value = 0.75
wv = nt.nodes.new("ShaderNodeTexWave")
wv.inputs["Scale"].default_value = 400.0
bump = nt.nodes.new("ShaderNodeBump")
bump.inputs["Strength"].default_value = 0.05
nt.links.new(wv.outputs["Fac"], bump.inputs["Height"])
nt.links.new(bump.outputs["Normal"], bs.inputs["Normal"])
me.materials.append(cm)
bmb = bmesh.new()
for p, n in buttons:
    g = bmesh.ops.create_uvsphere(bmb, u_segments=12, v_segments=8, radius=1.0)
    rot = Vector((0, 0, 1)).rotation_difference(Vector(n)).to_matrix().to_4x4()
    M = Matrix.Translation(Vector(p)) @ rot @ Matrix.Diagonal((BR, BR, BR * 0.45, 1.0))
    bmesh.ops.transform(bmb, matrix=M, verts=g["verts"])
bme = bpy.data.meshes.new("cuff_buttons")
bmb.to_mesh(bme)
bmb.free()
bo = bpy.data.objects.new("cuff_buttons", bme)
bpy.context.scene.collection.objects.link(bo)
for p in bme.polygons:
    p.use_smooth = True
brass = bpy.data.materials.new("gloves_brass")
brass.use_nodes = True
b2 = brass.node_tree.nodes["Principled BSDF"]
b2.inputs["Base Color"].default_value = (0.78, 0.55, 0.22, 1)
b2.inputs["Metallic"].default_value = 1.0
b2.inputs["Roughness"].default_value = 0.28
bme.materials.append(brass)
bpy.ops.object.select_all(action="DESELECT")
for o in (cuff, bo, glo):
    o.select_set(True)
bpy.context.view_layer.objects.active = glo
bpy.ops.object.join()
bpy.ops.export_scene.gltf(filepath=str(D / "shells" / "gloves.glb"), export_format="GLB", use_selection=True,
                          export_tangents=True)
print("CUFFS ok", len(buttons), "buttons")
