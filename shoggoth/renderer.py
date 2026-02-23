from PIL import Image, ImageOps, ImageDraw
import os
from io import BytesIO
from shoggoth.rich_text import RichTextRenderer
from shoggoth.files import template_dir, overlay_dir, icon_dir, asset_dir, defaults_dir
from pathlib import Path
from cairosvg import svg2png

import logging
logging.getLogger('PIL').setLevel(logging.ERROR)
logging.getLogger('pillow').setLevel(logging.ERROR)


class Region:
    x: int
    y: int
    width: int
    height: int
    SCALE: float = 1

    def __init__(self, data):
        if not data:
            data = {}
        self.x = int(data.get('x', 0) * Region.SCALE)
        self.y = int(data.get('y', 0) * Region.SCALE)
        self.width = int(data.get('width', 0) * Region.SCALE)
        self.height = int(data.get('height', 0) * Region.SCALE)
        self.is_attached = bool(data.get('is_attached', False))
        self.attach_before = data.get('attach_before')
        self.attach_after = data.get('attach_after')

    @staticmethod
    def unscaled(data):
        s = Region.SCALE
        Region.SCALE = 1
        r = Region(data)
        Region.SCALE = s
        return r

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
        self.card_wo_illus_cache = {}

        # Initialize rich text renderer
        self.rich_text = RichTextRenderer(self)

    def get_cached(self, path) -> Image.Image:
        if path not in self.cache:
            if str(path).endswith('.svg'):
                from cairosvg import svg2png
                with open(path, 'r') as file:
                    buffer = BytesIO()
                    svg2png(bytestring=file.read(), output_width=512, output_height=512, write_to=buffer)
                    buffer.seek(0)
                image = Image.open(buffer).convert('RGBA')
            else:
                image = Image.open(path).convert('RGBA')
            self.cache[path] = image
        return self.cache[path]

    def get_resized_cached(self, path, size) -> Image.Image:
        if (path, size) not in self.resized_cache:
            # svgs are always loaded directly as resized due to how cairo works
            if str(path).endswith('.svg'):
                with open(path, 'r') as file:
                    buffer = BytesIO()
                    svg2png(bytestring=file.read(), output_width=size[0], output_height=size[1], write_to=buffer)
                    buffer.seek(0)
                image = Image.open(buffer).convert('RGBA')
                self.resized_cache[(path, size)] = image
            else:
                img = self.get_cached(path)
                self.resized_cache[(path, size)] = img.resize(size)
        return self.resized_cache[(path, size)]

    def invalidate_cache(self, path=None):
        """Invalidate cached images.

        Args:
            path: If provided, invalidate only entries for this path.
                  If None, clear the entire cache.
        """
        if path:
            if path not in self.cache:
                return
            del self.cache[path]

            keys_to_remove = [k for k in self.resized_cache if k[0] == path]
            for k in keys_to_remove:
                del self.resized_cache[k]
        else:
            self.cache = {}
            self.resized_cache = {}

    def get_thumbnail(self, card):
        """ Renders a low res version of the front of a card """
        image = self.render_card_side(card, card.front)
        image = image.resize((int(image.width*.5), int(image.height*.5)))
        buffer = BytesIO()
        image.save(buffer, format='jpeg', quality=50)
        buffer.seek(0)
        return buffer

    def get_card_textures(self, card, size, bleed=True, format='jpeg', quality=80):
        """Render both sides of a card"""
        import time
        t = time.time()
        lossless = quality == 100
        front = self.render_card_side(card, card.front, include_bleed=bleed, **size)
        back = self.render_card_side(card, card.back, include_bleed=bleed, **size)

        f_buffer = BytesIO()
        front.save(f_buffer, format=format, quality=quality, lossless=lossless)
        f_buffer.seek(0)

        b_buffer = BytesIO()
        back.save(b_buffer, format=format, quality=quality, lossless=lossless)
        b_buffer.seek(0)

        print(f'get_card_textures in {time.time()-t}')
        return f_buffer, b_buffer

    def get_card_images(self, card, size):
        """Get raw PIL images for the card"""
        # Render front and back
        front_image = self.render_card_side(card, card.front, **size)
        back_image = self.render_card_side(card, card.back, **size)

        return front_image, back_image

    def export_card_images(self, card, folder, size, include_backs=False, bleed=True, format='png', quality=100, separate_versions=True):
        lossless = quality == 100
        outputs = []
        orig_card = card

        # should each version (eg. 1/2 and 2/2) be printed seperately or as 1-2/2?
        faces = orig_card.versions
        if not separate_versions:
            faces = [orig_card]

        for index, card in enumerate(faces):
            for face, name in ((card.front, 'front'), (card.back, 'back')):
                # if this is a repeated card, only export it once
                if face['type'] in ('player', 'encounter') and not include_backs:
                    file_path = Path(folder) / f'{face["type"]}.{format}'
                    if not file_path.exists():
                        image = self.render_card_side(card, face, include_bleed=bleed, **size)
                        image.save(file_path, quality=quality, lossless=lossless, compress_level=1)
                    outputs.append(str(file_path))
                else:
                    file_path = Path(folder) / f'{card.id}_{name}_{index}.{format}'
                    image = self.render_card_side(card, face, include_bleed=bleed, **size)
                    image.save(file_path, quality=quality, lossless=lossless, compress_level=1)
                    outputs.append(str(file_path))
        return outputs

    def pil_to_texture(self, pil_image):
        """Convert PIL image to buffer"""
        buffer = BytesIO()
        pil_image.save(buffer, format='jpeg', quality=50)
        buffer.seek(0)
        return buffer

    def text_replacement(self, field, value, side):
        """ handles advanced text replacement fields """
        # <name>
        value = value.replace('<name>', side.card.name)
        if side == side.card.front:
            other_side = side.card.back
        else:
            other_side = side.card.front
        value = value.replace('<copy>', other_side.get(field, '<copy>'))
        if side.card.expansion.icon:
            value = value.replace(
                '<exi>',
                f'<image src="{side.card.expansion.icon}">'
            )
        else:
            value = value.replace('<exi>', '')
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

    def render_card_side_without_illustration(self, card, side, include_bleed=True):
        from shoggoth.card import Card
        if card in self.card_wo_illus_cache[card]:
            return self.card_wo_illus_cache[card]

        c = Card(card.data, expansion=card.expansion, encounter=card.encounter)
        c.set('illustration', None)
        self.card_wo_illus_cache[card] = self.render_card_side(c, side, include_bleed)
        return self.card_wo_illus_cache[card]

    def render_card_side(self, card, side, include_bleed=True, width=1500, height=2100, bleed=72):
        """Render one side of a card"""
        if width == 750:
            Region.SCALE = .5
        if width == 375:
            Region.SCALE = .25

        height, width = height + bleed * 2, width + bleed * 2
        if side.get('orientation', 'vertical') == 'horizontal':
            width, height = height, width

        card_image = Image.new('RGB', (width, height), (255, 255, 255))

        template_bleed = side.get('template_bleed', False)
        self.render_illustration(card_image, side)
        self.render_template(card_image, side, bleed, template_bleed)
        if side['type'] in ('investigator'):
            self.render_illustration(card_image, side)

        if not template_bleed:
            # make fake mirror bleed
            source_img = card_image.crop((bleed, bleed, width - bleed, height - bleed))
            flip_lr = ImageOps.mirror(source_img)
            flip_ud = ImageOps.flip(source_img)
            flip_corners = ImageOps.flip(flip_lr)

            # right, left, top, bottom
            card_image.paste(flip_lr, (width - bleed, bleed))
            card_image.paste(flip_lr, (bleed - flip_lr.width, bleed))
            card_image.paste(flip_ud, (bleed, bleed - flip_ud.height))
            card_image.paste(flip_ud, (bleed, height - bleed))
            #corners, tl, tr, bl, br
            card_image.paste(flip_corners, (bleed-flip_corners.width, bleed-flip_corners.height))
            card_image.paste(flip_corners, (width-bleed, bleed-flip_corners.height))
            card_image.paste(flip_corners, (bleed-flip_corners.width, height-bleed))
            card_image.paste(flip_corners, (width-bleed, height-bleed))

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

        # cut out bleed
        if not include_bleed:
            card_image = card_image.crop((
                bleed,
                bleed,
                card_image.width - bleed,
                card_image.height - bleed
            ))

        # mark bleed area red
        if include_bleed == 'mark':
            mark_image = Image.new('RGBA', (width, height), (255, 255, 255, 0))
            draw = ImageDraw.Draw(mark_image)
            draw.polygon(
                [
                    # outer line
                    (0, 0),
                    (0, mark_image.height),
                    (mark_image.width, mark_image.height),
                    (mark_image.width, 0),
                    (0, 0),
                    # inner line
                    (bleed, bleed),
                    (mark_image.width - bleed, bleed),
                    (mark_image.width - bleed, mark_image.height - bleed),
                    (bleed, mark_image.height - bleed),
                    (bleed, bleed),
                ],
                fill=(255, 0, 0, 50),
            )
            card_image.paste(mark_image, mask=mark_image)

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
                    polygon = [(point[0]*Region.SCALE, point[1]*Region.SCALE) for point in polygon]

                if font.get('rotation'):
                    temp_image = Image.new('RGBA', region.size, (0, 0, 0, 0))
                    self.rich_text.render_text(
                        temp_image,
                        value,
                        Region({'x': 0, 'y': 0, 'height': card_image.height, 'width': card_image.width}),
                        font=font.get('font', 'regular'),
                        font_size=font.get('size', 20)*Region.SCALE,
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
                        font_size=font.get('size', 20)*Region.SCALE,
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
        try:
            base_image = Image.open(self.overlays_path/f"location_hi_base.png").convert("RGBA")

            # own icon
            value = side.get('connection')

            if value and value != "None":
                region = Region(side.get('connection_region'))
                connection_image = self.get_resized_cached(self.overlays_path / 'svg' / f"connection-{value}.svg", region.size)
                card_image.paste(base_image, region.pos, base_image)
                card_image.paste(connection_image, (region.x+int(12*Region.SCALE), region.y+int(12*Region.SCALE)), connection_image)

            # outgoing connections
            value = side.get('connections')

            if not value:
                return

            # grab and paint each icon
            for index, icon in enumerate(value):
                if not icon or icon == "None":
                    continue
                region = Region(side.get(f'connection_{index+1}_region'))
                connection_image = self.get_resized_cached(self.overlays_path / 'svg' / f"connection-{icon}.svg", region.size)
                card_image.paste(connection_image, (region.x+int(12*Region.SCALE), region.y+int(12*Region.SCALE)), connection_image)
        except Exception as e:
            print('error in connection', e)

    def render_icons(self, card_image, side):
        """ Renders commit icons """
        value = side.get('icons')
        if not value:
            return

        box_path = self.overlays_path/f"skill_box_{side.get_class()}.png"
        box_image = Image.open(box_path).convert("RGBA")
        for index, icon in enumerate(value):
            icon_path = self.overlays_path / 'svg' / f"skill_icon_{icon}.svg"
            icon_image = self.get_resized_cached(icon_path, (51, 51))
            card_image.paste(box_image, (10, index * 82 + 162 + 36), box_image)
            card_image.paste(icon_image, (31 + 36, index * 82 + 177 + 36), icon_image)

    def render_health(self, card_image, side):
        """ Add health and sanity overlay, if needed. """
        for stat in ['health', 'sanity']:
            if side.get(f'draw_{stat}_overlay', True) is False:
                continue
            value = side.get(stat)
            region = Region(side.get(f'{stat}_region'))
            if not side.get(f'draw_{stat}_overlay', False):
                if (not region) or value is None:
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

        icon_path = side.get('encounter_icon', side.card.encounter.icon)

        if not Path(icon_path).is_absolute():
            icon_path = Path(side.card.expansion.file_path).parent / Path(icon_path)
            icon_path = icon_path.absolute()

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
        try:
            for token in ('damage', 'horror'):
                value = int(side.get(token, "0"))
                if not value:
                    continue
                icon_path = self.overlays_path/f"{token}.png"
                raw_icon = self.get_cached(icon_path)
                raw_icon = self.get_resized_cached(icon_path, (int(raw_icon.width*Region.SCALE), int(raw_icon.height*Region.SCALE)))
                for i in range(value):
                    region = Region(side[f'{token}{i+1}_region'])
                    if not region:
                        continue
                    card_image.paste(raw_icon, (region.x, region.y), raw_icon)
        except Exception as e:
            print('error in enemy:', e)

    def render_template(self, card_image, side, bleed, include_bleed):
        """Render a template image onto a card"""
        template_value = side.get('template', '')
        if not template_value:
            return

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
            return

        if not include_bleed:
            template = self.get_resized_cached(template_path, (card_image.width-bleed*2, card_image.height-bleed*2))
            card_image.paste(template, (bleed, bleed), template)
        else:
            template = self.get_resized_cached(template_path, (card_image.width, card_image.height))
            card_image.paste(template, (0, 0), template)

    def render_illustration(self, card_image, side):
        """Render the illustration/portrait"""
        # Get illustration path
        illustration_path = side.get('illustration', None)
        if not illustration_path:
            return
        illustration_path = Path(illustration_path)
        if not illustration_path.is_absolute():
            illustration_path = side.card.expansion.find_file(illustration_path)
        if not illustration_path:
            return

        try:
            illustration = self.get_cached(illustration_path)
            region = Region(side['illustration_region'])

            # Calculate scaling
            illustration_scale = float(side.get('illustration_scale', 0))
            if not illustration_scale:
                illustration_scale = region.height / illustration.height
                if region.width / illustration.width > illustration_scale:
                    illustration_scale = region.width / illustration.width

            # Resize illustration
            new_width = int(illustration.width * illustration_scale)
            new_height = int(illustration.height * illustration_scale)
            illustration = self.get_resized_cached(illustration_path, (new_width, new_height))

            rotation = side.get('illustration_rotation', 0)
            if rotation:
                illustration = illustration.rotate(float(rotation))

            # Apply panning
            pan_x = side.get('illustration_pan_x', region.x)
            pan_y = side.get('illustration_pan_y', region.y)

            # Position and paste
            card_image.paste(
                illustration,
                (pan_x, pan_y),
                illustration
            )
        except Exception as e:
            print(f"Error rendering illustration: {str(e)}")

    def render_level(self, card_image, side):
        """Render the card level"""
        # Get level
        region = Region(side.get('level_region'))
        if not region:
            return

        level = side.get('level', None)
        if level is None or level == '' or level == 'None':
            level = 'no_level'

        card_class = side.get_class()
        is_skill = 'skill_' if side.get('type', '') == 'skill' else ''

        if is_skill and level != 'Custom':
            path = overlay_dir / 'levels' / f'skill_{level}.png'
        else:
            path = overlay_dir / 'levels' / f'{card_class}_{is_skill}{level}.png'

        level_icon = self.get_resized_cached(path, region.size)
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

            if isinstance(tokens, list):
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
                Region.unscaled({'x': (region.x+region.width//3), 'y': y, 'height': region.height//len(entries), 'width': (2*region.width)//3}),
                font=font.get('font', 'regular'),
                font_size=font.get('size', 32)*Region.SCALE,
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
