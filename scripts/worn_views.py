"""Render an aligned worn model (the goose wearing one garment) from the key mannequin's calibrated cameras, with a
stand-off map: how far the worn surface stands off OUR base body, per pixel (4 px grid).

  blender -b --factory-startup --python scripts/worn_views.py -- --garment jacket
      [--worn out/outfit_male_victorian/worn/<g>/aligned.glb] [--key refs/key_views]
      [--out out/outfit_male_victorian/wornviews/<g>]

Cameras: refs/key_views/cameras.json (same ortho scale, target, view axes and image size as key_views.py), so pixels
line up with the blue mannequin renders. Writes <out>/<view>.png (textured worn model alone on the key grey) and
<out>/standoff_<view>.npz: grid rows / cols (full-view pixels), standoff (m: + = the worn surface is outside our body;
measured along the view ray where the ray also meets our body, else the distance to our body), worn hit flag;
and <out>/prompts.json: SAM prompt points per view from body LANDMARKS (rig joints of OUR body, projected through
the calibrated cameras): positives where the garment must be, negatives where it cannot (PROMPTS below). A point is
kept only if the view ray through it meets the worn model on the intended body region (nearest body face's region),
so a torso point hidden by a sleeve in the side view is dropped instead of mislabelling the sleeve.
"""
import json
import math
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
G = opt("--garment", "jacket")
WORN = ROOT / opt("--worn", f"out/outfit_male_victorian/worn/{G}/aligned.glb")
KEYD = ROOT / opt("--key", "refs/key_views")
OUT = ROOT / opt("--out", f"out/outfit_male_victorian/wornviews/{G}")
OUT.mkdir(parents=True, exist_ok=True)
CAM = json.loads((KEYD / "cameras.json").read_text(encoding="utf-8"))
W0, H0 = CAM["size_px"]
PPM = CAM["px_per_m"]
TGT = np.array(CAM["target"])
STEP = 4

REGF = ROOT / "out" / "outfit_male_victorian" / "worn" / "_regions.npz"
REGV = np.load(REGF)["reg"]
# landmark -> (point builder over joints J / tails T, allowed body regions)
TORSO = ("torso_front", "torso_side", "torso_back")
LM = {
    # (the Head bone's head sits forward at the bill: head points hang off the top of the neck instead)
    "head_top": (lambda J, T: J["Neck3"] + np.array([0, -0.06, 0.23]), ("head",)),
    "head": (lambda J, T: J["Neck3"] + np.array([0, -0.06, 0.10]), ("head",)),
    "bill": (lambda J, T: J["Head"] + np.array([0, -0.05, 0.0]), ("head",)),
    "neck": (lambda J, T: J["Neck2"], ("neck",)),
    "neck_low": (lambda J, T: J["Neck"] + np.array([0, 0, -0.01]), ("neck", "torso_front", "torso_side")),
    "chest": (lambda J, T: J["Spine2"], TORSO),
    "belly": (lambda J, T: J["Spine"] + np.array([0, 0, 0.05]), TORSO),
    "hips": (lambda J, T: J["Hips"] + np.array([0, 0, 0.03]), TORSO),
}
for sd in ("Left", "Right"):
    k = sd[0]
    LM.update({
        f"upper_arm_{k}": (lambda J, T, s=sd: (J[f"{s}Arm"] + J[f"{s}ForeArm"]) / 2, ("upper_arm",)),
        f"forearm_{k}": (lambda J, T, s=sd: J[f"{s}ForeArm"] + 0.55 * (J[f"{s}Hand"] - J[f"{s}ForeArm"]), ("forearm",)),
        f"forearm_hi_{k}": (lambda J, T, s=sd: J[f"{s}ForeArm"] + 0.25 * (J[f"{s}Hand"] - J[f"{s}ForeArm"]), ("forearm",)),
        f"wrist_{k}": (lambda J, T, s=sd: J[f"{s}ForeArm"] + 0.95 * (J[f"{s}Hand"] - J[f"{s}ForeArm"]), ("forearm", "hand")),
        f"hand_{k}": (lambda J, T, s=sd: (J[f"{s}Hand"] + T[f"{s}Hand"]) / 2, ("hand",)),
        f"thigh_{k}": (lambda J, T, s=sd: (J[f"{s}UpLeg"] + J[f"{s}Leg"]) / 2, ("thigh",)),
        f"knee_{k}": (lambda J, T, s=sd: J[f"{s}Leg"] + np.array([0, 0, 0.05]), ("thigh", "shin")),
        f"shin_{k}": (lambda J, T, s=sd: (J[f"{s}Leg"] + J[f"{s}Foot"]) / 2, ("shin",)),
        f"ankle_{k}": (lambda J, T, s=sd: J[f"{s}Leg"] + 0.9 * (J[f"{s}Foot"] - J[f"{s}Leg"]), ("shin", "foot")),
        f"foot_{k}": (lambda J, T, s=sd: (J[f"{s}Foot"] + J[f"{s}ToeBase"]) / 2, ("foot",)),
    })


def both(*names):
    return [f"{n}_{k}" for n in names for k in "LR"]


PROMPTS = {
    "hat": (["head_top"], ["bill", "neck", "chest"]),
    "bow_tie": (["neck_low"], ["head", "neck", "chest", "belly"]),
    "shirt": (["chest", "belly"] + both("upper_arm", "forearm"), ["head", "neck"] + both("thigh", "hand")),
    "vest": (["chest", "belly"], ["head", "neck"] + both("upper_arm", "forearm", "thigh")),
    "jacket": (["chest", "belly", "hips"] + both("upper_arm", "forearm"), ["head", "neck"] + both("knee", "shin", "hand")),
    "glove": (both("hand", "wrist"), ["chest"] + both("forearm_hi", "upper_arm", "thigh")),
    "breeches": (["hips"] + both("thigh"), ["chest", "belly", "head"] + both("shin", "foot")),
    "boots": (both("shin", "ankle", "foot"), ["chest", "hips"] + both("thigh")),
}

