"""Draw commands -> pixels on a PIL image. `emit_html` is the other consumer of
the same command list."""

from PIL import ImageDraw

from shoggoth.renderer.richtext.model import ImageCommand, LineCommand, TextCommand


def render_commands(image, commands, glyph_run_cache):
    draw = ImageDraw.Draw(image)
    font_mode = draw.fontmode
    for command in commands:
        if isinstance(command, TextCommand):
            _draw_text(image, draw, command, glyph_run_cache, font_mode)
        elif isinstance(command, ImageCommand):
            image.paste(command.icon, (command.x, command.y), command.icon)
        elif isinstance(command, LineCommand):
            draw.line([(command.x1, command.y1), (command.x2, command.y2)],
                      fill=command.fill, width=command.width)


def _draw_text(image, draw, command, glyph_run_cache, font_mode):
    if command.outline:
        draw.text(
            (command.x, command.y), command.text,
            fill=command.fill, font=command.font,
            stroke_width=command.outline, stroke_fill=command.outline_fill,
            anchor='ls',
        )
        return
    # No stroke: paste a cached, already-shaped run instead of re-shaping. (A
    # stroked run can't use this cache -- see GlyphRunCache.)
    integer_x, integer_y = int(command.x), int(command.y)
    mask, offset = glyph_run_cache.get(
        command.font, command.text, font_mode, 0,
        (command.x - integer_x, command.y - integer_y),
    )
    paste_x, paste_y = integer_x + offset[0], integer_y + offset[1]
    if mask.size[0] and mask.size[1]:
        image.paste(command.fill,
                    (paste_x, paste_y, paste_x + mask.size[0], paste_y + mask.size[1]),
                    mask)
