"""P3 polish: design a garment as ONE clean, reusable piece fitted to the body (first: male breeches).

  blender -b --factory-startup --python scripts/make_garment.py -- --char outfit_male --piece breeches \
      [--tris 2600] [--tex 1024]

The extracted piece (pieces/<piece>.glb) is only a SHAPE guide; the garment itself is built from the body
the outfit is worn on (chars json "body_shape" via bodyshape.py), so it has no shards, holes or seams to
patch, and the same recipe refits another body. Recipe: chars json "garment_design" {piece: {kind: breeches | shirt, ...}}; the cut planes,
openings and covered body vertices follow the kind (shirt: neck base, tilted tucked hem, both wrists).
  1. region: body faces between the waist line (z_top at the front, rising "back_rise" m per m toward the
     back so it covers the tail base) and z_bot (below the knee, inside the boots), arms / hands
     dropped; the tail is removed and its hole capped with a soft seat bump (the tail is hidden under the
     breeches, P3.5 FORCE); a single surface: pelvis + both legs, continuous through the crotch.
  2. ease (distance off the body) per vertex: the extracted piece's outer surface along the normal (its
     jodhpur flare), heavily smoothed, clamped [ease_min, ease_max]; tight at the waistband and knee
     band; limited to 40 % of the gap to the other leg so the crotch never self-intersects.
  3. game mesh (lo): body region subdivided once, offset by the ease, QEM-decimated to --tris.
     detail mesh (hi): two more subdivisions + displacement: raised waistband and knee band with stitch
     grooves, fly placket, slit pockets, front creases, side seams, inseams, centre-back seam, soft folds
     above the knee and on the flare.
  4. textures: normal map baked hi -> lo; base colour = neutral tweed DETAIL texture (procedural weave +
     mottle, grooves darkened) x ONE colour factor (glTF baseColorFactor via a multiply node) -- recolouring
     = changing the factor ("colors" in the recipe are rendered as variants).
  5. out/<char>-goose/shells/<piece>.glb + .json (replaces build_shell.py's shell; "covers" = the body band
     dress_goose.py hides) + <piece>_weights.npz (the body's own skin weights per vertex) and
     renders/<char>_garment_<piece>.png: garment alone / on the bright green base body, front, side, back,
     3-4, one row per colour.
"""
import json
import math
import sys
import time
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

sys.path.insert(0, str(Path(__file__).parent))
import bodyshape  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]


def opt(name, default, cast=str):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


CHAR = opt("--char", "outfit_male")
PIECE = opt("--piece", "breeches")
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{CHAR}-goose"
OUT = D / "shells"
RENDERS = ROOT / "renders"
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
R = cfg["garment_design"][PIECE]
TRIS = opt("--tris", R.get("tris", 2600), int)
TEX = opt("--tex", R.get("tex", 1024), int)
RES = 640
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.1f}s]", *a, flush=True)


def load(path):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [o for o in bpy.context.scene.objects if o not in before]


def only_select(*obs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


def srgb_lin(c):
    c = np.array(c[:3], float) / 255.0
    return np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)


def mesh_vn(me):
    """Vertex positions + normals of a mesh (object space = world: transforms applied)."""
    P = np.array([v.co[:] for v in me.vertices])
    N = np.array([v.normal[:] for v in me.vertices])
    return P, N


def edges_of(me):
    return np.array([e.vertices[:] for e in me.edges])


def smooth_field(f, ed, it, pin=None):
    """Edge-neighbour averaging of a per-vertex field (pin: vertices that keep their value)."""
    deg = np.maximum(np.bincount(ed.ravel(), minlength=len(f)), 1)
    shape = (-1,) + (1,) * (f.ndim - 1)
    for _ in range(it):
        acc = np.zeros_like(f)
        np.add.at(acc, ed[:, 0], f[ed[:, 1]])
        np.add.at(acc, ed[:, 1], f[ed[:, 0]])
        nf = 0.5 * f + 0.5 * acc / deg.reshape(shape)
        f = np.where(pin.reshape(shape), f, nf) if pin is not None else nf
    return f


bpy.ops.wm.read_factory_settings(use_empty=True)

# ---- body the garment is worn on + bones
rig = load(ROOT / "out" / "base-goose" / "base_goose_rigged.glb")
arm = next(o for o in rig if o.type == "ARMATURE")
body = next(o for o in rig if o.type == "MESH" and o.name.startswith("base_goose_game"))
only_select(body)
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
for m in list(body.modifiers):
    body.modifiers.remove(m)
gn = [g.name for g in body.vertex_groups]
Wb = np.zeros((len(body.data.vertices), len(gn)))
for v in body.data.vertices:
    for g in v.groups:
        Wb[v.index, g.group] = g.weight
Wb /= np.maximum(Wb.sum(1, keepdims=True), 1e-9)
# shells_on_base: the garments are built on the BASE body; dress_goose.py applies the shape last (as it does)
T = bodyshape.body_transforms(ROOT, CHAR, arm) if cfg.get("body_shape", "base") != "base" and     not cfg.get("shells_on_base") else None
if T:
    V0 = np.array([v.co[:] for v in body.data.vertices])
    body.data.vertices.foreach_set("co", bodyshape.deform(V0, Wb, gn, arm, T).ravel())
    body.data.update()
bone = {b.name: (np.array(arm.matrix_world @ b.head_local), np.array(arm.matrix_world @ b.tail_local)) for b in arm.data.bones}
if T:
    bone = {k: (np.array(T[k]["head"]) if k in T else h, t) for k, (h, t) in bone.items()}
for o in rig:
    if o is not body:
        bpy.data.objects.remove(o)
dom = np.array(gn)[Wb.argmax(1)]
is_arm = np.array([("Arm" in d) or ("Hand" in d) or ("Shoulder" in d) for d in dom])
is_tail = dom == "Tail"
BPv = np.array([v.co[:] for v in body.data.vertices])
body_noarm = BVHTree.FromPolygons([tuple(x) for x in BPv],
                                  [list(p.vertices) for p in body.data.polygons if not is_arm[list(p.vertices)].any()])
TAIL_ROOT = bone["Tail"][0]
CROTCH_Z = min(bone["LeftUpLeg"][0][2], bone["RightUpLeg"][0][2])
Z_TOP, Z_BOT = R["z_top"], R["z_bot"]
RISE, Y0 = R.get("back_rise", 0.0), R.get("rise_y0", -0.10)   # waist line rises toward the back (tilted plane)


def ztop(y):
    return Z_TOP + RISE * (np.asarray(y) - Y0)
log("crotch", round(float(CROTCH_Z), 3), "z", Z_TOP, Z_BOT)
KIND = R.get("kind", "breeches")
is_hand = np.array(["Hand" in d for d in dom])
SIDES = (("Left", 1), ("Right", -1))
# cut planes: (point, normal, keep: -1 = the side away from the normal / +1 = toward it, x-side filter)
if KIND in ("shirt", "coat", "glove"):
    Z_NECK = R.get("z_neck", 1.28)
    WRIST = {}
    # the hand bone starts at the joint, but its first ~hand-width is feathered: the visible wrist is
    # where the body texture turns to dark skin -> the cuff ends there (+ "wrist_offset")
    img = None
    for m_ in body.data.materials:
        for l_ in m_.node_tree.links:
            if l_.to_socket.name == "Base Color" and l_.from_node.type == "TEX_IMAGE":
                img = l_.from_node.image
    lum = None
    if img is not None:
        IW, IH = img.size
        px = np.array(img.pixels[:], np.float32).reshape(IH, IW, -1)[..., :3]
        uvl = body.data.uv_layers.active.data
        vuv = np.zeros((len(BPv), 2))
        for lp_ in body.data.loops:
            vuv[lp_.vertex_index] = uvl[lp_.index].uv
        lum = px[np.clip((vuv[:, 1] * IH).astype(int), 0, IH - 1), np.clip((vuv[:, 0] * IW).astype(int), 0, IW - 1)] @ [0.3, 0.59, 0.11]
    for s, sg in SIDES:
        hh = bone[f"{s}Hand"][0]
        dd = hh - bone[f"{s}ForeArm"][0]
        dd /= np.linalg.norm(dd)
        s_tr = 0.0
        if lum is not None:
            hv = np.flatnonzero(np.array([d.startswith(f"{s}Hand") for d in dom]))
            sv = (BPv[hv] - hh) @ dd
            bins = [(b0, np.median(lum[hv][(sv >= b0) & (sv < b0 + 0.01)])) for b0 in np.arange(-0.02, 0.2, 0.01)
                    if ((sv >= b0) & (sv < b0 + 0.01)).sum() >= 4]
            if bins:
                ref_l = np.median([l_ for b0, l_ in bins if b0 < 0.02])
                dark = [b0 for b0, l_ in bins if b0 >= 0.0 and l_ < R.get("wrist_dark", 0.6) * ref_l]
                s_tr = float(dark[0]) if dark else 0.0
        log("visible wrist", s, "mm past the joint", round(s_tr * 1000))
        WRIST[sg] = (hh, dd, s_tr)
    s_sym = max(w[2] for w in WRIST.values())          # the goose is symmetric (one side's texture can mislead)
    for sg in list(WRIST):
        hh, dd, _ = WRIST[sg]
        WRIST[sg] = (hh + dd * (s_sym + R.get("wrist_offset", 0.0)), dd)
    PLANES = [((0, 0, Z_NECK), (0, 0, 1), -1, 0), ((0, Y0, Z_BOT), (0, -RISE, 1), 1, 2)] + \
             [(tuple(WRIST[sg][0]), tuple(WRIST[sg][1]), -1, sg) for _, sg in SIDES]
    R.setdefault("seat_bump", 0.0)
    R.setdefault("seat_r", 1e-4)
    if R.get("hem_points"):
        # pointed bodice hem (basque): the plane hem drops below, an exact field cut makes the points --
        # centre front dips to z_front, rises to z_side at |x| side_x, level z_back at the back
        HP_ = R["hem_points"]
        core_ = BPv[(np.abs(BPv[:, 0]) < 0.15) & ~np.array([("Arm" in d) or ("Hand" in d) or d == "Tail" for d in dom])]
        ZS_ = np.arange(0.5, 1.5, 0.01)
        YC_ = np.array([(lambda nb: (nb[:, 1].min() + nb[:, 1].max()) / 2 if len(nb) else 0.0)(core_[np.abs(core_[:, 2] - zz) < 0.012]) for zz in ZS_])

        def ycf(z):
            return np.interp(z, ZS_, YC_)

        def hem_z(x, y, z):
            fr = np.clip((ycf(z) - y) / 0.05 + 0.5, 0, 1)
            zf = np.interp(np.abs(x), HP_["x"], HP_["z"])
            return fr * zf + (1 - fr) * HP_["z_back"]

        def resid(c):
            if abs(c[0]) > 0.2:
                return {"hem": 9.0}
            return {"hem": float(c[2] - hem_z(c[0], c[1], c[2]))}

        def inside_amount(c):
            return resid(c)["hem"]
elif KIND == "vest":
    # outline (no planes but the back neck): pointed front hem, V opening with small lapels, deep armholes
    Z_NECK = R["z_neck"]
    V_ = R["outline"]
    core_ = BPv[(np.abs(BPv[:, 0]) < 0.15) & ~np.array([("Arm" in d) or ("Hand" in d) or d == "Tail" for d in dom])]

    def yc(z):
        z = np.atleast_1d(z)
        out = np.empty(len(z))
        for i_, zz in enumerate(z):
            nb = core_[np.abs(core_[:, 2] - zz) < 0.012]
            out[i_] = (nb[:, 1].min() + nb[:, 1].max()) / 2 if len(nb) else 0.0
        return out

    ZS_ = np.arange(0.6, 1.5, 0.01)
    YC_ = yc(ZS_)
    for _ in range(8):                             # a smooth centre line (the side seam follows it)
        YC_[1:-1] = 0.25 * YC_[:-2] + 0.5 * YC_[1:-1] + 0.25 * YC_[2:]

    def ycf(z):
        return np.interp(z, ZS_, YC_)

    def hem_z(x, y, z):
        """Hem height under a point: front (y < centre) points at |x| = point_x, small notch at the
        centre front, level at the sides and back."""
        fr = np.clip((ycf(z) - y) / 0.05 + 0.5, 0, 1)
        zf = np.interp(np.abs(x), [0, V_["point_x"], V_["side_x"]], [V_["z_notch"], V_["z_point"], V_["z_side"]])
        return fr * zf + (1 - fr) * V_["z_back"]

    def v_w(z):
        """Half width of the V opening at height z (0 below the top button)."""
        return V_["v_top_w"] * np.clip((z - V_["z_vbot"]) / (Z_NECK - V_["z_vbot"]), 0, 1) ** V_.get("v_pow", 0.9)

    ARMC = {sg: bone[f"{s}Arm"][0] + np.array(V_.get("arm_off", [0, 0, -0.035])) for s, sg in SIDES}
    ARMR = V_["arm_r"]
    ARMW = Wb[:, [i for i, n in enumerate(gn) if n.endswith(("Arm", "ForeArm", "Hand"))]].sum(1)
    KD4 = KDTree(len(BPv))
    for i_, q_ in enumerate(BPv):
        KD4.insert(Vector(q_), i_)
    KD4.balance()

    def resid(c):
        """Signed distances inside each outline edge (> 0 = inside the vest)."""
        x_, y_, z_ = c
        front = y_ < ycf(z_)
        r_ = {"hem": z_ - hem_z(x_, y_, z_), "neck": Z_NECK - z_}
        r_["v"] = (abs(x_) - v_w(z_)) if (front and z_ > V_["z_vbot"] - 0.005) else 9.0
        sgc = 1 if x_ > 0 else -1
        # the arm itself: its skin weight (heat weights are smooth) interpolated from the 4 nearest body
        # verts; the 0.5 iso line is the arm / torso border
        nn = KD4.find_n(Vector(c), 4)
        wv = np.array([1.0 / max(d_, 1e-5) for _, _, d_ in nn])
        aw = float(np.dot(wv, [ARMW[i_] for _, i_, _ in nn]) / wv.sum())
        r_["arm"] = min(float(np.linalg.norm(np.asarray(c) - ARMC[sgc]) - ARMR), (V_.get("arm_iso", 0.5) - aw) * 0.08)
        return r_

    def inside_amount(c):
        return min(resid(c).values())

    PLANES = [((0, 0, Z_NECK), (0, 0, 1), -1, 0)]
    R.setdefault("seat_bump", 0.0)
else:
    PLANES = [((0, Y0, Z_TOP), (0, -RISE, 1), -1, 0), ((0, 0, Z_BOT), (0, 0, 1), 1, 0)]
if KIND == "boot":
    # the leg below the boot top (over the breeches' knee band) and the whole foot; the boot's shape comes
    # from the extracted boots (ease measured to their outer surface, as the breeches)
    PLANES = [((0, 0, Z_TOP), (0, 0, 1), -1, 0)]
