"""Goose-fit tandem, step 2: frame geometry from the riders (side elevation, metres).

  .venv python scripts/frame_fit.py [--wheels 0.61,0.66] [--male-leg 1.0] [--tag goosefit]

Inputs: out/fit/geese_measure.json (measure_geese.py), out/bike/bike_rig.json (the current bike, for comparison).
Frame coordinates: u forward from the captain bottom bracket, z up from the ground.

Rules (each rider):
- crank c = CRANK_FRAC x inseam (hip joint to sole); one crank length for both riders (shared timing chain);
- bottom bracket height = c + BB_CLEAR (pedal clears the ground at the game's bike tilt);
- seat tube angle: knee over the pedal spindle at 3 o'clock (KOPS), clamped to [SEAT_MIN, SEAT_MAX];
- saddle on the seat-tube line, height so the farthest hip-to-ankle distance over the stroke is LEG_REACH x leg
  (ball of the foot on the pedal, toes TOE_DOWN; hip joint HIP_UP above the saddle top, as ride_fit.py);
- torso leaned LEAN, split over Spine / Spine1 / Spine2 about their own joints (as ride_fit.py: the shoulders
  move forward less than a lean from the hips); wrist at ARM_REACH x arm, ARM_DROP below horizontal, the
  reach shared with the sideways step from the shoulder out to the grip (GRIP_HALF x wheel scale); grip under
  the hanging hand (handshake grip, as ride_fit.py);
- captain: front hub far enough ahead for toe clearance; steer axis HEAD_ANGLE, fork offset FORK_OFFSET;
- stoker: grips on the captain's seat post, behind the captain's back; stoker BB placed so her reach is met;
- rear hub CHAINSTAY_CLEAR behind the stoker's tyre edge.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

argv = sys.argv[1:]


def arg(name, default):
    return argv[argv.index(name) + 1] if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
M = json.loads((ROOT / "out/fit/geese_measure.json").read_text(encoding="utf-8"))
BIKE = json.loads((ROOT / "out/bike/bike_rig.json").read_text(encoding="utf-8"))
WHEELS = [float(x) for x in arg("--wheels", "0.61,0.66").split(",")]   # 24 / 26 in: style (BB height is not)
MALE_LEG = [float(x) for x in arg("--male-leg", "1.0").split(",")]     # the male's legs are x1.15 since the refit
TAG = arg("--tag", "goosefit")
CRANK_FRAC = 0.20     # human rule of thumb: 170 mm for ~0.85 m inseam
BB_CLEAR = 0.10       # bottom pedal clears the ground at ~22 deg bike tilt
HIP_UP = 0.0          # #505: was 0.11 (a human's); a goose's bottom swallows the saddle, Pete wants the seat top at the hip joint
LEG_REACH = 0.95
TOE_DOWN = 12.0
PIN_UP = 0.011        # pedal top above the spindle (PedalPin socket)
SEAT_MIN, SEAT_MAX = 66.0, 76.0
LEAN = {"captain": 15.0, "stoker": 10.0}
ARM_REACH = 0.90
ARM_DROP = 35.0       # deg below horizontal, shoulder to wrist
HAND_CURL = 25.0
PALM_AT = 0.6
PALM_OFF = 0.03       # grip centre inboard of the hand bone (ride_fit.py)
GRIP_HALF = 0.18      # grip half-width of the game's bars at 28 in; scales with the wheel
HEAD_ANGLE = 70.0
FORK_OFFSET = 0.045
TOE_CLEAR = 0.03
BACK_CLEAR = 0.22     # stoker grips this far behind the captain's hip joint (saddle rear 0.13, breeches 0.13, coat)
KNEE_CLEAR = 0.04     # stoker's knee to the captain's back at the top of her stroke
CHAINSTAY_CLEAR = 0.18   # #505: was 0.08; the stoker's seat cluster and the rack sat below the top of the tyre


def rot(v, deg):
    a = math.radians(deg)
    return np.array([v[0] * math.cos(a) - v[1] * math.sin(a), v[0] * math.sin(a) + v[1] * math.cos(a)])


def leg_ik(hip, ankle, l1, l2, bend=1):
    d = ankle - hip
    dist = min(np.linalg.norm(d), (l1 + l2) * 0.999)
    u = d / np.linalg.norm(d)
    ca = (l1 * l1 + dist * dist - l2 * l2) / (2 * l1 * dist)
    w = np.array([-u[1], u[0]])                    # left of hip->ankle: forward for a downward leg
    if w[0] * bend < 0:                            # bend=1: joint forward (knee); -1: back (elbow)
        w = -w
    return hip + l1 * (ca * u + math.sqrt(max(0.0, 1 - ca * ca)) * w)


class Rider:
    def __init__(self, key, m, leg_scale=1.0):
        self.key, self.m = key, m
        self.l1, self.l2 = m["thigh"] * leg_scale, m["shin"] * leg_scale
        self.leg = self.l1 + self.l2
        # foot, side view (u forward = -Blender y): ankle->ball
        a2b = np.array([-m["ankle_to_ball"][1], m["ankle_to_ball"][2]])
        self.ball_to_ankle = -rot(a2b, -TOE_DOWN)            # toes down: the foot pitches clockwise about the ball
        self.sole_to_ball = m["ball_z"] - m["sole_z"]
        self.inseam = m["hip_joint_z"] - m["sole_z"] + (leg_scale - 1) * m["thigh"] + (leg_scale - 1) * m["shin"]
        self.torso, self.arm, self.hand = m["torso_hip_to_shoulder"], m["arm"], m["hand"]
        J = m["joints"]
        hip0 = np.array([-J["LeftUpLeg"][1], J["LeftUpLeg"][2]])
        self.spine = [np.array([-J[n][1], J[n][2]]) - hip0 for n in ("Spine", "Spine1", "Spine2")]
        self.sh_rel = np.array([-J["LeftArm"][1], J["LeftArm"][2]]) - hip0
        self.sh_x = J["LeftArm"][0]
        self.toe_ahead = m["boot_length"] - abs(a2b[0]) - 0.06

    def ankle(self, bb, c, phi):
        pin = bb + c * np.array([math.sin(phi), math.cos(phi)]) + np.array([0, PIN_UP])
        return pin + np.array([0, self.sole_to_ball]) + self.ball_to_ankle, pin

    def max_reach(self, hip, bb, c):
        return max(np.linalg.norm(hip - self.ankle(bb, c, p)[0]) for p in np.linspace(0, 2 * math.pi, 181))

    def seat(self, bb, c, alpha):
        """Saddle top on the seat-tube line (angle alpha from horizontal, leaning back) for LEG_REACH."""
        d = np.array([-math.cos(math.radians(alpha)), math.sin(math.radians(alpha))])
        lo, hi = 0.05, 1.5
        for _ in range(60):
            s = (lo + hi) / 2
            if self.max_reach(bb + d * s + np.array([0, HIP_UP]), bb, c) < LEG_REACH * self.leg:
                lo = s
            else:
                hi = s
        saddle = bb + d * s
        return saddle, saddle + np.array([0, HIP_UP])

    def kops(self, bb, c, alpha):
        _, hip = self.seat(bb, c, alpha)
        ank, pin = self.ankle(bb, c, math.pi / 2)
        knee = leg_ik(hip, ank, self.l1, self.l2)
        return knee[0] - (bb[0] + c)

    def shoulder(self, hip, lean_deg):
        """Arm joint after the lean, rotated about Spine, Spine1, Spine2 in turn (lean / 3 each), forward = +u."""
        pts = [hip + q for q in self.spine] + [hip + self.sh_rel]
        for i in range(3):
            piv = pts[i]
            for j in range(i + 1, 4):
                pts[j] = piv + rot(pts[j] - piv, -lean_deg / 3)
        return pts[3]

    def fit(self, bb, c, wheel=0.7112):
        lo, hi = SEAT_MIN, SEAT_MAX                     # kops(alpha) increases with alpha (steeper = hip forward)
        if self.kops(bb, c, lo) > 0:
            alpha = lo
        elif self.kops(bb, c, hi) < 0:
            alpha = hi
        else:
            for _ in range(40):
                mid = (lo + hi) / 2
                lo, hi = (mid, hi) if self.kops(bb, c, mid) < 0 else (lo, mid)
            alpha = (lo + hi) / 2
        saddle, hip = self.seat(bb, c, alpha)
        sh = self.shoulder(hip, LEAN[self.key])
        cu = math.radians(HAND_CURL)
        wrist_x = GRIP_HALF * wheel / 0.7112 + PALM_OFF + PALM_AT * self.hand * math.sin(cu)
        dx = wrist_x - self.sh_x
        r = math.sqrt(max(0.0, (ARM_REACH * self.arm) ** 2 - dx * dx))       # reach left for the side view
        wrist = sh + r * np.array([math.cos(math.radians(ARM_DROP)), -math.sin(math.radians(ARM_DROP))])
        grip = wrist + np.array([0, -PALM_AT * self.hand * math.cos(cu)])
        poses = {}
        for name, phi in (("top", 0.0), ("fwd", math.pi / 2), ("bottom", math.pi), ("back", 1.5 * math.pi)):
            ank, pin = self.ankle(bb, c, phi)
            poses[name] = {"pin": pin, "ankle": ank, "knee": leg_ik(hip, ank, self.l1, self.l2),
                           "ball": pin + np.array([0, self.sole_to_ball])}
        tk = poses["top"]["knee"]
        th, tv = tk - hip, sh - hip
        hip_angle = math.degrees(math.acos(np.dot(th, tv) / np.linalg.norm(th) / np.linalg.norm(tv)))
        return {"alpha": alpha, "saddle": saddle, "hip": hip, "shoulder": sh, "wrist": wrist, "grip": grip,
                "poses": poses, "hip_angle_top_deg": hip_angle, "kops_mm": self.kops(bb, c, alpha) * 1000}

    def offset_to(self, f, du):
        g = {}
        for k, v in f.items():
            if isinstance(v, np.ndarray):
                g[k] = v + np.array([du, 0])
            elif k == "poses":
                g[k] = {n: {kk: vv + np.array([du, 0]) for kk, vv in p.items()} for n, p in v.items()}
            else:
                g[k] = v
        return g


def design(male_leg, WHEEL):
    cap = Rider("captain", M["outfit_male"], male_leg)
    sto = Rider("stoker", M["outfit_female"])
    c = round(CRANK_FRAC * min(cap.inseam, sto.inseam), 3)
    bbz = c + BB_CLEAR
    R = WHEEL / 2
    bbF = np.array([0.0, bbz])
    F = cap.fit(bbF, c, WHEEL)
    # front hub: toe at 3 o'clock clears the tyre
    toe = F["poses"]["fwd"]["ball"] + np.array([cap.toe_ahead, 0.02])
    dz = toe[1] - R
    hubF_u = toe[0] + TOE_CLEAR + math.sqrt(max(0.0, R * R - dz * dz))
    hubF = np.array([hubF_u, R])
    # steer axis through the fork crown: hub + offset normal to the axis
    ax = np.array([-math.cos(math.radians(HEAD_ANGLE)), math.sin(math.radians(HEAD_ANGLE))])   # up and back
    nrm = np.array([ax[1], -ax[0]])                                      # forward-normal
    p0 = hubF - nrm * FORK_OFFSET
    t_grip = (F["grip"][1] - p0[1]) / ax[1]
    steer_at_grip = p0 + ax * t_grip
    bar_sweep = steer_at_grip[0] - F["grip"][0]                          # >0: grips behind the steer axis
    # stoker: grips behind the captain's back; place her BB so her reach is met
    gS_u = F["hip"][0] - BACK_CLEAR
    S0 = sto.fit(np.array([0.0, bbz]), c, WHEEL)                         # fit at BB u=0, then shift
    du = gS_u - S0["grip"][0]
    S = sto.offset_to(S0, du)
    bbR = np.array([du, bbz])
    # stoker knee vs the captain's back at the top of her stroke
    knee_gap = (F["hip"][0] - BACK_CLEAR + 0.05) - S["poses"]["top"]["knee"][0]
    if knee_gap < KNEE_CLEAR:                                            # move her back
        shift = KNEE_CLEAR - knee_gap
        S = sto.offset_to(S, -shift)
        bbR = bbR + np.array([-shift, 0])
        knee_gap = KNEE_CLEAR
    hubR = np.array([bbR[0] - (R + CHAINSTAY_CLEAR), R])
    rep = {
        "male_leg_scale": male_leg, "wheel_m": WHEEL, "wheel_in": round(WHEEL / 0.0254, 1), "crank_m": c,
        "bb_height_m": round(bbz, 3), "bb_drop_m": round(R - bbz, 3),
        "wheelbase_m": round(hubF[0] - hubR[0], 3), "length_m": round(hubF[0] - hubR[0] + WHEEL, 3),
        "bb_spacing_m": round(-bbR[0], 3), "front_center_m": round(hubF[0], 3),
        "chainstay_m": round(bbR[0] - hubR[0], 3), "head_angle_deg": HEAD_ANGLE,
        "captain": {"seat_angle_deg": round(F["alpha"], 1), "saddle_z": round(F["saddle"][1], 3),
                    "saddle_setback_m": round(-F["saddle"][0], 3), "grip_z": round(F["grip"][1], 3),
                    "grip_ahead_of_saddle_m": round(F["grip"][0] - F["saddle"][0], 3),
                    "bar_sweep_m": round(bar_sweep, 3), "hip_angle_top_deg": round(F["hip_angle_top_deg"], 1),
                    "kops_mm": round(F["kops_mm"], 1), "leg_m": round(cap.leg, 3)},
        "stoker": {"seat_angle_deg": round(S["alpha"], 1), "saddle_z": round(S["saddle"][1], 3),
                   "grip_z": round(S["grip"][1], 3), "grip_below_captain_saddle_m": round(F["saddle"][1] - S["grip"][1], 3),
                   "hip_angle_top_deg": round(S["hip_angle_top_deg"], 1), "kops_mm": round(S["kops_mm"], 1),
                   "knee_to_captain_back_m": round(knee_gap, 3), "leg_m": round(sto.leg, 3)},
    }
    geo = {"hubF": hubF, "hubR": hubR, "bbF": bbF, "bbR": bbR, "R": R, "c": c, "F": F, "S": S,
           "steer_lo": p0 + ax * ((R + 0.1 - p0[1]) / ax[1]), "steer_hi": steer_at_grip}
    return rep, geo


def current_bike():
    p, s = BIKE["pivots"], BIKE["sockets"]
    off = p["crank_F"][1]                                                # captain BB at u = 0
    U = lambda v: np.array([-(v[1] - off), v[2]])
    return {"hubF": U(p["hub_F"]), "hubR": U(p["hub_R"]), "bbF": U(p["crank_F"]), "bbR": U(p["crank_R"]),
            "R": BIKE["wheel_m"] / 2, "c": p["crank_len_m"]["Pedal_FL"],
            "seatC": U(s["Seat_Captain"]["pos"]), "seatS": U(s["Seat_Stoker"]["pos"]),
            "gripC": U(s["Grip_C_L"]["pos"]), "gripS": U(s["Grip_S_L"]["pos"]),
            "steer_lo": U(p["steer_lo"]), "steer_hi": U(p["steer_hi"])}


# ---- drawing --------------------------------------------------------------------------------------
PX = 330                     # px per metre
W_IMG, H_IMG = 1300, 760
try:
    FONT, SMALL = ImageFont.truetype("arial.ttf", 19), ImageFont.truetype("arial.ttf", 15)
except OSError:
    FONT = SMALL = ImageFont.load_default()


def panel(rep, geo, title):
    im = Image.new("RGB", (W_IMG, H_IMG), "white")
    d = ImageDraw.Draw(im)
    ox, oy = 0.62 * W_IMG, H_IMG - 40                                    # captain BB u=0 at x=ox; ground at oy
    P = lambda v: (ox + v[0] * PX, oy - v[1] * PX)

    def line(a, b, fill, w=3):
        d.line([P(a), P(b)], fill=fill, width=w)

    def circ(cn, r, outline, w=2, fill=None):
        x, y = P(cn)
        d.ellipse([x - r * PX, y - r * PX, x + r * PX, y + r * PX], outline=outline, width=w, fill=fill)

    d.line([(0, oy), (W_IMG, oy)], fill=(150, 150, 150), width=1)
    for z in np.arange(0.5, 2.01, 0.5):                                  # height ticks
        y = oy - z * PX
        d.line([(0, y), (W_IMG, y)], fill=(235, 235, 235), width=1)
        d.text((W_IMG - 50, y - 16), f"{z:.1f} m", fill=(150, 150, 150), font=SMALL)
    # current bike (grey)
    cb, grey = current_bike(), (190, 190, 200)
    for h in ("hubF", "hubR"):
        circ(cb[h], cb["R"], grey, 2)
    for b in ("bbF", "bbR"):
        circ(cb[b], cb["c"], grey, 1)
    for a, b in (("bbF", "seatC"), ("bbR", "seatS"), ("bbF", "bbR"), ("bbR", "hubR"), ("bbF", "steer_lo"),
                 ("seatC", "steer_hi"), ("seatC", "seatS"), ("steer_lo", "steer_hi"), ("steer_hi", "gripC"),
                 ("seatC", "gripS")):
        line(cb[a], cb[b], grey, 2)
    # new frame (black)
    F, S = geo["F"], geo["S"]
    blk, gold = (25, 25, 25), (190, 150, 40)
    for h in ("hubF", "hubR"):
        circ(geo[h], geo["R"], blk, 4)
        circ(geo[h], 0.015, blk, 2, fill=blk)
    for b in ("bbF", "bbR"):
        circ(geo[b], geo["c"], gold, 1)
        circ(geo[b], 0.02, blk, 2, fill=blk)
    tt_z = min(F["saddle"][1], S["saddle"][1]) - 0.10
    stC = geo["bbF"] + (F["saddle"] - geo["bbF"]) * ((tt_z - geo["bbF"][1]) / (F["saddle"][1] - geo["bbF"][1]))
    stS = geo["bbR"] + (S["saddle"] - geo["bbR"]) * ((tt_z - geo["bbR"][1]) / (S["saddle"][1] - geo["bbR"][1]))
    head_tt = geo["steer_lo"] + (geo["steer_hi"] - geo["steer_lo"]) * \
        ((tt_z - geo["steer_lo"][1]) / (geo["steer_hi"][1] - geo["steer_lo"][1]))
    for a, b in ((geo["bbF"], F["saddle"]), (geo["bbR"], S["saddle"]), (geo["bbF"], geo["bbR"]),
                 (geo["bbR"], geo["hubR"]), (stS, geo["hubR"]), (geo["bbF"], geo["steer_lo"]),
                 (head_tt, stS), (geo["steer_lo"], geo["hubF"]), (geo["steer_lo"], geo["steer_hi"])):
        line(a, b, blk, 5)
    line(geo["steer_hi"], F["grip"], blk, 4)
    stalk = np.array([S["grip"][0] + 0.02, tt_z])                         # stoker stem: up from the top tube
    line(stalk, stalk + np.array([0, S["grip"][1] - tt_z + 0.03]), blk, 4)
    line(stalk + np.array([0, S["grip"][1] - tt_z + 0.03]), S["grip"], blk, 4)
    for g in (F["grip"], S["grip"]):
        circ(g, 0.02, (120, 60, 20), 2, fill=(120, 60, 20))
    for sd in (F["saddle"], S["saddle"]):
        d.rounded_rectangle([P(sd + np.array([-0.13, 0.04])), P(sd + np.array([0.08, 0.0]))], 6, fill=(110, 50, 30))
    # riders: legs at top/bottom of the stroke, torso, arm, head
    for R_, col in ((F, (30, 70, 160)), (S, (170, 40, 90))):
        for pose, w in (("bottom", 6), ("top", 3)):
            p = R_["poses"][pose]
            line(R_["hip"], p["knee"], col, w)
            line(p["knee"], p["ankle"], col, w)
            line(p["ankle"], p["ball"], col, w)
            circ(p["pin"], 0.012, col, 2, fill=col)
        line(R_["hip"], R_["shoulder"], col, 7)
        elbow = leg_ik(R_["shoulder"], R_["wrist"], 0.2568, 0.2566, bend=-1)
        line(R_["shoulder"], elbow, col, 4)
        line(elbow, R_["wrist"], col, 4)
        line(R_["wrist"], R_["grip"], col, 4)
        head = R_["shoulder"] + np.array([0.04, 0.38])
        line(R_["shoulder"], head, col, 4)
        circ(head, 0.07, col, 3)
        circ(R_["hip"], 0.02, col, 2, fill=col)
    d.text((12, 10), title, fill="black", font=FONT)
    lines = [
        f"wheel {rep['wheel_in']:.0f} in ({rep['wheel_m'] * 100:.0f} cm)   crank {rep['crank_m'] * 1000:.0f} mm   BB height "
        f"{rep['bb_height_m'] * 100:.0f} cm   wheelbase {rep['wheelbase_m']:.2f} m   length {rep['length_m']:.2f} m",
        f"captain: saddle {rep['captain']['saddle_z'] * 100:.0f} cm, seat angle {rep['captain']['seat_angle_deg']:.0f} deg, grips "
        f"{rep['captain']['grip_z'] * 100:.0f} cm, bar sweep {rep['captain']['bar_sweep_m'] * 100:.0f} cm, hip angle at top "
        f"{rep['captain']['hip_angle_top_deg']:.0f} deg",
        f"stoker: saddle {rep['stoker']['saddle_z'] * 100:.0f} cm, seat angle {rep['stoker']['seat_angle_deg']:.0f} deg, grips "
        f"{rep['stoker']['grip_z'] * 100:.0f} cm, knee-to-captain gap {rep['stoker']['knee_to_captain_back_m'] * 100:.0f} cm, "
        f"BB spacing {rep['bb_spacing_m']:.2f} m",
        "grey: current bike at true size (captain BBs aligned)   blue: captain   magenta: stoker   (legs: bottom thick, top thin)",
    ]
    for i, t in enumerate(lines):
        d.text((12, 40 + 22 * i), t, fill=(60, 60, 60), font=SMALL)
    return im


reps, panels = [], []
out_dir = ROOT / "out" / "fit"
for ml in MALE_LEG:
    for wh in WHEELS:
        rep, geo = design(ml, wh)
        reps.append(rep)
        print("FRAME", json.dumps(rep))
        title = (f"Goose-fit tandem, {rep['wheel_in']:.0f} in wheels: captain leg {rep['captain']['leg_m']:.2f} m, "
                 f"stoker leg {rep['stoker']['leg_m']:.2f} m")
        panels.append(panel(rep, geo, title))
        F, S = geo["F"], geo["S"]
        pts = {"hub_F": geo["hubF"], "hub_R": geo["hubR"], "bb_F": geo["bbF"], "bb_R": geo["bbR"],
               "saddle_C": F["saddle"], "saddle_S": S["saddle"], "grip_C": F["grip"], "grip_S": S["grip"],
               "hip_C": F["hip"], "hip_S": S["hip"]}
        spec = {"wheel_m": wh, "crank_m": geo["c"], "frame": "u forward from the captain BB, z up (metres)",
                "points": {k: [round(float(x), 4) for x in v] for k, v in pts.items()}, "report": rep}
        (out_dir / f"frame_{TAG}_{round(wh / 0.0254)}in.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
(out_dir / "frame_fit.json").write_text(json.dumps(reps, indent=1), encoding="utf-8")
sheet = Image.new("RGB", (W_IMG, H_IMG * len(panels)), "white")
for i, p in enumerate(panels):
    sheet.paste(p, (0, H_IMG * i))
img = ROOT / "docs" / "img" / "fit_frame_side.png"
sheet.save(img)
print("SHEET", img)
