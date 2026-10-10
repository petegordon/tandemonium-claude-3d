"""P2.4: test animation set on the standard goose rig, exported with the rigged GLB.

  blender -b --factory-startup --python scripts/make_anims.py -- --char base

Clips (24 fps, looping, keyed in bone-local rotations so they retarget to any goose that uses
the standard rig): idle (breathing + small head sway, 2 s), blink (0.5 s), look_around (eyes
lead, head follows, 3 s), honk (neck stretch, jaw open + tongue lift, 1.25 s).
Each clip is its own action (pushed to an NLA track so the glTF exporter writes them all).
Writes out/<char>-goose/<char>_goose_rigged.glb (mesh + skin + clips).
"""
import math
import sys
from pathlib import Path

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1] if "--char" in argv else "base"
ROOT = Path(__file__).resolve().parents[1]
BLEND = ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_goose.blend"
bpy.ops.wm.open_mainfile(filepath=str(BLEND))
rig = bpy.data.objects["goose_rig"]
g = bpy.data.objects[f"{CHAR}_goose_game"]
FPS = 24
bpy.context.scene.render.fps = FPS
for pb in rig.pose.bones:
    pb.rotation_mode = "XYZ"
for a in [a for a in bpy.data.actions]:
    bpy.data.actions.remove(a)
rig.animation_data_create()
for t in list(rig.animation_data.nla_tracks):
    rig.animation_data.nla_tracks.remove(t)


def key(action, frame, bone, rot_deg):
    """Key a bone's local XYZ Euler rotation (degrees) at frame."""
    pb = rig.pose.bones[bone]
    pb.rotation_euler = [math.radians(r) for r in rot_deg]
    pb.keyframe_insert("rotation_euler", frame=frame, group=bone)


def clip(name, length_s, keys):
    """keys: {bone: [(t_seconds, (rx, ry, rz)), ...]} -> action pushed onto its own NLA track."""
    act = bpy.data.actions.new(name)
    rig.animation_data.action = act
    for pb in rig.pose.bones:
        pb.rotation_euler = (0, 0, 0)
    for bone, ks in keys.items():
        for t, rot in ks:
            key(act, round(t * FPS) + 1, bone, rot)
    act.use_fake_user = True
    track = rig.animation_data.nla_tracks.new()
    track.name = name
    strip = track.strips.new(name, 1, act)
    strip.extrapolation = "NOTHING"
    track.mute = True
    rig.animation_data.action = None
    return act


Z = (0, 0, 0)
clip("idle", 2.0, {
    "Spine1": [(0, Z), (1.0, (1.5, 0, 0)), (2.0, Z)],             # breathing
    "Spine2": [(0, Z), (1.0, (-1.5, 0, 0)), (2.0, Z)],
    "Neck2": [(0, Z), (1.0, (2, 0, 0)), (2.0, Z)],
    "Head": [(0, Z), (0.5, (0, 3, 0)), (1.5, (0, -3, 0)), (2.0, Z)],
    "LeftArm": [(0, Z), (1.0, (0, 0, 1.5)), (2.0, Z)],
    "RightArm": [(0, Z), (1.0, (0, 0, -1.5)), (2.0, Z)],
})
blink = {}
for s in ("Left", "Right"):
    blink[f"{s}EyelidUpper"] = [(0, Z), (0.12, (-30, 0, 0)), (0.2, (-30, 0, 0)), (0.5, Z)]
    blink[f"{s}EyelidLower"] = [(0, Z), (0.12, (17, 0, 0)), (0.2, (17, 0, 0)), (0.5, Z)]
clip("blink", 0.5, blink)
look = {"Head": [(0, Z), (0.5, (0, 14, 0)), (1.3, (0, 14, 0)), (1.8, (0, -14, 0)), (2.6, (0, -14, 0)), (3.0, Z)],
        "Neck3": [(0, Z), (0.6, (0, 6, 0)), (1.3, (0, 6, 0)), (1.9, (0, -6, 0)), (2.6, (0, -6, 0)), (3.0, Z)]}
for s, sg in (("Left", 1), ("Right", -1)):
    look[f"{s}Eye"] = [(0, Z), (0.25, (0, 0, 12 * sg)), (1.3, (0, 0, 12 * sg)), (1.55, (0, 0, -8 * sg)),
                       (2.6, (0, 0, -8 * sg)), (3.0, Z)]
clip("look_around", 3.0, look)
clip("honk", 1.25, {
    "Neck": [(0, Z), (0.3, (-6, 0, 0)), (0.85, (-6, 0, 0)), (1.25, Z)],
    "Neck1": [(0, Z), (0.3, (-5, 0, 0)), (0.85, (-5, 0, 0)), (1.25, Z)],
    "Head": [(0, Z), (0.3, (8, 0, 0)), (0.85, (8, 0, 0)), (1.25, Z)],
    "Jaw": [(0, Z), (0.3, (24, 0, 0)), (0.5, (16, 0, 0)), (0.7, (26, 0, 0)), (0.95, Z), (1.25, Z)],
    "Tongue": [(0, Z), (0.3, (-18, 0, 0)), (0.7, (-22, 0, 0)), (0.95, Z), (1.25, Z)],
})
for pb in rig.pose.bones:
    pb.rotation_euler = (0, 0, 0)
bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)

eyes = [o for o in bpy.data.objects if o.parent is rig and o.parent_type == "BONE"]
bpy.ops.object.select_all(action="DESELECT")
for o in [rig, g, *eyes]:
    o.select_set(True)
bpy.context.view_layer.objects.active = rig
out = ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_goose_rigged.glb"
bpy.ops.export_scene.gltf(filepath=str(out), export_format="GLB", use_selection=True, export_skins=True,
                          export_tangents=True, export_animations=True, export_animation_mode="NLA_TRACKS",
                          export_yup=True)
sys.path.insert(0, str(Path(__file__).parent))
from glb_fix_tangents import main as fix_tangents  # noqa: E402
fix_tangents(str(out))
print("ANIMS", [a.name for a in bpy.data.actions], "->", out)
