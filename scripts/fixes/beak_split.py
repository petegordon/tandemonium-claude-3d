"""Split the lower bill so the goose can open its beak / honk (PLAN P1.7). Runs on the game
mesh after the bake.

The generated bill is one closed shape. A plane through the mouth line (from the bill tip to
the mouth corners, containing the X axis) cuts the bill in front of the gape; the cut edges
are split so upper and lower bill separate, but stay joined at the two mouth corners. Inside:
- caps over each cut (roof / floor of the mouth) in a mouth colour,
- serrations (tomia "teeth") just inside the rim of both bill halves, pointing at the other half,
- a tongue on the mouth floor with spiky serrated edges, movable by its own bone.
All interior parts are hidden while the bill is closed. Colours live in the reserved atlas
strip: thirds = mouth / tongue / serrations (base colour, ORM, flat normal).

Rig data:
- vertex group "beak_lower": lower bill + floor + lower serrations + tongue (1 in front of the
  gape, fading to 0 just behind it so the chin skin stretches instead of tearing);
- vertex group "tongue": tongue only, weight ramping 0.25 at the root -> 1 at the tip (a
  single tongue bone, child of the jaw bone, lifts/curls and pokes it out);
- object props beak_hinge_point / beak_hinge_axis / beak_open_deg, tongue_root / tongue_axis /
  tongue_up.

mouth: {"tip": [y, z], "gape": [y, z]} in metres on the model's centre plane (x = 0).
"""
import math

import bmesh
import numpy as np
from mathutils import Vector

from .common import input_image, read_pixels, write_pixels

NAME = "beak_split"
STAGE = "game"
DEFAULTS = {
    "mouth": None,                   # {"tip": [y, z], "gape": [y, z]}
    "half_width": 0.06,              # |x| limit of the bill region (m)
    "z_band": [0.04, 0.06],          # region below / above the mouth line (m)
    "fade_behind_gape": 0.015,       # beak_lower weight fades to 0 over this distance behind the gape
    "mouth_rgb": [0.30, 0.14, 0.14],
    "tongue": {"length_frac": 0.6, "half_width": 0.017, "thickness": 0.007, "rgb": [0.78, 0.45, 0.47],
               "spikes_per_side": 7, "spike_len": 0.0028},
    "serrations": {"spacing": 0.007, "height": 0.0021, "inset": 0.0032, "rgb": [0.72, 0.68, 0.62]},
    "open_deg": 28,
}
U_MOUTH, U_TONGUE, U_TEETH = 1 / 6, 0.5, 5 / 6        # strip thirds


