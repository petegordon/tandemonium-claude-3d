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
PIECES = (argv[argv.index("--pieces") + 1] if "--pieces" in argv else "hat,collar,jacket,boots,vest").split(",")
D = ROOT / "out" / f"{CHAR}-goose"
SHD = D / "shells"
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
RP = cfg.get("robot_parts", {})
GLOW_RGB = [c / 255 for c in RP.get("glow", [40, 215, 255])]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ROOT / "out" / "base-goose" / "base_goose_rigged.glb"))
body = bpy.data.objects["base_goose_game"]
BV = np.array([(body.matrix_world @ v.co)[:] for v in body.data.vertices])
_GB = ROOT / "out" / "base-goose" / "garment_body.npz"          # the garment body (no tail, human-like seat)
if cfg.get("garment_body", True) and _GB.exists() and len(np.load(_GB)["pos"]) == len(BV):
    BV = np.load(_GB)["pos"].astype(float)
    _Mi = np.linalg.inv(np.array(body.matrix_world))
    body.data.vertices.foreach_set("co", (BV @ _Mi[:3, :3].T + _Mi[:3, 3]).ravel())
    body.data.update()
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


CHROME = lambda: mat("robot_chrome", (0.96, 0.965, 0.98), 0.75, 0.24)   # bright silver (Pete): brushed, part
# diffuse so it stays silver in the game even without the env map (a pure mirror read black in the RoomEnvironment)          # noqa: E731
WHITE = lambda: mat("robot_white", (0.86, 0.87, 0.89), 0.0, 0.32)            # noqa: E731
BLACK = lambda: mat("robot_black", (0.012, 0.012, 0.015), 0.0, 0.5)          # noqa: E731
LIGHT = lambda: mat("robot_light", tuple(GLOW_RGB), 0.0, 0.3, 3.0)           # noqa: E731
VISOR = lambda: mat("robot_visor", (0.01, 0.08, 0.16), 0.2, 0.08, 0.7)        # noqa: E731


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


def ring(center, rx, ry, tube, material, normal=(0, 0, 1), seg=36, tseg=6):
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


def rounded_box(center, size, bevel, material, segs=3):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.transform(Matrix.Translation(Vector(center)) @ Matrix.Diagonal((*size, 1)))
    ob = new_obj("box", bm, material)
    m = ob.modifiers.new("bev", "BEVEL")
    m.width = bevel
    m.segments = segs
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier="bev")
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def smooth_by_angle(ob, deg=40):
    """Smooth shading on curved parts, sharp on flat faces / bevel edges (no smeared shading on boxes)."""
    bpy.ops.object.select_all(action="DESELECT")
    ob.hide_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(deg))
    return ob


