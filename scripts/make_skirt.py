"""Designed Victorian skirt (female outfit): under-skirt + front apron + single bustle drape + two flounces.

  blender -b --factory-startup --python scripts/make_skirt.py -- --char outfit_female --piece skirt

A skirt does not follow the legs, so it is not cut from the body like make_garment.py's garments: it is a
lofted surface round the body axis -- radius r(azimuth, height) = the body radius at that height, held so it
never shrinks going down (the cloth falls straight past the legs), + clearance, bulked to the extracted
dress's smoothed silhouette (chars json "garment_design".skirt.guide) and the bustle drape. Game mesh = a
NA x NZ ring grid; detail mesh = the same loft at 6x resolution with the apron edge + swag folds, bustle
scallops + folds, gathered flounces, waistband. Skin weights from the nearest (non-arm) body vertex; hanging
cloth is weighted to cloth chains by dress_goose.py (LOOSE_PIECES). The body setup and the bake / export /
render stages are make_garment.py's own (executed from its source), so the skirt is a designed garment like
the others (one recolourable baseColorFactor, covers.npz, weights.npz).
"""
import math
import sys
from pathlib import Path

_SRC = (Path(__file__).parent / "make_garment.py").read_text(encoding="utf-8")
exec(_SRC[:_SRC.index("# ---- 1. region")])          # noqa: S102  args, body, bones, helpers

S = R
NA, NZ, UP = S.get("na", 64), S.get("nz", 38), S.get("hi_up", 6)
Z_TOP, Z_HEM = S["z_top"], S["z_hem"]
Z_BOT = Z_HEM
noarm = ~np.array([("Arm" in d) or ("Hand" in d) or ("Shoulder" in d) or (S.get("skip_tail") and d == "Tail") for d in dom])
bvh_body = BVHTree.FromPolygons([tuple(x) for x in BPv], [list(p.vertices) for p in body.data.polygons
                                                           if noarm[list(p.vertices)].all()])
core = BPv[noarm & (np.abs(BPv[:, 0]) < 0.16)]
ZS = np.linspace(Z_TOP, Z_HEM, NZ)
YC = np.array([(lambda nb: (nb[:, 1].min() + nb[:, 1].max()) / 2 if len(nb) else np.nan)(core[np.abs(core[:, 2] - z) < 0.015])
               for z in ZS])
YC = np.where(np.isnan(YC), np.nanmean(YC), YC)
for _ in range(10):
    YC[1:-1] = 0.25 * YC[:-2] + 0.5 * YC[1:-1] + 0.25 * YC[2:]
THS = np.linspace(0, 2 * math.pi, NA, endpoint=False)   # 0 = front (-Y), + = character left (+X)


def dirv(th):
    return np.array([math.sin(th), -math.cos(th), 0.0])


def radius_field(bvh, ths, zs, ycs):
    """Outer radius of a surface along rays from outside toward the axis (nan where missed)."""
    Rf = np.full((len(ths), len(zs)), np.nan)
    for i, th in enumerate(ths):
        d = dirv(th)
        for j, (z, yc) in enumerate(zip(zs, ycs)):
            c = np.array([0.0, yc, z])
            hit = bvh.ray_cast(Vector(c + d * 0.8), Vector(-d), 0.8)
            if hit[0] is not None:
                Rf[i, j] = np.linalg.norm((np.array(hit[0]) - c)[:2])
    return Rf


def smooth2(F, it, wrap=True):
    F = F.copy()
    for _ in range(it):
        F = 0.25 * np.roll(F, 1, 0) + 0.5 * F + 0.25 * np.roll(F, -1, 0)
        F[:, 1:-1] = 0.25 * F[:, :-2] + 0.5 * F[:, 1:-1] + 0.25 * F[:, 2:]
    return F


rb = radius_field(bvh_body, THS, ZS, YC)
rb = np.where(np.isnan(rb), 0.0, rb)
rb = np.maximum.accumulate(rb, axis=1)                 # hangs: never tucks in going down
clear = S.get("clear", 0.012)
r = smooth2(rb, 4) + clear
GUIDE_F = D / "pieces" / f"{S.get('guide') or 'dress'}.glb"
if S.get("guide") and GUIDE_F.exists():
    gp = next(o for o in load(GUIDE_F) if o.type == "MESH")
    only_select(gp)
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    rg = radius_field(BVHTree.FromObject(gp, bpy.context.evaluated_depsgraph_get()), THS, ZS, YC)
    bpy.data.objects.remove(gp)
