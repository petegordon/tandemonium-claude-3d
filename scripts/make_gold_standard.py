"""Gold Standard tandem (Tandemonium #611 / #644): the all-100-achievements bike, built in code on the game tandem's rig.

  blender -b --factory-startup --python scripts/make_gold_standard.py -- [--base <bike_rigged_goosefit26.blend>] [--sheet]

Look: refs/gold_standard/pete_refs/{side,front,rear,top}.png (Pete 2026-11-09; side is the primary). Polished gold
everywhere: an organic swooping frame with open teardrop cut-outs, a flat plate on the top tube carrying a crown in a
laurel wreath with filigree, gold fan-spoked wheels on black tyres, gold mudguards (red reflector on the rear), brown
leather saddles with a gold crown on the back, brown leather grips and roller pedals, a big gold head lamp, ornate
gold chainrings and gold chains. Captain bars loop up and forward then back to the grips; the stoker bars clamp to the
captain's seat post.

Rig: the game tandem's own armature (out/bike/bike_rigged_goosefit26.blend) with its Pedal and WheelSpin clips and
every socket (Seat_*, Grip_*, PedalPin_*), so every goose rider fits it as it fits the game tandem: nothing to
re-bake. Its meshes are thrown away and the new bike is built on the same bones:
  Bike_root  frame, saddles, chains, rear guard, stoker bars    Steer  fork, lamp, stem, bars, front guard
  Wheel_F|R  wheels      Crank_F|R  chainrings + crank arms      Pedal_*  pedals
The side ref is close to the rig's scale (hub to hub 1110 px = 1.806 m); frame points are traced from it with
art(px, py), which warps the art along the bike so its bottom brackets land on the rig's.

Writes out/gold_standard/gold_standard_tandem.glb (+ _info.json, .blend) and with --sheet renders/gold_standard/*.png.
Builds:  (default) full detail, ~140k tris   --game  the game asset (_game, ~88k tris -> Tandemonium
tandem-3d/goose/gold_standard_tandem.glb)   --tag master --frame-tris 2000000  the full sculpt (~1.05M tris, Drive).
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(k, d=None):
    return argv[argv.index(k) + 1] if k in argv else d


# --game: the in-game build (lighter frame, the engraving decimated, fewer saddle segments); --tag names the outputs
# (gold_standard_tandem_<tag>.glb), e.g. --tag master --frame-tris 2000000 keeps the full-detail sculpt
GAME = "--game" in argv
TAG = arg("--tag", "game" if GAME else "")
SFX = ("_" + TAG) if TAG else ""


BASE = Path(arg("--base", str(ROOT.parent / "tandemonium-claude-3d" / "out" / "bike" / "bike_rigged_goosefit26.blend")))
OUT = ROOT / "out" / "gold_standard"
REN = ROOT / "renders" / "gold_standard"
OUT.mkdir(parents=True, exist_ok=True)
REN.mkdir(parents=True, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=str(BASE))
RIG = bpy.data.objects["bike_rig"]
for o in list(bpy.data.objects):
    if o.type == "MESH":
        bpy.data.objects.remove(o, do_unlink=True)
for m in list(bpy.data.meshes):
    bpy.data.meshes.remove(m)
for m in list(bpy.data.materials):
    bpy.data.materials.remove(m)
SC = bpy.context.scene
COL = SC.collection
BONE = {b.name: b for b in RIG.data.bones}


def bh(n):
    return Vector(RIG.matrix_world @ BONE[n].head_local)


# ------------------------------------------------------------------ materials
def mat(name, rgb, metallic=0.0, rough=0.5, emit=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bs = m.node_tree.nodes["Principled BSDF"]
    bs.inputs["Base Color"].default_value = (*rgb, 1)
    bs.inputs["Metallic"].default_value = metallic
    bs.inputs["Roughness"].default_value = rough
    if emit:
        bs.inputs["Emission Color"].default_value = (*emit, 1)
        bs.inputs["Emission Strength"].default_value = strength
    return m


M = {
    # metallic kept below 1: full metal reads black under the game's lean-mode lighting (Time Warp lesson)
    "gold": mat("gs_gold", (1.0, 0.6, 0.1), 0.5, 0.28),
    "gold_deep": mat("gs_gold_deep", (0.33, 0.145, 0.022), 0.75, 0.27),     # recessed emblem panel, ring backing
    "leather": mat("gs_leather", (0.30, 0.12, 0.045), 0.0, 0.62),
    "leather_dark": mat("gs_leather_dark", (0.12, 0.045, 0.015), 0.0, 0.6),
    "leather_skirt": mat("gs_leather_skirt", (0.17, 0.062, 0.025), 0.0, 0.5),     # the saddles' side + back skirt
    "rubber": mat("gs_rubber", (0.025, 0.025, 0.025), 0.0, 0.85),
    "lens": mat("gs_lamp", (1.0, 0.88, 0.5), 0.0, 0.2, (1.0, 0.8, 0.35), 2.5),
    "reflector": mat("gs_reflector", (0.75, 0.02, 0.01), 0.0, 0.25, (0.8, 0.02, 0.01), 0.6),
}


# ------------------------------------------------------------------ geometry helpers (all in bike space, -Y forward)
def obj(name, bm, material):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    COL.objects.link(o)
    me.materials.append(M[material] if isinstance(material, str) else material)
    for p in me.polygons:
        p.use_smooth = True
    return o


def frame(p0, p1):
    """Rotation taking +Z to p1 - p0."""
    d = (Vector(p1) - Vector(p0)).normalized()
    return Vector((0, 0, 1)).rotation_difference(d).to_matrix().to_4x4()


def cyl(p0, p1, r, material, seg=16, r2=None, caps=True):
    p0, p1 = Vector(p0), Vector(p1)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=caps, segments=seg, radius1=r, radius2=r if r2 is None else r2, depth=(p1 - p0).length)
    bm.transform(Matrix.Translation((p0 + p1) / 2) @ frame(p0, p1))
    return obj("cyl", bm, material)


def sphere(c, r, material, seg=10, scale=(1, 1, 1)):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=max(6, seg // 2), radius=r)
    bm.transform(Matrix.Translation(Vector(c)) @ Matrix.Diagonal((*scale, 1)))
    return obj("sph", bm, material)


def torus(c, R, r, material, axis=(1, 0, 0), seg=32, tseg=6):
    bm = bmesh.new()
    rows = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        ctr = Vector((R * math.cos(a), R * math.sin(a), 0))
        out = Vector((math.cos(a), math.sin(a), 0))
        rows.append([bm.verts.new(ctr + out * (r * math.cos(2 * math.pi * j / tseg)) + Vector((0, 0, r * math.sin(2 * math.pi * j / tseg))))
                     for j in range(tseg)])
    for i in range(seg):
        for j in range(tseg):
            bm.faces.new([rows[i][j], rows[(i + 1) % seg][j], rows[(i + 1) % seg][(j + 1) % tseg], rows[i][(j + 1) % tseg]])
    bm.transform(Matrix.Translation(Vector(c)) @ frame((0, 0, 0), axis))
    return obj("torus", bm, material)


def sweep(points, r_lat, r_in, material, tseg=12, closed_caps=True):
    """Tube along a polyline in (roughly) the bike's YZ plane with an elliptical section: r_lat across the bike (X),
    r_in in the bike plane. r_lat / r_in are numbers, lists (one per point) or functions of t in [0, 1]."""
    P = [Vector(p) for p in points]
    n = len(P)

    def rv(r, i):
        if callable(r):
            return r(i / (n - 1))
        if isinstance(r, (list, tuple)):
            return r[i]
        return r
    bm = bmesh.new()
    rows = []
    for i in range(n):
        a = P[max(i - 1, 0)]
        b = P[min(i + 1, n - 1)]
        t = (b - a).normalized()
        u = Vector((1, 0, 0))
        u = (u - t * u.dot(t))
        u = u.normalized() if u.length > 1e-6 else Vector((0, 1, 0))
        w = t.cross(u).normalized()
        rl, ri = rv(r_lat, i), rv(r_in, i)
        rows.append([bm.verts.new(P[i] + u * (rl * math.cos(2 * math.pi * j / tseg)) + w * (ri * math.sin(2 * math.pi * j / tseg)))
                     for j in range(tseg)])
    for i in range(n - 1):
        for j in range(tseg):
            bm.faces.new([rows[i][j], rows[i + 1][j], rows[i + 1][(j + 1) % tseg], rows[i][(j + 1) % tseg]])
    if closed_caps:
        for row, flip in ((rows[0], True), (rows[-1], False)):
            c = bm.verts.new(sum((v.co for v in row), Vector()) / len(row))
            for j in range(tseg):
                f = [row[j], row[(j + 1) % tseg], c]
                bm.faces.new(f[::-1] if flip else f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return obj("sweep", bm, material)


def tube(points, r, material, tseg=8):
    return sweep(points, r, r, material, tseg)


def bezier(p0, p1, p2, n=12, p3=None):
    p0, p1, p2 = Vector(p0), Vector(p1), Vector(p2)
    if p3 is None:
        return [p0 * (1 - t) ** 2 + p1 * 2 * t * (1 - t) + p2 * t * t for t in (i / n for i in range(n + 1))]
    p3 = Vector(p3)
    return [p0 * (1 - t) ** 3 + p1 * 3 * t * (1 - t) ** 2 + p2 * 3 * t * t * (1 - t) + p3 * t ** 3 for t in (i / n for i in range(n + 1))]


def catmull(pts, per=6):
    """Smooth curve through the points (Catmull-Rom)."""
    P = [Vector(p) for p in pts]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(per):
            t = k / per
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-2])
    return out


def box(c, size, material, bevel=0.0, rot=None):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    m = Matrix.Translation(Vector(c)) @ (rot if rot is not None else Matrix.Identity(4)) @ Matrix.Diagonal((*size, 1))
    bm.transform(m)
    o = obj("box", bm, material)
    if bevel:
        mo = o.modifiers.new("bev", "BEVEL")
        mo.width = bevel
        mo.segments = 2
        apply_mods(o)
    return o


def apply_mods(o):
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    for mo in list(o.modifiers):
        bpy.ops.object.modifier_apply(modifier=mo.name)
    o.select_set(False)


def lathe(profile, axis_p0, axis_dir, material, seg=24):
    """Surface of revolution: profile = [(t along axis, radius)]."""
    d = Vector(axis_dir).normalized()
    up = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
    u = d.cross(up).normalized()
    w = d.cross(u).normalized()
    bm = bmesh.new()
    rows = []
    for t, r in profile:
        rows.append([bm.verts.new(Vector(axis_p0) + d * t + (u * math.cos(2 * math.pi * j / seg) + w * math.sin(2 * math.pi * j / seg)) * r)
                     for j in range(seg)])
    for i in range(len(rows) - 1):
        for j in range(seg):
            bm.faces.new([rows[i][j], rows[i][(j + 1) % seg], rows[i + 1][(j + 1) % seg], rows[i + 1][j]])
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    return obj("lathe", bm, material)


def plate(pts2d, origin, u, v, material, thick=0.002, smooth=False):
    """A thin plate: outline pts2d = [(a, b)] at origin + u*a + v*b, extruded thick along u x v (centred)."""
    o0, u, v = Vector(origin), Vector(u).normalized(), Vector(v).normalized()
    nrm = u.cross(v).normalized()
    bm = bmesh.new()
    fr = [bm.verts.new(o0 + u * a + v * b - nrm * thick / 2) for a, b in pts2d]
    bk = [bm.verts.new(o0 + u * a + v * b + nrm * thick / 2) for a, b in pts2d]
    bm.faces.new(fr[::-1])
    bm.faces.new(bk)
    n = len(pts2d)
    for i in range(n):
        bm.faces.new([fr[i], fr[(i + 1) % n], bk[(i + 1) % n], bk[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    o = obj("plate", bm, material)
    for p in o.data.polygons:
        p.use_smooth = smooth
    return o


def ell(a0, b0, ra, rb, n=16, rot=0.0):
    out = []
    for k in range(n):
        t = 2 * math.pi * k / n
        a, b = ra * math.cos(t), rb * math.sin(t)
        out.append((a0 + a * math.cos(rot) - b * math.sin(rot), b0 + a * math.sin(rot) + b * math.cos(rot)))
    return out


PARTS = {}


def add(bone, *obs, name=None):
    """Hang parts on a rig bone; name = its own mesh (the game's crash code knocks off the saddles and the
    stoker's bars by the game tandem's mesh names, js/physics/bike-parts.js)."""
    PARTS.setdefault((bone, name), []).extend(obs)


# ------------------------------------------------------------------ key points from the rig
HUB_F, HUB_R = bh("Wheel_F"), bh("Wheel_R")
WR = 0.33                                          # wheel radius (the rig's hub height)
BB_F, BB_R = bh("Crank_F"), bh("Crank_R")
ST0 = bh("Steer")
STD = (Vector(RIG.matrix_world @ BONE["Steer"].tail_local) - ST0).normalized()
SEAT_C, SEAT_S = bh("Seat_Captain"), bh("Seat_Stoker")
GRIP = {k: bh(k) for k in ("Grip_C_L", "Grip_C_R", "Grip_S_L", "Grip_S_R")}


def steer_pt(s):
    return ST0 + STD * s


def V(y, z, x=0.0):
    return Vector((x, y, z))


# side ref (1536 x 768, front to the right) -> bike space. The ref is drawn at the rig's scale (hub to hub 1110 px =
# 1.806 m) but puts its cranks ~0.1 m further back than the rig's, and the geese pedal the rig's cranks. So along the
# bike the art is mapped with a smooth monotone curve (PCHIP: no kinks, so the art's curves stay curves) through its
# hubs and bottom brackets onto the rig's; height keeps the ref's scale about its hub line, less a gentle drop where
# the art stands taller than the rig (its bottom brackets sit ~4 cm higher).
_S = 1.806 / 1110
_KX = [212.0, 458.0, 865.0, 1322.0]
_KY = [HUB_R.y, BB_R.y, BB_F.y, HUB_F.y]


def _pchip_m():
    h = [b - a for a, b in zip(_KX, _KX[1:])]
    d = [(y1 - y0) / hh for y0, y1, hh in zip(_KY, _KY[1:], h)]
    m = [d[0]]
    for k in range(1, len(_KX) - 1):
        w1, w2 = 2 * h[k] + h[k - 1], h[k] + 2 * h[k - 1]
        m.append((w1 + w2) / (w1 / d[k - 1] + w2 / d[k]) if d[k - 1] * d[k] > 0 else 0.0)
    m.append(d[-1])
    return m


_KM = _pchip_m()


NOWARP = "--nowarp" in argv     # debug: the art at its own uniform scale, no easing onto the rig (overlays the ref 1:1)


def _along(px):
    if NOWARP:
        return HUB_R.y - (px - 212) * _S
    if px <= _KX[0]:
        return _KY[0] + (px - _KX[0]) * _KM[0]
    if px >= _KX[-1]:
        return _KY[-1] + (px - _KX[-1]) * _KM[-1]
    for k in range(len(_KX) - 1):
        if _KX[k] <= px <= _KX[k + 1]:
            h = _KX[k + 1] - _KX[k]
            t = (px - _KX[k]) / h
            return ((2 * t ** 3 - 3 * t * t + 1) * _KY[k] + (t ** 3 - 2 * t * t + t) * h * _KM[k]
                    + (-2 * t ** 3 + 3 * t * t) * _KY[k + 1] + (t ** 3 - t * t) * h * _KM[k + 1])


def _dz(px):
    """One smooth bow (a parabola): ~4 cm down mid-bike, ~0 at the head tube. Piecewise ramps put waves in every tube."""
    if NOWARP:
        return 0.0
    return -0.042 * max(0.0, 1 - ((px - 700) / 560) ** 2)


def art(px, py, x=0.0):
    hub_py = 528.5 if NOWARP else 520 + (px - 212) / 1110 * 17     # the art is drawn ~0.9 deg nose-down; the bike is level
    z = WR + (hub_py - py) * _S
    # the drop only applies low down (the rig's cranks sit lower than the art's); the top tube and plate keep the art's height
    lo = 1.0 - min(1.0, max(0.0, (z - 0.32) / 0.34)) ** 2 * (3 - 2 * min(1.0, max(0.0, (z - 0.32) / 0.34)))
    return Vector((x, _along(px), z + _dz(px) * lo))


# ------------------------------------------------------------------ wheels (Wheel_F / Wheel_R): gold fan spokes, black tyres
def fan_spoke(hub, a, r0, r1, x, th=0.007):
    """A flat blade in the wheel plane, narrow at the hub and flaring wide at the rim (the ref's tulip spokes)."""
    d = Vector((0, math.cos(a), math.sin(a)))
    s = Vector((0, -math.sin(a), math.cos(a)))
    prof = [(0.0, 0.006), (0.45, 0.007), (0.75, 0.011), (0.9, 0.019), (1.0, 0.03)]
    left = [(r0 + (r1 - r0) * t, w) for t, w in prof]
    pts = [(r, w) for r, w in left] + [(r, -w) for r, w in left[::-1]]
    return plate(pts, hub + Vector((x, 0, 0)), d, s, "gold", th, smooth=False)


def wheel(bone, hub):
    obs = [torus(hub, WR - 0.019, 0.019, "rubber", seg=48, tseg=10),             # tyre
           torus(hub, WR - 0.042, 0.012, "gold", seg=48, tseg=8),                # rim
           torus(hub, WR - 0.058, 0.006, "gold", seg=48, tseg=6),                # inner rim bead
           cyl(hub + Vector((-0.05, 0, 0)), hub + Vector((0.05, 0, 0)), 0.02, "gold", 18),
           lathe([(0, 0.0), (0.0, 0.045), (0.012, 0.04), (0.022, 0.018), (0.03, 0.0)], hub + Vector((0.008, 0, 0)), (1, 0, 0), "gold", 20),
           lathe([(0, 0.0), (0.0, 0.045), (0.012, 0.04), (0.022, 0.018), (0.03, 0.0)], hub + Vector((-0.008, 0, 0)), (-1, 0, 0), "gold", 20)]
    for k in range(16):
        obs.append(fan_spoke(hub, 2 * math.pi * k / 16 + 0.1, 0.035, WR - 0.05, 0.0))
    add(bone, *obs)


wheel("Wheel_F", HUB_F)
wheel("Wheel_R", HUB_R)


# ------------------------------------------------------------------ guards (gold), rear reflector
def guard(bone, hub, a0, a1, R=WR + 0.03, w=0.036, flare=0.02, taper=0.0):
    rows_n = 30
    bm = bmesh.new()
    G = []
    for i in range(rows_n + 1):
        t = i / rows_n
        a = math.radians(a0 + (a1 - a0) * t)
        rad = Vector((0, -math.cos(a), math.sin(a)))
        rr = R + flare * max(0.0, t - 0.75) / 0.25                         # the tail flicks out (ref)
        row = []
        tq = min(1.0, t / taper) if taper > 0 else 1.0
        wt = w * (1.0 - (1.0 - tq * tq * (3 - 2 * tq)) * 0.7)          # front end narrows into the hook
        for xx in (-wt, -wt * 0.5, 0, wt * 0.5, wt):
            crown = 0.014 * (1 - (xx / wt) ** 2)
            row.append(bm.verts.new(hub + rad * (rr + crown - (0.012 if abs(xx) == wt else 0)) + Vector((xx, 0, 0))))
        G.append(row)
    for i in range(rows_n):
        for j in range(4):
            bm.faces.new([G[i][j], G[i + 1][j], G[i + 1][j + 1], G[i][j + 1]])
    o = obj("guard", bm, "gold")
    mo = o.modifiers.new("sol", "SOLIDIFY")
    mo.thickness = 0.003
    apply_mods(o)
    add(bone, o)
    for xx in (-w + 0.002, w - 0.002):
        pts = []
        for i in range(rows_n + 1):
            t = i / rows_n
            a = math.radians(a0 + (a1 - a0) * t)
            rr = R + flare * max(0.0, t - 0.75) / 0.25 - 0.012
            pts.append(hub + Vector((0, -math.cos(a), math.sin(a))) * rr + Vector((xx, 0, 0)))
        add(bone, tube(pts, 0.0035, "gold", tseg=5))


guard("Steer", HUB_F, 70, 200)
guard("Bike_root", HUB_R, 78, 172, taper=0.10)
_ar = math.radians(140)
_rp = HUB_R + Vector((0, -math.cos(_ar), math.sin(_ar))) * (WR + 0.03 + 0.016)
_rn = Vector((0, -math.cos(_ar), math.sin(_ar)))
add("Bike_root", lathe([(0, 0.0), (0, 0.022), (0.006, 0.02), (0.009, 0.0)], _rp, _rn, "reflector", 20),
    torus(_rp, 0.023, 0.003, "gold", axis=_rn, seg=20, tseg=4))

# ------------------------------------------------------------------ frame (Bike_root): traced from the side ref, fused
# Every frame member is a centreline traced on refs/gold_standard/pete_refs/side.png (pixel coords, front to the
# right) with its width in pixels at that point. Members are swept with an elliptical section (in-plane radius from
# the art; across the bike capped at CAP so wide parts read as flat plates, like the ref's crown plate), the crown
# plate and the cluster web are flat slabs, and everything is fused with a voxel remesh + smoothing so the joints web
# together like the art. Ends that meet the rig (head tube, bottom brackets, saddle clamps) are eased onto it.
CAP = 0.028                                     # half thickness across the bike (top ref: frame ~5-6 cm wide)
WIDTH_GAIN = 1.12                               # the mask misses the white specular edge of every tube: widths read ~10% thin
H_TOP, H_BOT = steer_pt(0.235), steer_pt(-0.005)
SEAT_CLAMP_C = V(SEAT_C.y - 0.02, SEAT_C.z - 0.08)
SEAT_CLAMP_S = V(SEAT_S.y - 0.02, SEAT_S.z - 0.08)
# where the frame's posts hand over to the saddle clamps: back along each post's own direction in the art, so the
# post runs straight into its clamp (no elbow)
C_POST0 = SEAT_CLAMP_C + V(-0.022, -0.045)
S_POST0 = SEAT_CLAMP_S + V(-0.03, -0.04)


def smooth01(e0, e1, v):
    t = min(1.0, max(0.0, (v - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def eased(pts, start=None, end=None, frac=0.3):
    """Move a stroke's ends onto targets, easing the shift out along frac of its length (keeps the art's curve)."""
    P = [Vector(p) for p in pts]
    L = [0.0]
    for a, b in zip(P, P[1:]):
        L.append(L[-1] + (b - a).length)
    tot = L[-1] or 1.0
    out = []
    ds = (Vector(start) - P[0]) if start is not None else Vector()
    de = (Vector(end) - P[-1]) if end is not None else Vector()
    for p, l in zip(P, L):
        u = l / tot
        out.append(p + ds * (1 - smooth01(0, frac, u)) + de * smooth01(1 - frac, 1, u))
    return out


def splay(pts, sx):
    """Near the rear hub a member splits into a pair either side of the tyre (it can't be one piece through it)."""
    out = []
    for p in pts:
        d = math.hypot(p.y - HUB_R.y, p.z - HUB_R.z)
        out.append(p + Vector((sx * 0.058 * smooth01(0.45, 0.33, d), 0, 0)))   # one tube at the cluster
    return out


# the ref's frame silhouette (scripts/gs_frame_mask.py): traced points snap onto its medial ridge and take its width
_MASK_IMG = bpy.data.images.load(str(ROOT / "refs" / "gold_standard" / "frame_mask.png"))
_MW, _MH = _MASK_IMG.size
MASK = (np.array(_MASK_IMG.pixels[:], dtype=np.float32).reshape(_MH, _MW, 4)[::-1, :, 0] > 0.5)
SNAP_LOG = {}


def edt_at(x, y, win=26):
    """Distance (px) from (x, y) to the nearest non-frame pixel of MASK, 0 if outside the frame."""
    xi, yi = int(round(x)), int(round(y))
    if not (0 <= xi < _MW and 0 <= yi < _MH) or not MASK[yi, xi]:
        return 0.0
    x0, x1, y0, y1 = max(0, xi - win), min(_MW, xi + win + 1), max(0, yi - win), min(_MH, yi + win + 1)
    bg = np.argwhere(~MASK[y0:y1, x0:x1])
    if not len(bg):
        return float(win)
    return float(np.sqrt(((bg[:, 1] + x0 - x) ** 2 + (bg[:, 0] + y0 - y) ** 2).min()))


def snap(Q, W, reach=18, until_px=None):
    """Slide each densified point across its stroke onto the ref's medial ridge; width = 2 x distance to the edge.
    Points the mask can't see (cut away round wheels, cranks, guards) keep the hand trace; then a light smoothing."""
    out_q, out_w = [], []
    for i, (q, w) in enumerate(zip(Q, W)):
        if i in (0, len(Q) - 1) or (until_px is not None and q.x > until_px):
            out_q.append(q)                               # ends are joints; edge rails of the plate stay on their edge
            out_w.append(w)
            continue
        a, b = Q[max(i - 1, 0)], Q[min(i + 1, len(Q) - 1)]
        t = (b - a)
        t = Vector((t.x, t.y, 0)).normalized() if t.length > 1e-6 else Vector((1, 0, 0))
        n = Vector((-t.y, t.x, 0))
        best = (edt_at(q.x, q.y), 0.0)
        for o in range(-reach, reach + 1):
            d = edt_at(q.x + n.x * o, q.y + n.y * o)
            if d > best[0] + 0.01 or (abs(d - best[0]) <= 0.01 and abs(o) < abs(best[1])):
                best = (d, o)
        if best[0] >= 4.0:
            out_q.append(q + n * best[1])
            # the art's width, but kept near the hand trace: at joints the silhouette merges and would balloon
            out_w.append(Vector((min(max(2 * best[0], 0.85 * w.x), 1.2 * w.x), 0, 0)))
        else:
            out_q.append(q)
            out_w.append(w)
    for _ in range(12):                                   # smooth hard: clean curves, steady tapers, no wobble
        out_q = [out_q[0]] + [out_q[i - 1] * 0.25 + out_q[i] * 0.5 + out_q[i + 1] * 0.25 for i in range(1, len(out_q) - 1)] + [out_q[-1]]
        out_w = [out_w[0]] + [out_w[i - 1] * 0.25 + out_w[i] * 0.5 + out_w[i + 1] * 0.25 for i in range(1, len(out_w) - 1)] + [out_w[-1]]
    return out_q, out_w


def member(px_pts, widths, start=None, end=None, frac=0.3, per=6, pair=False, name=None, snapped=True, until_px=None,
           fit=True, lat_max=None):
    """A traced frame member: art points [(px, py)] + full widths in px -> swept meshes (two if pair)."""
    Q = catmull([Vector((px, py, 0)) for px, py in px_pts], per)
    W = catmull([Vector((w, 0, 0)) for w in widths], per)
    if snapped:
        Q, W = snap(Q, W, until_px=until_px)
    if name:
        SNAP_LOG[name] = [(round(q.x, 1), round(q.y, 1), round(w.x, 1)) for q, w in zip(Q, W)]
    P = [art(q.x, q.y) for q in Q]
    if not NOWARP:
        P = eased(P, start, end, frac)
    r_in = [max(0.006, w.x / 2 * _S * WIDTH_GAIN) for w in W]
    if fit and len(P) > 4:                        # one smooth arc through the trace, ends pinned
        Qa = np.array([(p.y, p.z) for p in P])
        Kf = fit if isinstance(fit, int) and fit > 1 else min(7, max(4, len(px_pts) + 1))
        cpm, um = fit_arc(Qa, Kf, 3e-4)
        Qs, us = arc_sample(cpm, 0.004)
        if name:
            bend_report(name, Qs)
        r_in = list(np.interp(us, um, r_in))
        P = [Vector((0.0, y, z)) for y, z in Qs]
    r_lat = [min(r, CAP, lat_max or CAP) for r in r_in]
    if not pair:
        return [sweep(P, r_lat, r_in, "gold", 14)]
    return [sweep(splay(P, sx), [min(r, 0.018) for r in r_lat], r_in, "gold", 14) for sx in (1, -1)]


def slab(px_poly, half, per=4):
    """A flat slab filling an outline traced on the art (closed), half thickness across the bike."""
    P = catmull([art(px, py) for px, py in px_poly + px_poly[:1]], per)[:-1]
    return plate([(p.y, p.z) for p in P], V(0, 0), (0, 1, 0), (0, 0, 1), "gold", half * 2)


# traced centrelines (px) and widths (px)
# (measured down the ref's columns: top swoop 500:324-359, 560:311-341, 640:295-324, 700:285-321; plate top edge
#  800:252, 900:256, 1000:247, 1100:241; plate bottom edge 760:334, 800:367, 900:384, 1000:338, 1100:305, 1180:299;
#  diagonal 760:424-456, 700:457-485, 640:486-515; down tube 1000:462-499, 1100:374-407, 1180:320-351)
# (centres smoothed so the slope eases steadily: -0.23 at the cluster to flat at the head; 800's top edge is lifted by
#  the captain post's fillet and 700's reading includes the top rail, so neither is taken literally)
TOP_SWOOP = ([(430, 352), (500, 341), (560, 327), (640, 312), (700, 302), (760, 291), (820, 280), (900, 270), (1000, 262),
              (1100, 256), (1170, 256), (1208, 254)],
             [44, 36, 31, 30, 31, 30, 30, 30, 30, 30, 30, 32])
PLATE_LOW = ([(760, 322), (800, 354), (850, 371), (900, 371), (1000, 326), (1100, 294), (1180, 287), (1222, 296)],
             [24, 26, 26, 26, 24, 22, 24, 28])
SEAT_STAY = ([(212, 518), (255, 490), (330, 435), (390, 392), (430, 368)], [26, 28, 31, 35, 42])
DIAGONAL = ([(700, 471), (640, 500), (590, 518), (530, 538)], [29, 30, 30, 32])   # the core sculpt carries it above x=668
BAR_UP = ([(630, 500), (690, 497), (765, 503), (812, 522), (862, 550)], [16, 15, 16, 18, 22])
BAR_LOW = ([(468, 552), (540, 549), (620, 550), (690, 555), (790, 562), (862, 558)], [28, 25, 23, 23, 28, 30])
C_SEAT_TUBE = ([(813, 425), (818, 440), (826, 458), (840, 482), (858, 522), (865, 553)], [34, 30, 24, 21, 21, 24])   # flared into the lower tube (in plane)
DOWN_TUBE = ([(1215, 322), (1175, 342), (1100, 392), (1000, 478), (940, 525), (890, 552)], [28, 24, 22, 21, 22, 28])
STOKER_POST = ([(425, 342), (410, 325), (392, 300), (372, 262), (352, 228)], [38, 30, 26, 24, 24])
CAPT_POST = ([(818, 272), (812, 255), (805, 238), (798, 224)], [26, 22, 20, 20])
CHAINSTAY = ([(212, 520), (300, 528), (400, 538), (458, 543)], [20, 22, 26, 32])
CLUSTER_WEB = [(380, 318), (425, 330), (470, 345), (420, 372), (385, 392), (372, 360)]

# ------------------------------------------------------------------ the core sculpt (Pete 2026-11-09: "the core most
# important design of the bike frame"): the top tube that runs from behind the lamp all the way back to the rear hub,
# the lower tube that sweeps from behind the lamp down to the rear cranks, and the crown plate filling between them,
# which ends in the rounded curve just behind the captain's seat. The whole region is cut straight out of the side
# ref's silhouette and inflated: every point stands out from the bike's centre plane by a quarter circle of its
# distance to the outline (narrow parts come out as round tubes, wide parts as a plate CORE_HALF thick with rounded
# edges), the crown panel is sunk into the plate with a bead round it, and the result is mapped through art() and
# eased onto the rig's head tube.
CORE_ZONE = [(410, 300), (440, 318), (468, 296), (560, 250), (740, 250), (760, 270), (800, 265), (850, 259), (872, 256),
             (876, 234), (1203, 230), (1203, 296), (1150, 312), (1100, 338), (1000, 400), (900, 425), (872, 432),
             (860, 451), (812, 451), (780, 458), (700, 489), (668, 503), (668, 420), (470, 405), (440, 420),
             (390, 432), (352, 378), (376, 298)]
# white specular highlights inside the gold that the colour mask reads as background (filled back in)
CORE_FILL = [[(1110, 262), (1203, 258), (1203, 300), (1150, 302), (1110, 292)],
             [(797, 352), (832, 352), (832, 415), (770, 420), (786, 406), (797, 399), (803, 388), (805, 378), (803, 367),
              (799, 359)],
             [(1080, 244), (1150, 242), (1203, 241), (1203, 262), (1080, 262)]]   # top tube's split highlight near the head
CORE_BLUR_PX = 2.0
# the sunken crown panel, measured down the ref's columns (its bead / dark edge line), front tip to the right
PANEL_PX = [(768, 299), (780, 296.5), (800, 292), (840, 286), (880, 280), (920, 277), (960, 273), (1000, 271), (1060, 271),
            (1100, 272), (1124, 275), (1136, 277.5), (1120, 279.5), (1100, 283), (1060, 297), (1000, 322), (960, 342),
            (935, 353), (915, 357), (895, 354), (880, 347), (860, 337), (840, 325), (800, 306), (780, 300.5)]
# The ref builds this region from two round tubes running along its outer edges with a thinner web between them
# (a groove shows between the tubes where there is no panel, ref x=1140), so: the web is the inflated outline capped
# at WEB_HALF_PX, the crown panel is sunk into the web, and the two tubes are swept along the outline's top and bottom
# edges with their radius measured from the ref (outer edge to the window / panel edge, capped per stretch).
# the small sunken triangle in the stoker's cluster, between the post, the top swoop and the seat stay (ref 4x crop)
CLUSTER_PX = [(384, 321), (395, 326), (406, 334), (418, 343), (429, 352), (415, 359), (400, 368), (388, 374), (376, 378),
              (377, 365), (378, 350), (380, 335)]
# every sunken panel: outline (ref px) and the corners the floor inlay must not be inset at
PANELS = [(PANEL_PX, [PANEL_PX[0], max(PANEL_PX, key=lambda q: q[0])]),
          (CLUSTER_PX, [(384, 321), (429, 352), (376, 378)])]
CORE_HALF_PX = CAP / _S                         # the tubes' largest half thickness in ref px (~17)
WEB_HALF_PX = 10.0                              # the web between the tubes
FILLET_PX = float(arg("--fillet", "6"))
CLUSTER_WEB_PX = 6.0                            # the stoker's cluster web (its tubes are ~10 px radius)


def web_half(px):
    """Web half thickness (ref px) along the frame: thin in the stoker's cluster, full along the core."""
    t = np.clip((np.asarray(px, np.float64) - 470.0) / 90.0, 0.0, 1.0)
    return CLUSTER_WEB_PX + (WEB_HALF_PX - CLUSTER_WEB_PX) * t * t * (3 - 2 * t)         # web-to-tube fillet (smooth max width, ref px)
PANEL_DEPTH_PX = 4.0                            # the panel floor sits this far below the web face
PANEL_RAMP_PX = 2.5
PLATE_HALF = (WEB_HALF_PX - PANEL_DEPTH_PX) * _S
# approximate centrelines (ref px); each sample is pushed out along its normal to sit one radius inside the outline
TUBE1_GUIDE = [(405, 352), (450, 350), (500, 341), (560, 328), (640, 310), (700, 301), (760, 290), (820, 279), (900, 268),
               (1000, 260), (1100, 255), (1160, 252), (1203, 251)]
TUBE2_GUIDE = [(1203, 300), (1150, 289), (1100, 294), (1050, 312), (1000, 331), (960, 350), (920, 368), (890, 380),
               (862, 392), (835, 405), (805, 421), (760, 441), (700, 471), (668, 487)]
TUBE1_RMAX = [(400, 18), (780, 16), (900, 13), (1203, 14)]
TUBE2_RMAX = [(668, 16), (820, 16), (900, 13), (1100, 12), (1203, 14)]
_HEAD_A, _HEAD_B = (1208, 254), (1222, 296)     # where the top and lower tubes meet the head tube in the art
_D_TOP = steer_pt(0.19) - art(*_HEAD_A)
_D_LOW = steer_pt(0.05) - art(*_HEAD_B)
_D_TOP.x = _D_LOW.x = 0.0


def core_map(px, py, x=0.0):
    """art() plus the core's ease onto the rig's head tube (the art's head sits a little off the rig's steer axis)."""
    p = art(px, py, x)
    if NOWARP:
        return p
    t = min(1.0, max(0.0, (py - _HEAD_A[1]) / (_HEAD_B[1] - _HEAD_A[1])))
    return p + (_D_TOP * (1 - t) + _D_LOW * t) * smooth01(1040, 1210, px)


def _poly_fill(shape, pts, ox=0, oy=0):
    """Filled polygon (even-odd) on a pixel grid whose (0, 0) is ref px (ox, oy); pixel centres at integers."""
    h, w = shape
    yy, xx = np.mgrid[0:h, 0:w]
    xx, yy = xx + ox, yy + oy
    inside = np.zeros(shape, bool)
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        if y0 == y1:
            continue
        cond = (yy >= min(y0, y1)) & (yy < max(y0, y1))
        inside ^= cond & (xx < x0 + (yy - y0) * (x1 - x0) / (y1 - y0))
    return inside


def _shift(a, dy, dx, fill):
    out = np.full_like(a, fill)
    h, w = a.shape
    out[max(dy, 0):h + min(dy, 0), max(dx, 0):w + min(dx, 0)] = a[max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    return out


def _dilate(m, r):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r:
                out |= _shift(m, dy, dx, False)
    return out


def _blur(a, s):
    k = int(3 * s)
    wts = [math.exp(-0.5 * (i / s) ** 2) for i in range(-k, k + 1)]
    tot = sum(wts)
    for ax in (0, 1):
        acc = np.zeros_like(a)
        for i, wt in zip(range(-k, k + 1), wts):
            acc += wt * (_shift(a, i, 0, 0.0) if ax == 0 else _shift(a, 0, i, 0.0))
        a = acc / tot
    return a


def _maxfilt(a, r):
    for ax in (0, 1):
        acc = a.copy()
        for i in range(-r, r + 1):
            acc = np.maximum(acc, _shift(a, i, 0, 0.0) if ax == 0 else _shift(a, 0, i, 0.0))
        a = acc
    return a


def _contour(F):
    """Sub-pixel points where the field F crosses 0.5 (grid coords x, y)."""
    pts = []
    s = F - 0.5
    a, b = s[:, :-1], s[:, 1:]
    yy, xx = np.nonzero((a >= 0) != (b >= 0))
    t = a[yy, xx] / (a[yy, xx] - b[yy, xx])
    pts.append(np.stack([xx + t, yy], 1))
    a, b = s[:-1, :], s[1:, :]
    yy, xx = np.nonzero((a >= 0) != (b >= 0))
    t = a[yy, xx] / (a[yy, xx] - b[yy, xx])
    pts.append(np.stack([xx, yy + t], 1))
    return np.concatenate(pts, 0).astype(np.float32)


def _nearest(P, C, chunk=1500):
    """For points P (n, 2): distance to and index of the nearest of C (m, 2)."""
    d = np.empty(len(P), np.float32)
    k = np.empty(len(P), np.int64)
    for i in range(0, len(P), chunk):
        q = P[i:i + chunk]
        dd = (q[:, None, 0] - C[None, :, 0]) ** 2 + (q[:, None, 1] - C[None, :, 1]) ** 2
        k[i:i + chunk] = dd.argmin(1)
        d[i:i + chunk] = np.sqrt(dd[np.arange(len(q)), k[i:i + chunk]])
    return d, k


def _up2(a):
    """Bilinear upsample x2 on the grid's own points: (h, w) -> (2h - 1, 2w - 1)."""
    h, w = a.shape
    out = np.zeros((2 * h - 1, 2 * w - 1), np.float32)
    out[::2, ::2] = a
    out[1::2, ::2] = (a[:-1] + a[1:]) / 2
    out[:, 1::2] = (out[:, :-2:2] + out[:, 2::2]) / 2
    return out


def _along_np(px):
    px = np.asarray(px, np.float64)
    if NOWARP:
        return HUB_R.y - (px - 212) * _S
    kx, ky, km = np.array(_KX), np.array(_KY), np.array(_KM)
    out = np.empty_like(px)
    lo, hi = px <= kx[0], px >= kx[-1]
    out[lo] = ky[0] + (px[lo] - kx[0]) * km[0]
    out[hi] = ky[-1] + (px[hi] - kx[-1]) * km[-1]
    mid = ~(lo | hi)
    k = np.clip(np.searchsorted(kx, px[mid]) - 1, 0, len(kx) - 2)
    hh = kx[k + 1] - kx[k]
    t = (px[mid] - kx[k]) / hh
    out[mid] = ((2 * t ** 3 - 3 * t * t + 1) * ky[k] + (t ** 3 - 2 * t * t + t) * hh * km[k]
                + (-2 * t ** 3 + 3 * t * t) * ky[k + 1] + (t ** 3 - t * t) * hh * km[k + 1])
    return out


def core_map_np(px, py):
    """Vectorised core_map: arrays of ref px -> (Y, Z) arrays in bike space."""
    px, py = np.asarray(px, np.float64), np.asarray(py, np.float64)
    hub_py = 528.5 if NOWARP else 520 + (px - 212) / 1110 * 17
    z = WR + (hub_py - py) * _S
    if not NOWARP:
        s = np.clip((z - 0.32) / 0.34, 0.0, 1.0)
        z = z + (-0.042 * np.maximum(0.0, 1 - ((px - 700) / 560) ** 2)) * (1.0 - s * s * (3 - 2 * s))
    y = _along_np(px)
    if not NOWARP:
        t = np.clip((py - _HEAD_A[1]) / (_HEAD_B[1] - _HEAD_A[1]), 0.0, 1.0)
        u = np.clip((px - 1040) / (1210 - 1040), 0.0, 1.0)
        wgt = u * u * (3 - 2 * u)
        y = y + (_D_TOP.y * (1 - t) + _D_LOW.y * t) * wgt
        z = z + (_D_TOP.z * (1 - t) + _D_LOW.z * t) * wgt
    return y, z


CORE_RAW = None
CORE_FIELD = {}
_PXLUT = {}


def px_of(y, z):
    """Ref px (x, y) whose core_map lands nearest bike (y, z): lets parts designed in bike space join the traced web."""
    if not _PXLUT:
        gx, gy = np.meshgrid(np.arange(150.0, 1250.0, 0.5), np.arange(100.0, 620.0, 0.5))
        Y, Z = core_map_np(gx.ravel(), gy.ravel())
        _PXLUT.update(P=np.stack([gx.ravel(), gy.ravel()], 1), Q=np.stack([Y, Z], 1))
    d = (_PXLUT["Q"][:, 0] - y) ** 2 + (_PXLUT["Q"][:, 1] - z) ** 2
    return tuple(float(v) for v in _PXLUT["P"][int(np.argmin(d))])


def _bilinear(A, x, y):
    h, w = A.shape
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    return (A[y0, x0] * (1 - fx) * (1 - fy) + A[y0, x0 + 1] * fx * (1 - fy)
            + A[y0 + 1, x0] * (1 - fx) * fy + A[y0 + 1, x0 + 1] * fx * fy)


def _interp1(tab, x):
    return np.interp(x, [a for a, _ in tab], [b for _, b in tab])


def _bs_basis(u, K, deg=3):
    """Clamped uniform B-spline basis, (len(u), K)."""
    kn = np.concatenate([np.zeros(deg), np.linspace(0.0, 1.0, K - deg + 1), np.ones(deg)])
    u = np.clip(np.asarray(u, np.float64), 0.0, 1.0 - 1e-9)
    B = np.stack([((kn[i] <= u) & (u < kn[i + 1])).astype(np.float64) for i in range(len(kn) - 1)], 1)
    for d in range(1, deg + 1):
        nb = np.zeros((len(u), len(kn) - 1 - d))
        for i in range(len(kn) - 1 - d):
            a, b = kn[i + d] - kn[i], kn[i + d + 1] - kn[i + 1]
            if a > 0:
                nb[:, i] += (u - kn[i]) / a * B[:, i]
            if b > 0:
                nb[:, i] += (kn[i + d + 1] - u) / b * B[:, i + 1]
        B = nb
    return B


def fit_arc(P, K, lam, iters=6, w=None):
    """One smooth curve through a traced stroke: least-squares cubic B-spline with K control points, both ends pinned,
    bending penalised (lam), points re-projected onto the curve each pass. Returns (control points, u per input)."""
    P = np.asarray(P, np.float64)
    L = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    u = L / L[-1]
    W = np.ones(len(P)) if w is None else np.asarray(w, np.float64)
    D2 = np.diff(np.eye(K), 2, axis=0)
    uu = np.linspace(0.0, 1.0, 4000)
    Bu = _bs_basis(uu, K)
    for _ in range(iters):
        B = _bs_basis(u, K)
        A = (B * W[:, None]).T @ B + lam * W.sum() * (D2.T @ D2)
        rhs = (B * W[:, None]).T @ P - A[:, [0, K - 1]] @ np.stack([P[0], P[-1]])
        c = np.vstack([P[0], np.linalg.solve(A[1:-1, 1:-1], rhs[1:-1]), P[-1]])
        S = Bu @ c
        _, k = _nearest(P.astype(np.float64), S.astype(np.float64))
        u = np.maximum.accumulate(uu[k])
        u[0], u[-1] = 0.0, 1.0
    return c, u


def arc_sample(c, step):
    """Sample a fitted arc at (about) even spacing `step` (its own units)."""
    K = len(c)
    uu = np.linspace(0.0, 1.0, 6000)
    S = _bs_basis(uu, K) @ c
    L = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(S, axis=0), axis=1))]
    n = max(8, int(L[-1] / step))
    ut = np.interp(np.linspace(0.0, L[-1], n + 1), L, uu)
    return _bs_basis(ut, K) @ c, ut


def bend_report(name, S):
    """Tightest bend of a sampled curve (bike metres) and the number of times it changes bending direction."""
    S = np.asarray(S, np.float64)
    d1 = np.gradient(S, axis=0)
    d2 = np.gradient(d1, axis=0)
    sp = np.linalg.norm(d1, axis=1)
    cr = d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0] if S.shape[1] == 2 else np.linalg.norm(np.cross(d1, d2), axis=1)
    k = cr / np.maximum(sp ** 3, 1e-12)
    flips = int(np.sum(np.diff(np.sign(k[np.abs(k) > 0.15])) != 0)) if S.shape[1] == 2 else -1
    i = int(np.abs(k[3:-3]).argmax()) + 3
    print(f"BEND {name}: tightest radius {1 / max(abs(k[i]), 1e-9):.3f} m at {i}/{len(S)}  direction changes {flips}")
    BEND_LOG[name] = k
    return k


BEND_LOG = {}
BUILT = {}                                         # each core tube's final bike-space centre line (y, z)


def core_path(guide, rmax, outward, name, clip=(0, 9999), pre=None, post=None, K=8, lam=2e-4, trim=None, fade=(True, True), away=None):
    """Measure one core tube from the ref (ray-march each guide sample's normal to the outline: the tube touches the
    outer edge, radius = half the gap to the window / panel edge, capped), join the traced extensions, then fit ONE
    smooth arc through it all (no local wiggles). Returns the fitted centre / radius in ref px + the measured stroke."""
    F, pin, ox, oy = CORE_FIELD["F"], CORE_FIELD["pin"], CORE_FIELD["ox"], CORE_FIELD["oy"]
    Fin = F * (1 - pin)                           # the panel counts as an edge for the tube's inner side
    G = np.array([(q.x, q.y) for q in catmull([Vector((x, y, 0)) for x, y in guide], 10)], np.float64)
    T = np.gradient(G, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    N = np.stack([-T[:, 1], T[:, 0]], 1)
    if (N[:, 1] * outward).mean() < 0:
        N = -N                                                 # outward = -1: up the image, +1: down
    ts = np.arange(-24.0, 44.0, 0.25)
    X = G[:, None, 0] + N[:, None, 0] * ts[None] - ox
    Y = G[:, None, 1] + N[:, None, 1] * ts[None] - oy
    ins, ins_in = _bilinear(F, X, Y) >= 0.5, _bilinear(Fin, X, Y) >= 0.5
    RM = _interp1(rmax, G[:, 0])
    C = G.copy()
    r = RM.copy()
    ok = np.zeros(len(G), bool)
    for i in range(len(G)):
        idx = np.nonzero(ins[i])[0]
        if not len(idx):
            continue
        j0 = idx[np.abs(ts[idx]).argmin()]                     # the inside point nearest the guide
        out = np.nonzero(~ins[i, j0:])[0]
        if not len(out):
            continue
        t_out = ts[j0 + out[0]]
        if t_out - ts[j0] > 2 * RM[i] + 6:                     # ran up a joining tube (post, seat tube): no edge here
            continue
        back = np.nonzero(~ins_in[i, :j0 + 1])[0]
        t_in = ts[back[-1]] if len(back) else ts[0]
        r[i] = min((t_out - t_in) / 2, RM[i])
        C[i] = G[i] + N[i] * (t_out - r[i])
        ok[i] = True
    k = np.arange(len(G))
    for a in (0, 1):                                           # fill the samples with no edge from their neighbours
        C[~ok, a] = np.interp(k[~ok], k[ok], C[ok, a])
    r[~ok] = np.interp(k[~ok], k[ok], r[ok])
    keep = (G[:, 0] >= clip[0]) & (G[:, 0] <= clip[1])
    C, r, okk = C[keep], r[keep], ok[keep]

    def ext(pts):                                              # traced continuation [(px, py, r px)] -> dense arrays
        q = catmull([Vector(p) for p in pts], 8)
        return np.array([(v.x, v.y) for v in q]), np.array([v.z for v in q])
    wt = np.where(okk, 1.0, 0.35)                              # interpolated samples count for less
    if pre:
        a, b = ext(pre + [(C[0, 0], C[0, 1], r[0])])
        C, r, wt = np.concatenate([a[:-1], C]), np.concatenate([b[:-1], r]), np.concatenate([np.full(len(a) - 1, 1.0), wt])
    if post:
        a, b = ext([(C[-1, 0], C[-1, 1], r[-1])] + post)
        C, r, wt = np.concatenate([C, a[1:]]), np.concatenate([r, b[1:]]), np.concatenate([wt, np.full(len(a) - 1, 1.0)])
    cp, u = fit_arc(C, K, lam, w=wt)
    Bf = _bs_basis(u, K)
    dev = np.linalg.norm(Bf @ cp - C, axis=1)
    rc = np.linalg.solve(Bf.T @ Bf + 0.02 * len(C) * (np.diff(np.eye(K), 2, axis=0).T @ np.diff(np.eye(K), 2, axis=0)),
                         Bf.T @ r)                             # radius: same curve, smoother still
    S, us = arc_sample(cp, 1.0)
    rs = _bs_basis(us, K) @ rc
    print(f"ARC {name}: K={K} max dev {dev.max():.1f} px (mean {dev.mean():.1f}), r {rs.min():.1f}-{rs.max():.1f} px")
    SNAP_LOG[name] = [(round(float(a), 1), round(float(b), 1), round(float(2 * c), 1)) for (a, b), c in zip(S[::8], rs[::8])]
    # where this tube runs along the web: the web is trimmed at its centre line so its edge hides inside the tube
    tr = trim or clip
    tri = (S[:, 0] >= tr[0]) & (S[:, 0] <= tr[1])
    Tn = np.gradient(S, axis=0)
    Tn /= np.linalg.norm(Tn, axis=1, keepdims=True)
    Nn = np.stack([-Tn[:, 1], Tn[:, 0]], 1)
    if (Nn[:, 1] * outward).mean() < 0:
        Nn = -Nn
    if "--arc-debug" in argv:
        np.savez(str(REN / f"arc_{name}.npz"), S=S, r=rs, raw=C, rraw=r, cp=cp)
    trims = [(S[tri], Nn[tri], fade, 0.0)]
    for (ax0, ax1), cpt in (away or []):          # extra stretches trimmed on the side away from an interior point
        ta = (S[:, 0] >= ax0) & (S[:, 0] <= ax1)
        Na = Nn.copy()
        flip = ((S - np.array(cpt, float)) * Na).sum(1) < 0
        Na[flip] = -Na[flip]
        trims.append((S[ta], Na[ta], (False, True), 0.0))
    return dict(S=S, r=rs, trims=trims, raw=C)


TRACED_TRIM_IN = 3.0                               # px: the cluster web stops this far inside its tubes' centre lines


def traced_path(pts, radii, name, inside, K=6, lam=3e-4, toward=None):
    """A tube traced by hand on the ref (px points + radius px per point): one fitted arc; the web is trimmed on the
    side away from `inside` (a ref px point inside the panel it bounds)."""
    P = np.array(pts, np.float64)
    q = catmull([Vector((x, y, r)) for (x, y), r in zip(pts, radii)], 10)
    D = np.array([(v.x, v.y) for v in q])
    rd = np.array([v.z for v in q])
    cp, u = fit_arc(D, K, lam)
    S, us = arc_sample(cp, 1.0)
    rs = np.interp(us, u, rd)
    dev = np.linalg.norm(_bs_basis(u, K) @ cp - D, axis=1)
    print(f"ARC {name}: K={K} max dev {dev.max():.1f} px, r {rs.min():.1f}-{rs.max():.1f} px")
    Tn = np.gradient(S, axis=0)
    Tn /= np.linalg.norm(Tn, axis=1, keepdims=True)
    Nn = np.stack([-Tn[:, 1], Tn[:, 0]], 1)
    if toward is not None:                         # trim the side facing `toward` (a point in the window it borders)
        flip = ((np.array(toward, float) - S) * Nn).sum(1) < 0
    else:
        flip = ((S - np.array(inside, float)) * Nn).sum(1) < 0
    Nn[flip] = -Nn[flip]
    if "--arc-debug" in argv:
        np.savez(str(REN / f"arc_{name}.npz"), S=S, r=rs, raw=D, rraw=rd, cp=cp)
    return dict(S=S, r=rs, trims=[(S, Nn, (False, False), TRACED_TRIM_IN)], raw=D, prof=0.84)


def _clear(Q, dmin, k=0.02):
    """Push a bike-space (y, z) curve out to at least dmin from the rear hub (smooth max on the radius)."""
    d = np.hypot(Q[:, 0] - HUB_R.y, Q[:, 1] - HUB_R.z)
    dn = (d + dmin + np.sqrt((d - dmin) ** 2 + k * k)) / 2
    c = np.array([HUB_R.y, HUB_R.z])
    return c + (Q - c) * (dn / np.maximum(d, 1e-9))[:, None]


def core_tube_build(path, name, start=None, end=None, pair=False, K=9, lam=1e-4, frac=0.12, dmin=None):
    """Sweep a core_path in bike space: map, ease the ends onto the rig's hub / crank, re-fit one smooth arc (removes
    the warp's own small bends), and sweep it (a pair either side of the rear tyre for the top tube)."""
    S, rs = path["S"], path["r"]
    Y, Z = core_map_np(S[:, 0], S[:, 1])
    P = [Vector((0.0, y, z)) for y, z in zip(Y, Z)]
    if not NOWARP:
        P = eased(P, start, end, frac)
    Q = np.array([(p.y, p.z) for p in P])
    if dmin and not NOWARP:
        Q = _clear(Q, dmin)
    cp, u = fit_arc(Q, K, lam)
    Qs, us = arc_sample(cp, 0.004)
    L0 = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
    rr = np.interp(us, u, rs) * _S                              # radius carried along by curve parameter
    k = bend_report(name, Qs)
    BUILT[name] = Qs
    if "--arc-debug" in argv:
        np.savez(str(REN / f"bend_{name}.npz"), k=k, Q=Qs)
    P = [Vector((0.0, y, z)) for y, z in Qs]
    rr = [float(v) for v in rr]
    if not pair:
        return [sweep(P, rr, rr, "gold", 16)]
    # the pair: split apart along the arc, full width only where it passes the tyre, eased over a long stretch
    sl = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Qs, axis=0), axis=1))]
    dh = np.hypot(Qs[:, 0] - HUB_R.y, Qs[:, 1] - HUB_R.z)
    s_full = sl[dh <= WR + 0.035].max()                        # beyond this the tube is clear of the tyre
    s_end = s_full + SPLAY_LEN
    t = np.clip((s_end - sl) / (s_end - s_full), 0.0, 1.0)
    w = t * t * (3 - 2 * t)
    print(f"SPLAY {name}: full to {s_full:.3f} m, single from {s_end:.3f} m (cluster at {sl[np.argmin(np.hypot(Qs[:, 0] - CLUSTER.y, Qs[:, 1] - CLUSTER.z))]:.3f} m)")
    out = []
    for sx in (1, -1):
        Ps = [p + Vector((sx * 0.058 * wi, 0, 0)) for p, wi in zip(P, w)]
        lat = [v - (v - min(v, 0.018)) * wi for v, wi in zip(rr, w)]
        out.append(sweep(Ps, lat, rr, "gold", 16))
    return out


