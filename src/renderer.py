from time import time
from PIL import Image, ImageDraw, ImageFont, ImageOps
from kivy.graphics.texture import Texture
from kivy.core.image import Image as kivy_img
import os
import json
import re
from io import BytesIO
from rich_text import RichTextRenderer
import numpy as np

from kivy.uix.image import CoreImage

import logging
logging.getLogger('PIL').setLevel(logging.WARNING)
logging.getLogger('pillow').setLevel(logging.WARNING)

LOCATION_COLORS = {
    'Circle': 10,
    'CircleAlt': 10,
    'Clover': 50,
    'Cross': 10,
    'CrossAlt': 10,
    'Diamond': 10,
    'DiamondAlt': 10,
    'DoubleSlash': 10,
    'DoubleSlashAlt': 10,
    'Heart': 120,
    'HeartAlt': 10,
    'Hourglass': 10,
    'HourglassAlt': 10,
    'Moon': 10,
    'MoonAlt': -40,
    'Quote': 10,
    'Slash': 10,
    'SlashAlt': 10,
    'Spade': 10,
    'Square': 10,
    'SquareAlt': 10,
    'Star': 10,
    'StarAlt': 10,
    'T': 10,
    'TAlt': 10,
    'Triangle': 10,
    'TriangleAlt': 10,
}


