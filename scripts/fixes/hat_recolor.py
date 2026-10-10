"""Shift a hat's felt colour to match the reference sheet (male v1: olive bowler -> brown).

Selects texels of faces whose centroid is above z_frac * height, keeps only texels inside
the hue/saturation/value window (so the black band, cream cheek patch tucked under the
brim and eye highlights are untouched), then sets their hue to the reference's and
scales saturation/value so the hat's mean matches the reference hat region.
"""
import numpy as np

from .common import hsv_to_rgb, input_image, load_ref, read_pixels, rgb_to_hsv, texel_mask, write_pixels

NAME = "hat_recolor"
STAGE = "hi"
DEFAULTS = {
    "z_frac": 0.88,           # hat = faces above this fraction of model height
    "hue_deg": [15, 65],      # felt hue window on the MODEL texture (olive/brown)
    "sat_min": 0.35,
    "val": [0.12, 0.7],
    "ref_view": "front",      # refs/<char>/prepped/<ref_view>_white.png
    "ref_rgb": None,          # override target colour [r, g, b] (sRGB 0..1) instead of sampling
}


def reference_rgb(ctx, z_frac, ref_view):
    px = load_ref(ctx.ref_dir / f"{ref_view}_white.png")[..., :3]
    fg = px.min(-1) < 0.92  # matte is on white
    rows = np.where(fg.any(1))[0]
    top, bot = rows[0], rows[-1]
    band = np.zeros_like(fg)
    band[top: top + int((bot - top) * (1 - z_frac) * 0.9)] = True
    sel = fg & band & (px.max(-1) > 0.15)
    return px[sel].mean(0), int(sel.sum())


def apply(ctx, z_frac, hue_deg, sat_min, val, ref_view, ref_rgb):
    img = input_image(ctx.ob, "Base Color")
    px = read_pixels(img)
    h, w = px.shape[:2]
    mask = texel_mask(ctx.ob, w, h, lambda c: c[:, 2] > z_frac * ctx.height)
    rgb = px[..., :3]
    hsv = rgb_to_hsv(rgb)
    hue = hsv[..., 0] * 360
    lit = (mask & (hsv[..., 2] > val[0]) & (hsv[..., 2] < val[1]) & (hsv[..., 1] > sat_min)
           & (hue > hue_deg[0]) & (hue < hue_deg[1]))
    if not lit.any():
        return {"recolored": 0, "note": "no felt texels matched the window"}
    if ref_rgb is None:
        target, ref_n = reference_rgb(ctx, z_frac, ref_view)
    else:
        target, ref_n = np.array(ref_rgb, np.float32), 0
    t_hsv = rgb_to_hsv(target[None])[0]
    m_hsv = hsv[lit].mean(0)
    sel = hsv[lit]
    sel[:, 0] = t_hsv[0]
    sel[:, 1] = np.clip(sel[:, 1] * t_hsv[1] / max(m_hsv[1], 1e-3), 0, 1)
    sel[:, 2] = np.clip(sel[:, 2] * t_hsv[2] / max(m_hsv[2], 1e-3), 0, 1)
    model_rgb = rgb[lit].mean(0)
    rgb[lit] = hsv_to_rgb(sel)
    px[..., :3] = rgb
    write_pixels(img, px)
    return {"hat_texels": int(mask.sum()), "recolored": int(lit.sum()),
            "model_rgb": model_rgb.round(3).tolist(), "target_rgb": np.round(target, 3).tolist(),
            "ref_px": ref_n, "hue_deg": round(float(t_hsv[0] * 360), 1),
            "sat_ratio": round(float(t_hsv[1] / m_hsv[1]), 3), "val_ratio": round(float(t_hsv[2] / m_hsv[2]), 3)}