else:                                  # (no guide: the profile alone shapes the skirt)
    rg = np.full((NA, NZ), np.nan)
okg = ~np.isnan(rg)
rg = np.where(okg, rg, 0.0)
rgs = smooth2(rg, S.get("guide_smooth", 14)) / np.maximum(smooth2(okg.astype(float), S.get("guide_smooth", 14)), 1e-3)
if S.get("use_guide", False):
    r = np.maximum(r, rgs * S.get("guide_scale", 1.0))
if S.get("profile"):
    # silhouette from the reference side / front / rear views: extra radius over the hanging body radius at
    # front / side / back control heights, blended round the body by azimuth (smooth, no shelf)
    PR = S["profile"]
    zc = np.array(PR["z"])
    def prof(key):
        return np.interp(-ZS, -zc, np.array(PR[key]))
    pf, ps, pb = prof("front"), prof("side"), prof("back")
    a_ = np.abs(((THS + math.pi) % (2 * math.pi)) - math.pi)          # 0 front .. pi back
    wf = np.clip(np.cos(a_), 0, 1) ** 2
    wb = np.clip(-np.cos(a_), 0, 1) ** 2
    ws = 1 - wf - wb
    extra = wf[:, None] * pf[None] + ws[:, None] * ps[None] + wb[:, None] * pb[None]
    r = smooth2(rb, 6) + clear + extra
log("radius mm body p50 / guide p50", round(float(np.median(rb)) * 1000), round(float(np.median(rgs)) * 1000))
TT, ZZ = np.meshgrid(THS, ZS, indexing="ij")
az = np.degrees((TT + math.pi) % (2 * math.pi) - math.pi)              # -180..180, 0 = front
# bustle drape: a single swelling over the back below the waist
B_ = S.get("bustle") or {"z": 0.8, "dz": 0.1, "daz": 60, "r": 0.0, "fold": 0.0, "n": 0}
bz = np.exp(-((ZZ - B_["z"]) / B_["dz"]) ** 2) * np.clip((Z_TOP - ZZ) / 0.05, 0, 1)
ba = np.exp(-((np.abs(az) - 180) / B_["daz"]) ** 2)
r = r + B_.get("r", 0.0) * bz * ba
# flounces: two tiers standing out a little from the skirt
F_ = S.get("flounce")
st = lambda z, z0: np.clip((z0 - z) / 0.015, 0, 1)  # noqa: E731
if F_:
    z1, z2 = Z_HEM + F_["h"], Z_HEM + 2 * F_["h"]
    r = r + F_["out"] * st(ZZ, z2) * 0.6 + F_["out"] * st(ZZ, z1) * 0.6
    if F_.get("geo_amp"):              # the gathered flounce in the silhouette too (game mesh), growing to the hem
        gz = np.clip((z2 - ZZ) / max(z2 - Z_HEM, 1e-3), 0, 1)
        r = r + F_["geo_amp"] * gz * np.sin(TT * F_.get("geo_n", 24))
# apron: front panel over the skirt down to a curved hem rising to the hips
A_ = S.get("apron")
if A_:
    zap = A_["z_front"] + (A_["z_side"] - A_["z_front"]) * np.clip(np.abs(az) / A_["az"], 0, 1) ** 2
    in_ap = (np.abs(az) < A_["az"]) & (ZZ > zap)
    r = r + A_["out"] * in_ap * np.clip((ZZ - zap) / 0.01, 0, 1)
# waist: snug onto the body at the top
wt = np.clip((Z_TOP - ZZ) / S.get("waist_blend", 0.08), 0, 1) ** 1.5
wt = wt * wt * (3 - 2 * wt)
r = (rb + S.get("waist_clear", 0.006)) * (1 - wt) + r * wt
if S.get("close_az"):                    # fill narrow inward dips round the body (the hidden tail root's notch at the
    k_ = int(S["close_az"])              # centre back): a closing (max then min over +-k azimuth columns) per row
    d_ = np.max([np.roll(r, s_, 0) for s_ in range(-k_, k_ + 1)], 0)
    r = np.maximum(r, np.min([np.roll(d_, s_, 0) for s_ in range(-k_, k_ + 1)], 0))
