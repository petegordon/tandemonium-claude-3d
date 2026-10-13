"""Line a garment shell: a copy of its cloth faces 1.5 mm inside, normals flipped, in a lining material -- so the
inside seen at the tails' split, the cuffs and the open front is lining-coloured, not the outer cloth's back faces.

  blender -b --factory-startup --python scripts/add_lining.py -- --piece coat [--char outfit_male_victorian]
      [--color 92,58,38] [--rough 0.6] [--inset 0.0015] [--zmax 9] [--glb shells/coat.glb] [--out shells/coat.glb]

Only the first material's faces (the cloth) below --zmax are lined. The lining keeps the cloth's UVs (unused: one
flat colour) and is joined into the shell; dress_goose.py skins it from the nearest garment vertices like the rest.
"""
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_victorian")
PIECE = opt("--piece", "coat")
D = ROOT / "out" / f"{CHAR}-goose"
GLB = D / opt("--glb", f"shells/{PIECE}.glb")
OUT = D / opt("--out", f"shells/{PIECE}.glb")
COL = [int(x) for x in opt("--color", "92,58,38").split(",")]
INSET, ZMAX = opt("--inset", 0.0015), opt("--zmax", 9.0)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
gar = next(o for o in bpy.data.objects if o.type == "MESH")
me = gar.data
name = f"{CHAR}_{PIECE}_lining"
if any(m and m.name.startswith(name) for m in me.materials):
    raise SystemExit("already lined")
mat = bpy.data.materials.new(name)
mat.use_nodes = True
bs = mat.node_tree.nodes["Principled BSDF"]
c = np.array(COL) / 255.0
bs.inputs["Base Color"].default_value = tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)
bs.inputs["Roughness"].default_value = opt("--rough", 0.6)
me.materials.append(mat)
li = len(me.materials) - 1
M = gar.matrix_world
bm = bmesh.new()
bm.from_mesh(me)
bm.normal_update()
src = [f for f in bm.faces if f.material_index == 0 and (M @ f.calc_center_median()).z < ZMAX]
res = bmesh.ops.duplicate(bm, geom=src)
bm.normal_update()
new_faces = [g for g in res["geom"] if isinstance(g, bmesh.types.BMFace)]
new_verts = [g for g in res["geom"] if isinstance(g, bmesh.types.BMVert)]
for v in new_verts:
    v.co = v.co - v.normal * INSET
for f in new_faces:
    f.material_index = li
bmesh.ops.reverse_faces(bm, faces=new_faces)
bm.to_mesh(me)
bm.free()
me.update()
bpy.ops.object.select_all(action="DESELECT")
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.export_scene.gltf(filepath=str(OUT), export_format="GLB", use_selection=True, export_tangents=True)
print("LINED", PIECE, len(new_faces), "faces", COL)
