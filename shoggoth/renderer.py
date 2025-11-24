from PIL import Image, ImageOps
import os
from io import BytesIO
from shoggoth.rich_text import RichTextRenderer
from shoggoth.files import template_dir, overlay_dir, icon_dir, asset_dir, defaults_dir
from pathlib import Path

import logging
logging.getLogger('PIL').setLevel(logging.ERROR)
logging.getLogger('pillow').setLevel(logging.ERROR)


class Region:
    bleed: tuple[int, int] = (36, 36)
    x: int
    y: int
    width: int
    height: int

    def __init__(self, data):
        if not data:
            data = {}
        self.x = data.get('x', 0)
        self.y = data.get('y', 0)
        if Region.bleed:
            self.x += Region.bleed[0]
            self.y += Region.bleed[1]
        self.width = data.get('width', 0)
        self.height = data.get('height', 0)
        self.is_attached = bool(data.get('is_attached', False))
        self.attach_before = data.get('attach_before')
        self.attach_after = data.get('attach_after')

    @property
    def size(self):
        return (self.width, self.height)

    @property
    def pos(self):
        return (self.x, self.y)

    @property
    def center(self):
        return {'x': self.x + self.width // 2, 'y': self.y + self.height // 2}

    def __bool__(self):
        return self.width > 0 and self.height > 0 or self.is_attached

    def __repr__(self):
        return f'<Region pos({self.x},{self.x}) size({self.width},{self.height})>'


class CardRenderer:
    """Renders card images based on card data"""

    # Standard card dimensions
    #CARD_WIDTH = 375
    #CARD_HEIGHT = 524
    CARD_WIDTH = 750
    CARD_HEIGHT = 1050
    CARD_BLEED = 72

    def __init__(self):
        # Base paths
        self.assets_path = asset_dir
        self.templates_path = template_dir
        self.overlays_path = overlay_dir
        self.icons_path = icon_dir
        self.defaults_path = defaults_dir
        self.cache = {}
        self.resized_cache = {}

        # Initialize rich text renderer
        self.rich_text = RichTextRenderer(self)

    def get_cached(self, path) -> Image.Image:
        if path not in self.cache:
            if str(path).endswith('.svg'):
                from cairosvg import svg2png
                with open(path,'r') as file:
                    buffer = BytesIO()
                    svg2png(bytestring=file.read(), dpi=300, write_to=buffer)
                    buffer.seek(0)
                image = Image.open(buffer).convert('RGBA')
            else:
                image = Image.open(path).convert('RGBA')
            self.cache[path] = image
        return self.cache[path]

    def get_resized_cached(self, path, size) -> Image.Image:
        if (path, size) not in self.resized_cache:
            img = self.get_cached(path)
            self.resized_cache[(path, size)] = img.resize(size)
        return self.resized_cache[(path, size)]

    def invalidate_cache(self):
        self.cache = {}

    def get_thumbnail(self, card):
        """ Renders a low res version of the front of a card """
        image = self.render_card_side(card, card.front)
        image = image.resize((int(image.width*.5), int(image.height*.5)))
        buffer = BytesIO()
        image.save(buffer, format='jpeg', quality=50)
        buffer.seek(0)
        return buffer

    def get_card_textures(self, card, bleed=True):
        """Render both sides of a card"""
        front = self.render_card_side(card, card.front)
        back = self.render_card_side(card, card.back)

        if not bleed:
            front = front.crop((36, 36, front.width-36, front.height-36))
            back = back.crop((36, 36, back.width-36, back.height-36))

        f_buffer = BytesIO()
        front.save(f_buffer, format='jpeg', quality=90)
        f_buffer.seek(0)

        b_buffer = BytesIO()
        back.save(b_buffer, format='jpeg', quality=90)
        b_buffer.seek(0)

        return f_buffer, b_buffer

    def get_card_images(self, card):
        """Get raw PIL images for the card"""
        # Render front and back
        front_image = self.render_card_side(card, card.front)
        back_image  = self.render_card_side(card, card.back)

        return front_image, back_image

    def export_card_images(self, card, folder, include_backs=False, bleed=True, format='png', quality=100):
        lossless = quality == 100
        if include_backs or card.front['type'] not in ('player', 'encounter'):
            front_image = self.render_card_side(card, card.front, include_bleed=bleed)
            front_image.save(os.path.join(folder, card.name + f'_front.{format}'), quality=quality, lossless=lossless, compress_level=1)
        if include_backs or card.back['type'] not in ('player', 'encounter'):
            back_image  = self.render_card_side(card, card.back, include_bleed=bleed)
            back_image.save(os.path.join(folder, card.name + f'_back.{format}'), quality=quality, lossless=lossless, compress_level=1)

    def pil_to_texture(self, pil_image):
        """Convert PIL image to Kivy texture"""
        from kivy.uix.image import CoreImage

        buffer = BytesIO()
        pil_image.save(buffer, format='jpeg', quality=50)
        buffer.seek(0)

        # Create texture
        im = CoreImage(buffer, ext='jpeg')
        return im.texture

    def text_replacement(self, field, value, side):
        """ handles advanced text replacement fields """
        # <name>
        value = value.replace('<name>', side.card.name)
        # '<copy>': self.get_copy_field,
        if side == side.card.front:
            other_side = side.card.back
        else:
            other_side = side.card.front
        value = value.replace('<copy>', other_side.get(field, '<copy>'))
        #'<exi>': self.get_expansion_icon,
        if side.card.expansion.icon:
            value = value.replace(
                '<exi>',
                f'<image src="{side.card.expansion.icon}">'
            )
        else:
            value = value.replace('<exi>', '')
        #'<exn>': self.get_expansion_number,
        value = value.replace('<exn>', str(side.card.expansion_number))
        value = value.replace('<esn>', str(side.card.encounter_number))
        if side.card.encounter and '<est>' in value:
            value = value.replace('<est>', str(side.card.encounter.total_cards))
        else:
            value = value.replace('<est>', '')
        if side.card.encounter and side.card.encounter.icon:
            value = value.replace(
                '<esi>',
                f'<image src="{side.card.encounter.icon}">'
            )
        else:
            value = value.replace('<esi>', '')

        value = value.replace('<copyright>', side.card.get('copyright') or '')

        return value

    def render_card_side(self, card, side, include_bleed=True):
        """Render one side of a card"""
        height, width = self.CARD_HEIGHT+self.CARD_BLEED, self.CARD_WIDTH+self.CARD_BLEED
        if side.get('orientation', 'vertical') == 'horizontal':
            width, height = height, width

        card_image = Image.new('RGB', (width, height), (255, 255, 255))

        bleed = side.get('template_bleed', False)
        self.render_illustration(card_image, side)
        self.render_template(card_image, side, bleed)
        if side['type'] in ('investigator'):
            self.render_illustration(card_image, side)

        if not bleed:
            # make fake mirror bleed
            source_img = card_image.crop((36, 36, width-36, height-36))
            flip_lr = ImageOps.mirror(source_img)
            flip_ud = ImageOps.flip(source_img)
            flip_corners = ImageOps.flip(flip_lr)

            #right
            card_image.paste(flip_lr, (width-36, 36))
            #left
            card_image.paste(flip_lr, (36-flip_lr.width, 36))
            #top
            card_image.paste(flip_ud, (36, 36-flip_ud.height))
            #bottom
            card_image.paste(flip_ud, (36, height-36))
            #corners, tl, tr, bl, br
            card_image.paste(flip_corners, (36-flip_corners.width, 36-flip_corners.height))
            card_image.paste(flip_corners, (width-36, 36-flip_corners.height))
            card_image.paste(flip_corners, (36-flip_corners.width, height-36))
            card_image.paste(flip_corners, (width-36, height-36))

        for func in [
            self.render_level,
            self.render_encounter_icon,
            self.render_expansion_icon,
            self.render_icons,
            self.render_connection_icons,
            self.render_tokens,
            self.render_health,
            self.render_text,
            self.render_class_symbols,
            self.render_enemy_stats,
            self.render_slots,
            self.render_chaos,
            self.render_customizable,
        ]:
            try:
                func(card_image, side)
            except Exception as e:
                logging.debug(f'Failed in {func}: {e}')

        if not include_bleed:
            card_image = card_image.crop((
                self.CARD_BLEED/2,
                self.CARD_BLEED/2,
                card_image.width-self.CARD_BLEED/2,
                card_image.height-self.CARD_BLEED/2
            ))
        return card_image

    def render_text(self, card_image, side):
        for field in [
            'cost', 'name', 'traits', 'text', 'subtitle', 'label', 'index',
            'attack', 'evade', 'health', 'stamina', 'sanity', 'victory',
            'clues', 'doom', 'shroud', 'willpower', 'intellect',
            'combat', 'agility', 'illustrator', 'copyright', 'collection', 'difficulty',
            'text1', 'text2', 'text3',
        ]:
            value = side.get(field)
            region = Region(side.get(f'{field}_region', None))
            
            if region.is_attached or not region:
                # this field is part of another block, and
                # doesn't render on its own.
                continue

            # Checkboxes - primarily for Customizable
            if region.attach_before:
                attachment = side.get(region.attach_before)
                if attachment:
                    format = side.get(f'{region.attach_before}_format', '{value}\n')
                    value = format.format(value=attachment) + value

            if region.attach_after:
                attachment = side.get(region.attach_after)
                if attachment:
                    format = side.get(f'{region.attach_after}_format', '\n{value}')
                    value = value + format.format(value=attachment)

            if field == 'text':
                cb_value = side.get('checkbox_entries')
                if cb_value:
                    lines = ''
                    for slots, name, text in cb_value:
                        lines += '\n' + '☐'*slots + f' <b>{name}.</b> {text}'
                    value += lines

            if not value:
                continue

            # Replacements
            value = self.text_replacement(field, value, side)

            try:
                font = side.get(f'{field}_font', {})
                polygon = side.get(f'{field}_polygon', None)
                if polygon:
                    polygon = [(point[0]+self.CARD_BLEED/2, point[1]+self.CARD_BLEED/2) for point in polygon]

                if font.get('rotation'):
                    temp_image = Image.new('RGBA', region.size, (0, 0, 0, 0))
                    self.rich_text.render_text(
                        temp_image,
                        value,
                        Region({'x': -36, 'y': -36, 'height': region.height, 'width': region.width}),
                        font=font.get('font', 'regular'),
                        font_size=font.get('size', 20),
                        fill=font.get('color', '#231f20'),
                        outline=font.get('outline'),
                        outline_fill=font.get('outline_color'),
                        alignment=font.get('alignment', 'left'),
                        polygon=polygon,
                    )
                    temp_image = temp_image.rotate(font.get('rotation'), expand=True)
                    card_image.paste(temp_image, (region.x, region.y), temp_image)
                else:
                    self.rich_text.render_text(
                        card_image,
                        value,
                        region,
                        font=font.get('font', 'regular'),
                        font_size=font.get('size', 20),
                        fill=font.get('color', '#231f20'),
                        outline=font.get('outline'),
                        outline_fill=font.get('outline_color'),
                        alignment=font.get('alignment', 'left'),
                        polygon=polygon,
                    )
            except Exception as e:
                print(f"Error rendering field: {field}\n {e}")
                continue

    def render_tokens(self, card_image, side):
        value = side.get('tokens')
        if not value:
            return

        region = Region(side['chaos_region'])
        entry_height = region.height//len(value)
        font = side.get('chaos_font', {})

        for index, icon in enumerate(value):
            text = value[icon]
            text_region = {
                'x': region.x+94,
                'y': region.y+(index*entry_height),
                'width': region.width-94,
                'height': entry_height,
            }
            self.rich_text.render_text(
                card_image,
                text,
                text_region,
                font=font.get('font', 'regular'),
                font_size=font.get('size', 20),
                fill=font.get('color', '#231f20'),
                outline=font.get('outline'),
                outline_fill=font.get('outline_color'),
                alignment=font.get('alignment', 'left')
            )

            overlay_path = self.overlays_path/f"chaos_{icon}.png"
            overlay_icon = Image.open(overlay_path).convert("RGBA")
            overlay_icon = overlay_icon.resize((overlay_icon.width*2, overlay_icon.height*2))
            card_image.paste(overlay_icon, (region.x, region.y+(index*entry_height)), overlay_icon)

    def render_connection_icons(self, card_image, side):
        base_image = Image.open(self.overlays_path/f"location_hi_base.png").convert("RGBA")

        # own icon
        value = side.get('connection')

        if value and value != "None":
            region = Region(side.get('connection_region'))
            connection_image = Image.open(self.overlays_path/f"location_hi_{value}.png").convert("RGBA")
            card_image.paste(base_image, region.pos, base_image)
            card_image.paste(connection_image, (region.x+6, region.y+6), connection_image)

        # outgoing connections
        value = side.get('connections')

        if not value:
            return

        # grab and paint each icon
        for index, icon in enumerate(value):
            if not icon or icon == "None":
                continue
            region = Region(side.get(f'connection_{index+1}_region'))
            connection_image = Image.open(self.overlays_path/f"location_hi_{icon}.png").convert("RGBA")
            card_image.paste(connection_image, (region.x+6, region.y+6), connection_image)


    def render_icons(self, card_image, side):
        value = side.get('icons')
        if not value:
            return

        box_path = self.overlays_path/f"skill_box_{side.get_class()}.png"
        box_image = Image.open(box_path).convert("RGBA")
        box_image = box_image.resize((109, 83))
        for index, icon in enumerate(value):
            overlay_path = self.overlays_path/f"skill_icon_{icon}.png"
            overlay_icon = Image.open(overlay_path).convert("RGBA")
            overlay_icon = overlay_icon.resize((overlay_icon.width * 2, overlay_icon.height * 2))
            card_image.paste(box_image, (36, index*84+165+36), box_image)
            card_image.paste(overlay_icon, (25+36, index*84+181+36), overlay_icon)

    def render_health(self, card_image, side):
        """ Add health and sanity overlay, if needed. """
        for stat in ['health', 'sanity']:
            if not side.get(f'draw_{stat}_overlay', True):
                continue
            self.current_field = stat
            value = side.get(stat)
            region = Region(side.get(f'{stat}_region'))
            if region is None or value is None or not side.get('draw_health_overlay', True):
                continue

            overlay_path = self.overlays_path/f"{stat}_base.png"
            overlay_icon = Image.open(overlay_path).convert("RGBA")
            overlay_icon = overlay_icon.resize((region.width, region.height))
            center_x = region.x
            center_y = region.y - 15
            card_image.paste(overlay_icon, (center_x, center_y), overlay_icon)

    def render_expansion_icon(self, card_image, side):
        """Render the encounter icon """
        region = Region(side.get('collection_portrait_clip_region'))
        if not region:
            return

        icon = side.card.expansion.icon
        if not icon:
            return

        icon = Image.open(side.card.expansion.icon, formats=['png', 'jpg']).convert('RGBA')
        if icon.width > icon.height:
            icon = icon.resize((region.width, int(region.height*(icon.height/icon.width))))
        else:
            icon = icon.resize((int(region.width*(icon.width/icon.height)), region.height))

        # invert
        alpha = icon.getchannel('A')
        icon = icon.convert('RGB')
        icon = ImageOps.invert(icon)
        icon.putalpha(alpha)
        card_image.paste(icon, (region.x, region.y), icon)

    def render_encounter_icon(self, card_image, side):
        """Render the encounter icon """
        if not side.card.encounter and not side.get('encounter_icon', None):
            return

        region = Region(side.get('encounter_icon_region'))
        if not region:
            return

        overlay = side.get('encounter_overlay')
        if overlay:
            if not Path(overlay).is_file():
                overlay = overlay_dir / overlay
            overlay_image = Image.open(overlay).convert("RGBA")
            overlay_region = Region(side.get('encounter_overlay_region'))
            overlay_image = overlay_image.resize(overlay_region.size)
            card_image.paste(overlay_image, overlay_region.pos, overlay_image)

        icon_path = side.get('encounter_icon', None)
        if side.card.encounter and not icon_path:
            icon_path = side.card.encounter.icon

        if not Path(icon_path).is_file():
            icon_path = icon_dir / icon_path

        icon = Image.open(icon_path).convert("RGBA")
        scale = min(region.width/icon.width, region.height/icon.height)
        icon = icon.resize((int(icon.width*scale), int(icon.height*scale)))
        card_image.paste(icon, (region.x + (region.width-icon.width)//2, region.y + (region.height-icon.height)//2), icon)

    def render_slots(self, card_image, side):
        """Render the slot icons """
        slots = side.get('slots')
        slot = side.get('slot')
        if not slots:
            slots = [slot]
        if not slots:
            return

        for index, slot in enumerate(slots):
            region = Region(side.get(f'slot_{index+1}_region', {}))
            if not region:
                continue

            path = self.overlays_path/f'slot_{slot}.png'
            slot_image = Image.open(path).convert("RGBA")
            slot_image = slot_image.resize(region.size)
            card_image.paste(slot_image, region.pos, slot_image)

    def render_enemy_stats(self, card_image, side):
        """Render Damage and horror."""
        for token in ('damage', 'horror'):
            value = int(side.get(token, "0"))
            if not value:
                continue
            icon_path = self.overlays_path/f"{token}.png"
            raw_icon = Image.open(icon_path).convert("RGBA")
            for i in range(value):
                region = Region(side[f'{token}{i+1}_region'])
                if not region:
                    continue
                icon = raw_icon.resize((region.width, region.height))
                card_image.paste(icon, (region.x, region.y), icon)

    def render_template(self, card_image, side, bleed):
        """Render a template image onto a card"""
        template_value = side.get('template', '')

        if '<class>' in template_value:
            side_class = side.get('classes', ['guardian'])
            card_class = side_class[0] if len(side_class) == 1 else 'multi'
            template_value = template_value.replace('<class>', card_class)
        if '<subtitle>' in template_value:
            sub = side.get('subtitle', '')
            template_value = template_value.replace('<subtitle>', '_subtitle' if sub else '')

        if Path(template_value).is_file():
            template_path = Path(template_value)
        else:
            template_path = self.templates_path / (template_value + '.png')

        if not template_path.exists():
            return()

        if not bleed:
            template = self.get_resized_cached(template_path, (card_image.width-72, card_image.height-72))
            card_image.paste(template, (36, 36), template)
        else:
            template = self.get_resized_cached(template_path, (card_image.width, card_image.height))
            card_image.paste(template, (0, 0), template)

    def render_illustration(self, card_image, side):
        """Render the illustration/portrait"""
        # Get illustration path
        illustration_path = side.get('illustration', None)
        if not illustration_path or not os.path.exists(illustration_path):
            return

        try:
            # Load illustration
            illustration = self.get_cached(illustration_path)

            # Get clip region
            clip_region = Region(side['illustration_region'])

            # Calculate scaling
            illustration_scale = float(side.get('illustration_scale', 0))
            if not illustration_scale:
                if illustration.width > illustration.height:
                    illustration_scale = clip_region.height / illustration.height
                else:
                    illustration_scale = clip_region.width / illustration.width

            # Resize illustration
            new_width = int(illustration.width * illustration_scale)
            new_height = int(illustration.height * illustration_scale)
            illustration = self.get_resized_cached(illustration_path, (new_width, new_height))
            
            rotation = side.get('illustration_rotation', 0)
            if rotation:
                illustration = illustration.rotate(float(rotation))

            # Apply panning
            pan_x = side.get('illustration_pan_x', 0)
            pan_y = side.get('illustration_pan_y', 0)

            # Position and paste
            card_image.paste(
                illustration,
                (clip_region.x+pan_x, clip_region.y+pan_y),
                illustration
            )
        except Exception as e:
            print(f"Error rendering illustration: {str(e)}")


    def render_level(self, card_image, side):
        """Render the card level"""
        # Get level
        level = side.get('level', None)
        region = Region(side.get('level_region'))
        if not region:
            return

        if level is None or level == '' or level == 'None':
            level_icon_path = self.overlays_path/f"no_level.png"
            if side.get('no_level_overlay', None):
                level_icon_path = self.overlays_path/f"{side.get('no_level_overlay')}.png"
            level_icon = Image.open(level_icon_path).convert("RGBA")
            card_image.paste(level_icon, (region.x-14, region.y-63), level_icon)
            return

        level_icon_path = self.overlays_path/f"level_{level}.png"
        level_icon = Image.open(level_icon_path).convert("RGBA")
        card_image.paste(level_icon, region.pos, level_icon)

    def render_class_symbols(self, card_image, side):
        """Render class symbols for multiclass cards"""
        classes = side.get('classes', [])
        if len(classes) < 2:
            return

        # Render each class symbol
        for index, cls in enumerate(classes):
            symbol_path = self.overlays_path/f"class_symbol_{cls}.png"
            region = Region(side.get(f"class_symbol_{index+1}_region"))

            symbol = Image.open(symbol_path).convert("RGBA")
            #symbol = symbol.resize((symbol.width, symbol.height))
            card_image.paste(symbol, (region.x, region.y), symbol)

    def render_chaos(self, card_image, side):
        """ Renders the scenario reference cards.

            This could be handled in a lot of different ways,
            but this allows for easy json formatting of the card.
            It's essentially just a list of image and text.
        """
        entries = side.get('entries', [])
        if not entries:
            return

        region = Region(side['chaos_region'])
        font = side.get("chaos_font", {})
        for index, entry in enumerate(entries):
            tokens = entry['token']
            y = int(region.y + region.height/len(entries)*index)

            if type(tokens) != list:
                tokens = [tokens]

            for token_index, token in enumerate(tokens):
                try:
                    token_image = Image.open(overlay_dir / f"chaos_{token}.png")
                except:
                    continue

                size = min(
                    region.height/5.1,
                    (region.width/3)/len(tokens)
                )

                token_image = token_image.resize((int(size), int(size)))
                x = int(region.x + token_image.width*token_index)
                card_image.paste(token_image, (x, y), token_image)

            self.rich_text.render_text(
                card_image,
                entry['text'],
                Region({'x': (region.x+region.width//3)-32, 'y': y-32, 'height': region.height//len(entries), 'width': (2*region.width)//3}),
                font=font.get('font', 'regular'),
                font_size=font.get('size', 32),
                fill=font.get('color', '#231f20'),
                outline=font.get('outline'),
                outline_fill=font.get('outline_color'),
                alignment=font.get('alignment', 'left'),
            )

    def render_customizable(self, card_image, side):
        """ Renders the scenario reference cards.

            This could be handled in a lot of different ways,
            but this allows for easy json formatting of the card.
            It's essentially just a list of image and text.
        """
        if side['type'] != 'customizable':
            return

        entries = side.get('entries', [])
        if not entries:
            return

        region = Region(side['text_region'])
        font = side.get("text_font", {})
        parsed_text = ""
        for entry in entries:
            parsed_text += '\n' + int(entry[0])*'☐'
            parsed_text += f' <b>{entry[1]}.</b> '
            parsed_text += entry[2]

        self.rich_text.render_text(
            card_image,
            parsed_text,
            region,
            font=font.get('font', 'regular'),
            font_size=font.get('size', 32),
            fill=font.get('color', '#231f20'),
            outline=font.get('outline'),
            outline_fill=font.get('outline_color'),
            alignment=font.get('alignment', 'left'),
        )
