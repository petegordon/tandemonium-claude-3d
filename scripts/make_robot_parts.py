"""Modelled hard parts of the robot outfit (Tandemonium #611 player bots), in the base-body frame (z up, -y forward):

  blender -b --factory-startup --python scripts/make_robot_parts.py -- --char outfit_male_robot [--pieces hat,collar,jacket,boots]

  hat     visor helmet: an enamel dome fitted round the skull (open underneath, the beak free below the visor), a glowing
          wrap-around visor band across the eyes, chrome ear discs with light rings, a short antenna (rigid on Head)
  collar  the neckwear: a chrome ring round the base of the neck (rigid on Spine2, chars json "rigid")
  jacket  shoulder caps (on the upper arms), elbow caps (on the forearms), the back power pack with its light core and
          an antenna (on Spine2): one shell, each part on its own bone ("rigid_parts" in jacket.json -> dress_goose.py)
  boots   post-pass on make_boot.py's knee boots: white enamel, chrome sole, chrome ankle band, light ring round the top,
          chrome knee caps (rigid_parts on the shins)

Every part is pushed clear of the body and the garments under it (fit_out). Materials: chrome (metallic), white enamel,
black, light (emissive; glTF emissive + KHR_materials_emissive_strength). Writes out/<char>-goose/shells/<piece>.glb +
<piece>.json and renders/robot/parts_<piece>.png.
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ROOT = Path(__file__).resolve().parents[1]
CHAR = argv[argv.index("--char") + 1] if "--char" in argv else "outfit_male_robot"
PIECES = (argv[argv.index("--pieces") + 1] if "--pieces" in argv else "hat,collar,jacket,boots").split(",")
D = ROOT / "out" / f"{CHAR}-goose"
SHD = D / "shells"
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
RP = cfg.get("robot_parts", {})
GLOW_RGB = [c / 255 for c in RP.get("glow", [40, 215, 255])]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ROOT / "out" / "base-goose" / "base_goose_rigged.glb"))
body = bpy.data.objects["base_goose_game"]
BV = np.array([(body.matrix_world @ v.co)[:] for v in body.data.vertices])
GN = [g.name for g in body.vertex_groups]
BW = np.zeros((len(BV), len(GN)))
for v in body.data.vertices:
    for g in v.groups:
        BW[v.index, g.group] = g.weight
dg = bpy.context.evaluated_depsgraph_get()
BODY_BVH = BVHTree.FromObject(body, dg)
JS = json.loads((ROOT / "refs" / "key_views" / "joints.json").read_text(encoding="utf-8"))
for o in list(bpy.data.objects):
    o.hide_render = True
    o.hide_set(True)


def shell_bvh(piece):
    f = SHD / f"{piece}.glb"
    if not f.exists():
        return None
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(f))
    new = [o for o in bpy.data.objects if o not in before]
    bms = bmesh.new()
    for o in new:
        if o.type == "MESH":
            t = bmesh.new()
            t.from_mesh(o.data)
            t.transform(o.matrix_world)
            me_ = bpy.data.meshes.new("tmp")
            t.to_mesh(me_)
            bms.from_mesh(me_)
            t.free()
    for o in new:
        bpy.data.objects.remove(o)
    tree = BVHTree.FromBMesh(bms)
    bms.free()
    return tree


def mat(name, rgb, metallic=0.0, rough=0.4, emit=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    bs = m.node_tree.nodes["Principled BSDF"]
    bs.inputs["Base Color"].default_value = (*rgb, 1)
    bs.inputs["Metallic"].default_value = metallic
    bs.inputs["Roughness"].default_value = rough
    if emit:
        bs.inputs["Emission Color"].default_value = (*GLOW_RGB, 1)
        bs.inputs["Emission Strength"].default_value = emit
    return m


CHROME = lambda: mat("robot_chrome", (0.62, 0.64, 0.68), 0.85, 0.2)          # noqa: E731
WHITE = lambda: mat("robot_white", (0.86, 0.87, 0.89), 0.0, 0.32)            # noqa: E731
BLACK = lambda: mat("robot_black", (0.012, 0.012, 0.015), 0.0, 0.5)          # noqa: E731
LIGHT = lambda: mat("robot_light", tuple(GLOW_RGB), 0.0, 0.3, 3.0)           # noqa: E731
VISOR = lambda: mat("robot_visor", (0.02, 0.18, 0.32), 0.3, 0.12, 1.6)        # noqa: E731


def new_obj(name, bm, material):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(material)
    for p in me.polygons:
        p.use_smooth = True
    return ob


def ellipsoid(center, radii, keep, seg=48, rings=32):
    """UV-sphere surface scaled to radii at center; faces whose centre direction fails keep(dir) are deleted."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=1.0)
    dead = [f for f in bm.faces if not keep(f.calc_center_median().normalized())]
    bmesh.ops.delete(bm, geom=dead, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    for v in bm.verts:
        v.co = Vector((center[0] + v.co.x * radii[0], center[1] + v.co.y * radii[1], center[2] + v.co.z * radii[2]))
    return bm


def fit_out(bm, trees, clear, rounds=4, relax=3, max_move=0.06):
    """Push every vertex at least `clear` off the BODY (trees[0]), along the body's normal at the nearest point, then
    relax so pushed spots don't dent. Garment shells are not used for the push (their linings face inward and threw
    vertices out as spikes): `clear` includes the garments' own stand-off."""
    t = trees[0]
    start = {v: v.co.copy() for v in bm.verts}
    for _ in range(rounds):
        moved = 0
        for v in bm.verts:
            p, n, _, d = t.find_nearest(v.co)
            if p is None:
                continue
            if (v.co - p).dot(n) < 0 or d < clear:
                v.co = p + n * clear
                moved += 1
            off = v.co - start[v]
            if off.length > max_move:
                v.co = start[v] + off.normalized() * max_move
        for _ in range(relax):
            new = {}
            for v in bm.verts:
                if v.is_boundary or not v.link_edges:
                    continue
                new[v] = sum((e.other_vert(v).co for e in v.link_edges), Vector()) / len(v.link_edges)
            for v, c in new.items():
                v.co = v.co * 0.5 + c * 0.5
        if not moved:
            break


def solidify(ob, t, offset=1.0):
    m = ob.modifiers.new("sol", "SOLIDIFY")
    m.thickness = t
    m.offset = offset
    m.use_even_offset = True
    bpy.context.view_layer.objects.active = ob
    ob.hide_set(False)
    bpy.ops.object.modifier_apply(modifier="sol")


def cylinder(p0, p1, r, material, seg=20, caps=True):
    p0, p1 = Vector(p0), Vector(p1)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=caps, segments=seg, radius1=r, radius2=r, depth=(p1 - p0).length)
    rot = Vector((0, 0, 1)).rotation_difference((p1 - p0).normalized()).to_matrix().to_4x4()
    bm.transform(Matrix.Translation((p0 + p1) / 2) @ rot)
    return new_obj("cyl", bm, material)


