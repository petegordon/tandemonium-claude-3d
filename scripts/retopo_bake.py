"""Phase 4: build the game mesh (one mesh, <= --tris triangles) and bake from the hi-poly.

  blender -b --factory-startup --python scripts/retopo_bake.py -- [--char male] \
      [--tris 20000] [--voxel 0.004] [--tex 2048] [--stage all|retopo|bake] \
      [--extrusion 0.04] [--ray-dist 0.1] [--remesher decimate|instant] \
      [--reserve-rows 16] [--reserve-tris 500]

retopo: copy hi -> voxel remesh (watertight, fuses gloves/buttons) -> QEM decimate to
        tris - reserve (or --remesher instant: Instant Meshes quads; fuses layered cloth,
        see PLAN M5) -> smooth shading -> Smart UV + pack, top atlas rows reserved.
bake:   Cycles selected-to-active hi -> game: base colour (diffuse colour only),
        tangent normal, roughness, metallic (via emission), AO. Packs glTF ORM
        (R=AO, G=roughness, B=metallic) and exports <char>_goose_game.glb.
Everything lands in out/<char>-goose/<char>_goose.blend (collections Hi, Game).
"""
import json
import sys
import time
from pathlib import Path

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def opt(name, default, cast=str):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


CHAR = opt("--char", "male")
TRIS = opt("--tris", 20000, int)
VOXEL = opt("--voxel", 0.004, float)
TEX = opt("--tex", 2048, int)
STAGE = opt("--stage", "all")
EXTRUSION = opt("--extrusion", 0.04, float)   # bake cage extrusion (m); 0.01 left ray-miss smudges (M4)
RAY_DIST = opt("--ray-dist", 0.1, float)      # bake max ray distance (m)
RESERVE_ROWS = opt("--reserve-rows", 16, int)  # top atlas rows kept free (eyes plugin strip)
RESERVE_TRIS = opt("--reserve-tris", 500, int) # tri budget kept for meshes added by game fixes (eyes)
REMESHER = opt("--remesher", "decimate")      # decimate | instant (M5: IM fuses coat skirt+tail, see PLAN)
IM_EXE = Path(__file__).resolve().parents[1] / "tools" / "instant-meshes" / "Instant Meshes.exe"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out" / f"{CHAR}-goose"
BLEND = OUT / f"{CHAR}_goose.blend"
TEXDIR = OUT / "textures"


def log(*a):
    print("[retopo_bake]", *a, flush=True)


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def collection(name):
    col = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if col.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(col)
    return col


def only_select(*obs):
    bpy.ops.object.select_all(action="DESELECT")
    for o in obs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = obs[-1]