if KIND == "glove":
    # the hand from the wrist plane (tucked under the shirt cuff by "wrist_offset" < 0) to the fingertips
    PLANES = [(tuple(WRIST[sg][0]), tuple(WRIST[sg][1]), 1, sg) for _, sg in SIDES]
if KIND == "coat":
    # outline: back neck plane + wrist planes (sleeves end above the shirt cuff); hem (hip length,
    # longer tails at the back) and the open front with notched lapels as an exact field cut
    V_ = R["outline"]
    core_ = BPv[(np.abs(BPv[:, 0]) < 0.15) & ~np.array([("Arm" in d) or ("Hand" in d) or d == "Tail" for d in dom])]
    ZS_ = np.arange(0.5, 1.5, 0.01)
    YC_ = np.array([(lambda nb: (nb[:, 1].min() + nb[:, 1].max()) / 2 if len(nb) else 0.0)(core_[np.abs(core_[:, 2] - zz) < 0.012])
                    for zz in ZS_])

    def ycf(z):
        return np.interp(z, ZS_, YC_)

    def hem_z(x, y, z):
        fr = np.clip((ycf(z) - y) / 0.06 + 0.5, 0, 1)
        return fr * V_["z_front"] + (1 - fr) * V_["z_back"]

    def v_w(z):
        """Half width of the open front: cutaway below the button, lapel above, notch, collar."""
        zs, ws = zip(*V_["open"])
        return float(np.interp(z, zs, ws))

    def tail_w(z):
        """Half width of the gap between the tails: 0 at the vent top, w_bot at the hem."""
        TL = V_["tails"]
        t = np.clip((TL["z_top"] - z) / (TL["z_top"] - V_["z_back"]), 0, 1)
        return TL["w_bot"] * t ** TL.get("pow", 1.3)

    def resid(c):
        x_, y_, z_ = c
        front = (y_ < min(ycf(z_), V_.get("front_y", -0.02))) and abs(x_) < 0.2   # (the seat cap sags toward the centre)
        r_ = {"hem": z_ - hem_z(x_, y_, z_), "neck": Z_NECK - z_}
        r_["v"] = (abs(x_) - v_w(z_)) if front else 9.0
        TL = V_.get("tails")
        if TL and not front and y_ > ycf(z_) and z_ < TL["z_top"]:     # swallowtails: an open vent at the back
            r_["vent"] = abs(x_) - tail_w(z_)
        if abs(x_) > 0.2:                          # sleeves: only the wrist planes cut them
            r_["hem"] = 9.0
        return r_

    def inside_amount(c):
        return min(resid(c).values())

    PLANES = [((0, 0, Z_NECK + 0.05), (0, 0, 1), -1, 0)] + \
             [(tuple(WRIST[sg][0]), tuple(WRIST[sg][1]), -1, sg) for _, sg in SIDES]


def plane_ok(c, pl):
    co, no, keep, sg = pl
    if sg == 2 and abs(c[0]) > 0.22:               # hem plane: torso only (the sleeves hang below it)
        return True
    if sg in (1, -1) and c[0] * sg < 0.25:         # wrist planes only cut their own forearm
        return True
    return float(np.dot(np.asarray(c) - co, no)) * keep >= -1e-4 * np.linalg.norm(no)


def on_plane(c, pl, tol=0.003):
    co, no, keep, sg = pl
    if (sg == 2 and abs(c[0]) > 0.22) or (sg in (1, -1) and c[0] * sg < 0.25):
        return False
    no = np.asarray(no, float)
    return abs(float(np.dot(np.asarray(c) - co, no / np.linalg.norm(no)))) < tol

# ---- 1. region of the body surface
reg = body.copy()
reg.data = body.data.copy()
reg.name = reg.data.name = f"{PIECE}_region"
bpy.context.scene.collection.objects.link(reg)
# (vertex groups kept: the garment carries the body's own skin weights, interpolated by the subdivision)
bm = bmesh.new()
bm.from_mesh(reg.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=2e-4)   # glTF import splits the body at UV seams (+ centre seam)
# tail off, its hole capped on the closed body (it touches the waist line, so cap before cutting)
kd0 = KDTree(len(BPv))
for i, p in enumerate(BPv):
    kd0.insert(Vector(p), i)
kd0.balance()
bm.faces.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[f for f in bm.faces if is_tail[kd0.find(f.calc_center_median())[1]]], context="FACES")
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
capL = bm.faces.layers.int.new("cap")
holes = []
for e in [e for e in bm.edges if e.is_boundary]:
    if any(e in h for h in holes):
        continue
    st, h = [e], set([e])
    while st:
        x = st.pop()
        for v in x.verts:
            for y in v.link_edges:
                if y.is_boundary and y not in h:
                    h.add(y)
                    st.append(y)
    holes.append(h)
tail_hole = min(holes, key=lambda h: min((v.co - Vector(TAIL_ROOT)).length for e in h for v in e.verts))
CAP_R = max((v.co - Vector(TAIL_ROOT)).length for e in tail_hole for v in e.verts)   # tail-hole radius
log("tail hole radius mm", round(CAP_R * 1000))
for f in bmesh.ops.holes_fill(bm, edges=list(tail_hole), sides=0)["faces"]:
    f[capL] = 1
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if f[capL]])
if R.get("seat_fit", KIND == "breeches"):     # (the shirt only covers the hole; it stays inside the breeches)
    # even cap mesh: subdivide, relax its inner points in the hole's plane, lift them onto a quadric fitted
    # to the ring of body around the hole (the seat continues smoothly instead of a flat faceted patch)
    for _ in range(2):                               # (subdivided faces keep the cap flag; rim edges stay)
        ce = list({e for f in bm.faces if f[capL] for e in f.edges if all(lf[capL] for lf in e.link_faces)})
        bmesh.ops.subdivide_edges(bm, edges=ce, cuts=2, use_grid_fill=False)
        bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3 and f[capL]])
    rim = {v for v in bm.verts if any(f[capL] for f in v.link_faces) and any(not f[capL] for f in v.link_faces)}
    RP = np.array([v.co[:] for v in rim])
    o_c = RP.mean(0)
    _, _, vt = np.linalg.svd(RP - o_c)
    n_c = vt[2] * (1 if vt[2][1] > 0 else -1)          # plane normal, pointing back (+Y)
    u_c = np.cross(n_c, [0, 0, 1.0])
    u_c /= np.linalg.norm(u_c)
    v_c = np.cross(n_c, u_c)
    capvs = [v for v in {v for f in bm.faces if f[capL] for v in f.verts} if v not in rim]
    ringv = [v for v in bm.verts if v not in rim and not any(f[capL] for f in v.link_faces)
             and min((v.co - Vector(q)).length for q in RP[::4]) < 0.08]
    Q = np.array([v.co[:] for v in ringv]) - o_c
    Afit = lambda a, b: np.stack([np.ones_like(a), a, b, a * a, a * b, b * b], 1)  # noqa: E731
    coef_c = np.linalg.lstsq(Afit(Q @ u_c, Q @ v_c), Q @ n_c, rcond=None)[0]
    uv = {v: np.array([(np.array(v.co) - o_c) @ u_c, (np.array(v.co) - o_c) @ v_c]) for v in set(capvs) | rim}
    for _ in range(150):
        for v in capvs:
            nb = [e.other_vert(v) for e in v.link_edges]
            uv[v] = 0.5 * uv[v] + 0.5 * np.mean([uv[w] for w in nb], 0)
    def on_quadric(a_, b_):
        return o_c + a_ * u_c + b_ * v_c + float(Afit(np.array([a_]), np.array([b_])) @ coef_c) * n_c


    for v in capvs:
        v.co = Vector(on_quadric(*uv[v]))
    # rim + a 5 cm band of body around it blend onto the same quadric (the rim follows the jagged feather
    # line; leaving it put crumples the join), then a light 3D relax across the whole patch
    band = []
    for v in bm.verts:
        if v in rim or v in set(capvs):
            continue
        d_ = min((v.co - Vector(q)).length for q in RP[::2])
        if d_ < 0.05 and not any(f[capL] for f in v.link_faces):
            band.append((v, 1 - d_ / 0.05))
    def outward_only(v, tgt, w_):
        """Move toward tgt, but never into the body (only the part along the outward normal)."""
        o = np.array(v.co)
        n_ = np.array(v.normal)
        d_ = (tgt - o) * w_
        v.co = Vector(o + max(0.0, float(d_ @ n_)) * n_)


    for v in rim:
        q_ = np.array(v.co) - o_c
        outward_only(v, on_quadric(q_ @ u_c, q_ @ v_c), 1.0)
    for v, w_ in band:
        q_ = np.array(v.co) - o_c
        outward_only(v, on_quadric(q_ @ u_c, q_ @ v_c), w_ ** 2)
    patch = set(capvs) | rim | {v for v, _ in band}
    for _ in range(R.get("cap_relax", 30)):
        newp = {v: sum((e.other_vert(v).co for e in v.link_edges), Vector()) / len(v.link_edges) for v in patch if v.link_edges}
        for v, c in newp.items():
            v.co = v.co.lerp(c, 0.5)
    log("tail cap", len(capvs), "inner verts")

if R.get("pre_cuts", 0):
    # dense surface before cutting: an outline that is not a plane follows triangle edges, so the
    # triangles must be small for the snapped edge to be clean
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=R["pre_cuts"], use_grid_fill=True)
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
for co_, no_, _, _ in PLANES:
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co_, plane_no=no_)
kd = KDTree(len(BPv))
for i, p in enumerate(BPv):
    kd.insert(Vector(p), i)
kd.balance()
kill = []
for f in bm.faces:
    c = f.calc_center_median()
    i = kd.find(c)[1]
    drop = False if KIND == "shirt" else is_arm[i]   # (shirt: the wrist planes cut the hands off)
    if KIND in ("vest", "coat"):
        drop = ("Hand" in dom[i]) or inside_amount(np.array(c)) < -0.03   # (exact cut below)
    if KIND == "shirt" and R.get("hem_points"):
        drop = inside_amount(np.array(c)) < -0.03
    if KIND == "glove":
        drop = not ("Hand" in dom[i] or "ForeArm" in dom[i])
    if not all(plane_ok(c, pl) for pl in PLANES) or ((not f[capL] or KIND == "vest") and drop):   # (tail already off)
        kill.append(f)
if "--debug" in argv:
    for zz in np.arange(0.70, 0.86, 0.02):
        vs_ = [v for v in bm.verts if abs(v.co.z - zz) < 0.01 and abs(v.co.x) < 0.08 and v.co.y > 0]
        ks_ = [f for f in kill if abs(f.calc_center_median().z - zz) < 0.01 and abs(f.calc_center_median().x) < 0.08 and f.calc_center_median().y > 0]
        print("DBG pre z", round(zz, 2), len(vs_), "killed faces", len(ks_))
bmesh.ops.delete(bm, geom=kill, context="FACES")
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
# keep the largest connected part (stray bits of wrists / feathers)
bm.verts.ensure_lookup_table()
seen, parts = set(), []
for v in bm.verts:
    if v.index in seen:
        continue
    st, comp = [v], []
    seen.add(v.index)
    while st:
        x = st.pop()
        comp.append(x)
        for e in x.link_edges:
            y = e.other_vert(x)
            if y.index not in seen:
                seen.add(y.index)
                st.append(y)
    parts.append(comp)
parts.sort(key=len)
log("region parts", [len(p_) for p_ in parts[-4:]])
if KIND == "boot":
    bmesh.ops.delete(bm, geom=[v for p in parts[:-2] for v in p], context="VERTS")   # (one per leg)
elif KIND == "glove":     # each hand (and its separate finger shells) -- drop only real specks
    bmesh.ops.delete(bm, geom=[v for p in parts[:-2] for v in p], context="VERTS")   # (claw shells off)
    # stray flaps (thumb claw sheet) stick out of the mitten: drop verts far from the hand axis
    for s_, sg in SIDES:
        h0, h1 = bone[f"{s_}Hand"]
        dq = h1 - h0
        vs_ = [v for v in bm.verts if v.co.x * sg > 0.2]
        if not vs_:
            continue
        Q = np.array([v.co[:] for v in vs_])
        u_ = np.clip(((Q - h0) @ dq) / (dq @ dq), 0, 1)
        dd_ = np.linalg.norm(Q - (h0 + u_[:, None] * dq), axis=1)
        lim = np.percentile(dd_, 50) * R.get("flap_r", 1.7)
        bmesh.ops.delete(bm, geom=[v for v, d_ in zip(vs_, dd_) if d_ > lim], context="VERTS")
    seen2, parts2 = set(), []
    for v in bm.verts:
        if v in seen2:
            continue
        st, comp = [v], []
        seen2.add(v)
        while st:
            x_ = st.pop()
            comp.append(x_)
            for e in x_.link_edges:
                y_ = e.other_vert(x_)
                if y_ not in seen2:
                    seen2.add(y_)
                    st.append(y_)
        parts2.append(comp)
    parts2.sort(key=len)
    bmesh.ops.delete(bm, geom=[v for p in parts2[:-2] for v in p], context="VERTS")
else:
    bmesh.ops.delete(bm, geom=[v for p in parts[:-1] for v in p], context="VERTS")
