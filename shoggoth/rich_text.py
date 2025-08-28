from time import time
from PIL import Image, ImageDraw, ImageFont, ImageColor, ImageOps
import os
import numpy as np
import re
from shoggoth.files import font_dir, icon_dir, overlay_dir

#ImageDraw.fontmode = 'L'
ImageDraw.fontmode = "1"
image_regex = re.compile(r'<image(\s\w+=\".+?\"){1,}?>', flags=re.IGNORECASE)
tag_value_pattern = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


def parse_tag_attributes(tag_string):
    # This regex finds key="value" pairs
    return dict(re.findall(tag_value_pattern, tag_string))


def recolor_icon(icon, color):
    data = np.array(icon)
    red, green, blue, alpha = data.T
    black_areas = (red == 0) & (blue == 0) & (green == 0)
    data[..., :-1][black_areas.T] = ImageColor.getcolor(color, "RGB") # Transpose back needed
    return Image.fromarray(data)


def invert_icon(icon):
    alpha = icon.getchannel('A')
    icon = icon.convert('RGB')
    icon = ImageOps.invert(icon)
    icon.putalpha(alpha)
    return icon


class RichTextRenderer:
    def __init__(self, card_renderer):
        self.card_renderer = card_renderer
        self.icon_cache = {}  # Cache for loaded icons

        # Add alignment configuration
        self.alignment = 'left'  # Default alignment: 'left', 'center', 'right'
        self.min_font_size = 10  # Minimum font size to use when reducing

        # Define special formatting tags and their replacements
        self.formatting_tags = {
            '<b>': {'start': True, 'font': 'bold'},
            '</b>': {'start': False, 'font': 'bold'},
            '<i>': {'start': True, 'font': 'italic'},
            '</i>': {'start': False, 'font': 'italic'},
            '<bi>': {'start': True, 'font': 'bolditalic'},
            '</bi>': {'start': False, 'font': 'bolditalic'},
            '<icon>': {'start': True, 'font': 'icon'},
            '</icon>': {'start': False, 'font': 'icon'},
            '<center>': {'start': True, 'align': 'center'},
            '</center>': {'start': False, 'align': 'center'},
            '<left>': {'start': True, 'align': 'left'},
            '</left>': {'start': False, 'align': 'left'},
            '<right>': {'start': True, 'align': 'right'},
            '</right>': {'start': False, 'align': 'right'},
        }

        # Replacement tags - tags that render as different text when encountered
        self.replacement_tags = {
            '<for>': self.get_forced_template,
            '<prey>': self.get_prey_template,
            '<rev>': self.get_revelation_template,
        }

        # Define font-based icon tags and their corresponding characters
        self.font_icon_tags = {
            '<codex>': '#',
            '<star>': '*',
            '<dash>': '-',
            '<sign_1>': '1',
            '<sign_2>': '2',
            '<sign_3>': '3',
            '<sign_4>': '4',
            '<sign_5>': '5',
            '<question>': '?',

            '<tablet>': 'A',
            '<entry>': 'B',
            '<cultist>': 'C',
            '<blessing>': 'D',
            '<elder_sign>': 'E',
            '<fleur>': 'F',
            '<guardian>': 'G',
            '<frost>': 'h',
            '<seeker>': 'K',
            '<elder_thing>': 'L',
            '<mystic>': 'M',
            '<rogue>': 'R',
            '<skull>': 'S',
            '<auto_fail>': 'T',
            '<curse>': 'U',
            '<survivor>': 'V',

            '<agility>': 'a',
            '<bullet>': 'b',
            '<combat>': 'c',
            '<horror>': 'd',
            '<resolution>': 'e',
            '<free>': 'f',
            '<damage>': 'h',
            '<int>': 'i',
            '<resource>': 'm',
            '<action>': 'n',
            '<open>': 'o',
            '<per>': 'p',
            '<reaction>': 'r',
            '<unique>': 'u',
            '<willpower>': 'w',
        }

        # Define image-based icon tags and their corresponding image paths
        self.image_icon_tags = {
            '<set core>': 'icons/AHLCG-CoreSet',
            '<set dunwich>': 'icons/AHLCG-TheDunwichLegacy',
            '<set carcosa>': 'icons/AHLCG-ThePathToCarcosa',
            '<set forgotten>': 'icons/AHLCG-TheForgottenAge',
            '<set circle>': 'icons/AHLCG-TheCircleUndone',
            '<set dream>': 'icons/AHLCG-DreamEaters',
            '<set innsmouth>': 'icons/AHLCG-TheInnsmouthConspiracy',
            '<set scarlet>': 'icons/AHLCG-TheScarletKeys',
        }

        # Font configurations
        self.fonts = {
            'regular': {
                'path': font_dir / "Arno Pro" / "arnopro_regular.otf",
                'scale': 1,
                'fallback': None
            },
            'bold': {
                'path': font_dir / "Arno Pro" / "arnopro_bold.otf",
                'scale': 1,
                'fallback': None
            },
            'semibold': {
                'path': font_dir / "Arno Pro" / "arnopro_semibold.ttf",
                'scale': 1,
                'fallback': None
            },
            'italic': {
                'path': font_dir / "Arno Pro" / "arnopro_italic.otf",
                'scale': 1,
                'fallback': None
            },
            'bolditalic': {
                'path': font_dir / "Arno Pro" / "arnopro_bolditalic.otf",
                'scale': 1,
                'fallback': None
            },
            'icon': {
                'path': font_dir / "AHLCGSymbol.otf",
                'scale': 1,
                'fallback': None
            },
            'cost': {
                'path': font_dir / "Arkhamic.ttf",
                'scale': 1,
                'fallback': None
            },
            'title': {
                'path': font_dir / "Arkhamic.ttf",
                'scale': 1,
                'fallback': None
            },
            'skill': {
                'path': font_dir / "Bolton.ttf",
                'scale': 1,
                'fallback': None
            }
        }

    def get_card_name(self):
        return self.card_renderer.current_card.name

    def get_forced_template(self):
        return '<b>Forced –</b>'

    def get_prey_template(self):
        return '<b>Prey –</b>'

    def get_revelation_template(self):
        return '<b>Revelation –</b>'

    def get_copy_field(self):
        return self.card_renderer.current_opposite_side.get(self.card_renderer.current_field)

    def get_expansion_icon(self):
        if self.card_renderer.current_card.expansion.icon:
            return f'<image src="{self.card_renderer.current_card.expansion.icon}">'
        else:
            return " "

    def get_expansion_number(self):
        return str(self.card_renderer.current_card.expansion_number)

    def get_set_number(self):
        return str(self.card_renderer.current_card.encounter_number)

    def get_set_total(self):
        if not self.card_renderer.current_card.encounter:
            return ''
        return str(self.card_renderer.current_card.encounter.get('card_amount', '?'))

    def get_set_icon(self):
        if not self.card_renderer.current_card.encounter:
            return ''
        return f'<image src="{self.card_renderer.current_card.encounter.icon}">'

    def load_fonts(self, size):
        """Load all fonts at the specified size"""
        loaded_fonts = {}
        for font_type, font_info in self.fonts.items():
            loaded_fonts[font_type] = ImageFont.truetype(font_info['path'], size * font_info['scale'])
        return loaded_fonts

    def load_icon(self, icon_path, height):
        """Load an image icon and resize to match text height"""
        if (icon_path, height) in self.icon_cache:
            return self.icon_cache[(icon_path, height)]

        if os.path.exists(icon_path):
            full_path = icon_path
        else:
            full_path = icon_dir / f"{icon_path}.png"
            if not os.path.exists(full_path):
                return None

        try:
            height *= 1
            icon = Image.open(full_path).convert("RGBA")
            # Maintain aspect ratio
            aspect_ratio = icon.width / icon.height
            new_width = int(height * aspect_ratio)
            icon = icon.resize((new_width, height), Image.LANCZOS)

            # Cache the icon
            self.icon_cache[(icon_path, height)] = icon
            return icon
        except Exception:
            return None

    def parse_text(self, text):
        """Parse rich text into tokens with preserved whitespace"""
        tokens = []
        current_pos = 0

        # replacement tags
        for tag, func in self.replacement_tags.items():
            text = text.replace(tag, (func() or tag))

        # Find all special tags or icons
        while current_pos < len(text):
            # Check for formatting tags
            format_match = False
            for tag, info in self.formatting_tags.items():
                if text[current_pos:].startswith(tag):
                    if 'font' in info:
                        tokens.append({
                            'type': 'format',
                            'value': info['font'],
                            'start': info['start']
                        })
                        current_pos += len(tag)
                        format_match = True
                        break
                    elif 'align' in info:
                        tokens.append({
                            'type': 'align',
                            'value': info['align'],
                            'start': info['start']
                        })
                        current_pos += len(tag)
                        format_match = True
                        break

            if format_match:
                continue

            # Check for font-based icons
            font_icon_match = False
            for tag, char in self.font_icon_tags.items():
                if text[current_pos:].startswith(tag):
                    tokens.append({
                        'type': 'font_icon',
                        'value': char
                    })
                    current_pos += len(tag)
                    font_icon_match = True
                    break

            if font_icon_match:
                continue

            # Check for image-based icons
            image_icon_match = False
            for tag, icon_path in self.image_icon_tags.items():
                if text[current_pos:].startswith(tag):
                    tokens.append({
                        'type': 'image_icon',
                        'value': icon_path
                    })
                    current_pos += len(tag)
                    image_icon_match = True
                    break

            if image_icon_match:
                continue

            # image tag
            if match := image_regex.match(text[current_pos:]):
                tag = match[0]
                attributes = parse_tag_attributes(tag)
                print('found an image: ', tag, 'with attributes', attributes)
                if 'src' in attributes:
                    tokens.append({
                        'type': 'image_icon',
                        'value': attributes.get('src'),
                    })
                    print('appended an image icon')
                current_pos += len(tag)
                continue

            # Check for newlines
            if text[current_pos:].startswith('\n'):
                tokens.append({
                    'type': 'newline'
                })
                current_pos += 1
                continue

            # Check for whitespace
            if text[current_pos] == ' ':
                tokens.append({
                    'type': 'text',
                    'value': ' ',
                })
                current_pos += 1
                continue

            # Regular text - find the next special character or tag
            next_special = len(text)

            # Find the next special tag
            all_tags = (
                list(self.formatting_tags.keys()) +
                list(self.font_icon_tags.keys()) +
                list(self.image_icon_tags.keys()) +
                [' ', '\n']
            )

            for tag in all_tags:
                pos = text.find(tag, current_pos)
                if pos != -1 and pos < next_special:
                    next_special = pos

            # Add text token
            text_content = text[current_pos:next_special]
            if text_content:
                tokens.append({
                    'type': 'text',
                    'value': text_content
                })

            current_pos = next_special

        return tokens

    def render_text(self, image, text, region, polygon=None, alignment='left', font_size=16, min_font_size=10, font=None, outline=0, outline_fill=None, fill='#231f20'):
        """
        Render rich text with specified alignment and automatic font size reduction.

        Parameters:
            image: PIL Image to draw on
            text: The rich text string to render
            region: Dictionary with x, y, width, height of text region
            polygon: Optional list of points defining text boundary
            alignment: Text alignment - 'left', 'center', or 'right'
            font_size: Initial font size
            min_font_size: Minimum font size when auto-reducing
            font: The initial font
        """

        if not text:
            return
        # Parse the rich text
        tokens = self.parse_text(text)

        # Try rendering with progressively smaller font sizes until it fits
        current_size = font_size  # Start with default size
        best_size = None

        # Create a temporary image with same size to test text fitting
        temp_image = Image.new('RGBA', image.size, (0, 0, 0, 0))

        if not font:
            font = 'regular'
        # Test each font size to find the largest that fits
        while current_size >= min_font_size:
            # Clear the temp image for each test
            temp_image = Image.new('RGBA', image.size, (0, 0, 0, 0))

            # Try rendering at this size
            force = current_size == min_font_size
            success = self._render_with_font_size(temp_image, tokens, region, polygon, current_size, font=font, force=force, outline=outline, outline_fill=outline_fill, fill=fill, alignment=alignment)

            if success:
                best_size = current_size
                image.paste(temp_image, (0,0), temp_image)
                break

            current_size -= 1

    def _render_with_font_size(self, image, tokens, region, polygon, font_size, font='regular', force=False, outline=0, outline_fill=None, fill='#231f20', alignment='left'):
        """
        Attempt to render text at the specified font size.
        Returns True if rendering succeeded, False if text doesn't fit.
        """
        draw = ImageDraw.Draw(image)

        # Load fonts at the current size
        fonts = self.load_fonts(font_size)

        # Current position and state
        x, y = region.x, region.y
        max_width = region.width
        max_height = region.height

        # Current formatting state
        current_font = font
        font_stack = []  # Stack to track nested font changes
        current_alignment = alignment
        current_indent = 0
        indent_current = False
        alignment_stack = []

        # Word wrapping data
        current_line = []
        line_height = int(font_size * 1.34)  # Line height with spacing
        current_line_width = 0

        # Keep track of whether we're going to overflow
        will_overflow = False

        def polygon_width_at_y(target_y, polygon_points):
            x_intersections = []

            for i in range(len(polygon_points) - 1):
                (x1, y1), (x2, y2) = polygon_points[i], polygon_points[i + 1]

                # Skip horizontal edges or those that don't straddle target_y
                if (y1 < target_y and y2 < target_y) or (y1 > target_y and y2 > target_y) or y1 == y2:
                    continue

                # Linear interpolation to find x at target_y
                t = (target_y - y1) / (y2 - y1)
                x_val = x1 + t * (x2 - x1)
                x_intersections.append(x_val)

            if not x_intersections:
                return region.x, region.x+region.width  # target_y is outside the vertical range of the polygon

            left = min(x_intersections)
            right = max(x_intersections)
            return left, right

        if polygon:
            left, right = polygon_width_at_y(y, polygon)
            max_width = right-left
            x = left

        # Polygon check function (same as before)
        def is_point_in_polygon(point, polygon_points):
            """Check if a point is inside a polygon"""
            if polygon is None:
                return True

            x, y = point
            n = len(polygon_points)
            inside = False

            p1x, p1y = polygon_points[0]
            for i in range(1, n + 1):
                p2x, p2y = polygon_points[i % n]
                if y > min(p1y, p2y):
                    if y <= max(p1y, p2y):
                        if x <= max(p1x, p2x):
                            if p1y != p2y:
                                xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                            if p1x == p2x or x <= xinters:
                                inside = not inside
                p1x, p1y = p2x, p2y

            return inside

        def get_token_width(token):
            """Calculate the width of a token"""
            if token['type'] == 'text':
                x = draw.textlength(token['value'], font=fonts[token['font']])
                return x
            elif token['type'] == 'font_icon':
                x = draw.textlength(token['value'], font=fonts['icon'])
                return x
            elif token['type'] == 'image_icon':
                icon = self.load_icon(token['value'], font_size)
                return icon.width//1 if icon else 0
            return 0

        def get_line_width(line):
            """Calculate the total width of a line"""
            return sum(get_token_width(t) for t in line if t['type'] != 'format')

        def get_line_start_x(line, y):
            """Calculate starting X position based on alignment"""
            line_width = get_line_width(line)
            if polygon:
                left, right = polygon_width_at_y(y, polygon)
                if current_alignment == 'center':
                    return left + ((right-left) - line_width) // 2
                elif current_alignment == 'right':
                    return left + (right-left) - line_width
                else:
                    return left

            if current_alignment == 'center':
                return x + (max_width - line_width) // 2
            elif current_alignment == 'right':
                return x + max_width - line_width
            else:  # left alignment
                return x

        def render_line(line, y_pos, run_on_line=True, indent=0):
            """Render a line of tokens with proper alignment"""
            x_pos = get_line_start_x(line, y_pos)
            x_pos += indent

            if not line:
                return

            # remove spaces on newlines, if exactly 1, and it's a
            # continued line.
            if run_on_line and line[0]['type'] == 'text':
                if line[0]['value'] == ' ':
                    line = line[1:]

            for token in line:
                if token['type'] == 'format':
                    continue  # Format tokens don't render

                if token['type'] == 'text':
                    draw.text(
                        (x_pos, y_pos),
                        token['value'],
                        fill=fill,
                        font=fonts[token['font']],
                        stroke_width=outline,
                        stroke_fill=outline_fill,
                    )
                    x_pos += token['width']

                elif token['type'] == 'font_icon':
                    draw.text(
                        (x_pos, y_pos),
                        token['value'],
                        fill=fill,
                        font=fonts['icon'],
                        stroke_width=outline,
                        stroke_fill=outline_fill,
                    )
                    x_pos += token['width']

                elif token['type'] == 'image_icon':
                    icon = self.load_icon(token['value'], font_size)
                    if icon:
                        # Center the icon vertically with text
                        icon = invert_icon(icon)
                        icon_y = y_pos - (icon.height - font_size) // 2
                        image.paste(icon, (int(x_pos), int(icon_y)), icon)
                        x_pos += icon.width


        # Process each token to create lines
        for i, token in enumerate(tokens):
            if token['type'] == 'format':
                token['width'] = 0
                # Update current font
                if token['start']:
                    font_stack.append(current_font)  # Save current font
                    current_font = token['value']
                else:
                    # Restore previous font if stack isn't empty
                    if font_stack:
                        current_font = font_stack.pop()
                    else:
                        current_font = 'regular'

                # Add format change to current line (it has no width impact)
                current_line.append(token)

            elif token['type'] == 'align':
                token['width'] = 0
                # Update current alignment
                if token['start']:
                    alignment_stack.append(current_alignment)
                    current_alignment = token['value']
                else:
                    if font_stack:
                        current_alignment = alignment_stack.pop()
                    else:
                        current_alignment = self.alignment

                # Add alignment change to current line (it has no width impact)
                current_line.append(token)

            elif token['type'] == 'newline':
                # Render current line and start a new one
                current_indent_x = 0
                if current_line:
                    render_line(current_line, y, indent=(current_indent if indent_current else 0))
                    current_indent = 0
                    indent_current = False

                # Move to next line
                y += line_height
                if polygon:
                    l,r = polygon_width_at_y(y, polygon)
                    max_width = r-l
                current_line = []
                current_line_width = 0

                # Check if we've exceeded the region height
                if y + line_height > region.y + max_height:
                    if not force:
                        return False  # Text doesn't fit
                    will_overflow = True

            elif token['type'] in ['font_icon', 'image_icon']:
                # Calculate token width
                token['width'] = get_token_width(token)
                token_width = token['width']

                # if this is a bullet, at the start of a new line, indent it
                if token['value'] == 'b' and not current_line:
                    current_indent = token_width + get_token_width(
                        {'type': 'text', 'value': " ", 'font': current_font}
                    )

                # Check if adding this icon would exceed the max width
                if current_line_width + token_width > max_width:
                    # Icon doesn't fit, render current line first
                    if current_line:
                        render_line(current_line, y, indent=(current_indent if indent_current else 0))
                        indent_current = current_indent > 0

                        # Move to next line
                        y += font_size
                        if polygon:
                            l,r = polygon_width_at_y(y, polygon)
                            max_width = r-l
                        current_line = []
                        current_line_width = 0

                        # Check if we've exceeded the region height
                        if y + line_height > region.y + max_height:
                            if not force:
                                return False  # Text doesn't fit
                            will_overflow = True

                # Add icon to current line
                current_line.append(token)
                current_line_width += token_width

            elif token['type'] == 'text':
                # We'll process text as a unit to preserve all whitespace
                text_value = token['value']
                token_with_font = {
                    'type': 'text',
                    'value': text_value,
                    'font': current_font
                }

                # Calculate width if we add this token
                segment_width = get_token_width(token_with_font)
                token_with_font['width'] = segment_width
                token['width'] = segment_width

                if current_line_width + segment_width > max_width:
                    # Text doesn't fit on current line

                    # Render current line and move to next
                    render_line(current_line, y, indent=(current_indent if indent_current else 0))
                    indent_current = current_indent > 0
                    y += font_size
                    if polygon:
                        l,r = polygon_width_at_y(y, polygon)
                        max_width = r-l

                    # Check if we've exceeded the region height
                    if y + line_height > region.y + max_height:
                        if not force:
                            return False  # Text doesn't fit
                        will_overflow = True

                    # Start new line with this token
                    current_line = []
                    current_line_width = 0

                    # Special case: if the token is still too wide for a line by itself
                    # and we're forcing rendering, we'll still add it
                    if segment_width > max_width and force:
                        current_line.append(token_with_font)
                        current_line_width = segment_width
                    elif segment_width <= max_width:  # Only add if it fits
                        current_line.append(token_with_font)
                        current_line_width = segment_width
                else:
                    # Token fits on current line
                    current_line.append(token_with_font)
                    current_line_width += segment_width
        # Render any remaining line
        if current_line:
            render_line(current_line, y)

            # Check if we ran out of vertical space
            if y + line_height > region.y + max_height and not force:
                return False

        # If we get here and aren't forcing, the text fit successfully
        return not will_overflow or force
