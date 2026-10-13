"""Render the base goose as a chroma-key mannequin: front / left / rear / right orthographic views in one bright
colour, for the image generator to dress ("add the garment; keep the blue body and the background unchanged").

  blender -b --factory-startup --python scripts/key_views.py -- [--color 0,0.55,1] [--px 1536] [--out refs/key_views]
      [--with out/outfit_male-goose/shells/coat.glb,...]   (self-test: known garments over the key body)

Everything that is not the key hue in the dressed image is garment: an exact mask in a calibrated view of OUR body
(same pose, proportions, cameras), so it projects straight back onto the body, and silhouette-to-silhouette
distances in the front / side views are the ease in metres. Writes <out>/<view>.png (shaded key body on grey) and
<out>/cameras.json (ortho scale, pixels per metre, camera position / axes per view, image size).
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
KEY = [float(x) for x in opt("--color", "0,0.55,1").split(",")]
PX = opt("--px", 1536)
OUT = ROOT / opt("--out", "refs/key_views")
OUT.mkdir(parents=True, exist_ok=True)
ORTHO = 1.90                                    # m across the image height (the body is ~1.70 m)
TGT = Vector((0, 0, 0.88))

bpy.ops.wm.open_mainfile(filepath=str(ROOT / "out" / "base-goose" / "base_goose.blend"))
for o in list(bpy.data.objects):
    if o.type == "MESH" and o.name != "base_goose_game":
        bpy.data.objects.remove(o)
body = bpy.data.objects["base_goose_game"]
mat = bpy.data.materials.new("key")
mat.use_nodes = True
bs = mat.node_tree.nodes["Principled BSDF"]
bs.inputs["Base Color"].default_value = (*KEY, 1)
bs.inputs["Roughness"].default_value = 0.8
body.data.materials.clear()
body.data.materials.append(mat)
for p in body.data.polygons:
    p.material_index = 0
for path in [x for x in opt("--with", "").split(",") if x]:     # self-test: real shells (their own materials)
    bpy.ops.import_scene.gltf(filepath=str(ROOT / path))
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x, sc.render.resolution_y = int(PX * 2 / 3), PX
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.55, 0.55, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
sc.world = w
for i, (rot, en) in enumerate([((50, 0, 30), 2.5), ((60, 0, 200), 1.2), ((80, 0, 110), 0.8)]):
    L = bpy.data.objects.new(f"l{i}", bpy.data.lights.new(f"l{i}", "SUN"))
    L.data.energy = en
    L.rotation_euler = [math.radians(a) for a in rot]
    sc.collection.objects.link(L)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = ORTHO * 1.0          # Blender: ortho_scale spans the LARGER image side (the height here)
sc.collection.objects.link(cam)
sc.camera = cam
cams = {"ortho_m_height": ORTHO, "px_per_m": PX / ORTHO, "size_px": [sc.render.resolution_x, PX],
        "target": list(TGT), "views": {}}
for view, az in (("front", 0), ("left", 90), ("rear", 180), ("right", -90)):
    a = math.radians(az)
    d = Vector((math.sin(a), -math.cos(a), 0.0))          # camera direction from the target (yaw 0: in front, -Y)
    cam.location = TGT + d * 6
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    M = cam.matrix_world
    sc.render.filepath = str(OUT / f"{view}.png")
    bpy.ops.render.render(write_still=True)
    cams["views"][view] = {"yaw_deg": az, "location": list(cam.location), "right": list(M.col[0][:3]),
                           "up": list(M.col[1][:3]), "back": list(M.col[2][:3])}
(OUT / "cameras.json").write_text(json.dumps(cams, indent=1), encoding="utf-8")
print("KEY", OUT)
