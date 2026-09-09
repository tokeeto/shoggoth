import numpy as np
from scipy.ndimage import distance_transform_edt
from PIL import Image


def distance_fade(art, subject_mask, backdrop, max_distance=150, curve="exp"):
    """
    art:           PIL Image (RGB/RGBA) - the full painted artwork (contains the subject too)
    subject_mask:  PIL Image 'L' - 255 where the main subject is, 0 elsewhere. Same size as art.
    backdrop:      PIL Image (RGB/RGBA) - the template/background + class icon layer, same size.
    max_distance:  px distance from the subject's edge at which the art has fully faded to 0 opacity.
    curve:         "smoothstep" | "linear" | "exp" - shape of the falloff.

    Returns (composited_image, alpha_map) as PIL Images.
    """
    mask = np.array(subject_mask.convert("L")) > 127

    # distance, in pixels, from every point to the nearest subject pixel
    dist = distance_transform_edt(~mask)

    t = np.clip(dist / max_distance, 0, 1)
    if curve == "smoothstep":
        falloff = 1 - (3 * t**2 - 2 * t**3)
    elif curve == "linear":
        falloff = 1 - t
    elif curve == "exp":
        falloff = np.exp(-3 * t)
    else:
        raise ValueError(f"unknown curve: {curve}")

    alpha = np.where(mask, 1.0, falloff)          # subject itself: fully opaque
    alpha_u8 = (alpha * 255).astype(np.uint8)

    art_rgba = np.array(art.convert("RGBA"))
    art_rgba[..., 3] = alpha_u8
    art_layer = Image.fromarray(art_rgba, "RGBA")

    out = backdrop.convert("RGBA")
    out = Image.alpha_composite(out, art_layer)

    return out, Image.fromarray(alpha_u8)
