"""Small modelled trims joined into a garment shell as their own material slots (so dress_goose.py skins them with it,
by the nearest body weights), like add_kneestrap.py:

  blender -b --factory-startup --python scripts/add_trims.py -- --char outfit_grandpa --kind fob
  blender -b --factory-startup --python scripts/add_trims.py -- --char outfit_grandpa --kind braces

fob (chars json "fob"): a pocket watch (gold case + crown + bow) lying on the garment's front, its chain sagging to the
  watch pocket.  {piece: "waistcoat", watch: [x, z], watch_r, watch_t, chain_to: [x, z], chain_sag, chain_r, gold: rgb}
braces (chars json "braces"): dropped braces -- per side one strap from a clip on the front waistband, down round the
  outside of the thigh and up to a clip on the back waistband (worn off the shoulders, hanging in a loop).
  {piece: "breeches", w, t, off, color: rgb, clip: rgb, path: [[azimuth_deg, z], ...]} -- azimuth 0 = centre front,
  90 = the side, 180 = centre back (mirrored for the right side); each point is ray-cast from outside onto the shell.
pockets (chars json "pockets"): knit patch pockets -- a raised copy of the garment under each rectangle, sharing its
  UVs (the knit runs on; pattern_paint.py's chunky_knit paints their ribbed tops).  {piece, items: [{x: [x0, x1],
  z: [z0, z1], depth, lip, band, band_roll, round, res}]} (x mirrored)
buttons (chars json "button_trims"): modelled sew-through buttons (lathed, rim + dish, 4 holes).  {items: [{piece,
  name, x (or "band": centred on the front band, "side", "band_w"), z: [..], r, t, color, roughness}]} --piece picks
watch (chars json "watch"): a detailed pocket watch (case, dial image from make_watch_face.py, crown, bow) with an
  Albert chain of links to "chain_to" and a T-bar.  {piece, watch: [x, z], watch_r, watch_t, lift, chain_to: [x, z],
  chain_sag, link, chain_r, face, gold}
Heights are in the character's build frame. Run right after the shell is (re)built: it adds geometry every time.
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
    return argv[argv.index(name) + 1] if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR, KIND = opt("--char", ""), opt("--kind", "fob")
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
K = cfg[{"buttons": "button_trims"}.get(KIND, KIND)]
PIECE = opt("--piece", K.get("piece", "waistcoat" if KIND in ("fob", "watch") else "breeches"))
GLB = ROOT / "out" / f"{CHAR}-goose" / "shells" / f"{PIECE}.glb"


def srgb(c):
    c = np.array(c[:3]) / 255.0
    return tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)


def material(name, col, rough, metal):
    m = bpy.data.materials.new(f"{CHAR}_{PIECE}_{name}")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = srgb(col)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
shell = next(o for o in bpy.context.scene.objects if o.type == "MESH")
dg = bpy.context.evaluated_depsgraph_get()
me_ = shell.evaluated_get(dg).to_mesh()
bvh = BVHTree.FromPolygons([tuple(shell.matrix_world @ v.co) for v in me_.vertices], [tuple(p.vertices) for p in me_.polygons])
V = np.array([(shell.matrix_world @ v.co)[:] for v in shell.data.vertices])


def onto(o, d, far=0.6):
    """First shell hit from o along d: (point, outward normal)."""
    h = bvh.ray_cast(Vector(o), Vector(d), far)
    if h[0] is None:
        return None
    n = np.array(h[1])
    if n @ np.array(d) > 0:
        n = -n
    return np.array(h[0]), n / np.linalg.norm(n)


def front_hit(x, z):
    return onto(np.array([x, -0.6, z]), (0, 1.0, 0))


def ribbon(bm, pts, nrm, w, t):
    """A flat strap of width w, thickness t along pts (lying on normals nrm)."""
    rings = []
    for i, (p, n) in enumerate(zip(pts, nrm)):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, len(pts) - 1)]
        tg = (b - a) / max(np.linalg.norm(b - a), 1e-9)
        s = np.cross(tg, n)
        s /= max(np.linalg.norm(s), 1e-9)
        rings.append([bm.verts.new(tuple(p + s * sx * w / 2 + n * nz * t)) for sx, nz in ((-1, 0), (1, 0), (1, 1), (-1, 1))])
    for i in range(len(rings) - 1):
        r0, r1 = rings[i], rings[i + 1]
        for k in range(4):
            bm.faces.new((r0[k], r1[k], r1[(k + 1) % 4], r0[(k + 1) % 4]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])


def tube(bm, pts, r, seg=8):
    rings = []
    for i, p in enumerate(pts):
        a, b = pts[max(i - 1, 0)], pts[min(i + 1, len(pts) - 1)]
        tg = (b - a) / max(np.linalg.norm(b - a), 1e-9)
        ref = np.array([0, 0, 1.0]) if abs(tg[2]) < 0.9 else np.array([1.0, 0, 0])
        x = np.cross(tg, ref)
        x /= np.linalg.norm(x)
        y = np.cross(tg, x)
        rings.append([bm.verts.new(tuple(p + r * (math.cos(q) * x + math.sin(q) * y))) for q in np.linspace(0, 2 * math.pi, seg, endpoint=False)])
    for i in range(len(rings) - 1):
        for k in range(seg):
            bm.faces.new((rings[i][k], rings[i + 1][k], rings[i + 1][(k + 1) % seg], rings[i][(k + 1) % seg]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])


def disc(bm, c, n, r, t, seg=28):
    u = np.cross(n, [0, 0, 1.0])
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    ring = lambda off, rr: [bm.verts.new(tuple(c + n * off + rr * (math.cos(a) * u + math.sin(a) * v))) for a in np.linspace(0, 2 * math.pi, seg, endpoint=False)]
    r0, r1, r2 = ring(0.0, r * 0.96), ring(t * 0.6, r), ring(t, r * 0.88)        # a domed case
    for A, B in ((r0, r1), (r1, r2)):
        for k in range(seg):
            bm.faces.new((A[k], B[k], B[(k + 1) % seg], A[(k + 1) % seg]))
    bm.faces.new(r0[::-1])
    bm.faces.new(r2)
    return u, v


def finish(objs_mats):
    new = []
    for name, bm, mat in objs_mats:
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(o)
        me.materials.append(mat)
        me.uv_layers.new(name="UVMap")
        for pg in me.polygons:
            pg.use_smooth = True
        new.append(o)
    bpy.ops.object.select_all(action="DESELECT")
    for o in new:
        o.select_set(True)
    shell.select_set(True)
    bpy.context.view_layer.objects.active = shell
    bpy.ops.object.join()
    bpy.ops.export_scene.gltf(filepath=str(GLB), use_selection=True, export_format="GLB")


if KIND == "fob":
    gold = material("watch_gold", K.get("gold", [200, 160, 76]), 0.28, 1.0)
    wx, wz = K["watch"]
    p, n = front_hit(wx, wz)
    r, t = K.get("watch_r", 0.014), K.get("watch_t", 0.005)
    c = p + n * 0.0015
    bmw = bmesh.new()
    u, v = disc(bmw, c, n, r, t)
    up = np.array([0, 0, 1.0])
    top = c + up * r + n * t * 0.5
    tube(bmw, [top - up * 0.002, top + up * 0.004], 0.0022)                       # crown
    bow = [top + up * 0.004 + 0.0045 * (math.cos(a) * np.array([1.0, 0, 0]) + math.sin(a) * up) + up * 0.0045
           for a in np.linspace(-math.pi * 0.5, math.pi * 1.5, 14)]                 # bow ring
    tube(bmw, bow, 0.0009, seg=6)
    # chain: from the bow, sagging, to the pocket -- lying just off the cloth
    cx, cz = K["chain_to"]
    a3 = np.array([wx, wz + r + 0.01])
    b3 = np.array([cx, cz])
    pts = []
    for s in np.linspace(0, 1, 22):
        xz = a3 + (b3 - a3) * s
        xz[1] -= K.get("chain_sag", 0.02) * 4 * s * (1 - s)
        h = front_hit(xz[0], xz[1])
        if h:
            pts.append(h[0] + h[1] * 0.0028)
    bmc = bmesh.new()
    tube(bmc, pts, K.get("chain_r", 0.0011), seg=6)
    finish([("watch", bmw, gold), ("chain", bmc, gold)])
    print("FOB watch", np.round(c, 3).tolist(), "chain pts", len(pts), "->", GLB)
elif KIND == "braces":
    strap = material("braces", K.get("color", [170, 30, 34]), 0.6, 0.0)
    clipm = material("clip", K.get("clip", [190, 190, 196]), 0.3, 1.0)
    w, t, off = K.get("w", 0.024), K.get("t", 0.0025), K.get("off", 0.002)
    out = []
    for sg in (1, -1):
        pts, nrm = [], []
        path = np.array(K["path"], float)
        az = np.interp(np.linspace(0, len(path) - 1, 60), np.arange(len(path)), path[:, 0])
        zz = np.interp(np.linspace(0, len(path) - 1, 60), np.arange(len(path)), path[:, 1])
        for a_, z_ in zip(az, zz):
            th = math.radians(a_)
            sl = V[np.abs(V[:, 2] - z_) < 0.01]
            half = sl[sl[:, 0] * sg > 0.0] if z_ < K.get("crotch_z", 0.62) else sl          # below the crotch: the leg
            ctr = np.array([(half[:, 0].min() + half[:, 0].max()) / 2 if z_ < K.get("crotch_z", 0.62) else 0.0,
                            (half[:, 1].min() + half[:, 1].max()) / 2, z_])
            d = np.array([math.sin(th) * sg, -math.cos(th), 0.0])
            h = onto(ctr + d * 0.5, -d)
            if h:
                pts.append(h[0] + h[1] * off)
                nrm.append(h[1])
        pts = np.array(pts)
        for _ in range(3):                                     # a strap bridges small dips
            pts[1:-1] = 0.25 * pts[:-2] + 0.5 * pts[1:-1] + 0.25 * pts[2:]
        bm = bmesh.new()
        ribbon(bm, list(pts), nrm, w, t)
        out.append((f"brace_{sg}", bm, strap))
        for i in (0, len(pts) - 1):                            # a metal clip at each end
            bc = bmesh.new()
            p, n = pts[i], nrm[i]
            q = np.cross(n, [0, 0, 1.0])
            q /= np.linalg.norm(q)
            for dz in (-0.012, 0.012):
                pass
            tube(bc, [p + n * t - np.array([0, 0, 0.01]), p + n * t + np.array([0, 0, 0.012])], 0.0035, seg=6)
            out.append((f"clip_{sg}_{i}", bc, clipm))
    finish(out)
    print("BRACES", len(out), "parts ->", GLB)


# ---------------------------------------------------------------- opt-in kinds: pockets, buttons, a detailed watch
def lathe(bm, c, n, prof, seg=32, ref=None):
    """A solid of revolution about n through c from (radius, height) profile points (inner to outer, then back);
    returns the rings. The first point at radius 0 is a centre vertex."""
    u = np.cross(n, ref if ref is not None else [0, 0, 1.0])
    if np.linalg.norm(u) < 1e-6:
        u = np.cross(n, [1.0, 0, 0])
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    rings = []
    for r_, h_ in prof:
        if r_ <= 1e-9:
            rings.append([bm.verts.new(tuple(c + n * h_))])
        else:
            rings.append([bm.verts.new(tuple(c + n * h_ + r_ * (math.cos(a) * u + math.sin(a) * v)))
                          for a in np.linspace(0, 2 * math.pi, seg, endpoint=False)])
    for A, B in zip(rings[:-1], rings[1:]):
        if len(A) == 1:
            for k in range(seg):
                bm.faces.new((A[0], B[k], B[(k + 1) % seg]))
        elif len(B) == 1:
            for k in range(seg):
                bm.faces.new((A[k], B[0], A[(k + 1) % seg]))
        else:
            for k in range(seg):
                bm.faces.new((A[k], B[k], B[(k + 1) % seg], A[(k + 1) % seg]))
    return u, v


def torus(bm, c, n, R_, r_, seg=24, sseg=8, u=None):
    if u is None:
        u = np.cross(n, [0, 0, 1.0])
        if np.linalg.norm(u) < 1e-6:
            u = np.cross(n, [1.0, 0, 0])
    u = np.array(u, float) / np.linalg.norm(u)
    v = np.cross(n, u)
    rings = []
    for a in np.linspace(0, 2 * math.pi, seg, endpoint=False):
        cr = c + R_ * (math.cos(a) * u + math.sin(a) * v)
        rd = math.cos(a) * u + math.sin(a) * v
        rings.append([bm.verts.new(tuple(cr + r_ * (math.cos(b) * rd + math.sin(b) * n)))
                      for b in np.linspace(0, 2 * math.pi, sseg, endpoint=False)])
    for i in range(seg):
        A, B = rings[i], rings[(i + 1) % seg]
        for k in range(sseg):
            bm.faces.new((A[k], B[k], B[(k + 1) % sseg], A[(k + 1) % sseg]))


def front_edge_x(z, sg):
    """x of the garment's open front edge (side sg) at height z (open edges by position, nearest in z)."""
    from collections import Counter
    key = lambda i: tuple(np.round(V[i], 5))  # noqa: E731
    cnt = Counter()
    for pg in shell.data.polygons:
        for ek in pg.edge_keys:
            a_, b_ = sorted([key(ek[0]), key(ek[1])])
            cnt[(a_, b_)] += 1
    E = np.array([np.array(a_) for (a_, b_), k_ in cnt.items() if k_ == 1] + [np.array(b_) for (a_, b_), k_ in cnt.items() if k_ == 1])
    E = E[(E[:, 0] * sg > 0) & (np.abs(E[:, 0]) < 0.16) & (E[:, 1] < 0)]
    return float(E[np.argmin(np.abs(E[:, 2] - z)), 0])


