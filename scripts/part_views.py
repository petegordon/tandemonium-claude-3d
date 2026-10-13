"""Body-part label maps of OUR base goose in the key mannequin's calibrated views (front / left / rear / right).

  blender -b --factory-startup --python scripts/part_views.py -- [--key refs/key_views]

Each body vertex takes the part of its strongest skin weight (bone -> part, PART_OF); faces are flat-coloured by part
(emission, no anti-aliasing), rendered with the same cameras as key_views.py. Writes <key>/parts_<view>.png and
<key>/parts.json (part -> colour, legend order). These are exact: the reference for naming the drawn goose's parts.
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ROOT = Path(__file__).resolve().parents[1]
KEYD = ROOT / (argv[argv.index("--key") + 1] if "--key" in argv else "refs/key_views")
CAM = json.loads((KEYD / "cameras.json").read_text(encoding="utf-8"))
PARTS = ["head", "neck", "torso", "tail", "upper_arm_L", "forearm_L", "hand_L", "upper_arm_R", "forearm_R", "hand_R",
         "thigh_L", "shin_L", "foot_L", "thigh_R", "shin_R", "foot_R"]
COLORS = {"head": (0.9, 0.9, 0.2), "neck": (0.9, 0.55, 0.1), "torso": (0.85, 0.15, 0.15), "tail": (0.45, 0.2, 0.1),
          "upper_arm_L": (0.2, 0.45, 0.95), "forearm_L": (0.1, 0.75, 0.9), "hand_L": (0.6, 0.2, 0.9),
          "upper_arm_R": (0.15, 0.3, 0.6), "forearm_R": (0.1, 0.5, 0.55), "hand_R": (0.4, 0.1, 0.55),
          "thigh_L": (0.2, 0.8, 0.3), "shin_L": (0.6, 0.9, 0.3), "foot_L": (0.95, 0.5, 0.7),
          "thigh_R": (0.1, 0.5, 0.2), "shin_R": (0.4, 0.6, 0.15), "foot_R": (0.7, 0.3, 0.45)}


def part_of(bone):
    side = "L" if bone.startswith("Left") else "R"
    if bone.startswith(("Left", "Right")):
        b = bone[4:] if bone.startswith("Left") else bone[5:]
        return {"Shoulder": "upper_arm", "Arm": "upper_arm", "ForeArm": "forearm", "Hand": "hand", "UpLeg": "thigh",
                "Leg": "shin", "Foot": "foot", "ToeBase": "foot"}.get(b, "torso") + f"_{side}"
    if bone.startswith("Neck"):
        return "neck"
    if bone in ("Head", "Jaw", "Tongue", "beak_lower", "tongue"):
        return "head"
    if bone == "Tail":
        return "tail"
    return "torso"


bpy.ops.wm.open_mainfile(filepath=str(ROOT / "out" / "base-goose" / "base_goose.blend"))
for o in list(bpy.data.objects):
    if o.type == "MESH" and o.name != "base_goose_game":
        bpy.data.objects.remove(o)
body = bpy.data.objects["base_goose_game"]
gname = {g.index: g.name for g in body.vertex_groups}
vpart = []
for v in body.data.vertices:
    best = max(v.groups, key=lambda g: g.weight, default=None)
    vpart.append(part_of(gname[best.group]) if best else "torso")
mats = {}
body.data.materials.clear()
for i, p in enumerate(PARTS):
    m = bpy.data.materials.new(p)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*COLORS[p], 1)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(em.outputs[0], out.inputs[0])
    body.data.materials.append(m)
    mats[p] = i
for poly in body.data.polygons:
    votes = {}
    for vi in poly.vertices:
        votes[vpart[vi]] = votes.get(vpart[vi], 0) + 1
    poly.material_index = mats[max(votes, key=votes.get)]
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
sc.render.filter_size = 0.0
W0, H0 = CAM["size_px"]
sc.render.resolution_x, sc.render.resolution_y = W0, H0
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0, 0, 0, 1)
sc.world = w
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = CAM["ortho_m_height"]
sc.collection.objects.link(cam)
sc.camera = cam
for view, c in CAM["views"].items():
    cam.location = Vector(c["location"])
    a = math.radians(c["yaw_deg"])
    d = Vector((math.sin(a), -math.cos(a), 0.0))
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = str(KEYD / f"parts_{view}.png")
    bpy.ops.render.render(write_still=True)
(KEYD / "parts.json").write_text(json.dumps({"parts": PARTS, "colors": COLORS}, indent=1), encoding="utf-8")
print("PARTS", {p: vpart.count(p) for p in PARTS})
