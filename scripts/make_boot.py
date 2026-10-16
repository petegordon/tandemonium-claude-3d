"""Model a riding boot pair to the measured shape of Pete's drawing (the dressing hides the goose's feet + shins).

  blender -b --factory-startup --python scripts/make_boot.py -- [--char outfit_male_victorian] [--tris 6000] [--tag v1]

Recipe: chars/<char>.json "boot_design" (metres, base-body frame, per boot; the right boot mirrors the left in x):
  centre_x            leg centre (x) of the left boot
  toe_y, heel_y       foot length along y (forward is -y)
  sole_w              [[t, half width], ...] along the foot (t: 0 heel -> 1 toe)
  top_line            [[t, height], ...] the foot's upper line (heel counter -> vamp -> toe cap)
  shaft               [[z, half width (x), half depth (y), centre y], ...] up the leg to the top
  heel_h, heel_len    heel block height / length from the back
  power               superellipse exponent of the sections (2 = ellipse; higher = boxier)
Foot = sections across y (superellipse, flat sole at z = 0), shaft = sections up z; both closed tubes, unioned by a
voxel remesh, smoothed, decimated to --tris, UV-unwrapped (smart project). One leather material (black); the look
(shine, buttons, sole edge) comes from project_bake.py. Writes out/<char>-goose/shells/boots.glb + boots.json, and
out/<char>-goose/versions/boots_<tag>_geo.glb.
"""
import json
import math
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
TRIS = opt("--tris", 6000)
TAG = opt("--tag", "v1")
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
B = cfg["boot_design"]
D = ROOT / "out" / f"{CHAR}-goose"
(D / "shells").mkdir(parents=True, exist_ok=True)
(D / "versions").mkdir(parents=True, exist_ok=True)
NS = 40                                                 # points per section


def interp(table, t):
    a = np.array(table, float)
    return np.interp(t, a[:, 0], a[:, 1])


def superellipse(n, a, b, p):
    th = np.linspace(0, 2 * math.pi, n, endpoint=False)
    c, s = np.cos(th), np.sin(th)
    return a * np.sign(c) * np.abs(c) ** (2 / p), b * np.sign(s) * np.abs(s) ** (2 / p)


def tube(sections):
    """Closed tube from a list of (NS, 3) rings: side quads + fan caps."""
    bm = bmesh.new()
    rings = [[bm.verts.new(tuple(p)) for p in r] for r in sections]
    for r0, r1 in zip(rings[:-1], rings[1:]):
        for i in range(NS):
            bm.faces.new((r0[i], r0[(i + 1) % NS], r1[(i + 1) % NS], r1[i]))
    for r, flip in ((rings[0], True), (rings[-1], False)):
        c = bm.verts.new(tuple(np.mean([v.co for v in r], axis=0)))
        for i in range(NS):
            f = (r[i], r[(i + 1) % NS], c) if not flip else (r[(i + 1) % NS], r[i], c)
            bm.faces.new(f)
    me = bpy.data.meshes.new("tube")
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new("tube", me)
    bpy.context.scene.collection.objects.link(o)
    return o


ARCH = B.get("arch")       # Louis heel: {"h": lift under the arch, "t0", "t1": where along the foot (0 heel .. 1 toe)}


def arch(t):
    if not ARCH:
        return 0.0
    t0, t1 = ARCH.get("t0", 0.2), ARCH.get("t1", 0.58)
    if t >= t1:
        return 0.0
    if t <= t0:                                    # the back of the shoe rides on the heel
        return ARCH["h"]
    u = (t - t0) / (t1 - t0)
    return ARCH["h"] * (0.5 + 0.5 * math.cos(math.pi * u))       # down the arch to the ball of the foot