SPLAY_LEN = 0.30                                    # m of tube over which the top tube's pair eases into one


CROWN_MARGIN_PX = 1.0                           # gold ledge between each tube's edge and the crown panel
CROWN_ROUND_PX = 6.0                            # soft-min blend of the distances: rounds the panel's tips
CROWN_SEED = (930.0, 318.0)                     # a ref px point inside the crown panel
CROWN_COLS = {}                                 # the panel's top / bottom edge per ref px column (lays out the engraving)


def crown_panel_auto(paths, D, ox, oy):
    """Outline (ref px) of everything between the top tube, the lower tube and the window rail, an even ledge in from
    each tube's edge; the soft-min rounds the tips where two tubes close in."""
    h, w = D.shape
    xa, xb = max(0, 660 - ox), min(w, 1215 - ox)
    yy, xx = np.mgrid[0:h, xa:xb]
    G = np.stack([xx.ravel() + ox, yy.ravel() + oy], 1).astype(np.float64)
    terms = []
    for pth in paths:
        d_, k_ = _nearest(G, pth["S"])
        terms.append(d_ - pth["r"][k_] - CROWN_MARGIN_PX)
    terms.append(D[yy, xx].ravel().astype(np.float64) - (WEB_HALF_PX + 4.0))
    T = np.stack(terms, 0)
    m = T.min(0)
    g = (m - CROWN_ROUND_PX * np.log(np.exp(-(T - m) / CROWN_ROUND_PX).sum(0))).reshape(h, xb - xa)
    inside = g > 0
    sy, sx = int(CROWN_SEED[1] - oy), int(CROWN_SEED[0] - ox - xa)
    assert inside[sy, sx], "crown seed outside the panel space"
    comp = np.zeros_like(inside)
    comp[sy, sx] = True
    n0 = 0
    while True:                                   # flood fill from the seed (the panel's own piece of space)
        nb = comp.copy()
        nb[1:] |= comp[:-1]
        nb[:-1] |= comp[1:]
        nb[:, 1:] |= comp[:, :-1]
        nb[:, :-1] |= comp[:, 1:]
        comp = nb & inside
        n1 = int(comp.sum())
        if n1 == n0:
            break
        n0 = n1
    cols = np.nonzero(comp.any(0))[0]
    xs, top, bot = [], [], []
    for c in cols:
        rows = np.nonzero(comp[:, c])[0]
        r0, r1 = rows[0], rows[-1]
        y0 = r0 - g[r0, c] / (g[r0, c] - g[r0 - 1, c]) if r0 > 0 else float(r0)
        y1 = r1 + g[r1, c] / (g[r1, c] - g[r1 + 1, c]) if r1 < h - 1 else float(r1)
        xs.append(c + xa + ox)
        top.append(y0 + oy)
        bot.append(y1 + oy)
    xs, top, bot = np.array(xs, float), np.array(top), np.array(bot)

    def tip(c, step):                             # sub-pixel tip beyond the last column, at its mid height
        r = int(round((top[c] + bot[c]) / 2 - oy))
        cc = int(xs[c] - xa - ox)
        ga, gb = g[r, cc], g[r, cc + step]
        return (xs[c] + step * ga / (ga - gb), (top[c] + bot[c]) / 2)
    tl, tr = tip(0, -1), tip(-1, 1)
    ring = [tl] + list(zip(xs, top)) + [tr] + list(zip(xs[::-1], bot[::-1]))
    P = np.array(ring + ring[:1])
    L = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    u = np.arange(0, L[-1], 1.0)
    Q = np.stack([np.interp(u, L, P[:, 0]), np.interp(u, L, P[:, 1])], 1)
    for _ in range(3):                            # take out the column steps (a light circular smooth)
        Q = (np.roll(Q, 2, 0) + np.roll(Q, 1, 0) + Q + np.roll(Q, -1, 0) + np.roll(Q, -2, 0)) / 5
    n = 64
    k = np.linspace(0, len(Q), n, endpoint=False).astype(int)
    out = [tuple(float(v) for v in Q[i]) for i in k]
    CROWN_COLS.update(x=xs, top=top, bot=bot, tl=tl, tr=tr)
    print(f"CROWN PANEL: x {tl[0]:.0f}-{tr[0]:.0f}, tallest {np.max(bot - top):.0f} px at x {xs[np.argmax(bot - top)]:.0f}")
    return out, [min(out), max(out)]


