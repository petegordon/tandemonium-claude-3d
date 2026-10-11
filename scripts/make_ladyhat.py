"""Modelled lady's hat (female outfit, refs/v3): small burgundy hat with a flat brim, a short crown wrapped in
gathered fabric puffs, three spiral rosettes at the front-left and a curving feather plume with serrated barbs.

  blender -b --factory-startup --python scripts/make_ladyhat.py -- --char outfit_female

Recipe: chars json "hat_design" (style "lady"): brim / crown ellipses measured from pieces/hat.glb, puffs,
rosettes, feather spine control points. Materials: felt, satin (puffs + rosettes), feather -- each one
baseColorFactor, recolourable together through "colors". Writes shells/hat.glb + .json and
renders/<char>_shell_hat.png. dress_goose.py skins it rigidly to the Head bone.
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
CHAR = argv[argv.index("--char") + 1] if "--char" in argv else "outfit_female"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / f"{CHAR}-goose" / "shells"
H = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))["hat_design"]
NA = H.get("segments", 48)


def srgb(c):
    c = np.array(c[:3]) / 255.0
    return tuple(np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)) + (1.0,)


bpy.ops.wm.read_factory_settings(use_empty=True)
bm = bmesh.new()
mat_of = {}


def add_grid(P_, mat, wrap_i=False, cap_first=None):
    """Quads over a (n_i, n_j, 3) point grid; wrap_i closes the i direction."""
    ni, nj = P_.shape[:2]
    vs = [[bm.verts.new(tuple(p)) for p in row] for row in P_]
    for i in range(ni if wrap_i else ni - 1):
        i2 = (i + 1) % ni
        for j in range(nj - 1):
            f = bm.faces.new([vs[i][j], vs[i2][j], vs[i2][j + 1], vs[i][j + 1]])
            f.material_index = mat
    return vs


cx, cy = H["c"]
th = np.linspace(0, 2 * math.pi, NA, endpoint=False)
sx, sy = np.sin(th), -np.cos(th)                       # 0 = front (-Y)


def ring(ax, z, dz=None):
    zz = np.full(NA, z) if dz is None else z + dz
    return np.stack([cx + ax[0] * sx, cy + ax[1] * sy, zz], 1)


# ---- brim: top surface out, rim, underside back in (front droops a little)
bax, bz, cax = np.array(H["brim_ax"]), H["brim_z"], np.array(H["crown_ax"])
droop = H.get("droop", 0.012) * np.clip(-sy, 0, 1) ** 2 + H.get("droop_back", 0.0) * np.clip(sy, 0, 1) ** 2   # brim curves down
rows = []
for u, dzz in ((0.98, 0.0), (0.4, 0.0), (0.85, -0.002), (1.0, -0.007), (1.0, -0.018), (0.85, -0.02), (0.98, -0.017)):
    if u == 0.98 and not rows:
        a_ = cax * 0.98
    elif u == 0.98:
        a_ = cax * 0.98
    else:
        a_ = cax + (bax - cax) * u
    rows.append(ring(a_, bz + dzz, -droop * (np.linalg.norm(a_) / np.linalg.norm(bax))))
rows[1] = ring(cax + (bax - cax) * 0.4, bz, -droop * 0.5)
add_grid(np.stack(rows, 1), 0, wrap_i=True)
# ---- crown: drum with a softly domed top
ctop = H["crown_top"]
crow = []
for k, (u, z) in enumerate(((0.98, bz), (1.0, bz + 0.02), (1.0, ctop - 0.02), (0.9, ctop - 0.002), (0.65, ctop + 0.008), (0.3, ctop + 0.014))):
    crow.append(ring(cax * u, z))
cv = add_grid(np.stack(crow, 1), 0, wrap_i=True)
top = bm.verts.new((cx, cy, ctop + 0.016))
for i in range(NA):
    bm.faces.new([cv[i][-1], cv[(i + 1) % NA][-1], top]).material_index = 0
# ---- gathered puffs round the crown: lumpy band (radius modulated), bigger at the front-left
pz0, pz1 = bz + 0.004, ctop + 0.002
PF = H.get("puffs", {"n": 7, "amp": 0.022, "front": 0.02})
lumps = 0.5 + 0.5 * np.cos(th * PF["n"])
bias = PF["front"] * np.exp(-((th - math.radians(PF.get("front_az", 35))) / 0.9) ** 2)
prow = []
for v in np.linspace(0, 1, H.get("puff_rows", 6)):
    bulge = math.sin(math.pi * v) ** 0.7
    rr = (1.0 + (PF["amp"] * (0.6 + 0.4 * lumps) + bias) * bulge / np.linalg.norm(cax) * 1.4) * (1 - 0.45 * v ** 3)
    twist = 0.25 * math.sin(math.pi * v)
    zz = pz0 + (pz1 + 0.012 - pz0) * math.sin(v * math.pi / 2) + 0.004 * np.sin(th * PF["n"] + twist * 3)
    prow.append(np.stack([cx + cax[0] * rr * sx, cy + cax[1] * rr * sy, zz], 1))
pv_ = add_grid(np.stack(prow, 1), 1, wrap_i=True)
ptop = bm.verts.new((cx, cy, float(np.mean(prow[-1][:, 2])) + 0.006))    # gathered top closes over the crown
for i in range(NA):
    bm.faces.new([pv_[i][-1], pv_[(i + 1) % NA][-1], ptop]).material_index = 1
# ---- rosettes: spiral ribbons (Archimedean), tilted to face out from the crown
for (az_d, zr, sc) in H.get("rosettes", [[25, 0.0, 1.0], [55, 0.012, 0.85], [80, -0.004, 0.7]]):
    a_ = math.radians(az_d)
    out = np.array([math.sin(a_), -math.cos(a_) * cax[1] / cax[0], 0.0])
    out /= np.linalg.norm(out)
    c0 = np.array([cx + cax[0] * 1.32 * math.sin(a_), cy - cax[1] * 1.32 * math.cos(a_), (pz0 + pz1) / 2 + zr])
    up = np.array([0, 0, 1.0])
    side = np.cross(up, out)
    R0 = H.get("rose_r", 0.034) * sc
    c0 = c0 + out * 0.006

    def petal(ang, rad, size, lift, cup):
        """Cupped petal: a 4x3 patch fanning out from the rose centre, rim curled toward 'out'."""
        d_ = side * math.cos(ang) + up * math.sin(ang)
        tq = np.cross(out, d_)
        P_ = np.zeros((4, 3, 3))
        for a_i, a_u in enumerate(np.linspace(0, 1, 4)):
            for b_i, b_u in enumerate(np.linspace(-1, 1, 3)):
                rr_ = rad + size * a_u
                P_[a_i, b_i] = c0 + d_ * rr_ + tq * (b_u * size * 0.55 * math.sin(math.pi * (0.3 + 0.55 * a_u))) \
                    + out * (lift + cup * a_u ** 2 - cup * 0.5 * abs(b_u) * a_u)
        add_grid(P_, 1)
    for k_ in range(5):
        petal(2 * math.pi * k_ / 5, R0 * 0.25, R0 * 0.8, 0.0, R0 * 0.5)
    for k_ in range(4):
        petal(2 * math.pi * (k_ + 0.5) / 4, R0 * 0.1, R0 * 0.5, R0 * 0.25, R0 * 0.55)
    res = bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=5, radius=R0 * 0.3)
    for v in res["verts"]:
        q = np.array(v.co)
        v.co = Vector(c0 + side * q[0] + up * q[1] + out * (q[2] * 0.8 + R0 * 0.35))
    for f in {f for v in res["verts"] for f in v.link_faces}:
        f.material_index = 1
# ---- satin bow: two flattened ribbon loops and a knot, at the front-left of the crown (refs/v3)
BW = H.get("bow")
if BW:
    a_ = math.radians(BW["az"])
    outb = np.array([math.sin(a_), -math.cos(a_) * cax[1] / cax[0], 0.0])
    outb /= np.linalg.norm(outb)
    upb = np.array([0, 0, 1.0])
    sideb = np.cross(upb, outb)
    kb = np.array([cx + cax[0] * 1.18 * math.sin(a_), cy - cax[1] * 1.18 * math.cos(a_), (pz0 + pz1) / 2 + BW.get("dz", 0.0)])
    nl, nw = 18, 4
    for sgn, scl, rot in [(1, 1.0, 0.0), (-1, 1.0, 0.0)] + ([(1, 0.7, 0.5), (-1, 0.7, -0.5)] if BW.get("inner") else []):
        Pl_ = np.zeros((nl, nw, 3))
        for i in range(nl):
            s_ = i / (nl - 1) * 2 * math.pi
            # loop: out along +/-side, rising, back to the knot (teardrop)
            lx0 = sgn * BW["len"] * scl * (0.5 - 0.5 * math.cos(s_))
            ly0 = BW["h"] * scl * math.sin(s_) * (0.6 + 0.4 * math.cos(s_ / 2))
            lx = lx0 * math.cos(rot) - ly0 * math.sin(rot)
            ly = lx0 * math.sin(rot) + ly0 * math.cos(rot)
            cen_ = kb + sideb * lx + upb * ly + outb * (0.012 * math.sin(s_ / 2))
            tan_ = sideb * (sgn * BW["len"] * 0.5 * math.sin(s_)) + upb * (BW["h"] * math.cos(s_))
            tan_ /= max(np.linalg.norm(tan_), 1e-6)
            wdir_ = np.cross(outb, tan_)                  # ribbon face looks out from the crown
            wdir_ /= max(np.linalg.norm(wdir_), 1e-6)
            pinch = 0.35 + 0.65 * math.sin(s_ / 2)        # gathered at the knot
            for j, u in enumerate(np.linspace(-1, 1, nw)):
                Pl_[i, j] = cen_ + wdir_ * u * BW["w"] * scl * pinch * 0.5 + outb * BW.get("puff", 0.012) * (1 - u * u) * pinch
        add_grid(Pl_, 1)
    res = bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=BW["w"] * 0.45)
    for v in res["verts"]:
        q = np.array(v.co)
        v.co = Vector(kb + sideb * q[0] * 0.9 + upb * q[1] * 1.2 + outb * (q[2] * 0.7 + 0.006))
    for f in {f for v in res["verts"] for f in v.link_faces}:
        f.material_index = 1
# ---- feather: serrated vane along a cubic spine, barbs droop off the rachis
F = H["feather"]
P0, P1, P2, P3 = [np.array(p) for p in F["ctrl"]]
ns = F.get("n", 70)
ss = np.linspace(0, 1, ns)
spine = ((1 - ss) ** 3)[:, None] * P0 + (3 * (1 - ss) ** 2 * ss)[:, None] * P1 + \
    (3 * (1 - ss) * ss ** 2)[:, None] * P2 + (ss ** 3)[:, None] * P3
tang = np.gradient(spine, axis=0)
tang /= np.linalg.norm(tang, axis=1, keepdims=True)
nrm0 = np.array(F.get("vane_normal", [1.0, 0.0, 0.25]))
wdir = np.cross(tang, nrm0)
wdir /= np.linalg.norm(wdir, axis=1, keepdims=True)
vn = np.cross(wdir, tang)
width = F["w"] * np.sin(np.pi * np.clip(ss * 1.05, 0, 1)) ** 0.6 * (0.35 + 0.65 * ss ** 0.4)
saw = (ss * F.get("serrations", 26)) % 1.0
serr = 1 - F.get("serr_depth", 0.45) * saw ** 1.5          # barbs: sawtooth swept toward the tip
us = np.linspace(-1, 1, 13)
grid_f = np.zeros((ns, len(us), 3))
for k, u in enumerate(us):
    w_ = width * (serr ** (abs(u) ** 2)) * abs(u)
    grid_f[:, k] = spine + wdir * (np.sign(u) * w_)[:, None] - vn * (F.get("droop", 0.35) * w_ ** 1.5 / max(F["w"], 1e-3) ** 0.5)[:, None] \
        + vn * (0.0015 * (abs(u) < 0.15))
add_grid(grid_f, 2)
tilt = math.radians(H.get("tilt", 0.0))
if tilt:
    piv = np.array([cx, cy, bz])
    for v in bm.verts:
        q = np.array(v.co) - piv
        y_, z_ = q[1], q[2]
        q[1] = y_ * math.cos(tilt) - z_ * math.sin(tilt) * -1
        q[2] = -y_ * math.sin(tilt) + z_ * math.cos(tilt)
        v.co = Vector(piv + q)
me = bpy.data.meshes.new("hat_shell")
bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
bm.to_mesh(me)
bm.free()
o = bpy.data.objects.new("hat_shell", me)
bpy.context.scene.collection.objects.link(o)
COL = H["colors"][next(iter(H["colors"]))]
for nm, mul, rough in (("felt", 1.0, 0.97), ("satin", 1.1, 0.72), ("feather", 0.9, 0.9)):
    m = bpy.data.materials.new(f"{CHAR}_hat_{nm}")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = srgb(np.clip(np.array(COL) * mul, 0, 255))
    b.inputs["Roughness"].default_value = rough
    m.use_backface_culling = False
    me.materials.append(m)
bpy.context.view_layer.objects.active = o
o.select_set(True)
bpy.ops.object.shade_smooth()
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.01)
bpy.ops.object.mode_set(mode="OBJECT")
tris = sum(len(p.vertices) - 2 for p in me.polygons)
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.export_scene.gltf(filepath=str(OUT / "hat.glb"), use_selection=True, export_format="GLB")
(OUT / "hat.json").write_text(json.dumps({"char": CHAR, "piece": "hat", "tris": tris, "source": "make_ladyhat.py (modelled)",
                                          "colors": H["colors"]}, indent=1), encoding="utf-8")
print("SHELL hat", tris)

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
cam.data.ortho_scale = 0.55
sc.collection.objects.link(cam)
sc.camera = cam
row = []
for yaw in (0, 90, 180, 35):
    y = math.radians(yaw)
    c = Vector((0.08, cy + 0.05, 1.66))
    cam.location = c + Vector((5 * math.sin(y), -5 * math.cos(y), 0.5))
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = str(ROOT / "renders" / "_tmp" / "lhat.png")
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
