"""P4.2 / P5.1: seat a dressed goose on the rigged bike by contact (analytic two-bone IK).

  blender -b --factory-startup --python scripts/ride_fit.py -- --char outfit_male --seat Captain \
      --scales 0.62,0.68,0.8,1.0 [--theta 0] [--tag p42]

Per bike scale k (bike_rig object scale; the goose is never scaled, D1):
- Hips: the goose is translated so the hip joints sit HIP_UP above the saddle socket (then corrected so the
  lowest seated body / breeches point just touches the saddle top);
- feet: the ball of each foot (ToeBase head) on its PedalPin, sole flat but toes TOE_DOWN deg down;
  thigh/shin by two-bone IK, knees forward; legs that can't reach are reported (reach = dist / (thigh + shin));
- torso: the smallest forward lean (Spine, Spine1, Spine2) that lets both wrists reach the grips with the
  elbows bent; neck counter-rotates and the head keeps its rest orientation (upright, looking ahead);
- arms: two-bone IK to a wrist point just behind each grip, elbows out and down; hands aimed forward.
Crank angle --theta (rad, the bike's Pedal clip convention; 0 = captain left pedal up).
--stretch auto|<f>: lengthen thigh + shin by f (pose scale along the bone; feet unscaled) so the legs reach at
  a bike scale too big for them ("auto": just enough for LEG_REACH). --standing also renders the goose
  standing, unstretched vs stretched (what permanently longer legs would look like off the bike).
--bike <tag>: seat on out/bike/bike_rigged_<tag>.blend (make_bike.py --tag, e.g. goosefit24) instead of the P4.1 bike.
--base <blend>: start from an earlier fit scene (e.g. the captain's), so both geese ride in the renders.
--clips (P5.1-P5.4; one scale): bake the riding clips by the same IK and export out/<char>-goose/<char>_rider.glb
  (the dressed goose + its old clips + these; armature space, so the game places the goose by its hips on the socket):
  Pedal_<seat>    24 frames = one crank turn (time = crank angle / 2pi, the bike's Pedal clip); legs, feet, cloth chains
  Ride_<seat>     upper body seated, hands on the grips (2 keys)
  Lean_L_<seat> / Lean_R_<seat>   torso rolled SIDE_LEAN to the rider's left / right, head level, hands re-gripped
  Players blend Ride / Lean by lean input on the upper-body bones and play Pedal on the lower body.
Writes renders/_tmp/fit_<tag>_<k>_<view>.png, out/bike/fit_<char>_<seat>_<tag>.json.
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = arg("--char", "outfit_male")
SEAT = arg("--seat", "Captain")
SCALE_ARGS = arg("--scales", "auto,1.0").split(",")
SCALES = [float(x) for x in SCALE_ARGS if x != "auto"]
THETA = arg("--theta", 0.0)
TAG = arg("--tag", "fit")
BIKE_TAG = arg("--bike", "")
BIKE_SFX = f"_{BIKE_TAG}" if BIKE_TAG else ""
BASE = arg("--base", "")
STRETCH_ARG = arg("--stretch", "1")
STANDING = "--standing" in argv
VIEWS = (("side", 90, 0), ("front", 0, 0), ("q34", 40, 15), ("rq34", 215, 20), ("top", 120, 55))
HIP_UP = 0.11          # hip joints above the saddle top (the crotch is 0.14 below the hip joint)
LEG_REACH = 0.95       # "auto" scale: hip-to-ankle / (thigh + shin) at the bottom of the stroke
ARM_REACH = 0.90       # shoulder-to-wrist / (arm + forearm): bars are raised until both wrists reach
MAX_BAR_RAISE = arg("--max-bar-raise", 0.35)   # m; beyond this the bars stay put (goose-fit bikes: 0, the design is the fit)
LEAN = arg("--lean", 15.0)   # torso forward lean, deg (Spine + Spine1 + Spine2)
TOE_DOWN = 12.0        # deg: foot pitched toes-down about the ball of the foot
SIDE_LEAN = 20.0       # deg: Lean_L / Lean_R torso roll (Spine, Spine1, Spine2 a third each; neck gives some back)
CLIPS = "--clips" in argv
NCLIP = 24
HAND_CURL = 25.0       # deg: hand hangs down over the grip, tip curled inward under it (handshake grip)
PALM_AT = 0.6          # grip crosses the palm this far down the hand (fraction of the hand bone)
PALM_OFF = 0.03        # m: grip centre this far inboard of the hand bone (palm surface + grip radius)
CR = "F" if SEAT == "Captain" else "R"
GR = "C" if SEAT == "Captain" else "S"
OUT = ROOT / "out" / "bike"
TMP = ROOT / "renders" / "_tmp"
TMP.mkdir(parents=True, exist_ok=True)

# ---- scene: bike + goose -----------------------------------------------------------------------------
bpy.ops.wm.open_mainfile(filepath=str(ROOT / BASE) if BASE else str(OUT / f"bike_rigged{BIKE_SFX}.blend"))
with bpy.data.libraries.load(str(ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_dressed.blend")) as (src, dst):
    dst.objects = list(src.objects)
goose_objs = [o for o in dst.objects if o is not None and o.type in ("MESH", "ARMATURE")]
for o in goose_objs:
    bpy.context.scene.collection.objects.link(o)
rig = next(o for o in goose_objs if o.type == "ARMATURE")
GOBJ = {o.name.split(".")[0]: o for o in goose_objs}   # (a second goose's objects get ".001" names)
for o in goose_objs:            # skinned meshes must ride with the rig object (an unparented armature-modifier
    if o.type == "MESH" and o.parent is None:      # mesh ignores rig.location: the deform cancels the object move)
        o.parent = rig
        o.matrix_parent_inverse = rig.matrix_world.inverted()
for o in goose_objs:                                   # all pieces worn: layered sub-meshes hidden (as the game)
    if o.type == "MESH" and "__" in o.name:
        o.hide_render = o.hide_viewport = True
bike = bpy.data.objects["bike_rig"]
chains = json.loads((ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_cloth_chains.json").read_text(encoding="utf-8"))
DRAPE = chains["drape"]
pbs = rig.pose.bones
bones = rig.data.bones
for pb in pbs:
    pb.rotation_mode = "XYZ"
STRETCH = {"f": 1.0}
for s_ in ("Left", "Right"):                          # stretch the leg bones without scaling the children
    for b in (f"{s_}Leg", f"{s_}Foot"):
        bones[b].inherit_scale = "NONE"


def blen(b):
    return bones[b].length * (STRETCH["f"] if b.endswith("UpLeg") or b.endswith("Leg") else 1.0)


def upd():
    bpy.context.view_layer.update()


def bw(name, part="head"):
    """Bike bone world position (sockets included)."""
    pb = bike.pose.bones[name]
    return bike.matrix_world @ (pb.head if part == "head" else pb.tail)


def gw(name, part="head"):
    pb = pbs[name]
    return rig.matrix_world @ (pb.head if part == "head" else pb.tail)


def aim(name, direction):
    """Rotate a goose bone about its head so it points along a world direction (rig has no rotation)."""
    pb = pbs[name]
    upd()
    cur = pb.matrix.copy()
    R = cur.to_3x3().col[1].normalized().rotation_difference(Vector(direction).normalized()).to_matrix()
    new = (R @ cur.to_3x3()).to_4x4()
    new.translation = cur.translation
    pb.matrix = new
    upd()


def two_bone(b1, b2, target, pole):
    """Analytic IK: b1 head fixed, b2 tail -> target (clamped), bend toward pole. Returns reach ratio."""
    A = gw(b1)
    l1, l2 = blen(b1), blen(b2)
    d_vec = target - A
    d = d_vec.length
    reach = d / (l1 + l2)
    d = min(d, (l1 + l2) * 0.999)
    u = d_vec.normalized()
    w = (pole - pole.dot(u) * u).normalized()
    ca = max(-1.0, min(1.0, (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d)))
    J = A + l1 * (ca * u + math.sqrt(1 - ca * ca) * w)
    aim(b1, J - A)
    aim(b2, (A + u * d) - gw(b2))
    return reach


def apply_follow():
    """D12 cloth-chain rule (same as dress_goose.py / the game)."""
    hq = (pbs["Hips"].matrix @ bones["Hips"].matrix_local.inverted()).to_quaternion()
    for c in chains["chains"]:
        tq = (pbs[c["thigh"]].matrix.to_3x3().normalized() @
              bones[c["thigh"]].matrix_local.to_3x3().inverted()).to_quaternion()
        for j, bn in enumerate(c["bones"]):
            q = hq.slerp(tq, c["follow"] * DRAPE[j])
            pb = pbs[bn]
            head = pb.matrix.to_translation()
            pb.matrix = Matrix.Translation(head) @ q.to_matrix().to_4x4() @ bones[bn].matrix_local.to_3x3().to_4x4()
            upd()


def reset():
    for pb in pbs:
        pb.matrix_basis = Matrix.Identity(4)
    for s_ in ("Left", "Right"):
        for b in (f"{s_}UpLeg", f"{s_}Leg"):
            pbs[b].scale = (1.0, STRETCH["f"], 1.0)
    upd()


def set_crank(theta):
    for b in ("Crank_F", "Crank_R"):
        bike.pose.bones[b].rotation_euler = (0, theta, 0)
    for b in ("Pedal_FL", "Pedal_FR", "Pedal_RL", "Pedal_RR"):
        bike.pose.bones[b].rotation_euler = (0, -theta, 0)
    upd()


hip_mid_rest = (bones["LeftUpLeg"].head_local + bones["RightUpLeg"].head_local) / 2
head_rest_rot = bones["Head"].matrix_local.to_3x3()
foot_rest = {s: bones[f"{s}ToeBase"].head_local - bones[f"{s}Foot"].head_local for s in ("Left", "Right")}


SEAT_PROBE = {}                                       # rest-pose seat region (crotch + buttocks), by vertex index
for n in ("body", "breeches", "skirt"):
    o = GOBJ.get(n)
    if o is not None:
        v = np.array([x.co[:] for x in o.data.vertices])
        hz, hy = hip_mid_rest.z, hip_mid_rest.y
        SEAT_PROBE[n] = np.where((np.abs(v[:, 0]) < 0.10) & (np.abs(v[:, 1] - hy) < 0.14) &
                                 (v[:, 2] > hz - 0.22) & (v[:, 2] < hz))[0]


def seat_body_low():
    """Lowest posed point of the rest-pose seat region (thighs excluded by construction)."""
    dg = bpy.context.evaluated_depsgraph_get()
    lows = []
    for n, idx in SEAT_PROBE.items():
        o = GOBJ[n]
        me = o.evaluated_get(dg).to_mesh()
        co = np.array([me.vertices[i].co[:] for i in idx])
        o.evaluated_get(dg).to_mesh_clear()
        if len(co):
            lows.append((np.array(o.matrix_world) @ np.c_[co, np.ones(len(co))].T)[2].min())
    return float(min(lows)) if lows else float("nan")


BIKE_REP = json.loads((OUT / f"bike_rig{BIKE_SFX}.json").read_text(encoding="utf-8"))
_sv = Vector(BIKE_REP["pivots"]["steer_hi"]) - Vector(BIKE_REP["pivots"]["steer_lo"])
BAR_AXIS = {"C": _sv.normalized(), "S": Vector((0, 0, 1))}          # captain: quill along the steer axis
BAR_PARTS = {"C": ["NurbsPath", "Cylinder.012", "Tee Joint.001", "Cylinder.017"],
             "S": ["NurbsPath.009", "Cylinder.019"]}
BAR_BASE = {"C": Vector(BIKE_REP["pivots"]["steer_hi"]), "S": None}
BAR_ORIG = {n: bpy.data.objects[n + "_cycle_0"].data.copy() for g in BAR_PARTS.values() for n in g}


def raise_bars(gr, d_bike):
    """Fit the bars: move bar + grips + stem up the stem axis by d_bike (bike units), riser tube in the gap."""
    for n in BAR_PARTS[gr]:
        o = bpy.data.objects[n + "_cycle_0"]
        name = o.data.name
        o.data = BAR_ORIG[n].copy()
        o.data.name = name
        o.data.transform(Matrix.Translation(BAR_AXIS[gr] * d_bike))
    old = bpy.data.objects.get(f"riser_{gr}")
    if old:
        bpy.data.objects.remove(old)
    if d_bike <= 0.002 or BAR_BASE[gr] is None:
        return
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.0125, radius2=0.0125, depth=d_bike + 0.03)
    me = bpy.data.meshes.new(f"riser_{gr}")
    bm.to_mesh(me)
    bm.free()
    a = BAR_AXIS[gr]
    me.transform(Matrix.Translation(BAR_BASE[gr] + a * (d_bike / 2 + 0.01)) @
                 Vector((0, 0, 1)).rotation_difference(a).to_matrix().to_4x4())
    mat = bpy.data.materials.get("riser")
    if mat is None:
        mat = bpy.data.materials.new("riser")
        mat.diffuse_color = (0.03, 0.03, 0.03, 1)
        bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.node_tree else None
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.02, 0.02, 0.02, 1)
            bsdf.inputs["Metallic"].default_value = 0.6
            bsdf.inputs["Roughness"].default_value = 0.35
    me.materials.append(mat)
    o = bpy.data.objects.new(f"riser_{gr}", me)
    bpy.context.scene.collection.objects.link(o)
    o.parent = bike
    o.parent_type = "BONE"
    o.parent_bone = "Steer" if gr == "C" else "Bike_root"
    o.matrix_world = bike.matrix_world.copy()
    upd()


HAND_REST = {s: bones[f"{s}Hand"].matrix_local.to_3x3() for s in ("Left", "Right")}


def hand_dir(side):
    sx = 1 if side == "L" else -1
    c = math.radians(HAND_CURL)
    return Vector((-sx * math.sin(c), 0, -math.cos(c)))


def wrist_target(side, lift):
    """Hands: the swept-back grips run fore-aft, the mitt-hands' palms face inward -> handshake grip: hand hangs
    down over the grip with the grip across the palm, wrist above and outboard of it."""
    sx = 1 if side == "L" else -1
    g = bw(f"Grip_{GR}_{side}") + BAR_AXIS[GR] * lift
    L = bones[("Left" if side == "L" else "Right") + "Hand"].length
    return g, g - hand_dir(side) * (PALM_AT * L) + Vector((sx * PALM_OFF, 0, 0))


def roll_world(b, deg):
    """Rotate a pose bone about the world forward axis (+ = top to the rider's left, +X) through its head."""
    pb = pbs[b]
    h = pb.matrix.translation.copy()
    pb.matrix = Matrix.Translation(h) @ Matrix.Rotation(math.radians(deg), 4, "Y") @ Matrix.Translation(-h) @ pb.matrix
    upd()


def set_torso(phi, roll=0.0):
    reset()
    for b in ("Spine", "Spine1", "Spine2"):
        pbs[b].rotation_euler.x = math.radians(phi / 3)
    for b, f in (("Neck", 0.4), ("Neck1", 0.3)):
        pbs[b].rotation_euler.x = -math.radians(phi * f)
    upd()
    if roll:
        for b in ("Spine", "Spine1", "Spine2"):
            roll_world(b, roll / 3)
        roll_world("Neck", -roll * 0.35)
    pb = pbs["Head"]                                   # head upright: rest world orientation
    m = head_rest_rot.to_4x4()
    m.translation = pb.matrix.translation
    pb.matrix = m
    upd()


def arm_reach(lift):
    return max((wrist_target(side, lift)[1] - gw(f"{s}Arm")).length /
               (bones[f"{s}Arm"].length + bones[f"{s}ForeArm"].length) for s, side in (("Left", "L"), ("Right", "R")))


def place_hips():
    seat = bw("Seat_" + SEAT)
    rig.location = seat + Vector((0, 0, HIP_UP)) - hip_mid_rest
    upd()


def ankle_target(s, side):
    pin = bw(f"PedalPin_{CR}{side}")
    Rt = Matrix.Rotation(math.radians(TOE_DOWN), 3, "X")            # toes down: heel (ankle) rises
    sole = bones[f"{s}ToeBase"].head_local.z                         # ball height above the sole
    return pin + Vector((0, 0, sole)) - Rt @ foot_rest[s], Rt, pin + Vector((0, 0, sole))


def leg_reach_bottom(k):
    """Bottom-of-stroke reach (theta = 0: right pedal down) for bike scale k, hips placed, no pose."""
    bike.scale = (k, k, k)
    set_crank(0.0)
    place_hips()
    reset()
    s_, sd = ("Right", "R") if SEAT == "Captain" else ("Left", "L")    # (theta 0: stoker left pedal down, D15)
    at = ankle_target(s_, sd)[0]
    return (at - gw(f"{s_}UpLeg")).length / (blen(f"{s_}UpLeg") + blen(f"{s_}Leg"))


def pose_on_bike(lean, roll=0.0):
    rep = {"lean_deg": lean}
    place_hips()
    set_torso(lean, roll)
    lift = 0.0
    while arm_reach(lift) > ARM_REACH and lift < MAX_BAR_RAISE:
        lift += 0.005
    rep["bar_raise_m"] = round(lift, 3)
    for s, side, sx in (("Left", "L", 1), ("Right", "R", -1)):
        g, wt = wrist_target(side, lift)
        rep[f"arm_{side}"] = round(two_bone(f"{s}Arm", f"{s}ForeArm", wt, Vector((sx * 0.8, 0.4, -1.0))), 3)
        rest = HAND_REST[s]
        R = rest.col[1].normalized().rotation_difference(hand_dir(side)).to_matrix()   # palm stays inward
        hb = pbs[f"{s}Hand"]
        m = (R @ rest).to_4x4()
        m.translation = hb.matrix.translation
        hb.matrix = m
        upd()
        rep[f"grip_err_mm_{side}"] = round((gw(f"{s}Hand") + hand_dir(side) * PALM_AT * bones[f"{s}Hand"].length
                                            + Vector((-sx * PALM_OFF, 0, 0)) - g).length * 1000, 1)
    for s, side, sx in (("Left", "L", 1), ("Right", "R", -1)):
        at, Rt, ball = ankle_target(s, side)
        rep[f"leg_{side}"] = round(two_bone(f"{s}UpLeg", f"{s}Leg", at, Vector((sx * 0.15, -1.0, 0.1))), 3)
        fm = pbs[f"{s}Foot"]
        m = (Rt @ bones[f"{s}Foot"].matrix_local.to_3x3()).to_4x4()
        m.translation = fm.matrix.translation
        fm.matrix = m
        upd()
        rep[f"foot_err_mm_{side}"] = round((gw(f"{s}ToeBase") - ball).length * 1000, 1)
    apply_follow()
    seat = bw("Seat_" + SEAT)
    rep["seat_probe_mm"] = round((seat_body_low() - seat.z) * 1000, 1)   # < 0: flesh sinks into the saddle
    rep["hip_above_saddle_m"] = HIP_UP
    return rep


# ---- render setup ------------------------------------------------------------------------------------
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
if sc.world is None or sc.world.name != "w":
    sc.world = bpy.data.worlds.new("w")
sc.world.color = (0.93, 0.92, 0.9)
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.85, 0.84, 0.82, 1)
sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
sun = bpy.data.objects.get("sun")
if sun is None:
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.5
    sun.rotation_euler = (math.radians(50), 0, math.radians(35))
    sc.collection.objects.link(sun)
