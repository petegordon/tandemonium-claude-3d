"""Fit the shared eye asset (assets/goose_eye, scripts/make_eye_asset.py) into a goose head
(PLAN P1.6). Runs on the game mesh after the bake.

1. Erase the generator's painted eye: texels within `erase_radius` of each eye (exact 3D
   distance per texel) that are not near-black become the surrounding head colour.
2. Socket: subdivide the head locally; delete head faces entirely in front of the lid
   opening, snap the remaining in-front vertices onto the lid rim curve, and wrap the skin
   around the eye just over the lid shell, blending back to the original surface.
3. Eyes: the asset's eyeball / lid_upper / lid_lower / catchlight become child objects of
   the head, named *_L / *_R, each with its origin at the eye centre (rig pivots). The right
   eye is a true mirror (mesh mirrored, object transform a proper rotation). Lid material
   colour is matched to the head colour sampled around the eye.
4. Object props eye_L/R_center, eye_L/R_axis and blink angles for the rig.

left = {"point": [...], "normal": [...]}: surface pick on the +X (character's left) eye from
`head_views.py --pick`; the right eye is its mirror across X = 0 (symmetric base goose).
"""
import json
import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from .common import input_image, read_pixels, rgb_to_hsv, texel_positions, write_pixels

NAME = "eye_sockets"
STAGE = "game"
DEFAULTS = {
    "left": None,
    "asset": "assets/goose_eye",
    "proud": 0.002,            # lid shell front above the head surface (m)
    "erase_radius": 0.024,     # painted-eye texels within this of the eye surface point (m)
    "subdivide_cuts": 2,
}
MIRROR = Matrix.Scale(-1, 4, Vector((1, 0, 0)))


def _opening_f(spec, az, el):
    ha, pw = spec["opening_half_angle_deg"], spec["opening_power"]
    h, p = (ha[0], pw[0]) if az >= 0 else (ha[1], pw[1])
    return (abs(az) / h) ** p + (abs(el) / ha[2]) ** p


def _eye_matrix(p, n, r_lid, proud):
    a = Vector((0, -1, 0))
    a = (a - a.dot(n) * n).normalized()
    u = Vector((0, 0, 1))
    u = (u - u.dot(n) * n - u.dot(a) * a).normalized()
    m = Matrix((a, -n, u)).transposed().to_4x4()
    m.translation = p - n * (r_lid - proud)
    return m


def _erase(ob, points, radius):
    img = input_image(ob, "Base Color")
    px = read_pixels(img)
    h, w = px.shape[:2]
    pos = texel_positions(ob, w, h)
    val = rgb_to_hsv(px[..., :3])[..., 2]
    total = 0
    for p in points:
        d = np.linalg.norm(pos - np.array(p, np.float32), axis=-1)
        inner = d < radius
        ring = (d > radius) & (d < radius * 1.6) & (val < 0.2)
        if not ring.any():
            continue
        fix = inner & (val > 0.1)
        px[fix, :3] = np.median(px[ring, :3], 0)
        total += int(fix.sum())
    write_pixels(img, px)
    return total


