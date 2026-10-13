"""Relax crumpled folds in a built garment shell (folded / flipped faces where a sleeve meets the back, a vent top...).

  blender -b --factory-startup --python scripts/relax_folds.py -- --piece coat [--char outfit_male_victorian]
      [--thresh 0.35] [--grow 3] [--iters 40] [--clear 0.006] [--glb shells/coat.glb] [--out shells/coat.glb]

A vertex is creased when two of its faces' normals disagree (dot < --thresh); the creased vertices, grown --grow rings,
are Laplacian-smoothed (uniform, --iters) while the rest of the mesh stays put. So are the vertices of faces
turned against the surface (face normal . the garment's normals averaged over --smooth rings < --flip: the inside of a fold through itself, seen as dark shards);
up to --rounds rounds, each growing the smoothed patch by one more ring. Each moved vertex is then kept at least
--clear from the base body (pushed out along the body's normal). Only the first material's faces (the cloth) move --
buttons / trims keep their shape. Topology and UVs are untouched, so the baked albedo still fits (rebake to be sure).
Prints the creased vertex count before and after.
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_victorian")
PIECE = opt("--piece", "coat")
D = ROOT / "out" / f"{CHAR}-goose"
GLB = D / opt("--glb", f"shells/{PIECE}.glb")
OUT = D / opt("--out", f"shells/{PIECE}.glb")
TH, GROW, ITERS, CLEAR = opt("--thresh", 0.35), opt("--grow", 2), opt("--iters", 40), opt("--clear", 0.006)
FLIP, ROUNDS, SMOOTH = opt("--flip", 0.0), opt("--rounds", 3), opt("--smooth", 8)
USE_CREASE = "--crease" in argv

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB), merge_vertices=True)   # (else every UV seam is an open edge)
gar = next(o for o in bpy.data.objects if o.type == "MESH")
me = gar.data
M = np.array(gar.matrix_world)
with bpy.data.libraries.load(str(ROOT / "out" / "base-goose" / "base_goose.blend")) as (src, dst):
    dst.objects = ["base_goose_game"]
body = dst.objects[0]
BB = BVHTree.FromPolygons([v.co.copy() for v in body.data.vertices], [tuple(p.vertices) for p in body.data.polygons])

nv = len(me.vertices)
P = np.array([v.co[:] for v in me.vertices])
faces = [tuple(p.vertices) for p in me.polygons]
fmat = np.array([p.material_index for p in me.polygons])
movable = np.zeros(nv, bool)
for f, m in zip(faces, fmat):
    if m == 0:
        movable[list(f)] = True
for f, m in zip(faces, fmat):                      # a vertex shared with a trim / button face stays put
    if m != 0:
        movable[list(f)] = False
nbr = [set() for _ in range(nv)]
vf = [[] for _ in range(nv)]
for fi, f in enumerate(faces):
    for i, a in enumerate(f):
        vf[a].append(fi)
        nbr[a].update((f[i - 1], f[(i + 1) % len(f)]))
ZMIN = opt("--zmin", -9.0)          # only above this height (world z): e.g. the armpits, leaving vents / tails as built
Wz = P @ np.array(gar.matrix_world)[:3, :3].T + np.array(gar.matrix_world)[:3, 3]
movable &= Wz[:, 2] > ZMIN
# open-boundary vertices (hems, cuffs, neck) keep their place
edge_count = {}
for f in faces:
    for i in range(len(f)):
        e = tuple(sorted((f[i], f[(i + 1) % len(f)])))
        edge_count[e] = edge_count.get(e, 0) + 1
for (a, b), n in edge_count.items():
    if n == 1:
        movable[a] = movable[b] = False


def face_normals(P_):
    out = np.zeros((len(faces), 3))
    for fi, f in enumerate(faces):
        a, b, c = P_[f[0]], P_[f[1]], P_[f[2]]
        n = np.cross(b - a, c - a)
        if len(f) == 4:
            n = n + np.cross(c - a, P_[f[3]] - a)
        out[fi] = n / (np.linalg.norm(n) + 1e-12)
    return out


def creased(P_):
    FN = face_normals(P_)
    bad = np.zeros(nv, bool)
    for v in range(nv):
        fs = vf[v]
        if len(fs) < 2:
            continue
        ns = FN[fs]
        bad[v] = (ns @ ns.T).min() < TH
    return bad


Mw = np.array(gar.matrix_world)


def flipped(P_):
    """Vertices of faces turned against the surface's general direction (the face normal against the garment's own
    normals averaged over ~SMOOTH rings) -- the inside of a fold through itself. (The nearest body normal misled on
    sleeves and hanging tails, whose nearest body is another part.)"""
    FN = face_normals(P_)
    VN = np.zeros((nv, 3))
    for fi, f in enumerate(faces):
        VN[list(f)] += FN[fi]
    for _ in range(SMOOTH):
        VN = np.array([VN[list(nbr[v])].sum(0) + VN[v] for v in range(nv)])
        VN /= np.linalg.norm(VN, axis=1, keepdims=True) + 1e-12
    bad_ = np.zeros(nv, bool)
    for fi, f in enumerate(faces):
        if fmat[fi] == 0 and FN[fi] @ VN[list(f)].mean(0) < FLIP:
            bad_[list(f)] = True
    return bad_


# the layers beneath ("over" in the recipe, or --over a,b): kept --over-clear outside them, like the body
cfg_ = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text(encoding="utf-8"))
OVER = [k for k in opt("--over", ",".join(cfg_.get("garment_design", {}).get(PIECE, {}).get("over", []))).split(",") if k]
OVER_CLEAR = opt("--over-clear", 0.005)
under_bvh = []
for nm in OVER:
    f_ = D / "shells" / (f"variants/{opt('--variant', '')}/{nm}.glb" if "--variant" in argv and (D / "shells" / "variants" / opt("--variant", "") / f"{nm}.glb").exists() else f"{nm}.glb")
    if not f_.exists():
        continue
    seen = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(f_))
    for o_ in [o_ for o_ in bpy.data.objects if o_ not in seen and o_.type == "MESH"]:
        Mo = o_.matrix_world
        under_bvh.append(BVHTree.FromPolygons([Mo @ v.co for v in o_.data.vertices], [tuple(q.vertices) for q in o_.data.polygons]))
    for o_ in [o_ for o_ in bpy.data.objects if o_ not in seen]:
        bpy.data.objects.remove(o_)
LAYERS = [(BB, CLEAR)] + [(b_, OVER_CLEAR) for b_ in under_bvh]


def push_out(idx_):
    moved = 0
    for v in idx_:          # world space: the garment object may carry a transform
        w = Mw[:3, :3] @ P[v] + Mw[:3, 3]
        w0 = w.copy()
        for bvh_, cl in LAYERS:
            hit = bvh_.find_nearest(Vector(w))
            if hit[0] is None:
                continue
            loc, n = np.array(hit[0]), np.array(hit[1])
            d = (w - loc) @ n
            if -0.03 < d < cl:                 # (deeper: not this layer's surface -- an edge / another part)
                w = w + n * (cl - d)
        if np.any(w != w0):
            P[v] = np.linalg.solve(Mw[:3, :3], w - Mw[:3, 3])
            moved += 1
    return moved


PROJECT = "--project" in argv


def body_dist(P_):
    """Distance from each vertex to its nearest body point (world space) and that point."""
    W = P_ @ Mw[:3, :3].T + Mw[:3, 3]
    d_, near = np.zeros(nv), np.zeros((nv, 3))
    for v in range(nv):
        hit = BB.find_nearest(Vector(W[v]))
        near[v] = hit[0]
        d_[v] = np.linalg.norm(W[v] - near[v])
    return d_, near


if PROJECT:
    # the intended clearance per vertex: the built distance to the body, smoothed hard (the crumple's own
    # distances are noise) and kept within the garment's range
    E0, _ = body_dist(P)
    for _ in range(25):
        E0 = np.array([0.5 * E0[v] + 0.5 * E0[list(nbr[v])].mean() for v in range(nv)])
    E0 = np.clip(E0, opt("--e-min", 0.012), opt("--e-max", 0.06))


def project(idx_):
    """Each vertex onto the level surface at its clearance: nearest body point + clearance along the direction to
    it. The level surface of the distance to the body never folds, so the sleeve's and the back's sheets that
    crossed in the armpit both come to rest on one smooth surface bridging the crease."""
    W = P[idx_] @ Mw[:3, :3].T + Mw[:3, 3]
    for k, v in enumerate(idx_):
        hit = BB.find_nearest(Vector(W[k]))
        dv = W[k] - np.array(hit[0])
        L = np.linalg.norm(dv)
        dirv = dv / L if L > 1e-6 else np.array(hit[1])
        if dirv @ np.array(hit[1]) < 0:        # inside the body: out along its normal
            dirv = np.array(hit[1])
        w = np.array(hit[0]) + dirv * E0[v]
        P[v] = np.linalg.solve(Mw[:3, :3], w - Mw[:3, 3])


# --spheres "x,y,z,r;...": regions always relaxed (world space), e.g. the armpits, where the sleeve's and the
# back's sheets cross without either face turning over (the fold tests miss them)
FORCED = np.zeros(nv, bool)
Wf = P @ Mw[:3, :3].T + Mw[:3, 3]
for spec in [x for x in opt("--spheres", "").split(";") if x]:
    cx, cy, cz, r = (float(t) for t in spec.split(","))
    FORCED |= np.linalg.norm(Wf - np.array([cx, cy, cz]), axis=1) < r
if "--all" in argv:                   # the whole (movable) cloth: the offset copies the body's sculpted feather lumps
    FORCED |= True
FORCED &= movable
n0 = int((creased(P) & movable).sum())
f0 = int(flipped(P).sum())
total = set()
for rnd in range(ROUNDS):
    bad = (flipped(P) | (creased(P) if USE_CREASE else False)) & movable
    if rnd == 0:
        bad |= FORCED
    if not bad.any():
        break
    sel = bad.copy()
    for _ in range(GROW):
        grown = sel.copy()
        for v in np.where(sel)[0]:
            grown[list(nbr[v])] = True
        sel = grown & movable
    idx = np.where(sel)[0]
    total.update(idx.tolist())
    nb = [np.array(sorted(nbr[v])) for v in idx]
    for it in range(ITERS * 2):          # Taubin (lambda / mu): smooths the fold without shrinking tubes
        lam = 0.5 if it % 2 == 0 else -0.53
        newp = P.copy()
        for k, v in enumerate(idx):
            newp[v] = P[v] + lam * (P[nb[k]].mean(0) - P[v])
        P = newp
        if PROJECT and it % 8 == 7:
            project(idx)
    if PROJECT:
        project(idx)
    push_out(idx)
idx = np.array(sorted(total))
cloth = np.zeros(nv, bool)
for f, m in zip(faces, fmat):
    if m == 0:
        cloth[list(f)] = True
for f, m in zip(faces, fmat):
    if m != 0:
        cloth[list(f)] = False
pushed = push_out(np.where(cloth & movable)[0]) if "--push-all" in argv else 0   # (all of them crumpled the skirt)
n1 = int((creased(P) & movable).sum())
me.vertices.foreach_set("co", P.ravel())
me.update()
bpy.ops.object.select_all(action="DESELECT")
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.export_scene.gltf(filepath=str(OUT), export_format="GLB", use_selection=True, export_tangents=True)
print("RELAX", json.dumps({"piece": PIECE, "creased_before": n0, "flipped_before": f0,
                           "flipped_after": int(flipped(P).sum()), "smoothed": len(idx), "pushed_clear": pushed, "over": OVER, "creased_after": n1,
                           "out": str(OUT)}))