if KIND in ("vest", "coat") or (KIND == "shirt" and R.get("hem_points")):
    # exact outline: split every edge where the inside-distance field changes sign, join the split
    # points across each face, drop the outside -- the edge lies on the outline curves (no sawtooth)
    sv = {v: inside_amount(np.array(v.co)) for v in bm.verts}
    newv = set()
    for e in [e for e in bm.edges if sv[e.verts[0]] * sv[e.verts[1]] < 0]:
        a_, b_ = e.verts
        fr = sv[a_] / (sv[a_] - sv[b_])
        ne, nv = bmesh.utils.edge_split(e, a_, fr)
        sv[nv] = 0.0
        newv.add(nv)
    for f in list(bm.faces):
        cut = [v for v in f.verts if v in newv]
        if len(cut) == 2 and not any(cut[1] in [e.other_vert(cut[0]) for e in cut[0].link_edges] for _ in [0]):
            bmesh.ops.connect_verts(bm, verts=cut)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if np.mean([sv.get(v, 0.0) for v in f.verts]) < 0
                                and all(sv.get(v, 0.0) <= 1e-9 for v in f.verts)], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3])
    # slivers next to the cut: dissolve degenerate edges
    bmesh.ops.dissolve_degenerate(bm, dist=0.0015, edges=bm.edges[:])
    log("vest exact outline split", len(newv), "edges")
    if "--debug" in argv:
        for zz in np.arange(0.70, 0.86, 0.02):
            vs_ = [v for v in bm.verts if abs(v.co.z - zz) < 0.01 and abs(v.co.x) < 0.08 and v.co.y > 0]
            print("DBG cut z", round(zz, 2), len(vs_))
    bverts = [v for v in bm.verts if any(e.is_boundary for e in v.link_edges)]

    kind_of = {}
    for v in bverts:
        r0 = resid(np.array(v.co))
        kind_of[v] = min(r0, key=lambda kk: abs(r0[kk]))
        if abs(r0[kind_of[v]]) > 0.03:           # an edge made by a plane (neck / wrists): not an outline
            kind_of[v] = "plane"

    def snap(v):
        c = np.array(v.co)
        k_ = kind_of[v]
        if k_ == "plane":
            return
        if k_ == "hem":
            c[2] = hem_z(c[0], c[1], c[2])
        elif k_ == "v":
            c[0] = np.sign(c[0] or 1) * v_w(c[2])
        elif k_ == "vent":
            c[0] = np.sign(c[0] or 1) * tail_w(c[2])
        elif k_ == "arm":
            ac = ARMC[1 if c[0] > 0 else -1]
            c = ac + (c - ac) / max(np.linalg.norm(c - ac), 1e-6) * ARMR
        else:
            c[2] = Z_NECK
        v.co = Vector(c)
    for _ in range(R.get("edge_iter", 10)):
        for v in bverts:
            snap(v)
        newc = {}
        for v in bverts:
            nb = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
            if len(nb) == 2 and kind_of[v] != "plane":
                newc[v] = v.co * 0.5 + (nb[0].co + nb[1].co) * 0.25
        for v, c in newc.items():
            v.co = c
    for v in (bverts if R.get("edge_iter", 10) else []):
        snap(v)
    # snapped edge verts can cross their inner neighbours (folded sawtooth triangles): relax the rings
    # next to the edge with the edge pinned
    ring, frontier = set(), {v for v in bverts if kind_of[v] != "plane"}
    for _ in range(R.get("edge_rings", 4)):
        frontier = {e.other_vert(v) for v in frontier for e in v.link_edges} - set(bverts) - ring
        ring |= frontier
    for _ in range(R.get("edge_relax", 25)):
        newc = {v: sum((e.other_vert(v).co for e in v.link_edges), Vector()) / len(v.link_edges) for v in ring}
        for v, c in newc.items():
            v.co = v.co.lerp(c, 0.6)
    log("vest edge verts snapped", len(bverts), "relaxed", len(ring))
# boundary loops: waist (z_top), two knee loops (z_bot) stay open; others (tail hole) are capped
bnd = [e for e in bm.edges if e.is_boundary]
loops, used = [], set()
for e in bnd:
    if e.index in used:
        continue
    st, lp = [e], []
    used.add(e.index)
    while st:
        x = st.pop()
        lp.append(x)
        for v in x.verts:
            for y in v.link_edges:
                if y.is_boundary and y.index not in used:
                    used.add(y.index)
                    st.append(y)
    loops.append(lp)
caps = []
for lp in loops:
    lvs = [np.array(v.co) for e in lp for v in e.verts]
    if KIND not in ("vest", "coat") and not R.get("hem_points") and not any(all(on_plane(c, pl) for c in lvs) for pl in PLANES):      # not a cut opening -> cap it
        res = bmesh.ops.holes_fill(bm, edges=lp, sides=0)
        if not res["faces"]:                          # tiny holes: fan from the centre
            vs = list({v for e in lp for v in e.verts})
            c = bm.verts.new(sum((v.co for v in vs), Vector()) / len(vs))
            for e in lp:
                try:
                    res["faces"].append(bm.faces.new([e.verts[0], e.verts[1], c]))
                except ValueError:
                    pass
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        caps += res["faces"]
log("region loops", len(loops), "capped", len(caps))
if "--debug" in argv:
    for lp in loops:
        vs = {v for e in lp for v in e.verts}
        c = [v for v in vs if abs(v.co.x) < 0.03]
        print("LOOP", len(vs), sorted([(round(v.co.x, 4), round(v.co.y, 3), round(v.co.z - float(ztop(v.co.y)), 4)) for v in c])[:12])
bmesh.ops.triangulate(bm, faces=caps)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bm.faces.ensure_lookup_table()
kd_n = np.array([v.normal[:] for v in body.data.vertices])
agree = sum(float(np.dot(f.normal, kd_n[kd.find(f.calc_center_median())[1]])) for f in bm.faces)
if agree < 0:                                       # whole surface inside-out
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
bm.to_mesh(reg.data)
bm.free()
reg.data.update()

RV = np.array([v.co[:] for v in reg.data.vertices])
bmc = bmesh.new()
bmc.from_mesh(reg.data)
BND = np.array([v.co[:] for v in bmc.verts if any(e.is_boundary for e in v.link_edges)])
bmc.free()
kdb = KDTree(len(BND))
for i, q in enumerate(BND):
    kdb.insert(Vector(q), i)
kdb.balance()
COVER_MARGIN = R.get("cover_margin", 0.012)
def plane_dist(c, pl):
    co, no, keep, sg = pl
    if (sg == 2 and abs(c[0]) > 0.22) or (sg in (1, -1) and c[0] * sg < 0.25):
        return 9.0
    no = np.asarray(no, float)
    return float(np.dot(np.asarray(c) - co, no / np.linalg.norm(no))) * keep


excl = is_arm if KIND != "shirt" else np.zeros(len(BPv), bool)
if KIND == "vest":
    COVERS_POS = np.array([q for q, d_ in zip(BPv, dom) if "Arm" not in d_ and "Hand" not in d_
                           and inside_amount(q) > COVER_MARGIN])
elif KIND == "glove":
    COVERS_POS = np.array([q for q, d_ in zip(BPv, dom) if "Hand" in d_ and
                           all(plane_dist(q, pl) > COVER_MARGIN for pl in PLANES if (q[0] * pl[3]) >= 0.25)])
elif KIND == "coat":
    COVERS_POS = np.array([q for q, d_ in zip(BPv, dom) if "Hand" not in d_ and inside_amount(q) > COVER_MARGIN
                           and all(plane_dist(q, pl) > COVER_MARGIN for pl in PLANES)])
else:
    COVERS_POS = np.array([q for q, ex in zip(BPv, excl)
                           if not ex and all(plane_dist(q, pl) > COVER_MARGIN for pl in PLANES)])
# vertices made by the cuts / caps have no skin weights: take the nearest body vertex's
for v in reg.data.vertices:
    if sum(g.weight for g in v.groups) < 1e-6:
        j = kd.find(v.co)[1]
        for gi in np.flatnonzero(Wb[j] > 1e-4):
            vg = reg.vertex_groups.get(gn[gi]) or reg.vertex_groups.new(name=gn[gi])
            vg.add([v.index], float(Wb[j, gi]), "REPLACE")
if KIND == "boot":
    # boot = one smooth solid round leg + webbed foot: cap the top, voxel-remesh coarse (toes and claws
    # merge), relax, open the top again; flat sole; skin weights from the nearest body vertex
    only_select(reg)
    bmq = bmesh.new()
    bmq.from_mesh(reg.data)
    bnd_e = [e for e in bmq.edges if e.is_boundary]
    bmesh.ops.holes_fill(bmq, edges=bnd_e, sides=0)
    bmq.to_mesh(reg.data)
    bmq.free()
    reg.data.remesh_voxel_size = R.get("boot_voxel", 0.012)
    bpy.ops.object.voxel_remesh()
    me_ = reg.data
    Pb = np.array([v.co[:] for v in me_.vertices])
    ed_ = np.array([e.vertices[:] for e in me_.edges])
    z0 = Pb[:, 2].min()
    for _ in range(R.get("boot_relax", 25)):
        Pb = smooth_field(Pb, ed_, 1)
        Pq = smooth_field(Pb, ed_, 1)
        Pb = Pb - 0.53 * (Pq - Pb)
        Pb[:, 2] = np.maximum(Pb[:, 2], z0)
    # the relax shrank it into the leg: push every vertex out to the body surface (smoothed displacement)
    for _ in range(4):
        disp_ = np.zeros_like(Pb)
        for i_, q_ in enumerate(Pb):
            loc, nrm_, _, _ = body_noarm.find_nearest(Vector(q_))
            if loc is None:
                continue
            s_ = (Vector(q_) - loc).dot(nrm_)
            if s_ < 0.002 and q_[2] > R.get("push_above", 0.15):   # (feet are hidden under the boot: no lumps)
                disp_[i_] = np.array(nrm_) * (0.002 - s_)
        disp_ = smooth_field(disp_, ed_, 3)
        Pb = Pb + disp_ * 1.2
        Pb[:, 2] = np.maximum(Pb[:, 2], z0)
    me_.vertices.foreach_set("co", Pb.ravel())
    me_.update()
    bmq = bmesh.new()
    bmq.from_mesh(me_)
    bmesh.ops.bisect_plane(bmq, geom=bmq.verts[:] + bmq.edges[:] + bmq.faces[:], plane_co=(0, 0, Z_TOP - 0.006),
                           plane_no=(0, 0, 1), clear_outer=True)
    bmesh.ops.recalc_face_normals(bmq, faces=bmq.faces[:])
    bmesh.ops.delete(bmq, geom=[f for f in bmq.faces if f.calc_center_median().z > Z_TOP], context="FACES")
    comps_, seen_ = [], set()
    for v in bmq.verts:
        if v in seen_:
            continue
        st, c_ = [v], []
        seen_.add(v)
        while st:
            x_ = st.pop()
            c_.append(x_)
            for e in x_.link_edges:
                y_ = e.other_vert(x_)
                if y_ not in seen_:
                    seen_.add(y_)
                    st.append(y_)
        comps_.append(c_)
    comps_.sort(key=len)
    bmesh.ops.delete(bmq, geom=[v for c_ in comps_[:-2] for v in c_], context="VERTS")   # (claw specks)
    bmesh.ops.delete(bmq, geom=[v for v in bmq.verts if not v.link_faces], context="VERTS")
    bmq.to_mesh(me_)
    bmq.free()
    for g in list(reg.vertex_groups):
        reg.vertex_groups.remove(g)
    for v in me_.vertices:
        j = kd.find(v.co)[1]
        for gi in np.flatnonzero(Wb[j] > 1e-4):
            vg = reg.vertex_groups.get(gn[gi]) or reg.vertex_groups.new(name=gn[gi])
            vg.add([v.index], float(Wb[j, gi]), "REPLACE")
    log("boot solid", len(me_.vertices), "verts")
# subdivide once (game mesh precursor), relax the cap
only_select(reg)
if R.get("region_sub", 1):
    m = reg.modifiers.new("sub", "SUBSURF")
    m.levels = R.get("region_sub", 1)
    m.boundary_smooth = "PRESERVE_CORNERS"
    bpy.ops.object.modifier_apply(modifier=m.name)
me = reg.data
P, N = mesh_vn(me)
ed = edges_of(me)
boundary = np.zeros(len(P), bool)
bm = bmesh.new()
bm.from_mesh(me)
for e in bm.edges:
    if e.is_boundary:
        for v in e.verts:
            boundary[v.index] = True
bm.free()
if R.get("plain_smooth", 0):          # (gloves: the mitten's segment ridges must not print through)
    P = smooth_field(P, ed, R["plain_smooth"], pin=boundary)
if KIND == "boot" and R.get("foot_smooth", 0):
    # the webbed toes and claws merge into one boot shape: heavy smoothing on the foot (shaft pinned,
    # soft blend over the ankle), sole kept on the ground; the ease then reaches out to the boot surface
    zf = P[:, 2]
    w_ = np.clip((R.get("foot_top", 0.16) - zf) / 0.06, 0, 1)
    z0 = zf.min()
    Pf = P.copy()
    for _ in range(R["foot_smooth"]):
        Pf = smooth_field(Pf, ed, 1, pin=w_ <= 0)
        Pf[:, 2] = np.maximum(Pf[:, 2], z0)
    P = P * (1 - w_[:, None]) + Pf * w_[:, None]
    log("boot foot smoothed", int((w_ > 0).sum()), "verts")
for _ in range(R.get("base_smooth", 10)):
    P = smooth_field(P, ed, 1, pin=boundary)
    Pb = smooth_field(P, ed, 1, pin=boundary)
    P = P - 0.53 * (Pb - P)                          # Taubin inflate step
dtail = np.linalg.norm(P - TAIL_ROOT, axis=1)
# the tail (a fan of feathers over the upper seat) left a big flat cap: its inner vertices take their
# height from a quadric fitted to the ring of surface around it, blended in from the rim
capw = np.zeros(len(P))
if False and "cap" in me.attributes:      # (superseded: the cap is built on the fitted quadric above)
    fc_ = np.zeros(len(me.polygons), np.int32)
    me.attributes["cap"].data.foreach_get("value", fc_)
    capv, nonc = set(), set()
    for f_, c_ in zip(me.polygons, fc_):
        (capv if c_ else nonc).update(f_.vertices)
    inner = np.array(sorted(capv - nonc))
    rimv = np.array(sorted(capv & nonc))
    if len(inner) and len(rimv):
        kdr = KDTree(len(rimv))
        for i_, q_ in enumerate(P[rimv]):
            kdr.insert(Vector(q_), i_)
        kdr.balance()
        drim = np.array([kdr.find(Vector(q_))[2] for q_ in P])
        ring = np.array([i_ in nonc for i_ in range(len(P))]) & (drim < 0.08)
        nrm = N[ring].mean(0)
        nrm /= np.linalg.norm(nrm)
        u_ = np.cross(nrm, [0, 0, 1.0])
        u_ /= np.linalg.norm(u_)
        v_ = np.cross(nrm, u_)
        o_ = P[rimv].mean(0)
        dq = P - o_
        uq, vq, hq = dq @ u_, dq @ v_, dq @ nrm
        Afit = lambda a, b: np.stack([np.ones_like(a), a, b, a * a, a * b, b * b], 1)  # noqa: E731
        coef = np.linalg.lstsq(Afit(uq[ring], vq[ring]), hq[ring], rcond=None)[0]
        hfit = Afit(uq, vq) @ coef
        w_ = np.zeros(len(P))
        w_[inner] = np.clip(drim[inner] / 0.05, 0, 1) ** 2 * (3 - 2 * np.clip(drim[inner] / 0.05, 0, 1))
        P = P + (w_ * (hfit - hq))[:, None] * nrm
        capw = w_
        pin = np.ones(len(P), bool)
        pin[inner] = False
        P = smooth_field(P, ed, 6, pin=pin)
        log("seat cap", len(inner), "verts, rim", len(rimv))
dtail = np.linalg.norm(P - TAIL_ROOT, axis=1)
me.vertices.foreach_set("co", P.ravel())
me.update()
P, N = mesh_vn(me)
log("region", len(me.vertices), "verts")

