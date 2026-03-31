import base64
import platform
import shoggoth
from shoggoth.renderer import CardRenderer
from shoggoth.settings import EXPORT_SIZES
import subprocess
from threading import Thread
from time import time
from pathlib import Path
from shoggoth.files import prince_dir as _local_prince_dir

renderer = CardRenderer()


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


def _mbprint_html(cards, folder):
    """ Simple document template for mbprint output """
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
                    display: block;
                }
                img.wide {
                    page: wide;
                    width: 91mm;
                    height: 66.5mm;

                }
                @page {
                    margin: 0;
                    size: 66.5mm 91mm;
                }
                @page wide {
                    size: 91mm 66.5mm;
                }
            </style>
        </head>
        <body>
    """

    for card in cards:
        css = 'wide' if card.front.get('orientation') == 'horizontal' else ''
        for path in renderer.expected_export_paths(card, folder, EXPORT_SIZES[0][1], format='png', include_backs=False):
            yield f'<img class="{css}" src="{path}">\n'
    yield "</body>"


def _pdf_html(cards, folder):
    """ Simpel document template for pdf prints """
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
                img.wide {
                    height: 66.5mm;
                    width: 91mm;
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
        css = 'wide' if card.front.get('orientation') == 'horizontal' else ''
        for path in renderer.expected_export_paths(card, folder, EXPORT_SIZES[0][1], format='png'):
            yield f'<img class="{css}" src="{path}">\n'
    yield "</body>"


def export(cards, target_file, image_folder):
    prince_cmd, prince_cwd = _resolve_prince()
    if prince_cmd is None:
        raise Exception("can't export without prince")

    target_folder = Path(target_file).parent
    temp_file = target_folder / '_temp.html'

    start_time = time()
    with open(temp_file, 'w') as html_file:
        for txt in _pdf_html(cards, image_folder):
            html_file.write(txt)

    print(f"PDF html time: {time()-start_time}")
    subprocess.run(
        [prince_cmd, temp_file, '-o', Path(target_file)],
        cwd=prince_cwd,
    )
    print(f"PDF time: {time()-start_time}")


def create_mbprint_pdf(cards, target_file, image_folder):
    prince_cmd, prince_cwd = _resolve_prince()
    if prince_cmd is None:
        raise Exception("can't export without prince")

    target_folder = Path(target_file).parent
    temp_file = target_folder / '_temp.html'

    start_time = time()
    with open(temp_file, 'w') as html_file:
        for txt in _mbprint_html(cards, image_folder):
            html_file.write(txt)
    print(f"MBPrint html time: {time()-start_time}")

    subprocess.run(
        [prince_cmd, temp_file, '-o', Path(target_file)],
        cwd=prince_cwd,
    )

    print(f"MBPrint pdf time: {time()-start_time}")


