"""Replace the generated (painted-on) eyes with the shared eyeball from assets/goose_eye.json,
so every goose has exactly the same eye mesh, texture profile and size (PLAN F5/M9).

Per character you give one surface pick per eye ("left" = character's left = +X, model faces
-Y) as {"point": [x, y, z], "normal": [nx, ny, nz]} -- get them with
`scripts/head_views.py --char <c> --pick view:px:row,...`. With symmetric=True the two picks
are averaged across the head's mirror plane, so the eyes are mirror images (clean rig).

The eyeball is a polar sphere around the look axis (the pick normal), sunk so it meets the
head at embed_deg. Its UVs run along a 1-D radial profile painted into the top texel rows
of the atlas, which retopo_bake.py reserves (object prop "uv_reserved_rows"). The eyes join
the game mesh (still one mesh / one draw call) with vertex groups eye_L / eye_R; centres
and look axes are stored as object props + returned stats for the eye bones. Painted eye
texels under each eyeball are recoloured to the surrounding head colour.
"""
import json

import bmesh
import numpy as np
from mathutils import Vector

from .common import face_centroids, input_image, read_pixels, rgb_to_hsv, texel_mask, write_pixels

NAME = "eyes"
STAGE = "game"
DEFAULTS = {
    "label": "",
    "left": None,                     # {"point": [...], "normal": [...]} on the +X eye
    "right": None,                    # same on the -X eye
    "symmetric": True,
    "spec": "assets/goose_eye.json",
    "clean_radius_m": 0.016,          # recolour painted eye texels within this of each eye
}


def _mirror(p, m, a):
    return p - 2 * ((p - m) @ a) * a


def _profile(spec, deg):
    keys = spec["profile"]
    d = np.array([k["deg"] for k in keys], float)
    rgb = np.array([k["rgb"] for k in keys], float)
    rough = np.array([k["roughness"] for k in keys], float)
    return np.stack([np.interp(deg, d, rgb[:, i]) for i in range(3)], -1), np.interp(deg, d, rough)


def _paint_strip(img, rows, fn):
    px = read_pixels(img)
    h, w = px.shape[:2]
    deg = (np.arange(w) + 0.5) / w * 180.0
    px[h - rows:, :, :3] = fn(deg)[None]
    px[h - rows:, :, 3] = 1.0
    write_pixels(img, px)


