import numpy as np
from PIL import Image

_BACKGROUND_ALPHA = 0.4
_EDGE_FADE_WIDTH = 125


def _mask_luminance(mask, size):
    """
    Flatten a shape-image mask onto a white background, then read its
    luminance. This lets the mask be painted either way: white background
    around the subject, OR a transparent background around the subject -
    both collapse to "white" once composited, so only the black subject
    area survives.
    """
    if mask.size != size:
        mask = mask.resize(size, Image.LANCZOS)

    white_bg = Image.new("RGBA", size, (255, 255, 255, 255))
    flattened = Image.alpha_composite(white_bg, mask.convert("RGBA"))
    return np.array(flattened.convert("L"))


def subject_mask(mask, threshold=128):
    """Boolean array (same size as `mask`), True where the shape-image mask
    marks the subject - see _mask_luminance for how white/transparent
    backgrounds are both treated as "not the subject"."""
    luminance = _mask_luminance(mask, mask.size)
    return luminance < threshold


def shape_mask_alpha(mask, region_x, region_y, region_width, region_height, threshold=128,
                      allow_overflow=False):
    """
    Computes an alpha mask where the shape's subject is fully opaque and the
    rest of the region is _BACKGROUND_ALPHA, fading to 0 over the last
    _EDGE_FADE_WIDTH pixels approaching the region boundary.

    allow_overflow: When True, the subject overrules boundaries, making it
    stay opaque outside the region.
    """
    subject = subject_mask(mask, threshold)

    h, w = subject.shape
    yy, xx = np.mgrid[0:h, 0:w]
    left = xx - region_x
    right = (region_x + region_width - 1) - xx
    top = yy - region_y
    bottom = (region_y + region_height - 1) - yy
    d_edge = np.minimum(np.minimum(left, right), np.minimum(top, bottom))
    inside_region = d_edge >= 0

    edge_fade = np.clip(d_edge / _EDGE_FADE_WIDTH, 0, 1)
    alpha = np.where(subject, 1.0, _BACKGROUND_ALPHA * edge_fade)
    keep = inside_region | subject if allow_overflow else inside_region
    alpha = np.where(keep, alpha, 0.0)

    return (alpha * 255).astype(np.uint8)


def apply_shape_mask(art, mask, region_x, region_y, region_width, region_height, threshold=128,
                      allow_overflow=False):
    """
    Returns a new RGBA PIL Image: `art` with its alpha channel replaced by
    shape_mask_alpha(...) (intersected with any existing alpha, so
    pre-existing transparency in `art` is preserved).
    """
    alpha_u8 = shape_mask_alpha(mask, region_x, region_y, region_width, region_height, threshold,
                                 allow_overflow)

    art_rgba = np.array(art.convert("RGBA"))
    original_alpha = art_rgba[..., 3].astype(np.uint16)
    art_rgba[..., 3] = np.minimum(alpha_u8.astype(np.uint16), original_alpha).astype(np.uint8)

    return Image.fromarray(art_rgba, "RGBA")
