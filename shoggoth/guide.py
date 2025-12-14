from pathlib import Path
import pymupdf
from io import BytesIO
import subprocess
from subprocess import PIPE
from shoggoth import files


class Guide:
    def __init__(self, data, project, prince_cmd=None, prince_dir=None):
        self.path = data['path']
        self.id = data['id']
        self.data = data
        self.project = project
        self._html = None
        self._prince_cmd = prince_cmd
        self._prince_dir = prince_dir

    @property
    def prince_dir(self):
        if self._prince_dir is None:
            import shoggoth
            return shoggoth.app.config.get('Shoggoth', 'prince_dir') or None
        return self._prince_dir

    @property
    def prince_cmd(self):
        if self._prince_cmd is None:
            import shoggoth
            return shoggoth.app.config.get('Shoggoth', 'prince_cmd')
        return self._prince_cmd

    @property
    def target_path(self):
        return Path(self.path).parent / 'guide.pdf'

    def get_html(self):
        if not self._html:
            with open(self.path, 'r') as file:
                self._html = file.read()
        return self._html

    @property
    def front_page(self):
        return self.data.get('front_page', '')

    @front_page.setter
    def front_page(self, value):
        self.data['front_page'] = value

    @property
    def name(self):
        return self.data.get('name', 'Unnamed Guide')

    @name.setter
    def name(self, value):
        self.data['name'] = value

    def html_format(self, html) -> str:
        """ Does a simple string replacement for certain defined elements """
        html = html.replace("{{frontpage}}", self.front_page)
        html = html.replace("{{a4_empty}}", str(files.guide_dir/'guide_a4_empty.webp'))
        html = html.replace("{{a4_title}}", str(files.guide_dir/'guide_a4_title.webp'))
        html = html.replace("{{resolution_glyph_top}}", str(files.guide_dir/'resolution_glyph_top.png'))
        html = html.replace("{{resolution_glyph_bottom}}", str(files.guide_dir/'resolution_glyph_bottom.png'))
        return html

    def get_page(self, page, html: str = ''):
        print(self.front_page)
        if not html:
            p = subprocess.call([self.prince_cmd, self.path, '-o', str(self.target_path)], cwd=self.prince_dir)
            pdf = pymupdf.open(self.target_path)
        else:
            p = subprocess.run(
                [self.prince_cmd, '-', '-o', '-'],
                cwd=self.prince_dir,
                input=self.html_format(html).encode(),
                stdout=subprocess.PIPE,
            )
            data = p.stdout
            print('got data of len', len(data))
            pdf = pymupdf.open(stream=data)

        image = pdf[page].get_pixmap().pil_image()

        buffer = BytesIO()
        image.save(buffer, format='jpeg', quality=90)
        buffer.seek(0)
        return buffer

    def render_to_file(self):
        subprocess.run([self.prince_cmd, self.path, '-o', str(self.target_path)], cwd=self.prince_dir)


# todo:
# use pymupdf
# load file
# use file[n] to get page
# use page.get_pixmap(matrix=(scale_x, scale_y)) to get pixelmap
# use pixmap.pil_image() to get pil_image
# use pil_image as normal to get jpeg, then send to renderer.