# ---- 2. ease
vgn = [g.name for g in reg.vertex_groups]
WR = np.zeros((len(P), len(vgn)))
for v in me.vertices:
    for g in v.groups:
        WR[v.index, g.group] = g.weight
WR /= np.maximum(WR.sum(1, keepdims=True), 1e-9)
armw = WR[:, [i for i, n in enumerate(vgn) if ("Arm" in n)]].sum(1) if any("Arm" in n for n in vgn) else np.zeros(len(P))
if KIND in ("shirt", "coat", "glove"):
    dwr = np.full(len(P), 9.0)                         # distance up the forearm from the wrist cut
    for _, sg in SIDES:
        co, dd = WRIST[sg]
        on = P[:, 0] * sg > 0.2
        dwr = np.where(on, np.minimum(dwr, -((P - co) @ dd)), dwr)
    dneck = Z_NECK - P[:, 2]
    dhem = P[:, 2] - ztop(P[:, 1]) + (Z_TOP - Z_BOT)   # height above the (tilted) hem
REACH = R.get("ease_reach", 0.08)
ease = np.full(len(P), np.nan)
piece_f = D / "pieces" / f"{R.get('guide', PIECE)}.glb"
pb = piece = None
if KIND not in ("shirt", "vest", "coat", "glove", "boot") and piece_f.exists():   # (outfits drawn per garment
    piece = next(o for o in load(piece_f) if o.type == "MESH")                     #  have no extracted piece)
    only_select(piece)
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    pb = BVHTree.FromObject(piece, bpy.context.evaluated_depsgraph_get())
for i, (p, n) in enumerate(zip(P, N)):
    if pb is None:
        break
    hit = pb.ray_cast(Vector(p + n * REACH), Vector(-n), REACH)     # outermost surface of the piece
    if hit[0] is not None:
        ease[i] = REACH - hit[3]
if piece is not None:
    bpy.data.objects.remove(piece)
if R.get("ease_npz") and KIND not in ("shirt", "vest", "coat", "glove", "boot"):
    # measured ease (key_measure.py on the dressed key mannequin): per base-body vertex, NaN where not measured;
    # each region vertex takes its nearest body vertex's value
    EZ = np.load(ROOT / R["ease_npz"])["ease"]
    # (the measured field lives on base_goose.blend's game mesh; its vertex positions are in the worn set's
    #  _regions.npz -- the rigged GLB splits vertices at UV seams, so look up by position)
    EZco = np.load(ROOT / "out" / "outfit_male_victorian" / "worn" / "_regions.npz")["co"]
    kde = KDTree(len(EZco))
    for i, v in enumerate(EZco):
        kde.insert(v, i)
    kde.balance()
    for i, p in enumerate(P):
        _, j, d = kde.find(p)
        if d < 0.03 and not np.isnan(EZ[j]):
            ease[i] = EZ[j]
wb, kb = R.get("waistband", 0.04), R.get("kneeband", 0.035)
if KIND == "shirt":
    # torso close, sleeves fuller and bloused above a snug cuff, snug at the neck and the tucked hem
    E = R.get("ease", {})
    ease = E.get("torso", 0.007) + (E.get("sleeve", 0.011) - E.get("torso", 0.007)) * np.clip(armw, 0, 1)
    ease += E.get("blouse", 0.006) * np.exp(-((dwr - 0.085) / 0.045) ** 2) * (dwr < 1)
    if E.get("puff"):           # leg-of-mutton: a puff over the upper arm, fitted from the elbow down
        for s_, sg in SIDES:
            a0_, a1_ = bone[f"{s_}Arm"][0], bone[f"{s_}ForeArm"][0]
            dq = a1_ - a0_
            u_ = ((P - a0_) @ dq) / (dq @ dq)
            on_ = (P[:, 0] * sg > 0.05) & (armw > E.get("puff_armw", 0.3))
            ease += np.where(on_, E["puff"] * np.exp(-((u_ - E.get("puff_at", 0.3)) / E.get("puff_w", 0.28)) ** 2), 0.0)
    cuff = R.get("cuff", 0.045)
    ease = np.where(dwr < cuff + 0.01, np.minimum(ease, E.get("cuff", 0.005)) + 0.0 * dwr, ease)
    ease = ease * np.clip(dneck / 0.04, 0, 1) + E.get("neck", 0.003) * (1 - np.clip(dneck / 0.04, 0, 1))
    th = np.clip(dhem / R.get("hem_zone", 0.06), 0, 1)
    ease = ease * th + E.get("hem", 0.004) * (1 - th)
    ease = smooth_field(ease, ed, 6)
else:
    ok = ~np.isnan(ease)
    log("ease measured", round(float(ok.mean()), 3), "median mm", round(float(np.nanmedian(ease)) * 1000, 1))
    e_lo, e_hi = R.get("ease_min", 0.008), R.get("ease_max", 0.05)
    ease = np.clip(np.where(ok, ease, np.nanmedian(ease) if ok.any() else e_lo), e_lo, e_hi)
    for _ in range(4):                                  # fill unmeasured from measured neighbours
        sm = smooth_field(ease, ed, 10)
        ease = np.where(ok, ease, sm)
    ease = smooth_field(ease, ed, R.get("ease_smooth", 60))
    # tight bands: waistband and knee band
    z = P[:, 2]
    t_w = np.clip((ztop(P[:, 1]) - z) / (wb * 2.5), 0, 1) if KIND == "breeches" else np.ones(len(z))
    t_k = np.clip((z - Z_BOT) / (kb * 3.0), 0, 1) if KIND == "breeches" else np.ones(len(z))
    band = np.minimum(t_w, t_k) ** 1.5
    ease = R.get("band_ease", 0.007) + (ease - R.get("band_ease", 0.007)) * band
# seat bump over the capped tail
ease += R.get("seat_bump", 0.008) * capw
if KIND == "boot":
    ease = np.full(len(P), R.get("ease", {}).get("boot", 0.005))
    # clear the breeches' knee band at the boot top
    for nm in R.get("over", []):
        uo = next(o for o in load(OUT / f"{nm}.glb") if o.type == "MESH")
        ub = BVHTree.FromObject(uo, bpy.context.evaluated_depsgraph_get())
        under = np.zeros(len(P))
        for i, (p_, n_) in enumerate(zip(P, N)):
            hit = ub.ray_cast(Vector(p_ - n_ * 0.01), Vector(n_), 0.08)
            if hit[0] is not None:
                under[i] = max(under[i], hit[3] - 0.01)
        bpy.data.objects.remove(uo)
        ease = np.maximum(ease, np.minimum(under, 0.05) + R.get("ease", {}).get("clear", 0.004))
    need_b = ease.copy()
    ease = smooth_field(ease, ed, R.get("boot_smooth", 30))
    ease = np.maximum(np.maximum(ease, need_b), 0.003)     # (the boot top stays outside the breeches)
# crotch: stay under 40 % of the gap to the other surface along the normal


def gap(p, n):
    """Free distance along the normal to the next body surface (the other thigh); the region sits a
    few mm inside its own body surface (subdivision shrink), so that first exit is skipped."""
    o = Vector(p + n * 0.002)
    travelled = 0.002
    for _ in range(3):
        hit = body_noarm.ray_cast(o, Vector(n), 0.25)
        if hit[0] is None:
            return 9.0
        if travelled + hit[3] > 0.012:
            return travelled + hit[3]
        o = hit[0] + Vector(n) * 0.002
        travelled += hit[3] + 0.002
    return 9.0


if KIND == "shirt":     # the arms are part of the garment: gaps are to any body surface but the hands
    body_noarm = BVHTree.FromPolygons([tuple(x) for x in BPv],
                                      [list(p.vertices) for p in body.data.polygons if not is_hand[list(p.vertices)].any()])
G = np.array([gap(p, n) for p, n in zip(P, N)])
if KIND != "shirt":
    body_arms = BVHTree.FromPolygons([tuple(x) for x in BPv],
                                     [list(p.vertices) for p in body.data.polygons if is_arm[list(p.vertices)].all()])
    GA = np.array([(lambda h: h[3] if h[0] is not None else 9.0)(body_arms.ray_cast(Vector(p + n * 0.002), Vector(n), 0.25))
                   for p, n in zip(P, N)])
    G = np.minimum(G, GA / 0.4 * R.get("hand_share", 0.55))
ease = np.minimum(ease, 0.4 * G)
ease = smooth_field(ease, ed, 8)
ease = np.minimum(ease, 0.42 * G)                     # re-limit after smoothing
ease = np.maximum(ease, 0.004)
if R.get("ease_post_smooth"):          # (dense meshes: the gap limit leaves a noisy field -> crumples)
    ease = np.minimum(smooth_field(ease, ed, R["ease_post_smooth"]), 0.42 * G)
    ease = np.maximum(smooth_field(ease, ed, 4), 0.004)
if KIND == "glove":
    E = R.get("ease", {})
    ease = np.full(len(P), E.get("hand", 0.0025))
    ease += E.get("cuff", 0.002) * np.clip(1 + dwr / 0.02, 0, 1)    # (dwr < 0 on the hand side) the opening flares a little
    ease = smooth_field(ease, ed, 4)
if KIND == "coat":
    E = R.get("ease", {})
    ease = E.get("torso", 0.02) + (E.get("sleeve", 0.018) - E.get("torso", 0.02)) * np.clip(armw, 0, 1)
    dv = np.array([resid(c)["v"] for c in P])
    lap = (P[:, 2] > V_["z_break"]) & (dv < V_.get("lapel_w", 0.05))
    ease += np.where(lap, E.get("lapel", 0.006) * np.clip(1 - dv / V_.get("lapel_w", 0.05), 0.3, 1), 0.0)
    ease += E.get("collar", 0.006) * np.clip(1 - (Z_NECK - P[:, 2]) / 0.05, 0, 1)
    tor_ = np.clip(1 - armw / 0.3, 0, 1)
    zw_ = V_.get("waist_z", 0.93)
    ease += tor_ * (E.get("waist", 0.008) * np.exp(-((P[:, 2] - zw_) / 0.08) ** 2)
                    + E.get("skirt", 0.022) * np.clip((zw_ + 0.04 - P[:, 2]) / 0.2, 0, 1))
    ease = smooth_field(ease, ed, 4)
    under = np.zeros(len(P))
    for nm in R.get("over", []):
        uo = next(o for o in load(OUT / f"{nm}.glb") if o.type == "MESH")
        ub = BVHTree.FromObject(uo, bpy.context.evaluated_depsgraph_get())
        for i, (p_, n_) in enumerate(zip(P, N)):
            hit = ub.ray_cast(Vector(p_ - n_ * 0.01), Vector(n_), 0.1)
            # a layer beneath lies roughly parallel; a hit at a grazing angle is the side of a sleeve (the back by
            # the armpit pushed out 8 cm into shards)
            if hit[0] is not None and abs(hit[1].dot(Vector(n_))) > R.get("under_cos", 0.5):
                under[i] = max(under[i], hit[3] - 0.01)
        bpy.data.objects.remove(uo)
    # (the cap is for the sleeves: rays from the armpit hit the shirt sleeve; the torso takes the full depth)
    need = np.where(armw > 0.3, np.minimum(under, E.get("under_max", 0.045)), np.minimum(under, 0.08)) + E.get("clear", 0.006)
    ease = np.maximum(ease, need)
    ease = smooth_field(ease, ed, 6)
    ease = np.maximum(ease, need)
    log("coat over-layer clearance mm p50/p90", np.round(np.percentile(under, [50, 90]) * 1000, 1).tolist())
if KIND == "vest":
    # built on the layers beneath: torso ease, a lapel roll along the V, then never closer than "clear"
    # outside any "over" shell (shirt, breeches waistband) along the body normal
    E = R.get("ease", {})
    ease = np.full(len(P), E.get("torso", 0.014))
    dv = np.array([resid(c)["v"] for c in P])
    ease += E.get("lapel", 0.004) * np.clip(1 - dv / V_.get("lapel_w", 0.022), 0, 1) * (dv < 1)
    ease = smooth_field(ease, ed, 4)
    under = np.zeros(len(P))
    for nm in R.get("over", []):
        uo = next(o for o in load(OUT / f"{nm}.glb") if o.type == "MESH")
        ub = BVHTree.FromObject(uo, bpy.context.evaluated_depsgraph_get())
        for i, (p_, n_) in enumerate(zip(P, N)):
            hit = ub.ray_cast(Vector(p_ - n_ * 0.01), Vector(n_), 0.09)
            # a layer beneath lies roughly parallel; a hit at a grazing angle is the side of a sleeve (the back by
            # the armpit pushed out 8 cm into shards)
            if hit[0] is not None and abs(hit[1].dot(Vector(n_))) > R.get("under_cos", 0.5):
                under[i] = max(under[i], hit[3] - 0.01)
        bpy.data.objects.remove(uo)
    need = np.minimum(under, E.get("under_max", 0.03)) + E.get("clear", 0.005)   # (rays that hit a sleeve)
    ease = np.maximum(ease, need)
    ease = smooth_field(ease, ed, 6)
    ease = np.maximum(ease, need)
    log("vest over-layer clearance mm p50/p90", np.round(np.percentile(under, [50, 90]) * 1000, 1).tolist())
log("ease mm p10/50/90/max", np.round(np.percentile(ease, [10, 50, 90, 100]) * 1000, 1).tolist())

mid = reg
Pm = P + N * ease[:, None]
if KIND == "boot":
    # boot top = a clean round tube over the breeches cuff (or the leg): per leg, radius about the ring
    # centroid held to at least (breeches / leg radius there + "top_clear"), blended out over "top_len"
    if (OUT / "breeches.glb").exists() and "breeches" in R.get("over", ["breeches"]):
        bo = next(o for o in load(OUT / "breeches.glb") if o.type == "MESH")
        BRv = np.array([bo.matrix_world @ v.co for v in bo.data.vertices])
        bpy.data.objects.remove(bo)
    else:
        BRv = BPv
    tl_ = R.get("top_len", 0.07)
    for _, sg in SIDES:
        on = (Pm[:, 0] * sg > 0) & (Pm[:, 2] > Z_TOP - tl_ - 0.01)
        if not on.any():
            continue
        ring_ = on & (Pm[:, 2] > Z_TOP - 0.015)
        cen = Pm[ring_][:, :2].mean(0)
        br = BRv[(BRv[:, 0] * sg > 0) & (BRv[:, 2] > Z_TOP - tl_ - 0.02) & (BRv[:, 2] < Z_TOP + 0.01)]
        rb = np.percentile(np.linalg.norm(br[:, :2] - cen, axis=1), 97) if len(br) else 0.0
        rel = Pm[on][:, :2] - cen
        rr = np.linalg.norm(rel, axis=1)
        w_ = np.clip((Pm[on][:, 2] - (Z_TOP - tl_)) / tl_, 0, 1)
        w_ = w_ * w_ * (3 - 2 * w_)
        rt = rb + R.get("top_clear", 0.008)
        rnew = np.maximum(rr, rr + (rt - rr) * w_)
        Pm[np.flatnonzero(on), 0] = cen[0] + rel[:, 0] / np.maximum(rr, 1e-6) * rnew
        Pm[np.flatnonzero(on), 1] = cen[1] + rel[:, 1] / np.maximum(rr, 1e-6) * rnew
        log("boot top radius mm", round(rt * 1000, 1))
