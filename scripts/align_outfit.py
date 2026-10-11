"""P3.2: align a clothed outfit hi mesh to the shared base goose body.

  blender -b --factory-startup --python scripts/align_outfit.py -- --char outfit_male [--no-render]
      [--crown 0.05] [--trim 0.25]   (crown: anchor top, metres above the bill tip; lower = less hat)

The outfit hides most of the body, so only the parts it leaves bare are anchors: bill, face/cheeks
and neck (base verts between ANCHOR_Z_LO and just above the bill tip; the hat covers the crown).
Fit = trimmed similarity ICP (uniform scale + rotation + translation), base anchors -> nearest
point on the outfit surface; the worst TRIM fraction is dropped each round (collar, hat brim).
Init: match the bill-tip height (both meshes have feet on Z=0, face -Y).

Writes out/<char>-goose/<char>_goose_aligned.glb (outfit in the base frame), <char>_align.json
(matrix, residuals per region, outfit distance-to-body histogram) and renders/<char>_align_*.png:
  overlay  - outfit textured + base body in green: green on bare skin = aligned (z-fight speckle),
             green on clothes = body pokes through the garment.
  dist     - outfit coloured by distance to the base body (blue <5 mm ... red >=5 cm), the P3.3 cue.
  head     - close-ups of the overlay on the head.
"""
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1]
RENDER = "--no-render" not in argv
ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "out" / "base-goose" / "base_goose_hi.glb"
SRC = ROOT / "out" / f"{CHAR}-goose" / f"{CHAR}_goose_hi.glb"
OUT_GLB = SRC.with_name(f"{CHAR}_goose_aligned.glb")
OUT_JSON = SRC.with_name(f"{CHAR}_align.json")
RENDERS = ROOT / "renders"

ANCHOR_Z_LO = 0.80      # fraction of base height: neck above the collar line
CROWN_ABOVE_TIP = float(argv[argv.index("--crown") + 1]) if "--crown" in argv else 0.05  # higher = under the hat
N_ANCHORS = 12000
TRIM = float(argv[argv.index("--trim") + 1]) if "--trim" in argv else 0.25
ITERS = 40
RES = 640


def load(path, name):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    meshes = [o for o in bpy.context.scene.objects if o not in before and o.type == "MESH"]
    ob = meshes[0]
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    for o in list(bpy.context.scene.objects):
        if o not in before and o is not ob:
            bpy.data.objects.remove(o)
    ob.name = name
    return ob


def verts(ob):
    co = np.empty(len(ob.data.vertices) * 3)
    ob.data.vertices.foreach_get("co", co)
    return co.reshape(-1, 3)


def bill_tip(co):
    top = co[co[:, 2] > 0.75 * co[:, 2].max()]
    return top[top[:, 1].argmin()]


def umeyama(p, q):
    """Similarity (s, R, t) minimising |s R p + t - q|^2."""
    mp, mq = p.mean(0), q.mean(0)
    P, Q = p - mp, q - mq
    U, S, Vt = np.linalg.svd(Q.T @ P / len(p))
    D = np.eye(3)
    D[2, 2] = np.sign(np.linalg.det(U @ Vt))
    R = U @ D @ Vt
    s = (S * np.diag(D)).sum() / (P ** 2).sum(1).mean()
    return s, R, mq - s * R @ mp


def mat4(s, R, t):
    M = np.eye(4)
    M[:3, :3] = s * R
    M[:3, 3] = t
    return M


def apply(M, p):
    return p @ M[:3, :3].T + M[:3, 3]


def nearest(bvh, pts):
    loc = np.empty_like(pts)
    nrm = np.empty_like(pts)
    for i, p in enumerate(pts):
        l, n, _, _ = bvh.find_nearest(Vector(p))
        loc[i], nrm[i] = l, n
    return loc, nrm


def stats_mm(d):
    d = np.asarray(d) * 1000
    return {"median": round(float(np.median(d)), 1), "p90": round(float(np.percentile(d, 90)), 1),
            "within_5mm": round(float((d < 5).mean()), 3), "n": int(len(d))}


# ---------------------------------------------------------------- fit
bpy.ops.wm.read_factory_settings(use_empty=True)
base = load(BASE, "base_body")
outfit = load(SRC, "outfit")
bco, oco = verts(base), verts(outfit)
H = bco[:, 2].max()
btip, otip = bill_tip(bco), bill_tip(oco)

