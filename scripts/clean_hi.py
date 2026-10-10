"""Phase 3: clean the chosen generated candidate into the hi-poly source.

  blender -b --factory-startup --python scripts/clean_hi.py -- <candidate.glb> \
      [--char male] [--height 1.8] [--hat-recolor] [--hat-z 0.88]

1. Weld UV-seam duplicate verts (UV-safe: Blender UVs live on loops).
2. Delete loose specks (< MIN_ISLAND verts). Gloves / buttons / flaps are kept.
3. Feet on Z=0, centered on X/Y, scaled to --height metres; optional "yaw_steps" from config
   (generator output already faces -Y).
4. Fix plugins for stage "hi" (scripts/fixes/), from chars/<char>.json "fixes" plus any
   --fix given on the command line (e.g. the male's hat_recolor).
Writes out/<char>-goose/<char>_goose_hi.glb and <char>_goose.blend (collection "Hi").
"""
import json
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

argv = sys.argv[sys.argv.index("--") + 1:]
SRC = Path(argv[0]).resolve()


def opt(name, default, cast=str):
    return cast(argv[argv.index(name) + 1]) if name in argv else default


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))
import fixes  # noqa: E402

CHAR = opt("--char", "male")
CONFIG = {} if "--no-config" in argv else fixes.load_config(ROOT, CHAR)
HEIGHT = opt("--height", CONFIG.get("height_m", 1.8), float)
FIX_SPECS = CONFIG.get("fixes", []) + [fixes.parse_cli(argv[i + 1])
                                       for i, a in enumerate(argv) if a == "--fix"]
MIN_ISLAND = 100
OUT = ROOT / "out" / f"{CHAR}-goose"


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(SRC))
    ob = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    ob.name = ob.data.name = f"{CHAR}_goose_hi"
    stats = {"source": str(SRC)}

    # 1-2. weld + delete specks
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    n0 = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.verts.ensure_lookup_table()
    seen = np.zeros(len(bm.verts), bool)
    kill = []
    islands = 0
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
        islands += 1
        if len(comp) < MIN_ISLAND:
            kill.extend(comp)
    bmesh.ops.delete(bm, geom=kill, context="VERTS")
    stats.update(verts_in=n0, verts_welded=n0 - len(bm.verts) - len(kill), islands=islands,
                 speck_verts_removed=len(kill))
    bm.to_mesh(ob.data)
    bm.free()

    # 3. orient / scale
    co = np.empty(len(ob.data.vertices) * 3, np.float32)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    lo, hi = co.min(0), co.max(0)
    s = HEIGHT / (hi[2] - lo[2])
    ob.data.transform(Matrix.Scale(s, 4) @ Matrix.Translation(
        -Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]))))
    ob.data.update()
    # Facing: generators so far always emit front = -Y, so rotation comes from config
    # ("yaw_steps": quarter turns about Z). The beak heuristic only warns: it misfires on
    # wide hats / plumes that reach further back than the beak reaches forward (female).
    yaw_steps = int(CONFIG.get("yaw_steps", 0))
    if yaw_steps:
        ob.data.transform(Matrix.Rotation(yaw_steps * np.pi / 2, 4, "Z"))
        stats["yaw_steps"] = yaw_steps
    co = np.empty(len(ob.data.vertices) * 3, np.float32)
    ob.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    head = co[co[:, 2] > 0.8 * HEIGHT]
    if abs(head[:, 1].max()) > abs(head[:, 1].min()):
        stats["facing_warning"] = "head extends further +Y than -Y; check facing (yaw_steps)"
        print("[clean_hi] WARNING:", stats["facing_warning"], flush=True)
    dims = (co.max(0) - co.min(0)).round(3).tolist()
    stats.update(dims_m=dims, faces=len(ob.data.polygons),
                 tris=sum(len(p.vertices) - 2 for p in ob.data.polygons))

    # 4. fix plugins (per-character, chars/<char>.json + --fix)
    ctx = fixes.FixContext(ob=ob, char=CHAR, height=HEIGHT, root=ROOT, stats=stats)
    stats["fixes"] = fixes.run(ctx, FIX_SPECS, stage="hi")

    # export
    OUT.mkdir(parents=True, exist_ok=True)
    glb = OUT / f"{CHAR}_goose_hi.glb"
    bpy.ops.export_scene.gltf(filepath=str(glb), export_format="GLB", use_selection=False,
                              export_yup=True, export_apply=True)
    col = bpy.data.collections.new("Hi")
    bpy.context.scene.collection.children.link(col)
    for c in ob.users_collection:
        c.objects.unlink(ob)
    col.objects.link(ob)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f"{CHAR}_goose.blend"), compress=True)
    stats["glb"] = str(glb)
    (OUT / f"{CHAR}_goose_hi.json").write_text(json.dumps(stats, indent=1))
    print("CLEAN", json.dumps(stats))


if __name__ == "__main__":
    if "--list-fixes" in argv:
        for name, mod in sorted(fixes.registry().items()):
            print(f"{name:16s} stage={mod.STAGE:4s} {mod.DEFAULTS}")
            print(f"  {mod.__doc__.strip().splitlines()[0]}")
    else:
        main()
