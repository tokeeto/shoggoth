from time import time
from PIL import Image, ImageDraw, ImageFont, ImageOps
from kivy.graphics.texture import Texture
from kivy.core.image import Image as kivy_img
from kivy.uix.image import CoreImage
import os
import json
import re
from io import BytesIO
from shoggoth.rich_text import RichTextRenderer
import numpy as np
from shoggoth.files import template_dir, overlay_dir, icon_dir, asset_dir, defaults_dir


import logging
logging.getLogger('PIL').setLevel(logging.ERROR)
logging.getLogger('pillow').setLevel(logging.ERROR)

# HSL values for each connection icon
LOCATION_COLORS = {
    "Circle": (50, 0.71, 0.78),
    "Square": (-2, 0.73, 0.63),
    "Triangle": (-150, 0.41, 0.35),
    "Cross": (8, 0.65, 0.31),
    "Diamond": (98, 0.51, 0.53),
    "Slash": (40, 0.54, 0.46),
    "T": (-123, 0.39, 0.24),
    "Hourglass": (-20, 0.55, 0.30),
    "Moon": (-25, 0.51, 0.51),
    "DoubleSlash": (131, 0.34, 0.24),
    "Heart": (24, 0.72, 0.73),
    "Star": (-71, 0.36, 0.23),
    "Quote": (23, 0.64, 0.47),
    "Clover": (123, 0.23, 0.44),
    "Spade": (-26, 0.66, 0.72),

    "TriangleAlt": (50, 0.81, 0.88),
    "CrossAlt": (-2, 0.83, 0.73),
    "DiamondAlt": (-150, 0.51, 0.45),
    "SlashAlt": (8, 0.75, 0.51),
    "TAlt": (98, 0.61, 0.63),
    "HourglassAlt": (40, 0.64, 0.56),
    "MoonAlt": (-123, 0.49, 0.34),
    "DoubleSlashAlt": (-20, 0.65, 0.40),
    "HeartAlt": (-25, 0.61, 0.61),
    "StarAlt": (131, 0.44, 0.34),
    "CircleAlt": (24, 0.82, 0.83),
    "SquareAlt": (-71, 0.46, 0.33),
}


class Region:
    def __init__(self, data):
        if not data:
            data = {}
        self.x = data.get('x', 0)
        self.y = data.get('y', 0)
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
        return bool(self.x + self.y + self.width + self.height)


