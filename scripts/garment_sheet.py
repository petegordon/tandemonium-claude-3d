"""Sheet of the garments on their own (no body): one column per piece, front / side / back rows,
each piece framed on itself and labelled.

  blender -b --factory-startup --python scripts/garment_sheet.py -- --char outfit_male \
      [--pieces breeches,shirt,waistcoat,coat,gloves,bowtie] -> renders/<char>_garments_sheet.png

Loads out/<char>-goose/shells/<piece>.glb ("<piece>@<part>.glb" add-ons are shown with their piece).
"""
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
PIECES = opt("--pieces", "breeches,shirt,waistcoat,coat,gloves,bowtie").split(",")
NAMES = {"waistcoat": "vest", "coat": "jacket"}
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{CHAR}-goose" / "shells"
RES = 480
YAWS = (0, 90, 180)

bpy.ops.wm.read_factory_settings(use_empty=True)
groups = {}
for pc in PIECES:
    obs = []
    for f in sorted(D.glob(f"{pc}*.glb")):
        if f.stem != pc and not f.stem.startswith(pc + "@"):
            continue
        before = set(bpy.context.scene.objects)
        bpy.ops.import_scene.gltf(filepath=str(f))
        obs += [o for o in bpy.context.scene.objects if o not in before and o.type == "MESH"]
    groups[pc] = obs
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = RES
sc.view_settings.view_transform = "Standard"
sc.render.film_transparent = False
w = bpy.data.worlds.new("w")
w.use_nodes = True
BGV = float(opt("--bg", 0.42))                    # mid grey: light and dark garments both read
w.node_tree.nodes["Background"].inputs[0].default_value = (BGV, BGV, BGV, 1)
sc.world = w
for i, (r, e) in enumerate([((50, 0, 30), 3.0), ((60, 0, 200), 1.5)]):
    L = bpy.data.objects.new(f"l{i}", bpy.data.lights.new(f"l{i}", "SUN"))
    L.data.energy = e
    L.rotation_euler = [math.radians(a) for a in r]
    sc.collection.objects.link(L)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
sc.collection.objects.link(cam)
sc.camera = cam
tmp = ROOT / "renders" / "_tmp"
tmp.mkdir(parents=True, exist_ok=True)
cols = []
for pc, obs in groups.items():
    if not obs:
        continue
    for o in bpy.context.scene.objects:
        if o.type == "MESH":
            o.hide_render = o not in obs
    V = np.array([o.matrix_world @ v.co for o in obs for v in o.data.vertices])
    if pc in ("gloves", "cuffs"):            # frame one hand (the pair is a metre apart)
        V = V[V[:, 0] > 0]
    lo, hi = V.min(0), V.max(0)
    ctr = (lo + hi) / 2
    cam.data.ortho_scale = max(hi - lo) * 1.12
    col = []
    for yaw in YAWS:
        y = math.radians(yaw)
        c = Vector(ctr)
        cam.location = c + Vector((5 * math.sin(y), -5 * math.cos(y), 0))
        cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = str(tmp / "gs.png")
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(sc.render.filepath)
        col.append(np.array(img.pixels[:]).reshape(RES, RES, 4)[::-1, :, :3])
        bpy.data.images.remove(img)
    cols.append((NAMES.get(pc, pc), np.concatenate(col, 0)))
sheet = np.concatenate([c for _, c in cols], 1)
h, w_, _ = sheet.shape
img = bpy.data.images.new("sheet", w_, h)
img.pixels = np.concatenate([sheet[::-1], np.ones((h, w_, 1))], -1).ravel().tolist()
out = ROOT / "renders" / f"{CHAR}_garments_sheet.png"
img.filepath_raw = str(out)
img.file_format = "PNG"
img.save()
print("SHEET", out, [n for n, _ in cols])