def boot(sx):
    cx = B["centre_x"] * sx
    p = B.get("power", 2.4)
    # foot: sections across y from heel to toe; each superellipse spans z in [0, top] (flat-ish sole)
    foot = []
    for t in np.linspace(0, 1, 28):
        y = B["heel_y"] + (B["toe_y"] - B["heel_y"]) * t
        hw = interp(B["sole_w"], t)
        top = interp(B["top_line"], t)
        x_, z_ = superellipse(NS, hw, top / 2, p)
        z_ = np.maximum(z_ + top / 2, 0.0) + 0.0005
        lift = arch(t)
        if lift > 0:                               # a raised arch: the bottom half of the section is pushed up
            z_ = np.where(z_ < top / 2, lift + (z_) * (1 - lift / max(top, 1e-3)), z_)
        foot.append(np.stack([cx + x_, np.full(NS, y), z_], 1))
    # rounded heel: a quarter ellipse BEHIND the first section (the flat back read as a slab)
    first = foot[0].copy()
    back = []
    for k in range(1, 6):
        u = k / 5
        f = math.sqrt(max(1 - u * u, 0.0)) * 0.9 + 0.1
        r = first.copy()
        r[:, 0] = first[:, 0].mean() + (r[:, 0] - first[:, 0].mean()) * f ** 0.7
        hb = arch(0.0)                             # (scaled about the lifted bottom: the heel cup stays on the heel)
        r[:, 2] = hb + (r[:, 2] - hb) * f ** 0.35
        r[:, 1] = first[0, 1] - np.sign(B["toe_y"] - B["heel_y"]) * B.get("heel_round", 0.022) * u
        back.append(r)
    foot = back[::-1] + foot
    # rounded toe cap: a quarter ellipse ahead of the last section, shrunk about its BOTTOM centre (the sole stays on
    # the ground -- shrinking about the centre lifted the toe into a wedge)
    last = foot[-1].copy()
    base = np.array([last[:, 0].mean(), last[0, 1], 0.0])
    cap = B.get("toe_cap", 0.035)
    fwd = np.sign(B["toe_y"] - B["heel_y"])
    for k in range(1, 7):
        u = k / 6
        f = math.sqrt(max(1 - u * u, 0.0)) * 0.97 + 0.03
        r = last.copy()
        r[:, 0] = base[0] + (r[:, 0] - base[0]) * f ** B.get("toe_narrow", 1.4)
        r[:, 2] = r[:, 2] * f ** 0.8 + B.get("toe_up", 0.006) * u ** 2
        r[:, 1] = last[0, 1] + fwd * cap * u
        foot.append(r)
    shaft = []
    for z, hw, hd, cy in B["shaft"]:
        x_, y_ = superellipse(NS, hw, hd, B.get("shaft_power", 2.2))
        shaft.append(np.stack([cx + x_, cy + y_, np.full(NS, z)], 1))
    heel = []
    hl, hh = B.get("heel_len", 0.07), B.get("heel_h", 0.03)
    if ARCH:                                       # Louis heel: horizontal sections up from the floor, waisted
        fwd_ = np.sign(B["toe_y"] - B["heel_y"])
        y0 = B["heel_y"] + fwd_ * 0.004
        for zz in np.linspace(0.0, ARCH["h"] + 0.006, 7):
            u = zz / (ARCH["h"] + 0.006)
            waist = 1 - ARCH.get("waist", 0.35) * math.sin(math.pi * min(u * 1.2, 1.0))
            hw = interp(B["sole_w"], 0.08) * ARCH.get("heel_w", 0.8) * waist
            L = ARCH.get("heel_len", 0.035) * (0.7 + 0.3 * u) * waist
            x_, y_ = superellipse(NS, hw, L / 2, 2.6)
            heel.append(np.stack([cx + x_, y0 + fwd_ * (L / 2 + 0.002 * u) + y_, np.full(NS, zz)], 1))
    else:
        for y in np.linspace(B["heel_y"] - 0.004, B["heel_y"] - hl, 6):
            x_, z_ = superellipse(NS, interp(B["sole_w"], 0.05) * 0.85, hh / 2, 4.0)
            heel.append(np.stack([cx + x_, np.full(NS, y), z_ + hh / 2 - 0.004], 1))
    sole = []
    for t in np.linspace(0, 1, 24):
        y = B["heel_y"] + (B["toe_y"] - B["heel_y"]) * t
        hw = interp(B["sole_w"], t) + B.get("welt", 0.003)
        x_, z_ = superellipse(NS, hw, B.get("sole_h", 0.012) / 2, 6.0)
        sole.append(np.stack([cx + x_, np.full(NS, y), z_ + B.get("sole_h", 0.012) / 2 - 0.002], 1))
    for k in range(1, 5):                          # follow the toe cap
        u = k / 4
        f = math.sqrt(max(1 - u * u, 0.0)) * 0.9 + 0.1
        r = sole[-1].copy()
        r[:, 0] = cx + (r[:, 0] - cx) * f ** B.get("toe_narrow", 1.4)
        r[:, 1] = sole[-1][0, 1] + np.sign(B["toe_y"] - B["heel_y"]) * B.get("toe_cap", 0.035) * u
        sole.append(r)
    so = tube(sole)
    so.name = "sole"
    return [tube(foot), tube(shaft), tube(heel)], [so]


bpy.ops.wm.read_factory_settings(use_empty=True)
pl, sl = boot(1)
pr, sr = boot(-1)
parts = pl + pr
for so in sl + sr:                                   # (the pre-shaped sole overshot the smoothed toe: rebuilt below)
    bpy.data.objects.remove(so)
soles = []
bpy.ops.object.select_all(action="DESELECT")
for o in parts:
    o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