def cut_dome(center, radii, planes, seg=44, rings=26):
    """Ellipsoid surface cut by planes (in unit-sphere space: (point, normal), the side the normal points to is KEPT):
    clean conic edges, unlike deleting faces. Returns bmesh in world space + the boundary loops (lists of Vectors)."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=rings, radius=1.0)
    for co, no in planes:
        geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
        bmesh.ops.bisect_plane(bm, geom=geom, plane_co=Vector(co), plane_no=Vector(no).normalized(), clear_inner=True)
    S = Matrix.Translation(Vector(center)) @ Matrix.Diagonal((*radii, 1))
    bm.transform(S)
    return bm, boundary_loops(bm)


def boundary_loops(bm):
    """Ordered loops of boundary vertices (positions)."""
    bm.edges.ensure_lookup_table()
    bedges = [e for e in bm.edges if e.is_boundary]
    nbr = {}
    for e in bedges:
        a, b = e.verts
        nbr.setdefault(a, []).append(b)
        nbr.setdefault(b, []).append(a)
    seen, loops = set(), []
    for v0 in nbr:
        if v0 in seen:
            continue
        loop, prev, cur = [], None, v0
        while cur is not None and cur not in seen:
            seen.add(cur)
            loop.append(cur.co.copy())
            nxt = [w for w in nbr[cur] if w is not prev and w not in seen]
            prev, cur = cur, (nxt[0] if nxt else None)
        if len(loop) > 4:
            loops.append(loop)
    return loops


def tube_along(points, r, material, closed=True, tseg=6, push=None, step=2):
    """A round tube swept along a polyline (trim round an edge). push: (center, dist) moves each point away from center."""
    P = [Vector(p) for p in points][::max(1, step)]       # (every other edge point: plenty for a trim)
    if push is not None:
        c0, dd = Vector(push[0]), push[1]
        P = [p + (p - c0).normalized() * dd for p in P]
    n = len(P)
    bm = bmesh.new()
    rows = []
    for i in range(n):
        a, b = P[i - 1] if (closed or i > 0) else P[i], P[(i + 1) % n] if (closed or i < n - 1) else P[i]
        t = (b - a).normalized()
        up = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
        u = t.cross(up).normalized()
        w = t.cross(u).normalized()
        rows.append([bm.verts.new(P[i] + (u * math.cos(2 * math.pi * j / tseg) + w * math.sin(2 * math.pi * j / tseg)) * r)
                     for j in range(tseg)])
    for i in range(n if closed else n - 1):
        for j in range(tseg):
            bm.faces.new([rows[i][j], rows[(i + 1) % n][j], rows[(i + 1) % n][(j + 1) % tseg], rows[i][(j + 1) % tseg]])
    return new_obj("tube", bm, material)


def frame_to(center, normal):
    """Matrix taking local z to `normal` at `center`."""
    rot = Vector((0, 0, 1)).rotation_difference(Vector(normal).normalized()).to_matrix().to_4x4()
    return Matrix.Translation(Vector(center)) @ rot


ORB = lambda: mat("robot_orb", (0.0, 0.32, 0.62), 0.0, 0.15, 1.5)              # noqa: E731
def HOT():
    m = mat("robot_orb_hot", (1.0, 1.0, 1.0), 0.0, 0.1, 0.0)
    bs = m.node_tree.nodes["Principled BSDF"]
    bs.inputs["Emission Color"].default_value = (0.85, 1.0, 1.0, 1)
    bs.inputs["Emission Strength"].default_value = 4.0
    return m      # noqa: E731


def orb_module(center, normal, R, back_depth=0.006):
    """Arc-reactor style light: a dark recessed housing, a chrome bezel (two rings + 4 clamps), a ring of 12 light
    segments, a glowing domed orb with a brighter inner core, and 3 thin chrome spokes over it. Local z = outward."""
    M = frame_to(center, normal)
    parts = []

    def L(p):
        return M @ Vector(p)
    nrm = (M.to_3x3() @ Vector((0, 0, 1))).normalized()
    parts.append(cylinder(L((0, 0, -back_depth)), L((0, 0, 0.002)), R * 1.32, BLACK(), 24))          # housing
    for rr, tb, z in ((R * 1.32, R * 0.16, 0.003), (R * 1.0, R * 0.07, 0.004)):                      # bezel rings
        o = ring((0, 0, 0), rr, rr, tb, CHROME(), seg=32, tseg=6)
        o.matrix_world = M @ Matrix.Translation((0, 0, z))
        parts.append(o)
    for k in range(12):                                                                               # light segments
        a = 2 * math.pi * (k + 0.5) / 12
        o = rounded_box((0, 0, 0), (R * 0.12, R * 0.2, R * 0.08), R * 0.025, LIGHT(), segs=1)
        o.matrix_world = M @ Matrix.Translation((math.cos(a) * R * 1.16, math.sin(a) * R * 1.16, 0.004)) @ \
            Matrix.Rotation(a + math.pi / 2, 4, "Z")
        parts.append(o)
    for k in range(4):                                                                                # clamps
        a = 2 * math.pi * k / 4 + math.pi / 4
        o = rounded_box((0, 0, 0), (R * 0.36, R * 0.22, R * 0.22), R * 0.05, CHROME(), segs=1)
        o.matrix_world = M @ Matrix.Translation((math.cos(a) * R * 1.42, math.sin(a) * R * 1.42, 0.004)) @ \
            Matrix.Rotation(a, 4, "Z")
        parts.append(o)
    bm = bmesh.new()                                                                                  # glowing dome
    bmesh.ops.create_uvsphere(bm, u_segments=28, v_segments=14, radius=1.0)
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, -0.2), plane_no=(0, 0, 1), clear_inner=True)
    bm.transform(M @ Matrix.Translation((0, 0, 0.002)) @ Matrix.Diagonal((R * 0.92, R * 0.92, R * 0.62, 1)))
    parts.append(new_obj("orb_dome", bm, ORB()))
    parts.append(sphere(L((0, 0, R * 0.5)), R * 0.24, HOT()))                                       # white-hot centre
    for k in range(3):                                                                                # spokes
        a = 2 * math.pi * k / 3 + math.pi / 2
        p0 = L((math.cos(a) * R * 0.95, math.sin(a) * R * 0.95, R * 0.12))
        p1 = L((math.cos(a) * R * 0.45, math.sin(a) * R * 0.45, R * 0.5))
        parts.append(cylinder(p0, p1, R * 0.05, CHROME(), 8))
    for o in parts:                                                                                   # bake transforms
        o.data.transform(o.matrix_world)
        o.matrix_world = Matrix.Identity(4)
    return parts


def join(obs, name, unwrap=True):
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    if unwrap:                     # (never on a textured garment: it would scramble its painted UVs)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.01)
        bpy.ops.object.mode_set(mode="OBJECT")
    return ob


BUDGET = {"hat": 6000, "collar": 1600, "jacket": 8000, "boots": 7000, **RP.get("budget", {})}   # triangles per piece


def export(ob, piece, meta):
    tris0 = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    if piece in BUDGET and tris0 > BUDGET[piece]:          # over budget: collapse-decimate the whole piece, keep UV seams
        bpy.context.view_layer.objects.active = ob
        ob.hide_set(False)
        dm = ob.modifiers.new("dec", "DECIMATE")
        dm.ratio = BUDGET[piece] / tris0
        dm.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier="dec")
        smooth_by_angle(ob, 50)
        print("DECIMATE", piece, tris0, "->", sum(len(p.vertices) - 2 for p in ob.data.polygons))
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
    k = np.max(np.sum(((S - c) / r) ** 2, 1) ** 0.5)
    r = r * k + H.get("margin", 0.012)
    eye = np.array(JS["LeftEye"]["head"])
    vb = (eye[2] - H.get("visor_below", 0.022) - c[2]) / r[2]
    vt = (eye[2] + H.get("visor_above", 0.02) - c[2]) / r[2]
    bot = H.get("bottom", -0.42)
    # shell: cut flat underneath, and a slanted cut under the visor in front (the beak comes out there)
    fc = vb - H.get("brow", 0.015) / r[2]
    keep_n = Vector((0, H.get("slant_y", 0.75), 1.0)).normalized()      # kept side: above / behind this plane
    planes = [((0, 0, bot), (0, 0, 1)), ((0, -0.55, fc), tuple(keep_n))]
    bm, loops = cut_dome(c, r, planes)
    shell = new_obj("helmet", bm, WHITE())
    shell.data.materials.append(BLACK())                 # inner lining (the solidify's inner faces) dark
    m_ = shell.modifiers.new("sol", "SOLIDIFY")
    m_.thickness = H.get("thick", 0.005)
    m_.offset = -1.0
    m_.use_even_offset = True
    m_.use_flip_normals = False
    m_.material_offset = 1
    m_.material_offset_rim = 0
    bpy.context.view_layer.objects.active = shell
    shell.hide_set(False)
    bpy.ops.object.modifier_apply(modifier="sol")
    parts = [shell]
    for lp in loops:                                                     # chrome trim round every edge
        parts.append(tube_along(lp, H.get("trim_r", 0.0032), CHROME()))
    # visor: the front band between vb and vt, proud of the shell, chrome frame, a bright scan line
    rv = [x + H.get("visor_proud", 0.004) for x in r]
    vback = H.get("visor_back", 0.2)
    bm, vloops = cut_dome(c, rv, [((0, 0, vb), (0, 0, 1)), ((0, 0, vt), (0, 0, -1)), ((0, vback, 0), (0, -1, 0))])
    visor = new_obj("visor", bm, VISOR())
    solidify(visor, 0.003, offset=1.0)
    parts.append(visor)
    for lp in vloops:
        parts.append(tube_along(lp, 0.0028, CHROME(), push=(c, 0.002)))
    mid = (vb + vt) / 2
    bm, _ = cut_dome(c, [x + 0.0032 for x in rv], [((0, 0, mid - 0.022), (0, 0, 1)), ((0, 0, mid + 0.022), (0, 0, -1)),
                                                   ((0, vback - 0.1, 0), (0, -1, 0))], seg=64, rings=40)
    parts.append(new_obj("scan", bm, LIGHT()))
    # crest: a raised white ridge from above the visor over the top to the back, a light line along it
    crest = []
    for deg in np.linspace(-10, 120, 30):                                # angle up from straight ahead, over the top
        a = math.radians(deg)
        d = Vector((0, -math.cos(a), math.sin(a)))
        if d.z < vt + 0.14:
            continue
        p = Vector(c) + Vector((0, d.y * r[1], d.z * r[2]))
        crest.append(p + (p - Vector(c)).normalized() * 0.002)
    if len(crest) > 3:
        parts.append(tube_along(crest, H.get("crest_r", 0.009), WHITE(), closed=False, tseg=12))
        parts.append(tube_along([p + (p - Vector(c)).normalized() * 0.0088 for p in crest], 0.0022, LIGHT(), closed=False))
    # ear discs: chrome housing, recessed black face, light ring, centre bolt, three vent slots behind
    ez = (eye[2] - c[2]) / r[2]
    for sx in (1, -1):
        y0 = c[1] + H.get("ear_y", 0.02)
        x0 = c[0] + sx * r[0] * math.sqrt(max(0.0, 1 - ((y0 - c[1]) / r[1]) ** 2 - ez ** 2))
        parts.append(cylinder((x0 - sx * 0.006, y0, eye[2]), (x0 + sx * 0.010, y0, eye[2]), H.get("ear_r", 0.026), CHROME(), 24))
        parts.append(cylinder((x0 + sx * 0.010, y0, eye[2]), (x0 + sx * 0.0115, y0, eye[2]), 0.018, BLACK(), 20))
        o = ring((0, 0, 0), 0.0135, 0.0135, 0.0025, LIGHT(), seg=24, tseg=6)
        o.data.transform(frame_to((x0 + sx * 0.0125, y0, eye[2]), (sx, 0, 0)))
        parts.append(o)
        parts.append(cylinder((x0 + sx * 0.011, y0, eye[2]), (x0 + sx * 0.016, y0, eye[2]), 0.006, CHROME(), 16))
        for kk in range(3):
            yy = y0 + 0.038 + kk * 0.011
            zz = eye[2] - 0.004
            dx = r[0] * math.sqrt(max(0.0, 1 - ((yy - c[1]) / r[1]) ** 2 - ((zz - c[2]) / r[2]) ** 2))
            parts.append(rounded_box((c[0] + sx * (dx + 0.001), yy, zz), (0.006, 0.005, 0.026), 0.002, BLACK(), segs=1))
    top = Vector(c) + Vector((r[0] * 0.38, r[1] * 0.3, r[2] * 0.86))
    parts.append(cylinder(top - Vector((0, 0, 0.012)), top + Vector((0, 0, 0.006)), 0.007, CHROME(), 16))
    parts.append(cylinder(top, top + Vector((0, 0.01, H.get("antenna", 0.07))), 0.0028, CHROME(), 10))
    parts.append(sphere(top + Vector((0, 0.01, H.get("antenna", 0.07) + 0.005)), 0.0075, ORB()))
    ob = smooth_by_angle(join(parts, "hat"), 50)
    export(ob, "hat", {"center": c.round(4).tolist(), "radii": r.round(4).tolist()})


# ------------------------------------------------------------------ collar (neckwear)
def make_collar():
    C = RP.get("collar", {})
    z = C.get("z", 1.30)
    s = np.abs(BV[:, 2] - z) < 0.008
    cx, cy = 0.0, float((BV[s, 1].min() + BV[s, 1].max()) / 2)
    rx = float(np.abs(BV[s, 0]).max()) + C.get("clear", 0.016)
    ry = float((BV[s, 1].max() - BV[s, 1].min()) / 2) + C.get("clear", 0.016)
    nrm = C.get("normal", (0, 0.12, 1))
    tb = C.get("tube", 0.011)
    parts = [ring((cx, cy, z), rx, ry, tb, CHROME(), normal=nrm)]
    parts.append(ring((cx, cy, z + tb * 0.9), rx - 0.002, ry - 0.002, 0.0022, LIGHT(), normal=nrm))
    # a lower, wider ring under it: a gorget band that closes the gap down to the chest plate's neckline
    z2 = z - C.get("band_drop", 0.019)
    s2 = np.abs(BV[:, 2] - z2) < 0.008
    cy2 = float((BV[s2, 1].min() + BV[s2, 1].max()) / 2)
    rx2 = float(np.abs(BV[s2, 0]).max()) + C.get("clear", 0.016)
    ry2 = float((BV[s2, 1].max() - BV[s2, 1].min()) / 2) + C.get("clear", 0.016)
    parts.append(ring((cx, cy2, z2), rx2, ry2, tb * 1.05, CHROME(), normal=nrm))
    parts.append(ring((cx, (cy + cy2) / 2, (z + z2) / 2), (rx + rx2) / 2 + tb * 0.55, (ry + ry2) / 2 + tb * 0.55, 0.0018, BLACK(), normal=nrm))
    ob = smooth_by_angle(join(parts, "collar"), 60)
    export(ob, "collar", {"z": z, "rx": rx, "ry": ry})


def dome_cap(c, r_vec, nd, keep, mat_, thick, trim=0.0028):
    """A clean cap: ellipsoid cut by the plane `keep` along nd (unit-sphere space), solid, chrome trim round its edge and
    a light line a little inside it."""
    bm, loops = cut_dome(c, r_vec, [(tuple(Vector(nd) * keep), tuple(nd))], seg=32, rings=18)
    ob = new_obj("cap", bm, mat_)
    solidify(ob, thick, offset=-1.0)
    out = [ob]
    for lp in loops:
        out.append(tube_along(lp, trim, CHROME(), push=(c, 0.0005)))
    bm2, loops2 = cut_dome(c, [x + 0.0015 for x in r_vec], [(tuple(Vector(nd) * (keep + 0.12)), tuple(nd))], seg=32, rings=18)
    bm2.free()
    for lp in loops2:
        out.append(tube_along(lp, 0.0016, LIGHT()))
    return out


def dome_r(c, nd, keep, clear, sel_r, rmin, rmax):
    """Radius that clears every body vertex near joint c in the kept direction, plus `clear` (garments under it)."""
    rel = BV - c
    dd = np.linalg.norm(rel, axis=1)
    near = (dd < sel_r) & ((rel / np.maximum(dd[:, None], 1e-9)) @ np.array(nd) > keep)
    return float(np.clip((dd[near].max() if near.any() else rmin) + clear, rmin, rmax))


# ------------------------------------------------------------------ jacket: caps, power pack, antenna
def make_jacket():
    Jc = RP.get("jacket", {})
    under = [BODY_BVH, shell_bvh("shirt"), shell_bvh("waistcoat")]
    parts, rigid = [], []
    pc = Jc.get("pack", {})
    W_, D_, H_ = pc.get("size", [0.15, 0.055, 0.17])
    zc = pc.get("z", 1.14)
    hits = [t.ray_cast(Vector((0, 0.5, zc)), Vector((0, -1, 0)))[0] for t in under if t is not None]
    yb = max(h.y for h in hits if h is not None)
    cy = yb + pc.get("gap", 0.006) + D_ / 2
    yo = cy + D_ / 2
    parts.append(rounded_box((0, cy, zc), (W_, D_, H_), 0.016, CHROME()))                          # body
    parts.append(rounded_box((0, yo - 0.002, zc), (W_ * 0.86, 0.006, H_ * 0.88), 0.01, BLACK()))      # seam gap
    parts.append(rounded_box((0, yo + 0.001, zc + 0.004), (W_ * 0.8, 0.006, H_ * 0.82), 0.009, WHITE()))  # face panel
    parts += orb_module((0, yo + 0.004, zc + H_ * 0.13), (0, 1, 0), pc.get("orb_r", 0.026))
    for kk in range(4):                                                                            # vent slats
        zz = zc - H_ * 0.18 - kk * 0.011
        parts.append(rounded_box((0, yo + 0.003, zz), (W_ * 0.5, 0.004, 0.006), 0.0018, BLACK(), segs=1))
        parts.append(rounded_box((0, yo + 0.005, zz - 0.0055), (W_ * 0.52, 0.004, 0.0025), 0.001, CHROME(), segs=1))
    for sx in (1, -1):
        for sz in (1, -1):                                                                         # corner bolts
            q = (sx * W_ * 0.34, yo + 0.003, zc + sz * H_ * 0.36)
            parts.append(cylinder(q, (q[0], yo + 0.007, q[2]), 0.0045, CHROME(), 12))
        parts.append(rounded_box((sx * (W_ / 2 + 0.002), cy, zc), (0.006, D_ * 0.55, H_ * 0.74), 0.002, CHROME()))
        parts.append(rounded_box((sx * (W_ / 2 + 0.004), cy, zc), (0.004, D_ * 0.36, H_ * 0.66), 0.0015, LIGHT()))
    ax_ = pc.get("antenna_x", 0.045)
    a0 = Vector((ax_, cy, zc + H_ / 2 - 0.004))
    parts.append(cylinder(a0 - Vector((0, 0, 0.004)), a0 + Vector((0, 0, 0.014)), 0.008, CHROME(), 16))
    a1 = a0 + Vector((0, 0.01, pc.get("antenna", 0.13)))
    parts.append(cylinder(a0, a1, 0.0035, CHROME(), 10))
    parts.append(sphere(a1 + Vector((0, 0, 0.006)), 0.0085, ORB()))
    for sx in (1, -1):                                                                             # exhaust ports
        p0 = Vector((sx * W_ * 0.25, cy, zc - H_ / 2 + 0.004))
        parts.append(cylinder(p0, p0 - Vector((0, 0, 0.014)), 0.012, CHROME(), 20))
        parts.append(cylinder(p0 - Vector((0, 0, 0.012)), p0 - Vector((0, 0, 0.0145)), 0.008, ORB(), 20))
    rigid.append({"bone": "Spine2", "center": [0, cy, zc + 0.04], "radius": 0.2})
    sc = Jc.get("shoulder", {})
    ec = Jc.get("elbow", {})
    for sx, side in ((1, "Left"), (-1, "Right")):
        c = J(f"{side}Arm") + np.array(sc.get("offset", [0.02, 0.0, -0.005])) * [sx, 1, 1]
        nd = Vector((sx * 0.6, 0, 0.8)).normalized()
        r_ = dome_r(c, nd, sc.get("keep", 0.3), sc.get("clear", 0.03), 0.11, 0.05, 0.095)
        parts += dome_cap(c, [r_, r_, r_ * sc.get("squash", 0.85)], nd, sc.get("keep", 0.3), CHROME(), 0.005)
        rigid.append({"bone": f"{side}Arm", "center": c.round(4).tolist(), "radius": r_ + 0.03})
        c = J(f"{side}ForeArm")
        ax = J(f"{side}Hand") - J(f"{side}Arm")
        ax /= np.linalg.norm(ax)
        back = np.array([0.0, 1.0, 0.0]) - ax * ax[1]
        back /= np.linalg.norm(back)
        nd = Vector(back * 0.9 + np.array([sx * 0.3, 0, 0])).normalized()
        r_ = dome_r(c, nd, ec.get("keep", 0.35), ec.get("clear", 0.014), 0.06, 0.035, 0.06)
        parts += dome_cap(c, [r_, r_, r_], nd, ec.get("keep", 0.35), CHROME(), 0.004, trim=0.0024)
        rigid.append({"bone": f"{side}ForeArm", "center": c.round(4).tolist(), "radius": r_ + 0.02})
    ob = smooth_by_angle(join(parts, "jacket"), 50)
    export(ob, "jacket", {"rigid_parts": rigid})


# ------------------------------------------------------------------ vest: the 3D chest orb on the chest plate
def make_vest():
    import shutil
    Vc = RP.get("vest", {})
    src = D / "versions" / "waistcoat_preorb.glb"
    meta_f = SHD / "waistcoat.json"
    meta = json.loads(meta_f.read_text(encoding="utf-8"))
    if not meta.get("orb"):                 # a fresh build (build_cyclist rewrote the json): it becomes the source
        shutil.copy(SHD / "waistcoat.glb", src)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(src))
    plate = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in plate:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = plate[0]
    if len(plate) > 1:
        bpy.ops.object.join()
    po = bpy.context.view_layer.objects.active
    po.data.transform(po.matrix_world)
    po.matrix_world = Matrix.Identity(4)
    for m in po.data.materials:             # the plate's own chrome: brighter, full metal
        bs = m.node_tree.nodes.get("Principled BSDF") if m and m.node_tree else None
        if bs is not None and bs.inputs["Metallic"].default_value > 0.5:
            bs.inputs["Metallic"].default_value = 0.75
            bs.inputs["Roughness"].default_value = 0.24
            for l_ in list(bs.inputs["Normal"].links):      # no cloth-fold normal map on hard metal
                m.node_tree.links.remove(l_)
    lap = po.modifiers.new("lap", "LAPLACIANSMOOTH")      # the plate followed the body's bumps: smooth it (volume kept)
    lap.iterations = Vc.get("smooth_iter", 12)
    lap.lambda_factor = Vc.get("smooth_lambda", 1.2)
    lap.lambda_border = 0.0
    lap.use_volume_preserve = True
    bpy.context.view_layer.objects.active = po
    po.hide_set(False)
    bpy.ops.object.modifier_apply(modifier="lap")
    tree = BVHTree.FromObject(po, bpy.context.evaluated_depsgraph_get())
    oz = Vc.get("z", 1.15)
    hit, n, _, _ = tree.ray_cast(Vector((0, -0.5, oz)), Vector((0, 1, 0)))
    n = Vector((0, -1, 0)) if n is None or n.y > 0 else n
    n = (n + Vector((0, -1, 0))).normalized()
    parts = [po] + orb_module(hit + n * 0.001, n, Vc.get("orb_r", 0.03), back_depth=0.008)
    ob = join(parts, "waistcoat", unwrap=False)
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(SHD / "waistcoat.glb"), export_format="GLB", use_selection=True)
    meta["orb"] = {"z": oz, "r": Vc.get("orb_r", 0.03), "at": [round(x, 4) for x in hit]}
    meta_f.write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print("PART waistcoat + orb at", [round(x, 3) for x in hit])


# ------------------------------------------------------------------ boots: recolour + bands + knee caps
def make_boots():
    Bc = RP.get("boots", {})
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(D / "versions" / "boots_v1_geo.glb"))   # make_boot's own output (no parts)
    bo = [o for o in bpy.data.objects if o not in before and o.type == "MESH"][0]
    bo.data.transform(bo.matrix_world)
    bo.matrix_world = Matrix.Identity(4)
    for i, m in enumerate(bo.data.materials):
        bo.data.materials[i] = CHROME() if "sole" in m.name else WHITE()
    bd = cfg["boot_design"]
    parts, rigid = [bo], []
    for sx, side in ((1, "Left"), (-1, "Right")):
        x0 = sx * bd["centre_x"]
        for (zz, hw, hd, yc), tube, material, grow in ((Bc.get("ankle", [0.14, 0.038, 0.045, 0.04]), 0.008, CHROME(), 0.004),
                                                       (Bc.get("top", [0.425, 0.079, 0.085, 0.043]), 0.0035, LIGHT(), 0.0)):
            parts.append(ring((x0, yc, zz), hw + grow, hd + grow, tube, material, seg=24, tseg=6))
        kc = Bc.get("knee", {})
        c = np.array([x0, kc.get("y", -0.012), kc.get("z", 0.372)])
        parts += dome_cap(c, kc.get("radii", [0.05, 0.05, 0.058]), Vector((0, -1, 0)), kc.get("keep", 0.45), CHROME(), 0.005, trim=0.0026)
        rigid.append({"bone": f"{side}Leg", "center": c.round(4).tolist(), "radius": 0.07})
    meta = json.loads((SHD / "boots.json").read_text(encoding="utf-8")) if (SHD / "boots.json").exists() else {}
    ob = smooth_by_angle(join(parts, "boots"), 50)
    meta.pop("tris", None)
    export(ob, "boots", {**{k: v for k, v in meta.items() if k not in ("char", "piece", "source", "rigid_parts")}, "rigid_parts": rigid})


for p in PIECES:
    {"hat": make_hat, "collar": make_collar, "jacket": make_jacket, "boots": make_boots, "vest": make_vest}[p]()