anchor_mask = (bco[:, 2] > ANCHOR_Z_LO * H) & (bco[:, 2] < btip[2] + CROWN_ABOVE_TIP)
rng = np.random.default_rng(0)
idx = np.flatnonzero(anchor_mask)
idx = rng.choice(idx, min(N_ANCHORS, len(idx)), replace=False)
P = bco[idx]

obvh = BVHTree.FromObject(outfit, bpy.context.evaluated_depsgraph_get())
# init base -> outfit: scale about the floor so bill tips meet
s0 = otip[2] / btip[2]
M = mat4(s0, np.eye(3), np.array([otip[0] - s0 * btip[0], otip[1] - s0 * btip[1], 0.0]))
history = []
for it in range(ITERS):
    X = apply(M, P)
    Q, _ = nearest(obvh, X)
    d = np.linalg.norm(Q - X, axis=1)
    keep = d <= np.quantile(d, 1 - TRIM)
    s, R, t = umeyama(P[keep], Q[keep])
    M_new = mat4(s, R, t)
    step = np.abs(apply(M_new, P) - X).max()
    M = M_new
    history.append(round(float(np.median(d) * 1000), 2))
    if step < 1e-5:
        break

# outfit -> base frame
Minv = np.linalg.inv(M)
outfit.data.transform(Matrix(Minv.tolist()))
outfit.data.update()
oco = verts(outfit)
obvh = BVHTree.FromObject(outfit, bpy.context.evaluated_depsgraph_get())
bbvh = BVHTree.FromObject(base, bpy.context.evaluated_depsgraph_get())

# residuals: base anchor regions -> outfit surface
def region_resid(mask):
    pts = bco[mask]
    if len(pts) > 6000:
        pts = pts[rng.choice(len(pts), 6000, replace=False)]
    q, _ = nearest(obvh, pts)
    return stats_mm(np.linalg.norm(q - pts, axis=1))

bill = anchor_mask & (bco[:, 1] < btip[1] + 0.10) & (np.abs(bco[:, 2] - btip[2]) < 0.06)
neck = anchor_mask & (bco[:, 2] < btip[2] - 0.08)
face = anchor_mask & ~bill & ~neck
resid = {"anchors_all": region_resid(anchor_mask), "bill": region_resid(bill),
         "face_cheeks": region_resid(face), "neck": region_resid(neck)}

# outfit distance to body (signed by base normal: + = outside the body)
q, n = nearest(bbvh, oco)
dvec = oco - q
odist = np.linalg.norm(dvec, axis=1)
sign = np.sign((dvec * n).sum(1))
inside = (sign < 0) & (odist > 0.005)
edges = [0, 0.005, 0.01, 0.02, 0.05, 1e9]
hist = {f"{int(a*1000)}-{int(b*1000) if b < 1 else 'inf'}mm":
        round(float(((odist >= a) & (odist < b)).mean()), 3) for a, b in zip(edges, edges[1:])}

# body poke-through: base verts outside the outfit, below the anchor zone (clothed body)
clothed = bco[:, 2] < ANCHOR_Z_LO * H
cpts = bco[clothed][rng.choice(int(clothed.sum()), min(20000, int(clothed.sum())), replace=False)]
cq, cn = nearest(obvh, cpts)
cv = cpts - cq
poke = ((cv * cn).sum(1) > 0) & (np.linalg.norm(cv, axis=1) > 0.003)
poke_z = cpts[poke][:, 2]
poke_bands = {f"z{a:.1f}-{a+0.2:.1f}m": int(((poke_z >= a) & (poke_z < a + 0.2)).sum())
              for a in np.arange(0, 1.4, 0.2)}

scale = float(np.cbrt(np.linalg.det(Minv[:3, :3])))
rot = Matrix(Minv.tolist()).to_euler()
report = {
    "char": CHAR, "crown_m": CROWN_ABOVE_TIP, "trim": TRIM, "source": str(SRC.relative_to(ROOT)), "iterations": len(history),
    "median_mm_per_iter": history[:3] + ["..."] + history[-2:],
    "outfit_to_base": {"scale": round(scale, 4),
                       "rot_deg": [round(math.degrees(a), 2) for a in rot],
                       "translate_m": [round(float(v), 4) for v in Minv[:3, 3]],
                       "matrix": [[round(float(v), 6) for v in r] for r in Minv]},
    "outfit_height_m": round(float(oco[:, 2].max()), 4),
    "outfit_sole_z_m": round(float(oco[:, 2].min()), 4),
    "bill_tip_offset_mm": [round(float(v) * 1000, 1) for v in bill_tip(oco) - btip],
    "residual_base_to_outfit": resid,
    "outfit_dist_to_body_hist": hist,
    "outfit_inside_body_frac": round(float(inside.mean()), 3),
    "body_pokethrough_frac": round(float(poke.mean()), 4),
    "body_pokethrough_by_height": poke_bands,
}
OUT_JSON.write_text(json.dumps(report, indent=2))
print("ALIGN", json.dumps(report))

