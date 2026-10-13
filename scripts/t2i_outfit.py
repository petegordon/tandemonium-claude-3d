"""Text-to-image reference views: dress the naked base goose in a new outfit described in words, in the five views the
garment pipeline reads (front, 3/4, left, rear, right) -- local, on Claude's ComfyUI (:8189) with Qwen-Image-Edit-2511.

  python scripts/t2i_outfit.py --outfit outfit_male_cyclist [--seed 7] [--steps 4] [--views front,q34,left,rear,right]
      [--base renders/t2i/_base_views_{view}.png] [--tag v1]

Inputs:
  refs/<outfit>/t2i_prompt.json  {"outfit": "<garments in words>", "style": "...", "view_hint": {"front": "...", ...}}
  base views (outfit_beauty.py --views front:0,q34:35,left:90,rear:180,right:270 --floor 0.6 on the base goose)
How (consistency across views): the FRONT is dressed first from the words alone (picture 1 = the naked goose); every
other view is then dressed with picture 1 = that view of the naked goose and picture 2 = the dressed front, told to
put the identical outfit on, keeping picture 1's pose, camera and background. Lightning LoRA, 4 steps, cfg 1.
Writes refs/<outfit>/t2i/<tag>/<view>.png + sheet.png + run.json.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfy_job import COMFY_OUT, G, preflight, run, upload  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
UNET = "qwen-image-edit-2511-Q4_K_S.gguf"
CLIP = "qwen_2.5_vl_7b_fp8_scaled.safetensors"
VAE = "qwen_image_vae.safetensors"
LORA = "Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors"
VIEW_WORDS = {"front": "front view", "q34": "three-quarter front view (turned to its left)", "left": "side view, facing left",
              "rear": "back view", "right": "side view, facing right"}


def graph(img_names, prompt, seed, steps, prefix):
    g = G()
    unet = g.add("UnetLoaderGGUF", unet_name=UNET)
    clip = g.add("CLIPLoader", clip_name=CLIP, type="qwen_image", device="default")
    vae = g.add("VAELoader", vae_name=VAE)
    m = g.add("ModelSamplingAuraFlow", model=G.o(unet), shift=3.1)
    m = g.add("CFGNorm", model=G.o(m), strength=1.0)
    m = g.add("LoraLoaderModelOnly", model=G.o(m), lora_name=LORA, strength_model=1.0)
    imgs = []
    for i, n in enumerate(img_names):
        li = g.add("LoadImage", image=n)
        imgs.append(g.add("FluxKontextImageScale", image=G.o(li)) if i == 0 else li)
    kw = {f"image{i + 1}": G.o(n) for i, n in enumerate(imgs)}
    pos = g.add("TextEncodeQwenImageEditPlus", clip=G.o(clip), vae=G.o(vae), prompt=prompt, **kw)
    neg = g.add("TextEncodeQwenImageEditPlus", clip=G.o(clip), vae=G.o(vae), prompt="", **kw)
    pos = g.add("FluxKontextMultiReferenceLatentMethod", conditioning=G.o(pos), reference_latents_method="index_timestep_zero")
    neg = g.add("FluxKontextMultiReferenceLatentMethod", conditioning=G.o(neg), reference_latents_method="index_timestep_zero")
    lat = g.add("VAEEncode", pixels=G.o(imgs[0]), vae=G.o(vae))
    ks = g.add("KSampler", model=G.o(m), positive=G.o(pos), negative=G.o(neg), latent_image=G.o(lat), seed=seed,
               steps=steps, cfg=1.0, sampler_name="euler", scheduler="simple", denoise=1.0)
    dec = g.add("VAEDecode", samples=G.o(ks), vae=G.o(vae))
    g.add("SaveImage", images=G.o(dec), filename_prefix=prefix)
    return g.nodes


def first_image(outputs):
    for no in outputs.values():
        for it in no.get("images", []) or []:
            if it.get("type") == "output":
                return COMFY_OUT / it.get("subfolder", "") / it["filename"]
    raise RuntimeError("no image output")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outfit", required=True)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--steps", type=int, default=4)
    ap.add_argument("--views", default="front,q34,left,rear,right")
    ap.add_argument("--base", default="renders/t2i/_base_views_{view}.png")
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--front", default="", help="reuse an existing dressed front instead of generating one")
    a = ap.parse_args()
    spec = json.loads((ROOT / "refs" / a.outfit / "t2i_prompt.json").read_text(encoding="utf-8"))
    dest = ROOT / "refs" / a.outfit / "t2i" / a.tag
    dest.mkdir(parents=True, exist_ok=True)
    preflight(7.0)
    views = a.views.split(",")
    done, log = {}, {"seed": a.seed, "steps": a.steps, "unet": UNET, "lora": LORA, "spec": spec, "views": {}}
    if a.front:
        done["front"] = ROOT / a.front
    for v in (["front"] if "front" not in done else []) + [v for v in views if v != "front"]:
        base = ROOT / a.base.format(view=v)
        names = [upload(base, f"t2i_{a.outfit}_base_{v}.png")]
        hint = spec.get("view_hint", {}).get(v, "")
        if v == "front":
            prompt = (f"Dress the goose in picture 1 in this outfit: {spec['outfit']}. {spec.get('style', '')} "
                      f"Keep the goose's body, head, beak, eyes, pose, proportions, the camera ({VIEW_WORDS[v]}), the "
                      f"lighting and the plain light-grey background exactly as in picture 1. Full body, nothing cropped. {hint}")
        else:
            names.append(upload(done["front"], f"t2i_{a.outfit}_dressed_front.png"))
            prompt = (f"Dress the goose in picture 1 in exactly the same outfit the goose in picture 2 is wearing: the "
                      f"same garments, colours, patterns, buttons and accessories ({spec['outfit']}). Picture 1 is the "
                      f"{VIEW_WORDS[v]}: keep its pose, body, head, camera angle, lighting and plain light-grey "
                      f"background exactly; show the outfit as it looks from that side. {spec.get('style', '')} {hint}")
        t0 = time.time()
        outs, dt, peak = run(graph(names, prompt, a.seed, a.steps, f"t2i/{a.outfit}_{a.tag}_{v}"))
        src = first_image(outs)
        out = dest / f"{v}.png"
        Image.open(src).convert("RGB").save(out)
        done[v] = out
        log["views"][v] = {"prompt": prompt, "seconds": round(time.time() - t0), "peak_gb": round(peak, 1)}
        print(f"[t2i] {v} -> {out} ({dt:.0f}s)", flush=True)
    (dest / "run.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    tiles = [Image.open(done[v]) for v in views if v in done]
    h = 1024
    tiles = [t.resize((round(t.width * h / t.height), h)) for t in tiles]
    sheet = Image.new("RGB", (sum(t.width for t in tiles), h + 50), (36, 36, 38))
    x = 0
    try:
        font = ImageFont.truetype("arial.ttf", 30)
    except OSError:
        font = ImageFont.load_default()
    for v, t in zip([v for v in views if v in done], tiles):
        sheet.paste(t, (x, 50))
        ImageDraw.Draw(sheet).text((x + 14, 10), v, fill=(235, 230, 220), font=font)
        x += t.width
    sheet.save(dest / "sheet.png")
    print("[t2i] sheet", dest / "sheet.png")


if __name__ == "__main__":
    main()
