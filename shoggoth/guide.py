from pathlib import Path
import pymupdf
from io import BytesIO
import subprocess
from subprocess import PIPE


class Guide:
    def __init__(self, path, name, id, project, prince_cmd=None, prince_dir=None):
        self.path = path
        self.name = name
        self.id = id
        self.project = project
        self._html = None

        if not prince_cmd:
            from kivy.config import Config
            prince_cmd = Config.get('Shoggoth', 'prince_cmd')
            prince_dir = Config.get('Shoggoth', 'prince_dir')
        self.prince_cmd = prince_cmd
        self.prince_dir = prince_dir

    @property
    def target_path(self):
        return Path(self.path).parent / 'guide.pdf'

    def get_html(self):
        if not self._html:
            with open(self.path, 'r') as file:
                self._html = file.read()
        return self._html

    def get_page(self, page):
        print('get page', [self.prince_cmd, self.path, '-o', str(self.target_path)])
        p = subprocess.call([self.prince_cmd, self.path, '-o', str(self.target_path)], cwd=self.prince_dir)
        pdf = pymupdf.open(self.target_path)
        image = pdf[page].get_pixmap().pil_image()

        buffer = BytesIO()
        image.save(buffer, format='jpeg', quality=90)
        buffer.seek(0)
        return buffer

    def render_to_file(self):
        with open(self.target_path, "w+b") as result_file:
            # convert HTML to PDF
            subprocess.call([self.prince_cmd, str(self.path), str(result_file)], cwd=self.prince_dir)


# todo:
# use pymupdf
# load file
# use file[n] to get page
# use page.get_pixmap(matrix=(scale_x, scale_y)) to get pixelmap
# use pixmap.pil_image() to get pil_image
# use pil_image as normal to get jpeg, then send to renderer.