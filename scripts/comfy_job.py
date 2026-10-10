"""ComfyUI (Claude install, :8189) job runner for the goose builds.

Graphs are built in API format from the native templates shipped with ComfyUI
v0.39 (3d_pixal3d_multi_views / 3d_pixal3d_trellis2_image_to_model /
3d_hunyuan3d_multiview_to_model), with knobs exposed for a 12 GB laptop GPU.

Every job: nvidia-smi preflight (refuse rather than OOM -> TDR reboot), POST /free
on OUR server only, one job at a time, outputs copied into out/<name>/, and a line
appended to out/<name>/manifest.jsonl.

Usage (run with the ComfyUI-claude venv python):
  python scripts/comfy_job.py prep   --char male
  python scripts/comfy_job.py pixal-mv --char male --seed 42 [--upsample 1024]
  python scripts/comfy_job.py single --char male --view front --model trellis|pixal
  python scripts/comfy_job.py hunyuan-mv --char male --seed 42
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SERVER = "http://127.0.0.1:8189"
COMFY_OUT = Path(r"C:\Users\pete\ComfyUI-claude\output")
MIN_FREE_GB = 7.5  # int8 TRELLIS.2/Pixal3D + DINOv3 + VAEs, with offload headroom


# ---------------------------------------------------------------- server I/O
def _req(path, data=None, method=None, timeout=30):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(SERVER + path, data=body, method=method,
                               headers={"Content-Type": "application/json"} if body else {})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


def gpu_free_gb():
    out = subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.total,memory.used", "--format=csv,noheader,nounits"],
        text=True).strip().splitlines()[0]
    total, used = (float(x) for x in out.split(","))
    return (total - used) / 1024.0


def preflight(min_gb):
    _req("/free", {"unload_models": True, "free_memory": True}, "POST")
    time.sleep(2)
    free = gpu_free_gb()
    print(f"[preflight] free VRAM {free:.2f} GB (need {min_gb})", flush=True)
    if free < min_gb:
        sys.exit(f"ABORT: only {free:.2f} GB VRAM free. Another process (e.g. the Desktop "
                 f"ComfyUI on :8000) is holding the GPU. Refusing rather than risking a TDR.")


def upload(path, name=None):
    name = name or path.name
    boundary = "----goose" + uuid.uuid4().hex
    parts = [f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
             "Content-Type: image/png\r\n\r\n".encode(), path.read_bytes(), b"\r\n",
             f"--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\ntrue\r\n"
             f"--{boundary}--\r\n".encode()]
    r = urllib.request.Request(SERVER + "/upload/image", data=b"".join(parts), method="POST",
                               headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(r) as resp:
        return json.load(resp)["name"]


def run(graph, timeout=3600):
    pid = _req("/prompt", {"prompt": graph, "client_id": uuid.uuid4().hex}, "POST")["prompt_id"]
    print(f"[run] prompt {pid}", flush=True)
    t0, peak = time.time(), 0.0
    while time.time() - t0 < timeout:
        hist = _req(f"/history/{pid}")
        try:
            peak = max(peak, 12.2 - gpu_free_gb())
        except Exception:
            pass
        if pid in hist:
            st = hist[pid].get("status", {})
            if st.get("status_str") == "error":
                msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]
                raise RuntimeError(json.dumps(msgs[-1][1] if msgs else st, indent=1)[:3000])
            if st.get("completed"):
                dt = time.time() - t0
                print(f"[run] done in {dt:.0f}s, peak GPU used ~{peak:.1f} GB", flush=True)
                return hist[pid]["outputs"], dt, peak
        time.sleep(2)
    raise TimeoutError(pid)


def collect(outputs, dest):
    """Copy every file a node reported (images / 3d) into dest; return list of paths."""
    dest.mkdir(parents=True, exist_ok=True)
    got = []
    for node_out in outputs.values():
        for key in ("images", "3d", "meshes", "result"):
            for item in node_out.get(key, []) or []:
                if not isinstance(item, dict) or "filename" not in item:
                    continue
                if item.get("type") == "temp":
                    continue
                src = COMFY_OUT / item.get("subfolder", "") / item["filename"]
                if src.exists():
                    shutil.copy2(src, dest / item["filename"])
                    got.append(dest / item["filename"])
    return got


def log_manifest(dest, entry):
    with open(dest / "manifest.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------- graphs
class G:
    """Tiny API-graph builder: g.add('KSampler', seed=1, model=g.ref(n, 0))."""

    def __init__(self):
        self.nodes, self.n = {}, 0

    def add(self, cls, **inputs):
        self.n += 1
        nid = str(self.n)
        self.nodes[nid] = {"class_type": cls, "inputs": inputs}
        return nid

    @staticmethod
    def o(nid, slot=0):
        return [nid, slot]


def g_prep(images, prefix):
    """Upscale 4x -> BiRefNet matte -> square crop to mask on black (Pixal3D framing)."""
    g = G()
    up = g.add("UpscaleModelLoader", model_name="4x-UltraSharpV2.safetensors")
    bg = g.add("LoadBackgroundRemovalModel", bg_removal_name="birefnet.safetensors")
    for view, name in images.items():
        li = g.add("LoadImage", image=name)
        big = g.add("ImageUpscaleWithModel", upscale_model=G.o(up), image=G.o(li))
        m = g.add("RemoveBackground", bg_removal_model=G.o(bg), image=G.o(big))
        c = g.add("ImageCropToMask", images=G.o(big), masks=G.o(m), width=1024, height=1024,
                  pad_factor=1.1, grow_mask=0, background="#000000")
        g.add("SaveImage", images=G.o(c), filename_prefix=f"{prefix}/{view}_black")
        ca = g.add("ImageCropToMask", images=G.o(big), masks=G.o(m), width=1024, height=1024,
                   pad_factor=1.1, grow_mask=0, background="#FFFFFF")
        g.add("SaveImage", images=G.o(ca), filename_prefix=f"{prefix}/{view}_white")
        g.add("SaveImage", images=G.o(big), filename_prefix=f"{prefix}/{view}_up4x")
    return g.nodes


def _trellis_tail(g, cond, base_model, shape_vae, tex_vae, a):
    """Shared structure -> shape -> upsample -> texture -> remesh/unwrap/bake -> GLB."""
    o = G.o
    m1 = g.add("RescaleCFG", model=o(g.add("CFGOverride", model=o(base_model), cfg=1.0,
                                           start_percent=0.667, end_percent=1.0)), multiplier=0.7)
    m_struct = g.add("ModelSamplingSD3", model=o(m1), shift=5.0)
    m_shape = g.add("RescaleCFG", model=o(g.add("CFGOverride", model=o(base_model), cfg=1.0,
                                                start_percent=0.769, end_percent=1.0)), multiplier=0.5)
    lat = g.add("EmptyTrellis2LatentStructure", batch_size=1)
    s1 = g.add("KSampler", model=o(m_struct), positive=o(cond, 0), negative=o(cond, 1),
               latent_image=o(lat), seed=a.seed + 14, steps=a.steps_struct, cfg=7.5,
               sampler_name="euler", scheduler="normal", denoise=1.0)
    vox = g.add("VaeDecodeStructureTrellis2", samples=o(s1), vae=o(shape_vae), resolution="32")
    g.add("SaveGLB", mesh=o(g.add("VoxelToMesh", voxel=o(vox), algorithm="basic", threshold=0.6)),
          filename_prefix=f"{a.prefix}/structure")
    ss = g.add("Trellis2ShapeStage", positive=o(cond, 0), negative=o(cond, 1), voxel=o(vox))
    s2 = g.add("KSampler", model=o(m_shape), positive=o(ss, 0), negative=o(ss, 1),
               latent_image=o(ss, 2), seed=a.seed, steps=a.steps_shape, cfg=7.5,
               sampler_name="euler", scheduler="normal", denoise=1.0)
    shape_lat, pos = s2, ss
    if a.upsample:
        us = g.add("Trellis2UpsampleStage", positive=o(ss, 0), negative=o(ss, 1),
                   shape_latent=o(s2), vae=o(shape_vae), target_resolution=a.upsample)
        shape_lat = g.add("KSampler", model=o(m_shape), positive=o(us, 0), negative=o(us, 1),
                          latent_image=o(us, 2), seed=a.seed, steps=a.steps_up, cfg=7.5,
                          sampler_name="euler", scheduler="simple", denoise=1.0)
        pos = us
    shp = g.add("VaeDecodeShapeTrellis", samples=o(shape_lat), vae=o(shape_vae))
    g.add("SaveGLB", mesh=o(shp, 0), filename_prefix=f"{a.prefix}/shape_raw")
    ts = g.add("Trellis2TextureStage", positive=o(pos, 0), negative=o(pos, 1), shape_latent=o(shape_lat))
    s4 = g.add("KSampler", model=o(base_model), positive=o(ts, 0), negative=o(ts, 1),
               latent_image=o(ts, 2), seed=a.seed + 1, steps=a.steps_tex, cfg=1.0,
               sampler_name="euler", scheduler="normal", denoise=1.0)
    tvox = g.add("VaeDecodeTextureTrellis", samples=o(s4), vae=o(tex_vae), shape_subdivides=o(shp, 1))
    rem = g.add("RemeshMesh", mesh=o(shp, 0), resolution=a.remesh, sign_mode="udf",
                **{"sign_mode.qef": False, "sign_mode.drop_inverted_components": False,
                   "sign_mode.drop_enclosed_components": False},
                band=1.0, project_back=0.0, fix_poles=False, smooth_iters=20,
                drop_small_components=0.01, precluster_max_verts=20000000)
    dec = g.add("DecimateMesh", mesh=o(rem), target_face_count=a.faces, placement_mode="midpoint")
    sm = g.add("MeshSmoothNormals", mesh=o(dec), crease_angle=180.0)
    uv = g.add("UnwrapMesh", mesh=o(sm), segmenter="pec", resolution=a.tex, padding=1,
               weld_distance=0.0002)
    bake = g.add("BakeTextureFromVoxel", mesh=o(uv), voxel_colors=o(tvox), reference_mesh=o(shp, 0),
                 texture_size=a.tex)
    nrm = g.add("BakeNormalMapFromMesh", low_poly=o(uv), high_poly=o(rem), resolution=a.tex,
                cage_distance=0.05, ignore_backfaces=True)
    ao = g.add("BakeAmbientOcclusion", low_poly=o(uv), high_poly=o(rem), resolution=min(a.tex, 1024),
               samples=64, max_distance=0.71, strength=1.0, bias=0.01)
    for i, nm in enumerate(["basecolor", "metallic", "roughness"]):
        g.add("SaveImage", images=o(bake, i), filename_prefix=f"{a.prefix}/tex_{nm}")
    g.add("SaveImage", images=o(nrm), filename_prefix=f"{a.prefix}/tex_normal")
    g.add("SaveImage", images=o(ao), filename_prefix=f"{a.prefix}/tex_ao")
    tm = g.add("ApplyTextureToMesh", mesh=o(uv), base_color=o(bake, 0), metallic=o(bake, 1),
               roughness=o(bake, 2), occlusion=o(ao), normal_map=o(nrm))
    g.add("SaveGLB", mesh=o(g.add("MeshSmoothNormals", mesh=o(tm), crease_angle=180.0)),
          filename_prefix=f"{a.prefix}/textured")


def g_pixal_mv(views, a):
    g = G()
    o = G.o
    tex_vae = g.add("VAELoader", vae_name="trellis_2_texture_vae_bf16.safetensors")
    shape_vae = g.add("VAELoader", vae_name="trellis_2_shape_vae_bf16.safetensors")
    clip = g.add("CLIPVisionLoader", clip_name="dino_v3_L_naf_fp32.safetensors")
    unet = g.add("UNETLoader", unet_name="pixal3d_multiview_int8_convrot.safetensors", weight_dtype="default")
    imgs = {v: o(g.add("LoadImage", image=n)) for v, n in views.items()}
    cond = g.add("Pixal3DMultiViewConditioning", clip_vision_model=o(clip), fov=a.fov, **imgs)
    _trellis_tail(g, cond, unet, shape_vae, tex_vae, a)
    return g.nodes


def g_single(image, a):
    g = G()
    o = G.o
    tex_vae = g.add("VAELoader", vae_name="trellis_2_texture_vae_bf16.safetensors")
    shape_vae = g.add("VAELoader", vae_name="trellis_2_shape_vae_bf16.safetensors")
    clip = g.add("CLIPVisionLoader", clip_name="dino_v3_L_naf_fp32.safetensors")
    img = o(g.add("LoadImage", image=image))
    if a.model == "trellis":
        unet = g.add("UNETLoader", unet_name="trellis_2_int8_convrot.safetensors", weight_dtype="default")
        cond = g.add("Trellis2Conditioning", clip_vision_model=o(clip), image=img)
    else:
        unet = g.add("UNETLoader", unet_name="pixal3d_int8_convrot.safetensors", weight_dtype="default")
        cond = g.add("Pixal3DConditioning", clip_vision_model=o(clip), image=img, camera_angle_x=a.fov)
    _trellis_tail(g, cond, unet, shape_vae, tex_vae, a)
    return g.nodes


def g_hunyuan_mv(views, a):
    g = G()
    o = G.o
    ck = g.add("ImageOnlyCheckpointLoader", ckpt_name="hunyuan3d-dit-v2-mv_fp16.safetensors")
    enc = {v: o(g.add("CLIPVisionEncode", clip_vision=o(ck, 1),
                      image=o(g.add("LoadImage", image=n)), crop="none"))
           for v, n in views.items()}
    cond = g.add("Hunyuan3Dv2ConditioningMultiView", **enc)
    lat = g.add("EmptyLatentHunyuan3Dv2", resolution=3072, batch_size=1)
    model = g.add("ModelSamplingAuraFlow", model=o(ck, 0), shift=1.0)
    s = g.add("KSampler", model=o(model), positive=o(cond, 0), negative=o(cond, 1), latent_image=o(lat),
              seed=a.seed, steps=a.steps_shape, cfg=7.5, sampler_name="euler", scheduler="normal",
              denoise=1.0)
    vox = g.add("VAEDecodeHunyuan3D", samples=o(s), vae=o(ck, 2), num_chunks=8000,
                octree_resolution=a.octree)
    g.add("SaveGLB", mesh=o(g.add("VoxelToMesh", voxel=o(vox), algorithm="surface net", threshold=0.6)),
          filename_prefix=f"{a.prefix}/shape")
    return g.nodes


# ---------------------------------------------------------------- commands
VIEW_FILES = {"front": "front", "left": "left", "back": "rear"}


def cmd_prep(a):
    src = ROOT / "refs" / a.char
    names = {}
    for view, stem in VIEW_FILES.items():
        names[view] = upload(src / f"{stem}_raw.png", f"{a.char}_{view}_raw.png")
    # Right view: mirrored left profile (forces symmetry; default) or the sheet's drawn right
    # profile (--right drawn) for asymmetric costumes (female plume / bustle).
    if a.right == "drawn" and (src / "right_drawn_raw.png").exists():
        names["right"] = upload(src / "right_drawn_raw.png", f"{a.char}_right_raw.png")
    else:
        mirrored = src / "right_mirrored_raw.png"
        ImageOps.mirror(Image.open(src / "left_raw.png")).save(mirrored)
        names["right"] = upload(mirrored, f"{a.char}_right_raw.png")
    preflight(3.0)
    outs, dt, peak = run(g_prep(names, f"claude3d_{a.char}_prep"))
    files = collect(outs, src / "prepped")
    for f in files:  # strip ComfyUI counters: front_black_00001_.png -> front_black.png
        f.rename(f.with_name(f.name.split("_000")[0] + ".png"))
    print("prepped:", sorted(p.name for p in (src / "prepped").glob("*.png")))


def _gen(a, graph, kind):
    preflight(a.min_free)
    t = time.strftime("%Y%m%d_%H%M%S")
    outs, dt, peak = run(graph)
    dest = ROOT / "out" / f"{a.char}-goose" / f"{kind}_s{a.seed}_{t}"
    files = collect(outs, dest)
    entry = {"kind": kind, "seed": a.seed, "time": t, "secs": round(dt), "peak_gb": round(peak, 1),
             "args": {k: v for k, v in vars(a).items() if k not in ("func",)},
             "files": [f.name for f in files]}
    (dest / "job.json").write_text(json.dumps({"entry": entry, "graph": graph}, indent=1))
    log_manifest(dest.parent, entry)
    print(json.dumps(entry, indent=1))


def _prepped(a, bg):
    d = ROOT / "refs" / a.char / "prepped"
    return {v: upload(d / f"{v}_{bg}.png", f"{a.char}_{v}_{bg}.png")
            for v in ("front", "left", "back", "right") if v in a.views}


def cmd_pixal_mv(a):
    a.prefix = f"claude3d_{a.char}_pixalmv_s{a.seed}_{time.strftime('%H%M%S')}"
    _gen(a, g_pixal_mv(_prepped(a, "black"), a), "pixalmv")


def cmd_single(a):
    a.prefix = f"claude3d_{a.char}_{a.model}_{a.view}_s{a.seed}_{time.strftime('%H%M%S')}"
    name = upload(ROOT / "refs" / a.char / "prepped" / f"{a.view}_black.png")
    _gen(a, g_single(name, a), f"{a.model}_{a.view}")


def cmd_hunyuan_mv(a):
    a.prefix = f"claude3d_{a.char}_hymv_s{a.seed}_{time.strftime('%H%M%S')}"
    _gen(a, g_hunyuan_mv(_prepped(a, "white"), a), "hymv")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--char", default="male")
    common.add_argument("--seed", type=int, default=42)
    common.add_argument("--min-free", type=float, default=MIN_FREE_GB)
    common.add_argument("--views", default="front,left,back,right")
    common.add_argument("--right", default="mirror", choices=["mirror", "drawn"])
    common.add_argument("--fov", type=float, default=20.0)
    common.add_argument("--upsample", type=int, default=1024, help="0 = skip, 1024, 1536")
    common.add_argument("--steps-struct", type=int, default=12)
    common.add_argument("--steps-shape", type=int, default=20)
    common.add_argument("--steps-up", type=int, default=12)
    common.add_argument("--steps-tex", type=int, default=12)
    common.add_argument("--remesh", type=int, default=768)
    common.add_argument("--faces", type=int, default=500000)
    common.add_argument("--tex", type=int, default=2048)
    common.add_argument("--octree", type=int, default=256)
    sp = sub.add_parser("prep", parents=[common]); sp.set_defaults(func=cmd_prep)
    sp = sub.add_parser("pixal-mv", parents=[common]); sp.set_defaults(func=cmd_pixal_mv)
    sp = sub.add_parser("single", parents=[common]); sp.set_defaults(func=cmd_single)
    sp.add_argument("--view", default="front"); sp.add_argument("--model", default="trellis",
                                                                choices=["trellis", "pixal"])
    sp = sub.add_parser("hunyuan-mv", parents=[common]); sp.set_defaults(func=cmd_hunyuan_mv)
    a = p.parse_args()
    a.views = a.views.split(",")
    a.func(a)


if __name__ == "__main__":
    main()