bpy.ops.object.select_all(action="DESELECT")
outfit.select_set(True)
bpy.context.view_layer.objects.active = outfit
bpy.ops.export_scene.gltf(filepath=str(OUT_GLB), use_selection=True, export_format="GLB")

# ---------------------------------------------------------------- renders
if RENDER:
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.view_settings.view_transform = "Standard"
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.92, 0.92, 0.92, 1)
    sc.world = w
    for i, (r, e) in enumerate([((50, 0, 30), 3.0), ((60, 0, 200), 1.5)]):
        L = bpy.data.lights.new(f"l{i}", "SUN")
        L.energy = e
        lo = bpy.data.objects.new(f"l{i}", L)
        lo.rotation_euler = Euler([math.radians(a) for a in r])
        sc.collection.objects.link(lo)
    cam = bpy.data.cameras.new("cam")
    cam.type = "ORTHO"
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    sc.camera = co

    green = bpy.data.materials.new("body_green")
    green.use_nodes = True
    green.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.1, 0.9, 0.2, 1)
    base.data.materials.clear()
    base.data.materials.append(green)

    # distance heatmap copy of the outfit (vertex colours, emission)
    heat = outfit.copy()
    heat.data = outfit.data.copy()
    sc.collection.objects.link(heat)
    t = np.clip(odist / 0.05, 0, 1)
    cols = np.stack([t, 1 - np.abs(2 * t - 1), 1 - t, np.ones_like(t)], 1)
    cols[odist < 0.005] = (0.05, 0.25, 1.0, 1)
    attr = heat.data.color_attributes.new("dist", "FLOAT_COLOR", "POINT")
    attr.data.foreach_set("color", cols.ravel())
    hm = bpy.data.materials.new("heat")
    hm.use_nodes = True
    nt = hm.node_tree
    nt.nodes.clear()
    ca = nt.nodes.new("ShaderNodeVertexColor")
    ca.layer_name = "dist"
    em = nt.nodes.new("ShaderNodeEmission")
    outn = nt.nodes.new("ShaderNodeOutputMaterial")
    nt.links.new(ca.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], outn.inputs["Surface"])
    heat.data.materials.clear()
    heat.data.materials.append(hm)

    def shot(yaw, zc, scale, path):
        y = math.radians(yaw)
        cam.ortho_scale = scale
        co.location = Vector((5 * math.sin(y), -5 * math.cos(y), zc))
        co.rotation_euler = (Vector((0, 0, zc)) - co.location).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(str(path))
        px = np.array(img.pixels[:]).reshape(RES, RES, 4)[::-1, :, :3]
        bpy.data.images.remove(img)
        return px

    def sheet(name, shots, show):
        for o in (base, outfit, heat):
            o.hide_render = o not in show
        tmp = RENDERS / "_tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        row = np.concatenate([shot(*s, tmp / f"al_{j}.png") for j, s in enumerate(shots)], 1)
        h, w_, _ = row.shape
        img = bpy.data.images.new(name, w_, h)
        img.pixels = np.concatenate([row[::-1], np.ones((h, w_, 1))], -1).ravel().tolist()
        img.filepath_raw = str(RENDERS / f"{CHAR}_align_{name}.png")
        img.file_format = "PNG"
        img.save()
        print("RENDER", img.filepath_raw)

    full = [(0, H / 2, H * 1.1), (90, H / 2, H * 1.1), (180, H / 2, H * 1.1), (35, H / 2, H * 1.1)]
    sheet("overlay", full, (base, outfit))
    sheet("dist", full, (heat,))
    head = [(90, btip[2], 0.45), (35, btip[2], 0.45), (0, btip[2] - 0.1, 0.5), (270, btip[2], 0.45)]
    sheet("head", head, (base, outfit))