def _paint_strip(img, rows, cols):
    """Fill the reserved top rows with three colour bands (mouth / tongue / serrations)."""
    px = read_pixels(img)
    h, w = px.shape[:2]
    for k, c in enumerate(cols):
        px[h - rows:, k * w // 3:(k + 1) * w // 3, :3] = c
    px[h - rows:, :, 3] = 1.0
    write_pixels(img, px)


def _order_chain(edges):
    """Boundary edges forming one open path -> ordered vertex list."""
    adj = {}
    for e in edges:
        a, b = e.verts
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    ends = [v for v, n in adj.items() if len(n) == 1]
    if len(ends) != 2:
        raise RuntimeError(f"beak_split: cut boundary is not a single open path (ends={len(ends)})")
    path, prev = [ends[0]], None
    while len(path) < len(adj):
        nxt = [n for n in adj[path[-1]] if n is not prev]
        prev = path[-1]
        path.append(nxt[0])
    return path


def _set_uv(faces, uvl, uv, smooth=True):
    for f in faces:
        f.smooth = smooth
        for lp in f.loops:
            lp[uvl].uv = uv


def _add_tongue(bm, uvl, gape, tip, no, spec, uv):
    """Tapered, rounded, domed tongue lying on the mouth floor, with backward-pointing spikes
    along both edges (goose tongues are serrated). Returns {vert: along-fraction}, faces, frame."""
    a = (tip - gape).normalized()
    side = Vector((1, 0, 0))
    length = (tip - gape).length * spec["length_frac"]
    w0, th = spec["half_width"], spec["thickness"]
    n_s, n_r = 10, 12
    start = 0.06 * (tip - gape).length
    root = gape + a * start + no * 0.0004
    rings, frac = [], {}
    for i in range(n_s + 1):
        t = i / n_s
        width = w0 * (1 - 0.45 * t ** 1.6) * (math.sqrt(max(0.0, 1 - ((t - 0.82) / 0.18) ** 2)) if t > 0.82 else 1)
        height = th * (1 - 0.45 * t)
        centre = root + a * (length * t)
        ring = []
        for j in range(n_r):                           # dome on top, flat underside
            ang = math.pi * j / (n_r - 1)
            v = bm.verts.new(centre + side * (math.cos(ang) * max(width, 0.0008)) + no * (math.sin(ang) * height))
            frac[v] = t
            ring.append(v)
        rings.append(ring)
    faces = []
    for i in range(n_s):
        for j in range(n_r - 1):
            faces.append(bm.faces.new([rings[i][j], rings[i + 1][j], rings[i + 1][j + 1], rings[i][j + 1]]))
        faces.append(bm.faces.new([rings[i][-1], rings[i + 1][-1], rings[i + 1][0], rings[i][0]]))
    faces.append(bm.faces.new(rings[0][::-1]))
    faces.append(bm.faces.new(rings[-1]))
    # edge spikes: small 3-sided cones on both sides, pointing out and back
    sl = spec["spike_len"]
    for k in range(spec["spikes_per_side"]):
        i = 1 + round(k * (n_s - 3) / max(1, spec["spikes_per_side"] - 1))
        for j, out in ((0, side), (n_r - 1, -side)):
            p = rings[i][j].co.copy() + no * 0.0012
            t_ = frac[rings[i][j]]
            b = [bm.verts.new(p + a * 0.0012), bm.verts.new(p - a * 0.0012), bm.verts.new(p + no * 0.0014)]
            apex = bm.verts.new(p + out * sl - a * sl * 0.6 + no * 0.0004)
            for v in (*b, apex):
                frac[v] = t_
            faces += [bm.faces.new([b[0], b[1], apex]), bm.faces.new([b[1], b[2], apex]),
                      bm.faces.new([b[2], b[0], apex])]
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    _set_uv(faces, uvl, uv)
    return frac, faces, root, a


def _add_serrations(bm, uvl, path, point_dir, gape, no, spec, uv):
    """Small pale teeth along a cap rim, inset into the mouth, pointing at the other bill half."""
    pts = [v.co.copy() for v in path]
    seg = [(pts[i + 1] - pts[i]).length for i in range(len(pts) - 1)]
    total = sum(seg)
    centre = sum(pts, Vector()) / len(pts)
    verts, faces = [], []
    s = 2 * spec["spacing"]                             # none near the mouth corners (narrow bill)
    while s < total - 2 * spec["spacing"]:
        acc, i = 0.0, 0
        while acc + seg[i] < s:
            acc += seg[i]
            i += 1
        t = (s - acc) / seg[i]
        p = pts[i].lerp(pts[i + 1], t)
        tang = (pts[i + 1] - pts[i]).normalized()
        inward = centre - p
        inward = (inward - inward.dot(no) * no).normalized()
        c = p + inward * spec["inset"]
        b = [bm.verts.new(c - tang * 0.0012), bm.verts.new(c + tang * 0.0012), bm.verts.new(c + inward * 0.0012)]
        apex = bm.verts.new(c + inward * 0.0004 + point_dir * spec["height"])
        faces += [bm.faces.new([b[0], b[1], apex]), bm.faces.new([b[1], b[2], apex]),
                  bm.faces.new([b[2], b[0], apex])]
        verts += [*b, apex]
        s += spec["spacing"]
    bmesh.ops.recalc_face_normals(bm, faces=faces)
    _set_uv(faces, uvl, uv, smooth=False)
    return set(verts), faces


def apply(ctx, mouth, half_width, z_band, fade_behind_gape, mouth_rgb, tongue, serrations, open_deg):
    if mouth is None:
        raise ValueError("beak_split: give mouth={'tip': [y, z], 'gape': [y, z]}")
    ob, me = ctx.ob, ctx.ob.data
    rows = int(ob.get("uv_reserved_rows", 0))
    tip = Vector((0, *mouth["tip"]))
    gape = Vector((0, *mouth["gape"]))
    along = (gape - tip).normalized()
    no = Vector((1, 0, 0)).cross(along).normalized()       # plane normal, points up-ish
    if no.z < 0:
        no = -no

    def in_region(co):
        return (abs(co.x) < half_width and co.y < gape.y + 0.004 and
                -z_band[0] < (co - gape).dot(no) < z_band[1])

    bm = bmesh.new()
    bm.from_mesh(me)
    faces = [f for f in bm.faces if in_region(f.calc_center_median())]
    geom = list({v for f in faces for v in f.verts}) + list({e for f in faces for e in f.edges}) + faces
    res = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=gape, plane_no=no, dist=1e-5)
    cut = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMEdge)
           and all(abs((v.co - gape).dot(no)) < 1e-4 for v in e.verts)
           and (e.verts[0].co.y + e.verts[1].co.y) / 2 < gape.y and all(abs(v.co.x) < half_width for v in e.verts)]
    bmesh.ops.split_edges(bm, edges=cut)
    bm.edges.ensure_lookup_table()
    bnd = [e for e in bm.edges if e.is_boundary and all(abs((v.co - gape).dot(no)) < 1e-4 for v in e.verts)
           and all(v.co.y < gape.y + 1e-4 for v in e.verts)]
    upper = [e for e in bnd if (e.link_faces[0].calc_center_median() - gape).dot(no) > 0]
    lower = [e for e in bnd if e not in upper]
    uvl = bm.loops.layers.uv.active
    tex_h = input_image(ob, "Base Color").size[1]
    v_mid = 1.0 - rows / 2.0 / tex_h if rows else 0.999
    caps, paths = [], {}
    for name, chain, want in (("upper", upper, -no), ("lower", lower, no)):   # roof down, floor up
        path = _order_chain(chain)
        paths[name] = path
        f = bm.faces.new(path)
        if f.normal.dot(want) < 0:
            f.normal_flip()
        _set_uv([f], uvl, (U_MOUTH, v_mid), smooth=False)
        caps.append(f)
    corners = sorted({v.co.copy().freeze() for v in (paths["upper"][0], paths["upper"][-1])}, key=lambda c: c.x)
    teeth_up, f_up = _add_serrations(bm, uvl, paths["upper"], -no, gape, no, serrations, (U_TEETH, v_mid))
    teeth_lo, f_lo = _add_serrations(bm, uvl, paths["lower"], no, gape, no, serrations, (U_TEETH, v_mid))
    tri = bmesh.ops.triangulate(bm, faces=caps)["faces"]
    tongue_frac, t_faces, t_root, t_axis = ({}, [], gape, -along)
    if tongue:
        tongue_frac, t_faces, t_root, t_axis = _add_tongue(bm, uvl, gape, tip, no, tongue, (U_TONGUE, v_mid))
    # bisect leaves n-gons; tangent export (MikkTSpace) needs tris/quads
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    bm.verts.index_update()
    lower_w, tongue_w = {}, {}
    for v in bm.verts:
        if v in tongue_frac:
            lower_w[v.index] = 1.0
            tongue_w[v.index] = 0.25 + 0.75 * tongue_frac[v]
            continue
        if v in teeth_lo:
            lower_w[v.index] = 1.0
            continue
        if v in teeth_up:
            continue
        d = (v.co - gape).dot(no)
        if abs(v.co.x) >= half_width or v.co.y > gape.y + fade_behind_gape or d < -z_band[0]:
            continue
        if abs(d) <= 1e-4:                                 # on the cut: go by the side of its faces
            sides = [(f.calc_center_median() - gape).dot(no) for f in v.link_faces]
            if not sides or max(sides) > 1e-5:
                continue
        elif d > 0:
            continue
        w = 1.0 if v.co.y < gape.y else 1.0 - (v.co.y - gape.y) / fade_behind_gape
        if w > 0:
            lower_w[v.index] = w
    n_faces = {"caps": len(tri), "serrations": len(f_up) + len(f_lo), "tongue": len(t_faces)}
    bm.to_mesh(me)
    bm.free()
    me.update()
    for gname, wts in (("beak_lower", lower_w), ("tongue", tongue_w)):
        vg = ob.vertex_groups.get(gname) or ob.vertex_groups.new(name=gname)
        for i, w in wts.items():
            vg.add([i], float(w), "REPLACE")
    hinge = (corners[0] + corners[-1]) / 2 if len(corners) >= 2 else gape
    ob["beak_hinge_point"] = [round(float(x), 5) for x in hinge]
    ob["beak_hinge_axis"] = [1.0, 0.0, 0.0]
    ob["beak_open_deg"] = open_deg
    ob["tongue_root"] = [round(float(x), 5) for x in t_root]
    ob["tongue_axis"] = [round(float(x), 4) for x in t_axis]
    ob["tongue_up"] = [round(float(x), 4) for x in no]
    if rows:
        t_rgb = tongue["rgb"] if tongue else mouth_rgb
        _paint_strip(input_image(ob, "Base Color"), rows, [mouth_rgb, t_rgb, serrations["rgb"]])
        orm = input_image(ob, "Roughness")
        if orm is not None:                                 # AO 1; rough mouth 0.6 / wet tongue 0.35 / teeth 0.45
            _paint_strip(orm, rows, [[1.0, 0.6, 0.0], [1.0, 0.35, 0.0], [1.0, 0.45, 0.0]])
        nrm = input_image(ob, "Normal")
        if nrm is not None:
            _paint_strip(nrm, rows, [[0.5, 0.5, 1.0]] * 3)
    return {"cut_edges": len(cut), "faces": n_faces, "lower_verts": len(lower_w), "tongue_verts": len(tongue_w),
            "hinge_point": ob["beak_hinge_point"], "corners_x": [round(c.x, 4) for c in corners]}
