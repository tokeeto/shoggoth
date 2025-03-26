from time import time
from PIL import Image, ImageDraw, ImageFont, ImageOps
from kivy.graphics.texture import Texture
import os
import json
import re
from io import BytesIO
from rich_text import RichTextRenderer

from kivy.uix.image import CoreImage


class CardRenderer:
    """Renders card images based on card data"""

    # Standard card dimensions
    CARD_WIDTH = 375
    CARD_HEIGHT = 524

    def __init__(self):
        # Base paths
        self.assets_path = "assets"
        self.templates_path = os.path.join(self.assets_path, "templates")
        self.overlays_path = os.path.join(self.assets_path, "overlays")
        self.icons_path = os.path.join(self.assets_path, "icons")
        self.defaults_path = os.path.join(self.assets_path, "defaults")

        self.cache = {}

        # Initialize rich text renderer
        self.rich_text = RichTextRenderer(self.assets_path)

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

    def pil_to_texture(self, pil_image):
        """Convert PIL image to Kivy texture"""
        # Convert PIL image to bytes
        buffer = BytesIO()
        pil_image.save(buffer, format='png')
        buffer.seek(0)

        # Create texture
        im = CoreImage(BytesIO(buffer.read()), ext='png')
        return im.texture

    def render_card_side(self, card, side):
        """Render one side of a card"""
        #if not self.cache.get('base_image', None):
        # Create blank image
        card_image = Image.new('RGBA', (self.CARD_WIDTH, self.CARD_HEIGHT), (255, 255, 255, 255))
        self.render_illustration(card_image, side)
        self.render_template(card_image, side)
        #self.cache['base_image'] = card_image

        #card_image = self.cache['base_image'].copy()
        for func in [
            self.render_name,
            self.render_cost,
            self.render_traits,
            self.render_rule_text,
            self.render_level,
            self.render_label,
            self.render_enemy_stats,
            self.render_encounter_icon,
            self.render_expansion_icon,
        ]:
            try:
                func(card_image, side)
            except Exception as e:
                print(f'{func} failed: {e}')

        return card_image

    def render_expansion_icon(self, card_image, side):
        """Render the encounter icon """
        region = side.get('collection_portrait_clip_region')
        print(f'region is {region=}')
        print(f'icon is {side.card.expansion.icon}')
        icon = Image.open(side.card.expansion.icon, formats=['png', 'jpg']).convert('RGBA')
        icon = icon.resize((region['width'], region['height']))
        # invert
        alpha = icon.getchannel('A')
        icon = icon.convert('RGB')
        icon = ImageOps.invert(icon)
        icon.putalpha(alpha)
        card_image.paste(icon, (region['x'], region['y']), icon)

    def render_encounter_icon(self, card_image, side):
        """Render the encounter icon """
        if not side.card.encounter.icon:
            raise Exception("No encounter icon")
        region = side.get('encounter_portrait_clip_region', None)
        if not region:
            raise Exception("Encounter icon region not defined")
        icon = Image.open(side.card.encounter.icon).convert("RGBA")
        icon = icon.resize((region['width'], region['height']))
        card_image.paste(icon, (region['x'], region['y']), icon)

    def render_enemy_stats(self, card_image, side):
        """Render enemy stats: Health, evade, combat, damage, horror. """
        attack = side.get('attack', None)
        if attack != None:
            region = side['attack_region']
            self.rich_text.render_text(card_image, attack, region, alignment='center', font="cost", outline=2, outline_fill='black', fill='white')

        evade = side.get('evade', None)
        if evade != None:
            region = side['evade_region']
            self.rich_text.render_text(card_image, evade, region, alignment='center', font="cost", outline=2, outline_fill='black', fill='white')

        health = side.get('health', None)
        if health != None:
            region = side['health_region']
            self.rich_text.render_text(card_image, health, region, alignment='center', font="cost", outline=2, outline_fill='black', fill='white')

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


    def render_label(self, card_image, side):
        """Render the card name"""
        # Get name
        label = side.get('label', None)
        if not label:
            return

        region = side['label_region']

        self.rich_text.render_text(card_image, label, region, alignment='center', font="title")

    def render_template(self, card_image, side):
        """Render a template image onto a card"""
        template_path = os.path.join(self.templates_path, f"{side['type']}.png")
        if side['type'] in ('asset', 'event'):
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
                (clip_region['x'] + pan_x, clip_region['y'] - pan_y),
                illustration
            )
        except Exception as e:
            print(f"Error rendering illustration: {str(e)}")

    def render_name(self, card_image, side):
        """Render the card name"""
        # Get name
        name = side.get('name', None)
        if not name:
            return

        name_region = side['name_region']

        self.rich_text.render_text(card_image, name, name_region, alignment='center', font="title")

    def render_traits(self, card_image, side):
        """Render the card subtype"""
        subtype = side.get('traits', None)
        if not subtype:
            return

        # Get subtype region
        region = side['subtype_region']

        # Draw subtype
        self.rich_text.render_text(card_image, subtype, region, alignment='center', font="bolditalic")

    def render_rule_text(self, card_image, side):
        """Render the card rule text"""
        rule_text = side.get('rule_text', '')
        if not rule_text:
            return

        text_region = side['body_region']

        flavor_text = side.get('flavor_text', '')
        if flavor_text:
            rule_text += '\n'
            rule_text += f'<center><i>{flavor_text}</i>'

        # Get text polygon if available
        #text_polygon = self.get_setting('body_polygon', card_data, side, defaults)

        # Get alignment
        #alignment = self.get_setting('body_alignment', card_data, side, defaults, 'left')

        # Render using rich text renderer
        self.rich_text.render_text(
            card_image,
            rule_text,
            text_region,
            #text_polygon,
            alignment='left'
        )

    def render_cost(self, card_image, side):
        """Render the card cost"""
        cost = side.get('cost', None)
        if not cost:
            return

        cost_region = side['cost_region']

        # Draw cost
        if cost == '-':
            icon_path = os.path.join(self.assets_path, 'numbers/AHLCG-Cost--.png')
            dash_icon = Image.open(icon_path).convert("RGBA")
            template = dash_icon.resize((cost_region['width'], cost_region['height']))
            card_image.paste(dash_icon, (cost_region['x']+5, cost_region['y']+5), dash_icon)
            return

        self.rich_text.render_text(card_image, cost, cost_region, alignment='center', font="cost", outline=2, outline_fill='black', fill='white')

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

    def render_location_stats(self, card_image, card_data, side, defaults):
        """Render location card statistics"""
        # Get stats
        shroud = self.get_setting('shroud', card_data, side, defaults, 1)
        clues = self.get_setting('clues', card_data, side, defaults, 1)
        clues_per_investigator = self.get_setting('clues_per_investigator', card_data, side, defaults, False)

        # Load font
        try:
            stats_font = ImageFont.truetype(os.path.join(self.assets_path, 'fonts', 'Arkhamic.ttf'), 24)
        except IOError:
            stats_font = ImageFont.load_default()

        draw = ImageDraw.Draw(card_image)

        # Stat positions (these would come from defaults ideally)
        positions = {
            'shroud': {'x': 330, 'y': 120},
            'clues': {'x': 330, 'y': 160},
        }

        # Draw stats
        draw.text((positions['shroud']['x'], positions['shroud']['y']), str(shroud), fill=(255, 255, 255), font=stats_font)

        # Draw clues, with per-investigator symbol if needed
        clue_text = str(clues)
        if clues_per_investigator:
            clue_text += " per investigator"  # This would be replaced with an icon ideally

        draw.text((positions['clues']['x'], positions['clues']['y']), clue_text, fill=(255, 255, 255), font=stats_font)