def core_sculpt(paths_fn=None):
    xs, ys = [p[0] for p in CORE_ZONE], [p[1] for p in CORE_ZONE]
    ox, oy = int(min(xs)) - 6, int(min(ys)) - 6
    w, h = int(max(xs)) + 7 - ox, int(max(ys)) + 7 - oy
    m = MASK[oy:oy + h, ox:ox + w].copy()
    for poly in CORE_FILL:                        # white specular highlights the colour mask reads as background
        m |= _poly_fill((h, w), poly, ox, oy)
    m &= _poly_fill((h, w), CORE_ZONE, ox, oy)
    # close the remaining specular cracks, grow 1 px (the mask misses each tube's bright outer edge), smooth the outline
    m = ~_dilate(~_dilate(m, 3), 3)
    m = _dilate(m, 1)
    F = _blur(m.astype(np.float32), CORE_BLUR_PX)
    pin0 = np.zeros((h, w), bool)
    for outline, _tips in PANELS:
        pin0 |= _poly_fill((h, w), [(q.x, q.y) for q in catmull([Vector((x, y, 0)) for x, y in outline + outline[:2]], 40)[20:-20]], ox, oy)
    CORE_FIELD.update(F=F, pin=pin0.astype(np.float32), ox=ox, oy=oy)
    paths = paths_fn() if paths_fn else []
    if paths:                                     # the web stops at each tube's centre line (its edge hides inside the tube)
        yy, xx = np.mgrid[0:h, 0:w]
        Gp = np.stack([xx.ravel() + ox, yy.ravel() + oy], 1).astype(np.float64)
        keepw = np.ones(h * w)
        for S_, N_, fd, tin in [t for pth in paths for t in pth["trims"]]:
            if len(S_) < 3:
                continue
            d_, k_ = _nearest(Gp, S_)
            side = ((Gp - S_[k_]) * N_[k_]).sum(1)              # > 0: the outer side of the tube
            big = 10 ** 6
            ends = np.minimum(k_ if fd[0] else big, (len(S_) - 1 - k_) if fd[1] else big)
            fe = np.clip(ends / 25.0, 0.0, 1.0)                 # fade out near the trimmed stretch's ends
            near = np.clip((40.0 - d_) / 6.0, 0.0, 1.0)          # only near the tube (far pixels belong to other members)
            cut = np.clip((side + tin) / 2.0 + 0.5, 0.0, 1.0) * fe * near
            keepw *= 1.0 - cut
        F = F * keepw.reshape(h, w).astype(np.float32)
    C = _contour(F)
    band = _dilate(F >= 0.5, 3)
    by, bx = np.nonzero(band)
    G = np.stack([bx, by], 1).astype(np.float32)
    d, _ = _nearest(G, C)
    D = np.full((h, w), -9.0, np.float32)
    D[by, bx] = np.where(F[by, bx] >= 0.5, d, -d)                       # signed distance to the outline, px
    WH = web_half(np.arange(w, dtype=np.float64) + ox)[None, :].astype(np.float32)
    R = np.minimum(_maxfilt(np.maximum(D, 0.0), int(WEB_HALF_PX) + 1), WH)
    if paths:                                     # the crown panel fills the space its tubes leave
        PANELS[0] = crown_panel_auto([pp for pp in paths if pp.get("crown")], D, ox, oy)
    PC, pin = [], np.zeros((h, w), bool)
    for outline, _tips in PANELS:
        pan = catmull([Vector((x, y, 0)) for x, y in outline + outline[:2]], 40)[20:-20]
        PC.append(np.array([(q.x - ox, q.y - oy) for q in pan], np.float32))
        pin |= _poly_fill((h, w), [(q.x, q.y) for q in pan], ox, oy)
    dp, _ = _nearest(G, np.concatenate(PC, 0))
    DP = np.full((h, w), -9.0, np.float32)
    DP[by, bx] = np.where(pin[by, bx], dp, -dp)                         # signed distance to the panel edge, px
    # half-pixel grid (no stair steps big enough to survive the voxel remesh)
    F2, D2, R2, P2 = _up2(F), _up2(D), _up2(R), _up2(DP)
    inside = F2 >= 0.5
    iy, ix = np.nonzero(inside)
    dd = np.clip(D2[iy, ix], 0.0, None)
    rr = R2[iy, ix]
    H = np.sqrt(np.maximum(0.0, rr * rr - (rr - np.minimum(dd, rr)) ** 2))
    dpv = P2[iy, ix]                              # the panels are sunk into the web first, so each tube's flank
    ramp = np.clip((dpv + 0.5) / (PANEL_RAMP_PX + 0.5), 0.0, 1.0)   # flows down into the panel floor (no crease cut
    ramp = ramp * ramp * (3 - 2 * ramp)                              # into a tube's side)
    H = H - PANEL_DEPTH_PX * ramp
    if paths and FILLET_PX > 0:                   # web flows into each tube through a rounded fillet (smooth max)
        Gq = np.stack([ox + ix / 2.0, oy + iy / 2.0], 1).astype(np.float64)
        for pth in paths:
            d_, k_ = _nearest(Gq, pth["S"])
            hx = np.clip((Gq[:, 0] - 1040.0) / 170.0, 0.0, 1.0)
            wpan = (np.clip((dpv + 8.0) / 8.0, 0.0, 1.0) * (1 - hx)         # by the crown panel: the full tube (floor rounds up into it;
                    * np.clip((Gq[:, 0] - 620.0) / 40.0, 0.0, 1.0))         # the cluster's traced tubes keep their slimmer copy)
            f0 = pth.get("prof", 0.88)
            rp = pth["r"][k_] * (f0 + (0.98 - f0) * wpan - 0.16 * hx * hx * (3 - 2 * hx))   # inside the swept tube (the head ease shears the web)
            prof = np.sqrt(np.maximum(rp * rp - d_ * d_, 0.0))
            hh = np.clip(FILLET_PX - np.abs(H - prof), 0.0, None) / FILLET_PX * np.clip(prof / 2.0, 0.0, 1.0)   # only by the tube
            H = np.maximum(H, prof) + hh * hh * FILLET_PX * 0.25
    hv = np.maximum(H, 0.0)
    nb = np.zeros(inside.shape, bool)
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        nb |= ~_shift(inside, dy, dx, False)
    ring = (nb & inside)[iy, ix]
    hv = np.where(ring, 0.0, hv)                   # the outline: both faces meet here
    px, py = ox + ix / 2.0, oy + iy / 2.0
    Y, Z = core_map_np(px, py)
    n = len(ix)
    inner = ~ring
    top_id = np.full(inside.shape, -1, np.int64)
    top_id[iy, ix] = np.arange(n)
    bot_of = np.arange(n)
    bot_of[inner] = n + np.arange(inner.sum())
    bot_id = np.full(inside.shape, -1, np.int64)
    bot_id[iy, ix] = bot_of
    X = hv * _S
    V3 = np.concatenate([np.stack([X, Y, Z], 1), np.stack([-X[inner], Y[inner], Z[inner]], 1)], 0)
    cell = inside[:-1, :-1] & inside[1:, :-1] & inside[:-1, 1:] & inside[1:, 1:]
    cy, cx = np.nonzero(cell)
    Q = [np.stack([top_id[cy, cx], top_id[cy, cx + 1], top_id[cy + 1, cx + 1], top_id[cy + 1, cx]], 1),
         np.stack([bot_id[cy + 1, cx], bot_id[cy + 1, cx + 1], bot_id[cy, cx + 1], bot_id[cy, cx]], 1)]
    Q = np.concatenate(Q, 0)
    me = bpy.data.meshes.new("GS_core")
    me.vertices.add(len(V3))
    me.vertices.foreach_set("co", V3.astype(np.float32).ravel())
    me.loops.add(len(Q) * 4)
    me.loops.foreach_set("vertex_index", Q.astype(np.int32).ravel())
    me.polygons.add(len(Q))
    me.polygons.foreach_set("loop_start", (np.arange(len(Q)) * 4).astype(np.int32))
    me.update(calc_edges=True)
    me.validate()
    o = bpy.data.objects.new("GS_core", me)
    COL.objects.link(o)
    me.materials.append(M["gold"])
    if "--core-debug" in argv:                     # the outline over the ref, and the inflated height field
        ref = bpy.data.images.load(str(ROOT / "refs" / "gold_standard" / "pete_refs" / "side.png"))
        rw, rh = ref.size
        ra = np.array(ref.pixels[:], dtype=np.float32).reshape(rh, rw, 4)[::-1][oy:oy + h, ox:ox + w, :3].copy()
        ins = F >= 0.5
        edge = _dilate(ins, 1) & ~ins
        ra[edge] = [0.0, 0.9, 1.0]
        pe = _dilate(pin, 1) & ~pin
        ra[pe] = [1.0, 0.0, 1.0]
        g = np.zeros(inside.shape, np.float32)
        g[iy, ix] = hv / WEB_HALF_PX
        for nm, img in (("core_overlay", ra), ("core_height", np.stack([g, g, g], 2))):
            hh_, ww_ = img.shape[:2]
            im = bpy.data.images.new(nm, ww_, hh_)
            im.pixels[:] = np.concatenate([img, np.ones((hh_, ww_, 1), np.float32)], 2)[::-1].ravel()
            im.filepath_raw = str(REN / f"{nm}.png")
            im.file_format = "PNG"
            im.save()
    print("CORE", n, "px", len(V3), "verts", len(Q), "faces")
    if "--core-raw" in argv:                       # debug: keep a copy of the raw sculpt to render on its own
        global CORE_RAW
        CORE_RAW = o.copy()
        CORE_RAW.data = o.data.copy()
        COL.objects.link(CORE_RAW)
        CORE_RAW.location.x = 3.0
    return o, paths