def join_keep_material(objs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    shell.select_set(True)
    bpy.context.view_layer.objects.active = shell
    bpy.ops.object.join()
    bpy.ops.export_scene.gltf(filepath=str(GLB), use_selection=True, export_format="GLB")


if KIND == "pockets":
    # knit patch pockets: a raised pillow over each rectangle (front-projected onto the garment), its edge dropping
    # back to the cloth with a skirt just inside it. Each pocket has its own planar UVs in a small texture resampled
    # from the garment's finished colour + normal maps under it (the garment's own UV islands are cut up there), then
    # a ribbed top band ("band", ribs "rib_pitch") and a sewn edge are painted on. Run after pattern_paint.py.
    me_s = shell.evaluated_get(dg).to_mesh()
    uvl = me_s.uv_layers.active.data
    mat_g = shell.data.materials[0]
    col_img = nrm_img = None
    for nd in mat_g.node_tree.nodes:
        if nd.type == "TEX_IMAGE" and nd.image is not None:
            if nd.image.colorspace_settings.name == "Non-Color":
                nrm_img = nd.image
            else:
                col_img = nd.image
    CI = np.array(col_img.pixels[:], np.float32).reshape(col_img.size[1], col_img.size[0], -1)[..., :3]
    NI = (np.array(nrm_img.pixels[:], np.float32).reshape(nrm_img.size[1], nrm_img.size[0], -1)[..., :3] * 2 - 1
          if nrm_img is not None else None)
    Vs = np.array([v.co[:] for v in me_s.vertices])

    def sample(img, uv):
        h_, w_ = img.shape[:2]
        x_, y_ = uv[0] * w_ - 0.5, uv[1] * h_ - 0.5
        x0_, y0_ = int(np.floor(x_)) % w_, int(np.floor(y_)) % h_
        x1_, y1_ = (x0_ + 1) % w_, (y0_ + 1) % h_
        fx_, fy_ = x_ - np.floor(x_), y_ - np.floor(y_)
        return ((img[y0_, x0_] * (1 - fx_) + img[y0_, x1_] * fx_) * (1 - fy_)
                + (img[y1_, x0_] * (1 - fx_) + img[y1_, x1_] * fx_) * fy_)

    AZ = None                                   # (set per pocket: "az" items lie round the body, not front-projected)

    def hit_info(x, z):
        if AZ is not None:                      # x = arc length round the body axis at radius AZ[0], side AZ[1]
            a_ = x * AZ[1] / AZ[0]
            d_ = np.array([math.sin(a_), -math.cos(a_), 0.0])
            h = bvh.ray_cast(Vector(np.array([0.0, AZ[2], z]) + d_ * 0.6), Vector(-d_), 0.9)
        else:
            h = bvh.ray_cast(Vector((x, -0.6, z)), Vector((0, 1.0, 0)), 0.9)
        if h[0] is None:
            return None
        p, n_ = np.array(h[0]), np.array(h[1])
        if n_[1] > 0:
            n_ = -n_
        pg = me_s.polygons[h[2]]
        vi, li = list(pg.vertices)[:3], list(pg.loop_indices)[:3]
        A_ = Vs[vi]
        U_ = np.array([uvl[k].uv[:] for k in li])
        M_ = np.stack([A_[0] - A_[2], A_[1] - A_[2]], 1)
        l12 = np.linalg.lstsq(M_, p - A_[2], rcond=None)[0]
        uvp = np.array([l12[0], l12[1], 1 - l12.sum()]) @ U_
        e1, e2 = A_[1] - A_[0], A_[2] - A_[0]
        (du1, dv1), (du2, dv2) = U_[1] - U_[0], U_[2] - U_[0]
        rr_ = du1 * dv2 - du2 * dv1
        T_ = (e1 * dv2 - e2 * dv1) / rr_ if abs(rr_) > 1e-14 else np.array([1.0, 0, 0])
        B_ = (e2 * du1 - e1 * du2) / rr_ if abs(rr_) > 1e-14 else np.array([0, 0, 1.0])
        return p, n_, uvp, T_, B_

    its = K["items"]
    TW = K.get("tex_w", 256)                         # texels across one pocket
    cells = []
    for it in its:
        for sg in (1, -1):
            cells.append((it, sg))
    def pocket_w(it):
        return (math.radians(it["az"][1] - it["az"][0]) * it.get("r0", 0.21)) if "az" in it else it["x"][1] - it["x"][0]
    TH = max(int(round(TW * (it["z"][1] - it["z"][0]) / pocket_w(it))) for it, _ in cells)
    AW = TW * len(cells)
    acol = np.zeros((TH, AW, 3), np.float32)
    anrm = np.zeros((TH, AW, 3), np.float32)
    anrm[..., 2] = 1.0
    pmat = bpy.data.materials.new(f"{CHAR}_{PIECE}_pocket")
    pmat.use_nodes = True
    pb = pmat.node_tree.nodes["Principled BSDF"]
    gbs = next(nd for nd in mat_g.node_tree.nodes if nd.type == "BSDF_PRINCIPLED")
    pb.inputs["Roughness"].default_value = gbs.inputs["Roughness"].default_value
    pb.inputs["Specular IOR Level"].default_value = gbs.inputs["Specular IOR Level"].default_value
    objs = []
    for ci, (it, sg) in enumerate(cells):
        if "az" in it:                          # degrees from centre front; x below = arc length (m) at radius r0
            r0_ = it.get("r0", 0.21)
            x0, x1 = [math.radians(a_) * r0_ for a_ in it["az"]]
            AZ = (r0_, sg, it.get("yc", 0.03))
        else:
            x0, x1 = it["x"]
            AZ = None
        z0, z1 = it["z"]
        band, rp = it.get("band", 0.018), it.get("rib_pitch", 0.0065)
        # texture: per texel the garment colour / normal under it, re-expressed in the pocket's (s = outward x, t = up) frame
        th_ = int(round(TW * (z1 - z0) / (x1 - x0)))
        for tj in range(th_):
            z = z0 + (tj + 0.5) / th_ * (z1 - z0)
            for si in range(TW):
                xa = x0 + (si + 0.5) / TW * (x1 - x0)
                hi = hit_info(xa if AZ is not None else sg * xa, z)
                if hi is None:
                    continue
                p, n_, uvp, T_, B_ = hi
                c_ = sample(CI, uvp)
                nn = n_
                if NI is not None:
                    tn = sample(NI, uvp)
                    Tn = T_ - n_ * (T_ @ n_)
                    Tn /= max(np.linalg.norm(Tn), 1e-12)
                    Bn = np.cross(n_, Tn) * (1.0 if np.cross(n_, Tn) @ B_ >= 0 else -1.0)
                    nn = tn[0] * Tn + tn[1] * Bn + tn[2] * n_
                    nn /= max(np.linalg.norm(nn), 1e-9)
                Tp = (np.array([math.cos(xa / AZ[0]) * sg, math.sin(xa / AZ[0]), 0.0]) if AZ is not None
                      else np.array([sg, 0.0, 0.0]))
                Tp = Tp - n_ * (Tp @ n_)
                Tp /= max(np.linalg.norm(Tp), 1e-12)
                Bp = np.cross(n_, Tp)
                if Bp[2] < 0:
                    Bp = -Bp
                nt = np.array([nn @ Tp, nn @ Bp, nn @ n_])
                if z > z1 - band:                      # ribbed top: k1p1 ribs up the band
                    ph = 2 * math.pi * xa / rp
                    hr = (0.5 + 0.5 * math.cos(ph))
                    c_ = np.array(cfg["patterns"][PIECE]["color"][:3], float) / 255.0 * it.get("band_shade", 0.9)
                    c_ = c_ * (0.62 + 0.38 * hr ** 0.8) * (0.86 + 0.14 * abs(math.sin(math.pi * z / 0.0068)))
                    sl = -it.get("rib_amp", 0.0022) * (-math.sin(ph) * 2 * math.pi / rp) * 0.5
                    nt = np.array([sl, 0.0, 1.0])
                    nt /= np.linalg.norm(nt)
                    if z1 - z < 0.0035:                # the band's cast-off edge rolls over
                        c_ = c_ * 0.92
                de = min(xa - x0, x1 - xa, z - z0, z1 - z)
                if de < it.get("seam", 0.0022):          # sewn on: the edge stitches sit in a slight shadow
                    c_ = c_ * 0.72
                acol[tj, ci * TW + si] = c_
                anrm[tj, ci * TW + si] = nt
        # geometry
        res = it.get("res", 0.0035)
        nx, nz = max(int((x1 - x0) / res), 4), max(int((z1 - z0) / res), 4)
        depth, lip = it.get("depth", 0.005), it.get("lip", 0.002)
        G = {}
        for i in range(nx + 1):
            for j in range(nz + 1):
                xa = x0 + (x1 - x0) * i / nx
                z = z0 + (z1 - z0) * j / nz
                hi = hit_info(xa if AZ is not None else sg * xa, z)
                if hi is None:
                    continue
                p, n_ = hi[0], hi[1]
                de = min(i, nx - i) * (x1 - x0) / nx, min(j, nz - j) * (z1 - z0) / nz
                t_ = min(1.0, min(de) / it.get("round", 0.012))
                t_ = t_ * t_ * (3 - 2 * t_)
                hh = lip + depth * t_ * (1.0 - 0.25 * (j / nz) ** 2) + (it.get("band_roll", 0.0012) if z > z1 - band else 0.0)
                uv_ = ((ci * TW + (i / nx) * th_ * 0 + i / nx * TW) / AW, (j / nz) * th_ / TH)
                G[(i, j)] = (p + n_ * hh, p - n_ * 0.0015, uv_)
        bm = bmesh.new()
        uvL = bm.loops.layers.uv.new("UVMap")
        top = {k: bm.verts.new(tuple(v_[0])) for k, v_ in G.items()}
        ring = ([(i, 0) for i in range(nx)] + [(nx, j) for j in range(nz)] + [(i, nz) for i in range(nx, 0, -1)]
                + [(0, j) for j in range(nz, 0, -1)])
        bot = {k: bm.verts.new(tuple(G[k][1])) for k in ring if k in G}
        for i in range(nx):
            for j in range(nz):
                ks = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)]
                if all(k in top for k in ks):
                    ks_ = ks if sg > 0 else ks[::-1]
                    f = bm.faces.new([top[k] for k in ks_])
                    for lp, k in zip(f.loops, ks_):
                        lp[uvL].uv = G[k][2]
        for a_, b_ in zip(ring, ring[1:] + ring[:1]):
            if a_ in bot and b_ in bot:
                ks_ = [(bot, a_), (bot, b_), (top, b_), (top, a_)]
                if sg < 0:
                    ks_ = ks_[::-1]
                f = bm.faces.new([d_[k] for d_, k in ks_])
                for lp, (d_, k) in zip(f.loops, ks_):
                    lp[uvL].uv = G[k][2]
        bm.normal_update()
        me = bpy.data.meshes.new(f"pocket_{ci}")
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new(f"pocket_{ci}", me)
        bpy.context.scene.collection.objects.link(o)
        me.materials.append(pmat)
        for pg in me.polygons:
            pg.use_smooth = True
        objs.append(o)
        print("BRACES pocket", ci, "verts", len(me.vertices), "tex", TW, "x", th_)
    pc_img = bpy.data.images.new(f"{CHAR}_{PIECE}_pocket_color", AW, TH, alpha=False)
    pc_img.pixels = np.concatenate([acol, np.ones((TH, AW, 1), np.float32)], -1).ravel().tolist()
    pc_img.pack()
    pn_img = bpy.data.images.new(f"{CHAR}_{PIECE}_pocket_normal", AW, TH, alpha=False)
    pn_img.colorspace_settings.name = "Non-Color"
    pn_img.pixels = np.concatenate([anrm * 0.5 + 0.5, np.ones((TH, AW, 1), np.float32)], -1).ravel().tolist()
    pn_img.pack()
    t1 = pmat.node_tree.nodes.new("ShaderNodeTexImage")
    t1.image = pc_img
    pmat.node_tree.links.new(t1.outputs["Color"], pb.inputs["Base Color"])
    t2 = pmat.node_tree.nodes.new("ShaderNodeTexImage")
    t2.image = pn_img
    nm = pmat.node_tree.nodes.new("ShaderNodeNormalMap")
    pmat.node_tree.links.new(t2.outputs["Color"], nm.inputs["Color"])
    pmat.node_tree.links.new(nm.outputs["Normal"], pb.inputs["Normal"])
    join_keep_material(objs)
