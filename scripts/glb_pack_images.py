"""Delivery packing (P5.5): re-encode a GLB's embedded textures smaller, nothing else touched.

  .venv python scripts/glb_pack_images.py <in.glb> <out.glb> [--max 1024] [--quality 88]

Opaque images (RGB, or alpha fully 255) -> JPEG at --quality, downsized so the long side is <= --max; images with
real alpha stay PNG (downsized + optimised). The binary chunk is rebuilt with every bufferView re-packed (4-byte
aligned); accessors, meshes, skins and animations are byte-identical.
"""
import io
import json
import struct
import sys

from PIL import Image

argv = sys.argv[1:]
src, dst = argv[0], argv[1]
MAX = int(argv[argv.index("--max") + 1]) if "--max" in argv else 1024
Q = int(argv[argv.index("--quality") + 1]) if "--quality" in argv else 88

b = open(src, "rb").read()
jlen = struct.unpack("<I", b[12:16])[0]
g = json.loads(b[20:20 + jlen])
bin_off = 20 + jlen + 8
binary = b[bin_off:bin_off + struct.unpack("<I", b[20 + jlen:24 + jlen])[0]]

views = [binary[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]] for v in g["bufferViews"]]
before = sum(len(views[im["bufferView"]]) for im in g.get("images", []))
for im in g.get("images", []):
    pi = Image.open(io.BytesIO(views[im["bufferView"]]))
    pi.load()
    if max(pi.size) > MAX:
        f = MAX / max(pi.size)
        pi = pi.resize((round(pi.width * f), round(pi.height * f)), Image.LANCZOS)
    has_alpha = pi.mode in ("RGBA", "LA") and pi.getchannel("A").getextrema()[0] < 255
    out = io.BytesIO()
    if has_alpha or pi.mode in ("1", "P", "L"):
        pi.save(out, "PNG", optimize=True)
        im["mimeType"] = "image/png"
    else:
        pi.convert("RGB").save(out, "JPEG", quality=Q, optimize=True)
        im["mimeType"] = "image/jpeg"
    views[im["bufferView"]] = out.getvalue()

blob = bytearray()
for v, data in zip(g["bufferViews"], views):
    while len(blob) % 4:
        blob.append(0)
    v["byteOffset"] = len(blob)
    v["byteLength"] = len(data)
    blob += data
while len(blob) % 4:
    blob.append(0)
g["buffers"][0]["byteLength"] = len(blob)
js = json.dumps(g, separators=(",", ":")).encode()
js += b" " * ((4 - len(js) % 4) % 4)
total = 12 + 8 + len(js) + 8 + len(blob)
with open(dst, "wb") as f:
    f.write(struct.pack("<4sII", b"glTF", 2, total))
    f.write(struct.pack("<I4s", len(js), b"JSON") + js)
    f.write(struct.pack("<I4s", len(blob), b"BIN\x00") + bytes(blob))
after = sum(len(views[im["bufferView"]]) for im in g.get("images", []))
print(f"PACK {src} -> {dst}: {len(b) / 1e6:.1f} -> {total / 1e6:.1f} MB (images {before / 1e6:.1f} -> {after / 1e6:.1f} MB)")
