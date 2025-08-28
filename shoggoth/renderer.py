from time import time
from PIL import Image, ImageDraw, ImageFont, ImageOps
import pillow_jxl
from kivy.graphics.texture import Texture
from kivy.core.image import Image as kivy_img
from kivy.uix.image import CoreImage
import sys, os
import json
import re
from io import BytesIO
from shoggoth.rich_text import RichTextRenderer
import numpy as np
from shoggoth.files import template_dir, overlay_dir, icon_dir, asset_dir, defaults_dir
from pathlib import Path

from kivy.logger import Logger
import logging
logging.getLogger('PIL').setLevel(logging.ERROR)
logging.getLogger('pillow').setLevel(logging.ERROR)


class Region:
    bleed:tuple[int, int] = (0,0)

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
        return self.width > 0 and self.height > 0


class CardRenderer:
    """Renders card images based on card data"""

    # Standard card dimensions
    #CARD_WIDTH = 375
    #CARD_HEIGHT = 524
    CARD_WIDTH = 750
    CARD_HEIGHT = 1050

    def __init__(self):
        # Base paths
        self.assets_path = asset_dir
        self.templates_path = template_dir
        self.overlays_path = overlay_dir
        self.icons_path = icon_dir
        self.defaults_path = defaults_dir
        self.cache = {}

        # Initialize rich text renderer
        self.rich_text = RichTextRenderer(self)

    def get_thumbnail(self, card):
        """ Renders a low res version of the front of a card """
        image = self.render_card_side(card, card.front, size=1)
        image = image.resize((int(image.width*.5), int(image.height*.5)))
        buffer = BytesIO()
        image.save(buffer, format='jpeg', quality=50)
        buffer.seek(0)
        return buffer

    def get_card_textures(self, card):
        """Render both sides of a card"""
        front, back = self.get_card_images(card)

        # Convert PIL images to Kivy textures
        from time import time
        t = time()
        front_texture = self.pil_to_texture(front)
        back_texture = self.pil_to_texture(back)
        print(f'Time to texturize: {time()-t}')

        return front_texture, back_texture

    def get_card_images(self, card):
        """Get raw PIL images for the card"""
        # Render front and back
        front_image = self.render_card_side(card, card.front)
        back_image  = self.render_card_side(card, card.back)

        return front_image, back_image

    def export_card_images(self, card, folder, force=False):
        if force or card.front['type'] not in ('player', 'encounter'):
            front_image = self.render_card_side(card, card.front)
            front_image.save(os.path.join(folder, card.code + '_front.png'), quality=100, lossless=True)
        if force or card.back['type'] not in ('player', 'encounter'):
            back_image  = self.render_card_side(card, card.back)
            back_image.save(os.path.join(folder, card.code + '_back.png'), quality=100, lossless=True)

    def pil_to_texture(self, pil_image):
        """Convert PIL image to Kivy texture"""
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
        value = value.replace('<copy>', other_side.get('field', '<copy>'))
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
        value = value.replace('<exn>', str(side.card.encounter_number))
        if side.card.encounter and '<est>' in value:
            value = value.replace('<est>', str(len(side.card.encounter.cards)))
        else:
            value = value.replace('<est>', '')
        if side.card.encounter and side.card.encounter.icon:
            value = value.replace(
                '<esi>',
                f'<image src="{side.card.encounter.icon}">'
            )
        else:
            value = value.replace('<esi>', '')
        return value

    def render_card_side(self, card, side, size=1):
        """Render one side of a card"""
        from time import time

        self.current_card = card
        self.current_side = side
        self.current_opposite_side = card.front if side == card.back else card.back
        self.current_field = None

        height, width = int(self.CARD_HEIGHT*size), int(self.CARD_WIDTH*size)
        bleed = side.get('template_bleed', None)
        if bleed:
            height, width = int((self.CARD_HEIGHT+bleed[0]*2)*size), int((self.CARD_WIDTH+bleed[1]*2)*size)
            Region.bleed = (bleed[0], bleed[1])

        if side.get('orientation', 'vertical') == 'horizontal':
            card_image = Image.new('RGB', (height, width), (255, 255, 255))
        else:
            card_image = Image.new('RGB', (width, height), (255, 255, 255))

        self.render_illustration(card_image, side)
        self.render_template(card_image, side)
        if side['type'] in ('investigator'):
            self.render_illustration(card_image, side)

        for func in [
            self.render_level,
            self.render_encounter_icon,
            self.render_expansion_icon,
            self.render_act_info,
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
                Logger.info(f'Failed in {func}: {e}')
        return card_image

    def render_text(self, card_image, side):
        for field in [
            'cost', 'name', 'traits', 'text', 'subtitle', 'label',
            'attack', 'evade', 'health', 'stamina', 'sanity',
            'clues', 'doom', 'shroud', 'willpower', 'intellect',
            'combat', 'agility', 'illustrator', 'copyright', 'collection', 'difficulty'
        ]:
            self.current_field = field
            value = side.get(field)
            if not value:
                continue

            # Replacements
            value = self.text_replacement(field, value, side)

            # Checkboxes - primarily for Customizable
            if field == 'text':
                cb_value = side.get('checkbox_entries')
                if cb_value:
                    lines = ''
                    for slots, name, text in cb_value:
                        lines += '\n' + '☐'*slots + f' <b>{name}.</b> {text}'
                    value += lines

            if field == 'text':
                flavor = side.get('flavor_text', '')
                if flavor:
                    value += '\n'
                    value += f'<center><i>{flavor}</i>'

            try:
                region = Region(side[f'{field}_region'])
                font = side.get(f'{field}_font', {})
                polygon = side.get(f'{field}_polygon', None)
                if font.get('rotation'):
                    alignment = font.get('alignment', 'left')
                    temp_image = Image.new('RGBA', (region.height, region.width), (255, 255, 255, 0))
                    self.rich_text.render_text(
                        temp_image,
                        value,
                        {'x': 0, 'y': 0, 'height': region.width, 'width': region.height},
                        font=font.get('font', 'regular'),
                        font_size=font.get('size', 20),
                        fill=font.get('color', '#231f20'),
                        outline=font.get('outline'),
                        outline_fill=font.get('outline_color'),
                        alignment=font.get('alignment', 'left'),
                        polygon=polygon,
                    )
                    temp_image = temp_image.rotate(-90, expand=True)
                    card_image.paste(temp_image, (region.x-10, region.y), temp_image)
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
                import traceback
                print(f"Error rendering field: {field}\n {e}")
                traceback.print_exc()
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
        # own icon
        value = side.get('connection')
        if value and value != "None":
            # ready circle for coloring
            region = side.get('connection_region')
            connection_image = Image.open(self.overlays_path/f"location_{value}.png").convert("RGBA")
            connection_image = connection_image.resize((connection_image.width*2, connection_image.height*2))
            card_image.paste(connection_image, (region.x, region.y), connection_image)

        # outgoing connections
        value = side.get('connections')
        if not value:
            return

        # grab and paint each icon
        for index, icon in enumerate(value):
            if not icon or icon == "None":
                continue
            region = Region(side.get(f'connection_{index+1}_region'))

            connection_image = Image.open(self.overlays_path/f"location_{icon}.png").convert("RGBA")
            connection_image = connection_image.resize((connection_image.width*2, connection_image.height*2))
            card_image.paste(connection_image, region.pos, connection_image)


    def render_icons(self, card_image, side):
        value = side.get('icons')
        if not value:
            return

        box_path = self.overlays_path/f"skill_box_{side['class']}.png"
        box_image = Image.open(box_path).convert("RGBA")
        box_image = box_image.resize((109, 83))
        for index, icon in enumerate(value):
            overlay_path = self.overlays_path/f"skill_icon_{icon}.png"
            overlay_icon = Image.open(overlay_path).convert("RGBA")
            overlay_icon = overlay_icon.resize((overlay_icon.width * 2, overlay_icon.height * 2))
            card_image.paste(box_image, (0, index*84+165), box_image)
            card_image.paste(overlay_icon, (25, index*84+181), overlay_icon)

    def render_act_info(self, card_image, side):
        self.current_field = 'index'
        value = side.get('index')
        region = Region(side.get('scenarioindex_region'))
        if not region or not value:
            return

        self.rich_text.render_text(card_image, value, region, alignment='center')

    def render_health(self, card_image, side):
        """ Add health and sanity overlay, if needed. """
        for stat in ['health', 'sanity']:
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
        if not side.card.encounter:
            return

        region = Region(side.get('encounter_portrait_clip_region'))
        if not region:
            raise Exception("Encounter icon region not defined")

        overlay = side.get('encounter_overlay')
        if overlay:
            overlay_image = Image.open(overlay).convert("RGBA")
            overlay_region = side.get('encounter_overlay_region')
            overlay_image = overlay_image.resize((overlay_region.width, overlay_region.height))
            card_image.paste(overlay_image, (overlay_region.x, overlay_region.y), overlay_image)

        icon = Image.open(side.card.encounter.icon).convert("RGBA")
        icon = icon.resize((region.width, region.height))
        card_image.paste(icon, (region.x, region.y), icon)

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
            value = int(side.get(token, '0'))
            icon_path = self.overlays_path/f"{token}.png"
            raw_icon = Image.open(icon_path).convert("RGBA")
            for i in range(value):
                region = side[f'{token}{i+1}_region']
                if not region:
                    continue
                icon = raw_icon.resize((region.width, region.height))
                card_image.paste(icon, (region.x, region.y), icon)

    def render_template(self, card_image, side):
        """Render a template image onto a card"""
        template_value = side['template']
        if '<class>' in side['template']:
            side_class = side.get('classes', ['guardian'])
            card_class = side_class[0] if len(side_class) == 1 else 'multi'
            template_value = template_value.replace('<class>', card_class)
        if Path(template_value).is_file():
            template_path = Path(template_value)
        else:
            template_path = self.templates_path / (template_value + '.png')

        try:
            template = Image.open(template_path).convert("RGBA")
            template = template.resize((card_image.width, card_image.height))
            card_image.paste(template, (0, 0), template)
        except Exception as e:
            print(f"Error rendering template: {str(e)}")

    def render_illustration(self, card_image, side):
        """Render the illustration/portrait"""
        # Get illustration path
        illustration_path = side.get('illustration', None)
        if not illustration_path or not os.path.exists(illustration_path):
            return

        try:
            # Load illustration
            illustration = Image.open(illustration_path).convert("RGBA")

            # Get clip region
            clip_region = Region(side['illustration_region'])

            rotation = side.get('illustration_rotation', 0)
            if rotation:
                illustration = illustration.rotate(rotation)

            # Calculate scaling
            illustration_scale = side.get('illustration_scale', None)
            if not illustration_scale:
                if illustration.width > illustration.height:
                    illustration_scale = clip_region.height / illustration.height
                else:
                    illustration_scale = clip_region.width / illustration.width

            # Resize illustration
            new_width = int(illustration.width * illustration_scale)
            new_height = int(illustration.height * illustration_scale)
            illustration = illustration.resize((new_width, new_height))

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
        level = side.get('level')
        region = Region(side.get('level_region'))
        if not region:
            return

        if level is None or level == '':
            level_icon_path = self.overlays_path/f"no_level.png"
            level_icon = Image.open(level_icon_path).convert("RGBA")
            level_icon = level_icon.resize((level_icon.width*2, level_icon.height*2))
            card_image.paste(level_icon, (16, 7), level_icon)
            return

        level_icon_path = self.overlays_path/f"level_{level}.png"
        level_icon = Image.open(level_icon_path).convert("RGBA")
        level_icon = level_icon.resize((level_icon.width*2, level_icon.height*2))
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
            symbol = symbol.resize((symbol.width*2, symbol.height*2))
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
                    token_image = Image.open( overlay_dir / f"chaos_{token}.png")
                except:
                    continue
                token_image = token_image.resize((
                    int((region.width/4)/len(tokens)),
                    int((region.width/4)/len(tokens))
                ))
                x = int(region.x + token_image.width*token_index)
                card_image.paste(token_image, (x,y), token_image)

            self.rich_text.render_text(
                card_image,
                entry['text'],
                Region({'x': (region.x+region.width//3), 'y': y, 'height': region.height//len(entries), 'width': (2*region.width)//3}),
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
