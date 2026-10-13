"""P3.4 polish: model a small accessory piece cleanly instead of extracting it (generated neckwear is
too thin / mixed for build_shell.py: the bow tie came out as shards, the brooch collar as ragged strips).

  blender -b --factory-startup --python scripts/make_accessory.py -- --char outfit_male --piece bowtie

Pieces (shapes and colours from the refs/v3 front views, sizes from the worn neck):
  bowtie (male): cream standing shirt collar with turned-down wing tips, black neck band along its
      top, cream shirt front in the V, black butterfly bow + knot at the front;
  collar (female): cream standing collar with a scalloped top + gold dome brooch at the throat; the
      terracotta scalloped bib and dress-red round collar draped over the bodice belong to the dress
      ("accessory_split" -> shells/dress@bib.glb, joined into the dress by dress_goose.py).
Placement: the neck base (lowest height where the side radius stops flaring: < 0.4 mm/mm),
searched upward from 6 cm below the extracted piece's front-most part (pieces/<piece>.glb); neck
cross-section from the worn body (chars json "body_shape" via bodyshape.py), rays from the neck axis;
draped parts are projected from outside onto the outermost of body + the shells under them.
chars json "accessory_clear" {piece: {pieces, parts}}: dress_goose.py removes faces of those extracted
shells that sit just under / over these parts (old fragments of the piece left in them).
Writes out/<char>-goose/shells/<piece>.glb + .json (same names build_shell.py uses, so dress_goose.py and
assemble_outfit.py pick it up) and renders/<char>_shell_<piece>.png.
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

sys.path.insert(0, str(Path(__file__).parent))
import bodyshape  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]


def opt(name, default, cast=str):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


CHAR = opt("--char", "outfit_male")
PIECE = opt("--piece", "bowtie")
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{CHAR}-goose"
OUT = D / "shells"
RENDERS = ROOT / "renders"
RES = 640
NA = 48                       # azimuth steps around the neck


def srgb(c):
    """sRGB 0-255 -> linear 0-1 (glTF base colour factors are linear)."""
    c = np.array(c[:3]) / 255.0
    return tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)


# colours sampled from refs/v3 front views (5x5 medians; specular dome highlight -> darker gold base)
COL = {"cream_m": srgb((236, 218, 192)), "black": srgb((30, 28, 28)), "cream_f": srgb((230, 203, 181)),
       "bib": srgb((168, 89, 73)), "red": srgb((116, 52, 50)), "gold": srgb((214, 160, 80)),
       "gold_dark": srgb((120, 70, 30))}


def load(path):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [o for o in bpy.context.scene.objects if o not in before]


def only_select(*obs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


bpy.ops.wm.read_factory_settings(use_empty=True)
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text())

# ---- worn body (same as build_shell.py)
rig = load(ROOT / "out" / "base-goose" / "base_goose_rigged.glb")
arm = next(o for o in rig if o.type == "ARMATURE")
body = next(o for o in rig if o.type == "MESH" and o.name.startswith("base_goose_game"))
only_select(body)
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
for m in list(body.modifiers):
    body.modifiers.remove(m)
if cfg.get("body_shape", "base") != "base":
    names = [g.name for g in body.vertex_groups]
    V = np.array([v.co[:] for v in body.data.vertices])
    W = np.zeros((len(V), len(names)))
    for v in body.data.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
    body.data.vertices.foreach_set("co", bodyshape.deform(V, W, names, arm, bodyshape.body_transforms(ROOT, CHAR, arm)).ravel())
    body.data.update()
for o in rig:
    if o is not body:
        bpy.data.objects.remove(o)
dg = bpy.context.evaluated_depsgraph_get()
body_bvh = BVHTree.FromObject(body, dg)

# ---- height from the extracted piece: its front-most part (the bow / the brooch)
AD = cfg.get("accessory_design", {}).get(PIECE, {})    # measured from the drawing (outfits drawn per garment)
if "anchor_z" in AD:
    Z0 = float(AD["anchor_z"])
    print("ANCHOR z (recipe)", Z0)
else:
    old = next(o for o in load(D / "pieces" / f"{PIECE}.glb") if o.type == "MESH")
    OP = np.array([old.matrix_world @ v.co for v in old.data.vertices])
    bpy.data.objects.remove(old)
    OP = OP[np.abs(OP[:, 0]) < 0.12]
    front = OP[OP[:, 1] < OP[:, 1].min() + 0.012]
    Z0 = float(np.median(front[:, 2]))
    print("ANCHOR z", round(Z0, 4), "front y", round(float(front[:, 1].min()), 4))
for k_, v_ in AD.get("colors", {}).items():
    COL[k_] = srgb(v_)

under = [body]                                   # draped parts sit on the outermost of these
for nm in cfg.get("accessory_over", {}).get(PIECE, []):
    o = next(x for x in load(OUT / f"{nm}.glb") if x.type == "MESH")
    under.append(o)


def axis_y(z):
    """Neck/chest axis at height z: midway between the front and back body surface on x = 0."""
    f = body_bvh.ray_cast(Vector((0, -1, z)), Vector((0, 1, 0)), 2)[0]
    b = body_bvh.ray_cast(Vector((0, 1, z)), Vector((0, -1, 0)), 2)[0]
    return (f.y + b.y) / 2


def dirv(th):
    """Azimuth -> horizontal unit vector (0 = front = -Y, + = character left = +X)."""
    return np.array([math.sin(th), -math.cos(th), 0.0])


def neck_r(th, z):
    """Neck radius at azimuth th, height z (ray from the axis outward, last exit = outer surface)."""
    c = np.array([0, axis_y(z), z])
    d = dirv(th)
    loc = body_bvh.ray_cast(Vector(c + d * 0.25), Vector(-d), 0.25)[0]     # from outside inward
    return float(np.linalg.norm((np.array(loc) - c)[:2])) if loc else 0.05


def outer(th, z, extra=()):
    """Outermost surface point + normal at (th, z) over body + `under` shells (rays from outside)."""
    c = np.array([0, axis_y(z), z])
    d = dirv(th)
    best = None
    for o in under + list(extra):
        b = body_bvh if o is body else BVHTree.FromObject(o, bpy.context.evaluated_depsgraph_get())
        hit = b.ray_cast(Vector(c + d * 0.4), Vector(-d), 0.4)
        if hit[0] is not None and (best is None or hit[3] < best[2]):
            best = (np.array(hit[0]), np.array(hit[1]), hit[3])
    return (best[0], best[1]) if best else (c + d * 0.05, d)


def mesh_obj(name, verts, faces, color, rough=0.7, metal=0.0, solid=0.0, smooth=True):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.validate()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    mat = bpy.data.materials.get(f"{CHAR}_{PIECE}_{name}") or bpy.data.materials.new(f"{CHAR}_{PIECE}_{name}")
    mat.use_nodes = True
    bs = mat.node_tree.nodes["Principled BSDF"]
    bs.inputs["Base Color"].default_value = color
    bs.inputs["Roughness"].default_value = rough
    bs.inputs["Metallic"].default_value = metal
    me.materials.append(mat)
    only_select(o)
    if solid:
        m = o.modifiers.new("sol", "SOLIDIFY")
        m.thickness = solid
        m.offset = -1.0
        bpy.ops.object.modifier_apply(modifier=m.name)
    if smooth:
        bpy.ops.object.shade_smooth()
    return o


def grid_faces(nu, nv, wrap_u=False):
    f = []
    for i in range(nu - (0 if wrap_u else 1)):
        for j in range(nv - 1):
            a, b = i * nv + j, ((i + 1) % nu) * nv + j
            f.append((a, b, b + 1, a + 1))
    return f


def band(name, z_lo, z_hi_fn, off, color, th_range=(-math.pi, math.pi), nz=3, wrap=True, solid=0.002, **kw):
    """Standing band around the neck: azimuth x height grid at neck radius + off."""
    ths = np.linspace(*th_range, NA, endpoint=not wrap)
    vs = []
    for th in ths:
        zt = z_hi_fn(th)
        for z in np.linspace(z_lo, zt, nz):
            r = neck_r(th, z) + off
            vs.append(np.array([0, axis_y(z), z]) + dirv(th) * r)
    return mesh_obj(name, vs, grid_faces(len(ths), nz, wrap), color, solid=solid, **kw)


def drape(name, th_max, z_top, depth_fn, off, color, nth=25, nd=7, solid=0.0015, extra=(), smooth_it=6, **kw):
    """Flat garment on the chest: (azimuth, depth below z_top) grid projected onto the outermost surface,
    lower edge depth_fn(th). The radial distance is smoothed over the grid (fabric bridges the dress
    shell's wrinkles) and kept within 1.5 mm of the surface it lies on."""
    ths = np.linspace(-th_max, th_max, nth)
    C, Dv, Rr = [], [], []
    for th in ths:
        dm = depth_fn(th)
        for t in np.linspace(0, 1, nd):
            z = z_top - dm * t
            c = np.array([0, axis_y(z), z])
            p, _ = outer(th, z, extra)
            C.append(c)
            Dv.append(dirv(th))
            Rr.append(np.linalg.norm((p - c)[:2]))
    Rr = np.array(Rr).reshape(nth, nd)
    Rs = Rr.copy()
    for _ in range(smooth_it):
        P_ = np.pad(Rs, 1, mode="edge")
        Rs = (P_[1:-1, 1:-1] * 2 + P_[:-2, 1:-1] + P_[2:, 1:-1] + P_[1:-1, :-2] + P_[1:-1, 2:]) / 6
    Rf = np.maximum(Rs, Rr - 0.0015).ravel() + off
    vs = [c + d * r for c, d, r in zip(C, Dv, Rf)]
    return mesh_obj(name, vs, grid_faces(nth, nd), color, solid=solid, **kw)


def tube(name, path, rad_fn, color, nseg=12, caps=True, **kw):
    """Closed tube along path points (N, 3) with cross-section radii rad_fn(i) -> (ra, rb) in the
    (up, out) plane of a front-facing piece."""
    vs, faces = [], []
    N = len(path)
    for i, c in enumerate(path):
        ra, rb, frame = rad_fn(i)
        u, w = frame
        for k in range(nseg):
            a = 2 * math.pi * k / nseg
            vs.append(c + u * ra * math.sin(a) + w * rb * math.cos(a))
    for i in range(N - 1):
        for k in range(nseg):
            a, b = i * nseg + k, i * nseg + (k + 1) % nseg
            faces.append((a, b, b + nseg, a + nseg))
    if caps:
        for i, rev in ((0, True), (N - 1, False)):
            vs.append(np.array(path[i]))
            ci = len(vs) - 1
            for k in range(nseg):
                a, b = i * nseg + k, i * nseg + (k + 1) % nseg
                faces.append((ci, b, a) if rev else (ci, a, b))
    return mesh_obj(name, vs, faces, color, **kw)


def textured_bow(c0, Wb, Hb, tex_path, AD):
    """Butterfly bow tie as in the product shot (front view = the texture, 1.75 : 1): two wings, each a slab
    narrow at the knot (KNOT_H x the height) flaring to the full height at the rounded tips, puffed in the middle
    and pleated near the knot, the tips bending back toward the neck; a wrapped knot band over the centre. Every
    vertex's UV is its front-view position in the bow's bounding box (front projection; the backs mirror it)."""
    up, out = np.array([0, 0, 1.0]), np.array([0, -1.0, 0])
    KX = AD.get("knot_w", 0.16) / 2 * Wb          # knot half width (texture: 0.42 .. 0.58 of the width)
    KH = AD.get("knot_h", 0.47)                   # wing height at the knot / full height
    NU, NS = 22, 28
    obs = []

    def uv_of(p):
        return ((p[0] - (c0[0] - Wb / 2)) / Wb, (p[2] - (c0[2] - Hb / 2)) / Hb)

    def section(ra, rb, n=3.0):
        out_ = []
        for kk in range(NS):
            a = 2 * math.pi * kk / NS
            sa, ca_ = math.sin(a), math.cos(a)
            out_.append((ra * math.copysign(abs(sa) ** (2 / n), sa), rb * math.copysign(abs(ca_) ** (2 / n), ca_)))
        return out_

    def build(name, rings, color_tex):
        vs, faces = [], []
        for ring in rings:
            vs.extend(ring)
        nr = len(rings)
        for i in range(nr - 1):
            for kk in range(NS):
                a, b = i * NS + kk, i * NS + (kk + 1) % NS
                faces.append((a, b, b + NS, a + NS))
        for i, rev in ((0, True), (nr - 1, False)):
            vs.append(np.mean(rings[i], 0))
            ci = len(vs) - 1
            for kk in range(NS):
                a, b = i * NS + kk, i * NS + (kk + 1) % NS
                faces.append((ci, b, a) if rev else (ci, a, b))
        o = mesh_obj(name, vs, faces, (0.4, 0.08, 0.08, 1), rough=AD.get("bow_rough", 0.5))
        me = o.data
        uvl = me.uv_layers.new(name="UVMap")
        for lp in me.loops:
            uvl.data[lp.index].uv = uv_of(me.vertices[lp.vertex_index].co)
        mat = me.materials[0]
        nt = mat.node_tree
        tx = nt.nodes.new("ShaderNodeTexImage")
        tx.image = color_tex
        tx.extension = "EXTEND"
        bs = nt.nodes["Principled BSDF"]
        nt.links.new(tx.outputs["Color"], bs.inputs["Base Color"])
        if "Sheen Weight" in bs.inputs:           # silk (a white sheen veiled the burgundy pale pink: keep it low)
            bs.inputs["Sheen Weight"].default_value = AD.get("bow_sheen", 0.0)
        return o

    img = bpy.data.images.load(str(tex_path))
    img.pack()
    for sgn in (1, -1):
        rings = []
        for i in range(NU + 1):
            u = i / NU
            x = KX * 0.7 + (Wb / 2 - KX * 0.7) * u
            # height: pinched at the knot, full at the tip; the last 12 % rounds the tip's corners
            hh = Hb * (KH + (1 - KH) * u ** 0.85) / 2
            tipr = 1.0 if u < 0.88 else math.sqrt(max(1 - ((u - 0.88) / 0.12) ** 2, 0.0)) * 0.85 + 0.15
            tk = (0.006 + 0.007 * math.sin(math.pi * min(u * 1.25, 1.0))) * (0.6 + 0.4 * tipr)
            zc = c0[2] - 0.06 * Hb * (1 - u)              # the wing centre sits a little low at the knot
            yc = c0[1] + AD.get("bow_back", 0.012) * u * u + 0.003 * u     # tips bend back toward the neck
            ring = []
            for ra, rb in section(hh * (0.75 + 0.25 * tipr) if u >= 0.88 else hh, tk):
                zz = ra
                pleat = 0.0022 * (1 - u) ** 1.5 * math.cos(3 * math.pi * zz / max(hh, 1e-6))   # folds at the knot
                ring.append(np.array([sgn * x, yc - rb - pleat * (rb < 0), zc + zz]))
            rings.append(ring)
        if sgn < 0:
            rings = rings                                     # (faces wind the other way: normals fixed on join)
        obs.append(build(f"bow_{'L' if sgn > 0 else 'R'}", rings, img))
    # knot: a wrapped band, a little proud of the wings, rounded front
    rings = []
    for i in range(7):
        x = -KX + 2 * KX * i / 6
        ring = []
        for ra, rb in section(Hb * AD.get("knot_band_h", 0.52) / 2, 0.011, n=2.6):
            ring.append(np.array([x, c0[1] - 0.004 - rb * (1.15 if rb < 0 else 0.6), c0[2] - 0.035 * Hb + ra]))
        rings.append(ring)
    obs.append(build("knot", rings, img))
    return obs


def neck_base(z_from):
    """Neck base: lowest height above z_from - 6 cm where the side radius stops flaring, i.e. it
    shrinks by less than 0.4 mm per mm going up (below: the shoulders)."""
    zs = np.arange(z_from - 0.06, z_from + 0.2, 0.005)
    rs = np.array([neck_r(math.pi / 2, z) for z in zs])
    slope = (rs[:-1] - rs[1:]) / 0.005
    zb = float(zs[np.argmax(slope < 0.4)])
    return zb, float(rs[np.argmax(slope < 0.4)]), [[round(float(z), 3), round(float(r) * 1000, 1)] for z, r in zip(zs[::4], rs[::4])]


ZB, RMIN, prof = neck_base(Z0)
print("NECK base z", round(ZB, 4), "r_base mm", round(RMIN * 1000, 1), prof)
parts = []
info = {"anchor_z": round(Z0, 4), "neck_base_z": round(ZB, 4), "neck_r_base_mm": round(RMIN * 1000, 1)}
if PIECE == "bowtie":
    Rs = neck_r(math.pi / 2, ZB + 0.01)
    Hc = AD.get("collar_h_scale", 0.95) * Rs         # ref: high shirt collar ~ half the neck width
    z_lo, z_hi = ZB - 0.012, ZB + 0.85 * Hc          # tucked under the coat collar at the base
    Z0 = z_lo + 0.33 * Hc                            # bow centre in the collar's lower half (ref)
    R = neck_r(0.0, Z0)
    gap = math.radians(4)
    gap = math.radians(AD.get("collar_gap_deg", 4))
    # collar band: open at the front (tips fold down there)
    parts.append(band("collar", z_lo, lambda th: z_hi, AD.get("collar_off", 0.004), COL["cream_m"],
                      th_range=(gap, 2 * math.pi - gap), nz=3, wrap=False))
    # neck band (black) along the top edge, behind the bow
    parts.append(band("neckband", z_hi - 0.004, lambda th: z_hi + 0.002, 0.0065, COL.get("neckband", COL["black"]), nz=2, solid=0.0015,
                      rough=0.45))
    # wing tips: triangles turned down over the collar front
    for s in (1, -1):
        th0, th1, thp = gap * s, math.radians(34) * s, math.radians(13) * s
        pts = []
        for th, z in ((th0, z_hi), (th1, z_hi), (thp, z_hi - 0.55 * Hc)):
            pts.append(np.array([0, axis_y(z), z]) + dirv(th) * (neck_r(th, z) + 0.0075))
        mid = (pts[0] + pts[1]) / 2 + dirv((th0 + th1) / 2) * 0.002
        vs = [pts[0], mid, pts[1], pts[2]]
        parts.append(mesh_obj(f"wing_{'L' if s > 0 else 'R'}", vs, [(0, 1, 3), (1, 2, 3)] if s > 0 else [(1, 0, 3), (2, 1, 3)],
                              COL["cream_m"], solid=0.0015))
    # shirt front (cream) in the coat / waistcoat V under the bow: covers the old bow fragments the
    # extracted shells kept there (dress_goose.py clears them, chars json "accessory_clear")
    thf = math.radians(26)
    parts.append(drape("shirtfront", thf, z_lo + 0.006, lambda th, thf=thf: 0.035 + 0.11 * (1 - abs(th) / thf) ** 1.3,
                       0.006, COL["cream_m"], nth=15, nd=8))       # a V: follows the waistcoat opening
    # bow: centre in front of the collar; width ~ 0.85 x collar width, height ~ 0.53 x width (ref)
    yc = axis_y(Z0)
    Wb = AD.get("bow_w", 0.85 * 2 * Rs)
    Hb = AD.get("bow_h_ratio", 0.5) * Wb
    c0 = np.array([0, yc - R - 0.012, Z0])
    up, out = np.array([0, 0, 1.0]), np.array([0, -1.0, 0])
    k = 0.11 * Wb                                   # knot half width
    TEX = AD.get("bow_texture")
    if TEX:
        parts.extend(textured_bow(c0, Wb, Hb, ROOT / TEX, AD))
    for s in (1, -1) if not TEX else ():
        us = np.linspace(0, 1, 9)
        path = [c0 + np.array([s * (k * 0.6 + u * (Wb / 2 - k * 0.6)), 0.004 * u, -0.06 * Hb * u]) for u in us]

        def rad(i, us=us, s=s):
            u = us[i]
            h = Hb * (0.17 + 0.33 * math.sin(u * math.pi / 2) ** 0.8)   # pinched at the knot, flared tips
            t = 0.0055 + 0.0045 * math.sin(math.pi * min(u * 1.3, 1))
            return h, t, (up, out)
        parts.append(tube(f"bow_{'L' if s > 0 else 'R'}", path, rad, COL.get("bow", COL["black"]), nseg=14, rough=0.55))
    kpath = [c0 + np.array([x, -0.003, 0]) for x in np.linspace(-k, k, 4)]
    if not TEX:
        parts.append(tube("knot", kpath, lambda i: (0.24 * Hb, 0.0085, (up, out)), COL.get("bow", COL["black"]), nseg=14, rough=0.55))
    info.update({"neck_r_front_side_mm": [round(R * 1000, 1), round(Rs * 1000, 1)], "collar_h_mm": round(Hc * 1000, 1),
                 "bow_w_h_mm": [round(Wb * 1000, 1), round(Hb * 1000, 1)]})
elif PIECE == "collar":
    Rs = neck_r(math.pi / 2, ZB + 0.01)
    R = neck_r(0.0, ZB + 0.01)
    z_base = ZB + 0.004                              # standing collar from the neck base up
    Hc = 0.85 * Rs
    n_sc = 14
    parts.append(band("standing", z_base - 0.008, lambda th: z_base + Hc - 0.004 * abs(math.sin(n_sc * th / 2)),
                      0.007, COL["cream_f"], nz=4))   # (7 mm: clear of the bodice neck under it)
    # bib: terracotta, 5 scallops along the lower edge, down ~ 1.2 x collar height at the front
    thb = math.radians(68)
    Db = 2.1 * Hc                                    # ref: the bib reaches a third down the bodice

    def bib_depth(th, Db=Db, thb=thb):
        x = th / thb
        return Db * (1 - 0.35 * x * x) - 0.006 * (1 - abs(math.cos(2.5 * math.pi * (x + 1)))) ** 1.5
    parts.append(drape("bib", thb, z_base, bib_depth, 0.0035, COL["bib"], nth=31, nd=7))
    # round collar (dress red) over the bib: two lobes meeting under the brooch
    thr = math.radians(70)

    def roll_depth(th, thr=thr, Hc=Hc):
        x = abs(th) / thr
        return 0.55 * Hc * (0.45 + 0.55 * math.sin(math.pi * min(x * 1.15, 1))) * (1 - 0.2 * x)
    bib_o = parts[-1]
    parts.append(drape("roll", thr, z_base + 0.002, roll_depth, 0.0025, COL["red"], nth=31, nd=5, extra=(bib_o,)))
    # brooch: gold rim ring + dome at the throat, facing the surface normal
    p, n = outer(0.0, z_base - 0.008, (bib_o, parts[-1]))
    n = n / np.linalg.norm(n)
    up = np.array([0, 0, 1.0]) - n * n[2]
    up /= np.linalg.norm(up)
    side = np.cross(up, n)
    rx, rz = 0.013, 0.015                            # ref: brooch ~ a quarter of the bib top
    ring = [p + n * 0.002 + side * rx * math.cos(a) + up * rz * math.sin(a) for a in np.linspace(0, 2 * math.pi, 25)]
    parts.append(tube("brooch_rim", ring, lambda i: (0.0018, 0.0018, (n, np.cross(n, side))), COL["gold_dark"],
                      nseg=8, caps=False, rough=0.35, metal=1.0))
    vs, faces = [p + n * 0.007], []
    nr, na = 4, 20
    for i in range(1, nr + 1):
        t = i / nr
        for j in range(na):
            a = 2 * math.pi * j / na
            vs.append(p + n * (0.002 + 0.005 * math.cos(t * math.pi / 2)) +
                      (side * rx * math.cos(a) + up * rz * math.sin(a)) * 0.85 * math.sin(t * math.pi / 2) / math.sin(math.pi / 2))
    for j in range(na):
        faces.append((0, 1 + (j + 1) % na, 1 + j))
    for i in range(nr - 1):
        for j in range(na):
            a, b = 1 + i * na + j, 1 + i * na + (j + 1) % na
            faces.append((a, b, b + na, a + na))
    parts.append(mesh_obj("brooch_dome", vs, faces, COL["gold"], rough=0.25, metal=1.0))
    info.update({"neck_r_front_side_mm": [round(R * 1000, 1), round(Rs * 1000, 1)], "collar_h_mm": round(Hc * 1000, 1)})
else:
    raise SystemExit(f"no accessory recipe for {PIECE}")

for o in under[1:]:
    bpy.data.objects.remove(o)
clear = cfg.get("accessory_clear", {}).get(PIECE)
# chars json "accessory_split" {piece: {"<target>@<name>": [parts]}}: those parts belong to another
# garment (female: the bib and round collar are part of the dress) -> shells/<target>@<name>.glb, which
# dress_goose.py joins into <target> after the clear step
drop = cfg.get("accessory_drop", {}).get(PIECE, [])   # parts now made by a designed garment (shirt front)
for o in [o for o in parts if o.name.split(".")[0] in drop]:
    parts.remove(o)
    bpy.data.objects.remove(o)
groups = {PIECE: []}
split = cfg.get("accessory_split", {}).get(PIECE, {})
for o in parts:
    g = next((k for k, v in split.items() if o.name.split(".")[0] in v), PIECE)
    groups.setdefault(g, []).append(o)
OUT.mkdir(exist_ok=True)
outs = []
for g, obs in groups.items():
    names_g = [o.name.split(".")[0] for o in obs]
    only_select(*obs)
    bpy.ops.object.join()
    acc = bpy.context.view_layer.objects.active
    acc.name = acc.data.name = f"{g}_shell"
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    keep_uv = {i for i, m in enumerate(acc.data.materials) if m and m.node_tree and
               any(n.type == "TEX_IMAGE" for n in m.node_tree.nodes)}          # textured bow: front-projected UVs
    uvd = acc.data.uv_layers.active.data if acc.data.uv_layers else None
    saved = {lp: tuple(uvd[lp].uv) for p_ in acc.data.polygons if p_.material_index in keep_uv
             for lp in p_.loop_indices} if uvd is not None else {}
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.01)
    bpy.ops.object.mode_set(mode="OBJECT")
    if saved:          # (selecting only the other faces did not hold: put the bow's front projection back)
        uvd = acc.data.uv_layers.active.data
        for lp, uv in saved.items():
            uvd[lp].uv = uv
    tris = sum(len(p_.vertices) - 2 for p_ in acc.data.polygons)
    report = {"char": CHAR, "piece": g, "tris": tris, "source": "make_accessory.py (modelled)", "parts": names_g, **info}
    mine = [n for n in (clear or {}).get("parts", []) if n in names_g]
    if mine:     # dress_goose.py deletes faces of these shells whose radial line meets these parts within 2.5 cm
        report["clear"] = {"pieces": clear["pieces"], "parts": mine, "axis_y": round(axis_y(Z0), 4), "radial": 0.025,
                           "materials": [f"{CHAR}_{PIECE}_{n}" for n in mine]}
    (OUT / f"{g}.json").write_text(json.dumps(report, indent=1))
    print("SHELL", json.dumps(report))
    only_select(acc)
    bpy.ops.export_scene.gltf(filepath=str(OUT / f"{g}.glb"), use_selection=True, export_format="GLB")
    outs.append(acc)

