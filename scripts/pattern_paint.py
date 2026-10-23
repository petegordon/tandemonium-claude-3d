"""Paint a woven / knitted pattern onto a built garment, in 3D: every texel's surface point (position + normal, rasterised
from the garment's own UVs) gets its colour from a procedural pattern laid out on the body, so a herringbone runs
straight down the leg and an argyle stays square on the chest whatever the UV islands are.

  blender -b --factory-startup --python scripts/pattern_paint.py -- --char outfit_male_cyclist --piece breeches
      [--tex 2048] [--glb out/<char>-goose/shells/<piece>.glb]

Recipe: chars/<char>.json "patterns" {piece: {"type": herringbone | argyle | rib | leather, ...}} (colours sRGB 0-255,
sizes in metres). The garment's baked detail texture (weave, grooves, folds: make_garment.py) is kept as shading: the
new base colour = pattern x (detail / its mean). The material's colour factor becomes white. The shell is rewritten in
place (the previous one kept as versions/<piece>_prepattern.glb) + renders/<char>_pattern_<piece>.png.
"""
import json
import math
import shutil
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_cyclist")
PIECE = opt("--piece", "breeches")
D = ROOT / "out" / f"{CHAR}-goose"
GLB = ROOT / opt("--glb", f"out/{CHAR}-goose/shells/{PIECE}.glb")
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
PR = cfg["patterns"][PIECE]
TEX = opt("--tex", PR.get("tex", 1024))


def rgb(c):
    return np.array(c[:3], float) / 255.0


def hash01(*q):
    """Deterministic per-cell noise in [0, 1) from integer cell coordinates."""
    h = np.zeros(q[0].shape, np.uint64)
    for i, a in enumerate(q):
        h ^= (a.astype(np.int64).astype(np.uint64) * np.uint64([73856093, 19349663, 83492791][i % 3]))
    h = (h * np.uint64(2654435761)) % np.uint64(4294967291)
    return (h % np.uint64(10007)).astype(float) / 10007.0


def value_noise(p, cell):
    """Smooth 3D value noise (trilinear over hashed lattice), p (N, 3) metres."""
    q = p / cell
    i = np.floor(q).astype(np.int64)
    f = q - i
    f = f * f * (3 - 2 * f)
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * (f[:, 2] if dz else 1 - f[:, 2])
                out = out + w * hash01(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz)
    return out


# ---------------------------------------------------------------- surface coordinates
def around(P, N, axes):
    """(u, v): u = arc length round the nearest vertical axis (x, y centre per axis), v = height; texels facing up /
    down (|nz| > 0.75) use the plane (x, -y) so a cap's top or a sock's sole has no pinch."""
    best = None
    for cx, cy in axes:
        d = np.hypot(P[:, 0] - cx, P[:, 1] - cy)
        best = d if best is None else np.minimum(best, d)
    u = np.zeros(len(P))
    for cx, cy in axes:
        d = np.hypot(P[:, 0] - cx, P[:, 1] - cy)
        on = d <= best + 1e-9
        ang = np.arctan2(P[:, 0] - cx, -(P[:, 1] - cy))          # 0 = front, seam at the back
        u = np.where(on, ang * (PR.get("r0", 0.0) or np.maximum(d, 0.02)) + cx * 10, u)
    v = P[:, 2].copy()
    flat = np.abs(N[:, 2]) > PR.get("flat_nz", 0.75)       # (a skirt's rump shelf is not a top: flat_nz 0.97)
    u = np.where(flat, P[:, 0], u)
    v = np.where(flat, -P[:, 1] + 5.0, v)
    return u, v


def axes_for(P):
    """Vertical axes: the legs below the crotch (|x| ~ 0.09), else the body's centre line."""
    return PR.get("axes", [[0.0, 0.03]])


def leg_axes(P):
    crotch = PR.get("crotch_z", 0.70)
    legs = P[:, 2] < crotch
    return legs


# ---------------------------------------------------------------- patterns
def herringbone(P, N):
    u, v = around(P, N, PR.get("axes", [[0.0, 0.03]]))
    if PR.get("arms"):          # a jacket: on the sleeves the columns run along the arm (u round it, v along it)
        da, ua = arm_coords(P)
        on_arm = (da < 0.07) & (np.abs(P[:, 0]) > PR.get("arm_x", 0.13))
        u = np.where(on_arm, ua, u)
        v = np.where(on_arm, np.abs(P[:, 0]) * 0.8 + P[:, 2] * 0.6, v)
    w, per = PR.get("column", 0.008), PR.get("period", 0.0045)
    col = np.floor(u / w)
    s = np.where(col % 2 == 0, 1.0, -1.0)
    t = (v + s * (u - col * w) * PR.get("slope", 1.0)) / per
    thread = 0.5 + 0.5 * np.sin(2 * np.pi * t)
    thread = np.clip((thread - 0.5) * PR.get("contrast", 1.6) + 0.5, 0, 1)
    dark, light = rgb(PR["dark"]), rgb(PR["light"])
    c = dark[None] * (1 - thread[:, None]) + light[None] * thread[:, None]
    # tweed: slubby yarn (fine noise), flecks of other colours, a little column-to-column variation
    c *= (0.92 + 0.16 * value_noise(P, 0.0025))[:, None]
    c *= (0.96 + 0.08 * hash01(col, np.floor(v / 0.05)))[:, None]
    for fc, rate in PR.get("flecks", []):
        cell = np.floor(P / 0.0016).astype(np.int64)
        hit = hash01(cell[:, 0], cell[:, 1], cell[:, 2]) < rate
        c = np.where(hit[:, None], rgb(fc)[None], c)
    c *= (0.94 + 0.12 * value_noise(P, 0.03))[:, None]
    bs = PR.get("back_seam")
    if bs:      # centre back seam down the seat (it reads the two cheeks apart), shaded a little each side
        on_ = (P[:, 1] > bs.get("y0", 0.03)) & (P[:, 2] > bs["z0"]) & (P[:, 2] < bs["z1"])
        ax_ = np.abs(P[:, 0])
        k_ = np.where(on_ & (ax_ < bs.get("w", 0.0015)), bs.get("dark", 0.55),
                      np.where(on_, 1 - (1 - bs.get("shade", 0.85)) * np.exp(-(ax_ / 0.012) ** 2), 1.0))
        c *= k_[:, None]
    return c


