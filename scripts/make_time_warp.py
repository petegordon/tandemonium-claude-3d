"""Time Warp tandem (Tandemonium #611): Pete's steampunk time-travel tandem, built in code on the game tandem's rig.

  blender -b --factory-startup --python scripts/make_time_warp.py -- [--base <bike_rigged_goosefit26.blend>] [--sheet]

Look: refs/time_warp/pete_refs/concept_01_steampunk_side.png (maroon + brass; the clock between two glowing blue
tubes; sprung leather saddles; big brass headlamp; rockets on the rear with blue flames; a goose on the fin).
Pete 2026-11-07: the clock spins fast; blue flames with an orange/red pop now and then; FOUR engines, a stacked pair
on each side of the rear wheel.

Rig: the game tandem's own armature (out/bike/bike_rigged_goosefit26.blend, make_bike.py --tag goosefit26) with its
Pedal and WheelSpin clips and every socket (Seat_*, Grip_*, PedalPin_*), so every goose rider fits it exactly as it
fits the game tandem: nothing to re-bake. Its meshes are thrown away and the new bike is built on the same bones:
  Bike_root  frame, saddles, clock module, chain, rack, fin, rockets     Steer  fork, head lamp, stem, bars, front guard
  Wheel_F|R  wheels      Crank_F|R  chainrings + crank arms      Pedal_*  pedals
New bones for the effects (all under Bike_root):
  ClockM_L|R, ClockH_L|R   minute / hour hand on each face (local Y = through the face)
  FlameB_<n>, FlameO_<n>   the blue flame and the orange/red pop of engine n (local Y = out of the nozzle)
New clip TimeWarpFX (4 s loop): minute hands 8 turns (2 a second), hour hands 1 turn; blue flames flicker; each
engine pops orange/red twice, at its own moments.

Writes out/time_warp/time_warp_tandem.glb (+ _info.json) and with --sheet renders/time_warp/*.png.
"""
import json
import math
import random
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(k, d=None):
    return argv[argv.index(k) + 1] if k in argv else d


BASE = Path(arg("--base", str(ROOT.parent / "tandemonium-claude-3d" / "out" / "bike" / "bike_rigged_goosefit26.blend")))
OUT = ROOT / "out" / "time_warp"
REN = ROOT / "renders" / "time_warp"
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


def halo_mat(name, rgb, alpha, strength):
    """See-through glow round a flame (alpha-blended, emissive)."""
    m = mat(name, rgb, 0.0, 0.5, rgb, strength)
    m.node_tree.nodes["Principled BSDF"].inputs["Alpha"].default_value = alpha
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED"
    if hasattr(m, "blend_method"):
        m.blend_method = "BLEND"
    m.use_backface_culling = True
    return m


