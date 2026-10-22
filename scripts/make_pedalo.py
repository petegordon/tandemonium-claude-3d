"""SandQuest pedalo: a tin-toy tandem pedal boat built around the geese's riding clips (docs/sandquest-assets.md).

  blender -b --factory-startup --python scripts/make_pedalo.py -- [--sheet] [--out out/sandquest/pedalo_raw.glb]

Catamaran: two pontoons, a flat deck, two bench seats in line (captain front, stoker behind, same spacing as the
goose tandem), a paddle wheel between the hulls at the stern, a brass crank per seat, a steering bar for the
captain, a grab rail for the stoker, a pennant at the stern. Painted-tin look: cream hull, red and teal stripes,
brass fittings -- baked as vertex colours, two materials (paint, brass).

Fit: the seat sockets, cranks and bars come from the geese's own numbers (out/sandquest/<goose>_clips.json:
rest hip height, Ride-pose grip points) and the tandem's seat/crank geometry (make_bike.py sockets: crank 0.197 m
ahead of and 0.518 m below the saddle top; hip joints HIP_UP = 0.11 above the saddle), so the UNCHANGED
Pedal_<seat> clips put the feet on the pedals.

Conventions: Blender Z up, boat faces -Y; exported +Y up, +Z forward (three.js). Origin = waterline centre,
metres. Nodes: Seat_Captain / Seat_Stoker (empties: put the goose rig origin here, identity rotation),
PaddleWheel + Crank_F + Crank_R (rotate about local +X; clip "Paddle" = one turn in 1.0 s, same phase as the
geese's Pedal clips: left pedal at the top at t = 0), Flag (pennant, origin at the pole top).
--sheet also renders renders/sandquest/pedalo_sheet.png with both toy geese seated (needs winston.glb / victoria.glb).
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
OUT_GLB = Path(argv[argv.index("--out") + 1]) if "--out" in argv else OUT / "pedalo_raw.glb"
SHEET = "--sheet" in argv
FPS = 24

# ---- rider numbers ---------------------------------------------------------------------------------------------
def goose_meta(name):
    p = OUT / f"{name}_clips.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def bl(v):                                              # three.js (x, y, z) -> Blender (x, -z, y)
    return Vector((v[0], -v[2], v[1]))


HIP_UP = 0.11                                           # hip joints above the saddle top (ride_fit.py / game)
CRANK_FWD, CRANK_DOWN = 0.197 - 0.004, 0.78 - 0.262     # tandem: Seat_Captain -> Crank_F (bike metres)
SEAT_GAP = 0.642                                        # Seat_Captain -> Seat_Stoker along the boat
CRANK_R = 0.162                                         # pedal circle radius in the Pedal clips (ankle orbit)
meta = {"Captain": goose_meta("winston"), "Stoker": goose_meta("victoria")}
hip_mid = {s: bl(m["hip_mid_rest"]) if m else Vector((0, 0.0247, 0.8135)) for s, m in meta.items()}
grip = {s: {k: bl(v) for k, v in m["ride_grip"].items()} if m else
        {"Left": Vector((0.19, -0.44, 0.94)), "Right": Vector((-0.19, -0.44, 0.94))} for s, m in meta.items()}

# ---- boat layout (Blender, metres) -------------------------------------------------------------------------------
PONTOON_R, PONTOON_X, PONTOON_ZC = 0.16, 0.40, -0.02
DECK_Z0, DECK_Z1 = 0.14, 0.17                            # tin deck plate
G = DECK_Z1 + 0.02                                       # the goose rig origin ("ground") floats 2 cm over the deck
Y_C = -0.30                                              # captain rig origin (forward is -Y)
Y_S = Y_C + SEAT_GAP
BOW, STERN = -1.28, 1.16
WHEEL_Y, WHEEL_Z, WHEEL_R, WHEEL_W = Y_S + 0.47, 0.12, 0.27, 0.40

CREAM = (0.93, 0.86, 0.68, 1)
RED = (0.72, 0.10, 0.09, 1)
TEAL = (0.07, 0.42, 0.42, 1)
NAVY = (0.08, 0.10, 0.20, 1)
WHITE = (0.95, 0.94, 0.90, 1)
BRASS = (0.85, 0.60, 0.25, 1)


class Part:
    """Accumulates a mesh: verts, faces, per-face colour and material (0 paint, 1 brass)."""

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

    def cyl(self, a, b, r, color, mat=0, n=8, caps=True):
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

    def revolve(self, axis_pts, radii, colors, n=12):
        """Rings along +Y at (x, y, z) centres with radii; colors[j] per angular sector (len n) per ring pair."""
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
        fs.append([i for i in range(n)])                    # bow cap (ring 0, looking -Y)
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
            for li in p.loop_indices:                       # brass: white (three.js multiplies COLOR_0 in anyway)
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

# ---- hull --------------------------------------------------------------------------------------------------------
hull = Part("Hull")
ys = [BOW, BOW + 0.10, BOW + 0.26, BOW + 0.5, -0.5, 0.0, 0.5, 0.9, STERN - 0.08, STERN]
rs = [0.03, 0.09, 0.135, PONTOON_R, PONTOON_R, PONTOON_R, PONTOON_R, PONTOON_R, 0.13, 0.08]
N = 12


def sector_colors():
    """Tin stripes around the pontoon: cream top, red belt just above the waterline, teal below."""
    cols = []
    for i in range(N):
        t = 2 * math.pi * (i + 0.5) / N
        z = math.sin(t)                                     # -1 bottom .. 1 top (relative)
        cols.append(CREAM if z > 0.35 else RED if z > -0.05 else TEAL)
    return cols


for sx in (-1, 1):
    pts = [(sx * PONTOON_X, y, PONTOON_ZC) for y in ys]
    hull.revolve(pts, rs, [sector_colors()] * (len(ys) - 1), n=N)
# deck plate (bow to the wheel housing), teal edge trim
DECK_Y0, DECK_Y1 = BOW + 0.45, WHEEL_Y - WHEEL_R - 0.05
hull.box((0, (DECK_Y0 + DECK_Y1) / 2, (DECK_Z0 + DECK_Z1) / 2), (2 * PONTOON_X + 0.12, DECK_Y1 - DECK_Y0, DECK_Z1 - DECK_Z0), CREAM)
for sx in (-1, 1):
    hull.box((sx * (PONTOON_X + 0.04), (DECK_Y0 + DECK_Y1) / 2, DECK_Z1 + 0.01), (0.04, DECK_Y1 - DECK_Y0, 0.02), TEAL)
# stern beam behind the wheel + wheel brackets
hull.box((0, STERN - 0.16, DECK_Z1 - 0.03), (2 * PONTOON_X + 0.12, 0.10, 0.06), CREAM)
for sx in (-1, 1):
    hull.box((sx * (WHEEL_W / 2 + 0.025), WHEEL_Y, (WHEEL_Z + DECK_Z0) / 2 + 0.02), (0.03, 0.08, DECK_Z0 - WHEEL_Z + 0.16), BRASS, 1)
# central spine (houses the cranks) between the knees: narrow so the pedals clear it
SPINE_W = 0.08
for seat, yr in (("Captain", Y_C), ("Stoker", Y_S)):
    cz = G + hip_mid[seat].z - HIP_UP - CRANK_DOWN      # crank axle height
    cy = yr + hip_mid[seat].y - CRANK_FWD                 # crank axle (forward of the saddle point)
    saddle = Vector((0, yr + hip_mid[seat].y, G + hip_mid[seat].z - HIP_UP))
    hull.box((0, cy, (DECK_Z1 + cz + 0.06) / 2), (SPINE_W, 0.26, cz + 0.06 - DECK_Z1), CREAM)
    hull.box((0, cy, cz + 0.06 + 0.01), (SPINE_W + 0.02, 0.28, 0.02), TEAL)
    # seat pedestal + bench + backrest
    ped_top = saddle.z - 0.05
    hull.box((0, saddle.y + 0.07, (DECK_Z1 + ped_top) / 2), (0.14, 0.14, ped_top - DECK_Z1), CREAM)
    hull.box((0, saddle.y + 0.07, (DECK_Z1 + ped_top) / 2), (0.16, 0.16, 0.05), TEAL)
    hull.box((0, saddle.y + 0.07, saddle.z - 0.025), (0.32, 0.26, 0.05), RED)
    hull.box((0, saddle.y + 0.20, saddle.z + 0.11), (0.32, 0.03, 0.28), RED,
             rot=Matrix.Rotation(math.radians(-12), 3, "X"))
    hull.box((0, saddle.y + 0.22, saddle.z + 0.25), (0.34, 0.035, 0.03), CREAM,
             rot=Matrix.Rotation(math.radians(-12), 3, "X"))
# captain's steering bar: a brass T rising from the spine to the Ride-pose grips
gl, gr = grip["Captain"]["Left"], grip["Captain"]["Right"]
bar_z, bar_y = G + (gl.z + gr.z) / 2, Y_C + (gl.y + gr.y) / 2
hull.cyl((0, bar_y, DECK_Z1), (0, bar_y, bar_z - 0.02), 0.016, BRASS, 1)
hull.cyl((gl.x + 0.03, bar_y, bar_z), (gr.x - 0.03, bar_y, bar_z), 0.014, BRASS, 1)
for gx in (gl.x, gr.x):
    hull.cyl((gx, bar_y, bar_z), (gx, bar_y + 0.09, bar_z), 0.018, NAVY, 0)
hull.cyl((0, bar_y, bar_z - 0.02), (0, bar_y, bar_z + 0.05), 0.02, BRASS, 1)
# stoker's grab rail on the back of the captain's backrest
sl, sr = grip["Stoker"]["Left"], grip["Stoker"]["Right"]
rail_z, rail_y = G + (sl.z + sr.z) / 2, Y_S + (sl.y + sr.y) / 2
hull.cyl((sl.x + 0.03, rail_y, rail_z), (sr.x - 0.03, rail_y, rail_z), 0.014, BRASS, 1)
for gx in (sl.x, sr.x):
    hull.cyl((gx, rail_y, rail_z), (gx, rail_y + 0.09, rail_z), 0.018, NAVY, 0)
cap_back_y = Y_C + hip_mid["Captain"].y + 0.20
for gx in (-0.10, 0.10):
    hull.cyl((gx, cap_back_y, rail_z - 0.04), (gx, rail_y, rail_z), 0.012, BRASS, 1)
# flag pole on the stern beam
POLE_TOP = (0, STERN - 0.16, 1.05)
hull.cyl((0, STERN - 0.16, DECK_Z1), POLE_TOP, 0.015, BRASS, 1)
hull_ob = hull.build()

# ---- cranks (animated, origin at the axle) -------------------------------------------------------------------------
cranks = {}
for seat, yr, name in (("Captain", Y_C, "Crank_F"), ("Stoker", Y_S, "Crank_R")):
    cz = G + hip_mid[seat].z - HIP_UP - CRANK_DOWN
    cy = yr + hip_mid[seat].y - CRANK_FWD
    p = Part(name)
    PIN_X = 0.095
    p.cyl((-PIN_X - 0.02, cy, cz), (PIN_X + 0.02, cy, cz), 0.014, BRASS, 1)
    for sx, phase in ((1, 0.0), (-1, math.pi)):           # left pin up at t = 0 (Pedal clips: left foot on top)
        tip = Vector((sx * PIN_X, cy - CRANK_R * math.sin(phase), cz + CRANK_R * math.cos(phase)))
        mid = (Vector((sx * PIN_X, cy, cz)) + tip) / 2
        p.box(tuple(mid), (0.02, 0.035, CRANK_R), BRASS, 1)
        p.cyl((sx * PIN_X, tip.y, tip.z), (sx * (PIN_X + 0.07), tip.y, tip.z), 0.012, BRASS, 1)
        p.cyl((sx * (PIN_X + 0.02), tip.y, tip.z), (sx * (PIN_X + 0.07), tip.y, tip.z), 0.022, NAVY, 0)
    cranks[name] = p.build(origin=(0, cy, cz))
    cranks[name].parent = hull_ob
    cranks[name].matrix_parent_inverse = Matrix.Identity(4)

# ---- paddle wheel -------------------------------------------------------------------------------------------------
w = Part("PaddleWheel")
for sx in (-1, 1):                                       # side rims: 12-gon rings, cream with a red face
    ring_o = [(sx * WHEEL_W / 2, WHEEL_Y + WHEEL_R * math.cos(2 * math.pi * i / 12), WHEEL_Z + WHEEL_R * math.sin(2 * math.pi * i / 12)) for i in range(12)]
    ring_i = [(sx * WHEEL_W / 2, WHEEL_Y + 0.6 * WHEEL_R * math.cos(2 * math.pi * i / 12), WHEEL_Z + 0.6 * WHEEL_R * math.sin(2 * math.pi * i / 12)) for i in range(12)]
    w.add(ring_o + ring_i, [[i, (i + 1) % 12, 12 + (i + 1) % 12, 12 + i] for i in range(12)], RED)
    w.add([(x + sx * 0.02, y, z) for x, y, z in ring_o] + [(x + sx * 0.02, y, z) for x, y, z in ring_i],
          [[i, 12 + i, 12 + (i + 1) % 12, (i + 1) % 12] for i in range(12)], CREAM)
for i in range(8):                                       # paddles
    t = 2 * math.pi * i / 8
    r_mid = 0.5 * WHEEL_R + 0.3 * WHEEL_R
    c = (0, WHEEL_Y + r_mid * math.cos(t), WHEEL_Z + r_mid * math.sin(t))
    w.box(c, (WHEEL_W - 0.02, 0.6 * WHEEL_R, 0.025), TEAL if i % 2 else CREAM,
          rot=Matrix.Rotation(t + math.pi / 2, 3, "X"))
w.cyl((-WHEEL_W / 2 - 0.05, WHEEL_Y, WHEEL_Z), (WHEEL_W / 2 + 0.05, WHEEL_Y, WHEEL_Z), 0.02, BRASS, 1)
wheel_ob = w.build(origin=(0, WHEEL_Y, WHEEL_Z))
wheel_ob.parent = hull_ob
wheel_ob.matrix_parent_inverse = Matrix.Identity(4)

# ---- flag ---------------------------------------------------------------------------------------------------------
fl = Part("Flag")
px, py, pz = POLE_TOP
fl.add([(0, py, pz), (0, py, pz - 0.14), (0, py + 0.26, pz - 0.07)], [[0, 1, 2]], RED)
fl.add([(0.004, py + 0.02, pz - 0.03), (0.004, py + 0.02, pz - 0.11), (0.004, py + 0.16, pz - 0.07)], [[0, 1, 2]], CREAM)
flag_ob = fl.build(origin=POLE_TOP)
flag_ob.parent = hull_ob
flag_ob.matrix_parent_inverse = Matrix.Identity(4)
flag_ob.data.materials[0] = PAINT
PAINT.use_backface_culling = False

# ---- seat sockets (goose rig origin goes here) ----------------------------------------------------------------------
sockets = {}
for seat, yr in (("Captain", Y_C), ("Stoker", Y_S)):
    e = bpy.data.objects.new("Seat_" + seat, None)
    e.empty_display_size = 0.1
    e.location = (0, yr, G)
    sc.collection.objects.link(e)
    e.parent = hull_ob
    sockets[seat] = e

# ---- Paddle clip: one turn per second about local +X on the wheel and both cranks ----------------------------------
for ob in (wheel_ob, cranks["Crank_F"], cranks["Crank_R"]):
    ob.rotation_mode = "XYZ"
    act = bpy.data.actions.new("Paddle_" + ob.name)
    ob.animation_data_create()
    ob.animation_data.action = act
    for f, ang in ((1, 0.0), (1 + FPS, 2 * math.pi)):
        ob.rotation_euler = Euler((ang, 0, 0))
        ob.keyframe_insert("rotation_euler", frame=f)
    for fc in act.fcurves if hasattr(act, "fcurves") else []:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"
    try:
        for layer in act.layers:
            for strip in layer.strips:
                for cb in strip.channelbags:
                    for fc in cb.fcurves:
                        for k in fc.keyframe_points:
                            k.interpolation = "LINEAR"
    except AttributeError:
        pass
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

# ---- export -------------------------------------------------------------------------------------------------------
tris = sum(len(p.vertices) - 2 for ob in (hull_ob, wheel_ob, flag_ob, *cranks.values()) for p in ob.data.polygons)
bpy.ops.object.select_all(action="DESELECT")
for ob in (hull_ob, wheel_ob, flag_ob, *cranks.values(), *sockets.values()):
    ob.select_set(True)
bpy.context.view_layer.objects.active = hull_ob
bpy.ops.export_scene.gltf(filepath=str(OUT_GLB), export_format="GLB", use_selection=True, export_yup=True,
                          export_animations=True, export_animation_mode="NLA_TRACKS", export_tangents=False,
                          export_optimize_animation_size=True, export_morph=False, export_skins=False,
                          export_vertex_color="ACTIVE", export_anim_slide_to_zero=True)


def yup(v):
    return [round(v.x, 4), round(v.z, 4), round(-v.y, 4)]


info = {"origin": "waterline centre", "up": "+Y", "forward": "+Z", "units": "metres",
        "length_m": STERN - BOW, "width_m": 2 * PONTOON_X + 2 * PONTOON_R, "deck_top_m": DECK_Z1,
        "draft_m": -(PONTOON_ZC - PONTOON_R), "tris": tris,
        "sockets": {"Seat_" + s: yup(Vector((0, y, G))) for s, y in (("Captain", Y_C), ("Stoker", Y_S))},
        "saddle_top": {s: yup(Vector((0, y + hip_mid[s].y, G + hip_mid[s].z - HIP_UP))) for s, y in (("Captain", Y_C), ("Stoker", Y_S))},
        "cranks": {n: yup(Vector(cranks[n].location)) for n in cranks},
        "crank_radius_m": CRANK_R, "paddle_wheel": yup(Vector((0, WHEEL_Y, WHEEL_Z))), "paddle_wheel_radius_m": WHEEL_R,
        "flag": yup(Vector(POLE_TOP)), "hip_up_above_saddle": HIP_UP,
        "clips": {"Paddle": {"duration": 1.0, "loop": True, "nodes": ["PaddleWheel", "Crank_F", "Crank_R"],
                             "note": "one full turn about local +X; play at the same rate as the geese's Pedal_* clips"}}}
(OUT / "pedalo_info.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
print("PEDALO", OUT_GLB, "tris", tris, json.dumps(info["sockets"]), json.dumps(info["cranks"]))

# ---- review sheet: both toy geese seated, pedalling ---------------------------------------------------------------
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
    sc.frame_set(1 + 7)                                    # left foot forward
    for ob in (wheel_ob, *cranks.values()):
        ob.rotation_euler = Euler((2 * math.pi * 7 / FPS, 0, 0))
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 900, 700
    sc.render.film_transparent = False
    sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.62, 0.70, 1)
    sc.world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = Euler((math.radians(50), math.radians(10), math.radians(-30)))
    sc.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.lens = 40
    target = Vector((0, 0.0, 0.85))
    views = {"front34": Vector((-3.0, -3.2, 1.9)), "side": Vector((-4.6, 0.0, 1.1)),
             "back34": Vector((2.8, 3.4, 1.8)), "top": Vector((-0.8, 0.3, 5.2))}
    rdir = ROOT / "renders" / "sandquest"
    rdir.mkdir(parents=True, exist_ok=True)
    tiles = []
    for name, loc in views.items():
        cam.location = loc
        cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = str(rdir / f"_pedalo_{name}.png")
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
    out.filepath_raw = str(rdir / "pedalo_sheet.png")
    out.file_format = "PNG"
    out.save()
    print("SHEET", out.filepath_raw)
