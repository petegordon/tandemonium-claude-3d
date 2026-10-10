"""Override PBR metallic and/or roughness in a region (e.g. boots: chrome patches -> leather).

Region = faces with centroid in the z_frac height band (optionally |x| <= x_max, y in
y_range), further limited to texels whose BASE COLOUR value (HSV V) is within val (so you
can target e.g. only dark leather). Writes the glTF metallicRoughness texture the model
imported with: G = roughness, B = metallic. None leaves that channel untouched.
"""
import numpy as np

from .common import input_image, read_pixels, rgb_to_hsv, texel_mask, write_pixels

NAME = "material_override"
STAGE = "hi"
DEFAULTS = {
    "label": "",
    "z_frac": [0.0, 1.0],
    "x_max": None,
    "y_range": None,
    "val": [0.0, 1.0],     # base-colour brightness window
    "metallic": None,      # e.g. 0.0
    "roughness": None,     # e.g. 0.55; or [lo, hi] to clamp instead of set
}


def apply(ctx, label, z_frac, x_max, y_range, val, metallic, roughness):
    mr_img = input_image(ctx.ob, "Metallic") or input_image(ctx.ob, "Roughness")
    if mr_img is None:
        return {"label": label, "note": "no metallic/roughness texture; nothing to override"}
    base = read_pixels(input_image(ctx.ob, "Base Color"))
    mr = read_pixels(mr_img)
    h, w = mr.shape[:2]

    def pick(c):
        z = c[:, 2] / ctx.height
        m = (z >= z_frac[0]) & (z <= z_frac[1])
        if x_max is not None:
            m &= np.abs(c[:, 0]) <= x_max
        if y_range is not None:
            m &= (c[:, 1] >= y_range[0]) & (c[:, 1] <= y_range[1])
        return m

    region = texel_mask(ctx.ob, w, h, pick)
    if base.shape[:2] != (h, w):  # sample the brightness window at the MR resolution
        yi = (np.arange(h) * base.shape[0] / h).astype(int)
        xi = (np.arange(w) * base.shape[1] / w).astype(int)
        base = base[yi][:, xi]
    v = rgb_to_hsv(base[..., :3])[..., 2]
    sel = region & (v >= val[0]) & (v <= val[1])
    before = {"metallic_mean": round(float(mr[sel, 2].mean()), 3) if sel.any() else None,
              "metallic_max": round(float(mr[sel, 2].max()), 3) if sel.any() else None,
              "roughness_mean": round(float(mr[sel, 1].mean()), 3) if sel.any() else None}
    if metallic is not None:
        mr[sel, 2] = metallic
    if roughness is not None:
        if isinstance(roughness, list):
            mr[sel, 1] = np.clip(mr[sel, 1], roughness[0], roughness[1])
        else:
            mr[sel, 1] = roughness
    write_pixels(mr_img, mr)
    after = {"metallic_mean": round(float(mr[sel, 2].mean()), 3) if sel.any() else None,
             "roughness_mean": round(float(mr[sel, 1].mean()), 3) if sel.any() else None}
    return {"label": label, "texels": int(sel.sum()), "image": mr_img.name, "before": before, "after": after}