CLUSTER = art(400, 345)
CLUSTER_IN = (402, 348)
# the window edge measured from the mask (top 700:322 740:329 780:345 800:368, front tip ~803:378, lower 790:407 770:417)
# moved one rail radius into the frame
C_RAIL = [(630, 314), (660, 313), (690, 312), (712, 311), (735, 315), (757, 322), (775, 331), (789, 342), (799, 355), (806, 368), (809, 381),
          (806, 394), (799, 405), (789, 414), (777, 423), (765, 432), (754, 441), (744, 448)]
C_RAIL_R = [5, 7, 9, 10, 11, 12, 12.5, 13, 13, 13, 13, 13, 12.5, 12, 12, 12, 11, 10]
# designed in bike (y, z) and carried into ref px so the web, its trims and fillets follow them
SA_BIKE = [(0.656, 0.823), (0.615, 0.820), (0.565, 0.805), (0.515, 0.776), (0.474, 0.728), (0.447, 0.668), (0.433, 0.600),
           (0.427, 0.520), (0.418, 0.430), (0.405, 0.340), (0.393, 0.262)]
BL_BIKE = [(0.530, 0.785), (0.480, 0.758), (0.430, 0.728), (0.380, 0.700), (0.330, 0.672), (0.290, 0.650), (0.255, 0.640)]
TRI_BIKE = [(0.459, 0.733), (0.4235, 0.640), (0.341, 0.6655)]          # the sunken triangle (inside its tubes)
STOKER_A = [px_of(*q) for q in SA_BIKE]
STOKER_A_R = [10.5, 10.5, 10.5, 10.5, 10.5, 10.5, 10.5, 10.5, 10.5, 11, 12]
STOKER_BL = [px_of(*q) for q in BL_BIKE]
STOKER_BL_R = [10, 10, 10, 10, 10, 10, 9.5]
CLUSTER_PX = [px_of(*q) for q in TRI_BIKE]
CLUSTER_PX = [tuple(a + (b - a) * t for a, b in zip(CLUSTER_PX[i], CLUSTER_PX[(i + 1) % 3]))
              for i in range(3) for t in (0.0, 0.25, 0.5, 0.75)]      # edge samples for the panel outline
