"""Trim a garment shell's ragged top (or bottom) edge with one straight plane cut: everything above (below) the plane
goes, the cut follows the plane exactly. UVs, materials and skin-weight lookup (by position) are unaffected.

  blender -b --factory-startup --python scripts/trim_edge.py -- --piece breeches --z 0.972 [--below]
      [--rise 0.0] [--y0 -0.1] [--char outfit_male_victorian] [--glb shells/breeches.glb] [--out shells/breeches.glb]

The plane is z = --z + --rise * (y - --y0) (a back rise tilts it). Only the first material's faces (the cloth) are
cut; buttons / trims above the plane are left alone.
"""
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_victorian")
PIECE = opt("--piece", "breeches")
D = ROOT / "out" / f"{CHAR}-goose"
GLB = D / opt("--glb", f"shells/{PIECE}.glb")
OUT = D / opt("--out", f"shells/{PIECE}.glb")
Z, RISE, Y0 = opt("--z", 0.97), opt("--rise", 0.0), opt("--y0", -0.1)
BELOW = "--below" in argv

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
gar = next(o for o in bpy.data.objects if o.type == "MESH")
bpy.ops.object.select_all(action="DESELECT")
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = gar.data
bm = bmesh.new()
bm.from_mesh(me)
cloth = [f for f in bm.faces if f.material_index == 0]
geom = list({v for f in cloth for v in f.verts}) + list({e for f in cloth for e in f.edges}) + cloth
no = Vector((0, -RISE, 1)).normalized()
co = Vector((0, Y0, Z))
res = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no, clear_outer=not BELOW, clear_inner=BELOW)
bm.faces.ensure_lookup_table()
n_after = len([f for f in bm.faces if f.material_index == 0])
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
bm.to_mesh(me)
bm.free()
me.update()
bpy.ops.export_scene.gltf(filepath=str(OUT), export_format="GLB", use_selection=True, export_tangents=True)
print("TRIM", PIECE, "cloth faces", len(cloth), "->", n_after)
