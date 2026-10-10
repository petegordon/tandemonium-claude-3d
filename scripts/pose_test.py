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


sys.path.insert(0, str(Path(__file__).parent))
from rig_poses import Poser  # noqa: E402

poser = Poser(rig)
reset = poser.reset
POSE_FNS = {"t_pose": poser.t_pose, "a_pose": poser.a_pose, "riding": poser.riding,
            "neck_curve": poser.neck_curve, "honk_blink": poser.honk_blink}


for o in bpy.data.objects:                                # only the game mesh + its eye parts render
    if o.type == "MESH":
        o.hide_render = not (o is g or (o.name.split("_")[0] in ("eyeball", "lid", "catchlight")
                                        and o.name[-2:] in ("_L", "_R")))
POSES = [("rest", None)] + list(POSE_FNS.items())
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
