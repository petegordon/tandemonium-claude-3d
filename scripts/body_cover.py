"""Which base-body faces a set of worn shells hides (as dress_goose.py masks them): shared by project_bake.py and
garment_score.py so a bake / score sees the body the way the dressed goose shows it.

covered_faces(body, shells, hide_tail) -> bool per body polygon: every vertex of the face has a shell within MASK_D
along its normal (or, poking through, within MASK_IN against it); with hide_tail, faces whose vertices are all
dominated by the Tail group are hidden too (Pete: the tail stays under the breeches and the jacket).
"""
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

MASK_D = 0.06
MASK_IN = 0.02
POKE_IN = 0.10      # torso / leg / tail feathers poking through the cloth by up to this much are hidden too
POKE_GROUPS = ("Hips", "Spine", "UpLeg", "Leg", "Tail", "Foot", "ToeBase")
TAIL_RINGS = 2


def shells_bvh(shells):
    V, F = [], []
    for o in shells:
        mw = o.matrix_world
        off = len(V)
        V += [mw @ v.co for v in o.data.vertices]
        F += [tuple(i + off for i in p.vertices) for p in o.data.polygons]
    return BVHTree.FromPolygons(V, F) if F else None


FORCE = {"boots": ("Foot", "ToeBase"), "gloves": ("Hand",)}    # always hidden under these (as dress_goose.py)


def force_groups(pieces):
    return tuple(g for p in pieces for g in FORCE.get(p, ()))


def covered_faces(body, shells, hide_tail=False, force=()):
    me = body.data
    nv = len(me.vertices)
    cov = np.zeros(nv, bool)
    bvh = shells_bvh(shells)
    gname = {g.index: g.name for g in body.vertex_groups}
    if bvh is not None:
        mw = body.matrix_world
        for v in me.vertices:
            best = max(v.groups, key=lambda g: g.weight, default=None)
            dom = gname.get(best.group, "") if best is not None else ""
            poke_ok = any(k in dom for k in POKE_GROUPS) and "Arm" not in dom and "Hand" not in dom
            p = mw @ v.co
            n = (mw.to_3x3() @ v.normal).normalized()
            h = bvh.ray_cast(p + n * 0.001, n, MASK_D)
            if h[0] is None:
                h = bvh.ray_cast(p + n * 0.001, -n, POKE_IN if poke_ok else MASK_IN)
            cov[v.index] = h[0] is not None
    if force:
        for v in me.vertices:
            best = max(v.groups, key=lambda g: g.weight, default=None)
            if best is not None and any(gname.get(best.group, "").endswith(f) for f in force):
                cov[v.index] = True
    if hide_tail:
        gi = {g.name: g.index for g in body.vertex_groups}
        if "Tail" in gi:
            tail = np.zeros(nv, bool)
            for v in me.vertices:
                best = max(v.groups, key=lambda g: g.weight, default=None)
                if best is not None and best.group == gi["Tail"]:
                    tail[v.index] = True
            ed = np.array([e.vertices[:] for e in me.edges])
            for _ in range(TAIL_RINGS):                # (the rump just above the tail pokes through the seat too)
                nb = tail.copy()
                nb[ed[:, 0]] |= tail[ed[:, 1]]
                nb[ed[:, 1]] |= tail[ed[:, 0]]
                tail = nb
            cov |= tail
    return np.array([all(cov[i] for i in p.vertices) for p in me.polygons])


def remove_faces(obj, mask):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in np.where(mask)[0]], context="FACES")
    bm.to_mesh(obj.data)
    bm.free()
