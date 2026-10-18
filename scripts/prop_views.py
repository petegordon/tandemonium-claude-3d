"""Prop reference views from one photo: re-stage a real object (phone photo, any angle) as clean straight-on
product shots -- front, left, rear (+ right) -- that comfy_job.py prep / pixal-mv read. Same local
Qwen-Image-Edit-2511 graph as t2i_outfit.py (Claude's ComfyUI :8189).

  python scripts/prop_views.py --prop ketchup --photo <photo.jpg> [--seed 7] [--views front,left,rear,right]
      [--front refs/ketchup/t2i/v1/front.png] [--tag v1]

Inputs: refs/<prop>/prop.json {"object": "<what it is, in words>", "view_hint": {"left": "...", ...}}
The FRONT is redrawn from the photo (picture 1 = photo); every other view gets picture 1 = the photo and picture 2 =
the approved front. Writes refs/<prop>/t2i/<tag>/<view>.png + sheet.png + run.json.
"""
import argparse
import json
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfy_job import preflight, run, upload  # noqa: E402
from t2i_outfit import first_image, graph  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
VIEW_WORDS = {"front": "straight-on front view, label facing the camera",
              "left": "exact side profile view, the object turned 90 degrees so its left side faces the camera",
              "rear": "straight-on back view, the object turned 180 degrees",
              "right": "exact side profile view, the object turned 90 degrees so its right side faces the camera"}
STAGE = ("Orthographic product photo, camera at the object's mid-height, level, no perspective tilt. The whole object "
         "centred and upright exactly as it stands in picture 1, nothing cropped, filling about 80% of the image "
         "height. Plain flat light-grey studio background, soft even lighting, no shadows on the background, no other "
         "objects.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prop", required=True)
    ap.add_argument("--photo", required=True)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--steps", type=int, default=4)
    ap.add_argument("--views", default="front,left,rear,right")
    ap.add_argument("--front", default="")
    ap.add_argument("--tag", default="v1")
    a = ap.parse_args()
    spec = json.loads((ROOT / "refs" / a.prop / "prop.json").read_text(encoding="utf-8"))
    dest = ROOT / "refs" / a.prop / "t2i" / a.tag
    dest.mkdir(parents=True, exist_ok=True)
    preflight(7.0)
    photo = upload(Path(a.photo), f"prop_{a.prop}_photo.png")
    done = {"front": ROOT / a.front} if a.front else {}
    log = {"seed": a.seed, "steps": a.steps, "spec": spec, "views": {}}
    views = a.views.split(",")
    for v in (["front"] if "front" not in done else []) + [v for v in views if v != "front"]:
        hint = spec.get("view_hint", {}).get(v, "")
        names = [photo]
        if v == "front":
            prompt = (f"Picture 1 is a photo of {spec['object']}. Redraw exactly this object as a {VIEW_WORDS[v]}. "
                      f"Keep its exact shape, proportions, colours, materials, label artwork and text. {STAGE} {hint}")
        else:
            names.append(upload(done["front"], f"prop_{a.prop}_front.png"))
            prompt = (f"Picture 1 is a photo of {spec['object']}; picture 2 is the same object as a clean front view. "
                      f"Show exactly the same object as a {VIEW_WORDS[v]}, with the same shape, proportions, colours "
                      f"and materials as picture 2, as it looks from that side. {STAGE} Match picture 2's background, "
                      f"lighting and scale. {hint}")
        t0 = time.time()
        outs, dt, peak = run(graph(names, prompt, a.seed, a.steps, f"t2i/prop_{a.prop}_{a.tag}_{v}"))
        out = dest / f"{v}.png"
        Image.open(first_image(outs)).convert("RGB").save(out)
        done[v] = out
        log["views"][v] = {"prompt": prompt, "seconds": round(time.time() - t0), "peak_gb": round(peak, 1)}
        print(f"[prop_views] {v} -> {out} ({dt:.0f}s)", flush=True)
    (dest / "run.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
    tiles = [Image.open(done[v]) for v in views if v in done]
    tiles = [t.resize((round(t.width * 768 / t.height), 768)) for t in tiles]
    sheet = Image.new("RGB", (sum(t.width for t in tiles), 768), (36, 36, 38))
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0))
        x += t.width
    sheet.save(dest / "sheet.png")
    print("[prop_views] sheet", dest / "sheet.png")


if __name__ == "__main__":
    main()
