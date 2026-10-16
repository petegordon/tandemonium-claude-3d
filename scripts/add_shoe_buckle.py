"""Square silver buckles on 18th-century shoes: a leather strap across the instep with a rectangular silver frame on it,
joined into the boots shell in their own materials (leather strap, metallic silver).

  blender -b --factory-startup --python scripts/add_shoe_buckle.py -- --char outfit_male_georgian
      [--t 0.6] [--w 0.036]  (defaults: chars json "shoe_buckle")
       [--h 0.028] [--bar 0.0045] [--color 214,216,220] [--glb shells/boots.glb] [--out shells/boots.glb]

Placement per shoe: x = boot_design centre_x (mirrored), y at --t along the foot (0 heel -> 1 toe), a ray down onto the
shoe's top; the buckle lies in the surface's tangent plane there, 1.5 mm proud, long side across the foot.
"""
import json
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_georgian")
D = ROOT / "out" / f"{CHAR}-goose"
GLB, OUTF = D / opt("--glb", "shells/boots.glb"), D / opt("--out", "shells/boots.glb")
CFG = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
BD, SB = CFG["boot_design"], CFG.get("shoe_buckle", {})       # (recipe "shoe_buckle" {t, w, h, bar} = the defaults)
T, W, H, BAR = (opt(f"--{k}", float(SB.get(k, dv))) for k, dv in (("t", 0.6), ("w", 0.036), ("h", 0.028), ("bar", 0.0045)))
COL = [int(c) for c in opt("--color", ",".join(str(c) for c in SB.get("color", [214, 216, 220]))).split(",")]


def lin(c):
    c = np.array(c[:3]) / 255.0
    return tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
shoe = next(o for o in bpy.data.objects if o.type == "MESH")
M = shoe.matrix_world
bvh = BVHTree.FromPolygons([M @ v.co for v in shoe.data.vertices], [tuple(p.vertices) for p in shoe.data.polygons])
zoff = BD.get("z_off", 0.0)
bm = bmesh.new()


def box(frame, cx, cy, sx, sy, sz, mat):
    res = bmesh.ops.create_cube(bm, size=1.0)
    for v in res["verts"]:
        v.co = frame @ Vector((cx + v.co.x * sx, cy + v.co.y * sy, v.co.z * sz))
    for f in {f for v in res["verts"] for f in v.link_faces}:
        f.material_index = mat
    bmesh.ops.bevel(bm, geom=[e for e in {e for v in res["verts"] for e in v.link_edges}], offset=min(sx, sy, sz) * 0.3,
                    segments=1, affect="EDGES")


placed = []
for sg in (1, -1):
    x = sg * BD["centre_x"]
    y = BD["heel_y"] + (BD["toe_y"] - BD["heel_y"]) * T
    loc, nrm, _, _ = bvh.ray_cast(Vector((x, y, 0.5 + zoff)), Vector((0, 0, -1)), 1.0)
    if loc is None:
        print("no shoe under", x, y)
        continue
    n = nrm.normalized()
    ax = Vector((1, 0, 0))
    ax = (ax - n * ax.dot(n)).normalized()
    ay = n.cross(ax).normalized()
    frame = Matrix.Translation(loc + n * 0.0015) @ Matrix(((ax.x, ay.x, n.x, 0), (ax.y, ay.y, n.y, 0), (ax.z, ay.z, n.z, 0), (0, 0, 0, 1)))
    box(frame, 0, 0, W * 1.5, H * 0.75, 0.002, 0)                     # the strap under it
    t_ = 0.0028
    for cx, cy, sx, sy in ((0, H / 2 - BAR / 2, W, BAR), (0, -H / 2 + BAR / 2, W, BAR),
                           (W / 2 - BAR / 2, 0, BAR, H), (-W / 2 + BAR / 2, 0, BAR, H)):
        box(Matrix.Translation(frame @ Vector((0, 0, 0.0018))) @ frame.to_3x3().to_4x4(), cx, cy, sx, sy, t_, 1)
    box(Matrix.Translation(frame @ Vector((0, 0, 0.0022))) @ frame.to_3x3().to_4x4(), 0, 0, BAR * 0.6, H * 0.95, 0.0016, 1)  # chape bar
    placed.append([round(c, 3) for c in loc])
me = bpy.data.meshes.new("buckles")
bm.to_mesh(me)
bm.free()
bo = bpy.data.objects.new("buckles", me)
bpy.context.scene.collection.objects.link(bo)
for nm, col, rough, metal in (("strap", SB.get("strap_color", [22, 21, 21]), 0.35, 0.0), ("silver", COL, SB.get("rough", 0.15), SB.get("metal", 1.0))):
    m = bpy.data.materials.new(f"{CHAR}_boots_buckle_{nm}")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = lin(col)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    me.materials.append(m)
bm2 = bmesh.new()
bm2.from_mesh(me)
bmesh.ops.triangulate(bm2, faces=bm2.faces[:])
bm2.to_mesh(me)
bm2.free()
uv = me.uv_layers.new(name=shoe.data.uv_layers[0].name if shoe.data.uv_layers else "UVMap")
for o in bpy.data.objects:
    o.select_set(False)
bo.select_set(True)
shoe.select_set(True)
bpy.context.view_layer.objects.active = shoe
bpy.ops.object.join()
bpy.ops.export_scene.gltf(filepath=str(OUTF), use_selection=True, export_format="GLB", export_tangents=True)
print("BUCKLES", json.dumps({"at": placed, "out": str(OUTF)}))
