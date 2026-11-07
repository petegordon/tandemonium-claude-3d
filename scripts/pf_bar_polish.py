"""Polish the code-drawn cross bar: Qwen restyles a crop around it, only the bar strip (between the collars)
is pasted back, so the bikes cannot move.
  python scripts/pf_bar_polish.py --img refs/pf_tandem_v6/views/bar_high.png --box 740,430,1218,640 --strip 790,511,1168,559 --seeds 7,21
"""
import argparse
import sys
from pathlib import Path

from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfy_job import preflight, run, upload  # noqa: E402
from t2i_outfit import first_image, graph  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--img", required=True)
ap.add_argument("--box", required=True)
ap.add_argument("--strip", required=True)
ap.add_argument("--seeds", default="7,21")
a = ap.parse_args()
src = Path(a.img)
im = Image.open(src).convert("RGB")
bx = tuple(int(v) for v in a.box.split(","))
st = tuple(int(v) for v in a.strip.split(","))
crop = im.crop(bx)
tmp = src.with_name(src.stem + "_crop.png")
crop.save(tmp)
preflight(7.0)
names = [upload(tmp, f"pfb_{src.stem}.png")]
p = ("Picture 1 is a close-up of a straight horizontal decorative frame bar on a Victorian steampunk bicycle. Repaint "
     "ONLY the bar as a polished realistic render: glossy black lacquered straight beam with crisp gold edging lines, "
     "fine raised gold filigree scrollwork along it, and in the centre a round polished gold medallion with a small "
     "embossed goose. Keep the bar perfectly straight and level, exactly the same position, size and thickness; keep "
     "everything else and the plain light-grey background unchanged. No text.")
for s in a.seeds.split(","):
    outs, dt, _ = run(graph(names, p, int(s), 4, f"t2i/pfb_{src.stem}_s{s}"))
    o = Image.open(first_image(outs)).convert("RGB").resize(crop.size, Image.LANCZOS)
    res = im.copy()
    sx0, sy0, sx1, sy1 = st[0] - bx[0], st[1] - bx[1], st[2] - bx[0], st[3] - bx[1]
    piece = o.crop((sx0, sy0, sx1, sy1))
    left = piece.crop((0, 0, piece.width // 2, piece.height))       # exact symmetry
    piece.paste(left.transpose(Image.FLIP_LEFT_RIGHT), (piece.width - piece.width // 2, 0))
    mask = Image.new("L", piece.size, 0)
    mask.paste(255, (3, 3, piece.width - 3, piece.height - 3))
    res.paste(piece, (st[0], st[1]), mask.filter(ImageFilter.GaussianBlur(2)))
    out = src.with_name(f"{src.stem}_pol_s{s}.png")
    res.save(out)
    print("[pf_bar_polish]", out, f"{dt:.0f}s", flush=True)