def apply(ctx, label, left, right, symmetric, spec, clean_radius_m):
    ob, me = ctx.ob, ctx.ob.data
    if left is None or right is None:
        raise ValueError("eyes: give left/right surface picks (scripts/head_views.py --pick)")
    rows = int(ob.get("uv_reserved_rows", 0))
    if not rows:
        raise ValueError("eyes: game mesh has no reserved UV strip; rerun retopo_bake.py")
    sp = json.loads((ctx.root / spec).read_text())
    R, seg, rings, embed = sp["radius_m"], sp["segments"], sp["rings_deg"], sp["embed_deg"]

    pL, pR = np.array(left["point"], float), np.array(right["point"], float)
    nL, nR = np.array(left["normal"], float), np.array(right["normal"], float)
    if symmetric:
        m = (pL + pR) / 2
        a = (pL - pR) / np.linalg.norm(pL - pR)
        pL = (pL + _mirror(pR, m, a)) / 2
        nL = nL / np.linalg.norm(nL) + (nR - 2 * (nR @ a) * a) / np.linalg.norm(nR)
        nL /= np.linalg.norm(nL)
        pR, nR = _mirror(pL, m, a), nL - 2 * (nL @ a) * a
    eyes = {}
    for name, p, n in (("eye_L", pL, nL), ("eye_R", pR, nR)):
        n = n / np.linalg.norm(n)
        eyes[name] = {"surface": p, "axis": n, "center": p - n * R * np.cos(np.radians(embed))}

    # 1) recolour the painted eyes under the eyeballs to the local head colour
    base_img = input_image(ob, "Base Color")
    base = read_pixels(base_img)
    h, w = base.shape[:2]
    cent, _ = face_centroids(ob)
    val = rgb_to_hsv(base[..., :3])[..., 2]
    recoloured = {}
    for name, e in eyes.items():
        d = np.linalg.norm(cent - e["surface"], axis=1)
        inner = texel_mask(ob, w, h, lambda c, d=d: d < clean_radius_m)
        ring = texel_mask(ob, w, h, lambda c, d=d: (d > clean_radius_m) & (d < 2.2 * clean_radius_m))
        ring_px = base[ring & (val < 0.2), :3]
        head = np.median(ring_px if len(ring_px) else base[ring, :3], 0)
        fix = inner & (val > 0.12)
        base[fix, :3] = head
        recoloured[name] = {"texels": int(fix.sum()), "head_rgb": np.round(head, 3).tolist()}
    write_pixels(base_img, base)

    # 2) radial profile into the reserved strip of every map
    _paint_strip(base_img, rows, lambda deg: _profile(sp, deg)[0])
    orm = input_image(ob, "Roughness")
    if orm is not None:
        _paint_strip(orm, rows, lambda deg: np.stack(
            [np.ones_like(deg), _profile(sp, deg)[1], np.zeros_like(deg)], -1))
    nrm_img = input_image(ob, "Normal")
    if nrm_img is not None:
        _paint_strip(nrm_img, rows, lambda deg: np.tile([0.5, 0.5, 1.0], (len(deg), 1)))

    # 3) eyeball geometry joined into the mesh
    v_mid = 1.0 - rows / 2.0 / h
    bm = bmesh.new()
    bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    n_before = len(bm.verts)
    ranges = {}
    for name, e in eyes.items():
        c, n = e["center"], e["axis"]
        t = np.cross([0.0, 0.0, 1.0], n)
        t = t / np.linalg.norm(t) if np.linalg.norm(t) > 1e-6 else np.array([1.0, 0, 0])
        b = np.cross(n, t)
        start = len(bm.verts)
        grid = []
        for th in rings:
            r = np.radians(th)
            if th in (0, 180):
                grid.append([bm.verts.new(Vector(c + R * np.cos(r) * n))] * seg)
                continue
            grid.append([bm.verts.new(Vector(c + R * (np.cos(r) * n + np.sin(r) * (np.cos(f) * t + np.sin(f) * b))))
                         for f in np.linspace(0, 2 * np.pi, seg, endpoint=False)])
        for i in range(len(rings) - 1):
            for j in range(seg):
                k = (j + 1) % seg
                vs = list(dict.fromkeys([grid[i][j], grid[i + 1][j], grid[i + 1][k], grid[i][k]]))
                # wind outward: face normal must point away from the eyeball centre
                fn = (vs[1].co - vs[0].co).cross(vs[2].co - vs[0].co)
                if fn.dot(vs[0].co - Vector(c)) < 0:
                    vs = vs[::-1]
                f = bm.faces.new(vs)
                f.smooth = True
                for loop in f.loops:
                    th = np.degrees(np.arccos(np.clip((np.array(loop.vert.co) - c) @ n / R, -1, 1)))
                    loop[uvl].uv = (th / 180.0, v_mid)
        ranges[name] = (start, len(bm.verts))
    bm.to_mesh(me)
    bm.free()
    me.update()
    for name, (s, e_) in ranges.items():
        vg = ob.vertex_groups.get(name) or ob.vertex_groups.new(name=name)
        vg.add(list(range(s, e_)), 1.0, "REPLACE")
        ob[f"{name}_center"] = [round(float(x), 5) for x in eyes[name]["center"]]
        ob[f"{name}_axis"] = [round(float(x), 4) for x in eyes[name]["axis"]]
    return {"added_verts": len(me.vertices) - n_before, "recoloured": recoloured,
            "eyes": {k: {"center": [round(float(x), 4) for x in v["center"]],
                         "axis": [round(float(x), 3) for x in v["axis"]]} for k, v in eyes.items()}}
