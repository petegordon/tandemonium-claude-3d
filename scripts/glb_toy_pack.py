"""Game-ready GLB packing (SandQuest toys): animations + vertex attributes, images untouched (use glb_pack_images.py).

  .venv python scripts/glb_toy_pack.py <in.glb> <out.glb> [--rot-eps 0.002] [--loc-eps 0.001] [--no-quant-normals]
                                       [--keep-scale] [--keep-colors]

Animations (the Blender exporter samples EVERY bone into every clip, so most channels are dead weight):
  * a channel whose values never leave the node's rest transform is dropped (three.js restores the rest pose for
    bones no running clip touches, so layering clips just works: blink owns the lids, walk owns the legs ...);
  * scale channels that stay at 1 are dropped (--keep-scale keeps them);
  * keyframes are thinned (Douglas-Peucker against linear interpolation, --rot-eps per quaternion component,
    --loc-eps metres); the first and last key always stay, so clip durations are kept;
  * rotation outputs are stored as normalized SHORT (core glTF; half the bytes); channels sharing the same key
    times share one input accessor; every animation starts at t = 0.
Meshes: TEXCOORD_n -> normalized UNSIGNED_SHORT, JOINTS_0 -> UNSIGNED_BYTE, WEIGHTS_0 -> normalized UNSIGNED_BYTE
  (re-summed to exactly 1), NORMAL -> normalized BYTE (needs KHR_mesh_quantization; --no-quant-normals keeps float).
  POSITION stays float32 (skinned meshes cannot carry a dequantisation transform). Unused accessors go away, accessor
  min/max is kept only where the spec needs it, and the binary chunk is rebuilt tightly packed.
"""
import json
import struct
import sys

import numpy as np

argv = sys.argv[1:]
SRC, DST = argv[0], argv[1]


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


ROT_EPS = opt("--rot-eps", 0.002)
LOC_EPS = opt("--loc-eps", 0.001)
QUANT_NORMALS = "--no-quant-normals" not in argv
KEEP_SCALE = "--keep-scale" in argv
KEEP_COLORS = "--keep-colors" in argv                     # COLOR_0 as normalized UNSIGNED_BYTE RGB (vertex-painted toys)

CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
NT = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
RT = {v: k for k, v in CT.items()}
TN = {v: k for k, v in NT.items()}

raw = open(SRC, "rb").read()
jlen = struct.unpack("<I", raw[12:16])[0]
g = json.loads(raw[20:20 + jlen])
blen = struct.unpack("<I", raw[20 + jlen:24 + jlen])[0]
binary = raw[28 + jlen:28 + jlen + blen]


def read(ai):
    a = g["accessors"][ai]
    bv = g["bufferViews"][a["bufferView"]]
    dt = np.dtype(CT[a["componentType"]])
    n, w = a["count"], NT[a["type"]]
    off = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    stride = bv.get("byteStride", 0)
    if stride and stride != w * dt.itemsize:
        rows = [np.frombuffer(binary, dt, w, off + i * stride) for i in range(n)]
        arr = np.stack(rows) if n else np.zeros((0, w), dt)
    else:
        arr = np.frombuffer(binary, dt, n * w, off).reshape(n, w)
    out = arr.astype(np.float64)
    if a.get("normalized"):
        out = out / {np.int8: 127, np.uint8: 255, np.int16: 32767, np.uint16: 65535}[CT[a["componentType"]]]
        if dt.kind == "i":
            out = np.maximum(out, -1.0)
    return out if a.get("normalized") or dt == np.float32 else arr.reshape(n, w)


# ---- new buffer ------------------------------------------------------------------------------------------------
out_bin = bytearray()
out_views, out_acc = [], []


def add_view(data: bytes, target=None, stride=None):
    while len(out_bin) % 4:
        out_bin.append(0)
    v = {"buffer": 0, "byteOffset": len(out_bin), "byteLength": len(data)}
    if target:
        v["target"] = target
    if stride:
        v["byteStride"] = stride
    out_bin.extend(data)
    out_views.append(v)
    return len(out_views) - 1


