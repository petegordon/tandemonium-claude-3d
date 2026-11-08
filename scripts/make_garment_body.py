"""The GARMENT body: the base goose with the tail flattened into the rump and a human-like seat, for building clothes on.

  blender -b --factory-startup --python scripts/make_garment_body.py -- [--bulge 0.014] [--render]

Why (Pete, 2026-11-07): every outfit lost time to the tail -- breeches seats caved into the hollow under the tail root,
the tail cap's rim showed through, seat_shape hacks per outfit, text-to-image views re-adding a tail. Clothes now
build on a body whose back is shaped like a person's under the clothes; the game already hides the real tail (and the
rump feathers round it) under breeches / coats / skirts (dress_goose.py FORCE).

Same mesh, same vertex order as base_goose_rigged.glb's game mesh, only moved (so bones, weights and every per-vertex
table still match):
  1. per 1 cm height band through the hips, the band's (x, y) outline is filled out to its convex hull at the back
     (cloth spans a hollow, it doesn't follow it in), with the tail's vertices left out of the hull;
  2. the tail's vertices are pressed onto that hull (no tail sticking out behind);
  3. two rounded cheeks are added (gaussian bulge along the back normal), then the zone is relaxed.
Writes out/base-goose/garment_body.npz {pos (N, 3), moved (N,) bool} and renders/garment_body.png (before / after).
make_garment.py and make_robot_parts.py use it unless the chars json says "garment_body": false.
"""
import sys
from pathlib import Path

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
BULGE = opt("--bulge", 0.014)
Z0, Z1 = opt("--z0", 0.62), opt("--z1", 0.98)          # the reshaped height range (hips / seat)
BACK_Y = opt("--back-y", 0.0)                          # only the back half moves (y > this; +y = back)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ROOT / "out" / "base-goose" / "base_goose_rigged.glb"))
body = bpy.data.objects["base_goose_game"]
me = body.data
M = np.array(body.matrix_world)
V0 = np.array([v.co[:] for v in me.vertices])
V0w = V0 @ M[:3, :3].T + M[:3, 3]
gn = [g.name for g in body.vertex_groups]
W = np.zeros((len(V0), len(gn)))
for v in me.vertices:
    for g in v.groups:
        W[v.index, g.group] = g.weight
W /= np.maximum(W.sum(1, keepdims=True), 1e-9)
tail_w = W[:, gn.index("Tail")]
arm_w = sum(W[:, i] for i, n in enumerate(gn) if "Arm" in n or "Hand" in n or "Shoulder" in n)
V = V0w.copy()
zone = (V[:, 2] > Z0) & (V[:, 2] < Z1) & (arm_w < 0.2)
is_tail = W.argmax(1) == gn.index("Tail")   # the same rule dress_goose.py FORCE hides by (dominant bone = Tail)


def hull_upper_back(pts):
    """Upper (back, max-y) convex hull chain of 2D points (x, y), sorted by x (monotone chain)."""
    P = sorted(map(tuple, pts))
    up = []
    for p in P:
        while len(up) >= 2 and (up[-1][0] - up[-2][0]) * (p[1] - up[-2][1]) - (up[-1][1] - up[-2][1]) * (p[0] - up[-2][0]) >= 0:
            up.pop()
        up.append(p)
    return np.array(up)


moved = np.zeros(len(V), bool)
for z in np.arange(Z0, Z1, 0.01):
    band = zone & (np.abs(V[:, 2] - (z + 0.005)) < 0.007)
    ref = band & ~is_tail
    if ref.sum() < 8:
        continue
    hull = hull_upper_back(V[ref][:, :2])
    if len(hull) < 2:
        continue
    back = band & (V[:, 1] > BACK_Y)
    hy = np.interp(V[back, 0], hull[:, 0], hull[:, 1], left=np.nan, right=np.nan)
    idx = np.nonzero(back)[0]
    for i_, y_ in zip(idx, hy):
        if np.isnan(y_):
            continue
        if is_tail[i_] or V[i_, 1] < y_:          # fill the hollow out to the hull; press the tail onto it
            V[i_, 1] = y_
            moved[i_] = True
