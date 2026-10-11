"""P3.3 step 1: colour palette + body-region map of an aligned outfit (to write its garment rules).

  blender -b --factory-startup --python scripts/garment_explore.py -- --char outfit_male [--k 10]

Per face of out/<char>-goose/<char>_goose_aligned.glb:
  colour  = mean albedo over the face's loops (sampled at loop UVs), to Lab; clustered with k-means
            on (0.5 L, a, b) so baked shadows weigh less than hue;
  region  = dominant bone of the nearest vertex of the base body deformed by <char>_rigfit.json
            (rig_fit.py transforms, re-applied here so the skin weights line up per vertex) -> head / neck / torso /
            hips / upper_arm / forearm / hand / thigh / shin / foot; plus distance to that vertex.
Writes out/<char>-goose/<char>_faces.npz (lab, cluster, region, dist, area) and renders/<char>_explore_
{clusters,regions}.png (4 views; clusters sheet has the palette with ids, areas and Lab).
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Euler, Vector
from mathutils.kdtree import KDTree

sys.path.insert(0, str(Path(__file__).parent))
from fixes.common import input_image, read_pixels  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1]
K = int(argv[argv.index("--k") + 1]) if "--k" in argv else 10
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{CHAR}-goose"
RENDERS = ROOT / "renders"
RES = 640

REGION_OF = {"Head": "head", "Jaw": "head", "Tongue": "head", "HatSocket": "head", "Neck": "neck",
             "Spine": "torso", "Spine1": "torso", "Spine2": "torso", "Hips": "hips", "Tail": "hips",
             "Shoulder": "torso", "Arm": "upper_arm", "ForeArm": "forearm", "Hand": "hand",
             "UpLeg": "thigh", "Leg": "shin", "Foot": "foot", "ToeBase": "foot", "Eye": "head"}
REGIONS = ["head", "neck", "torso", "hips", "upper_arm", "forearm", "hand", "thigh", "shin", "foot"]
REGION_RGB = np.array([[.9, .2, .2], [.95, .6, .1], [.2, .5, .95], [.55, .25, .8], [.1, .75, .7],
                       [.2, .85, .3], [.95, .9, .1], [.85, .4, .6], [.5, .35, .2], [.4, .4, .4]])


def region_of_bone(name):
    for side in ("Left", "Right"):
        name = name.replace(side, "")
    for key in sorted(REGION_OF, key=len, reverse=True):
        if name.startswith(key) or name.endswith(key):
            return REGION_OF[key]
    return "torso"


def load(path):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [o for o in bpy.context.scene.objects if o not in before]


def srgb_to_lab(rgb):
    c = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], 1)


def kmeans(X, w, k, iters=30, seed=0):
    rng = np.random.default_rng(seed)
    C = X[rng.choice(len(X), k, replace=False, p=w / w.sum())]
    for _ in range(iters):
        lab = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(-1), 1)
        for j in range(k):
            m = lab == j
            if m.any():
                C[j] = np.average(X[m], 0, w[m])
    return C, lab


bpy.ops.wm.read_factory_settings(use_empty=True)
outfit = [o for o in load(D / f"{CHAR}_goose_aligned.glb") if o.type == "MESH"][0]
rig = load(ROOT / "out" / "base-goose" / "base_goose_rigged.glb")
body = next(o for o in rig if o.type == "MESH" and o.name.startswith("base_goose_game"))
arm = next(o for o in rig if o.type == "ARMATURE")
FITS = json.loads((D / f"{CHAR}_rigfit.json").read_text())["transforms"]
me = outfit.data

# ---- face colour
px = read_pixels(input_image(outfit))
th, tw = px.shape[:2]
uv = np.empty(len(me.loops) * 2)
me.uv_layers.active.data.foreach_get("uv", uv)
uv = uv.reshape(-1, 2)
lrgb = px[np.clip((uv[:, 1] % 1) * th, 0, th - 1).astype(int),
          np.clip((uv[:, 0] % 1) * tw, 0, tw - 1).astype(int), :3]
loop_face = np.empty(len(me.loops), int)
for p in me.polygons:
    loop_face[p.loop_start:p.loop_start + p.loop_total] = p.index
nf = len(me.polygons)
frgb = np.zeros((nf, 3))
np.add.at(frgb, loop_face, lrgb)
frgb /= np.bincount(loop_face, minlength=nf)[:, None]
lab = srgb_to_lab(np.clip(frgb, 0, 1))
area = np.empty(nf)
me.polygons.foreach_get("area", area)
cen = np.empty(nf * 3)
me.polygons.foreach_get("center", cen)
cen = cen.reshape(-1, 3) @ np.array(outfit.matrix_world.to_3x3()).T + np.array(outfit.matrix_world.translation)

feat = lab * np.array([0.5, 1, 1])
sub = np.random.default_rng(0).choice(nf, min(60000, nf), replace=False)
C, _ = kmeans(feat[sub], area[sub], K)
cluster = np.argmin(((feat[:, None, :] - C[None]) ** 2).sum(-1), 1)

# ---- region from the fitted base body
names = [g.name for g in body.vertex_groups]
W = np.zeros((len(body.data.vertices), len(names)))
for v in body.data.vertices:
    for g in v.groups:
        W[v.index, g.group] = g.weight
vregion = np.array([REGIONS.index(region_of_bone(names[i])) for i in W.argmax(1)])
V = np.array([body.matrix_world @ v.co for v in body.data.vertices])
Wn = W / np.maximum(W.sum(1, keepdims=True), 1e-9)
fco = np.zeros_like(V)
for i, n in enumerate(names):
    m = Wn[:, i] > 0
    if not m.any():
        continue
    if n in FITS:
        h0 = np.array(arm.matrix_world @ arm.data.bones[n].head_local)
        fco[m] += Wn[m, i, None] * (np.array(FITS[n]["head"]) + (V[m] - h0) @ np.array(FITS[n]["A"]).T)
    else:
        fco[m] += Wn[m, i, None] * V[m]
kd = KDTree(len(fco))
for i, c in enumerate(fco):
    kd.insert(c, i)
kd.balance()
region = np.empty(nf, int)
dist = np.empty(nf)
for i, c in enumerate(cen):
    _, j, d = kd.find(c)
    region[i], dist[i] = vregion[j], d

np.savez_compressed(D / f"{CHAR}_faces.npz", lab=lab, cluster=cluster, region=region, dist=dist,
                    area=area, centers=C / np.array([0.5, 1, 1]))
tot = area.sum()
pal = []
for j in np.argsort(-np.bincount(cluster, area, K)):
    m = cluster == j
    reg = np.bincount(region[m], area[m], len(REGIONS))
    top = [f"{REGIONS[r]} {reg[r] / reg.sum():.0%}" for r in np.argsort(-reg)[:3] if reg[r] > 0.05 * reg.sum()]
    pal.append({"id": int(j), "area": round(float(area[m].sum() / tot), 3),
                "lab": [round(float(x), 1) for x in C[j] / np.array([0.5, 1, 1])], "regions": top})
print("PALETTE", json.dumps(pal))
print("REGIONS", json.dumps({REGIONS[r]: round(float(area[region == r].sum() / tot), 3) for r in range(len(REGIONS))}))

# ---- renders: face colours by cluster (palette colour) and by region
for o in list(bpy.context.scene.objects):
    if o is not outfit:
        bpy.data.objects.remove(o)


def lab_to_srgb(L):
    fy = (L[:, 0] + 16) / 116
    f = np.stack([fy + L[:, 1] / 500, fy, fy - L[:, 2] / 200], 1)
    xyz = np.where(f ** 3 > 0.008856, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    M = np.linalg.inv(np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]]))
    c = np.clip(xyz @ M.T, 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


pal_rgb = lab_to_srgb(C / np.array([0.5, 1, 1]))
# distinct label colours so neighbouring clusters with similar albedo still read apart
hue = np.array([[.9, .1, .1], [.1, .6, .9], [.95, .75, .1], [.2, .8, .3], [.7, .2, .8], [.95, .45, .1],
                [.1, .85, .8], [.9, .4, .7], [.5, .5, .5], [.55, .35, .15], [.2, .2, .9], [.7, .9, .2]])
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
ca.layer_name = "lab"
em = nt.nodes.new("ShaderNodeEmission")
on = nt.nodes.new("ShaderNodeOutputMaterial")
nt.links.new(ca.outputs["Color"], em.inputs["Color"])
nt.links.new(em.outputs["Emission"], on.inputs["Surface"])
me.materials.clear()
me.materials.append(mat)
attr = me.color_attributes.new("lab", "FLOAT_COLOR", "CORNER")
H = cen[:, 2].max()


def render(name, face_rgb, legend):
    cols = np.concatenate([face_rgb, np.ones((nf, 1))], 1)[loop_face]
    attr.data.foreach_set("color", cols.ravel())
    me.update()
    shots = []
    tmp = RENDERS / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    for j, yaw in enumerate((0, 90, 180, 35)):
        y = math.radians(yaw)
        cam.ortho_scale = H * 1.1
        co.location = Vector((5 * math.sin(y), -5 * math.cos(y), H / 2))
        co.rotation_euler = (Vector((0, 0, H / 2)) - co.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = str(tmp / f"ge_{j}.png")
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(sc.render.filepath)
        shots.append(np.array(img.pixels[:]).reshape(RES, RES, 4)[::-1, :, :3])
        bpy.data.images.remove(img)
    row = np.concatenate(shots, 1)
    sw = np.ones((48, row.shape[1], 3)) * 0.92       # legend strip: one swatch per entry
    step = row.shape[1] // max(1, len(legend))
    for i, rgb in enumerate(legend):
        sw[6:42, i * step + 6:(i + 1) * step - 6] = rgb
    sheet = np.concatenate([row, sw], 0)
    h, w_, _ = sheet.shape
    img = bpy.data.images.new(name, w_, h)
    img.pixels = np.concatenate([sheet[::-1], np.ones((h, w_, 1))], -1).ravel().tolist()
    img.filepath_raw = str(RENDERS / f"{CHAR}_explore_{name}.png")
    img.file_format = "PNG"
    img.save()
    print("RENDER", img.filepath_raw)


render("clusters", hue[cluster % len(hue)], [hue[j % len(hue)] for j in range(K)])
render("albedo_mean", pal_rgb[cluster], list(pal_rgb))
render("regions", REGION_RGB[region], list(REGION_RGB))
