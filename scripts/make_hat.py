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
STYLE = H.get("style", "bowler")
if STYLE == "top":       # top hat: flat top, crisp rounded edge, straight sides flaring slightly to the top
    flare = H.get("crown_flare", 1.06)
    for k_, z_ in ((0.12, ctop), (0.6, ctop), (0.92, ctop - 0.001), (0.985, ctop - 0.004), (1.0 * flare, ctop - 0.010),
                   (0.985 * flare, ctop - 0.03)):
        prof.append(("crown", k_, z_, 0.0, 0))
    n_ = 6
    zb_ = cbase + band_h + 0.004
    for i in range(1, n_ + 1):
        t = i / n_
        prof.append(("crown", flare * (1 - t) * 0.985 + 1.0 * t, ctop - 0.03 - (ctop - 0.03 - zb_) * t, 0.0, 0))
else:
    for k_, z_ in ((0.12, ctop), (0.3, ctop - 0.0015), (0.45, ctop - 0.004), (0.58, ctop - 0.0075), (0.7, ctop - 0.013),
                   (0.86, ctop - 0.025), (0.95, ctop - 0.038), (1.0, ctop - 0.052)):
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
PL = H.get("plume")


def band_point(PL_):
    """Point on the band at PL["angle_deg"] from the front toward PL["side"], and the band's outward normal there."""
    th = math.radians(PL_.get("angle_deg", 90))
    sg_ = PL_.get("side", 1)
    px = Vector((cc[0] + sg_ * math.sin(th) * ca[0] * 1.03, cc[1] - math.cos(th) * ca[1] * 1.03, cbase + band_h / 2))
    n_ = Vector((sg_ * math.sin(th) / ca[0], -math.cos(th) / ca[1], 0)).normalized()
    return px, n_


if PL:                    # the plume's brass medallion: a rimmed disc with a domed boss, on the band
    mp, mn = band_point(PL)
    rot = Vector((0, 0, 1)).rotation_difference(mn).to_matrix()
    r0 = PL.get("medallion_r", 0.016)
    for rad1, rad2, dep, off in ((r0, r0 * 0.92, 0.003, 0.0015), (r0 * 0.8, r0 * 0.78, 0.0016, 0.0035)):
        res = bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=rad1, radius2=rad2, depth=dep)
        for v in res["verts"]:
            v.co = rot @ (v.co + Vector((0, 0, off))) + mp
        for f in {f for v in res["verts"] for f in v.link_faces}:
            f.material_index = 2
    res = bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=1.0)
    for v in res["verts"]:
        v.co = rot @ Vector((v.co.x * r0 * 0.42, v.co.y * r0 * 0.42, v.co.z * 0.004 + 0.0045)) + mp
    for f in {f for v in res["verts"] for f in v.link_faces}:
        f.material_index = 2
for sg in ((1, -1) if H.get("buckles", True) else ()):
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
for nm, col, rough, metal in (("felt", H["colors"][next(iter(H["colors"]))], H.get("felt_rough", 0.9), 0.0),
                              ("band", H.get("band_color", [32, 30, 30]), 0.5, 0.0),
                              ("brass", H.get("brass_color", [176, 132, 62]), 0.3, 1.0),
                              ("plume", (H.get("plume") or {}).get("color", [200, 140, 60]), 0.7, 0.0)):
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


def feather_texture(seed, W=256, Hh=640):
    """RGBA feather (v: base -> tip, u: across, rachis at u=0.5): a tapered vane of slanted barbs in clumps with
    ragged ends and a few splits, a downy base, a cream rachis; brown near the rachis to gold at the edges."""
    rng = np.random.default_rng(seed)
    v = (np.arange(Hh)[:, None] + 0.5) / Hh
    u = (np.arange(W)[None, :] + 0.5) / W
    sx = u - 0.5
    d = np.abs(sx) * 2                                           # 0 at the rachis, 1 at the strip edge
    hw = 0.96 * np.sin(np.pi * np.clip((v - 0.05) / 1.0, 0, 1)) ** 0.5 * (1 - 0.18 * v)
    hw = np.where(v < 0.07, 0.0, hw) * np.where(sx < 0, 0.82, 1.0)   # bare quill at the base; asymmetric vane
    p = v - d * 0.22                                             # barb coordinate (barbs sweep toward the tip)
    NC = 46
    ci = np.clip((p * NC).astype(int) + 60, 0, NC + 120)
    side = (sx > 0).astype(int)
    reach = rng.uniform(0.72, 1.02, (NC + 121, 2))[ci, side]       # ragged clump ends
    split = rng.random((NC + 121, 2))[ci, side] < 0.28
    fr = (p * NC) % 1.0
    gap = split & (fr < 0.16) & (d > 0.18)
    a = (d < hw * reach) & ~gap
    down = (v < 0.16) & (d < hw * 1.1)                            # fluffy afterfeather near the base
    a = np.where(v < 0.16, down & (rng.random((Hh, W)) < 0.5 + 4.0 * (v - 0.07)), a)
    t = np.clip(d / np.maximum(hw, 1e-3), 0, 1)
    brown, gold, pale = np.array([96, 60, 30.0]), np.array([212, 158, 78.0]), np.array([238, 206, 140.0])
    col = brown + (gold - brown) * (t ** 0.6)[..., None]
    col = col + (pale - col) * (np.clip((v - 0.55) / 0.45, 0, 1) * 0.55 * t)[..., None]
    col *= (0.82 + 0.18 * (0.5 + 0.5 * np.sin(p * 2 * np.pi * 260)))[..., None]   # individual barbs
    col *= rng.uniform(0.86, 1.1, (NC + 121, 2))[ci, side][..., None]
    rach = np.abs(sx) < 0.016 * (1 - 0.65 * v) + 0.003
    col = np.where(rach[..., None], np.array([226, 204, 160.0]), col)
    a = a | (rach & (v < 0.985))
    rgba = np.concatenate([np.clip(col, 0, 255) / 255.0, a[..., None].astype(float)], -1)
    im = bpy.data.images.new(f"feather_{seed}", W, Hh, alpha=True)
    im.pixels = rgba.ravel().tolist()                            # row 0 = v=0 (the base)
    im.filepath_raw = str(OUT / f"_feather_{seed}.png")
    im.file_format = "PNG"
    im.save()
    im.pack()
    return im


