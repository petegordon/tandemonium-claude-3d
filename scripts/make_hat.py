"""Modelled bowler hat (male outfit): a lathe of a felt profile on ellipses fitted to the extracted hat,
with a ribbon band and a brass buckle on each side (refs/v3).

  blender -b --factory-startup --python scripts/make_hat.py -- --char outfit_male

Fit (chars json "hat_design"): brim ellipse (centre, semi-axes, height), crown ellipse + top height, measured
from pieces/hat.glb once and stored in the recipe. The brim edge curls up at the sides ("curl"), the crown is a
dome. Materials: felt (one baseColorFactor, recolourable), band, brass. Writes shells/hat.glb + .json and
renders/<char>_shell_hat.png.
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Euler, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1] if "--char" in argv else "outfit_male"
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{CHAR}-goose"
OUT = D / "shells"
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
H = cfg["hat_design"]
NA = H.get("segments", 48)


def srgb(c):
    c = np.array(c[:3]) / 255.0
    return tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)


bpy.ops.wm.read_factory_settings(use_empty=True)
bc, ba, bz = np.array(H["brim_c"]), np.array(H["brim_ax"]), H["brim_z"]
cc, ca, ctop = np.array(H["crown_c"]), np.array(H["crown_ax"]), H["crown_top"]
cbase = H.get("crown_base", bz + 0.004)
curl = H.get("curl", 0.014)
band_h = H.get("band_h", 0.016)


def ring(c, ax, z, zcurl=0.0):
    out = []
    for k in range(NA):
        th = 2 * math.pi * k / NA
        side = abs(math.sin(th))                          # sin: x side (curl up at the sides)
        out.append((c[0] + ax[0] * math.sin(th), c[1] - ax[1] * math.cos(th), z + zcurl * side ** 2))
    return out


def lerp(a, b, u):
    return a * (1 - u) + b * u


# profile, outside then underside then inside: (kind, param, z, curl, material)
prof = []
for k_, z_ in ((0.12, ctop), (0.3, ctop - 0.0015), (0.45, ctop - 0.004), (0.58, ctop - 0.0075), (0.7, ctop - 0.013), (0.86, ctop - 0.025), (0.95, ctop - 0.038),
               (1.0, ctop - 0.052)):
    prof.append(("crown", k_, z_, 0.0, 0))
zb0 = cbase + band_h
prof.append(("crown", 1.0, zb0 + 0.002, 0.0, 0))
prof.append(("crown", 1.03, zb0, 0.0, 1))                 # band (slightly proud)
prof.append(("crown", 1.03, cbase, 0.0, 1))
prof.append(("crown", 1.0, cbase - 0.002, 0.0, 0))
for u, dz, cu in ((0.25, -0.004, 0.2), (0.6, -0.005, 0.5), (0.88, -0.003, 0.85), (1.0, 0.002, 1.0),
                  (1.02, -0.003, 1.0), (0.98, -0.008, 0.9), (0.6, -0.010, 0.5), (0.2, -0.010, 0.2)):
    prof.append(("brim", u, bz + dz, cu, 0))
prof.append(("crown", 0.96, cbase - 0.008, 0.0, 0))          # inside the crown
prof.append(("crown", 0.92, ctop - 0.03, 0.0, 0))
prof.append(("crown", 0.5, ctop - 0.01, 0.0, 0))

rings = []
for kind, u, z, cu, mat in prof:
    if kind == "crown":
        rings.append((ring(cc, ca * u, z), mat))
    else:
        rings.append((ring(lerp(cc, bc, u), lerp(ca, ba, u), z, curl * cu), mat))

bm = bmesh.new()
vs = [[bm.verts.new(p) for p in r] for r, _ in rings]
top = bm.verts.new((cc[0], cc[1], ctop + 0.001))
for k in range(NA):
    bm.faces.new([top, vs[0][(k + 1) % NA], vs[0][k]])
for i in range(len(vs) - 1):
    mat = rings[i][1] if rings[i][1] == rings[i + 1][1] else 0
    for k in range(NA):
        f = bm.faces.new([vs[i][k], vs[i][(k + 1) % NA], vs[i + 1][(k + 1) % NA], vs[i + 1][k]])
        f.material_index = mat
# close the inner crown with a fan (hidden)
inner = bm.verts.new((cc[0], cc[1], ctop - 0.008))
for k in range(NA):
    bm.faces.new([inner, vs[-1][k], vs[-1][(k + 1) % NA]])
# brass buckles: small raised rectangles on the band at each side
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
for sg in (1, -1):
    cx = cc[0] + sg * ca[0] * 1.035
    cy = cc[1]
    cz = cbase + band_h / 2
    res = bmesh.ops.create_cube(bm, size=1.0)
    for v in res["verts"]:
        v.co = Vector((cx + v.co.x * 0.004, cy + v.co.y * 0.018, cz + v.co.z * 0.014))
    for f in {f for v in res["verts"] for f in v.link_faces}:
        f.material_index = 2
me = bpy.data.meshes.new("hat_shell")
bm.to_mesh(me)
bm.free()
o = bpy.data.objects.new("hat_shell", me)
bpy.context.scene.collection.objects.link(o)
for nm, col, rough, metal in (("felt", H["colors"][next(iter(H["colors"]))], 0.9, 0.0),
                              ("band", H.get("band_color", [32, 30, 30]), 0.5, 0.0),
                              ("brass", H.get("brass_color", [176, 132, 62]), 0.3, 1.0)):
    m = bpy.data.materials.new(f"{CHAR}_hat_{nm}")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = srgb(col)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    me.materials.append(m)
bpy.context.view_layer.objects.active = o
o.select_set(True)
bpy.ops.object.shade_smooth()
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.01)
bpy.ops.object.mode_set(mode="OBJECT")
tris = sum(len(p.vertices) - 2 for p in me.polygons)
OUT.mkdir(exist_ok=True)
bpy.ops.export_scene.gltf(filepath=str(OUT / "hat.glb"), use_selection=True, export_format="GLB")
(OUT / "hat.json").write_text(json.dumps({"char": CHAR, "piece": "hat", "tris": tris, "source": "make_hat.py (modelled)",
                                          "colors": H["colors"]}, indent=1), encoding="utf-8")
print("SHELL hat", tris)

# render: front / side / back / 3-4
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = 480
sc.view_settings.view_transform = "Standard"
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.92, 0.92, 0.92, 1)
sc.world = w
for i, (r, e) in enumerate([((50, 0, 30), 3.0), ((60, 0, 200), 1.5)]):
    L = bpy.data.objects.new(f"l{i}", bpy.data.lights.new(f"l{i}", "SUN"))
    L.data.energy = e
    L.rotation_euler = Euler([math.radians(a) for a in r])
    sc.collection.objects.link(L)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = 0.3
sc.collection.objects.link(cam)
sc.camera = cam
row = []
for yaw in (0, 90, 180, 35):
    y = math.radians(yaw)
    c = Vector((cc[0], cc[1], (bz + ctop) / 2))
    cam.location = c + Vector((5 * math.sin(y), -5 * math.cos(y), 0.6))
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = str(ROOT / "renders" / "_tmp" / "hat.png")
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(sc.render.filepath)
    row.append(np.array(im.pixels[:]).reshape(480, 480, 4)[::-1, :, :3])
    bpy.data.images.remove(im)
sheet = np.concatenate(row, 1)
h, w_, _ = sheet.shape
im = bpy.data.images.new("sheet", w_, h)
im.pixels = np.concatenate([sheet[::-1], np.ones((h, w_, 1))], -1).ravel().tolist()
im.filepath_raw = str(ROOT / "renders" / f"{CHAR}_shell_hat.png")
im.file_format = "PNG"
im.save()
print("RENDER", im.filepath_raw)