r = smooth2(r, S.get("final_smooth", 1))
TIERS = S.get("tiers", [])


def tier_fields(az_deg, zz):
    """Cascading bustle tiers (refs/v3 rear / side views): each tier flares out from its top to a
    scalloped lower edge, the next tier starts under it -> stepped overhangs instead of one bulge.
    Returns (extra radius, per-tier edge heights)."""
    add = np.zeros_like(zz)
    edges = []
    for tr in TIERS:
        wa = (np.abs(az_deg) > 180 - tr["span_deg"]).astype(float) if tr.get("uniform") else             np.exp(-((np.abs(az_deg) - 180) / tr["daz"]) ** 2)
        zbe = tr["z_bot"] + tr.get("v", 0.0) * (1 - np.abs(np.abs(az_deg) - 180) / 180) ** 0 * 0 +             tr.get("scallop", 0.02) * np.sin(np.radians(az_deg) * tr.get("n_sc", 3)) ** 2
        zbe = zbe - tr.get("v", 0.0) * np.exp(-((np.abs(az_deg) - 180) / (tr["daz"] * 0.6)) ** 2)   # dips at the centre back
        inside = (zz <= tr["z_top"]) & (zz >= zbe)
        u = np.clip((tr["z_top"] - zz) / np.maximum(tr["z_top"] - zbe, 1e-3), 0, 1)
        # soft swag: rounds over near the edge (the cloth turns under), not a flat shelf
        prof_ = u ** 1.2 - tr.get("roll", 0.35) * np.clip((u - 0.8) / 0.2, 0, 1) ** 2
        add = add + np.where(inside, tr["o_top"] + (tr["o_bot"] - tr["o_top"]) * prof_, 0.0) * wa
        edges.append((zbe, wa))
    return add, edges


for nm in S.get("under", []):           # tucked under these (bodice): stay inside them where they reach
    uo = next(o for o in load(OUT / f"{nm}.glb") if o.type == "MESH")
    ru = radius_field(BVHTree.FromObject(uo, bpy.context.evaluated_depsgraph_get()), THS, ZS, YC)
    bpy.data.objects.remove(uo)
    lim = np.where(np.isnan(ru), 9.0, ru - S.get("under_gap", 0.004))
    lim = np.minimum(lim, np.roll(lim, 1, 0)); lim = np.minimum(lim, np.roll(lim, -1, 0))
    r = np.minimum(r, np.maximum(lim, rb + 0.001))
    log("tucked under", nm, int((~np.isnan(ru)).sum()), "grid points")
for nm in S.get("over", []):            # worn over these (a gown over its bodice's hem): stay outside them where they reach
    uo = next(o for o in load(OUT / f"{nm}.glb") if o.type == "MESH")
    ru = radius_field(BVHTree.FromObject(uo, bpy.context.evaluated_depsgraph_get()), THS, ZS, YC)
    bpy.data.objects.remove(uo)
    lo_ = np.where(np.isnan(ru), 0.0, ru + S.get("over_gap", 0.005))
    lo_ = np.maximum(lo_, np.roll(lo_, 1, 0)); lo_ = np.maximum(lo_, np.roll(lo_, -1, 0))
    lo_ = np.maximum.accumulate(lo_, axis=1)          # (hangs: what clears the hem above stays out below)
    r = np.maximum(r, lo_)
    log("over", nm, int((~np.isnan(ru)).sum()), "grid points")
PL_ = S.get("pleats")
if PL_:
    ramp_ = np.clip((PL_.get("z_stitch", Z_TOP - 0.08) - ZZ) / PL_.get("open", 0.12), 0, 1) ** 0.8
    saw_ = (TT * PL_["n"] / (2 * math.pi) + PL_.get("phase", 0.0)) % 1.0
    if PL_.get("dir", 1) < 0:
        saw_ = 1.0 - saw_
    r = r + PL_["depth"] * ramp_ * (saw_ - 0.5)
    log("pleats", PL_["n"], "depth mm", PL_["depth"] * 1000)
# (tiers are separate panels, built after the hi skirt below)


def loft(ths, zs, Rg, ycs):
    P_ = np.zeros((len(ths), len(zs), 3))
    for i, th in enumerate(ths):
        d = dirv(th)
        P_[i] = np.stack([np.zeros(len(zs)), ycs, zs], 1) + d[None] * Rg[i][:, None]
    return P_


