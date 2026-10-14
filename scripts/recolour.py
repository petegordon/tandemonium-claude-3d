"""Colourway remap shared by the review renders (outfit_beauty.py --recolour) and the game data (colourway_params.py):
each garment material's albedo (texture x baseColorFactor, the texels under its own UVs) is moved to a target sRGB
colour by a hue / saturation / value remap -- Blender's Hue/Saturation node, mirrored in the game's shader
(tandemonium js/goose-colourways.js) -- so weave, argyle, buttons and seams keep their detail. Flat-colour materials
take the target colour itself. Targets: refs/colourways.json ("piece" or "piece:material-substring" keys)."""
import colorsys
import re

import numpy as np


def lin(c):
    c = np.asarray(c, float) / 255.0
    return np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)


def way_targets(W, way, seat):
    return next(p for p in W["pairs"].values() if way in p["ways"])["ways"][way].get(seat, {})


def target_for(targets, piece, mat):
    hit = [k for k in targets if ":" in k and k.split(":")[0] == piece and k.split(":")[1] in mat]
    return targets[hit[0]] if hit else targets.get(piece)


def gltf_name(mat):
    return re.sub(r"\.\d{3}$", "", mat.name)      # Blender's duplicate suffix -> the glTF material name


def material_params(o, m, tgt):
    """{'color': [r, g, b] linear} for a flat material, {'hsv': [hue, sat, val]} (Blender node inputs; hue 0.5 = none)
    for a textured one, or None when the material has no base colour to remap."""
    nt = m.node_tree
    bs = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None) if nt else None
    if bs is None:
        return None
    link = next((l for l in nt.links if l.to_socket == bs.inputs["Base Color"]), None)
    tl = lin(tgt)
    if link is None:
        return {"color": [round(float(x), 5) for x in tl]}
    src, fac = link.from_node, np.ones(3)
    if src.type == "MIX":                           # glTF import: texture x baseColorFactor as a MULTIPLY mix
        ins = [i for i in src.inputs if i.enabled and i.name in ("A", "B")]
        lk = next((i for i in ins if i.is_linked), None)
        un = next((i for i in ins if not i.is_linked), None)
        if un is not None:
            fac = np.array(un.default_value[:3])
        src = lk.links[0].from_node if lk is not None else None
    tex = src if (src is not None and src.type == "TEX_IMAGE" and src.image) else None
    if tex is None:
        return None
    iw, ih = tex.image.size
    img = np.array(tex.image.pixels[:]).reshape(ih, iw, 4)
    mi = list(o.data.materials).index(m)
    uvl = o.data.uv_layers.active.data
    uv = np.array([uvl[li].uv[:] for p in o.data.polygons if p.material_index == mi for li in p.loop_indices][::3])
    if not len(uv):
        return None
    xs = np.clip((uv[:, 0] % 1.0) * iw, 0, iw - 1).astype(int)
    ys = np.clip((uv[:, 1] % 1.0) * ih, 0, ih - 1).astype(int)
    px = img[ys, xs]
    px = px[px[:, 3] > 0.5][:, :3]
    if tex.image.colorspace_settings.name == "sRGB":
        px = np.where(px > 0.04045, ((px + 0.055) / 1.055) ** 2.4, px / 12.92)
    mean = np.median(px, 0) * fac
    mh, ms, mv = colorsys.rgb_to_hsv(*np.clip(mean, 1e-4, 1))
    th, ts, tv = colorsys.rgb_to_hsv(*np.clip(tl, 1e-4, 1))
    return {"hsv": [round((0.5 + th - mh) % 1.0, 5), round(float(np.clip(ts / max(ms, 0.02), 0, 4)), 5),
                    round(float(np.clip(tv / max(mv, 1e-3), 0, 6)), 5)], "mean": [round(float(x), 4) for x in mean]}


def apply_params(m, p):
    """Apply material_params() to a Blender material (the review renders)."""
    nt = m.node_tree
    bs = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    if "color" in p:
        bs.inputs["Base Color"].default_value = (*p["color"], 1.0)
        return
    link = next(l for l in nt.links if l.to_socket == bs.inputs["Base Color"])
    h = nt.nodes.new("ShaderNodeHueSaturation")
    h.inputs["Hue"].default_value, h.inputs["Saturation"].default_value, h.inputs["Value"].default_value = p["hsv"]
    nt.links.new(link.from_socket, h.inputs["Color"])
    nt.links.new(h.outputs["Color"], bs.inputs["Base Color"])


def recolour_objects(objs, targets, log=print):
    """Remap every garment material of these mesh objects; returns {gltf material name: params}."""
    out = {}
    for o in objs:
        piece = o.name.split(".")[0].split("__")[0]
        for m in o.data.materials:
            if m is None or gltf_name(m) in out:
                continue
            tgt = target_for(targets, piece, m.name)
            if tgt is None:
                continue
            p = material_params(o, m, tgt)
            if p is None:
                continue
            out[gltf_name(m)] = p
            log("RECOLOUR", piece, m.name, p, "->", tgt)
    return out
