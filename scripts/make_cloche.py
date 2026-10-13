"""Modelled 1920s cloche hat (female cyclist): a deep bell crown on a head band ray-fitted to the goose's head, a
short downturned brim all round (longer at the front), a grosgrain ribbon band and a flat bow on one side.

  blender -b --factory-startup --python scripts/make_cloche.py -- --char outfit_female_cyclist

Recipe chars json "cloche_design" (metres, build frame -- for the female sliders the head is where the base
goose's head is):
  band_z, band_tilt, band_off   head band height (back), how much lower at the front, clearance off the head
  crown_h, crown_puff           crown height above the band, its fullness (fraction of the band radius)
  brim_front, brim_back, brim_droop   brim reach at the front / back, and how far it turns down (0..1)
  ribbon_h, bow_az, bow_w, bow_h      ribbon band height, bow position (degrees from the front, + = the goose's left)
  felt, ribbon (sRGB)
Clearance: the crown is kept "skin_clear" off every head mesh (the bill ridge, the eyes). Materials: felt, ribbon.
Writes shells/hat.glb + hat.json (dress_goose.py rigs "hat" to the Head bone).
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


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_female_cyclist")
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
C = cfg["cloche_design"]
OUT = ROOT / "out" / f"{CHAR}-goose" / "shells"
OUT.mkdir(parents=True, exist_ok=True)
NA = 72


def srgb(c):
    c = np.array(c[:3]) / 255.0
    return tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ROOT / "out" / "base-goose" / "base_goose_rigged.glb"))
heads = [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.name.startswith("Icosphere")]
body = next(o for o in heads if o.name.startswith("base_goose_game"))
dg = bpy.context.evaluated_depsgraph_get()
bvh = BVHTree.FromObject(body, dg)
ALL = [BVHTree.FromObject(o, dg) for o in heads]
V = np.array([(body.matrix_world @ v.co)[:] for v in body.data.vertices])
BZ = C["band_z"]
sl = V[(np.abs(V[:, 2] - BZ) < 0.006) & (V[:, 1] > -0.2)]
cy = float((sl[:, 1].min() + sl[:, 1].max()) / 2) + C.get("centre_dy", 0.0)


def dirv(th):
    return np.array([math.sin(th), -math.cos(th), 0.0])


def band_z(th):
    return BZ - C.get("band_tilt", 0.012) * (0.5 + 0.5 * math.cos(th))


ths = np.linspace(-math.pi, math.pi, NA, endpoint=False)
rb = []
for th in ths:
    z = band_z(th)
    c0 = np.array([0, cy, z])
    d = dirv(th)
    hit = bvh.ray_cast(Vector(c0 + d * 0.25), Vector(-d), 0.25)
    rb.append((np.linalg.norm((np.array(hit[0]) - c0)[:2]) if hit[0] else 0.06) + C.get("band_off", 0.008))
rb = np.array(rb)
for _ in range(8):
    rb = 0.25 * np.roll(rb, 1) + 0.5 * rb + 0.25 * np.roll(rb, -1)
rb = np.maximum(rb, np.max(rb) * C.get("round", 0.85))       # (a hat is rounder than the narrow goose head)
print("CLOCHE band radius mm", round(rb.min() * 1000), round(rb.max() * 1000), "centre y", round(cy, 3))


def clear_off(p, need):
    for b_ in ALL:
        loc, nrm, _, _ = b_.find_nearest(Vector(p), 0.08)
        if loc is not None:
            g_ = (Vector(p) - loc).dot(nrm)
            if g_ < need:
                p = p + np.array(nrm) * (need - g_)
    return p


bm = bmesh.new()
NK = 18
rings = []
for k in range(NK):
    s = k / NK
    ring = []
    for i, th in enumerate(ths):
        z = band_z(th) + C["crown_h"] * (1 - (1 - s) ** 1.7)
        rr = rb[i] * (1 - s ** 2.6) ** (1 / 2.6) * (1 + C.get("crown_puff", 0.06) * math.sin(math.pi * min(s * 1.2, 1)))
        p = np.array([0, cy, z]) + dirv(th) * rr
        p[2] = z
        if s > 0.05:
            p = clear_off(p, C.get("skin_clear", 0.012))
        ring.append(bm.verts.new(tuple(p)))
    rings.append(ring)
top = bm.verts.new((0.0, cy, max(v.co.z for v in rings[-1]) + 0.004))
for k in range(NK - 1):
    for i in range(NA):
        bm.faces.new((rings[k][i], rings[k][(i + 1) % NA], rings[k + 1][(i + 1) % NA], rings[k + 1][i]))
for i in range(NA):
    bm.faces.new((rings[-1][i], rings[-1][(i + 1) % NA], top))
# brim: from the band ring outward and down, longer at the front, a slight upturn at the very edge
NB = 7
brim = [rings[0]]
for j in range(1, NB + 1):
    u = j / NB
    ring = []
    for i, th in enumerate(ths):
        w = 0.5 + 0.5 * math.cos(th)
        reach = C["brim_back"] * (1 - w) + C["brim_front"] * w
        dr = reach * u
        dz = -reach * C.get("brim_droop", 0.6) * u ** 1.3 + C.get("brim_flip", 0.003) * max(u - 0.8, 0) / 0.2
        p = np.array([0, cy, band_z(th)]) + dirv(th) * (rb[i] + dr)
        p[2] = band_z(th) + dz
        ring.append(bm.verts.new(tuple(p)))
    brim.append(ring)
for j in range(NB):
    for i in range(NA):
        bm.faces.new((brim[j + 1][i], brim[j + 1][(i + 1) % NA], brim[j][(i + 1) % NA], brim[j][i]))
me = bpy.data.meshes.new("hat")
bm.to_mesh(me)
bm.free()
hat = bpy.data.objects.new("hat_shell", me)
bpy.context.scene.collection.objects.link(hat)
for o in bpy.context.scene.objects:
    if o is not hat:
        o.hide_render = True
bpy.ops.object.select_all(action="DESELECT")
hat.select_set(True)
bpy.context.view_layer.objects.active = hat
sub = hat.modifiers.new("sub", "SUBSURF")
sub.levels = 1
bpy.ops.object.modifier_apply(modifier=sub.name)
for v in hat.data.vertices:                  # the bill ridge between the vertices: one pass on the dense mesh
    if v.co.z > BZ - 0.02:
        v.co = Vector(clear_off(np.array(v.co[:]), C.get("skin_clear", 0.012) + C.get("thickness", 0.003)))
sol = hat.modifiers.new("sol", "SOLIDIFY")
sol.thickness = C.get("thickness", 0.003)
sol.offset = -1.0
bpy.ops.object.modifier_apply(modifier=sol.name)
felt = bpy.data.materials.new(f"{CHAR}_hat_felt")
felt.use_nodes = True
bs = felt.node_tree.nodes["Principled BSDF"]
bs.inputs["Base Color"].default_value = srgb(C.get("felt", [40, 70, 50]))
bs.inputs["Roughness"].default_value = 0.92
me.materials.append(felt)
rib = bpy.data.materials.new(f"{CHAR}_hat_ribbon")
rib.use_nodes = True
bs2 = rib.node_tree.nodes["Principled BSDF"]
bs2.inputs["Base Color"].default_value = srgb(C.get("ribbon", [190, 140, 50]))
bs2.inputs["Roughness"].default_value = 0.55

# ribbon band: a ring just outside the crown's base, ribbon_h tall
rbm = bmesh.new()
rh = C.get("ribbon_h", 0.02)
NR = 3
rr_rings = []
for j in range(NR):
    zf = j / (NR - 1)
    ring = []
    for i, th in enumerate(ths):
        z = band_z(th) + 0.002 + rh * zf
        rr = rb[i] * (1 + C.get("crown_puff", 0.06) * 0.15) + C.get("ribbon_off", 0.004)
        hit = None
        p = np.array([0, cy, z]) + dirv(th) * (rr + 0.05)
        loc = None
        h_ = BVHTree.FromObject(hat, bpy.context.evaluated_depsgraph_get()).ray_cast(Vector(p), Vector(-dirv(th)), 0.1)
        if h_[0] is not None:
            p = np.array(h_[0]) + dirv(th) * C.get("ribbon_off", 0.003)
        ring.append(rbm.verts.new(tuple(p)))
    rr_rings.append(ring)
for j in range(NR - 1):
    for i in range(NA):
        rbm.faces.new((rr_rings[j][i], rr_rings[j][(i + 1) % NA], rr_rings[j + 1][(i + 1) % NA], rr_rings[j + 1][i]))
# bow: two flat loops + a knot, standing on the ribbon at bow_az
az = math.radians(C.get("bow_az", 70))
i0 = int(round((az + math.pi) / (2 * math.pi) * NA)) % NA
cpt = np.mean([np.array(rr_rings[j][i0].co) for j in range(NR)], axis=0)
n_ = dirv(az)
t_ = np.array([math.cos(az), math.sin(az), 0.0])
up = np.array([0, 0, 1.0])
bw, bh = C.get("bow_w", 0.05), C.get("bow_h", 0.024)


def loop(sign):
    if C.get("bow_flat"):
        # a flat loop of ribbon: a filled lobe in the hat's surface plane, pinched at the knot, rounded at the end
        NL = 16
        ctr_ = rbm.verts.new(tuple(cpt + n_ * 0.005 + t_ * sign * bw * 0.25))
        rim_ = []
        for a_ in range(NL):
            ang = 2 * math.pi * a_ / NL
            x_ = sign * bw * 0.25 * (1 + math.cos(ang))
            y_ = bh / 2 * math.sin(ang) * (0.35 + 0.65 * (1 + math.cos(ang)) / 2)
            rim_.append(rbm.verts.new(tuple(cpt + n_ * (0.004 + 0.003 * (1 + math.cos(ang)) / 2) + t_ * x_ + up * y_)))
        for a_ in range(NL):
            rbm.faces.new((ctr_, rim_[a_], rim_[(a_ + 1) % NL]))
        return
    vs = []
    NL, NW = 14, 3
    for a_ in range(NL):
        ang = 2 * math.pi * a_ / NL
        for w_ in range(NW):
            off = (w_ - 1) * 0.0015
            x_ = sign * (bw / 4) * (1 - math.cos(ang)) + sign * 0.004
            y_ = (bh / 2) * math.sin(ang) * (0.6 + 0.4 * (1 - math.cos(ang)) / 2)
            vs.append(cpt + n_ * (0.004 + off + 0.003 * math.sin(ang / 2)) + t_ * x_ + up * y_)
    vv = [rbm.verts.new(tuple(v)) for v in vs]
    for a_ in range(NL):
        for w_ in range(NW - 1):
            a0 = a_ * NW + w_
            b0 = ((a_ + 1) % NL) * NW + w_
            rbm.faces.new((vv[a0], vv[b0], vv[b0 + 1], vv[a0 + 1]))


loop(1)
loop(-1)
kn = [cpt + n_ * 0.006 + t_ * sx * 0.006 + up * sz * 0.008 for sx in (-1, 1) for sz in (-1, 1)]
kk = [rbm.verts.new(tuple(v)) for v in kn]
rbm.faces.new((kk[0], kk[2], kk[3], kk[1]))
rme = bpy.data.meshes.new("ribbon")
rbm.to_mesh(rme)
rbm.free()
ro = bpy.data.objects.new("ribbon", rme)
bpy.context.scene.collection.objects.link(ro)
rme.materials.append(rib)
bpy.ops.object.select_all(action="DESELECT")
ro.select_set(True)
sol2 = ro.modifiers.new("sol", "SOLIDIFY")
sol2.thickness = 0.0015
bpy.context.view_layer.objects.active = ro
bpy.ops.object.modifier_apply(modifier=sol2.name)
ro.select_set(True)
hat.select_set(True)
bpy.context.view_layer.objects.active = hat
bpy.ops.object.join()
bpy.ops.object.shade_smooth()
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.quads_convert_to_tris()
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.006)
bpy.ops.object.mode_set(mode="OBJECT")
tris = len(hat.data.polygons)
bpy.ops.export_scene.gltf(filepath=str(OUT / "hat.glb"), use_selection=True, export_format="GLB")
(OUT / "hat.json").write_text(json.dumps({"char": CHAR, "piece": "hat", "tris": tris, "source": "make_cloche.py (modelled)",
                                          "design": C}, indent=1), encoding="utf-8")
print("CAP cloche", tris)
