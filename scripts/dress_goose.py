"""P3.5: dress the rigged goose in an outfit: worn shape, body masks, skinned shells, pose test.

  blender -b --factory-startup --python scripts/dress_goose.py -- --char outfit_male [--no-poses]

1. Opens out/base-goose/base_goose.blend (skinned base body "base_goose_game" + "goose_rig" + eye
   parts). body_shape != base (bodyshape.py): the rest pose moves to the character's shape -- edit
   bones take the shape's heads/tails, the body mesh the deformed rest positions (same weights).
2. Masks: a body vertex is covered when a ray along its normal hits a shell within MASK_D; a face is
   hidden when all its vertices are covered. Replacement pieces force-hide what they replace
   (gloves: Hand bones, boots: Foot/ToeBase + shin below the boot top, coat / dress: Tail). The
   body is split into sub-meshes keyed by the pieces that hide them ("body" = always visible,
   "body__coat+waistcoat" = hidden while any of those is worn).
3. Skinning: each shell copies vertex groups from the nearest body face (Data Transfer, polygon
   interpolated); loose cloth (LOOSE_D0..D1 off the body) blends leg weights to Hips; weights
   smoothed (WEIGHT_SMOOTH rounds), limited to 4, normalised; armature modifier + parent to the rig.
4. Exports out/<char>-goose/<char>_dressed.glb + <char>_dressed.blend; writes <char>_dress.json
   (mask stats, tris visible) and renders/<char>_dressed_poses.png (rest + rig_poses.Poser poses,
   front and side).
"""
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).parent))
import bodyshape  # noqa: E402
from rig_poses import Poser  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1]
POSES_ON = "--no-poses" not in argv
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{CHAR}-goose"
MASK_D = 0.06
LOOSE_D0, LOOSE_D1 = 0.015, 0.035
WEIGHT_SMOOTH = 6
LOOSE_PIECES = {"coat", "dress"}   # only hanging cloth rides the pelvis (boots / baggy breeches tore in riding)
FORCE = {"gloves": ("Hand",), "boots": ("Foot", "ToeBase"), "coat": ("Tail",), "dress": ("Tail", "UpLeg", "Leg")}   # long skirt hangs > MASK_D off the legs
RES_W, RES_H = 420, 560

bpy.ops.wm.open_mainfile(filepath=str(ROOT / "out" / "base-goose" / "base_goose.blend"))
body = bpy.data.objects["base_goose_game"]
rig = bpy.data.objects["goose_rig"]
for o in list(bpy.data.objects):                    # keep rig, body, eye parts
    if o.type == "MESH" and o is not body and not (o.name.split("_")[0] in ("eyeball", "lid", "catchlight")):
        bpy.data.objects.remove(o)
cfg = json.loads((ROOT / "chars" / f"{CHAR}.json").read_text())
names = [g.name for g in body.vertex_groups]
me = body.data
V = np.array([v.co[:] for v in me.vertices])
W = np.zeros((len(V), len(names)))
for v in me.vertices:
    for g in v.groups:
        W[v.index, g.group] = g.weight
W /= np.maximum(W.sum(1, keepdims=True), 1e-9)

# ---- 1. worn shape: rest pose + rest mesh
T = bodyshape.body_transforms(ROOT, CHAR, rig)
if T:
    tails0 = {b.name: np.array(rig.matrix_world @ b.tail_local) for b in rig.data.bones}
    heads0 = {b.name: np.array(rig.matrix_world @ b.head_local) for b in rig.data.bones}
    Vs = bodyshape.deform(V, W, names, rig, T)
    me.vertices.foreach_set("co", Vs.ravel())
    me.update()
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode="EDIT")
    inv = rig.matrix_world.inverted()
    for eb in rig.data.edit_bones:
        if eb.name not in T:
            continue
        h, A = np.array(T[eb.name]["head"]), np.array(T[eb.name]["A"])
        tail = h + A @ (tails0[eb.name] - heads0[eb.name])
        roll = eb.roll
        eb.head = inv @ Vector(h)
        eb.tail = inv @ Vector(tail)
        eb.roll = roll
    bpy.ops.object.mode_set(mode="OBJECT")
    V = Vs