elif KIND == "buttons":
    # modelled buttons: a lathed body (raised rim, dished centre) with four thread holes, on the garment's surface;
    # "x": "band" = the middle of the front band ("band_w" in from the open edge, the side of "side")
    objs = []
    for it in [b for b in K["items"] if b.get("piece") == PIECE]:
        col = it.get("color", [92, 54, 30])
        mb = material(f"button_{it.get('name', 'b')}", col, it.get("roughness", 0.35), 0.0)
        bs_ = mb.node_tree.nodes["Principled BSDF"]
        bs_.inputs["Specular IOR Level"].default_value = it.get("spec", 0.6)
        mh = material(f"buttonhole_{it.get('name', 'b')}", [int(col[0] * 0.25), int(col[1] * 0.25), int(col[2] * 0.25)], 0.8, 0.0)
        r, t = it.get("r", 0.009), it.get("t", 0.0035)
        prof = [(0.0, 0.55 * t), (0.42 * r, 0.6 * t), (0.62 * r, 0.92 * t), (0.8 * r, 1.0 * t), (0.95 * r, 0.82 * t),
                (1.0 * r, 0.45 * t), (0.96 * r, 0.0)]
        for z in it["z"]:
            sg = it.get("side", -1)
            x = it["x"] if it["x"] != "band" else front_edge_x(z, sg) + sg * it.get("band_w", 0.026) / 2
            h = front_hit(x, z)
            if h is None:
                continue
            p, n_ = h
            bm = bmesh.new()
            u, v = lathe(bm, p + n_ * it.get("lift", 0.0006), n_, prof, seg=it.get("seg", 28))
            o = bpy.data.meshes.new("btn")
            bm.normal_update()
            bm.to_mesh(o)
            bm.free()
            ob = bpy.data.objects.new("btn", o)
            bpy.context.scene.collection.objects.link(ob)
            o.materials.append(mb)
            objs.append(ob)
            bmh = bmesh.new()                       # thread holes: dark discs just above the dish
            for a in (45, 135, 225, 315):
                q = p + n_ * (it.get("lift", 0.0006) + 0.6 * t + 0.00025) + 0.2 * r * (math.cos(math.radians(a)) * u + math.sin(math.radians(a)) * v)
                ring_ = [bmh.verts.new(tuple(q + 0.07 * r * (math.cos(b) * u + math.sin(b) * v))) for b in np.linspace(0, 2 * math.pi, 8, endpoint=False)]
                bmh.faces.new(ring_)
            oh = bpy.data.meshes.new("btnh")
            bmh.normal_update()
            bmh.to_mesh(oh)
            bmh.free()
            obh = bpy.data.objects.new("btnh", oh)
            bpy.context.scene.collection.objects.link(obh)
            oh.materials.append(mh)
            objs.append(obh)
        print("BRACES buttons", it.get("name", ""), len(it["z"]), "on", PIECE)
    for o in objs:
        o.data.uv_layers.new(name="UVMap")
        for pg in o.data.polygons:
            pg.use_smooth = True
    join_keep_material(objs)
