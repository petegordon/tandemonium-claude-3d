"""Texture a built garment from Pete's drawings: bake the four calibrated reference views onto the garment's UVs.

  blender -b --factory-startup --python scripts/project_bake.py -- --piece breeches [--ref breeches]
      [--char outfit_male_victorian] [--tex 2048] [--tag v1] [--power 2.0]

Inputs: out/<char>-goose/shells/<piece>.glb (built by make_garment & co., UV-unwrapped), the reference views
out/outfit_male_victorian/dressed/<ref>/<view>_garment.png (RGBA: alpha = garment, drawn pixels warped part by part
onto OUR body, refs/key_views/cameras.json cameras). Per vertex and view: weight = max(0, n . to-camera)^power x
visible (a ray toward the camera meets neither the base body nor the garment itself); each view's UVs = the vertex's
pixel in that view. A Cycles emission bake blends sum(w x alpha x colour) / sum(w x alpha) into the garment's own UVs;
a second bake keeps the weight sum (coverage). Texels no view covers are filled from their neighbours (push-pull).
The result replaces the garment's base colour (its normal map stays): out/<char>-goose/versions/<piece>_<tag>.glb and
its texture <piece>_<tag>_albedo.png; also out/<char>-goose/shells/<piece>.glb unless --no-install.
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import body_cover  # noqa: E402
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_victorian")
PIECE = opt("--piece", "breeches")
REF = opt("--ref", {"waistcoat": "vest", "coat": "jacket", "gloves": "glove", "bowtie": "bow_tie"}.get(PIECE, PIECE))
TEX = opt("--tex", 2048)
TAG = opt("--tag", "v1")
POWER = opt("--power", 2.0)
SIDE_W = opt("--side-weight", 0.5)
CLOTH_TILE = opt("--cloth-tile", 0)  # > 0: plain cloth farther than this many texels from any gold (trim, embroidery,
                                     # lapel facing) takes the fabric tile in the median cloth colour -- clean cloth, the
                                     # drawing kept only around its ornament
FLATTEN = opt("--flatten", 0.0)  # 0-1: even out the cloth's broad light / dark blotches (painted shading, the drawing's
                                 # wear) toward its median colour; fine weave and the gold trim / embroidery are kept
LIFT = opt("--lift", 0.0)       # > 0: broad areas darker than LIFT x the cloth's median turn to the (median-shaded)
                                # fabric tile -- shadows painted into the drawing (arm shadow on the flank, shoulder blades)
MATS = [m for m in opt("--mats", "").split(",") if m]      # only these materials (name substrings) take the albedo
TILE_ONLY = "--tile-only" in argv                          # fabric tile everywhere (small pieces the views barely see)
INSTALL = "--no-install" not in argv
D = ROOT / "out" / f"{CHAR}-goose"
RD = ROOT / "out" / "outfit_male_victorian" / "dressed" / REF
VD = D / "versions"
VD.mkdir(parents=True, exist_ok=True)
CAM = json.loads((ROOT / "refs" / "key_views" / "cameras.json").read_text(encoding="utf-8"))
W0, H0 = CAM["size_px"]
PPM = CAM["px_per_m"]
TGT = np.array(CAM["target"])
VIEWS = [v for v in opt("--views", "front,left,rear,right").split(",") if (RD / f"{v}_garment.png").exists()]

bpy.ops.wm.read_factory_settings(use_empty=True)
# (an empty scene + the body appended: baking in the opened base_goose.blend scene fails "No valid selected objects")
with bpy.data.libraries.load(str(ROOT / "out" / "base-goose" / "base_goose.blend")) as (src, dst):
    dst.objects = ["base_goose_game"]
body = dst.objects[0]
bpy.context.scene.collection.objects.link(body)
for m in list(body.modifiers):
    body.modifiers.remove(m)
body.parent = None
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(D / "shells" / f"{PIECE}.glb"))
gar = next(o for o in bpy.data.objects if o not in before and o.type == "MESH")
bpy.ops.object.select_all(action="DESELECT")
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = gar.data
base_uv = me.uv_layers.active.name

# occluders: the base body as the dressed goose shows it (faces the garment hides -- and the tail under the breeches
# / jacket -- removed: the tail stuck out behind and hid the seat from the rear camera) and the garment itself
body_cover.remove_faces(body, body_cover.covered_faces(body, [gar], hide_tail=PIECE in ("breeches", "coat"),
                                                       force=body_cover.force_groups([PIECE])))
BV = [v.co.copy() for v in body.data.vertices]
GV = [v.co.copy() for v in me.vertices]
polys = [tuple(p.vertices) for p in body.data.polygons] + [tuple(i + len(BV) for i in p.vertices) for p in me.polygons]
OCC = BVHTree.FromPolygons(BV + GV, polys)
P = np.array([v.co[:] for v in me.vertices])
N = np.array([v.normal[:] for v in me.vertices])
loops_v = np.array([l.vertex_index for l in me.loops])
cover_stats = {}
for view in VIEWS:
    c = CAM["views"][view]
    R, U, B = np.array(c["right"]), np.array(c["up"]), np.array(c["back"])
    facing = np.clip(N @ B, 0, 1) ** POWER
    vis = np.zeros(len(P))
    for i in np.where(facing > 1e-4)[0]:
        o = Vector(P[i] + N[i] * 0.003 + B * 0.001)
        hit = OCC.ray_cast(o, Vector(B), 5.0)
        vis[i] = 0.0 if hit[0] is not None else 1.0
    w = facing * vis * (SIDE_W if view in ("left", "right") else 1.0)   # the side references are the weakest
    cover_stats[view] = round(float((w > 0.05).mean()), 3)
    rel = P - TGT
    x = W0 / 2 + rel @ R * PPM
    y = H0 / 2 - rel @ U * PPM
    uv = np.stack([x / W0, 1 - y / H0], 1)
    lay = me.uv_layers.new(name=f"pv_{view}")
    lay.data.foreach_set("uv", uv[loops_v].ravel())
    att = me.color_attributes.new(f"w_{view}", "FLOAT_COLOR", "POINT")
    att.data.foreach_set("color", np.repeat(w[:, None], 4, 1).ravel())
me.uv_layers.active = me.uv_layers[base_uv]
for i, l in enumerate(me.uv_layers):
    l.active_render = (l.name == base_uv)
print("COVER (verts seen > 0.05)", cover_stats, flush=True)

# bake material: sum_v w_v * a_v * rgb_v  and  sum_v w_v * a_v
mat = bpy.data.materials.new("projbake")
mat.use_nodes = True
nt = mat.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)
out = nt.nodes.new("ShaderNodeOutputMaterial")
em = nt.nodes.new("ShaderNodeEmission")
nt.links.new(em.outputs[0], out.inputs[0])
acc_c, acc_w = None, None
for view in VIEWS:
    sf = RD / f"{view}_garment_soft.png"
    img = bpy.data.images.load(str(sf if sf.exists() else RD / f"{view}_garment.png"))
    img.colorspace_settings.name = "sRGB"
    tx = nt.nodes.new("ShaderNodeTexImage")
    tx.image = img
    tx.interpolation = "Closest"
    tx.extension = "CLIP"
    uvn = nt.nodes.new("ShaderNodeUVMap")
    uvn.uv_map = f"pv_{view}"
    nt.links.new(uvn.outputs[0], tx.inputs[0])
    at = nt.nodes.new("ShaderNodeVertexColor")
    at.layer_name = f"w_{view}"
    wv = nt.nodes.new("ShaderNodeMath")
    wv.operation = "MULTIPLY"
    nt.links.new(at.outputs["Color"], wv.inputs[0])
    nt.links.new(tx.outputs["Alpha"], wv.inputs[1])
    cw = nt.nodes.new("ShaderNodeMixRGB")
    cw.blend_type = "MULTIPLY"
    cw.inputs[0].default_value = 1.0
    nt.links.new(tx.outputs["Color"], cw.inputs[1])
    nt.links.new(wv.outputs[0], cw.inputs[2])
    if acc_c is None:
        acc_c, acc_w = cw.outputs[0], wv.outputs[0]
    else:
        ac = nt.nodes.new("ShaderNodeMixRGB")
        ac.blend_type = "ADD"
        ac.inputs[0].default_value = 1.0
        nt.links.new(acc_c, ac.inputs[1])
        nt.links.new(cw.outputs[0], ac.inputs[2])
        aw = nt.nodes.new("ShaderNodeMath")
        aw.operation = "ADD"
        nt.links.new(acc_w, aw.inputs[0])
        nt.links.new(wv.outputs[0], aw.inputs[1])
        acc_c, acc_w = ac.outputs[0], aw.outputs[0]
sel = nt.nodes.new("ShaderNodeMixRGB")          # colour pass / weight pass switch
sel.blend_type = "MIX"
nt.links.new(acc_c, sel.inputs[1])
gw = nt.nodes.new("ShaderNodeCombineColor")
nt.links.new(acc_w, gw.inputs[0])
nt.links.new(acc_w, gw.inputs[1])
nt.links.new(acc_w, gw.inputs[2])
nt.links.new(gw.outputs[0], sel.inputs[2])
nt.links.new(sel.outputs[0], em.inputs["Color"])
old_mats = [s.material for s in gar.material_slots]
mat_idx = np.empty(len(me.polygons), dtype=np.int32)          # (materials.clear() resets every face to slot 0)
me.polygons.foreach_get("material_index", mat_idx)
gar.data.materials.clear()
gar.data.materials.append(mat)
tgt = nt.nodes.new("ShaderNodeTexImage")
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = 1
sc.cycles.device = "CPU"
res = {}
FT = RD / "fabric_tile.png"
FAB = FT.exists()
if FAB:                                              # fabric layer: the tile box-projected in object space at its size
    finfo = json.loads((RD / "fabric_tile.json").read_text(encoding="utf-8"))
    tco = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    s_ = 1.0 / finfo["size_m"]
    mp.inputs["Scale"].default_value = (s_, s_, s_)
    nt.links.new(tco.outputs["Object"], mp.inputs["Vector"])
    ftx = nt.nodes.new("ShaderNodeTexImage")
    ftx.image = bpy.data.images.load(str(FT))
    ftx.projection = "BOX"
    ftx.projection_blend = 0.3
    ftx.extension = "REPEAT"
    nt.links.new(mp.outputs[0], ftx.inputs[0])
white = nt.nodes.new("ShaderNodeRGB")                # island pass: 1 wherever a UV face is
white.outputs[0].default_value = (1, 1, 1, 1)
for pas, fac in (("color", 0.0), ("weight", 1.0), ("island", None)) + ((("fabric", None),) if FAB else ()):
    if pas == "island":
        nt.links.new(white.outputs[0], em.inputs["Color"])
    if pas == "fabric":
        nt.links.new(ftx.outputs["Color"], em.inputs["Color"])
    if fac is not None:
        sel.inputs[0].default_value = fac
    im = bpy.data.images.new(f"bake_{pas}", TEX, TEX, alpha=False, float_buffer=True)
    im.colorspace_settings.name = "Non-Color"
    tgt.image = im
    nt.nodes.active = tgt
    bpy.ops.object.select_all(action="DESELECT")
    gar.select_set(True)
    bpy.context.view_layer.objects.active = gar
    bpy.ops.object.bake(type="EMIT", margin=0, use_clear=True)
    res[pas] = np.array(im.pixels[:]).reshape(TEX, TEX, 4)[..., :3]
wsum = res["weight"][..., 0]
covered = wsum > 0.02
col = np.where(covered[..., None], res["color"] / np.maximum(wsum[..., None], 1e-6), 0)
# the bake ran on sRGB-decoded (linear) texels; keep linear for the image we write as linear float, then encode
# push-pull fill of the uncovered texels (coarse-to-fine averages of the covered ones)


def pushpull(c, m):
    if c.shape[0] <= 4 or m.all():
        return np.where(m[..., None], c, c[m].mean(0) if m.any() else 0)
    h, w = c.shape[0] // 2, c.shape[1] // 2
    cs = (c[:2 * h:2, :2 * w:2] * m[:2 * h:2, :2 * w:2, None] + c[1:2 * h:2, :2 * w:2] * m[1:2 * h:2, :2 * w:2, None] +
          c[:2 * h:2, 1:2 * w:2] * m[:2 * h:2, 1:2 * w:2, None] + c[1:2 * h:2, 1:2 * w:2] * m[1:2 * h:2, 1:2 * w:2, None])
    ms = (m[:2 * h:2, :2 * w:2].astype(float) + m[1:2 * h:2, :2 * w:2] + m[:2 * h:2, 1:2 * w:2] + m[1:2 * h:2, 1:2 * w:2])
    coarse = pushpull(np.where(ms[..., None] > 0, cs / np.maximum(ms[..., None], 1e-9), 0), ms > 0)
    # bilinear upsampling (nearest repeats left blocky mosaics in the filled areas)
    ys = (np.arange(c.shape[0]) + 0.5) / 2 - 0.5
    xs = (np.arange(c.shape[1]) + 0.5) / 2 - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, coarse.shape[0] - 1)
    x0 = np.clip(np.floor(xs).astype(int), 0, coarse.shape[1] - 1)
    y1 = np.clip(y0 + 1, 0, coarse.shape[0] - 1)
    x1 = np.clip(x0 + 1, 0, coarse.shape[1] - 1)
    fy = np.clip(ys - np.floor(ys), 0, 1)[:, None, None]
    fx = np.clip(xs - np.floor(xs), 0, 1)[None, :, None]
    up = (coarse[y0][:, x0] * (1 - fy) * (1 - fx) + coarse[y0][:, x1] * (1 - fy) * fx +
          coarse[y1][:, x0] * fy * (1 - fx) + coarse[y1][:, x1] * fy * fx)
    return np.where(m[..., None], c, up)


# 1) clone fill, tile by tile (32 texels): the uncovered texels inside the UV islands copy the cloth at the
#    nearest offset where the shifted texels are covered (keeps weaves / brocade instead of a blur);
# 2) push-pull for whatever is left
island = res["island"][..., 0] > 0.5
todo = island & ~covered
col2, cov2 = col.copy(), covered.copy()
TS = 32
OFFS = [(dy, dx) for r in (1, 2, 3) for dy, dx in ((0, r), (0, -r), (r, 0), (-r, 0), (r, r), (-r, -r), (r, -r), (-r, r))]
cloned = 0
for ty in range(0, TEX, TS):
    for tx_ in range(0, TEX, TS):
        tm = todo[ty:ty + TS, tx_:tx_ + TS]
        if not tm.any():
            continue
        yy, xx = np.where(tm)
        yy, xx = yy + ty, xx + tx_
        for dy, dx in OFFS:
            sy, sx = yy + dy * TS, xx + dx * TS
            okb = (sy >= 0) & (sy < TEX) & (sx >= 0) & (sx < TEX)
            if okb.all() and covered[sy, sx].mean() > 0.95:
                col2[yy, xx] = col[sy, sx]
                cov2[yy, xx] = True
                cloned += len(yy)
                break
print("CLONE texels", cloned, "of", int(todo.sum()), flush=True)
fill = pushpull(col2, cov2)
if FAB:
    # projection where the cameras see the garment well, fading into the fabric layer as coverage thins; the fabric
    # takes the drawing's slow shading (the projection blurred heavily, pushed into the gaps) so the seam disappears
    fab = res["fabric"]
    a_ = np.clip((wsum - 0.05) / 0.30, 0, 1)[..., None]
    a_ = a_ * covered[..., None]
    small = 16
    cs = col.reshape(TEX // small, small, TEX // small, small, 3).mean((1, 3))
    ms = covered.reshape(TEX // small, small, TEX // small, small).mean((1, 3)) > 0.3
    shade_s = pushpull(cs, ms)
    # smooth (bilinear) enlargement -- repeating texels made a blocky, jagged shading edge on the seat
    n_ = shade_s.shape[0]
    q = (np.arange(TEX) + 0.5) / small - 0.5
    i0 = np.clip(np.floor(q).astype(int), 0, n_ - 1)
    i1 = np.clip(i0 + 1, 0, n_ - 1)
    f = np.clip(q - np.floor(q), 0, 1)
    rows_ = shade_s[i0] * (1 - f)[:, None, None] + shade_s[i1] * f[:, None, None]
    shade = rows_[:, i0] * (1 - f)[None, :, None] + rows_[:, i1] * f[None, :, None]
    fmean = fab[island].mean(0) if island.any() else fab.reshape(-1, 3).mean(0)
    ratio = np.clip(shade / np.maximum(fmean, 1e-3), 0.6, 1.6)          # per channel: the tile takes the local colour
    fab_shaded = np.clip(fab * ratio, 0, 1)
    if TILE_ONLY:
        a_ = a_ * 0
        fab_shaded = np.clip(fab * np.clip(shade / np.maximum(fmean, 1e-3), 0.85, 1.15), 0, 1) if False else fab
    fill = col * a_ + fab_shaded * (1 - a_)
    print("FABRIC layer", FT.name, "projection share", round(float(a_[island].mean()), 3), flush=True)
    if LIFT > 0:
        lum = fill @ np.array([0.2126, 0.7152, 0.0722])
        med = np.median(lum[island])
        mcol = np.median(fill[island], 0)
        def box(a, r):                   # separable box blur (an integral image along each axis)
            for ax in (0, 1):
                c_ = np.cumsum(np.pad(a, [(r + 1, r) if k == ax else (0, 0) for k in range(a.ndim)], mode="edge"), ax)
                a = (np.take(c_, range(2 * r + 1, c_.shape[ax]), ax) - np.take(c_, range(0, c_.shape[ax] - 2 * r - 1), ax)) / (2 * r + 1)
            return a
        broad = box(box(lum, 6), 6)      # broad darkness only: fine dark lines (embroidery) average out with the gold
        dark = np.clip((LIFT * med - broad) / (0.25 * LIFT * med), 0, 1) * island
        dark = box(dark, 4)
        fab_med = np.clip(fab * (mcol / np.maximum(fmean, 1e-3)), 0, 1)
        fill = fill * (1 - dark[..., None]) + fab_med * dark[..., None]
        print("LIFT texels", int((dark > 0.5).sum()), "median lum", round(float(med), 3), flush=True)
if FLATTEN > 0:
    # cloth = texels near the cloth's own hue (not gold trim, not dark embroidery outlines); its broad colour
    # (a cloth-only blurred average over ~1/40 of the atlas) is divided out and replaced by the median cloth colour
    lum0 = fill @ np.array([0.2126, 0.7152, 0.0722])
    mx, mn = fill.max(2), fill.min(2)
    hue_r = (fill[..., 0] >= fill[..., 1]) & (fill[..., 0] >= fill[..., 2])
    gold = (fill[..., 1] > 0.4 * fill[..., 0]) & (fill[..., 2] < 0.6 * fill[..., 1]) & hue_r & (lum0 > 0.03)   # yellow (pale pink is not)
    cloth = island & hue_r & ~gold & (lum0 > 0.004)
    target = np.median(fill[cloth], 0)
    rr_ = max(4, TEX // 80)

    def boxm(a_, m_):
        def b1(x):
            for ax in (0, 1):
                c_ = np.cumsum(np.pad(x, [(rr_ + 1, rr_) if k == ax else (0, 0) for k in range(x.ndim)], mode="edge"), ax)
                x = (np.take(c_, range(2 * rr_ + 1, c_.shape[ax]), ax) - np.take(c_, range(0, c_.shape[ax] - 2 * rr_ - 1), ax))
            return x
        num = b1(a_ * m_[..., None])
        den = b1(m_.astype(float))[..., None]
        return num / np.maximum(den, 1e-6), den[..., 0]

    broad, den = boxm(fill, cloth)
    broad, _ = boxm(broad, den > 0.5)          # twice: smooth
    ratio = target / np.maximum(broad, 1e-4)
    flat = np.clip(fill * ratio, 0, 1)
    k_ = FLATTEN * cloth
    fill = fill * (1 - k_[..., None]) + flat * k_[..., None]
    print("FLATTEN cloth texels", int(cloth.sum()), "target", np.round(target, 3).tolist(), flush=True)
    if CLOTH_TILE and FAB:
        near = gold.astype(float)
        for _ in range(2):                       # grow the ornament by CLOTH_TILE texels (box max), soft edge
            near = (boxm(near, np.ones_like(near, bool))[0][..., 0] > 0.02).astype(float) if False else near
        from math import ceil
        g_ = gold.copy()
        step = max(1, CLOTH_TILE // 4)
        for _ in range(4):
            g2 = g_.copy()
            for dy in (-step, 0, step):
                for dx in (-step, 0, step):
                    g2 |= np.roll(np.roll(g_, dy, 0), dx, 1)
            g_ = g2
        keep_ = g_.astype(float)
        for _ in range(3):                       # feather the boundary
            keep_ = (keep_ + np.roll(keep_, 2, 0) + np.roll(keep_, -2, 0) + np.roll(keep_, 2, 1) + np.roll(keep_, -2, 1)) / 5
        tile_c = np.clip(fab * (target / np.maximum(fmean, 1e-3)), 0, 1)
        w_t = cloth * (1 - keep_)
        fill = fill * (1 - w_t[..., None]) + tile_c * w_t[..., None]
        print("CLOTH TILE texels", int((w_t > 0.5).sum()), flush=True)
# pad the islands: the texels outside them were black, and texture filtering / mipmaps bled that black into the
# cloth along every UV seam (dark marks on the jacket's shoulders); push-pull carries the island colours outward
# near-black specks inside the cloth (shadow pixels of the drawing, unseen texels): holes, refilled from around
lum_ = fill @ np.array([0.2126, 0.7152, 0.0722])
specks = island & (lum_ < opt("--speck", 0.2) * np.median(lum_[island]))
fill = np.where(specks[..., None], pushpull(fill, island & ~specks), fill)
print("SPECKS filled", int(specks.sum()), flush=True)
fill = pushpull(fill, island)
out_img = bpy.data.images.new(f"{PIECE}_{TAG}_albedo", TEX, TEX, alpha=False)
lin = np.clip(fill, 0, 1)
srgb = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - 0.055)
out_img.pixels = np.dstack([srgb, np.ones((TEX, TEX))]).ravel().tolist()
out_img.filepath_raw = str(VD / f"{PIECE}_{TAG}_albedo.png")
out_img.file_format = "PNG"
out_img.save()
cov_frac = float(covered.mean())

# put the garment's own material back, base colour = the baked albedo (normal map etc. kept)
gar.data.materials.clear()
for m in old_mats:
    gar.data.materials.append(m)
me.polygons.foreach_set("material_index", mat_idx)
me.update()
for v in VIEWS:
    me.uv_layers.remove(me.uv_layers[f"pv_{v}"])
    me.color_attributes.remove(me.color_attributes[f"w_{v}"])
alb = bpy.data.images.load(str(VD / f"{PIECE}_{TAG}_albedo.png"))
for m in old_mats:
    if not (m and m.use_nodes):
        continue
    if MATS and not any(k in m.name for k in MATS):
        continue
    bs = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bs is None:
        continue
    for l in list(bs.inputs["Base Color"].links):
        m.node_tree.links.remove(l)
    t = m.node_tree.nodes.new("ShaderNodeTexImage")
    t.image = alb
    m.node_tree.links.new(t.outputs[0], bs.inputs["Base Color"])
    if not MATS:
        break                                       # (first material = the cloth; trims / linings keep theirs)
bpy.ops.object.select_all(action="DESELECT")
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
outs = [VD / f"{PIECE}_{TAG}.glb"] + ([D / "shells" / f"{PIECE}.glb"] if INSTALL else [])
for f in outs:
    bpy.ops.export_scene.gltf(filepath=str(f), export_format="GLB", use_selection=True, export_tangents=True)
print("BAKED", json.dumps({"piece": PIECE, "tag": TAG, "views": VIEWS, "texel_cover": round(cov_frac, 3),
                           "verts_seen": cover_stats, "out": [str(f) for f in outs]}))