# tail vertices outside the band range (its tip) come onto the nearest band surface too
far_tail = is_tail & ~zone
V[far_tail, 1] = np.minimum(V[far_tail, 1], np.interp(V[far_tail, 2], [Z0, Z1], [V[zone, 1].max()] * 2))
moved |= far_tail
# two rounded cheeks: gaussian bulge backwards, centred under the hips
hips_z = float(np.mean([V0w[W[:, gn.index(n)] > 0.6][:, 2].mean() for n in ("LeftUpLeg", "RightUpLeg")]))
for sx in (1, -1):
    dx, dz = (V[:, 0] - sx * opt("--cheek-x", 0.062)) / opt("--cheek-sx", 0.06), (V[:, 2] - opt("--cheek-z", 0.80)) / opt("--cheek-sz", 0.065)
    g = np.exp(-(dx ** 2 + dz ** 2)) * (V[:, 1] > 0.02) * zone
    V[:, 1] += BULGE * g
    moved |= g > 0.05
# relax the moved zone (Laplacian over mesh edges, the rest pinned). The glTF mesh is split at UV seams (duplicate
# vertices, no shared edge): relax on the WELDED mesh -- relaxed apart, the duplicates opened the seams into cracks
# through the seat (make_garment.py welds them back at 0.2 mm: holes, fragments, crumpled breeches; 2026-11-08)
from mathutils import Vector as _V
from mathutils.kdtree import KDTree as _KD
_kd = _KD(len(V0w))
for i_, p_ in enumerate(V0w):
    _kd.insert(_V(p_), i_)
_kd.balance()
rep = np.array([min(j_ for _, j_, _ in _kd.find_range(_V(p_), 2e-4)) for p_ in V0w])
moved = np.bincount(rep, weights=moved.astype(float), minlength=len(V))[rep] > 0
V = V[rep]
ed = np.unique(np.sort(rep[np.array([e.vertices[:] for e in me.edges])], 1), axis=0)
ed = ed[ed[:, 0] != ed[:, 1]]
deg = np.maximum(np.bincount(ed.ravel(), minlength=len(V)), 1)[:, None]
free = moved.copy()
for _ in range(opt("--relax", 12)):
    acc = np.zeros_like(V)
    np.add.at(acc, ed[:, 0], V[ed[:, 1]])
    np.add.at(acc, ed[:, 1], V[ed[:, 0]])
    V = np.where(free[:, None], 0.5 * V + 0.5 * acc / deg, V)
V = V[rep]
# never inside the real body: smoothing shrank convex spots, and clothes built there let the real rump poke through.
# Only the back moves, only backwards (y), and only the tail itself may go in (the game hides it under the clothes).
V[:, 0], V[:, 2] = V0w[:, 0], V0w[:, 2]
V[:, 1] = np.where(is_tail, V[:, 1], np.maximum(V[:, 1], V0w[:, 1]))
print("GARMENT_BODY moved", int(moved.sum()), "of", len(V), "tail verts", int(is_tail.sum()),
      "max shift mm", round(float(np.abs(V - V0w).max()) * 1000, 1))
out = ROOT / "out" / "base-goose" / "garment_body.npz"
np.savez(out, pos=V.astype(np.float32), moved=moved)
print("GARMENT_BODY ->", out)

if "--render" in argv:
    import math
    from mathutils import Euler, Vector
    for o in bpy.data.objects:
        if o.type == "MESH" and o is not body:
            o.hide_render = True
    after = body.copy()
    after.data = me.copy()
    bpy.context.scene.collection.objects.link(after)
    inv = np.linalg.inv(M)
    after.data.vertices.foreach_set("co", (V @ inv[:3, :3].T + inv[:3, 3]).ravel())
    after.data.update()
    for o in (body, after):
        for m in list(o.modifiers):
            o.modifiers.remove(m)
        o.parent = None
    body.location.x -= 0.45
    after.location.x += 0.45
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = 1400, 900
    sc.world = bpy.data.worlds.new("w")
    sc.world.use_nodes = True
    sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.75, 0.76, 0.78, 1)
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
    sun.data.energy = 3.0
    sun.rotation_euler = Euler((math.radians(50), 0, math.radians(150)))
    sc.collection.objects.link(sun)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    for name, loc in (("rear", (0.0, 3.2, 0.85)), ("side", (3.2, 1.2, 0.85))):
        cam.location = loc
        cam.rotation_euler = (Vector((0, 0, 0.8)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = 60
        sc.render.filepath = str(ROOT / "renders" / f"garment_body_{name}.png")
        bpy.ops.render.render(write_still=True)
    print("RENDER renders/garment_body_rear.png renders/garment_body_side.png (left: base, right: garment body)")
