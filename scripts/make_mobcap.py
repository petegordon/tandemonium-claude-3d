"""Modelled Victorian mob cap (Grandma): a soft puffy crown gathered onto a head band that is tilted (just above the eyes
at the front, down at the nape at the back), a deep ruffled frill all round, a satin ribbon round the band and a bow
at the front.

  blender -b --factory-startup --python scripts/make_mobcap.py -- --char outfit_grandma

Recipe chars json "mobcap_design" (metres, BUILD frame):
  band_z, band_tilt, band_off   band height at the side, how much higher at the front / lower at the back, clearance
  crown_h, crown_puff, top_back crown top above the head top, how far the pouf swells past the band, top shift back (+y)
  gathers, gather_amp           gathered folds round the crown (count, fraction of the radius)
  frill_w, frill_droop, frill_n, frill_amp, frill_wave   frill width, droop (0..1), ruffles, radial / vertical ruffle
  ribbon_h, ribbon_off, bow_az, bow_w, bow_h            ribbon band + bow (degrees from the front)
  cotton, ribbon (sRGB), skin_clear, thickness
The head comes from the character's naked shaped body (out/<char>-goose/<char>_naked_dressed.glb) moved back into the
build frame (- build_frame_lift), so a slider body's head (shorter, scaled) is fitted, not the base goose's.
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
CHAR = opt("--char", "outfit_grandma")
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
C = cfg["mobcap_design"]
LIFT = cfg.get("build_frame_lift", 0.0)
OUT = ROOT / "out" / f"{CHAR}-goose" / "shells"
OUT.mkdir(parents=True, exist_ok=True)
NA = C.get("na", 128)


def srgb(c):
    c = np.array(c[:3]) / 255.0
    return tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)


bpy.ops.wm.read_factory_settings(use_empty=True)
naked = ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_naked_dressed.glb"
bpy.ops.import_scene.gltf(filepath=str(naked if naked.exists() else ROOT / "out" / "base-goose" / "base_goose_rigged.glb"))
if not naked.exists():
    LIFT = 0.0
for o in bpy.context.scene.objects:            # back into the build frame
    if o.parent is None:
        o.location.z -= LIFT
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
heads = [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.name.startswith("Icosphere")]
body = next(o for o in heads if o.name.startswith("body") or o.name.startswith("base_goose_game"))


def world_bvh(o):
    me = o.evaluated_get(dg).to_mesh()
    vs = [o.matrix_world @ v.co for v in me.vertices]
    return BVHTree.FromPolygons(vs, [tuple(p.vertices) for p in me.polygons]), np.array([v[:] for v in vs])


bvh, V = world_bvh(body)
ALL = [world_bvh(o)[0] for o in heads]
HT = float(V[:, 2].max())                         # head top
BZ = C["band_z"]
sl = V[(np.abs(V[:, 2] - BZ) < 0.006) & (V[:, 1] > -0.2)]
cy = float((sl[:, 1].min() + sl[:, 1].max()) / 2) + C.get("centre_dy", 0.0)


def dirv(th):
    return np.array([math.sin(th), -math.cos(th), 0.0])


def band_z(th):
    return BZ + C.get("band_tilt", 0.03) * math.cos(th)          # higher at the front (th 0), lower at the back


ths = np.linspace(-math.pi, math.pi, NA, endpoint=False)
rb = []
for th in ths:
    z = band_z(th)
    c0 = np.array([0, cy, z])
    d = dirv(th)
    hit = bvh.ray_cast(Vector(c0 + d * 0.3), Vector(-d), 0.3)
    rb.append((np.linalg.norm((np.array(hit[0]) - c0)[:2]) if hit[0] else 0.05) + C.get("band_off", 0.008))
rb = np.array(rb)
for _ in range(10):
    rb = 0.25 * np.roll(rb, 1) + 0.5 * rb + 0.25 * np.roll(rb, -1)
rb = np.maximum(rb, np.max(rb) * C.get("round", 0.9))
print("MOBCAP head top", round(HT, 3), "band radius mm", round(rb.min() * 1000), round(rb.max() * 1000), "centre y", round(cy, 3))


def clear_off(p, need):
    for b_ in ALL:
        loc, nrm, _, _ = b_.find_nearest(Vector(p), 0.08)
        if loc is not None:
            g_ = (Vector(p) - loc).dot(nrm)
            if g_ < need:
                p = p + np.array(nrm) * (need - g_)
    return p


bm = bmesh.new()
NK = C.get("nk", 14)
ZT = HT + C.get("crown_h", 0.04)
rings = []
for k in range(NK):
    s = k / NK
    ring = []
    for i, th in enumerate(ths):
        f = 1 - (1 - s) ** 1.6
        z = band_z(th) * (1 - f) + ZT * f
        puff = 1 + C.get("crown_puff", 0.35) * math.sin(math.pi * min(s * 1.15, 1)) ** 0.8
        gat = 1 + C.get("gather_amp", 0.03) * math.sin(th * C.get("gathers", 22)) * math.sin(math.pi * s) * (1 - s) * 2
        rr = rb[i] * (1 - s ** 2.2) ** (1 / 2.2) * puff * gat
        p = np.array([0, cy + C.get("top_back", 0.01) * s, z]) + dirv(th) * rr
        p[2] = z
        if s > 0.03:
            p = clear_off(p, C.get("skin_clear", 0.01))
        ring.append(bm.verts.new(tuple(p)))
    rings.append(ring)
crown_pts = [[np.array(v.co[:]) for v in r_] for r_ in rings]
top = bm.verts.new((0.0, cy + C.get("top_back", 0.01), max(v.co.z for v in rings[-1]) + 0.003))
for k in range(NK - 1):
    for i in range(NA):
        bm.faces.new((rings[k][i], rings[k][(i + 1) % NA], rings[k + 1][(i + 1) % NA], rings[k + 1][i]))
for i in range(NA):
    bm.faces.new((rings[-1][i], rings[-1][(i + 1) % NA], top))
# frill: a ruffled ring from the band outward and down
NB = C.get("nb", 6)
FW = C.get("frill_w", 0.035)
brim = [rings[0]]
for j in range(1, NB + 1):
    u = j / NB
    ring = []
    for i, th in enumerate(ths):
        w_ = FW * C.get("frill_front", 1.0) if math.cos(th) > 0 else FW
        w_ = FW + (FW * C.get("frill_front", 1.0) - FW) * max(math.cos(th), 0.0)
        rr = rb[i] + w_ * u + C.get("frill_amp", 0.006) * u ** 1.2 * math.sin(th * C.get("frill_n", 40))
        wf_ = max(math.cos(th), 0.0)                 # droop by azimuth: lifts off the face at the front
        dr_ = C.get("frill_droop", 0.55) * (1 - wf_) + C.get("frill_droop_front", C.get("frill_droop", 0.55)) * wf_
        z = band_z(th) - w_ * dr_ * u ** 1.3 + C.get("frill_wave", 0.004) * u ** 1.2 * math.cos(th * C.get("frill_n", 40))
        p = np.array([0, cy, z]) + dirv(th) * rr
        p[2] = z
        if u < 0.5:
            p = clear_off(p, C.get("skin_clear", 0.01) * 0.6)
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
if C.get("subsurf", 0):
    sub = hat.modifiers.new("sub", "SUBSURF")
    sub.levels = C["subsurf"]
    bpy.ops.object.modifier_apply(modifier=sub.name)
for v in hat.data.vertices:                  # one clearance pass on the dense mesh (bill ridge, eyes, lids)
    v.co = Vector(clear_off(np.array(v.co[:]), C.get("skin_clear", 0.01) * 0.6 + C.get("thickness", 0.002)))
sol = hat.modifiers.new("sol", "SOLIDIFY")
sol.thickness = C.get("thickness", 0.002)
sol.offset = -1.0
bpy.ops.object.modifier_apply(modifier=sol.name)
cot = bpy.data.materials.new(f"{CHAR}_hat_cotton")
cot.use_nodes = True
bs = cot.node_tree.nodes["Principled BSDF"]
bs.inputs["Base Color"].default_value = srgb(C.get("cotton", [214, 212, 206]))
bs.inputs["Roughness"].default_value = 0.85
me.materials.append(cot)
rib = bpy.data.materials.new(f"{CHAR}_hat_ribbon")
rib.use_nodes = True
bs2 = rib.node_tree.nodes["Principled BSDF"]
bs2.inputs["Base Color"].default_value = srgb(C.get("ribbon", [120, 26, 80]))
bs2.inputs["Roughness"].default_value = C.get("ribbon_rough", 0.35)

# ribbon band on the crown just above the frill
rbm = bmesh.new()
rh = C.get("ribbon_h", 0.016)
NR = 3
hb = BVHTree.FromObject(hat, bpy.context.evaluated_depsgraph_get())
rr_rings = []
for j in range(NR):
    zf = j / (NR - 1)
    ring = []
    for i, th in enumerate(ths):
        # on the crown just above the band: walk up the crown's own column (never the frill below it)
        col_ = np.array([crown_pts[k_][i] for k_ in range(NK)])
        arc_ = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(col_, axis=0), axis=1))]   # by distance along the crown
        L_ = 0.003 + rh * zf
        k1 = int(np.clip(np.searchsorted(arc_, L_), 1, NK - 1))
        a_ = (L_ - arc_[k1 - 1]) / max(arc_[k1] - arc_[k1 - 1], 1e-6)
        q_ = col_[k1 - 1] * (1 - a_) + col_[k1] * a_
        tn_ = col_[k1] - col_[k1 - 1]
        on_ = np.cross(tn_, np.cross(dirv(th), np.array([0, 0, 1.0])))         # outward normal of the crown there
        on_ = on_ / max(np.linalg.norm(on_), 1e-9)
        on_ = on_ if np.dot(on_, dirv(th)) > 0 else -on_
        p = q_ + on_ * (C.get("ribbon_off", 0.002) + C.get("thickness", 0.002))
        ring.append(rbm.verts.new(tuple(p)))
    rr_rings.append(ring)
for j in range(NR - 1):
    for i in range(NA):
        rbm.faces.new((rr_rings[j][i], rr_rings[j][(i + 1) % NA], rr_rings[j + 1][(i + 1) % NA], rr_rings[j + 1][i]))
# bow: two puffed loops + a knot on the ribbon at bow_az, lying in the ribbon's plane
az = math.radians(C.get("bow_az", 0))
i0 = int(round((az + math.pi) / (2 * math.pi) * NA)) % NA
cpt = np.mean([np.array(rr_rings[j][i0].co) for j in range(NR)], axis=0)
n_ = dirv(az)
t_ = np.array([math.cos(az), math.sin(az), 0.0])
up = np.array([0, 0, 1.0])
hn_ = hb.ray_cast(Vector(cpt + n_ * 0.1 + up * 0.0), Vector(-n_), 0.2)
cpt = cpt + n_ * C.get("bow_out", 0.0)          # stand off the band (the crown above it bulges out over an upright bow)
if hn_[0] is not None and C.get("bow_on_surface"):   # or lie in the cap's surface there
    n_ = np.array(hn_[1]) * (1 if np.dot(np.array(hn_[1]), n_) > 0 else -1)
    up = np.cross(n_, t_)
    up = up / np.linalg.norm(up) * (1 if up[2] >= 0 else -1)
    t_ = np.cross(up, n_)
bw, bh = C.get("bow_w", 0.07), C.get("bow_h", 0.035)


def loop(sign):
    if C.get("bow_flat", True):
        # a flat ribbon loop facing out: a filled lobe pinched at the knot, rounded and puffed toward its end
        NL = 20
        ctr_ = rbm.verts.new(tuple(cpt + n_ * (0.004 + C.get("bow_puff", 0.006)) + t_ * sign * bw * 0.25))
        rim_ = []
        for a_ in range(NL):
            ang = 2 * math.pi * a_ / NL
            x_ = sign * bw * 0.25 * (1 + math.cos(ang))
            y_ = bh / 2 * math.sin(ang) * (0.3 + 0.7 * (1 + math.cos(ang)) / 2)
            rim_.append(rbm.verts.new(tuple(cpt + n_ * (0.004 + C.get("bow_puff", 0.006) * 0.4 * (1 + math.cos(ang)) / 2)
                                            + t_ * x_ + up * y_)))
        for a_ in range(NL):
            rbm.faces.new((ctr_, rim_[a_], rim_[(a_ + 1) % NL]))
        return
    vs = []
    NL, NW = 16, 3
    for a_ in range(NL):
        ang = 2 * math.pi * a_ / NL
        for w_ in range(NW):
            off = (w_ - 1) * 0.002
            x_ = sign * (bw / 4) * (1 - math.cos(ang)) + sign * 0.005
            y_ = (bh / 2) * math.sin(ang) * (0.55 + 0.45 * (1 - math.cos(ang)) / 2)
            vs.append(cpt + n_ * (0.005 + off + C.get("bow_puff", 0.006) * math.sin(ang / 2)) + t_ * x_ + up * y_)
    vv = [rbm.verts.new(tuple(v)) for v in vs]
    for a_ in range(NL):
        for w_ in range(NW - 1):
            a0 = a_ * NW + w_
            b0 = ((a_ + 1) % NL) * NW + w_
            rbm.faces.new((vv[a0], vv[b0], vv[b0 + 1], vv[a0 + 1]))


loop(1)
loop(-1)
kn = [cpt + n_ * 0.008 + t_ * sx * 0.008 + up * sz * 0.01 for sx in (-1, 1) for sz in (-1, 1)]
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
(OUT / "hat.json").write_text(json.dumps({"char": CHAR, "piece": "hat", "tris": tris, "source": "make_mobcap.py (modelled)",
                                          "design": C}, indent=1), encoding="utf-8")
print("CAP mobcap", tris)
