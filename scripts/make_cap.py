"""Modelled tweed flat cap (1920s cyclist): a soft crown on a head band fitted to the goose's head, its top pulled forward
and down over a short stiff peak; a covered button on top.

  blender -b --factory-startup --python scripts/make_cap.py -- --char outfit_male_cyclist

Recipe chars json "cap_design" (metres, base-body frame):
  band_z, band_tilt     head band height at the back, how much lower it sits at the front (the peak over the brow)
  band_off              band clearance off the head (rays from the head axis at that height)
  top_back, top_front   crown height above the band at the back / front
  overhang              how far the top is pulled forward over the peak
  puff                  the crown's sideways fullness (fraction of the band radius, mid-height)
  peak_len, peak_droop, peak_half_angle   the peak's reach at the front, its drop at the edge, its extent round the band
  button_r              the covered button on top
One material (tweed: pattern_paint.py "patterns.hat" paints the herringbone). Writes shells/hat.glb + hat.json (the
name dress_goose.py rigs to the Head bone) and renders/<char>_shell_hat.png.
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_cyclist")
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
C = cfg["cap_design"]
OUT = ROOT / "out" / f"{CHAR}-goose" / "shells"
OUT.mkdir(parents=True, exist_ok=True)
NA, NK = 64, 16


def srgb(c):
    c = np.array(c[:3]) / 255.0
    return tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ROOT / "out" / "base-goose" / "base_goose_rigged.glb"))
body = next(o for o in bpy.context.scene.objects if o.type == "MESH" and o.name.startswith("base_goose_game"))
bvh = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
head_objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
ALL_BVH = [BVHTree.FromObject(o, bpy.context.evaluated_depsgraph_get()) for o in head_objs]   # body + eyes, beak parts

# head axis: the slice of the head at the band height (vertices within 6 mm), its x/y centre
V = np.array([(body.matrix_world @ v.co)[:] for v in body.data.vertices])
BZ = C["band_z"]
sl = V[(np.abs(V[:, 2] - BZ) < 0.006) & (V[:, 1] > -0.2)]
cy = float((sl[:, 1].min() + sl[:, 1].max()) / 2) + C.get("centre_dy", 0.0)
top_z = float(V[(np.abs(V[:, 0]) < 0.02) & (np.abs(V[:, 1] - cy) < 0.03), 2].max())
print("CAP head slice y", round(float(sl[:, 1].min()), 3), round(float(sl[:, 1].max()), 3), "centre", round(cy, 3),
      "head top", round(top_z, 3))


def dirv(th):
    return np.array([math.sin(th), -math.cos(th), 0.0])          # 0 = front (-y), + = the goose's left (+x)


ths = np.linspace(-math.pi, math.pi, NA, endpoint=False)
tilt = C.get("band_tilt", 0.012)


def band_z(th):
    return BZ - tilt * (0.5 + 0.5 * math.cos(th))


rb = []
for th in ths:
    z = band_z(th)
    c = np.array([0, cy, z])
    d = dirv(th)
    hit = bvh.ray_cast(Vector(c + d * 0.25), Vector(-d), 0.25)
    rb.append((np.linalg.norm((np.array(hit[0]) - c)[:2]) if hit[0] else 0.06) + C.get("band_off", 0.006))
rb = np.array(rb)
for _ in range(6):                                  # a smooth band (the head's feathers are bumpy)
    rb = 0.25 * np.roll(rb, 1) + 0.5 * rb + 0.25 * np.roll(rb, -1)
print("CAP band radius mm min/max", round(rb.min() * 1000), round(rb.max() * 1000))

bm = bmesh.new()
rings = []
A = math.radians(C.get("peak_half_angle", 70))


def peak_drop(th, reach_frac):
    return C.get("peak_droop", 0.02) * reach_frac ** 1.6 * max(math.cos(th / A * math.pi / 2), 0) ** 0.5


for k in range(NK + 1):
    s = k / NK
    ring = []
    for i, th in enumerate(ths):
        w = 0.5 + 0.5 * math.cos(th)
        H = C["top_back"] * (1 - w) + C["top_front"] * w
        # at the front the crown's lower edge is snapped down ONTO the peak, "attach" metres out from the band
        att = C.get("attach", 0.0) * max(math.cos(th / A * math.pi / 2), 0) ** 2 if abs(th) <= A else 0.0
        z0 = band_z(th) - (peak_drop(th, att / C["peak_len"]) if att else 0.0) - C.get("seat_in", 0.0) * (att > 0)
        z = z0 + H * (1 - (1 - s) ** 2.2) if s < 1 else z0 + H
        # flat top: the radius holds out wide, then closes quickly (superellipse); puffed out at mid-height
        rr = (rb[i] + att * (1 - s) ** 0.7) * (1 - s ** 3.5) ** (1 / 3.5) * (1 + C.get("puff", 0.15) * (1 - C.get("puff_front_cut", 0.0) * w * w) * math.sin(math.pi * min(s * 1.3, 1)) ** 0.8)
        rr *= 1 + C.get("front_wide", 0.08) * w * s       # the front panel spreads over the peak
        ctr = np.array([0, cy - C.get("overhang", 0.04) * s ** 1.3, 0])
        p = ctr + dirv(th) * rr
        p[2] = z - C.get("front_drop", 0.012) * w * s ** 2
        if s > 0.04:           # never into the head: the crown's upper part stays "clear" above the head's top
            for bv_ in ALL_BVH:
                hh = bv_.ray_cast(Vector((p[0], p[1], 2.0)), Vector((0, 0, -1)), 0.5)
                if hh[0] is not None and hh[0].z > band_z(th):
                    p[2] = max(p[2], hh[0].z + C.get("clear", 0.01) * min((s - 0.04) / 0.15, 1))
        if s > 0:              # nor through the brow / bill ridge in front: push out along the nearest surface normal
            for bv_ in ALL_BVH:
                loc_, nrm_, _, dist_ = bv_.find_nearest(Vector(p), 0.06)
                if loc_ is not None:
                    gap_ = (Vector(p) - loc_).dot(nrm_)
                    need_ = C.get("skin_clear", 0.008)
                    if gap_ < need_:
                        p = p + np.array(nrm_) * (need_ - gap_)
        ring.append(bm.verts.new(tuple(p)))
    rings.append(ring)
for k in range(NK):
    for i in range(NA):
        a, b = rings[k][i], rings[k][(i + 1) % NA]
        c_, d_ = rings[k + 1][(i + 1) % NA], rings[k + 1][i]
        if k == NK - 1:
            continue
        bm.faces.new((a, b, c_, d_))
top_c = bm.verts.new(tuple(np.mean([v.co for v in rings[NK - 1]], axis=0) + Vector((0, 0, 0.002))))
for i in range(NA):
    bm.faces.new((rings[NK - 1][i], rings[NK - 1][(i + 1) % NA], top_c))
for v in rings[NK]:
    bm.verts.remove(v)
# peak: a stiff crescent from the band at the front, drooping a little at its edge
A = math.radians(C.get("peak_half_angle", 70))
pk = [i for i, th in enumerate(ths) if abs(th) <= A]
NP = 6
prow = []
for j in range(NP + 1):
    u = j / NP
    row = []
    for i in pk:
        th = ths[i]
        reach = C["peak_len"] * math.cos(th / A * math.pi / 2) ** 0.6
        p = np.array([0, cy, 0]) + dirv(th) * (rb[i] - 0.004 + reach * u)
        p[2] = band_z(th) - 0.002 - C.get("peak_droop", 0.02) * u ** 1.6 * math.cos(th / A * math.pi / 2) ** 0.5
        row.append(bm.verts.new(tuple(p)))
    prow.append(row)
for j in range(NP):
    for i in range(len(pk) - 1):
        bm.faces.new((prow[j][i], prow[j + 1][i], prow[j + 1][i + 1], prow[j][i + 1]))
me = bpy.data.meshes.new("hat")
bm.to_mesh(me)
bm.free()
cap = bpy.data.objects.new("hat_shell", me)
bpy.context.scene.collection.objects.link(cap)
for o in head_objs + [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]:
    o.hide_render = True
bpy.ops.object.select_all(action="DESELECT")
cap.select_set(True)
bpy.context.view_layer.objects.active = cap
sub = cap.modifiers.new("sub", "SUBSURF")
sub.levels = 1
bpy.ops.object.modifier_apply(modifier=sub.name)
# the bill's narrow top ridge ran up between the crown's vertices: a clearance pass on the dense (subdivided) surface,
# everything inside "skin_clear" + the cloth thickness pushed out along the head's normal, twice with a relax between
for _pass in range(2):
    for v in [v_ for v_ in cap.data.vertices if v_.co.z > BZ - tilt + 0.004]:     # (crown only: the peak stays flat)
        for bv_ in ALL_BVH:
            loc_, nrm_, _, _ = bv_.find_nearest(v.co, 0.06)
            if loc_ is not None:
                gap_ = (v.co - loc_).dot(nrm_)
                need_ = C.get("skin_clear", 0.008) + C.get("thickness", 0.003)
                if gap_ < need_:
                    v.co = v.co + nrm_ * (need_ - gap_)
    if _pass == 0:
        sm_ = cap.modifiers.new("relax", "SMOOTH")
        sm_.iterations = 3
        sm_.factor = 0.5
        bpy.ops.object.modifier_apply(modifier=sm_.name)
sol =cap.modifiers.new("sol", "SOLIDIFY")
sol.thickness = C.get("thickness", 0.003)
sol.offset = -1.0
bpy.ops.object.modifier_apply(modifier=sol.name)
# panel seams + the button: a covered button at the top, six seams from it (a groove via a vertex-colour-free bump
# is not portable to glTF: the seams are painted by pattern_paint.py; the button is geometry)
topv = np.array(top_c.co[:]) if False else None
mat = bpy.data.materials.new(f"{CHAR}_hat_tweed")
mat.use_nodes = True
bs = mat.node_tree.nodes["Principled BSDF"]
bs.inputs["Base Color"].default_value = srgb(C.get("color", [110, 86, 64]))
bs.inputs["Roughness"].default_value = 0.92
me.materials.append(mat)
# button: dome at the crown's highest point
Vc = np.array([(v.co)[:] for v in me.vertices])
tp = Vc[np.argmax(Vc[:, 2])]
br = C.get("button_r", 0.009)
bb = bmesh.new()
nv, nu = 6, 16
vs = []
for i in range(nv + 1):
    ph = math.pi / 2 * i / nv
    for k in range(nu):
        a = 2 * math.pi * k / nu
        vs.append(bb.verts.new((tp[0] + br * math.cos(ph) * math.cos(a), tp[1] + br * math.cos(ph) * math.sin(a),
                                tp[2] - 0.002 + br * 0.55 * math.sin(ph))))
for i in range(nv):
    for k in range(nu):
        bb.faces.new((vs[i * nu + k], vs[i * nu + (k + 1) % nu], vs[(i + 1) * nu + (k + 1) % nu], vs[(i + 1) * nu + k]))
bme = bpy.data.meshes.new("button")
bb.to_mesh(bme)
bb.free()
bo = bpy.data.objects.new("button", bme)
bpy.context.scene.collection.objects.link(bo)
bme.materials.append(mat)
bpy.ops.object.select_all(action="DESELECT")
bo.select_set(True)
cap.select_set(True)
bpy.context.view_layer.objects.active = cap
bpy.ops.object.join()
bpy.ops.object.shade_smooth()
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.mesh.quads_convert_to_tris()
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.006)
bpy.ops.object.mode_set(mode="OBJECT")
tris = len(me.polygons)
bpy.ops.export_scene.gltf(filepath=str(OUT / "hat.glb"), use_selection=True, export_format="GLB")
(OUT / "hat.json").write_text(json.dumps({"char": CHAR, "piece": "hat", "tris": tris, "source": "make_cap.py (modelled)",
                                          "design": C, "head_centre_y": cy}, indent=1), encoding="utf-8")
print("CAP", json.dumps({"tris": tris, "centre_y": round(cy, 4)}))
