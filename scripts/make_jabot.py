"""Modelled 18th-century neckwear (outfit_male_georgian): a white linen stock wrapped round the neck and a lace jabot
falling from the throat over the waistcoat front in gathered tiers.

  blender -b --factory-startup --python scripts/make_jabot.py -- --char outfit_male_georgian

Recipe: chars json "jabot_design":
  stock    {z0, z1, ease}            band round the neck between z0 and z1 (rays from the neck axis onto the body)
  tiers    [{z_top, h, w_top, w_bot, off, amp, n}, ...]
           each tier a gathered strip hanging from z_top (height h), half width w_top -> w_bot, standing "off" m out
           from the surface under it (waistcoat / shirt / body, rays from the front) with ruffle depth "amp" and "n"
           folds across; the bottom edge is scalloped. Upper tiers are drawn over lower ones (bigger off).
  over     shells it lies on (default waistcoat, shirt)
  colors   {"lace": rgb, "linen": rgb}
The lace look is a procedural texture (sprig + mesh holes painted darker, scallop eyelets along the edge).
Writes out/<char>-goose/shells/jabot.glb + .json and renders/<char>_shell_jabot.png. dress_goose.py: chars json
"no_mask" [jabot] (it never hides the body) and the nearest-body skinning like the other modelled pieces.
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

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
CHAR = argv[argv.index("--char") + 1] if "--char" in argv else "outfit_male_georgian"
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{CHAR}-goose"
OUT = D / "shells"
PIECE = argv[argv.index("--piece") + 1] if "--piece" in argv else "jabot"     # jabot | fichu ("fichu_design")
J = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))[f"{PIECE}_design"]


def srgb(c):
    c = np.array(c[:3]) / 255.0
    return tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)


def load(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [o for o in bpy.data.objects if o not in before]


def bvh_of(o):
    dg = bpy.context.evaluated_depsgraph_get()
    oe = o.evaluated_get(dg)
    me = oe.to_mesh()
    M = o.matrix_world
    t = BVHTree.FromPolygons([M @ v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    V = np.array([(M @ v.co)[:] for v in me.vertices])
    oe.to_mesh_clear()
    return t, V


bpy.ops.wm.read_factory_settings(use_empty=True)
rig = load(ROOT / "out" / "base-goose" / "base_goose_rigged.glb")
body = next(o for o in rig if o.type == "MESH" and o.name.startswith("base_goose_game"))
bbody, BV = bvh_of(body)
overs = []
for nm in J.get("over", ["waistcoat", "shirt"]):
    f = OUT / f"{nm}.glb"
    if f.exists():
        for o in load(f):
            if o.type == "MESH":
                overs.append(bvh_of(o)[0])
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)


def front_hit(x, z):
    """Outermost surface point seen from the front at (x, z): the first hit of a ray going +y."""
    best = None
    for t in overs + [bbody]:
        loc, nrm, _, d = t.ray_cast(Vector((x, -0.6, z)), Vector((0, 1, 0)), 2.0)
        if loc is not None and (best is None or loc.y < best[0].y):
            best = (loc, nrm)
    return best


bm = bmesh.new()
uvl = bm.loops.layers.uv.new("UVMap")


def grid(P, U, mat):
    rows = [[bm.verts.new(tuple(p)) for p in row] for row in P]
    for i in range(len(rows) - 1):
        for j in range(len(rows[0]) - 1):
            f = bm.faces.new([rows[i][j], rows[i][j + 1], rows[i + 1][j + 1], rows[i + 1][j]])
            f.material_index = mat
            for lp, (a, b) in zip(f.loops, ((i, j), (i, j + 1), (i + 1, j + 1), (i + 1, j))):
                lp[uvl].uv = U[a][b]


# ---- the stock: a band round the neck
if "stock" in J:
    S = J["stock"]
    NA = 48
    slab = BV[np.abs(BV[:, 2] - (S["z0"] + S["z1"]) / 2) < 0.01]
    cx, cy = float(slab[:, 0].mean()), float((slab[:, 1].min() + slab[:, 1].max()) / 2)
    zs = np.linspace(S["z0"], S["z1"], 5)
    RN = []                                  # neck radius per angle: the narrowest over the band's heights (a stock is
    for k in range(NA + 1):                  # a straight wrapped band; rays low on the neck catch the shoulders)
        th = 2 * math.pi * k / NA
        d = Vector((math.sin(th), -math.cos(th), 0))
        rs = []
        for z in zs:
            loc, _, _, _ = bbody.ray_cast(Vector((cx, cy, z)), d, 0.3)
            rs.append((loc - Vector((cx, cy, z))).length if loc is not None else 0.08)
        RN.append(min(rs))
    RN_f = []
    if S.get("front_deg"):
        for k in range(NA + 1):
            th = math.radians(-S["front_deg"] + 2 * S["front_deg"] * k / NA)
            d = Vector((math.sin(th), -math.cos(th), 0))
            rs = []
            for z in zs:
                loc, _, _, _ = bbody.ray_cast(Vector((cx, cy, z)), d, 0.3)
                rs.append((loc - Vector((cx, cy, z))).length if loc is not None else 0.08)
            RN_f.append(min(rs))
    P, U = [], []
    FD = S.get("front_deg")                 # a kerchief round the front of the neck only (+-front_deg from the front)
    for zi, z in enumerate(zs):
        row, urow = [], []
        for k in range(NA + 1):
            th = 2 * math.pi * k / NA if not FD else math.radians(-FD + 2 * FD * k / NA)
            d = Vector((math.sin(th), -math.cos(th), 0))
            endf = 0.0
            if FD:                               # the kerchief's ends taper to a point under the jacket edge
                endf = float(np.clip((abs(-FD + 2 * FD * k / NA) / FD - 0.55) / 0.45, 0, 1))
            zm_ = (S["z0"] + S["z1"]) / 2
            o = Vector((cx, cy, zm_ + (z - zm_) * (1 - 0.85 * endf)))
            r = RN[k] if not FD else RN_f[k]
            bulge = 0.002 * math.sin(math.pi * zi / (len(zs) - 1))
            fl = S.get("flare", 0.0) * (1 - zi / (len(zs) - 1)) ** 1.5 * (1 - endf)   # spreads onto the shoulders at the bottom
            row.append(o + d * (r + S.get("ease", 0.004) + bulge + fl))
            urow.append((k / NA * 0.5, 0.9 + 0.1 * zi / (len(zs) - 1)))
        P.append(row)
        U.append(urow)
    grid(P, U, S.get("mat", 1))

# ---- fichu: kerchief ends crossing over the bodice front (each a strip lying on the shells under it)
for si, ST in enumerate(J.get("strips", [])):
    (x0, z0), (x1, z1) = ST["from"], ST["to"]
    NL_, NW_ = 16, 8
    P, U = [], []
    for il in range(NL_ + 1):
        t = il / NL_
        cxs, czs = x0 + (x1 - x0) * t, z0 + (z1 - z0) * t
        dl = np.array([x1 - x0, z1 - z0]); dl /= np.linalg.norm(dl)
        perp = np.array([-dl[1], dl[0]])
        w_ = ST["w"] * (1 - ST.get("taper", 0.3) * t)
        row, urow = [], []
        for iw in range(NW_ + 1):
            u = iw / NW_ * 2 - 1
            x, z = cxs + perp[0] * u * w_ / 2, czs + perp[1] * u * w_ / 2
            hit = front_hit(x, z)
            base = hit[0] if hit else Vector((x, -0.12, z))
            roll = ST.get("roll", 0.003) * u * u + 0.0015 * math.sin((u + 1) * math.pi * ST.get("folds", 3)) * (0.3 + t)
            row.append(base + Vector((0, -(ST["off"] + roll), 0)))
            urow.append((0.05 + 0.4 * (iw / NW_), 0.05 + 0.75 * t))
        P.append(row)
        U.append(urow)
    grid(P, U, 0)

# ---- the jabot tiers (lowest first so the upper ones overlap them)
NU, NT = 30, 9
for ti, T in enumerate(sorted(J.get("tiers", []), key=lambda t: t["z_top"])):
    P, U = [], []
    for it in range(NT + 1):
        t = it / NT
        z = T["z_top"] - t * T["h"]
        hw = T["w_top"] + (T["w_bot"] - T["w_top"]) * t
        row, urow = [], []
        for iu in range(NU + 1):
            u = iu / NU * 2 - 1
            x = u * hw
            hit = front_hit(x, z)
            base = hit[0] if hit else Vector((x, -0.12, z))
            amp = T["amp"] * (0.25 + 0.75 * t ** 1.2)
            wave = amp * math.sin((u + 1) * math.pi * T["n"] + 0.6 * ti)
            scal = 0.0
            if it == NT:             # scalloped bottom edge
                scal = 0.004 * (0.5 + 0.5 * math.cos((u + 1) * math.pi * T["n"] * 2))
            out = T["off"] + 0.5 * amp + wave + J.get("hem_out", 0.012) * t * t       # the hem stands off a little
            row.append(base + Vector((0, -out, scal)))
            urow.append((0.5 + 0.5 * (iu / NU), 0.85 * (1 - t) * 0.999))
        P.append(row)
        U.append(urow)
    grid(P, U, 0)

me = bpy.data.meshes.new(f"{PIECE}_shell")
bm.normal_update()
bm.to_mesh(me)
bm.free()
o = bpy.data.objects.new(f"{PIECE}_shell", me)
bpy.context.scene.collection.objects.link(o)


def lace_texture(W=512):
    """Lace: white ground with a net of small holes (painted darker) and flower motifs, eyelets toward the
    lower edge of each tier (v small)."""
    y, x = np.mgrid[0:W, 0:W] / W
    lace = np.array(J.get("colors", {}).get("lace", [246, 244, 238]), float) / 255.0
    col = np.ones((W, W, 3)) * lace
    net = (np.sin(x * 2 * np.pi * 70) * np.sin(y * 2 * np.pi * 70)) > 0.55
    col[net] *= J.get("net_dark", 0.86)
    fl = ((np.hypot((x * 14) % 1 - 0.5, (y * 10) % 1 - 0.5) < 0.18)
          & (np.hypot((x * 14) % 1 - 0.5, (y * 10) % 1 - 0.5) > 0.1))
    col[fl] *= J.get("motif_dark", 0.8)
    eyelet = (y < 0.06) & (np.hypot((x * 40) % 1 - 0.5, (y * 40) % 1 - 0.5) < 0.2)
    col[eyelet] *= 0.72
    return col


img = bpy.data.images.new(f"{CHAR}_{PIECE}_lace", 512, 512, alpha=False)
lt = lace_texture()
img.pixels = np.concatenate([lt[::-1], np.ones((512, 512, 1))], -1).ravel().tolist()
img.pack()
for nm, col, tex in (("lace", J.get("colors", {}).get("lace", [246, 244, 238]), True),
                     ("linen", J.get("colors", {}).get("linen", [240, 238, 232]), False)):
    m = bpy.data.materials.new(f"{CHAR}_{PIECE}_{nm}")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.8
    m.use_backface_culling = False
    if tex:
        tn = m.node_tree.nodes.new("ShaderNodeTexImage")
        tn.image = img
        m.node_tree.links.new(tn.outputs["Color"], b.inputs["Base Color"])
    else:
        b.inputs["Base Color"].default_value = srgb(col)
    me.materials.append(m)
bpy.context.view_layer.objects.active = o
o.select_set(True)
sub = o.modifiers.new("sub", "SUBSURF")                 # soft gathered lace, not shards
sub.levels = J.get("subdiv", 1)
bpy.ops.object.modifier_apply(modifier="sub")
sol = o.modifiers.new("sol", "SOLIDIFY")
sol.thickness = 0.0015
sol.offset = 0.0
bpy.ops.object.modifier_apply(modifier="sol")
bpy.ops.object.shade_smooth()
bm = bmesh.new()
bm.from_mesh(me)
bmesh.ops.triangulate(bm, faces=bm.faces[:])
bm.to_mesh(me)
bm.free()
tris = len(me.polygons)
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.export_scene.gltf(filepath=str(OUT / f"{PIECE}.glb"), use_selection=True, export_format="GLB")
(OUT / f"{PIECE}.json").write_text(json.dumps({"char": CHAR, "piece": PIECE, "tris": tris, "source": "make_jabot.py (modelled)",
                                            "colors": J.get("colors", {})}, indent=1), encoding="utf-8")
print("SHELL", PIECE, tris)

# render: front / 3-4 / side
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = 480
sc.view_settings.view_transform = "Standard"
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.35, 0.38, 0.45, 1)
sc.world = w
L = bpy.data.objects.new("l", bpy.data.lights.new("l", "SUN"))
L.data.energy = 3.0
L.rotation_euler = Euler([math.radians(a) for a in (50, 0, 30)])
sc.collection.objects.link(L)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = 0.3
sc.collection.objects.link(cam)
sc.camera = cam
row = []
for yaw in (0, 35, 90):
    y_ = math.radians(yaw)
    c = Vector((0, -0.08, 1.2))
    cam.location = c + Vector((5 * math.sin(y_), -5 * math.cos(y_), 0.3))
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = str(ROOT / "renders" / "_tmp" / f"{PIECE}.png")
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(sc.render.filepath)
    row.append(np.array(im.pixels[:]).reshape(480, 480, 4)[::-1, :, :3])
    bpy.data.images.remove(im)
sheet = np.concatenate(row, 1)
h, w_, _ = sheet.shape
im = bpy.data.images.new("sheet", w_, h)
im.pixels = np.concatenate([sheet[::-1], np.ones((h, w_, 1))], -1).ravel().tolist()
im.filepath_raw = str(ROOT / "renders" / f"{CHAR}_shell_{PIECE}.png")
im.file_format = "PNG"
im.save()
print("RENDER", im.filepath_raw)
