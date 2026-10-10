"""Generic region recolor: texels in a height band AND a colour window -> a target colour.

Region = faces whose centroid z is within z_frac * height (optionally |x| <= x_max and
y in y_range, metres, model faces -Y). Colour window = HSV limits on the current texels.
Selected texels get the target hue; saturation/value are scaled so their mean matches the
target, which keeps the original shading/detail. Configure several in chars/<char>.json,
e.g. {"fix": "recolor", "label": "iris green->brown", "z_frac": [0.84, 0.9], ...}.
"""
import numpy as np

from .common import hsv_to_rgb, input_image, read_pixels, rgb_to_hsv, texel_mask, write_pixels

NAME = "recolor"
STAGE = "hi"
DEFAULTS = {
    "label": "",
    "z_frac": [0.0, 1.0],     # height band, fraction of model height
    "x_max": None,            # optional |x| limit (m)
    "y_range": None,          # optional [min, max] y (m); front is -Y
    "hue_deg": [0, 360],      # colour window on the current texture
    "sat": [0.0, 1.0],
    "val": [0.0, 1.0],
    "target_rgb": [0.5, 0.5, 0.5],  # sRGB 0..1
    "keep_shading": True,     # False = flat fill with target_rgb
}


def apply(ctx, label, z_frac, x_max, y_range, hue_deg, sat, val, target_rgb, keep_shading):
    img = input_image(ctx.ob, "Base Color")
    px = read_pixels(img)
    h, w = px.shape[:2]

    def pick(c):
        z = c[:, 2] / ctx.height
        m = (z >= z_frac[0]) & (z <= z_frac[1])
        if x_max is not None:
            m &= np.abs(c[:, 0]) <= x_max
        if y_range is not None:
            m &= (c[:, 1] >= y_range[0]) & (c[:, 1] <= y_range[1])
        return m

    region = texel_mask(ctx.ob, w, h, pick)
    rgb = px[..., :3]
    hsv = rgb_to_hsv(rgb)
    hue = hsv[..., 0] * 360
    in_hue = (hue >= hue_deg[0]) & (hue <= hue_deg[1]) if hue_deg[0] <= hue_deg[1] else \
        (hue >= hue_deg[0]) | (hue <= hue_deg[1])  # wrap-around window, e.g. [340, 20] for reds
    lit = (region & in_hue & (hsv[..., 1] >= sat[0]) & (hsv[..., 1] <= sat[1])
           & (hsv[..., 2] >= val[0]) & (hsv[..., 2] <= val[1]))
    if not lit.any():
        return {"label": label, "region_texels": int(region.sum()), "recolored": 0,
                "note": "no texels matched the colour window"}
    target = np.array(target_rgb, np.float32)
    before = rgb[lit].mean(0)
    if keep_shading:
        t_hsv = rgb_to_hsv(target[None])[0]
        sel = hsv[lit]
        m_hsv = sel.mean(0)
        sel[:, 0] = t_hsv[0]
        sel[:, 1] = np.clip(sel[:, 1] * t_hsv[1] / max(m_hsv[1], 1e-3), 0, 1)
        sel[:, 2] = np.clip(sel[:, 2] * t_hsv[2] / max(m_hsv[2], 1e-3), 0, 1)
        rgb[lit] = hsv_to_rgb(sel)
    else:
        rgb[lit] = target
    px[..., :3] = rgb
    write_pixels(img, px)
    return {"label": label, "region_texels": int(region.sum()), "recolored": int(lit.sum()),
            "before_rgb": before.round(3).tolist(), "after_rgb": rgb[lit].mean(0).round(3).tolist()}
