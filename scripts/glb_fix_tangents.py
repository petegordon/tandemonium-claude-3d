"""Replace zero-length TANGENTs in a GLB (MikkTSpace emits 0 on zero-area UV triangles).

Each bad tangent becomes a unit vector orthogonal to that vertex's normal (w = +1),
which keeps the glTF validator clean (ACCESSOR_VECTOR3_NON_UNIT). Edits in place.

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
    open(path, "wb").write(data)
    print(f"fixed {fixed} zero tangents in {path}")


if __name__ == "__main__":
    main(sys.argv[1])
