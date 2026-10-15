"""Rich text rendering, checked on the rendered pixels.

These need the asset pack's fonts (marker `assets`): skipped in CI, required
by scripts/release.py.
"""
import pytest
from PIL import Image

pytestmark = pytest.mark.assets

DEFAULT_INK = (35, 31, 32)  # RichTextRenderer's default fill, #231f20
WIDTH, HEIGHT = 600, 100


@pytest.fixture(scope='module')
def rich_text():
    from shoggoth.renderer import CardRenderer
    return CardRenderer().rich_text


def render(rich_text, text):
    from shoggoth.renderer import Region
    image = Image.new('RGB', (WIDTH, HEIGHT), 'white')
    rich_text.render_text(image, text, Region({'x': 10, 'y': 10, 'width': WIDTH - 20, 'height': HEIGHT - 20}),
                          font_size=40, min_font_size=40)
    return image


def ink(image):
    """The set of (x, y) of every pixel that isn't white: where text was drawn."""
    return {(x, y) for y in range(image.height) for x in range(image.width) if image.getpixel((x, y)) != (255, 255, 255)}


def ink_color(image):
    """The color the text was drawn in: the most common non-white color (glyph
    interiors; anti-aliased edges are blends spread over many shades)."""
    return max((n, color) for n, color in image.getcolors(WIDTH * HEIGHT) if color != (255, 255, 255))[1]


@pytest.mark.parametrize('tag_value, rgb', [
    ('red', (255, 0, 0)),
    ('#00a000', (0, 160, 0)),
    ('rgb(0, 0, 255)', (0, 0, 255)),
])
def test_color_tag_colors_text(rich_text, tag_value, rgb):
    colored = render(rich_text, f'<color "{tag_value}">Colored text</color>')
    plain = render(rich_text, 'Colored text')

    color = ink_color(colored)
    assert color == rgb, f'text drawn in {color}, expected {rgb}'
    # the tag itself isn't drawn, and the text is laid out exactly as without it
    differing = len(ink(colored) ^ ink(plain))
    assert differing == 0, f'{differing} pixels differ from the same text rendered without the tag'


def test_color_ends_at_closing_tag(rich_text):
    image = render(rich_text, '<color "red">Red</color> Default')
    colors = {color for _, color in image.getcolors(WIDTH * HEIGHT)}
    assert (255, 0, 0) in colors, 'no red text'
    assert DEFAULT_INK in colors, 'text after </color> is not in the default color'


def test_nested_color_returns_to_outer_color(rich_text):
    image = render(rich_text, '<color "red">Red <color "blue">Blue</color> Red again</color>')
    nested = render(rich_text, '<color "red">Red Red again</color>')
    red_pixels = {color: n for n, color in image.getcolors(WIDTH * HEIGHT)}.get((255, 0, 0), 0)
    assert (0, 0, 255) in {color for _, color in image.getcolors(WIDTH * HEIGHT)}, 'no blue text'
    assert red_pixels > ink_color_count(nested) / 2, 'text after the inner </color> is not red again'


def test_unknown_color_keeps_default_and_hides_tag(rich_text):
    colored = render(rich_text, '<color "not a color">Some text</color> more')
    plain = render(rich_text, 'Some text more')
    assert ink_color(colored) == DEFAULT_INK
    differing = len(ink(colored) ^ ink(plain))
    assert differing == 0, f'{differing} pixels differ from the same text rendered without the tag'


def ink_color_count(image):
    return max(n for n, color in image.getcolors(WIDTH * HEIGHT) if color != (255, 255, 255))


def ink_rows(image):
    """{y: (min x, max x)} of every row with ink."""
    rows = {}
    for x, y in ink(image):
        low, high = rows.get(y, (x, x))
        rows[y] = (min(low, x), max(high, x))
    return rows


@pytest.mark.parametrize('markup', ['<u>Underline</u>', '<color "red"><u>Underline</u></color>'])
def test_underline_sits_just_below_the_text(rich_text, markup):
    # "Underline" has no descenders: the plain text's lowest ink is the baseline
    plain_rows = ink_rows(render(rich_text, 'Underline'))
    underlined_rows = ink_rows(render(rich_text, markup))
    baseline = max(plain_rows)
    line_rows = sorted(y for y in underlined_rows if y not in plain_rows)
    assert line_rows, 'no underline drawn'

    gap = line_rows[0] - baseline
    assert 1 <= gap <= 40 * 0.25, f'underline starts {gap}px below the baseline of 40px text'
    text_left = min(left for left, _ in plain_rows.values())
    text_right = max(right for _, right in plain_rows.values())
    left, right = underlined_rows[line_rows[0]]
    assert abs(left - text_left) <= 3 and abs(right - text_right) <= 3, 'underline does not span the text'
