"""Goose Studio body clips (docs/goose-studio-plan.md S3): walk, turns, gestures, baked on a DRESSED goose.

  blender -b --factory-startup --python scripts/show_clips.py -- --char outfit_male_victorian --dressed-tag full \
      --name goose_captain_fancy [--only walk,turn_L] [--render]

Writes out/show/<name>_clips.glb (the armature + clips only; no meshes) and out/show/<name>_clips.json (clip
metadata: duration, loop, root motion, turn yaw, footfalls). The studio plays these clips on the in-game rider GLB of
the same goose (tandem-3d/goose/<name>.glb) by bone name, so each goose gets its own bake (leg lengths, heels).

Posing is parametric: every frame is a parameter set P (pelvis offset / tilt, feet in object space, spine bend,
neck / head, wrist targets, hat lift, tail) solved by world-space aims + analytic two-bone IK, so feet stay planted
whatever the body does. Face bones (eyes, lids, jaw, tongue) are never keyed: the studio's face layer owns them.

Root motion: walk clips move the Hips forward for real (feet planted in object space); the studio strips the Hips
forward channel and moves the goose instead. Turns rotate the whole goose about the object origin; at the end of a
turn clip the pose equals the rest pose rotated by "yaw_end" (the studio then turns the object and plays idle).
Conventions: Blender object space, the goose faces -Y, its left is +X, Z up. Angles in degrees.
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
CHAR = arg("--char", "outfit_male_victorian")
DTAG = arg("--dressed-tag", "")
DPRE = f"{CHAR}_{DTAG}" if DTAG else CHAR
NAME = arg("--name", DPRE)
ONLY = [s for s in arg("--only", "").split(",") if s]
RENDER = "--render" in argv
FPS = 24
OUT = ROOT / "out" / "show"
OUT.mkdir(parents=True, exist_ok=True)
FACE = {"Jaw", "Tongue", "LeftEye", "RightEye", "LeftEyelidUpper", "LeftEyelidLower", "RightEyelidUpper",
        "RightEyelidLower"}

bpy.ops.wm.open_mainfile(filepath=str(ROOT / "out" / f"{CHAR}-goose" / f"{DPRE}_dressed.blend"))
sc = bpy.context.scene
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
assert rig.location.length < 1e-6, "rig expected at the origin"
pbs = rig.pose.bones
bones = rig.data.bones
chains = json.loads((ROOT / "out" / f"{CHAR}-goose" / f"{DPRE}_cloth_chains.json").read_text(encoding="utf-8"))
DRAPE = chains.get("drape", [1.0, 0.45, 0.15])
rig.animation_data_create()
rig.animation_data.action = None
for t in list(rig.animation_data.nla_tracks):
    rig.animation_data.nla_tracks.remove(t)
for a in list(bpy.data.actions):
    bpy.data.actions.remove(a)
for pb in pbs:
    pb.rotation_mode = "XYZ"
BODY = [b.name for b in bones if b.name not in FACE]
KEY_LOC = {"Hips", "HatSocket"}

# ---- rest measurements ------------------------------------------------------------------------------
H0 = bones["Hips"].head_local.copy()
ANK0 = {s: bones[f"{s}Foot"].head_local.copy() for s in ("Left", "Right")}
SX = {"Left": 1.0, "Right": -1.0}


def blen(b):
    return bones[b].length


def upd():
    bpy.context.view_layer.update()


def reset():
    for pb in pbs:
        pb.matrix_basis = Matrix.Identity(4)
    upd()


def gw(name, part="head"):
    pb = pbs[name]
    return (pb.head if part == "head" else pb.tail).copy()


def rot3(axis, deg):
    return Matrix.Rotation(math.radians(deg), 3, Vector(axis).normalized())


def set_world(name, head, rot):
    pbs[name].matrix = Matrix.Translation(head) @ rot.to_4x4()
    upd()


def rot_world(name, axis, deg):
    """Rotate a bone about its own head by a world (object-space) axis."""
    if abs(deg) < 1e-9:
        return
    m = pbs[name].matrix
    set_world(name, m.to_translation(), rot3(axis, deg) @ m.to_3x3())


def aim(name, direction):
    pb = pbs[name]
    cur = pb.matrix.copy()
    R = cur.to_3x3().col[1].normalized().rotation_difference(Vector(direction).normalized()).to_matrix()
    set_world(name, cur.to_translation(), R @ cur.to_3x3())


def two_bone(b1, b2, target, pole):
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


def delta_rot(name):
    """World rotation of a bone relative to its rest orientation."""
    return pbs[name].matrix.to_3x3().normalized() @ bones[name].matrix_local.to_3x3().inverted()


def apply_follow():
    """D12 cloth-chain rule (dress_goose.py / ride_fit.py): standing follow values from the chains json."""
    hq = delta_rot("Hips").to_quaternion()
    for c in chains["chains"]:
        tq = delta_rot(c["thigh"]).to_quaternion()
        for j, bn in enumerate(c["bones"]):
            q = hq.slerp(tq, c["follow"] * c.get("drape", DRAPE)[j])
            head = pbs[bn].matrix.to_translation()
            set_world(bn, head, q.to_matrix() @ bones[bn].matrix_local.to_3x3())


# ---- the parametric pose ------------------------------------------------------------------------------
REST_FOOT = {s: (ANK0[s].copy(), 0.0, 0.0) for s in ("Left", "Right")}   # (object-space ankle, yaw, toe pitch)


def default_params():
    return {"yaw": 0.0, "hips_yaw": 0.0, "dx": 0.0, "df": 0.0, "dz": 0.0, "pitch": 0.0, "roll": 0.0,
            "bend": 0.0, "side": 0.0, "twist": 0.0, "neck_pitch": 0.0, "neck_yaw": 0.0,
            "head_pitch": 0.0, "head_yaw": 0.0, "head_roll": 0.0, "tail_yaw": 0.0, "tail_pitch": 0.0,
            "hat_lift": 0.0, "hat_fwd": 0.0, "hat_tilt": 0.0,
            "swingL": 0.0, "swingR": 0.0, "outL": 0.0, "outR": 0.0,
            "armL": None, "armR": None, "handL": None, "handR": None,
            "footL": REST_FOOT["Left"], "footR": REST_FOOT["Right"]}


def arm_target(side, spec, P):
    """World wrist target for an arm spec at the current body pose.
    None            rest arm (rides the torso) swung by swing<s> (deg, + = forward) and out<s> (deg, + = away)
    ("sh", v)       shoulder-relative, in the torso frame (v in the rest frame: x out = +x for Left, -y forward)
    ("head", v)     relative to the Head bone's head (the face front: the bone runs up-back), in the head frame
    ("hat", v)      relative to the HatSocket head (crown of the head, brim level), in the head frame
    """
    s = side
    R_body = delta_rot("Spine2")
    sh = gw(f"{s}Arm")
    if spec is None:
        rest = bones[f"{s}ForeArm"].tail_local - bones[f"{s}Arm"].head_local
        sw = P["swingL" if s == "Left" else "swingR"]
        out = P["outL" if s == "Left" else "outR"]
        v = rot3((1, 0, 0), sw) @ rot3((0, -1, 0), -SX[s] * out) @ rest
        return sh + R_body @ v
    kind, v = spec
    v = Vector(v)
    if kind == "sh":
        return sh + R_body @ v
    if kind == "head":
        return gw("Head") + delta_rot("Head") @ v
    if kind == "hat":                  # relative to the hat's seat on the head (HatSocket head = brim level)
        return gw("HatSocket") + delta_rot("Head") @ v
    raise ValueError(kind)


def solve(P):
    """Pose the goose from parameter set P (see default_params)."""
    reset()
    Rz = rot3((0, 0, 1), P["yaw"])
    Xh = Rz @ Vector((1, 0, 0))
    Yh = Rz @ Vector((0, 1, 0))
    # pelvis: tilt about its head in the heading frame, heading about the object origin
    Rh = rot3((0, 0, 1), P["yaw"] + P["hips_yaw"]) @ rot3((1, 0, 0), P["pitch"]) @ rot3((0, 1, 0), P["roll"])
    head = Rz @ (H0 + Vector((P["dx"], -P["df"], P["dz"])))
    set_world("Hips", head, Rh @ bones["Hips"].matrix_local.to_3x3())
    # torso
    for b in ("Spine", "Spine1", "Spine2"):
        rot_world(b, (0, 0, 1), P["twist"] / 3 - (P["hips_yaw"] / 3))
        rot_world(b, Xh, P["bend"] / 3 - P["pitch"] / 3 * 0.5)
        rot_world(b, Yh, P["side"] / 3 - P["roll"] / 3)
    for b in ("Neck", "Neck1", "Neck2", "Neck3"):
        rot_world(b, Xh, P["neck_pitch"] / 4 - P["bend"] / 4 * 0.85)
        rot_world(b, (0, 0, 1), P["neck_yaw"] / 4)
    rot_world("Head", (0, 0, 1), P["head_yaw"])
    rot_world("Head", delta_rot("Head") @ Vector((1, 0, 0)), P["head_pitch"])
    rot_world("Head", delta_rot("Head") @ Vector((0, -1, 0)), P["head_roll"])
    # arms
    reach = {}
    for s in ("Left", "Right"):
        t = arm_target(s, P["armL" if s == "Left" else "armR"], P)
        pole = delta_rot("Spine2") @ Vector((SX[s] * 0.6, 0.7, -0.3))
        reach[s] = two_bone(f"{s}Arm", f"{s}ForeArm", t, pole)
        hd = P["handL" if s == "Left" else "handR"]
        if hd is not None:
            aim(f"{s}Hand", Vector(hd))
    # legs + feet (object-space ankle targets; knees over the toes)
    for s in ("Left", "Right"):
        pos, fy, fp = P["footL" if s == "Left" else "footR"]
        Rf = rot3((0, 0, 1), fy)
        pole = Rf @ Vector((SX[s] * 0.15, -1.0, 0.0))
        reach[s + "Leg"] = two_bone(f"{s}UpLeg", f"{s}Leg", Vector(pos), pole)
        Xf = Rf @ Vector((1, 0, 0))
        set_world(f"{s}Foot", gw(f"{s}Foot"), rot3(Xf, fp) @ Rf @ bones[f"{s}Foot"].matrix_local.to_3x3())
    rot_world("Tail", (0, 0, 1), P["tail_yaw"])
    rot_world("Tail", Xh, P["tail_pitch"])
    if "HatSocket" in pbs and (P["hat_lift"] or P["hat_fwd"] or P["hat_tilt"]):
        m = pbs["HatSocket"].matrix
        hx = delta_rot("Head") @ Vector((1, 0, 0))
        hf = delta_rot("Head") @ Vector((0, -1, 0))
        set_world("HatSocket", m.to_translation() + Vector((0, 0, P["hat_lift"])) + hf * P["hat_fwd"],
                  rot3(hx, P["hat_tilt"]) @ m.to_3x3())
    apply_follow()
    return reach


# ---- keyframed parameter clips ------------------------------------------------------------------------------
def smooth(u):
    u = max(0.0, min(1.0, u))
    return u * u * (3 - 2 * u)


class Blend:
    """An arm / hand spec halfway between two keys (resolved at the current pose by resolve_arms)."""

    def __init__(self, a, b, u):
        self.a, self.b, self.u = a, b, u


def lerp_params(a, b, u):
    out = {}
    for k in a:
        va, vb = a[k], b[k]
        if k in ("footL", "footR"):
            out[k] = (va[0].lerp(vb[0], u), va[1] + (vb[1] - va[1]) * u, va[2] + (vb[2] - va[2]) * u)
        elif k in ("armL", "armR", "handL", "handR"):
            out[k] = Blend(va, vb, u)
        else:
            out[k] = va + (vb - va) * u
    return out


def resolve_arms(P):
    """Solve with the start specs and with the end specs, then lerp the wrist targets and hand directions."""
    keys = ("armL", "armR", "handL", "handR")
    if not any(isinstance(P[k], Blend) for k in keys):
        return P
    got = {}
    for end in (0, 1):
        R = dict(P)
        for k in keys:
            if isinstance(P[k], Blend):
                R[k] = P[k].b if end else P[k].a
        solve(R)
        for s in ("Left", "Right"):
            got[("arm" + s[0], end)] = gw(f"{s}ForeArm", "tail")
            got[("hand" + s[0], end)] = pbs[f"{s}Hand"].matrix.to_3x3().col[1].normalized()
    Q = dict(P)
    for k in keys:
        u = P[k].u if isinstance(P[k], Blend) else 0.0
        v = got[(k, 0)].lerp(got[(k, 1)], u)
        Q[k] = ("abs", v) if k.startswith("arm") else v
    return Q


_arm_target = arm_target


def arm_target(side, spec, P):  # noqa: F811  (adds the "abs" kind used by resolve_arms)
    if isinstance(spec, tuple) and spec[0] == "abs":
        return Vector(spec[1])
    return _arm_target(side, spec, P)


def keyed(keys, t):
    """keys: [(t, overrides)] sorted; returns the eased parameter set at time t."""
    sets = [(kt, {**default_params(), **ov}) for kt, ov in keys]
    if t <= sets[0][0]:
        return sets[0][1]
    for (t0, a), (t1, b) in zip(sets, sets[1:]):
        if t <= t1:
            return lerp_params(a, b, smooth((t - t0) / (t1 - t0)))
    return sets[-1][1]


# ---- gait planner --------------------------------------------------------------------------------------
LIFT = 0.05          # m swing-foot lift
TOE_UP = -14.0       # deg toe pitch mid-swing
SWAY = 0.035         # m pelvis sway over the stance foot
ROLL = 5.0           # deg pelvis roll toward the stance foot
DROP = 0.025         # m pelvis lowered while walking (knees soft)
BOB = 0.012          # m extra drop in double support


class Feet:
    """Footstep timeline: events (side, t0, t1, end_pos(object space), end_yaw)."""

    def __init__(self, start, events):
        self.start = start          # {side: (pos, yaw)}
        self.events = sorted(events, key=lambda e: e[1])

    def at(self, side, t):
        pos, yaw = self.start[side]
        for s, t0, t1, p1, y1 in self.events:
            if s != side or t < t0:
                continue
            if t >= t1:
                pos, yaw = Vector(p1), y1
                continue
            u = (t - t0) / (t1 - t0)
            e = smooth(u)
            p = Vector(pos).lerp(Vector(p1), e)
            p.z += LIFT * math.sin(math.pi * u)
            return p, yaw + (y1 - yaw) * e, TOE_UP * math.sin(math.pi * u), True
        return Vector(pos), yaw, 0.0, False

    def swinging(self, side, t):
        return self.at(side, t)[3]

    def footfalls(self):
        return [(s, round(t1, 3)) for s, t0, t1, p, y in self.events]


def support_signal(feet, times, period=None, sigma=2.5):
    """+1 while the right foot swings (weight on the left), -1 while the left swings; gaussian-smoothed."""
    raw = np.array([(1.0 if feet.swinging("Right", t) else 0.0) - (1.0 if feet.swinging("Left", t) else 0.0)
                    for t in times])
    k = np.exp(-0.5 * (np.arange(-8, 9) / sigma) ** 2)
    k /= k.sum()
    if period:
        n = len(raw) - 1          # last frame == first frame of the next cycle
        base = raw[:n]
        ext = np.concatenate([base[-8:], base, base[:8]])
        sm = np.convolve(ext, k, "same")[8:8 + n]
        return np.append(sm, sm[0])
    ext = np.concatenate([np.full(8, raw[0]), raw, np.full(8, raw[-1])])
    return np.convolve(ext, k, "same")[8:-8]


def ank(side, fwd=0.0, x=0.0, yaw=0.0):
    """Rest ankle moved forward (object -Y) by fwd, out by x, the whole thing rotated by yaw about the origin."""
    p = ANK0[side] + Vector((SX[side] * x, -fwd, 0.0))
    return rot3((0, 0, 1), yaw) @ p


def hermite(t, D, d, v0, v1):
    """Position on [0, D] from 0 to d with start / end speeds v0, v1."""
    u = max(0.0, min(1.0, t / D))
    h10, h01, h11 = u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
    return h10 * D * v0 + h01 * d + h11 * D * v1


# walk cycle: period T, duty 0.6, each foot moves STRIDE per cycle; stance spans +-STRIDE*0.3 about the hips
T_WALK = 0.9
STRIDE = 0.48
V_WALK = STRIDE / T_WALK


def walk_body(P, s, t, w=1.0):
    """Common waddle overlay: sway/roll over the stance foot, bob, lean, counter-twist, arm swing, head bob."""
    P["dx"] += SWAY * s * w
    P["roll"] += ROLL * s * w
    P["dz"] += -(DROP + BOB * (1 - abs(s))) * w
    P["pitch"] += 4.0 * w
    P["hips_yaw"] += -5.0 * s * w
    P["twist"] += 4.0 * s * w
    P["tail_yaw"] += 12.0 * s * w
    P["swingL"] += 14.0 * s * w      # left arm forward while the left foot carries the weight (right leg swings)
    P["swingR"] += -14.0 * s * w
    P["outL"] += 6.0 * w
    P["outR"] += 6.0 * w
    P["neck_pitch"] += 3.0 * math.sin(4 * math.pi * t / T_WALK) * w
    return P


def gait_clip(feet, times, pelvis_df, weight=lambda t: 1.0, period=None, extra=None):
    sig = support_signal(feet, times, period)
    frames = []
    for i, t in enumerate(times):
        def go(t=t, s=sig[i]):
            P = default_params()
            P["df"] = pelvis_df(t)
            walk_body(P, s, t, weight(t))
            for side, k in (("Left", "footL"), ("Right", "footR")):
                pos, yaw, pitch, _ = feet.at(side, t)
                P[k] = (pos, yaw, pitch)
            if extra:
                extra(P, t)
            return solve(P)
        frames.append(go)
    return frames


def walk_loop():
    n = int(round(T_WALK * FPS))
    times = [i / FPS for i in range(n + 1)]
    v = V_WALK
    # left swings [0, 0.4T], right swings [0.5T, 0.9T]; plant = hips at landing + 0.3 * STRIDE
    lp0 = -0.3 * STRIDE
    rp0 = v * 0.9 * T_WALK + 0.3 * STRIDE - STRIDE
    feet = Feet({"Left": (ank("Left", lp0), 0.0), "Right": (ank("Right", rp0), 0.0)}, [
        ("Left", 0.0, 0.4 * T_WALK, ank("Left", lp0 + STRIDE), 0.0),
        ("Right", 0.5 * T_WALK, 0.9 * T_WALK, ank("Right", rp0 + STRIDE), 0.0)])
    return gait_clip(feet, times, lambda t: v * t, period=T_WALK), {
        "duration": T_WALK, "loop": True, "root_speed": v, "footfalls": feet.footfalls()}


def walk_start():
    """Standing -> walk-cycle phase 0 (left foot about to lift, right planted ahead of it)."""
    D = 0.55
    lp0 = -0.3 * STRIDE                        # loop phase 0: left ankle relative to the hips
    rp0 = V_WALK * 0.9 * T_WALK + 0.3 * STRIDE - STRIDE
    P_end = -lp0                               # left foot stays at 0 -> hips end 0.12 ahead
    times = [i / FPS for i in range(int(round(D * FPS)) + 1)]
    feet = Feet({"Left": (ank("Left"), 0.0), "Right": (ank("Right"), 0.0)}, [
        ("Right", 0.08, 0.45, ank("Right", P_end + rp0), 0.0)])
    return gait_clip(feet, times, lambda t: hermite(t, D, P_end, 0.0, V_WALK), weight=lambda t: smooth(t / 0.3)), {
        "duration": D, "loop": False, "root_dist": P_end, "footfalls": feet.footfalls()}


def walk_stop():
    """Walk-cycle phase 0 -> standing: the left foot swings up beside the right and the hips settle over both."""
    D = 0.75
    lp0 = -0.3 * STRIDE
    rp0 = V_WALK * 0.9 * T_WALK + 0.3 * STRIDE - STRIDE
    times = [i / FPS for i in range(int(round(D * FPS)) + 1)]
    feet = Feet({"Left": (ank("Left", lp0), 0.0), "Right": (ank("Right", rp0), 0.0)}, [
        ("Left", 0.0, 0.4, ank("Left", rp0), 0.0)])
    return gait_clip(feet, times, lambda t: hermite(t, 0.6, rp0, V_WALK, 0.0),
                     weight=lambda t: 1 - smooth((t - 0.3) / 0.45)), {
        "duration": D, "loop": False, "root_dist": rp0, "footfalls": feet.footfalls()}


def turn(total, steps, D, arms_out=0.0, name=""):
    """Turn in place by `total` deg (+ = to the goose's left), stepping feet to the rotated rest stance.
    steps: [(side, t0, t1, yaw_fraction)]. The pelvis heading follows the mean foot heading (smoothed)."""
    times = [i / FPS for i in range(int(round(D * FPS)) + 1)]
    feet = Feet({"Left": (ank("Left"), 0.0), "Right": (ank("Right"), 0.0)},
                [(s, t0, t1, ank(s, yaw=total * f), total * f) for s, t0, t1, f in steps])
    heading = np.array([(feet.at("Left", t)[1] + feet.at("Right", t)[1]) / 2 for t in times])
    k = np.exp(-0.5 * (np.arange(-6, 7) / 2.0) ** 2)
    k /= k.sum()
    heading = np.convolve(np.concatenate([np.full(6, heading[0]), heading, np.full(6, heading[-1])]), k, "same")[6:-6]
    heading[-3:] = total
    sig = support_signal(feet, times)
    frames = []
    for i, t in enumerate(times):
        def go(t=t, s=sig[i], h=heading[i]):
            P = default_params()
            P["yaw"] = float(h)
            w = math.sin(math.pi * min(1.0, t / D))
            P["dx"] += SWAY * 0.7 * s
            P["roll"] += ROLL * 0.7 * s
            P["dz"] -= 0.02 * w
            P["tail_yaw"] += 10.0 * s
            P["outL"] = P["outR"] = arms_out * w
            P["neck_yaw"] = 8.0 * math.copysign(1, total) * w     # head leads into the turn
            for side, kk in (("Left", "footL"), ("Right", "footR")):
                pos, yaw, pitch, _ = feet.at(side, t)
                P[kk] = (pos, yaw, pitch)
            return solve(P)
        frames.append(go)
    return frames, {"duration": D, "loop": False, "yaw_end": total, "footfalls": feet.footfalls()}


# ---- gesture clips (feet planted at rest) ---------------------------------------------------------------
def gesture(keys, D):
    times = [i / FPS for i in range(int(round(D * FPS)) + 1)]
    frames = []
    for t in times:
        def go(t=t):
            return solve(resolve_arms(keyed(keys, t)))
        frames.append(go)
    return frames, {"duration": D, "loop": False}


def hat_tip():
    """Right mitten takes the brim (right-front), lifts the hat ~6 cm and tips it forward with a nod, puts it back.
    Wrist targets sit below / outside the brim so the mitten (~0.19 m) reaches up onto it."""
    B = Vector((-0.085, -0.075, 0.0))           # brim contact, hat-relative (rest frame: -x = right, -y = forward)
    W = B + Vector((-0.11, 0.0, -0.12))
    up = Vector((0.0, -0.01, 0.06))
    aim_h = tuple(B - W)
    on_brim = {"armR": ("hat", tuple(W)), "handR": aim_h, "head_pitch": -3}
    lifted = {"armR": ("hat", tuple(W + up)), "handR": aim_h, "hat_lift": 0.06, "hat_fwd": 0.01, "hat_tilt": -12,
              "head_pitch": 10, "bend": 7}
    return gesture([
        (0.0, {}),
        (0.45, on_brim),
        (0.75, lifted),
        (1.15, lifted),
        (1.45, on_brim),
        (1.9, {}),
    ], 1.9)


def curtsy():
    back = (ank("Right", -0.12, x=-0.06), 8.0, 10.0)   # right foot tucked behind, crossing in
    skirt = {"armL": ("sh", (0.30, -0.10, -0.40)), "armR": ("sh", (-0.30, -0.10, -0.40)),
             "handL": (0.6, -0.3, -0.75), "handR": (-0.6, -0.3, -0.75)}
    low = {**skirt, "footR": back, "dz": -0.09, "bend": 12, "head_pitch": 16, "neck_pitch": 6}
    return gesture([
        (0.0, {}),
        (0.4, {**skirt, "footR": back}),
        (0.95, low),
        (1.35, low),
        (1.8, {**skirt, "footR": back}),
        (2.2, {}),
    ], 2.2)


def bow():
    across = ("sh", (-0.02, -0.22, -0.40))       # right hand across the waist
    behind = ("sh", (0.05, 0.22, -0.40))         # left hand behind the back
    low = {"armR": across, "armL": behind, "bend": 38, "pitch": 6, "head_pitch": 10, "neck_pitch": 12}
    return gesture([(0.0, {}), (0.35, {"armR": across, "armL": behind}), (0.85, low), (1.25, low),
                    (1.65, {"armR": across, "armL": behind}), (2.0, {})], 2.0)


def wave():
    up = ("sh", (-0.20, -0.08, 0.30))
    keys = [(0.0, {}), (0.35, {"armR": up, "side": 4, "head_yaw": -6})]
    for i in range(4):
        x = -0.30 if i % 2 == 0 else -0.10
        keys.append((0.55 + i * 0.25, {"armR": ("sh", (x, -0.08, 0.30)), "side": 4, "head_yaw": -6,
                                        "handR": (-0.25 if i % 2 == 0 else 0.1, -0.2, 1.0)}))
    keys += [(1.75, {"armR": up, "side": 2}), (2.1, {})]
    return gesture(keys, 2.1)


def admire():
    look = {"armL": ("sh", (0.10, -0.30, -0.25)), "handL": (0.2, -1.0, 0.0), "head_pitch": 30, "neck_pitch": 10,
            "head_yaw": 12, "twist": 8}
    smooth_coat = {"armR": ("sh", (0.10, -0.18, -0.35)), "head_pitch": 34, "neck_pitch": 12, "head_yaw": -6,
                   "twist": -4}
    return gesture([(0.0, {}), (0.5, look), (1.1, look), (1.5, smooth_coat), (2.0, smooth_coat),
                    (2.5, {})], 2.5)


def celebrate():
    up = {"armL": ("sh", (0.25, -0.05, 0.35)), "armR": ("sh", (-0.25, -0.05, 0.35)), "neck_pitch": -10}
    crouch = {"dz": -0.06, "bend": 10}
    air = {**up, "dz": 0.09, "footL": (ank("Left") + Vector((0, 0, 0.09)), 0.0, 8.0),
           "footR": (ank("Right") + Vector((0, 0, 0.09)), 0.0, 8.0)}
    return gesture([(0.0, {}), (0.25, crouch), (0.5, air), (0.75, {**up, "dz": -0.03}), (1.05, up),
                    (1.5, {})], 1.5)


def flap_startle():
    keys = [(0.0, {})]
    for i in range(6):
        hi = i % 2 == 0
        a = 0.35 if hi else 0.05
        keys.append((0.08 + i * 0.1, {"armL": ("sh", (0.42, 0.02, a)), "armR": ("sh", (-0.42, 0.02, a)),
                                      "dz": 0.03 if hi else 0.0, "neck_pitch": -14, "head_pitch": -6,
                                      "tail_pitch": -15}))
    keys.append((1.0, {}))
    return gesture(keys, 1.0)


def idle_shift():
    D = 4.0
    times = [i / FPS for i in range(int(D * FPS) + 1)]
    frames = []
    for t in times:
        def go(t=t):
            P = default_params()
            s = math.sin(2 * math.pi * t / D)
            P["dx"] = 0.02 * s
            P["roll"] = 2.0 * s
            P["side"] = -1.5 * s
            P["tail_yaw"] = 6.0 * math.sin(2 * math.pi * 2 * t / D)
            P["neck_pitch"] = 1.5 * math.sin(2 * math.pi * 2 * t / D)
            P["swingL"] = P["swingR"] = 1.5 * math.sin(2 * math.pi * 2 * t / D)
            return solve(P)
        frames.append(go)
    return frames, {"duration": D, "loop": True}


CLIPS = {
    "idle_shift": idle_shift,
    "walk_start": walk_start,
    "walk": walk_loop,
    "walk_stop": walk_stop,
    "turn_L90": lambda: turn(90.0, [("Left", 0.05, 0.35, 0.6), ("Right", 0.35, 0.65, 1.0), ("Left", 0.6, 0.9, 1.0)], 1.0),
    "turn_R90": lambda: turn(-90.0, [("Right", 0.05, 0.35, 0.6), ("Left", 0.35, 0.65, 1.0), ("Right", 0.6, 0.9, 1.0)], 1.0),
    "twirl": lambda: turn(360.0, [("Left", 0.05, 0.3, 1 / 6), ("Right", 0.25, 0.5, 2 / 6), ("Left", 0.45, 0.7, 3 / 6),
                                  ("Right", 0.65, 0.9, 4 / 6), ("Left", 0.85, 1.1, 5 / 6), ("Right", 1.05, 1.3, 1.0),
                                  ("Left", 1.25, 1.5, 1.0)], 1.6, arms_out=25.0),
    "hat_tip": hat_tip,
    "curtsy": curtsy,
    "bow": bow,
    "wave": wave,
    "admire": admire,
    "celebrate": celebrate,
    "flap_startle": flap_startle,
}


# ---- bake ----------------------------------------------------------------------------------------------
def bake(name, frames):
    act = bpy.data.actions.new(name)
    rig.animation_data.action = act
    prev, worst = {}, 0.0
    for f, pose in enumerate(frames):
        reach = pose()
        worst = max(worst, *reach.values())
        for b in BODY:
            pb = pbs[b]
            mb = pb.matrix_basis
            e = mb.to_euler("XYZ", prev[b]) if b in prev else mb.to_euler("XYZ")
            prev[b] = e
            pb.rotation_euler = e
            pb.keyframe_insert("rotation_euler", frame=f, group=b)
            if b in KEY_LOC:
                pb.location = mb.to_translation()
                pb.keyframe_insert("location", frame=f, group=b)
    act.use_fake_user = True
    rig.animation_data.action = None
    tr = rig.animation_data.nla_tracks.new()
    tr.name = name
    st = tr.strips.new(name, 0, act)
    st.extrapolation = "NOTHING"
    tr.mute = True
    return worst


sc.render.fps = FPS
sc.frame_start = 0
meta = {"goose": NAME, "char": CHAR, "dressed_tag": DTAG, "fps": FPS, "forward": "+Z (three.js)",
        "hips_rest_m": [round(v, 4) for v in H0], "clips": {}}
for cname, fn in CLIPS.items():
    if ONLY and cname not in ONLY:
        continue
    frames, info = fn()
    worst = bake(cname, frames)
    info["frames"] = len(frames)
    info["max_reach"] = round(worst, 3)
    meta["clips"][cname] = info
    print("CLIP", cname, json.dumps(info))
reset()

if RENDER:
    # quick contact sheet per clip: side view, 6 evenly spaced frames (Workbench)
    sc.render.engine = "BLENDER_WORKBENCH"
    sc.render.resolution_x, sc.render.resolution_y = 360, 480
    cam_d = bpy.data.cameras.new("cam")
    cam_d.type = "ORTHO"
    cam_d.ortho_scale = 2.2
    cam = bpy.data.objects.new("cam", cam_d)
    sc.collection.objects.link(cam)
    sc.camera = cam
    for o in bpy.data.objects:
        if o.type == "MESH" and "__" in o.name:
            o.hide_render = True
    tmp = ROOT / "renders" / "show"
    tmp.mkdir(parents=True, exist_ok=True)
    for cname in meta["clips"]:
        tr = rig.animation_data.nla_tracks[cname]
        rig.animation_data.action = bpy.data.actions[cname]
        n = meta["clips"][cname]["frames"]
        for view, loc, rot in (("side", (3.0, 0, 0.9), (math.pi / 2, 0, math.pi / 2)),
                               ("front", (0, -3.0, 0.9), (math.pi / 2, 0, 0))):
            cam.location, cam.rotation_euler = loc, rot
            for j, f in enumerate(np.linspace(0, n - 1, 6).round().astype(int)):
                sc.frame_set(int(f))
                if view == "side":
                    cam.location = (3.0, float(pbs["Hips"].head.y), 0.9)
                sc.render.filepath = str(tmp / f"{NAME}_{cname}_{view}_{j}.png")
                bpy.ops.render.render(write_still=True)
    rig.animation_data.action = None

# export the armature alone, rest pose, with every clip
for o in bpy.data.objects:
    o.select_set(False)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
out_glb = OUT / f"{NAME}_clips.glb"
bpy.ops.export_scene.gltf(filepath=str(out_glb), export_format="GLB", use_selection=True, export_skins=True,
                          export_animations=True, export_animation_mode="NLA_TRACKS", export_yup=True)
(OUT / f"{NAME}_clips.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
print("SHOW", out_glb, "clips:", list(meta["clips"]))