elif KIND == "watch":
    # a detailed open-face pocket watch: lathed gold case (back, band, bezel), an enamel dial textured with
    # make_watch_face.py's image, a domed crystal, pendant + crown + bow; an Albert chain of real links swagging from
    # the bow to "chain_to" (a buttonhole / the pocket), with a T-bar
    gold = material("watch_gold", K.get("gold", [212, 170, 80]), K.get("gold_rough", 0.22), 1.0)
    wx, wz = K["watch"]
    p, n = front_hit(wx, wz)
    r, t = K.get("watch_r", 0.02), K.get("watch_t", 0.007)
    c = p + n * K.get("lift", 0.0035)
    up = np.array([0, 0, 1.0]) - n * n[2]
    up /= np.linalg.norm(up)
    bm = bmesh.new()
    lathe(bm, c, n, [(0.0, 0.0), (0.7 * r, -0.0005), (0.93 * r, 0.0006), (r, 0.0025), (r, 0.0045), (0.97 * r, 0.0058),
                     (0.9 * r, 0.0062), (0.86 * r, 0.0056), (0.86 * r, 0.0052)], seg=48, ref=up)
    tc = c + up * r * 0.99
    lathe(bm, tc, up, [(0.0, -0.001), (0.0026, -0.001), (0.0026, 0.0035), (0.0018, 0.0042)], seg=16)   # pendant
    lathe(bm, tc + up * 0.0042, up, [(0.0, 0.0), (0.0034, 0.0), (0.0036, 0.0012), (0.0036, 0.0032), (0.0034, 0.0044), (0.0, 0.0044)], seg=20)
    torus(bm, tc + up * 0.0042 + up * 0.0072, n, 0.0058, 0.0011, seg=24, sseg=8, u=up)          # bow (in the dial plane)
    mw = bpy.data.meshes.new("watch")
    bm.normal_update()
    bm.to_mesh(mw)
    bm.free()
    ow = bpy.data.objects.new("watch", mw)
    bpy.context.scene.collection.objects.link(ow)
    mw.materials.append(gold)
    mw.uv_layers.new(name="UVMap")
    # dial: a disc with planar UVs, the face image upright (12 toward "up")
    dial = bpy.data.materials.new(f"{CHAR}_{PIECE}_watch_dial")
    dial.use_nodes = True
    db = dial.node_tree.nodes["Principled BSDF"]
    db.inputs["Roughness"].default_value = 0.25
    tx = dial.node_tree.nodes.new("ShaderNodeTexImage")
    tx.image = bpy.data.images.load(str(ROOT / K.get("face", "refs/textures/watch_face.png")))
    tx.image.pack()
    dial.node_tree.links.new(tx.outputs["Color"], db.inputs["Base Color"])
    right = np.cross(up, n)
    bm = bmesh.new()
    uvL = bm.loops.layers.uv.new("UVMap")
    cen = bm.verts.new(tuple(c + n * 0.0053))
    k_ = 48
    rim = [bm.verts.new(tuple(c + n * 0.0053 + 0.86 * r * (math.cos(a) * right + math.sin(a) * up))) for a in np.linspace(0, 2 * math.pi, k_, endpoint=False)]
    for i in range(k_):
        a0, a1 = 2 * math.pi * i / k_, 2 * math.pi * (i + 1) / k_
        f = bm.faces.new((cen, rim[i], rim[(i + 1) % k_]))
        for lp, uvp in zip(f.loops, [(0.5, 0.5), (0.5 + 0.5 * math.cos(a0), 0.5 + 0.5 * math.sin(a0)), (0.5 + 0.5 * math.cos(a1), 0.5 + 0.5 * math.sin(a1))]):
            lp[uvL].uv = uvp
    bm.normal_update()
    md = bpy.data.meshes.new("dial")
    bm.to_mesh(md)
    bm.free()
    od = bpy.data.objects.new("dial", md)
    bpy.context.scene.collection.objects.link(od)
    md.materials.append(dial)
    if (np.array(md.polygons[0].normal) @ n) < 0:
        for pg in md.polygons:
            pg.flip()
    # Albert chain: links alternating flat / edge-on along a sagging curve from the bow to chain_to
    a3 = tc + up * 0.0042 + up * 0.0125
    cx, cz = K["chain_to"]
    hb = front_hit(cx, cz)
    b3 = hb[0] + hb[1] * 0.0025
    path = []
    for s in np.linspace(0, 1, 60):
        q = a3 * (1 - s) + b3 * s
        q[2] -= K.get("chain_sag", 0.03) * 4 * s * (1 - s)
        h = onto(q + np.array([0, -0.3, 0]), (0, 1.0, 0))
        path.append((h[0] + h[1] * 0.0022) if h else q)
    path = np.array(path)
    seg_len = np.r_[0, np.cumsum(np.linalg.norm(np.diff(path, axis=0), axis=1))]
    L_ = K.get("link", 0.0042)
    bmc = bmesh.new()
    nlinks = int(seg_len[-1] / (L_ * 0.78))
    for i in range(nlinks):
        s_ = (i + 0.5) * seg_len[-1] / nlinks
        q = np.array([np.interp(s_, seg_len, path[:, k]) for k in range(3)])
        q2 = np.array([np.interp(min(s_ + 0.001, seg_len[-1]), seg_len, path[:, k]) for k in range(3)])
        tg = (q2 - q) / max(np.linalg.norm(q2 - q), 1e-9)
        hq = onto(q + np.array([0, -0.3, 0]), (0, 1.0, 0))
        nq = hq[1] if hq else n
        side = np.cross(tg, nq)
        plane_n = nq if i % 2 == 0 else side / max(np.linalg.norm(side), 1e-9)
        bmt = bmesh.new()
        torus(bmt, q, plane_n, L_ * 0.38, K.get("chain_r", 0.00055), seg=12, sseg=6, u=tg)
        # stretch along the chain: an oval link
        for v_ in bmt.verts:
            d_ = np.array(v_.co) - q
            v_.co = Vector(q + d_ + tg * (d_ @ tg) * 0.45)
        tmp = bpy.data.meshes.new("lk")
        bmt.to_mesh(tmp)
        bmt.free()
        bmc.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
    tb = path[-1]                                   # T-bar through the buttonhole
    tgb = path[-1] - path[-3]
    tgb /= np.linalg.norm(tgb)
    bar = np.cross(tgb, hb[1])
    bar /= np.linalg.norm(bar)
    lathe(bmc, tb - bar * 0.009, bar, [(0.0, 0.0), (0.0012, 0.0), (0.0012, 0.018), (0.0, 0.018)], seg=10)
    mc = bpy.data.meshes.new("chain")
    bmc.normal_update()
    bmc.to_mesh(mc)
    bmc.free()
    oc = bpy.data.objects.new("chain", mc)
    bpy.context.scene.collection.objects.link(oc)
    mc.materials.append(gold)
    mc.uv_layers.new(name="UVMap")
    for o in (ow, oc):
        for pg in o.data.polygons:
            pg.use_smooth = True
    print("FOB watch r", r, "at", np.round(c, 3).tolist(), "links", nlinks, "->", GLB)
    join_keep_material([ow, od, oc])
