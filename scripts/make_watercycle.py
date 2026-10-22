"""SandQuest pedalo, take 2: a period water-cycle (Pete's reference photo, 2026-10-22).

  blender -b --factory-startup --python scripts/make_watercycle.py -- [--sheet] [--out out/sandquest/watercycle_raw.glb]

A tandem bicycle frame raised on struts over two long, narrow floats, a paddle wheel at the stern where the rear
wheel would be (chain-driven from the stoker's crank), upright bars for the captain, the stoker's bars on the
captain's seat post, sprung leather saddles. Black enamel frame, varnished floats with a cream deck strip and a
red waterline, brass fittings: vertex colours + two materials (paint, brass), like make_pedalo.py.

Same contract as make_pedalo.py so the game needs no new code: nodes Seat_Captain / Seat_Stoker (goose rig origin,
identity rotation), Crank_F / Crank_R / PaddleWheel (rotate about local +X; clip "Paddle" = one turn in 1.0 s, left
pedal at the top at t = 0, matching the geese's Pedal_* clips). The seat/crank/grip geometry is the geese's own
(<goose>_clips.json + the tandem's crank offsets), only lifted higher above the water, as in the photo.

Conventions: Blender Z up, boat faces -Y; exported +Y up, +Z forward. Origin = waterline centre, metres.
--sheet renders renders/sandquest/watercycle_sheet.png with both toy geese seated (needs winston.glb / victoria.glb).
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
OUT = ROOT / "out" / "sandquest"
OUT.mkdir(parents=True, exist_ok=True)
OUT_GLB = Path(argv[argv.index("--out") + 1]) if "--out" in argv else OUT / "watercycle_raw.glb"
SHEET = "--sheet" in argv
FPS = 24


def goose_meta(name):
    p = OUT / f"{name}_clips.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def bl(v):                                              # three.js (x, y, z) -> Blender (x, -z, y)
    return Vector((v[0], -v[2], v[1]))


HIP_UP = 0.11
CRANK_FWD, CRANK_DOWN = 0.197 - 0.004, 0.78 - 0.262
SEAT_GAP = 0.642
CRANK_R = 0.162
meta = {"Captain": goose_meta("winston"), "Stoker": goose_meta("victoria")}
hip_mid = {s: bl(m["hip_mid_rest"]) if m else Vector((0, 0.0247, 0.8135)) for s, m in meta.items()}
grip = {s: {k: bl(v) for k, v in m["ride_grip"].items()} if m else
        {"Left": Vector((0.19, -0.44, 0.94)), "Right": Vector((-0.19, -0.44, 0.94))} for s, m in meta.items()}

# ---- layout (Blender, metres; forward is -Y) ----------------------------------------------------------------------
FLOAT_R, FLOAT_X, FLOAT_ZC = 0.115, 0.46, -0.025         # long narrow floats, riding low
FLOAT_TOP = FLOAT_ZC + FLOAT_R
G = 0.40                                                 # goose rig origin: the riders sit high, as in the photo
Y_C = -0.36
Y_S = Y_C + SEAT_GAP
BOW, STERN = -1.62, 1.42
TUBE = 0.024
WHEEL_R, WHEEL_W = 0.30, 0.52

BLACK = (0.035, 0.035, 0.04, 1)
WOOD = (0.42, 0.22, 0.10, 1)
WOOD_D = (0.25, 0.12, 0.06, 1)
CREAM = (0.93, 0.86, 0.68, 1)
RED = (0.72, 0.10, 0.09, 1)
TEAL = (0.07, 0.42, 0.42, 1)
NAVY = (0.08, 0.10, 0.20, 1)
LEATHER = (0.36, 0.18, 0.08, 1)
BRASS = (0.85, 0.60, 0.25, 1)


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
        cx, cy, cz = center
        sx, sy, sz = (s / 2 for s in size)
        vs = [Vector((x, y, z)) for x in (-sx, sx) for y in (-sy, sy) for z in (-sz, sz)]
        if rot is not None:
            vs = [rot @ v for v in vs]
        vs = [(v.x + cx, v.y + cy, v.z + cz) for v in vs]
        fs = [[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]]
        self.add(vs, fs, color, mat)

    def cyl(self, a, b, r, color, mat=0, n=6, caps=True):
        a, b = Vector(a), Vector(b)
        axis = (b - a).normalized()
        u = axis.cross(Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((1, 0, 0))).normalized()
        w = axis.cross(u)
        ring = [(math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n)) for i in range(n)]
        vs = [tuple(a + (u * c + w * s) * r) for c, s in ring] + [tuple(b + (u * c + w * s) * r) for c, s in ring]
        fs = [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
        if caps:
            fs.append(list(range(n))[::-1])
            fs.append([n + i for i in range(n)])
        self.add(vs, fs, color, mat)

    def tube(self, pts, r=TUBE, color=BLACK, mat=0, n=6):
        for a, b in zip(pts, pts[1:]):
            self.cyl(a, b, r, color, mat, n)
        for p in pts[1:-1]:                                  # a little lug at each bend
            self.cyl(Vector(p) - Vector((0, 0, r * 0.8)), Vector(p) + Vector((0, 0, r * 0.8)), r * 1.3, color, mat, n)

    def revolve(self, axis_pts, radii, colors, n=12):
        m = len(axis_pts)
        vs, fs, cs = [], [], []
        for (cx, cy, cz), r in zip(axis_pts, radii):
            for i in range(n):
                t = 2 * math.pi * i / n
                vs.append((cx + r * math.cos(t), cy, cz + r * math.sin(t)))
        for k in range(m - 1):
            for i in range(n):
                fs.append([k * n + i, (k + 1) * n + i, (k + 1) * n + (i + 1) % n, k * n + (i + 1) % n])
                cs.append(colors[k][i])
        fs.append([i for i in range(n)])
        cs.append(colors[0][0])
        fs.append([(m - 1) * n + i for i in range(n)][::-1])
        cs.append(colors[-1][0])
        start = len(self.v)
        self.v += [Vector(x) for x in vs]
        self.f += [[i + start for i in face] for face in fs]
        self.c += cs
        self.m += [0] * len(fs)

    def build(self, origin=(0, 0, 0)):
        me = bpy.data.meshes.new(self.name)
        o = Vector(origin)
        me.from_pydata([v - o for v in self.v], [], self.f)
        me.update()
        me.materials.append(PAINT)
        me.materials.append(BRASSM)
        col = me.color_attributes.new("Col", "BYTE_COLOR", "CORNER")
        for p, c, mi in zip(me.polygons, self.c, self.m):
            p.material_index = mi
            p.use_smooth = False
            for li in p.loop_indices:
                col.data[li].color = c if mi == 0 else (1, 1, 1, 1)
        ob = bpy.data.objects.new(self.name, me)
        ob.location = o
        bpy.context.scene.collection.objects.link(ob)
        return ob


bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.fps = FPS
PAINT = bpy.data.materials.new("pedalo_paint")
PAINT.use_nodes = True
nt = PAINT.node_tree
bsdf = nt.nodes["Principled BSDF"]
bsdf.inputs["Roughness"].default_value = 0.35
bsdf.inputs["Metallic"].default_value = 0.0
ca = nt.nodes.new("ShaderNodeVertexColor")
ca.layer_name = "Col"
nt.links.new(ca.outputs["Color"], bsdf.inputs["Base Color"])
BRASSM = bpy.data.materials.new("pedalo_brass")
BRASSM.use_nodes = True
b2 = BRASSM.node_tree.nodes["Principled BSDF"]
b2.inputs["Base Color"].default_value = BRASS
b2.inputs["Metallic"].default_value = 1.0
b2.inputs["Roughness"].default_value = 0.3

# ---- the riders' fixed points ----------------------------------------------------------------------------------------
saddle, bb = {}, {}
for seat, yr in (("Captain", Y_C), ("Stoker", Y_S)):
    saddle[seat] = Vector((0, yr + hip_mid[seat].y, G + hip_mid[seat].z - HIP_UP))
    bb[seat] = Vector((0, yr + hip_mid[seat].y - CRANK_FWD, G + hip_mid[seat].z - HIP_UP - CRANK_DOWN))
WHEEL = Vector((0, bb["Stoker"].y + 0.78, FLOAT_TOP + 0.06))        # paddle wheel axle (the "rear wheel")
cluster = {s: saddle[s] + Vector((0, 0.03, -0.11)) for s in saddle}  # where seat tube meets top tube
# Head tube a little below the seat clusters (the top tube slopes, as in the photo); the fork rakes well forward.
HEAD_T = Vector((0, bb["Captain"].y - 0.42, cluster["Captain"].z - 0.02))
HEAD_B = HEAD_T + Vector((0, -0.07, -0.20))
FORK_FOOT = Vector((0, HEAD_B.y - 0.42, FLOAT_TOP + 0.03))

# ---- floats: long, narrow, pointed, varnished with a cream deck strip and a red waterline ---------------------------
hull = Part("Hull")
ys = [BOW, BOW + 0.08, BOW + 0.25, BOW + 0.6, -0.4, 0.3, STERN - 0.55, STERN - 0.22, STERN - 0.06, STERN]
rs = [0.015, 0.05, 0.085, FLOAT_R, FLOAT_R, FLOAT_R, FLOAT_R, 0.09, 0.05, 0.02]
zs = [FLOAT_ZC + 0.06, FLOAT_ZC + 0.035, FLOAT_ZC + 0.015, FLOAT_ZC, FLOAT_ZC, FLOAT_ZC, FLOAT_ZC, FLOAT_ZC + 0.01, FLOAT_ZC + 0.03, FLOAT_ZC + 0.045]
N = 12


def float_colors():
    cols = []
    for i in range(N):
        z = math.sin(2 * math.pi * (i + 0.5) / N)
        cols.append(CREAM if z > 0.8 else WOOD if z > 0.05 else RED if z > -0.25 else WOOD_D)
    return cols


for sx in (-1, 1):
    hull.revolve([(sx * FLOAT_X, y, z) for y, z in zip(ys, zs)], rs, [float_colors()] * (len(ys) - 1), n=N)

# cross beams over the floats: bow (fork foot), under the cranks, and the stern (wheel axle)
BEAM_H = 0.04
for y in (FORK_FOOT.y, (bb["Captain"].y + bb["Stoker"].y) / 2, WHEEL.y + WHEEL_R + 0.10):
    hull.box((0, y, FLOAT_TOP + BEAM_H / 2), (2 * FLOAT_X + 0.10, 0.06, BEAM_H), WOOD)
hull.box((0, FORK_FOOT.y, FLOAT_TOP + BEAM_H + 0.01), (0.12, 0.08, 0.02), BRASS, 1)

# the tandem frame (black enamel)
cc, cs_ = cluster["Captain"], cluster["Stoker"]
hull.tube([HEAD_T, cc, cs_])                                       # top tube
hull.tube([HEAD_B, bb["Captain"], bb["Stoker"]])                   # down tube + boom
hull.tube([cc, bb["Captain"]])                                     # seat tubes
hull.tube([cs_, bb["Stoker"]])
hull.tube([cc, bb["Stoker"]], r=TUBE * 0.8)                        # the tandem's lateral
hull.cyl(HEAD_T + Vector((0, 0.01, 0.04)), HEAD_B - Vector((0, 0.005, 0.02)), TUBE * 1.35, BLACK)   # head tube
for sx in (-1, 1):
    o = Vector((sx * 0.05, 0, 0))
    hull.cyl(bb["Stoker"] + o * 0.6, WHEEL + o, TUBE * 0.75, BLACK)                     # chainstays
    hull.cyl(cs_ + o * 0.3, WHEEL + o, TUBE * 0.75, BLACK)                             # seatstays
    hull.cyl(HEAD_B + o * 0.5, FORK_FOOT + o, TUBE * 0.8, BLACK)                       # fork blades
    hull.cyl(WHEEL + Vector((sx * (WHEEL_W / 2 + 0.03), 0, 0)), Vector((sx * FLOAT_X, WHEEL.y, FLOAT_TOP)), 0.018, BLACK)  # axle hangers
# A-frame struts from the floats up to the bottom brackets (the photo's diagonal braces)
for seat in ("Captain", "Stoker"):
    for sx in (-1, 1):
        foot = Vector((sx * FLOAT_X, bb[seat].y, FLOAT_TOP))
        hull.cyl(foot, bb[seat] + Vector((sx * 0.06, 0, 0)), 0.016, BLACK)
        hull.cyl(foot - Vector((0, 0.03, 0)), foot + Vector((0, 0.03, 0)), 0.03, BRASS, 1)  # brass shoe on the float
hull.cyl(bb["Captain"] + Vector((-0.07, 0, 0)), bb["Captain"] + Vector((0.07, 0, 0)), 0.035, BLACK)   # BB shells
hull.cyl(bb["Stoker"] + Vector((-0.07, 0, 0)), bb["Stoker"] + Vector((0.07, 0, 0)), 0.035, BLACK)

# seat posts + sprung leather saddles
for seat in ("Captain", "Stoker"):
    s = saddle[seat]
    hull.cyl(cluster[seat], s + Vector((0, 0.03, -0.05)), 0.017, BRASS, 1)
    hull.box((0, s.y + 0.05, s.z - 0.03), (0.17, 0.12, 0.05), LEATHER)                   # broad back
    hull.box((0, s.y - 0.06, s.z - 0.025), (0.07, 0.14, 0.04), LEATHER)                   # nose
    for sx in (-1, 1):
        hull.cyl((sx * 0.05, s.y + 0.08, s.z - 0.06), (sx * 0.05, s.y + 0.08, s.z - 0.11), 0.014, BRASS, 1, n=6)

# captain's upright bars: stem up from the head tube, bars swept back to the Ride-pose grips
gl, gr = grip["Captain"]["Left"], grip["Captain"]["Right"]
bar_z, bar_y = G + (gl.z + gr.z) / 2, Y_C + (gl.y + gr.y) / 2
stem_top = Vector((0, bar_y - 0.12, bar_z + 0.02))
hull.cyl(HEAD_T, stem_top, 0.017, BRASS, 1)
for g in (gl, gr):
    end = Vector((g.x, bar_y, bar_z))
    bend = Vector((g.x * 0.6, bar_y - 0.12, bar_z + 0.02))
    hull.cyl(stem_top, bend, 0.013, BRASS, 1)
    hull.cyl(bend, end, 0.013, BRASS, 1)
    hull.cyl((g.x, bar_y - 0.02, bar_z), (g.x, bar_y + 0.08, bar_z), 0.02, NAVY)
# stoker's bars on the captain's seat post
sl, sr = grip["Stoker"]["Left"], grip["Stoker"]["Right"]
rail_z, rail_y = G + (sl.z + sr.z) / 2, Y_S + (sl.y + sr.y) / 2
post = saddle["Captain"] + Vector((0, 0.06, -0.07))
mid = Vector((0, rail_y - 0.06, rail_z))
hull.cyl(post, mid, 0.014, BRASS, 1)
hull.cyl((sl.x, rail_y - 0.04, rail_z), (sr.x, rail_y - 0.04, rail_z), 0.013, BRASS, 1)
for g in (sl, sr):
    hull.cyl((g.x, rail_y - 0.04, rail_z), (g.x, rail_y + 0.06, rail_z), 0.02, NAVY)

# chain (stoker's chainring to the wheel's sprocket), right side; the wheel is open, as in the photo
CX = -0.085
for dz in (0.09, -0.09):
    hull.box((CX, (bb["Stoker"].y + WHEEL.y) / 2, (bb["Stoker"].z + WHEEL.z) / 2 + dz * 0.75),
             (0.008, (WHEEL.y - bb["Stoker"].y) * 1.0, 0.01), NAVY,
             rot=Matrix.Rotation(math.atan2(-(bb["Stoker"].z - WHEEL.z), WHEEL.y - bb["Stoker"].y), 3, "X"))
hull_ob = hull.build()

# ---- cranks -------------------------------------------------------------------------------------------------------
cranks = {}
for seat, name in (("Captain", "Crank_F"), ("Stoker", "Crank_R")):
    cy, cz = bb[seat].y, bb[seat].z
    p = Part(name)
    PIN_X = 0.095
    p.cyl((-PIN_X - 0.02, cy, cz), (PIN_X + 0.02, cy, cz), 0.014, BRASS, 1)
    if seat == "Stoker":                                             # chainring
        ring = [(CX, cy + 0.10 * math.cos(2 * math.pi * i / 12), cz + 0.10 * math.sin(2 * math.pi * i / 12)) for i in range(12)]
        p.add(ring, [list(range(12)), list(range(12))[::-1]], BRASS, 1)
    for sx, phase in ((1, 0.0), (-1, math.pi)):
        tip = Vector((sx * PIN_X, cy - CRANK_R * math.sin(phase), cz + CRANK_R * math.cos(phase)))
        mid_ = (Vector((sx * PIN_X, cy, cz)) + tip) / 2
        p.box(tuple(mid_), (0.02, 0.035, CRANK_R), BRASS, 1)
        p.cyl((sx * PIN_X, tip.y, tip.z), (sx * (PIN_X + 0.07), tip.y, tip.z), 0.012, BRASS, 1)
        p.cyl((sx * (PIN_X + 0.02), tip.y, tip.z), (sx * (PIN_X + 0.07), tip.y, tip.z), 0.022, BLACK, 0)
    cranks[name] = p.build(origin=(0, cy, cz))
    cranks[name].parent = hull_ob
    cranks[name].matrix_parent_inverse = Matrix.Identity(4)

# ---- paddle wheel (the rear "wheel") ---------------------------------------------------------------------------------
w = Part("PaddleWheel")
WY, WZ = WHEEL.y, WHEEL.z
for sx in (-1, 1):
    ring_o = [(sx * WHEEL_W / 2, WY + WHEEL_R * math.cos(2 * math.pi * i / 12), WZ + WHEEL_R * math.sin(2 * math.pi * i / 12)) for i in range(12)]
    ring_i = [(sx * WHEEL_W / 2, WY + 0.75 * WHEEL_R * math.cos(2 * math.pi * i / 12), WZ + 0.75 * WHEEL_R * math.sin(2 * math.pi * i / 12)) for i in range(12)]
    w.add(ring_o + ring_i, [[i, (i + 1) % 12, 12 + (i + 1) % 12, 12 + i] for i in range(12)], RED)
    w.add([(x + sx * 0.02, y, z) for x, y, z in ring_o] + [(x + sx * 0.02, y, z) for x, y, z in ring_i],
          [[i, 12 + i, 12 + (i + 1) % 12, (i + 1) % 12] for i in range(12)], RED)
    for i in range(6):                                               # spokes
        t = 2 * math.pi * i / 6
        w.cyl((sx * WHEEL_W / 2, WY, WZ), (sx * WHEEL_W / 2, WY + 0.75 * WHEEL_R * math.cos(t), WZ + 0.75 * WHEEL_R * math.sin(t)), 0.008, BLACK, n=4, caps=False)
for i in range(8):
    t = 2 * math.pi * i / 8
    r_mid = 0.62 * WHEEL_R
    c = (0, WY + r_mid * math.cos(t), WZ + r_mid * math.sin(t))
    w.box(c, (WHEEL_W - 0.02, 0.7 * WHEEL_R, 0.022), CREAM if i % 2 else WOOD, rot=Matrix.Rotation(t + math.pi / 2, 3, "X"))
w.cyl((-WHEEL_W / 2 - 0.05, WY, WZ), (WHEEL_W / 2 + 0.05, WY, WZ), 0.02, BRASS, 1)
sprocket = [(CX, WY + 0.06 * math.cos(2 * math.pi * i / 8), WZ + 0.06 * math.sin(2 * math.pi * i / 8)) for i in range(8)]
w.add(sprocket, [list(range(8)), list(range(8))[::-1]], BRASS, 1)
wheel_ob = w.build(origin=(0, WY, WZ))
wheel_ob.parent = hull_ob
wheel_ob.matrix_parent_inverse = Matrix.Identity(4)

# ---- seat sockets ------------------------------------------------------------------------------------------------
sockets = {}
for seat, yr in (("Captain", Y_C), ("Stoker", Y_S)):
    e = bpy.data.objects.new("Seat_" + seat, None)
    e.empty_display_size = 0.1
    e.location = (0, yr, G)
    sc.collection.objects.link(e)
    e.parent = hull_ob
    sockets[seat] = e

# ---- Paddle clip ---------------------------------------------------------------------------------------------------
for ob in (wheel_ob, cranks["Crank_F"], cranks["Crank_R"]):
    ob.rotation_mode = "XYZ"
    act = bpy.data.actions.new("Paddle_" + ob.name)
    ob.animation_data_create()
    ob.animation_data.action = act
    for f, ang in ((1, 0.0), (1 + FPS, 2 * math.pi)):
        ob.rotation_euler = Euler((ang, 0, 0))
        ob.keyframe_insert("rotation_euler", frame=f)
    try:
        for layer in act.layers:
            for strip in layer.strips:
                for cb in strip.channelbags:
                    for fc in cb.fcurves:
                        for k in fc.keyframe_points:
                            k.interpolation = "LINEAR"
    except AttributeError:
        for fc in act.fcurves:
            for k in fc.keyframe_points:
                k.interpolation = "LINEAR"
    ob.animation_data.action = None
    tr = ob.animation_data.nla_tracks.new()
    tr.name = "Paddle"
    st = tr.strips.new("Paddle", 1, act)
    try:
        st.action_slot = act.slots[0]
    except Exception:                                      # noqa: BLE001
        pass
    st.extrapolation = "NOTHING"
    tr.mute = True
    ob.rotation_euler = Euler((0, 0, 0))
sc.frame_start, sc.frame_end = 1, 1 + FPS
sc.frame_set(1)

# ---- export -----------------------------------------------------------------------------------------------------
parts = (hull_ob, wheel_ob, *cranks.values())
tris = sum(len(p.vertices) - 2 for ob in parts for p in ob.data.polygons)
bpy.ops.object.select_all(action="DESELECT")
for ob in (*parts, *sockets.values()):
    ob.select_set(True)
bpy.context.view_layer.objects.active = hull_ob
bpy.ops.export_scene.gltf(filepath=str(OUT_GLB), export_format="GLB", use_selection=True, export_yup=True,
                          export_animations=True, export_animation_mode="NLA_TRACKS", export_tangents=False,
                          export_optimize_animation_size=True, export_morph=False, export_skins=False,
                          export_vertex_color="ACTIVE", export_anim_slide_to_zero=True)


def yup(v):
    return [round(v.x, 4), round(v.z, 4), round(-v.y, 4)]


info = {"style": "water-cycle", "origin": "waterline centre", "up": "+Y", "forward": "+Z", "units": "metres",
        "length_m": round(STERN - BOW, 3), "width_m": round(2 * FLOAT_X + 2 * FLOAT_R, 3),
        "draft_m": round(-(FLOAT_ZC - FLOAT_R), 3), "tris": tris,
        "sockets": {"Seat_" + s: yup(Vector((0, y, G))) for s, y in (("Captain", Y_C), ("Stoker", Y_S))},
        "saddle_top": {s: yup(saddle[s]) for s in saddle},
        "cranks": {n: yup(Vector(cranks[n].location)) for n in cranks},
        "crank_radius_m": CRANK_R, "paddle_wheel": yup(WHEEL), "paddle_wheel_radius_m": WHEEL_R,
        "hip_up_above_saddle": HIP_UP,
        "clips": {"Paddle": {"duration": 1.0, "loop": True, "nodes": ["PaddleWheel", "Crank_F", "Crank_R"]}}}
(OUT / "watercycle_info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
print("WATERCYCLE", OUT_GLB, "tris", tris, json.dumps(info["sockets"]))

# ---- review sheet -------------------------------------------------------------------------------------------------
if SHEET:
    for seat, gname, clip in (("Captain", "winston", "Pedal_Captain"), ("Stoker", "victoria", "Pedal_Stoker")):
        glb = OUT / f"{gname}.glb"
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
    sc.frame_set(1 + 7)
    for ob in (wheel_ob, *cranks.values()):
        ob.rotation_euler = Euler((2 * math.pi * 7 / FPS, 0, 0))
    # a sheet of water so the waterline reads
    bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, 0))
    water = bpy.context.active_object
    wm = bpy.data.materials.new("water")
    wm.use_nodes = True
    wb = wm.node_tree.nodes["Principled BSDF"]
    wb.inputs["Base Color"].default_value = (0.18, 0.32, 0.36, 1)
    wb.inputs["Roughness"].default_value = 0.15
    water.data.materials.append(wm)
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 900, 700
    sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.62, 0.68, 0.74, 1)
    sc.world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = Euler((math.radians(50), math.radians(10), math.radians(-30)))
    sc.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.lens = 40
    target = Vector((0, 0.1, 0.75))
    views = {"photo": Vector((-5.2, -1.4, 1.2)), "front34": Vector((-3.4, -3.6, 2.0)),
             "back34": Vector((3.0, 3.8, 1.9)), "top": Vector((-0.8, 0.3, 5.8))}
    rdir = ROOT / "renders" / "sandquest"
    rdir.mkdir(parents=True, exist_ok=True)
    tiles = []
    for name, loc in views.items():
        cam.location = loc
        cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = str(rdir / f"_watercycle_{name}.png")
        bpy.ops.render.render(write_still=True)
        im = bpy.data.images.load(sc.render.filepath)
        tiles.append(np.array(im.pixels[:]).reshape(im.size[1], im.size[0], 4))
    h, wd = tiles[0].shape[:2]
    sheet = np.zeros((2 * h, 2 * wd, 4), np.float32)
    for i, t in enumerate(tiles):
        r, c = 1 - i // 2, i % 2
        sheet[r * h:(r + 1) * h, c * wd:(c + 1) * wd] = t
    out = bpy.data.images.new("sheet", 2 * wd, 2 * h)
    out.pixels = sheet.reshape(-1).tolist()
    out.filepath_raw = str(rdir / "watercycle_sheet.png")
    out.file_format = "PNG"
    out.save()
    print("SHEET", out.filepath_raw)