def argyle(P, N):
    yc = PR.get("centre_y", 0.0)
    front = P[:, 1] < yc + PR.get("front_margin", 0.0)
    W, H = PR.get("diamond_w", 0.09), PR.get("diamond_h", 0.125)
    # knitted in: the diamonds wrap round the body (arc at a fixed radius "r0"), not a flat print from the front
    u = around(P, np.zeros_like(P), PR.get("axes", [[0.0, 0.03]]))[0] if PR.get("r0") else P[:, 0]
    v = P[:, 2] - PR.get("z0", 1.0)
    a, b = u / W + v / H, -u / W + v / H
    i, j = np.floor(a), np.floor(b)
    cA, cB, cC = rgb(PR["a"]), rgb(PR["b"]), rgb(PR["c"])
    colc = (i - j)            # horizontal index of the diamond (0 = centre column)
    c = np.where(((i + j) % 2 == 0)[:, None], cA[None], cB[None])
    # centre column (i == j, always the "a" colour by parity): every other diamond in cream, as the reference
    centre = (np.abs(colc) < 0.5) & (i % 2 == PR.get("accent_phase", 0)) if PR.get("centre_accent", True) else np.zeros(len(P), bool)
    c = np.where(centre[:, None], cC[None], c)
    # overcheck: thin lines along the diagonals through the diamond centres
    fa, fb = a - i - 0.5, b - j - 0.5
    lw = PR.get("line_w", 0.0022)
    da = np.abs(fa) * math.hypot(W, H) / 2 * 2 / math.hypot(1, 1)
    near_a = np.abs(fa) * (W * H / math.hypot(W, H)) < lw
    near_b = np.abs(fb) * (W * H / math.hypot(W, H)) < lw
    c = np.where((near_a | near_b)[:, None], rgb(PR["line"])[None], c)
    base = rgb(PR["back"])
    c = np.where(front[:, None], c, base[None])
    c = knit_shade(P, N, c)
    return c


def knit_shade(P, N, c):
    """Stockinette: rows of small Vs (columns of knit stitches) as a gentle light / dark modulation."""
    sw, sh = PR.get("stitch_w", 0.0042), PR.get("stitch_h", 0.0036)
    u, v = around(P, N, PR.get("axes", [[0.0, 0.03]]))
    col = np.floor(u / sw)
    fx = u / sw - col
    vv = v / sh + np.abs(fx - 0.5) * 0.9
    k = 0.5 + 0.5 * np.cos(2 * np.pi * vv)
    edge = np.abs(fx - 0.5) * 2
    shade = 0.9 + 0.1 * k - 0.06 * edge ** 3
    return c * shade[:, None] * (0.98 + 0.04 * value_noise(P, 0.006))[:, None]     # (2 cm noise read as blotches)


def joints():
    """The character's joints (heads / tails): chars json "joints_file" (a shaped body, e.g. the female sliders),
    else the base rig's refs/key_views/joints.json."""
    import json as _j
    f = ROOT / cfg.get("joints_file", "refs/key_views/joints.json")
    return _j.loads(f.read_text(encoding="utf-8"))


def arm_coords(P):
    """Per point: distance to the nearer arm polyline (shoulder -> elbow -> wrist -> hand tip) and the arc
    coordinate round that arm (fixed radius 4 cm, so ribs run straight down the sleeve)."""
    js = joints()
    best = np.full(len(P), 9.0)
    u = np.zeros(len(P))
    for s_ in ("Left", "Right"):
        pts = [np.array(js[f"{s_}Arm"]["head"]), np.array(js[f"{s_}ForeArm"]["head"]),
               np.array(js[f"{s_}Hand"]["head"]), np.array(js[f"{s_}Hand"]["tail"])]
        for q0, q1 in zip(pts[:-1], pts[1:]):
            dq = q1 - q0
            t_ = np.clip(((P - q0) @ dq) / (dq @ dq), 0, 1)
            c_ = q0 + t_[:, None] * dq
            rad = P - c_
            d_ = np.linalg.norm(rad, axis=1)
            ax = dq / np.linalg.norm(dq)
            ref = np.array([0, -1.0, 0]) - ax * ax[1] * -1
            ref -= ax * (ref @ ax)
            ref /= np.linalg.norm(ref)
            side = np.cross(ax, ref)
            ang = np.arctan2(rad @ side, rad @ ref)
            take = d_ < best
            best = np.where(take, d_, best)
            u = np.where(take, ang * 0.04, u)
    return best, u


def rib(P, N):
    u, v = around(P, N, PR.get("leg_axes", [[0.09, 0.035], [-0.09, 0.035]]))
    if PR.get("arms"):          # sleeves: ribs along the arm (the torso keeps the vertical ones)
        da, ua = arm_coords(P)
        torso_r = np.hypot(P[:, 0], P[:, 1])
        on_arm = (da < 0.07) & (np.abs(P[:, 0]) > PR.get("arm_x", 0.13))
        u = np.where(on_arm, ua, u)
    pitch = PR.get("pitch", 0.005)
    r = 0.5 + 0.5 * np.cos(2 * np.pi * (P[:, 2] if PR.get("horizontal") else u) / pitch)   # (a knitted tie: across)
    c = rgb(PR["color"])[None] * (PR.get("rib_dark", 0.72) + (1 - PR.get("rib_dark", 0.72)) * r)[:, None]
    WF = PR.get("waffle")        # chunky waffle knit: horizontal ridges x the ribs -> a grid of raised cells
    if WF:
        w_ = 0.5 + 0.5 * np.cos(2 * np.pi * P[:, 2] / WF.get("pitch", 0.009))
        c *= (WF.get("dark", 0.8) + (1 - WF.get("dark", 0.8)) * (w_ * r) ** WF.get("gamma", 0.5))[:, None]
    c *= (0.95 + 0.1 * value_noise(P, 0.015))[:, None]
    return c


