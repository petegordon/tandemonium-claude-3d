"""Close-up review renders of a dressed goose (dress_goose.py output) with pieces toggled off.

  blender -b --factory-startup --python scripts/dressed_closeup.py -- --char outfit_male \
      [--hide coat,waistcoat | --only breeches] [--z 0.95] [--size 0.7] [--yaws 0,90,180,215] [--tag nocoat]
      [--tint breeches=44,56,88] [--pose riding|a_pose|neck_curve]

--tint sets a designed garment's glTF baseColorFactor (make_garment.py: colour / detail-texture mean) --
the recolour the game does. --pose uses rig_poses.Poser (cloth chains not applied).

Opens out/<char>-goose/<char>_dressed.blend, hides the listed shells and shows the body sub-meshes
the way the game toggles them ("body__a+b" is hidden while any of a, b is worn), renders an ortho
row centred at height --z -> renders/<char>_closeup_<tag>.png.
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]


def opt(name, default, cast=str):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


CHAR = opt("--char", "outfit_male")
HIDE = [h for h in opt("--hide", "").split(",") if h]
ONLY = [h for h in opt("--only", "").split(",") if h]
TINT = dict(kv.split("=") for kv in opt("--tint", "").split(";") if kv)
POSE = opt("--pose", "")
Z = opt("--z", 0.95, float)
SIZE = opt("--size", 0.7, float)
YAWS = [float(y) for y in opt("--yaws", "0,90,180,215").split(",")]
TAG = opt("--tag", "+".join(HIDE) or "all")
RES = 560
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{CHAR}-goose"

bpy.ops.wm.open_mainfile(filepath=str(D / f"{CHAR}_dressed.blend"))
FIXED = ("body", "eyeball", "lid", "catchlight")
worn = set()
for o in bpy.data.objects:
    if o.type != "MESH" or "__" in o.name or o.name.startswith(FIXED):
        continue
    if o.name in HIDE or (ONLY and o.name not in ONLY):
        o.hide_render = True
    else:
        worn.add(o.name)
for o in bpy.data.objects:   # "<piece>__a+b" sub-meshes (body, layered garments): hidden while a or b is worn
    if o.type == "MESH" and "__" in o.name:
        base, keys = o.name.split("__", 1)
        on = base == "body" or base in worn
        o.hide_render = (not on) or bool(set(keys.split("+")) & worn)
for k, rgb in TINT.items():
    meta = json.loads((D / "shells" / f"{k}.json").read_text(encoding="utf-8"))
    c = np.array([float(x) for x in rgb.split(",")]) / 255.0
    lin = lambda v: np.where(v > 0.04045, ((v + 0.055) / 1.055) ** 2.4, v / 12.92)  # noqa: E731
    fac = tuple(np.clip(lin(c) / lin(np.array([meta.get("detail_mean_srgb", 1.0)]))[0], 0, 1)) + (1.0,)
    for m in bpy.data.objects[k].data.materials:
        for n in m.node_tree.nodes:
            if n.type in ("MIX", "MIX_RGB") and getattr(n, "blend_type", "") == "MULTIPLY":
                (n.inputs["B"] if "B" in n.inputs else n.inputs[2]).default_value = fac
    print("TINT", k, [round(x, 3) for x in fac])
if "--flat" in argv:                            # diagnostics: no normal maps
    for o in bpy.data.objects:
        for m in (o.data.materials if o.type == "MESH" else []):
            for l in list(m.node_tree.links):
                if l.to_node.type == "BSDF_PRINCIPLED" and l.to_socket.name == "Normal":
                    m.node_tree.links.remove(l)
if POSE:
    sys.path.insert(0, str(Path(__file__).parent))
    from rig_poses import Poser  # noqa: E402
    poser = Poser(bpy.data.objects["goose_rig"])
    poser.reset()
    getattr(poser, POSE)()
    bpy.context.view_layer.update()
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = RES
sc.view_settings.view_transform = "Standard"
sc.world = bpy.data.worlds.new("w")
sc.world.color = (0.85, 0.85, 0.85)
for i, (r, e) in enumerate([((50, 0, 30), 3.0), ((60, 0, 200), 1.5)]):
    L = bpy.data.objects.new(f"cl{i}", bpy.data.lights.new(f"cl{i}", "SUN"))
    L.data.energy = e
    L.rotation_euler = [math.radians(a) for a in r]
    sc.collection.objects.link(L)
cam = bpy.data.objects.new("ccam", bpy.data.cameras.new("ccam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = SIZE
sc.collection.objects.link(cam)
sc.camera = cam
tmp = ROOT / "renders" / "_tmp"
tmp.mkdir(parents=True, exist_ok=True)
row = []
for yaw in YAWS:
    y = math.radians(yaw)
    c = Vector((0, 0, Z))
    cam.location = c + Vector((5 * math.sin(y), -5 * math.cos(y), 0))
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = str(tmp / "cl.png")
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(sc.render.filepath)
    row.append(np.array(img.pixels[:]).reshape(RES, RES, 4)[::-1, :, :3])
    bpy.data.images.remove(img)
sheet = np.concatenate(row, 1)
h, w_, _ = sheet.shape
img = bpy.data.images.new("sheet", w_, h)
img.pixels = np.concatenate([sheet[::-1], np.ones((h, w_, 1))], -1).ravel().tolist()
img.filepath_raw = str(ROOT / "renders" / f"{CHAR}_closeup_{TAG}.png")
img.file_format = "PNG"
img.save()
print("RENDER", img.filepath_raw)