def sphere(c, r, material):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=r)
    bm.transform(Matrix.Translation(Vector(c)))
    return new_obj("sph", bm, material)


def ring(center, rx, ry, tube, material, normal=(0, 0, 1), seg=64, tseg=10):
    """Elliptic torus round `center` in the plane normal to `normal`."""
    bm = bmesh.new()
    verts = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        c_ = Vector((rx * math.cos(a), ry * math.sin(a), 0))
        out = Vector((math.cos(a) / max(rx, 1e-6), math.sin(a) / max(ry, 1e-6), 0)).normalized()
        row = []
        for j in range(tseg):
            b = 2 * math.pi * j / tseg
            row.append(bm.verts.new(c_ + out * (tube * math.cos(b)) + Vector((0, 0, tube * math.sin(b)))))
        verts.append(row)
    for i in range(seg):
        for j in range(tseg):
            bm.faces.new([verts[i][j], verts[(i + 1) % seg][j], verts[(i + 1) % seg][(j + 1) % tseg], verts[i][(j + 1) % tseg]])
    rot = Vector((0, 0, 1)).rotation_difference(Vector(normal).normalized()).to_matrix().to_4x4()
    bm.transform(Matrix.Translation(Vector(center)) @ rot)
    return new_obj("ring", bm, material)