def open_remap(P_, ycs):
    """Opening: respace every row round the body from the front edge a(z) to 2 pi - a(z) (clean front edges, no
    stair steps); the radius at each new azimuth is the row's own, interpolated."""
    OP_ = S.get("opening")
    PN_ = S.get("panel")                # panel (an apron): every row spans only -a(z)..+a(z) across the front
    if not OP_ and not PN_:
        return P_
    na = P_.shape[0]
    if PN_:
        pz, pw = zip(*PN_["front"])
        Q = P_.copy()
        th0 = 2 * np.pi * np.arange(na) / na
        for j in range(P_.shape[1]):
            z_ = float(P_[0, j, 2])
            yc_ = float(ycs[j])
            rr = np.hypot(P_[:, j, 0], P_[:, j, 1] - yc_)
            a_ = math.radians(float(np.interp(z_, pz, pw)))
            thn = (-a_ + np.arange(na) * (2 * a_) / (na - 1)) % (2 * np.pi)
            rn = np.interp(thn, np.r_[th0, 2 * np.pi], np.r_[rr, rr[0]])
            Q[:, j, 0] = np.sin(thn) * rn
            Q[:, j, 1] = yc_ - np.cos(thn) * rn
        return Q
    fz, fw = zip(*OP_["front"])
    Q = P_.copy()
    th0 = 2 * np.pi * np.arange(na) / na
    for j in range(P_.shape[1]):
        z_ = float(P_[0, j, 2])
        yc_ = float(ycs[j])
        rr = np.hypot(P_[:, j, 0], P_[:, j, 1] - yc_)
        a_ = math.radians(float(np.interp(z_, fz, fw)))
        thn = a_ + th0 * (2 * np.pi - 2 * a_) / (2 * np.pi * (na - 1) / na)
        rn = np.interp(thn, np.r_[th0, 2 * np.pi], np.r_[rr, rr[0]])
        Q[:, j, 0] = np.sin(thn) * rn
        Q[:, j, 1] = yc_ - np.cos(thn) * rn
    return Q


def grid_mesh(name, P_, wrap=True):
    na, nz = P_.shape[:2]
    me = bpy.data.meshes.new(name)
    faces = []
    OP_ = S.get("opening")              # open front (coat skirts): no faces across the front; back vent left out
    VT = (OP_ or {}).get("vent")
    for i in range(na):
        i2 = (i + 1) % na
        if (OP_ or S.get("panel")) and i == na - 1:
            continue
        for j in range(nz - 1):
            if VT and abs((i + 0.5) / na - 0.5) * 360 < VT["half_az"] and                     float(P_[i, j, 2] + P_[i, j + 1, 2]) / 2 < VT["z_top"]:
                continue
            faces.append((i * nz + j, i * nz + j + 1, i2 * nz + j + 1, i2 * nz + j))
    me.from_pydata([tuple(p) for p in P_.reshape(-1, 3)], [], faces)
    me.validate()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


Plo = loft(THS, ZS, r, YC)
Plo = open_remap(Plo, YC)
lo = grid_mesh(f"{PIECE}_shell", Plo)
# hi: interpolated loft + detail displacement along the radial direction
THh = np.linspace(0, 2 * math.pi, NA * UP, endpoint=False)
ZSh = np.linspace(Z_TOP, Z_HEM, (NZ - 1) * UP + 1)


def interp(F, ths, zs):
    """Bilinear sample of a (NA, NZ) field (periodic in azimuth) at ths x zs."""
    fi = ths / (2 * math.pi) * NA
    fj = (Z_TOP - zs) / (Z_TOP - Z_HEM) * (NZ - 1)
    i0 = np.floor(fi).astype(int) % NA
    i1 = (i0 + 1) % NA
    wi = (fi - np.floor(fi))[:, None]
    j0 = np.clip(np.floor(fj).astype(int), 0, NZ - 2)
    wj = np.clip(fj - j0, 0, 1)[None, :]
    a = F[i0][:, j0] * (1 - wj) + F[i0][:, j0 + 1] * wj
    b = F[i1][:, j0] * (1 - wj) + F[i1][:, j0 + 1] * wj
    return a * (1 - wi) + b * wi


