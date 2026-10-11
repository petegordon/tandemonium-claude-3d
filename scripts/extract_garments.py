"""P3.3 (D10): label every face of an aligned outfit with a garment (or "body") by colour family x
body region, then smooth.

  blender -b --factory-startup --python scripts/extract_garments.py -- --char outfit_male

Needs garment_explore.py's out/<char>-goose/<char>_faces.npz (per-face Lab, region, distance to the
rig-fitted base body). Colour families (Lab, chroma C = |ab|), first match wins:
  cream  L >= 62 | black  L < 20 and C < 8 | red  a >= 15 | brown  C >= 13 | tan  C < 13 | dark (rest)
chars/<char>.json "garments": ordered rules {name, family: [...], region: [...], z_min / z_max, y_max (front is -Y)
(m, base frame), L_min, dist_min / dist_max (m from the fitted body)}; the first matching rule labels the face, unmatched =
"other". Then SMOOTH rounds of an area-weighted majority vote over vertex-sharing faces (baked shadows
leave speckle). Writes <char>_garments.npz (label per face, names), <char>_garments.json (area share
per garment and per garment x region) and renders/<char>_garments.png (4 views + legend).
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1]
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
    if "dist_min" in r:
        m &= dist >= r["dist_min"]
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

tot = area.sum()
share = {n: round(float(area[label == i].sum() / tot), 3) for i, n in enumerate(NAMES)}
by_region = {n: {REGIONS[g]: round(float(area[(label == i) & (region == g)].sum() / max(1e-9, area[label == i].sum())), 2)
                 for g in range(len(REGIONS)) if area[(label == i) & (region == g)].sum() > 0.03 * area[label == i].sum()}
             for i, n in enumerate(NAMES)}
np.savez_compressed(D / f"{CHAR}_garments.npz", label=label, names=np.array(NAMES))
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
cols = np.concatenate([PALETTE[label % len(PALETTE)], np.ones((nf, 1))], 1)[lf]
attr.data.foreach_set("color", cols.ravel())
me.update()
H = cen[:, 2].max()
shots = []
tmp = RENDERS / "_tmp"
tmp.mkdir(parents=True, exist_ok=True)
for j, yaw in enumerate((0, 90, 180, 35)):
    y = math.radians(yaw)
    cam.ortho_scale = H * 1.1
    co.location = Vector((5 * math.sin(y), -5 * math.cos(y), H / 2))
    co.rotation_euler = (Vector((0, 0, H / 2)) - co.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = str(tmp / f"eg_{j}.png")
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(sc.render.filepath)
    shots.append(np.array(img.pixels[:]).reshape(RES, RES, 4)[::-1, :, :3])
    bpy.data.images.remove(img)
row = np.concatenate(shots, 1)
sw = np.ones((48, row.shape[1], 3)) * 0.92
step = row.shape[1] // nl
for i in range(nl):
    sw[6:42, i * step + 6:(i + 1) * step - 6] = PALETTE[i % len(PALETTE)]
sheet = np.concatenate([row, sw], 0)
h, w_, _ = sheet.shape
img = bpy.data.images.new("sheet", w_, h)
img.pixels = np.concatenate([sheet[::-1], np.ones((h, w_, 1))], -1).ravel().tolist()
img.filepath_raw = str(RENDERS / f"{CHAR}_garments.png")
img.file_format = "PNG"
img.save()
print("LEGEND", " | ".join(f"{i}:{n}" for i, n in enumerate(NAMES)))
print("RENDER", img.filepath_raw)