def retopo(hi):
    old = bpy.data.objects.get(f"{CHAR}_goose_game")
    if old:
        for child in old.children_recursive:              # attached parts (eyes) from a previous run
            bpy.data.objects.remove(child)
        bpy.data.objects.remove(old)
    game = hi.copy()
    game.data = hi.data.copy()
    game.name = game.data.name = f"{CHAR}_goose_game"
    for c in game.users_collection:
        c.objects.unlink(game)
    collection("Game").objects.link(game)
    game.data.materials.clear()
    for uv in list(game.data.uv_layers):
        game.data.uv_layers.remove(uv)
    only_select(game)

    t = time.time()
    bpy.ops.mesh.customdata_custom_splitnormals_clear()
    game.data.remesh_voxel_size = VOXEL
    game.data.use_remesh_fix_poles = True
    bpy.ops.object.voxel_remesh()
    log(f"voxel remesh {VOXEL*1000:.1f} mm -> {len(game.data.polygons)} faces ({time.time()-t:.0f}s)")
    log(f"dropped {drop_small_islands(game)} speck verts")

    # Quad remesh. Quadriflow refuses/fails on these meshes in 5.2, so the default is
    # Instant Meshes (tools/instant-meshes, wjakob) on the watertight voxel mesh -> pure quads
    # with edge loops for skinning (M5). "decimate" = adaptive QEM triangles (v1 behaviour).
    t = time.time()
    if REMESHER == "instant":
        instant_meshes(game, (TRIS - RESERVE_TRIS) // 2)
        log(f"instant meshes -> {len(game.data.polygons)} faces / {tri_count(game)} tris ({time.time()-t:.0f}s)")
    else:
        try:
            bpy.ops.object.quadriflow_remesh(mode="FACES", target_faces=TRIS // 2, use_mesh_symmetry=False,
                                             use_preserve_sharp=True, use_preserve_boundary=True, seed=0)
        except RuntimeError as e:
            log("quadriflow failed:", e)
        log(f"quadriflow -> {len(game.data.polygons)} faces / {tri_count(game)} tris ({time.time()-t:.0f}s)")
    if tri_count(game) > TRIS:
        m = game.modifiers.new("dec", "DECIMATE")
        m.ratio = (TRIS - RESERVE_TRIS) / tri_count(game) * 0.98
        bpy.ops.object.modifier_apply(modifier=m.name)
        log(f"decimate trim -> {tri_count(game)} tris")
    # Decimation leaves a few zero-area slivers whose normals/tangents are zero-length
    # (glTF validator: ACCESSOR_VECTOR3_NON_UNIT). Dissolve them.
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(game.data)
    n0 = len(bm.faces)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-5, edges=bm.edges)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_area() < 1e-10], context="FACES")
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    bm.to_mesh(game.data)
    bm.free()
    log(f"degenerate cleanup removed {n0 - len(game.data.polygons)} faces")
    bpy.ops.object.shade_smooth()

    t = time.time()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.003, area_weight=0.0)
    bpy.ops.uv.pack_islands(margin=0.003, rotate=True)
    bpy.ops.object.mode_set(mode="OBJECT")
    # keep the top RESERVE_ROWS texel rows free for 1-D strips written by game fixes (eyes)
    uv = np.empty(len(game.data.loops) * 2, np.float32)
    game.data.uv_layers.active.data.foreach_get("uv", uv)
    uv[1::2] *= 1.0 - (RESERVE_ROWS + 2) / TEX
    game.data.uv_layers.active.data.foreach_set("uv", uv)
    game["uv_reserved_rows"] = RESERVE_ROWS
    log(f"UV unwrap ({time.time()-t:.0f}s)")
    return game