if KIND in ("shirt", "coat") and R.get("armpit_relax", 30):
    # the offset surface folds over itself in the armpit crease (hidden at rest, crumpled once the arm
    # rises): relax positions in the arm / torso band, pinned outside it
    bandp = (armw > 0.2) & (armw < 0.8) & (P[:, 2] > 0.95) & (np.abs(P[:, 0]) > 0.1)
    bandp = smooth_field(bandp.astype(float), ed, 2) > 0.2
    for _ in range(R.get("armpit_relax", 30)):
        Pm = np.where(bandp[:, None], smooth_field(Pm, ed, 1, pin=~bandp), Pm)
        Pq = np.where(bandp[:, None], smooth_field(Pm, ed, 1, pin=~bandp), Pm)
        Pm = Pm - 0.5 * (Pq - Pm) * bandp[:, None]
    req_ = need if KIND == "coat" else np.full(len(P), 0.004)   # never back inside the layers beneath
    dn_ = np.sum((Pm - P) * N, 1)
    Pm = Pm + N * np.maximum(req_ - dn_, 0)[:, None]
    log("armpit relaxed", int(bandp.sum()), "verts")
if KIND == "glove" and R.get("round", 0):
    # rounder mitten: blend each hand toward an ellipsoid fitted to it (PCA axes, 95th-percentile radii),
    # only past the wrist tube so the cuff stays put
    for s_, sg in SIDES:
        co_, dd_ = WRIST[sg]
        on = (Pm[:, 0] * sg > 0.25) & (-dwr > R.get("top_len", 0.06) * 0.7)
        if on.sum() < 20:
            continue
        Q = Pm[on]
        c0 = Q.mean(0)
        U_, S_, VT = np.linalg.svd(Q - c0, full_matrices=False)
        loc = (Q - c0) @ VT.T
        rad3 = np.percentile(np.abs(loc), 97, axis=0) * np.array(R.get("round_scale", [1.0, 1.0, 1.15]))
        dirs = loc / np.maximum(np.linalg.norm(loc / rad3, axis=1, keepdims=True), 1e-9)
        w_ = R["round"] * np.clip((-dwr[on] - R.get("top_len", 0.06) * 0.7) / 0.03, 0, 1)
        Pm[on] = Pm[on] * (1 - w_[:, None]) + (c0 + dirs @ VT) * w_[:, None]
        log("glove rounded", s_, "radii mm", np.round(rad3 * 1000).tolist())
if KIND == "glove":
    # the top of the glove tucks under the shirt cuff: within "top_len" of the opening the radius about
    # the wrist axis (through the opening ring's centroid) is held to "top_r", blending back below it
    for s_, sg in SIDES:
        co_, dd_ = WRIST[sg]
        on = P[:, 0] * sg > 0.25
        dep = -dwr                                  # depth into the hand from the opening
        ring_ = on & (np.abs(dep) < 0.008)
        if not ring_.any():
            continue
        rel0 = Pm[ring_] - co_
        cen = co_ + (rel0 - np.outer(rel0 @ dd_, dd_)).mean(0)
        sel_ = on & (dep < R.get("top_len", 0.06))
        rel = Pm[sel_] - cen
        al = rel @ dd_
        rad = rel - np.outer(al, dd_)
        rr = np.linalg.norm(rad, axis=1)
        w_ = np.clip(1 - (dep[sel_] - R.get("top_len", 0.06) * 0.6) / (R.get("top_len", 0.06) * 0.4), 0, 1)
        rnew = np.where(rr > R.get("top_r", 0.034), R.get("top_r", 0.034), rr)
        rr2 = rr + (rnew - rr) * w_
        Pm[sel_] = cen + np.outer(al, dd_) + rad / np.maximum(rr, 1e-6)[:, None] * rr2[:, None]
        log("glove top", s_, "max radius before mm", round(float(rr.max()) * 1000, 1))
if KIND in ("coat", "vest") and R.get("offset_smooth", 0):
    # the offset direction tilts at open edges (one-sided normals) and spikes the edge: smooth the
    # offset vectors, then restore at least the required depth along the normal
    Dv = N * ease[:, None]
    Dv = smooth_field(Dv, ed, R["offset_smooth"])
    dn_ = np.sum(Dv * N, 1)
    Dv = Dv + N * np.maximum(need - dn_, 0)[:, None]
    Pm = P + Dv
if KIND == "coat":
    # the back skirt and tails hang: below "hang_top" the horizontal radius about the body axis never
    # shrinks going down (the cloth falls straight over the seat and the tail instead of following them in)
    yc_ = ycf(Pm[:, 2])
    rel_ = np.stack([Pm[:, 0], Pm[:, 1] - yc_], 1)
    rr_ = np.linalg.norm(rel_, axis=1)
    az_ = np.degrees(np.arctan2(Pm[:, 0], -(Pm[:, 1] - yc_)))
    hang = (Pm[:, 2] < V_["hang_top"]) & (np.abs(Pm[:, 0]) < 0.2) & (np.abs(az_) > V_.get("hang_az", 60))
    nb_ = 72
    bins = ((az_ + 180) / 360 * nb_).astype(int) % nb_
    order = np.argsort(-Pm[:, 2])
    run = np.zeros(nb_)
    target = rr_.copy()
    for i in order:
        if not hang[i]:
            continue
        b_ = bins[i]
        run[b_] = max(run[b_], rr_[i])
        target[i] = run[b_]
    push_ = np.where(hang, target - rr_, 0.0)     # (azimuth bins -> stair steps: smooth the push over the mesh)
    push_ = smooth_field(push_, ed, R.get("hang_smooth", 25))
    target = rr_ + np.maximum(push_, 0.0)
    scale = np.where(target > rr_, target / np.maximum(rr_, 1e-6), 1.0)
    Pm[:, 0] = rel_[:, 0] * scale
    Pm[:, 1] = yc_ + rel_[:, 1] * scale
    # the hanging skirt is one smooth surface: relax it (edges to the rest of the coat pinned), but
    # never inside the layers beneath (radius >= that of body + clearance over the under shells)
    zone = hang | (smooth_field(hang.astype(float), ed, 3) > 0.01)
    Pmin = P + N * need[:, None]
    rmin = np.linalg.norm(np.stack([Pmin[:, 0], Pmin[:, 1] - ycf(Pmin[:, 2])], 1), axis=1)
    for _ in range(R.get("skirt_relax", 6)):
        Pm = np.where(zone[:, None], smooth_field(Pm, ed, 8, pin=~zone), Pm)
        yc_ = ycf(Pm[:, 2])
        rel_ = np.stack([Pm[:, 0], Pm[:, 1] - yc_], 1)
        rr2 = np.linalg.norm(rel_, axis=1)
        sc_ = np.where(zone & (rr2 < rmin), rmin / np.maximum(rr2, 1e-6), 1.0)
        Pm[:, 0] = rel_[:, 0] * sc_
        Pm[:, 1] = yc_ + rel_[:, 1] * sc_
    # straight hem: the edge stays exactly on the hem line (the hang / relax / offset moved it up and down)
    hem_b = boundary & (np.abs(P[:, 2] - hem_z(P[:, 0], P[:, 1], P[:, 2])) < 0.006)
    Pm[hem_b, 2] = hem_z(Pm[hem_b, 0], Pm[hem_b, 1], Pm[hem_b, 2])
    for _ in range(4):                            # ease the row above onto it
        Pm = np.where(zone[:, None] & ~hem_b[:, None], smooth_field(Pm, ed, 2, pin=hem_b | ~zone), Pm)
    log("coat hem verts pinned", int(hem_b.sum()))
    log("coat hang verts", int(hang.sum()), "max push mm", round(float(np.max((target - rr_) * hang)) * 1000, 1))
if KIND == "shirt":
    # cuffs are round tubes around the wrist, not shrink-wrapped over the hand: inside the cuff band each
    # vertex goes to the forearm axis + one radius per side (largest wrist radius + clearance), blended
    # back to the fitted sleeve over "cuff_blend" above the cuff
    cuff = R.get("cuff", 0.045)
    for s_, sg in SIDES:
        co_, dd_ = WRIST[sg]
        on = (P[:, 0] * sg > 0.2) & (dwr < cuff + R.get("cuff_blend", 0.04))
        if not on.any():
            continue
        # axis through the centroid of the sleeve ring at the cuff top (the bone runs off-centre)
        top = on & (np.abs(dwr - cuff) < 0.008)
        for w8 in (0.015, 0.03, 0.06):                 # (coarse meshes: widen the ring until it has verts)
            if top.sum() >= 6:
                break
            top = on & (np.abs(dwr - cuff) < w8)
        rel0 = Pm[top] - co_
        cen = co_ + (rel0 - np.outer(rel0 @ dd_, dd_)).mean(0)
        rel = Pm[on] - cen
        along = rel @ dd_
        radial = rel - along[:, None] * dd_
        rr = np.linalg.norm(radial, axis=1)
        rtop = np.linalg.norm(rel0 - np.outer(rel0 @ dd_, dd_) - (cen - co_), axis=1)
        r_cuff = float(np.median(rtop)) + R.get("cuff_clear", 0.004)    # the sleeve's own radius at the wrist
        w_ = np.clip(1 - (dwr[on] - cuff) / R.get("cuff_blend", 0.04), 0, 1)
        w_ = w_ * w_ * (3 - 2 * w_)
        tgt = cen + along[:, None] * dd_ + radial / np.maximum(rr, 1e-6)[:, None] * r_cuff
        Pm[on] = Pm[on] * (1 - w_[:, None]) + tgt * w_[:, None]
        log("cuff", s_, "radius mm", round(r_cuff * 1000, 1), "ring", int(top.sum()), "on", int(on.sum()), "dwr range", np.round([dwr[on].min(), dwr[on].max()], 3).tolist(), "x range", np.round([Pm[on][:, 0].min(), Pm[on][:, 0].max()], 3).tolist())
mid.data.vertices.foreach_set("co", Pm.ravel())
mid.data.update()
mid.name = mid.data.name = f"{PIECE}_mid"
# store per-vertex design coordinates as attributes for the detail pass
extra_attr = {"armw": armw}
if KIND == "vest":
    extra_attr["back"] = (P[:, 1] > ycf(P[:, 2])).astype(float)
if KIND == "shirt":
    extra_attr.update({"dwr": np.minimum(dwr, 1.0), "dhem": dhem})
if KIND == "coat":
    extra_attr.update({"dwr": np.minimum(dwr, 1.0)})
if KIND == "glove":
    extra_attr.update({"dwr": np.clip(-dwr, -1.0, 1.0),
                       "back": np.array([n_[0] * (1 if p_[0] > 0 else -1) for p_, n_ in zip(P, N)])})
for name, val in (("ease", ease), ("z0", P[:, 2]), *extra_attr.items()):
    a = mid.data.attributes.new(name, "FLOAT", "POINT")
    a.data.foreach_set("value", val.astype(np.float32))

# ---- 3. hi (detail) and lo (game)
hi = mid.copy()
hi.data = mid.data.copy()
hi.name = hi.data.name = f"{PIECE}_hi"
bpy.context.scene.collection.objects.link(hi)
only_select(hi)
m = hi.modifiers.new("sub", "SUBSURF")
m.levels = 2
bpy.ops.object.modifier_apply(modifier=m.name)
Ph, Nh = mesh_vn(hi.data)
log("hi", len(Ph), "verts")


def leg_frame(side):
    h, t = bone[f"{side}UpLeg"]
    ax = (t - h) / np.linalg.norm(t - h)
    fwd = np.array([0, -1.0, 0]) - ax * ax[1] * -1
    fwd -= ax * (fwd @ ax)
    fwd /= np.linalg.norm(fwd)
    return h, ax, fwd, np.cross(ax, fwd)


LEGS = {s: leg_frame(s) for s in ("Left", "Right")}


def groove(d, w=0.0018, depth=0.0009):
    return -depth * np.exp(-(d / w) ** 2)


disp = np.zeros(len(Ph))
occ = np.ones(len(Ph))
zh = Ph[:, 2]
x, y = Ph[:, 0], Ph[:, 1]
if KIND == "breeches":
    front = y < np.interp(zh, [Z_BOT, Z_TOP], [0.05, 0.04])
    ZT = ztop(y)                                          # local waist line per detail vertex
    # waistband: raised, top stitch + bottom edge groove
    in_wb = zh > ZT - wb
    disp += np.where(in_wb, 0.0016, 0.0) * np.clip((ZT - zh) / 0.004, 0, 1)
    disp += groove(np.abs(zh - (ZT - wb)), 0.0016, 0.0012) + groove(np.abs(zh - (ZT - 0.007)), 0.0009, 0.0004)
    # knee band
    in_kb = zh < Z_BOT + kb
    disp += np.where(in_kb, 0.0016, 0.0) * np.clip((zh - Z_BOT) / 0.004, 0, 1)
    disp += groove(np.abs(zh - (Z_BOT + kb)), 0.0016, 0.0012) + groove(np.abs(zh - (Z_BOT + 0.007)), 0.0009, 0.0004)
    # fly placket (front, character's left of centre), J-curve into the centre seam
    fly_bot = Z_TOP - R.get("fly_len", 0.15)
    fz = (zh < ZT - wb) & (zh > fly_bot) & front
    dfly = np.where(fz, np.abs(x - 0.022), 9.0)
    jz = (zh <= fly_bot) & (zh > fly_bot - 0.03) & front
    jx = 0.022 * np.clip((zh - (fly_bot - 0.03)) / 0.03, 0, 1) ** 0.6
    dfly = np.minimum(dfly, np.where(jz, np.abs(x - jx), 9.0))
    disp += groove(dfly, 0.0016, 0.0011)
    # centre seams (front below the fly, back) on the pelvis
    pelvis = zh > CROTCH_Z - 0.02
    disp += groove(np.where(pelvis & (zh < ZT - wb) & ((~front) | (zh < fly_bot - 0.02)), np.abs(x), 9.0), 0.0015, 0.0009)
    # slit pockets: slanted lines on the front hips
    for s in (1, -1):
        a0, a1 = np.array([0.085 * s, Z_TOP - wb]), np.array([0.135 * s, Z_TOP - wb - 0.11])
        q = np.stack([x, zh], 1)
        u = np.clip(((q - a0) @ (a1 - a0)) / ((a1 - a0) @ (a1 - a0)), 0, 1)
        dp = np.linalg.norm(q - (a0 + u[:, None] * (a1 - a0)), axis=1)
        disp += groove(np.where(front & (zh < Z_TOP - wb) & (zh > Z_TOP - wb - 0.115), dp, 9.0), 0.0018, 0.0014)
    # legs: side seam (outer), inseam (inner), front crease; folds above the knee and on the flare
    easeh_f = np.zeros(len(Ph), np.float32)
    hi.data.attributes["ease"].data.foreach_get("value", easeh_f)
    easeh = easeh_f.astype(float)
    for side, (h, ax, fwd, lat) in LEGS.items():
        sgn = 1 if side == "Left" else -1
        on = (x * sgn > 0.005) & (zh < CROTCH_Z + 0.04)
        rel = Ph - h
        along = rel @ ax
        radial = rel - along[:, None] * ax
        rr = np.linalg.norm(radial, axis=1)
        phi = np.arctan2(radial @ (-lat * sgn), radial @ fwd)         # 0 = front, +pi/2 = outer side
        arc = lambda a0: np.abs((phi - a0 + np.pi) % (2 * np.pi) - np.pi) * rr  # noqa: E731
        disp += np.where(on, groove(arc(np.pi / 2), 0.0016, 0.0010) + groove(arc(-np.pi / 2), 0.0016, 0.0009)
                         + groove(arc(0.0), 0.0035, 0.0006), 0.0)
        # gathered folds above the knee band: horizontal ripples fading upward
        kz = (zh - (Z_BOT + kb)) / 0.12
        wk = np.clip(1 - kz, 0, 1) * (kz > 0) * on
        ph = 0.9 * np.sin(phi * 2.3 + 1.7 * sgn) + 0.6 * np.sin(phi * 5.1 + zh * 40)
        amp = 0.55 + 0.45 * np.sin(phi * 3.7 + zh * 23 + sgn)
        ripple = np.sin((zh / 0.026 + 0.25 * ph) * 2 * np.pi)
        disp += 0.0014 * ripple * amp * wk
        # flare folds: long soft diagonal folds where the cloth stands off the thigh
        fl = np.clip((easeh - 0.02) / 0.02, 0, 1) * on
        disp += 0.0022 * np.sin(phi * 5 + zh / 0.05) * fl
