import base64
import platform
import re
import shoggoth
from shoggoth.card import natural_sort_key
from shoggoth.renderer import CardRenderer, CARD_SIZES
from shoggoth.settings import EXPORT_SIZES
import subprocess
from threading import Thread
from time import time
from pathlib import Path
from shoggoth.files import prince_dir as _local_prince_dir

# Printed card size for the one-card-per-page exports (mbprint, azao)
_CARD_W_MM = 66.5
_CARD_H_MM = 91
_CSS_PX_PER_MM = 96 / 25.4


def _card_mm(card):
    """Printed size (mm, incl. bleed) for a card. Standard cards are the
    _CARD_W_MM x _CARD_H_MM baseline; named sizes (mini) scale with their
    pixel dimensions since all sizes share one px/mm density."""
    size_px = CARD_SIZES.get(card.front.get('card_size', 'standard'), CARD_SIZES['standard'])
    w = round(_CARD_W_MM * (size_px['width'] + 144) / (1500 + 144), 2)
    h = round(_CARD_H_MM * (size_px['height'] + 144) / (2100 + 144), 2)
    return w, h


def _size_class(w_mm, h_mm):
    if (w_mm, h_mm) == (_CARD_W_MM, _CARD_H_MM):
        return ''
    return f'size-{w_mm}x{h_mm}'.replace('.', '_')


def _size_css(cards):
    """Extra page/card rules for non-standard card sizes (mini cards)."""
    css = ''
    for w, h in sorted({_card_mm(c) for c in cards} - {(_CARD_W_MM, _CARD_H_MM)}):
        name = _size_class(w, h)
        css += (
            f'.card.{name} {{ page: {name}; width: {w}mm; height: {h}mm; }}\n'
            f'.card.{name} > img {{ width: {w}mm; height: {h}mm; }}\n'
            f'@page {name} {{ margin: 0; size: {w}mm {h}mm; }}\n'
        )
    return f'<style>\n{css}</style>\n' if css else ''


def _font_css(folder):
    """Inline the @font-face rules the card exporter left in the image folder
    (only present when cards were exported with a vector text layer)."""
    css_path = Path(folder) / 'fonts.css'
    if css_path.exists():
        return f'<style>\n{css_path.read_text(encoding="utf-8")}\n</style>'
    return ''


def _card_page(path, w_mm=_CARD_W_MM, h_mm=_CARD_H_MM):
    """One card page: the raster image plus, if the renderer wrote an HTML
    text sidecar next to it, the vector text overlay scaled from card pixels
    down to the printed size."""
    cls = ('card ' + _size_class(w_mm, h_mm)).strip()
    sidecar = Path(path).with_suffix('.html')
    if sidecar.exists():
        overlay = sidecar.read_text(encoding='utf-8')
        m = re.search(r'data-width="(\d+)"', overlay)
        if m:
            k = w_mm * _CSS_PX_PER_MM / int(m[1])
            return (f'<div class="{cls}"><img src="{path}">'
                    f'<div class="text-scale" style="transform:scale({k:.6f})">{overlay}</div></div>\n')
    return f'<div class="{cls}"><img src="{path}"></div>\n'


def _local_prince_bin():
    if platform.system() == 'Windows':
        return _local_prince_dir / 'bin' / 'prince.exe'
    return _local_prince_dir / 'lib' / 'prince' / 'bin' / 'prince'


def _resolve_prince():
    """Returns (cmd, cwd) for running prince, preferring local install."""
    local_bin = _local_prince_bin()
    if local_bin.exists():
        return str(local_bin), None
    # Fall back to settings-configured prince
    cmd = shoggoth.app.config.get('Shoggoth', 'prince_cmd') or None
    cwd = shoggoth.app.config.get('Shoggoth', 'prince_dir') or None
    return cmd, cwd


def check_prince_installed():
    return _local_prince_bin().exists()


