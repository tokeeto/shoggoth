from time import time
from PIL import Image, ImageTk, ImageDraw, ImageFont
import os

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
            '<survivor>': 'S',

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
            '<per>': 'p',
            '<reaction>': 'r',
            '<unique>': 'u',
            '<willpower>': 'w',
        }

        # Define image-based icon tags and their corresponding image paths
        self.image_icon_tags = {
            '<set core>': 'sets/core',
            '<set dunwich>': 'sets/dunwich_legacy',
            '<set carcosa>': 'sets/path_to_carcosa',
            '<set forgotten>': 'sets/the_forgotten_age',
            '<set circle>': 'sets/circle_undone',
            '<set dream>': 'sets/dream_eaters',
            '<set innsmouth>': 'sets/innsmouth_conspiracy',
            '<set scarlet>': 'sets/scarlet_keys',
            '<wild>': 'icons/wild'  # Some icons might be better as images
        }

        # Font configurations
        self.fonts = {
            'regular': {
                'path': "assets/fonts/Arno Pro/arnopro_regular.otf",
                'scale': 1,
                'fallback': None
            },
            'bold': {
                'path': "assets/fonts/Arno Pro/arnopro_bold.otf",
                'scale': 1,
                'fallback': None
            },
            'italic': {
                'path': "assets/fonts/Arno Pro/arnopro_italic.otf",
                'scale': 1,
                'fallback': None
            },
            'bolditalic': {
                'path': "assets/fonts/Arno Pro/arnopro_bolditalic.otf",
                'scale': 1,
                'fallback': None
            },
            'icon': {
                'path': "assets/fonts/AHLCGSymbol.ttf",  # Special icon font
                'scale': 0.8,
                'fallback': None
            },
            'cost': {
                'path': "assets/fonts/Arkhamic.ttf",  # Special icon font
                'scale': 2,
                'fallback': None
            },
            'title': {
                'path': "assets/fonts/Arkhamic.ttf",  # Special icon font
                'scale': 2,
                'fallback': None
            }
        }

    def load_fonts(self, size):
        """Load all fonts at the specified size"""
        loaded_fonts = {}
        for font_type, font_info in self.fonts.items():
            try:
                loaded_fonts[font_type] = ImageFont.truetype(font_info['path'], size * font_info['scale'])
            except IOError:
                # Use fallback if specified, otherwise default
                if font_info['fallback']:
                    try:
                        loaded_fonts[font_type] = ImageFont.truetype(font_info['fallback'], size)
                    except IOError:
                        loaded_fonts[font_type] = ImageFont.load_default()
                else:
                    loaded_fonts[font_type] = ImageFont.load_default()
        return loaded_fonts

    def load_icon(self, icon_path, height):
        """Load an image icon and resize to match text height"""
        if (icon_path, height) in self.icon_cache:
            return self.icon_cache[(icon_path, height)]

        full_path = f"assets/{icon_path}.png"
        if not os.path.exists(full_path):
            return None

        try:
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

    def render_text(self, image, text, region, polygon=None, alignment='left', min_font_size=10, font=None, outline=0, outline_fill=None, fill='black'):
        """
        Render rich text with specified alignment and automatic font size reduction.

        Parameters:
            image: PIL Image to draw on
            text: The rich text string to render
            region: Dictionary with x, y, width, height of text region
            polygon: Optional list of points defining text boundary
            alignment: Text alignment - 'left', 'center', or 'right'
            min_font_size: Minimum font size when auto-reducing
            font: The initial font
        """

        if not text:
            return
        # Parse the rich text
        tokens = self.parse_text(text)

        self.alignment = alignment
        self.min_font_size = min_font_size

        # Try rendering with progressively smaller font sizes until it fits
        current_size = 16  # Start with default size
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
            success = self._render_with_font_size(temp_image, tokens, region, polygon, current_size, font=font, force=force, outline=outline, outline_fill=outline_fill, fill=fill)

            if success:
                best_size = current_size
                image.paste(temp_image, (0,0), temp_image)
                break

            current_size -= 1

    def _render_with_font_size(self, image, tokens, region, polygon, font_size, font='regular', force=False, outline=0, outline_fill=None, fill='black'):
        """
        Attempt to render text at the specified font size.
        Returns True if rendering succeeded, False if text doesn't fit.
        """
        draw = ImageDraw.Draw(image)

        # Load fonts at the current size
        fonts = self.load_fonts(font_size)

        # Current position and state
        x, y = region['x'], region['y']
        max_width = region['width']
        max_height = region['height']

        # Current formatting state
        current_font = font
        font_stack = []  # Stack to track nested font changes
        current_alignment = self.alignment
        alignment_stack = []

        # Word wrapping data
        current_line = []
        line_height = int(font_size * 1.3)  # Line height with spacing
        current_line_width = 0

        # Keep track of whether we're going to overflow
        will_overflow = False

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
                return icon.width if icon else 0
            return 0

        def get_line_width(line):
            """Calculate the total width of a line"""
            return sum(get_token_width(t) for t in line if t['type'] != 'format')

        def get_line_start_x(line):
            """Calculate starting X position based on alignment"""
            line_width = get_line_width(line)

            if current_alignment == 'center':
                return x + (max_width - line_width) // 2
            elif current_alignment == 'right':
                return x + max_width - line_width
            else:  # left alignment
                return x

        def render_line(line, y_pos):
            """Render a line of tokens with proper alignment"""
            if not line:
                return

            x_pos = get_line_start_x(line)

            for token in line:
                if token['type'] == 'format':
                    continue  # Format tokens don't render

                # Skip if outside polygon bounds
                if polygon and not is_point_in_polygon((x_pos, y_pos), polygon):
                    x_pos += token['width']
                    continue

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
                    draw.text((x_pos, y_pos), token['value'],
                            fill=(0, 0, 0), font=fonts['icon'])
                    x_pos += token['width']

                elif token['type'] == 'image_icon':
                    icon = self.load_icon(token['value'], font_size)
                    if icon:
                        # Center the icon vertically with text
                        icon_y = y_pos - (icon.height - font_size) // 2
                        image.paste(icon, (x_pos, icon_y), icon)
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
                if current_line:
                    render_line(current_line, y)

                # Move to next line
                y += line_height
                current_line = []
                current_line_width = 0

                # Check if we've exceeded the region height
                if y + line_height > region['y'] + max_height:
                    if not force:
                        return False  # Text doesn't fit
                    will_overflow = True

            elif token['type'] in ['font_icon', 'image_icon']:
                # Calculate token width
                token['width'] = get_token_width(token)
                token_width = token['width']

                # Check if adding this icon would exceed the max width
                if current_line_width + token_width > max_width:
                    # Icon doesn't fit, render current line first
                    if current_line:
                        render_line(current_line, y)

                        # Move to next line
                        y += font_size
                        current_line = []
                        current_line_width = 0

                        # Check if we've exceeded the region height
                        if y + line_height > region['y'] + max_height:
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
                    render_line(current_line, y)
                    y += font_size

                    # Check if we've exceeded the region height
                    if y + line_height > region['y'] + max_height:
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
            if y + line_height > region['y'] + max_height and not force:
                return False

        # If we get here and aren't forcing, the text fit successfully
        return not will_overflow or force
