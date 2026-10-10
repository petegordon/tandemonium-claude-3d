"""P2.4: pose the skinned goose, measure deformation, render.

  blender -b --factory-startup --python scripts/pose_test.py -- --char base

Poses (all set from world-space bone directions so they are rig-agnostic):
rest, T-pose, A-pose (45 deg), riding (thighs forward, shins down, hands forward on bars,
slight lean), neck curve + head turn, honk + blink + look.
Per pose: edge-length ratio posed/rest over the whole mesh -> % edges stretched > 1.6x or
squashed < 0.5x, worst ratio and the bone that dominates the worst edges. Writes
out/<char>-goose/<char>_pose_test.json and renders/<char>_pose_test.png (front + side rows).
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1] if "--char" in argv else "base"
ROOT = Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_goose.blend"))
g = bpy.data.objects[f"{CHAR}_goose_game"]
rig = bpy.data.objects["goose_rig"]
pbs = rig.pose.bones
order = [b.name for b in rig.data.bones]                   # parents before children
me = g.data
edges = np.array([e.vertices[:] for e in me.edges])
rest_co = np.array([v.co[:] for v in me.vertices])
rest_len = np.linalg.norm(rest_co[edges[:, 0]] - rest_co[edges[:, 1]], axis=1)
vg_names = {vg.index: vg.name for vg in g.vertex_groups}
dominant = []
for v in me.vertices:
    ws = [(e.weight, vg_names[e.group]) for e in v.groups if vg_names[e.group][0].isupper()]
    dominant.append(max(ws)[1] if ws else "-")


def reset():
    for pb in pbs:
        pb.rotation_mode = "XYZ"
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()


def aim(name, direction, twist_up=None):
    """Rotate bone so it points along `direction` (armature space), keeping its head."""
    pb = pbs[name]
    bpy.context.view_layer.update()
    cur = pb.matrix.copy()
    d = Vector(direction).normalized()
    R = cur.to_3x3().col[1].normalized().rotation_difference(d).to_matrix()
    new = (R @ cur.to_3x3()).to_4x4()
    new.translation = cur.translation
    pb.matrix = new
    bpy.context.view_layer.update()


def rot_local(name, axis, deg):
    pb = pbs[name]
    pb.rotation_euler["XYZ".index(axis)] += math.radians(deg)
    bpy.context.view_layer.update()


def bone_dir(name):
    b = rig.data.bones[name]
    return (b.tail_local - b.head_local).normalized()


def mirror(v):
    return Vector((-v[0], v[1], v[2]))


def pose_t():
    for s, sx in (("Left", 1), ("Right", -1)):
        aim(f"{s}Arm", (sx, 0, 0))
        aim(f"{s}ForeArm", (sx, 0, 0))
        aim(f"{s}Hand", (sx, 0, -0.15))


def pose_a():
    for s, sx in (("Left", 1), ("Right", -1)):
        d = (sx * math.cos(math.radians(45)), 0, -math.sin(math.radians(45)))
        aim(f"{s}Arm", d)
        aim(f"{s}ForeArm", d)
        aim(f"{s}Hand", d)


def pose_riding():
    rot_local("Spine", "X", 8)
    rot_local("Spine1", "X", 6)
    for s, sx in (("Left", 1), ("Right", -1)):
        aim(f"{s}UpLeg", (sx * 0.12, -1.0, -0.25))
        aim(f"{s}Leg", (0, 0.15 if s == "Left" else -0.05, -1.0))
        aim(f"{s}Foot", (0, -1, -0.25))
        aim(f"{s}Arm", (sx * 0.25, -0.7, -0.45))
        aim(f"{s}ForeArm", (sx * 0.1, -1.0, -0.1))
        aim(f"{s}Hand", (0, -1, -0.3))


def pose_neck():
    for n, deg in (("Neck", -12), ("Neck1", 10), ("Neck2", 16), ("Neck3", 10)):
        rot_local(n, "X", deg)
    rot_local("Head", "Y", 30)


def pose_face():
    rot_local("Jaw", "X", -26)        # rig convention: -X opens the jaw
    rot_local("Tongue", "X", 15)      # +X lifts the tongue
    for s in ("Left", "Right"):
        rot_local(f"{s}EyelidUpper", "X", -28)
        rot_local(f"{s}EyelidLower", "X", 16)
        rot_local(f"{s}Eye", "Z", 12)


for o in bpy.data.objects:                                # only the game mesh + its eye parts render
    if o.type == "MESH":
        o.hide_render = not (o is g or (o.name.split("_")[0] in ("eyeball", "lid", "catchlight")
                                        and o.name[-2:] in ("_L", "_R")))
POSES = [("rest", None), ("t_pose", pose_t), ("a_pose", pose_a), ("riding", pose_riding),
         ("neck_curve", pose_neck), ("honk_blink", pose_face)]
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y = 480, 640
sc.view_settings.view_transform = "Standard"
sc.world = bpy.data.worlds.new("w")
sc.world.color = (0.85, 0.85, 0.85)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
sc.collection.objects.link(cam)
sc.camera = cam
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3
sc.collection.objects.link(sun)
report, rows = {}, [[], [], []]
for name, fn in POSES:
    reset()
    if fn:
        fn()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = g.evaluated_get(dg)
    pco = np.array([v.co[:] for v in ev.to_mesh().vertices])
    ev.to_mesh_clear()
    ratio = np.linalg.norm(pco[edges[:, 0]] - pco[edges[:, 1]], axis=1) / np.maximum(rest_len, 1e-9)
    bad = (ratio > 1.6) | (ratio < 0.5)
    worst = np.argsort(-np.abs(np.log(np.maximum(ratio, 1e-6))))[:30]
    bones = {}
    for e in worst:
        b = dominant[edges[e, 0]]
        bones[b] = bones.get(b, 0) + 1
    report[name] = {"stretched_pct": round(float((ratio > 1.6).mean() * 100), 2),
                    "squashed_pct": round(float((ratio < 0.5).mean() * 100), 2),
                    "max_ratio": round(float(ratio.max()), 2), "min_ratio": round(float(ratio.min()), 2),
                    "worst_edges_by_bone": dict(sorted(bones.items(), key=lambda t: -t[1])[:4])}
    print("POSE", name, json.dumps(report[name]))
    for ri, (yaw, zc, span) in enumerate(((20, 0.5, 1.95), (90, 0.5, 1.95), (60, 0.93, 0.32))):
        y = math.radians(yaw)
        H = 1.65
        tgt = Vector((0, -0.05 if ri == 2 else 0, zc * H))
        cam.location = tgt + Vector((math.sin(y), -math.cos(y), 0.05)) * 3
        cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler()
        cam.data.ortho_scale = span
        sun.rotation_euler = cam.rotation_euler
        sc.render.filepath = str(ROOT / "renders" / "_tmp" / f"pose_{name}_{ri}.png")
        bpy.ops.render.render(write_still=True)
        rows[ri].append(sc.render.filepath)
(ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_pose_test.json").write_text(json.dumps(report, indent=1))
W, Hh = 480, 640
canvas = np.ones((Hh * 3, W * len(POSES), 4), np.float32)
for ri, row in enumerate(rows):
    for ci, pth in enumerate(row):
        canvas[(2 - ri) * Hh:(3 - ri) * Hh, ci * W:(ci + 1) * W] = \
            np.array(bpy.data.images.load(pth).pixels[:], np.float32).reshape(Hh, W, 4)
out = bpy.data.images.new("o", W * len(POSES), Hh * 3)
out.pixels.foreach_set(canvas.ravel())
out.filepath_raw = str(ROOT / "renders" / f"{CHAR}_pose_test.png")
out.file_format = "PNG"
out.save()
print("POSETEST", out.filepath_raw)
