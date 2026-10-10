"""Shared helpers for fix plugins (run inside Blender's python)."""
from dataclasses import dataclass, field
from pathlib import Path

import bpy
import numpy as np


@dataclass
class FixContext:
    ob: "bpy.types.Object"   # the mesh being cleaned (transforms applied, metres, faces -Y, feet Z=0)
    char: str                # "male", "female", ...
    height: float            # model height in metres
    root: Path               # project root
    stats: dict = field(default_factory=dict)

    @property
    def ref_dir(self):
        return self.root / "refs" / self.char / "prepped"


# ---------------------------------------------------------------- textures
def principled(ob):
    mat = ob.data.materials[0]
    return next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def input_image(ob, socket="Base Color"):
    """The image feeding a Principled BSDF input (follows one Separate Color hop for ORM maps)."""
    links = principled(ob).inputs[socket].links
    if not links:
        return None
    node = links[0].from_node
    while node.type != "TEX_IMAGE":
        inp = next((i for i in node.inputs if i.links), None)
        if inp is None:
            return None
        node = inp.links[0].from_node
    return node.image


def read_pixels(img):
    """(h, w, 4) float32, row 0 = v 0 (Blender order), values as stored (sRGB for byte images)."""
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    return px.reshape(h, w, 4)


def write_pixels(img, px):
    img.pixels.foreach_set(np.ascontiguousarray(px, np.float32).ravel())
    img.update()
    img.pack()


def load_ref(path):
    """Reference PNG as (h, w, 4), top row first."""
    img = bpy.data.images.load(str(path))
    px = read_pixels(img)[::-1]
    bpy.data.images.remove(img)
    return px


# ---------------------------------------------------------------- colour
def rgb_to_hsv(rgb):
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn
    h = np.zeros_like(mx)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    nz = d > 1e-6
    rm = nz & (mx == r)
    gm = nz & (mx == g) & ~rm
    bm = nz & ~rm & ~gm
    h[rm] = ((g - b)[rm] / d[rm]) % 6
    h[gm] = (b - r)[gm] / d[gm] + 2
    h[bm] = (r - g)[bm] / d[bm] + 4
    return np.stack([h / 6, np.where(mx > 0, d / np.maximum(mx, 1e-6), 0), mx], -1)


def hsv_to_rgb(hsv):
    h, s, v = hsv[..., 0] * 6, hsv[..., 1], hsv[..., 2]
    i = np.floor(h).astype(int) % 6
    f = h - np.floor(h)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], -1)


# ---------------------------------------------------------------- geometry -> texels
def face_centroids(ob):
    """(n_loop_tris, 3) centroids, plus loop indices (n, 3), for the active mesh."""
    me = ob.data
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    tri_loops = np.empty(n * 3, np.int32)
    me.loop_triangles.foreach_get("loops", tri_loops)
    tri_verts = np.empty(n * 3, np.int32)
    me.loop_triangles.foreach_get("vertices", tri_verts)
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    return co[tri_verts.reshape(-1, 3)].mean(1), tri_loops.reshape(-1, 3)


def texel_mask(ob, w, h, tri_select):
    """Rasterize the UV triangles chosen by tri_select(centroids) -> bool[n] into a (h, w) mask."""
    cent, tri_loops = face_centroids(ob)
    uv = np.empty(len(ob.data.loops) * 2, np.float32)
    ob.data.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    tuv = uv[tri_loops[tri_select(cent)]] * (w, h)  # pixel coords, row 0 = v 0
    mask = np.zeros((h, w), bool)
    for a, b, c in tuv:
        x0 = int(max(0, np.floor(min(a[0], b[0], c[0]))))
        x1 = int(min(w - 1, np.ceil(max(a[0], b[0], c[0]))))
        y0 = int(max(0, np.floor(min(a[1], b[1], c[1]))))
        y1 = int(min(h - 1, np.ceil(max(a[1], b[1], c[1]))))
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        l1 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / d
        l2 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / d
        mask[y0:y1 + 1, x0:x1 + 1] |= (l1 >= -0.02) & (l2 >= -0.02) & (1 - l1 - l2 >= -0.02)
    return mask


def texel_positions(ob, w, h):
    """Rasterize every UV triangle -> (h, w, 3) object-space position per texel (NaN where no
    triangle covers the texel). Lets texture edits select texels by exact 3D distance instead
    of by whole-face centroids (coarse game meshes have ~1 cm faces)."""
    me = ob.data
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    tri_loops = np.empty(n * 3, np.int32)
    me.loop_triangles.foreach_get("loops", tri_loops)
    tri_verts = np.empty(n * 3, np.int32)
    me.loop_triangles.foreach_get("vertices", tri_verts)
    co = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)[tri_verts.reshape(-1, 3)]
    uv = np.empty(len(me.loops) * 2, np.float32)
    me.uv_layers.active.data.foreach_get("uv", uv)
    tuv = uv.reshape(-1, 2)[tri_loops.reshape(-1, 3)] * (w, h)
    pos = np.full((h, w, 3), np.nan, np.float32)
    for (a, b, c), (pa, pb, pc) in zip(tuv, co):
        x0 = int(max(0, np.floor(min(a[0], b[0], c[0]))))
        x1 = int(min(w - 1, np.ceil(max(a[0], b[0], c[0]))))
        y0 = int(max(0, np.floor(min(a[1], b[1], c[1]))))
        y1 = int(min(h - 1, np.ceil(max(a[1], b[1], c[1]))))
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-12 or x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        l1 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / d
        l2 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / d
        l3 = 1 - l1 - l2
        m = (l1 >= -0.02) & (l2 >= -0.02) & (l3 >= -0.02)
        p = l1[..., None] * pa + l2[..., None] * pb + l3[..., None] * pc
        blk = pos[y0:y1 + 1, x0:x1 + 1]
        blk[m] = p[m]
    return pos
