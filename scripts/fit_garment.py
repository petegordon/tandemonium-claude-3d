"""Fit generated garments (one Pixal3D model per garment) onto the male goose's base body -> dress_goose shells.

  blender -b --factory-startup --python scripts/fit_garment.py -- --char outfit_male_victorian [--pieces coat,shirt]

Config: chars/<char>.json "fit" {piece: {...}}; piece = the shell name dress_goose.py knows (hat, bowtie, shirt,
waistcoat, coat, gloves, breeches, boots). Source out/<char>/<src>/candidate_s42.glb, facing from its review
(renders/mvic_<src>_s42.json "yaw_steps"); size / place target: the outfit_male shell of the same piece
(out/outfit_male-goose/shells/<target>.glb, already on the base body).

1. orient, weld (generated meshes are split along UV seams), "drop_grey" (texels of the reference's grey
   mannequin), decimate to "tris" (collapse, UVs + texture kept);
2. uniform scale by "scale_by" -- width (x extent x "width_factor"), height, topband (x extent of the top 12%),
   sleeve (outer shoulder -> cuff = "sleeve_len" m: the sheet draws cuffs at the wrists), length (glove long
   axis) -- then "anchor" (top / bottom / front) to the target's box;
3. "wrap": profile remap onto the body. The body is split by its skin weights into torso (Hips/Spine/Neck),
   arms and legs. Torso: per height, rays from the body's centre line give the body radius r_b(z, angle); rays
   from the garment's centre line give the garment's INNER wall r_in(z, angle) (first hit, so the generated
   double-walled cloth reads right; open fronts are filled across angles). A torso vertex at (z, angle, r) goes to
   r_b + ease + (r - r_in): the inner wall lies on the body with "ease", the cloth keeps its thickness. Below the
   body's torso (coat tails) it keeps its own flare from the last body level. Limbs ("limbs": arms / legs): the same
   remap about the shoulder -> cuff (hip -> cuff) axis of the garment onto the goose's arm (leg), length by
   "limb_end" ([joint, offset m]: the cuff lands there), blended in over the first part of the limb;
   "loose" (0..1) keeps that fraction of the garment's own extra width over its tightest angle (puffed sleeves);
4. rigid pieces (hat, bowtie, gloves, boots) are only placed: "pair" (boots) fits each half to the target's half
   box (per axis); "glove": long axis onto the left hand bone, back of the hand outward, mirrored copy on the right;
   "push" ease: verts inside the body go out (boots, gloves);
5. writes out/<char>-goose/shells/<piece>.glb + .json and renders/<char>_fit.png (body + all shells, 4 views).
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_victorian")
CFG = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
FIT = CFG["fit"]
ONLY = opt("--pieces", "").split(",") if "--pieces" in argv else list(FIT)
SRC = ROOT / "out" / CHAR
OLD = ROOT / "out" / "outfit_male-goose" / "shells"
DST = ROOT / "out" / f"{CHAR}-goose" / "shells"
DST.mkdir(parents=True, exist_ok=True)
NA = 72                                   # angle bins
DZ = 0.01                                 # torso height step (m)

bpy.ops.wm.open_mainfile(filepath=str(ROOT / "out" / "base-goose" / "base_goose.blend"))
for o in list(bpy.data.objects):
    if o.type == "MESH" and o.name != "base_goose_game":
        bpy.data.objects.remove(o)
body = bpy.data.objects["base_goose_game"]
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
J = {b.name: np.array((rig.matrix_world @ b.head_local)[:]) for b in rig.data.bones}
JT = {b.name: np.array((rig.matrix_world @ b.tail_local)[:]) for b in rig.data.bones}


# ---- body parts by skin weight -----------------------------------------------------------------------------
def part_of(name):
    if any(k in name for k in ("Arm", "Hand", "Shoulder")):
        return ("L" if name.startswith("Left") else "R") + "arm"
    if any(k in name for k in ("UpLeg", "Leg", "Foot", "ToeBase")):
        return ("L" if name.startswith("Left") else "R") + "leg"
    if name in ("Hips", "Spine", "Spine1", "Spine2", "Neck", "Neck1", "Neck2", "Neck3", "Tail"):
        return "torso"
    return "head"


BV = np.array([v.co[:] for v in body.data.vertices])
gname = {g.index: g.name for g in body.vertex_groups}
vpart = []
for v in body.data.vertices:
    acc = {}
    for g in v.groups:
        p = part_of(gname[g.group])
        acc[p] = acc.get(p, 0) + g.weight
    vpart.append(max(acc, key=acc.get) if acc else "torso")
PART_BVH = {}
for part in ("torso", "Larm", "Rarm", "Lleg", "Rleg"):
    faces = [tuple(p.vertices) for p in body.data.polygons
             if sum(vpart[i] == part for i in p.vertices) * 2 > len(p.vertices)]
    PART_BVH[part] = BVHTree.FromPolygons([Vector(v) for v in BV], faces)
BODY = BVHTree.FromPolygons([Vector(v) for v in BV], [tuple(p.vertices) for p in body.data.polygons])


# ---- mesh helpers ------------------------------------------------------------------------------------------
def import_glb(path, name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for o in new:
        if o != ob and o.name in bpy.data.objects:
            bpy.data.objects.remove(o)
    ob.name = name
    return ob


def getV(o):
    a = np.empty(len(o.data.vertices) * 3)
    o.data.vertices.foreach_get("co", a)
    return a.reshape(-1, 3)


def setV(o, V):
    o.data.vertices.foreach_set("co", np.asarray(V, float).ravel())
    o.data.update()


def bvh_of(o):
    return BVHTree.FromPolygons([Vector(v) for v in getV(o)], [tuple(p.vertices) for p in o.data.polygons])


def weld(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.to_mesh(o.data)
    bm.free()


def tris_of(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def decimate(o, tris):
    for _ in range(4):
        n = tris_of(o)
        if n <= tris * 1.05:
            break
        m = o.modifiers.new("dec", "DECIMATE")
        m.ratio = max(0.05, tris / n)
        m.use_collapse_triangulate = True
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.modifier_apply(modifier=m.name)
    return tris_of(o)


def base_image(o):
    for slot in o.material_slots:
        m = slot.material
        if m and m.use_nodes:
            for n in m.node_tree.nodes:
                if n.type == "BSDF_PRINCIPLED" and n.inputs["Base Color"].links:
                    src = n.inputs["Base Color"].links[0].from_node
                    if src.type == "TEX_IMAGE" and src.image:
                        return src.image
    return None


def drop_grey(o):
    img = base_image(o)
    if img is None:
        return 0
    w, h = img.size
    px = np.array(img.pixels[:]).reshape(h, w, -1)[..., :3]
    bm = bmesh.new()
    bm.from_mesh(o.data)
    uv = bm.loops.layers.uv.active
    kill = []
    for f in bm.faces:
        u = sum(l[uv].uv.x for l in f.loops) / len(f.loops)
        v = sum(l[uv].uv.y for l in f.loops) / len(f.loops)
        c = px[min(h - 1, max(0, int(v * h))), min(w - 1, max(0, int((u % 1) * w)))]
        mx, mn = c.max(), c.min()
        if 0.25 < mx < 0.85 and (mx - mn) / max(mx, 1e-6) < 0.10:
            kill.append(f)
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    bm.to_mesh(o.data)
    bm.free()
    return len(kill)


def box(V):
    return V.min(0), V.max(0)


def topband_width(V):
    lo, hi = box(V)
    b = V[V[:, 2] > hi[2] - 0.12 * (hi[2] - lo[2])]
    return b[:, 0].max() - b[:, 0].min()


def cuff_of(V, sx, kind):
    xs = sx * V[:, 0]
    cand = (xs > 0.6 * xs.max()) if kind == "arms" else (xs > 0.0)
    h = V[:, 2].max() - V[:, 2].min()
    cuff = cand & (V[:, 2] < V[cand, 2].min() + 0.035 * h)
    return V[cuff].mean(0)


def sleeve_len(V):
    out = []
    for sx in (1, -1):
        C = cuff_of(V, sx, "arms")
        top = V[:, 2] > V[:, 2].max() - 0.2 * (V[:, 2].max() - C[2])
        S = V[top][np.argmax(sx * V[top, 0])]
        out.append(np.linalg.norm(C - S))
    return float(np.mean(out))


def fill_circular(a):
    """NaN gaps in a circular profile -> linear interpolation around the circle."""
    ok = ~np.isnan(a)
    if ok.sum() == 0:
        return a
    idx = np.arange(len(a))
    x = np.concatenate([idx[ok] - len(a), idx[ok], idx[ok] + len(a)])
    y = np.tile(a[ok], 3)
    return np.interp(idx, x, y)


def fill_rows(P):
    """Rows that are all NaN take the nearest valid row."""
    good = [i for i in range(len(P)) if not np.isnan(P[i]).all()]
    for i in range(len(P)):
        if np.isnan(P[i]).all() and good:
            P[i] = P[min(good, key=lambda g: abs(g - i))]
    return P


ANG = np.arange(NA) * 2 * math.pi / NA


def ray_profile(bvh, origin, e1, e2, rmax):
    """Distance of the first hit along each angle in the plane (e1, e2) from origin (NaN = miss)."""
    out = np.full(NA, np.nan)
    o = Vector(origin)
    for k, a in enumerate(ANG):
        d = Vector(math.cos(a) * e1 + math.sin(a) * e2)
        hit, _, _, dist = bvh.ray_cast(o, d, rmax)
        if hit is not None:
            out[k] = dist
    return out


def interp_prof(P, rows, angs):
    """Bilinear lookup in a (rows x NA) profile at fractional row indices and angles."""
    rows = np.clip(rows, 0, len(P) - 1)
    r0 = np.floor(rows).astype(int)
    r1 = np.minimum(r0 + 1, len(P) - 1)
    fr = rows - r0
    a = (angs % (2 * math.pi)) / (2 * math.pi) * NA
    a0 = np.floor(a).astype(int) % NA
    a1 = (a0 + 1) % NA
    fa = a - np.floor(a)
    top = P[r0, a0] * (1 - fa) + P[r0, a1] * fa
    bot = P[r1, a0] * (1 - fa) + P[r1, a1] * fa
    return top * (1 - fr) + bot * fr


# ---- torso wrap ----------------------------------------------------------------------------------------------
EX, EY = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])


def centre_y(bvh, z, y_guess, half=0.6):
    """Mid of the front and back walls on the x = 0 line at height z (from a point inside)."""
    o = Vector((0, y_guess, z))
    f = bvh.ray_cast(o, Vector((0, -1, 0)), half)
    b = bvh.ray_cast(o, Vector((0, 1, 0)), half)
    if f[0] is None or b[0] is None:
        return None
    return (f[0].y + b[0].y) / 2


def torso_profiles(bvh, zs, y0):
    cy = np.full(len(zs), np.nan)
    P = np.full((len(zs), NA), np.nan)
    for i, z in enumerate(zs):
        c = centre_y(bvh, z, y0)
        if c is None:
            continue
        cy[i] = c
        P[i] = ray_profile(bvh, (0, c, z), EX, EY, 0.8)
    return cy, P


def wrap_torso(V, ease, zs_b, cyb, Pb, bvh_g, rep):
    lo, hi = box(V)
    zs = np.arange(lo[2], hi[2] + DZ, DZ)
    cyg, Pg = torso_profiles(bvh_g, zs, (lo[1] + hi[1]) / 2)
    ok = ~np.isnan(cyg)
    cyg = np.interp(np.arange(len(zs)), np.where(ok)[0], cyg[ok]) if ok.any() else np.full(len(zs), (lo[1] + hi[1]) / 2)
    Pg = fill_rows(np.array([fill_circular(r) for r in Pg]))
    rg = (V[:, 2] - zs[0]) / DZ
    cg = np.interp(rg, np.arange(len(zs)), cyg)
    th = np.arctan2(V[:, 1] - cg, V[:, 0])
    r = np.hypot(V[:, 0], V[:, 1] - cg)
    r_in = interp_prof(Pg, rg, th)
    thick = r - r_in
    zb_lo = zs_b[0]
    rb_rows = (np.maximum(V[:, 2], zb_lo) - zb_lo) / DZ
    r_b = interp_prof(Pb, rb_rows, th)
    cb = np.interp(rb_rows, np.arange(len(zs_b)), cyb)
    below = V[:, 2] < zb_lo                                    # under the body's torso: keep the garment's own flare
    if below.any():
        r_in_at = interp_prof(Pg, np.full(below.sum(), (zb_lo - zs[0]) / DZ), th[below])
        thick[below] = r[below] - r_in_at
    r_new = r_b + ease + thick
    out = V.copy()
    out[:, 0] = r_new * np.cos(th)
    out[:, 1] = cb + r_new * np.sin(th)
    rep["torso_thick_mm_p10_50_90"] = np.percentile(thick * 1000, [10, 50, 90]).round(1).tolist()
    return out


# ---- limb wrap -------------------------------------------------------------------------------------------------
def frame(a):
    e1 = np.array([0, -1.0, 0]) - a * (-a[1])               # forward, perpendicular to the axis
    e1 /= np.linalg.norm(e1)
    return e1, np.cross(a, e1)


def limb_profiles(bvh, P0, a, L, ts, rmax=0.25):
    e1, e2 = frame(a)
    Pr = np.full((len(ts), NA), np.nan)
    for i, t in enumerate(ts):
        Pr[i] = ray_profile(bvh, P0 + a * t * L, e1, e2, rmax)
    return Pr


def wrap_limb(V, side, kind, c, ease, bvh_g, rep):
    sx = 1 if side == "Left" else -1
    part = ("L" if side == "Left" else "R") + ("arm" if kind == "arms" else "leg")
    if kind == "arms":
        Pb0 = J[f"{side}Arm"]
    else:
        Pb0 = J[f"{side}UpLeg"]
    jn, off = c.get("limb_end", ["Hand", 0.0] if kind == "arms" else ["Leg", 0.08])
    end_dir = (J[f"{side}Hand"] - Pb0) if kind == "arms" else (J[f"{side}Foot"] - Pb0)
    ab = end_dir / np.linalg.norm(end_dir)
    Lb = (J[f"{side}{jn}"] - Pb0) @ ab + off
    C = cuff_of(V, sx, kind)
    Pg0 = Pb0.copy()                                         # the torso is already on the body: same pivot
    ag = C - Pg0
    Lg = np.linalg.norm(ag)
    ag /= Lg
    ts = np.linspace(0, 1.15, 47)
    Pg = limb_profiles(bvh_g, Pg0, ag, Lg, ts)
    Pb = limb_profiles(PART_BVH[part], Pb0, ab, Lb, ts)
    Pg = fill_rows(np.array([fill_circular(r) for r in Pg]))
    Pb = fill_rows(np.array([fill_circular(r) for r in Pb]))
    e1g, e2g = frame(ag)
    e1b, e2b = frame(ab)
    rel = V - Pg0
    t = rel @ ag / Lg
    rad = rel - np.outer(t * Lg, ag)
    r = np.linalg.norm(rad, axis=1)
    phi = np.arctan2(rad @ e2g, rad @ e1g)
    rows = t / 1.15 * (len(ts) - 1)
    r_in = interp_prof(Pg, rows, phi)
    r_b = interp_prof(Pb, rows, phi)
    loose = c.get("loose", 0.0)
    extra = loose * np.maximum(0, r_in - np.nanmin(Pg, axis=1)[np.clip(np.round(rows).astype(int), 0, len(ts) - 1)])
    thick = r - r_in
    member = (t > 0.0) & (t < 1.2) & (thick < 0.03) & (sx * V[:, 0] > 0)
    w = np.clip((t - c.get("blend", [0.05, 0.3])[0]) / (c.get("blend", [0.05, 0.3])[1] - c.get("blend", [0.05, 0.3])[0]), 0, 1) * member
    r_new = r_b + ease + extra + thick
    dst = Pb0 + np.outer(t * Lb, ab) + (r_new * np.cos(phi))[:, None] * e1b + (r_new * np.sin(phi))[:, None] * e2b
    out = V + w[:, None] * (dst - V)
    rep.setdefault("limbs", []).append({"side": side, "garment_len": round(float(Lg), 3), "body_len": round(float(Lb), 3),
                                        "verts": int((w > 0).sum())})
    return out


def push_out(V, ease):
    n_ = 0
    for i, v in enumerate(V):
        loc, nrm, _, d = BODY.find_nearest(Vector(v), 0.1)
        if loc is not None and (Vector(v) - loc).dot(nrm) < ease:
            V[i] = (loc + nrm * ease)[:]
            n_ += 1
    return V, n_


def export(o, piece, meta):
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.export_scene.gltf(filepath=str(DST / f"{piece}.glb"), export_format="GLB", use_selection=True,
                              export_materials="EXPORT", export_yup=True)
    (DST / f"{piece}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")


# body torso profile, once
ZS_B = np.arange(0.62, 1.40, DZ)
CYB, PB = torso_profiles(PART_BVH["torso"], ZS_B, 0.02)
okb = ~np.isnan(CYB)
CYB = np.interp(np.arange(len(ZS_B)), np.where(okb)[0], CYB[okb])
PB = fill_rows(np.array([fill_circular(r) for r in PB]))
first = int(np.argmax(okb))
ZS_B, CYB, PB = ZS_B[first:], CYB[first:], PB[first:]
print("BODY torso z", round(ZS_B[0], 2), "-", round(ZS_B[-1], 2))

fitted, report = {}, {}
for piece, c in FIT.items():
    if piece not in ONLY:
        if (DST / f"{piece}.glb").exists():
            fitted[piece] = import_glb(DST / f"{piece}.glb", piece)
        continue
    rev = json.loads((ROOT / "renders" / f"mvic_{c['src']}_s42.json").read_text())
    g = import_glb(SRC / c["src"] / "candidate_s42.glb", piece)
    g.data.transform(Matrix.Rotation(math.radians(90 * rev["yaw_steps"]), 4, "Z"))
    weld(g)
    rep = {"src": c["src"], "tris_in": tris_of(g)}
    if c.get("drop_grey"):
        rep["grey_faces_dropped"] = drop_grey(g)
    rep["tris"] = decimate(g, c["tris"])
    t = import_glb(OLD / f"{c['target']}.glb", "_target")
    TV = getV(t)
    bpy.data.objects.remove(t)
    V = getV(g)
    tlo, thi = box(TV)
    glo, ghi = box(V)
    if c.get("glove"):
        m = V.mean(0)
        _, _, vt = np.linalg.svd(V - m, full_matrices=False)
        a = vt[0] if vt[0][2] < 0 else -vt[0]
        proj = (V - m) @ a
        s = c["length"] / (proj.max() - proj.min())
        V = (V - m) * s
        hd = JT["LeftHand"] - J["LeftHand"]
        hd /= np.linalg.norm(hd)
        R1 = Vector(a).rotation_difference(Vector(hd)).to_matrix()
        V = V @ np.array(R1).T
        back = np.array(R1 @ Vector((0, -1, 0)))
        out_dir = np.array([1.0, 0, 0]) - hd * hd[0]
        b_ = back - hd * (back @ hd)
        ang = math.atan2(np.cross(b_, out_dir) @ hd, b_ @ out_dir)
        V = V @ np.array(Matrix.Rotation(ang, 3, Vector(hd))).T
        tip = V[np.argmax(V @ hd)]
        V += JT["LeftHand"] + hd * 0.005 - tip
        V, rep["pushed"] = push_out(V, c.get("ease", 0.003))
        setV(g, V)
        gr = g.copy()
        gr.data = g.data.copy()
        bpy.context.scene.collection.objects.link(gr)
        setV(gr, V * np.array([-1, 1, 1]))
        gr.data.flip_normals()
        bpy.ops.object.select_all(action="DESELECT")
        gr.select_set(True)
        g.select_set(True)
        bpy.context.view_layer.objects.active = g
        bpy.ops.object.join()
        g = bpy.context.view_layer.objects.active
        g.name = piece
        rep["scale"] = round(float(s), 4)
    else:
        sb = c["scale_by"]
        if sb == "width":
            s = (thi[0] - tlo[0]) * c.get("width_factor", 1.0) / (ghi[0] - glo[0])
        elif sb == "height":
            s = (thi[2] - tlo[2]) / (ghi[2] - glo[2])
        elif sb == "sleeve":
            s = c["sleeve_len"] / sleeve_len(V)
        else:
            s = topband_width(TV) / topband_width(V)
        V = V * s
        glo, ghi = box(V)
        tc = (tlo + thi) / 2
        off = np.array([-(glo[0] + ghi[0]) / 2, tc[1] - (glo[1] + ghi[1]) / 2, 0.0])
        anc = c.get("anchor", "top")
        if anc == "top":
            off[2] = thi[2] - ghi[2] + c.get("raise", 0.0)
        elif anc == "bottom":
            off[2] = tlo[2] - glo[2]
        else:
            off[1] = tlo[1] - glo[1]
            off[2] = tc[2] - (glo[2] + ghi[2]) / 2
        V = V + off
        rep["scale"] = round(float(s), 4)
        if c.get("pair"):
            for sx in (1, -1):
                gm, tm = sx * V[:, 0] > 0, sx * TV[:, 0] > 0
                glo2, ghi2 = box(V[gm])
                tlo2, thi2 = box(TV[tm])
                k = (thi2 - tlo2) / (ghi2 - glo2)
                V[gm] = (V[gm] - glo2) * k + tlo2
            V, rep["pushed"] = push_out(V, c.get("ease", 0.004))
        if c.get("wrap"):
            setV(g, V)
            bvh_g = bvh_of(g)
            Vt = wrap_torso(V, c["ease"], ZS_B, CYB, PB, bvh_g, rep)
            for side in ("Left", "Right") if c.get("limbs") else ():
                Vt = wrap_limb(Vt if False else V, side, c["limbs"], c, c["ease"], bvh_g, rep) * 0 + \
                    Vt + (wrap_limb(V, side, c["limbs"], c, c["ease"], bvh_g, rep) - V) * 1.0 \
                    if False else Vt
            if c.get("limbs"):
                # each limb's map replaces the torso map where its weight is on
                for side in ("Left", "Right"):
                    Vl = wrap_limb(V, side, c["limbs"], c, c["ease"], bvh_g, rep)
                    moved = np.linalg.norm(Vl - V, axis=1) > 1e-9
                    Vt[moved] = Vl[moved] + (Vt[moved] - V[moved]) * 0.0
            V = Vt
        setV(g, V)
    fitted[piece] = g
    lo, hi = box(getV(g))
    rep["box"] = [lo.round(3).tolist(), hi.round(3).tolist()]
    export(g, piece, {"char": CHAR, "piece": piece, "source": f"fit_garment.py (Pixal3D s42: out/{CHAR}/{c['src']})",
                      "tris": rep["tris"], "fit": rep})
    report[piece] = rep
    print("FIT", piece, json.dumps(rep), flush=True)

# ---- sheet: base body + every fitted shell -----------------------------------------------------------------
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x, sc.render.resolution_y = 600, 900
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.86, 0.85, 0.83, 1)
sc.world = w
for i, (rot, e) in enumerate([((50, 0, 30), 3.0), ((60, 0, 200), 1.5)]):
    L = bpy.data.objects.new(f"l{i}", bpy.data.lights.new(f"l{i}", "SUN"))
    L.data.energy = e
    L.rotation_euler = [math.radians(a) for a in rot]
    sc.collection.objects.link(L)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = 1.95
sc.collection.objects.link(cam)
sc.camera = cam
tiles = []
for view, az in (("front", 0), ("left", 90), ("back", 180), ("q34", 35)):
    a = math.radians(az)
    d = Vector((math.sin(a), -math.cos(a), 0.12)).normalized()
    tgt = Vector((0, 0, 0.88))
    cam.location = tgt + d * 6
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    path = ROOT / "renders" / "_tmp" / f"{CHAR}_fit_{view}.png"
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    tiles.append(path)
img = [bpy.data.images.load(str(p)) for p in tiles]
W, H = 600, 900
sheet = np.zeros((H, W * len(img), 4))
for i, im in enumerate(img):
    sheet[:, i * W:(i + 1) * W] = np.array(im.pixels[:]).reshape(H, W, 4)
out = bpy.data.images.new("sheet", W * len(img), H)
out.pixels = sheet.ravel().tolist()
out.filepath_raw = str(ROOT / "renders" / f"{CHAR}_fit.png")
out.file_format = "PNG"
out.save()
(DST.parent / f"{CHAR}_fit.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
print("SHEET", ROOT / "renders" / f"{CHAR}_fit.png")
