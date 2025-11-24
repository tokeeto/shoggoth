from pathlib import Path
import pymupdf
from io import BytesIO
import subprocess
from subprocess import PIPE

PRINCE_DIR = '/home/toke/Downloads/prince-16.1-linux-generic-x86_64/lib/prince'
PRINCE_CMD = './bin/prince'


class Guide:
    def __init__(self, path, name, id, project):
        self.path = path
        self.name = name
        self.id = id
        self.project = project
        self._html = None

    @property
    def target_path(self):
        return Path(self.path).parent / 'guide.pdf'

    def get_html(self):
        if not self._html:
            with open(self.path, 'r') as file:
                self._html = file.read()
        return self._html

    def get_page(self, page):
        print('get page', [PRINCE_CMD, self.path, '-o', str(self.target_path)])
        p = subprocess.call([PRINCE_CMD, self.path, '-o', str(self.target_path)], cwd=PRINCE_DIR)
        pdf = pymupdf.open(self.target_path)
        image = pdf[page].get_pixmap().pil_image()

        buffer = BytesIO()
        image.save(buffer, format='jpeg', quality=90)
        buffer.seek(0)
        return buffer

    def render_to_file(self):
        with open(self.target_path, "w+b") as result_file:
            # convert HTML to PDF
            subprocess.call([PRINCE_CMD, str(self.path), str(result_file)], cwd=PRINCE_DIR)


# todo:
# use pymupdf
# load file
# use file[n] to get page
# use page.get_pixmap(matrix=(scale_x, scale_y)) to get pixelmap
# use pixmap.pil_image() to get pil_image
# use pil_image as normal to get jpeg, then send to renderer.