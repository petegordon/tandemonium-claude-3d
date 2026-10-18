"""Low-poly game prop from a generated hi-poly (TRELLIS / Pixal3D GLB) + decals from the clean reference views.

  blender -b --factory-startup --python scripts/prop_lowpoly.py -- --prop ketchup --hi <textured.glb>
      [--height 0.195] [--depth-ratio 0.64] [--lods 32x30,16x14] [--tex 2048]

For bottles, cans, jars -- anything that is a closed "lathe-like" shell around a vertical axis:
1. Hi mesh: transforms applied, centred on X/Y, bottom on Z=0, scaled to --height; X scaled so width/height matches the
   front reference silhouette, Y so depth = --depth-ratio x width (generators guess depth).
2. Shape grid: <seg> meridians x rings. Side rings cast horizontal rays from the axis; the two end caps cast rays from
   an axis point at rising elevation (pole = straight up / down). Each ray keeps its FARTHEST hit (outer shell, any
   interior junk ignored). Radii mirrored in X (left = right; --mirror-y: front = back too) and smoothed around each ring. Side rings are spaced by
   profile curvature, with a ring pinned on the cap line so the cap/bottle step stays crisp.
3. One UV island: u = angle (seam on the +X side), v = arc length along the meridian -> no stretch, label upright.
4. Texture (numpy, analytic per texel): base colour = plastic above the cap line, cap colour below; the front/rear
   label decals are projected orthographically from their views, faded by facing. ORM: AO 1, roughness per region.
   Material: Principled + glossy clear coat (KHR_materials_clearcoat in three.js / glTF viewers).
Writes out/props/<prop>/<prop>_lod<i>.glb, <prop>.blend, textures/, <prop>.json.
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]


def opt(name, default, cast=str):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
PROP = opt("--prop", "ketchup")
HI = Path(opt("--hi", "")).resolve()
HEIGHT = opt("--height", 0.195, float)
DEPTH_RATIO = opt("--depth-ratio", 0.64, float)
LODS = [tuple(int(x) for x in s.split("x")) for s in opt("--lods", "32x30,16x14").split(",")]
TEX = opt("--tex", 2048, int)
CAP_RINGS = opt("--cap-rings", 4, int)
MIRROR_Y = "--mirror-y" in argv
ROUGH = {"plastic": 0.22, "label": 0.62, "cap": 0.45}
PLASTIC_GAIN = opt("--plastic-gain", 1.8, float)   # photo red is shaded; PBR albedo must be brighter
SMOOTH = opt("--smooth", 2, int)                   # [1,2,1] passes along each meridian (cap line kept)
DEC = ROOT / "refs" / PROP / "decals"
OUT = ROOT / "out" / "props" / PROP
CFG = json.loads((DEC / "decals.json").read_text())


def log(*a):
    print("[prop_lowpoly]", *a, flush=True)


# ---------------------------------------------------------------- hi mesh
def load_hi():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(HI))
    obs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    for o in bpy.context.scene.objects:
        o.select_set(o in obs)
    bpy.context.view_layer.objects.active = obs[0]
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    if len(obs) > 1:
        bpy.ops.object.join()
    hi = bpy.context.view_layer.objects.active
    hi.name = f"{PROP}_hi"
    co = np.empty(len(hi.data.vertices) * 3, np.float32)
    hi.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    lo, up = co.min(0), co.max(0)
    h = up[2] - lo[2]
    width = HEIGHT * CFG["front"]["aspect_w_over_h"]
    sx, sy, sz = width / (up[0] - lo[0]), DEPTH_RATIO * width / (up[1] - lo[1]), HEIGHT / h
    hi.data.transform(Matrix.Diagonal((sx, sy, sz, 1)) @ Matrix.Translation(
        -Vector(((lo[0] + up[0]) / 2, (lo[1] + up[1]) / 2, lo[2]))))
    hi.data.update()
    return hi, width


def far_hit(bvh, origin, d, maxd=1.0):
    """Farthest surface hit along a ray (walks through every crossing)."""
    o, best, n = Vector(origin), None, 0
    while n < 64:
        loc, nor, idx, dist = bvh.ray_cast(o, d, maxd)
        if loc is None:
            break
        best = loc
        o = loc + d * 1e-5
        n += 1
    return best


# ---------------------------------------------------------------- shape grid
def side_levels(bvh, seg, n_side, z_lo, z_hi, z_cap):
    """Side ring heights: spaced by profile curvature, one pinned on the cap line."""
    zs = np.linspace(z_lo, z_hi, 240)
    ang = np.linspace(0, 2 * np.pi, 24, endpoint=False)
    prof = np.array([[(far_hit(bvh, (0, 0, z), Vector((math.cos(t), math.sin(t), 0))) or Vector((0, 0, z))).length
                      for t in ang] for z in zs])
    d1 = np.abs(np.gradient(prof, zs, axis=0)).mean(1)
    d2 = np.abs(np.gradient(np.gradient(prof.mean(1), zs), zs))
    dens = 1.0 + 4.0 * d1 / (d1.mean() + 1e-9) + 2.0 * d2 / (d2.mean() + 1e-9)
    dens = np.convolve(dens, np.ones(7) / 7, "same")
    cum = np.concatenate([[0], np.cumsum((dens[1:] + dens[:-1]) / 2 * np.diff(zs))])
    lv = np.interp(np.linspace(0, cum[-1], n_side), cum, zs)
    k = int(np.argmin(np.abs(lv[1:-1] - z_cap))) + 1          # pin the nearest inner ring on the cap line
    lv[k] = z_cap
    return np.sort(lv)


def build_grid(hi, seg, n_side, z_cap):
    bvh = BVHTree.FromObject(hi, bpy.context.evaluated_depsgraph_get())
    z_top, z_bot = HEIGHT, 0.0
    half_d = DEPTH_RATIO * CFG["front"]["aspect_w_over_h"] * HEIGHT / 2
    zs_top = z_top - 0.55 * half_d                    # end-cap ray origins sit inside the rounded ends
    zs_bot = z_bot + 0.5 * z_cap                       # inside the cap
    lv = side_levels(bvh, seg, n_side, zs_bot, zs_top, z_cap)
    thetas = np.linspace(0, 2 * np.pi, seg, endpoint=False)   # theta 0 = +X (seam), 3pi/2 = -Y = front
    rows = []                                                  # bottom -> top, each [seg, 3]
    for k in range(CAP_RINGS, 0, -1):                          # bottom cap (excluding pole)
        phi = -0.5 * np.pi * k / (CAP_RINGS + 1)
        rows.append(("cap", zs_bot, phi))
    for z in lv:
        rows.append(("side", z, 0.0))
    for k in range(1, CAP_RINGS + 1):
        phi = 0.5 * np.pi * k / (CAP_RINGS + 1)
        rows.append(("cap", zs_top, phi))
    P = np.zeros((len(rows), seg, 3))
    for i, (kind, z, phi) in enumerate(rows):
        for j, t in enumerate(thetas):
            d = Vector((math.cos(t) * math.cos(phi), math.sin(t) * math.cos(phi), math.sin(phi)))
            hit = far_hit(bvh, (0, 0, z), d)
            P[i, j] = hit if hit is not None else (0, 0, z)
    # mirror in X (theta <-> pi - theta) and, with --mirror-y, in Y (theta <-> -theta); seg must be a multiple of 4
    jm = (seg // 2 - np.arange(seg)) % seg
    P = (P + P[:, jm] * np.array([-1, 1, 1])) / 2
    if MIRROR_Y:
        P = (P + P[:, (-np.arange(seg)) % seg] * np.array([1, -1, 1])) / 2
    # smooth along each meridian, per group of rings sharing a ray origin (bottom cap / side / top cap); group ends
    # and the cap-line ring (+ neighbours) stay put so the cap step stays crisp
    origins = np.array([[0, 0, r[1]] for r in rows])
    rad = np.linalg.norm(P - origins[:, None], axis=2)
    dirs = (P - origins[:, None]) / rad[..., None]
    nb = CAP_RINGS
    groups = [range(0, nb), range(nb, nb + len(lv)), range(nb + len(lv), len(rows))]
    kcap = nb + int(np.argmin(np.abs(lv - z_cap)))
    fixed = {kcap - 1, kcap, kcap + 1}
    for _ in range(SMOOTH):
        r2 = rad.copy()
        for g in groups:
            for i in list(g)[1:-1]:
                if i not in fixed:
                    r2[i] = (rad[i - 1] + 2 * rad[i] + rad[i + 1]) / 4
        rad = r2
    P = origins[:, None] + dirs * rad[..., None]
    # smooth around each ring (relative to the ray origin) to remove generator lumps
    for i, (kind, z, phi) in enumerate(rows):
        o = np.array([0, 0, z])
        v = P[i] - o
        r = np.linalg.norm(v, axis=1)
        rs = (np.roll(r, 1) + 2 * r + np.roll(r, -1)) / 4
        P[i] = o + v / r[:, None] * rs[:, None]
    bot = far_hit(bvh, (0, 0, zs_bot), Vector((0, 0, -1)))
    top = far_hit(bvh, (0, 0, zs_top), Vector((0, 0, 1)))
    poles = np.array([[0, 0, max(bot.z, 0.0) if bot else 0.0], [0, 0, top.z if top else HEIGHT]])
    P[0, :, 2] = np.maximum(P[0, :, 2], 0.0)
    return P, poles, thetas, [r[0] for r in rows]


def make_mesh(name, P, poles, seg):
    R = P.shape[0]
    verts = [tuple(p) for p in P.reshape(-1, 3)] + [tuple(poles[0]), tuple(poles[1])]
    ib, it = R * seg, R * seg + 1
    faces = []
    for i in range(R - 1):
        for j in range(seg):
            a, b = i * seg + j, i * seg + (j + 1) % seg
            faces.append((a, b, b + seg, a + seg))
    for j in range(seg):
        faces.append((ib, (j + 1) % seg, j))                        # bottom fan
        faces.append((it, (R - 1) * seg + j, (R - 1) * seg + (j + 1) % seg))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    # arc-length v per ring (meridian-averaged), poles at 0 / 1
    pts = np.concatenate([np.repeat(poles[:1][None], seg, 1), P, np.repeat(poles[1:][None], seg, 1)], 0)
    seglen = np.linalg.norm(np.diff(pts, axis=0), axis=2).mean(1)
    vring = np.concatenate([[0], np.cumsum(seglen)]) / seglen.sum()      # len R + 2
    uvl = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        vis = [me.loops[li].vertex_index for li in poly.loop_indices]
        jj = [vi % seg for vi in vis if vi < R * seg]
        wrap = max(jj) - min(jj) > 1                                      # face crossing the seam: 0 -> seg
        jj = [j + seg if (wrap and j == 0) else j for j in jj]
        for li, vi in zip(poly.loop_indices, vis):
            if vi >= R * seg:                                             # pole: middle of its fan wedge
                uvl.data[li].uv = (sum(jj) / len(jj) / seg, 0.0 if vi == ib else 1.0)
            else:
                i, j = divmod(vi, seg)
                if wrap and j == 0:
                    j = seg
                uvl.data[li].uv = (j / seg, vring[i + 1])
    return me, vring


# ---------------------------------------------------------------- texture
def load_rgba(path):
    img = bpy.data.images.load(str(path))
    w, h = img.size
    a = np.array(img.pixels[:], np.float32).reshape(h, w, 4)[::-1]   # row 0 = top
    bpy.data.images.remove(img)
    return a


def sample(img, x, y):
    h, w, _ = img.shape
    x = np.clip(x, 0, w - 1.001)
    y = np.clip(y, 0, h - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = (x - x0)[..., None], (y - y0)[..., None]
    return (img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy)
            + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy)


def srgb_to_lin(c):
    c = np.asarray(c, np.float32) / 255
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def bake_textures(P, poles, vring, z_cap, width, tex):
    """Per texel: (u, v) -> grid (j, ring) -> bilinear position / normal -> colours."""
    seg = P.shape[1]
    pts = np.concatenate([np.repeat(poles[:1][None], seg, 1), P, np.repeat(poles[1:][None], seg, 1)], 0)
    # vertex normals of the grid (central differences)
    du = np.roll(pts, -1, 1) - np.roll(pts, 1, 1)
    dv = np.zeros_like(pts)
    dv[1:-1] = pts[2:] - pts[:-2]
    dv[0], dv[-1] = pts[1] - pts[0], pts[-1] - pts[-2]
    N = np.cross(du, dv)
    N /= np.linalg.norm(N, axis=2, keepdims=True) + 1e-12
    N[0], N[-1] = (0, 0, -1), (0, 0, 1)
    u = (np.arange(tex) + 0.5) / tex
    v = (np.arange(tex) + 0.5) / tex
    U, V = np.meshgrid(u, v)                      # row = v (0 at bottom in Blender image order)
    jf = U * seg
    rf = np.interp(V, vring, np.arange(len(vring)))
    j0 = np.floor(jf).astype(int) % seg
    j1 = (j0 + 1) % seg
    r0 = np.clip(np.floor(rf).astype(int), 0, len(vring) - 2)
    fj, fr = (jf - np.floor(jf))[..., None], (rf - r0)[..., None]

    def bil(A):
        return (A[r0, j0] * (1 - fj) * (1 - fr) + A[r0, j1] * fj * (1 - fr)
                + A[r0 + 1, j0] * (1 - fj) * fr + A[r0 + 1, j1] * fj * fr)

    X, Nn = bil(pts), bil(N)
    Nn /= np.linalg.norm(Nn, axis=2, keepdims=True) + 1e-12
    plastic = np.clip(srgb_to_lin(CFG["front"]["plastic_rgb"]) * PLASTIC_GAIN, 0, 1)
    cap = srgb_to_lin(CFG["front"]["cap_rgb"])
    is_cap = X[..., 2] < z_cap
    col = np.where(is_cap[..., None], cap, plastic)
    rough = np.where(is_cap, ROUGH["cap"], ROUGH["plastic"])
    label_a = np.zeros(is_cap.shape, np.float32)
    for view, sgn in (("front", -1), ("rear", 1)):
        c = CFG[view]
        x0, x1, y0, y1 = c["bbox"]
        img = load_rgba(DEC / c["label"])
        xn = (X[..., 0] / width + 0.5)                      # 0 at -X
        if view == "rear":
            xn = 1 - xn                                     # seen from behind, image left = +X
        px = x0 + xn * (x1 - x0)
        py = y1 - X[..., 2] / HEIGHT * (y1 - y0)
        s = sample(img, px, py)
        facing = np.clip((sgn * Nn[..., 1] - 0.15) / 0.35, 0, 1)
        a = s[..., 3] * facing * (sgn * Nn[..., 1] > 0)
        lin = s[..., :3]                                    # Blender loads PNG as sRGB -> pixels already linear
        col = col * (1 - a[..., None]) + lin * a[..., None]
        label_a = np.maximum(label_a, a)
    rough = rough * (1 - label_a) + ROUGH["label"] * label_a
    orm = np.dstack([np.ones_like(rough), rough, np.zeros_like(rough)])
    return col, orm, label_a


def save_image(name, arr, path, colorspace):
    h, w, _ = arr.shape
    img = bpy.data.images.new(name, w, h, alpha=False, float_buffer=False)
    img.colorspace_settings.name = colorspace
    rgba = np.dstack([arr, np.ones((h, w))]).astype(np.float32)
    img.pixels.foreach_set(rgba.ravel())
    img.filepath_raw = str(path)
    img.file_format = "PNG"
    img.save()
    return img


def make_material(albedo, orm):
    m = bpy.data.materials.new(f"{PROP}_mat")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    t_alb = nt.nodes.new("ShaderNodeTexImage")
    t_alb.image = albedo
    t_orm = nt.nodes.new("ShaderNodeTexImage")
    t_orm.image = orm
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(t_alb.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(t_orm.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    bsdf.inputs["Coat Weight"].default_value = 0.5        # glossy squeeze-bottle sheen (label gets it too: printed film)
    bsdf.inputs["Coat Roughness"].default_value = 0.08
    return m


# ---------------------------------------------------------------- main
def main():
    hi, width = load_hi()
    z_cap = CFG["front"]["cap_frac"] * HEIGHT
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "textures").mkdir(exist_ok=True)
    col_hi = bpy.data.collections.new("Hi")
    bpy.context.scene.collection.children.link(col_hi)
    for c in hi.users_collection:
        c.objects.unlink(hi)
    col_hi.objects.link(hi)
    hi.hide_render = True
    stats = {"hi": str(HI), "height_m": HEIGHT, "width_m": round(width, 4), "depth_m": round(DEPTH_RATIO * width, 4),
             "cap_z_m": round(z_cap, 4), "lods": []}
    mat = None
    for li, (seg, n_side) in enumerate(LODS):
        P, poles, thetas, kinds = build_grid(hi, seg, n_side, z_cap)
        me, vring = make_mesh(f"{PROP}_lod{li}", P, poles, seg)
        if mat is None:                                   # texture from the finest LOD; all LODs share UV layout
            col, orm, la = bake_textures(P, poles, vring, z_cap, width, TEX)
            albedo = save_image(f"{PROP}_albedo", col, OUT / "textures" / f"{PROP}_albedo.png", "sRGB")
            ormi = save_image(f"{PROP}_orm", orm, OUT / "textures" / f"{PROP}_orm.png", "Non-Color")
            mat = make_material(albedo, ormi)
        me.materials.append(mat)
        ob = bpy.data.objects.new(f"{PROP}_lod{li}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.location.x = 0.15 * li
        for o in bpy.context.scene.objects:
            o.select_set(o == ob)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(50))
        ob.location.x = 0
        glb = OUT / f"{PROP}_lod{li}.glb"
        bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True, export_yup=True,
                                  export_apply=True, export_image_format="AUTO", export_tangents=False)
        ob.location.x = 0.15 * li
        tris = sum(len(p.vertices) - 2 for p in me.polygons)
        stats["lods"].append({"glb": glb.name, "segments": seg, "side_rings": n_side, "tris": tris,
                              "verts": len(me.vertices), "kb": round(glb.stat().st_size / 1024)})
        log(f"lod{li}: {seg} seg x {n_side} rings -> {tris} tris, {glb}")
    for img in bpy.data.images:
        if img.filepath_raw:
            img.filepath = str(Path(img.filepath_raw))
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{PROP}.blend"), compress=True)
    (OUT / f"{PROP}.json").write_text(json.dumps(stats, indent=1))
    log("DONE", json.dumps(stats))


main()