def brogue(P, N):
    """Full brogue oxford in brown calf: wingtip toe cap (W seam + perforation row), toe medallion, quarter seam with
    perforations, heel counter seam, lace throat with laces + eyelets, a darker topline binding, burnished toe / heel.
    Per shoe: X across from the shoe's centre line, Y along (forward = -y), z up (metres, base-body frame)."""
    cx0, toe, heel = PR["centre_x"], PR["toe_y"], PR["heel_y"]
    sx = np.where(P[:, 0] >= 0, 1.0, -1.0)
    X = (P[:, 0] - cx0 * sx) * sx               # + = outward
    Y, Z = P[:, 1], P[:, 2] - PR.get("z_off", 0.0)      # (z_off: the shoe built below the floor -- female sliders)
    L = heel - toe
    t = (heel - Y) / L                           # 0 heel .. 1 toe
    base = rgb(PR["leather"])
    c = np.tile(base, (len(P), 1))
    c *= (0.9 + 0.2 * value_noise(P, 0.004))[:, None]
    burn = np.clip((t - 0.7) / 0.4, 0, 1) ** 1.5 + np.clip((0.15 - t) / 0.15, 0, 1) ** 1.5    # antiqued toe and heel
    burn *= 0.7 + 0.6 * value_noise(P, 0.012)
    c *= (1 - 0.3 * np.clip(burn, 0, 1))[:, None]
    dark = rgb(PR.get("seam", [44, 24, 14]))
    upper = Z > PR.get("welt_z", 0.016)
    ztop = np.interp(t, *np.array(PR["top_line"]).T)

    def seam(dist, along, w=0.0007, dots=True, off=0.0026, pitch=0.0042, r=0.00085):
        """A stitched seam line (dist = signed distance across it) and a row of punched holes beside it."""
        out = np.abs(dist) < w
        if dots:
            fr = (along / pitch) % 1.0 - 0.5
            out |= (np.hypot(dist - off, fr * pitch) < r)
        return out & upper
    # wingtip: W-shaped cap seam, its wings sweeping back down the sides
    hw = 0.05
    yw = toe + PR.get("wing_c", 0.055) + PR.get("wing_back", 0.085) * np.clip(np.abs(X) / hw, 0, 1.2) ** 2
    side = np.clip((ztop - Z) / 0.03, 0, 1) * (np.abs(X) > 0.03)
    along = np.abs(X) + np.maximum(ztop - Z, 0)
    m = seam(Y - yw, along, off=0.0028) if PR.get("wing", True) else np.zeros(len(P), bool)
    # toe medallion: a rosette of holes on the cap
    mc = np.array([0.0, toe + PR.get("medallion", 0.026)])
    dm = np.hypot(X - mc[0], Y - mc[1])
    ang = np.arctan2(Y - mc[1], X - mc[0])
    for rr_, n_ in (((0.0, 1), (0.0055, 8), (0.010, 12)) if PR.get("medallion_on", True) else ()):
        if rr_ == 0:
            m |= (dm < 0.0012) & upper & (Z > ztop - 0.02)
            continue
        a_ = (ang / (2 * np.pi) * n_) % 1.0 - 0.5
        m |= (np.abs(dm - rr_) < 0.0009) & (np.abs(a_) * 2 * np.pi * rr_ / n_ * n_ / 1.0 < 0.0011) & upper & (Z > ztop - 0.02)
    # quarter seam: across the instep in front of the laces, down to the sole at both sides
    yq = heel - L * PR.get("quarter_t", 0.47) + 0.03 * np.clip(np.abs(X) / hw, 0, 1.2) ** 1.5
    m |= seam(Y - yq, along, off=-0.0026, dots=PR.get("wing", True))
    # heel counter: a curved seam round the heel
    hz = 0.035 + 0.02 * np.clip(t / 0.25, 0, 1)
    m |= seam(np.where(t < 0.3, Z - hz, 9.0), np.abs(X) + Y, off=0.0025)
    c = np.where(m[:, None], dark[None] * (0.8 + 0.4 * value_noise(P, 0.002))[:, None], c)
    tl0, tl1 = PR.get("lace_t", [0.44, 0.62])
    TB = PR.get("tbar")
    if TB:
        # T-bar: a strap across the instep (side to side, down to the sole line on each side) and a centre bar from
        # the throat to the vamp; darker leather, stitched edges, a brass buckle on the outer side
        st = TB.get("strap_t", 0.36)
        ys_ = heel - L * st
        w_ = TB.get("w", 0.006)
        strap = (np.abs(Y - ys_) < w_) & (Z > TB.get("z_low", 0.03))
        bar = (np.abs(X) < TB.get("bar_w", 0.006)) & (t > st) & (t < TB.get("bar_t", 0.62)) & (Z > ztop - 0.02)
        sc = rgb(TB.get("color", [86, 44, 22]))
        c = np.where((strap | bar)[:, None], sc[None] * (0.9 + 0.2 * value_noise(P, 0.003))[:, None], c)
        edge = ((np.abs(np.abs(Y - ys_) - w_ + 0.0012) < 0.0005) & (Z > TB.get("z_low", 0.03))) | \
               ((np.abs(np.abs(X) - TB.get("bar_w", 0.006) + 0.0012) < 0.0005) & bar)
        c = np.where(edge[:, None], c * 0.7, c)
        bx = (X > 0.025) & (np.abs(Y - ys_) < w_ * 1.5) & (np.abs(Z - TB.get("buckle_z", 0.06)) < 0.008)
        ring = bx & ((np.abs(Y - ys_) > w_ * 1.5 - 0.0018) | (np.abs(Z - TB.get("buckle_z", 0.06)) > 0.008 - 0.0018))
        c = np.where(ring[:, None], rgb(TB.get("brass", [170, 130, 70]))[None], c)
    if not PR.get("laces", True):
        c = np.where(((Z > PR.get("collar_z", 0.1)) & (t < tl0))[:, None], c * 0.84, c)
        return c
    # lace throat: eyelet facings, 5 eyelets a side, crossed laces
    inth = (t > tl0) & (t < tl1) & (Z > ztop - 0.016)
    gap = np.abs(X) < 0.006 + 0.004 * (t - tl0) / (tl1 - tl0)
    c = np.where((inth & gap)[:, None], rgb(PR.get("tongue", [86, 46, 24]))[None], c)
    k = (t - tl0) / (tl1 - tl0) * 5
    rowd = (np.abs(k % 1.0 - 0.5)) * L * (tl1 - tl0) / 5
    eye = inth & (np.hypot(np.abs(X) - 0.012, rowd) < 0.0016)
    lace = inth & (np.abs(X) < 0.012) & (rowd < 0.0011)
    c = np.where(lace[:, None], rgb(PR.get("lace", [52, 30, 18]))[None], c)
    c = np.where(eye[:, None], rgb([30, 22, 16])[None], c)
    # topline binding
    c = np.where(((Z > PR.get("collar_z", 0.1)) & (t < tl0))[:, None], c * 0.84, c)
    SL = PR.get("shaft_laces")
    if SL:      # ankle boot: the lacing runs on up the front of the shaft (eyelets each side, crossed laces)
        z0_, z1_, n_ = SL["z0"], SL["z1"], SL.get("rows", 6)
        on_ = (N[:, 1] < -0.3) & (Z > z0_) & (Z < z1_)
        k_ = (Z - z0_) / (z1_ - z0_) * n_
        rd_ = np.abs(k_ % 1.0 - 0.5) * (z1_ - z0_) / n_
        c = np.where((on_ & (np.abs(X) < 0.007))[:, None], rgb(PR.get("tongue", [86, 46, 24]))[None], c)
        c = np.where((on_ & (np.abs(X) < 0.011) & (rd_ < 0.001))[:, None], rgb(PR.get("lace", [52, 30, 18]))[None], c)
        eye_ = on_ & (np.hypot(np.abs(X) - 0.011, rd_) < 0.0017)
        c = np.where(eye_[:, None], rgb(SL.get("eyelet", [150, 120, 70]))[None], c)
    return c