def rounded_box(center, size, bevel, material):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.transform(Matrix.Translation(Vector(center)) @ Matrix.Diagonal((*size, 1)))
    ob = new_obj("box", bm, material)
    m = ob.modifiers.new("bev", "BEVEL")
    m.width = bevel
    m.segments = 4
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier="bev")
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def join(obs, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.01)
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob


def export(ob, piece, meta):
    bpy.ops.object.select_all(action="DESELECT")
    ob.hide_set(False)
    ob.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(SHD / f"{piece}.glb"), export_format="GLB", use_selection=True)
    tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    meta = {"char": CHAR, "piece": piece, "source": "make_robot_parts.py (modelled)", "tris": tris, **meta}
    (SHD / f"{piece}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print("PART", piece, "tris", tris, "->", SHD / f"{piece}.glb")
    ob.hide_set(True)
    ob.hide_render = True


def grp(n):
    return BW[:, GN.index(n)] if n in GN else np.zeros(len(BV))


def J(n, end="head"):
    return np.array(JS[n][end])


# ------------------------------------------------------------------ hat: visor helmet
def make_hat():
    H = RP.get("hat", {})
    skull = (grp("Head") > 0.4) & (grp("Jaw") < 0.2) & (BV[:, 1] > H.get("beak_y", -0.165)) & (BV[:, 2] > 1.47)
    S = BV[skull]
    lo, hi = S.min(0), S.max(0)
    c = (lo + hi) / 2
    c[2] += H.get("c_up", 0.006)
    r = (hi - lo) / 2
    k = np.max(np.sum(((S - c) / r) ** 2, 1) ** 0.5)          # scale so every skull vertex is inside
    r = r * k + H.get("margin", 0.012)
    eye = np.array(JS["LeftEye"]["head"])
    ez = (eye[2] - c[2]) / r[2]                               # eye height on the unit sphere
    vb, vt = (eye[2] - H.get("visor_below", 0.022) - c[2]) / r[2], (eye[2] + H.get("visor_above", 0.02) - c[2]) / r[2]
    bot = H.get("bottom", -0.42)
    front_cut = vb - H.get("brow", 0.02) / r[2]               # in front, the shell ends just under the visor (beak free)

    def keep(d):
        if d.z < bot:
            return False
        fwd = -d.y / max(math.hypot(d.x, d.y), 1e-6)          # 1 = straight ahead
        return not (fwd > H.get("open_front", 0.35) and d.z < front_cut)
    bm = ellipsoid(c, r, keep)
    shell = new_obj("helmet", bm, WHITE())
    solidify(shell, H.get("thick", 0.004))
    # visor band: the front strip between vb and vt, a little proud of the shell
    bm = ellipsoid(c, r + H.get("visor_proud", 0.005), lambda d: vb <= d.z <= vt and -d.y / max(math.hypot(d.x, d.y), 1e-6) > -0.25)
    visor = new_obj("visor", bm, VISOR())
    solidify(visor, 0.003)
    rim = []
    for zz in (vb, vt):                                       # chrome rims above and below the visor
        bm = ellipsoid(c, r + H.get("visor_proud", 0.005) + 0.001,
                       lambda d, zz=zz: abs(d.z - zz) < 0.035 and -d.y / max(math.hypot(d.x, d.y), 1e-6) > -0.3)
        rim.append(new_obj("rim", bm, CHROME()))
        solidify(rim[-1], 0.002)
    parts = [shell, visor] + rim
    for sx in (1, -1):                                        # ear discs + light rings
        y0 = c[1] + H.get("ear_y", 0.02)
        x0 = c[0] + sx * r[0] * math.sqrt(max(0.0, 1 - ((y0 - c[1]) / r[1]) ** 2 - ez ** 2))
        p0, p1 = (x0 - sx * 0.004, y0, eye[2]), (x0 + sx * 0.012, y0, eye[2])
        parts.append(cylinder(p0, p1, H.get("ear_r", 0.024), CHROME(), 28))
        parts.append(ring((x0 + sx * 0.0125, y0, eye[2]), 0.012, 0.012, 0.0022, LIGHT(), normal=(sx, 0, 0), seg=32, tseg=8))
    top = Vector(c) + Vector((0, r[1] * 0.35, r[2] * 0.92))
    parts.append(cylinder(top - Vector((0, 0, 0.01)), top + Vector((0, 0.012, H.get("antenna", 0.06))), 0.0032, CHROME(), 10))
    parts.append(sphere(top + Vector((0, 0.012, H.get("antenna", 0.06) + 0.004)), 0.007, LIGHT()))
    ob = join(parts, "hat")
    export(ob, "hat", {"center": c.round(4).tolist(), "radii": r.round(4).tolist()})


# ------------------------------------------------------------------ collar (neckwear)
def make_collar():
    C = RP.get("collar", {})
    z = C.get("z", 1.30)
    s = np.abs(BV[:, 2] - z) < 0.008
    cx, cy = 0.0, float((BV[s, 1].min() + BV[s, 1].max()) / 2)
    rx = float(np.abs(BV[s, 0]).max()) + C.get("clear", 0.016)
    ry = float((BV[s, 1].max() - BV[s, 1].min()) / 2) + C.get("clear", 0.016)
    parts = [ring((cx, cy, z), rx, ry, C.get("tube", 0.011), CHROME(), normal=C.get("normal", (0, 0.12, 1)))]
    parts.append(ring((cx, cy, z + C.get("tube", 0.011) * 0.9), rx - 0.002, ry - 0.002, 0.0022, LIGHT(), normal=C.get("normal", (0, 0.12, 1))))
    ob = join(parts, "collar")
    export(ob, "collar", {"z": z, "rx": rx, "ry": ry})


# ------------------------------------------------------------------ jacket: caps, power pack, antenna
def make_jacket():
    Jc = RP.get("jacket", {})
    under = [BODY_BVH, shell_bvh("shirt"), shell_bvh("waistcoat")]
    parts, rigid = [], []
    # power pack on the upper back (first: the caps' rigid spheres override it where they overlap)
    pc = Jc.get("pack", {})
    size = pc.get("size", [0.15, 0.05, 0.17])
    zc = pc.get("z", 1.14)
    hits = [t.ray_cast(Vector((0, 0.5, zc)), Vector((0, -1, 0)))[0] for t in under if t is not None]
    yb = max(h.y for h in hits if h is not None)
    cy = yb + pc.get("gap", 0.006) + size[1] / 2
    parts.append(rounded_box((0, cy, zc), size, pc.get("bevel", 0.018), CHROME()))
    yo = cy + size[1] / 2
    parts.append(rounded_box((0, yo + 0.002, zc), (size[0] * 0.72, 0.006, size[2] * 0.78), 0.012, WHITE()))
    parts.append(cylinder((0, yo + 0.004, zc + 0.01), (0, yo + 0.010, zc + 0.01), pc.get("core_r", 0.026), LIGHT(), 32))
    parts.append(ring((0, yo + 0.008, zc + 0.01), pc.get("core_r", 0.026) + 0.004, pc.get("core_r", 0.026) + 0.004, 0.003, CHROME(), normal=(0, 1, 0), seg=40, tseg=8))
    for sx in (1, -1):                                         # light strips down the pack's sides
        parts.append(rounded_box((sx * (size[0] / 2 + 0.001), cy, zc), (0.004, size[1] * 0.5, size[2] * 0.7), 0.0015, LIGHT()))
    ax_ = pc.get("antenna_x", 0.045)
    a0 = Vector((ax_, cy, zc + size[2] / 2 - 0.01))
    a1 = a0 + Vector((0, 0.01, pc.get("antenna", 0.13)))
    parts.append(cylinder(a0, a1, 0.004, CHROME(), 10))
    parts.append(sphere(a1 + Vector((0, 0, 0.006)), 0.008, LIGHT()))
    rigid.append({"bone": "Spine2", "center": [0, cy, zc + 0.04], "radius": 0.2})
    # shoulder caps (upper arm) and elbow caps (forearm)
    sc = Jc.get("shoulder", {})
    ec = Jc.get("elbow", {})
    def dome(c, nd, keep, clear, sel_r, squash, rmin, rmax):
        """A sphere segment centred on a joint, big enough to clear every body vertex near it in the kept direction
        (plus `clear` for the garments under it): clean round edges, no per-vertex push."""
        rel = BV - c
        dd = np.linalg.norm(rel, axis=1)
        near = (dd < sel_r) & ((rel / np.maximum(dd[:, None], 1e-9)) @ np.array(nd) > keep)
        r_ = float(np.clip((dd[near].max() if near.any() else rmin) + clear, rmin, rmax))
        rr = [r_, r_, r_ * squash]
        return ellipsoid(c, rr, lambda d: d.dot(Vector(nd)) > keep, 40, 24), r_
    for sx, side in ((1, "Left"), (-1, "Right")):
        c = J(f"{side}Arm") + np.array(sc.get("offset", [0.02, 0.0, -0.005])) * [sx, 1, 1]
        nd = Vector((sx * 0.6, 0, 0.8)).normalized()
        bm, r_ = dome(c, nd, sc.get("keep", 0.3), sc.get("clear", 0.03), 0.11, sc.get("squash", 0.85), 0.05, 0.095)
        ob = new_obj("scap", bm, CHROME())
        solidify(ob, 0.005)
        parts.append(ob)
        rigid.append({"bone": f"{side}Arm", "center": c.round(4).tolist(), "radius": r_ + 0.03})
        print("CAP shoulder", side, round(r_, 3))
        c = J(f"{side}ForeArm")
        ax = J(f"{side}Hand") - J(f"{side}Arm")
        ax /= np.linalg.norm(ax)
        back = np.array([0.0, 1.0, 0.0]) - ax * ax[1]
        back /= np.linalg.norm(back)
        nd = Vector(back * 0.9 + np.array([sx * 0.3, 0, 0])).normalized()
        bm, r_ = dome(c, nd, ec.get("keep", 0.35), ec.get("clear", 0.014), 0.06, 1.0, 0.035, 0.06)
        ob = new_obj("ecap", bm, CHROME())
        solidify(ob, 0.004)
        parts.append(ob)
        rigid.append({"bone": f"{side}ForeArm", "center": c.round(4).tolist(), "radius": r_ + 0.02})
        print("CAP elbow", side, round(r_, 3))
    ob = join(parts, "jacket")
    export(ob, "jacket", {"rigid_parts": rigid})


# ------------------------------------------------------------------ boots: recolour + bands + knee caps
def make_boots():
    Bc = RP.get("boots", {})
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(SHD / "boots.glb"))
    bo = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
    for i, m in enumerate(bo.data.materials):
        bo.data.materials[i] = CHROME() if "sole" in m.name else WHITE()
    boot_tree = BVHTree.FromObject(bo, bpy.context.evaluated_depsgraph_get())
    bd = cfg["boot_design"]
    parts, rigid = [bo], []
    for sx, side in ((1, "Left"), (-1, "Right")):
        x0 = sx * bd["centre_x"]
        for (zz, hw, hd, yc), tube, material, grow in ((Bc.get("ankle", [0.14, 0.038, 0.045, 0.04]), 0.008, CHROME(), 0.004),
                                                       (Bc.get("top", [0.425, 0.079, 0.085, 0.043]), 0.0035, LIGHT(), 0.0)):
            parts.append(ring((x0, yc, zz), hw + grow, hd + grow, tube, material))
        kc = Bc.get("knee", {})
        c = np.array([x0, kc.get("y", -0.04), kc.get("z", 0.372)])
        bm = ellipsoid(c, kc.get("radii", [0.045, 0.03, 0.052]), lambda d: d.y < -kc.get("keep", 0.15), 32, 20)
        fit_out(bm, [boot_tree], kc.get("clear", 0.004), max_move=0.03)
        ob = new_obj("kcap", bm, CHROME())
        solidify(ob, 0.005)
        parts.append(ob)
        parts.append(ring((x0, c[1] - 0.01, c[2]), 0.012, 0.012, 0.0025, LIGHT(), normal=(0, -1, 0), seg=28, tseg=8))
        rigid.append({"bone": f"{side}Leg", "center": c.round(4).tolist(), "radius": 0.06})
    meta = json.loads((SHD / "boots.json").read_text(encoding="utf-8")) if (SHD / "boots.json").exists() else {}
    ob = join(parts, "boots")
    meta.pop("tris", None)
    export(ob, "boots", {**{k: v for k, v in meta.items() if k not in ("char", "piece", "source")}, "rigid_parts": rigid})


for p in PIECES:
    {"hat": make_hat, "collar": make_collar, "jacket": make_jacket, "boots": make_boots}[p]()