rh = interp(r, THh, ZSh)            # (tier steps at game-mesh resolution: the bake matches the silhouette)
ych = np.interp(-ZSh, -ZS, YC)
Th, Zh = np.meshgrid(THh, ZSh, indexing="ij")
azh = np.degrees((Th + math.pi) % (2 * math.pi) - math.pi)
taddh, tedges = tier_fields(azh, Zh)
disp = np.zeros_like(rh)
occm = np.ones_like(rh)


def groove(d, w, depth):
    return -depth * np.exp(-(d / w) ** 2)


arc = rh * 1.0
# waistband
disp += groove(np.abs(Zh - (Z_TOP - 0.02)), 0.0015, 0.0012)
# flounces: gathered (dense vertical ruffles growing toward each tier's lower edge), tier tops gathered
for zt in ((z2, z1) if F_ else ()):
    inb = (Zh < zt) & (Zh > zt - F_["h"])
    u = np.clip((zt - Zh) / F_["h"], 0, 1)
    # gathered ruffle: uneven folds (two frequencies, wandering phase) opening toward the tier's edge
    ph_ = Th * F_["n"] + 1.4 * np.sin(Th * 7 + zt * 40) + 0.8 * np.sin(Th * 17)
    am_ = 0.55 + 0.45 * np.sin(Th * 5 + zt * 9)
    disp += np.where(inb, F_["ruffle"] * (0.25 + 0.75 * u) * am_ * np.sin(ph_), 0.0)
    disp += groove(np.abs(Zh - zt), 0.0016, 0.0016) + groove(np.abs(Zh - (zt - 0.006)), 0.0008, 0.0005)
    occm = np.where(np.abs(Zh - zt) < 0.004, 0.75, occm)
disp += groove(np.abs(Zh - (Z_HEM + 0.004)), 0.001, 0.0008)
apr = np.zeros_like(Zh, bool)
if A_:
    # apron: edge (turned, shadowed underneath) + swag folds sweeping up toward the hips
    zaph = A_["z_front"] + (A_["z_side"] - A_["z_front"]) * np.clip(np.abs(azh) / A_["az"], 0, 1) ** 2
    de = Zh - zaph
    apr = (np.abs(azh) < A_["az"]) & (de > 0)
    disp += np.where(apr, 0.0012 * np.clip(1 - de / 0.006, 0, 1), 0.0)
    occm = np.where((np.abs(azh) < A_["az"]) & (de < 0) & (de > -0.008), 0.7, occm)
    # swags: a few soft catenary folds hanging between the hip gathers (deepest at the centre front)
    xa = np.abs(azh) / A_["az"]
    sag = Zh - (zaph + (Z_TOP - zaph) * 0.0) + 0.09 * (1 - xa ** 2)
    sw = np.where(apr, np.sin(sag / A_["swag"] * 2 * math.pi) * (1 - xa ** 2) ** 0.5, 0.0)
    disp += A_["swag_amp"] * sw * np.clip((Z_TOP - 0.08 - Zh) / 0.12, 0, 1) * np.clip(de / 0.05, 0, 1)
if PL_:
    # pleat folds: a crisp crease along each fold edge (shadowed under the overlap), a pressed line on the inner fold
    ph_h = (Th * PL_["n"] / (2 * math.pi) + PL_.get("phase", 0.0)) % 1.0
    if PL_.get("dir", 1) < 0:
        ph_h = 1.0 - ph_h
    ramp_h = np.clip((PL_.get("z_stitch", Z_TOP - 0.08) - Zh) / PL_.get("open", 0.12), 0, 1)
    dfold = np.minimum(ph_h, 1 - ph_h) * 2 * math.pi * rh / PL_["n"]
    disp += groove(dfold, 0.0012, 0.0014) * (0.3 + 0.7 * ramp_h)
    occm = np.where((ph_h < 0.06) & (ramp_h > 0.05), 0.62 + 0.38 * ph_h / 0.06, occm)
    # the stitched-down part: a seam line along each fold from the waist to z_stitch
    disp += np.where(Zh > PL_.get("z_stitch", Z_TOP - 0.08), groove(dfold, 0.0007, 0.0006), 0.0)
# tiers: gathered folds in each tier, turned scalloped edge, shadow on the tier below
for (zbe_, wa_), tr in zip(tedges, TIERS):
    occm = np.where((wa_ > 0.3) & (Zh < zbe_) & (Zh > zbe_ - 0.025), 0.6 + 0.4 * np.clip((zbe_ - Zh) / 0.025, 0, 1), occm)
