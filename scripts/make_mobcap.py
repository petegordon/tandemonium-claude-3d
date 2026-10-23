"""Modelled Victorian mob cap (Grandma): a big gathered pouf of white cotton over the back of the head, a ruffled frill
framing the face, a satin ribbon round the gathers just behind the frill and a ribbon bow at the top front.

  blender -b --factory-startup --python scripts/make_mobcap.py -- --char outfit_grandma

Geometry (r2, after Pete 2026-10-23 "bigger and puffier, like the reference"):
  * the face opening ("rim") is where a plane tilted back crosses the head: high on the forehead at the front, at the
    nape at the back (rim_front / rim_back = [y, z] of the plane's front and back points);
  * the pouf is an ellipsoid dome about the plane's normal: in-plane radii rx (sideways) and re (front-back in the
    plane), height h behind the plane, its centre set back by d (so the dome overhangs the gathered rim);
  * each meridian runs from the rim on the head out under the overhang ("shelf") and over the dome to its pole, with
    gathers (rounded puffs between creases) strongest at the rim and fading to the pole;
  * the frill is a ruffled strip from the rim, out and forward round the face, narrowing to nothing at the back;
  * the ribbon lies on the dome just behind the frill; the bow (two pillow lobes + knot + two notched tails) sits on it
    at the front.

Recipe chars json "mobcap_design" (metres, BUILD frame):
  rim_front, rim_back, rim_off   plane points [y, z], clearance of the rim above the head
  rx, re, h, d, puff_p           dome radii, height, set-back, superellipse power (> 2 = fuller shoulders)
  gathers, gather_amp, gather_reach   puffs round the dome, depth (fraction of the radius), how far up they run (0..1)
  frill_w, frill_fwd, frill_n, frill_amp, frill_back   frill width, forward tilt, ruffles, ruffle depth, width at the back
  ribbon_h, ribbon_at, bow_w, bow_h, bow_puff, tail_len, tail_w
  cotton, ribbon (sRGB), ribbon_rough, skin_clear, thickness, na, nm
The head comes from the character's naked shaped body (out/<char>-goose/<char>_naked_dressed.glb) moved back into the
build frame (- build_frame_lift). Writes shells/hat.glb + hat.json (dress_goose.py rigs "hat" to the Head bone).
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
NA = C.get("na", 256)                 # samples round the rim
NM = C.get("nm", 30)                  # samples along each meridian


def srgb(c):
    c = np.array(c[:3]) / 255.0
    return tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)


bpy.ops.wm.read_factory_settings(use_empty=True)
naked = ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_naked_dressed.glb"
bpy.ops.import_scene.gltf(filepath=str(naked))
for o in bpy.context.scene.objects:            # back into the build frame
    if o.parent is None:
        o.location.z -= LIFT
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
parts = [o for o in bpy.context.scene.objects if o.type == "MESH" and not o.name.startswith(("Icosphere", "catchlight"))]
body = next(o for o in parts if o.name.startswith("body"))


def world_bvh(o):
    me = o.evaluated_get(dg).to_mesh()
    vs = [o.matrix_world @ v.co for v in me.vertices]
    return BVHTree.FromPolygons(vs, [tuple(p.vertices) for p in me.polygons])


bvh = world_bvh(body)
ALL = [world_bvh(o) for o in parts]

# the rim plane: e1 = sideways (+x), e2 = in the plane toward the front-top, a = its normal into the cap (back-up)
F = np.array([0.0, *C["rim_front"]])
Bk = np.array([0.0, *C["rim_back"]])
c0 = (F + Bk) / 2
e1 = np.array([1.0, 0.0, 0.0])
e2 = (F - Bk) / np.linalg.norm(F - Bk)
a = np.cross(e1, e2)
a = a if a[2] > 0 else -a
print("MOBCAP rim centre", np.round(c0, 3).tolist(), "axis", np.round(a, 3).tolist())


def inplane(ps):
    return math.cos(ps) * e2 + math.sin(ps) * e1


ps_ = np.linspace(0, 2 * math.pi, NA, endpoint=False)       # psi 0 = front-top, pi/2 = her left (+x), pi = nape
rim = []
for ps in ps_:
    d_ = inplane(ps)
    hit = bvh.ray_cast(Vector(c0 + d_ * 0.3), Vector(-d_), 0.3)
    r_ = np.linalg.norm(np.array(hit[0]) - c0) if hit[0] else 0.06
    rim.append(r_ + C.get("rim_off", 0.006))
rim = np.array(rim)
for _ in range(8):
    rim = 0.25 * np.roll(rim, 1) + 0.5 * rim + 0.25 * np.roll(rim, -1)
print("MOBCAP rim radius mm", round(rim.min() * 1000), round(rim.max() * 1000))


def clear_off(p, need):
    for b_ in ALL:
        loc, nrm, _, _ = b_.find_nearest(Vector(p), 0.03)
        if loc is not None:
            g_ = (Vector(p) - loc).dot(nrm)
            if -0.02 < g_ < need:              # (a far side or a sliver's back face is not "inside")
                p = p + np.array(nrm) * (need - g_)
    return p


RX, RE, H, D = C.get("rx", 0.12), C.get("re", 0.13), C.get("h", 0.18), C.get("d", 0.03)
PP = C.get("puff_p", 2.4)
NG, GA, GR = C.get("gathers", 20), C.get("gather_amp", 0.05), C.get("gather_reach", 0.75)


def spow(x, p):
    return np.sign(x) * np.abs(x) ** p


def dome(ps, ph):
    """Dome point at azimuth ps, polar angle ph (0 = pole) -- a superellipsoid about the axis, centre set back by D."""
    s_, c_ = math.sin(ph), math.cos(ph)
    s2 = spow(s_, 2 / PP)
    c2 = spow(c_, 2 / PP)
    return c0 + a * D + (math.cos(ps) * RE * e2 + math.sin(ps) * RX * e1) * s2 + a * H * c2


def gather(ps):
    """Rounded puffs between narrow creases (1 at a puff, about -1 in a crease)."""
    x = abs(math.sin(NG * ps / 2))
    return 2 * x ** 0.45 - 1.15


# meridians: rim (on the head) -> shelf under the overhang -> over the dome to the pole
ph_end = math.acos(-min(0.99, (D / H) ** (PP / 2)))         # where the dome comes back round to the rim plane
ph_end = ph_end + C.get("overhang", 0.0)                    # curl a little past it, under the dome
NS = C.get("ns", 6)                                          # shelf samples
cols = []
PHE = []
for i, ps in enumerate(ps_):
    p_rim = c0 + inplane(ps) * rim[i]
    rad_ = math.hypot(RE * math.cos(ps), RX * math.sin(ps))      # the dome's in-plane radius at this azimuth
    need_ = (rim[i] + C.get("lip_gap", 0.014)) / rad_                 # the lip clears the rim (the head) by lip_gap
    ph_i = ph_end
    if need_ < 1 and spow(math.sin(ph_end), 2 / PP) < need_:
        ph_i = math.pi - math.asin(need_ ** (PP / 2))
    PHE.append(ph_i)
PHE = np.array(PHE)
for _ in range(10):
    PHE = 0.25 * np.roll(PHE, 1) + 0.5 * PHE + 0.25 * np.roll(PHE, -1)
for i, ps in enumerate(ps_):
    p_rim = c0 + inplane(ps) * rim[i]
    ph_end = PHE[i]
    col = []
    for k in range(NS):                                      # shelf: rim -> the dome's lower lip
        t = k / NS
        q_ = dome(ps, ph_end)
        p = p_rim * (1 - t) + q_ * t + a * 0.012 * math.sin(math.pi * t)     # bowed back a little (gathered in)
        col.append(p)
    for k in range(NM):
        u = k / (NM - 1)
        ph = ph_end * (1 - u)
        p = dome(ps, ph)
        w = (1 - u) ** 1.2 * min(1.0, u / 0.08) if u < GR else 0.0
        w = w * max(0.0, 1 - u / GR) ** 0.5
        ctr_ = c0 + a * D + a * H * spow(math.cos(ph), 2 / PP)
        p = ctr_ + (p - ctr_) * (1 + GA * w * gather(ps))
        col.append(p)
    cols.append(col)
NC = len(cols[0])
bm = bmesh.new()
VV = [[bm.verts.new(tuple(clear_off(p, C.get("skin_clear", 0.008)) if k < NS + 4 else p))
       for k, p in enumerate(col)] for col in cols]
for i in range(NA):
    j = (i + 1) % NA
    for k in range(NC - 2):
        bm.faces.new((VV[i][k], VV[j][k], VV[j][k + 1], VV[i][k + 1]))
pole = VV[0][NC - 1]                                          # all columns end at the same pole: weld to one vertex
for i in range(NA):
    j = (i + 1) % NA
    bm.faces.new((VV[i][NC - 2], VV[j][NC - 2], pole if j else VV[0][NC - 1]))
crown_cols = [np.array([v.co[:] for v in col]) for col in VV]

# frill: from the dome's lip, out and forward (-a) round the face, ruffled; narrower round the nape
NB = C.get("nb", 7)
FW = C.get("frill_w", 0.03)
FB = C.get("frill_back", 0.3)
FF = C.get("frill_fwd", 0.75)
fr = [[VV[i][NS] for i in range(NA)]]
for jb in range(1, NB + 1):
    u = jb / NB
    ring = []
    for i, ps in enumerate(ps_):
        wf = FW * (FB + (1 - FB) * (0.5 + 0.5 * math.cos(ps)) ** 0.7)
        ps_s = (ps + math.pi) % (2 * math.pi) - math.pi           # -pi..pi
        sa_ = math.radians(C.get("frill_side_at", 90))
        wf *= 1 - (1 - C.get("frill_side", 1.0)) * math.exp(-((abs(ps_s) - sa_) / C.get("frill_side_w", 0.6)) ** 2)  # (clear of the eyes)
        out = inplane(ps)
        n_rf = math.sin(C.get("frill_n", 60) * ps)
        root = crown_cols[i][NS]
        ff = FF * (1 - C.get("frill_up_front", 0.6) * max(math.cos(ps), 0.0) ** 2)   # stands up over the forehead
        fdir = out * C.get("frill_out", 1 - ff) - a * ff          # (frill_out < 0: tucked in toward the face)
        fdir = fdir / np.linalg.norm(fdir)
        tng = -math.sin(ps) * e2 + math.cos(ps) * e1
        nrm = np.cross(tng, fdir)
        p = root + fdir * wf * u + nrm * C.get("frill_amp", 0.006) * u ** 0.9 * n_rf
        ring.append(bm.verts.new(tuple(p)))
    fr.append(ring)
for jb in range(NB):
    for i in range(NA):
        j = (i + 1) % NA
        bm.faces.new((fr[jb + 1][i], fr[jb + 1][j], fr[jb][j], fr[jb][i]))
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
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.remove_doubles(threshold=1e-5)
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode="OBJECT")
sol = hat.modifiers.new("sol", "SOLIDIFY")
sol.thickness = C.get("thickness", 0.0018)
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


def crown_at(i, L):
    """Point + outward normal on crown column i, at arc length L from the dome's lower lip (the shelf end)."""
    col_ = crown_cols[i][NS:]
    arc_ = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(col_, axis=0), axis=1))]
    k1 = int(np.clip(np.searchsorted(arc_, L), 1, len(col_) - 1))
    t_ = (L - arc_[k1 - 1]) / max(arc_[k1] - arc_[k1 - 1], 1e-6)
    q_ = col_[k1 - 1] * (1 - t_) + col_[k1] * t_
    tn_ = col_[k1] - col_[k1 - 1]
    side_ = np.cross(inplane(ps_[i]), a)
    n_ = np.cross(side_, tn_)
    n_ = n_ / max(np.linalg.norm(n_), 1e-9)
    if np.dot(n_, q_ - (c0 + a * D)) < 0:
        n_ = -n_
    return q_, n_


