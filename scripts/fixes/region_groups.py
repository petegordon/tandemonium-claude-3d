"""Tag game-mesh vertices into named vertex groups (hat, coat, boots, ...) by baked colour
and height. Prep for rigging and the separate-clothing stretch goal (PLAN M6/F6).

Each group: {"name", "z_frac": [lo, hi], "hue_deg", "sat", "val"} evaluated on the BAKED
base colour at each vertex's UV. Groups are assigned in order; a vertex goes to the first
group that matches ("first wins"), unmatched vertices go to "other". Stored in the .blend
(glTF exports vertex groups only as skin weights, so this is for Blender-side work).
"""
import numpy as np

from .common import input_image, read_pixels, rgb_to_hsv

NAME = "region_groups"
STAGE = "game"
DEFAULTS = {"groups": []}


def apply(ctx, groups):
    ob, me = ctx.ob, ctx.ob.data
    img = input_image(ob, "Base Color")
    px = read_pixels(img)
    h, w = px.shape[:2]
    # average UV per vertex (verts on seams get one of their loops; fine for tagging)
    lv = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", lv)
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    vuv = np.zeros((len(me.vertices), 2), np.float32)
    vuv[lv] = uv.reshape(-1, 2)
    rgb = px[np.clip((vuv[:, 1] * h).astype(int), 0, h - 1), np.clip((vuv[:, 0] * w).astype(int), 0, w - 1), :3]
    hsv = rgb_to_hsv(rgb)
    hue = hsv[:, 0] * 360
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    z = co.reshape(-1, 3)[:, 2] / ctx.height
    taken = np.zeros(len(me.vertices), bool)
    counts = {}
    for vg in list(ob.vertex_groups):
        ob.vertex_groups.remove(vg)
    for g in groups:
        zl, zh = g.get("z_frac", [0, 1])
        hl, hh = g.get("hue_deg", [0, 360])
        sl, sh = g.get("sat", [0, 1])
        vl, vh = g.get("val", [0, 1])
        in_hue = (hue >= hl) & (hue <= hh) if hl <= hh else (hue >= hl) | (hue <= hh)
        m = (~taken & (z >= zl) & (z <= zh) & in_hue & (hsv[:, 1] >= sl) & (hsv[:, 1] <= sh)
             & (hsv[:, 2] >= vl) & (hsv[:, 2] <= vh))
        vg = ob.vertex_groups.new(name=g["name"])
        vg.add(np.where(m)[0].tolist(), 1.0, "REPLACE")
        taken |= m
        counts[g["name"]] = int(m.sum())
    other = ob.vertex_groups.new(name="other")
    other.add(np.where(~taken)[0].tolist(), 1.0, "REPLACE")
    counts["other"] = int((~taken).sum())
    return {"verts": len(me.vertices), "groups": counts}