cam = bpy.data.objects.get("cam")
if cam is None:
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    sc.collection.objects.link(cam)
sc.camera = cam
W, H = 900, 700
sc.render.resolution_x, sc.render.resolution_y = W, H


def shoot(path, az, el, span, tgt):
    a, e = math.radians(az), math.radians(el)
    d = Vector((math.cos(e) * math.sin(a), -math.cos(e) * math.cos(a), math.sin(e)))
    cam.location = tgt + d * 12
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = span
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


report = {}
if "auto" in SCALE_ARGS:                       # bisect k: bottom-of-stroke leg reach == LEG_REACH
    lo_k, hi_k = 0.3, 1.5
    for _ in range(30):
        mid = (lo_k + hi_k) / 2
        lo_k, hi_k = (mid, hi_k) if leg_reach_bottom(mid) < LEG_REACH else (lo_k, mid)
    SCALES = [round(mid, 3) if a == "auto" else float(a) for a in SCALE_ARGS]
    print("AUTO k", SCALES)
for k in SCALES:
    if STRETCH_ARG == "auto":
        STRETCH["f"] = 1.0
        STRETCH["f"] = max(1.0, leg_reach_bottom(k) / LEG_REACH)
    else:
        STRETCH["f"] = float(STRETCH_ARG)
    bike.scale = (k, k, k)
    set_crank(THETA)
    raise_bars(GR, 0.0)
    rep = pose_on_bike(LEAN)
    raise_bars(GR, rep["bar_raise_m"] / k)
    rep["k"] = k
    rep["leg_stretch"] = round(STRETCH["f"], 3)
    rep["wheel_m"] = round(BIKE_REP["wheel_m"] * k, 3)
    rep["bike_length_m"] = round(BIKE_REP["length_m"] * k, 3)
    rep["saddle_top_m"] = round(bw("Seat_" + SEAT).z, 3)
    rep["grip_z_m"] = round(wrist_target("L", rep["bar_raise_m"])[0].z, 3)
    report[str(k)] = rep
    print("FIT", k, json.dumps(rep))
    tgt = Vector((0, 0, 0.98))                    # frame ground to hat top (900x700: height = 0.78 span)
    span = max(BIKE_REP["length_m"] * k + 0.5, 2.7)
    for view, az, el in VIEWS:
        shoot(TMP / f"fit_{TAG}_{k}_{view}.png", az, el, span if view != "front" else 2.7, tgt)
