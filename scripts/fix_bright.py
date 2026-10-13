"""Refill broad bright patches in a garment shell's baked albedo (something else drawn over the garment in a
reference view -- a hand or a shirt sleeve over the vest's hip -- baked in as a pale smear).

  blender -b --factory-startup --python scripts/fix_bright.py -- --piece waistcoat [--char outfit_male_victorian]
      [--k 1.7] [--r 10] [--sat 0.45] [--glb shells/waistcoat.glb] [--out shells/waistcoat.glb] [--preview out.png]

Luminance box-blurred over --r texels (fine gold pattern averages away); texels where that broad brightness exceeds
--k x the cloth's median and that are broadly unsaturated (saturation < --sat: not the gold), and their 3-texel surround, are refilled with a coarse-to-fine average of the rest. Only the
first textured material (the cloth). --preview writes the patch mask next to the albedo for a check.
"""
import sys
from pathlib import Path

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
CHAR = opt("--char", "outfit_male_victorian")
PIECE = opt("--piece", "waistcoat")
D = ROOT / "out" / f"{CHAR}-goose"
GLB = D / opt("--glb", f"shells/{PIECE}.glb")
OUT = D / opt("--out", f"shells/{PIECE}.glb")
K, RR, SAT = opt("--k", 1.7), opt("--r", 10), opt("--sat", 0.45)


def box(a, r):
    for ax in (0, 1):
        c_ = np.cumsum(np.pad(a, [(r + 1, r) if k == ax else (0, 0) for k in range(a.ndim)], mode="edge"), ax)
        a = (np.take(c_, range(2 * r + 1, c_.shape[ax]), ax) - np.take(c_, range(0, c_.shape[ax] - 2 * r - 1), ax)) / (2 * r + 1)
    return a


def pushpull(c, m):
    if c.shape[0] <= 4 or m.all():
        return np.where(m[..., None], c, c[m].mean(0) if m.any() else 0)
    h, w = c.shape[0] // 2, c.shape[1] // 2
    cs = sum(c[i:2 * h:2, j:2 * w:2] * m[i:2 * h:2, j:2 * w:2, None] for i in (0, 1) for j in (0, 1))
    ms = sum(m[i:2 * h:2, j:2 * w:2].astype(float) for i in (0, 1) for j in (0, 1))
    coarse = pushpull(np.where(ms[..., None] > 0, cs / np.maximum(ms[..., None], 1e-9), 0), ms > 0)
    up = np.repeat(np.repeat(coarse, 2, 0), 2, 1)[:c.shape[0], :c.shape[1]]
    return np.where(m[..., None], c, up)


bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(GLB))
gar = next(o for o in bpy.data.objects if o.type == "MESH")
img = None
for m in gar.data.materials:
    bs = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if m and m.node_tree else None
    if bs and bs.inputs["Base Color"].links and bs.inputs["Base Color"].links[0].from_node.type == "TEX_IMAGE":
        img = bs.inputs["Base Color"].links[0].from_node.image
        break
w, h = img.size
px = np.array(img.pixels[:]).reshape(h, w, 4)
rgb = px[..., :3]
lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
used = lum > 0.002
med = np.median(lum[used])
broad = box(box(lum, RR), RR)
sat = (rgb.max(2) - rgb.min(2)) / np.maximum(rgb.max(2), 1e-4)
pale = box(box((sat < SAT).astype(float), RR // 2), RR // 2) > 0.6     # broadly unsaturated (gold is saturated)
bad = (broad > K * med) & pale & used
bad = box(bad.astype(float), 3) > 0.01
print("BRIGHT median", round(float(med), 3), "patch texels", int(bad.sum()))
px[..., :3] = np.where(bad[..., None], pushpull(rgb, used & ~bad), rgb)
# --dark K2 (white cloth, e.g. the shirt): broad grey smudges darker than K2 x median are lifted by the ratio
# median / broad brightness (the weave and fine creases kept), fading in over K2 -> 1
DARK = opt("--dark", 0.0)
if DARK > 0:
    rgb = px[..., :3]
    ratio = np.clip(med / np.maximum(broad, 1e-4), 1.0, 2.5)
    k = np.clip((1.0 - broad / med) / (1.0 - DARK), 0, 1) * pale * used
    k = box(box(k, 3), 3)
    lift = 1.0 + (ratio - 1.0) * k
    # ... and the cool grey cast goes too: inside the patch the colour becomes the cloth's median colour carrying only
    # the fine light / dark detail (lum / broad)
    medcol = np.median(rgb[used & (lum > med * 0.9)], 0)
    tinted = medcol[None, None, :] * np.clip(lum / np.maximum(broad, 1e-4), 0.6, 1.3)[..., None]
    px[..., :3] = np.clip(rgb * lift[..., None] * (1 - k[..., None]) + tinted * k[..., None], 0, 1)
    bad = k > 0.05
    print("DARK lifted texels", int(bad.sum()))
img.pixels = px.ravel().tolist()
img.pack()
if "--preview" in argv:
    pv = bpy.data.images.new("pv", w, h)
    vis = rgb.copy() ** (1 / 2.2)
    vis[bad] = [1, 0, 1]
    pv.pixels = np.dstack([vis, np.ones((h, w))]).ravel().tolist()
    pv.filepath_raw = opt("--preview", "")
    pv.file_format = "PNG"
    pv.save()
bpy.ops.object.select_all(action="DESELECT")
gar.select_set(True)
bpy.context.view_layer.objects.active = gar
bpy.ops.export_scene.gltf(filepath=str(OUT), export_format="GLB", use_selection=True, export_tangents=True)
print("FIXED", OUT)
