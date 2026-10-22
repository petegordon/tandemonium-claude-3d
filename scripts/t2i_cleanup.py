"""One edit pass on finished t2i reference views: remove something the model keeps inventing (a goose tail behind the
trousers, ...) and keep everything else -- same model and settings as t2i_outfit.py, picture 1 = the view itself.

  python scripts/t2i_cleanup.py --outfit outfit_grandpa_cardigan --src turn2s21 --tag turn2s21c --views q34,left,right
      [--fix "<what to remove>"] [--seed 7] [--ref <picture 2 to match, e.g. an edited front>]

Copies the untouched views of --src, writes the edited ones, rebuilds sheet.png in refs/<outfit>/t2i/<tag>/.
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfy_job import preflight, run, upload  # noqa: E402
from t2i_outfit import first_image, graph  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIX = ("Remove the tail feathers sticking out behind the goose's hips and legs: the goose has no tail. Where the tail was, "
       "show what is behind it (the trousers, the cardigan hem, or the plain light-grey background).")
ap = argparse.ArgumentParser()
ap.add_argument("--outfit", required=True)
ap.add_argument("--src", required=True)
ap.add_argument("--tag", required=True)
ap.add_argument("--views", default="q34,left,right")
ap.add_argument("--fix", default=FIX)
ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--steps", type=int, default=4)
ap.add_argument("--ref", default="", help="picture 2: a reference image (e.g. the edited front) to match")
a = ap.parse_args()
src = ROOT / "refs" / a.outfit / "t2i" / a.src
dest = ROOT / "refs" / a.outfit / "t2i" / a.tag
dest.mkdir(parents=True, exist_ok=True)
ALL = ["front", "q34", "left", "rear", "right"]
for v in ALL:
    if (src / f"{v}.png").exists():
        shutil.copy(src / f"{v}.png", dest / f"{v}.png")
preflight(7.0)
log = {"src": a.src, "fix": a.fix, "seed": a.seed, "views": {}}
for v in a.views.split(","):
    names = [upload(dest / f"{v}.png", f"t2i_{a.outfit}_{a.tag}_{v}_in.png")]
    if a.ref:
        names.append(upload(ROOT / a.ref, f"t2i_{a.outfit}_{a.tag}_ref.png"))
    prompt = (f"{a.fix} Change nothing else: keep the goose, its outfit, colours, pose, camera, lighting and background "
              f"exactly as in picture 1.")
    t0 = time.time()
    outs, dt, _ = run(graph(names, prompt, a.seed, a.steps, f"t2i/{a.outfit}_{a.tag}_{v}"))
    Image.open(first_image(outs)).convert("RGB").save(dest / f"{v}.png")
    log["views"][v] = {"prompt": prompt, "seconds": round(time.time() - t0)}
    print(f"[cleanup] {v} ({dt:.0f}s)", flush=True)
(dest / "run.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
views = [v for v in ALL if (dest / f"{v}.png").exists()]
tiles = [Image.open(dest / f"{v}.png") for v in views]
tiles = [t.resize((round(t.width * 1024 / t.height), 1024)) for t in tiles]
sheet = Image.new("RGB", (sum(t.width for t in tiles), 1074), (36, 36, 38))
try:
    font = ImageFont.truetype("arial.ttf", 30)
except OSError:
    font = ImageFont.load_default()
x = 0
for v, t in zip(views, tiles):
    sheet.paste(t, (x, 50))
    ImageDraw.Draw(sheet).text((x + 14, 10), v, fill=(235, 230, 220), font=font)
    x += t.width
sheet.save(dest / "sheet.png")
print("[cleanup] sheet", dest / "sheet.png")