elif KIND == "shirt":
    def attr(nm):
        a_ = np.zeros(len(Ph), np.float32)
        hi.data.attributes[nm].data.foreach_get("value", a_)
        return a_.astype(float)
    armh, dwh, dhh = attr("armw"), attr("dwr"), attr("dhem")
    torso = armh < 0.25
    front = (y < 0.0) & torso
    # button placket: raised strip with stitch lines, buttons every 6.5 cm
    plk = front & (zh < Z_NECK - 0.004)
    disp += np.where(plk & (np.abs(x) < 0.0125), 0.0008, 0.0)
    disp += groove(np.where(plk, np.abs(np.abs(x) - 0.0125), 9.0), 0.0011, 0.0008)
    tintm = np.ones(len(Ph))
    for zb_ in np.arange(Z_NECK - 0.03, float(ztop(-0.1)) - (Z_TOP - Z_BOT) + 0.05, -R.get("button_step", 0.065)):
        dbt = np.sqrt(x ** 2 + (zh - zb_) ** 2)
        disp += np.where(plk, 0.0017 * np.exp(-(dbt / 0.0036) ** 2) - 0.0005 * np.exp(-((dbt - 0.0045) / 0.0012) ** 2), 0.0)
        if R.get("button_tint"):
            tintm = np.where(plk & (dbt < 0.0042), R["button_tint"], tintm)
    if R.get("princess"):          # princess seams: front and back panels curving over the bust / blades
        for sx in (1, -1):
            xs = sx * (0.045 + 0.03 * np.clip((zh - 1.0) / 0.2, 0, 1))
            disp += np.where(torso & (zh > ztop(y) - (Z_TOP - Z_BOT)), groove(np.abs(x - xs), 0.0013, 0.0009), 0.0)
    # side seams of the torso, armhole seam, sleeve underseams
    yc = 0.0
    phit = np.arctan2(x, -(y - yc))
    rt = np.hypot(x, y - yc)
    disp += np.where(torso, groove(np.abs(np.abs(phit) - np.pi / 2) * rt, 0.0015, 0.0009), 0.0)
    disp += groove(np.abs(armh - 0.5) * 0.05, 0.0014, 0.0009) * (np.abs(x) > 0.06)
    for s_, sg in SIDES:
        a0_, a1_, a2_ = bone[f"{s_}Arm"][0], bone[f"{s_}ForeArm"][0], bone[f"{s_}Hand"][0]
        on = (x * sg > 0.08) & (armh > 0.3)
        # nearest point on the arm polyline -> radial frame around it, 'down' = 0
        best = np.full(len(Ph), 9.0)
        rad = np.zeros_like(Ph)
        axs = np.zeros_like(Ph)
        for q0, q1 in ((a0_, a1_), (a1_, a2_)):
            dq = q1 - q0
            u = np.clip(((Ph - q0) @ dq) / (dq @ dq), 0, 1)
            c_ = q0 + u[:, None] * dq
            dist = np.linalg.norm(Ph - c_, axis=1)
            take = dist < best
            best = np.where(take, dist, best)
            rad = np.where(take[:, None], Ph - c_, rad)
            axs = np.where(take[:, None], np.tile(dq / np.linalg.norm(dq), (len(Ph), 1)), axs)
        down = np.array([0, 0, -1.0]) - axs * axs[:, 2:3] * -1
        down -= axs * np.sum(down * axs, 1, keepdims=True)
        down /= np.maximum(np.linalg.norm(down, axis=1, keepdims=True), 1e-9)
        side = np.cross(axs, down)
        phi = np.arctan2(np.sum(rad * side, 1) * sg, np.sum(rad * down, 1))
        rr = np.linalg.norm(rad, axis=1)
        disp += np.where(on, groove(np.abs(phi) * rr, 0.0015, 0.0009), 0.0)        # underseam
        # cuff: raised band, edge grooves, a cufflink on the back of the wrist
        cuff = R.get("cuff", 0.045)
        inc = on & (dwh < cuff)
        disp += np.where(inc, 0.0015 * np.clip(dwh / 0.003, 0, 1), 0.0)
        disp += np.where(on, groove(np.abs(dwh - cuff), 0.0015, 0.0011) + groove(np.abs(dwh - 0.006), 0.0008, 0.0004), 0.0)
        dl = np.hypot((np.abs(phi) - np.pi * 0.62) * rr, dwh - cuff * 0.5)
        disp += np.where(on, 0.0022 * np.exp(-(dl / 0.0042) ** 2), 0.0)
        # gathers above the cuff and at the inner elbow
        g_ = np.clip(1 - (dwh - cuff) / 0.09, 0, 1) * (dwh > cuff) * on
        ph_ = 0.8 * np.sin(phi * 2.1 + sg) + 0.5 * np.sin(phi * 4.7 + dwh * 50)
        disp += 0.0012 * np.sin((dwh / 0.021 + 0.3 * ph_) * 2 * np.pi) * g_ * (0.6 + 0.4 * np.sin(phi * 3.3))
        de = np.linalg.norm(Ph - a1_, axis=1)
        inner = np.clip(np.cos(phi - np.pi * 0.5 * sg * 0), 0, 1)
        disp += 0.0013 * np.sin(de / 0.012 * 2 * np.pi) * np.exp(-(de / 0.045) ** 2) * on * (0.5 + 0.5 * inner)
    # tucked hem: soft blousing folds just above the breeches line
    bl = np.clip(1 - dhh / 0.08, 0, 1) * torso
    phb = 0.9 * np.sin(phit * 3.1) + 0.5 * np.sin(phit * 7.3 + zh * 30)
    disp += 0.0013 * np.sin(phit * 9 + phb) * bl
if KIND == "vest":
    tintm = np.ones(len(Ph))                      # extra darkening (buttons, strap, buckle)
    rs = [resid(c) for c in Ph]
    dh = np.array([r_["hem"] for r_ in rs])
    dv = np.array([r_["v"] for r_ in rs])
    da = np.array([r_["arm"] for r_ in rs])
    dn = np.array([r_["neck"] for r_ in rs])
    ycv = ycf(zh)
    front = y < ycv
    phit = np.arctan2(x, -(y - ycv))
    rt = np.hypot(x, y - ycv)
    # edge stitching 6 mm in from every edge, a turned edge (slight rise) at the hem / armholes
    for d_ in (dh, da, np.where(front, dv, 9.0)):
        disp += groove(np.abs(d_ - 0.006), 0.0009, 0.0005) + 0.0008 * np.clip(1 - d_ / 0.004, 0, 1)
    # lapels: raised band along the V, roll line groove at its inner edge, notch near the top
    lw = V_.get("lapel_w", 0.022)
    inl = front & (zh > V_["z_vbot"] - 0.01) & (dv < lw)
    disp += np.where(inl, 0.0018 * np.clip(dv / 0.003, 0, 1), 0.0)
    disp += np.where(front & (zh > V_["z_vbot"] - 0.01), groove(np.abs(dv - lw), 0.0013, 0.0012), 0.0)
    zn_ = Z_NECK - V_.get("notch_down", 0.045)
    disp += np.where(inl, groove(np.abs(zh - zn_ + 0.4 * dv), 0.0012, 0.0012), 0.0)
    # centre front: the two fronts meet below the V (overlap edge + stitch)
    cf = front & (zh < V_["z_vbot"])
    disp += np.where(cf, groove(np.abs(x - 0.0), 0.0012, 0.0011) + 0.0008 * (x < 0) * np.clip(-x / 0.003, 0, 1), 0.0)
    # four buttons on the centre line
    zb_ = np.linspace(V_["z_vbot"] - 0.012, V_["z_notch"] + 0.035, R.get("buttons", 4))
    for zz in zb_:
        dbt = np.sqrt((x - 0.0) ** 2 + (zh - zz) ** 2)
        b_ = front & (dbt < 0.0075)
        disp += np.where(front, 0.0022 * np.clip(1 - (dbt / 0.0065) ** 2, 0, 1), 0.0)
        disp += np.where(front, groove(np.abs(dbt - 0.0068), 0.0007, 0.0006), 0.0)
        tintm = np.where(b_, 0.42, tintm)
    # welt pockets: slanted raised welts with grooves round them
    for sg in (1, -1):
        pc = np.array(V_.get("pocket", [0.085, 0.965]))
        ang = np.radians(V_.get("pocket_tilt", 8)) * sg
        u_ = (x - pc[0] * sg) * np.cos(ang) + (zh - pc[1]) * np.sin(ang)
        w_ = -(x - pc[0] * sg) * np.sin(ang) + (zh - pc[1]) * np.cos(ang)
        hw, hh_ = V_.get("pocket_w", 0.036), 0.0055
        inside = front & (np.abs(u_) < hw) & (np.abs(w_) < hh_)
        edge = np.maximum(np.abs(u_) - hw, np.abs(w_) - hh_)
        disp += np.where(inside, 0.0014, 0.0) + np.where(front, groove(np.abs(edge), 0.0009, 0.0011), 0.0)
        disp += np.where(inside, groove(np.abs(w_), 0.0006, 0.0005), 0.0)
        # front dart below the pocket
        dd_ = front & (zh < pc[1] - hh_ - 0.004) & (dh > 0.01)
        disp += np.where(dd_, groove(np.abs(x - (pc[0] + 0.005) * sg), 0.0011, 0.0006), 0.0)
    # side seams, back centre seam
    disp += groove(np.abs(np.abs(phit) - np.pi / 2) * rt, 0.0013, 0.0008)
    bk = ~front
    disp += np.where(bk, groove(np.abs(x), 0.0012, 0.0008), 0.0)
    # back adjuster: two strap halves from the side seams to a buckle at the centre back
    zs_ = V_.get("strap_z", 0.935)
    sh_ = 0.009
    st = bk & (np.abs(zh - zs_) < sh_) & (np.abs(x) < V_.get("strap_x", 0.085))
    disp += np.where(st, 0.0016, 0.0) + np.where(bk & (np.abs(x) < V_.get("strap_x", 0.085)),
                                                groove(np.abs(np.abs(zh - zs_) - sh_), 0.0008, 0.0009), 0.0)
    disp += np.where(st, groove(np.abs(np.abs(zh - zs_) - sh_ + 0.002), 0.0005, 0.0003), 0.0)
    tintm = np.where(st, 0.82, tintm)
    bx, bz = np.abs(x - 0.0) , np.abs(zh - zs_)
    frame = bk & (np.maximum(bx / 0.013, bz / 0.011) < 1) & (np.maximum(bx / 0.013, bz / 0.011) > 0.62)
    bar = bk & (np.abs(x) < 0.0015) & (bz < 0.011)
    disp += np.where(frame | bar, 0.0026, 0.0)
    tintm = np.where(frame | bar, 0.3, tintm)
    # soft drag folds from the buttons toward the sides and at the small of the back
    disp += 0.0009 * np.sin(phit * 7 + zh * 35) * np.clip(1 - dh / 0.12, 0, 1)
