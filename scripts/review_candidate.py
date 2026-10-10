"""Phase 2D: render a candidate GLB in the sheet's 4 orthographic views + 3/4,
compare silhouettes with the prepped reference mattes, write a contact sheet.

Run:
  "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" -b --factory-startup \
      --python scripts/review_candidate.py -- <candidate.glb> [--char male] [--out renders/x.png]

Orientation: generated meshes are glTF Y-up; after import Blender makes them Z-up.
We auto-detect the facing direction by testing which of the 4 yaw rotations best
matches the FRONT reference silhouette, then render all views from that pose.
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
GLB = Path(argv[0]).resolve()
CHAR = argv[argv.index("--char") + 1] if "--char" in argv else "male"
ROOT = Path(__file__).resolve().parents[1]
OUT = Path(argv[argv.index("--out") + 1]).resolve() if "--out" in argv else \
    ROOT / "renders" / f"review_{GLB.parent.name}_{GLB.stem}.png"
REF = ROOT / "refs" / CHAR / "prepped"
RES = 512
# View name -> camera yaw around the model (degrees). Camera looks at the model's
# front from -Y in Blender after we pose the model facing -Y.
VIEWS = {"front": 0, "left": 90, "back": 180, "right": -90, "threeq": 35}


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.film_transparent = True
    sc.view_settings.view_transform = "Standard"
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.9, 0.9, 0.9, 1)
    sc.world = w
    return sc


def load(sc):
    bpy.ops.import_scene.gltf(filepath=str(GLB))
    meshes = [o for o in sc.objects if o.type == "MESH"]
    for o in sc.objects:
        o.select_set(o.type == "MESH")
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    # Normalise: feet on z=0, centered, height 1.
    co = np.array([v.co for v in ob.data.vertices])
    lo, hi = co.min(0), co.max(0)
    s = 1.0 / (hi[2] - lo[2])
    center = Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]))
    ob.data.transform(Matrix.Scale(s, 4) @ Matrix.Translation(-center))
    tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    return ob, tris


def camera(sc):
    cam = bpy.data.cameras.new("cam")
    cam.type = "ORTHO"
    cam.ortho_scale = 1.1
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co
    for i, (rot, e) in enumerate([((50, 0, 30), 3.0), ((60, 0, 200), 1.5)]):
        L = bpy.data.lights.new(f"l{i}", "SUN")
        L.energy = e
        lo = bpy.data.objects.new(f"l{i}", L)
        lo.rotation_euler = Euler([math.radians(a) for a in rot])
        sc.collection.objects.link(lo)
    return co


def aim(co, yaw_deg):
    # yaw 0 => camera at -Y looking +Y (sees model front when model faces -Y).
    yaw = math.radians(yaw_deg)
    d = 5.0
    co.location = Vector((d * math.sin(yaw), -d * math.cos(yaw), 0.5))
    look = Vector((0, 0, 0.5)) - co.location
    co.rotation_euler = look.to_track_quat("-Z", "Y").to_euler()


def render(sc, path):
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(str(path))
    px = np.array(img.pixels[:]).reshape(RES, RES, 4)[::-1]
    bpy.data.images.remove(img)
    return px


def ref_mask(view):
    img = bpy.data.images.load(str(REF / f"{view}_black.png"))
    w, h = img.size
    px = np.array(img.pixels[:]).reshape(h, w, 4)[::-1]
    bpy.data.images.remove(img)
    m = px[..., :3].max(-1) > 0.02
    return m


def norm_mask(m, size=RES):
    """Crop to bbox, scale by HEIGHT into size x size, bottom-aligned, centered."""
    ys, xs = np.where(m)
    if len(ys) == 0:
        return np.zeros((size, size), bool)
    c = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = c.shape
    tgt_h = int(size * 0.9)
    sc = tgt_h / h
    tw = max(1, int(w * sc))
    yi = (np.arange(tgt_h) / sc).astype(int).clip(0, h - 1)
    xi = (np.arange(tw) / sc).astype(int).clip(0, w - 1)
    r = c[yi][:, xi]
    # Center horizontally on silhouette mass (robust to stray ground slivers / thin floaters).
    cx = int(np.nonzero(r)[1].mean()) if r.any() else tw // 2
    out = np.zeros((size, size), bool)
    x0 = size // 2 - cx
    a, b = max(0, x0), min(size, x0 + tw)
    out[size - tgt_h - size // 20: size - size // 20, a:b] = r[:, a - x0:b - x0]
    return out


def iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


def main():
    sc = reset()
    ob, tris = load(sc)
    co = camera(sc)
    tmp = OUT.parent / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    # Find model yaw that best matches the front silhouette (and side for disambiguation).
    refs = {v: norm_mask(ref_mask(v)) for v in ("front", "left", "back", "right")}
    best = None
    for k in range(4):
        ob.rotation_euler = (0, 0, math.radians(90 * k))
        score = 0
        for v in ("front", "left"):
            aim(co, VIEWS[v])
            px = render(sc, tmp / f"probe_{k}_{v}.png")
            score += iou(norm_mask(px[..., 3] > 0.5), refs[v])
        if best is None or score > best[0]:
            best = (score, k)
    ob.rotation_euler = (0, 0, math.radians(90 * best[1]))
    scores, tiles = {}, []
    for v, yaw in VIEWS.items():
        aim(co, yaw)
        px = render(sc, tmp / f"{v}.png")
        rgb = px[..., :3] * px[..., 3:4] + 0.93 * (1 - px[..., 3:4])
        if v in refs:
            m = norm_mask(px[..., 3] > 0.5)
            scores[v] = round(iou(m, refs[v]), 3)
            diff = np.ones((RES, RES, 3)) * 0.93
            diff[m & refs[v]] = (0.55, 0.55, 0.55)
            diff[m & ~refs[v]] = (0.85, 0.2, 0.2)   # red = model only
            diff[~m & refs[v]] = (0.2, 0.4, 0.9)   # blue = reference only
            tiles.append((rgb, diff))
        else:
            tiles.append((rgb, None))
    # Contact sheet: row 1 renders, row 2 silhouette diffs.
    sheet = np.ones((RES * 2, RES * len(tiles), 3)) * 0.93
    for i, (rgb, diff) in enumerate(tiles):
        sheet[:RES, i * RES:(i + 1) * RES] = rgb
        if diff is not None:
            sheet[RES:, i * RES:(i + 1) * RES] = diff
    img = bpy.data.images.new("sheet", RES * len(tiles), RES * 2)
    rgba = np.concatenate([sheet[::-1], np.ones((RES * 2, RES * len(tiles), 1))], -1)
    img.pixels = rgba.ravel().tolist()
    img.filepath_raw = str(OUT)
    img.file_format = "PNG"
    img.save()
    info = {"glb": str(GLB), "tris": tris, "yaw_steps": best[1], "silhouette_iou": scores,
            "mean_iou": round(sum(scores.values()) / len(scores), 3), "sheet": str(OUT)}
    OUT.with_suffix(".json").write_text(json.dumps(info, indent=1))
    print("REVIEW", json.dumps(info))


main()
