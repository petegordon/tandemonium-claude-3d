"""Penny-Farthing tandem (Time Warp bike, Tandemonium #611), built in code from the approved refs (refs/pf_tandem).

  blender -b --factory-startup --python scripts/make_pf_tandem.py -- [--sheet] [--wheel-r 0.36] [--out out/pf_tandem/pf_tandem.glb]

Two penny-farthings back to back, riders facing away from each other, joined by one straight black-and-gold cross bar
with a goose medallion at mid backbone height. Each half: big wheel with a gold fender, hub crank (direct drive: the
pedals turn with the wheel), raked fork, moustache bars with wooden grips and a bell, sprung leather saddle on the
curved backbone, and a small wheel tucked in at the middle.

Rider fit (contact points from the geese, the look scaled to them): each goose's own Ride/Pedal numbers fix the hub
under the hip (CRANK_FWD ahead, CRANK_DOWN below, CRANK_R arm), the saddle under the hip (HIP_UP) and the grips
(<goose>_clips.json ride_grip). With hub cranks the hub height IS the wheel radius, so the big wheel follows from the
legs: ~0.72 m (28 in). The Image-to-3D passes (out/pf_tandem/mesh) are the look reference, not geometry.

Halves: the captain's half is at the front (-Y in Blender, +Z in glTF) and faces forward; the stoker's half is the
same half turned 180 deg about the vertical, so she faces backwards. Rolling forward turns every wheel the same way,
so the stoker's pedals turn backwards for her (play Pedal_Stoker reversed) - a design question for Pete.

Nodes (glTF +Y up, +Z forward, metres, origin = ground centre):
  Frame                      backbones, cross bar + medallion, saddles, small-wheel forks
    Steer_F / Steer_R        fork, fender, bars, bell; local +Y (glTF) = that half's steer axis
      Wheel_F / Wheel_R      big wheel, rotates about local +X
      Crank_F / Crank_R      hub crank + pedals, rotates about local +X with its wheel
    Wheel_SF / Wheel_SR      small wheels, rotate about local +X (R / r times faster)
    Seat_Captain             goose rig origin, identity rotation
    Seat_Stoker              goose rig origin, turned 180 deg about +Y
Clip "Ride": one big-wheel turn in 1.0 s (the geese's Pedal clips are one crank turn in 1.0 s), rolling forward,
rider-left pedal at the top at t = 0 for both riders.
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / "pf_tandem"
OUT.mkdir(parents=True, exist_ok=True)
OUT_GLB = Path(argv[argv.index("--out") + 1]) if "--out" in argv else OUT / "pf_tandem.glb"
SHEET = "--sheet" in argv
FPS = 24
GEESE = ROOT / "out" / "sandquest"


def arg(name, default):
    return float(argv[argv.index(name) + 1]) if name in argv else default


def goose_meta(name):
    p = GEESE / f"{name}_clips.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def bl(v):                                              # three.js (x, y, z) -> Blender (x, -z, y)
    return Vector((v[0], -v[2], v[1]))


# ---- the geese's contact numbers (same as make_watercycle.py) --------------------------------------------------------
HIP_UP = 0.11
CRANK_FWD, CRANK_DOWN = 0.197 - 0.004, 0.78 - 0.262
CRANK_R = 0.162
meta = {"Captain": goose_meta("winston"), "Stoker": goose_meta("victoria")}
hip_mid = {s: bl(m["hip_mid_rest"]) if m else Vector((0, 0.0247, 0.8135)) for s, m in meta.items()}
grip = {s: {k: bl(v) for k, v in m["ride_grip"].items()} if m else
        {"Left": Vector((0.19, -0.44, 0.94)), "Right": Vector((-0.19, -0.44, 0.94))} for s, m in meta.items()}

# ---- layout, in "half" coordinates: x = that rider's left, f = forward from the bike centre, z up -------------------
R = arg("--wheel-r", 0.36)                  # big wheel (to the tyre's outside)
D = 2 * R
HUB_F = arg("--hub-f", 0.885 * D)           # art: hubs 1.77 wheel diameters apart
SR = arg("--small-r", 0.12 * D)             # art: small wheel ~0.24 D across
SMALL_F = 0.27 * D                          # art: small hubs ~0.54 D apart
TYRE_R = 0.022                              # tyre section radius (solid rubber, fat as in the art)
BB_R = R + 0.045                            # backbone arc radius about the hub
TUBE = 0.019
BAR_Z = arg("--bar-z", 0.65 * D)            # cross bar height (art: mid backbone)

BLACK = (0.02, 0.02, 0.025, 1)
RUBBER = (0.03, 0.03, 0.03, 1)
LEATHER = (0.36, 0.17, 0.07, 1)
LEATHER_D = (0.22, 0.09, 0.04, 1)
WOOD = (0.36, 0.14, 0.06, 1)
WOOD_D = (0.20, 0.07, 0.03, 1)
GOLD = (0.90, 0.58, 0.18, 1)


def half_points(s):
    """The fixed points of one half (s = +1 captain, -1 stoker), in half coordinates (x, f, z)."""
    seat = "Captain" if s > 0 else "Stoker"
    hub = Vector((0, HUB_F, R))
    hip = hub + Vector((0, -CRANK_FWD, CRANK_DOWN))
    hm = hip_mid[seat]                                 # Blender, forward = -Y
    origin = Vector((0, hip.y - (-hm.y), hip.z - hm.z))  # rig origin: hm.y > 0 means the hip is behind the origin
    saddle = Vector((0, hip.y, hip.z - HIP_UP))
    g = {k: Vector((v.x, origin.y - v.y, origin.z + v.z)) for k, v in grip[seat].items()}   # -v.y = forward
    gz = sum(v.z for v in g.values()) / 2
    head = Vector((0, HUB_F - 0.03, gz - 0.11))        # fork top: a tall fork, so the bars sit just over the saddle
    return dict(seat=seat, hub=hub, hip=hip, origin=origin, saddle=saddle, grip=g, head=head)


def W(s, p):
    """half coordinates -> Blender world: captain f forward = -Y; stoker = turned 180 deg about Z."""
    p = Vector(p)
    return Vector((s * p.x, -s * p.y, p.z))


class Part:
    def __init__(self, name):
        self.name, self.v, self.f, self.c, self.m = name, [], [], [], []

    def add(self, verts, faces, color, mat=0):
        n = len(self.v)
        self.v += [Vector(x) for x in verts]
        self.f += [[i + n for i in face] for face in faces]
        self.c += [color] * len(faces)
        self.m += [mat] * len(faces)

    def box(self, center, size, color, mat=0, rot=None):
        c = Vector(center)
        sx, sy, sz = (q / 2 for q in size)
        vs = [Vector((x, y, z)) for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)]
        if rot is not None:
            vs = [rot @ v for v in vs]
        fs = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
        self.add([v + c for v in vs], fs, color, mat)

    def cyl(self, a, b, r, color, mat=0, n=6, caps=True, r2=None):
        a, b = Vector(a), Vector(b)
        r2 = r if r2 is None else r2
        axis = (b - a).normalized()
        u = axis.cross(Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))).normalized()
        w = axis.cross(u)
        ring = [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)) for i in range(n)]
        vs = [a + (u * c + w * q) * r for c, q in ring] + [b + (u * c + w * q) * r2 for c, q in ring]
        fs = [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
        if caps:
            fs.append(list(range(n))[::-1])
            fs.append([n + i for i in range(n)])
        self.add(vs, fs, color, mat)

    def tube(self, pts, r=TUBE, color=BLACK, mat=0, n=8):
        pts = [Vector(p) for p in pts]
        for a, b in zip(pts, pts[1:]):
            self.cyl(a, b, r, color, mat, n, caps=False)
        for p in (pts[0], pts[-1]):
            self.sphere(p, r, color, mat, n=n)
        for p in pts[1:-1]:
            self.sphere(p, r, color, mat, n=n)

    def sphere(self, c, r, color, mat=0, n=8, squash=(1, 1, 1)):
        c = Vector(c)
        rings = max(3, n // 2)
        vs = []
        for i in range(1, rings):
            phi = math.pi * i / rings
            for j in range(n):
                t = 2 * math.pi * j / n
                vs.append(c + Vector((math.sin(phi) * math.cos(t) * squash[0], math.sin(phi) * math.sin(t) * squash[1],
                                      math.cos(phi) * squash[2])) * r)
        top, bot = len(vs), len(vs) + 1
        vs += [c + Vector((0, 0, r * squash[2])), c - Vector((0, 0, r * squash[2]))]
        fs = []
        for i in range(rings - 2):
            for j in range(n):
                fs.append([i * n + j, i * n + (j + 1) % n, (i + 1) * n + (j + 1) % n, (i + 1) * n + j])
        for j in range(n):
            fs.append([top, (j + 1) % n, j])
            fs.append([bot, (rings - 2) * n + j, (rings - 2) * n + (j + 1) % n])
        self.add(vs, fs, color, mat)

    def torus_x(self, c, rmaj, rmin, color, mat=0, nmaj=48, nmin=6, arc=(0, 2 * math.pi), flat=1.0):
        """Ring in the YZ plane about the X axis through c. arc = (a0, a1) angles (0 = +Z top, + = toward +Y)."""
        c = Vector(c)
        full = abs(arc[1] - arc[0] - 2 * math.pi) < 1e-6
        segs = nmaj if full else max(2, int(nmaj * (arc[1] - arc[0]) / (2 * math.pi)))
        cnt = segs if full else segs + 1
        vs = []
        for i in range(cnt):
            t = arc[0] + (arc[1] - arc[0]) * i / segs
            radial = Vector((0, math.sin(t), math.cos(t)))
            for j in range(nmin):
                q = 2 * math.pi * j / nmin
                vs.append(c + radial * (rmaj + rmin * math.cos(q)) + Vector((rmin * flat * math.sin(q), 0, 0)))
        fs = []
        for i in range(segs):
            i2 = (i + 1) % cnt
            for j in range(nmin):
                fs.append([i * nmin + j, i2 * nmin + j, i2 * nmin + (j + 1) % nmin, i * nmin + (j + 1) % nmin])
        if not full:
            fs.append([j for j in range(nmin)][::-1])
            fs.append([(cnt - 1) * nmin + j for j in range(nmin)])
        self.add(vs, fs, color, mat)

    def build(self, origin=(0, 0, 0)):
        me = bpy.data.meshes.new(self.name)
        o = Vector(origin)
        me.from_pydata([v - o for v in self.v], [], self.f)
        me.update()
        me.materials.append(PAINT)
        me.materials.append(GOLDM)
        col = me.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
        for p, c, mi in zip(me.polygons, self.c, self.m):
            p.material_index = mi
            p.use_smooth = True
            for li in p.loop_indices:
                col.data[li].color = c if mi == 0 else (1, 1, 1, 1)
        me.shade_smooth_by_angle(angle=math.radians(40)) if hasattr(me, "shade_smooth_by_angle") else None
        ob = bpy.data.objects.new(self.name, me)
        ob.location = o
        bpy.context.scene.collection.objects.link(ob)
        return ob


bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.fps = FPS
PAINT = bpy.data.materials.new("pf_paint")
PAINT.use_nodes = True
bsdf = PAINT.node_tree.nodes["Principled BSDF"]
bsdf.inputs["Roughness"].default_value = 0.3
ca = PAINT.node_tree.nodes.new("ShaderNodeVertexColor")
ca.layer_name = "Col"
PAINT.node_tree.links.new(ca.outputs["Color"], bsdf.inputs["Base Color"])
GOLDM = bpy.data.materials.new("pf_gold")
GOLDM.use_nodes = True
b2 = GOLDM.node_tree.nodes["Principled BSDF"]
b2.inputs["Base Color"].default_value = GOLD
b2.inputs["Metallic"].default_value = 1.0
b2.inputs["Roughness"].default_value = 0.28


def parent_keep(child, parent):
    bpy.context.view_layer.update()                    # new objects' matrix_world is stale until an update
    mw = child.matrix_world.copy()
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()
    child.matrix_world = mw


frame = Part("Frame")
nodes, info_half = {}, {}

for s, tag in ((1, "F"), (-1, "R")):
    P = half_points(s)
    hub, head, saddle = P["hub"], P["head"], P["saddle"]
    w = lambda p: W(s, p)                                          # noqa: E731

    # -- backbone: from behind the head, arcing round the back of the big wheel, down to the small wheel's fork ------
    def arc_pt(theta, r=BB_R):                                     # theta from the top, + = toward the bike centre
        return hub + Vector((0, -math.sin(theta) * r, math.cos(theta) * r))
    neck = Vector((0, head.y - 0.06, head.z - 0.05))
    th0 = math.atan2(-(neck.y - hub.y), neck.z - hub.z)
    pts = [neck] + [arc_pt(th0 + (math.radians(100) - th0) * i / 9) for i in range(1, 10)]
    small_hub = Vector((0, SMALL_F, SR))
    small_top = Vector((0, SMALL_F + 0.005, SR + 0.11))
    pts.append(small_top)
    frame.tube([w(p) for p in pts], r=TUBE * 1.1, n=8)
    frame.cyl(w(neck), w(head + Vector((0, -0.005, 0.005))), TUBE * 1.0, BLACK, n=8)  # neck to the head bearing
    frame.cyl(w(small_top + Vector((0, 0, 0.012))), w(small_top - Vector((0, 0, 0.012))), TUBE * 1.5, GOLD, 1, n=8)
    for sx in (-1, 1):                                             # small-wheel fork
        frame.cyl(w(small_top + Vector((sx * 0.012, 0, -0.01))), w(small_hub + Vector((sx * 0.03, 0, 0))), 0.008, BLACK, n=6)
    # gold collars along the backbone (the art's gold bands)
    for th in (math.radians(55), math.radians(88)):
        a = arc_pt(th - 0.03)
        b = arc_pt(th + 0.03)
        frame.cyl(w(a), w(b), TUBE * 1.35, GOLD, 1, n=8)

    # -- saddle on two coil springs + a front leaf, on a clip to the backbone ---------------------------------------
    # find the backbone point under the saddle
    th_s = math.asin(max(-1, min(1, (hub.y - saddle.y) / BB_R)))
    under = arc_pt(th_s)
    sz = saddle.z - 0.03
    frame.box(w((0, saddle.y + 0.035, sz)), (0.20, 0.13, 0.045), LEATHER)          # broad back
    frame.box(w((0, saddle.y - 0.07, sz + 0.002)), (0.08, 0.14, 0.035), LEATHER)    # nose
    frame.box(w((0, saddle.y + 0.035, sz - 0.03)), (0.19, 0.12, 0.012), LEATHER_D)  # skirt/frame
    for sx in (-1, 1):
        base = Vector((sx * 0.055, saddle.y + 0.07, under.z + 0.005))
        top = Vector((sx * 0.055, saddle.y + 0.07, sz - 0.035))
        turns, rad = 4, 0.016
        coil = [base + (top - base) * (i / (turns * 8)) + Vector((rad * math.cos(i * math.pi / 4), rad * math.sin(i * math.pi / 4), 0))
                for i in range(turns * 8 + 1)]
        for a, b in zip(coil, coil[1:]):
            frame.cyl(w(a), w(b), 0.0035, GOLD, 1, n=4, caps=False)
        frame.cyl(w((sx * 0.055, saddle.y + 0.07, under.z)), w((0, under.y, under.z)), 0.006, GOLD, 1, n=6)
    frame.cyl(w((0, saddle.y - 0.11, sz - 0.01)), w(under + Vector((0, -0.02, 0.01))), 0.006, GOLD, 1, n=6)
    frame.box(w(under + Vector((0, 0.01, 0.012))), (0.05, 0.06, 0.02), GOLD, 1)        # saddle clip

    # -- steer group: fork, fender, bars, bell -----------------------------------------------------------------------
    st = Part(f"Steer_{tag}")
    for sx in (-1, 1):
        st.cyl(w(head + Vector((sx * 0.03, 0, -0.03))), w(hub + Vector((sx * 0.055, 0, 0))), 0.011, BLACK, n=8,
               r2=0.008)
        st.sphere(w(hub + Vector((sx * 0.055, 0, 0))), 0.014, BLACK, n=8)
    st.box(w(head + Vector((0, 0, -0.03))), (0.075, 0.035, 0.03), BLACK)              # fork crown
    st.cyl(w(head + Vector((0, 0, -0.02))), w(head + Vector((0, 0, 0.05))), 0.022, GOLD, 1, n=10)   # head bearing
    # fender: gold strip over the front-top of the wheel
    st.torus_x(w(hub) if s > 0 else w(hub), R + 0.018, 0.026, GOLD, 1, nmaj=40, nmin=4, flat=0.35,
               arc=(math.radians(-55), math.radians(5)) if s > 0 else (math.radians(-5), math.radians(55)))
    # bars: stem up and forward from the head, then moustache bars out to the Ride-pose grips
    gl, gr = P["grip"]["Left"], P["grip"]["Right"]
    gy, gz = (gl.y + gr.y) / 2, (gl.z + gr.z) / 2
    stem_top = Vector((0, head.y + 0.07, head.z + 0.085))   # short gooseneck forward
    st.cyl(w(head + Vector((0, 0, 0.04))), w(stem_top), 0.015, GOLD, 1, n=8)
    st.sphere(w(stem_top), 0.024, GOLD, 1, n=10)                                   # the art's gold knob
    for g in (gl, gr):
        sx = 1 if g.x > 0 else -1
        bend = Vector((g.x * 0.40, (stem_top.y + gy) / 2, stem_top.z + 0.01))
        inner = Vector((g.x * 0.82, gy - 0.02, gz + 0.005))
        st.tube([w(stem_top), w(bend), w(inner)], r=0.011, color=GOLD, mat=1, n=8)
        # grip: wooden, ridged, running outward and back from the bar end
        a = inner
        b = Vector((g.x * 1.18, gy + 0.05, gz - 0.01))
        segs = 5
        for i in range(segs):
            p0 = a + (b - a) * (i / segs)
            p1 = a + (b - a) * ((i + 0.55) / segs)
            p2 = a + (b - a) * ((i + 1) / segs)
            st.cyl(w(p0), w(p1), 0.019, WOOD, n=8, caps=(i == 0))
            st.cyl(w(p1), w(p2), 0.0165, WOOD_D, n=8, caps=(i == segs - 1))
        st.sphere(w(b), 0.017, WOOD, n=8)
    # bell, on the left bar
    bell_at = Vector((gl.x * 0.40, (stem_top.y + gy) / 2, stem_top.z + 0.01))   # on the left bar's bend
    st.cyl(w(bell_at), w(bell_at + Vector((0, 0, 0.02))), 0.005, GOLD, 1, n=6)
    st.sphere(w(bell_at + Vector((0, 0, 0.035))), 0.024, GOLD, 1, n=10, squash=(1, 1, 0.75))
    steer_axis = (head - hub).normalized()
    steer = st.build(origin=w(head))
    # tilt the steer node so its local Z (glTF +Y) runs along the steer axis
    ax_world = W(s, steer_axis) - W(s, Vector((0, 0, 0)))
    tilt = Vector((0, 0, 1)).rotation_difference(ax_world).to_matrix().to_4x4()
    mw = Matrix.Translation(w(head)) @ tilt
    me = steer.data
    me.transform(tilt.inverted())
    steer.matrix_world = mw
    nodes[f"Steer_{tag}"] = steer

    # -- big wheel ---------------------------------------------------------------------------------------------------
    wh = Part(f"Wheel_{tag}")
    hc = w(hub)
    wh.torus_x(hc, R - TYRE_R, TYRE_R, RUBBER, nmaj=56, nmin=6)                      # solid rubber tyre
    wh.torus_x(hc, R - 2 * TYRE_R - 0.004, 0.009, GOLD, 1, nmaj=56, nmin=4, flat=1.6)  # gold rim
    wh.cyl(hc + Vector((-0.05, 0, 0)), hc + Vector((0.05, 0, 0)), 0.018, GOLD, 1, n=10)  # hub barrel
    for sx in (-1, 1):
        wh.cyl(hc + Vector((sx * 0.032, 0, 0)), hc + Vector((sx * 0.038, 0, 0)), 0.042, GOLD, 1, n=12)  # flanges
    NSPOKE = 36
    rim_r = R - 2 * TYRE_R - 0.01
    for i in range(NSPOKE):
        t = 2 * math.pi * i / NSPOKE
        sx = 1 if i % 2 else -1
        a = hc + Vector((sx * 0.035, math.sin(t + 0.04 * sx) * 0.038, math.cos(t + 0.04 * sx) * 0.038))
        b = hc + Vector((sx * 0.004, math.sin(t) * rim_r, math.cos(t) * rim_r))
        wh.cyl(a, b, 0.0028, GOLD, 1, n=4, caps=False)
    wheel = wh.build(origin=hc)
    nodes[f"Wheel_{tag}"] = wheel

    # -- hub crank + pedals (rider-left pedal at the top at rest) --------------------------------------------------------
    cr = Part(f"Crank_{tag}")
    PIN_X = 0.075
    for sx_half, top in ((1, True), (-1, False)):                 # sx_half = that rider's left (+) / right (-)
        z = CRANK_R if top else -CRANK_R
        base = Vector((sx_half * PIN_X, HUB_F, R))
        tip = Vector((sx_half * PIN_X, HUB_F, R + z))
        cr.cyl(w(base), w(tip), 0.011, GOLD, 1, n=6, r2=0.008)
        cr.sphere(w(base), 0.017, GOLD, 1, n=8)
        pin_o = tip + Vector((sx_half * 0.06, 0, 0))
        cr.cyl(w(tip), w(pin_o), 0.006, GOLD, 1, n=6)
        pc = tip + Vector((sx_half * 0.035, 0, 0))
        cr.box(w(pc), (0.055, 0.075, 0.018), BLACK)               # rubber block pedal
        cr.box(w(pc + Vector((0, 0, 0.0095))), (0.03, 0.05, 0.002), GOLD, 1)
    crank = cr.build(origin=hc)
    nodes[f"Crank_{tag}"] = crank

    # -- small wheel -------------------------------------------------------------------------------------------------
    sw = Part(f"Wheel_S{tag}")
    shc = w(small_hub)
    sw.torus_x(shc, SR - 0.014, 0.014, RUBBER, nmaj=28, nmin=6)
    sw.torus_x(shc, SR - 0.030, 0.006, GOLD, 1, nmaj=28, nmin=4, flat=1.5)
    sw.cyl(shc + Vector((-0.03, 0, 0)), shc + Vector((0.03, 0, 0)), 0.012, GOLD, 1, n=8)
    for i in range(12):
        t = 2 * math.pi * i / 12
        sw.cyl(shc, shc + Vector((0, math.sin(t) * (SR - 0.03), math.cos(t) * (SR - 0.03))), 0.0025, GOLD, 1, n=4,
               caps=False)
    nodes[f"Wheel_S{tag}"] = sw.build(origin=shc)

    info_half[P["seat"]] = P | {"small_hub": small_hub, "steer_axis": steer_axis}

# ---- the straight cross bar between the backbones, with the goose medallion ------------------------------------------
P = info_half["Captain"]
hub = P["hub"]
c = max(-1, min(1, (BAR_Z - hub.z) / BB_R))
bar_f = hub.y - math.sqrt(max(0, 1 - c * c)) * BB_R            # where the backbone crosses BAR_Z
L = 2 * bar_f
frame.box((0, 0, BAR_Z), (0.036, L, 0.05), BLACK)
for dz in (-0.022, 0.022):                                      # gold pinstripe edges, both faces
    for sx in (-1, 1):
        frame.box((sx * 0.0185, 0, BAR_Z + dz), (0.002, L * 0.92, 0.004), GOLD, 1)
for sx in (-1, 1):                                              # scroll panels: short gold dashes either side of the medallion
    for k in range(5):
        y0 = 0.07 + k * (bar_f - 0.11) / 5
        for sy in (-1, 1):
            frame.box((sx * 0.0185, sy * y0, BAR_Z + (0.006 if k % 2 else -0.006)), (0.002, 0.025, 0.008), GOLD, 1)
for sy in (-1, 1):                                              # gold collars where the bar meets the backbones
    frame.cyl((0, sy * (bar_f - 0.03), BAR_Z), (0, sy * (bar_f + 0.005), BAR_Z), 0.034, GOLD, 1, n=8)
frame.cyl((-0.03, 0, BAR_Z), (0.03, 0, BAR_Z), 0.062, GOLD, 1, n=20)                   # medallion
for sx in (-1, 1):
    frame.torus_x((sx * 0.03, 0, BAR_Z), 0.058, 0.006, GOLD, 1, nmaj=20, nmin=4)       # rim
    # a little goose in relief: body, neck, head, beak
    g0 = Vector((sx * 0.034, 0, BAR_Z - 0.008))
    frame.sphere(g0 + Vector((0, 0.008, 0)), 0.021, GOLD, 1, n=8, squash=(0.25, 1.2, 0.7))
    frame.cyl(g0 + Vector((0, -0.012, 0.006)), g0 + Vector((0, -0.016, 0.032)), 0.006, GOLD, 1, n=6)
    frame.sphere(g0 + Vector((0, -0.018, 0.036)), 0.008, GOLD, 1, n=8, squash=(0.6, 1, 1))
    frame.cyl(g0 + Vector((0, -0.024, 0.036)), g0 + Vector((0, -0.034, 0.034)), 0.004, GOLD, 1, n=4, r2=0.0015)

frame_ob = frame.build()
for name, ob in nodes.items():
    if name.startswith(("Steer", "Wheel_S")):
        parent_keep(ob, frame_ob)
for tag in ("F", "R"):
    for n in (f"Wheel_{tag}", f"Crank_{tag}"):
        parent_keep(nodes[n], nodes[f"Steer_{tag}"])

sockets = {}
for seat, s in (("Captain", 1), ("Stoker", -1)):
    e = bpy.data.objects.new("Seat_" + seat, None)
    e.empty_display_size = 0.1
    e.location = W(s, info_half[seat]["origin"])
    e.rotation_euler = (0, 0, 0 if s > 0 else math.pi)
    sc.collection.objects.link(e)
    parent_keep(e, frame_ob)
    sockets[seat] = e

# ---- Ride clip: every wheel rolls forward (-Y), cranks with their big wheels ------------------------------------------
# Wheel/crank nodes sit under tilted steer nodes; keyframe their world rotation about world X, expressed locally.
spin = {"Wheel_F": 1.0, "Wheel_R": 1.0, "Crank_F": 1.0, "Crank_R": 1.0, "Wheel_SF": R / SR, "Wheel_SR": R / SR}
bpy.context.view_layer.update()
rest = {n: nodes[n].matrix_world.copy() for n in spin}
for n, turns in spin.items():
    ob = nodes[n]
    ob.rotation_mode = "QUATERNION"
    act = bpy.data.actions.new("Ride_" + n)
    ob.animation_data_create()
    ob.animation_data.action = act
    steps = 8
    for k in range(steps + 1):
        ang = 2 * math.pi * turns * k / steps
        loc, rot, scl = rest[n].decompose()
        world = Matrix.Translation(loc) @ Matrix.Rotation(ang, 4, "X") @ rot.to_matrix().to_4x4()
        ob.matrix_world = world
        ob.keyframe_insert("rotation_quaternion", frame=1 + FPS * k / steps)
    try:
        fcs = [fc for layer in act.layers for strip in layer.strips for cb in strip.channelbags for fc in cb.fcurves]
    except AttributeError:
        fcs = list(act.fcurves)
    for fc in fcs:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
    ob.animation_data.action = None
    tr = ob.animation_data.nla_tracks.new()
    tr.name = "Ride"
    strip = tr.strips.new("Ride", 1, act)
    try:
        strip.action_slot = act.slots[0]
    except Exception:                                      # noqa: BLE001
        pass
    strip.extrapolation = "NOTHING"
    tr.mute = True
    ob.matrix_world = rest[n]
sc.frame_start, sc.frame_end = 1, 1 + FPS
sc.frame_set(1)
for n in spin:
    nodes[n].matrix_world = rest[n]

# ---- export ----------------------------------------------------------------------------------------------------------
parts = [frame_ob, *nodes.values()]
tris = sum(len(p.vertices) - 2 for ob in parts for p in ob.data.polygons)
bpy.ops.object.select_all(action="DESELECT")
for ob in (*parts, *sockets.values()):
    ob.select_set(True)
bpy.context.view_layer.objects.active = frame_ob
bpy.ops.export_scene.gltf(filepath=str(OUT_GLB), export_format="GLB", use_selection=True, export_yup=True,
                          export_animations=True, export_animation_mode="NLA_TRACKS", export_tangents=False,
                          export_optimize_animation_size=True, export_morph=False, export_skins=False,
                          export_vertex_color="ACTIVE", export_anim_slide_to_zero=True)


def yup(v):
    return [round(v.x, 4), round(v.z, 4), round(-v.y, 4)]


pts = [ob.matrix_world @ Vector(cn) for ob in parts for cn in ob.bound_box]
size = [max(p[i] for p in pts) - min(p[i] for p in pts) for i in range(3)]
info = {"style": "penny-farthing tandem (Time Warp bike)", "origin": "ground centre", "up": "+Y", "forward": "+Z",
        "units": "metres", "length_m": round(size[1], 3), "width_m": round(size[0], 3), "height_m": round(size[2], 3),
        "tris": tris, "big_wheel_diameter_m": round(D, 3), "small_wheel_diameter_m": round(2 * SR, 3),
        "crank_radius_m": CRANK_R, "hip_up_above_saddle": HIP_UP, "cross_bar_height_m": round(BAR_Z, 3),
        "halves": {}}
for seat, s in (("Captain", 1), ("Stoker", -1)):
    H = info_half[seat]
    info["halves"][seat] = {
        "faces": "+Z (forward)" if s > 0 else "-Z (backward)",
        "seat_socket": yup(W(s, H["origin"])), "saddle_top": yup(W(s, H["saddle"])),
        "hub": yup(W(s, H["hub"])), "grips": {k: yup(W(s, v)) for k, v in H["grip"].items()},
        "steer_axis": yup(W(s, H["steer_axis"])), "small_hub": yup(W(s, H["small_hub"]))}
info["clips"] = {"Ride": {"duration": 1.0, "loop": True, "nodes": list(spin),
                          "note": "rolling forward; stoker's cranks turn backwards for her (Pedal_Stoker reversed)"}}
(OUT / "pf_tandem_info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
print("PF_TANDEM", OUT_GLB, "tris", tris, "size", [round(x, 3) for x in size])

# ---- review sheet ------------------------------------------------------------------------------------------------------
if SHEET:
    for seat, gname, clip in (("Captain", "winston", "Pedal_Captain"), ("Stoker", "victoria", "Pedal_Stoker")):
        glb = GEESE / f"{gname}.glb"
        if not glb.exists():
            print("SHEET: missing", glb)
            continue
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(glb))
        new = [o for o in bpy.data.objects if o not in before]
        rig = [o for o in new if o.type == "ARMATURE"][0]
        for o in new:
            if o.parent is None:
                o.parent = sockets[seat]
                o.matrix_parent_inverse = Matrix.Identity(4)
                o.location = (0, 0, 0)
                o.rotation_euler = (0, 0, 0)
        ad = rig.animation_data
        for t in ad.nla_tracks:
            t.mute = True
        act = bpy.data.actions.get(clip)
        if act:
            ad.action = act
            try:
                ad.action_slot = act.slots[0]
            except Exception:                              # noqa: BLE001
                pass
    sc.frame_set(1)
    bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 0, 0))
    ground = bpy.context.active_object
    gm = bpy.data.materials.new("ground")
    gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.45, 0.42, 0.36, 1)
    ground.data.materials.append(gm)
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 1000, 700
    sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.70, 0.74, 0.80, 1)
    sc.world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.5
    sun.rotation_euler = Euler((math.radians(45), math.radians(10), math.radians(-35)))
    sc.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.lens = 50
    target = Vector((0, 0, 0.75))
    tag = argv[argv.index("--tag") + 1] if "--tag" in argv else ""
    views = {"side": Vector((-6.5, 0, 0.9)), "front34": Vector((-3.6, -4.2, 1.7)),
             "back34": Vector((3.4, 4.4, 1.9)), "high": Vector((-2.0, 1.5, 5.2))}
    rdir = ROOT / "renders" / "pf_tandem"
    rdir.mkdir(parents=True, exist_ok=True)
    tiles = []
    for name, loc in views.items():
        cam.location = loc
        cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = str(rdir / f"_build_{name}.png")
        bpy.ops.render.render(write_still=True)
        im = bpy.data.images.load(sc.render.filepath)
        tiles.append(np.array(im.pixels[:]).reshape(im.size[1], im.size[0], 4))
    h, wd = tiles[0].shape[:2]
    sheet = np.zeros((2 * h, 2 * wd, 4), np.float32)
    for i, t in enumerate(tiles):
        r, cc = 1 - i // 2, i % 2
        sheet[r * h:(r + 1) * h, cc * wd:(cc + 1) * wd] = t
    out = bpy.data.images.new("sheet", 2 * wd, 2 * h)
    out.pixels = sheet.reshape(-1).tolist()
    out.filepath_raw = str(rdir / f"build_sheet{tag}.png")
    out.file_format = "PNG"
    out.save()
    print("SHEET", out.filepath_raw)
