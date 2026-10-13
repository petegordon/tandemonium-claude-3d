"""Keep only the part of a garment shell inside a box (the rest is deleted): a garment worn under another that only
shows through an opening (the blouse in the cardigan's V) -- the hidden rest otherwise pokes through in poses.

  blender -b --factory-startup --python scripts/crop_shell.py -- --char outfit_female_cyclist --piece shirt
      --glb shells/variants/withshoes/shirt.glb --box xmin,xmax,ymin,ymax,zmin,zmax

A face is kept when its centre is inside the box; with --bisect the mesh is first cut along the box planes, so the
crop edge is a clean straight line (not a stair of whole faces). Weights / covers files are looked up by position,
so they still fit.
"""
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{opt('--char', 'outfit_female_cyclist')}-goose"
GLB = D / opt("--glb", "")
x0, x1, y0, y1, z0, z1 = [float(v) for v in opt("--box", "").split(",")]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
o = next(x for x in bpy.context.scene.objects if x.type == "MESH")
bm = bmesh.new()
bm.from_mesh(o.data)
M = o.matrix_world
if "--bisect" in argv:          # cut along each box plane first (object space = world here: imported glTF, no parent)
    Mi = M.inverted()
    for co, no in (((x0, 0, 0), (-1, 0, 0)), ((x1, 0, 0), (1, 0, 0)), ((0, y0, 0), (0, -1, 0)), ((0, y1, 0), (0, 1, 0)),
                   ((0, 0, z0), (0, 0, -1)), ((0, 0, z1), (0, 0, 1))):
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=Mi @ Vector(co), plane_no=Vector(no), clear_outer=True)
drop = []
for f in bm.faces:
    c = M @ f.calc_center_median()
    if not (x0 <= c.x <= x1 and y0 <= c.y <= y1 and z0 <= c.z <= z1):
        drop.append(f)
bmesh.ops.delete(bm, geom=drop, context="FACES")
bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
bm.to_mesh(o.data)
bm.free()
bpy.ops.object.select_all(action="DESELECT")
for x in bpy.context.scene.objects:
    x.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(GLB), use_selection=True, export_format="GLB")
print("CROP", GLB.name, "dropped", len(drop), "faces, kept", len(o.data.polygons))