# ribbon: a band on the dome just behind the frill, smoothed round (it lies over the gathers, not in them)
rbm = bmesh.new()
rh = C.get("ribbon_h", 0.018)
R0 = C.get("ribbon_at", 0.012)
NR = 4
rr = []
for jr in range(NR):
    ring = []
    pts = []
    for i in range(NA):
        q_, n_ = crown_at(i, R0 + rh * jr / (NR - 1))
        pts.append((q_, n_))
    P = np.array([p for p, _ in pts])
    N = np.array([n for _, n in pts])
    for _ in range(C.get("ribbon_smooth", 14)):   # ride over the creases
        P = (np.roll(P, 1, 0) + 2 * P + np.roll(P, -1, 0)) / 4
    for i in range(NA):
        ring.append(rbm.verts.new(tuple(P[i] + N[i] * (C.get("thickness", 0.0018) + C.get("ribbon_off", 0.003)))))
    rr.append(ring)
for jr in range(NR - 1):
    for i in range(NA):
        j = (i + 1) % NA
        rbm.faces.new((rr[jr][i], rr[jr][j], rr[jr + 1][j], rr[jr + 1][i]))

# bow at the front on the ribbon: frame = (t sideways, up along the dome, n out of it)
ib = 0
cpt, n_ = crown_at(ib, C.get("bow_at", R0 + rh / 2))
t_ = e1.copy()
up = np.cross(n_, t_)
up = up if up[2] > 0 else -up
cpt = cpt + n_ * C.get("bow_out", 0.006)
print("MOBCAP bow", np.round(cpt, 3).tolist(), "n", np.round(n_, 2).tolist(), "up", np.round(up, 2).tolist())
bw, bh, bp = C.get("bow_w", 0.1), C.get("bow_h", 0.05), C.get("bow_puff", 0.012)