if KIND == "coat":
    tintm = np.ones(len(Ph))
    def attr(nm):
        a_ = np.zeros(len(Ph), np.float32)
        hi.data.attributes[nm].data.foreach_get("value", a_)
        return a_.astype(float)
    armh, dwh = attr("armw"), attr("dwr")
    rs = [resid(c) for c in Ph]
    dh = np.array([r_["hem"] for r_ in rs])
    dv = np.array([r_["v"] for r_ in rs])
    ycv = ycf(zh)
    torso = (armh < 0.35) & (np.abs(x) < 0.2)
    front = (y < ycv) & torso
    phit = np.arctan2(x, -(y - ycv))
    rt = np.hypot(x, y - ycv)
    # edge stitching along hem and front edges, turned edges
    for d_ in (np.where(torso, dh, 9.0), np.where(front, dv, 9.0)):
        disp += groove(np.abs(d_ - 0.007), 0.0009, 0.0005) + 0.001 * np.clip(1 - d_ / 0.005, 0, 1)
    # notched lapels: raised band from the break point up, roll line, gorge seam toward the notch
    lw = V_.get("lapel_w", 0.05)
    zb, zn = V_["z_break"], V_["z_notch"]
    wl = lw * np.clip((zh - zb) / 0.06, 0, 1)         # lapel widens from the break point
    lap = front & (zh > zb) & (dv < wl) & (zh < zn + 0.004)
    disp += np.where(lap, 0.0024 * np.clip(dv / 0.004, 0, 1), 0.0)
    disp += np.where(front & (zh > zb) & (zh < zn + 0.004), groove(np.abs(dv - wl), 0.0016, 0.0016), 0.0)
    col_ = front & (zh >= zn + 0.004)                  # collar above the notch
    disp += np.where(col_ & (dv < 0.035), 0.002, 0.0) + np.where(col_, groove(np.abs(dv - 0.035), 0.0014, 0.0013), 0.0)
    disp += np.where(front & (dv < lw + 0.01), groove(np.abs(zh - (zn + 0.004)), 0.0012, 0.0014), 0.0)   # gorge
    # back collar band + seam
    bk = (y >= ycv) & torso
    disp += np.where(bk, 0.0018 * np.clip(1 - (Z_NECK - zh) / 0.04, 0, 1), 0.0) + \
        np.where(bk, groove(np.abs(Z_NECK - zh - 0.04), 0.0013, 0.0011), 0.0)
    # three front buttons on the wearer's left front edge, button holes on the right
    for zz in V_.get("buttons_z", [0.99, 0.925, 0.86]):
        bxp = v_w(zz) + 0.022
        for sgx, kind_ in ((1, "button"), (-1, "hole")):
            if kind_ == "button":
                dbt = np.sqrt((x - bxp) ** 2 + (zh - zz) ** 2)
                disp += np.where(front, 0.0026 * np.clip(1 - (dbt / 0.0085) ** 2, 0, 1) + groove(np.abs(dbt - 0.0088), 0.0008, 0.0007), 0.0)
                tintm = np.where(front & (dbt < 0.009), 0.45, tintm)
            else:
                dhl = np.maximum(np.abs(x + bxp) - 0.009, 0) + np.abs(zh - zz)
                disp += np.where(front, groove(dhl, 0.0008, 0.0011), 0.0)
    # hip pocket flaps and a breast welt
    for sg in (1, -1):
        for (cx, cz, hw, hh_, flap) in ((0.105, V_.get("pocket_z", 0.80), 0.055, 0.022, True), (0.09, 1.09, 0.035, 0.006, False)):
            if not flap and sg < 0:
                continue
            u_ = x - cx * sg
            w_ = zh - cz
            inside = front & (np.abs(u_) < hw) & (w_ < hh_) & (w_ > -hh_)
            edge = np.maximum(np.abs(u_) - hw, np.abs(w_) - hh_)
            disp += np.where(inside, 0.0018 if flap else 0.0012, 0.0) + np.where(front, groove(np.abs(edge), 0.001, 0.0012), 0.0)
            if flap:                                   # shadow under the flap
                tintm = np.where(front & (np.abs(u_) < hw) & (w_ < -hh_) & (w_ > -hh_ - 0.004), 0.7, tintm)
    # seams: side, centre back with a vent, shoulder, armhole, sleeve underseam; waist seam at the back
    disp += np.where(torso, groove(np.abs(np.abs(phit) - np.pi / 2) * rt, 0.0014, 0.0009), 0.0)
    disp += np.where(bk, groove(np.abs(x), 0.0013, 0.0009), 0.0)
    vent = bk & (zh < V_["z_back"] + V_.get("vent_h", 0.17)) & (np.abs(x) < 0.02)
    disp += np.where(vent, groove(np.abs(x - 0.006), 0.0012, 0.0016) + 0.0008 * (x > 0.006), 0.0)
    disp += groove(np.abs(armh - 0.5) * 0.06, 0.0015, 0.001) * (np.abs(x) > 0.05)
    disp += np.where(bk, groove(np.abs(zh - V_.get("waist_z", 0.93)), 0.0012, 0.0008), 0.0)
    # sleeves: underseam, cuff band, three cuff buttons on the outer back of each sleeve
    for s_, sg in SIDES:
        a0_, a1_, a2_ = bone[f"{s_}Arm"][0], bone[f"{s_}ForeArm"][0], bone[f"{s_}Hand"][0]
        on = (x * sg > 0.12) & (armh > 0.3)
        best = np.full(len(Ph), 9.0)
        rad = np.zeros_like(Ph)
        axs = np.zeros_like(Ph)
        for q0, q1 in ((a0_, a1_), (a1_, a2_)):
            dq = q1 - q0
            u_ = np.clip(((Ph - q0) @ dq) / (dq @ dq), 0, 1)
            c_ = q0 + u_[:, None] * dq
            dist = np.linalg.norm(Ph - c_, axis=1)
            take = dist < best
            best = np.where(take, dist, best)
            rad = np.where(take[:, None], Ph - c_, rad)
            axs = np.where(take[:, None], np.tile(dq / np.linalg.norm(dq), (len(Ph), 1)), axs)
        down = np.array([0, 0, -1.0]) - axs * axs[:, 2:3] * -1
        down -= axs * np.sum(down * axs, 1, keepdims=True)
        down /= np.maximum(np.linalg.norm(down, axis=1, keepdims=True), 1e-9)
        side = np.cross(axs, down)
        phi = np.arctan2(np.sum(rad * side, 1) * sg, np.sum(rad * down, 1))
        rr = np.linalg.norm(rad, axis=1)
        disp += np.where(on, groove(np.abs(phi) * rr, 0.0014, 0.0009), 0.0)
        cb = V_.get("cuff_band", 0.06)
        disp += np.where(on, groove(np.abs(dwh - cb), 0.0013, 0.001) + groove(np.abs(dwh - 0.006), 0.0008, 0.0004), 0.0)
        disp += np.where(on & (dwh < 0.004), 0.001, 0.0)
        pb_ = np.pi * 0.75                              # outer back of the sleeve
        for k_ in range(3):
            dd_ = np.hypot((phi - pb_ * 1) * rr, dwh - (0.018 + 0.016 * k_))
            disp += np.where(on, 0.0018 * np.clip(1 - (dd_ / 0.0055) ** 2, 0, 1), 0.0)
            tintm = np.where(on & (dd_ < 0.006), 0.45, tintm)
        # elbow and inner-arm folds
        de = np.linalg.norm(Ph - a1_, axis=1)
        disp += 0.0012 * np.sin(de / 0.014 * 2 * np.pi) * np.exp(-(de / 0.05) ** 2) * on
    # soft drape folds on the back skirt and tails
    sk = bk & (zh < V_.get("waist_z", 0.93))
    disp += 0.0018 * np.sin(phit * 9 + 0.6 * np.sin(zh * 20)) * np.clip((V_.get("waist_z", 0.93) - zh) / 0.12, 0, 1) * sk
if KIND == "boot":
    tintm = np.ones(len(Ph))
    # boot top: turned band + stitch; sole: welt groove and darker edge; heel; back seam; toe cap
    dtop = Z_TOP - zh
    disp += 0.0012 * np.clip(1 - dtop / 0.018, 0, 1) + groove(np.abs(dtop - 0.018), 0.0009, 0.0011)
    zs_ = float(zh.min()) + R.get("sole_z", 0.022)       # (above the lowest point: shaped bodies stand lower)
    disp += groove(np.abs(zh - zs_), 0.0012, 0.0014)
    tintm = np.where(zh < zs_, 0.55, tintm)
    for s_, sg in SIDES:
        h0, _ = bone[f"{s_}Leg"]
        on = x * sg > 0
        back = on & (y > h0[1] + 0.01) & (zh > 0.12)
        disp += np.where(back, groove(np.abs(x - h0[0]), 0.0012, 0.0009), 0.0)
        f0 = bone[f"{s_}Foot"][0]
        toe = on & (zh < 0.09) & (y < f0[1] - 0.06)
        dy = y - (f0[1] - 0.09)
        disp += np.where(toe, groove(np.abs(dy), 0.0012, 0.0010), 0.0)
        # ankle creases
        ank = on & (zh > 0.09) & (zh < 0.16) & (y < h0[1])
        pass                                       # (ankle creases dropped: they read as rings)
        if R.get("laces"):                           # lace-up front: eyelet rows + crossed laces
            fr_ = on & (y < h0[1] - 0.005) & (zh > 0.05) & (zh < Z_TOP - 0.01) & (np.abs(x - h0[0]) < 0.022)
            dxl = np.abs(x - h0[0])
            disp += np.where(fr_, groove(np.abs(dxl - 0.012), 0.0012, 0.0012), 0.0)
            for zl in np.arange(0.06, Z_TOP - 0.015, R["laces"]):
                for sgl in (1, -1):
                    dd_ = np.abs((zh - zl) - sgl * (x - h0[0]) * 0.7)
                    disp += np.where(fr_ & (dxl < 0.012), 0.0009 * np.exp(-(dd_ / 0.0016) ** 2), 0.0)
                    tintm = np.where(fr_ & (dxl < 0.012) & (dd_ < 0.0015), 0.55, tintm)
if KIND == "glove":
    tintm = np.ones(len(Ph))
    def attr(nm):
        a_ = np.zeros(len(Ph), np.float32)
        hi.data.attributes[nm].data.foreach_get("value", a_)
        return a_.astype(float)
    dh_, bk_ = attr("dwr"), attr("back")              # depth into the hand from the opening, back-of-hand facing
    # rolled opening band + stitch
    disp += 0.0012 * np.clip(1 - dh_ / 0.012, 0, 1) + groove(np.abs(dh_ - 0.012), 0.0008, 0.0009)
    for s_, sg in SIDES:
        on = x * sg > 0.25
        h0, h1 = bone[f"{s_}Hand"]
        ax = (h1 - h0) / np.linalg.norm(h1 - h0)
        rel = Ph - h0
        along = rel @ ax
        side = np.cross(ax, np.array([0, 1.0, 0]))
        side /= np.linalg.norm(side)
        lat = rel @ side
        back = on & (bk_ > 0.25)
        # three points stitched on the back of the hand
        for off in (-0.012, 0.0, 0.012):
            m_ = back & (along > 0.05) & (along < 0.12)
            disp += np.where(m_, groove(np.abs(lat - off), 0.0007, 0.0007), 0.0)
        # side seams round the edge of the hand, soft creases over the knuckles and the palm
        disp += np.where(on & (np.abs(bk_) < 0.2), groove(np.abs(bk_) * 0.02, 0.0006, 0.0006), 0.0)
        kn = on & (along > 0.12) & (along < 0.2)
        pass                                       # (knuckle creases dropped: they read as ridges)
        # wrist wrinkles just in from the opening
        wr = on & (dh_ > 0.015) & (dh_ < 0.05)
        disp += np.where(wr, 0.0003 * np.sin(dh_ / 0.011 * 2 * np.pi + 1.3 * np.sin(lat * 60)) * np.clip(1 - (dh_ - 0.015) / 0.035, 0, 1), 0.0)
occ = np.clip(1 + disp / 0.0012 * 0.22, 0.65, 1.08)                  # grooves read darker
if KIND in ("vest", "coat", "glove", "boot") or (KIND == "shirt" and R.get("button_tint")):
    occ = occ * tintm
Ph2 = Ph + Nh * disp[:, None]
hi.data.vertices.foreach_set("co", Ph2.ravel())
hi.data.update()
col = hi.data.color_attributes.new("occ", "FLOAT_COLOR", "POINT")
col.data.foreach_set("color", np.repeat(occ[:, None], 4, 1).astype(np.float32).ravel())
log("detail disp mm min/max", round(float(disp.min()) * 1000, 2), round(float(disp.max()) * 1000, 2))

lo = mid
only_select(lo)
for a in list(lo.data.attributes):
    if a.name in ("ease", "z0", "armw", "dwr", "dhem", "back"):  # (coat: same set)
        lo.data.attributes.remove(a)
tri = sum(len(p.vertices) - 2 for p in lo.data.polygons)
bmq = bmesh.new()
bmq.from_mesh(lo.data)
keep_e = {v.index for v in bmq.verts if any(e.is_boundary for e in v.link_edges)}
for _ in range(R.get("edge_keep_rings", 1)):
    keep_e |= {e.other_vert(v).index for v in bmq.verts if v.index in keep_e for e in v.link_edges}
bmq.free()
vg_dec = lo.vertex_groups.new(name="_decimate")
vg_dec.add([v.index for v in lo.data.vertices if v.index not in keep_e], 1.0, "REPLACE")
vg_dec.add(sorted(keep_e), 0.0, "REPLACE")
m = lo.modifiers.new("dec", "DECIMATE")
m.ratio = min(1.0, TRIS / max(tri, 1) * 0.98)
m.vertex_group = vg_dec.name
m.vertex_group_factor = R.get("edge_keep_factor", 8.0)
bpy.ops.object.modifier_apply(modifier=m.name)
lo.vertex_groups.remove(lo.vertex_groups["_decimate"])
if KIND in ("vest", "coat") or (KIND == "shirt" and R.get("hem_points")):
    bmq = bmesh.new()
    bmq.from_mesh(lo.data)
    bv = [v for v in bmq.verts if any(e.is_boundary for e in v.link_edges)]
    E0 = {v: (np.array(v.co), np.array(v.normal)) for v in bv}
    kinds = {}
    for v in bv:
        r0 = resid(np.array(v.co))
        kinds[v] = min(r0, key=lambda kk: abs(r0[kk]))
        if abs(r0[kinds[v]]) > (0.06 if kinds[v] == "hem" else 0.03):   # an edge made by a plane (wrists): leave it
            kinds[v] = "plane"
    for it in range(R.get("lo_edge_iter", 12)):
        for v in bv:
            c = np.array(v.co)
            k_ = kinds[v]
            if k_ == "hem":
                c[2] = hem_z(c[0], c[1], c[2])
            elif k_ == "v":
                c[0] = np.sign(c[0] or 1) * v_w(c[2])
            elif k_ == "neck":
                c[2] = Z_NECK
            elif k_ == "plane":
                continue
            # (armhole: smoothing only -- the offset garment sits outside the body sphere)
            v.co = Vector(c)
        newc = {}
        for v in bv:
            nb = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
            if len(nb) == 2 and kinds[nb[0]] == kinds[v] == kinds[nb[1]]:
                newc[v] = v.co * 0.4 + (nb[0].co + nb[1].co) * 0.3
        for v, c in newc.items():
            v.co = c
    if KIND == "vest":
        # the shoulder straps end on the neck plane: the offset pushed their edge up into teeth
        top = [v for v in bmq.verts if v.co.z > Z_NECK - 0.015]
        for v in top:
            if v.co.z > Z_NECK:
                v.co.z = Z_NECK
        tb = [v for v in bv if v.co.z > Z_NECK - 0.004]
        for _ in range(6):
            newc = {}
            for v in tb:
                nb = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
                if len(nb) == 2:
                    c_ = v.co * 0.4 + (nb[0].co + nb[1].co) * 0.3
                    c_.z = Z_NECK
                    newc[v] = c_
            for v, c_ in newc.items():
                v.co = c_
    bmq.to_mesh(lo.data)
    bmq.free()
    lo.data.update()
    log("lo edge re-snapped", len(bv))