def add_accessor(arr, dtype, typ, normalized=False, target=None, minmax=False):
    arr = np.ascontiguousarray(arr.astype(dtype))
    n = arr.shape[0]
    w = NT[typ]
    elem = w * arr.dtype.itemsize
    stride = None
    data = arr.tobytes()
    if target == 34962 and elem % 4:                     # vertex attributes: 4-byte aligned stride
        pad = (4 - elem % 4)
        rows = arr.view(np.uint8).reshape(n, elem)
        data = np.concatenate([rows, np.zeros((n, pad), np.uint8)], 1).tobytes()
        stride = elem + pad
    a = {"bufferView": add_view(data, target, stride), "componentType": RT[dtype], "count": int(n), "type": typ}
    if normalized:
        a["normalized"] = True
    if minmax:                                           # exact stored values (the validator checks them bit-wise)
        a["min"] = [x.item() for x in np.min(arr, 0).reshape(-1)]
        a["max"] = [x.item() for x in np.max(arr, 0).reshape(-1)]
    out_acc.append(a)
    return len(out_acc) - 1


# ---- meshes ----------------------------------------------------------------------------------------------------
ext_quant = False
for mesh in g.get("meshes", []):
    for p in mesh["primitives"]:
        attrs = {}
        wq = None
        if "WEIGHTS_0" in p["attributes"]:                 # quantize first: joints with a zero weight must read 0
            wq = np.round(read(p["attributes"]["WEIGHTS_0"]) * 255).astype(np.int64)
            for i in range(len(wq)):
                wq[i, int(np.argmax(wq[i]))] += 255 - wq[i].sum()
        for name, ai in p["attributes"].items():
            v = read(ai)
            if name == "POSITION":
                attrs[name] = add_accessor(v, np.float32, "VEC3", target=34962, minmax=True)
            elif name == "NORMAL":
                if QUANT_NORMALS:
                    q = np.clip(np.round(v * 127), -127, 127)
                    attrs[name] = add_accessor(q, np.int8, "VEC3", normalized=True, target=34962)
                    ext_quant = True
                else:
                    attrs[name] = add_accessor(v, np.float32, "VEC3", target=34962)
            elif name.startswith("TEXCOORD"):
                if v.min() >= 0 and v.max() <= 1:
                    attrs[name] = add_accessor(np.round(v * 65535), np.uint16, "VEC2", normalized=True, target=34962)
                else:
                    attrs[name] = add_accessor(v, np.float32, "VEC2", target=34962)
            elif name.startswith("JOINTS"):
                j = np.array(v, dtype=np.int64)
                if wq is not None and name == "JOINTS_0":
                    j[wq == 0] = 0
                dt = np.uint8 if j.max() < 256 else np.uint16
                attrs[name] = add_accessor(j, dt, "VEC4", target=34962)
            elif name == "WEIGHTS_0":
                attrs[name] = add_accessor(wq, np.uint8, "VEC4", normalized=True, target=34962)
            elif name.startswith("COLOR"):
                if not KEEP_COLORS or name != "COLOR_0":
                    continue                               # the geese bake colour into the atlas
                attrs[name] = add_accessor(np.round(v[:, :3] * 255), np.uint8, "VEC3", normalized=True, target=34962)
            else:
                a = g["accessors"][ai]
                attrs[name] = add_accessor(v, CT[a["componentType"]], a["type"], a.get("normalized", False), 34962)
        p["attributes"] = attrs
        if "indices" in p:
            idx = read(p["indices"]).reshape(-1)
            dt = np.uint16 if idx.max() < 65535 else np.uint32
            p["indices"] = add_accessor(idx, dt, "SCALAR", target=34963)
for skin in g.get("skins", []):
    if "inverseBindMatrices" in skin:
        skin["inverseBindMatrices"] = add_accessor(read(skin["inverseBindMatrices"]), np.float32, "MAT4")

# ---- animations --------------------------------------------------------------------------------------------------
def rest(node, path):
    n = g["nodes"][node]
    return np.array(n.get(path, {"translation": [0, 0, 0], "rotation": [0, 0, 0, 1], "scale": [1, 1, 1]}[path]), float)


def thin(t, v, eps):
    """Douglas-Peucker on a vector curve against linear interpolation; returns the kept key indices."""
    keep = {0, len(t) - 1}

    def rec(a, b):
        if b - a < 2:
            return
        u = (t[a + 1:b] - t[a]) / (t[b] - t[a])
        lin = v[a] + u[:, None] * (v[b] - v[a])
        err = np.abs(v[a + 1:b] - lin).max(1)
        i = int(np.argmax(err))
        if err[i] > eps:
            keep.add(a + 1 + i)
            rec(a, a + 1 + i)
            rec(a + 1 + i, b)

    rec(0, len(t) - 1)
    return sorted(keep)