def add_grid(F_, nu, nv):
    """F_(u, v) -> point; a quad grid (nu x nv samples) in rbm; returns the vertex grid."""
    g = [[rbm.verts.new(tuple(F_(iu / (nu - 1), iv / (nv - 1)))) for iv in range(nv)] for iu in range(nu)]
    for iu in range(nu - 1):
        for iv in range(nv - 1):
            rbm.faces.new((g[iu][iv], g[iu + 1][iv], g[iu + 1][iv + 1], g[iu][iv + 1]))
    return g


def lobe(sign):
    """A pillow lobe: pinched at the knot, rounded at its end, the front face puffed with two satin creases."""
    L = bw / 2 - 0.008
    rot = math.radians(C.get("bow_lift", 14)) * sign

    def outline(t):
        hh = bh / 2 * (0.32 + 0.68 * math.sin(math.pi / 2 * min(t / 0.7, 1.0)) ** 0.8)
        if t > 0.7:
            hh *= math.sqrt(max(0.0, 1 - ((t - 0.7) / 0.3) ** 2))
        return hh

    def P(t, v, front):
        x = sign * (0.009 + L * t)
        y = outline(t) * v
        x, y = x * math.cos(rot) - sign * 0 + -y * math.sin(rot), x * math.sin(rot) + y * math.cos(rot)
        bulge = bp * (1 - v * v) * math.sin(math.pi * min(t, 0.999)) ** 0.6
        crease = 0.0
        if front:
            for vc, wc in ((0.35, 0.16), (-0.4, 0.14)):
                crease += 0.45 * bp * math.exp(-((v - vc) / wc) ** 2) * min(1.0, t * 1.4) * (1 - t)
            dn = 0.004 + bulge - crease
        else:
            dn = 0.004 - 0.35 * bulge
        return cpt + t_ * x + up * y + n_ * dn

    add_grid(lambda u, v: P(u, 2 * v - 1, True), 18, 13)
    add_grid(lambda u, v: P(u, 1 - 2 * v, False), 18, 13)