if PL:
    mp, mn = band_point(PL)
    up = Vector((0, 0, 1))
    rear = up.cross(mn).normalized() * PL.get("side", 1)          # along the band, toward the back
    if rear.y < 0:
        rear = -rear
    fm = bpy.data.materials.new(f"{CHAR}_hat_feather")
    fm.use_nodes = True
    fm.use_backface_culling = False
    fm.surface_render_method = "DITHERED"
    nt = fm.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.62
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = feather_texture(7)
    rnd = nt.nodes.new("ShaderNodeMath")
    rnd.operation = "ROUND"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(tex.outputs["Alpha"], rnd.inputs[0])
    nt.links.new(rnd.outputs[0], bsdf.inputs["Alpha"])
    fb = bmesh.new()
    uvl = fb.loops.layers.uv.new("UVMap")
    NL, NW = 28, 7
    for fi, F in enumerate(PL["feathers"]):
        L_, W_ = F["length"], F["width"]
        tilt, curl_ = math.radians(F["tilt_deg"]), math.radians(F["curl_deg"])
        az = math.radians(F["azimuth_deg"])                     # 0: out from the band, 90: toward the back
        hdir = (mn * math.cos(az) + rear * math.sin(az)).normalized()
        base = mp + mn * 0.003 + up * F.get("base_dz", 0.006) + rear * F.get("base_back", 0.0)
        c_ = base.copy()
        rows = []
        for i in range(NL + 1):
            t = i / NL
            a_ = tilt + curl_ * t ** 1.6
            dirv = (up * math.cos(a_) + hdir * math.sin(a_)).normalized()
            if i:
                c_ = c_ + dirv * (L_ / NL)
            face_n = (mn * 0.6 + hdir * 0.4 + Vector((0, -1, 0)) * PL.get("face_front", 0.0)).normalized()
            sd = dirv.cross(face_n).normalized()
            tw = math.radians(F.get("twist_deg", 0)) * t
            sd = (sd * math.cos(tw) + dirv.cross(sd) * math.sin(tw)).normalized()
            nrm = sd.cross(dirv).normalized()
            env = 0.35 + 0.65 * min(1.0, t / 0.18)
            hw = W_ / 2 * env
            row_ = []
            for j in range(NW):
                uu = j / (NW - 1) * 2 - 1
                fold = F.get("fold", 0.25) * hw * abs(uu) + 0.004 * math.sin(math.pi * t) * uu * uu
                row_.append((fb.verts.new(c_ + sd * hw * uu + nrm * fold), ((uu + 1) / 2, t)))
            rows.append(row_)
        for i in range(NL):
            for j in range(NW - 1):
                q = (rows[i][j], rows[i][j + 1], rows[i + 1][j + 1], rows[i + 1][j])
                f = fb.faces.new([x[0] for x in q])
                for lp, (_, uv) in zip(f.loops, q):
                    lp[uvl].uv = uv
    fme = bpy.data.meshes.new("feathers")
    fb.to_mesh(fme)
    fb.free()
    fme.materials.append(fm)
    for pg in fme.polygons:
        pg.use_smooth = True
    fo = bpy.data.objects.new("feathers", fme)
    sc0 = bpy.context.scene
    sc0.collection.objects.link(fo)
    me.uv_layers[0].name = "UVMap"
    bpy.ops.object.select_all(action="DESELECT")
    fo.select_set(True)
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.join()
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
