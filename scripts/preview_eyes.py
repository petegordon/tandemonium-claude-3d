"""Preview the shared eye asset fitted to a goose head (P1.6 review; not the final integration).

  blender -b --factory-startup --python scripts/preview_eyes.py -- --char base \
      --point x,y,z --normal x,y,z [--proud 0.002] [--states] [--out renders/x.png]

point/normal = the +X (character's left) eye surface pick from head_views.py --pick; the -X eye
is its mirror across X=0 (the base goose is symmetric). The lid shell front sits `proud` metres
above the head surface along the normal.

Socket (preview version of what the integration will do): head faces around each eye are
subdivided, then every head vertex near the eye is re-seated in the eye's own frame -
outside the opening it is wrapped just over the lid shell (the head skin covers the shell,
no flaps), inside the opening it is pushed back behind the eyeball. The generator's painted
eye is recoloured to the surrounding head colour.

Default output: head views (side, 3/4, front, close-up). --states renders a sheet of eye
states on the head: rest, look toward the bill / back / up / down, half blink, closed.
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]


def opt(name, default):
    return argv[argv.index(name) + 1] if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "base")
P = Vector(map(float, opt("--point", "0,0,0").split(",")))
N = Vector(map(float, opt("--normal", "1,0,0").split(","))).normalized()
PROUD = float(opt("--proud", "0.002"))
STATES = "--states" in argv
OUT = ROOT / opt("--out", f"renders/{CHAR}_eyes_{'states' if STATES else 'preview'}.png")
EYE = ROOT / "assets" / "goose_eye" / "goose_eye.glb"
META = json.loads((ROOT / "assets" / "goose_eye" / "goose_eye.json").read_text())
SPEC = META["spec"]
R_EYE = SPEC["eyeball_radius"]
R_LID = R_EYE * SPEC["lid_radius_scale"]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_goose_game.glb"))
head = next(o for o in bpy.context.scene.objects if o.type == "MESH")
bpy.context.view_layer.objects.active = head
head.select_set(True)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)


def opening_f(az, el):
    """< 1 inside the lid opening (same superellipse as make_eye_asset.py)."""
    ha, pw = SPEC["opening_half_angle_deg"], SPEC["opening_power"]
    h = ha[0] if az >= 0 else ha[1]
    p = pw[0] if az >= 0 else pw[1]
    return (abs(az) / h) ** p + (abs(el) / ha[2]) ** p


def place(mirror):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(EYE))
    parts = {o.name.split(".")[0]: o for o in bpy.context.scene.objects if o not in before}
    root = bpy.data.objects.new("eye_R" if mirror else "eye_L", None)
    bpy.context.scene.collection.objects.link(root)
    for o in parts.values():
        o.rotation_mode = "XYZ"                  # glTF import uses quaternions; pose() sets Euler
        if o.parent is None:
            o.parent = root
    a = Vector((0, -1, 0))                       # anterior = toward the bill (model faces -Y)
    a = (a - a.dot(N) * N).normalized()
    u = Vector((0, 0, 1))
    u = (u - u.dot(N) * N - u.dot(a) * a).normalized()
    m = Matrix((a, -N, u)).transposed().to_4x4()   # columns: canonical X, Y, Z -> world
    m.translation = P - N * (R_LID - PROUD)
    if mirror:
        m = Matrix.Scale(-1, 4, Vector((1, 0, 0))) @ m
    root.matrix_world = m
    return root, parts


def carve_socket(root):
    """Subdivide the head around the eye, then re-seat nearby head vertices in eye space."""
    to_eye = root.matrix_world.inverted()
    centre = root.matrix_world.translation
    bm = bmesh.new()
    bm.from_mesh(head.data)
    near = [f for f in bm.faces if (f.calc_center_median() - centre).length < R_LID * 1.6]
    bmesh.ops.subdivide_edges(bm, edges=list({e for f in near for e in f.edges}), cuts=3, use_grid_fill=True)
    moved = 0
    for v in bm.verts:
        q = to_eye @ v.co                         # eye frame: look -Y, anterior +X, up +Z
        r = q.length
        if r > R_LID * 1.25 or r < 1e-9:
            continue
        d = q / r
        az = math.degrees(math.atan2(d.x, -d.y))
        el = math.degrees(math.asin(max(-1.0, min(1.0, d.z))))
        if d.y < 0 and opening_f(az, el) < 1.0:
            if r < R_LID * 1.1:                   # in front of the eye: push behind the eyeball
                v.co = root.matrix_world @ (d * R_EYE * 0.9)
                moved += 1
        else:                                     # around the eye: skin wraps just over the lid
            target = R_LID * 1.012
            if r < target:
                v.co = root.matrix_world @ (d * target)
                moved += 1
            elif r < R_LID * 1.25:                # blend back to the original surface
                t = (r - target) / (R_LID * 1.25 - target)
                v.co = root.matrix_world @ (d * (target + (r - target) * (t ** 0.5)))
    bm.to_mesh(head.data)
    bm.free()
    head.data.update()
    return moved


def erase_painted_eye(c, radius):
    sys.path.insert(0, str(ROOT / "scripts"))
    from fixes.common import face_centroids, input_image, read_pixels, rgb_to_hsv, texel_mask, write_pixels
    img = input_image(head, "Base Color")
    px = read_pixels(img)
    h, w = px.shape[:2]
    cent, _ = face_centroids(head)
    d = np.linalg.norm(cent - np.array(c), axis=1)
    inner = texel_mask(head, w, h, lambda _c: d < radius)
    ring = texel_mask(head, w, h, lambda _c: (d > radius) & (d < 1.6 * radius))
    val = rgb_to_hsv(px[..., :3])[..., 2]
    px[inner & (val > 0.1), :3] = np.median(px[ring & (val < 0.2), :3], 0)
    write_pixels(img, px)


eyes = [place(False), place(True)]
bpy.context.view_layer.update()
for side, (root, _) in zip((1, -1), eyes):
    erase_painted_eye(Vector((P.x * side, P.y, P.z)), 0.02)
for root, _ in eyes:
    print("SOCKET", root.name, carve_socket(root), "head verts re-seated")
bpy.ops.object.select_all(action="DESELECT")
head.select_set(True)
bpy.context.view_layer.objects.active = head
bpy.ops.object.shade_smooth()


def pose(look_az=0.0, look_el=0.0, blink=0.0):
    up, lo = META["blink_closed_deg"]["lid_upper"], META["blink_closed_deg"]["lid_lower"]
    for root, parts in eyes:
        parts["eyeball"].rotation_euler = (math.radians(-look_el), 0,
                                           math.radians(SPEC["gaze_rest_az_deg"] + look_az))
        parts["lid_upper"].rotation_euler = (math.radians(up) * blink, 0, 0)
        parts["lid_lower"].rotation_euler = (math.radians(lo) * blink, 0, 0)
        # lids follow the gaze a little vertically, like a real eye
        parts["lid_upper"].rotation_euler.x += math.radians(-0.35 * look_el)
        parts["lid_lower"].rotation_euler.x += math.radians(-0.35 * look_el)


sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
RES = 600
sc.render.resolution_x = sc.render.resolution_y = RES
sc.view_settings.view_transform = "Standard"
sc.world = bpy.data.worlds.new("w")
sc.world.color = (0.85, 0.85, 0.85)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
sc.collection.objects.link(cam)
sc.camera = cam
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.5
sc.collection.objects.link(sun)


def shot(target, yaw, span, path):
    y = math.radians(yaw)
    cam.location = target + Vector((math.sin(y), -math.cos(y), 0.05)) * 2
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = span
    sun.rotation_euler = cam.rotation_euler
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    return str(path)


head_t = Vector((0, P.y - 0.02, P.z - 0.01))
tmp = ROOT / "renders" / "_tmp"
rows = []
if STATES:
    states = [("rest", {}), ("look_bill", {"look_az": 15}), ("look_back", {"look_az": -8}),
              ("look_up", {"look_el": 8}), ("look_down", {"look_el": -8}),
              ("half_blink", {"blink": 0.5}), ("closed", {"blink": 1.0})]
    row_close, row_head = [], []
    for name, kw in states:
        pose(**kw)
        row_close.append(shot(P, 75, 0.06, tmp / f"st_{name}_eye.png"))
        row_head.append(shot(head_t, 35, 0.19, tmp / f"st_{name}_head.png"))
    rows = [row_close, row_head]
else:
    pose()
    rows = [[shot(head_t, 90, 0.20, tmp / "pv_side.png"), shot(head_t, 50, 0.20, tmp / "pv_q.png"),
             shot(head_t, 0, 0.20, tmp / "pv_front.png"), shot(P, 70, 0.07, tmp / "pv_eye.png")]]
cols = max(len(r) for r in rows)
canvas = np.ones((RES * len(rows), RES * cols, 4), np.float32)
for ri, row in enumerate(rows):
    for ci, pth in enumerate(row):
        im = bpy.data.images.load(pth)
        canvas[(len(rows) - 1 - ri) * RES:(len(rows) - ri) * RES, ci * RES:(ci + 1) * RES] = \
            np.array(im.pixels[:]).reshape(RES, RES, 4)
out = bpy.data.images.new("o", RES * cols, RES * len(rows))
out.pixels.foreach_set(canvas.ravel())
out.filepath_raw = str(OUT)
out.file_format = "PNG"
out.save()
print("PREVIEW", OUT)