def _carve(ob, m, spec, cuts):
    r_eye = spec["eyeball_radius"]
    r_lid = r_eye * spec["lid_radius_scale"]
    to_eye, to_obj = m.inverted(), m
    centre = m.translation
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    near = [f for f in bm.faces if (f.calc_center_median() - centre).length < r_lid * 1.6]
    bmesh.ops.subdivide_edges(bm, edges=list({e for f in near for e in f.edges}), cuts=cuts, use_grid_fill=True)
    # neighbours of the subdivided patch become n-gons; tangent export (MikkTSpace) needs tris/quads
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    def eye_dir(v):
        q = to_eye @ v.co
        r = q.length
        d = q / r if r > 1e-9 else Vector((0, 1, 0))
        az = math.degrees(math.atan2(d.x, -d.y))
        el = math.degrees(math.asin(max(-1.0, min(1.0, d.z))))
        f = _opening_f(spec, az, el) if d.y < 0 else 9.0
        return r, d, az, el, f

    info = {v: eye_dir(v) for v in bm.verts}
    in_front = {v for v, (r, d, az, el, f) in info.items() if f < 1.0 and r < r_lid * 1.15}
    # faces entirely in front of the opening go: the head's hole follows the lid rim
    dead = [f for f in bm.faces if all(v in in_front for v in f.verts)]
    bmesh.ops.delete(bm, geom=dead, context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    moved = len(dead)
    for v in bm.verts:
        r, d, az, el, f = info[v]
        if r > r_lid * 1.3:
            continue
        if v in in_front:                           # straddling the edge: snap onto the rim curve
            p = spec["opening_power"][0 if az >= 0 else 1]
            sc = f ** (-1.0 / p)
            a_, e_ = math.radians(az * sc), math.radians(el * sc)
            rim = Vector((math.sin(a_) * math.cos(e_), -math.cos(a_) * math.cos(e_), math.sin(e_)))
            v.co = to_obj @ (rim * r_lid * 1.03)
            moved += 1
            continue
        target = r_lid * 1.03                       # around the eye: skin just over the lid shell
        if r < target:
            v.co = to_obj @ (d * target)
            moved += 1
        else:                                       # blend back to the original surface
            t = (r - target) / (r_lid * 1.3 - target)
            v.co = to_obj @ (d * (target + (r - target) * t ** 0.5))
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    return moved


def _head_colour_near(ob, p, r0, r1):
    img = input_image(ob, "Base Color")
    px = read_pixels(img)
    h, w = px.shape[:2]
    pos = texel_positions(ob, w, h)
    d = np.linalg.norm(pos - np.array(p, np.float32), axis=-1)
    ring = (d > r0) & (d < r1) & (rgb_to_hsv(px[..., :3])[..., 2] < 0.2)
    return np.median(px[ring, :3], 0) if ring.any() else np.array([0.05, 0.045, 0.04])


_SHARED_MATS = {}


def _add_eye(ob, root, m, side, lid_rgb):
    glb = root / "goose_eye.glb"
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(glb))
    parts = [o for o in bpy.data.objects if o not in before]
    out = {}
    world = m if side == "L" else MIRROR @ m @ MIRROR      # proper rotation for the right eye
    for o in parts:
        o.data.transform(o.matrix_basis)                   # bake rest pose (eyeball gaze) into data
        o.matrix_basis = Matrix.Identity(4)
        if side == "R":
            o.data.transform(MIRROR)
            o.data.flip_normals()
        base = o.name.split(".")[0]
        o.name = o.data.name = f"{base}_{side}"
        o.parent = ob
        o.matrix_world = world
        mat = o.data.materials[0]
        key = mat.name.split(".")[0]
        if key in _SHARED_MATS:                            # both eyes share one set of materials
            o.data.materials[0] = _SHARED_MATS[key]
            bpy.data.materials.remove(mat)
        else:
            mat.name = key
            _SHARED_MATS[key] = mat
            if base.startswith("lid"):
                pb = next(nd for nd in mat.node_tree.nodes if nd.type == "BSDF_PRINCIPLED")
                pb.inputs["Base Color"].default_value = (*[float(c) ** 2.2 for c in lid_rgb], 1)
        out[base] = o
    return out


def apply(ctx, left, asset, proud, erase_radius, subdivide_cuts):
    if left is None:
        raise ValueError("eye_sockets: give left={'point','normal'} (head_views.py --pick)")
    ob = ctx.ob
    root = ctx.root / asset
    meta = json.loads((root / "goose_eye.json").read_text())
    spec = meta["spec"]
    r_lid = spec["eyeball_radius"] * spec["lid_radius_scale"]
    p = Vector(left["point"])
    n = Vector(left["normal"]).normalized()
    m_left = _eye_matrix(p, n, r_lid, proud)
    m_right = MIRROR @ m_left                               # placement (det -1) for carving
    p_right = Vector((-p.x, p.y, p.z))
    stats = {"erased_texels": _erase(ob, [p, p_right], erase_radius)}
    lid_rgb = _head_colour_near(ob, p, erase_radius, erase_radius * 1.8)
    stats["lid_rgb"] = [round(float(c), 3) for c in lid_rgb]
    stats["socket_verts"] = [_carve(ob, m_left, spec, subdivide_cuts), _carve(ob, m_right, spec, subdivide_cuts)]
    names = []
    _SHARED_MATS.clear()
    for side, m in (("L", m_left), ("R", m_left)):
        parts = _add_eye(ob, root, m, side, lid_rgb)
        names += [o.name for o in parts.values()]
        c = (m if side == "L" else MIRROR @ m).translation
        axis = -(m.to_3x3().col[1]) if side == "L" else -(MIRROR.to_3x3() @ m.to_3x3().col[1])
        ob[f"eye_{side}_center"] = [round(float(x), 5) for x in c]
        ob[f"eye_{side}_axis"] = [round(float(x), 4) for x in axis.normalized()]
    ob["eye_blink_closed_deg"] = json.dumps(meta["blink_closed_deg"])
    stats.update(eye_objects=names, tris_head=sum(len(f.vertices) - 2 for f in ob.data.polygons),
                 eye_L_center=list(ob["eye_L_center"]), eye_R_center=list(ob["eye_R_center"]))
    return stats
