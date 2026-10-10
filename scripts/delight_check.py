"""P1.8: is lighting baked into the albedo? Measures + renders, changes nothing.

  blender -b --factory-startup --python scripts/delight_check.py -- --char base

1. Per texel of the game mesh: albedo luminance, surface normal, baked AO.
2. Texels are clustered by colour (k-means on albedo, k=4: dark / brown / cream / bill);
   within each cluster, fit  luminance ~ a + b*normal_z + c*(1-AO)  (top-light and crevice terms).
   |b| or |c| large relative to a = shading painted into the albedo.
3. Renders the model unlit (albedo only) next to lit, front and back.
Writes renders/<char>_delight_check.png and out/<char>-goose/<char>_delight_check.json.
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from fixes.common import input_image, read_pixels, rgb_to_hsv  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1] if "--char" in argv else "base"
ROOT = Path(__file__).resolve().parents[1]
bpy.ops.wm.open_mainfile(filepath=str(ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_goose.blend"))
ob = bpy.data.objects[f"{CHAR}_goose_game"]
me = ob.data
base = read_pixels(input_image(ob, "Base Color"))
orm = read_pixels(input_image(ob, "Roughness"))
h, w = base.shape[:2]
rows = int(ob.get("uv_reserved_rows", 0))

# rasterize per-texel normal (face normal) via UV triangles
me.calc_loop_triangles()
n = len(me.loop_triangles)
tl = np.empty(n * 3, np.int32)
me.loop_triangles.foreach_get("loops", tl)
fn = np.empty(n * 3, np.float32)
me.loop_triangles.foreach_get("normal", fn)
fn = fn.reshape(-1, 3)
uv = np.empty(len(me.loops) * 2, np.float32)
me.uv_layers.active.data.foreach_get("uv", uv)
tuv = uv.reshape(-1, 2)[tl.reshape(-1, 3)] * (w, h)
nz = np.full((h, w), np.nan, np.float32)
for k, (a, b, c) in enumerate(tuv):
    x0, x1 = int(max(0, min(a[0], b[0], c[0]))), int(min(w - 1, max(a[0], b[0], c[0]) + 1))
    y0, y1 = int(max(0, min(a[1], b[1], c[1]))), int(min(h - 1, max(a[1], b[1], c[1]) + 1))
    d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(d) < 1e-9 or x1 < x0 or y1 < y0:
        continue
    xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
    l1 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / d
    l2 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / d
    m = (l1 >= 0) & (l2 >= 0) & (1 - l1 - l2 >= 0)
    nz[y0:y1 + 1, x0:x1 + 1][m] = fn[k, 2]
valid = ~np.isnan(nz)
if rows:
    valid[h - rows:] = False
rgb = base[..., :3][valid]
lum = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
ao = orm[..., 0][valid]
z = nz[valid]
# k-means on albedo
rng = np.random.default_rng(0)
cent = rgb[rng.choice(len(rgb), 4, replace=False)]
for _ in range(20):
    lab = np.argmin(((rgb[:, None] - cent[None]) ** 2).sum(-1), 1)
    cent = np.array([rgb[lab == k].mean(0) if (lab == k).any() else cent[k] for k in range(4)])
report = {"texels": int(valid.sum()), "clusters": []}
for k in range(4):
    m = lab == k
    X = np.stack([np.ones(m.sum()), z[m], 1 - ao[m]], 1)
    coef, *_ = np.linalg.lstsq(X, lum[m], rcond=None)
    pred = X @ coef
    r2 = 1 - ((lum[m] - pred) ** 2).sum() / max(((lum[m] - lum[m].mean()) ** 2).sum(), 1e-9)
    up, down = lum[m][z[m] > 0.5], lum[m][z[m] < -0.5]
    report["clusters"].append({
        "albedo_rgb": np.round(cent[k], 3).tolist(), "share": round(float(m.mean()), 3),
        "lum_mean": round(float(lum[m].mean()), 3),
        "top_light_term": round(float(coef[1]), 4), "crevice_term": round(float(coef[2]), 4),
        "r2_shading_model": round(float(r2), 3),
        "up_vs_down_facing_lum": [round(float(up.mean()), 3) if len(up) else None,
                                  round(float(down.mean()), 3) if len(down) else None]})
(ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_delight_check.json").write_text(json.dumps(report, indent=1))
print("DELIGHT", json.dumps(report))

# unlit vs lit renders
sc = bpy.context.scene
for o in bpy.data.objects:
    o.hide_render = not (o is ob or o.parent is ob)
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y = 500, 800
sc.view_settings.view_transform = "Standard"
sc.world = bpy.data.worlds.new("w")
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.type = "ORTHO"
cam.data.ortho_scale = 1.9
sc.collection.objects.link(cam)
sc.camera = cam
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.0
sc.collection.objects.link(sun)
mat = me.materials[0]
nt = mat.node_tree
bsdf = next(nd for nd in nt.nodes if nd.type == "BSDF_PRINCIPLED")
out = next(nd for nd in nt.nodes if nd.type == "OUTPUT_MATERIAL")
img_node = bsdf.inputs["Base Color"].links[0].from_node
emit = nt.nodes.new("ShaderNodeEmission")
nt.links.new(img_node.outputs[0], emit.inputs["Color"])
paths = []
from mathutils import Euler  # noqa: E402
for unlit in (False, True):
    nt.links.new((emit if unlit else bsdf).outputs[0], out.inputs["Surface"])
    sc.world.color = (1, 1, 1) if unlit else (0.4, 0.4, 0.4)
    sun.hide_render = unlit
    for yaw in (0, 180):
        y = np.radians(yaw)
        cam.location = (3 * np.sin(y), -3 * np.cos(y), 0.85)
        cam.rotation_euler = Euler((np.radians(90), 0, y))
        sun.rotation_euler = Euler((np.radians(50), 0, y + np.radians(30)))
        sc.render.filepath = str(ROOT / "renders" / "_tmp" / f"dl_{int(unlit)}_{yaw}.png")
        bpy.ops.render.render(write_still=True)
        paths.append(sc.render.filepath)
imgs = [np.array(bpy.data.images.load(p).pixels[:], np.float32).reshape(800, 500, 4) for p in paths]
canvas = np.concatenate(imgs, 1)
o = bpy.data.images.new("o", 2000, 800)
o.pixels.foreach_set(canvas.ravel())
o.filepath_raw = str(ROOT / "renders" / f"{CHAR}_delight_check.png")
o.file_format = "PNG"
o.save()