ob = bpy.context.view_layer.objects.active
ob.name = "boots_shell"
rm = ob.modifiers.new("remesh", "REMESH")
rm.mode = "VOXEL"
rm.voxel_size = B.get("voxel", 0.004)
rm.use_smooth_shade = True
bpy.ops.object.modifier_apply(modifier=rm.name)
sm = ob.modifiers.new("smooth", "LAPLACIANSMOOTH")
sm.iterations = B.get("smooth_iter", 6)
sm.lambda_factor = 0.6
sm.use_volume_preserve = True
bpy.ops.object.modifier_apply(modifier=sm.name)
n = sum(len(p.vertices) - 2 for p in ob.data.polygons)
dec = ob.modifiers.new("dec", "DECIMATE")
dec.ratio = min(1.0, TRIS / max(n, 1))
bpy.ops.object.modifier_apply(modifier=dec.name)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.quads_convert_to_tris()
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.004)
bpy.ops.object.mode_set(mode="OBJECT")
for p in ob.data.polygons:
    p.use_smooth = True
# sole: per 5 mm slice along y, the upper's footprint (verts below 2.5 cm) + a welt, per boot
V = np.array([v.co[:] for v in ob.data.vertices])
for sx in (1, -1):
    low = V[(V[:, 2] < 0.025) & (V[:, 0] * sx > 0)]
    ys = np.arange(low[:, 1].min(), low[:, 1].max() + 1e-6, B.get("sole_step", 0.005))
    prof = []
    for y in ys:
        sl_ = low[np.abs(low[:, 1] - y) < 0.004]
        if len(sl_) < 3:
            continue
        prof.append((y, (sl_[:, 0].max() - sl_[:, 0].min()) / 2, (sl_[:, 0].max() + sl_[:, 0].min()) / 2))
    prof = np.array(prof)
    for _ in range(B.get("sole_smooth", 0)):     # (the voxel footprint is noisy: a stepped, toothed sole edge)
        prof[1:-1, 1:] = 0.25 * prof[:-2, 1:] + 0.5 * prof[1:-1, 1:] + 0.25 * prof[2:, 1:]
    runs = [[]]
    for y, hw, cxs in prof:
        if ARCH:                                   # no sole under the arch or the heel (the heel is its own block)
            t_ = (y - B["heel_y"]) / (B["toe_y"] - B["heel_y"])
            if t_ < ARCH.get("t1", 0.58) - 0.04:
                if runs[-1]:
                    runs.append([])
                continue
        hw += B.get("welt", 0.003)
        x_, z_ = superellipse(NS, hw, B.get("sole_h", 0.012) / 2, 6.0)
        runs[-1].append(np.stack([cxs + x_, np.full(NS, y), z_ + B.get("sole_h", 0.012) / 2 - 0.002], 1))
    for rings in [r_ for r_ in runs if len(r_) > 1]:
        so = tube(rings)
        so.name = "sole"
        soles.append(so)
mat = bpy.data.materials.new("boots_leather")
mat.use_nodes = True
nt = mat.node_tree
bs = nt.nodes["Principled BSDF"]
bs.inputs["Base Color"].default_value = (*B.get("leather_rgb", (0.022, 0.019, 0.018)), 1)
bs.inputs["Roughness"].default_value = B.get("roughness", 0.42)
bs.inputs["Coat Weight"].default_value = 0.25
bs.inputs["Coat Roughness"].default_value = 0.35
nz = nt.nodes.new("ShaderNodeTexNoise")
nz.inputs["Scale"].default_value = 900.0
bump = nt.nodes.new("ShaderNodeBump")
bump.inputs["Strength"].default_value = 0.08
nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
nt.links.new(bump.outputs["Normal"], bs.inputs["Normal"])
ob.data.materials.append(mat)
smat = bpy.data.materials.new("boots_sole")
smat.use_nodes = True
sbs = smat.node_tree.nodes["Principled BSDF"]
sbs.inputs["Base Color"].default_value = (0.05, 0.032, 0.022, 1)
sbs.inputs["Roughness"].default_value = 0.6
for so in soles:
    so.data.materials.append(smat)
    for poly in so.data.polygons:
        poly.use_smooth = False
bpy.ops.object.select_all(action="DESELECT")
for so in soles:
    so.select_set(True)
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.join()
ob = bpy.context.view_layer.objects.active
if B.get("z_off"):        # a shaped body whose soles sit below z = 0 in the build frame (female sliders: -0.0932)
    for v in ob.data.vertices:
        v.co.z += B["z_off"]
tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
for f in (D / "versions" / f"boots_{TAG}_geo.glb", D / "shells" / "boots.glb"):
    bpy.ops.export_scene.gltf(filepath=str(f), export_format="GLB", use_selection=True)
meta = {"char": CHAR, "piece": "boots", "source": "make_boot.py (modelled to the measured drawing)", "tris": tris,
        "z_top": max(s[0] for s in B["shaft"]), "design": B}
(D / "shells" / "boots.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
print("BOOT", json.dumps({"tris": tris, "tag": TAG}))