bm = bmesh.new()
bm.from_mesh(lo.data)
bmesh.ops.triangulate(bm, faces=bm.faces[:])
bm.to_mesh(lo.data)
bm.free()
if KIND == "vest":
    # clean side seam between the front fabric and the linen back: split the game mesh exactly where
    # y - centre(z) changes sign; faces then take a material by side (see the lining below)
    bmq = bmesh.new()
    bmq.from_mesh(lo.data)
    sv = {v: float(v.co.y - ycf(v.co.z)) for v in bmq.verts}
    newv = set()
    for e in [e for e in bmq.edges if sv[e.verts[0]] * sv[e.verts[1]] < 0]:
        a_, b_ = e.verts
        ne, nv = bmesh.utils.edge_split(e, a_, sv[a_] / (sv[a_] - sv[b_]))
        sv[nv] = 0.0
        newv.add(nv)
    for f in list(bmq.faces):
        cut = [v for v in f.verts if v in newv]
        if len(cut) == 2:
            bmesh.ops.connect_verts(bmq, verts=cut)
    bmesh.ops.triangulate(bmq, faces=[f for f in bmq.faces if len(f.verts) > 3])
    bmq.to_mesh(lo.data)
    bmq.free()
    lo.data.update()
    log("side seam split", len(newv))
lo.name = lo.data.name = f"{PIECE}_shell"
bpy.ops.object.shade_smooth()
tris = sum(len(p.vertices) - 2 for p in lo.data.polygons)
log("lo", tris, "tris")
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.006, area_weight=0.0)
bpy.ops.uv.pack_islands(margin=0.006, rotate=True)
bpy.ops.object.mode_set(mode="OBJECT")

# ---- 4. bake: tweed detail (emission) and normal, hi -> lo
sc = bpy.context.scene
sc.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
for dev in ("OPTIX", "CUDA"):
    try:
        prefs.compute_device_type = dev
        prefs.get_devices()
        if any(d_.type == dev for d_ in prefs.devices):
            for d_ in prefs.devices:
                d_.use = d_.type == dev
            sc.cycles.device = "GPU"
            break
    except TypeError:
        continue
sc.cycles.samples = 8
hm = bpy.data.materials.new(f"{PIECE}_tweed_src")
hm.use_nodes = True
nt = hm.node_tree
for n_ in list(nt.nodes):
    nt.nodes.remove(n_)
outn = nt.nodes.new("ShaderNodeOutputMaterial")
emi = nt.nodes.new("ShaderNodeEmission")
tc = nt.nodes.new("ShaderNodeTexCoord")
n1 = nt.nodes.new("ShaderNodeTexNoise")          # mottle
n1.inputs["Scale"].default_value = R.get("mottle_scale", 60.0)
n1.inputs["Detail"].default_value = 6.0
n2 = nt.nodes.new("ShaderNodeTexWave")           # twill: fine diagonal ribs
n2.wave_type = "BANDS"
n2.bands_direction = "DIAGONAL"
n2.inputs["Scale"].default_value = R.get("twill_scale", 260.0)
n2.inputs["Distortion"].default_value = 1.5
n3 = nt.nodes.new("ShaderNodeTexNoise")          # flecks
n3.inputs["Scale"].default_value = 420.0
for nn in (n1, n2, n3):
    nt.links.new(tc.outputs["Object"], nn.inputs["Vector"])
ca = nt.nodes.new("ShaderNodeVertexColor")
ca.layer_name = "occ"
math_nodes = []


def mnode(op, a, b, clamp=False):
    n_ = nt.nodes.new("ShaderNodeMath")
    n_.operation = op
    n_.use_clamp = clamp
    for k, v in enumerate((a, b)):
        if isinstance(v, (int, float)):
            n_.inputs[k].default_value = v
        else:
            nt.links.new(v, n_.inputs[k])
    return n_.outputs[0]


# detail = 0.86 + 0.10 * (mottle - .5) + 0.05 * (twill - .5) + 0.06 * (fleck > .62) ; x occ
d = mnode("ADD", mnode("MULTIPLY", mnode("SUBTRACT", n1.outputs["Fac"], 0.5), R.get("mottle", 0.22)), 0.84)
d = mnode("ADD", d, mnode("MULTIPLY", mnode("SUBTRACT", n2.outputs["Fac"], 0.5), R.get("twill", 0.09)))
d = mnode("ADD", d, mnode("MULTIPLY", mnode("GREATER_THAN", n3.outputs["Fac"], 0.62), 0.06))
sep = nt.nodes.new("ShaderNodeSeparateColor")
nt.links.new(ca.outputs["Color"], sep.inputs["Color"])
d = mnode("MULTIPLY", d, sep.outputs["Red"], clamp=True)
nt.links.new(d, emi.inputs["Color"])
nt.links.new(emi.outputs[0], outn.inputs["Surface"])
hi.data.materials.clear()
hi.data.materials.append(hm)

mat = bpy.data.materials.new(f"{CHAR}_{PIECE}")
mat.use_nodes = True
lo.data.materials.clear()
lo.data.materials.append(mat)
lnt = mat.node_tree
bsdf = lnt.nodes["Principled BSDF"]
imgs = {}
sc.render.bake.use_selected_to_active = True
sc.render.bake.cage_extrusion = R.get("bake_cage", 0.006)
sc.render.bake.max_ray_distance = R.get("bake_ray", 0.02)
sc.render.bake.margin = 8
for name, btype, cs in (("detail", "EMIT", "sRGB"), ("normal", "NORMAL", "Non-Color")):
    img = bpy.data.images.new(f"{CHAR}_{PIECE}_{name}", TEX, TEX, alpha=False)
    img.colorspace_settings.name = cs
    node = lnt.nodes.new("ShaderNodeTexImage")
    node.image = img
    lnt.nodes.active = node
    only_select(hi, lo)
    bpy.ops.object.bake(type=btype, **({"normal_space": "TANGENT"} if btype == "NORMAL" else {}))
    img.pack()
    imgs[name] = (img, node)
    log("baked", name)
dimg = np.array(imgs["detail"][0].pixels[:]).reshape(TEX, TEX, 4)[..., :3]
mean_detail = float(np.mean(dimg[dimg.sum(2) > 0.05]))               # (sRGB-encoded mean)
mix = lnt.nodes.new("ShaderNodeMix")
mix.data_type = "RGBA"
mix.blend_type = "MULTIPLY"
mix.inputs["Factor"].default_value = 1.0
lnt.links.new(imgs["detail"][1].outputs["Color"], mix.inputs["A"])
lnt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
nmap = lnt.nodes.new("ShaderNodeNormalMap")
lnt.links.new(imgs["normal"][1].outputs["Color"], nmap.inputs["Color"])
lnt.links.new(nmap.outputs[0], bsdf.inputs["Normal"])
bsdf.inputs["Roughness"].default_value = R.get("roughness", 0.85)
mat.use_backface_culling = False                  # doubleSided: the inside of the waistband / cuffs shows cloth
mlin = float(srgb_lin([mean_detail * 255] * 3)[0])


def factor_for(rgb):
    """Linear baseColorFactor so the garment's mean colour = rgb (sRGB 0-255) over the detail texture."""
    return tuple(np.clip(srgb_lin(rgb) / max(mlin, 1e-6), 0, 1)) + (1.0,)


COLORS = R.get("colors", {"tan": [165, 133, 105]})
base_name = next(iter(COLORS))
mix.inputs["B"].default_value = factor_for(COLORS[base_name])
if KIND == "vest":
    # the back panel is linen: a second material (glTF primitive) with the same textures and its own colour
    lin = mat.copy()
    lin.name = f"{CHAR}_{PIECE}_lining"
    lin.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = R.get("lining_roughness", 0.7)
    for n_ in lin.node_tree.nodes:
        if n_.type == "MIX":
            n_.inputs["B"].default_value = factor_for(R.get("lining_color", [205, 192, 168]))
    lo.data.materials.append(lin)
    for f_ in lo.data.polygons:
        c_ = np.array(f_.center)
        f_.material_index = 1 if (c_[1] > ycf(c_[2])) else 0
    log("lining faces", sum(1 for f_ in lo.data.polygons if f_.material_index == 1))

if R.get("thickness", 0):
    # the rim faces reuse the UVs of the edge they come from (the edge colour), so no bake is needed
    bmq = bmesh.new()
    bmq.from_mesh(lo.data)
    uvl = bmq.loops.layers.uv.active
    bedges = [e for e in bmq.edges if e.is_boundary]
    vuv = {}
    for e in bedges:
        for v in e.verts:
            if v not in vuv:
                lp_ = next(l_ for l_ in v.link_loops)
                vuv[v] = lp_[uvl].uv.copy()
    vn = {v: v.normal.copy() for e in bedges for v in e.verts}
    ext = bmesh.ops.extrude_edge_only(bmq, edges=bedges)
    nv = [g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)]
    src_of = {}
    for g in ext["geom"]:
        if isinstance(g, bmesh.types.BMEdge):
            pass
    # map each new vert to its source by position
    for v in nv:
        src = min(vn, key=lambda s_: (s_.co - v.co).length_squared)
        src_of[v] = src
        v.co = v.co - vn[src] * R["thickness"]
    for f in bmq.faces:
        if any(v in src_of for v in f.verts):
            for l_ in f.loops:
                s_ = src_of.get(l_.vert, l_.vert)
                if s_ in vuv:
                    l_[uvl].uv = vuv[s_]
    bmesh.ops.recalc_face_normals(bmq, faces=[f for f in bmq.faces if any(v in src_of for v in f.verts)])
    bmq.to_mesh(lo.data)
    bmq.free()
    lo.data.update()
    log("rim", len(nv), "verts, thickness mm", R["thickness"] * 1000)
    tris = sum(len(p_.vertices) - 2 for p_ in lo.data.polygons)

# ---- 5. export + report
OUT.mkdir(exist_ok=True)
vg_names = [g.name for g in lo.vertex_groups]
WL = np.zeros((len(lo.data.vertices), len(vg_names)), np.float32)
for v in lo.data.vertices:
    for g in v.groups:
        WL[v.index, g.group] = g.weight
for src, dst in R.get("weight_merge", {"Tail": "Hips"}).items():   # the tail is hidden under the garment
    if src in vg_names and dst in vg_names:
        WL[:, vg_names.index(dst)] += WL[:, vg_names.index(src)]
        WL[:, vg_names.index(src)] = 0
WL /= np.maximum(WL.sum(1, keepdims=True), 1e-9)
np.savez_compressed(OUT / f"{PIECE}_covers.npz", pos=COVERS_POS.astype(np.float32))
np.savez_compressed(OUT / f"{PIECE}_weights.npz", pos=np.array([v.co[:] for v in lo.data.vertices], np.float32),
                    W=WL, names=np.array(vg_names))
for o in (hi,):
    o.hide_render = True
only_select(lo)
bpy.ops.export_scene.gltf(filepath=str(OUT / f"{PIECE}.glb"), use_selection=True, export_format="GLB", export_tangents=True)
report = {"char": CHAR, "piece": PIECE, "source": "make_garment.py (designed)", "tris": tris,
          "z_top_bot": [Z_TOP, Z_BOT],
          "weights": f"{PIECE}_weights.npz",
          "tuck": R.get("tuck"),
          "covers_file": f"{PIECE}_covers.npz",
          "weight_smooth": R.get("weight_smooth", 20),
          "covers": {"z_top": Z_TOP, "rise": RISE, "y0": Y0, "z_bot": Z_BOT, "margin": R.get("cover_margin", 0.012)}, "ease_mm_p10_50_90": np.round(np.percentile(ease, [10, 50, 90]) * 1000, 1).tolist(),
          "detail_mean_srgb": round(mean_detail, 3), "colors": COLORS, "base_color": base_name,
          "lining_color": R.get("lining_color") if KIND == "vest" else None,
          "base_color_factor": [round(c, 4) for c in factor_for(COLORS[base_name])]}
(OUT / f"{PIECE}.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
print("SHELL", json.dumps(report))

# ---- renders: per colour row: garment alone x4, on green body x4
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = RES
sc.view_settings.view_transform = "Standard"
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.92, 0.92, 0.92, 1)
sc.world = w
for i, (r_, e_) in enumerate([((50, 0, 30), 3.0), ((60, 0, 200), 1.5)]):
    L = bpy.data.lights.new(f"l{i}", "SUN")
    L.energy = e_
    lob = bpy.data.objects.new(f"l{i}", L)
    lob.rotation_euler = Euler([math.radians(a) for a in r_])
    sc.collection.objects.link(lob)
cam = bpy.data.cameras.new("cam")
cam.type = "ORTHO"
co = bpy.data.objects.new("cam", cam)
sc.collection.objects.link(co)
sc.camera = co
bm = bmesh.new()
bm.from_mesh(body.data)
bm.verts.ensure_lookup_table()
bmesh.ops.delete(bm, geom=[bm.verts[i] for i in np.flatnonzero(is_tail)], context="VERTS")
bm.to_mesh(body.data)
bm.free()
green = bpy.data.materials.new("green")
green.use_nodes = True
green.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.1, 0.9, 0.2, 1)
body.data.materials.clear()
body.data.materials.append(green)
reg_b = [o for o in bpy.data.objects if o.name.endswith("_region")]
SP = np.array([v.co[:] for v in lo.data.vertices])
lo3, hi3 = SP.min(0), SP.max(0)
ctr = (lo3 + hi3) / 2
size = max(hi3[2] - lo3[2], hi3[0] - lo3[0]) * 1.12
tmp = RENDERS / "_tmp"
tmp.mkdir(parents=True, exist_ok=True)
rows = []
for cname, rgb in COLORS.items():
    mix.inputs["B"].default_value = factor_for(rgb)
    for show_body in (False, True):
        body.hide_render = not show_body
        row = []
        for j, yaw in enumerate((0, 90, 180, 35)):
            yy = math.radians(yaw)
            cam.ortho_scale = size
            c = Vector(ctr)
            co.location = c + Vector((5 * math.sin(yy), -5 * math.cos(yy), 0))
            co.rotation_euler = (c - co.location).to_track_quat("-Z", "Y").to_euler()
            sc.render.filepath = str(tmp / f"g_{j}.png")
            bpy.ops.render.render(write_still=True)
            im = bpy.data.images.load(sc.render.filepath)
            row.append(np.array(im.pixels[:]).reshape(RES, RES, 4)[::-1, :, :3])
            bpy.data.images.remove(im)
        rows.append(np.concatenate(row, 1))
mix.inputs["B"].default_value = factor_for(COLORS[base_name])
sheet = np.concatenate(rows, 0)
h_, w_, _ = sheet.shape
im = bpy.data.images.new("sheet", w_, h_)
im.pixels = np.concatenate([sheet[::-1], np.ones((h_, w_, 1))], -1).ravel().tolist()
im.filepath_raw = str(RENDERS / f"{CHAR}_garment_{PIECE}.png")
im.file_format = "PNG"
im.save()
log("render", im.filepath_raw)