def glove(P, N):
    """Tan driving gloves (the goose's mitt hands): pebbled leather, a darker wrist strap with a press stud on the back
    of the hand, three stitched points running down the back, a perforated knuckle panel (refs/key_views/joints.json:
    each hand from its Hand bone's head (wrist) to its tail (tip); the back of the hand faces away from the body)."""
    import json as _j
    js = joints()
    base = rgb(PR["leather"])
    c = np.tile(base, (len(P), 1)) * (0.9 + 0.2 * value_noise(P, 0.0025))[:, None]
    c *= (0.95 + 0.1 * value_noise(P, 0.02))[:, None]
    dark = rgb(PR.get("strap", [96, 62, 36]))
    stitch = rgb(PR.get("stitch", [70, 44, 26]))
    for s in ("Left", "Right"):
        h0, h1 = np.array(js[f"{s}Hand"]["head"]), np.array(js[f"{s}Hand"]["tail"])
        ax = (h1 - h0) / np.linalg.norm(h1 - h0)
        on = (P[:, 0] > 0) if s == "Left" else (P[:, 0] < 0)
        rel = P - h0
        a = rel @ ax                                        # along the hand from the wrist joint
        rad = rel - a[:, None] * ax
        outw = np.array([1.0 if s == "Left" else -1.0, 0, 0])
        outw = outw - (outw @ ax) * ax
        outw /= np.linalg.norm(outw)
        fwd = np.cross(ax, outw)
        phi = np.arctan2(rad @ fwd, rad @ outw)             # 0 = back of the hand
        r_ = np.linalg.norm(rad, axis=1)
        w0 = PR.get("strap_a", [-0.03, -0.012])
        band = on & (a > w0[0]) & (a < w0[1])
        c = np.where(band[:, None], dark[None] * (0.9 + 0.2 * value_noise(P, 0.003))[:, None], c)
        edge = on & ((np.abs(a - w0[0]) < 0.0012) | (np.abs(a - w0[1]) < 0.0012))
        c = np.where(edge[:, None], stitch[None], c)
        stud = on & (np.hypot(a - (w0[0] + w0[1]) / 2, phi * r_) < PR.get("stud_r", 0.0045))
        c = np.where(stud[:, None], rgb(PR.get("stud", [150, 116, 66]))[None], c)
        for k in (-1, 0, 1):                                # three points down the back of the hand
            pts = on & (a > w0[1] + 0.008) & (a < w0[1] + 0.06) & (np.abs(phi * r_ - k * 0.009) < 0.0009)
            c = np.where(pts[:, None], stitch[None], c)
        kn = on & (a > w0[1] + 0.07) & (a < w0[1] + 0.09) & (np.abs(phi) < 0.9)
        holes = kn & ((((a / 0.0045) % 1.0 - 0.5) ** 2 + ((phi * r_ / 0.0045) % 1.0 - 0.5) ** 2) < 0.07)
        if PR.get("holes", True):
            c = np.where(holes[:, None], c * 0.45, c)
    return c


