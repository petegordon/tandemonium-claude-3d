"""Preview the Penny-Farthing with two in-game geese pedalling (Pedal_PF legs + their Ride_<seat> upper body).

  blender -b --factory-startup --python scripts/pf_preview.py -- <bike.glb> <captain.glb> <captain_pf.glb> \
      <stoker.glb> <stoker_pf.glb> <out_prefix> [--frames 12] [--view side|q34]

Seats each goose the way the game does (goose-riders.js _seat: hips on the Seat_<seat> socket), plays Ride_<seat> on
the upper body and Pedal_PF on the legs (the stoker's reversed: she faces backwards and the bike rolls the captain's
way), and turns the bike's wheels / cranks by world X to the same crank angle. Writes <out_prefix>_NN.png per frame.
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Euler, Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
BIKE, CAP, CAP_PF, STO, STO_PF, OUTP = argv[:6]
NF = int(argv[argv.index("--frames") + 1]) if "--frames" in argv else 12
VIEW = argv[argv.index("--view") + 1] if "--view" in argv else "side"
NCLIP = 24

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene


def imp(path):
    before = set(bpy.data.objects)
    acts = set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=str(path))
    return [o for o in bpy.data.objects if o not in before], [a for a in bpy.data.actions if a not in acts]


bike_objs, _ = imp(BIKE)
B = {o.name: o for o in bike_objs}
for o in bike_objs:                                    # the bike's own Ride clip: we drive it by hand
    if o.animation_data:
        o.animation_data.action = None
        for t in list(o.animation_data.nla_tracks):
            o.animation_data.nla_tracks.remove(t)
bpy.context.view_layer.update()
spin_nodes = ["Wheel_F", "Wheel_R", "Crank_F", "Crank_R", "Wheel_SF", "Wheel_SR"]
rest = {n: B[n].matrix_world.copy() for n in spin_nodes if n in B}
info = __import__("json").loads((Path(BIKE).with_name("pf_tandem_info.json")).read_text()) \
    if Path(BIKE).with_name("pf_tandem_info.json").exists() else {}
small_ratio = info.get("big_wheel_diameter_m", 1.0) / info.get("small_wheel_diameter_m", 1.0)


def seat_goose(glb, pf_glb, seat):
    objs, acts = imp(glb)
    rig = next(o for o in objs if o.type == "ARMATURE")
    for o in objs:
        if o.type == "MESH" and "__" in o.name:
            o.hide_render = True
    pf_objs, pf_acts = imp(pf_glb)
    pedal = next(a for a in pf_acts if a.name.startswith("Pedal_PF"))
    for o in pf_objs:
        bpy.data.objects.remove(o)
    # the game cuts Pedal_* clips to the legs + cloth chains (goose-rider-clips.js boneFilterFor / LOWER_RE)
    import re
    lower = re.compile(r'^(Left|Right)(UpLeg|Leg|Foot|ToeBase)$|^Cloth_')
    try:
        bags = [cb for l in pedal.layers for s in l.strips for cb in s.channelbags]
    except AttributeError:
        bags = [pedal]
    for cb in bags:
        for fc in list(cb.fcurves):
            bn = fc.data_path.split('"')[1] if '"' in fc.data_path else ""
            if not lower.match(bn):
                cb.fcurves.remove(fc)
    ride = next(a for a in bpy.data.actions if a.name.startswith(f"Ride_{seat}") and a in acts)
    roots = [o for o in objs if o.parent is None]
    sock = B["Seat_" + seat]
    bpy.context.view_layer.update()
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    hip = (rig.matrix_world @ rig.pose.bones["LeftUpLeg"].head + rig.matrix_world @ rig.pose.bones["RightUpLeg"].head) / 2
    for o in roots:
        rel = o.matrix_world.copy()
        rel.translation -= hip                          # hips onto the socket (seatOffset, HIP_UP 0)
        o.parent = sock
        o.matrix_parent_inverse = Matrix.Identity(4)
        o.matrix_basis = rel
    ad = rig.animation_data or rig.animation_data_create()
    ad.action = None
    for t in list(ad.nla_tracks):
        ad.nla_tracks.remove(t)
    for act, rev in ((ride, False), (pedal, seat == "Stoker")):
        tr = ad.nla_tracks.new()
        tr.name = act.name
        st = tr.strips.new(act.name, 0, act)
        try:
            st.action_slot = act.slots[0]
        except Exception:                              # noqa: BLE001
            pass
        st.extrapolation = "HOLD"
        st.blend_type = "REPLACE"
        if act is pedal:
            st.use_reverse = rev
            st.frame_end = st.frame_start + NCLIP
    return rig


seat_goose(CAP, CAP_PF, "Captain")
seat_goose(STO, STO_PF, "Stoker")

bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
gm = bpy.data.materials.new("ground")
gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.45, 0.42, 0.36, 1)
bpy.context.active_object.data.materials.append(gm)
sc.render.engine = "BLENDER_EEVEE"
sc.render.resolution_x, sc.render.resolution_y = 1000, 640
sc.world = bpy.data.worlds.new("w")
sc.world.use_nodes = True
sc.world.node_tree.nodes["Background"].inputs[0].default_value = (0.70, 0.74, 0.80, 1)
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.5
sun.rotation_euler = Euler((math.radians(45), math.radians(10), math.radians(-35)))
sc.collection.objects.link(sun)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.lens = 50
target = Vector((0, 0, 0.95))
loc = Vector((-7.5, 0, 1.0)) if VIEW == "side" else Vector((-4.6, -5.0, 2.0))
cam.location = loc
cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
Path(OUTP).parent.mkdir(parents=True, exist_ok=True)
for i in range(NF):
    f = NCLIP * i / NF
    sc.frame_set(int(round(f)))
    ang = 2 * math.pi * round(f) / NCLIP
    for n, m in rest.items():
        k = small_ratio if n.startswith("Wheel_S") else 1.0
        l_, r_, _ = m.decompose()
        B[n].matrix_world = Matrix.Translation(l_) @ Matrix.Rotation(ang * k, 4, "X") @ r_.to_matrix().to_4x4()
    bpy.context.view_layer.update()
    sc.render.filepath = f"{OUTP}_{i:02d}.png"
    bpy.ops.render.render(write_still=True)
print("PREVIEW", OUTP, NF)
