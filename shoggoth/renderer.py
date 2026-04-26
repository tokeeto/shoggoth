from PIL import Image, ImageOps, ImageDraw
import os
from collections import OrderedDict
from io import BytesIO
from shoggoth.rich_text import RichTextRenderer
from shoggoth.files import template_dir, overlay_dir, icon_dir, asset_dir, defaults_dir, translation_dir
from pathlib import Path
import pyvips
import re
import json
import functools

_ILLUS_LRU_MAXSIZE = 24


class _ImgDims:
    """Minimal stand-in returned by get_illustration_cached — holds only dimensions."""
    __slots__ = ('width', 'height')

    def __init__(self, w, h):
        self.width = w
        self.height = h

import logging
logging.getLogger('PIL').setLevel(logging.ERROR)
logging.getLogger('pillow').setLevel(logging.ERROR)


card_value_pattern = re.compile(r'(<:(.+?) (.+?)>)')


def scale(x: int | None, s: float):
    if not x:
        return x
    return int(x * s)


class Region:
    x: int
    y: int
    width: int
    height: int

    def __init__(self, data, scale: float = 1.0):
        if not data:
            data = {}
        self.x = int(data.get('x', 0) * scale)
        self.y = int(data.get('y', 0) * scale)
        self.width = int(data.get('width', 0) * scale)
        self.height = int(data.get('height', 0) * scale)
        self.is_attached = bool(data.get('is_attached', False))
        self.attach_before = data.get('attach_before')
        self.attach_after = data.get('attach_after')

    @staticmethod
    def unscaled(data):
        return Region(data, scale=1.0)

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

    def __init__(self, locale='en'):
        # Base paths
        self.assets_path = asset_dir
        self.templates_path = template_dir
        self.overlays_path = overlay_dir
        self.icons_path = icon_dir
        self.defaults_path = defaults_dir
        self.cache = {}
        self.resized_cache = {}
        self.card_wo_illus_cache = {}
        self._illus_dims_cache = {}      # path → _ImgDims; cheap, never evicted
        self._illus_resized_lru = OrderedDict()  # (path, size) → PIL Image; bounded LRU
        self.translations = {}
        self.locale = locale
        self.translations = {}
        if self.locale:
            try:
                self.translations = json.load(open(translation_dir / f'{self.locale}.json'))
            except Exception as e:
                print('error while loading translation for renderer:', e)

        # Initialize rich text renderer
        self.rich_text = RichTextRenderer(self)

    def get_illustration_cached(self, path) -> _ImgDims:
        """Return illustration dimensions without decoding pixels.

        Only .width and .height are meaningful on the returned object.
        pyvips reads just the image header, so this is cheap even for large JPEGs.
        """
        if path not in self._illus_dims_cache:
            if str(path).endswith('.pdf'):
                vips_image = pyvips.Image.pdfload(str(path), dpi=72)
            else:
                vips_image = pyvips.Image.new_from_file(str(path))
            self._illus_dims_cache[path] = _ImgDims(vips_image.width, vips_image.height)
        return self._illus_dims_cache[path]

    def get_illustration_resized_cached(self, path, size) -> Image.Image:
        """Return a resized illustration, using vips thumbnail for fast shrink-on-load.

        Results are kept in a bounded LRU (_ILLUS_LRU_MAXSIZE entries) so that
        repeated renders of the same illustration (e.g. multiple copies of a card)
        hit the cache while old entries are evicted to keep RAM bounded.
        Full-resolution illustrations are never stored in self.cache.
        """
        if size[0] * size[1] > 24_000_000:
            raise Exception('image too big, dangerous')
        key = (path, size)
        if key in self._illus_resized_lru:
            self._illus_resized_lru.move_to_end(key)
            return self._illus_resized_lru[key]

        if str(path).endswith('.pdf'):
                vips_image = pyvips.Image.pdfload(str(path), dpi=600, page=1)
                image = Image.frombytes(
                    'RGBA',
                    (vips_image.width, vips_image.height),
                    vips_image.write_to_memory()
                )
                self.resized_cache[(path, size)] = image
        elif str(path).endswith('.svg'):
            vips_image = pyvips.Image.new_from_file(str(path))
            svg_scale = size[0] / vips_image.width
            if svg_scale > (size[1] / vips_image.height):
                svg_scale = size[1] / vips_image.height
            vips_image = pyvips.Image.new_from_file(str(path), scale=svg_scale)
            image = Image.frombytes('RGBA', (vips_image.width, vips_image.height), vips_image.write_to_memory())
        else:
            # thumbnail() uses JPEG shrink-on-load: decodes at 1/2, 1/4 or 1/8
            # native resolution, so large photos are decoded at a fraction of
            # their full size before the final resize step.
            vips_image = pyvips.Image.thumbnail(str(path), size[0], height=size[1], size='force')
            mode = 'RGBA' if vips_image.bands == 4 else 'RGB'
            image = Image.frombytes(mode, (vips_image.width, vips_image.height), vips_image.write_to_memory())

        self._illus_resized_lru[key] = image
        if len(self._illus_resized_lru) > _ILLUS_LRU_MAXSIZE:
            self._illus_resized_lru.popitem(last=False)
        return image

    def get_cached(self, path) -> Image.Image:
        if path not in self.cache:
            if str(path).endswith('.pdf'):
                vips_image = pyvips.Image.pdfload(str(path), dpi=600, page=1)
            else:
                vips_image = pyvips.Image.new_from_file(str(path))
            bands = vips_image.bands
            mode = 'RGBA' if bands == 4 else 'RGB'
            self.cache[path] = Image.frombytes(mode, (vips_image.width, vips_image.height), vips_image.write_to_memory())
        return self.cache[path]

    def get_resized_cached(self, path, size) -> Image.Image:
        if (path, size) not in self.resized_cache:
            if str(path).endswith('.pdf'):
                vips_image = pyvips.Image.pdfload(str(path), dpi=600, page=1)
                image = Image.frombytes(
                    'RGBA',
                    (vips_image.width, vips_image.height),
                    vips_image.write_to_memory()
                )
                self.resized_cache[(path, size)] = image
            elif str(path).endswith('.svg'):
                vips_image = pyvips.Image.new_from_file(str(path))
                svg_scale = size[0]/vips_image.width
                if svg_scale > (size[1]/vips_image.height):
                    svg_scale = size[1]/vips_image.height
                vips_image = pyvips.Image.new_from_file(str(path), scale=svg_scale)
                image = Image.frombytes(
                    'RGBA',
                    (vips_image.width, vips_image.height),
                    vips_image.write_to_memory()
                )
                self.resized_cache[(path, size)] = image
            else:
                img = self.get_cached(path)
                if img.size == size:
                    return img
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
        image = self.render_card_side(card, card.front, include_bleed=False, width=375, height=525, bleed=18)
        return image

    def get_card_textures(self, card, size, bleed=True, format='jpeg', quality=80):
        """Render both sides of a card"""
        import time
        t = time.time()
        front = self.render_card_side(card, card.front, include_bleed=bleed, **size)
        back = self.render_card_side(card, card.back, include_bleed=bleed, **size)
        print(f'get_card_textures in {time.time()-t}')
        return front, back

    def export_card_images(self, card, folder, size, include_backs=False, bleed=True, format='png', quality=100, separate_versions=True):
        lossless = quality == 100
        outputs = []

        # should each version (eg. 1/2 and 2/2) be printed seperately or as 1-2/2?
        faces = card.versions
        if not separate_versions:
            faces = [card]

        for index, variant in enumerate(faces):
            for face, name in ((variant.front, 'front'), (variant.back, 'back')):
                # if this is a repeated card, only export it once
                if face['type'] in ('player', 'encounter') and not include_backs:
                    file_path = Path(folder) / f'{face["type"]}.{format}'
                    if not file_path.exists():
                        image = self.render_card_side(variant, face, include_bleed=bleed, **size)
                        image.save(file_path, quality=quality, lossless=lossless, compress_level=1)
                    outputs.append(str(file_path))
                else:
                    file_path = Path(folder) / f'{variant.id}_{name}_{index}.{format}'
                    image = self.render_card_side(variant, face, include_bleed=bleed, **size)
                    image.save(file_path, quality=quality, lossless=lossless, compress_level=1)
                    outputs.append(str(file_path))
        return outputs

    @staticmethod
    def expected_export_paths(card, folder, size, include_backs=False, bleed=True, format='png', quality=100, separate_versions=True):
        """ Get the expected output paths from export_card_images without actually generating images """
        outputs = []
        faces = card.versions
        if not separate_versions:
            faces = [card]

        for index, variant in enumerate(faces):
            for face, name in ((variant.front, 'front'), (variant.back, 'back')):
                # if this is a repeated card, only export it once
                if face['type'] in ('player', 'encounter') and not include_backs:
                    file_path = Path(folder) / f'{face["type"]}.{format}'
                    outputs.append(str(file_path))
                else:
                    file_path = Path(folder) / f'{card.id}_{name}_{index}.{format}'
                    outputs.append(str(file_path))
        return outputs

    def pil_to_texture(self, pil_image):
        """Convert PIL image to buffer"""
        buffer = BytesIO()
        pil_image.save(buffer, format='jpeg', quality=50)
        buffer.seek(0)
        return buffer

    def card_value(self, project, id, field):
        path = field.split('.')
        val = project.get_card(id)
        if len(path) > 1:
            if path[0] == 'front':
                val = val.front
            if path[0] == 'back':
                val = val.back
            path = path[1:]
        val = val.get(path[0])

        return val

    def text_replacement(self, field, value, side):
        """ handles advanced text replacement fields """
        value = value.replace('<name>', side.card.name)
        if side == side.card.front:
            other_side = side.card.back
        else:
            other_side = side.card.front
        value = value.replace('<copy>', other_side.get(field, '<copy>'))
        if side.card.project.icon:
            path = side.card.project.find_file(side.card.project.icon)
            value = value.replace('<exi>', f'<image src="{path}">')
        else:
            value = value.replace('<exi>', '')
        value = value.replace('<exn>', str(side.card.project_number))
        if side.card.encounter_number:
            value = value.replace('<esn>', str(side.card.encounter_number))
        else:
            value = value.replace('<esn>', '')

        if side.card.encounter and '<est>' in value:
            value = value.replace('<est>', str(side.card.encounter.total_cards))
        else:
            value = value.replace('<est>', '')
        if side.card.encounter and side.card.encounter.icon:
            path = side.card.project.find_file(side.card.project.icon)
            value = value.replace('<esi>', f'<image src="{path}">')
        else:
            value = value.replace('<esi>', '')

        value = value.replace('<copyright>', side.card.get('copyright') or '')

        # card reference
        references = re.findall(card_value_pattern, value)
        for match in references:
            value = value.replace(match[0], self.card_value(side.card.project, match[1], match[2]))

        # translations
        if value.startswith('%:'):
            value = self.translations.get(value[2:], value[2:])

        return value

    def render_card_side_without_illustration(self, card, side, include_bleed=True):
        from shoggoth.card import Card
        if card in self.card_wo_illus_cache[card]:
            return self.card_wo_illus_cache[card]

        c = Card(card.data, project=card.project, encounter=card.encounter)
        c.set('illustration', None)
        self.card_wo_illus_cache[card] = self.render_card_side(c, side, include_bleed)
        return self.card_wo_illus_cache[card]

    def render_card_side(self, card, side, include_bleed=True, width=1500, height=2100, bleed=72):
        """Render one side of a card"""
        s = width / 1500

        height, width = height + bleed * 2, width + bleed * 2
        if side.get('orientation', 'vertical') == 'horizontal':
            width, height = height, width

        card_image = Image.new('RGB', (width, height), (255, 255, 255))

        template_bleed = side.get('template_bleed', False)
        try:
            self.render_illustration(card_image, side, s)
        except Exception as e:
            print('failed illus', e)
        try:
            self.render_template(card_image, side, bleed, template_bleed)
        except Exception as e:
            print('failed template', e)
        if side['type'] in ('investigator'):
            self.render_illustration(card_image, side, s)

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
            self.render_project_icon,
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
                func(card_image, side, s)
            except Exception as e:
                logging.debug(f'Failed in {func}: {e}')
                print(f'Failed in {func}: {e}')

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

    def render_text(self, card_image, side, s: float = 1.0):
        for field in [
            'cost', 'name', 'traits', 'text', 'subtitle', 'label', 'index',
            'attack', 'evade', 'health', 'stamina', 'sanity', 'victory',
            'clues', 'doom', 'shroud', 'willpower', 'intellect',
            'combat', 'agility', 'illustrator', 'copyright', 'collection', 'difficulty',
            'text1', 'text2', 'text3',
        ]:
            value = side.get(field)
            region = Region(side.get(f'{field}_region', None), s)

            if region.is_attached or not region:
                # this field is part of another block, and doesn't render on its own.
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
                    polygon = [(point[0]*s, point[1]*s) for point in polygon]

                if font.get('rotation'):
                    temp_image = Image.new('RGBA', region.size, (0, 0, 0, 0))
                    self.rich_text.render_text(
                        temp_image,
                        value,
                        Region.unscaled({'x': 0, 'y': 0, 'height': region.height, 'width': region.width}),
                        font=font.get('font', 'regular'),
                        font_size=scale(font.get('size', 20), s),
                        min_font_size=scale(font.get('min_size', None), s),
                        fill=font.get('color', '#231f20'),
                        outline=scale(font.get('outline', None), s),
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
                        font_size=scale(font.get('size', 20), s),
                        min_font_size=scale(font.get('min_size', None), s),
                        fill=font.get('color', '#231f20'),
                        outline=scale(font.get('outline'), s),
                        outline_fill=font.get('outline_color'),
                        alignment=font.get('alignment', 'left'),
                        polygon=polygon,
                    )
            except Exception as e:
                print(f"Error rendering field: {field}\n {e}")
                continue

    def render_tokens(self, card_image, side, s: float = 1.0):
        value = side.get('tokens')
        if not value:
            return

        region = Region(side['chaos_region'], s)
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
            native = self.get_cached(overlay_path)
            overlay_icon = self.get_resized_cached(overlay_path, (native.width * 2, native.height * 2))
            card_image.paste(overlay_icon, (region.x, region.y+(index*entry_height)), overlay_icon)

    def render_connection_icons(self, card_image, side, s: float = 1.0):
        try:

            # own icon
            value = side.get('connection')

            if value and value != "None":
                region = Region(side.get('connection_region'), s)
                try:
                    connection_image = self.get_resized_cached(self.overlays_path / 'svg' / f"connection_{value}.svg", region.size)
                except:
                    return

                padding = int(24*s)
                base_image = self.get_resized_cached(
                    self.overlays_path / "location_hi_base.png",
                    (region.width + padding, region.height + padding)
                )
                card_image.paste(base_image, region.pos, base_image)
                card_image.paste(connection_image, (region.x+int(12*s), region.y+int(12*s)), connection_image)

            # outgoing connections
            value = side.get('connections')

            if not value:
                return

            # grab and paint each icon
            for index, icon in enumerate(value):
                if not icon or icon == "None":
                    continue
                region = Region(side.get(f'connection_{index+1}_region'), s)
                try:
                    connection_image = self.get_resized_cached(self.overlays_path / 'svg' / f"connection_{icon}.svg", region.size)
                except:
                    continue
                card_image.paste(connection_image, (region.x+int(12*s), region.y+int(12*s)), connection_image)
        except Exception as e:
            print('error in connection', e)

    def render_icons(self, card_image, side, s: float = 1.0):
        """ Renders commit icons """
        value = side.get('icons')
        if not value:
            return

        box_path = side.get('icons_box', 'skill_box_<class>.png').replace('<class>', side.get_class())
        box_path = self.overlays_path / box_path

        icon_region = Region(side.get('icons_region', {"x": 112, "y": 424, "width": 0, "height": 164}), s)
        box_region = Region(side.get('icons_box_region', {"x": -112, "y": -28, "width": 270, "height": 160}), s)
        box_image = self.get_resized_cached(box_path, box_region.size)

        for index, icon in enumerate(value):
            icon_path = self.overlays_path / 'svg' / f"skill_icon_{icon}.svg"
            icon_image = self.get_resized_cached(icon_path, (scale(102, s), scale(102, s)))
            card_image.paste(box_image, (icon_region.x + box_region.x, index * icon_region.height + icon_region.y + box_region.y), box_image)
            card_image.paste(icon_image, (icon_region.x, index * icon_region.height + icon_region.y), icon_image)

    def render_health(self, card_image, side, s: float = 1.0):
        """ Add health and sanity overlay, if needed. """
        for stat in ['health', 'sanity']:
            if side.get(f'draw_{stat}_overlay', True) is False:
                continue
            value = side.get(stat, None)
            region = Region(side.get(f'{stat}_region'), s)
            if not side.get(f'draw_{stat}_overlay', False):
                if (not region) or value is None:
                    continue

            overlay_path = self.overlays_path/f"{stat}_base.png"
            overlay_icon = self.get_resized_cached(overlay_path, (region.width, region.height))
            center_x = region.x
            center_y = region.y - (scale(23, s) if stat == 'health' else scale(15, s))
            card_image.paste(overlay_icon, (center_x, center_y), overlay_icon)

    def render_project_icon(self, card_image, side, s: float = 1.0):
        """Render the encounter icon """
        region = Region(side.get('collection_portrait_clip_region'), s)
        if not region:
            return

        icon = side.card.project.icon
        if not icon:
            return

        icon = Image.open(side.card.project.icon, formats=['png', 'jpg'])
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

    def render_encounter_icon(self, card_image, side, s: float = 1.0):
        """Render the encounter icon """
        region = Region(side.get('encounter_icon_region'), s)
        if not region:
            return

        icon_path = side.get('encounter_icon')
        if not icon_path:
            if not side.card.encounter or not side.card.encounter.icon:
                return
            icon_path = side.card.encounter.icon


        overlay = side.get('encounter_overlay')
        if overlay:
            if not Path(overlay).is_file():
                overlay = overlay_dir / overlay
            overlay_region = Region(side.get('encounter_overlay_region'), s)
            overlay_image = self.get_resized_cached(Path(overlay), overlay_region.size)
            card_image.paste(overlay_image, overlay_region.pos, overlay_image)

        if not Path(icon_path).is_absolute():
            icon_path = Path(side.card.project.file_path).parent / Path(icon_path)
            icon_path = icon_path.absolute()

        try:
            icon = self.get_cached(icon_path)
            icon_scale = min(region.width/icon.width, region.height/icon.height)
            icon = self.get_resized_cached(icon_path, (int(icon.width*icon_scale), int(icon.height*icon_scale)))
            card_image.paste(icon, (region.x + (region.width-icon.width)//2, region.y + (region.height-icon.height)//2), icon if icon.has_transparency_data else None)
        except Exception as e:
            print('icon failure:', e, icon_path, side.card.name)

    def render_slots(self, card_image, side, s: float = 1.0):
        """Render the slot icons """
        slots = side.get('slots')
        slot = side.get('slot')
        if not slot and not slots:
            return
        if slot and not slots:
            slots = [slot]

        for index, slot in enumerate(slots):
            region = Region(side.get(f'slot_{index+1}_region', {}), s)
            if not region:
                continue

            path = self.overlays_path/f'slot_{slot}.png'
            slot_image = self.get_resized_cached(path, region.size)
            card_image.paste(slot_image, region.pos, slot_image)

    def render_enemy_stats(self, card_image, side, s: float = 1.0):
        """Render Damage and horror."""
        try:
            for token in ('damage', 'horror'):
                value = int(side.get(token, "0"))
                if not value:
                    continue
                icon_path = self.overlays_path/f"{token}.png"
                raw_icon = self.get_cached(icon_path)
                raw_icon = self.get_resized_cached(icon_path, (int(raw_icon.width*s), int(raw_icon.height*s)))
                for i in range(value):
                    region = Region(side[f'{token}{i+1}_region'], s)
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
            card_image.paste(template, (bleed, bleed), template if template.has_transparency_data else None)
        else:
            template = self.get_resized_cached(template_path, (card_image.width, card_image.height))
            card_image.paste(template, (0, 0), template if template.has_transparency_data else None)

    def render_illustration(self, card_image, side, s: float = 1.0):
        """Render the illustration/portrait"""
        # Get illustration path
        illustration_path = side.get('illustration', None)
        if not illustration_path:
            return
        illustration_path = Path(illustration_path)
        if not illustration_path.is_absolute():
            illustration_path = side.card.project.find_file(illustration_path)
        if not illustration_path:
            return

        illustration = self.get_illustration_cached(illustration_path)
        region = Region(side.get('illustration_region'), s)
        # Calculate scaling
        illustration_scale = float(side.get('illustration_scale', 0)) * s
        if not illustration_scale:
            illustration_scale = region.height / illustration.height
            if region.width / illustration.width > illustration_scale:
                illustration_scale = region.width / illustration.width

        # Resize illustration
        new_width = int(illustration.width * illustration_scale)
        new_height = int(illustration.height * illustration_scale)
        illustration = self.get_illustration_resized_cached(illustration_path, (new_width, new_height))

        rotation = side.get('illustration_rotation', 0)
        if rotation:
            illustration = illustration.rotate(float(rotation))

        # Apply panning
        if side.get('illustration_pan_x', None) is None:
            pan_x = region.x
        else:
            pan_x = int(side.get('illustration_pan_x', 0) * s)

        if side.get('illustration_pan_y', None) is None:
            pan_y = region.y
        else:
            pan_y = int(side.get('illustration_pan_y', 0) * s)
        # Position and paste
        if illustration.has_transparency_data:
            card_image.paste(
                illustration,
                (pan_x, pan_y),
                illustration
            )
        else:
            card_image.paste(
                illustration,
                (pan_x, pan_y)
            )

    def render_level(self, card_image, side, s: float = 1.0):
        """Render the card level"""
        # Get level
        region = Region(side.get('level_region'), s)
        if not region:
            return

        level = side.get('level', None)
        if level is None or level == '' or level == 'None':
            level = 'no_level'
        if level == "Custom":
            level = 'custom'

        level_overlay_format = side.get('level_overlay', None)
        if not level_overlay_format:
            return

        level_overlay_path = level_overlay_format.format(
            card_class=side.get_class(),
            level=level
        )
        path = side.card.project.find_file(level_overlay_path)
        if not path:
            path = overlay_dir / 'levels' / level_overlay_path

        level_icon = self.get_resized_cached(path, region.size)
        card_image.paste(level_icon, region.pos, level_icon)

    def render_class_symbols(self, card_image, side, s: float = 1.0):
        """Render class symbols for multiclass cards"""
        classes = side.get('classes', [])
        if len(classes) < 2:
            return

        # Render each class symbol
        for index, cls in enumerate(classes):
            symbol_path = self.overlays_path / f"class_symbol_{cls}.png"
            region = Region(side.get(f"class_symbol_{index+1}_region"), s)

            symbol = self.get_resized_cached(symbol_path, region.size)
            card_image.paste(symbol, (region.x, region.y), symbol)

    def render_chaos(self, card_image, side, s: float = 1.0):
        """ Renders the scenario reference cards.

            This could be handled in a lot of different ways,
            but this allows for easy json formatting of the card.
            It's essentially just a list of image and text.
        """
        entries = side.get('entries')
        if not entries:
            return

        region = Region(side.get('chaos_region'), s)
        if not region:
            return
        font = side.get("chaos_font", {})
        token_size = 200*s  # pixel size of token icons
        surfaces = []

        for entry in entries:
            if not entry['token'] and not entry['text']:
                continue
            tokens = entry['token']
            if not isinstance(tokens, list):
                tokens = [tokens]

            token_surface = Image.new('RGBA', (int(token_size), int(region.height)), (255, 255, 255, 0))
            for token_index, token in enumerate(tokens):
                token_image = self.get_resized_cached(overlay_dir / f"chaos_{token}.png", (int(token_size), int(token_size)))
                token_surface.paste(token_image, (0, int(token_size*1.1) * token_index), token_image)

            text_surface = Image.new('RGBA', region.size, (255, 255, 255, 0))
            self.rich_text.render_text(
                text_surface,
                entry['text'],
                Region.unscaled({'x': 0, 'y': 0, 'height': region.height, 'width': region.width-token_size*2}),
                font=font.get('font', 'regular'),
                font_size=int(font.get('size', 32)*s),
                fill=font.get('color', '#231f20'),
                outline=int(font.get('outline', 0)*s),
                outline_fill=font.get('outline_color'),
                alignment=font.get('alignment', 'left'),
            )
            surfaces.append((token_surface, text_surface))

        weights = [max(n.getbbox()[3], m.getbbox()[3]) for n,m in surfaces]
        weight_pixels = region.height/sum(weights)

        for index, weight in enumerate(weights):
            chaos, text = surfaces[index]
            height = weight_pixels * weight
            y = region.y + int(sum(weights[:index]) * weight_pixels)

            card_image.paste(chaos, (region.x, y + int(height/2 - chaos.getbbox()[3]/2)), chaos)
            card_image.paste(text, (region.x + int(token_size*1.3), y + int(height/2 - text.getbbox()[3]/2)), text)

    def render_customizable(self, card_image, side, s: float = 1.0):
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

        region = Region(side['text_region'], s)
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
