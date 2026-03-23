from pathlib import Path
import re
import uuid
import pymupdf
from io import BytesIO
import subprocess
from shoggoth import files


# ── Guide section / block data model ──────────────────────────────────────────

SECTION_TYPES = ['intro', 'prelude', 'interlude', 'scenario', 'blank']

BLOCK_TYPES = [
    'header', 'story', 'text', 'table_of_contents', 'illustration',
    'setup', 'location_overview', 'resolution', 'box',
]

BLOCK_TEMPLATES = {
    'header': '<h2>Header</h2>',
    'story': '<div class="story">\n<p><em>Story text here...</em></p>\n</div>',
    'text': '<p>Text content here...</p>',
    'table_of_contents': (
        '<div class="toc">\n<h3>Table of Contents</h3>\n'
        '<ul>\n<li>...</li>\n</ul>\n</div>'
    ),
    'illustration': '<div class="illustration">\n<img src="" alt="">\n</div>',
    'setup': '<div class="setup">\n<h3>Setup</h3>\n<p>Setup instructions here...</p>\n</div>',
    'location_overview': '<div class="location-overview">\n<p>Location overview here...</p>\n</div>',
    'resolution': '<div class="resolution">\n<h3>Resolution</h3>\n<p>Resolution text here...</p>\n</div>',
    'box': '<div class="box">\n<p>Box content here...</p>\n</div>',
}

SECTIONS_START = '<!-- [SHOGGOTH-SECTIONS-START] -->'
SECTIONS_END = '<!-- [SHOGGOTH-SECTIONS-END] -->'

# CSS class for the auto-generated wrapper div per section type.
# None means no wrapper (used for blank sections like cover pages).
_SECTION_CSS = {
    'intro': 'chapter intro',
    'prelude': 'chapter',
    'interlude': 'chapter',
    'scenario': 'chapter',
    'blank': None,
}

_SECTION_OPEN = re.compile(
    r'<!-- \[SHOGGOTH-SECTION type="([^"]+)" name="([^"]*)" id="([^"]*)"\] -->'
)
_SECTION_CLOSE = re.compile(r'<!-- \[/SHOGGOTH-SECTION\] -->')
_BLOCK_OPEN = re.compile(r'<!-- \[SHOGGOTH-BLOCK type="([^"]+)"\] -->')
_BLOCK_CLOSE = re.compile(r'<!-- \[/SHOGGOTH-BLOCK\] -->')


class GuideBlock:
    def __init__(self, block_type: str, content: str):
        self.type = block_type
        self.content = content

    @classmethod
    def new(cls, block_type: str) -> 'GuideBlock':
        return cls(block_type, BLOCK_TEMPLATES.get(block_type, '<p>Content here...</p>'))

    def to_html(self) -> str:
        return (
            f'<!-- [SHOGGOTH-BLOCK type="{self.type}"] -->\n'
            f'{self.content}\n'
            f'<!-- [/SHOGGOTH-BLOCK] -->'
        )


class GuideSection:
    def __init__(self, section_type: str, name: str, html_content: str = '', section_id=None):
        self.type = section_type
        self.name = name
        self.html_content = html_content
        self.id = section_id or uuid.uuid4().hex[:8]

    def to_html(self) -> str:
        css_class = _SECTION_CSS.get(self.type)
        lines = [
            f'<!-- [SHOGGOTH-SECTION type="{self.type}" name="{self.name}" id="{self.id}"] -->'
        ]
        if css_class:
            lines.append(f'<div class="{css_class}">')
        if self.html_content:
            lines.append(self.html_content)
        if css_class:
            lines.append('</div>')
        lines.append('<!-- [/SHOGGOTH-SECTION] -->')
        return '\n'.join(lines)


def _parse_sections_from_html(html: str):
    """Parse GuideSection list from an HTML fragment. Returns None if malformed."""
    sections = []
    pos = 0
    while pos < len(html):
        m = _SECTION_OPEN.search(html, pos)
        if not m:
            break
        section_type, section_name, section_id = m.group(1), m.group(2), m.group(3)
        end_m = _SECTION_CLOSE.search(html, m.end())
        if not end_m:
            return None
        raw = html[m.end():end_m.start()].strip()
        # Strip the auto-generated chapter div wrapper if present
        css_class = _SECTION_CSS.get(section_type)
        if css_class:
            open_div = f'<div class="{css_class}">'
            close_div = '</div>'
            if raw.startswith(open_div) and raw.endswith(close_div):
                raw = raw[len(open_div):-len(close_div)].strip()
        # Strip legacy SHOGGOTH-BLOCK markers (backward compat with old format)
        raw = _BLOCK_OPEN.sub('', raw)
        raw = _BLOCK_CLOSE.sub('', raw)
        raw = raw.strip()
        sections.append(GuideSection(section_type, section_name, raw, section_id))
        pos = end_m.end()
    return sections


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
        html = html.replace("{{frontpage}}", str(self.front_page))
        html = html.replace("{{a4_empty}}", str(files.guide_dir/'guide_a4_empty.webp'))
        html = html.replace("{{a4_title}}", str(files.guide_dir/'guide_a4_title.webp'))
        html = html.replace("{{resolution_glyph_top}}", str(files.guide_dir/'resolution_glyph_top.png'))
        html = html.replace("{{resolution_glyph_bottom}}", str(files.guide_dir/'resolution_glyph_bottom.png'))
        html = html.replace("{{project.icon}}", str((self.project.folder / self.project.icon).resolve()))
        return html

    def get_page(self, page, html: str = ''):
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
            pdf = pymupdf.open(stream=data)

        image = pdf[page].get_pixmap().pil_image()

        buffer = BytesIO()
        image.save(buffer, format='jpeg', quality=90)
        buffer.seek(0)
        return buffer

    def parse_sections(self):
        """Parse HTML into (preamble, sections, postamble). Returns None if not structured."""
        html = self.get_html()
        start = html.find(SECTIONS_START)
        end = html.find(SECTIONS_END)
        if start == -1 or end == -1:
            return None
        preamble = html[:start]
        postamble = html[end + len(SECTIONS_END):]
        sections_html = html[start + len(SECTIONS_START):end]
        sections = _parse_sections_from_html(sections_html)
        if sections is None:
            return None
        return preamble, sections, postamble

    def save_sections(self, preamble: str, sections: list, postamble: str):
        """Serialize sections back to HTML and save."""
        sections_html = '\n'.join(s.to_html() for s in sections)
        html = f'{preamble}{SECTIONS_START}\n{sections_html}\n{SECTIONS_END}{postamble}'
        self.save(html)

    def initialize_sections(self):
        """Add sections markers to an unstructured guide HTML file."""
        html = self.get_html()
        if SECTIONS_START in html:
            return
        marker_block = f'{SECTIONS_START}\n{SECTIONS_END}\n'
        if '</body>' in html:
            html = html.replace('</body>', marker_block + '</body>', 1)
        else:
            html = html + '\n' + marker_block
        self.save(html)

    def save(self, html):
        self._html = html
        with open(self.path, 'w') as file:
            file.write(html)

    def render_to_file(self, html=None):
        if not html:
            html = self.get_html()
        html = self.html_format(html)

        p = subprocess.run(
            [self.prince_cmd, '-', '-o', str(self.target_path)],
            cwd=self.prince_dir,
            input=html.encode(),
        )
        return
