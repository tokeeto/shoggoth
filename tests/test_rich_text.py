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


def render(rich_text, text, height=HEIGHT, polygon=None, **options):
    from shoggoth.renderer import Region
    image = Image.new('RGB', (WIDTH, height), 'white')
    rich_text.render_text(image, text, Region({'x': 10, 'y': 10, 'width': WIDTH - 20, 'height': height - 20}),
                          font_size=40, min_font_size=40, polygon=polygon, **options)
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


@pytest.mark.parametrize('markup', [
    '<s>Struck text</s>',
    '<color "red"><s>Struck text</s></color>',
    '<s><font "regular">Struck text</font></s>',  # a found font keeps the outer <s>
])
def test_strikethrough_crosses_the_whole_text(rich_text, markup):
    plain = render(rich_text, 'Struck text')
    struck = render(rich_text, markup)
    rows = ink_rows(plain)
    text_left = min(left for left, _ in rows.values())
    text_right = max(right for _, right in rows.values())

    # the strike is the row that gained the most ink; it lies within the glyphs' height
    gained = ink(struck) - ink(plain)
    assert gained, 'no strikethrough drawn'
    counts = {}
    for _, y in gained:
        counts[y] = counts.get(y, 0) + 1
    strike_y = max(counts, key=counts.get)
    assert min(rows) < strike_y < max(rows), 'strikethrough is outside the text'
    left, right = ink_rows(struck)[strike_y]
    assert abs(left - text_left) <= 3 and abs(right - text_right) <= 3, 'strikethrough does not span the text'


def test_strikethrough_ends_at_closing_tag(rich_text):
    closed = render(rich_text, '<s>Struck</s> plain')
    all_struck = render(rich_text, '<s>Struck plain</s>')
    assert ink(closed) < ink(all_struck), 'text after </s> is still struck through'


def test_html_capture_keeps_strikethrough(rich_text):
    from shoggoth.renderer import Region
    image = Image.new('RGB', (WIDTH, HEIGHT), 'white')
    region = Region({'x': 10, 'y': 10, 'width': WIDTH - 20, 'height': HEIGHT - 20})

    def capture(text):
        rich_text.start_html_capture()
        rich_text.render_text(image, text, region, font_size=40, min_font_size=40)
        return rich_text.finish_html_capture().parts

    assert len(capture('<s>Struck</s>')) == len(capture('Struck')) + 1, 'no line in the PDF text layer'


TALL = 400
BOX_BOTTOM = TALL - 10  # render() insets the text box by 10px


def bands(image):
    """(top, bottom) of each block of ink rows, top to bottom."""
    rows = sorted({y for _, y in ink(image)})
    result = [[rows[0], rows[0]]]
    for y in rows[1:]:
        if y > result[-1][1] + 1:
            result.append([y, y])
        result[-1][1] = y
    return [tuple(band) for band in result]


def test_align_top_is_the_default(rich_text):
    assert ink(render(rich_text, '<align top>Text', TALL)) == ink(render(rich_text, 'Text', TALL))


def test_valign_is_align_center(rich_text):
    assert ink(render(rich_text, '<valign>Text', TALL)) == ink(render(rich_text, '<align center>Text', TALL))


@pytest.mark.parametrize('text', ['Happy', 'First\nHappy', 'First line that wraps around in the box here\nHappy'])
def test_align_bottom_puts_the_last_line_at_the_bottom(rich_text, text):
    bottom = bands(render(rich_text, f'<align bottom>{text}', TALL))[-1][1]
    assert BOX_BOTTOM - 3 <= bottom <= BOX_BOTTOM, f'last line ends at {bottom}'


def test_align_bottom_field_setting_matches_the_tag(rich_text):
    tag = render(rich_text, '<align bottom>Happy', TALL)
    assert ink(render(rich_text, 'Happy', TALL, valignment='bottom')) == ink(tag)


def test_align_bottom_section_leaves_top_section_alone(rich_text):
    top = bands(render(rich_text, 'Top', TALL))[0]
    image = render(rich_text, 'Top\n<align bottom>Happy', TALL)
    assert bands(image)[0] == top
    assert bands(image)[-1][1] >= BOX_BOTTOM - 3


def test_center_is_centered_between_top_and_bottom_sections(rich_text):
    image = render(rich_text, 'Top\n<align center>HHH\n<align bottom>Happy', TALL)
    (_, top_end), (middle_start, middle_end), (bottom_start, bottom_end) = bands(image)
    assert bottom_end >= BOX_BOTTOM - 3
    above, below = middle_start - top_end, bottom_start - middle_end
    assert abs(above - below) <= 40 * 0.25, f'{above}px above the center section, {below}px below'


def test_align_bottom_in_a_polygon(rich_text):
    # a triangle narrowing downward: the last line must wrap for its band, and still land low
    polygon = [(10, 10), (WIDTH - 10, 10), (WIDTH / 2, TALL - 10), (10, 10)]
    text = 'Words going down into the narrow part of the shape'
    plain = bands(render(rich_text, text, TALL, polygon=polygon))
    low = bands(render(rich_text, f'<align bottom>{text}', TALL, polygon=polygon))
    assert low[-1][1] > plain[-1][1], 'text did not move down'
    assert low[-1][1] <= BOX_BOTTOM


def line_gaps(rich_text, text):
    """Distance between the bottoms of consecutive lines (all words without
    descenders, so these are baselines)."""
    bottoms = [bottom for _, bottom in bands(render(rich_text, text, height=TALL))]
    return [lower - upper for upper, lower in zip(bottoms, bottoms[1:])]


def test_dash_lines_are_a_line_break_apart(rich_text):
    assert line_gaps(rich_text, '- one\n- are\n- ten') == line_gaps(rich_text, 'one<br>are<br>ten')


def test_paragraph_gap_around_a_dash_list(rich_text):
    assert line_gaps(rich_text, 'one\n- are\n- ten\nnow') == line_gaps(rich_text, 'one\nare<br>ten\nnow')


def test_lines_of_a_dash_item_are_not_indented(rich_text):
    """The wrapped line of an item starts where the same text would without a bullet."""
    def wrapped_line_left(text):
        image = render(rich_text, text, height=TALL)
        top, bottom = bands(image)[1]
        return min(x for x, y in ink(image) if top <= y <= bottom)

    words = 'word ' * 30
    assert wrapped_line_left(f'- {words}') == wrapped_line_left(words)
