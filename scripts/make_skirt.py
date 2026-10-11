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
noarm = ~np.array([("Arm" in d) or ("Hand" in d) or ("Shoulder" in d) for d in dom])
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
gp = next(o for o in load(D / "pieces" / f"{S.get('guide', 'dress')}.glb") if o.type == "MESH")
only_select(gp)
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
rg = radius_field(BVHTree.FromObject(gp, bpy.context.evaluated_depsgraph_get()), THS, ZS, YC)
bpy.data.objects.remove(gp)
okg = ~np.isnan(rg)
rg = np.where(okg, rg, 0.0)
rgs = smooth2(rg, S.get("guide_smooth", 14)) / np.maximum(smooth2(okg.astype(float), S.get("guide_smooth", 14)), 1e-3)
r = np.maximum(r, rgs * S.get("guide_scale", 1.0))
log("radius mm body p50 / guide p50", round(float(np.median(rb)) * 1000), round(float(np.median(rgs)) * 1000))
TT, ZZ = np.meshgrid(THS, ZS, indexing="ij")
az = np.degrees((TT + math.pi) % (2 * math.pi) - math.pi)              # -180..180, 0 = front
# bustle drape: a single swelling over the back below the waist
B_ = S["bustle"]
bz = np.exp(-((ZZ - B_["z"]) / B_["dz"]) ** 2) * np.clip((Z_TOP - ZZ) / 0.05, 0, 1)
ba = np.exp(-((np.abs(az) - 180) / B_["daz"]) ** 2)
r = r + B_["r"] * bz * ba
# flounces: two tiers standing out a little from the skirt
F_ = S["flounce"]
z1, z2 = Z_HEM + F_["h"], Z_HEM + 2 * F_["h"]
st = lambda z, z0: np.clip((z0 - z) / 0.015, 0, 1)  # noqa: E731
r = r + F_["out"] * st(ZZ, z2) * 0.6 + F_["out"] * st(ZZ, z1) * 0.6
# apron: front panel over the skirt down to a curved hem rising to the hips
A_ = S["apron"]
zap = A_["z_front"] + (A_["z_side"] - A_["z_front"]) * np.clip(np.abs(az) / A_["az"], 0, 1) ** 2
in_ap = (np.abs(az) < A_["az"]) & (ZZ > zap)
r = r + A_["out"] * in_ap * np.clip((ZZ - zap) / 0.01, 0, 1)
# waist: snug onto the body at the top
wt = np.clip((Z_TOP - ZZ) / S.get("waist_blend", 0.08), 0, 1) ** 1.5
r = (rb + S.get("waist_clear", 0.006)) * (1 - wt) + r * wt
r = smooth2(r, 1)


def loft(ths, zs, Rg, ycs):
    P_ = np.zeros((len(ths), len(zs), 3))
    for i, th in enumerate(ths):
        d = dirv(th)
        P_[i] = np.stack([np.zeros(len(zs)), ycs, zs], 1) + d[None] * Rg[i][:, None]
    return P_


def grid_mesh(name, P_, wrap=True):
    na, nz = P_.shape[:2]
    me = bpy.data.meshes.new(name)
    faces = []
    for i in range(na):
        i2 = (i + 1) % na
        for j in range(nz - 1):
            faces.append((i * nz + j, i * nz + j + 1, i2 * nz + j + 1, i2 * nz + j))
    me.from_pydata([tuple(p) for p in P_.reshape(-1, 3)], [], faces)
    me.validate()
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    return o


Plo = loft(THS, ZS, r, YC)
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


rh = interp(r, THh, ZSh)
ych = np.interp(-ZSh, -ZS, YC)
Th, Zh = np.meshgrid(THh, ZSh, indexing="ij")
azh = np.degrees((Th + math.pi) % (2 * math.pi) - math.pi)
disp = np.zeros_like(rh)
occm = np.ones_like(rh)


def groove(d, w, depth):
    return -depth * np.exp(-(d / w) ** 2)


arc = rh * 1.0
# waistband
disp += groove(np.abs(Zh - (Z_TOP - 0.02)), 0.0015, 0.0012)
# flounces: gathered (dense vertical ruffles growing toward each tier's lower edge), tier tops gathered
for zt in (z2, z1):
    inb = (Zh < zt) & (Zh > zt - F_["h"])
    u = np.clip((zt - Zh) / F_["h"], 0, 1)
    disp += np.where(inb, F_["ruffle"] * (0.3 + 0.7 * u) * np.sin(Th * F_["n"] + 0.6 * np.sin(Th * 7)), 0.0)
    disp += groove(np.abs(Zh - zt), 0.0016, 0.0016) + groove(np.abs(Zh - (zt - 0.006)), 0.0008, 0.0005)
    occm = np.where(np.abs(Zh - zt) < 0.004, 0.75, occm)
disp += groove(np.abs(Zh - (Z_HEM + 0.004)), 0.001, 0.0008)
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
# bustle drape: vertical folds + scalloped lower edge with a shadow under it
bzh = np.exp(-((Zh - B_["z"]) / B_["dz"]) ** 2)
bah = np.exp(-((np.abs(azh) - 180) / B_["daz"]) ** 2)
disp += B_["fold"] * np.sin(Th * B_["n"] + 1.5 * np.sin(Th * 5)) * bzh * bah * (0.6 + 0.4 * np.sin(Th * 13))
zbe = B_["z"] - B_["dz"] * 1.2 + 0.02 * np.abs(np.sin(np.radians(azh) * 4))
edge_b = (bah > 0.25) & (np.abs(Zh - zbe) < 0.006)
disp += np.where(edge_b, 0.002, 0.0)
occm = np.where((bah > 0.25) & (Zh < zbe) & (Zh > zbe - 0.012), 0.72, occm)
# long soft folds on the under-skirt
disp += 0.0018 * np.sin(Th * 11 + 0.8 * np.sin(Zh * 9)) * np.clip((Z_TOP - 0.15 - Zh) / 0.3, 0, 1) * ~apr
Phi = loft(THh, ZSh, rh + disp, ych)
hi = grid_mesh(f"{PIECE}_hi", Phi)
occ = np.clip((1 + disp / 0.0012 * 0.18) * occm, 0.6, 1.08).ravel()
col = hi.data.color_attributes.new("occ", "FLOAT_COLOR", "POINT")
col.data.foreach_set("color", np.repeat(occ[:, None], 4, 1).astype(np.float32).ravel())
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
