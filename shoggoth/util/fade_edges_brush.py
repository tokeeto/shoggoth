from PIL import Image, ImageFilter
import numpy as np


def _create_contour(length, scale, rng):
    """Create a smooth random 1D contour in the range [-1, 1]."""

    num_points = max(2, int(length / scale))

    control_x = np.linspace(0, length - 1, num_points)
    control_y = rng.uniform(-1, 1, num_points)

    x = np.arange(length)
    contour = np.interp(x, control_x, control_y)

    contour_img = Image.fromarray(((contour + 1) * 127.5).astype(np.uint8))
    contour_img = contour_img.filter(ImageFilter.GaussianBlur(max(1, scale / 10)))
    contour = np.asarray(contour_img, dtype=float).ravel() / 127.5 - 1

    maximum = np.max(np.abs(contour))
    if maximum > 0:
        contour /= maximum

    return contour


def _fractal_contour_1d(length, base_scale, rng, octaves=4, persistence=0.55):
    """
    Multi-octave version of _create_contour: sums several contours at
    decreasing scale/increasing frequency. This is what gives a brush
    edge its 'detail within detail' look instead of one smooth wave.
    """
    result = np.zeros(length)
    amplitude = 1.0
    total_amplitude = 0.0
    scale = base_scale

    for _ in range(octaves):
        result += amplitude * _create_contour(length, max(1, scale), rng)
        total_amplitude += amplitude
        amplitude *= persistence
        scale *= 0.5  # each octave adds finer detail

    result /= total_amplitude
    maximum = np.max(np.abs(result))
    if maximum > 0:
        result /= maximum

    return result


def _smooth_min(a, b, k):
    """
    Polynomial smooth minimum. Behaves like np.minimum(a, b) except where
    a and b are close in value, where it blends them with a rounded
    transition instead of a hard crease. k controls the blend width.
    """
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def _combine_edges_rounded(edges, k):
    """Combine a list of per-edge alpha arrays with a rounded (smooth) min."""
    result = edges[0]
    for edge in edges[1:]:
        result = _smooth_min(result, edge, k)
    return result


def _value_noise_2d(shape, scale_y, scale_x, rng):
    """Smooth 2D noise via a coarse random grid resized up (cheap Perlin-ish noise)."""
    h, w = shape
    low_h = max(2, int(h / scale_y))
    low_w = max(2, int(w / scale_x))
    low = rng.uniform(-1, 1, (low_h, low_w))

    img = Image.fromarray(((low + 1) * 127.5).astype(np.uint8), mode="L")
    img = img.resize((w, h), Image.BICUBIC)
    arr = np.asarray(img, dtype=float) / 127.5 - 1
    return arr


def _fractal_noise_2d(shape, scale_y, scale_x, rng, octaves=3, persistence=0.5):
    result = np.zeros(shape)
    amplitude = 1.0
    total_amplitude = 0.0
    sy, sx = scale_y, scale_x

    for _ in range(octaves):
        result += amplitude * _value_noise_2d(shape, max(2, sy), max(2, sx), rng)
        total_amplitude += amplitude
        amplitude *= persistence
        sy *= 0.5
        sx *= 0.5

    result /= total_amplitude
    maximum = np.max(np.abs(result))
    if maximum > 0:
        result /= maximum

    return result


