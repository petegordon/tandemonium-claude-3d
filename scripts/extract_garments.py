"""P3.3 (D10): label every face of an aligned outfit with a garment (or "body") by colour family x
body region, then smooth.

  blender -b --factory-startup --python scripts/extract_garments.py -- --char outfit_male

Needs garment_explore.py's out/<char>-goose/<char>_faces.npz (per-face Lab, region, distance to the
rig-fitted base body). Colour families (Lab, chroma C = |ab|), first match wins:
  cream  L >= 62 | black  L < 20 and C < 8 | red  a >= 15 | brown  C >= 13 | tan  C < 13 | dark (rest)
chars/<char>.json "garments": ordered rules {name, family: [...], region: [...], layered (another surface 8-45 mm behind: outer layer),
ax_max (|x| limit), inside_of (strictly inside an earlier garment's front x-extent per 2 cm band), z_min / z_max, y_max (front is -Y)
(m, base frame), L_min, dist_min / dist_max (m from the fitted body)}; the first matching rule labels the face, unmatched =
"other". Then SMOOTH rounds of an area-weighted majority vote over vertex-sharing faces (baked shadows
leave speckle), and same-label islands under --island m^2 (default 4 cm^2) join the label bordering
them most (buttons, collar specks, hem fragments). Writes <char>_garments.npz (label per face, names), <char>_garments.json (area share
per garment and per garment x region; "pieces" = the shells P3.4 builds, chars json "pieces"
{piece: [garments]}, Pete's mid split) and renders/<char>_garments.png (4 views + legend).
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1]
ISLAND_M2 = float(argv[argv.index("--island") + 1]) if "--island" in argv else 4e-4
ISLAND_ROUNDS = 2
PIECE_ISLAND_M2 = 15e-4   # 40e-4 swallowed glove fingers (separate small islands)
SMOOTH = int(argv[argv.index("--smooth") + 1]) if "--smooth" in argv else 2
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{CHAR}-goose"
RENDERS = ROOT / "renders"
RES = 640
REGIONS = ["head", "neck", "torso", "hips", "upper_arm", "forearm", "hand", "thigh", "shin", "foot"]
FAMILIES = ["cream", "black", "red", "brown", "tan", "dark"]
PALETTE = np.array([[.55, .55, .55], [.9, .15, .15], [.15, .55, .95], [.95, .75, .1], [.2, .8, .3],
                    [.7, .25, .85], [.95, .45, .1], [.1, .85, .8], [.95, .45, .7], [.55, .35, .15],
                    [.25, .25, .9], [.7, .9, .2], [.1, .1, .1], [1, 1, 1]])

cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text())
RULES = cfg["garments"]
NAMES = ["other"] + list(dict.fromkeys(r["name"] for r in RULES))
F = np.load(D / f"{CHAR}_faces.npz")
lab, region, dist, area = F["lab"], F["region"], F["dist"], F["area"]
L, a, b = lab.T
C = np.hypot(a, b)
family = np.full(len(L), FAMILIES.index("dark"))
for name, m in reversed([("cream", L >= 62), ("black", (L < 20) & (C < 8)), ("red", a >= 15),
                         ("brown", C >= 13), ("tan", C < 13)]):
    family[m] = FAMILIES.index(name)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(D / f"{CHAR}_goose_aligned.glb"))
ob = next(o for o in bpy.context.scene.objects if o.type == "MESH")
me = ob.data
nf = len(me.polygons)
assert nf == len(L), "faces.npz is stale: re-run garment_explore.py"
cen = np.empty(nf * 3)
me.polygons.foreach_get("center", cen)
cen = cen.reshape(-1, 3) @ np.array(ob.matrix_world.to_3x3()).T + np.array(ob.matrix_world.translation)

nrm = np.empty(nf * 3)
me.polygons.foreach_get("normal", nrm)
nrm = nrm.reshape(-1, 3) @ np.array(ob.matrix_world.to_3x3()).T
nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
bvh = BVHTree.FromObject(ob, bpy.context.evaluated_depsgraph_get())


def layered(idx):
    """Another surface 8-45 mm behind the face (past its own ~5 mm double wall): an outer layer."""
    out = np.zeros(len(idx), bool)
    for k, f in enumerate(idx):
        o, d = Vector(cen[f] - nrm[f] * 0.001), Vector(-nrm[f])
        travelled = 0.001
        for _ in range(4):
            hit = bvh.ray_cast(o, d, 0.045 - travelled)
            if hit[0] is None:
                break
            travelled += hit[3]
            if travelled > 0.008:
                out[k] = True
                break
            o = hit[0] + d * 0.0005
            travelled += 0.0005
    return out


label = np.zeros(nf, int)
done = np.zeros(nf, bool)
for r in RULES:
    m = ~done
    if "family" in r:
        m &= np.isin(family, [FAMILIES.index(f) for f in r["family"]])
    if "region" in r:
        m &= np.isin(region, [REGIONS.index(g) for g in r["region"]])
    if "z_min" in r:
        m &= cen[:, 2] >= r["z_min"]
    if "z_max" in r:
        m &= cen[:, 2] < r["z_max"]
    if "y_max" in r:
        m &= cen[:, 1] < r["y_max"]
    if "L_min" in r:
        m &= L >= r["L_min"]
    if "ax_max" in r:
        m &= np.abs(cen[:, 0]) < r["ax_max"]
    if "dist_min" in r:
        m &= dist >= r["dist_min"]
    if "inside_of" in r:                      # strictly inside another garment's x-extent per 2 cm band
        ref = (label == NAMES.index(r["inside_of"])) & (cen[:, 1] < 0)
        band = np.floor(cen[:, 2] / 0.02).astype(int)
        ok = np.zeros(nf, bool)
        for bz in np.unique(band[m]):
            rb = ref & (band == bz)
            if rb.sum() < 20:
                continue
            lo, hi = np.percentile(cen[rb, 0], [20, 80])   # 5-95 reached the tan lapel highlights
            sel = m & (band == bz) & (cen[:, 0] > lo + 0.01) & (cen[:, 0] < hi - 0.01)
            ok |= sel
        m &= ok
    if r.get("layered"):
        idx = np.flatnonzero(m)
        m[idx[~layered(idx)]] = False
    if "dist_max" in r:
        m &= dist < r["dist_max"]
    label[m] = NAMES.index(r["name"])
    done |= m

# majority smoothing over faces sharing a vertex
lv = np.empty(len(me.loops), int)
me.loops.foreach_get("vertex_index", lv)
lf = np.repeat(np.arange(nf), [p.loop_total for p in me.polygons])
nl = len(NAMES)
for _ in range(SMOOTH):
    vh = np.zeros((len(me.vertices), nl))
    np.add.at(vh, (lv, label[lf]), area[lf])
    fh = np.zeros((nf, nl))
    np.add.at(fh, lf, vh[lv])
    label = fh.argmax(1)

# islands: same-label connected components (faces sharing a vertex) under ISLAND_M2 join the label
# that borders them most (buttons, collar specks, hem fragments)
order = np.argsort(lv, kind="stable")
sv, sf = lv[order], lf[order]
same_v = sv[1:] == sv[:-1]
pa, pb = sf[1:][same_v], sf[:-1][same_v]
pairs = np.unique(np.stack([np.minimum(pa, pb), np.maximum(pa, pb)], 1), axis=0)
pa, pb = pairs[:, 0], pairs[:, 1]
kd = None


def merge_islands(lab_, thresh, nlab):
    global kd
    lab_ = lab_.copy()
    for _ in range(ISLAND_ROUNDS):
        eq = lab_[pa] == lab_[pb]
        comp = np.arange(nf)
        while True:
            prev = comp.copy()
            lo = np.minimum(comp[pa[eq]], comp[pb[eq]])
            np.minimum.at(comp, pa[eq], lo)
            np.minimum.at(comp, pb[eq], lo)
            comp = comp[comp]
            if np.array_equal(comp, prev):
                break
        carea = np.bincount(comp, area, nf)
        small = carea[comp] < thresh
        border = ~eq & (small[pa] | small[pb])
        votes = np.zeros((nf, nlab))
        np.add.at(votes, (comp[pa[border]], lab_[pb[border]]), area[pb[border]])
        np.add.at(votes, (comp[pb[border]], lab_[pa[border]]), area[pa[border]])
        votes[comp, lab_] = 0                 # never vote for your own label (components are single-label)
        lonely = np.unique(comp[small & (votes[comp].max(1) == 0)])   # detached pieces (buttons)
        if len(lonely):
            if kd is None:
                kd = KDTree(nf)
                for i, c in enumerate(cen):
                    kd.insert(c, i)
                kd.balance()
            order_c = np.argsort(comp, kind="stable")
            starts = np.searchsorted(comp[order_c], lonely)
            ends = np.searchsorted(comp[order_c], lonely, side="right")
            for c, s0, e0 in zip(lonely, starts, ends):
                fs = order_c[s0:e0]
                own = lab_[fs[0]]
                for f in fs[:: max(1, len(fs) // 8)]:
                    for _, j, d in kd.find_n(cen[f], 24):
                        if lab_[j] != own and d < 0.015:
                            votes[c, lab_[j]] += area[j]
        target = votes.argmax(1)
        move = small & (votes[comp].max(1) > 0)
        lab_[move] = target[comp[move]]
    return lab_


label = merge_islands(label, ISLAND_M2, nl)

tot = area.sum()
share = {n: round(float(area[label == i].sum() / tot), 3) for i, n in enumerate(NAMES)}
by_region = {n: {REGIONS[g]: round(float(area[(label == i) & (region == g)].sum() / max(1e-9, area[label == i].sum())), 2)
                 for g in range(len(REGIONS)) if area[(label == i) & (region == g)].sum() > 0.03 * area[label == i].sum()}
             for i, n in enumerate(NAMES)}
PIECES = cfg.get("pieces", {n: [n] for n in NAMES if n not in ("other", "body")})
piece_of = {g: p for p, gs in PIECES.items() for g in gs}
PNAMES = ["other", "body"] + list(PIECES)
piece = np.array([PNAMES.index(piece_of.get(n, n if n in PNAMES else "other")) for n in NAMES])[label]
piece = merge_islands(piece, PIECE_ISLAND_M2, len(PNAMES))   # fragments between pieces
share["pieces"] = {p: round(float(area[piece == i].sum() / tot), 3) for i, p in enumerate(PNAMES)}
np.savez_compressed(D / f"{CHAR}_garments.npz", label=label, names=np.array(NAMES),
                    piece=piece, piece_names=np.array(PNAMES))
(D / f"{CHAR}_garments.json").write_text(json.dumps({"share": share, "by_region": by_region}, indent=1))
print("GARMENTS", json.dumps({"share": share, "by_region": by_region}))

# render
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = RES
sc.view_settings.view_transform = "Standard"
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.92, 0.92, 0.92, 1)
sc.world = w
cam = bpy.data.cameras.new("cam")
cam.type = "ORTHO"
co = bpy.data.objects.new("cam", cam)
sc.collection.objects.link(co)
sc.camera = co
mat = bpy.data.materials.new("vc")
mat.use_nodes = True
nt = mat.node_tree
nt.nodes.clear()
ca = nt.nodes.new("ShaderNodeVertexColor")
ca.layer_name = "g"
em = nt.nodes.new("ShaderNodeEmission")
on = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(ca.outputs["Color"], em.inputs["Color"])
nt.links.new(em.outputs["Emission"], on.inputs["Surface"])
me.materials.clear()
me.materials.append(mat)
attr = me.color_attributes.new("g", "FLOAT_COLOR", "CORNER")
H = cen[:, 2].max()
tmp = RENDERS / "_tmp"
tmp.mkdir(parents=True, exist_ok=True)


def shot(yaw, zc, scale, xc=0.0):
    y = math.radians(yaw)
    cam.ortho_scale = scale
    side = Vector((math.cos(y), math.sin(y), 0)) * xc
    co.location = Vector((5 * math.sin(y), -5 * math.cos(y), zc)) + side
    co.rotation_euler = (Vector((0, 0, zc)) + side - co.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = str(tmp / "eg.png")
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(sc.render.filepath)
    px = np.array(img.pixels[:]).reshape(RES, RES, 4)[::-1, :, :3]
    bpy.data.images.remove(img)
    return px


def sheet(lab_, names, suffix):
    cols = np.concatenate([PALETTE[lab_ % len(PALETTE)], np.ones((nf, 1))], 1)[lf]
    attr.data.foreach_set("color", cols.ravel())
    me.update()
    nl = len(names)
    row = np.concatenate([shot(yaw, H / 2, H * 1.1) for yaw in (0, 90, 180, 35)], 1)
    # close-ups: chest/collar front, collar 3/4, back hem, right cuff + glove
    close = np.concatenate([shot(0, 1.12, 0.42), shot(35, 1.32, 0.26), shot(180, 0.68, 0.42),
                            shot(0, 0.86, 0.26, xc=-0.36)], 1)
    row = np.concatenate([row, close], 0)
    sw = np.ones((48, row.shape[1], 3)) * 0.92
    step = row.shape[1] // nl
    for i in range(nl):
        sw[6:42, i * step + 6:(i + 1) * step - 6] = PALETTE[i % len(PALETTE)]
    sheet = np.concatenate([row, sw], 0)
    h, w_, _ = sheet.shape
    img = bpy.data.images.new("sheet", w_, h)
    img.pixels = np.concatenate([sheet[::-1], np.ones((h, w_, 1))], -1).ravel().tolist()
    img.filepath_raw = str(RENDERS / f"{CHAR}_{suffix}.png")
    img.file_format = "PNG"
    img.save()
    print("LEGEND", suffix, " | ".join(f"{i}:{n}" for i, n in enumerate(names)))
    print("RENDER", img.filepath_raw)


sheet(label, NAMES, "garments")
sheet(piece, PNAMES, "pieces")