# ---- shells
shells = {}
for f in sorted((D / "shells").glob("*.glb")):
    before = set(bpy.context.scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(f))
    o = next(x for x in bpy.context.scene.objects if x not in before and x.type == "MESH")
    for x in bpy.context.scene.objects:
        if x not in before and x is not o:
            bpy.data.objects.remove(x)
    o.name = f.stem
    shells[f.stem] = o
dg = bpy.context.evaluated_depsgraph_get()
sbvh = {k: BVHTree.FromObject(o, dg) for k, o in shells.items()}

# ---- 2. masks
NRM = np.array([v.normal[:] for v in me.vertices])
hid_by = [set() for _ in range(len(V))]
for i, (p, n) in enumerate(zip(V, NRM)):
    best = None
    for k, b in sbvh.items():
        hit = b.ray_cast(Vector(p) + Vector(n) * 0.0005, Vector(n), MASK_D)
        if hit[0] is not None and (best is None or hit[3] < best[1]):
            best = (k, hit[3])
    if best:
        hid_by[i].add(best[0])
dom = np.array(names)[W.argmax(1)]
for piece, bones in FORCE.items():
    if piece in shells:
        for i in np.flatnonzero([d.endswith(bones) for d in dom]):
            hid_by[i].add(piece)
key_of_face = []
for p in me.polygons:
    vs = list(p.vertices)
    if all(hid_by[v] for v in vs):
        key_of_face.append("+".join(sorted(set().union(*[hid_by[v] for v in vs]))))
    else:
        key_of_face.append("")
keys = sorted(set(key_of_face))
stats = {k or "visible": sum(1 for x in key_of_face if x == k) for k in keys}
print("MASK", json.dumps(stats))

# split the body: one object per key, sharing the armature modifier / weights
parts = {}
for k in keys:
    o = body.copy()
    o.data = me.copy()
    bpy.context.scene.collection.objects.link(o)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if key_of_face[f.index] != k], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(o.data)
    bm.free()
    o.name = "body" if not k else f"body__{k}"
    parts[o.name] = o
bpy.data.objects.remove(body)

# ---- 3. skin the shells
src = parts["body"].copy()                       # a whole body for the weight source
src.data = me.copy()
bpy.context.scene.collection.objects.link(src)
leg = [n for n in names if n.endswith(("UpLeg", "Leg", "Foot", "ToeBase"))]
for k, o in shells.items():
    for g in names:
        if g not in o.vertex_groups:
            o.vertex_groups.new(name=g)
    m = o.modifiers.new("dt", "DATA_TRANSFER")
    m.object = src
    m.use_vert_data = True
    m.data_types_verts = {"VGROUP_WEIGHTS"}
    m.vert_mapping = "POLYINTERP_NEAREST"
    m.layers_vgroup_select_src = "ALL"
    m.layers_vgroup_select_dst = "NAME"
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.modifier_apply(modifier=m.name)
    # loose cloth -> Hips
    sb = BVHTree.FromObject(src, bpy.context.evaluated_depsgraph_get())
    gi = {g.name: g.index for g in o.vertex_groups}
    Wv = np.zeros((len(o.data.vertices), len(names)))
    for v in o.data.vertices:
        for g in v.groups:
            nm = o.vertex_groups[g.group].name
            if nm in names:
                Wv[v.index, names.index(nm)] = g.weight
    d = np.array([sb.find_nearest(v.co)[3] for v in o.data.vertices])
    legw = Wv[:, [names.index(n) for n in leg]].sum(1)
    t = np.clip((d - LOOSE_D0) / (LOOSE_D1 - LOOSE_D0), 0, 1) * (legw > 0.5) * (k in LOOSE_PIECES)
    hips = np.zeros(len(names))
    hips[names.index("Hips")] = 1
    Wv = (1 - t)[:, None] * Wv + t[:, None] * hips
    # transferred weights are noisy where shell and body shapes differ (boots over webbed feet,
    # breeches at the crotch): neighbouring verts tore apart in the riding pose -> smooth over edges,
    # keep the 4 largest influences, normalise
    ed = np.array([e.vertices[:] for e in o.data.edges])
    deg = np.maximum(np.bincount(ed.ravel(), minlength=len(Wv)), 1)[:, None]
    for _ in range(WEIGHT_SMOOTH):
        acc = np.zeros_like(Wv)
        np.add.at(acc, ed[:, 0], Wv[ed[:, 1]])
        np.add.at(acc, ed[:, 1], Wv[ed[:, 0]])
        Wv = 0.5 * Wv + 0.5 * acc / deg
    keep = np.argsort(-Wv, 1)[:, :4]
    lim = np.zeros_like(Wv)
    np.put_along_axis(lim, keep, np.take_along_axis(Wv, keep, 1), 1)
    Wv = lim / np.maximum(lim.sum(1, keepdims=True), 1e-9)
    for j, n in enumerate(names):
        vg = o.vertex_groups[n]
        nz = np.flatnonzero(Wv[:, j] > 1e-4)
        vg.remove(list(range(len(o.data.vertices))))
        for i in nz:
            vg.add([int(i)], float(Wv[i, j]), "REPLACE")
    am = o.modifiers.new("arm", "ARMATURE")
    am.object = rig
    o.parent = rig
    o.matrix_parent_inverse = rig.matrix_world.inverted()
