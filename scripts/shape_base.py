"""Export the naked base goose reshaped by body-shape sliders (bodyshape.py), for reference renders of a new body type
(e.g. the grandparents: shorter, wider) before any outfit exists.

  blender -b --factory-startup --python scripts/shape_base.py -- --shape '{"leg_length":0.9,"torso_girth":1.3}'
      --out out/shapes/<name>.glb

Imports out/base-goose/base_goose_rigged.glb, moves the skinned body by its own weights (bodyshape.deform), moves each
bone-parented part (eyes, lids) by its parent bone's map, re-poses the edit bones to the shape, and lifts the goose so
its lowest point sits on z = 0 (short legs would otherwise float). Then outfit_beauty.py renders it like the base.
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).parent))
import bodyshape  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
ROOT = Path(__file__).resolve().parents[1]
SHAPE = json.loads(argv[argv.index("--shape") + 1])
OUT = ROOT / argv[argv.index("--out") + 1]
OUT.parent.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ROOT / "out" / "base-goose" / "base_goose_rigged.glb"))
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
T = bodyshape.slider_transforms(rig, SHAPE)
heads0 = {b.name: np.array(rig.matrix_world @ b.head_local) for b in rig.data.bones}
tails0 = {b.name: np.array(rig.matrix_world @ b.tail_local) for b in rig.data.bones}


def bone_map(name, X):
    tr = T[name]
    return np.array(tr["head"]) + (X - heads0[name]) @ np.array(tr["A"]).T


meshes = [o for o in bpy.data.objects if o.type == "MESH"]
for o in meshes:                                        # bone-parented parts: world space, by the parent bone's map
    if o.parent is rig and o.parent_type == "BONE":
        mw = o.matrix_world.copy()
        X = np.array([(mw @ v.co)[:] for v in o.data.vertices])
        Y = bone_map(o.parent_bone, X)
        inv = mw.inverted()
        for v, y in zip(o.data.vertices, Y):
            v.co = inv @ Vector(y)
        o.data.update()
for o in meshes:                                        # skinned meshes: linear blend of the bone maps
    if not o.vertex_groups or o.parent_type == "BONE":
        continue
    names = [g.name for g in o.vertex_groups]
    V = np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices])
    W = np.zeros((len(V), len(names)))
    for v in o.data.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
    Vs = bodyshape.deform(V, W, [n if n in T else "" for n in names], rig, T)
    inv = o.matrix_world.inverted()
    for v, y in zip(o.data.vertices, Vs):
        v.co = inv @ Vector(y)
    o.data.update()

# edit bones take the shape (bone-parented parts keep their world place: re-parenting below would move them, so we
# restore each one's world matrix after the edit)
keep = {o: o.matrix_world.copy() for o in meshes if o.parent_type == "BONE"}
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
inv = rig.matrix_world.inverted()
for eb in rig.data.edit_bones:
    h, A = np.array(T[eb.name]["head"]), np.array(T[eb.name]["A"])
    roll = eb.roll
    eb.head = inv @ Vector(h)
    eb.tail = inv @ Vector(h + A @ (tails0[eb.name] - heads0[eb.name]))
    eb.roll = roll
bpy.ops.object.mode_set(mode="OBJECT")
bpy.context.view_layer.update()
for o, mw in keep.items():
    o.matrix_world = mw

# feet on the floor
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
zmin = min((o.matrix_world @ v.co).z for o in meshes if o.vertex_groups and o.parent_type != "BONE"
           for v in o.evaluated_get(dg).to_mesh().vertices)
rig.location.z -= zmin
zmax = max((o.matrix_world @ Vector(c)).z for o in meshes for c in o.bound_box)
print("SHAPE", json.dumps(SHAPE), "lift", round(-zmin, 3), "height_m", round(zmax - zmin, 3))
bpy.ops.export_scene.gltf(filepath=str(OUT), export_format="GLB", export_animations=False, export_skins=True)
print("wrote", OUT)