lobe(1)
lobe(-1)


def tail(sign):
    TL, TW = C.get("tail_len", 0.05), C.get("tail_w", 0.017)
    ang = math.radians(C.get("tail_deg", 28))
    dirt = -up * math.cos(ang) + t_ * sign * math.sin(ang)

    def P(u, v):
        x = (v - 0.5) * TW * (1 + 0.25 * u)
        end_notch = 0.35 * TW * abs(v - 0.5) * 2 if u > 0.98 else 0.0
        return cpt + dirt * (TL * u - (TL * 0.25 * (1 - abs(v - 0.5) * 2) if u > 0.98 else 0.0) + 0.006) \
            + np.cross(n_, dirt) * x + n_ * (0.003 + 0.004 * math.sin(math.pi * u) * (1 if sign > 0 else 0.6)) \
            + 0 * end_notch

    add_grid(P, 8, 4)


if C.get("tail_len", 0.05) > 0:
    tail(1)
    tail(-1)
# knot: a small puffed cushion over the centre
NKn = 10
kc = cpt + n_ * (0.006 + bp * 0.5)


def knot(u, v):
    th, ph = 2 * math.pi * u, math.pi * v
    return kc + t_ * 0.011 * math.sin(ph) * math.cos(th) + up * 0.016 * math.cos(ph) + n_ * 0.008 * math.sin(ph) * math.sin(th)


add_grid(knot, NKn + 1, NKn)
rme = bpy.data.meshes.new("ribbon")
rbm.to_mesh(rme)
rbm.free()
ro = bpy.data.objects.new("ribbon", rme)
bpy.context.scene.collection.objects.link(ro)
rme.materials.append(rib)
bpy.ops.object.select_all(action="DESELECT")
ro.select_set(True)
bpy.context.view_layer.objects.active = ro
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.remove_doubles(threshold=1e-5)
bpy.ops.object.mode_set(mode="OBJECT")
sol2 = ro.modifiers.new("sol", "SOLIDIFY")
sol2.thickness = 0.0012
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
V_ = np.array([v.co[:] for v in hat.data.vertices])
print("MOBCAP extent x", np.round([V_[:, 0].min(), V_[:, 0].max()], 3).tolist(), "y",
      np.round([V_[:, 1].min(), V_[:, 1].max()], 3).tolist(), "z", np.round([V_[:, 2].min(), V_[:, 2].max()], 3).tolist())
tris = len(hat.data.polygons)
bpy.ops.export_scene.gltf(filepath=str(OUT / "hat.glb"), use_selection=True, export_format="GLB")
(OUT / "hat.json").write_text(json.dumps({"char": CHAR, "piece": "hat", "tris": tris, "source": "make_mobcap.py (modelled)",
                                          "design": C}, indent=1), encoding="utf-8")
print("CAP mobcap", tris)
