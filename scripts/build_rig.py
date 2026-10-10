"""P2.1/P2.2: build the standard goose skeleton on the base goose (Pete: keep the model's own
pose as bind pose; Mixamo-style humanoid names + goose extras).

  blender -b --factory-startup --python scripts/build_rig.py -- --char base [--render]

Joints are measured from the game mesh, not hand-placed:
- legs: hip = where the legs merge into the torso, knee = top of the dark scaly lower leg,
  ankle = just above the foot, toe = front of the webbed foot;
- arms: the outermost slice segment at each height is the arm; its centroids give the arm
  line; shoulder = where the arm meets the torso, wrist = where the dark hand begins;
- spine / neck: centroids of the torso and neck cross-sections; head from the eye level;
- face: eye centres / axes, beak hinge, tongue root / axis from the P1 fix props.
Character's left = +X (model faces -Y). Writes armature "goose_rig" into the .blend,
out/<char>-goose/<char>_rig.json (joint positions) and with --render
renders/<char>_rig_overlay.png (front, side, back, 3/4).
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).parent))
from fixes.common import input_image, read_pixels, rgb_to_hsv  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1] if "--char" in argv else "base"
ROOT = Path(__file__).resolve().parents[1]
BLEND = ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_goose.blend"
bpy.ops.wm.open_mainfile(filepath=str(BLEND))
g = bpy.data.objects[f"{CHAR}_goose_game"]
me = g.data
co = np.array([v.co[:] for v in me.vertices])
H = co[:, 2].max()

# per-vertex albedo value (dark = hands, lower legs, neck/head)
px = read_pixels(input_image(g, "Base Color"))
th, tw = px.shape[:2]
lv = np.empty(len(me.loops), np.int32)
me.loops.foreach_get("vertex_index", lv)
uv = np.empty(len(me.loops) * 2, np.float32)
me.uv_layers.active.data.foreach_get("uv", uv)
vuv = np.zeros((len(co), 2))
vuv[lv] = uv.reshape(-1, 2)
val = rgb_to_hsv(px[np.clip((vuv[:, 1] * th).astype(int), 0, th - 1),
                    np.clip((vuv[:, 0] * tw).astype(int), 0, tw - 1), :3])[:, 2]
body = np.ones(len(co), bool)
for name in ("beak_lower", "tongue"):                    # ignore mouth interior parts
    if name in g.vertex_groups:
        gi = g.vertex_groups[name].index
        for v in me.vertices:
            if any(e.group == gi and e.weight > 0.99 for e in v.groups) and v.co.y < -0.16:
                body[v.index] = False


def segments(z, tol=0.008, gap=0.03):
    """X-segments of the horizontal slice at height z -> list of vertex index arrays."""
    idx = np.where(body & (np.abs(co[:, 2] - z) < tol))[0]
    if not len(idx):
        return []
    order = idx[np.argsort(co[idx, 0])]
    cuts = np.where(np.diff(co[order, 0]) > gap)[0]
    return np.split(order, cuts + 1)


def centroid(ids):
    return Vector(co[ids].mean(0))


J = {}
# ---- legs (+X side; mirrored later)
crotch = None
for z in np.arange(0.30, 0.75, 0.005) * H:
    segs = [s for s in segments(z) if abs(co[s, 0].mean()) < 0.25]
    if len(segs) == 1:
        crotch = z
        break
leg = lambda z: next(s for s in segments(z) if co[s, 0].mean() > 0.02 and co[s, 0].mean() < 0.25)
knee_z = None
for z in np.arange(0.12, 0.45, 0.005) * H:               # top of the dark lower leg
    s = leg(z)
    if (val[s] < 0.16).mean() < 0.5:
        knee_z = z
        break
J["LeftUpLeg"] = centroid(leg(crotch - 0.03))
J["LeftUpLeg"].z = crotch + 0.06              # hip joint sits inside the pelvis (Pete: was low)
J["LeftLeg"] = centroid(leg(knee_z))
ankle_z = 0.07 * H
J["LeftFoot"] = centroid(leg(ankle_z))
foot = np.where(body & (co[:, 2] < 0.045 * H) & (co[:, 0] > 0))[0]
toe_tip = Vector(co[foot[np.argmin(co[foot, 1])]])
J["LeftToeBase"] = J["LeftFoot"].lerp(Vector((toe_tip.x, toe_tip.y, 0.02)), 0.45)
J["LeftToeBase"].z = 0.025
J["LeftToe_End"] = Vector((toe_tip.x, toe_tip.y, 0.02))

# ---- arms: outermost slice segment = arm
arm_pts = []
for z in np.arange(0.38, 0.72, 0.01) * H:
    segs = [s for s in segments(z) if co[s, 0].mean() > 0.15]
    if segs:
        s = max(segs, key=lambda s: co[s, 0].mean())
        arm_pts.append((z, centroid(s), (val[s] < 0.16).mean()))
wrist = next(c for z, c, d in sorted(arm_pts, key=lambda t: -t[0]) if d > 0.5)
hand_ids = np.where(body & (co[:, 0] > 0.3) & (co[:, 2] < wrist.z))[0]
hand_end = Vector(co[hand_ids[np.argmin(co[hand_ids, 2])]])
top = max(arm_pts, key=lambda t: t[0])[1]
# shoulder = lowest height (going up) where nothing sticks out past the upper-chest width, i.e.
# the arm has fully merged into the torso (an asymmetric arm+torso slice must not stop it early)
chest_half = max(co[s_, 0].max() for s_ in segments(0.76 * H) if co[s_, 0].min() < 0 < co[s_, 0].max())
shoulder_z = None
for z in np.arange(0.60, 0.80, 0.005) * H:
    if max((co[s_, 0].max() for s_ in segments(z)), default=0) < chest_half + 0.02:
        shoulder_z = z
        break
torso_at_shoulder = [s for s in segments(shoulder_z) if co[s, 0].min() < 0 < co[s, 0].max()]
J["LeftArm"] = Vector((chest_half * 0.78, centroid(torso_at_shoulder[0]).y, shoulder_z - 0.035))
J["LeftForeArm"] = J["LeftArm"].lerp(wrist, 0.5) + Vector((0, 0.012, 0))   # slight elbow bend back
J["LeftHand"] = wrist
J["LeftHand_End"] = hand_end
J["LeftShoulder"] = Vector((0.04, J["LeftArm"].y, J["LeftArm"].z + 0.01))

# ---- spine / neck / head (centre line)
torso = lambda z: next(s for s in segments(z) if co[s, 0].min() < 0.01 and co[s, 0].max() > -0.01)
J["Hips"] = Vector((0, centroid(torso(crotch + 0.08)).y, crotch + 0.08))
neck_base = shoulder_z + 0.05
for k, name in enumerate(("Spine", "Spine1", "Spine2")):
    z = J["Hips"].z + (neck_base - J["Hips"].z) * (k + 1) / 4
    J[name] = Vector((0, centroid(torso(z)).y, z))
eye_l = Vector(g["eye_L_center"])
head_z = eye_l.z - 0.09
for k, name in enumerate(("Neck", "Neck1", "Neck2", "Neck3")):
    z = neck_base + (head_z - neck_base) * k / 4
    J[name] = Vector((0, centroid(torso(z)).y, z))
J["Head"] = Vector((0, centroid(torso(head_z)).y, head_z))
J["HeadTop_End"] = Vector((0, eye_l.y + 0.01, H))
J["HatSocket"] = J["HeadTop_End"].copy()

# ---- tail: rearmost feather fan
back = np.where(body & (co[:, 2] > crotch - 0.1) & (co[:, 2] < crotch + 0.2) & (np.abs(co[:, 0]) < 0.08))[0]
tail_tip = Vector(co[back[np.argmax(co[back, 1])]])
tail_root_z = J["Hips"].z + 0.16                   # where the fan attaches on the back (Pete: was low)
back_at = np.where(body & (np.abs(co[:, 2] - tail_root_z) < 0.01) & (np.abs(co[:, 0]) < 0.05))[0]
J["Tail"] = Vector((0, co[back_at, 1].max() - 0.035, tail_root_z))
J["Tail_End"] = Vector((0, tail_tip.y, tail_tip.z))

# ---- face (from the P1 fix props / eye objects)
hinge = Vector(g["beak_hinge_point"])
t_root, t_axis = Vector(g["tongue_root"]), Vector(g["tongue_axis"])
lower_tip = Vector((0, -0.2875, 1.494))
eye_frame = {s: bpy.data.objects[f"eyeball_{s}"].matrix_world.to_3x3() for s in ("L", "R")}


def mirror(v):
    return Vector((-v.x, v.y, v.z))


# ---- armature
for o in [o for o in bpy.data.objects if o.type == "ARMATURE"]:
    bpy.data.objects.remove(o)
arm = bpy.data.armatures.new("goose_rig")
rig = bpy.data.objects.new("goose_rig", arm)
bpy.context.scene.collection.objects.link(rig)
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
eb = arm.edit_bones


def bone(name, head, tail, parent=None, roll_up=None, connect=False):
    b = eb.new(name)
    b.head, b.tail = head, tail
    if roll_up is not None:
        b.align_roll(roll_up)
    if parent:
        b.parent = eb[parent]
        b.use_connect = connect
    return b


up, fwd = Vector((0, 0, 1)), Vector((0, -1, 0))
bone("Hips", J["Hips"], J["Spine"], roll_up=fwd)
bone("Spine", J["Spine"], J["Spine1"], "Hips", fwd, True)
bone("Spine1", J["Spine1"], J["Spine2"], "Spine", fwd, True)
bone("Spine2", J["Spine2"], J["Neck"], "Spine1", fwd, True)
chain = ["Neck", "Neck1", "Neck2", "Neck3", "Head"]
for a, b_ in zip(chain, chain[1:]):
    bone(a, J[a], J[b_], "Spine2" if a == "Neck" else chain[chain.index(a) - 1], fwd, a != "Neck")
bone("Head", J["Head"], J["HeadTop_End"], "Neck3", fwd, True)
bone("HatSocket", J["HatSocket"], J["HatSocket"] + Vector((0, 0, 0.05)), "Head", fwd)
bone("Jaw", hinge, lower_tip, "Head", up)
bone("Tongue", t_root, t_root + t_axis * 0.08, "Jaw", Vector(g["tongue_up"]))
for s, side, mir in (("L", "Left", False), ("R", "Right", True)):
    m = eye_frame[s]
    c = Vector(g[f"eye_{s}_center"])
    look, eup = -m.col[1], m.col[2]
    bone(f"{side}Eye", c, c + look * 0.025, "Head", eup)
    bone(f"{side}EyelidUpper", c, c + look * 0.02 + eup * 0.006, "Head", eup)
    bone(f"{side}EyelidLower", c, c + look * 0.02 - eup * 0.006, "Head", eup)
    f = mirror if mir else (lambda v: v)
    bone(f"{side}Shoulder", f(J["LeftShoulder"]), f(J["LeftArm"]), "Spine2", up)
    bone(f"{side}Arm", f(J["LeftArm"]), f(J["LeftForeArm"]), f"{side}Shoulder", fwd, True)
    bone(f"{side}ForeArm", f(J["LeftForeArm"]), f(J["LeftHand"]), f"{side}Arm", fwd, True)
    bone(f"{side}Hand", f(J["LeftHand"]), f(J["LeftHand_End"]), f"{side}ForeArm", fwd, True)
    bone(f"{side}UpLeg", f(J["LeftUpLeg"]), f(J["LeftLeg"]), "Hips", fwd)
    bone(f"{side}Leg", f(J["LeftLeg"]), f(J["LeftFoot"]), f"{side}UpLeg", fwd, True)
    bone(f"{side}Foot", f(J["LeftFoot"]), f(J["LeftToeBase"]), f"{side}Leg", up, True)
    bone(f"{side}ToeBase", f(J["LeftToeBase"]), f(J["LeftToe_End"]), f"{side}Foot", up, True)
bone("Tail", J["Tail"], J["Tail_End"], "Hips", up)
bpy.ops.object.mode_set(mode="OBJECT")
bones = {b.name: [list(map(lambda x: round(x, 4), b.head_local)), list(map(lambda x: round(x, 4), b.tail_local))]
         for b in arm.bones}
(ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_rig.json").write_text(json.dumps(
    {"bind_pose": "model rest pose (arms ~30 deg out)", "naming": "Mixamo-style + goose extras",
     "crotch_z": round(float(crotch), 4), "knee_z": round(float(knee_z), 4), "shoulder_z": round(float(shoulder_z), 4),
     "bones": bones}, indent=1))
print("RIG", len(arm.bones), "bones")
bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)

if "--render" in argv:
    # overlay: translucent mesh + bones as coloured sticks with joint balls
    import bmesh
    colors = {"Left": (0.9, 0.15, 0.1), "Right": (0.1, 0.35, 0.95), "face": (0.1, 0.8, 0.3), "mid": (1.0, 0.8, 0.0)}
    mats = {}
    for k, c in colors.items():
        m = bpy.data.materials.new(f"bone_{k}")
        m.use_nodes = True
        e = m.node_tree.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = (*c, 1)
        m.node_tree.links.new(e.outputs[0], m.node_tree.nodes["Material Output"].inputs["Surface"])
        mats[k] = m
    for b in arm.bones:
        k = "Left" if b.name.startswith("Left") else "Right" if b.name.startswith("Right") else \
            "face" if b.name in ("Jaw", "Tongue", "HatSocket") else "mid"
        bm = bmesh.new()
        L = (b.tail_local - b.head_local).length
        bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=min(0.012, L * 0.12), radius2=0.002, depth=L)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, L / 2))
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=min(0.016, L * 0.15))
        mesh = bpy.data.meshes.new(b.name)
        bm.to_mesh(mesh)
        bm.free()
        o = bpy.data.objects.new("vis_" + b.name, mesh)
        o.matrix_world = Matrix.Translation(b.head_local) @ (b.tail_local - b.head_local).to_track_quat("Z", "Y").to_matrix().to_4x4()
        mesh.materials.append(mats[k])
        bpy.context.scene.collection.objects.link(o)
    gm = me.materials[0]
    p = next(n for n in gm.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Alpha"].default_value = 0.35
    gm.surface_render_method = "BLENDED"
    for o in bpy.data.objects:
        if o.parent is g:
            o.hide_render = True
        elif o.type == "MESH" and o is not g and not o.name.startswith("vis_"):
            o.hide_render = True
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 520, 800
    sc.view_settings.view_transform = "Standard"
    sc.world = bpy.data.worlds.new("w")
    sc.world.color = (0.9, 0.9, 0.9)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 1.85
    sc.collection.objects.link(cam)
    sc.camera = cam
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3
    sc.collection.objects.link(sun)
    paths = []
    for yaw in (0, 90, 180, 35):
        y = np.radians(yaw)
        tgt = Vector((0, 0, H / 2))
        cam.location = tgt + Vector((np.sin(y), -np.cos(y), 0)) * 3
        cam.rotation_euler = (tgt - cam.location).to_track_quat("-Z", "Y").to_euler()
        sun.rotation_euler = cam.rotation_euler
        sc.render.filepath = str(ROOT / "renders" / "_tmp" / f"rig_{yaw}.png")
        bpy.ops.render.render(write_still=True)
        paths.append(sc.render.filepath)
    imgs = [np.array(bpy.data.images.load(p_).pixels[:], np.float32).reshape(800, 520, 4) for p_ in paths]
    out = bpy.data.images.new("o", 520 * 4, 800)
    out.pixels.foreach_set(np.concatenate(imgs, 1).ravel())
    out.filepath_raw = str(ROOT / "renders" / f"{CHAR}_rig_overlay.png")
    out.file_format = "PNG"
    out.save()
    print("OVERLAY", out.filepath_raw)
