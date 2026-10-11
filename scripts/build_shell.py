"""P3.4 step 2: build a game-ready garment shell from a transferred piece.

  blender -b --factory-startup --python scripts/build_shell.py -- --char outfit_male --piece gloves \
      [--tris 1600] [--voxel 0.003] [--offset 0.003] [--tex 1024]

Input: out/<char>-goose/pieces/<piece>.glb (geometry; colour is baked from the whole
<char>_outfit_on_base.glb unless --bake-src piece; chars json "shell_tris" overrides budgets,
"shell_mirror" {piece: "+x"} rebuilds a symmetric pair from its good half) (transfer_garments.py: the piece on the body it is worn on)
and that body (chars json "body_shape" via bodyshape.py: base game mesh, or deformed by
<char>_rigfit.json). Same recipe as retopo_bake.py for the base goose:
  1. solidify --solid (cut pieces are open sheets), voxel remesh (one closed solid), drop specks;
  2. QEM decimate to --tris, dissolve degenerates, triangulate n-gons;
  3. push-out (not for --no-push replacement pieces: gloves, boots, hat): every vertex closer than --offset
     to the body minus tail / hands / feet (masked or replaced in P3.5) (or inside it) moves to --offset outside
     along the body normal; the displacement is smoothed over the mesh (SMOOTH_IT) and re-clamped,
     so tight garments clear the body without kinks;
  4. smart UV + pack; Cycles bake (selected-to-active from the piece) of base colour + tangent normal;
     texels the bake misses keep a key colour and tex_clean.py fills them from the garment's own texels
     (plus colour-outlier repaint, chars json "shell_clean"); "shell_fill" {piece: [bones]} first closes
     the piece over uncovered body faces of those bones (male breeches seat once the tail is hidden);
  5. export out/<char>-goose/shells/<piece>.glb + <piece>.json (tris, push stats, poke of the
     covered body through the shell) and renders/<char>_shell_<piece>.png (shell, shell + body).
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

sys.path.insert(0, str(Path(__file__).parent))
import bodyshape  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]


def opt(name, default, cast=str):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


CHAR = opt("--char", "outfit_male")
PIECE = opt("--piece", "gloves")
BUDGET = {"hat": 800, "coat": 6000, "chest": 1500, "waistcoat": 900, "shirt": 500, "bowtie": 200, "breeches": 2500, "gloves": 3000, "boots": 1600,
          "dress": 9000, "collar": 400}
_cfg = json.loads((Path(__file__).resolve().parents[1] / "chars" / f"{CHAR}.json").read_text())
TRIS = opt("--tris", _cfg.get("shell_tris", {}).get(PIECE, BUDGET.get(PIECE, 2000)), int)
MIRROR = opt("--mirror", _cfg.get("shell_mirror", {}).get(PIECE, ""))   # "+x": keep the +X half, mirror it to -X
BAKE_SRC = opt("--bake-src", "piece")  # piece: colour from this piece only (misses are filled by tex_clean);
                                       # all: from the whole outfit (outer layers leaked in: coat on the waistcoat)
FILL = _cfg.get("shell_fill", {}).get(PIECE)   # bones whose uncovered body faces are closed over (tail hole)
FILL_OPT = {}
if isinstance(FILL, dict):   # {"bones", "z_max" (+ "v_slope" * |x|: V neckline), "x_max", "front": normal faces -Y}
    FILL_OPT, FILL = FILL, FILL["bones"]
CLEAN = _cfg.get("shell_clean", {}).get(PIECE, {})   # tex_clean.py options
KEY = (0.0, 0.0, 0.0)                  # texels the bake misses come out pure black
VOXEL = opt("--voxel", 0.0025, float)
SOLID = opt("--solid", 0.004, float)
OFFSET = opt("--offset", 0.003, float)
TEX = opt("--tex", 1024, int)
SMOOTH_IT = 8
MAX_PUSH = 0.03
ISLAND_KEEP = 0.03     # islands under 3 % of the largest are fragments mislabelled into the piece
PUSH = "--no-push" not in argv
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{CHAR}-goose"
OUT = D / "shells"
RENDERS = ROOT / "renders"
RES = 640
TEXCLEAN_PY = r"C:\Users\pete\ComfyUI-claude\.venv\Scripts\python.exe"   # numpy + scipy (same venv as sam_masks.py)
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


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


bpy.ops.wm.read_factory_settings(use_empty=True)
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text())

# ---- body the garment is worn on
rig = load(ROOT / "out" / "base-goose" / "base_goose_rigged.glb")
arm = next(o for o in rig if o.type == "ARMATURE")
body = next(o for o in rig if o.type == "MESH" and o.name.startswith("base_goose_game"))
TAIL_ROOT = np.array(arm.matrix_world @ arm.data.bones["Tail"].head_local) if "Tail" in arm.data.bones else None
for o in rig:
    if o is not body:
        bpy.data.objects.remove(o) if o.name in bpy.data.objects else None
bpy.ops.object.select_all(action="DESELECT")
body.select_set(True)
bpy.context.view_layer.objects.active = body
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
for m in list(body.modifiers):
    body.modifiers.remove(m)
if cfg.get("body_shape", "base") != "base":
    rig2 = load(ROOT / "out" / "base-goose" / "base_goose_rigged.glb")
    arm2 = next(o for o in rig2 if o.type == "ARMATURE")
    names = [g.name for g in body.vertex_groups]
    V = np.array([v.co[:] for v in body.data.vertices])
    W = np.zeros((len(V), len(names)))
    for v in body.data.vertices:
        for g in v.groups:
            W[v.index, g.group] = g.weight
    W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
    body.data.vertices.foreach_set("co", bodyshape.deform(V, W, names, arm2, bodyshape.body_transforms(ROOT, CHAR, arm2)).ravel())
    body.data.update()
    for o in rig2:
        bpy.data.objects.remove(o)
dg = bpy.context.evaluated_depsgraph_get()
# push against the body minus the parts that get masked / replaced (P3.5): tail under the coat,
# hands in gloves, feet in boots -- pushing around them only bulges the garment
gn = [g.name for g in body.vertex_groups]
Wb = np.zeros((len(body.data.vertices), len(gn)))
for v in body.data.vertices:
    for g in v.groups:
        Wb[v.index, g.group] = g.weight
skip_v = np.isin(np.array(gn)[Wb.argmax(1)], [n for n in gn if n == "Tail" or n.endswith(("Hand", "Foot", "ToeBase"))])
pv = [[v for v in p.vertices] for p in body.data.polygons if not skip_v[list(p.vertices)].all()]
body_bvh = BVHTree.FromPolygons([v.co[:] for v in body.data.vertices], pv)

# ---- piece (hi) and its shell
hi = next(o for o in load(D / "pieces" / f"{PIECE}.glb") if o.type == "MESH")
if MIRROR:                                       # a symmetric pair with one bad side (female s7 right boot)
    bm = bmesh.new()
    bm.from_mesh(hi.data)
    keep = 1 if MIRROR == "+x" else -1
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.x * keep < 0], context="VERTS")
    res = bmesh.ops.duplicate(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:])
    dup = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.scale(bm, vec=(-1, 1, 1), verts=dup)
    bmesh.ops.reverse_faces(bm, faces=[g for g in res["geom"] if isinstance(g, bmesh.types.BMFace)])
    bm.to_mesh(hi.data)
    bm.free()
    hi.data.update()
only_select(hi)
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
fill_report = None
if FILL:
    # The tail is hidden under breeches / coat (P3.5 FORCE), which leaves the hole the generated
    # piece had around it. Filler = body faces of the FILL bones that the piece does not cover (normal
    # ray misses it within 6 cm) plus a 4 cm overlap under the piece, with the tail pulled into its root,
    # offset to the piece's median clearance there. It joins the piece in the voxel remesh; its texels
    # miss the bake and are filled from the garment by tex_clean.py.
    hb = BVHTree.FromObject(hi, dg)
    dom = np.array(gn)[Wb.argmax(1)]
    BV = np.array([v.co[:] for v in body.data.vertices])
    BN = np.array([v.normal[:] for v in body.data.vertices])
    if "Tail" in gn and TAIL_ROOT is not None:     # (base rest pose; the sliders do not move the tail root much)
        tw = Wb[:, gn.index("Tail")] / np.maximum(Wb.sum(1), 1e-9)
        BV = BV + tw[:, None] * 0.85 * (TAIL_ROOT - BV)
    HP = np.array([v.co[:] for v in hi.data.vertices])
    zlo, ztop = np.percentile(HP[:, 2], [2, 97])
    polys = [list(pp.vertices) for pp in body.data.polygons]
    fc = np.array([BV[pv].mean(0) for pv in polys])
    fn = np.array([BN[pv].mean(0) for pv in polys])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-9)
    cand = np.array([all(dom[i] in FILL for i in pv) for pv in polys]) & (fc[:, 2] > zlo) & (fc[:, 2] < ztop)
    cand &= fc[:, 2] < FILL_OPT.get("z_max", 9.0) + FILL_OPT.get("v_slope", 0.0) * np.abs(fc[:, 0])   # V neckline
    cand &= np.abs(fc[:, 0]) < FILL_OPT.get("x_max", 9.0)
    if FILL_OPT.get("front"):
        cand &= fn[:, 1] < -0.3
    miss = np.array([c and hb.ray_cast(Vector(x), Vector(nn), 0.06)[0] is None for c, x, nn in zip(cand, fc, fn)])
    if miss.any():
        from mathutils.kdtree import KDTree
        kd = KDTree(int(miss.sum()))
        for j, x in enumerate(fc[miss]):
            kd.insert(Vector(x), j)
        kd.balance()
        dmin = np.array([kd.find(Vector(x))[2] for x in fc])
        sel = cand & (dmin < 0.04)
        near = HP[np.array([kd.find(Vector(x))[2] < 0.06 for x in HP])]
        clr = np.median([np.linalg.norm(np.array(body_bvh.find_nearest(Vector(x))[0]) - x) for x in near]) if len(near) else 0.01
        clr = float(np.clip(clr, OFFSET + 0.002, 0.03))
        bm = bmesh.new()
        bm.from_mesh(hi.data)
        vmap = {}
        for fi in np.flatnonzero(sel):
            vs = []
            for i in polys[fi]:
                if i not in vmap:
                    vmap[i] = bm.verts.new(BV[i] + BN[i] * clr)
                vs.append(vmap[i])
            try:
                bm.faces.new(vs)
            except ValueError:
                pass
        bm.to_mesh(hi.data)
        bm.free()
        hi.data.update()
        fill_report = {"bones": FILL, "uncovered_faces": int(miss.sum()), "filler_faces": int(sel.sum()),
                       "clearance_mm": round(clr * 1000, 1)}
        log("fill", fill_report)
shell = hi.copy()
shell.data = hi.data.copy()
shell.name = shell.data.name = f"{PIECE}_shell"
bpy.context.scene.collection.objects.link(shell)
shell.data.materials.clear()
for uv in list(shell.data.uv_layers):
    shell.data.uv_layers.remove(uv)
only_select(shell)
bpy.ops.mesh.customdata_custom_splitnormals_clear()
# a cut piece is an open sheet: voxelising a sheet thinner than a voxel leaks holes -> thicken first
sol = shell.modifiers.new("sol", "SOLIDIFY")
sol.thickness = SOLID
sol.offset = 0.0
bpy.ops.object.modifier_apply(modifier=sol.name)
shell.data.remesh_voxel_size = VOXEL
bpy.ops.object.voxel_remesh()
log(f"voxel {VOXEL * 1000:.1f} mm -> {len(shell.data.polygons)} faces")

bm = bmesh.new()
bm.from_mesh(shell.data)
islands, seen = [], set()
for v in bm.verts:
    if v.index in seen:
        continue
    stack, isl = [v], []
    seen.add(v.index)
    while stack:
        x = stack.pop()
        isl.append(x)
        for e in x.link_edges:
            y = e.other_vert(x)
            if y.index not in seen:
                seen.add(y.index)
                stack.append(y)
    islands.append(isl)
big = max(len(i) for i in islands)
drop = [v for isl in islands if len(isl) < max(50, ISLAND_KEEP * big) for v in isl]   # loose labelled fragments
bmesh.ops.delete(bm, geom=drop, context="VERTS")
bm.to_mesh(shell.data)
bm.free()
log(f"islands {len(islands)}, dropped {len(drop)} speck verts")

m = shell.modifiers.new("dec", "DECIMATE")
m.ratio = min(1.0, TRIS / max(1, tri_count(shell)) * 0.98)
bpy.ops.object.modifier_apply(modifier=m.name)
bm = bmesh.new()
bm.from_mesh(shell.data)
bmesh.ops.dissolve_degenerate(bm, dist=1e-5, edges=bm.edges)
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_area() < 1e-10], context="FACES")
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
bm.to_mesh(shell.data)
bm.free()
log(f"decimate -> {tri_count(shell)} tris")

# ---- push-out with smoothed displacement
me = shell.data
P = np.array([v.co[:] for v in me.vertices])
ed = np.array([e.vertices[:] for e in me.edges])


def clearance(P):
    """Signed distance to the body along its normal, the nearest body point and normal."""
    s = np.empty(len(P))
    q = np.empty_like(P)
    n = np.empty_like(P)
    for i, p in enumerate(P):
        loc, nrm, _, _ = body_bvh.find_nearest(Vector(p))
        q[i], n[i] = loc, nrm
        s[i] = (p - q[i]) @ n[i]
    return s, q, n


s, q, n = clearance(P)
need = (s < OFFSET) & (s > OFFSET - MAX_PUSH) & PUSH   # deeper = wrong-surface match (crotch/armpit) or masked
disp = np.where(need[:, None], n * (OFFSET - s)[:, None], 0.0)
deg = np.bincount(ed.ravel(), minlength=len(P)).astype(float)
for _ in range(SMOOTH_IT):
    acc = np.zeros_like(disp)
    np.add.at(acc, ed[:, 0], disp[ed[:, 1]])
    np.add.at(acc, ed[:, 1], disp[ed[:, 0]])
    avg = acc / np.maximum(deg, 1)[:, None]
    disp = np.where(need[:, None], disp, 0.5 * disp + 0.5 * avg)   # pushed verts keep theirs, neighbours ease in
P2 = P + disp
s2, q2, n2 = clearance(P2)                      # re-clamp after smoothing
P2 = np.where(((s2 < OFFSET) & (s2 > OFFSET - MAX_PUSH) & PUSH)[:, None], P2 + n2 * (OFFSET - s2)[:, None], P2)   # along the normal only (snapping to q2 jumped sideways)
me.vertices.foreach_set("co", P2.ravel())
me.update()
push = np.linalg.norm(P2 - P, axis=1)
push_stats = {"verts_pushed": round(float((push > 1e-4).mean()), 3),
              "push_mm_p50_p90_max": np.round(np.percentile(push, [50, 90, 100]) * 1000, 1).tolist()}
log("push", push_stats)
bpy.ops.object.shade_smooth()

# ---- UV + bake
only_select(shell)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.004, area_weight=0.0)
bpy.ops.uv.pack_islands(margin=0.004, rotate=True)
bpy.ops.object.mode_set(mode="OBJECT")

bake_src = hi
if FILL:
    bake_src = next(o for o in load(D / "pieces" / f"{PIECE}.glb") if o.type == "MESH")
    only_select(bake_src)
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
if BAKE_SRC == "all" and not MIRROR:
    # colour from the real clothed surface: a piece has holes where fragments were labelled to other
    # pieces, and rays through them baked the shirt patches / waistcoat flecks
    bake_src = next(o for o in load(D / f"{CHAR}_outfit_on_base.glb") if o.type == "MESH")
    only_select(bake_src)
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
for dev in ("OPTIX", "CUDA"):
    try:
        prefs.compute_device_type = dev
        prefs.get_devices()
        if any(d.type == dev for d in prefs.devices):
            for d in prefs.devices:
                d.use = d.type == dev
            sc.cycles.device = "GPU"
            break
    except TypeError:
        continue
sc.cycles.samples = 16
sc.render.bake.use_selected_to_active = True
sc.render.bake.cage_extrusion = OFFSET + 0.012
sc.render.bake.max_ray_distance = 0.06
sc.render.bake.margin = 8
mat = bpy.data.materials.new(f"{CHAR}_{PIECE}")
mat.use_nodes = True
me.materials.append(mat)
nt = mat.node_tree
bsdf = nt.nodes["Principled BSDF"]
imgs = {}
for name, btype, cs, kw in (("basecolor", "DIFFUSE", "sRGB", {"pass_filter": {"COLOR"}}),
                            ("normal", "NORMAL", "Non-Color", {"normal_space": "TANGENT"})):
    img = bpy.data.images.new(f"{CHAR}_{PIECE}_{name}", TEX, TEX, alpha=False)
    img.colorspace_settings.name = cs
    img.generated_color = (*KEY, 1) if name == "basecolor" else (0.5, 0.5, 1.0, 1)
    sc.render.bake.margin = 0 if name == "basecolor" else 8   # basecolor: tex_clean fills misses + margin
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = img
    nt.nodes.active = node
    only_select(bake_src, shell)
    bpy.ops.object.bake(type=btype, **kw)
    imgs[name] = (img, node)
    log("baked", name)
# ---- texture clean-up (tex_clean.py, scripts venv): fill bake misses (holes in the piece, filler)
# from the garment's own texels; optional colour-outlier repaint (chars json "shell_clean")
import subprocess  # noqa: E402
RAW = OUT / "_raw"
RAW.mkdir(parents=True, exist_ok=True)
img = imgs["basecolor"][0]
img.filepath_raw = str(RAW / f"{PIECE}_basecolor_raw.png")
img.file_format = "PNG"
img.save()
uvmask = RAW / f"{PIECE}_uvmask.npy"
uvs = np.array([d.uv[:] for d in me.uv_layers.active.data])
tri_uv = [uvs[list(pp.loop_indices)] for pp in me.polygons]
np.save(uvmask, np.array([tu[[0, k, k + 1]] for tu in tri_uv for k in range(1, len(tu) - 1)]))
clean_out = RAW / f"{PIECE}_basecolor.png"
if CLEAN.get("foreign"):                         # garment names -> median Lab of their faces
    fz, gz = np.load(D / f"{CHAR}_faces.npz"), np.load(D / f"{CHAR}_garments.npz")
    gnames = [str(x) for x in gz["names"]]

    def med(nm):
        return np.median(fz["lab"][gz["label"] == gnames.index(nm)], 0).round(1).tolist()
    CLEAN = {**CLEAN, "own": [med(x) for x in cfg["pieces"].get(PIECE, [PIECE])],
             "foreign": [med(x) for x in CLEAN["foreign"]], "foreign_names": CLEAN["foreign"]}
cmd = [TEXCLEAN_PY, "-I", str(Path(__file__).parent / "tex_clean.py"), str(img.filepath_raw), str(clean_out),
       "--uv-tris", str(uvmask), "--key", "0,0,0", "--opts", json.dumps(CLEAN)]
res = subprocess.run(cmd, capture_output=True, text=True)
print(res.stdout.strip(), res.stderr.strip()[-2000:])
clean_report = json.loads(next(ln for ln in res.stdout.splitlines() if ln.startswith("{"))) if res.returncode == 0 else None
if res.returncode == 0:
    cimg = bpy.data.images.load(str(clean_out))
    img.pixels = cimg.pixels[:]
    bpy.data.images.remove(cimg)
nt.links.new(imgs["basecolor"][1].outputs[0], bsdf.inputs["Base Color"])
nm = nt.nodes.new("ShaderNodeNormalMap")
nt.links.new(imgs["normal"][1].outputs[0], nm.inputs["Color"])
nt.links.new(nm.outputs[0], bsdf.inputs["Normal"])
bsdf.inputs["Roughness"].default_value = 0.8
for img, _ in imgs.values():
    img.pack()

# ---- poke of the covered body through the shell: body verts within 3 cm of the piece
hi_bvh = BVHTree.FromObject(hi, dg)
sh_bvh = BVHTree.FromObject(shell, bpy.context.evaluated_depsgraph_get())
BV = np.array([v.co[:] for v in body.data.vertices])
BN = np.array([v.normal[:] for v in body.data.vertices])
cov = np.array([hi_bvh.find_nearest(Vector(p))[3] < 0.03 for p in BV])
out_ = np.array([sh_bvh.ray_cast(Vector(p), Vector(nn), 0.3)[0] is None for p, nn in zip(BV[cov], BN[cov])])
report = {"char": CHAR, "piece": PIECE, "tris": tri_count(shell), "voxel_mm": VOXEL * 1000,
          "offset_mm": OFFSET * 1000, **push_stats, "covered_body_verts": int(cov.sum()),
          "covered_body_outside": round(float(out_.mean()), 3) if len(out_) else None,
          "bake_src": BAKE_SRC, "fill": fill_report, "tex_clean": clean_report}
OUT.mkdir(exist_ok=True)
(OUT / f"{PIECE}.json").write_text(json.dumps(report, indent=1))
print("SHELL", json.dumps(report))
only_select(shell)
bpy.ops.export_scene.gltf(filepath=str(OUT / f"{PIECE}.glb"), use_selection=True, export_format="GLB")

# ---- render: shell alone | shell + body (green), front / side / back / 3-4, framed on the piece
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
hi.hide_render = True
bake_src.hide_render = True
SP = np.array([v.co[:] for v in shell.data.vertices])
lo3, hi3 = SP.min(0), SP.max(0)
ctr = (lo3 + hi3) / 2
size = max(hi3[2] - lo3[2], hi3[0] - lo3[0], hi3[1] - lo3[1]) * 1.15
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
        sc.render.filepath = str(tmp / f"sh_{j}.png")
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
log("render", img.filepath_raw)
