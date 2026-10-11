"""P3.5: dress the rigged goose in an outfit: worn shape, body masks, skinned shells, pose test.

  blender -b --factory-startup --python scripts/dress_goose.py -- --char outfit_male [--no-poses]

1. Opens out/base-goose/base_goose.blend (skinned base body "base_goose_game" + "goose_rig" + eye
   parts). body_shape != base (bodyshape.py): the rest pose moves to the character's shape -- edit
   bones take the shape's heads/tails, the body mesh the deformed rest positions (same weights).
   Modelled accessories (make_accessory.py, json "clear") first delete faces of the listed extracted
   shells whose horizontal radial line meets the accessory within 2.5 cm (old fragments of the piece).
2. Masks: designed garments (make_garment.py, json "covers") hide exactly the body band they were built
   from; for the other shells a body vertex is covered when a ray along its normal hits a shell within MASK_D (or, poking
   through, against its normal within MASK_IN); a face is
   hidden when all its vertices are covered. Replacement pieces force-hide what they replace
   (gloves: Hand bones, boots: Foot/ToeBase + shin below the boot top, coat / breeches / dress: Tail --
   the tail is hidden under clothes; build_shell.py "shell_fill" closes the breeches seat over it). The
   body is split into sub-meshes keyed by the pieces that hide them ("body" = always visible,
   "body__coat+waistcoat" = hidden while any of those is worn).
3. Skinning (D12 chains: hanging pieces coat / dress get 6 cloth chains, front/side/back x L/R,
   3 bones from Hips, placed from their loose verts; loose verts weight to them by angle and height;
   chain roots follow the thighs at FOLLOW -> <char>_cloth_chains.json): each shell copies
   vertex groups from the nearest body face (Data Transfer, polygon
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
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

sys.path.insert(0, str(Path(__file__).parent))
import bodyshape  # noqa: E402
from rig_poses import Poser  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
CHAR = argv[argv.index("--char") + 1]
POSES_ON = "--no-poses" not in argv
ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "out" / f"{CHAR}-goose"
MASK_D = 0.06
MASK_IN = 0.015       # inward: a shell up to 1.5 cm under the body surface (the body pokes through it)
LOOSE_D0, LOOSE_D1 = 0.015, 0.035
WEIGHT_SMOOTH = 6
LOOSE_PIECES = {"coat", "dress"}
CHAIN_AZ = {"FL": 30, "FR": -30, "SL": 90, "SR": -90, "BL": 150, "BR": -150}   # 0 = front, + = character left
FOLLOW = {"F": 0.7, "S": 0.35, "B": 0.0}
DRAPE = [1.0, 0.45, 0.15]   # share of the follow per chain bone (root, mid, tip): fabric bends at the knee   # only hanging cloth rides the pelvis (boots / baggy breeches tore in riding)
FORCE = {"gloves": ("Hand",), "boots": ("Foot", "ToeBase"), "coat": ("Tail",), "breeches": ("Tail",), "dress": ("Tail", "UpLeg", "Leg")}   # long skirt hangs > MASK_D off the legs
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
# modelled accessories (make_accessory.py) clear the old fragments other shells kept around them
for f in sorted((D / "shells").glob("*.json")):
    spec = json.loads(f.read_text()).get("clear")
    if not spec or f.stem not in shells:
        continue
    acc = shells[f.stem]
    keep = [p_.index for p_ in acc.data.polygons if acc.data.materials[p_.material_index].name.split(".")[0] in spec["materials"]]
    AV = [acc.matrix_world @ v.co for v in acc.data.vertices]
    cover = BVHTree.FromPolygons(AV, [list(acc.data.polygons[i].vertices) for i in keep])
    for k in spec["pieces"]:
        o = shells.get(k)
        if o is None:
            continue
        bm = bmesh.new()
        bm.from_mesh(o.data)
        kill = []
        for fc in bm.faces:
            c = o.matrix_world @ fc.calc_center_median()
            d = Vector((c.x, c.y - spec["axis_y"], 0))
            if d.length < 1e-6:
                continue
            d.normalize()
            if any(cover.ray_cast(c, s * d, spec["radial"])[0] is not None for s in (1, -1)):
                kill.append(fc)
        bmesh.ops.delete(bm, geom=kill, context="FACES")
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
        bm.to_mesh(o.data)
        bm.free()
        print("CLEAR", f.stem, k, len(kill))
# "<target>@<name>" add-ons (make_accessory.py "accessory_split") are part of the target garment
for k in [k for k in shells if "@" in k]:
    tgt = k.split("@")[0]
    if tgt in shells:
        bpy.ops.object.select_all(action="DESELECT")
        shells[k].select_set(True)
        shells[tgt].select_set(True)
        bpy.context.view_layer.objects.active = shells[tgt]
        bpy.ops.object.join()
        shells[tgt].name = tgt
    shells.pop(k)
dg = bpy.context.evaluated_depsgraph_get()
sbvh = {k: BVHTree.FromObject(o, dg) for k, o in shells.items()}

# ---- 2. masks
NRM = np.array([v.normal[:] for v in me.vertices])
hid_by = [set() for _ in range(len(V))]
# designed garments (make_garment.py) are built from a known body band: they hide exactly that band
# (below the waist line by "margin", arms excluded) and take no part in the ray masks
designed = {}
for k in shells:
    jf = D / "shells" / f"{k}.json"
    cv = json.loads(jf.read_text(encoding="utf-8")).get("covers") if jf.exists() else None
    if cv:
        designed[k] = cv
domv = np.array(names)[W.argmax(1)]
armv = np.array([("Arm" in d) or ("Hand" in d) or ("Shoulder" in d) for d in domv])
for k, cv in designed.items():
    zt = cv["z_top"] + cv["rise"] * (V[:, 1] - cv["y0"]) - cv["margin"]
    for i in np.flatnonzero((V[:, 2] < zt) & (V[:, 2] > cv["z_bot"]) & ~armv):
        hid_by[i].add(k)
ray_shells = {k: b for k, b in sbvh.items() if k not in designed}
for i, (p, n) in enumerate(zip(V, NRM)):
    best = None
    for k, b in ray_shells.items():
        hit = b.ray_cast(Vector(p) + Vector(n) * 0.0005, Vector(n), MASK_D)
        if hit[0] is not None and (best is None or hit[3] < best[1]):
            best = (k, hit[3])
    if best is None:      # body poking just past a shell (shell right behind the surface): hidden too
        for k, b in ray_shells.items():
            hit = b.ray_cast(Vector(p) - Vector(n) * 0.0005, -Vector(n), MASK_IN)
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

# ---- 3. skin the shells (pass A: transfer + loose factor; B: cloth chains; C: weights)
src = parts["body"].copy()                       # a whole body for the weight source
src.data = me.copy()
bpy.context.scene.collection.objects.link(src)
leg = [n for n in names if n.endswith(("UpLeg", "Leg", "Foot", "ToeBase"))]
sb = BVHTree.FromObject(src, bpy.context.evaluated_depsgraph_get())
skin = {}
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
    Wv = np.zeros((len(o.data.vertices), len(names)))
    for v in o.data.vertices:
        for g in v.groups:
            nm = o.vertex_groups[g.group].name
            if nm in names:
                Wv[v.index, names.index(nm)] = g.weight
    X = np.array([v.co[:] for v in o.data.vertices])
    d = np.array([sb.find_nearest(Vector(x))[3] for x in X])
    legw = Wv[:, [names.index(n) for n in leg]].sum(1)
    tl = np.clip((d - LOOSE_D0) / (LOOSE_D1 - LOOSE_D0), 0, 1) * (legw > 0.5) * (k in LOOSE_PIECES)
    jf = D / "shells" / f"{k}.json"
    meta = json.loads(jf.read_text(encoding="utf-8")) if jf.exists() else {}
    if meta.get("weights"):          # designed garment: the body's own weights, matched by position
        wz = np.load(D / "shells" / meta["weights"])
        kdw = KDTree(len(wz["pos"]))
        for i_, q_ in enumerate(wz["pos"]):
            kdw.insert(Vector(q_), i_)
        kdw.balance()
        idx = np.array([kdw.find(Vector(x))[1] for x in X])
        Wv = np.zeros((len(X), len(names)))
        for j_, nm in enumerate(wz["names"]):
            if str(nm) in names:
                Wv[:, names.index(str(nm))] = wz["W"][idx, j_]
        Wv /= np.maximum(Wv.sum(1, keepdims=True), 1e-9)
        tl = np.zeros(len(X))
        print("WEIGHTS", k, "from", meta["weights"])
    skin[k] = (Wv, X, tl)
bpy.data.objects.remove(src)

# pass B (D12): cloth chains around the hips for hanging pieces; front chains follow the thighs at
# runtime (FOLLOW), back chains hang. Joints = sector centroids of the loose verts at 4 heights.
hips_h = np.array(rig.matrix_world @ rig.data.bones["Hips"].head_local)
chains = []
bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode="EDIT")
inv = rig.matrix_world.inverted()
for k, (Wv, X, tl) in skin.items():
    sel = tl > 0.3
    if sel.sum() < 200:
        continue
    P = X[sel]
    z_top, z_bot = np.percentile(P[:, 2], [97, 2])
    az = np.degrees(np.arctan2(P[:, 0] - hips_h[0], -(P[:, 1] - hips_h[1])))
    for tag, a0 in CHAIN_AZ.items():
        da = (az - a0 + 180) % 360 - 180
        sec = np.abs(da) < 30
        if sec.sum() < 60:
            continue
        joints = []
        for j in range(4):
            zj = z_top - (z_top - z_bot) * j / 3
            m_ = sec & (np.abs(P[:, 2] - zj) < 0.03)
            if m_.sum() < 5:
                m_ = sec & (np.abs(P[:, 2] - zj) < 0.08)
            c = P[m_].mean(0) if m_.sum() else P[sec].mean(0)
            r = c[:2] - hips_h[:2]
            c[:2] = hips_h[:2] + r * max(0.0, 1 - 0.01 / max(np.linalg.norm(r), 1e-6))
            c[2] = zj
            joints.append(c)
        bones = []
        for j in range(1, 4):
            eb = rig.data.edit_bones.new(f"Cloth_{k}_{tag}_{j}")
            eb.head, eb.tail = inv @ Vector(joints[j - 1]), inv @ Vector(joints[j])
            eb.parent = rig.data.edit_bones["Hips"] if j == 1 else rig.data.edit_bones[bones[-1]]
            eb.use_connect = j > 1
            bones.append(eb.name)
        side = "Left" if a0 > 0 else "Right"
        chains.append({"piece": k, "tag": tag, "az": a0, "bones": bones, "z": [float(z_top), float(z_bot)],
                       "thigh": f"{side}UpLeg", "follow": FOLLOW[tag[0]]})
bpy.ops.object.mode_set(mode="OBJECT")
cnames = [b for c in chains for b in c["bones"]]
allnames = names + cnames
print("CHAINS", [(c["piece"], c["tag"]) for c in chains])

# pass C: weights = body weights x (1 - loose) + chain weights x loose; smooth; 4 influences
for k, o in shells.items():
    Wv, X, tl = skin[k]
    Wv = np.concatenate([Wv, np.zeros((len(Wv), len(cnames)))], 1)
    hips = np.zeros(len(allnames))
    hips[allnames.index("Hips")] = 1
    mine = [c for c in chains if c["piece"] == k]
    if mine:
        az = np.degrees(np.arctan2(X[:, 0] - hips_h[0], -(X[:, 1] - hips_h[1])))
        caz = np.array([c["az"] for c in mine])
        dd = np.abs((az[:, None] - caz[None] + 180) % 360 - 180)
        second = np.sort(dd, 1)[:, 1:2] if len(mine) > 1 else np.full((len(X), 1), 180.0)
        wa = np.maximum(0, 1 - dd / np.maximum(second, 1e-6))       # the two nearest chains
        wa /= np.maximum(wa.sum(1, keepdims=True), 1e-9)
        Cw = np.zeros((len(X), len(cnames)))
        for ci, c in enumerate(mine):
            z_top, z_bot = c["z"]
            s_ = np.clip((z_top - X[:, 2]) / max(z_top - z_bot, 1e-6) * 3, 0, 3)
            for j, b in enumerate(c["bones"]):
                wb = np.clip(1 - np.abs(s_ - (j + 0.5)), 0, 1)
                Cw[:, cnames.index(b)] += wa[:, ci] * wb
        has = Cw.sum(1) > 1e-6
        Cw /= np.maximum(Cw.sum(1, keepdims=True), 1e-9)
        loose = np.where(has[:, None], np.concatenate([np.zeros((len(X), len(names))), Cw], 1), hips)
    else:
        loose = np.tile(hips, (len(X), 1))
    Wv = (1 - tl)[:, None] * Wv + tl[:, None] * loose
    # transferred weights are noisy where shell and body shapes differ (boots over webbed feet,
    # breeches at the crotch): neighbouring verts tore apart in the riding pose -> smooth over edges,
    # keep the 4 largest influences, normalise
    ed = np.array([e.vertices[:] for e in o.data.edges])
    deg = np.maximum(np.bincount(ed.ravel(), minlength=len(Wv)), 1)[:, None]
    ws = WEIGHT_SMOOTH
    jf = D / "shells" / f"{k}.json"
    if jf.exists():
        ws = json.loads(jf.read_text(encoding="utf-8")).get("weight_smooth", ws)   # designed garments: more
    for _ in range(ws):
        acc = np.zeros_like(Wv)
        np.add.at(acc, ed[:, 0], Wv[ed[:, 1]])
        np.add.at(acc, ed[:, 1], Wv[ed[:, 0]])
        Wv = 0.5 * Wv + 0.5 * acc / deg
    # vertices split at UV seams (same position, no shared edge) drift apart in the smoothing and the
    # seam opens when posed: give every copy the mean of its group
    _, grp = np.unique(np.round(X, 5), axis=0, return_inverse=True)
    grp = grp.ravel()
    acc = np.zeros((grp.max() + 1, Wv.shape[1]))
    np.add.at(acc, grp, Wv)
    Wv = acc[grp] / np.bincount(grp)[grp][:, None]
    keep = np.argsort(-Wv, 1)[:, :4]
    lim = np.zeros_like(Wv)
    np.put_along_axis(lim, keep, np.take_along_axis(Wv, keep, 1), 1)
    Wv = lim / np.maximum(lim.sum(1, keepdims=True), 1e-9)
    for j, n in enumerate(allnames):
        vg = o.vertex_groups.get(n) or o.vertex_groups.new(name=n)
        vg.remove(list(range(len(o.data.vertices))))
        for i in np.flatnonzero(Wv[:, j] > 1e-4):
            vg.add([int(i)], float(Wv[i, j]), "REPLACE")
    am = o.modifiers.new("arm", "ARMATURE")
    am.object = rig
    # no parenting: skinned meshes stay root nodes in glTF (NODE_SKINNED_MESH_NON_ROOT otherwise)
(D / f"{CHAR}_cloth_chains.json").write_text(json.dumps(
    {"rule": "chain bone j takes, in armature space, slerp(Hips rotation delta, thigh rotation delta, "
             "follow * drape[j]), root first", "drape": DRAPE, "chains": chains}, indent=1))

tris = {k: sum(len(p.vertices) - 2 for p in o.data.polygons) for k, o in {**parts, **shells}.items()}
visible = tris.get("body", 0) + sum(tris[k] for k in shells)
report = {"char": CHAR, "mask_faces": stats, "tris": tris, "tris_dressed_visible": visible}
(D / f"{CHAR}_dress.json").write_text(json.dumps(report, indent=1))
print("DRESS", json.dumps({"tris_dressed_visible": visible, "body_visible": tris.get("body", 0)}))
bpy.ops.wm.save_as_mainfile(filepath=str(D / f"{CHAR}_dressed.blend"))
bpy.ops.object.select_all(action="SELECT")
bpy.context.view_layer.objects.active = rig
out_glb = D / f"{CHAR}_dressed.glb"
bpy.ops.export_scene.gltf(filepath=str(out_glb), export_format="GLB", use_selection=True, export_skins=True,
                          export_tangents=True, export_animations=True, export_animation_mode="NLA_TRACKS",
                          export_yup=True)                      # same settings as make_anims.py (base goose)
from glb_fix_tangents import main as fix_tangents  # noqa: E402
fix_tangents(str(out_glb))

# ---- 4. pose test renders
if POSES_ON:
    poser = Poser(rig)

    def apply_follow():
        """D12 runtime rule (the game implements the same): chain roots blend from the hips' to the
        thigh's armature-space rotation delta."""
        pbs = rig.pose.bones
        hq = (pbs["Hips"].matrix @ rig.data.bones["Hips"].matrix_local.inverted()).to_quaternion()
        for c in chains:
            tq = (pbs[c["thigh"]].matrix @ rig.data.bones[c["thigh"]].matrix_local.inverted()).to_quaternion()
            for j, bn in enumerate(c["bones"]):           # less follow down the chain: the hem drapes
                q = hq.slerp(tq, c["follow"] * DRAPE[j])
                pb = pbs[bn]
                rest = rig.data.bones[bn].matrix_local
                head = pb.matrix.to_translation()
                pb.matrix = Matrix.Translation(head) @ q.to_matrix().to_4x4() @ rest.to_3x3().to_4x4()
                bpy.context.view_layer.update()
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
        apply_follow()
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