bpy.data.objects.remove(src)

tris = {k: sum(len(p.vertices) - 2 for p in o.data.polygons) for k, o in {**parts, **shells}.items()}
visible = tris.get("body", 0) + sum(tris[k] for k in shells)
report = {"char": CHAR, "mask_faces": stats, "tris": tris, "tris_dressed_visible": visible}
(D / f"{CHAR}_dress.json").write_text(json.dumps(report, indent=1))
print("DRESS", json.dumps({"tris_dressed_visible": visible, "body_visible": tris.get("body", 0)}))
bpy.ops.wm.save_as_mainfile(filepath=str(D / f"{CHAR}_dressed.blend"))
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=str(D / f"{CHAR}_dressed.glb"), use_selection=True, export_format="GLB")

# ---- 4. pose test renders
if POSES_ON:
    poser = Poser(rig)
    poses = [("rest", None), ("a_pose", poser.a_pose), ("riding", poser.riding), ("neck_curve", poser.neck_curve)]
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = RES_W, RES_H
    sc.view_settings.view_transform = "Standard"
    sc.world = bpy.data.worlds.new("w")
    sc.world.color = (0.85, 0.85, 0.85)
    if not any(o.type == "LIGHT" for o in sc.objects):
        L = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
        L.data.energy = 3
        L.rotation_euler = (math.radians(50), 0, math.radians(30))
        sc.collection.objects.link(L)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 2.0
    sc.collection.objects.link(cam)
    sc.camera = cam
    tmp = ROOT / "renders" / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    tiles = []
    for name, fn in poses:
        poser.reset()
        if fn:
            fn()
        bpy.context.view_layer.update()
        col = []
        for yaw in (0, 90):
            y = math.radians(yaw)
            cam.location = Vector((5 * math.sin(y), -5 * math.cos(y), 0.85))
            cam.rotation_euler = (Vector((0, 0, 0.85)) - cam.location).to_track_quat("-Z", "Y").to_euler()
            sc.render.filepath = str(tmp / "dp.png")
            bpy.ops.render.render(write_still=True)
            img = bpy.data.images.load(sc.render.filepath)
            col.append(np.array(img.pixels[:]).reshape(RES_H, RES_W, 4)[::-1, :, :3])
            bpy.data.images.remove(img)
        tiles.append(np.concatenate(col, 0))
    sheet = np.concatenate(tiles, 1)
    h, w_, _ = sheet.shape
    img = bpy.data.images.new("sheet", w_, h)
    img.pixels = np.concatenate([sheet[::-1], np.ones((h, w_, 1))], -1).ravel().tolist()
    img.filepath_raw = str(ROOT / "renders" / f"{CHAR}_dressed_poses.png")
    img.file_format = "PNG"
    img.save()
    print("RENDER", img.filepath_raw)