CLUSTER_IN = tuple(float(v) for v in np.mean([px_of(*q) for q in TRI_BIKE], 0))
PANELS = [(PANEL_PX, [PANEL_PX[0], max(PANEL_PX, key=lambda q: q[0])]),
          (CLUSTER_PX, [px_of(*q) for q in TRI_BIKE])]
# the art has no frame where the cluster now sits: fill its web between the seat tube, the triangle's top edge and the
# top tube, and take the web out of the old cluster (behind the seat tube)
_cf = [px_of(*q) for q in [(0.505, 0.770), (0.470, 0.722), (0.447, 0.668), (0.437, 0.615), (0.432, 0.575), (0.380, 0.585),
                           (0.320, 0.610), (0.262, 0.628), (0.262, 0.652), (0.330, 0.684), (0.430, 0.740)]]
CORE_FILL = CORE_FILL + [_cf]
_zr = [px_of(*q) for q in [(0.520, 0.800), (0.470, 0.740), (0.448, 0.668), (0.440, 0.600), (0.437, 0.540)]]
CORE_ZONE = [(_zr[0][0], _zr[0][1]), (520, 236), (560, 250)] + CORE_ZONE[CORE_ZONE.index((560, 250)) + 1:
                                                                      CORE_ZONE.index((440, 420))] + _zr[:0:-1]
_PATHS = {}


def _core_paths():
    _PATHS["T1"] = core_path(TUBE1_GUIDE, TUBE1_RMAX, -1, "TUBE1", clip=(445, 1196),
                             pre=[(212, 518, 14.5), (255, 490, 15.5), (330, 435, 16.5), (392, 393, 17.5)],
                             post=[(1218, 250, 14.0)], K=int(arg("--k1", "8")), lam=float(arg("--lam1", "2e-4")),
                             trim=(STOKER_BL[-1][0] + 6, 9999), fade=(True, False),   # the triangle sits above it
                             away=[((330, 435), (450, 300)), ((435, 640), (600, 150))])
    _PATHS["T2"] = core_path(TUBE2_GUIDE, TUBE2_RMAX, 1, "TUBE2", clip=(684, 1192), pre=[(1222, 291, 12.0)],
                             post=[(640, 500, 16.0), (590, 518, 16.5), (530, 538, 17.5)],
                             K=int(arg("--k2", "7")), lam=float(arg("--lam2", "2e-4")), trim=(0, 9999), fade=(False, False))
    # the stoker's cluster (ref 6x crops): the bowed seat tube from under the saddle's back, down through the cluster,
    # across the top tube and down in front of the rear tyre to the rear cranks; the front post from the saddle down
    # into the top tube's top (a long fillet); the sunken triangle sits between them and the top tube
    _PATHS["SA"] = traced_path(STOKER_A, STOKER_A_R, "STOKER_A", CLUSTER_IN, K=6)
    _PATHS["SB"] = traced_path(STOKER_BL, STOKER_BL_R, "STOKER_BL", CLUSTER_IN, K=5)
    # the big window's rail (side ref 4x): the top tube's lower edge peels away at ~x 700, runs along the window's top,
    # rounds the C at its front and curls back into the lower tube; the crown panel's web sits outside it
    _PATHS["CR"] = traced_path(C_RAIL, C_RAIL_R, "C_RAIL", None, K=7, toward=(740, 385))
    for _k in ("T1", "T2", "CR"):
        _PATHS[_k]["crown"] = True                # the tubes round the crown panel
    return [_PATHS["T1"], _PATHS["T2"], _PATHS["SA"], _PATHS["SB"], _PATHS["CR"]]


_core, _ = core_sculpt(_core_paths)
fr = [_core]
# tube 1: from the rear hub (a pair either side of the tyre) up through the stoker's cluster, along the top of the
# frame to the head tube, one unbroken sweep; tube 2: from the head tube along the plate's lower edge, round the curve
# behind the captain's seat and down the diagonal to the rear cranks
if "--probe" in argv:
    def _pp(nm, v):
        print(f"PROBE {nm:10s} y {v.y:+.4f} z {v.z:+.4f}  d_hub {math.hypot(v.y - HUB_R.y, v.z - HUB_R.z):.3f}")
    for nm, v in (("HUB_R", HUB_R), ("BB_R", BB_R), ("SEAT_S", SEAT_S), ("CLAMP_S", SEAT_CLAMP_S), ("S_POST0", S_POST0),
                  ("CLUSTER", CLUSTER)):
        _pp(nm, v)
    for q in ((290, 225), (300, 232), (346, 262), (370, 300), (378, 340), (372, 370), (356, 390), (366, 420), (380, 460),
              (395, 505), (410, 530), (360, 215), (395, 215), (430, 335), (470, 336), (342, 305)):
        _pp(str(q), art(*q))
    print("PROBE WR", WR, "guard r", WR + 0.03 + 0.016)
    for k, v in GRIP.items():
        print(f"PROBE {k} x {v.x:+.4f} y {v.y:+.4f} z {v.z:+.4f}")
    _pp("SEAT_C", SEAT_C)
    _pp("CLAMP_C", SEAT_CLAMP_C)
    _pp("C_POST0", C_POST0)
    for q in ((700, 222), (740, 224), (770, 240), (795, 256), (813, 250), (873, 212), (643, 207), (893, 207), (627, 160), (560, 125)):
        _pp(str(q), art(*q))
fr += core_tube_build(_PATHS["T1"], "TUBE1", start=HUB_R, pair=True)
fr += core_tube_build(_PATHS["T2"], "TUBE2", end=BB_R)
if "--probe" in argv:
    _t = BUILT["TUBE1"]
    _sl = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(_t, axis=0), axis=1))]
    for _yy in np.arange(0.30, 0.66, 0.03):
        _i = int(np.argmin(np.abs(_t[:, 0] - _yy) + (np.abs(_t[:, 1] - 0.6) > 0.2) * 9))
        print(f"PROBE T1 y {_t[_i, 0]:.3f} z {_t[_i, 1]:.3f} arc {_sl[_i]:.3f}")