# Shared page setup for the one-card-per-page exports. Each card is a
# positioned .card box so a vector text overlay can sit on top of the image.
_CARD_PAGE_HEAD = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                .card {{
                    position: relative;
                    width: {_CARD_W_MM}mm;
                    height: {_CARD_H_MM}mm;
                    break-before: page;
                    overflow: hidden;
                }}
                .card > img {{
                    -prince-image-resolution: 900dpi;
                    width: {_CARD_W_MM}mm;
                    height: {_CARD_H_MM}mm;
                    display: block;
                }}
                .card > .text-scale {{
                    position: absolute;
                    left: 0;
                    top: 0;
                    transform-origin: 0 0;
                }}
                @page {{
                    margin: 0;
                    size: {_CARD_W_MM}mm {_CARD_H_MM}mm;
                }}
            </style>
    """


def _mbprint_html(cards, folder, size):
    """ Simple document template for mbprint output """
    yield _CARD_PAGE_HEAD
    yield _size_css(cards)
    yield _font_css(folder)
    yield "</head>\n<body>\n"

    for card in cards:
        w_mm, h_mm = _card_mm(card)
        for path in CardRenderer.expected_export_paths(card, folder, size, format='png', include_backs=False):
            yield _card_page(path, w_mm, h_mm)
    yield "</body>"


def _azao_html(cards, folder, size, side='front'):
    """ Simple document template for azao output """
    yield _CARD_PAGE_HEAD
    yield _size_css(cards)
    yield _font_css(folder)
    yield "</head>\n<body>\n"

    offset = 0 if side == 'front' else 1
    for card in cards:
        w_mm, h_mm = _card_mm(card)
        for path in CardRenderer.expected_export_paths(card, folder, size, format='png', include_backs=False)[offset::2]:
            yield _card_page(path, w_mm, h_mm)
    yield "</body>"

def _pdf_html(cards, folder, size, format='png', include_backs=False):
    """ Simple document template for pdf prints """
    yield """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                img {
                    -prince-image-resolution: 900dpi;
                    break-before: page;
                    width: 66.5mm;
                    height: 91mm;
                    display: inline-block;
                    margin: 2mm;
                }
                @page {
                    margin: 10mm;
                    size: a4;
                }
            </style>
        </head>
        <body>
    """

    for card in cards:
        w_mm, h_mm = _card_mm(card)
        style = '' if (w_mm, h_mm) == (_CARD_W_MM, _CARD_H_MM) else f' style="width:{w_mm}mm;height:{h_mm}mm"'
        for path in CardRenderer.expected_export_paths(card, folder, size, format=format, include_backs=include_backs):
            yield f'<img src="{path}"{style}>\n'
    yield "</body>"


def export(cards, target_file, image_folder, size=None, format='png', include_backs=False):
    prince_cmd, prince_cwd = _resolve_prince()
    if prince_cmd is None:
        raise Exception("can't export without prince")

    if size is None:
        size = EXPORT_SIZES[0][1]

    cards.sort(key=lambda x: natural_sort_key(x.project_number))

    target_folder = Path(target_file).parent
    temp_file = target_folder / '_temp.html'

    start_time = time()
    with open(temp_file, 'w', encoding='utf-8') as html_file:
        for txt in _pdf_html(cards, image_folder, size, format=format, include_backs=include_backs):
            html_file.write(txt)

    print(f"PDF html time: {time()-start_time}")
    subprocess.run(
        [prince_cmd, temp_file, '-o', Path(target_file)],
        cwd=prince_cwd,
    )
    print(f"PDF time: {time()-start_time}")


def create_mbprint_pdf(cards, target_file, image_folder, size=None):
    prince_cmd, prince_cwd = _resolve_prince()
    if prince_cmd is None:
        raise Exception("can't export without prince")

    if size is None:
        size = EXPORT_SIZES[0][1]

    cards.sort(key=lambda x: natural_sort_key(x.project_number))

    target_folder = Path(target_file).parent
    temp_file = target_folder / '_temp.html'

    start_time = time()
    with open(temp_file, 'w', encoding='utf-8') as html_file:
        for txt in _mbprint_html(cards, image_folder, size):
            html_file.write(txt)
    print(f"MBPrint html time: {time()-start_time}")

    subprocess.run(
        [prince_cmd, temp_file, '-o', Path(target_file)],
        cwd=prince_cwd,
    )

    print(f"MBPrint pdf time: {time()-start_time}")


def azao_pdf(cards, target_file_front, target_file_back, image_folder, size=None):
    prince_cmd, prince_cwd = _resolve_prince()
    if prince_cmd is None:
        raise Exception("can't export without prince")

    if size is None:
        size = EXPORT_SIZES[0][1]

    cards.sort(key=lambda x: natural_sort_key(x.project_number))

    target_folder = Path(target_file_front).parent
    temp_file = target_folder / '_temp.html'

    start_time = time()
    with open(temp_file, 'w', encoding='utf-8') as html_file:
        for txt in _azao_html(cards, image_folder, size, 'front'):
            html_file.write(txt)
    print(f"Azao front html time: {time()-start_time}")

    subprocess.run(
        [prince_cmd, temp_file, '-o', Path(target_file_front)],
        cwd=prince_cwd,
    )
    print(f"Azao pdf front time: {time()-start_time}")

    start_time = time()
    with open(temp_file, 'w', encoding='utf-8') as html_file:
        for txt in _azao_html(cards, image_folder, size, 'back'):
            html_file.write(txt)
    print(f"Azao front html time: {time()-start_time}")

    subprocess.run(
        [prince_cmd, temp_file, '-o', Path(target_file_back)],
        cwd=prince_cwd,
    )
    print(f"Azao pdf front time: {time()-start_time}")


