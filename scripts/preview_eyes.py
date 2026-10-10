"""Preview the shared eye asset placed on a goose head (P1.6 review; not the final integration).

  blender -b --factory-startup --python scripts/preview_eyes.py -- --char base \
      --point x,y,z --normal x,y,z [--proud 0.001] [--out renders/x.png]

point/normal = the +X (character's left) eye surface pick from head_views.py --pick; the -X eye
is its mirror across X=0 (the base goose is symmetric). The eye's lid shell front sits `proud`
metres above the head surface along the normal; head vertices inside the lid sphere are pushed behind the eye (socket) and the generator's painted eye is recoloured.
"""
import math
import sys
from pathlib import Path

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
OUT = ROOT / opt("--out", f"renders/{CHAR}_eyes_preview.png")
EYE = ROOT / "assets" / "goose_eye" / "goose_eye.glb"
import json  # noqa: E402
SPEC = json.loads((ROOT / "assets" / "goose_eye" / "goose_eye.json").read_text())["spec"]

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_goose_game.glb"))
head = next(o for o in bpy.context.scene.objects if o.type == "MESH")


def place(mirror):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(EYE))
    parts = [o for o in bpy.context.scene.objects if o not in before]
    root = bpy.data.objects.new("eye_R" if mirror else "eye_L", None)
    bpy.context.scene.collection.objects.link(root)
    for o in parts:
        if o.parent is None:
            o.parent = root
    a = Vector((0, -1, 0))                       # anterior = toward the bill (model faces -Y)
    a = (a - a.dot(N) * N).normalized()
    u = Vector((0, 0, 1))
    u = (u - u.dot(N) * N - u.dot(a) * a).normalized()
    rl = SPEC["eyeball_radius"] * SPEC["lid_radius_scale"]
    c = P - N * (rl - PROUD)
    m = Matrix((a, -N, u)).transposed().to_4x4()   # columns: canonical X, Y, Z -> world
    m.translation = c
    if mirror:
        m = Matrix.Scale(-1, 4, Vector((1, 0, 0))) @ m
    root.matrix_world = m


centres = []


def socket(c, r):
    """Push head vertices that sit inside the lid sphere back behind the eyeball (radially to
    0.9 r), so the lid shell and opening show through without holes in the head mesh."""
    me = head.data
    mw, mi = head.matrix_world, head.matrix_world.inverted()
    n = 0
    for v in me.vertices:
        w = mw @ v.co
        d = w - c
        if d.length < r:
            v.co = mi @ (c + d.normalized() * 0.9 * r)
            n += 1
    me.update()
    return n


def erase_painted_eye(c, radius):
    """Recolour the generator's painted eye around c to the surrounding head colour."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from fixes.common import face_centroids, input_image, read_pixels, rgb_to_hsv, texel_mask, write_pixels
    img = input_image(head, "Base Color")
    px = read_pixels(img)
    h, w = px.shape[:2]
    cent, _ = face_centroids(head)
    cent = np.array([tuple(head.matrix_world @ Vector(x)) for x in cent])
    d = np.linalg.norm(cent - np.array(c), axis=1)
    inner = texel_mask(head, w, h, lambda _c: d < radius)
    ring = texel_mask(head, w, h, lambda _c: (d > radius) & (d < 1.6 * radius))
    val = rgb_to_hsv(px[..., :3])[..., 2]
    col = np.median(px[ring & (val < 0.2), :3], 0)
    fix = inner & (val > 0.1)
    px[fix, :3] = col
    write_pixels(img, px)
    return int(fix.sum())


place(False)
place(True)
bpy.context.view_layer.update()
rl = SPEC["eyeball_radius"] * SPEC["lid_radius_scale"]
for side in (1, -1):
    c = P - N * (rl - PROUD)
    c = Vector((c.x * side, c.y, c.z))
    print("SOCKET", side, socket(c, rl * 0.995), "verts pushed;",
          erase_painted_eye(Vector((P.x * side, P.y, P.z)), 0.02), "painted-eye texels recoloured")
sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x = sc.render.resolution_y = 700
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
target = Vector((0, P.y - 0.02, P.z - 0.01))
shots = [("side", 90, 0.20), ("three_quarter", 50, 0.20), ("front", 0, 0.20), ("eye_close", 70, 0.07)]
paths = []
for name, yaw, span in shots:
    y = math.radians(yaw)
    t = P if name == "eye_close" else target
    cam.location = t + Vector((math.sin(y), -math.cos(y), 0.05)) * 2
    cam.rotation_euler = (t - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.ortho_scale = span
    sun.rotation_euler = cam.rotation_euler
    sc.render.filepath = str(OUT.with_name(OUT.stem + f"_{name}.png"))
    bpy.ops.render.render(write_still=True)
    paths.append(sc.render.filepath)
imgs = [bpy.data.images.load(p) for p in paths]
canvas = np.zeros((700, 700 * len(imgs), 4), np.float32)
for i, im in enumerate(imgs):
    canvas[:, i * 700:(i + 1) * 700] = np.array(im.pixels[:]).reshape(700, 700, 4)
out = bpy.data.images.new("o", 700 * len(imgs), 700)
out.pixels.foreach_set(canvas.ravel())
out.filepath_raw = str(OUT)
out.file_format = "PNG"
out.save()
print("PREVIEW", OUT)