fr += core_tube_build(_PATHS["CR"], "C_RAIL", K=7, lam=2e-4)
STOKER_A_TOP = V(SEAT_S.y + 0.068, SEAT_S.z - 0.071)          # under the saddle's back edge, arriving almost level
fr += core_tube_build(_PATHS["SA"], "STOKER_A", start=STOKER_A_TOP, end=BB_R, K=9, lam=6e-5, frac=0.06, dmin=0.385)
fr += core_tube_build(_PATHS["SB"], "STOKER_BL", K=8, lam=3e-5)
def web_between(Qa, Qb, half, n=40):
    """A solid web strip between two bike-space (y, z) centre lines (each resampled to n by arc length), half thick."""
    def rs(Q):
        L = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(Q, axis=0), axis=1))]
        t = np.linspace(0.0, L[-1], n)
        return np.stack([np.interp(t, L, Q[:, 0]), np.interp(t, L, Q[:, 1])], 1)
    A2, B2 = rs(Qa), rs(Qb)
    bm = bmesh.new()
    rows = []
    for (ya, za), (yb, zb) in zip(A2, B2):
        rows.append([bm.verts.new((xx, y, z)) for y, z in ((ya, za), (yb, zb)) for xx in (-half, half)])
    for r0, r1 in zip(rows, rows[1:]):                # rows: [A-, A+, B-, B+]
        for f in ((0, 2, 2, 0), (1, 1, 3, 3)):
            pass
        bm.faces.new([r0[1], r1[1], r1[3], r0[3]])        # +x face
        bm.faces.new([r0[0], r0[2], r1[2], r1[0]])        # -x face
        bm.faces.new([r0[0], r1[0], r1[1], r0[1]])        # A edge
        bm.faces.new([r0[2], r0[3], r1[3], r1[2]])        # B edge
    for r, flip in ((rows[0], False), (rows[-1], True)):
        f = [r[0], r[1], r[3], r[2]]
        bm.faces.new(f[::-1] if flip else f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return obj("web", bm, "gold")


_qa = BUILT["STOKER_A"]
fr.append(sphere(V(float(_qa[0, 0]), float(_qa[0, 1])), 0.0172, "gold", 16))   # domed top under the saddle's back
# the fender hook (ref): the rear guard's front end runs on forward round the tyre and curls up into the seat tube
_hk_pts = []
for a, rr in ((86, 0.366), (79, 0.368)):
    _a = math.radians(a)
    _hk_pts.append(HUB_R + Vector((0, -math.cos(_a), math.sin(_a))) * rr)
_sa = BUILT["STOKER_A"]
_ya = float(np.interp(0.685, _sa[::-1, 1], _sa[::-1, 0])) if _sa[0, 1] > _sa[-1, 1] else float(np.interp(0.685, _sa[:, 1], _sa[:, 0]))
_hk_pts += [V(0.785, 0.688), V(0.738, 0.708), V(0.694, 0.742), V(0.655, 0.780), V(0.622, 0.806), V(0.596, 0.814)]
_hk = np.array([(q.y, q.z) for q in _hk_pts])
_hc, _ = fit_arc(_hk, 6, 3e-4)
_hs, _ = arc_sample(_hc, 0.004)
bend_report("HOOK", _hs)
fr.append(sweep([Vector((0.0, y, z)) for y, z in _hs], lambda t: 0.016 - 0.005 * min(1.0, t * 3), lambda t: 0.011 + 0.002 * t, "gold", 12))
fr += member(*BAR_UP, name="BAR_UP", end=BB_F, frac=0.4, fit=4)
fr += member(*BAR_LOW, name="BAR_LOW", start=BB_R, end=BB_F, frac=0.3, fit=4)
def on_tube(name, near, back=0.0):
    """The point of a built core tube's centre line nearest `near` (bike y, z), moved `back` m along -normal."""
    Qn = BUILT[name]
    i = int(np.argmin(np.hypot(Qn[:, 0] - near.y, Qn[:, 1] - near.z)))
    return V(float(Qn[i, 0]), float(Qn[i, 1]))


fr += member(*C_SEAT_TUBE, name="C_SEAT_TUBE", start=on_tube("TUBE2", art(*C_SEAT_TUBE[0][0])), end=BB_F, frac=0.4, lat_max=0.019)
fr += member(*DOWN_TUBE, name="DOWN_TUBE", start=steer_pt(0.0), end=BB_F, frac=0.3)
def bike_arc(pts, K=5, lam=3e-4, step=0.003):
    """One smooth arc through bike-space (y, z) points, ends pinned -> sampled [Vector] at x = 0."""
    c, _ = fit_arc(np.array([(q.y, q.z) for q in pts]), K, lam)
    Qs, _ = arc_sample(c, step)
    return [Vector((0.0, y, z)) for y, z in Qs], Qs


def under_saddle(sock):
    """The saddle's rails and underside (they follow saddle()'s geometry): rear y, nose y, bottom z."""
    return sock.y + 0.07, sock.y - 0.26, sock.z - 0.06


# under the captain's saddle (side ref 4x): a swan neck rises out of the top tube, curls back and runs level under the
# saddle to a collar below its back (the stoker's bars carry on from there); a strut drops from under the saddle's nose
# onto the neck's foot, leaving a small window between neck, strut and saddle
_cyr, _cyn, _czb = under_saddle(SEAT_C)
NECK_R = 0.0215                                          # the neck's radius (art ~12 px)
NECK_Z = _czb - 0.022                                    # neck centre: its top just under the rails
NECK_END = V(_cyr - 0.004, NECK_Z)                       # the collar, under the saddle's back
_foot = on_tube("TUBE1", V(_cyr - 0.175, NECK_Z - 0.06))
NECK_PTS, NECK_Q = bike_arc([NECK_END, V(_cyr - 0.045, NECK_Z + 0.001), V(_cyr - 0.085, NECK_Z - 0.004),
                             V(_cyr - 0.118, NECK_Z - 0.018), V(_cyr - 0.143, NECK_Z - 0.038), _foot], K=5)
bend_report("CAPT_NECK", NECK_Q)
fr.append(sweep(NECK_PTS, lambda t: NECK_R + 0.003 * smooth01(0.7, 1.0, t),
                lambda t: NECK_R + 0.010 * smooth01(0.65, 1.0, t) ** 2, "gold", 18))
_kr = int(len(NECK_Q) * 0.72)                            # the ring round the neck's foot (side ref)
_tr = Vector((0.0, *(NECK_Q[_kr + 2] - NECK_Q[_kr - 2]))).normalized()
fr.append(torus(V(float(NECK_Q[_kr, 0]), float(NECK_Q[_kr, 1])), NECK_R + 0.0028, 0.0048, "gold", axis=_tr, seg=28, tseg=8))
_nose_c = V(_cyn + 0.05, _czb + 0.016)                   # under the captain saddle's nose, where its rails meet
_kn = int(len(NECK_Q) * 0.80)                            # the strut lands on the neck's down-curve, above the top tube
_sf = V(float(NECK_Q[_kn, 0]), float(NECK_Q[_kn, 1]))
_cs_pts, _cs_q = bike_arc([_nose_c, (_nose_c * 0.55 + _sf * 0.45) + V(0.006, -0.006), _sf], K=4, step=0.003)
bend_report("CAPT_STRUT", _cs_q)
fr.append(sweep(_cs_pts, lambda t: 0.0115 + 0.004 * t * t, lambda t: 0.0115 + 0.006 * t * t, "gold", 14))
# the slim front bar: up from the triangle's top edge to under the saddle's front
_syr, _syn, _szb = under_saddle(SEAT_S)
STOKER_FRONT_Y = _syn + 0.095                            # where the bar meets the saddle (its front, behind the nose)
_bl = BUILT["STOKER_BL"]
_j = V(0.432, 0.729)
_kb = int(np.argmin(np.hypot(_bl[:, 0] - _j.y, _bl[:, 1] - _j.z)))
_b0 = V(float(_bl[_kb, 0]), float(_bl[_kb, 1]))
_b1 = V(STOKER_FRONT_Y, _szb - 0.004)
_bu_pts, _bu_q = bike_arc([_b0, _b0 * 0.62 + _b1 * 0.38 + V(0.010, 0.0), _b0 * 0.25 + _b1 * 0.75 + V(0.008, 0.0), _b1],
                          K=4, step=0.003)
bend_report("STOKER_FRONT", _bu_q)
fr.append(sweep(_bu_pts, lambda t: 0.0125 - 0.002 * t, lambda t: 0.0135 - 0.0025 * t, "gold", 14))
fr.append(sphere(_b1, 0.0112, "gold", 14))
fr += member(*CHAINSTAY, name="CHAINSTAY", start=HUB_R, end=BB_R, frac=0.3, pair=True)
# head tube on the rig's steering axis (the fork turns about it), flared ends
fr.append(sweep([H_BOT - STD * 0.03, H_BOT + STD * 0.05, H_TOP - STD * 0.05, H_TOP + STD * 0.03], 0.027,
                [0.032, 0.027, 0.027, 0.032], "gold", 20))
for p in (BB_F, BB_R):                                                                             # bottom brackets
    fr.append(cyl(p + V(0, 0, -0.045), p + V(0, 0, 0.045), 0.031, "gold", 24))
for sx in (1, -1):
    fr.append(sphere(HUB_R + V(0, 0, sx * 0.06), 0.021, "gold", 12))                              # dropouts


def fuse(obs, name, voxel=0.0018, smooth_iter=12, tris=26000):
    """One smooth piece: voxel remesh of the union, Laplacian smoothing, then decimate to a game budget."""
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = o.data.name = name
    rm = o.modifiers.new("remesh", "REMESH")
    rm.mode = "VOXEL"
    rm.voxel_size = voxel
    rm.adaptivity = 0.0
    sm = o.modifiers.new("smooth", "LAPLACIANSMOOTH")
    sm.iterations = smooth_iter
    sm.lambda_factor = 0.5
    sm.use_volume_preserve = True
    apply_mods(o)
    n = sum(len(p.vertices) - 2 for p in o.data.polygons)
    if n > tris and "--quadriflow" in argv:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
        bad = [e for e in bm.edges if not e.is_manifold]
        badv = [v for v in bm.verts if not v.is_manifold]
        print("NONMANIFOLD edges", len(bad), "verts", len(badv))
        for _ in range(3):
            badv = [v for v in bm.verts if not v.is_manifold]
            if not badv:
                break
            bmesh.ops.delete(bm, geom=list({f for v in badv for f in v.link_faces}), context="FACES")
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
            bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        print("NONMANIFOLD after", sum(1 for v in bm.verts if not v.is_manifold))
        bm.to_mesh(o.data)
        bm.free()
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        r = bpy.ops.object.quadriflow_remesh(mode="FACES", target_faces=tris // 2, use_mesh_symmetry=False,
                                             use_preserve_sharp=False, use_preserve_boundary=False, smooth_normals=False,
                                             seed=0)
        print("QUADRIFLOW", r, len(o.data.polygons))
        n = sum(len(p.vertices) - 2 for p in o.data.polygons)
    if n > tris:
        hi = o.copy()                                   # keep the full-detail surface to take the shading from
        hi.data = o.data.copy()
        COL.objects.link(hi)
        for p in hi.data.polygons:
            p.use_smooth = True
        if "--voxel-lod" in argv:                       # (tried: an even coarser voxel grid staircases the fillets)
            rm2 = o.modifiers.new("remesh2", "REMESH")
            rm2.mode = "VOXEL"
            rm2.voxel_size = voxel * math.sqrt(n / tris) * 0.97
            apply_mods(o)
        else:
            dm = o.modifiers.new("dec", "DECIMATE")
            dm.ratio = tris / n
            apply_mods(o)
            # the collapse leaves long spokes across gently curved areas (the web's fold) whose shading streaks:
            # split every long edge, put the new points back on the full-detail surface
            lmax = float(arg("--edge-max", "0.014"))
            for _ in range(3 if "--snap" in argv else 0):
                bm = bmesh.new()
                bm.from_mesh(o.data)
                long_e = [e for e in bm.edges if e.calc_length() > lmax]
                if not long_e:
                    bm.free()
                    break
                bmesh.ops.subdivide_edges(bm, edges=long_e, cuts=1, use_grid_fill=False)
                bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
                bm.to_mesh(o.data)
                bm.free()
            if "--snap" in argv:
                sw = o.modifiers.new("snap", "SHRINKWRAP")
                sw.target = hi
                # along each point's own normal, a short way only: the nearest surface point jumps across sharp
                # creases (a panel's edge against its tube) and leaves a sawtooth
                sw.wrap_method = "PROJECT"
                sw.use_negative_direction = True
                sw.use_positive_direction = True
                sw.project_limit = float(arg("--snap-limit", "0.004"))
                apply_mods(o)
        print("FUSE", name, n, "->", sum(len(p.vertices) - 2 for p in o.data.polygons), "tris")
        for p in o.data.polygons:
            p.use_smooth = True
        # the decimated surface's long thin triangles streak the shading on broad smooth areas: give it the
        # full-detail surface's normals instead (exported as the glTF's vertex normals)
        dt = o.modifiers.new("nrm", "DATA_TRANSFER")
        dt.object = hi
        dt.use_loop_data = True
        dt.data_types_loops = {"CUSTOM_NORMAL"}
        dt.loop_mapping = "POLYINTERP_NEAREST"
        apply_mods(o)
        bpy.data.objects.remove(hi, do_unlink=True)
    o.data.materials.clear()
    o.data.materials.append(M["gold"])
    for p in o.data.polygons:
        p.use_smooth = True
    return o


FRAME = fuse(fr, "GS_frame", tris=int(arg("--frame-tris", "24000" if GAME else "55000")), smooth_iter=int(arg("--smooth", "12")))
FRAME_PART = "GS_frame"                            # the whole frame: one mesh (tubes, web, inlays, emblem, rings)
add("Bike_root", FRAME, name=FRAME_PART)
# the sunken panel's floor: a thin deep-gold inlay cut to the panel's outline just inside its ramp (the ref's dark
# inset behind the crown), so its edge is crisp instead of following the frame mesh's triangles
for _outline, _tips in PANELS:
    _pan = catmull([Vector((x, y, 0)) for x, y in _outline + _outline[:2]], 12)[6:-6]
    _P2 = np.array([(q.x, q.y) for q in _pan])
    _T2 = np.roll(_P2, -1, 0) - np.roll(_P2, 1, 0)
    _N2 = np.stack([_T2[:, 1], -_T2[:, 0]], 1) / np.linalg.norm(_T2, axis=1, keepdims=True)
    if ((_P2.mean(0) - _P2) * _N2).sum(1).mean() < 0:
        _N2 = -_N2                                               # point inward
    _dt = np.min(np.linalg.norm(_P2[:, None, :] - np.array(_tips, float)[None], axis=2), 1)
    _span = 24.0 if _outline is PANELS[0][0] else 10.0
    _P2 = _P2 + _N2 * ((PANEL_RAMP_PX + 0.4) * np.clip(_dt / _span, 0.0, 1.0))[:, None]
    _py2, _pz2 = core_map_np(_P2[:, 0], _P2[:, 1])
    _ph = (float(web_half(np.mean([q[0] for q in _outline]))) - PANEL_DEPTH_PX) * _S
    for sx in (1, -1):
        add("Bike_root", plate(list(zip(_py2, _pz2)), V(0, 0, sx * _ph), (0, 1, 0), (0, 0, 1), "gold_deep", 0.0016),
            name=FRAME_PART)
for s in (-0.03, 0.265):                                                                           # head tube rings
    add("Bike_root", torus(steer_pt(s), 0.033, 0.006, "gold", axis=STD, seg=24, tseg=6), name=FRAME_PART)
for p in (BB_F, BB_R):
    for sx in (1, -1):
        add("Bike_root", torus(p + V(0, 0, sx * 0.046), 0.031, 0.004, "gold", seg=18, tseg=4), name=FRAME_PART)

# ------------------------------------------------------------------ the crown panel's engraving
def crown2d(cy, cz, s):
    """Crown outline pieces (y, z) facing the side: band, five points with pearls, a cross on top."""
    pieces = []
    band = [(cy - 0.5 * s, cz - 0.3 * s), (cy + 0.5 * s, cz - 0.3 * s), (cy + 0.5 * s, cz - 0.12 * s), (cy - 0.5 * s, cz - 0.12 * s)]
    pieces.append(("gold", band))
    body = [(cy - 0.5 * s, cz - 0.12 * s), (cy - 0.58 * s, cz + 0.32 * s), (cy - 0.3 * s, cz + 0.06 * s), (cy - 0.16 * s, cz + 0.42 * s),
            (cy, cz + 0.12 * s), (cy + 0.16 * s, cz + 0.42 * s), (cy + 0.3 * s, cz + 0.06 * s), (cy + 0.58 * s, cz + 0.32 * s),
            (cy + 0.5 * s, cz - 0.12 * s)]
    pieces.append(("gold", body))
    for py_, pz_ in ((-0.58, 0.32), (-0.16, 0.42), (0.16, 0.42), (0.58, 0.32)):
        pieces.append(("gold", ell(cy + py_ * s, cz + pz_ * s + 0.05 * s, 0.06 * s, 0.06 * s, 8)))
    pieces.append(("gold", [(cy - 0.05 * s, cz + 0.12 * s), (cy + 0.05 * s, cz + 0.12 * s), (cy + 0.05 * s, cz + 0.7 * s),
                            (cy - 0.05 * s, cz + 0.7 * s)]))
    pieces.append(("gold", [(cy - 0.15 * s, cz + 0.52 * s), (cy + 0.15 * s, cz + 0.52 * s), (cy + 0.15 * s, cz + 0.6 * s),
                            (cy - 0.15 * s, cz + 0.6 * s)]))
    return pieces


_CC = CROWN_COLS


def pan_mid(px):
    """The crown panel's centre line and half height (ref px) at column px."""
    t = np.interp(px, _CC["x"], _CC["top"])
    b = np.interp(px, _CC["x"], _CC["bot"])
    return (t + b) / 2, (b - t) / 2


EM_FLOOR = (WEB_HALF_PX - PANEL_DEPTH_PX) * _S + 0.0008     # the inlay's face: the engraving stands on it


def _to_bike(P):
    Y, Z = core_map_np(np.asarray(P)[:, 0], np.asarray(P)[:, 1])
    return Y, Z


def relief(P, height, bevel, material="gold"):
    """A raised, bevelled shape on both faces of the panel: outline P (ref px, closed, any winding), walls up to 60%,
    then a chamfer inset by `bevel` px to a flat top (catches the light like a struck medal)."""
    P = np.asarray(P, np.float64)
    if (np.roll(P[:, 0], -1) * P[:, 1] - P[:, 0] * np.roll(P[:, 1], -1)).sum() < 0:
        P = P[::-1]
    E = np.roll(P, -1, 0) - P                                  # edge i: P[i] -> P[i+1]
    En = np.stack([-E[:, 1], E[:, 0]], 1)
    En /= np.maximum(np.linalg.norm(En, axis=1, keepdims=True), 1e-9)
    if ((P.mean(0) - P) * En).sum(1).mean() < 0:
        En = -En                                               # inward
    Nb = En + np.roll(En, 1, 0)                                # mitre: bisector of the two edges at each vertex
    Nb /= np.maximum(np.linalg.norm(Nb, axis=1, keepdims=True), 1e-9)
    mit = np.clip((Nb * En).sum(1), 0.5, 1.0)                  # capped: sharp points round off instead of crossing
    Pin = P + Nb * (bevel / mit)[:, None]
    Y0, Z0 = _to_bike(P)
    Y1, Z1 = _to_bike(Pin)
    obs = []
    for sx in (1, -1):
        bm = bmesh.new()
        lv = [(EM_FLOOR - 0.0004, Y0, Z0), (EM_FLOOR + height * 0.6, Y0, Z0), (EM_FLOOR + height, Y1, Z1)]
        rings = [[bm.verts.new((sx * x, float(y), float(z))) for y, z in zip(Ys, Zs)] for x, Ys, Zs in lv]
        n = len(P)
        for a, b in zip(rings, rings[1:]):
            for q in range(n):
                bm.faces.new([a[q], a[(q + 1) % n], b[(q + 1) % n], b[q]])
        bm.faces.new(rings[-1])
        bm.faces.new(rings[0][::-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        o = obj("relief", bm, material)
        for f in o.data.polygons:
            f.use_smooth = False
        obs.append(o)
    return obs


def scroll(P, w0, w1, height=0.0011, tseg=5):
    """An engraved line (ref px points) as a flattened, tapering bead on both faces."""
    P = np.asarray(P, np.float64)
    Y, Z = _to_bike(P)
    obs = []
    for sx in (1, -1):
        pts = [V(float(y), float(z), sx * (EM_FLOOR + 0.0002)) for y, z in zip(Y, Z)]
        obs.append(sweep(pts, height, lambda t: (w0 + (w1 - w0) * t) * _S, "gold", tseg))
    return obs


def curl(p0, ang0, size, sgn, lead=0.15, wind=3.2, length=4.0, n=36):
    """An Euler-spiral curl (ref px; screen y down): leaves p0 heading ang0 almost straight, then winds tighter and
    tighter (curvature lead/size -> wind/size). sgn +1 turns clockwise on screen."""
    pts = [tuple(p0)]
    x, y = p0
    a = ang0
    L = length * size
    ds = L / n
    for i in range(n):
        t = (i + 0.5) / n
        a += sgn * (lead + (wind - lead) * t * t) / size * ds
        x += math.cos(a) * ds
        y += math.sin(a) * ds
        pts.append((x, y))
    return pts


def fit_panel(P, anchor, lim=0.74):
    """Scale a stroke about its anchor until it stays inside `lim` of the panel's half height (it never touches a tube)."""
    P = np.asarray(P, np.float64)
    a = np.asarray(anchor, np.float64)
    for _ in range(4):
        mid, hh = pan_mid(P[:, 0])
        k = float(np.max(np.abs(P[:, 1] - mid) / np.maximum(hh, 1.0)))
        if k <= lim:
            break
        P = a + (P - a) * (lim / k) ** 0.9
    return P


def leaf(c, ang, ln, wd):
    """A laurel leaf (ref px): rounded base at c, pointed tip ln along angle ang."""
    ca, sa = math.cos(ang), math.sin(ang)
    m = 9

    def at(t, side):
        w = wd * math.sin(math.pi * t ** 0.75) * side
        return (c[0] + ca * ln * t - sa * w, c[1] + sa * ln * t + ca * w)
    return [at(k / m, 1) for k in range(m + 1)] + [at(k / m, -1) for k in range(m - 1, 0, -1)]


def qbez(a, c, b, n):
    return [(a[0] * (1 - t) ** 2 + 2 * c[0] * t * (1 - t) + b[0] * t * t, a[1] * (1 - t) ** 2 + 2 * c[1] * t * (1 - t) + b[1] * t * t)
            for t in (k / n for k in range(n + 1))]


em = []
_xl, _xr = _CC["tl"][0], _CC["tr"][0]
# the medallion (crown in a laurel wreath) sits 40% along the panel, sized to the panel's height there
_cx = _xl + 0.40 * (_xr - _xl)
_cy, _ch = (float(v) for v in pan_mid(_cx))
_wry = 0.70 * _ch                                 # wreath half height / half width (ref px): wider than tall (ref)
_wrx = 1.15 * _wry
_wc = (_cx, _cy)
_cs = 1.05 * _wry                                 # crown width
_cyc = _cy + 0.21 * _cs                           # the crown's visual middle on the wreath's middle


def C(u, v):                                      # crown-local (u right, v up, in crown widths) -> ref px
    return (_cx + u * _cs, _cyc - v * _cs)


# the crown: band, five points with scalloped valleys, pearls on the points, jewels on the band, a cross on top
_tips = [(-0.52, 0.30), (-0.27, 0.40), (0.0, 0.48), (0.27, 0.40), (0.52, 0.30)]
_body = qbez((-0.44, -0.14), (-0.50, 0.05), (_tips[0][0] - 0.03, _tips[0][1]), 6)
for (ua, va), (ub, vb) in zip(_tips, _tips[1:]):
    _body += [(ua - 0.015, va + 0.02), (ua + 0.015, va + 0.02)]
    _body += qbez((ua + 0.03, va), ((ua + ub) / 2, -0.20), (ub - 0.03, vb), 10)
_body += [(_tips[-1][0] - 0.015, _tips[-1][1] + 0.02), (_tips[-1][0] + 0.015, _tips[-1][1] + 0.02)]
_body += qbez((_tips[-1][0] + 0.03, _tips[-1][1]), (0.50, 0.05), (0.44, -0.14), 6)
em += relief([C(u, v) for u, v in _body], 0.0026, 0.35)
_band = []
for (cu, cv), a0 in (((0.43, -0.30), -0.5 * math.pi), ((0.43, -0.20), 0.0), ((-0.43, -0.20), 0.5 * math.pi), ((-0.43, -0.30), math.pi)):
    _band += [(cu + 0.04 * math.cos(a0 + 0.5 * math.pi * k / 4), cv + 0.04 * math.sin(a0 + 0.5 * math.pi * k / 4)) for k in range(5)]
em += relief([C(u, v) for u, v in _band], 0.0030, 0.8)
for u, v in _tips:                                                                  # pearls
    em += relief([C(u + 0.055 * math.cos(a), v + 0.06 + 0.055 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 14, endpoint=False)],
                 0.0032, 0.7)
for u in (-0.27, 0.0, 0.27):                                                        # jewels on the band
    em += relief([C(u + 0.07 * math.cos(a), -0.25 + 0.045 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 14, endpoint=False)],
                 0.0036, 0.6)
em += relief([C(u, v) for u, v in [(-0.035, 0.53), (0.035, 0.53), (0.035, 0.62), (0.10, 0.62), (0.10, 0.68), (0.035, 0.68),
                                    (0.035, 0.76), (-0.035, 0.76), (-0.035, 0.68), (-0.10, 0.68), (-0.10, 0.62), (-0.035, 0.62)]],
             0.0030, 0.5)                                                           # the cross
# the laurel wreath: two branches rising round the crown from a tie below it, leaves in pairs shrinking to the tips
_a0, _a1 = math.radians(-98), math.radians(64)
for side in (-1, 1):
    stem = [(_wc[0] + side * _wrx * math.cos(a), _wc[1] - _wry * math.sin(a)) for a in np.linspace(_a0, _a1, 44)]
    em += scroll(stem, 1.2, 0.6)
    nl = 7
    for q in range(nl):
        t = 0.08 + 0.86 * q / (nl - 1)
        a = _a0 + t * (_a1 - _a0)
        base = (_wc[0] + side * _wrx * math.cos(a), _wc[1] - _wry * math.sin(a))
        tng = math.atan2(-_wry * math.cos(a), side * -_wrx * math.sin(a))        # along the stem, toward its tip
        ln = (0.46 - 0.18 * t) * _wry
        wd = ln * 0.30
        for out_ in (1, -1):
            em += relief(leaf(base, tng + side * out_ * 0.60, ln, wd), 0.0020, 0.35 * wd)
    tb = (_wc[0] + side * _wrx * math.cos(_a1), _wc[1] - _wry * math.sin(_a1))
    em += relief(leaf(tb, math.atan2(-_wry * math.cos(_a1), side * -_wrx * math.sin(_a1)), 0.30 * _wry, 0.09 * _wry), 0.0020, 0.03 * _wry)
_tb = (_wc[0], _wc[1] + _wry)                                                       # the tie where the branches cross
em += relief([(_tb[0] + 0.10 * _wry * math.cos(a), _tb[1] + 0.07 * _wry * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 16, endpoint=False)],
             0.0026, 0.5)


# the filigree: a vine along the panel's centre line from the wreath toward each tip; C-scrolls branch off it on
# alternate sides and wind into Euler-spiral curls; every curl is sized to the panel's height where it sits (so the
# whole thing tapers with the panel) and kept clear of the tubes; the vine ends in a curl of its own
def filigree(x0, x1):
    d = 1 if x1 > x0 else -1
    n = 90
    xs = np.linspace(x0, x1, n)
    mid, hh = pan_mid(xs)
    t = np.linspace(0, 1, n)
    nb = max(2, int(round(abs(x1 - x0) / (0.85 * float(np.mean(hh))))))
    yv = mid + 0.10 * hh * np.sin(math.pi * nb * t)                                  # a gentle wave through the branches
    obs = scroll(list(zip(xs, yv)), 2.1, 1.1)
    va = np.arctan2(np.gradient(yv), np.gradient(xs))
    for b in range(nb):
        tb = (b + 0.35) / (nb + 0.2)
        i = int(tb * (n - 1))
        up = 1 if b % 2 == 0 else -1                                                # screen up first
        size = 0.37 * float(hh[i])
        ang = float(va[i]) - up * math.radians(35) * (1 if d > 0 else -1)
        br = curl((xs[i], yv[i]), ang, size, -d * up, lead=0.6, wind=3.4, length=3.6)
        br = fit_panel(br, (xs[i], yv[i]))
        w = 1.8 * (1 - 0.3 * tb)
        obs += scroll(br, w, 0.45 * w)
        lf = (xs[i] + d * 0.15 * size, yv[i])                                     # a small leaf at the branch's foot, other side
        la = (0.0 if d > 0 else math.pi) + d * up * math.radians(40)
        obs += relief(leaf(lf, la, 0.85 * size, 0.26 * size), 0.0018, 0.08 * size)
    end_up = 1 if nb % 2 == 0 else -1
    tail = curl((xs[-1], yv[-1]), float(va[-1]), 0.34 * float(hh[-1]), -d * end_up, lead=0.4, wind=3.6, length=4.0)
    obs += scroll(fit_panel(tail, (xs[-1], yv[-1])), 1.1, 0.5)
    return obs


_slim = np.nonzero((_CC["bot"] - _CC["top"]) / 2 > 9.0)[0]
_front_end = float(_CC["x"][_slim[-1]]) - 6.0          # where the panel gets too slim for the strokes
_rear_end = float(_CC["x"][_slim[0]]) + 8.0
_gap = 0.20 * _wry
em += filigree(_cx + _wrx + _gap, _front_end)
em += filigree(_cx - _wrx - _gap, _rear_end)
print(f"EMBLEM: crown x {_cx:.0f} (panel {_xl:.0f}-{_xr:.0f}, filigree to {_rear_end:.0f} / {_front_end:.0f}), "
      f"half height {_ch:.0f} px, {len(em)} parts")
if GAME:                                          # game: one engraving mesh, collapsed (it is a few px on screen)
    bpy.ops.object.select_all(action="DESELECT")
    for o in em:
        o.select_set(True)
    bpy.context.view_layer.objects.active = em[0]
    bpy.ops.object.join()
    _emo = bpy.context.view_layer.objects.active
    _n0 = len(_emo.data.polygons)
    _dm = _emo.modifiers.new("dec", "DECIMATE")
    _dm.ratio = float(arg("--emblem-ratio", "0.35"))
    apply_mods(_emo)
    print("EMBLEM game", _n0, "->", len(_emo.data.polygons), "faces")
    em = [_emo]
add("Bike_root", *em, name=FRAME_PART)


# ------------------------------------------------------------------ saddles (brown leather, gold rim + crown) + posts
SADDLE_LIP = 0.022                                 # the back's raised lip (side ref: the cantle rolls up behind the rider)


def saddle_hw(t):
    """Half width along the saddle (t 0 = back, 1 = nose): broad back rounded in plan, waist, narrow nose."""
    k = min(1.0, max(0.0, (t - 0.28) / 0.5))
    hw = 0.026 + 0.068 * (1 - k * k * (3 - 2 * k))
    if t < 0.09:
        hw *= max(0.06, math.sqrt(max(0.0, 1 - ((0.09 - t) / 0.09) ** 2)))
    return hw


def saddle_ring(sock, t):
    """One cross-section of the saddle: (y, half width, bottom z, top z, back lean)."""
    top = sock.z
    yr, yn = sock.y + 0.07, sock.y - 0.26
    lipw = (1 - smooth01(0.0, 0.34, t)) ** 2
    zt = top + 0.002 - 0.010 * t + SADDLE_LIP * lipw - 0.005 * math.sin(math.pi * min(1.0, t / 0.6))
    zb = top - 0.058 + 0.020 * t ** 1.5
    hw = saddle_hw(t)
    if t > 0.9:                                   # the nose rounds off (plan and side) instead of ending in a cut
        k = (t - 0.9) / 0.1
        sc = max(0.12, math.sqrt(max(0.0, 1 - k * k)))
        zc = 0.5 * (zt + zb)
        hw *= sc
        zt, zb = zc + (zt - zc) * (0.35 + 0.65 * sc), zc + (zb - zc) * (0.35 + 0.65 * sc)
    lean = 0.010 * (1 - smooth01(0.06, 0.30, t))        # the whole back leans out a little toward its top
    return yr + (yn - yr) * min(t, 1.0) + 0.012 * max(0.0, t - 0.9) / 0.1, hw, zb, zt, lean


def saddle_pt(sock, t, a, out=0.0):
    """Point on the saddle's surface: ring t, angle a (0 = right side, pi/2 = top); `out` pushes it off the surface."""
    y, hw, zb, zt, lean = saddle_ring(sock, t)
    c, s = math.cos(a), math.sin(a)
    g = 0.5 + 0.5 * math.copysign(abs(s) ** (0.85 if s >= 0 else 0.32), s)       # domed top, flat bottom
    x = hw * math.copysign(abs(c) ** 0.5, c) + out * c
    z = zb + (zt - zb) * g + out * s
    return Vector((x, y + lean * max(0.0, s) ** 2, z))


def saddle_pipe(t):
    """Where the gold piping runs, as sin of the ring angle: set by height (fraction of the ring's height) so it falls
    smoothly from high over the back's lip down the sides to near the base at the nose."""
    h = 0.955 + 0.02 * max(0.0, 1 - t / 0.09) - 0.86 * smooth01(0.08, 0.97, t)
    u = 2 * h - 1
    return u ** (1 / 0.85) if u >= 0 else -((-u) ** (1 / 0.32))


def saddle(sock, post_from, part, mounts=()):
    """Side + rear refs: a quilted cushion on a deep brown skirt, the gold piping between them arching over the raised
    back and running down the sides to the nose, a gold band round the base, a crown on the back and on each side."""
    top = sock.z
    yr = sock.y + 0.07                            # rear edge (the hips sit over the wide back)
    yn = sock.y - 0.26                            # nose
    ts = [0.0, 0.004, 0.012, 0.024, 0.04, 0.06, 0.085, 0.11, 0.14, 0.18, 0.23, 0.29, 0.36, 0.44, 0.52, 0.60, 0.68, 0.76,
          0.83, 0.89, 0.94, 0.975, 1.0]
    seg = 20 if GAME else 32
    base = [2 * math.pi * j / seg for j in range(seg)]
    bm = bmesh.new()
    rings, mats = [], []
    for t in ts:
        f = saddle_pipe(t)
        ap = [math.asin(f) % (2 * math.pi), math.pi - math.asin(f)]
        ang = list(base)
        for a in ap:                                                         # a ring vertex exactly on the piping line
            j = min(range(seg), key=lambda q: abs(math.atan2(math.sin(ang[q] - a), math.cos(ang[q] - a))))
            ang[j] = a
        rings.append([bm.verts.new(saddle_pt(sock, t, a)) for a in ang])
        mats.append([math.sin((ang[j] + ang[(j + 1) % seg]) / 2 + (math.pi if abs(ang[(j + 1) % seg] - ang[j]) > math.pi else 0)) < f - 1e-6
                     for j in range(seg)])
    lea, skirt = M["leather"], M["leather_skirt"]
    for i in range(len(ts) - 1):
        for j in range(seg):
            fc = bm.faces.new([rings[i][j], rings[i][(j + 1) % seg], rings[i + 1][(j + 1) % seg], rings[i + 1][j]])
            fc.material_index = 1 if (mats[i][j] and mats[i + 1][j]) else 0
            fc.smooth = True
    for ring, flip, mt in ((rings[0], False, mats[0]), (rings[-1], True, mats[-1])):
        c = bm.verts.new(sum((v.co for v in ring), Vector()) / len(ring))
        for j in range(seg):
            f_ = [ring[j], ring[(j + 1) % seg], c]
            fc = bm.faces.new(f_ if not flip else f_[::-1])
            fc.material_index = 1 if mt[j] else 0
            fc.smooth = True
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    so = obj("saddle", bm, "leather")
    so.data.materials.append(skirt)
    sd = so.modifiers.new("subd", "SUBSURF")              # one level: a soft, even leather surface (no ring seams)
    sd.levels = sd.render_levels = 1
    apply_mods(so)
    obs = [so]
    # the gold piping, both sides, joined over the back's lip
    tp = np.linspace(0.0, 0.96, 60)
    right = [saddle_pt(sock, t, math.asin(saddle_pipe(t)), 0.0015) for t in tp]
    left = [saddle_pt(sock, t, math.pi - math.asin(saddle_pipe(t)), 0.0015) for t in tp]
    obs.append(sweep(left[::-1] + right[1:], 0.0028, 0.0028, "gold", 8))
    # the gold band round the base (a closed loop just above the flat bottom)
    tb = np.linspace(0.0, 1.0, 50)
    ab = math.asin(-0.78)
    loop = [saddle_pt(sock, t, ab, 0.002) for t in tb] + [saddle_pt(sock, t, math.pi - ab, 0.002) for t in tb[::-1]]
    obs.append(sweep(loop + loop[:2], 0.0042, 0.0042, "gold", 8, closed_caps=False))
    # quilting: stitched pleats along the cushion and a seam where it rises into the lip
    for fr_ in (-0.55, -0.28, 0.0, 0.28, 0.55):
        pl = []
        for t in np.linspace(0.20, 0.90, 30):
            a = math.acos(math.copysign(abs(fr_) ** 2, fr_))                 # x = hw * |c|^0.5  ->  c = f^2
            pl.append(saddle_pt(sock, t, a, 0.0007))
        obs.append(sweep(pl, 0.0013, 0.0013, "leather_dark", 4))
    seam = [saddle_pt(sock, 0.17, a, 0.0008) for a in np.linspace(math.asin(saddle_pipe(0.17)) + 0.05,
                                                                   math.pi - math.asin(saddle_pipe(0.17)) - 0.05, 24)]
    obs.append(sweep(seam, 0.0014, 0.0014, "leather_dark", 4))
    # crowns: on the back (faces +Y, rearward) and on the skirt of each side near the back
    yb, hb, zbb, ztb, _ = saddle_ring(sock, 0.0)
    for mtl, pts in crown2d(0.0, zbb + 0.42 * (ztb - zbb), 0.030):
        obs.append(plate([(-a, b) for a, b in pts], V(yr + 0.0035, 0), (1, 0, 0), (0, 0, 1), mtl, 0.0025))
    tcw = 0.16
    for sx in (1, -1):
        q = saddle_pt(sock, tcw, 0.0 if sx > 0 else math.pi, 0.0018)
        _, _, zb_, zt_, _ = saddle_ring(sock, tcw)
        for mtl, pts in crown2d(q.y, zb_ + 0.40 * (zt_ - zb_), 0.026):
            obs.append(plate(pts, Vector((q.x, 0, 0)), (0, 1, 0), (0, 0, 1), mtl, 0.0025))
    # gold under-frame: two rails from the nose to a cantle bar
    zb = top - 0.06
    for sx in (1, -1):
        obs.append(tube(bezier(V(yn + 0.04, top - 0.035, sx * 0.012), V(sock.y - 0.08, zb - 0.02, sx * 0.04),
                               V(yr - 0.02, zb + 0.005, sx * 0.06), 10), 0.005, "gold", tseg=6))
    obs.append(tube([V(yr - 0.02, zb + 0.005, 0.06), V(yr - 0.02, zb + 0.005, -0.06)], 0.005, "gold", tseg=6))
    clamp = V(sock.y - 0.02, zb - 0.02)
    for my in mounts:                                    # cross bars: rail to rail over the frame tube below
        u = min(1.0, max(0.0, (my - (yn + 0.04)) / ((yr - 0.02) - (yn + 0.04))))
        mz = (1 - u) ** 2 * (top - 0.035) + 2 * u * (1 - u) * (zb - 0.02) + u * u * (zb + 0.005)
        hw = (1 - u) ** 2 * 0.012 + 2 * u * (1 - u) * 0.04 + u * u * 0.06
        obs.append(tube([V(my, mz - 0.002, hw), V(my, mz - 0.006, 0.0), V(my, mz - 0.002, -hw)], 0.0055, "gold", tseg=8))
    add("Bike_root", *obs, name=part)
    return clamp


C_CLAMP = saddle(SEAT_C, C_POST0, "seat_cycle_0", mounts=(SEAT_C.y + 0.03, SEAT_C.y - 0.03))
S_CLAMP = saddle(SEAT_S, S_POST0, "seat.001_cycle_0", mounts=(STOKER_FRONT_Y,))
# the decorative hook behind the stoker's post (ref): curls back from under the saddle and lands on top of the rear guard
_ga = math.radians(74)
GUARD_TOP = HUB_R + Vector((0, -math.cos(_ga), math.sin(_ga))) * (WR + 0.03 + 0.016)


# ------------------------------------------------------------------ chainrings, cranks, pedals, chains
def gear(c, r, teeth, x, spokes=8, th=0.006):
    bm = bmesh.new()
    outer, inner = [], []
    for k in range(teeth * 2):
        a = math.pi * k / teeth
        rr = r + (0.007 if k % 2 == 0 else 0.0)
        outer.append((rr * math.cos(a), rr * math.sin(a)))
        inner.append((r * 0.78 * math.cos(a), r * 0.78 * math.sin(a)))
    top_o = [bm.verts.new((x + th / 2, c.y + u, c.z + v)) for u, v in outer]
    bot_o = [bm.verts.new((x - th / 2, c.y + u, c.z + v)) for u, v in outer]
    top_i = [bm.verts.new((x + th / 2, c.y + u, c.z + v)) for u, v in inner]
    bot_i = [bm.verts.new((x - th / 2, c.y + u, c.z + v)) for u, v in inner]
    n = len(outer)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new([top_o[i], top_o[j], top_i[j], top_i[i]])
        bm.faces.new([bot_o[j], bot_o[i], bot_i[i], bot_i[j]])
        bm.faces.new([top_o[j], top_o[i], bot_o[i], bot_o[j]])
        bm.faces.new([top_i[i], top_i[j], bot_i[j], bot_i[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    o = obj("gear", bm, "gold")
    for p in o.data.polygons:
        p.use_smooth = False
    obs = [o, cyl(Vector((x - th, c.y, c.z)), Vector((x + th, c.y, c.z)), r * 0.24, "gold", 16),
           cyl(Vector((x - th * 0.2, c.y, c.z)), Vector((x + th * 0.2, c.y, c.z)), r * 0.77, "gold_deep", 28),   # backing disc
           torus(Vector((x, c.y, c.z)), r * 0.52, 0.004, "gold", seg=24, tseg=4)]
    for k in range(spokes):
        a = 2 * math.pi * k / spokes
        obs.append(box(Vector((x, c.y + math.cos(a) * r * 0.5, c.z + math.sin(a) * r * 0.5)), (th * 1.5, 0.011, r * 0.56), "gold",
                       rot=Matrix.Rotation(-a + math.pi / 2, 4, "X")))
    return obs


RING = 0.095
add("Crank_F", *gear(BB_F, RING, 32, -0.03))
add("Crank_R", *gear(BB_R, RING, 32, -0.03), *gear(BB_R, 0.07, 24, 0.03))
for crank, pins in (("Crank_F", ("Pedal_FL", "Pedal_FR")), ("Crank_R", ("Pedal_RL", "Pedal_RR"))):
    c = bh(crank)
    obs = [cyl(c + V(0, 0, -0.052), c + V(0, 0, 0.052), 0.012, "gold", 12)]
    for pb in pins:
        p = bh(pb)
        sx = 1 if p.x > 0 else -1
        a0, a1 = Vector((sx * 0.045, c.y, c.z)), Vector((sx * 0.045, p.y, p.z))
        obs.append(box((a0 + a1) / 2, (0.013, 0.024, (a1 - a0).length + 0.02), "gold", 0.005))
        obs.append(sphere(a0 + Vector((sx * 0.006, 0, 0)), 0.016, "gold", 10, (0.6, 1, 1)))
        obs.append(cyl(Vector((sx * 0.038, p.y, p.z)), Vector((sx * 0.05, p.y, p.z)), 0.013, "gold", 12))
    add(crank, *obs)
for pb in ("Pedal_FL", "Pedal_FR", "Pedal_RL", "Pedal_RR"):                 # brown leather rollers with gold caps
    p = bh(pb)
    pin = bh("PedalPin_" + pb.split("_")[1])
    c = Vector((p.x, p.y, pin.z - 0.012))
    sx = 1 if p.x > 0 else -1
    x0, x1 = c.x - sx * 0.035, c.x + sx * 0.05
    obs = [cyl(Vector((x0, c.y, c.z)), Vector((x1, c.y, c.z)), 0.018, "leather", 16)]
    for k in range(4):
        xx = x0 + (x1 - x0) * (0.15 + 0.23 * k)
        obs.append(torus(Vector((xx, c.y, c.z)), 0.0182, 0.0018, "leather", axis=(1, 0, 0), seg=14, tseg=4))
    for xx in (x0, x1):
        obs.append(cyl(Vector((xx - 0.006, c.y, c.z)), Vector((xx + 0.006, c.y, c.z)), 0.021, "gold", 16))
    add(pb, *obs)


def chain_loop(c0, r0, c1, r1, x, n=24):
    """Points round two sprockets along their outer tangents (in the YZ plane at x)."""
    d = c1 - c0
    ang = math.atan2(d.z, d.y)
    phi = math.acos(max(-1.0, min(1.0, (r0 - r1) / d.length)))
    pts = []
    for k in range(n + 1):
        a = ang + phi + (2 * math.pi - 2 * phi) * k / n
        pts.append(Vector((x, c0.y + r0 * math.cos(a), c0.z + r0 * math.sin(a))))
    for k in range(n + 1):
        a = ang - phi + 2 * phi * k / n
        pts.append(Vector((x, c1.y + r1 * math.cos(a), c1.z + r1 * math.sin(a))))
    return pts


def chain(c0, r0, c1, r1, x):
    pts = chain_loop(c0, r0, c1, r1, x)
    pts.append(pts[0])
    return sweep(pts, 0.0045, 0.0045, "gold", 4, closed_caps=False)


add("Bike_root", chain(BB_F, RING + 0.004, BB_R, RING + 0.004, -0.03))
add("Bike_root", chain(BB_R, 0.074, HUB_R, 0.042, 0.03))
add("Wheel_R", *gear(HUB_R, 0.036, 16, 0.03, spokes=5))

def grip(gp, sx):
    """Brown leather grip centred on the socket, its back end splayed outward (top ref). Returns (meshes, front end, axis)."""
    d = Vector((sx * 0.42, 1.0, 0.0)).normalized()
    g0, g1 = gp - d * 0.052, gp + d * 0.055
    obs = [cyl(g0, g1, 0.0185, "leather", 16)]
    for k in range(7):
        obs.append(torus(g0 + d * (0.01 + 0.0145 * k), 0.0188, 0.0022, "leather", axis=d, seg=12, tseg=4))
    for e, dd in ((g0, -1), (g1, 1)):
        obs.append(cyl(e - d * 0.006, e + d * 0.006, 0.021, "gold", 16))
    obs.append(sphere(g1 + d * 0.008, 0.012, "gold", 10))
    return obs, g0, d


# ------------------------------------------------------------------ steering (Steer): fork, steerer, stem, looped bars, lamp
st = []
crown = steer_pt(-0.03)
st.append(box(crown, (0.14, 0.045, 0.035), "gold", 0.01, rot=frame((0, 0, 0), STD)))
for sx in (1, -1):
    pts = bezier(crown + V(0, 0, sx * 0.052), steer_pt(-0.17) + V(0, 0, sx * 0.054), HUB_F + V(0.0, 0.07, sx * 0.056), 14,
                 HUB_F + V(0, 0, sx * 0.056))
    st.append(sweep(pts, 0.013, lambda t: 0.019 - 0.007 * t, "gold", 10))
    st.append(sphere(HUB_F + V(0, 0, sx * 0.056), 0.017, "gold", 10))
ST_TOP = steer_pt(0.33)
st.append(cyl(steer_pt(-0.03), ST_TOP, 0.017, "gold", 14))
for s in (0.27, 0.31):
    st.append(torus(steer_pt(s), 0.021, 0.0045, "gold", axis=STD, seg=18, tseg=6))
STEM = steer_pt(0.36)
st.append(sphere(ST_TOP, 0.024, "gold", 12))
for g in ("Grip_C_L", "Grip_C_R"):
    gp = GRIP[g]
    sx = 1 if gp.x > 0 else -1
    gobs, g0, d = grip(gp, sx)
    # up from the stem, out wide and a little forward, then back into the grip (side + top + front refs)
    pts = bezier(ST_TOP + V(0, 0.0, sx * 0.012), ST_TOP + V(-0.03, 0.2, sx * 0.07), g0 - d * 0.32 + V(-0.02, 0.07, sx * 0.07), 22, g0)
    st.append(tube(pts, 0.012, "gold", tseg=10))
    st += gobs
# head lamp: a big gold bell, sunburst lens (side ref: as tall as the head tube, out in front of it)
LC = steer_pt(0.2) + V(-0.17, 0.0)
LAX = Vector((0, -1, 0))
st.append(lathe([(0.0, 0.0), (0.0, 0.035), (0.05, 0.045), (0.13, 0.08), (0.17, 0.095), (0.2, 0.1), (0.201, 0.0)],
                LC + V(0.12, 0), LAX, "gold", 28))
st.append(torus(LC + V(-0.081, 0), 0.097, 0.011, "gold", axis=(0, 1, 0), seg=32, tseg=8))           # front bezel
for yy in (0.01, 0.05):
    st.append(torus(LC + V(yy, 0), 0.08 - yy * 0.6, 0.005, "gold", axis=(0, 1, 0), seg=28, tseg=6))  # body rings
st.append(lathe([(0.0, 0.09), (0.008, 0.07), (0.014, 0.0)], LC + V(-0.081, 0), LAX, "lens", 28))
for k in range(12):                                                                                 # sunburst ribs
    a = 2 * math.pi * k / 12
    st.append(box(LC + V(-0.094, 0.045 * math.cos(a), 0.045 * math.sin(a)), (0.004, 0.003, 0.07), "gold",
                  rot=Matrix.Rotation(a, 4, "Y")))
st.append(sphere(LC + V(-0.04, 0.104), 0.014, "gold", 10))                                          # top knob
st.append(cyl(LC + V(-0.04, 0.08), LC + V(-0.04, 0.104), 0.008, "gold", 10))
for sx in (1, -1):                                                                                 # bracket to the head
    st.append(tube([LC + V(0.12, -0.02, sx * 0.03), steer_pt(0.18) + V(0.0, 0.0, sx * 0.03)], 0.009, "gold"))
add("Steer", *st)

# stoker bars (Bike_root): clamp on the captain's seat post, swoop up and back to the stoker grips
_stem, _stq = bike_arc([NECK_END + V(-0.004, 0), NECK_END + V(0.035, 0.001), NECK_END + V(0.065, 0.012),
                        NECK_END + V(0.082, 0.040), NECK_END + V(0.086, 0.068)], K=5)
bend_report("STOKER_STEM", _stq)
SPLIT = _stem[-1]
_sdir = (_stem[-1] - _stem[-4]).normalized()
sobs = [sweep(_stem, lambda t: NECK_R - 0.002 - 0.005 * t, lambda t: NECK_R - 0.002 - 0.005 * t, "gold", 16),
        torus(NECK_END + V(0.002, 0), NECK_R + 0.0012, 0.0055, "gold", axis=(0, 1, 0), seg=24, tseg=8),   # the collar
        sphere(SPLIT + _sdir * 0.004, 0.0215, "gold", 16)]                                            # the ball (top ref)
for g in ("Grip_S_L", "Grip_S_R"):
    gp = GRIP[g]
    sx = 1 if gp.x > 0 else -1
    gobs, g0, d = grip(gp, sx)
    # out to the side and up from the ball, then round and back into the grip (a U opening rearward, top ref)
    pts = bezier(SPLIT, SPLIT + _sdir * 0.05 + V(-0.012, 0.0, sx * 0.075), g0 - d * 0.12 + V(0, -0.01, 0), 24, g0)
    sobs += [sweep(pts, 0.012, 0.012, "gold", 12)] + gobs
add("Bike_root", *sobs, name="goosefit_stoker_stem_cycle_0")


# ------------------------------------------------------------------ join per bone, parent to the bone
def join_into(obs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    if len(obs) > 1:
        bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = name
    o.data.name = name
    return o


TRIS = {}
FINAL = []
for (bone, part), obs in PARTS.items():
    o = join_into(obs, part or f"GS_{bone}")
    b = BONE[bone]
    pm = RIG.matrix_world @ b.matrix_local @ Matrix.Translation((0, b.length, 0))
    o.parent = RIG
    o.parent_type = "BONE"
    o.parent_bone = bone
    o.matrix_parent_inverse = pm.inverted()
    TRIS[part or bone] = sum(len(p.vertices) - 2 for p in o.data.polygons)
    FINAL.append(o)
print("TRIS", sum(TRIS.values()), TRIS)

# ------------------------------------------------------------------ export
bpy.ops.object.select_all(action="DESELECT")
RIG.select_set(True)
for o in FINAL:
    o.select_set(True)
glb = OUT / f"gold_standard_tandem{SFX}.glb"
bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True, export_animations=True,
                          export_animation_mode="NLA_TRACKS", export_yup=True, export_def_bones=False, export_tangents=False)
info = {"glb": str(glb.relative_to(ROOT)), "tris": TRIS, "tris_total": sum(TRIS.values()), "frame_trace_px": SNAP_LOG,
        "clips": ["Pedal", "WheelSpin"], "base_rig": str(BASE), "refs": "refs/gold_standard/pete_refs"}
(OUT / f"gold_standard_tandem{SFX}_info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"gold_standard_tandem{SFX}.blend"))
print("EXPORT", glb, round(glb.stat().st_size / 1e6, 2), "MB")
# the frame on its own (bike space, no rig): one component to review / hand on
bpy.ops.object.select_all(action="DESELECT")
_fo = bpy.data.objects[FRAME_PART]
_fo.select_set(True)
_fglb = OUT / f"gold_standard_frame{SFX}.glb"
bpy.ops.export_scene.gltf(filepath=str(_fglb), export_format="GLB", use_selection=True, export_animations=False,
                          export_yup=True, export_tangents=False)
print("EXPORT FRAME", _fglb, TRIS.get(FRAME_PART), "tris", len(_fo.data.materials), "materials",
      round(_fglb.stat().st_size / 1e6, 2), "MB")

# ------------------------------------------------------------------ review renders (match the ref views)
if "--sheet" in argv:
    for o in bpy.data.objects:
        if o.type == "CAMERA":
            bpy.data.objects.remove(o, do_unlink=True)
    # Cycles: real reflections, so polished gold reads as gold (EEVEE showed it as matte clay)
    SC.render.engine = "CYCLES"
    SC.cycles.samples = int(arg("--samples", "64"))
    SC.cycles.use_denoising = True
    try:
        cp = bpy.context.preferences.addons["cycles"].preferences
        for kind in ("OPTIX", "CUDA"):
            try:
                cp.compute_device_type = kind
                cp.get_devices()
                if any(d.type == kind for d in cp.devices):
                    for d in cp.devices:
                        d.use = d.type == kind
                    SC.cycles.device = "GPU"
                    break
            except TypeError:
                continue
    except Exception as e:                                # CPU is fine, only slower
        print("cycles gpu:", e)
    print("CYCLES device", SC.cycles.device)
    SC.render.film_transparent = True                    # backdrop composited after: the world only lights + reflects
    w = bpy.data.worlds.new("w") if not SC.world else SC.world
    SC.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes.get("Background")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    ramp = nt.nodes.new("ShaderNodeValToRGB")             # studio: dark floor, bright horizon band, soft sky
    ramp.color_ramp.elements[0].position = 0.40
    ramp.color_ramp.elements[0].color = (0.03, 0.025, 0.02, 1)
    ramp.color_ramp.elements[1].position = 0.52
    ramp.color_ramp.elements[1].color = (2.2, 2.1, 1.9, 1)
    e = ramp.color_ramp.elements.new(0.62)
    e.color = (0.35, 0.36, 0.4, 1)
    e = ramp.color_ramp.elements.new(0.9)
    e.color = (0.9, 0.9, 0.95, 1)
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = -1.0
    mr.inputs["From Max"].default_value = 1.0
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs[0])
    bg.inputs[1].default_value = 0.9
    SC.view_settings.view_transform = "AgX"
    for nm, rot, en in (("key", (50, 0, 120), 2.0), ("fill", (60, 0, -60), 0.6), ("rim", (20, 0, 180), 0.8)):
        ld = bpy.data.lights.new(nm, "SUN")
        ld.energy = en
        lo = bpy.data.objects.new(nm, ld)
        lo.rotation_euler = [math.radians(a) for a in rot]
        COL.objects.link(lo)
    cd = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cd)
    COL.objects.link(cam)
    SC.camera = cam
    SC.frame_set(0)
    # orthographic views like Pete's refs (side = left side, front to the right), plus a 3/4
    views = {"side": ((-4.0, 0.0, 0.62), (0, 0.0, 0.62), 2.5, (1536, 768), True),
             # framed exactly like pete_refs/side.png (1536 x 768 at its 1.627 mm/px): overlay it with gs_overlay.py
             "side_ref": ((-4.0, HUB_R.y - 556 * _S, WR + 144.5 * _S), (0, HUB_R.y - 556 * _S, WR + 144.5 * _S), 1536 * _S, (1536, 768), True),
             "front": ((0.0, -4.0, 0.62), (0, 0.0, 0.62), 1.3, (1086, 1448), True),
             "rear": ((0.0, 4.0, 0.62), (0, 0.0, 0.62), 1.3, (1086, 1448), True),
             "top": ((0.0, 0.0, 4.0), (0, 0.0, 0.62), 2.5, (2000, 667), True),
             "q34": ((-2.4, -2.3, 1.3), (0, 0.0, 0.55), 32, (1600, 900), False),
             "plate": ((-0.9, -0.33, 0.72), (0, -0.33, 0.68), 35, (1200, 800), False),
             "lamp_q34": ((-1.0, -1.9, 1.05), (0, -0.75, 0.85), 40, (1200, 800), False),
             # the core sculpt up close: square on, and from low front-left so the plate's relief shows
             "core": ((-4.0, -0.25, 0.68), (0, -0.25, 0.68), 1.45, (1600, 900), True),
             "core_q": ((-1.25, -1.05, 0.62), (0, -0.28, 0.66), 40, (1600, 900), False),
             "core_r": ((-1.3, 0.75, 0.95), (0, -0.15, 0.62), 40, (1600, 900), False)}
    _t, _hd = core_map(815, 370), core_map(1160, 285)
    views["tail_q"] = (tuple(_t + Vector((-0.55, -0.32, 0.12))), tuple(_t), 50, (1400, 1000), False)
    views["tail"] = (tuple(_t + Vector((-4.0, 0, 0))), tuple(_t), 0.42, (1400, 1000), True)
    views["head_q"] = (tuple(_hd + Vector((-0.55, -0.3, 0.15))), tuple(_hd), 50, (1400, 1000), False)
    _cl = core_map(405, 350)
    # 1:1 with the ref crop x 340..1240, y 92..598 (use with --nowarp; scripts/gs_core_compare.py)
    views["core_ref"] = ((-4.0, HUB_R.y - (790 - 212) * _S, WR + (528.5 - 345) * _S), (0, HUB_R.y - (790 - 212) * _S, WR + (528.5 - 345) * _S), 900 * _S, (1600, 900), True)
    _rb = arg("--refbox")                       # any ref box (x0,y0,x1,y1 px) 1:1 side-on (use with --nowarp)
    if _rb:
        bx0, by0, bx1, by1 = map(float, _rb.split(","))
        _cy, _cz = HUB_R.y - ((bx0 + bx1) / 2 - 212) * _S, WR + (528.5 - (by0 + by1) / 2) * _S
        _bw, _bh = bx1 - bx0, by1 - by0
        _k = 1600 / max(_bw, _bh)
        views["refbox"] = ((-4.0, _cy, _cz), (0, _cy, _cz), max(_bw, _bh) * _S, (int(_bw * _k), int(_bh * _k)), True)
    _cs = SEAT_C + V(-0.06, -0.09)
    views["capseat_q"] = (tuple(_cs + Vector((-0.55, -0.32, 0.12))), tuple(_cs), 50, (1400, 1000), False)
    views["capseat_r"] = (tuple(_cs + Vector((-0.5, 0.42, 0.18))), tuple(_cs), 50, (1400, 1000), False)
    _ss = SEAT_S + V(-0.07, -0.13)
    views["stkseat_q"] = (tuple(_ss + Vector((-0.6, -0.34, 0.12))), tuple(_ss), 50, (1400, 1000), False)
    views["frame_q"] = ((-1.55, -1.25, 1.05), (0, 0.05, 0.5), 38, (1600, 1000), False)
    _pc = core_map(940, 318)
    views["panel"] = (tuple(_pc + Vector((-4.0, 0, 0))), tuple(_pc), 0.62, (1600, 900), True)
    views["panel_q"] = (tuple(_pc + Vector((-0.62, -0.42, 0.10))), tuple(_pc), 50, (1600, 1000), False)
    views["cluster_q"] = (tuple(_cl + Vector((-0.6, -0.25, 0.1))), tuple(_cl), 50, (1400, 1000), False)
    only = arg("--views")
    if only:
        views = {k: v for k, v in views.items() if k in only.split(",")}
    if CORE_RAW is not None:
        CORE_RAW.location.x = 0.0
        for o in bpy.data.objects:
            if o.type == "MESH" and o is not CORE_RAW:
                o.hide_render = True
    _pre = ""
    if "--frame-only" in argv:                     # the frame component alone
        _pre = "frame_"
        for o in bpy.data.objects:
            if o.type == "MESH" and o.name != FRAME_PART:
                o.hide_render = True
    for nm, (eye, tgt, lens, res, ortho) in views.items():
        SC.render.resolution_x, SC.render.resolution_y = res
        cam.location = Vector(eye)
        up = "Y"
        q = (Vector(tgt) - Vector(eye)).to_track_quat("-Z", up)
        if nm == "top":
            q = Matrix.Rotation(math.radians(-90), 4, "Z").to_quaternion()      # front (-Y) to the right
        cam.rotation_euler = q.to_euler()
        cd.type = "ORTHO" if ortho else "PERSP"
        if ortho:
            cd.ortho_scale = lens
        else:
            cd.lens = lens
        SC.render.filepath = str(REN / f"gs_{_pre}{nm}{SFX}.png")
        bpy.ops.render.render(write_still=True)
        _im = bpy.data.images.load(SC.render.filepath, check_existing=False)    # composite onto a flat grey backdrop
        _w, _h = _im.size
        _a = np.array(_im.pixels[:], dtype=np.float32).reshape(_h, _w, 4)
        _a[..., :3] = _a[..., :3] * _a[..., 3:4] + np.array([0.74, 0.74, 0.76]) * (1 - _a[..., 3:4])
        _a[..., 3] = 1.0
        _im.pixels[:] = _a.ravel()
        _im.save()
        print("RENDER", SC.render.filepath)