class CardRenderer:
    """Renders card images based on card data"""

    # Standard card dimensions
    CARD_WIDTH = 375
    CARD_HEIGHT = 524
    #CARD_WIDTH = 750
    #CARD_HEIGHT = 1048

    def __init__(self):
        # Base paths
        self.assets_path = "assets"
        self.templates_path = os.path.join(self.assets_path, "templates")
        self.overlays_path = os.path.join(self.assets_path, "overlays")
        self.icons_path = os.path.join(self.assets_path, "icons")
        self.defaults_path = os.path.join(self.assets_path, "defaults")

        self.cache = {}

        # card faces that should render sideways
        self.horizontal_cards = (
            'investigator', 'investigator_back', 'act', 'agenda', 'act_back', 'agenda_back'
        )

        # Initialize rich text renderer
        self.rich_text = RichTextRenderer(self)


    def get_card_textures(self, card):
        """Render both sides of a card"""
        front, back = self.get_card_images(card)

        # Convert PIL images to Kivy textures
        front_texture = self.pil_to_texture(front)
        back_texture = self.pil_to_texture(back)

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

        front_image.save(os.path.join(folder, card.code + '_front.png'))
        back_image.save(os.path.join(folder, card.code + '_back.png'))

    def pil_to_texture(self, pil_image):
        """Convert PIL image to Kivy texture"""
        buffer = BytesIO()
        pil_image.save(buffer, format='png')
        buffer.seek(0)

        # Create texture
        im = CoreImage(buffer, ext='png')
        return im.texture

    def render_card_side(self, card, side):
        """Render one side of a card"""
        self.current_card = card
        self.current_side = side
        self.current_opposite_side = card.front if side == card.back else card.back
        self.current_field = None

        if side['type'] in self.horizontal_cards:
            card_image = Image.new('RGBA', (self.CARD_HEIGHT, self.CARD_WIDTH), (255, 255, 255, 255))
        else:
            card_image = Image.new('RGBA', (self.CARD_WIDTH, self.CARD_HEIGHT), (255, 255, 255, 255))

        self.render_illustration(card_image, side)
        self.render_template(card_image, side)
        if side['type'] in ('investigator'):
            self.render_illustration(card_image, side)

        for func in [
            self.render_name,
            self.render_cost,
            self.render_traits,
            self.render_rule_text,
            self.render_level,
            self.render_enemy_stats,
            self.render_encounter_icon,
            self.render_expansion_icon,
            self.render_subtitle,
            self.render_investigator_stats,
            self.render_health,
            self.render_act_info,
            self.render_clues,
            self.render_doom,
            self.render_shroud,
            self.render_icons,
            self.render_label,
            self.render_connection_icons,
            self.render_tokens,
        ]:
            try:
                func(card_image, side)
            except Exception as e:
                print(f'Failed: {e}')
        return card_image

    def render_tokens(self, card_image, side):
        value = side.get('tokens')
        if not value:
            return

        region = side['chaos_region']
        entry_height = region['height']//len(value)

        for index, icon in enumerate(value):
            text = value[icon]
            text_region = {
                'x': region['x']+47,
                'y': region['y']+(index*entry_height),
                'width': region['width']-47,
                'height': entry_height,
            }
            self.rich_text.render_text(card_image, text, text_region)


            overlay_path = os.path.join(self.overlays_path, f"chaos_{icon}.png")
            overlay_icon = Image.open(overlay_path).convert("RGBA")
            card_image.paste(overlay_icon, (region['x'], region['y']+(index*entry_height)), overlay_icon)

    def render_connection_icons(self, card_image, side):
        value = side.get('connections')
        if not value:
            return

        # ready circle for coloring
        circle_path = os.path.join(self.assets_path, 'icons/AHLCG-LocationBase.png')
        circle = Image.open(circle_path).convert("RGBA")
        h, s, v = circle.convert('HSV').split()
        np_s = np.array(h, dtype=np.int8)

        # grab and paint each icon
        for index, icon in enumerate(value):
            if not icon:
                continue
            region = side.get(f'connection_{index+1}_region')

            np_color = (np_s + LOCATION_COLORS.get(icon, 0))
            s_shifted = Image.fromarray(np_color, 'L')
            new_img = Image.merge('HSV', (s_shifted, s, v))
            card_image.paste(new_img, (region['x'], region['y']), circle)

            overlay_path = os.path.join(self.icons_path, f"AHLCG-Loc{icon}.png")
            overlay_icon = Image.open(overlay_path).convert("RGBA")
            card_image.paste(overlay_icon, (region['x']+5, region['y']+5), overlay_icon)


    def render_icons(self, card_image, side):
        value = side.get('icons')
        if not value:
            return

        box_path = os.path.join(self.overlays_path, f"skill_box_{side['class']}.png")
        box_image = Image.open(box_path).convert("RGBA")
        for index, icon in enumerate(value):
            overlay_path = os.path.join(self.overlays_path, f"skill_icon_{icon}.png")
            overlay_icon = Image.open(overlay_path).convert("RGBA")
            card_image.paste(box_image, (0, index*42+80), box_image)
            card_image.paste(overlay_icon, (10, index*42+88), overlay_icon)

    def render_doom(self, card_image, side):
        self.current_field = 'doom'
        value = side.get('doom')
        region = side.get('doom_region')
        if not region or not value:
            return

        self.rich_text.render_text(card_image, value, region, alignment='center', font="skill", fill="white", outline=1, outline_fill="black")

    def render_act_info(self, card_image, side):
        self.current_field = 'index'
        value = side.get('index')
        region = side.get('scenarioindex_region')
        if not region or not value:
            return

        self.rich_text.render_text(card_image, value, region, alignment='center')

    def render_shroud(self, card_image, side):
        self.current_field = 'shroud'
        value = side.get('shroud')
        region = side.get('shroud_region')
        if not region or not value:
            return

        self.rich_text.render_text(card_image, value, region, font="skill", alignment='center', fill='white', outline=1, outline_fill="black")

    def render_clues(self, card_image, side):
        self.current_field = 'clues'
        value = side.get('clues')
        region = side.get('clues_region')
        if not region or not value:
            return

        self.rich_text.render_text(card_image, value, region, font="skill", alignment='center', fill="white", outline=1, outline_fill="black")


    def render_health(self, card_image, side):
        for stat in ['stamina', 'sanity']:
            self.current_field = stat
            value = side.get(stat)
            region = side.get(f'{stat}_region')
            if not region or not value:
                continue

            overlay_path = os.path.join(self.overlays_path, f"{stat}_base.png")
            overlay_icon = Image.open(overlay_path).convert("RGBA")
            card_image.paste(overlay_icon, (region['x'], region['y']-10), overlay_icon)

            outline_fill = '#dd0000' if stat == 'stamina' else '#0000dd'

            self.rich_text.render_text(card_image, value, region, alignment='center', font="skill", fill="white", outline_fill=outline_fill, outline=1)


    def render_investigator_stats(self, card_image, side):
        """Render the card cost"""
        for stat in ['willpower', 'intellect', 'combat', 'agility']:
            self.current_field = stat
            value = side.get(stat, 0)
            region = side.get(f'{stat}_region')
            if not region:
                continue

            self.rich_text.render_text(card_image, value, region, alignment='center', font="skill")

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
            card_image.paste(overlay_image, (overlay_region['x'], overlay_region['y']), overlay_image)

        icon = Image.open(side.card.encounter.icon).convert("RGBA")
        icon = icon.resize((region['width'], region['height']))
        card_image.paste(icon, (region['x'], region['y']), icon)

    def render_enemy_stats(self, card_image, side):
        """Render enemy stats: Health, evade, combat, damage, horror. """
        for stat in ('attack', 'evade', 'health'):
            self.current_field = stat
            value = side.get(stat, None)
            if value != None:
                region = side[f'{stat}_region']
                self.rich_text.render_text(card_image, stat, region, alignment='center', font="cost", outline=1, outline_fill='black', fill='white')

        damage = int(side.get('damage', '0'))
        if damage > 5:
            print('damage more than 5 - cannot render, reducing to 5')
            damage = 5
        damage_icon_path = os.path.join(self.overlays_path, "damage.jp2")
        damage_icon = Image.open(damage_icon_path).convert("RGBA")
        for i in range(damage):
            region = side[f'damage{i+1}_region']
            card_image.paste(damage_icon, (region['x'], region['y']), damage_icon)

        horror = int(side.get('horror', '0'))
        if horror > 5:
            print('horror more than 5 - cannot render, reducing to 5')
            horror = 5
        horror_icon_path = os.path.join(self.overlays_path, "horror.jp2")
        horror_icon = Image.open(horror_icon_path).convert("RGBA")
        for i in range(horror):
            region = side[f'horror{i+1}_region']
            card_image.paste(horror_icon, (region['x'], region['y']), horror_icon)

    def render_subtitle(self, card_image, side):
        """Render the subtitle"""
        # Get name
        self.current_field = 'subtitle'
        text = side.get('subtitle', None)
        if not text:
            return

        region = side['subtitle_region']

        self.rich_text.render_text(card_image, text, region, alignment='center')

    def render_label(self, card_image, side):
        """Render the card name"""
        # Get name
        self.current_field = 'label'
        label = side.get('label', None)
        if not label:
            return

        region = side['label_region']

        self.rich_text.render_text(card_image, f'<b>{label}</b>', region, alignment='center')

    def render_template(self, card_image, side):
        """Render a template image onto a card"""
        template_path = os.path.join(self.templates_path, f"{side['type']}.png")
        if side['type'] in ('asset', 'event', 'skill', 'investigator', 'investigator_back'):
            template_path = os.path.join(self.templates_path, f"{side['type']}_{side['class']}.png")

        try:
            template = Image.open(template_path).convert("RGBA")
            #template = template.resize((self.CARD_WIDTH, self.CARD_HEIGHT))
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
            clip_region = side['portrait_clip_region']

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

    def render_name(self, card_image, side):
        """Render the card name"""
        # Get name
        self.current_field = 'name'
        name = side.get('name', None)
        if not name:
            return

        region = side['name_region']
        rotation = side.get('name_rotation')
        if rotation:
            temp_image = Image.new('RGBA', (region['height'], region['width']), (255, 255, 255, 0))
            self.rich_text.render_text(temp_image, name, {'x': 0, 'y': 0, 'height': region['width'], 'width': region['height']}, alignment='left', font="title")
            temp_image = temp_image.rotate(-90, expand=True)
            card_image.paste(temp_image, (region['x']-10, region['y']), temp_image)
        else:
            self.rich_text.render_text(card_image, name, region, alignment='center', font="title")

    def render_traits(self, card_image, side):
        """Render the card subtype"""
        self.current_field = 'traits'
        subtype = side.get('traits', None)
        if not subtype:
            return
        region = side['subtype_region']
        self.rich_text.render_text(card_image, subtype, region, alignment='center', font="bolditalic")

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
            icon_path = os.path.join(self.assets_path, 'numbers/AHLCG-Cost--.png')
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

        self.rich_text.render_text(card_image, cost, cost_region, alignment='center', font="cost", outline=1, outline_fill='black', fill='white')

    def render_level(self, card_image, side):
        """Render the card level"""
        # Get level
        level = side.get('level', None)
        if not level:
            return

        region = side['level_region']

        level_icon_path = os.path.join(self.overlays_path, f"level_{level}.png")
        if not os.path.exists(level_icon_path):
            return

        try:
            level_icon = Image.open(level_icon_path).convert("RGBA")
            level_icon = level_icon.resize((region['width'], region['height']))
            card_image.paste(level_icon, (region['x'], region['y']), level_icon)
        except Exception as e:
            print(f"Error rendering level: {str(e)}")

    def render_flavor_text(self, card_image, side):
        self.current_field = 'flavor_text'
        text = side.get('flavor_text', None)
        if not text:
            return

        region = side['flavor_region']

        # Get text polygon if available
        #text_polygon = self.get_setting('body_polygon', card_data, side, defaults)

        # Get alignment
        alignment = side.get('flavor_alignment', 'center')

        # Render using rich text renderer
        self.rich_text.render_text(
            card_image,
            text,
            region,
            #text_polygon,
            alignment=alignment
        )

    def render_class_symbols(self, card_image, card_data, side, defaults):
        """Render class symbols for multiclass cards"""
        # Get classes
        classes = self.get_setting('classes', card_data, side, defaults, [])
        if not classes or len(classes) < 2:
            # Single class or no class
            return

        # Class code mapping
        class_codes = {
            'guardian': 'G',
            'seeker': 'K',
            'mystic': 'M',
            'rogue': 'R',
            'survivor': 'V',
            'weakness': 'W',
            'neutral': 'N',
            'story': 'N',
        }

        # Render each class symbol
        for index, cls in enumerate(classes):
            if cls not in class_codes:
                continue

            class_code = class_codes[cls]
            symbol_path = os.path.join(self.overlays_path, f"class_symbol_{class_code}.png")

            if not os.path.exists(symbol_path):
                continue

            # Get symbol region key
            symbol_region_key = f"class_symbol_{index+1}_region"
            symbol_region = self.get_setting(symbol_region_key, card_data, side, defaults)

            if not symbol_region:
                # Default positions for up to 5 symbols
                default_regions = [
                    {'x': 300, 'y': 430, 'width': 20, 'height': 20},
                    {'x': 325, 'y': 430, 'width': 20, 'height': 20},
                    {'x': 350, 'y': 430, 'width': 20, 'height': 20},
                    {'x': 300, 'y': 455, 'width': 20, 'height': 20},
                    {'x': 325, 'y': 455, 'width': 20, 'height': 20}
                ]

                if index < len(default_regions):
                    symbol_region = default_regions[index]
                else:
                    continue

            try:
                symbol = Image.open(symbol_path).convert("RGBA")
                symbol = symbol.resize((symbol_region['width'], symbol_region['height']))
                card_image.paste(symbol, (symbol_region['x'], symbol_region['y']), symbol)
            except Exception as e:
                print(f"Error rendering class symbol: {str(e)}")
