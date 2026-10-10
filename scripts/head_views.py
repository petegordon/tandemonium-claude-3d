"""Calibrated orthographic head views of the hi mesh with a 1 cm grid overlay, for placing
eyes and other head features by eye. Prints pixel->metre mapping per view.

  blender -b --factory-startup --python scripts/head_views.py -- --char male [--obj hi|game]
Writes renders/<char>_head_{right,left,front}.png (right = view from +X).
"""
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Euler

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1] if "--char" in argv else "male"
OBJ = argv[argv.index("--obj") + 1] if "--obj" in argv else "hi"
ROOT = Path(__file__).resolve().parents[1]
RES, SPAN = 800, 0.40          # px, metres covered by the view
ZC_FRAC = 0.86                 # view centre height (fraction of model height)

bpy.ops.wm.open_mainfile(filepath=str(ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_goose.blend"))
ob = bpy.data.objects[f"{CHAR}_goose_{OBJ}"]
for o in bpy.data.objects:
    o.hide_render = o is not ob
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = RES
sc.view_settings.view_transform = "Standard"
sc.world = sc.world or bpy.data.worlds.new("w")
sc.world.color = (1, 1, 1)
co = np.array([v.co[:] for v in ob.data.vertices])
zc = ZC_FRAC * co[:, 2].max()
head = co[np.abs(co[:, 2] - zc) < 0.1]
xc, yc = float(np.median(head[:, 0])), float(np.median(head[:, 1]))
cam_d = bpy.data.cameras.new("c")
cam_d.type, cam_d.ortho_scale = "ORTHO", SPAN
cam = bpy.data.objects.new("c", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
light = bpy.data.objects.new("l", bpy.data.lights.new("l", "SUN"))
light.data.energy = 3
sc.collection.objects.link(light)
# view: (name, location offset, rotation, image-right axis (idx, sign))
VIEWS = [("right", (1, 0, 0), (90, 0, 90), (1, 1)), ("left", (-1, 0, 0), (90, 0, -90), (1, -1)),
         ("front", (0, -1, 0), (90, 0, 0), (0, 1))]
for name, d, rot, (ax, sg) in VIEWS:
    cam.location = (xc + d[0], yc + d[1], zc)
    cam.rotation_euler = Euler([np.radians(r) for r in rot])
    light.rotation_euler = cam.rotation_euler
    out = ROOT / "renders" / f"{CHAR}_head_{name}.png"
    sc.render.filepath = str(out)
    bpy.ops.render.render(write_still=True)
    # grid overlay: 1 cm lines, 5 cm darker; label mapping
    img = bpy.data.images.load(str(out))
    px = np.array(img.pixels[:], np.float32).reshape(RES, RES, 4)
    h0 = (xc, yc)[ax]
    for k in range(-20, 21):
        p = int(round((k * 0.01 / SPAN + 0.5) * RES))
        if 0 <= p < RES:
            a = 0.35 if k % 5 == 0 else 0.12
            px[:, p, :3] = px[:, p, :3] * (1 - a) + np.array([0, 0.4, 1]) * a
            px[p, :, :3] = px[p, :, :3] * (1 - a) + np.array([0, 0.4, 1]) * a
    img.pixels.foreach_set(px.ravel())
    img.save()
    print(f"VIEW {name}: image-right axis {'XYZ'[ax]} sign {sg}; centre ({'XYZ'[ax]}={sg*0 + h0:.4f}, Z={zc:.4f}); "
          f"metres = centre + (px - 400)/{RES/SPAN:.0f} along right, Z = {zc:.4f} + (400 - row)/{RES/SPAN:.0f}; "
          f"grid lines every 1 cm from centre")

# --pick view:px:row[,view:px:row...] -> raycast each pixel onto the mesh, print point+normal
if "--pick" in argv:
    from mathutils import Vector
    dg = bpy.context.evaluated_depsgraph_get()
    vmap = {v[0]: v for v in VIEWS}
    for spec in argv[argv.index("--pick") + 1].split(","):
        name, pxs, rows = spec.split(":")
        _, d, rot, _ = vmap[name]
        cam.location = (xc + d[0], yc + d[1], zc)
        cam.rotation_euler = Euler([np.radians(r) for r in rot])
        bpy.context.view_layer.update()
        mw = cam.matrix_world
        right, up, fwd = mw.col[0].xyz, mw.col[1].xyz, -mw.col[2].xyz
        o = mw.translation + right * ((float(pxs) - RES / 2) * SPAN / RES) + up * ((RES / 2 - float(rows)) * SPAN / RES)
        hit, loc, nrm, *_ = sc.ray_cast(dg, o, fwd)
        print(f"PICK {spec}: hit={hit} point={tuple(round(c, 4) for c in loc)} normal={tuple(round(c, 3) for c in nrm)}")