def sprig(P, N):
    """Silk with scattered flower sprigs (18th-century damask / embroidered waistcoat): a plain fine-weave ground in
    "ground", and on a staggered lattice ("cell" m, round the body like the tweeds) a five-petal flower of "size" m in
    "flower" with a "centre" dot and two leaves in "leaf", each turned and nudged at random; "fill" = share of lattice
    cells with a sprig. "region" {z_min, z_max, front_only, abs_x_min} limits where sprigs go. Damask = flower /
    leaf colours a little lighter than the ground (self-coloured)."""
    u, v = around(P, N, PR.get("axes", [[0.0, 0.03]]))
    if PR.get("v_radial"):         # a skirt sloping out over the hips: v ~ arc length down the surface, not height
        ax0 = PR.get("axes", [[0.0, 0.03]])[0]
        v = v - PR["v_radial"] * np.hypot(P[:, 0] - ax0[0], P[:, 1] - ax0[1])
    if PR.get("arms"):
        da, ua = arm_coords(P)
        on_arm = (da < 0.07) & (np.abs(P[:, 0]) > PR.get("arm_x", 0.13))
        u = np.where(on_arm, ua, u)
        v = np.where(on_arm, np.abs(P[:, 0]) * 0.8 + P[:, 2] * 0.6, v)
    c = np.repeat(rgb(PR["ground"])[None], len(P), 0)
    c *= (0.95 + 0.07 * value_noise(P, 0.0012))[:, None]          # fine weave
    c *= (0.95 + 0.10 * value_noise(P, 0.035))[:, None]           # sheen variation
    cell, R = PR.get("cell", 0.045), PR.get("size", 0.009)
    row = np.floor(v / cell)
    off = np.where(row % 2 == 0, 0.0, 0.5)
    col = np.floor(u / cell + off)
    j1, j2, j3, j4 = (hash01(col + 11 * k, row + 7 * k) for k in range(4))
    cu = (col + 0.5 - off) * cell + (j1 - 0.5) * cell * 0.3
    cv = (row + 0.5) * cell + (j2 - 0.5) * cell * 0.3
    th = j3 * 2 * np.pi
    du, dv = u - cu, v - cv
    if PR.get("lattice") == "3d":
        # sprigs on a jittered 3D lattice, drawn in each texel's tangent plane (no wrap angle: a wide skirt's back
        # is not sheared the way an angle x radius coordinate shears it where the radius changes with height)
        q = P / cell
        best = np.full(len(P), 9.0)
        D3 = np.zeros_like(P)
        J3 = np.zeros((len(P), 2))
        base = np.floor(q - 0.5).astype(np.int64)
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    ci = base + np.array([dx, dy, dz])
                    jit = np.stack([hash01(ci[:, 0] + 3 * k, ci[:, 1] + 5 * k, ci[:, 2] + 7 * k) for k in range(5)], 1)
                    cen = (ci + 0.5 + (jit[:, :3] - 0.5) * 0.4) * cell
                    d3 = P - cen
                    dd = np.linalg.norm(d3, axis=1)
                    take = dd < best
                    best = np.where(take, dd, best)
                    D3 = np.where(take[:, None], d3, D3)
                    J3 = np.where(take[:, None], jit[:, 3:5], J3)
        t1 = np.cross(N, np.array([0.0, 0.0, 1.0]))
        t1 /= np.maximum(np.linalg.norm(t1, axis=1, keepdims=True), 1e-6)
        t2 = np.cross(N, t1)
        du, dv = np.sum(D3 * t1, 1), np.sum(D3 * t2, 1)
        th = J3[:, 0] * 2 * np.pi
        j4 = J3[:, 1]
    x_, y_ = du * np.cos(th) + dv * np.sin(th), -du * np.sin(th) + dv * np.cos(th)
    r, a = np.hypot(x_, y_), np.arctan2(y_, x_)
    keep = j4 < PR.get("fill", 1.0)
    rg = PR.get("region")
    if rg:
        keep &= (P[:, 2] >= rg.get("z_min", -9)) & (P[:, 2] <= rg.get("z_max", 9))
        if rg.get("front_only"):
            keep &= P[:, 1] < rg.get("y_max", 0.0)
        if "abs_x_min" in rg:
            keep &= np.abs(P[:, 0]) >= rg["abs_x_min"]
    petal = keep & (r < R * (PR.get("petal_base", 0.45) + (1 - PR.get("petal_base", 0.45)) * np.abs(np.cos(2.5 * a))))
    centre = keep & (r < R * 0.28)
    leaf = np.zeros(len(P), bool)
    for la in (np.pi * 0.85, -np.pi * 0.15):
        lr = PR.get("leaf_r", 1.55)
        lx, ly = x_ - np.cos(la) * R * lr, y_ - np.sin(la) * R * lr
        ex = lx * np.cos(la) + ly * np.sin(la)
        ey = -lx * np.sin(la) + ly * np.cos(la)
        ls = PR.get("leaf_size", 1.0)
        leaf |= keep & ((ex / (R * 0.75 * ls)) ** 2 + (ey / (R * 0.32 * ls)) ** 2 < 1)
    stem = keep & (np.abs(y_ + R * 0.1) < R * 0.07) & (x_ < -R * 0.4) & (x_ > -R * 2.2)
    lc = rgb(PR.get("leaf", PR["flower"]))
    if not PR.get("stems", True):
        stem = np.zeros(len(P), bool)
    mx = PR.get("mix", 1.0)                 # damask woven into the ground: < 1 blends the motif with the ground
    c = np.where((leaf | stem)[:, None], c * (1 - mx) + mx * lc[None] * (0.9 + 0.15 * value_noise(P, 0.002))[:, None], c)
    c = np.where(petal[:, None], c * (1 - mx) + mx * rgb(PR["flower"])[None] * (0.88 + 0.2 * np.clip(1 - r / R, 0, 1))[:, None], c)
    c = np.where(centre[:, None], rgb(PR.get("centre", PR["flower"]))[None], c)
    return c


def crochet(P, N):
    """Open-work (filet) crochet: a square mesh of yarn round the body with open holes; the holes are painted the colour
    of what shows through (a shawl over a dress), the yarn has a twisted-stitch texture. pitch = mesh cell (m),
    hole = half the hole's width as a fraction of the cell."""
    # tri-planar (the mesh is a square grid in space; a cape's shoulders are near-flat, where "around" smears)
    ax_ = np.argmax(np.abs(N), 1)
    u = np.where(ax_ == 0, P[:, 1], P[:, 0])
    v = np.where(ax_ == 2, P[:, 1], P[:, 2])
    p = PR.get("pitch", 0.016)
    if PR.get("map") == "cone":            # opt-in: worked in rounds from the neck (a cape): rings by distance from an apex
        ay_, az_ = PR.get("apex", [0.0, 1.3])   # above the neck; columns radiate, increases every "group" rounds
        r_ = np.hypot(P[:, 0], P[:, 1] - ay_)
        v = np.hypot(r_, az_ - P[:, 2])
        ring_ = np.floor(v / p)
        grp_ = PR.get("group", 4)
        gi_ = np.floor(ring_ / grp_).astype(int)
        gi_ -= gi_.min()
        rk_ = np.bincount(gi_, weights=r_) / np.maximum(np.bincount(gi_), 1)   # mean girth radius of each group
        n_ = np.round(2 * np.pi * rk_[gi_] * PR.get("spread", 1.0) / p)
        ang_ = np.arctan2(P[:, 0], -(P[:, 1] - ay_)) + PR.get("seam_az", 0.0)   # 0 = centre front
        u = (ang_ / (2 * np.pi)) * n_ * p
    fu, fv = (u / p) % 1.0 - 0.5, (v / p) % 1.0 - 0.5
    h = PR.get("hole", 0.3)
    e = np.maximum(np.abs(fu), np.abs(fv))                     # square holes, soft edged (yarn rounds over)
    if PR.get("hole_round"):               # opt-in: rounded-square holes (superellipse power)
        q_ = PR["hole_round"]
        e = (np.abs(fu) ** q_ + np.abs(fv) ** q_) ** (1 / q_)
    hole = np.clip((h - e) / 0.06 + 0.5, 0, 1)
    tw = 0.5 + 0.5 * np.cos(2 * np.pi * (u + v) / (p / 3))     # twisted stitches along the yarn
    yarn = rgb(PR["color"])[None] * (0.84 + 0.16 * tw)[:, None] * (0.94 + 0.12 * value_noise(P, 0.01))[:, None]
    yarn *= (1 - 0.25 * np.clip((e - h) / 0.08, 0, 1) * (e < h + 0.08))[:, None]   # shade where the yarn turns into the hole
    if PR.get("alpha_holes"):              # opt-in: real open holes (alpha-clipped), the yarn shaded round each hole
        global HOLE
        HOLE = np.clip((h - e) / PR.get("hole_soft", 0.03) + 0.5, 0, 1)
        yarn *= (1 - PR.get("hole_rim_dark", 0.35) * np.clip(1 - (e - h) / 0.12, 0, 1) * (e >= h - 0.02))[:, None]
        bu_ = np.clip((0.5 - np.abs(fu)) / max(0.5 - h, 1e-3), 0, 1)     # 0 at a bar's centre line, 1 at the hole
        bv_ = np.clip((0.5 - np.abs(fv)) / max(0.5 - h, 1e-3), 0, 1)
        tube_ = np.cos(np.minimum(bu_, bv_) * np.pi / 2) ** 0.6       # round yarn: bright on top, darker to the sides
        yarn *= (1 - PR.get("tube", 0.28) + PR.get("tube", 0.28) * tube_)[:, None]
        return yarn
    return yarn * (1 - hole)[:, None] + rgb(PR.get("hole_color", [60, 16, 46]))[None] * hole[:, None]


