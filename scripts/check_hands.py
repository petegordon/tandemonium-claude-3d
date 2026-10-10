"""Gate check for generated goose candidates: hands and loose pieces.

  blender -b --factory-startup --python scripts/check_hands.py -- <a.glb> [<b.glb> ...]

v2 references disagreed between front and side views about where the hands are, and every
candidate came out with a second hand per side. This counts dark (hand/glove-coloured) clusters
at hand height on each side of the body (expect exactly 1 per side) and reports the large loose
mesh pieces (detached hands, floaters). Prints one JSON line per file: "CHECK {...}".
"""
import json
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from fixes.common import face_centroids, input_image, read_pixels, rgb_to_hsv  # noqa: E402

VAL_MAX = 0.2           # hands/gloves are near-black
Z_BAND = (0.25, 0.62)   # fraction of height where hanging hands sit
X_MIN_FRAC = 0.12       # |x| / height: outside the torso
CELL = 0.012            # clustering grid (fraction of height)
TIP_BAND = 0.08         # height above the lowest dark point that counts as "hand"


def clusters(pts, cell):
    idx = np.floor(pts / cell).astype(int)
    cells = {}
    for i, c in enumerate(map(tuple, idx)):
        cells.setdefault(c, []).append(i)
    lab, n = {}, 0
    for c in cells:
        if c in lab:
            continue
        n += 1
        stack = [c]
        lab[c] = n
        while stack:
            x = stack.pop()
            for d in ((a, b, e) for a in (-1, 0, 1) for b in (-1, 0, 1) for e in (-1, 0, 1)):
                y = (x[0] + d[0], x[1] + d[1], x[2] + d[2])
                if y in cells and y not in lab:
                    lab[y] = n
                    stack.append(y)
    out = np.zeros(len(pts), int)
    for c, ii in cells.items():
        out[ii] = lab[c]
    return out


def check(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(path))
    ob = next(o for o in bpy.context.scene.objects if o.type == "MESH")
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    me = ob.data
    cent, tl = face_centroids(ob)
    z0, z1 = cent[:, 2].min(), cent[:, 2].max()
    H = z1 - z0
    px = read_pixels(input_image(ob, "Base Color"))
    h, w = px.shape[:2]
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)[tl].mean(1)
    val = rgb_to_hsv(px[np.clip((uv[:, 1] * h).astype(int), 0, h - 1),
                        np.clip((uv[:, 0] * w).astype(int), 0, w - 1), :3])[:, 2]
    zf = (cent[:, 2] - z0) / H
    res = {"file": Path(path).name, "height": round(float(H), 3), "hands": {}}
    for side, sg in (("+X", 1), ("-X", -1)):
        m = (val < VAL_MAX) & (zf > Z_BAND[0]) & (zf < Z_BAND[1]) & (cent[:, 0] * sg > X_MIN_FRAC * H)
        if m.any():  # only the lowest 8 % of the dark region: fingers/palms, not a dark forearm
            m &= zf < zf[m].min() + TIP_BAND
        lab = clusters(cent[m], CELL * H)
        counts = {k: int((lab == k).sum()) for k in np.unique(lab)} if m.any() else {}
        top = max(counts.values(), default=0)
        big = [k for k, c in counts.items() if c >= 0.25 * top and c > 200]   # thumbs/specks don't count
        res["hands"][side] = [{"faces": int((lab == k).sum()),
                               "center_frac": np.round((cent[m][lab == k].mean(0) - [0, 0, z0]) / H, 3).tolist()}
                              for k in big]
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5 * H)
    bm.verts.ensure_lookup_table()
    seen = np.zeros(len(bm.verts), bool)
    sizes = []
    for v in bm.verts:
        if seen[v.index]:
            continue
        stack, n = [v], 0
        seen[v.index] = True
        while stack:
            x = stack.pop()
            n += 1
            for e in x.link_edges:
                y = e.other_vert(x)
                if not seen[y.index]:
                    seen[y.index] = True
                    stack.append(y)
        sizes.append(n)
    sizes.sort(reverse=True)
    res["islands"] = len(sizes)
    res["loose_pieces_over_500_verts"] = [s for s in sizes[1:] if s > 500]
    res["pass"] = (all(len(v) == 1 for v in res["hands"].values()))
    print("CHECK", json.dumps(res))


for p in sys.argv[sys.argv.index("--") + 1:]:
    check(p)
