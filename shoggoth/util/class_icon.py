from PIL import Image

# Rough starting colors, one per player class - mirrors the background
# column of ui/compact_widgets.py:CLASS_CHIP_COLORS for visual consistency
# with the rest of the editor. Adjust both together if these get re-tuned.
CLASS_ICON_COLORS = {
    'guardian': '#2a5f8f',
    'seeker': '#c9a227',
    'rogue': '#2e7d46',
    'survivor': '#a5322f',
    'mystic': '#5c3f8f',
    'neutral': '#6b6f76',
}


def tint_icon(icon, card_class):
    """
    Flat-recolors an alpha-silhouette icon (e.g. a rasterized set_icons/*.svg)
    to the given class's color, using the icon's own alpha channel as the
    shape mask - so the source image's own fill color doesn't matter.
    """
    value = CLASS_ICON_COLORS.get(card_class, CLASS_ICON_COLORS['neutral']).lstrip('#')
    color = tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))

    icon = icon.convert('RGBA')
    tinted = Image.new('RGBA', icon.size, color + (0,))
    tinted.putalpha(icon.getchannel('A'))
    return tinted
