from PIL import Image, ImageFilter
import numpy as np


def _create_contour(length, scale, rng):
    """Create a smooth random 1D contour in the range [-1, 1]."""

    num_points = max(2, int(length / scale))

    control_x = np.linspace(0, length - 1, num_points)
    control_y = rng.uniform(-1, 1, num_points)

    x = np.arange(length)

    # Interpolate between random control points
    contour = np.interp(x, control_x, control_y)

    # Smooth the contour
    contour_img = Image.fromarray(((contour + 1) * 127.5).astype(np.uint8))
    contour_img = contour_img.filter(ImageFilter.GaussianBlur(max(1, scale / 10)))
    contour = np.asarray(contour_img, dtype=float).ravel() / 127.5 - 1

    # Normalize after smoothing
    maximum = np.max(np.abs(contour))

    if maximum > 0:
        contour /= maximum

    return contour


def fade_edges(image, fade_percent=5, ruggedness=0.3, roughness_percent=50, seed=None):
    """
    Fade the edges of an image to transparency with irregular contours.

    Parameters
    ----------
    image : PIL.Image
        Input image.

    fade_percent : float
        Width of the fade as a percentage of the corresponding
        image dimension.

    ruggedness : float
        Amount by which the fade boundary varies.

        0.0 = perfectly straight
        0.3 = subtle irregularity
        0.7 = strong irregularity
        1.0 = very rough

    roughness_percent : float
        Size of the irregular features relative to the fade width.

        20 = small/frequent irregularities
        50 = medium irregularities
        100 = broad irregularities

    seed : int | None
        Optional random seed for reproducible results.
    """

    image = image.convert("RGBA")

    width, height = image.size
    rng = np.random.default_rng(seed)

    fade_x = width * fade_percent / 100
    fade_y = height * fade_percent / 100

    # Create coordinate grids
    y, x = np.mgrid[0:height, 0:width]

    # ------------------------------------------------------------
    # Create random contour for each edge
    # ------------------------------------------------------------

    # Roughness is relative to the fade width.
    horizontal_scale = max(1, fade_x * roughness_percent / 100)
    vertical_scale = max(1, fade_y * roughness_percent / 100)
    top_contour = _create_contour(width, horizontal_scale, rng)
    bottom_contour = _create_contour(width, horizontal_scale, rng)
    left_contour = _create_contour(height, vertical_scale, rng)
    right_contour = _create_contour(height, vertical_scale, rng)

    # ------------------------------------------------------------
    # Convert contour into boundary displacement
    # ------------------------------------------------------------

    # Maximum boundary displacement.
    horizontal_variation = fade_x * 0.5 * ruggedness
    vertical_variation = fade_y * 0.5 * ruggedness

    # One value per coordinate along each edge.
    top_boundary = fade_y + top_contour * vertical_variation
    bottom_boundary = fade_y + bottom_contour * vertical_variation
    left_boundary = fade_x + left_contour * horizontal_variation
    right_boundary = fade_x + right_contour * horizontal_variation

    # ------------------------------------------------------------
    # Calculate alpha for each edge
    # ------------------------------------------------------------

    top_alpha = np.clip(y / top_boundary[np.newaxis, :], 0, 1)
    bottom_alpha = np.clip((height - 1 - y) / bottom_boundary[np.newaxis, :], 0, 1)
    left_alpha = np.clip(x / left_boundary[:, np.newaxis], 0, 1)
    right_alpha = np.clip((width - 1 - x) / right_boundary[:, np.newaxis], 0, 1)

    # ------------------------------------------------------------
    # Combine all four edges
    # ------------------------------------------------------------

    alpha = np.minimum.reduce([top_alpha, bottom_alpha, left_alpha, right_alpha])
    alpha = (alpha * 255).astype(np.uint8)

    # ------------------------------------------------------------
    # Preserve existing alpha
    # ------------------------------------------------------------

    original_alpha = np.asarray(image.getchannel("A"), dtype=np.uint16)
    alpha = np.minimum(alpha.astype(np.uint16), original_alpha).astype(np.uint8)
    image.putalpha(Image.fromarray(alpha, mode="L"))

    return image