# bustle drape: vertical folds + scalloped lower edge with a shadow under it
bzh = np.exp(-((Zh - B_["z"]) / B_["dz"]) ** 2)
bah = np.exp(-((np.abs(azh) - 180) / B_["daz"]) ** 2)
disp += B_["fold"] * np.sin(Th * B_["n"] + 1.5 * np.sin(Th * 5)) * bzh * bah * (0.6 + 0.4 * np.sin(Th * 13))
zbe = B_["z"] - B_["dz"] * 1.2 + 0.02 * np.abs(np.sin(np.radians(azh) * 4))
edge_b = (bah > 0.25) & (np.abs(Zh - zbe) < 0.006) & (B_.get("r", 0.0) > 0)
disp += np.where(edge_b, 0.002, 0.0)
occm = np.where((bah > 0.25) & (Zh < zbe) & (Zh > zbe - 0.012) & (B_.get("r", 0.0) > 0), 0.72, occm)
# long soft folds on the under-skirt
disp += S.get("soft_folds", 0.0018) * np.sin(Th * 11 + 0.8 * np.sin(Zh * 9)) * np.clip((Z_TOP - 0.15 - Zh) / 0.3, 0, 1) * ~apr
Phi = loft(THh, ZSh, rh + disp, ych)
Phi = open_remap(Phi, ych)
hi = grid_mesh(f"{PIECE}_hi", Phi)
occ = np.clip((1 + disp / 0.0012 * 0.18) * occm, 0.6, 1.08).ravel()
col = hi.data.color_attributes.new("occ", "FLOAT_COLOR", "POINT")
col.data.foreach_set("color", np.repeat(occ[:, None], 4, 1).astype(np.float32).ravel())


def drop_loose(o_):
    """Vertices only the opening's left-out faces used (after per-point attributes are set on the full grid)."""
    bm_ = bmesh.new()
    bm_.from_mesh(o_.data)
    bmesh.ops.delete(bm_, geom=[v for v in bm_.verts if not v.link_faces], context="VERTS")
    bm_.to_mesh(o_.data)
    bm_.free()


if S.get("opening"):
    drop_loose(hi)
    drop_loose(lo)


def r_at(th, z):
    """Bilinear sample of the main skirt radius at points (periodic azimuth)."""
    fi = (th % (2 * math.pi)) / (2 * math.pi) * NA
    fj = np.clip((Z_TOP - z) / (Z_TOP - Z_HEM) * (NZ - 1), 0, NZ - 1.0001)
    i0 = np.floor(fi).astype(int) % NA
    i1 = (i0 + 1) % NA
    wi = fi - np.floor(fi)
    j0 = np.floor(fj).astype(int)
    wj = fj - j0
    a = r[i0, j0] * (1 - wj) + r[i0, j0 + 1] * wj
    b = r[i1, j0] * (1 - wj) + r[i1, j0 + 1] * wj
    return a * (1 - wi) + b * wi


def tier_panel(tr, na, nu, detail):
    span = math.radians(tr["span_deg"]) if "span_deg" in tr else math.radians(tr["daz"] * tr.get("span", 2.2))
    ths = math.radians(tr.get("center_deg", 180)) + np.linspace(-span, span, na)   # (center_deg 0: across the front)
    azd = np.degrees((ths + math.pi) % (2 * math.pi) - math.pi)
    wa = np.ones(na) if tr.get("uniform") else np.exp(-((np.abs(azd) - 180) / tr["daz"]) ** 2)   # (a hem flounce: all round)
    zbe = tr["z_bot"] + tr.get("scallop", 0.02) * np.sin(np.radians(azd) * tr.get("n_sc", 3)) ** 2 \
        - tr.get("v", 0.0) * np.exp(-((np.abs(azd) - 180) / (tr["daz"] * 0.6)) ** 2)
    zb_eff = tr["z_top"] - (tr["z_top"] - zbe) * np.clip(wa, 0, 1) ** 0.5     # ends taper into the skirt
    us = np.linspace(0, 1, nu)
    P_ = np.zeros((na, nu, 3))
    dsp = np.zeros((na, nu))
    for i, th in enumerate(ths):
        z_ = tr["z_top"] - us * (tr["z_top"] - zb_eff[i])
        prof_ = us ** 1.2 - tr.get("roll", 0.35) * np.clip((us - 0.8) / 0.2, 0, 1) ** 2
        rr_ = r_at(np.full(nu, th), z_) + 0.004 + (tr["o_top"] + (tr["o_bot"] - tr["o_top"]) * prof_) * wa[i]
        # big soft folds (in the game mesh too), growing toward the hem; turned edge only in the detail
        dsp[i] = tr.get("fold", 0.004) * us ** 0.8 * np.sin(th * tr.get("n_fold", 16) + 1.2 * np.sin(th * 7)) * wa[i]
        if detail:
            dsp[i] += 0.0015 * np.clip(1 - (1 - us) / 0.05, 0, 1)
        yc_ = np.interp(-z_, -ZS, YC)
        P_[i] = np.stack([np.zeros(nu), yc_, z_], 1) + dirv(th)[None] * (rr_ + dsp[i])[:, None]
    return P_, dsp