def instant_meshes(ob, quads):
    """Replace ob's mesh with an Instant Meshes pure-quad remesh of ~quads faces."""
    import subprocess
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="im_"))
    src, dst = tmp / "in.obj", tmp / "out.obj"
    only_select(ob)
    bpy.ops.wm.obj_export(filepath=str(src), export_selected_objects=True, export_uv=False,
                          export_normals=False, export_materials=False, apply_modifiers=True,
                          forward_axis="Y", up_axis="Z")
    # -d deterministic, rosy/posy 4 = quads. Pure-quad mode subdivides its quad-dominant
    # result, so the output is ~3.5x -f; calibrate from each run and retry (max 4 runs).
    f = quads / 3.6
    for attempt in range(4):
        dst.unlink(missing_ok=True)
        cmd = [str(IM_EXE), str(src), "-o", str(dst), "-f", str(int(f)), "-d", "-r", "4", "-p", "4"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if not dst.exists():
            raise RuntimeError(f"Instant Meshes failed ({r.returncode}): {r.stdout[-500:]} {r.stderr[-500:]}")
        n = sum(1 for line in dst.open() if line.startswith("f "))
        log(f"instant meshes -f {int(f)} -> {n} faces (want <= {quads})")
        if 0.93 * quads <= n <= quads:
            break
        f *= 0.965 * quads / n
    bpy.ops.wm.obj_import(filepath=str(dst), forward_axis="Y", up_axis="Z")
    new = bpy.context.selected_objects[0]
    old_me = ob.data
    ob.data = new.data
    ob.data.name = ob.name
    bpy.data.objects.remove(new)
    bpy.data.meshes.remove(old_me)
    only_select(ob)
    # IM writes its own vertex normals; imported as custom normals they steer the bake rays.
    # Its pure-quad output also has inconsistent winding (~half the faces flipped) and small
    # cracks, which made the bake sample the wrong surfaces. Drop the normals, close holes,
    # and make the winding consistent / outward per connected piece.
    bpy.ops.mesh.customdata_custom_splitnormals_clear()
    for a in ("sharp_edge", "sharp_face"):
        if a in ob.data.attributes:
            ob.data.attributes.remove(ob.data.attributes[a])
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    filled = bmesh.ops.holes_fill(bm, edges=bm.edges, sides=8)["faces"]
    bmesh.ops.triangulate(bm, faces=[f for f in filled if len(f.verts) > 4])
    bm.faces.index_update()
    # Consistent winding, then flip any connected piece whose signed volume is negative.
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    flip = []
    seen = set()
    for f0 in bm.faces:
        if f0.index in seen:
            continue
        comp, stack = [], [f0]
        seen.add(f0.index)
        while stack:
            f = stack.pop()
            comp.append(f)
            for e in f.edges:
                for g in e.link_faces:
                    if g.index not in seen:
                        seen.add(g.index)
                        stack.append(g)
        vol = sum(f.calc_center_median().dot(f.normal) * f.calc_area() for f in comp)
        if vol < 0:
            flip.extend(comp)
    bmesh.ops.reverse_faces(bm, faces=flip)
    boundary = sum(1 for e in bm.edges if e.is_boundary)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()
    log(f"instant meshes cleanup: filled {len(filled)} holes, flipped {len(flip)} faces, {boundary} boundary edges left")


def drop_small_islands(ob, keep_frac=0.002):
    """Delete connected pieces smaller than keep_frac of the mesh (voxel specks)."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    seen = np.zeros(len(bm.verts), bool)
    kill = []
    for v in bm.verts:
        if seen[v.index]:
            continue
        stack, comp = [v], []
        seen[v.index] = True
        while stack:
            x = stack.pop()
            comp.append(x)
            for e in x.link_edges:
                y = e.other_vert(x)
                if not seen[y.index]:
                    seen[y.index] = True
                    stack.append(y)
        if len(comp) < keep_frac * len(bm.verts):
            kill.extend(comp)
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    bm.to_mesh(ob.data)
    bm.free()
    return len(kill)


def setup_cycles():
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for dev_type in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = dev_type
            prefs.get_devices()
            if any(d.type == dev_type for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == dev_type
                sc.cycles.device = "GPU"
                log("cycles device", dev_type)
                break
        except TypeError:
            continue
    sc.cycles.samples = 16
    sc.render.bake.use_selected_to_active = True
    sc.render.bake.use_cage = False
    sc.render.bake.cage_extrusion = EXTRUSION
    sc.render.bake.max_ray_distance = RAY_DIST
    sc.render.bake.margin = 8


def fresh_image(name):
    """New image every run: reusing one from the .blend kept its stale *packed* pixels
    (pack() doesn't repack), so the GLB shipped the previous run's texture on new UVs."""
    old = bpy.data.images.get(name)
    if old:
        bpy.data.images.remove(old)
    return bpy.data.images.new(name, TEX, TEX, alpha=False, float_buffer=False)


def bake_pass(game, hi, name, bake_type, colorspace, **kw):
    img = fresh_image(f"{CHAR}_{name}")
    img.colorspace_settings.name = colorspace
    nt = game.data.materials[0].node_tree
    node = nt.nodes.get("bake_target") or nt.nodes.new("ShaderNodeTexImage")
    node.name = "bake_target"
    node.image = img
    nt.nodes.active = node
    only_select(hi, game)
    t = time.time()
    bpy.ops.object.bake(type=bake_type, **kw)
    log(f"baked {name} ({time.time()-t:.0f}s)")
    img.filepath_raw = str(TEXDIR / f"{CHAR}_goose_{name}.png")
    img.file_format = "PNG"
    img.save()
    return img


def px(img):
    a = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(img.size[1], img.size[0], 4)


def bake(hi, game):
    TEXDIR.mkdir(parents=True, exist_ok=True)
    setup_cycles()
    game.data.materials.clear()
    mat = bpy.data.materials.new(f"{CHAR}_goose_game")
    mat.use_nodes = True
    game.data.materials.append(mat)

    hmat = hi.data.materials[0]
    hnt = hmat.node_tree
    bsdf = next(n for n in hnt.nodes if n.type == "BSDF_PRINCIPLED")

    base = bake_pass(game, hi, "basecolor", "DIFFUSE", "sRGB", pass_filter={"COLOR"})
    normal = bake_pass(game, hi, "normal", "NORMAL", "Non-Color", normal_space="TANGENT")
    rough = bake_pass(game, hi, "roughness", "ROUGHNESS", "Non-Color")
    # Metallic: route the hi metallic input into emission for one bake, then restore.
    out = next(n for n in hnt.nodes if n.type == "OUTPUT_MATERIAL")
    emit = hnt.nodes.new("ShaderNodeEmission")
    met_link = bsdf.inputs["Metallic"].links[0].from_socket if bsdf.inputs["Metallic"].links else None
    if met_link:
        hnt.links.new(met_link, emit.inputs["Color"])
    else:
        v = bsdf.inputs["Metallic"].default_value
        emit.inputs["Color"].default_value = (v, v, v, 1)
    orig = out.inputs["Surface"].links[0].from_socket
    hnt.links.new(emit.outputs[0], out.inputs["Surface"])
    metal = bake_pass(game, hi, "metallic", "EMIT", "Non-Color")
    hnt.links.new(orig, out.inputs["Surface"])
    hnt.nodes.remove(emit)
    ao = bake_pass(game, hi, "ao", "AO", "Non-Color")

    # glTF ORM: R=occlusion, G=roughness, B=metallic
    orm = fresh_image(f"{CHAR}_orm")
    orm.colorspace_settings.name = "Non-Color"
    o = np.ones((TEX, TEX, 4), np.float32)
    o[..., 0], o[..., 1], o[..., 2] = px(ao)[..., 0], px(rough)[..., 0], px(metal)[..., 0]
    orm.pixels.foreach_set(o.ravel())
    orm.filepath_raw = str(TEXDIR / f"{CHAR}_goose_orm.png")
    orm.file_format = "PNG"
    orm.save()

    # Final material wired the way the glTF exporter expects.
    nt = mat.node_tree
    nt.nodes.clear()
    o_n = nt.nodes.new("ShaderNodeOutputMaterial")
    p = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(p.outputs[0], o_n.inputs["Surface"])

    def tex(img, x, y):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = img
        n.location = (x, y)
        return n

    nt.links.new(tex(base, -600, 300).outputs[0], p.inputs["Base Color"])
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(tex(orm, -800, 0).outputs[0], sep.inputs[0])
    nt.links.new(sep.outputs[1], p.inputs["Roughness"])
    nt.links.new(sep.outputs[2], p.inputs["Metallic"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex(normal, -600, -300).outputs[0], nm.inputs["Color"])
    nt.links.new(nm.outputs[0], p.inputs["Normal"])
    gltf_settings = nt.nodes.new("ShaderNodeGroup")
    grp = bpy.data.node_groups.get("glTF Material Output") or bpy.data.node_groups.new(
        "glTF Material Output", "ShaderNodeTree")
    if "Occlusion" not in [s.name for s in grp.interface.items_tree]:
        grp.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
    gltf_settings.node_tree = grp
    nt.links.new(sep.outputs[0], gltf_settings.inputs["Occlusion"])
    for im in (base, normal, orm):
        im.pack()


def main():
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    hi = bpy.data.objects[f"{CHAR}_goose_hi"]
    stats = {}
    if STAGE in ("all", "retopo"):
        game = retopo(hi)
    else:
        game = bpy.data.objects[f"{CHAR}_goose_game"]
    if STAGE in ("all", "bake"):
        bake(hi, game)
        # stage-"game" fix plugins from chars/<char>.json (e.g. region_groups)
        sys.path.insert(0, str(Path(__file__).parent))
        import fixes
        cfg = fixes.load_config(ROOT, CHAR)
        ctx = fixes.FixContext(ob=game, char=CHAR, height=cfg.get("height_m", 1.8), root=ROOT, stats=stats)
        stats["fixes"] = fixes.run(ctx, cfg.get("fixes", []), stage="game")
        only_select(*game.children_recursive, game)       # head + attached parts (eyes)
        glb = OUT / f"{CHAR}_goose_game.glb"
        bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=True,
                                  export_yup=True, export_apply=True, export_image_format="AUTO",
                                  export_tangents=True)
        from glb_fix_tangents import main as fix_tangents
        fix_tangents(str(glb))
        stats["glb"] = str(glb)
        stats["glb_mb"] = round(glb.stat().st_size / 1e6, 2)
    co = np.empty(len(game.data.vertices) * 3, np.float32)
    game.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    stats.update(tris=tri_count(game), verts=len(game.data.vertices), faces=len(game.data.polygons),
                 dims_m=(co.max(0) - co.min(0)).round(3).tolist(), tex=TEX, voxel_m=VOXEL,
                 bake_extrusion_m=EXTRUSION, bake_ray_dist_m=RAY_DIST)
    hi.hide_render = False
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    (OUT / f"{CHAR}_goose_game.json").write_text(json.dumps(stats, indent=1))
    log("DONE", json.dumps(stats))


main()
