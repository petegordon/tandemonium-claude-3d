"""Close-up renders of each rider's hands on the grips (fit scene from argv).

  blender -b --factory-startup --python scripts/grip_closeup.py -- <fit.blend> <out_prefix>

Per grip (Grip_C_L/R, Grip_S_L/R): side (outside), top, and from behind-outside, ortho 0.40 m, grip bone marked
by a small red sphere; prints the wrist bend (forearm vs hand angle) of each rider.
"""
import math
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.open_mainfile(filepath=argv[0])
PREFIX = argv[1]
sc = bpy.context.scene
bike = bpy.data.objects["bike_rig"]
cam = bpy.data.objects.get("cam")
sc.camera = cam
cam.data.type = "ORTHO"
sc.render.resolution_x = sc.render.resolution_y = 600
mat = bpy.data.materials.new("mark")
mat.diffuse_color = (1, 0, 0, 1)
mat.use_nodes = True
mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (1, 0, 0, 1)
mat.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (1, 0, 0, 1)
mat.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 2.0

for o in bpy.data.objects:
    if o.type == "ARMATURE" and o.name != "bike_rig":
        for s in ("Left", "Right"):
            fa, h = o.pose.bones[f"{s}ForeArm"], o.pose.bones[f"{s}Hand"]
            a = (o.matrix_world.to_3x3() @ (fa.tail - fa.head)).normalized()
            b = (o.matrix_world.to_3x3() @ (h.tail - h.head)).normalized()
            print(f"WRIST {o.name} {s}: bend {math.degrees(a.angle(b)):.0f} deg, forearm dir {tuple(round(x, 2) for x in a)},"
                  f" hand dir {tuple(round(x, 2) for x in b)}")

for g in ("Grip_C_L", "Grip_C_R", "Grip_S_L", "Grip_S_R"):
    p = bike.matrix_world @ bike.pose.bones[g].head
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.008, location=p)
    m = bpy.context.object
    m.data.materials.append(mat)
    sx = 1 if g.endswith("L") else -1
    for view, d in (("out", Vector((sx, 0, 0))), ("top", Vector((0.001, 0, 1))), ("back", Vector((sx * 0.6, 1, 0.5)))):
        d.normalize()
        cam.location = p + d * 3
        cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
        cam.data.ortho_scale = 0.40
        sc.render.filepath = f"{PREFIX}_{g}_{view}.png"
        bpy.ops.render.render(write_still=True)