def open_grid(name, P_):
    na, nu = P_.shape[:2]
    me = bpy.data.meshes.new(name)
    faces = [(i * nu + j, i * nu + j + 1, (i + 1) * nu + j + 1, (i + 1) * nu + j) for i in range(na - 1) for j in range(nu - 1)]
    me.from_pydata([tuple(q) for q in P_.reshape(-1, 3)], [], faces)
    me.validate()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


tl_parts, th_parts = [], []
for k_, tr in enumerate(TIERS):
    Pl, _ = tier_panel(tr, S.get("tier_na", 34), S.get("tier_nu", 7), False)
    Ph_, dh_ = tier_panel(tr, S.get("tier_na", 34) * 6, S.get("tier_nu", 7) * 6, True)
    tl_parts.append(open_grid(f"tier{k_}_lo", Pl))
    th_ = open_grid(f"tier{k_}_hi", Ph_)
    occ_t = np.clip(1 + dh_ / 0.0012 * 0.18, 0.6, 1.08).ravel()
    c_ = th_.data.color_attributes.new("occ", "FLOAT_COLOR", "POINT")
    c_.data.foreach_set("color", np.repeat(occ_t[:, None], 4, 1).astype(np.float32).ravel())
    th_parts.append(th_)
for parts_, base in ((tl_parts, None), (th_parts, None)):
    pass
only_select(*th_parts, hi)
bpy.ops.object.join()
hi = bpy.context.view_layer.objects.active
only_select(*tl_parts, lo)
bpy.ops.object.join()
lo = bpy.context.view_layer.objects.active
log("tiers", len(TIERS), "panels")
log("hi", len(hi.data.vertices), "verts; disp mm", round(float(disp.min()) * 1000, 2), round(float(disp.max()) * 1000, 2))

# lo: weights from the nearest non-arm body vertex, smooth shading, UVs
kdb = KDTree(int(noarm.sum()))
idx_noarm = np.flatnonzero(noarm)
for k_, i in enumerate(idx_noarm):
    kdb.insert(Vector(BPv[i]), k_)
kdb.balance()
for v in lo.data.vertices:
    j = idx_noarm[kdb.find(v.co)[1]]
    for gi in np.flatnonzero(Wb[j] > 1e-4):
        vg = lo.vertex_groups.get(gn[gi]) or lo.vertex_groups.new(name=gn[gi])
        vg.add([v.index], float(Wb[j, gi]), "REPLACE")
only_select(lo)
bm = bmesh.new()
bm.from_mesh(lo.data)
bmesh.ops.triangulate(bm, faces=bm.faces[:])
bm.to_mesh(lo.data)
bm.free()
bpy.ops.object.shade_smooth()
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.006, area_weight=0.0)
bpy.ops.uv.pack_islands(margin=0.006, rotate=True)
bpy.ops.object.mode_set(mode="OBJECT")
tris = sum(len(p_.vertices) - 2 for p_ in lo.data.polygons)
log("lo", tris, "tris")
ease = (r - rb).ravel()
RISE, Y0 = 0.0, -0.1
COVER_MARGIN = S.get("cover_margin", 0.015)
rin = interp(r, np.arange(1), np.array([Z_TOP]))  # (unused helper call keeps shapes honest)
COVERS_POS = np.array([q for q, ok in zip(BPv, noarm) if ok and Z_HEM + 0.04 < q[2] < Z_TOP - COVER_MARGIN])
KIND = "skirt"
exec(_SRC[_SRC.index("# ---- 4. bake"):])             # noqa: S102  bake, export, report, renders