if STANDING:                                  # off the bike: rest pose, original legs vs the stretch
    f_ride = STRETCH["f"]
    for o in sc.objects:
        if o.type in ("MESH", "ARMATURE") and o not in goose_objs and o.name != "riser_C":
            o.hide_render = True
    for o in [x for x in sc.objects if x.name.startswith("riser_")]:
        o.hide_render = True
    for f in (1.0, f_ride):
        STRETCH["f"] = f
        rig.location = (0, 0, 0)
        reset()
        rig.location.z = bones["RightToeBase"].head_local.z - gw("RightToeBase").z
        upd()
        rep_h = gw("Head", "tail").z
        print("STAND", f, "head tail z", round(rep_h, 3))
        for view, az, el in (("side", 90, 0), ("front", 0, 0)):
            shoot(TMP / f"stand_{TAG}_{f:.2f}_{view}.png", az, el, 2.7, Vector((0, 0, 1.0)))
        report[f"stand_{f:.2f}"] = {"stretch": round(f, 3), "head_top_z_m": round(rep_h, 3)}
# ---- P5 clips ----------------------------------------------------------------------------------------
UPPER = ("Spine", "Spine1", "Spine2", "Neck", "Neck1", "Neck2", "Neck3", "Head", "LeftShoulder", "LeftArm",
         "LeftForeArm", "LeftHand", "RightShoulder", "RightArm", "RightForeArm", "RightHand")
