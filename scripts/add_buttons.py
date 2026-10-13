"""Model the brass buttons Pete drew: find them in the reference views, place domed brass buttons on the garment.

  blender -b --factory-startup --python scripts/add_buttons.py -- --piece boots [--ref boots] [--views left,right,front]
      [--min-px 4] [--max-px 260] [--radius-scale 1.0] [--glb <in>] [--out <out>] [--extra x,y,z;x,y,z]

Brass pixels in out/outfit_male_victorian/dressed/<ref>/<view>_garment.png (warm, bright, R-B > 0.22) group into blobs
(--min-px .. --max-px view pixels); each blob centre is cast from its calibrated camera onto the garment; hits closer
than 1.5 x their radius merge (seen from several views). Each button: a dome (radius from the blob area, height 0.45 r)
along the surface normal, 1.5 mm proud, brass material (metallic). --extra adds buttons at given points (snapped to the
surface). The buttons join the shell as their own material slot (after the cloth, so project_bake.py leaves them).
Writes the shell back (default out/<char>-goose/shells/<piece>.glb) and prints the button list.
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


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_victorian")
PIECE = opt("--piece", "boots")
REF = opt("--ref", {"waistcoat": "vest", "coat": "jacket", "gloves": "glove", "bowtie": "bow_tie"}.get(PIECE, PIECE))
VIEWS = [] if "--extra-only" in argv else opt("--views", "front,left,rear,right").split(",")   # --extra-only: just the --extra spots
MINPX, MAXPX = opt("--min-px", 4), opt("--max-px", 260)
EXTEND = opt("--extend", 0)       # continue each side's button line this many steps further down
DRIFT = opt("--extend-drift", 0.0)  # metres per step toward the toe (-y): the line curves onto the instep
RSCALE = opt("--radius-scale", 1.0)
D = ROOT / "out" / f"{CHAR}-goose"
GLB = ROOT / opt("--glb", str((D / "shells" / f"{PIECE}.glb").relative_to(ROOT)))
OUTF = ROOT / opt("--out", str((D / "shells" / f"{PIECE}.glb").relative_to(ROOT)))
RD = ROOT / "out" / "outfit_male_victorian" / "dressed" / REF
CAM = json.loads((ROOT / "refs" / "key_views" / "cameras.json").read_text(encoding="utf-8"))
W0, H0 = CAM["size_px"]
PPM = CAM["px_per_m"]
TGT = np.array(CAM["target"])

bpy.ops.wm.read_factory_settings(use_empty=True)
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(GLB))
gar = next(o for o in bpy.data.objects if o not in before and o.type == "MESH")
bpy.ops.object.select_all(action="DESELECT")
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
GB = BVHTree.FromPolygons([v.co.copy() for v in gar.data.vertices], [tuple(p.vertices) for p in gar.data.polygons])


def blobs(mask):
    """Connected components (4-neighbour) of a sparse boolean mask: list of (ys, xs)."""
    pts = set(zip(*np.where(mask)))
    out = []
    while pts:
        seed = pts.pop()
        stack, comp = [seed], [seed]
        while stack:
            y, x = stack.pop()
            for q in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                if q in pts:
                    pts.remove(q)
                    stack.append(q)
                    comp.append(q)
        out.append(np.array(comp))
    return out


found = []
for view in VIEWS:
    f = RD / f"{view}_garment.png"
    if not f.exists():
        continue
    im = bpy.data.images.load(str(f))
    w, h = im.size
    px = np.array(im.pixels[:]).reshape(h, w, 4)[::-1]
    bpy.data.images.remove(im)
    r, g, b, a = px[..., 0], px[..., 1], px[..., 2], px[..., 3]
    brass = (a > 0.5) & (r > 0.55) & (r - b > 0.25) & (g > 0.35) & (g < r)
    c = CAM["views"][view]
    R, U, B = np.array(c["right"]), np.array(c["up"]), np.array(c["back"])
    for comp in blobs(brass):
        if not (MINPX <= len(comp) <= MAXPX):
            continue
        # a button is a round, compact blob (brocade / trim gold is thin, branched or elongated)
        ys_, xs_ = comp[:, 0], comp[:, 1]
        hh, ww = ys_.max() - ys_.min() + 1, xs_.max() - xs_.min() + 1
        if max(hh, ww) > 1.7 * min(hh, ww) or len(comp) < 0.55 * hh * ww:
            continue
        # and isolated: little other brass in a ring around it
        ring_r = int(max(hh, ww) * 1.6)
        y0_, x0_ = int(ys_.mean()), int(xs_.mean())
        win = brass[max(0, y0_ - ring_r):y0_ + ring_r + 1, max(0, x0_ - ring_r):x0_ + ring_r + 1]
        if win.sum() > 2.2 * len(comp):
            continue
        yc, xc = comp[:, 0].mean(), comp[:, 1].mean()
        rad = math.sqrt(len(comp) / math.pi) / PPM * RSCALE
        p = TGT + R * (xc - W0 / 2) / PPM - U * (yc - H0 / 2) / PPM
        hit = GB.ray_cast(Vector(p + B * 3.0), Vector(-B), 6.0)
        # a blob seen through an opening (the vest's buttons in the coat's open front) hits the garment's inside
        # at the back, facing away: not this garment's button
        if hit[0] is None or np.dot(np.array(hit[1][:]), B) < 0.2:
            continue
        found.append((np.array(hit[0][:]), np.array(hit[1][:]), rad, view))
for spec in [s for s in opt("--extra", "").split(";") if s]:
    p = np.array([float(x) for x in spec.split(",")])
    if "--extra-ray" in argv:     # first surface straight behind the spot (+y), seen from the front
        loc, nrm, _, _ = GB.ray_cast(Vector(p), Vector((0, 1, 0)), 1.0)
        if loc is None:
            continue
    else:
        loc, nrm, _, _ = GB.find_nearest(Vector(p))
    found.append((np.array(loc[:]), np.array(nrm[:]), opt("--extra-r", 0.007), "extra"))
# merge duplicates seen from several views (keep the most frontal: largest radius estimate)
found.sort(key=lambda t: -t[2])
buttons = []
for p, n, rad, v in found:
    if all(np.linalg.norm(p - q) > 1.5 * max(rad, r2) for q, _, r2, _ in buttons):
        buttons.append((p, n, rad, v))
if "--mirror" in argv:
    # symmetric garments: every button gets its mirror partner (x -> -x) unless one is already there
    for p, n, rad, v in list(buttons):
        q = p * np.array([-1, 1, 1])
        if abs(p[0]) > 0.01 and all(np.linalg.norm(q - b_[0]) > 1.5 * rad for b_ in buttons):
            loc, nrm, _, _ = GB.find_nearest(Vector(q))
            buttons.append((np.array(loc[:]), np.array(nrm[:]), rad, "extra"))
if EXTEND:
    # per side (x sign): the detected line of buttons, continued downward at its own spacing, snapped to the surface
    for sx in (1, -1):
        side = sorted([b_ for b_ in buttons if b_[0][0] * sx > 0], key=lambda b_: -b_[0][2])
        if len(side) < 2:
            continue
        P_ = np.array([b_[0] for b_ in side])
        step = np.median(np.diff(P_, axis=0), axis=0)
        last = P_[-1]
        for k in range(1, EXTEND + 1):
            q = last + step * k + np.array([0, -DRIFT * k * k / 2, 0])
            loc, nrm, _, _ = GB.find_nearest(Vector(q))
            buttons.append((np.array(loc[:]), np.array(nrm[:]), side[-1][2], "extra"))
bm = bmesh.new()
for p, n, rad, v in buttons:
    rad = float(np.clip(rad, 0.004, 0.014))
    geom = bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=1.0)
    vs = geom["verts"]
    nv = Vector(n).normalized()
    rot = Vector((0, 0, 1)).rotation_difference(nv).to_matrix().to_4x4()
    M = Matrix.Translation(Vector(p) + nv * 0.0015) @ rot @ Matrix.Diagonal((rad, rad, rad * 0.45, 1.0))
    bmesh.ops.transform(bm, matrix=M, verts=vs)
me = bpy.data.meshes.new("buttons")
bm.to_mesh(me)
bm.free()
bo = bpy.data.objects.new("buttons", me)
bpy.context.scene.collection.objects.link(bo)
for poly in me.polygons:
    poly.use_smooth = True
brass = bpy.data.materials.new(f"{PIECE}_brass")
brass.use_nodes = True
bs = brass.node_tree.nodes["Principled BSDF"]
bs.inputs["Base Color"].default_value = (0.78, 0.55, 0.22, 1)
bs.inputs["Metallic"].default_value = 1.0
bs.inputs["Roughness"].default_value = 0.28
me.materials.append(brass)
bpy.ops.object.select_all(action="DESELECT")
bo.select_set(True)
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.object.join()
bpy.ops.export_scene.gltf(filepath=str(OUTF), export_format="GLB", use_selection=True, export_tangents=True)
print("BUTTONS", json.dumps({"n": len(buttons), "by_view": {v: sum(1 for b_ in buttons if b_[3] == v) for v in VIEWS + ["extra"]},
                             "out": str(OUTF)}))