def fade_edges_brush(
    image,
    fade_percent=8,
    ruggedness=0.4,
    roughness_percent=50,
    bristle_strength=0.6,
    bristle_length=2.5,
    bristle_density=18,
    grain_strength=0.15,
    grain_scale=6,
    fade_curve=1.6,
    final_blur=1.5,
    corner_round=1.8,
    seed=None,
):
    """
    Fade the edges of an image to transparency with a hand-brushed look:
    irregular boundary + inward-reaching bristle streaks + fine grain.

    New parameters vs. the plain version
    -------------------------------------
    bristle_strength : float
        How strongly the streaky noise perturbs the transition band.
        0 = off (same as a plain irregular fade). 0.5-0.8 = visible
        brush fingers. 1.0+ = very ragged.

    bristle_length : float
        How far the streaks stretch relative to their width. Higher
        values = longer trailing fingers, like a drier brush.

    bristle_density : float
        Controls how many streaks appear per unit length. Lower =
        fewer, fatter streaks. Higher = many thin hairs.

    grain_strength : float
        Amount of fine textural noise mixed into the translucent band
        (paper/canvas grain). 0 = off.

    grain_scale : float
        Size of the grain speckles in pixels.

    fade_curve : float
        Exponent applied to the alpha ramp. 1.0 = linear (original
        behaviour, tends to look like a hard-edged rectangle with a
        thin fuzzy fringe). Higher values (1.4-2.2) push more of the
        transition band toward transparent before it snaps to fully
        opaque, so the fade reads as soft/gradual rather than abrupt.
        This is usually the single biggest lever for "edge still looks
        too hard."

    final_blur : float
        Radius (px) of a Gaussian blur applied to the finished alpha
        mask. Smooths any residual stair-stepping introduced by the
        noise fields, without softening the RGB content itself. 0 = off.

    corner_round : float
        How much to round the corners where two edge fades meet.
        0 = hard min (original behaviour, sharp/spiky corners where
        edges + bristles overlap). Useful range is roughly 1-4; try
        1.5-2.5 for a natural rounded corner, higher to round more
        aggressively (this can start to eat into straight edge
        sections near the corners at high values).
    """

    image = image.convert("RGBA")
    width, height = image.size
    rng = np.random.default_rng(seed)

    fade_x = width * fade_percent / 100
    fade_y = height * fade_percent / 100

    y, x = np.mgrid[0:height, 0:width]

    # ------------------------------------------------------------
    # Structural boundary: fractal contour instead of single-scale
    # ------------------------------------------------------------
    horizontal_scale = max(1, fade_x * roughness_percent / 100)
    vertical_scale = max(1, fade_y * roughness_percent / 100)

    top_contour = _fractal_contour_1d(width, horizontal_scale, rng)
    bottom_contour = _fractal_contour_1d(width, horizontal_scale, rng)
    left_contour = _fractal_contour_1d(height, vertical_scale, rng)
    right_contour = _fractal_contour_1d(height, vertical_scale, rng)

    horizontal_variation = fade_x * 0.5 * ruggedness
    vertical_variation = fade_y * 0.5 * ruggedness

    top_boundary = fade_y + top_contour * vertical_variation
    bottom_boundary = fade_y + bottom_contour * vertical_variation
    left_boundary = fade_x + left_contour * horizontal_variation
    right_boundary = fade_x + right_contour * horizontal_variation

    top_alpha = y / top_boundary[np.newaxis, :]
    bottom_alpha = (height - 1 - y) / bottom_boundary[np.newaxis, :]
    left_alpha = x / left_boundary[:, np.newaxis]
    right_alpha = (width - 1 - x) / right_boundary[:, np.newaxis]
    # NOTE: intentionally left unclamped here — the rounded combine below
    # needs the raw ramp values to stay correct in the deep interior
    # (see _combine_edges_rounded). Clamping happens right after.

    base_alpha = _combine_edges_rounded(
        [top_alpha, bottom_alpha, left_alpha, right_alpha], k=corner_round
    )
    # smooth-min can dip slightly outside [0, 1] in the blend region; clamp
    base_alpha = np.clip(base_alpha, 0.0, 1.0)

    # Ease the ramp so the transition reads as a soft dissolve rather
    # than "solid, then a thin fringe, then a hard stop."
    if fade_curve != 1.0:
        base_alpha = base_alpha ** fade_curve

    # ------------------------------------------------------------
    # Bristle streaks: anisotropic noise per edge, stretched inward,
    # only allowed to act inside the transition band (not on solid
    # interior, not past fully-transparent margin).
    # ------------------------------------------------------------
    if bristle_strength > 0:
        band_weight = base_alpha * (1 - base_alpha) * 4  # 0 at 0/1, peaks at 0.5

        # streaks elongated along the inward direction of each edge:
        # small scale across the edge (many fingers), large scale along it
        top_noise = _fractal_noise_2d(
            (height, width), scale_y=fade_y * bristle_length, scale_x=fade_x / bristle_density * 10, rng=rng
        )
        bottom_noise = _fractal_noise_2d(
            (height, width), scale_y=fade_y * bristle_length, scale_x=fade_x / bristle_density * 10, rng=rng
        )
        left_noise = _fractal_noise_2d(
            (height, width), scale_y=fade_y / bristle_density * 10, scale_x=fade_x * bristle_length, rng=rng
        )
        right_noise = _fractal_noise_2d(
            (height, width), scale_y=fade_y / bristle_density * 10, scale_x=fade_x * bristle_length, rng=rng
        )

        # weight each edge's noise by proximity to that specific edge
        top_w = np.clip(1 - y / (top_boundary[np.newaxis, :] + 1e-6), 0, 1)
        bottom_w = np.clip(1 - (height - 1 - y) / (bottom_boundary[np.newaxis, :] + 1e-6), 0, 1)
        left_w = np.clip(1 - x / (left_boundary[:, np.newaxis] + 1e-6), 0, 1)
        right_w = np.clip(1 - (width - 1 - x) / (right_boundary[:, np.newaxis] + 1e-6), 0, 1)

        bristle = (
            top_noise * top_w
            + bottom_noise * bottom_w
            + left_noise * left_w
            + right_noise * right_w
        )
        # normalize contribution so overlapping corners don't blow up
        weight_sum = np.clip(top_w + bottom_w + left_w + right_w, 1e-6, None)
        bristle /= weight_sum

        base_alpha = np.clip(
            base_alpha * (1 + bristle_strength * bristle * band_weight), 0, 1
        )

    # ------------------------------------------------------------
    # Fine grain across the translucent band (paper/canvas texture)
    # ------------------------------------------------------------
    if grain_strength > 0:
        grain = _value_noise_2d((height, width), grain_scale, grain_scale, rng)
        # only perturb the translucent band itself, never the solid
        # interior (alpha == 1) or the fully-transparent margin (alpha == 0)
        grain_weight = base_alpha * (1 - base_alpha) * 4
        base_alpha = np.clip(base_alpha * (1 + grain_strength * grain * grain_weight), 0, 1)

    alpha = (base_alpha * 255).astype(np.uint8)

    # Smooth away any residual jaggedness from the noise fields before
    # compositing (this softens the mask only, not the image content).
    if final_blur > 0:
        alpha = np.asarray(
            Image.fromarray(alpha, mode="L").filter(ImageFilter.GaussianBlur(final_blur))
        )

    # ------------------------------------------------------------
    # Preserve existing alpha
    # ------------------------------------------------------------
    original_alpha = np.asarray(image.getchannel("A"), dtype=np.uint16)
    alpha = np.minimum(alpha.astype(np.uint16), original_alpha).astype(np.uint8)
    image.putalpha(Image.fromarray(alpha, mode="L"))

    return image
