import numpy as np
from scipy.ndimage import distance_transform_edt
from PIL import Image

# Ease-out cubic exponent for the distance fade: steep drop right past the
# subject shape, flattening to a slow final approach to 0 near the region
# boundary. Deliberately not exposed as a parameter anywhere - the whole
# point of this formula is a single answer that looks reasonable for any
# illustration/region combination without per-card tuning.
_EASE_POWER = 1.01

# Flat alpha applied to the non-subject area of the region, as a floor
# beneath the distance fade - covers user-supplied art that doesn't fit the
# shape/template cleanly, where the shape-distance falloff alone isn't
# enough. Deliberately not exposed as a parameter anywhere.
_BACKGROUND_ALPHA = 0.7

# Width, in pixels, of the fade from _BACKGROUND_ALPHA down to 0 right at
# the region edge.
_EDGE_FADE_WIDTH = 125

# fade_mode values for shape_mask_alpha()/apply_shape_mask(). FADE_FLAT
# mirrors how official card art looks (uniform, subtle); FADE_DISTANCE
# tends to give better results for user-supplied art, which more often
# doesn't fit the shape/template cleanly.
FADE_FLAT = 'flat'
FADE_DISTANCE = 'distance'


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
                      allow_overflow=False, fade_mode=FADE_FLAT):
    """
    Computes an alpha mask where the shape's subject is fully opaque, and
    the rest of the region fades to 0 approaching the region boundary,
    using one of two fade_mode styles:
      - FADE_FLAT: a flat _BACKGROUND_ALPHA, fading to 0 over the last
        _EDGE_FADE_WIDTH pixels approaching the region boundary.
      - FADE_DISTANCE: eases out from the subject's own edge, down to 0 at
        the region boundary.

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

    if fade_mode == FADE_DISTANCE:
        d_shape = distance_transform_edt(~subject)
        d_edge_clamped = np.clip(d_edge, 0, None)
        t = d_shape / np.maximum(d_shape + d_edge_clamped, 1e-6)
        edge_fade = np.clip(d_edge / 150, 0, 1)
        background = np.clip(1 - t, .6, 1)
        background *= edge_fade
    else:
        edge_fade = np.clip(d_edge / _EDGE_FADE_WIDTH, 0, 1)
        background = _BACKGROUND_ALPHA * edge_fade

    alpha = np.where(subject, 1.0, background)
    keep = inside_region | subject if allow_overflow else inside_region
    alpha = np.where(keep, alpha, 0.0)

    return (alpha * 255).astype(np.uint8)


def apply_shape_mask(art, mask, region_x, region_y, region_width, region_height, threshold=128,
                      allow_overflow=False, fade_mode=FADE_FLAT):
    """
    Returns a new RGBA PIL Image: `art` with its alpha channel replaced by
    shape_mask_alpha(...) (intersected with any existing alpha, so
    pre-existing transparency in `art` is preserved).
    """
    alpha_u8 = shape_mask_alpha(mask, region_x, region_y, region_width, region_height, threshold,
                                 allow_overflow, fade_mode)

    art_rgba = np.array(art.convert("RGBA"))
    original_alpha = art_rgba[..., 3].astype(np.uint16)
    art_rgba[..., 3] = np.minimum(alpha_u8.astype(np.uint16), original_alpha).astype(np.uint8)

    return Image.fromarray(art_rgba, "RGBA")
