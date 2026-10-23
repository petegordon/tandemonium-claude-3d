"""Round wire spectacles for a goose: a rim in front of each eye, a bridge over the top of the beak, temple arms back
along the sides of the head. Rigid on the Head bone (chars json "rigid": {"spectacles": "Head"}).

  blender -b --factory-startup --python scripts/make_spectacles.py -- --char outfit_grandpa
  blender -b --factory-startup --python scripts/shell_to_shape.py -- --char outfit_grandpa --piece spectacles --fresh

Built on the BASE goose's head (eyeballs, lids, body), like the hats; shell_to_shape.py carries it to a slider-shaped
character (its Head map). Recipe: chars json "spectacles_design" (metres, base head), all optional:
  lens_r 0.019          rim radius
  wire_r 0.0011         wire thickness (radius)
  gap 0.006             rim centre this far outside the eye / lid surface along the eye's look direction
  face_fwd 0.45         0 = each lens faces along its eye (sideways), 1 = straight forward; the rim plane between
  shift [0, 0, 0]       extra offset of the lens centres (x is mirrored)
  bridge_clear 0.004    the bridge stands this far in front of the face (over the beak base)
  bridge_rise 0.006     ... at this height above the lens centres
  temple_len 0.085      temple arm length back from the rim (along y)
  temple_clear 0.003    off the side of the head
  temple_drop 0.012     the arm's end hooks down by this much
  color [196, 156, 72]  gold (metallic); roughness 0.3
  lens_alpha 0.0        > 0: a faint glass disc in each rim (alpha blend)
  perch {...}           opt-in: reading glasses perched DOWN THE BILL, away from the eyes (Pete 2026-10-23) instead of
                        a rim in front of each eye. Keys (all optional):
     y -0.2             lens centres this far along the bill (base frame; bill tip -0.288, forehead -0.15)
     x 0.024            lens centre half-spacing
     clear 0.0015       rims stand this far off the bill (each lens is raised until every rim point clears it)
     face_fwd 0.75      0 = lens faces sideways, 1 = straight ahead
     tilt 12            degrees the lens tops lean back
     sink 0.45          start height: lens centre this many lens radii above the bill top (then raised to clear)
     temple_z -0.004    the temples' height at the head relative to the lens centres (they pass under the eye)
     temple_end -0.02   y where the temples end (behind the eye), hooking down by temple_drop
Writes out/<char>-goose/shells/spectacles.glb + spectacles.json and renders/<char>_spectacles.png.
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
CHAR = argv[argv.index("--char") + 1]
ROOT = Path(__file__).resolve().parents[1]
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
SD = cfg.get("spectacles_design", {})
LENS_R = SD.get("lens_r", 0.019)
WIRE = SD.get("wire_r", 0.0011)
OUT = ROOT / "out" / f"{CHAR}-goose" / "shells"
OUT.mkdir(parents=True, exist_ok=True)


def srgb(c):
    c = np.array(c[:3]) / 255.0
    return tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ROOT / "out" / "base-goose" / "base_goose_rigged.glb"))
dg = bpy.context.evaluated_depsgraph_get()
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.name.startswith("Icosphere")]
body = next(o for o in meshes if o.name.startswith("base_goose_game"))
def world_bvh(o):
    me = o.evaluated_get(dg).to_mesh()
    return BVHTree.FromPolygons([tuple(o.matrix_world @ v.co) for v in me.vertices], [tuple(p.vertices) for p in me.polygons])


head_bvh = [world_bvh(o) for o in meshes]       # (FromObject is in each object's local space; the eye parts sit on bones)
body_bvh = world_bvh(body)
rig = next(o for o in bpy.context.scene.objects if o.type == "ARMATURE")


def cast(o, d, far=0.5, trees=None):
    """Nearest hit of any head part along a ray."""
    best = None
    for t in (trees or head_bvh):
        h = t.ray_cast(Vector(o), Vector(d), far)
        if h[0] is not None and (best is None or h[3] < best[1]):
            best = (np.array(h[0]), h[3])
    return best


def eye(side):
    b = rig.data.bones[f"{side}Eye"]
    h = np.array(rig.matrix_world @ b.head_local)
    t = np.array(rig.matrix_world @ b.tail_local)
    return h, (t - h) / np.linalg.norm(t - h)


fwd = np.array([0.0, -1.0, 0.0])
lens = {}
PERCH = SD.get("perch")
if PERCH is not None:
    py_, px_ = PERCH.get("y", -0.2), PERCH.get("x", 0.024)
    top = cast(np.array([0.0, py_, 2.0]), (0, 0, -1), trees=[body_bvh])     # the bill ridge here
    ztop = top[0][2] if top else 1.54
    for side, sg in (("Left", 1), ("Right", -1)):
        ff = PERCH.get("face_fwd", 0.75)
        n = np.array([sg * (1 - ff), -ff, 0.0])
        n /= np.linalg.norm(n)
        tl = math.radians(PERCH.get("tilt", 12))                       # lens top leans back (toward +y)
        n = n * math.cos(tl) + np.array([0.0, 0.0, math.sin(tl)])
        n /= np.linalg.norm(n)
        up = np.array([0.0, 0.0, 1.0])
        u = np.cross(up, n)
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        c = np.array([sg * px_, py_, ztop + PERCH.get("sink", 0.45) * LENS_R]) + np.array(SD.get("shift", [0.0, 0.0, 0.0])) * np.array([sg, 1, 1])
        for _ in range(200):                                          # raise until every rim point clears the bill
            bad = False
            for a in np.linspace(0, 2 * math.pi, 48, endpoint=False):
                p = c + LENS_R * (math.cos(a) * u + math.sin(a) * v)
                loc, nor, _i, dist = body_bvh.find_nearest(Vector(p))
                if loc is not None and (np.dot(p - np.array(loc), np.array(nor)) < 0 or dist < PERCH.get("clear", 0.0015) + WIRE):
                    bad = True
                    break
            if not bad:
                break
            c = c + np.array([0.0, 0.0, 0.0005])
        lens[side] = (c, n, u, v, sg)
        print("LENS perch", side, np.round(c, 4).tolist(), "normal", np.round(n, 3).tolist(), "bill top", round(ztop, 4))
for side, sg in (() if PERCH is not None else (("Left", 1), ("Right", -1))):
    c0, d = eye(side)
    o = c0 + d * 0.2                                        # from outside back toward the eye: first head-part hit
    hit = cast(o, -d)
    surf = hit[0] if hit else c0 + d * 0.025
    n = d * (1 - SD.get("face_fwd", 0.45)) + fwd * SD.get("face_fwd", 0.45)
    n /= np.linalg.norm(n)
    sh = np.array(SD.get("shift", [0.0, 0.0, 0.0])) * np.array([sg, 1, 1])
    c = surf + d * SD.get("gap", 0.006) + sh
    up = np.array([0.0, 0.0, 1.0])
    u = np.cross(up, n)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    lens[side] = (c, n, u, v, sg)
    print("LENS", side, np.round(c, 4).tolist(), "normal", np.round(n, 3).tolist())


def ring_pts(c, u, v, r, k=40):
    return [c + r * (math.cos(a) * u + math.sin(a) * v) for a in np.linspace(0, 2 * math.pi, k, endpoint=False)]


def tube(name, pts, closed=False, r=WIRE, seg=8):
    pts = [np.array(p, float) for p in pts]
    bm = bmesh.new()
    rings = []
    m = len(pts)
    for i, p in enumerate(pts):
        a = pts[(i - 1) % m] if (closed or i > 0) else p
        b = pts[(i + 1) % m] if (closed or i < m - 1) else p
        t = b - a
        t /= max(np.linalg.norm(t), 1e-9)
        ref = np.array([0, 0, 1.0]) if abs(t[2]) < 0.9 else np.array([1.0, 0, 0])
        x = np.cross(t, ref)
        x /= np.linalg.norm(x)
        y = np.cross(t, x)
        rings.append([bm.verts.new(p + r * (math.cos(q) * x + math.sin(q) * y)) for q in np.linspace(0, 2 * math.pi, seg, endpoint=False)])
    for i in range(m if closed else m - 1):
        r0, r1 = rings[i], rings[(i + 1) % m]
        for j in range(seg):
            bm.faces.new((r0[j], r0[(j + 1) % seg], r1[(j + 1) % seg], r1[j]))
    if not closed:
        for rr, rev in ((rings[0], True), (rings[-1], False)):
            bm.faces.new(list(reversed(rr)) if rev else rr)
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


parts = []
for side, (c, n, u, v, sg) in lens.items():
    parts.append(tube(f"rim_{side}", ring_pts(c, u, v, LENS_R), closed=True))
# bridge: inner rim points (toward x = 0), arching over the beak top
inner = {s: c - np.sign(c[0]) * LENS_R * u * np.sign(u[0]) for s, (c, n, u, v, sg) in lens.items()}
mid = (inner["Left"] + inner["Right"]) / 2
# the bridge crosses the FRONT of the face (over the top of the beak base) a little above the lens centres:
# cast from in front, at x = 0, and stand bridge_clear off that surface
zb = mid[2] + SD.get("bridge_rise", 0.006)
if PERCH is not None:                       # over the bill ridge: a small saddle arch, bridge_clear above the ridge
    rt = cast(np.array([0.0, mid[1], 2.0]), (0, 0, -1), trees=[body_bvh])
    peak = np.array([0.0, mid[1], max(zb, (rt[0][2] if rt else mid[2]) + SD.get("bridge_clear", 0.004) + 2 * WIRE)])
else:
    front = cast(np.array([0.0, -0.6, zb]), (0, 1, 0), trees=[body_bvh])
    fy = front[0][1] if front else mid[1]
    peak = np.array([0.0, min(fy - SD.get("bridge_clear", 0.004), mid[1]), zb])
bez = [(1 - t) ** 2 * inner["Right"] + 2 * (1 - t) * t * (2 * peak - (inner["Left"] + inner["Right"]) / 2) + t ** 2 * inner["Left"]
       for t in np.linspace(0, 1, 16)]
parts.append(tube("bridge", bez))
# temples: from the rim's back-most point along the side of the head, then a small hook down
for side, (c, n, u, v, sg) in lens.items():
    ring = ring_pts(c, u, v, LENS_R)
    if PERCH is not None:                 # perched: from the rim's outer point back along the cheek, under the eye
        p0 = max(ring, key=lambda p: sg * p[0] + 0.5 * p[1])
        y_end, zt = PERCH.get("temple_end", -0.02), c[2] + PERCH.get("temple_z", -0.004)
        pts = [p0]
        for t in np.linspace(0.06, 1.0, 22):
            y = p0[1] + (y_end - p0[1]) * t
            z = p0[2] + (zt - p0[2]) * min(1.0, t * 2.5) - SD.get("temple_drop", 0.012) * max(0.0, (t - 0.85) / 0.15) ** 2
            h = cast(np.array([sg * 0.3, y, z]), (-sg, 0, 0))            # all head parts (eyes, lids) as well
            x = (h[0][0] + sg * SD.get("temple_clear", 0.003)) if h else p0[0]
            x = sg * max(sg * x, sg * p0[0] - 0.004 * t) if t < 0.2 else x
            pts.append(np.array([x, y, z]))
        P = np.array(pts)                     # a smooth wire: the clearance is kept as an outer envelope, then eased
        X = sg * P[:, 0]
        for _ in range(3):
            Xs = X.copy()
            Xs[1:-1] = (X[:-2] + X[1:-1] + X[2:]) / 3
            X = np.maximum(X, Xs) if _ == 0 else Xs
        X = np.maximum.accumulate(X) if PERCH.get("temple_flare", True) else X     # never cuts back in toward the head
        P[:, 0] = sg * X
        parts.append(tube(f"temple_{side}", list(P)))
        continue
    p0 = max(ring, key=lambda p: p[1] + 0.3 * abs(p[0]))   # back and outer
    y_end = p0[1] + SD.get("temple_len", 0.085)
    pts = [p0]
    for t in np.linspace(0.08, 1.0, 14):
        y = p0[1] + (y_end - p0[1]) * t
        z = p0[2] + 0.002 * math.sin(t * math.pi) - SD.get("temple_drop", 0.012) * max(0.0, (t - 0.8) / 0.2) ** 2
        h = cast(np.array([sg * 0.3, y, z]), (-sg, 0, 0), trees=[body_bvh])
        x = (h[0][0] + sg * SD.get("temple_clear", 0.003)) if h else p0[0]
        x = sg * max(sg * x, sg * p0[0] - 0.012) if t < 0.25 else x
        pts.append(np.array([x, y, z]))
    parts.append(tube(f"temple_{side}", pts))
mat = bpy.data.materials.new(f"{CHAR}_spectacles_gold")
mat.use_nodes = True
bs = mat.node_tree.nodes["Principled BSDF"]
bs.inputs["Base Color"].default_value = srgb(SD.get("color", [196, 156, 72]))
bs.inputs["Metallic"].default_value = 1.0
bs.inputs["Roughness"].default_value = SD.get("roughness", 0.3)
for o in parts:
    o.data.materials.append(mat)
if SD.get("lens_alpha", 0.0) > 0:
    gl = bpy.data.materials.new(f"{CHAR}_spectacles_glass")
    gl.use_nodes = True
    gb = gl.node_tree.nodes["Principled BSDF"]
    gb.inputs["Base Color"].default_value = (0.9, 0.95, 1.0, 1.0)
    gb.inputs["Alpha"].default_value = SD["lens_alpha"]
    gb.inputs["Roughness"].default_value = 0.05
    gl.blend_method = "BLEND"
    for side, (c, n, u, v, sg) in lens.items():
        bm = bmesh.new()
        vs = [bm.verts.new(p) for p in ring_pts(c, u, v, LENS_R - WIRE)]
        bm.faces.new(vs)
        me = bpy.data.meshes.new(f"lens_{side}")
        bm.to_mesh(me)
        bm.free()
        ob = bpy.data.objects.new(f"lens_{side}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.data.materials.append(gl)
        parts.append(ob)
bpy.ops.object.select_all(action="DESELECT")
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
sp = bpy.context.view_layer.objects.active
sp.name = "spectacles"
bpy.ops.object.shade_smooth()
for o in list(bpy.data.objects):
    if o is not sp:
        bpy.data.objects.remove(o)
bpy.ops.object.select_all(action="DESELECT")
sp.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(OUT / "spectacles.glb"), export_format="GLB", use_selection=True, export_animations=False)
tris = sum(len(p.vertices) - 2 for p in sp.data.polygons)
info = {"char": CHAR, "piece": "spectacles", "source": "make_spectacles.py (modelled, base head)", "tris": tris,
        "rigid": "Head", "lens_r": LENS_R, "lens_centres": {s: np.round(l[0], 4).tolist() for s, l in lens.items()}}
(OUT / "spectacles.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
print("SPECTACLES", json.dumps(info))