bpy.ops.wm.open_mainfile(filepath=str(ROOT / "out" / "base-goose" / "base_goose.blend"))
rig = next(o for o in bpy.data.objects if o.type == "ARMATURE")
JJ = {b.name: np.array((rig.matrix_world @ b.head_local)[:]) for b in rig.data.bones}
TT = {b.name: np.array((rig.matrix_world @ b.tail_local)[:]) for b in rig.data.bones}
body = bpy.data.objects["base_goose_game"]
BFACE_REG = [REGV[p.vertices[0]] for p in body.data.polygons]
BBVH = BVHTree.FromPolygons([v.co.copy() for v in body.data.vertices], [tuple(p.vertices) for p in body.data.polygons])
for o in list(bpy.data.objects):
    if o.type == "MESH":
        bpy.data.objects.remove(o)
before = set(bpy.data.objects)
bpy.ops.import_scene.gltf(filepath=str(WORN))
worn = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
wv, wp = [], []
for o in worn:
    off = len(wv)
    wv += [o.matrix_world @ v.co for v in o.data.vertices]
    wp += [tuple(i + off for i in p.vertices) for p in o.data.polygons]
WBVH = BVHTree.FromPolygons(wv, wp)

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x, sc.render.resolution_y = W0, H0
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.55, 0.55, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
sc.world = w
for i, (rot, en) in enumerate([((50, 0, 30), 2.5), ((60, 0, 200), 1.2), ((80, 0, 110), 0.8)]):
    L = bpy.data.objects.new(f"l{i}", bpy.data.lights.new(f"l{i}", "SUN"))
    L.data.energy = en
    L.rotation_euler = [math.radians(a) for a in rot]
    sc.collection.objects.link(L)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = CAM["ortho_m_height"]
sc.collection.objects.link(cam)
sc.camera = cam
prompts = {}
for view, c in CAM["views"].items():
    cam.location = Vector(c["location"])
    a = math.radians(c["yaw_deg"])
    d = Vector((math.sin(a), -math.cos(a), 0.0))
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = str(OUT / f"{view}.png")
    bpy.ops.render.render(write_still=True)
    # stand-off grid
    R, U, B = np.array(c["right"]), np.array(c["up"]), np.array(c["back"])
    rows = np.arange(0, H0, STEP)
    cols = np.arange(0, W0, STEP)
    so = np.full((len(rows), len(cols)), np.nan)
    hitw = np.zeros((len(rows), len(cols)), bool)
    for i, r in enumerate(rows):
        for j, cc in enumerate(cols):
            p = TGT + R * (cc - W0 / 2) / PPM - U * (r - H0 / 2) / PPM
            o = Vector(p + B * 4.0)
            hw = WBVH.ray_cast(o, Vector(-B), 8.0)
            if hw[0] is None:
                continue
            hitw[i, j] = True
            hb = BBVH.ray_cast(o, Vector(-B), 8.0)
            if hb[0] is not None:
                so[i, j] = hb[3] - hw[3]                     # worn surface this far in front of our body
            else:
                so[i, j] = BBVH.find_nearest(hw[0])[3]       # beyond our silhouette: distance to the body
    np.savez_compressed(OUT / f"standoff_{view}.npz", rows=rows, cols=cols, standoff=so, worn=hitw)
    # prompt points
    pos, neg = PROMPTS[G]
    pts = []
    for names, lab in ((pos, 1), (neg, 0)):
        for n in names:
            fn, allowed = LM[n]
            p = fn(JJ, TT)
            rel = p - TGT
            x, y = W0 / 2 + rel @ R * PPM, H0 / 2 - rel @ U * PPM
            # the generated goose's limbs sit a little differently: search outward (<= 40 px) for the nearest
            # pixel whose ray meets the worn model on an allowed body region (the hat counts as head)
            found = None
            for rad in range(0, 44, 4):
                ring = [(0, 0)] if rad == 0 else [(dx, dy) for dx in range(-rad, rad + 1, 4) for dy in (-rad, rad)] + \
                    [(dx, dy) for dy in range(-rad + 4, rad, 4) for dx in (-rad, rad)]
                for dx, dy in ring:
                    o = Vector(TGT + R * (x + dx - W0 / 2) / PPM - U * (y + dy - H0 / 2) / PPM + B * 4.0)
                    hw = WBVH.ray_cast(o, Vector(-B), 8.0)
                    if hw[0] is None:
                        continue
                    reg = BFACE_REG[BBVH.find_nearest(hw[0])[2]]
                    if reg in allowed:
                        found = (x + dx, y + dy, reg, rad)
                        break
                if found:
                    break
            if not found:
                continue
            pts.append({"name": n, "x": round(float(found[0]), 1), "y": round(float(found[1]), 1), "label": lab,
                        "region": str(found[2]), "moved_px": found[3]})
    prompts[view] = pts
    print("VIEW", view, "worn px", int(hitw.sum()), "standoff>2cm", int(np.nansum(so > 0.02)), flush=True)
(OUT / "prompts.json").write_text(json.dumps(prompts, indent=1), encoding="utf-8")
print("PROMPTS", {v: (sum(p["label"] for p in ps), sum(1 - p["label"] for p in ps)) for v, ps in prompts.items()})