PATTERNS = {"herringbone": herringbone, "argyle": argyle, "rib": rib, "brogue": brogue, "glove": glove, "sprig": sprig,
            "crochet": crochet}


def bands(P, c, boundary):
    """Ribbed bands along the garment's open edges (sweater vest: hem, V-neck, armholes): 'bands' list of
    {z_max | z_min, width, color}; ribs run across the band."""
    if not PR.get("bands") or not len(boundary):
        return c
    from mathutils.kdtree import KDTree
    for bd in PR["bands"]:
        sel = np.ones(len(boundary), bool)
        if "z_max" in bd:
            sel &= boundary[:, 2] < bd["z_max"]
        if "z_min" in bd:
            sel &= boundary[:, 2] > bd["z_min"]
        if "y_max" in bd:
            sel &= boundary[:, 1] < bd["y_max"]
        if "abs_x_min" in bd:      # e.g. the sleeve ends only (not the hem at the same height)
            sel &= np.abs(boundary[:, 0]) > bd["abs_x_min"]
        if "abs_x_max" in bd:
            sel &= np.abs(boundary[:, 0]) < bd["abs_x_max"]
        pts = boundary[sel]
        if not len(pts):
            continue
        kd = KDTree(len(pts))
        for k_, p_ in enumerate(pts):
            kd.insert(Vector(p_), k_)
        kd.balance()
        dist = np.array([kd.find(Vector(p_))[2] for p_ in P])
        off = bd.get("offset", 0.0)        # a band set back from the edge (a skirt's hem band)
        inb = (dist >= off) & (dist < off + bd["width"])
        # ribs across the band: the along-edge coordinate of the nearest edge point
        along = P[:, 2] if bd.get("rib") == "z" else around(P, np.zeros_like(P), PR.get("axes", [[0.0, 0.03]]))[0]
        rr = 0.5 + 0.5 * np.cos(2 * np.pi * along / bd.get("pitch", 0.0045))
        if bd.get("rib") == "none":        # plain cloth band (cuffs, lapels, a hem band): fine weave noise only
            rr = 0.7 + 0.3 * value_noise(P, 0.002)
        col = rgb(bd["color"])[None] * (0.78 + 0.22 * rr)[:, None]
        c = np.where(inb[:, None], col, c)
        print("BAND", bd.get("name", ""), int(inb.sum()), "texels")
    return c


# ---------------------------------------------------------------- rasterise the UVs
# always paint the UNPATTERNED build: a fresh build (GLB newer than the stamp this script leaves) is copied to
# versions/<piece>_prepattern.glb first; a re-run on an already painted shell starts from that copy
(D / "versions").mkdir(parents=True, exist_ok=True)
BAK = D / "versions" / f"{GLB.stem}_prepattern.glb"
STAMP = GLB.with_suffix(".patterned")
if not (STAMP.exists() and STAMP.read_text() == str(GLB.stat().st_mtime_ns) and BAK.exists()):
    shutil.copy(GLB, BAK)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(BAK))
obs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
target_imgs = set()
for o in obs:
    for m in o.data.materials:
        if not m or not m.node_tree:
            continue
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image and n.image.colorspace_settings.name != "Non-Color":
                if any(l_.to_socket.name in ("Base Color", "A", "B", "Color1", "Color2") for l_ in n.outputs["Color"].links):
                    target_imgs.add(n.image.name)
print("TARGET images", target_imgs)
if not target_imgs:
    # modelled pieces with a plain colour (make_boot.py, make_cap.py): a new texture on the materials named in
    # "materials", no detail shading to keep
    ph = bpy.data.images.new(f"{CHAR}_{PIECE}_flat", 4, 4, alpha=False)
    ph.pixels = [1.0] * 64
    target_imgs.add(ph.name)
    for o in obs:
        for m in o.data.materials:
            if m and m.node_tree and any(k in m.name for k in PR.get("materials", [])):
                bs = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
                tx = m.node_tree.nodes.new("ShaderNodeTexImage")
                tx.image = ph
                m.node_tree.links.new(tx.outputs["Color"], bs.inputs["Base Color"])
src_img = bpy.data.images[sorted(target_imgs)[0]]
SW, SH = src_img.size
detail = np.array(src_img.pixels[:], np.float32).reshape(SH, SW, -1)[..., :3]
PAINT_MATS = PR.get("materials")       # only texels of faces with these materials are painted (else every face)

