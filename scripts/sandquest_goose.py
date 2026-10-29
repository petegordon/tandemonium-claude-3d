"""SandQuest toy goose (docs/sandquest-assets.md): a small game-ready goose figurine from the delivery rider GLB.

  blender -b --factory-startup --python scripts/sandquest_goose.py -- --goose winston|victoria
      [--budget 8000] [--atlas 1024] [--src <delivery.glb>] [--clips <show_clips.glb>] [--seat Captain|Stoker]

What it does (one Blender run, then pack with glb_anim_pack.py + glb_pack_images.py, see docs/sandquest-assets.md):
  1. imports the delivery goose (skinned, face + riding clips) and the Goose Studio body-clips GLB (armature only);
     drops the layered "__" sub-meshes (everything is worn on a figurine), the stray Icosphere, lining and piping;
  2. turns the bone-parented eye parts into skinned geometry (one vertex group each) so the whole goose is ONE mesh;
  3. splits every object by material, decimates each piece to a tri target solved from --budget (the face, eyes and lids
     keep a gentle ratio; brass details get a small floor; cloth shares the rest by area), joins everything;
  4. smart-UV-projects the joined mesh into one atlas UV layer and bakes every material's base colour into one
     --atlas px image (Cycles, colour pass only) -> ONE material / ONE draw call (+ the alpha-masked hat feather);
  5. copies the Studio body clips onto the delivery rig by bone name (same rest pose), composes Pedal_<seat> with the
     seated upper body of Ride_<seat> (hands on the pedalo bar), keeps idle/blink/look_around/honk, drops pose_* /
     Ride_* / Lean_* / twirl;
  6. exports out/sandquest/<goose>_raw.glb (+Y up, +Z forward, feet on y=0, metres) and <goose>_clips.json
     (durations, loop flags, root motion, rest hip height, Ride-pose grip points for the pedalo bars).
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
GOOSE = arg("--goose", "winston")
PRESET = {"winston": ("goose_captain_fancy", "Captain"), "victoria": ("goose_stoker_victorian", "Stoker")}
base, seat = PRESET[GOOSE]
SRC = Path(arg("--src", str(ROOT / "out" / "delivery" / f"{base}.glb")))
CLIPS = Path(arg("--clips", str(ROOT / "out" / "show" / f"{base}_clips.glb")))
SEAT = arg("--seat", seat)
BUDGET = arg("--budget", 8000)
ATLAS = arg("--atlas", 1024)
UV_MODE = arg("--uv", "smart")                       # smart: smart-UV-project (the garments' own UVs are per-face); orig: repack them
UV_ANGLE = arg("--angle", 89.0)                      # smart-project angle limit: big islands = few split vertices
OUT = ROOT / "out" / "sandquest"
OUT.mkdir(parents=True, exist_ok=True)

KEEP_FACE = ["idle", "blink", "look_around", "honk"]
KEEP_BODY = ["idle_shift", "walk_start", "walk", "walk_stop", "turn_L90", "turn_R90", "hat_tip", "curtsy", "bow",
             "wave", "admire", "celebrate", "flap_startle"]
UPPER = ["Spine", "Spine1", "Spine2", "Neck", "Neck1", "Neck2", "Neck3", "Head", "LeftShoulder", "LeftArm",
         "LeftForeArm", "LeftHand", "RightShoulder", "RightArm", "RightForeArm", "RightHand"]
DROP_MATS = ("lining", "piping")                      # invisible at toy scale, thousands of tris
# eyes (tandemonium-claude-3d #41): the eyeball keeps every front face (its hidden back half is cut instead) and the
# lids stay round; at 0.3 the almond opening went polygonal and the iris smeared, which shows on full-size geese
FACE_RATIO = {"body": 0.6, "eyeball": 1.0, "lid": 0.75, "catchlight": 1.0}
SOCKET_R = 0.045                                      # head skin within this of an eye centre is not decimated (m)
EYE_PATCH = 0.19                                      # eyeball's own square atlas patch (top of the right strip)
DETAIL_WORDS = ("brass", "stud", "rim", "tab", "band", "gold", "wing", "buckle", "button")
DETAIL_FLOOR = 60
FEATHER_RATIO = 0.15

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene

# ---- 1. import ----------------------------------------------------------------------------------------------------
bpy.ops.import_scene.gltf(filepath=str(SRC))
rig = [o for o in bpy.data.objects if o.type == "ARMATURE"][0]
rig.name = "goose_rig"
ad = rig.animation_data
for t in ad.nla_tracks:
    t.mute = True
ad.action = None
sc.frame_set(0)
bpy.context.view_layer.update()
assert all(abs(v) < 1e-6 for row in (rig.matrix_world - rig.matrix_world.Identity(4)) for v in row), "rig not at origin"


def tris(o):
    o.data.calc_loop_triangles()
    return len(o.data.loop_triangles)


def delete(objs):
    for o in list(objs):
        me = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if isinstance(me, bpy.types.Mesh) and me.users == 0:
            bpy.data.meshes.remove(me)


# the coat's COLOR_n layers are all-white masks for the game's colourway shader; the importer multiplies them into
# the base colour through a Color Attribute node, which reads black once the pieces are joined -> cut them out
for mat in bpy.data.materials:
    if not mat.use_nodes:
        continue
    nt = mat.node_tree
    for n in [n for n in nt.nodes if n.type == "VERTEX_COLOR"]:
        for l in list(n.outputs[0].links):
            l.to_socket.default_value = (1, 1, 1, 1)
            nt.links.remove(l)
        nt.nodes.remove(n)
for o in [o for o in bpy.data.objects if o.type == "MESH"]:
    for ca in list(o.data.color_attributes):
        o.data.color_attributes.remove(ca)
strays = [o for o in bpy.data.objects if o.type == "MESH" and (o.parent is not rig or "__" in o.name)]
print("DROP objects", [o.name for o in strays])
delete(strays)

# ---- 2. eye parts: bone-parented objects -> skinned (vertex group = parent bone) -------------------------------------
for o in [o for o in bpy.data.objects if o.type == "MESH" and o.parent_type == "BONE"]:
    bone = o.parent_bone
    mw = o.matrix_world.copy()
    o.parent = None
    o.matrix_world = mw
    o.data.transform(mw)                                   # rig is at the origin: world == armature space
    o.matrix_world = mw.Identity(4)
    o.parent = rig
    vg = o.vertex_groups.new(name=bone)
    vg.add(list(range(len(o.data.vertices))), 1.0, "REPLACE")
    o.modifiers.new("Armature", "ARMATURE").object = rig

for o in [o for o in bpy.data.objects if o.type == "MESH"]:
    if not o.data.uv_layers:
        o.data.uv_layers.new(name="UVMap")

# ---- 3. split by material, drop junk, decimate per piece -------------------------------------------------------------
bpy.ops.object.select_all(action="DESELECT")
for o in [o for o in bpy.data.objects if o.type == "MESH"]:
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.quads_convert_to_tris(quad_method="BEAUTY", ngon_method="BEAUTY")
# the beak split keeps upper and lower lip vertices on the same spot on purpose: welding them glues the mouth shut
# (no honk), so the weld below skips every vertex weighted to Jaw / Tongue
bpy.ops.object.mode_set(mode="OBJECT")
for o in [o for o in bpy.data.objects if o.type == "MESH"]:
    mouth = {o.vertex_groups[n].index for n in ("Jaw", "Tongue") if n in o.vertex_groups}
    me_ = o.data
    for v in me_.vertices:
        v.select = not any(g.group in mouth and g.weight > 0 for g in v.groups)
    for e in me_.edges:                                 # edges / faces too, or edit mode re-selects the mouth
        e.select = all(me_.vertices[i].select for i in e.vertices)
    for p in me_.polygons:
        p.select = all(me_.vertices[i].select for i in p.vertices)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.remove_doubles(threshold=0.0003)           # the garment builders leave split vertices: welded, the
bpy.ops.mesh.select_all(action="SELECT")                # decimator can collapse across them and the GLB is small
bpy.ops.mesh.separate(type="MATERIAL")
bpy.ops.object.mode_set(mode="OBJECT")
pieces = [o for o in bpy.data.objects if o.type == "MESH"]
nomat = [o for o in pieces if not o.data.materials or o.data.materials[0] is None]
print("DROP no-material pieces", [(o.name, tris(o)) for o in nomat])
delete(nomat)
pieces = [o for o in bpy.data.objects if o.type == "MESH"]
junk = [o for o in pieces if any(w in o.data.materials[0].name.lower() for w in DROP_MATS)]
print("DROP materials", [(o.name, o.data.materials[0].name) for o in junk])
delete(junk)
pieces = [o for o in bpy.data.objects if o.type == "MESH"]


def piece_class(o):
    n, m = o.name.lower(), o.data.materials[0].name.lower()
    for k, r in FACE_RATIO.items():
        if n.startswith(k):
            return "face", r
    if "feather" in m:
        return "feather", FEATHER_RATIO
    if any(w in m for w in DETAIL_WORDS):
        return "detail", None
    return "cloth", None


targets, cloth = {}, []
for o in pieces:
    n = tris(o)
    cls, r = piece_class(o)
    if o.name.startswith("eyeball"):                    # the eye profile is a planar UV along the look axis; the
        uvd_ = o.data.uv_layers[0].data                 # hidden back half all sits on (0.01, 0.01): cut it
        back = [p for p in o.data.polygons
                if any(abs(uvd_[li].uv.x - 0.01) < 1e-4 and abs(uvd_[li].uv.y - 0.01) < 1e-4 for li in p.loop_indices)]
        import bmesh
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.faces.ensure_lookup_table()
        bmesh.ops.delete(bm, geom=[bm.faces[p.index] for p in back], context="FACES")
        bm.to_mesh(o.data)
        bm.free()
        n = tris(o)
    if cls in ("face", "feather"):
        targets[o.name] = max(8, round(n * r))
    elif cls == "detail":
        targets[o.name] = min(n, DETAIL_FLOOR)
    else:
        cloth.append(o)
budget = int(BUDGET * 0.97) - sum(targets.values())
w = {o.name: tris(o) ** 0.6 for o in cloth}
for o in cloth:
    targets[o.name] = max(12, round(budget * w[o.name] / sum(w.values())))
print("TARGETS", {k: (tris(bpy.data.objects[k]), v) for k, v in targets.items()})


EYE_CENTRES = [sum((v.co for v in o.data.vertices), Vector()) / max(1, len(o.data.vertices))
               for o in pieces if o.name.startswith("eyeball")]


def socket_guard(o):
    """Vertex group "dec_ok": 0 round the eye sockets, 1 elsewhere, so the socket rim keeps its almond shape."""
    if not EYE_CENTRES or not o.name.startswith("body"):
        return None
    vg = o.vertex_groups.get("dec_ok") or o.vertex_groups.new(name="dec_ok")
    for v in o.data.vertices:
        d = min((v.co - c).length for c in EYE_CENTRES)
        vg.add([v.index], min(1.0, max(0.0, (d - SOCKET_R) / SOCKET_R)), "REPLACE")
    return vg.name


def decimate(o, target):
    n = tris(o)
    if target >= n:
        return
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    m = o.modifiers.new("dec", "DECIMATE")
    m.decimate_type = "COLLAPSE"
    m.ratio = max(0.02, target / n)
    m.use_collapse_triangulate = True
    guard = socket_guard(o)
    if guard:
        m.vertex_group = guard
        m.vertex_group_factor = 1000.0
    bpy.ops.object.modifier_move_to_index(modifier="dec", index=0)
    bpy.ops.object.modifier_apply(modifier="dec")
    if guard:                                           # not a bone: keep it out of the skin
        o.vertex_groups.remove(o.vertex_groups[guard])


for o in pieces:
    decimate(o, targets[o.name])
total = sum(tris(o) for o in pieces)
print("DECIMATED total", total, "verts", sum(len(o.data.vertices) for o in pieces))
if total > BUDGET:                                      # second pass on the cloth only
    over = total - int(BUDGET * 0.97)
    ct = sum(tris(o) for o in cloth)
    for o in cloth:
        decimate(o, tris(o) - round(over * tris(o) / ct))
    total = sum(tris(o) for o in pieces)
    print("DECIMATED pass 2 total", total)

# ---- 4. join -> atlas UV -> bake base colour --------------------------------------------------------------------------
feather = [o for o in pieces if piece_class(o)[0] == "feather"]
main_pieces = [o for o in pieces if o not in feather]
bpy.ops.object.select_all(action="DESELECT")
for o in main_pieces:
    o.select_set(True)
bpy.context.view_layer.objects.active = main_pieces[0]
bpy.ops.object.join()
goose = bpy.context.view_layer.objects.active
goose.name = goose.data.name = "goose"
bpy.ops.object.mode_set(mode="EDIT")                   # decimation leaves loose vertices; smooth shading so only
bpy.ops.mesh.select_all(action="SELECT")               # UV seams split vertices in the glTF
bpy.ops.mesh.delete_loose()
bpy.ops.mesh.mark_sharp(clear=True)
bpy.ops.object.mode_set(mode="OBJECT")
bpy.ops.mesh.customdata_custom_splitnormals_clear()    # imported custom normals would split every vertex
bpy.ops.object.shade_smooth()
for o in (goose, *feather):
    o.modifiers.clear()
    o.modifiers.new("Armature", "ARMATURE").object = rig
    o.parent = rig
if feather:
    bpy.ops.object.select_all(action="DESELECT")
    for o in feather:
        o.select_set(True)
    bpy.context.view_layer.objects.active = feather[0]
    bpy.ops.object.join()
    feather = bpy.context.view_layer.objects.active
    feather.name = feather.data.name = "feather"
else:
    feather = None

me = goose.data
me.uv_layers["UVMap"].active_render = True            # the materials sample their own textures through this one
atlas_uv = me.uv_layers.new(name="atlas", do_init=True)  # starts as a copy of the garments' own islands
atlas_uv.active = True


def is_solid(mat):
    return mat.use_nodes and not any(n.type == "TEX_IMAGE" and n.image is not None for n in mat.node_tree.nodes)


solid = [i for i, sl in enumerate(goose.material_slots) if is_solid(sl.material)]
print("SOLID materials", [goose.material_slots[i].material.name for i in solid])
# textured faces: smart-projected and packed by Blender into [0,1]; squeezed into the left 79 % of the atlas.
# Solid-colour faces: every face of a material maps onto one flat patch in the right-hand strip -> no UV seams on
# the brass, lids, hat, boots ... (vertex splits in the glTF come from UV seams) and patches big enough for mipmaps.
eye_mats = [i for i, sl in enumerate(goose.material_slots) if sl.material.name.startswith("goose_eye")]
for pg in me.polygons:
    pg.select = pg.material_index not in solid and pg.material_index not in eye_mats
bpy.ops.object.select_all(action="DESELECT")
goose.select_set(True)
bpy.context.view_layer.objects.active = goose
bpy.ops.object.mode_set(mode="EDIT")
if UV_MODE == "smart":
    bpy.ops.uv.smart_project(angle_limit=math.radians(UV_ANGLE), island_margin=0.004, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=True)
else:
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin=0.003)
bpy.ops.object.mode_set(mode="OBJECT")
uvd = me.uv_layers["atlas"].data
src_uv = me.uv_layers["UVMap"].data
STRIP = 0.79
SOLID_H = 1.0 - EYE_PATCH - 0.02 if eye_mats else 1.0   # solid patches below, the eyeball patch above
rows = max(1, math.ceil(len(solid) / 2))
for pg in me.polygons:
    if pg.material_index in eye_mats:                    # both eyeballs share one patch: same profile texture
        for li in pg.loop_indices:
            u, v = src_uv[li].uv
            uvd[li].uv = (STRIP + 0.01 + u * EYE_PATCH, SOLID_H + 0.01 + v * EYE_PATCH)
    elif pg.material_index in solid:
        k = solid.index(pg.material_index)
        col, row = k % 2, k // 2
        x0, y0 = STRIP + 0.01 + col * (1 - STRIP - 0.02) / 2, row / rows * SOLID_H
        w, h = (1 - STRIP - 0.02) / 2 - 0.01, SOLID_H / rows - 0.01
        corners = [(x0, y0), (x0 + w, y0), (x0, y0 + h), (x0 + w, y0 + h)]
        for j, li in enumerate(pg.loop_indices):
            uvd[li].uv = corners[j % 4]
    else:
        for li in pg.loop_indices:
            uvd[li].uv.x *= STRIP

img = bpy.data.images.new("goose_atlas", ATLAS, ATLAS)
img.generated_color = (0.5, 0.5, 0.5, 1)
for slot in goose.material_slots:
    mat = slot.material
    mat.use_nodes = True
    nt = mat.node_tree
    if "catchlight" in mat.name:                        # emissive white dot: bake it as plain white
        for n in nt.nodes:
            if n.type == "BSDF_PRINCIPLED":
                n.inputs["Base Color"].default_value = (1, 1, 1, 1)
                for l in list(n.inputs["Base Color"].links):
                    nt.links.remove(l)
    node = nt.nodes.new("ShaderNodeTexImage")
    node.image = img
    node.select = True
    nt.nodes.active = node
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 4
sc.render.bake.use_pass_direct = sc.render.bake.use_pass_indirect = False
sc.render.bake.use_pass_color = True
sc.render.bake.margin = 6
bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, use_clear=True, margin=6)
img.filepath_raw = str(OUT / f"{GOOSE}_atlas.png")
img.file_format = "PNG"
img.save()
img.pack()
print("BAKED atlas", img.size[:])

# one material, one UV layer, no colour layers (the coat's COLOR_n feed its material, so only after the bake)
for ca in list(me.color_attributes):
    me.color_attributes.remove(ca)
me.uv_layers.remove(me.uv_layers["UVMap"])
me.uv_layers["atlas"].name = "UVMap"
gmat = bpy.data.materials.new("goose_toy")
gmat.use_nodes = True
nt = gmat.node_tree
bsdf = nt.nodes["Principled BSDF"]
bsdf.inputs["Roughness"].default_value = 0.7
bsdf.inputs["Metallic"].default_value = 0.0
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = img
nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
me.materials.clear()
me.materials.append(gmat)
for p in me.polygons:
    p.material_index = 0
if feather is not None:
    fm = feather.data.materials[0]
    fm.name = "goose_feather"
    for n in fm.node_tree.nodes:                        # the alpha card reads at toy scale from a 64 px strip
        if n.type == "TEX_IMAGE" and n.image is not None and max(n.image.size) > 160:
            n.image.scale(64, 128)
            n.image.pack()
    for ca in list(feather.data.color_attributes):
        feather.data.color_attributes.remove(ca)
me.validate(verbose=False)

# ---- 5. clips ----------------------------------------------------------------------------------------------------
bpy.ops.import_scene.gltf(filepath=str(CLIPS))
rig2 = [o for o in bpy.data.objects if o.type == "ARMATURE" and o is not rig][0]
assert len(rig2.data.bones) == len(rig.data.bones), "clips rig differs"
for b in rig.data.bones:
    d = rig2.data.bones[b.name].matrix_local - b.matrix_local
    assert max(abs(v) for row in d for v in row) < 1e-5, f"rest pose differs on {b.name}"
for o in [o for o in bpy.data.objects if o.type == "MESH" and o.parent is rig2]:
    delete([o])
body_actions = {n: bpy.data.actions[n] for n in KEEP_BODY if n in bpy.data.actions}
delete([rig2])
for t in list(ad.nla_tracks):
    ad.nla_tracks.remove(t)

# Pedal_<seat>: legs/hips/cloth from the riding clip + the seated upper body (hands on the bar) from Ride_<seat>
ride, pedal = bpy.data.actions["Ride_" + SEAT], bpy.data.actions["Pedal_" + SEAT]
pbs = rig.pose.bones
FPS_SRC = 24                                              # the delivery clips are 24 fps samples


def use(action):
    ad.action = action
    ad.action_slot = action.slots[0]


use(ride)
sc.frame_set(1)
upper = {b: pbs[b].matrix_basis.copy() for b in UPPER}
bpy.context.view_layer.update()
grip = {}
for side in ("Left", "Right"):
    h, t = pbs[side + "Hand"].head, pbs[side + "Hand"].tail
    grip[side] = (h + (t - h) * 0.55)
feet_ride = {s: pbs[s + "Foot"].head.copy() for s in ("Left", "Right")}
use(pedal)
n_pedal = int(round(FPS_SRC * 1.0))                      # one crank turn = 1.0 s: frames 1..24, frame 25 = frame 1
frames = []
for f in range(1, n_pedal + 1):
    sc.frame_set(f)
    pose = {b.name: b.matrix_basis.copy() for b in pbs}
    pose.update(upper)
    frames.append(pose)
frames.append(frames[0])                                  # seamless loop closure
sc.frame_set(1)
feet_pedal = {s: pbs[s + "Foot"].head.copy() for s in ("Left", "Right")}
merged = bpy.data.actions.new("Pedal_" + SEAT + "_toy")
ad.action = merged
for f, pose in enumerate(frames):
    for b, m in pose.items():
        pb = pbs[b]
        pb.matrix_basis = m
        pb.keyframe_insert("rotation_quaternion", frame=f + 1, group=b)
        pb.keyframe_insert("location", frame=f + 1, group=b)
ad.action = None
for pb in pbs:
    pb.matrix_basis = pb.matrix_basis.Identity(4)
bpy.data.actions.remove(pedal)
merged.name = "Pedal_" + SEAT
merged.use_fake_user = True

meta_clips = {}
clips_json = json.loads(CLIPS.with_suffix(".json").read_text(encoding="utf-8"))
fps = clips_json.get("fps", 24)


def add_track(name, act):
    tr = ad.nla_tracks.new()
    tr.name = name
    st = tr.strips.new(name, 1, act)
    try:
        st.action_slot = act.slots[0]
    except Exception as e:                              # noqa: BLE001
        print("slot", name, e)
    st.extrapolation = "NOTHING"
    tr.mute = True
    return st


for name in KEEP_FACE:
    st = add_track(name, bpy.data.actions[name])
    meta_clips[name] = {"duration": round((st.frame_end - st.frame_start) / fps, 3), "loop": name == "idle",
                        "layer": "face"}
st = add_track("Pedal_" + SEAT, merged)
meta_clips["Pedal_" + SEAT] = {"duration": round(n_pedal / fps, 3), "loop": True, "layer": "ride",
                               "note": "time = crank angle / 2pi; plays the paddle wheel 'Paddle' clip at the same rate"}
for name in KEEP_BODY:
    if name not in body_actions:
        print("MISSING body clip", name)
        continue
    add_track(name, body_actions[name])
    info = dict(clips_json["clips"][name])
    info.pop("frames", None)
    info.pop("max_reach", None)
    info["layer"] = "body"
    meta_clips[name] = info
for a in list(bpy.data.actions):
    if a.name not in meta_clips:
        bpy.data.actions.remove(a)
sc.frame_start, sc.frame_end = 1, 2
sc.render.fps = fps

# ---- 6. export ---------------------------------------------------------------------------------------------------
sc.frame_set(1)
bpy.ops.object.select_all(action="DESELECT")
for o in (rig, goose, *( [feather] if feather else [])):
    o.select_set(True)
bpy.context.view_layer.objects.active = rig
out_glb = OUT / f"{GOOSE}_raw.glb"
bpy.ops.export_scene.gltf(filepath=str(out_glb), export_format="GLB", use_selection=True, export_skins=True,
                          export_tangents=False, export_animations=True, export_animation_mode="NLA_TRACKS",
                          export_optimize_animation_size=True, export_optimize_animation_keep_anim_armature=True,
                          export_yup=True, export_image_format="AUTO", export_morph=False,
                          export_anim_slide_to_zero=True)
print("EXPORT verts", len(me.vertices), "polys", len(me.polygons))
hb = rig.data.bones
hip_mid = (hb["LeftUpLeg"].head_local + hb["RightUpLeg"].head_local) / 2


def yup(v):
    return [round(v.x, 4), round(v.z, 4), round(-v.y, 4)]


meta = {"goose": GOOSE, "source": SRC.name, "clips_source": CLIPS.name, "seat": SEAT, "fps": fps,
        "units": "metres (real-world; the game scales the figurine)", "up": "+Y", "forward": "+Z",
        "root_bone": "Hips", "hip_mid_rest": yup(hip_mid), "hips_rest": yup(hb["Hips"].head_local),
        "hip_up_above_saddle": 0.11,
        "ride_grip": {k: yup(v) for k, v in grip.items()},
        "ride_feet": {k: yup(v) for k, v in feet_ride.items()},
        "pedal_feet_frame0": {k: yup(v) for k, v in feet_pedal.items()},
        "tris_after_decimate": total, "clips": meta_clips}
(OUT / f"{GOOSE}_clips.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
print("SANDQUEST", out_glb, "tris", total, "clips", list(meta_clips))