# ---- render: piece alone | piece + body (green), front / side / back / 3-4 (as build_shell.py)
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = RES
sc.view_settings.view_transform = "Standard"
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.92, 0.92, 0.92, 1)
sc.world = w
for i, (r, e) in enumerate([((50, 0, 30), 3.0), ((60, 0, 200), 1.5)]):
    L = bpy.data.lights.new(f"l{i}", "SUN")
    L.energy = e
    lo = bpy.data.objects.new(f"l{i}", L)
    lo.rotation_euler = Euler([math.radians(a) for a in r])
    sc.collection.objects.link(lo)
cam = bpy.data.cameras.new("cam")
cam.type = "ORTHO"
co = bpy.data.objects.new("cam", cam)
sc.collection.objects.link(co)
sc.camera = co
green = bpy.data.materials.new("green")
green.use_nodes = True
green.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.1, 0.9, 0.2, 1)
body.data.materials.clear()
body.data.materials.append(green)
SP = np.array([v.co[:] for a_ in outs for v in a_.data.vertices])
lo3, hi3 = SP.min(0), SP.max(0)
ctr = (lo3 + hi3) / 2
size = max(hi3[2] - lo3[2], hi3[0] - lo3[0], hi3[1] - lo3[1]) * 1.4
tmp = RENDERS / "_tmp"
tmp.mkdir(parents=True, exist_ok=True)
rows = []
for show_body in (False, True):
    body.hide_render = not show_body
    row = []
    for j, yaw in enumerate((0, 90, 180, 35)):
        y = math.radians(yaw)
        cam.ortho_scale = size
        c = Vector(ctr)
        co.location = c + Vector((5 * math.sin(y), -5 * math.cos(y), 0))
        co.rotation_euler = (c - co.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = str(tmp / f"acc_{j}.png")
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(sc.render.filepath)
        row.append(np.array(img.pixels[:]).reshape(RES, RES, 4)[::-1, :, :3])
        bpy.data.images.remove(img)
    rows.append(np.concatenate(row, 1))
sheet = np.concatenate(rows, 0)
h, w_, _ = sheet.shape
img = bpy.data.images.new("sheet", w_, h)
img.pixels = np.concatenate([sheet[::-1], np.ones((h, w_, 1))], -1).ravel().tolist()
img.filepath_raw = str(RENDERS / f"{CHAR}_shell_{PIECE}.png")
img.file_format = "PNG"
img.save()
print("RENDER", img.filepath_raw)