stats = {}
for anim in g.get("animations", []):
    chans, samplers, inputs = [], [], {}
    t0 = min(read(s["input"]).min() for s in anim["samplers"])
    for ch in anim["channels"]:
        s = anim["samplers"][ch["sampler"]]
        path = ch["target"]["path"]
        t = read(s["input"]).reshape(-1) - t0
        v = read(s["output"])
        if s.get("interpolation", "LINEAR") == "CUBICSPLINE":
            v = v.reshape(len(t), 3, -1)[:, 1, :]           # keep the values, drop the tangents
        eps = ROT_EPS if path == "rotation" else LOC_EPS
        r = rest(ch["target"]["node"], path)
        if path == "rotation":                              # consistent hemisphere, starting on the rest side
            if np.dot(v[0], r) < 0:
                v[0] = -v[0]
            for i in range(1, len(v)):
                if np.dot(v[i], v[i - 1]) < 0:
                    v[i] = -v[i]
        if path == "scale" and not KEEP_SCALE and np.abs(v - 1).max() < 1e-4:
            continue
        if np.abs(v - r).max() < eps and (path != "rotation" or np.abs(np.abs(v @ r) - 1).max() < 1e-5):
            continue
        keep = thin(t, v, eps)
        if len(keep) < 2:
            keep = [0, len(t) - 1] if len(t) > 1 else [0]
        tk, vk = t[keep], v[keep]
        key = tuple(np.round(tk, 6))
        if key not in inputs:
            inputs[key] = add_accessor(tk, np.float32, "SCALAR", minmax=True)
        if path == "rotation":
            q = np.clip(np.round(vk / np.linalg.norm(vk, axis=1, keepdims=True) * 32767), -32767, 32767)
            oi = add_accessor(q, np.int16, "VEC4", normalized=True)
        else:
            oi = add_accessor(vk, np.float32, TN[vk.shape[1]])
        samplers.append({"input": inputs[key], "output": oi})           # LINEAR is the default
        chans.append({"sampler": len(samplers) - 1, "target": ch["target"]})
    anim["channels"], anim["samplers"] = chans, samplers
    stats[anim["name"]] = len(chans)
    if not chans:
        print("WARNING: animation", anim["name"], "has no channels left")

# ---- images ------------------------------------------------------------------------------------------------------
for im in g.get("images", []):
    bv = g["bufferViews"][im["bufferView"]]
    im["bufferView"] = add_view(binary[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]])

g["accessors"], g["bufferViews"] = out_acc, out_views
g["buffers"] = [{"byteLength": len(out_bin)}]
if ext_quant:
    for k in ("extensionsUsed", "extensionsRequired"):
        g[k] = sorted(set(g.get(k, [])) | {"KHR_mesh_quantization"})
# skinned mesh nodes sit at the scene root (their parent transform is ignored anyway; validator warning otherwise)
skinned = [i for i, n in enumerate(g["nodes"]) if "skin" in n]
for n in g["nodes"]:
    if "children" in n:
        n["children"] = [c for c in n["children"] if c not in skinned] or None
        if n["children"] is None:
            del n["children"]
for scn in g.get("scenes", []):
    scn["nodes"] = scn.get("nodes", []) + [i for i in skinned if i not in scn.get("nodes", [])]
for n in g["nodes"]:
    n.pop("extras", None)
    for k in ("translation", "rotation", "scale"):
        if k in n:
            n[k] = [round(float(x), 6) for x in n[k]]
g.pop("extras", None)
while len(out_bin) % 4:
    out_bin.append(0)
js = json.dumps(g, separators=(",", ":")).encode()
js += b" " * ((4 - len(js) % 4) % 4)
total = 12 + 8 + len(js) + 8 + len(out_bin)
with open(DST, "wb") as f:
    f.write(struct.pack("<4sII", b"glTF", 2, total))
    f.write(struct.pack("<I4s", len(js), b"JSON") + js)
    f.write(struct.pack("<I4s", len(out_bin), b"BIN\x00") + bytes(out_bin))
print(f"TOYPACK {SRC} -> {DST}: {len(raw) / 1e3:.0f} -> {total / 1e3:.0f} KB (json {len(js) / 1e3:.0f} KB, bin "
      f"{len(out_bin) / 1e3:.0f} KB); channels per clip: {stats}")
