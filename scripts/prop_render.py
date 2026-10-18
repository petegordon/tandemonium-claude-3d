"""Turntable sheet for prop GLBs: each GLB is one row, views at the given yaws (Eevee, orthographic, grey bg).

  blender -b --factory-startup --python scripts/prop_render.py -- --out renders/x.png [--yaws 0,90,180,270,35]
      [--px 512] [--elev 8] a.glb b.glb ...
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]


def opt(name, default, cast=str):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


OUT = Path(opt("--out", "renders/prop.png")).resolve()
YAWS = [float(y) for y in opt("--yaws", "0,90,180,270,35").split(",")]
PX = opt("--px", 512, int)
ELEV = opt("--elev", 8.0, float)
skip = {"--out", "--yaws", "--px", "--elev"}
glbs, i = [], 0
while i < len(argv):
    if argv[i] in skip:
        i += 2
        continue
    if argv[i].endswith(".glb"):
        glbs.append(Path(argv[i]).resolve())
    i += 1


def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [e.identifier for e in
        bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE"
    sc.render.resolution_x = sc.render.resolution_y = PX
    sc.render.film_transparent = False
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.56, 0.58, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    sc.world = w
    sc.view_settings.view_transform = "Standard"
    for rot, e in (((50, 0, 30), 3.0), ((60, 0, 200), 1.5)):
        ld = bpy.data.lights.new("sun", "SUN")
        ld.energy = e
        lo = bpy.data.objects.new("sun", ld)
        lo.rotation_euler = [math.radians(r) for r in rot]
        sc.collection.objects.link(lo)


def render_all():
    setup()
    sc = bpy.context.scene
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    sc.collection.objects.link(cam)
    sc.camera = cam
    tiles = []
    for gi, g in enumerate(glbs):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(g))
        obs = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
        root = bpy.data.objects.new(f"root{gi}", None)
        sc.collection.objects.link(root)
        for o in bpy.data.objects:
            if o not in before and o is not root and o.parent is None:
                o.parent = root
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ Vector(c) for o in obs for c in o.bound_box]
        lo = Vector([min(p[k] for p in pts) for k in range(3)])
        hi = Vector([max(p[k] for p in pts) for k in range(3)])
        ctr, size = (lo + hi) / 2, max(hi - lo)
        cam.data.ortho_scale = size * 1.15
        for yaw in YAWS:
            a, e = math.radians(yaw), math.radians(ELEV)
            d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
            cam.location = ctr + d * size * 4
            cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
            p = OUT.parent / f"_{OUT.stem}_{gi}_{int(yaw)}.png"
            sc.render.filepath = str(p)
            bpy.ops.render.render(write_still=True)
            tiles.append((gi, yaw, p))
        for o in bpy.data.objects:
            if o not in before:
                o.hide_render = True
    # stitch with Blender images (no PIL in Blender's python)
    import numpy as np
    rows = []
    for gi in range(len(glbs)):
        row = []
        for _, _, p in [t for t in tiles if t[0] == gi]:
            im = bpy.data.images.load(str(p))
            a = np.array(im.pixels[:], np.float32).reshape(PX, PX, 4)
            row.append(a)
        rows.append(np.concatenate(row, 1))
    sheet = np.concatenate(rows[::-1], 0)
    out = bpy.data.images.new("sheet", sheet.shape[1], sheet.shape[0], alpha=True)
    out.pixels = sheet.ravel()
    out.filepath_raw = str(OUT)
    out.file_format = "PNG"
    out.save()
    for t in tiles:
        t[2].unlink()
    print("[prop_render]", OUT)


render_all()
