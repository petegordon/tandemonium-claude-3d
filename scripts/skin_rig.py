"""P2.3: skin the base goose game mesh to goose_rig.

  blender -b --factory-startup --python scripts/skin_rig.py -- --char base

1. Bone-heat automatic weights (Blender ARMATURE_AUTO) on the head/body mesh.
2. Overrides for parts heat weighting can't know about (from the P1 fix vertex groups):
   lower bill + mouth floor + lower serrations -> Jaw (weight from "beak_lower", rest Head);
   tongue -> Tongue (ramp from "tongue") / Jaw; upper bill + roof + upper serrations -> Head.
3. Max 4 influences per vertex, normalized (glTF skinning).
4. Eye parts are bone-parented: eyeball_* -> {Side}Eye, lid_upper_* -> {Side}EyelidUpper,
   lid_lower_* -> {Side}EyelidLower, catchlight_* -> Head.
Saves the .blend and exports out/<char>-goose/<char>_goose_rigged.glb.
"""
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1] if "--char" in argv else "base"
ROOT = Path(__file__).resolve().parents[1]
BLEND = ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_goose.blend"
bpy.ops.wm.open_mainfile(filepath=str(BLEND))
g = bpy.data.objects[f"{CHAR}_goose_game"]
rig = bpy.data.objects["goose_rig"]
me = g.data
bone_names = {b.name for b in rig.data.bones}

# keep the P1 helper groups, clear any old bone weights / modifiers
for vg in list(g.vertex_groups):
    if vg.name in bone_names:
        g.vertex_groups.remove(vg)
for m in list(g.modifiers):
    if m.type == "ARMATURE":
        g.modifiers.remove(m)
helper = {}
for name in ("beak_lower", "tongue"):
    w = np.zeros(len(me.vertices), np.float32)
    if name in g.vertex_groups:
        gi = g.vertex_groups[name].index
        for v in me.vertices:
            for e in v.groups:
                if e.group == gi:
                    w[v.index] = e.weight
    helper[name] = w

# eye parts: detach from the mesh before heat weighting (they get bone parents below)
eyes = [o for o in bpy.data.objects if o.type == "MESH" and o.name.split("_")[0] in ("eyeball", "lid", "catchlight")
        and o.name[-2:] in ("_L", "_R")]
for o in eyes:
    mw = o.matrix_world.copy()
    o.parent = None
    o.matrix_world = mw

# face-detail bones never take part in heat weighting: eye/lid bones only carry the eye objects,
# HatSocket is an attachment point, Jaw/Tongue get their weights from the overrides below
NO_HEAT = {b.name for b in rig.data.bones if b.name.endswith(("Eye", "EyelidUpper", "EyelidLower"))} |     {"HatSocket", "Jaw", "Tongue"}
for b in rig.data.bones:
    b.use_deform = b.name not in NO_HEAT
bpy.ops.object.select_all(action="DESELECT")
g.select_set(True)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.parent_set(type="ARMATURE_AUTO")
for name in ("Jaw", "Tongue"):
    rig.data.bones[name].use_deform = True
mw = g.matrix_world.copy()               # skinned mesh as a root node (glTF NODE_SKINNED_MESH_NON_ROOT);
g.parent = None                          # the Armature modifier still drives it
g.matrix_world = mw
print("SKIN auto weights done")

# ---- overrides from the beak / tongue helper groups
co = np.array([v.co[:] for v in me.vertices])
hinge = Vector(g["beak_hinge_point"])
mouth_front = co[:, 1] < hinge.y + 0.004


def set_weights(i, wmap):
    for vg in g.vertex_groups:
        if vg.name in bone_names:
            vg.remove([i])
    for name, w in wmap.items():
        if w > 1e-4:
            g.vertex_groups[name].add([i], float(w), "REPLACE")


for name in ("Head", "Jaw", "Tongue"):
    if name not in g.vertex_groups:
        g.vertex_groups.new(name=name)
n_jaw = n_tongue = n_head = 0
for i in range(len(co)):
    wl, wt = helper["beak_lower"][i], helper["tongue"][i]
    if wt > 0:
        set_weights(i, {"Tongue": wt, "Jaw": 1 - wt})
        n_tongue += 1
    elif wl > 0:
        if wl >= 0.999:
            set_weights(i, {"Jaw": 1.0})
        else:                                              # chin skin just behind the gape: blend
            set_weights(i, {"Jaw": wl, "Head": 1 - wl})
        n_jaw += 1
    elif mouth_front[i] and co[i, 2] > hinge.z - 0.05 and abs(co[i, 0]) < 0.06:
        set_weights(i, {"Head": 1.0})                      # upper bill, roof, upper serrations
        n_head += 1

# ---- max 4 influences, normalized
bone_vg = {vg.index: vg for vg in g.vertex_groups if vg.name in bone_names}
unweighted = 0
for v in me.vertices:
    ws = sorted(((e.weight, e.group) for e in v.groups if e.group in bone_vg and e.weight > 0), reverse=True)
    if not ws:
        unweighted += 1
        continue
    keep = ws[:4]
    tot = sum(w for w, _ in keep)
    for w, gi in ws[4:]:
        bone_vg[gi].remove([v.index])
    for w, gi in keep:
        bone_vg[gi].add([v.index], w / tot, "REPLACE")
print("SKIN overrides: jaw", n_jaw, "tongue", n_tongue, "head(beak/roof)", n_head, "unweighted", unweighted)

# ---- eye parts -> bone parents
bpy.ops.object.select_all(action="DESELECT")
for o in eyes:
    base, side = o.name.rsplit("_", 1)
    sname = "Left" if side == "L" else "Right"
    target = {"eyeball": f"{sname}Eye", "lid_upper": f"{sname}EyelidUpper",
              "lid_lower": f"{sname}EyelidLower", "catchlight": "Head"}[base]
    mw = o.matrix_world.copy()
    o.parent = rig
    o.parent_type = "BONE"
    o.parent_bone = target
    pb = rig.pose.bones[target]
    o.matrix_parent_inverse = (rig.matrix_world @ pb.matrix @
                               __import__("mathutils").Matrix.Translation((0, pb.bone.length, 0))).inverted()
    o.matrix_world = mw
print("SKIN eyes bone-parented:", len(eyes))
bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)

bpy.ops.object.select_all(action="DESELECT")
for o in [rig, g, *eyes]:
    o.select_set(True)
bpy.context.view_layer.objects.active = rig
out = ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_goose_rigged.glb"
bpy.ops.export_scene.gltf(filepath=str(out), export_format="GLB", use_selection=True, export_skins=True,
                          export_tangents=True, export_animations=False, export_yup=True)
sys.path.insert(0, str(Path(__file__).parent))
from glb_fix_tangents import main as fix_tangents  # noqa: E402
fix_tangents(str(out))
print("SKIN exported", out)