M = {
    "paint": mat("tw_maroon", (0.21, 0.012, 0.022), 0.35, 0.28),
    "brass": mat("tw_brass", (0.76, 0.49, 0.17), 0.6, 0.3),        # (metallic 0.6: full metal reads black in lean mode)
    "leather": mat("tw_leather", (0.40, 0.19, 0.09), 0.0, 0.55),
    "rubber": mat("tw_rubber", (0.025, 0.025, 0.025), 0.0, 0.85),
    "dark": mat("tw_dark", (0.045, 0.04, 0.035), 0.3, 0.45),
    "face": mat("tw_clockface", (0.93, 0.87, 0.71), 0.0, 0.6),
    "glass": mat("tw_timeglass", (0.03, 0.3, 1.0), 0.0, 0.15, (0.03, 0.35, 1.0), 1.0),
    "lens": mat("tw_lamp", (1.0, 0.86, 0.55), 0.0, 0.2, (1.0, 0.78, 0.4), 2.0),
    "flame_b": mat("tw_flame_blue", (0.02, 0.2, 1.0), 0.0, 0.4, (0.02, 0.22, 1.0), 1.3),
    "flame_core": mat("tw_flame_core", (0.45, 0.85, 1.0), 0.0, 0.4, (0.3, 0.75, 1.0), 2.0),
    "flame_halo": halo_mat("tw_flame_halo", (0.05, 0.3, 1.0), 0.28, 1.2),
    "flame_o": mat("tw_flame_orange", (1.0, 0.4, 0.02), 0.0, 0.4, (1.0, 0.36, 0.01), 1.7),
    "flame_r": mat("tw_flame_red", (0.9, 0.05, 0.01), 0.0, 0.4, (0.95, 0.05, 0.01), 1.4),
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


def tube(points, r, material, tseg=8, closed=False):
    """Round tube swept along a polyline (parallel-transported frames, no twist)."""
    P = [Vector(p) for p in points]
    n = len(P)
    bm = bmesh.new()
    rows = []
    prev_u = None
    for i in range(n):
        a = P[i - 1] if (closed or i > 0) else P[i]
        b = P[(i + 1) % n] if (closed or i < n - 1) else P[i]
        t = (b - a).normalized()
        if prev_u is None:
            up = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
            u = t.cross(up).normalized()
        else:
            u = (prev_u - t * prev_u.dot(t)).normalized()
        prev_u = u
        w = t.cross(u).normalized()
        rows.append([bm.verts.new(P[i] + (u * math.cos(2 * math.pi * j / tseg) + w * math.sin(2 * math.pi * j / tseg)) * r)
                     for j in range(tseg)])
    for i in range(n if closed else n - 1):
        for j in range(tseg):
            bm.faces.new([rows[i][j], rows[(i + 1) % n][j], rows[(i + 1) % n][(j + 1) % tseg], rows[i][(j + 1) % tseg]])
    if not closed:
        for row, flip in ((rows[0], True), (rows[-1], False)):
            f = bm.faces.new(row[::-1] if flip else row)
            f.smooth = False
    return obj("tube", bm, material)


def bezier(p0, p1, p2, n=12, p3=None):
    p0, p1, p2 = Vector(p0), Vector(p1), Vector(p2)
    if p3 is None:
        return [p0 * (1 - t) ** 2 + p1 * 2 * t * (1 - t) + p2 * t * t for t in (i / n for i in range(n + 1))]
    p3 = Vector(p3)
    return [p0 * (1 - t) ** 3 + p1 * 3 * t * (1 - t) ** 2 + p2 * 3 * t * t * (1 - t) + p3 * t ** 3 for t in (i / n for i in range(n + 1))]


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


def flat_poly(pts2d, x, material, thick=0.002):
    """A thin plate in the YZ plane at x (the fin, the goose emblem): pts2d = [(y, z)] outline (convex-ish fan)."""
    bm = bmesh.new()
    fr = [bm.verts.new((x - thick / 2, y, z)) for y, z in pts2d]
    bk = [bm.verts.new((x + thick / 2, y, z)) for y, z in pts2d]
    bm.faces.new(fr[::-1])
    bm.faces.new(bk)
    n = len(pts2d)
    for i in range(n):
        bm.faces.new([fr[i], fr[(i + 1) % n], bk[(i + 1) % n], bk[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    o = obj("plate", bm, material)
    for p in o.data.polygons:
        p.use_smooth = False
    return o


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


# ------------------------------------------------------------------ wheels (Wheel_F / Wheel_R)
def wheel(bone, hub):
    obs = [torus(hub, WR - 0.021, 0.021, "rubber", seg=48, tseg=10),
           torus(hub, WR - 0.045, 0.009, "brass", seg=48, tseg=8),
           torus(hub, WR - 0.056, 0.004, "brass", seg=48, tseg=6),
           cyl(hub + Vector((-0.055, 0, 0)), hub + Vector((0.055, 0, 0)), 0.018, "brass", 16),
           cyl(hub + Vector((-0.035, 0, 0)), hub + Vector((-0.028, 0, 0)), 0.034, "brass", 20),
           cyl(hub + Vector((0.028, 0, 0)), hub + Vector((0.035, 0, 0)), 0.034, "brass", 20)]
    for k in range(32):                                                     # spokes, laced from both flanges
        a = 2 * math.pi * k / 32
        side = 1 if k % 2 else -1
        p0 = hub + Vector((side * 0.031, 0.03 * math.cos(a + 0.35), 0.03 * math.sin(a + 0.35)))
        p1 = hub + Vector((0, (WR - 0.05) * math.cos(a), (WR - 0.05) * math.sin(a)))
        obs.append(cyl(p0, p1, 0.0019, "brass", 4, caps=False))
    add(bone, *obs)


wheel("Wheel_F", HUB_F)
wheel("Wheel_R", HUB_R)


# ------------------------------------------------------------------ guards
def guard(bone, hub, a0, a1, R=WR + 0.035, w=0.034):
    rows_n = 28
    bm = bmesh.new()
    G = []
    for i in range(rows_n + 1):
        a = math.radians(a0 + (a1 - a0) * i / rows_n)
        rad = Vector((0, -math.cos(a), math.sin(a)))
        row = []
        for j, xx in enumerate((-w, -w * 0.5, 0, w * 0.5, w)):
            crown = 0.012 * (1 - (xx / w) ** 2)
            row.append(bm.verts.new(hub + rad * (R + crown - (0.012 if abs(xx) == w else 0)) + Vector((xx, 0, 0))))
        G.append(row)
    for i in range(rows_n):
        for j in range(4):
            bm.faces.new([G[i][j], G[i + 1][j], G[i + 1][j + 1], G[i][j + 1]])
    o = obj("guard", bm, "paint")
    mo = o.modifiers.new("sol", "SOLIDIFY")
    mo.thickness = 0.003
    apply_mods(o)
    tip = hub + Vector((0, -math.cos(math.radians(a1)), math.sin(math.radians(a1)))) * (R - 0.004)
    add(bone, o, sphere(tip, 0.012, "brass", 10, (2.8, 1, 1)))


guard("Steer", HUB_F, -12, 128)
guard("Bike_root", HUB_R, 48, 192)

# ------------------------------------------------------------------ frame (Bike_root)
H_TOP, H_BOT = steer_pt(0.19), steer_pt(0.02)
C_TOP = V(-0.075, 0.775)                         # captain seat tube top lug
S_TOP = V(0.565, 0.75)                           # stoker seat tube top lug
TT_END = V(0.553, 0.712)
fr = []
fr.append(cyl(H_BOT - STD * 0.01, H_TOP + STD * 0.01, 0.026, "paint", 20))      # head tube
for s in (0.0, 0.2):
    fr.append(torus(steer_pt(s), 0.028, 0.006, "brass", axis=STD, seg=24, tseg=6))
fr.append(tube(bezier(H_TOP + V(0.01, -0.01), V(-0.2, 0.77), TT_END, 16), 0.019, "paint"))           # top tube
fr.append(tube([H_BOT + V(0.01, 0.0), BB_F], 0.021, "paint"))                                        # down tube
fr.append(tube([BB_F, C_TOP], 0.019, "paint"))                                                       # captain seat tube
fr.append(tube([BB_R, S_TOP], 0.019, "paint"))                                                       # stoker seat tube
fr.append(tube([BB_F + V(0, 0.0), BB_R], 0.019, "paint"))                                            # bottom tube
fr.append(tube(bezier(H_BOT + V(0.02, -0.03), V(-0.3, 0.50), V(0.47, 0.43), 16), 0.016, "paint"))    # lower tube
for sx in (1, -1):
    fr.append(tube([BB_R + V(0, 0, sx * 0.02), HUB_R + V(0, 0, sx * 0.058)], 0.013, "paint"))         # chainstays
    fr.append(tube([S_TOP + V(0.0, -0.03, sx * 0.02), HUB_R + V(0, 0.01, sx * 0.058)], 0.012, "paint"))  # seatstays
for p in (BB_F, BB_R):                                                                               # bottom brackets
    fr.append(cyl(p + V(0, 0, -0.04), p + V(0, 0, 0.04), 0.026, "paint", 20))
    fr.append(torus(p + V(0, 0, 0.041), 0.026, 0.004, "brass", seg=16, tseg=4))
    fr.append(torus(p + V(0, 0, -0.041), 0.026, 0.004, "brass", seg=16, tseg=4))
for p in (C_TOP, S_TOP, TT_END, H_TOP, H_BOT):                                                       # lugs
    fr.append(sphere(p, 0.026, "brass", 10))
add("Bike_root", *fr)
# gold scroll decals along the top tube (a few raised brass curls, the concept's filigree)
for i, (yy, zz) in enumerate(((-0.5, 0.79), (-0.36, 0.778), (0.25, 0.735), (0.4, 0.725))):
    for sx in (1, -1):
        pts = [V(yy + 0.03 * math.cos(a) * (1 - a / 12), zz - 0.012 + 0.012 * math.sin(a) * (1 - a / 12), sx * 0.0195)
               for a in [k * 0.45 for k in range(22)]]
        add("Bike_root", tube(pts[::2], 0.0022, "brass", tseg=4))


# ------------------------------------------------------------------ saddles (sprung leather) + seat posts
def saddle(sock, top_lug, part):
    top = sock.z
    yr = sock.y + 0.065                           # rear edge (the hips sit over the wide back)
    yn = sock.y - 0.27                            # nose
    n, seg = 14, 18
    bm = bmesh.new()
    rings = []
    for i in range(n + 1):
        t = i / n
        y = yr + (yn - yr) * t
        hw = 0.088 * (1 - t) ** 0.5 * (1 - 0.72 * t) + 0.024 * t
        hh = 0.036 * (1 - 0.4 * t)
        zc = top - hh - 0.012 * t
        ring = []
        for j in range(seg):
            a = 2 * math.pi * j / seg
            c, s = math.cos(a), math.sin(a)
            ring.append(bm.verts.new((hw * math.copysign(abs(c) ** 0.6, c), y, zc + hh * math.copysign(abs(s) ** 0.8, s))))
        rings.append(ring)
    for i in range(n):
        for j in range(seg):
            bm.faces.new([rings[i][j], rings[i][(j + 1) % seg], rings[i + 1][(j + 1) % seg], rings[i + 1][j]])
    for ring, flip in ((rings[0], False), (rings[-1], True)):
        c = bm.verts.new(sum((v.co for v in ring), Vector()) / len(ring))
        for j in range(seg):
            f = [ring[j], ring[(j + 1) % seg], c]
            bm.faces.new(f if not flip else f[::-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    obs = [obj("saddle", bm, "leather")]
    zb = top - 0.05
    for k in range(5):                                                      # brass rivets round the rim
        t = k / 4
        a = math.pi * (0.15 + 0.7 * t)
        obs.append(sphere(V(yr - 0.02 - 0.05 * math.sin(a), top - 0.016, 0.082 * math.cos(a)), 0.005, "brass", 5))
        obs.append(sphere(V(yr - 0.02 - 0.05 * math.sin(a), top - 0.016, -0.082 * math.cos(a)), 0.005, "brass", 5))
    for sx in (1, -1):                                                      # coil springs at the back
        c0 = V(yr - 0.02, zb - 0.045, sx * 0.05)
        pts = []
        for k in range(37):
            a = k / 36 * 2 * math.pi * 4.5
            pts.append(V(c0.y + 0.014 * math.sin(a), c0.z + 0.055 * k / 36, c0.x + 0.014 * math.cos(a)))
        obs.append(tube(pts, 0.0028, "brass", tseg=4))
        obs.append(tube([V(sock.y - 0.21, top - 0.04, sx * 0.02), V(yr - 0.02, zb - 0.045, sx * 0.05)], 0.004, "brass", tseg=6))   # rails
    post_top = V(sock.y - 0.03, zb - 0.045)
    obs.append(tube([top_lug, post_top], 0.013, "brass"))                   # seat post
    obs.append(box(V(sock.y - 0.03, zb - 0.045), (0.12, 0.03, 0.012), "brass", 0.004))   # clamp bar under the springs
    add("Bike_root", *obs, name=part)


saddle(SEAT_C, C_TOP, "seat_cycle_0")
saddle(SEAT_S, S_TOP, "seat.001_cycle_0")

# ------------------------------------------------------------------ clock module (Bike_root): brass clock between two time-glass tubes
CLK = V(0.19, 0.6)
CLK_R = 0.075
MOD_Y0, MOD_Y1 = -0.125, 0.505
cm = []
for (y0, y1) in ((MOD_Y0 + 0.045, CLK.y - CLK_R - 0.012), (CLK.y + CLK_R + 0.012, MOD_Y1 - 0.045)):
    cm.append(cyl(V(y0, CLK.z), V(y1, CLK.z), 0.03, "glass", 20))                                    # glowing glass
    for k in range(3):                                                                               # brass cage bars
        a = 2 * math.pi * k / 3 + 0.5
        off = Vector((0.033 * math.cos(a), 0, 0.033 * math.sin(a)))
        cm.append(cyl(V(y0, CLK.z) + off, V(y1, CLK.z) + off, 0.0035, "brass", 6))
    for yy in (y0, y1):
        cm.append(cyl(V(yy - 0.008, CLK.z), V(yy + 0.008, CLK.z), 0.038, "brass", 20))               # end collars
        cm.append(torus(V(yy, CLK.z), 0.038, 0.004, "brass", axis=(0, 1, 0), seg=16, tseg=4))
cm.append(lathe([(0, 0.038), (0.02, 0.034), (0.045, 0.012), (0.05, 0.0)], V(MOD_Y0 + 0.045, CLK.z), (0, -1, 0), "brass"))   # end cones
cm.append(lathe([(0, 0.038), (0.02, 0.034), (0.045, 0.012), (0.05, 0.0)], V(MOD_Y1 - 0.045, CLK.z), (0, 1, 0), "brass"))
cm.append(tube([V(MOD_Y0 + 0.005, CLK.z), V(-0.135, 0.6)], 0.008, "brass"))                          # to the seat tubes
cm.append(tube([V(MOD_Y1 - 0.005, CLK.z), V(0.51, 0.6)], 0.008, "brass"))
cm.append(cyl(CLK + V(0, 0, -0.022), CLK + V(0, 0, 0.022), CLK_R + 0.012, "brass", 40))                # clock case
for sx in (1, -1):
    cm.append(cyl(CLK + V(0, 0, sx * 0.022), CLK + V(0, 0, sx * 0.0235), CLK_R, "face", 40))         # dial
    cm.append(torus(CLK + V(0, 0, sx * 0.024), CLK_R + 0.006, 0.006, "brass", seg=40, tseg=8))         # bezel
    for k in range(12):                                                                              # hour marks
        a = 2 * math.pi * k / 12
        L = 0.016 if k % 3 == 0 else 0.009
        c = CLK + V(math.sin(a) * (CLK_R - 0.012 - L / 2), math.cos(a) * (CLK_R - 0.012 - L / 2), sx * 0.0242)
        cm.append(box(c, (0.0012, 0.004 if k % 3 else 0.006, L), "dark", rot=Matrix.Rotation(-a, 4, "X")))
    for k in range(4):                                                                               # bezel rivets
        a = 2 * math.pi * k / 4 + math.pi / 4
        cm.append(sphere(CLK + V(math.sin(a) * (CLK_R + 0.006), math.cos(a) * (CLK_R + 0.006), sx * 0.03), 0.004, "brass", 6))
cm.append(sphere(CLK + V(0, CLK_R + 0.02, 0), 0.012, "brass", 10))                                     # crown on top
cm.append(cyl(CLK + V(0, CLK_R + 0.008, 0), CLK + V(0, CLK_R + 0.02, 0), 0.008, "brass", 10))
add("Bike_root", *cm)

# ------------------------------------------------------------------ chainrings, cranks, pedals, chains
def gear(c, r, teeth, x, material="brass", th=0.005):
    bm = bmesh.new()
    outer, inner = [], []
    for k in range(teeth * 2):
        a = math.pi * k / teeth
        rr = r + (0.007 if k % 2 == 0 else 0.0)
        outer.append((rr * math.cos(a), rr * math.sin(a)))
    for k in range(teeth * 2):
        a = math.pi * k / teeth
        inner.append((r * 0.72 * math.cos(a), r * 0.72 * math.sin(a)))
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
    o = obj("gear", bm, material)
    for p in o.data.polygons:
        p.use_smooth = False
    obs = [o, cyl(Vector((x - th, c.y, c.z)), Vector((x + th, c.y, c.z)), r * 0.25, material, 16)]
    for k in range(5):
        a = 2 * math.pi * k / 5
        obs.append(box(Vector((x, c.y + math.cos(a) * r * 0.48, c.z + math.sin(a) * r * 0.48)), (th, 0.012, r * 0.5), material,
                       rot=Matrix.Rotation(-a + math.pi / 2, 4, "X")))
    return obs


RING = 0.09
add("Crank_F", *gear(BB_F, RING, 30, -0.026))
add("Crank_R", *gear(BB_R, RING, 30, -0.026), *gear(BB_R, 0.07, 24, 0.026))
for crank, pins in (("Crank_F", ("Pedal_FL", "Pedal_FR")), ("Crank_R", ("Pedal_RL", "Pedal_RR"))):
    c = bh(crank)
    obs = [cyl(c + V(0, 0, -0.05), c + V(0, 0, 0.05), 0.011, "brass", 12)]
    for pb in pins:
        p = bh(pb)
        sx = 1 if p.x > 0 else -1
        a0, a1 = Vector((sx * 0.04, c.y, c.z)), Vector((sx * 0.04, p.y, p.z))
        obs.append(box((a0 + a1) / 2, (0.012, 0.022, (a1 - a0).length + 0.02), "brass", 0.004))
        obs.append(cyl(Vector((sx * 0.034, p.y, p.z)), Vector((sx * 0.046, p.y, p.z)), 0.012, "brass", 12))
    add(crank, *obs)
for pb in ("Pedal_FL", "Pedal_FR", "Pedal_RL", "Pedal_RR"):
    p = bh(pb)
    pin = bh("PedalPin_" + pb.split("_")[1])
    c = Vector((p.x, p.y, pin.z - 0.012))
    obs = [box(c, (0.09, 0.05, 0.022), "dark", 0.004)]
    for sx in (-1, 1):
        obs.append(box(c + Vector((sx * 0.046, 0, 0)), (0.006, 0.054, 0.026), "brass", 0.002))
    for k in range(3):
        obs.append(sphere(c + Vector((-0.03 + 0.03 * k, -0.026, 0.004)), 0.0035, "brass", 6))
    add(pb, *obs)


def chain_loop(c0, r0, c1, r1, x, n=24):
    """Points round two sprockets along their outer tangents (in the YZ plane at x)."""
    d = c1 - c0
    ang = math.atan2(d.z, d.y)
    phi = math.acos(max(-1.0, min(1.0, (r0 - r1) / d.length)))
    pts = []
    for k in range(n + 1):                                   # round the far side of sprocket 0
        a = ang + phi + (2 * math.pi - 2 * phi) * k / n
        pts.append(Vector((x, c0.y + r0 * math.cos(a), c0.z + r0 * math.sin(a))))
    for k in range(n + 1):                                   # round the far side of sprocket 1
        a = ang - phi + 2 * phi * k / n
        pts.append(Vector((x, c1.y + r1 * math.cos(a), c1.z + r1 * math.sin(a))))
    return pts


def chain(c0, r0, c1, r1, x):
    pts = chain_loop(c0, r0, c1, r1, x)
    return tube(pts, 0.0045, "dark", tseg=4, closed=True)


add("Bike_root", chain(BB_F, RING + 0.004, BB_R, RING + 0.004, -0.026))
add("Bike_root", chain(BB_R, 0.074, HUB_R, 0.042, 0.026))
add("Wheel_R", *gear(HUB_R, 0.036, 16, 0.026))

# ------------------------------------------------------------------ steering (Steer): fork, steerer, stem, bars, grips, head lamp
st = []
crown = steer_pt(-0.01)
st.append(box(crown, (0.13, 0.04, 0.03), "brass", 0.008, rot=frame((0, 0, 0), STD)))
for sx in (1, -1):
    pts = bezier(crown + V(0, 0, sx * 0.05), steer_pt(-0.17) + V(0, 0, sx * 0.052), HUB_F + V(0.03, 0.06, sx * 0.055), 14,
                 HUB_F + V(0, 0, sx * 0.055))
    st.append(tube(pts, 0.014, "paint"))
    st.append(sphere(HUB_F + V(0, 0, sx * 0.055), 0.016, "brass", 10))
ST_TOP = steer_pt(0.29)
st.append(cyl(steer_pt(-0.01), ST_TOP, 0.016, "brass", 14))
for s in (0.23, 0.27):
    st.append(torus(steer_pt(s), 0.019, 0.004, "brass", axis=STD, seg=18, tseg=6))
STEM = V(-0.632, 0.975)
st.append(tube(bezier(ST_TOP, ST_TOP + STD * 0.04, STEM, 8), 0.016, "brass"))
st.append(sphere(STEM, 0.022, "brass", 12))
for g in ("Grip_C_L", "Grip_C_R"):
    gp = GRIP[g]
    sx = 1 if gp.x > 0 else -1
    g0 = gp + V(-0.05, 0)
    pts = bezier(STEM, STEM + V(-0.015, 0.02, sx * 0.08), g0 + V(-0.06, -0.005, 0), 14, g0)
    st.append(tube(pts, 0.012, "brass"))
    st.append(cyl(gp + V(-0.05, 0), gp + V(0.052, 0), 0.0175, "paint", 16))                   # grip (maroon, ribbed)
    for k in range(7):
        st.append(torus(gp + V(-0.042 + 0.014 * k, 0), 0.0178, 0.0022, "paint", axis=(0, 1, 0), seg=12, tseg=4))
    for yy in (-0.054, 0.056):
        st.append(cyl(gp + V(yy - 0.006, 0), gp + V(yy + 0.006, 0), 0.02, "brass", 16))
# head lamp
LC = V(-0.875, 0.8)
st.append(lathe([(0.0, 0.0), (0.0, 0.04), (0.03, 0.055), (0.11, 0.058), (0.13, 0.062), (0.14, 0.0)], LC + V(0.065, 0), (0, -1, 0), "paint"))
st.append(torus(LC + V(-0.07, 0), 0.06, 0.008, "brass", axis=(0, 1, 0), seg=28, tseg=8))
st.append(torus(LC + V(0.05, 0), 0.058, 0.006, "brass", axis=(0, 1, 0), seg=28, tseg=8))
st.append(lathe([(0.0, 0.052), (0.012, 0.035), (0.016, 0.0)], LC + V(-0.07, 0), (0, -1, 0), "lens"))
st.append(lathe([(0.0, 0.04), (0.06, 0.015), (0.07, 0.0)], LC + V(0.065, 0), (0, 1, 0), "brass"))
st.append(tube([LC + V(0.04, -0.05), steer_pt(0.12) + V(0, 0, 0)], 0.009, "brass"))
for sx in (1, -1):
    pts = [LC + V(-0.02 + 0.025 * math.cos(a), 0.012 * math.sin(2 * a), sx * 0.0585) for a in [k * 0.5 for k in range(13)]]
    st.append(tube(pts, 0.002, "brass", tseg=5))
add("Steer", *st)

# stoker bars (Bike_root): a post up from the top tube, bars back to the stoker grips
SPOST0 = V(0.105, 0.73)
SPOST1 = V(0.105, 0.955)
add("Bike_root", tube([SPOST0, SPOST1], 0.014, "brass"), sphere(SPOST1, 0.02, "brass", 12), name="goosefit_stoker_stem_cycle_0")
for g in ("Grip_S_L", "Grip_S_R"):
    gp = GRIP[g]
    sx = 1 if gp.x > 0 else -1
    g0 = gp + V(-0.05, 0)
    pts = bezier(SPOST1, SPOST1 + V(-0.02, 0.03, sx * 0.08), g0 + V(-0.06, -0.01, 0), 14, g0)
    obs = [tube(pts, 0.012, "brass"), cyl(gp + V(-0.05, 0), gp + V(0.052, 0), 0.0175, "paint", 16)]
    for k in range(7):
        obs.append(torus(gp + V(-0.042 + 0.014 * k, 0), 0.0178, 0.0022, "paint", axis=(0, 1, 0), seg=12, tseg=4))
    for yy in (-0.054, 0.056):
        obs.append(cyl(gp + V(yy - 0.006, 0), gp + V(yy + 0.006, 0), 0.02, "brass", 16))
    add("Bike_root", *obs, name="goosefit_stoker_stem_cycle_0")

# ------------------------------------------------------------------ rear: rack, fin with the goose, four rockets
RACK_Z = 0.72
RK_Y0, RK_Y1 = 0.70, 1.12
rk = [box(V((RK_Y0 + RK_Y1) / 2, RACK_Z), (0.34, RK_Y1 - RK_Y0, 0.012), "paint", 0.004)]
for sx in (1, -1):
    rk.append(tube([V(RK_Y0, RACK_Z + 0.008, sx * 0.17), V(RK_Y1, RACK_Z + 0.008, sx * 0.17)], 0.005, "brass"))
    rk.append(tube([V(RK_Y1 - 0.06, RACK_Z - 0.006, sx * 0.06), HUB_R + V(0, 0.0, sx * 0.064)], 0.008, "brass"))     # rack stays
    rk.append(tube([V(RK_Y0 + 0.02, RACK_Z - 0.006, sx * 0.03), S_TOP + V(0, -0.04, sx * 0.02)], 0.008, "brass"))
rk.append(tube([V(RK_Y0, RACK_Z + 0.008, 0.17), V(RK_Y0, RACK_Z + 0.008, -0.17)], 0.005, "brass"))
rk.append(tube([V(RK_Y1, RACK_Z + 0.008, 0.17), V(RK_Y1, RACK_Z + 0.008, -0.17)], 0.005, "brass"))
FIN = [(0.80, RACK_Z + 0.006), (0.92, RACK_Z + 0.05), (1.02, RACK_Z + 0.11), (1.10, RACK_Z + 0.16), (1.16, RACK_Z + 0.172),
       (1.13, RACK_Z + 0.12), (1.11, RACK_Z + 0.006)]
rk.append(flat_poly(FIN, 0.0, "paint", 0.012))
rk.append(tube([V(y, z) for y, z in FIN[:5]] + [V(*FIN[5])], 0.0045, "brass", tseg=6))


def goose_emblem(cy, cz, s, x):
    obs = []
    def ell(y0, z0, ry, rz, n=18):
        return [(y0 + ry * math.cos(2 * math.pi * k / n), z0 + rz * math.sin(2 * math.pi * k / n)) for k in range(n)]
    obs.append(flat_poly(ell(cy + 0.05 * s, cz + 0.1 * s, 0.42 * s, 0.22 * s), x, "brass"))                      # body
    obs.append(flat_poly([(cy - 0.24 * s, cz + 0.18 * s), (cy - 0.36 * s, cz + 0.62 * s), (cy - 0.24 * s, cz + 0.66 * s),
                          (cy - 0.1 * s, cz + 0.22 * s)], x, "brass"))                                           # neck
    obs.append(flat_poly(ell(cy - 0.3 * s, cz + 0.68 * s, 0.12 * s, 0.1 * s, 12), x, "brass"))                   # head
    obs.append(flat_poly([(cy - 0.4 * s, cz + 0.72 * s), (cy - 0.58 * s, cz + 0.66 * s), (cy - 0.4 * s, cz + 0.62 * s)], x, "brass"))
    obs.append(flat_poly([(cy + 0.3 * s, cz + 0.18 * s), (cy + 0.62 * s, cz + 0.36 * s), (cy + 0.42 * s, cz + 0.08 * s)], x, "brass"))
    obs.append(flat_poly([(cy + 0.0 * s, cz - 0.08 * s), (cy + 0.04 * s, cz - 0.3 * s), (cy + 0.14 * s, cz - 0.3 * s), (cy + 0.06 * s, cz - 0.08 * s)], x, "brass"))
    return obs


for sx in (1, -1):
    rk += goose_emblem(1.0, RACK_Z + 0.055, 0.075, sx * 0.0075)
add("Bike_root", *rk)

ENG = []                                            # (side, level) -> nozzle exit
R_ROCK, Y_NOSE, Y_BODY0, Y_BODY1 = 0.044, 0.66, 0.74, 1.04
for sx in (1, -1):
    for lv, zz in ((0, 0.655), (1, 0.548)):
        x = sx * 0.135
        c0, c1 = V(Y_BODY0, zz, x), V(Y_BODY1, zz, x)
        ro = [cyl(c0, c1, R_ROCK, "paint", 24)]
        ro.append(lathe([(0, R_ROCK), (0.03, R_ROCK * 0.9), (0.06, R_ROCK * 0.55), (0.08, 0.008), (0.083, 0.0)], c0, (0, -1, 0), "brass", 24))
        for yy in (0.76, 0.85, 0.95, 1.02):
            ro.append(torus(V(yy, zz, x), R_ROCK + 0.002, 0.005, "brass", axis=(0, 1, 0), seg=20, tseg=4))
        for k in range(6):                                                   # rivet rows
            a = 2 * math.pi * k / 6
            ro.append(sphere(V(0.85, zz + (R_ROCK + 0.004) * math.sin(a), x + (R_ROCK + 0.004) * math.cos(a)), 0.0035, "brass", 6))
        ro.append(lathe([(0, R_ROCK * 0.92), (0.03, R_ROCK * 0.82), (0.05, R_ROCK * 1.05), (0.055, R_ROCK * 1.12), (0.056, 0.0)],
                        c1, (0, 1, 0), "brass", 24))                          # nozzle bell
        ro.append(cyl(V(Y_BODY1 + 0.05, zz, x), V(Y_BODY1 + 0.0535, zz, x), R_ROCK * 0.95, "dark", 24))
        ro.append(cyl(V(Y_BODY1 + 0.0535, zz, x), V(Y_BODY1 + 0.0545, zz, x), R_ROCK * 0.6, "glass", 20))
        # gold flourish (a thin brass wave) along the body, outward side
        pts = [V(0.79 + 0.2 * t, zz + 0.012 * math.sin(t * math.pi * 3), x + sx * (R_ROCK + 0.0005)) for t in [k / 30 for k in range(31)]]
        ro.append(tube(pts, 0.002, "brass", tseg=5))
        # clamps to the rack / to the upper rocket, brass straps
        if lv == 0:
            ro.append(box(V(0.8, (zz + RACK_Z) / 2, x), (0.014, 0.02, RACK_Z - zz), "brass", 0.003))
            ro.append(box(V(1.0, (zz + RACK_Z) / 2, x), (0.014, 0.02, RACK_Z - zz), "brass", 0.003))
        else:
            ro.append(box(V(0.8, zz + 0.0535, x), (0.014, 0.02, 0.025), "brass", 0.003))
            ro.append(box(V(1.0, zz + 0.0535, x), (0.014, 0.02, 0.025), "brass", 0.003))
            ro.append(tube([V(0.9, zz, x - sx * R_ROCK), HUB_R + V(0, 0, sx * 0.064)], 0.006, "brass"))
        add("Bike_root", *ro)
        ENG.append((sx, lv, V(Y_BODY1 + 0.056, zz, x)))

# ------------------------------------------------------------------ effect bones + their meshes
POP_STRETCH, POP_TUCK, POP_W = 20.0, 0.02, 2.0    # orange pop rest shape: 1/20 long, tucked inside the bell (hidden at rest)
bpy.context.view_layer.objects.active = RIG
RIG.select_set(True)
bpy.ops.object.mode_set(mode="EDIT")
EB = RIG.data.edit_bones
root_eb = EB["Bike_root"]
FX_BONES = []


def new_bone(name, head, tail):
    b = EB.new(name)
    b.head, b.tail = Vector(head), Vector(tail)
    b.parent = root_eb
    b.use_deform = False
    FX_BONES.append(name)


for sx, side in ((1, "L"), (-1, "R")):
    hc = CLK + V(0, 0, sx * 0.026)
    new_bone(f"ClockM_{side}", hc, hc + V(0, 0, sx * 0.03))
    new_bone(f"ClockH_{side}", hc, hc + V(0, 0, sx * 0.03))
for i, (sx, lv, p) in enumerate(ENG):
    new_bone(f"FlameB_{i}", p, p + V(0.1, 0))
    new_bone(f"FlameO_{i}", p - V(POP_TUCK, 0), p - V(POP_TUCK, 0) + V(0.1, 0))   # (at the tucked rest shape: it grows out of the bell)
bpy.ops.object.mode_set(mode="OBJECT")
BONE = {b.name: b for b in RIG.data.bones}

for sx, side in ((1, "L"), (-1, "R")):
    hc = CLK + V(0, 0, sx * 0.026)
    # hands drawn pointing at 12 (+Z); rotation about the bone's Y (through the dial) sweeps them round
    add(f"ClockM_{side}", box(hc + V(0, CLK_R * 0.4), (0.002, 0.006, CLK_R * 0.82), "dark"),
        lathe([(0, 0.0), (0.0, 0.007), (0.004, 0.0)], hc + V(0, 0, sx * 0.001), (sx, 0, 0), "brass", 12))
    add(f"ClockH_{side}", box(hc + V(0, CLK_R * 0.26, sx * -0.0015), (0.002, 0.01, CLK_R * 0.55), "dark"))


def flame(p, L, R, mats, seg=16):
    """Flame along +Y from the nozzle exit: an outer cone and a hot inner core."""
    outer = lathe([(0, R * 0.95), (L * 0.12, R), (L * 0.45, R * 0.72), (L * 0.8, R * 0.3), (L, 0.0)], p, (0, 1, 0), mats[0], seg)
    inner = lathe([(0, R * 0.55), (L * 0.1, R * 0.55), (L * 0.4, R * 0.35), (L * 0.62, 0.0)], p + V(0.002, 0), (0, 1, 0), mats[1], seg)
    return [outer, inner]


for i, (sx, lv, p) in enumerate(ENG):
    halo = lathe([(0, 0.044), (0.04, 0.052), (0.14, 0.04), (0.26, 0.016), (0.32, 0.0)], p - V(0.004, 0), (0, 1, 0), "flame_halo", 16)
    add(f"FlameB_{i}", *flame(p, 0.27, 0.036, ("flame_b", "flame_core")), halo)
    add(f"FlameO_{i}", *flame(p - V(POP_TUCK, 0), 0.36 / POP_STRETCH, 0.064 / POP_W, ("flame_r", "flame_o")))


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


if "--debug-tris" in argv:
    from collections import Counter
    cnt = Counter()
    for o in PARTS[("Bike_root", None)]:
        cnt[o.name.split(".")[0]] += sum(len(p.vertices) - 2 for p in o.data.polygons)
    print("BYKIND", cnt.most_common(12))
TRIS = {}
FINAL = []
for (bone, part), obs in PARTS.items():
    o = join_into(obs, part or f"TW_{bone}")
    b = BONE[bone]
    pm = RIG.matrix_world @ b.matrix_local @ Matrix.Translation((0, b.length, 0))
    o.parent = RIG
    o.parent_type = "BONE"
    o.parent_bone = bone
    o.matrix_parent_inverse = pm.inverted()
    TRIS[part or bone] = sum(len(p.vertices) - 2 for p in o.data.polygons)
    FINAL.append(o)
print("TRIS", sum(TRIS.values()), TRIS)

# ------------------------------------------------------------------ the TimeWarpFX clip
FPS = SC.render.fps
NF = 4 * FPS
rnd = random.Random(611)
act = bpy.data.actions.new("TimeWarpFX")
RIG.animation_data_create()
RIG.animation_data.action = act
for name in FX_BONES:
    pb = RIG.pose.bones[name]
    pb.rotation_mode = "QUATERNION"
for f in range(NF + 1):
    t = f / NF
    for side in ("L", "R"):
        for name, turns in ((f"ClockM_{side}", 8), (f"ClockH_{side}", 1)):
            pb = RIG.pose.bones[name]
            pb.rotation_quaternion = Matrix.Rotation(-2 * math.pi * turns * t, 4, "Y").to_quaternion()
            pb.keyframe_insert("rotation_quaternion", frame=f)
pops = {}
for i in range(len(ENG)):
    base = rnd.random() * 0.5
    pops[i] = sorted(((base + 0.5 * k + rnd.uniform(-0.12, 0.12)) % 1.0) for k in range(2))
flick = {i: [(1 + rnd.uniform(-0.22, 0.25), 1 + rnd.uniform(-0.1, 0.1)) for _ in range(NF // 2)] for i in range(len(ENG))}
for i in range(len(ENG)):
    fl = flick[i] + [flick[i][0]]
    for k, (ly, lw) in enumerate(fl):
        pb = RIG.pose.bones[f"FlameB_{i}"]
        pb.scale = (lw, ly, lw)
        pb.keyframe_insert("scale", frame=k * 2)
    pb = RIG.pose.bones[f"FlameO_{i}"]
    keys = {0: 0.0, NF: 0.0}
    for tp in pops[i]:
        f0 = int(tp * NF)
        for df, s in ((-1, 0.0), (0, 0.4), (2, 1.25), (4, 1.0), (6, 0.6), (9, 0.0)):
            keys[(f0 + df) % (NF + 1)] = s
    for f, s in sorted(keys.items()):
        # s = 0: the rest shape (tucked in the bell); s > 0: stretched out to s x full length, swelling a little
        pb.scale = (1 + (POP_W * 1.1 - 1) * min(s, 1.0) + 0.2 * max(0.0, s - 1.0), 1 + (POP_STRETCH - 1) * s,
                    1 + (POP_W * 1.1 - 1) * min(s, 1.0) + 0.2 * max(0.0, s - 1.0))
        pb.keyframe_insert("scale", frame=f)
for fc in act.fcurves if hasattr(act, "fcurves") else []:
    for kp in fc.keyframe_points:
        kp.interpolation = "LINEAR"
try:                                                   # Blender 5 layered actions
    for layer in act.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                for fc in cb.fcurves:
                    for kp in fc.keyframe_points:
                        kp.interpolation = "LINEAR"
except AttributeError:
    pass
RIG.animation_data.action = None
tr = RIG.animation_data.nla_tracks.new()
tr.name = "TimeWarpFX"
tr.strips.new("TimeWarpFX", 0, act)
for b in FX_BONES:
    pb = RIG.pose.bones[b]
    pb.rotation_quaternion = (1, 0, 0, 0)
    pb.scale = (1, 1, 1)

# ------------------------------------------------------------------ export
bpy.ops.object.select_all(action="DESELECT")
RIG.select_set(True)
for o in FINAL:
    o.select_set(True)
glb = OUT / "time_warp_tandem.glb"
bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True, export_animations=True,
                          export_animation_mode="NLA_TRACKS", export_yup=True, export_def_bones=False, export_tangents=False)
info = {"glb": str(glb.relative_to(ROOT)), "tris": TRIS, "tris_total": sum(TRIS.values()), "engines": len(ENG),
        "clips": ["Pedal", "WheelSpin", "TimeWarpFX"], "fx_bones": FX_BONES, "clock": {"minute_turns_per_s": 2, "hour_turns_per_s": 0.25},
        "orange_pops": {f"FlameO_{i}": [round(t * 4, 2) for t in pops[i]] for i in pops}, "base_rig": str(BASE)}
(OUT / "time_warp_tandem_info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "time_warp_tandem.blend"))
print("EXPORT", glb, round(glb.stat().st_size / 1e6, 2), "MB")

# ------------------------------------------------------------------ review sheet
if "--sheet" in argv:
    for o in bpy.data.objects:
        if o.type == "CAMERA":
            bpy.data.objects.remove(o, do_unlink=True)
    SC.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE_NEXT"
    SC.render.resolution_x, SC.render.resolution_y = 1600, 900
    SC.render.film_transparent = False
    w = bpy.data.worlds.new("w") if not SC.world else SC.world
    SC.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0.85, 0.85, 0.87, 1)
    bg.inputs[1].default_value = 0.55
    SC.view_settings.view_transform = "AgX"
    for nm, rot, en in (("key", (50, 0, 120), 2.2), ("fill", (60, 0, -60), 0.7), ("rim", (20, 0, 180), 1.0)):
        ld = bpy.data.lights.new(nm, "SUN")
        ld.energy = en
        lo = bpy.data.objects.new(nm, ld)
        lo.rotation_euler = [math.radians(a) for a in rot]
        COL.objects.link(lo)
    fl = bpy.data.meshes.new("floor")
    bmf = bmesh.new()
    bmesh.ops.create_grid(bmf, x_segments=1, y_segments=1, size=6)
    bmf.to_mesh(fl)
    flo = bpy.data.objects.new("floor", fl)
    fm = mat("floor", (0.8, 0.8, 0.82), 0, 0.8)
    fl.materials.append(fm)
    COL.objects.link(flo)
    cd = bpy.data.cameras.new("cam")
    cam = bpy.data.objects.new("cam", cd)
    COL.objects.link(cam)
    SC.camera = cam
    SC.frame_set(0)
    views = {"side": ((3.6, 0.15, 0.62), (0, 0.15, 0.55), 30), "q34": ((2.3, -2.2, 1.25), (0, 0.1, 0.5), 32),
             "rear_q34": ((1.9, 2.6, 1.2), (0, 0.55, 0.55), 32), "clock": ((0.9, 0.19, 0.7), (0, 0.19, 0.6), 30),
             "engines": ((1.0, 1.75, 0.95), (0.0, 0.95, 0.62), 32), "rear": ((0.0, 3.3, 0.8), (0, 0.9, 0.62), 22)}
    frames_for = {"engines": None}
    for nm, (eye, tgt, lens) in views.items():
        cam.location = Vector(eye)
        cam.rotation_euler = (Vector(tgt) - Vector(eye)).to_track_quat("-Z", "Y").to_euler()
        cd.lens = lens * (1.0 if nm not in ("clock",) else 1.6)
        # pose the effects mid-pop for the engine shots: every orange flame at its peak, as a still
        if nm in ("engines", "rear", "rear_q34"):
            RIG.animation_data.action = act
            SC.frame_set(int(pops[0][0] * NF) + 2)
        else:
            RIG.animation_data.action = None
        SC.render.filepath = str(REN / f"tw_{nm}.png")
        bpy.ops.render.render(write_still=True)
        print("RENDER", SC.render.filepath)
