"""Side-by-side close-ups (head+torso, front and 3/4) of several GLBs.

Run:
  blender -b --factory-startup --python scripts/closeup_compare.py -- out.png a.glb b.glb ...
      [--shots yaw:zc:scale,yaw:zc:scale]   (zc / scale are fractions of model height)
"""
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
SHOTS = [(0, 0.78, 0.48), (35, 0.78, 0.48), (180, 0.5, 0.62)]  # (yaw, z center, ortho scale)
if "--shots" in argv:
    i = argv.index("--shots")
    SHOTS = [tuple(float(x) for x in s.split(":")) for s in argv[i + 1].split(",")]
    argv = argv[:i] + argv[i + 2:]
OUT, GLBS = Path(argv[0]).resolve(), [Path(p).resolve() for p in argv[1:]]
RES = 768


def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.view_settings.view_transform = "Standard"
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.9, 0.9, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    sc.world = w
    for i, (rot, e) in enumerate([((50, 0, 30), 3.0), ((60, 0, 200), 1.5)]):
        L = bpy.data.lights.new(f"l{i}", "SUN")
        L.energy = e
        lo = bpy.data.objects.new(f"l{i}", L)
        lo.rotation_euler = Euler([math.radians(a) for a in rot])
        sc.collection.objects.link(lo)
    cam = bpy.data.cameras.new("cam")
    cam.type = "ORTHO"
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    return sc, co


def load(sc, glb):
    before = set(sc.objects)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    new = [o for o in sc.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    co = np.array([v.co for v in ob.data.vertices])
    lo, hi = co.min(0), co.max(0)
    c = Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]))
    ob.data.transform(Matrix.Scale(1.0 / (hi[2] - lo[2]), 4) @ Matrix.Translation(-c))
    for o in new:
        if o is not ob and o.name in bpy.data.objects:
            bpy.data.objects.remove(o)
    return ob


def shot(sc, co, yaw, zc, scale, path):
    y = math.radians(yaw)
    co.data.ortho_scale = scale
    co.location = Vector((5 * math.sin(y), -5 * math.cos(y), zc))
    co.rotation_euler = (Vector((0, 0, zc)) - co.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(str(path))
    px = np.array(img.pixels[:]).reshape(RES, RES, 4)[::-1, :, :3]
    bpy.data.images.remove(img)
    return px


sc, co = setup()
tmp = OUT.parent / "_tmp"
tmp.mkdir(parents=True, exist_ok=True)
rows = []
for i, g in enumerate(GLBS):
    ob = load(sc, g)
    rows.append([shot(sc, co, *s, tmp / f"cu_{i}_{j}.png") for j, s in enumerate(SHOTS)])
    bpy.data.objects.remove(ob)
sheet = np.concatenate([np.concatenate(r, 1) for r in rows], 0)
h, w, _ = sheet.shape
img = bpy.data.images.new("sheet", w, h)
img.pixels = np.concatenate([sheet[::-1], np.ones((h, w, 1))], -1).ravel().tolist()
img.filepath_raw = str(OUT)
img.file_format = "PNG"
img.save()
print("CLOSEUP", OUT)