class CardRenderer:
    """Renders card images based on card data"""

    # Standard card dimensions
    #CARD_WIDTH = 375
    #CARD_HEIGHT = 524
    CARD_WIDTH = 747
    CARD_HEIGHT = 1057

    def __init__(self):
        # Base paths
        self.assets_path = asset_dir
        self.templates_path = template_dir
        self.overlays_path = overlay_dir
        self.icons_path = icon_dir
        self.defaults_path = defaults_dir
        self.cache = {}

        # card faces that should render sideways
        self.horizontal_cards = (
            'investigator', 'investigator_back', 'act', 'agenda', 'act_back', 'agenda_back'
        )

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

    def export_card_images(self, card, folder):
        front_image = self.render_card_side(card, card.front)
        back_image  = self.render_card_side(card, card.back)

        front_image.save(os.path.join(folder, card.code + '_front.jpeg'), quality=95)
        back_image.save(os.path.join(folder, card.code + '_back.jpeg'), quality=95)

    def pil_to_texture(self, pil_image):
        """Convert PIL image to Kivy texture"""
        buffer = BytesIO()
        pil_image.save(buffer, format='jpeg', quality=50)
        buffer.seek(0)

        # Create texture
        im = CoreImage(buffer, ext='jpeg')
        return im.texture

    def render_card_side(self, card, side, size=1):
        """Render one side of a card"""
        from time import time

        t = time()
        print(f'start render card side')
        self.current_card = card
        self.current_side = side
        self.current_opposite_side = card.front if side == card.back else card.back
        self.current_field = None

        height, width = int(self.CARD_HEIGHT*size), int(self.CARD_WIDTH*size)

        if side['type'] in self.horizontal_cards:
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
        ]:
            try:
                func(card_image, side)
            except Exception as e:
                print(f'Failed: {e}')
        print(f'end render card side: {time()-t}')
        return card_image

    def render_text(self, card_image, side):
        for field in ['cost', 'name', 'traits', 'text', 'subtitle', 'label', 'attack', 'evade', 'health', 'stamina', 'sanity', 'clues', 'doom', 'shroud', 'willpower', 'intellect', 'combat', 'agility', 'illustrator', 'copyright', 'collection', 'difficulty']:
            value = side.get(field)
            if not value:
                continue

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
                region = side[f'{field}_region']
                font = side.get(f'{field}_font', {})
                polygon = side.get(f'{field}_polygon', None)
                if font.get('rotation'):
                    alignment = font.get('alignment', 'left')
                    temp_image = Image.new('RGBA', (region['height'], region['width']), (255, 255, 255, 0))
                    self.rich_text.render_text(
                        temp_image,
                        value,
                        {'x': 0, 'y': 0, 'height': region['width'], 'width': region['height']},
                        font=font.get('font', 'regular'),
                        font_size=font.get('size', 20),
                        fill=font.get('color', '#231f20'),
                        outline=font.get('outline'),
                        outline_fill=font.get('outline_color'),
                        alignment=font.get('alignment', 'left'),
                        polygon=polygon,
                    )
                    temp_image = temp_image.rotate(-90, expand=True)
                    card_image.paste(temp_image, (region['x']-10, region['y']), temp_image)
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

        region = side['chaos_region']
        entry_height = region['height']//len(value)
        font = side.get('chaos_font', {})

        for index, icon in enumerate(value):
            text = value[icon]
            text_region = {
                'x': region['x']+94,
                'y': region['y']+(index*entry_height),
                'width': region['width']-94,
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
            card_image.paste(overlay_icon, (region['x'], region['y']+(index*entry_height)), overlay_icon)

    def render_connection_icons(self, card_image, side):
        circle_path = self.icons_path/'AHLCG-LocationBase.png'
        circle = Image.open(circle_path).convert("RGBA")

        # own icon
        value = side.get('connection')
        if value and value != "None":
            if value not in LOCATION_COLORS:
                raise ValueError(f"Invalid location icon: {value}")
            # ready circle for coloring
            region = side.get('connection_region')
            _circle = circle.resize((region['width'], region['height']))
            h, s, v = _circle.convert('HSV').split()
            np_h = np.array(h, dtype=np.uint8) + LOCATION_COLORS[value][0] % 256
            np_s = np.array(s, dtype=np.uint8) + LOCATION_COLORS[value][1] % 256
            np_v = np.array(v, dtype=np.uint8) + LOCATION_COLORS[value][2] % 256

            # grab and paint each icon
            h_shifted = Image.fromarray(np_h, 'L')
            s_shifted = Image.fromarray(np_s, 'L')
            v_shifted = Image.fromarray(np_v, 'L')
            new_img = Image.merge('HSV', (h_shifted, s_shifted, v_shifted))
            card_image.paste(new_img, (region['x'], region['y']), _circle)

            overlay_path = self.icons_path/f"AHLCG-Loc{value}.png"
            overlay_icon = Image.open(overlay_path).convert("RGBA")
            overlay_icon = overlay_icon.resize((overlay_icon.width*2, overlay_icon.height*2))
            card_image.paste(overlay_icon, (region['x'], region['y']), overlay_icon)

        # outgoing connections
        value = side.get('connections')
        if not value:
            return

        # ready circle for coloring
        circle_path = self.assets_path/'icons/AHLCG-LocationBase.png'
        circle = Image.open(circle_path).convert("RGBA")
        size_region = side.get('connection_1_region')
        circle = circle.resize((size_region['width'], size_region['height']))
        h, s, v = circle.convert('HSV').split()

        # grab and paint each icon
        for index, icon in enumerate(value):
            if not icon or icon == "None" or icon not in LOCATION_COLORS:
                continue
            region = Region(side.get(f'connection_{index+1}_region'))

            np_h = np.array(h, dtype=np.uint8) + LOCATION_COLORS[icon][0] % 256
            np_s = np.array(s, dtype=np.uint8) * LOCATION_COLORS[icon][1]
            np_v = np.array(v, dtype=np.uint8) * LOCATION_COLORS[icon][2]
            h_shifted = Image.fromarray(np_h, 'L')
            s_shifted = Image.fromarray(np_s, 'L')
            v_shifted = Image.fromarray(np_v, 'L')
            new_img = Image.merge('HSV', (h_shifted, s_shifted, v_shifted))
            card_image.paste(new_img, (region.x, region.y), circle)

            overlay_path = self.icons_path/f"AHLCG-Loc{icon}.png"
            overlay_icon = Image.open(overlay_path).convert("RGBA")
            overlay_icon = overlay_icon.resize((overlay_icon.width*2, overlay_icon.height*2))
            card_image.paste(
                overlay_icon,
                (region.center['x'] - overlay_icon.width//2, region.center['y']-overlay_icon.height//2),
                overlay_icon
            )


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
        region = side.get('scenarioindex_region')
        if not region or not value:
            return

        self.rich_text.render_text(card_image, value, region, alignment='center')

    def render_health(self, card_image, side):
        """ Add health and sanity overlay, if needed. """
        for stat in ['stamina', 'sanity']:
            self.current_field = stat
            value = side.get(stat)
            region = side.get(f'{stat}_region')
            if region is None or value is None:
                continue

            overlay_path = self.overlays_path/f"{stat}_base.png"
            overlay_icon = Image.open(overlay_path).convert("RGBA")
            overlay_icon = overlay_icon.resize((region['width'], region['height']))
            center_x = region['x']
            center_y = region['y'] - 15
            card_image.paste(overlay_icon, (center_x, center_y), overlay_icon)

    def render_expansion_icon(self, card_image, side):
        """Render the encounter icon """
        region = side.get('collection_portrait_clip_region')
        if not region:
            return

        icon = side.card.expansion.icon
        if not icon:
            return

        icon = Image.open(side.card.expansion.icon, formats=['png', 'jpg']).convert('RGBA')
        if icon.width > icon.height:
            icon = icon.resize((region['width'], int(region['height']*(icon.height/icon.width))))
        else:
            icon = icon.resize((int(region['width']*(icon.width/icon.height)), region['height']))

        # invert
        alpha = icon.getchannel('A')
        icon = icon.convert('RGB')
        icon = ImageOps.invert(icon)
        icon.putalpha(alpha)
        card_image.paste(icon, (region['x'], region['y']), icon)

    def render_encounter_icon(self, card_image, side):
        """Render the encounter icon """
        if not side.card.encounter:
            return

        region = side.get('encounter_portrait_clip_region', None)
        if not region:
            raise Exception("Encounter icon region not defined")

        overlay = side.get('encounter_overlay')
        if overlay:
            overlay_image = Image.open(overlay).convert("RGBA")
            overlay_region = side.get('encounter_overlay_region')
            overlay_image = overlay_image.resize((overlay_region['width'], overlay_region['height']))
            card_image.paste(overlay_image, (overlay_region['x'], overlay_region['y']), overlay_image)

        icon = Image.open(side.card.encounter.icon).convert("RGBA")
        icon = icon.resize((region['width'], region['height']))
        card_image.paste(icon, (region['x'], region['y']), icon)

    def render_slots(self, card_image, side):
        """Render the slot icons """
        slots = side.get('slots')
        slot = side.get('slot')
        if not slots:
            slots = [slot]
        if not slots:
            return

        for index, slot in enumerate(slots):
            print('render slots inner:', index, slot)
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
                icon = raw_icon.resize((region['width'], region['height']))
                card_image.paste(icon, (region['x'], region['y']), icon)

    def render_template(self, card_image, side):
        """Render a template image onto a card"""
        template_path = self.templates_path/f"{side['type']}.png"
        if side['type'] in ('asset', 'event', 'skill', 'investigator', 'investigator_back'):
            template_path = self.templates_path/f"{side['type']}_{side['class']}.png"

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
            illustration = Image.open(illustration_path, formats=['png', 'jpg', 'png']).convert("RGBA")

            # Get clip region
            clip_region = side['illustration_region']

            rotation = side.get('illustration_rotation', 0)
            if rotation:
                illustration = illustration.rotate(rotation)

            # Calculate scaling
            illustration_scale = side.get('illustration_scale', None)
            if not illustration_scale:
                if illustration.width > illustration.height:
                    illustration_scale = clip_region['height'] / illustration.height
                else:
                    illustration_scale = clip_region['width'] / illustration.width

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
                (clip_region['x']+pan_x, clip_region['y']+pan_y),
                illustration
            )
        except Exception as e:
            print(f"Error rendering illustration: {str(e)}")

    def render_rule_text(self, card_image, side):
        """Render the card rule text"""
        self.current_field = 'rule_text'
        rule_text = side.get('rule_text', '')
        if not rule_text:
            return

        text_region = side['body_region']

        # Checkboxes - primarily for Customizable
        value = side.get('checkbox_entries')
        if value:
            lines = ''
            for slots, name, text in value:
                lines += '\n' + '☐'*slots + f' <b>{name}.</b> {text}'
            rule_text += lines

        flavor_text = side.get('flavor_text', '')
        if flavor_text:
            rule_text += '\n'
            rule_text += f'<center><i>{flavor_text}</i>'

        # Get text polygon if available
        text_polygon = side.get('body_polygon', None)

        # Get alignment
        #alignment = self.get_setting('body_alignment', card_data, side, defaults, 'left')

        # Render using rich text renderer
        self.rich_text.render_text(
            card_image,
            rule_text,
            text_region,
            polygon=text_polygon,
            alignment='left'
        )

    def render_cost(self, card_image, side):
        """Render the card cost"""
        self.current_field = 'cost'
        cost = side.get('cost', None)
        if not cost:
            return

        cost_region = side['cost_region']

        # Draw cost
        if cost == '-':
            icon_path = self.assets_path/'numbers/AHLCG-Cost--.png'
            dash_icon = Image.open(icon_path).convert("RGBA")
            dash_2 = dash_icon.convert('HSV')
            h, s, v = dash_2.split()
            np_h = np.array(s, dtype=np.int8)
            np_h = (np_h * 0)
            h_shifted = Image.fromarray(np_h, 'L')
            new_img = Image.merge('HSV', (h, h_shifted, v))
            #new_img = new_img.resize((cost_region['width'], cost_region['height']))
            card_image.paste(new_img, (cost_region['x']+5, cost_region['y']+5), dash_icon)
            return

        self.rich_text.render_text(card_image, cost, cost_region, alignment='center', font="cost", font_size=40, outline=1, outline_fill='black', fill='white')

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
        classes = side.get('classes')
        if not classes:
            return

        # Render each class symbol
        for index, cls in enumerate(classes):
            symbol_path = self.overlays_path/f"class_symbol_{cls}.png"
            region = side.get(f"class_symbol_{index+1}_region")

            symbol = Image.open(symbol_path).convert("RGBA")
            symbol = symbol.resize((symbol.width*2, symbol.height*2))
            card_image.paste(symbol, (region['x'], region['y']), symbol)
