import base64
import shoggoth
from shoggoth.renderer import CardRenderer
import subprocess
from threading import Thread
from time import time
from pathlib import Path

renderer = CardRenderer()


class CustomThread(Thread):
    def __init__(self, group=None, target=None, name=None, args=(), kwargs={}, verbose=None):
        # Initializing the Thread class
        super().__init__(group, target, name, args, kwargs)
        self._return = None

    # Overriding the Thread.run function
    def run(self):
        if self._target is not None:
            self._return = self._target(*self._args, **self._kwargs)

    def join(self):
        super().join()
        return self._return


def export(cards, page_size, bleed, seperation, format):
    pass


def _mbprint_html(cards, folder):
    yield """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                img {
                    -prince-image-resolution: 600dpi; 
                    break-before: page;
                    width: 64.5mm;
                    height: 94mm;
                    display: block;
                }
                img.wide {
                    page: wide;
                    width: 94mm;
                    height: 64.5mm;

                }
                @page {
                    margin: 0;
                    size: 64.5mm 94mm;
                }
                @page wide {
                    size: 94mm 64.5mm;
                }
            </style>
        </head>
        <body>
    """

    threads = []
    for card in cards:
        t = CustomThread(target=renderer.export_card_images, args=(card, folder), kwargs={'format': 'webp'})
        threads.append((t, card.front.get('orientation'), card.back.get('orientation')))
        t.start()

    # for t in threads:
    #     front, back = t.join()
    #     b64front = base64.b64encode(front.read())
    #     yield f'<img src="data:image/jpeg;base64,{b64front.decode()}"><br>\n'

    #     b64back = base64.b64encode(back.read())
    #     yield f'<img src="data:image/jpeg;base64,{b64back.decode()}"><br>\n'
    for t, front_orientation, back_orientation in threads:
        front, back = t.join()
        c1 = 'wide' if front_orientation == 'horizontal' else ''
        c2 = 'wide' if back_orientation == 'horizontal' else ''
        yield f'<img class="{c1}" src="{front}">\n<img class="{c2}" src="{back}">\n'
    yield "</body>"


def create_mbprint_pdf(cards, path):
    prince_dir = shoggoth.app.config.get('Shoggoth', 'prince_dir') or None
    prince_cmd = shoggoth.app.config.get('Shoggoth', 'prince_cmd') or None

    out_folder = Path(path)
    start_time = time()
    with open(out_folder/'mbprint.html', 'w') as html_file:
        for txt in _mbprint_html(cards, out_folder):
            html_file.write(txt)
    print(f"MBPrint html time: {time()-start_time}")

    subprocess.run(
        [prince_cmd, out_folder/'mbprint.html', '-o', out_folder/'mbprint.pdf'],
        cwd=prince_dir,
    )
    print(f"MBPrint pdf time: {time()-start_time}")


