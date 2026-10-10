"""Tidy TANGENTs in a GLB for the glTF validator. Edits in place.

- Zero-length tangents (MikkTSpace emits 0 on zero-area UV triangles) become a unit vector
  orthogonal to the vertex normal, w = +1 (ACCESSOR_VECTOR3_NON_UNIT).
- Primitives whose material has no normal map drop their TANGENT attribute
  (UNUSED_MESH_TANGENT), e.g. the eye parts attached to the game mesh.

  python scripts/glb_fix_tangents.py out/male-goose/male_goose_game.glb
"""
import json
import struct
import sys

import numpy as np

COMP = {5126: np.float32}


def main(path):
    data = bytearray(open(path, "rb").read())
    jlen = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + jlen])
    bin_off = 20 + jlen + 8  # skip BIN chunk header
    fixed = 0
    for mesh in gltf["meshes"]:
        for prim in mesh["primitives"]:
            attrs = prim["attributes"]
            if "TANGENT" not in attrs:
                continue
            views = []
            for key, n in (("TANGENT", 4), ("NORMAL", 3)):
                acc = gltf["accessors"][attrs[key]]
                bv = gltf["bufferViews"][acc["bufferView"]]
                start = bin_off + bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
                stride = bv.get("byteStride", n * 4)
                assert stride == n * 4, "interleaved buffers not supported"
                views.append(np.frombuffer(data, np.float32, acc["count"] * n, start).reshape(-1, n))
            tan, nrm = views[0].copy(), views[1]
            bad = np.linalg.norm(tan[:, :3], axis=1) < 1e-6
            if bad.any():
                n = nrm[bad]
                helper = np.where(np.abs(n[:, :1]) < 0.9, [[1.0, 0, 0]], [[0, 1.0, 0]])
                t = np.cross(n, helper)
                t /= np.linalg.norm(t, axis=1, keepdims=True)
                tan[bad, :3], tan[bad, 3] = t, 1.0
                acc = gltf["accessors"][attrs["TANGENT"]]
                bv = gltf["bufferViews"][acc["bufferView"]]
                start = bin_off + bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
                data[start:start + tan.nbytes] = tan.astype(np.float32).tobytes()
                fixed += int(bad.sum())
    dropped = 0
    mats = gltf.get("materials", [])
    for mesh in gltf["meshes"]:
        for prim in mesh["primitives"]:
            mat = mats[prim["material"]] if "material" in prim else {}
            if "TANGENT" in prim["attributes"] and "normalTexture" not in mat:
                del prim["attributes"]["TANGENT"]
                dropped += 1
    if dropped:                                   # rewrite the container with the new JSON chunk
        js = json.dumps(gltf, separators=(",", ":")).encode()
        js += b" " * (-len(js) % 4)
        rest = data[20 + jlen:]                   # BIN chunk (header + payload)
        out = bytearray(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + len(rest)))
        out += struct.pack("<II", len(js), 0x4E4F534A) + js + rest
        data = out
    open(path, "wb").write(data)
    print(f"fixed {fixed} zero tangents, dropped {dropped} unused TANGENT attributes in {path}")


if __name__ == "__main__":
    main(sys.argv[1])