pos = np.zeros((TEX, TEX, 3), np.float32)
nrm = np.zeros((TEX, TEX, 3), np.float32)
mask = np.zeros((TEX, TEX), bool)
boundary = []
for o in obs:
    me = o.data
    M = np.array(o.matrix_world)
    V = np.array([(o.matrix_world @ v.co)[:] for v in me.vertices])
    Nv = np.array([(o.matrix_world.to_3x3() @ v.normal).normalized()[:] for v in me.vertices])
    me.calc_loop_triangles()
    uvd = me.uv_layers.active.data
    # boundary edges by POSITION (the glTF splits vertices along UV seams)
    from collections import Counter
    key = lambda i: tuple(np.round(V[i], 5))  # noqa: E731
    cnt = Counter()
    for pg in me.polygons:                 # faces per edge, by position: 1 = an open edge of the garment
        for ek in pg.edge_keys:
            a_, b_ = sorted([key(ek[0]), key(ek[1])])
            cnt[(a_, b_)] += 1
    for (a_, b_), k_ in cnt.items():
        if k_ == 1:
            for t_ in np.linspace(0, 1, 4):
                boundary.append(np.array(a_) * (1 - t_) + np.array(b_) * t_)
    for t in me.loop_triangles:
        if PAINT_MATS and not any(k in me.materials[t.material_index].name for k in PAINT_MATS):
            continue
        uv =np.array([uvd[li].uv[:] for li in t.loops]) * [TEX, TEX]
        vi = list(t.vertices)
        x0, y0 = np.floor(uv.min(0)).astype(int)
        x1, y1 = np.ceil(uv.max(0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, TEX - 1), min(y1, TEX - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        (ax_, ay_), (bx_, by_), (cx_, cy_) = uv
        den = (by_ - cy_) * (ax_ - cx_) + (cx_ - bx_) * (ay_ - cy_)
        if abs(den) < 1e-12:
            continue
        l1 = ((by_ - cy_) * (gx - cx_) + (cx_ - bx_) * (gy - cy_)) / den
        l2 = ((cy_ - ay_) * (gx - cx_) + (ax_ - cx_) * (gy - cy_)) / den
        l3 = 1 - l1 - l2
        ins = (l1 >= -0.02) & (l2 >= -0.02) & (l3 >= -0.02)
        if not ins.any():
            continue
        L = np.stack([l1[ins], l2[ins], l3[ins]], 1)
        yy, xx = (gy[ins] - 0.5).astype(int), (gx[ins] - 0.5).astype(int)
        pos[yy, xx] = L @ V[vi]
        nn = L @ Nv[vi]
        nrm[yy, xx] = nn / np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-9)
        mask[yy, xx] = True
boundary = np.array(boundary) if boundary else np.zeros((0, 3))
print("TEXELS", int(mask.sum()), "boundary pts", len(boundary))

P, N = pos[mask].astype(float), nrm[mask].astype(float)
col = PATTERNS[PR["type"]](P, N)
col = bands(P, col, boundary)


def in_poly(x, z, poly):
    """Even-odd point-in-polygon test, vectorised over (x, z)."""
    inside = np.zeros(len(x), bool)
    q = np.asarray(poly, float)
    for i in range(len(q)):
        (x0, z0), (x1, z1) = q[i], q[i - 1]
        cross = ((z0 > z) != (z1 > z)) & (x < (x1 - x0) * (z - z0) / np.where(z1 - z0 == 0, 1e-12, z1 - z0) + x0)
        inside ^= cross
    return inside


# "panels": front-projected regions painted over the pattern (a fichu in a bodice's neckline, a stomacher):
#   [{"poly": [[x, z], ...], "color": rgb, "front_only": true, "edge": rgb, "edge_w": m, "cross": [w, rgb]}]
for pn in PR.get("panels", []):
    on = in_poly(P[:, 0], P[:, 2], pn["poly"]) & ((P[:, 1] < 0) if pn.get("front_only", True) else True)
    pc = rgb(pn["color"])[None] * (0.95 + 0.07 * value_noise(P, 0.0015))[:, None]
    if pn.get("sheer"):                       # sheer muslin: the colour under it shows a little, fine pleats
        pc = pc * (0.9 + 0.1 * np.sin(P[:, 0] / pn["sheer"] * 2 * np.pi))[:, None]
    col = np.where(on[:, None], pc, col)
    if pn.get("cross"):                       # a crossed kerchief's two folded edges (an X from the shoulders)
        w_, cc_ = pn["cross"]
        zt = max(z for _, z in pn["poly"])
        xs_ = max(abs(x) for x, _ in pn["poly"])
        for sg in (1, -1):
            d_ = np.abs((P[:, 0] * sg) - (xs_ - (zt - P[:, 2]) * xs_ / max(zt - min(z for _, z in pn["poly"]), 1e-3)))
            col = np.where((on & (d_ < w_))[:, None], rgb(cc_)[None], col)
    if pn.get("edge"):
        q = np.asarray(pn["poly"], float)
        dmin = np.full(len(P), 9.0)
        for i in range(len(q)):
            a_, b_ = q[i - 1], q[i]
            ab = b_ - a_
            t_ = np.clip(((P[:, [0, 2]] - a_) @ ab) / max(ab @ ab, 1e-12), 0, 1)
            dmin = np.minimum(dmin, np.linalg.norm(P[:, [0, 2]] - (a_ + t_[:, None] * ab), axis=1))
        ed = (dmin < pn.get("edge_w", 0.004)) & ((P[:, 1] < 0) if pn.get("front_only", True) else True) &             (dmin < 0.02) & (np.abs(P[:, 0]) < 0.3)
        col = np.where(ed[:, None], rgb(pn["edge"])[None], col)
# "bows": small painted ribbon bows down the centre front (a stomacher's echelle): {"z": [..], "w", "h", "color", "x"}
BW = PR.get("bows")
if BW:
    for zb_ in BW["z"]:
        dx_, dz_ = P[:, 0] - BW.get("x", 0.0), P[:, 2] - zb_
        w_, h_ = BW.get("w", 0.03), BW.get("h", 0.016)
        loop = (np.abs(dx_) < w_ / 2) & (np.abs(dz_) < h_ / 2 * (0.35 + 0.65 * np.abs(dx_) / (w_ / 2)))
        knot = (np.abs(dx_) < w_ * 0.09) & (np.abs(dz_) < h_ * 0.3)
        tails = (np.abs(np.abs(dx_) - (-dz_) * 0.5) < w_ * 0.07) & (dz_ < 0) & (dz_ > -h_ * 1.1)
        front = P[:, 1] < 0
        shade_ = 0.82 + 0.25 * np.clip(1 - np.abs(dz_) / (h_ / 2), 0, 1)
        bc = rgb(BW["color"])
        col = np.where(((loop | tails) & front)[:, None], bc[None] * shade_[:, None], col)
        col = np.where((knot & front)[:, None], bc[None] * 0.8, col)
    print("BOWS", len(BW["z"]))
BT = PR.get("buttons")
if BT:
    # buttons painted where the garment's own detail bake put them (centre front, every button_step from button_top)
    Rg = cfg.get("garment_design", {}).get(PIECE, {})
    zs_ = np.arange(Rg.get("button_top", 1.2), Rg.get("z_bot", 0.9) + 0.03, -Rg.get("button_step", 0.06))
    br = BT.get("r", 0.0055)
    bx_ = BT.get("x", 0.0)          # x of the button line (an open cardigan: on one front edge; default centre)
    if "z" in BT:                   # explicit button heights
        zs_ = np.array(BT["z"], float)
    for zb_ in zs_:
        dbt = np.hypot(P[:, 0] - bx_, P[:, 2] - zb_)
        on_ = (P[:, 1] < 0) & (dbt < br)
        shade_ = 0.75 + 0.35 * np.clip(1 - dbt / br, 0, 1)
        col = np.where(on_[:, None], rgb(BT["color"])[None] * shade_[:, None], col)
        ring_ = (P[:, 1] < 0) & (np.abs(dbt - br) < 0.0008)
        col = np.where(ring_[:, None], col * 0.6, col)
    print("BUTTONS", len(zs_))
# keep the detail texture's shading (its folds / grooves), resampled to TEX
ys, xs = np.nonzero(mask)
dy = np.clip((ys + 0.5) * SH / TEX, 0, SH - 1).astype(int)
dx = np.clip((xs + 0.5) * SW / TEX, 0, SW - 1).astype(int)
dl = detail[dy, dx].mean(1)
dmean = float(np.median(dl[dl > 0.05])) if (dl > 0.05).any() else 1.0
shade = np.clip(dl / dmean, 0.55, 1.25) ** PR.get("detail_gamma", 1.0)
shade = np.where(dl < 0.25 * dmean, 1.0, shade)        # (texels the detail bake missed are black: no shading, not a dark spot)
col = np.clip(col * shade[:, None], 0, 1)
        if HOLE is not None:               # (open-work: the band is solid; "scallop": [depth, pitch] cuts its outer edge)
            HOLE[inb] = 0.0
            if bd.get("scallop"):
                dep_, pit_ = bd["scallop"]
                sc_ = dep_ * (0.5 + 0.5 * np.cos(2 * np.pi * along / pit_)) ** 0.7
                cut_ = (dist < off + sc_) & (dist < off + bd["width"])
                HOLE[cut_] = 1.0
img = np.zeros((TEX, TEX, 3), np.float32)
img[mask] = col
# pad the islands (push-pull: empty texels take their filled neighbours' mean, 12 rounds)
filled = mask.copy()
for _ in range(12):
    acc = np.zeros_like(img)
    cntm = np.zeros((TEX, TEX), np.float32)
    for sy, sx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        acc += np.roll(np.roll(img * filled[..., None], sy, 0), sx, 1)
        cntm += np.roll(np.roll(filled.astype(np.float32), sy, 0), sx, 1)
    new = (~filled) & (cntm > 0)
    img[new] = acc[new] / cntm[new][:, None]
    filled |= new
ALPHA = np.ones((TEX, TEX, 1), np.float32)
if HOLE is not None:                       # the alpha channel: 0 in the holes (padded like the colour, so seams stay closed)
    am = np.zeros((TEX, TEX), np.float32)
    am[mask] = 1 - HOLE
    fa = mask.copy()
    for _ in range(12):
        acc = np.zeros_like(am)
        cntm = np.zeros((TEX, TEX), np.float32)
        for sy, sx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            acc += np.roll(np.roll(am * fa, sy, 0), sx, 1)
            cntm += np.roll(np.roll(fa.astype(np.float32), sy, 0), sx, 1)
        new = (~fa) & (cntm > 0)
        am[new] = acc[new] / cntm[new]
        fa |= new
    am[~fa] = 1.0
    ALPHA = am[..., None]
out = bpy.data.images.new(f"{CHAR}_{PIECE}_pattern", TEX, TEX, alpha=HOLE is not None)
out.pixels = np.concatenate([img, ALPHA], -1).ravel().tolist()
out.pack()
for o in obs:
    for m in o.data.materials:
        if not m or not m.node_tree:
            continue
        for n in m.node_tree.nodes:
            if n.type == "TEX_IMAGE" and n.image and n.image.name in target_imgs:
                n.image = out
            if n.type == "MIX" and getattr(n, "blend_type", "") == "MULTIPLY":
                for s_ in n.inputs:
                    if s_.name in ("B", "Color2") and s_.type == "RGBA" and not s_.is_linked:
                        s_.default_value = (1, 1, 1, 1)
        if not any(n.type == "TEX_IMAGE" and n.image == out for n in m.node_tree.nodes):
            continue                       # (other materials -- a sole, a lining with its own colour -- stay as they are)
        bs = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bs is not None and "roughness" in PR:
            bs.inputs["Roughness"].default_value = PR["roughness"]
bpy.ops.object.select_all(action="DESELECT")
for o in bpy.context.scene.objects:
    o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(GLB), use_selection=True, export_format="GLB")
STAMP.write_text(str(GLB.stat().st_mtime_ns))
print("PATTERN", PIECE, PR["type"], "->", GLB)
HOLE = None                                # (crochet with "alpha_holes": per-texel hole cover, 1 = open)
        if bs is not None and HOLE is not None:     # alpha clip (glTF alphaMode MASK: image alpha -> Round -> Alpha)
            tx_ = next(n for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.image == out)
            rd_ = m.node_tree.nodes.new("ShaderNodeMath")
            rd_.operation = "ROUND"
            m.node_tree.links.new(tx_.outputs["Alpha"], rd_.inputs[0])
            m.node_tree.links.new(rd_.outputs[0], bs.inputs["Alpha"])
            m.use_backface_culling = False
            print("ALPHA clip", m.name)