LOWER = tuple(f"{s_}{b}" for s_ in ("Left", "Right") for b in ("UpLeg", "Leg", "Foot", "ToeBase")) + \
    tuple(b for c in chains["chains"] for b in c["bones"])


def bake(name, frames, bset):
    """frames: list of callables posing the goose; keys bset (Euler, continuous) at 0..len-1 -> NLA track."""
    act = bpy.data.actions.new(name)
    rig.animation_data_create()
    rig.animation_data.action = act
    prev = {}
    for f, pose in enumerate(frames):
        pose()
        for b in bset:
            pb = pbs[b]
            mb = pb.matrix_basis
            e = mb.to_euler("XYZ", prev[b]) if b in prev else mb.to_euler("XYZ")
            prev[b] = e
            pb.rotation_euler = e
            pb.location = mb.to_translation()
            pb.keyframe_insert("rotation_euler", frame=f, group=b)
            pb.keyframe_insert("location", frame=f, group=b)
    act.use_fake_user = True
    rig.animation_data.action = None
    tr = rig.animation_data.nla_tracks.new()
    tr.name = name
    st = tr.strips.new(name, 0, act)
    st.extrapolation = "NOTHING"
    tr.mute = True
    return act


if CLIPS:
    assert len(SCALES) == 1, "--clips: one bike scale"
    k = SCALES[0]
    bike.scale = (k, k, k)
    sc.render.fps = 24
    sc.frame_start = 0
    clip_rep = {}

    def pedal_frame(f):
        def go():
            set_crank(2 * math.pi * f / NCLIP)
            r = pose_on_bike(LEAN)
            clip_rep[f] = max(r["foot_err_mm_L"], r["foot_err_mm_R"], r["grip_err_mm_L"], r["grip_err_mm_R"])
        return go

    bake(f"Pedal_{SEAT}", [pedal_frame(f) for f in range(NCLIP + 1)], LOWER)

    def still(roll):
        def go():
            set_crank(0.0)
            r = pose_on_bike(LEAN, roll)
            clip_rep[f"roll{roll}"] = max(r["grip_err_mm_L"], r["grip_err_mm_R"])
        return go

    bake(f"Ride_{SEAT}", [still(0.0)] * 2, UPPER)
    bake(f"Lean_L_{SEAT}", [still(SIDE_LEAN)] * 2, UPPER)
    bake(f"Lean_R_{SEAT}", [still(-SIDE_LEAN)] * 2, UPPER)
    report["clips"] = {"contact_err_mm_max": max(clip_rep.values()), "frames": NCLIP + 1, "side_lean_deg": SIDE_LEAN}
    print("CLIPS", json.dumps(report["clips"]))
    # export the goose alone: rig back at the origin, rest pose, all pieces (layered ones too)
    sc.frame_end = NCLIP
    rig.location = (0, 0, 0)
    reset()
    hidden = [o for o in goose_objs if o.hide_viewport]
    for o in hidden:
        o.hide_viewport = False
    bpy.ops.object.select_all(action="DESELECT")
    for o in goose_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = rig
    out_glb = ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_rider.glb"
    bpy.ops.export_scene.gltf(filepath=str(out_glb), export_format="GLB", use_selection=True, export_skins=True,
                              export_tangents=True, export_animations=True, export_animation_mode="NLA_TRACKS",
                              export_yup=True)
    sys.path.insert(0, str(Path(__file__).parent))
    from glb_fix_tangents import main as fix_tangents  # noqa: E402
    fix_tangents(str(out_glb))
    for o in hidden:
        o.hide_viewport = True
    set_crank(0.0)                            # back on the bike for the saved scene (--base for the next rider)
    pose_on_bike(LEAN)
    print("RIDER", out_glb)
(OUT / f"fit_{CHAR}_{SEAT}_{TAG}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"fit_{CHAR}_{SEAT}_{TAG}.blend"), compress=True)
print("DONE")
