"""Score a garment version on the naked base goose against Pete's drawings (the reference views on our body).

  blender -b --factory-startup --python scripts/garment_score.py -- --piece breeches [--ref breeches]
      [--glb out/outfit_male_victorian-goose/versions/breeches_v1.glb] [--tag v1] [--with shirt,breeches]

Renders, from the four calibrated key cameras (refs/key_views/cameras.json):
  - the garment alone (transparent film) -> its silhouette; IoU against the reference garment alpha
    (out/outfit_male_victorian/dressed/<ref>/<view>_garment.png); also the reference pixels the garment misses
    ("missing", % of the reference) and the garment pixels outside the reference ("extra");
  - the garment on the textured naked base goose (with eyes), plus --with other shells (layering checks), and a 3/4
    beauty view.
Writes renders/score/<piece>_<tag>.png (rows: reference on the blue mannequin | version on the goose, per view, then
the 3/4) and renders/score/<piece>_<tag>.json.
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import body_cover  # noqa: E402
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_victorian")
PIECE = opt("--piece", "breeches")
REF = opt("--ref", {"waistcoat": "vest", "coat": "jacket", "gloves": "glove", "bowtie": "bow_tie"}.get(PIECE, PIECE))
TAG = opt("--tag", "cur")
D = ROOT / "out" / f"{CHAR}-goose"
GLB = ROOT / opt("--glb", str((D / "shells" / f"{PIECE}.glb").relative_to(ROOT)))
WITH = [x for x in opt("--with", "").split(",") if x and x != PIECE]
RD = ROOT / "out" / "outfit_male_victorian" / "dressed" / REF
SD = ROOT / "renders" / "score"
SD.mkdir(parents=True, exist_ok=True)
CAM = json.loads((ROOT / "refs" / "key_views" / "cameras.json").read_text(encoding="utf-8"))
W0, H0 = CAM["size_px"]
VIEWS = ("front", "left", "rear", "right")

bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(str(ROOT / "out" / "base-goose" / "base_goose.blend")) as (src, dst):
    dst.objects = [n for n in src.objects if n != "base_goose_hi"]
goose = []
for o in dst.objects:
    if o is None:
        continue
    if o.type == "MESH":
        bpy.context.scene.collection.objects.link(o)
        for m in list(o.modifiers):
            o.modifiers.remove(m)
        o.parent = None
        goose.append(o)


def imp(path):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    new = [o for o in bpy.data.objects if o not in before]
    for o in new:
        if o.type == "MESH":
            mw = o.matrix_world.copy()
            o.parent = None
            o.matrix_world = mw
    return [o for o in new if o.type == "MESH"]


gar = imp(GLB)
if False:                                            # (superseded by body_cover below)
    import bmesh
    bo = next(o for o in goose if o.name.startswith("base_goose_game"))
    gi = {g.name: g.index for g in bo.vertex_groups}
    if "Tail" in gi:
        tail_v = set()
        for v in bo.data.vertices:
            best = max(v.groups, key=lambda g: g.weight, default=None)
            if best is not None and best.group == gi["Tail"]:
                tail_v.add(v.index)
        bm = bmesh.new()
        bm.from_mesh(bo.data)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if all(v.index in tail_v for v in f.verts)], context="FACES")
        bm.to_mesh(bo.data)
        bm.free()
others = []
for w in WITH:
    f = D / "shells" / f"{w}.glb"
    if f.exists():
        others += imp(f)
bo_ = next(o for o in goose if o.name.startswith("base_goose_game"))     # the body as the dressed goose shows it
body_cover.remove_faces(bo_, body_cover.covered_faces(bo_, gar + others, hide_tail=bool({PIECE, *WITH} & {"breeches", "coat"}),
                                                     force=body_cover.force_groups([PIECE, *WITH])))
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x, sc.render.resolution_y = W0, H0
sc.render.resolution_percentage = 50
wd = bpy.data.worlds.new("w")
wd.use_nodes = True
wd.node_tree.nodes["Background"].inputs[0].default_value = (0.78, 0.78, 0.78, 1)
wd.node_tree.nodes["Background"].inputs[1].default_value = 0.6
sc.world = wd
for i, (rot, en) in enumerate([((50, 0, 30), 3.0), ((60, 0, 200), 1.4), ((75, 0, 110), 0.9)]):
    L = bpy.data.objects.new(f"l{i}", bpy.data.lights.new(f"l{i}", "SUN"))
    L.data.energy = en
    L.rotation_euler = [math.radians(a) for a in rot]
    sc.collection.objects.link(L)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = CAM["ortho_m_height"]
sc.collection.objects.link(cam)
sc.camera = cam


def aim(view):
    c = CAM["views"][view]
    cam.location = Vector(c["location"])
    a = math.radians(c["yaw_deg"])
    d = Vector((math.sin(a), -math.cos(a), 0.0))
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()


def render(path, transparent):
    sc.render.film_transparent = transparent
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(str(path))
    w, h = im.size
    px = np.array(im.pixels[:]).reshape(h, w, 4)[::-1]
    bpy.data.images.remove(im)
    return px


def load_png(path, size):
    im = bpy.data.images.load(str(path))
    w, h = im.size
    px = np.array(im.pixels[:]).reshape(h, w, -1)[::-1]
    bpy.data.images.remove(im)
    ys = (np.arange(size[1]) * h / size[1]).astype(int)
    xs = (np.arange(size[0]) * w / size[0]).astype(int)
    return px[ys][:, xs]


scores, tiles = {}, []
for view in VIEWS:
    aim(view)
    for o in goose + others:
        o.hide_render = True
    alone = render(SD / f"_{PIECE}_{TAG}_{view}_alone.png", True)
    for o in goose + others:
        o.hide_render = False
    full = render(SD / f"_{PIECE}_{TAG}_{view}_full.png", False)
    h, w = alone.shape[:2]
    m = alone[..., 3] > 0.5
    ref = None
    if (RD / f"{view}_garment.png").exists():
        ref = load_png(RD / f"{view}_garment.png", (w, h))
        rm = ref[..., 3] > 0.5
        inter, union = (m & rm).sum(), (m | rm).sum()
        scores[view] = {"iou": round(float(inter / max(union, 1)), 3) if rm.any() else None,
                        "missing_pct": round(float((rm & ~m).sum() / max(rm.sum(), 1) * 100), 1),
                        "extra_pct": round(float((m & ~rm).sum() / max(rm.sum(), 1) * 100), 1)}
        comp = load_png(RD / f"{view}.png", (w, h))[..., :3]
    else:
        comp = np.ones((h, w, 3)) * 0.8
    tiles.append(np.concatenate([comp, full[..., :3]], axis=1))
# 3/4 beauty
c = CAM["views"]["front"]
a = math.radians(35)
d = Vector((math.sin(a), -math.cos(a), 0.15)).normalized()
cam.location = Vector(CAM["target"]) + d * 6
cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
beauty = render(SD / f"_{PIECE}_{TAG}_q34.png", False)[..., :3]
h, w = beauty.shape[:2]
sheet = np.ones((h * 2, w * 6, 3)) * 1.0
for i, t in enumerate(tiles):
    r, c_ = divmod(i, 2)
    sheet[r * h:(r + 1) * h, c_ * 2 * w:(c_ + 1) * 2 * w] = t
sheet[0:h, 4 * w:5 * w] = beauty
img = bpy.data.images.new("sheet", sheet.shape[1], sheet.shape[0])
img.pixels = np.dstack([sheet[::-1], np.ones(sheet.shape[:2])]).ravel().tolist()
img.filepath_raw = str(SD / f"{PIECE}_{TAG}.png")
img.file_format = "PNG"
img.save()
# close-ups framed on the garment itself (800 x 800, on the goose): front, left, rear, right, 3/4 -> <piece>_<tag>_close.png
gv = np.concatenate([np.array([(o.matrix_world @ v.co)[:] for v in o.data.vertices]) for o in gar])
lo, hi = gv.min(0), gv.max(0)
ctr = Vector(((lo + hi) / 2).tolist())
ext = float(max(hi[2] - lo[2], hi[0] - lo[0], hi[1] - lo[1])) * 1.25
sc.render.resolution_x = sc.render.resolution_y = 800
sc.render.resolution_percentage = 100
cam.data.ortho_scale = ext
close = []
for name, az, el in (("front", 0, 0.05), ("left", 90, 0.05), ("rear", 180, 0.05), ("right", -90, 0.05), ("q34", 35, 0.25)):
    a_ = math.radians(az)
    d = Vector((math.sin(a_), -math.cos(a_), el)).normalized()
    cam.location = ctr + d * 6
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    close.append(render(SD / f"_{PIECE}_{TAG}_close_{name}.png", False)[..., :3])
strip = np.concatenate(close, axis=1)
ci = bpy.data.images.new("close", strip.shape[1], strip.shape[0])
ci.pixels = np.dstack([strip[::-1], np.ones(strip.shape[:2])]).ravel().tolist()
ci.filepath_raw = str(SD / f"{PIECE}_{TAG}_close.png")
ci.file_format = "PNG"
ci.save()
ious = [s["iou"] for s in scores.values() if s.get("iou") is not None]
summary = {"piece": PIECE, "tag": TAG, "glb": str(GLB.relative_to(ROOT)), "views": scores,
           "mean_iou": round(float(np.mean(ious)), 3) if ious else None, "sheet": str(SD / f"{PIECE}_{TAG}.png")}
(SD / f"{PIECE}_{TAG}.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
print("SCORE", json.dumps(summary))
