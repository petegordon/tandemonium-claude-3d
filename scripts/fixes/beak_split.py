"""Split the lower bill so the goose can open its beak / honk (PLAN P1.7). Runs on the game
mesh after the bake.

The generated bill is one closed shape. A plane through the mouth line (from the bill tip to
the mouth corners, containing the X axis) cuts the bill in front of the gape; the cut edges
are split so upper and lower bill separate, but stay joined at the two mouth corners. Each half
gets a cap over its cut (roof / floor of the mouth) in a mouth colour painted into the
reserved atlas strip. When the lower bill rotates about the hinge (the line through the two
mouth corners) the caps open like a wedge, hinged at the back of the mouth.

Outputs: vertex group "beak_lower" (1 in front of the gape, fading to 0 just behind it so the
chin skin stretches instead of tearing), object props beak_hinge_point / beak_hinge_axis /
beak_open_deg for the jaw bone.

mouth: {"tip": [y, z], "gape": [y, z]} in metres on the model's centre plane (x = 0).
"""
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
    "open_deg": 28,
}


def _paint_strip(img, rows, rgb):
    px = read_pixels(img)
    h = px.shape[0]
    px[h - rows:, :, :3] = rgb
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


def apply(ctx, mouth, half_width, z_band, fade_behind_gape, mouth_rgb, open_deg):
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
    # boundary edges on the plane, in front of the gape: two open paths (upper / lower copy)
    bnd = [e for e in bm.edges if e.is_boundary and all(abs((v.co - gape).dot(no)) < 1e-4 for v in e.verts)
           and all(v.co.y < gape.y + 1e-4 for v in e.verts)]
    upper = [e for e in bnd if (e.link_faces[0].calc_center_median() - gape).dot(no) > 0]
    lower = [e for e in bnd if e not in upper]
    uvl = bm.loops.layers.uv.active
    tex_h = input_image(ob, "Base Color").size[1]
    v_mid = 1.0 - rows / 2.0 / tex_h if rows else 0.999
    caps = []
    for chain, want in ((upper, -no), (lower, no)):   # roof faces down, floor faces up
        path = _order_chain(chain)
        f = bm.faces.new(path)
        if f.normal.dot(want) < 0:
            f.normal_flip()
        for lp in f.loops:
            lp[uvl].uv = (0.5, v_mid)
        caps.append(f)
    tri = bmesh.ops.triangulate(bm, faces=caps)["faces"]
    # bisect leaves n-gons; tangent export (MikkTSpace) needs tris/quads
    bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4])
    for f in tri:
        f.smooth = False
    corners = sorted({v.co.copy().freeze() for e in upper for v in e.verts
                      if len([x for x in v.link_edges if x in upper]) == 1}, key=lambda c: c.x)
    # lower-bill weights: below the mouth plane, in front of the gape (fading behind it). Vertices
    # ON the plane (the two copies along the cut) go by the side their faces are on.
    bm.verts.index_update()
    weights = {}
    for v in bm.verts:
        d = (v.co - gape).dot(no)
        if abs(v.co.x) >= half_width or v.co.y > gape.y + fade_behind_gape or d < -z_band[0]:
            continue
        if abs(d) <= 1e-4:
            sides = [(f.calc_center_median() - gape).dot(no) for f in v.link_faces]
            if not sides or max(sides) > 1e-5:
                continue                              # upper copy, or a mouth corner (hinge)
        elif d > 0:
            continue
        w = 1.0 if v.co.y < gape.y else 1.0 - (v.co.y - gape.y) / fade_behind_gape
        if w > 0:
            weights[v.index] = w
    bm.to_mesh(me)
    bm.free()
    me.update()
    vg = ob.vertex_groups.get("beak_lower") or ob.vertex_groups.new(name="beak_lower")
    for i, w in weights.items():
        vg.add([i], float(w), "REPLACE")
    sel = np.array(list(weights))
    hinge = (corners[0] + corners[-1]) / 2 if len(corners) >= 2 else gape
    ob["beak_hinge_point"] = [round(float(x), 5) for x in hinge]
    ob["beak_hinge_axis"] = [1.0, 0.0, 0.0]
    ob["beak_open_deg"] = open_deg
    # mouth colour into the reserved strip (base colour; flat normal; AO 1 / rough 0.6 / metal 0)
    if rows:
        _paint_strip(input_image(ob, "Base Color"), rows, mouth_rgb)
        orm = input_image(ob, "Roughness")
        if orm is not None:
            _paint_strip(orm, rows, [1.0, 0.6, 0.0])
        nrm = input_image(ob, "Normal")
        if nrm is not None:
            _paint_strip(nrm, rows, [0.5, 0.5, 1.0])
    return {"cut_edges": len(cut), "cap_tris": len(tri), "lower_verts": int(len(sel)),
            "hinge_point": ob["beak_hinge_point"], "corners_x": [round(c.x, 4) for c in corners]}
