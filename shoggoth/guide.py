from pathlib import Path
import re
import uuid
import pymupdf
from io import BytesIO
import subprocess
from bs4 import BeautifulSoup, Tag
from shoggoth import files


SECTION_TYPES = ['intro', 'prelude', 'interlude', 'scenario', 'blank']


# CSS class for the auto-generated wrapper div per section type.
# None means no wrapper (used for blank sections like cover pages).
_SECTION_CSS = {
    'intro': 'chapter intro',
    'prelude': 'chapter prelude',
    'interlude': 'chapter interlude',
    'scenario': 'chapter scenario',
    'blank': 'chapter',
}


class SectionFieldDef:
    """Describes one structured field in a guide section and locates it in HTML."""

    def __init__(
        self,
        key: str,
        label: str,
        kind: str,
        selector_tag: str,
        selector_class: str,
        default_html: str,
        extra_selectors: list | None = None,
    ):
        self.key = key
        self.label = label
        # kind: 'line' | 'story' | 'text' | 'html' | 'list' | 'titled_list' | 'titled_html'
        self.kind = kind
        self.selector_tag = selector_tag
        self.selector_class = selector_class   # '' means tag-only match
        self.default_html = default_html
        # Fallback (tag, class) pairs tried if the primary selector finds nothing.
        # Allows matching legacy HTML that uses different tags/classes.
        self.extra_selectors: list[tuple[str, str]] = extra_selectors or []

    def locate(self, wrapper: Tag) -> list:
        """Return matching elements that are direct children of *wrapper*.

        Tries the primary (selector_tag, selector_class) first, then each entry
        in extra_selectors in order, stopping at the first non-empty result.
        """
        def _find(tag, cls):
            if cls:
                return wrapper.find_all(tag, class_=cls, recursive=False)
            return wrapper.find_all(tag, recursive=False)

        results = _find(self.selector_tag, self.selector_class)
        if results:
            return results
        for tag, cls in self.extra_selectors:
            results = _find(tag, cls)
            if results:
                return results
        return []


_STORY_EXTRAS = [("section", "story"), ("div", "story")]  # legacy <section class="story">
_SETUP_EXTRAS = [("section", "setup"), ("div", "setup")]
_RESOLUTION_EXTRAS = [
    ("div", "resolution_box"),
    ("section", "resolution"),
    ("section", "resolution_box"),
]

# Fields declared per section type, in display and generation order.
SECTION_FIELDS: dict = {
    "intro": [
        SectionFieldDef("header", "Header", "line", "h1", "", "<h1>Intro</h1>"),
        SectionFieldDef(
            "story",
            "Story Teaser",
            "story",
            "div",
            "story",
            '<div class="story">\n<p><em></em></p>\n</div>',
            extra_selectors=_STORY_EXTRAS,
        ),
        SectionFieldDef(
            "toc",
            "Table of Contents",
            "html",
            "div",
            "toc",
            '<div class="toc">\n<h3>Table of Contents</h3>\n<ul>\n<li></li>\n</ul>\n</div>',
        ),
        SectionFieldDef(
            "introduction",
            "Introduction",
            "html",
            "div",
            "introduction",
            '<div class="introduction">\n<p></p>\n</div>',
        ),
        SectionFieldDef(
            "new_rules",
            "New Rules",
            "html",
            "div",
            "box",
            '<div class="box">\n<p></p>\n</div>',
            extra_selectors=[("div", "codex")],
        ),
    ],
    "prelude": [
        SectionFieldDef("header", "Header", "line", "h1", "", "<h1>Prelude</h1>"),
        SectionFieldDef(
            "story",
            "Story",
            "story",
            "div",
            "story",
            '<div class="story">\n<p><em></em></p>\n</div>',
            extra_selectors=_STORY_EXTRAS,
        ),
        SectionFieldDef(
            "text",
            "Text",
            "html",
            "div",
            "section-text",
            '<div class="section-text">\n<p></p>\n</div>',
        ),
    ],
    "interlude": [
        SectionFieldDef("header", "Header", "line", "h1", "", "<h1>Interlude</h1>"),
        SectionFieldDef(
            "story",
            "Story",
            "story",
            "div",
            "story",
            '<div class="story">\n<p><em></em></p>\n</div>',
            extra_selectors=_STORY_EXTRAS,
        ),
        SectionFieldDef(
            "text",
            "Text",
            "html",
            "div",
            "section-text",
            '<div class="section-text">\n<p></p>\n</div>',
        ),
    ],
    "scenario": [
        SectionFieldDef("header", "Header", "line", "h1", "", "<h1>Scenario</h1>"),
        SectionFieldDef(
            "story",
            "Story Teaser",
            "story",
            "div",
            "story",
            '<div class="story">\n<p><em></em></p>\n</div>',
            extra_selectors=_STORY_EXTRAS,
        ),
        SectionFieldDef(
            "setup",
            "Setup",
            "titled_list",
            "div",
            "setup",
            '<div class="setup">\n<h3>Setup</h3>\n<ul>\n</ul>\n</div>',
            extra_selectors=_SETUP_EXTRAS,
        ),
        SectionFieldDef(
            "location_overview",
            "Location Overview",
            "text",
            "div",
            "location-overview",
            '<div class="location-overview">\n<p></p>\n</div>',
        ),
        SectionFieldDef(
            "resolution",
            "Resolution",
            "titled_html",
            "div",
            "resolution",
            '<div class="resolution">\n<h3>Resolution</h3>\n<p></p>\n</div>',
            extra_selectors=_RESOLUTION_EXTRAS,
        ),
    ],
    "blank": [],
}


class GuideSection:
    def __init__(self, section_type: str, name: str, html_content: str = '', section_id=None):
        self.type = section_type
        self.name = name
        self.html_content = html_content
        self.id = section_id or uuid.uuid4().hex[:8]

    @classmethod
    def new(cls, section_type: str, name: str) -> 'GuideSection':
        """Create a new section with default HTML for its predefined fields."""
        field_defs = SECTION_FIELDS.get(section_type, [])
        html_content = ''.join(fd.default_html + '\n' for fd in field_defs)
        return cls(section_type, name, html_content)

    def to_html(self) -> str:
        css_class = _SECTION_CSS.get(self.type, 'chapter')
        attrs = (
            f'data-shoggoth-id="{self.id}"'
        )
        open_tag = f'<div class="{css_class}" {attrs}>'
        lines = [open_tag]
        if self.html_content:
            lines.append(self.html_content)
        lines.append('</div>')
        return '\n'.join(lines)



def _parse_sections_from_html(html: str):
    """Parse GuideSection list from an HTML fragment.

    Looks for elements carrying ``data-shoggoth-type`` / ``data-shoggoth-name``
    / ``data-shoggoth-id`` attributes (new format).  Falls back to the legacy
    comment-based format so that old files continue to work; they will be
    silently upgraded to the new format on the next save.
    """
    soup = BeautifulSoup(html, 'html.parser')
    section_elements = soup.find('body').find_all('div', recursive=False)

    sections = []
    for i, elem in enumerate(section_elements):
        section_type = elem.get('class', ['unknown'])[-1]
        section_name = elem.get('data-shoggoth-name')
        if not section_name and elem.find('h1'):
            section_name = elem.find('h1').get_text()
        # Prefer the explicit shoggoth id, then a regular id attr, then a
        # stable positional fallback so the id is consistent across re-parses
        # of the same unmodified HTML (avoids UUID churn on legacy files).
        section_id = (
            elem.get('data-shoggoth-id')
            or elem.get('id')
            or f'sec_{i}'
        )
        inner = elem.decode_contents().strip()
        sections.append(GuideSection(section_type, section_name, inner, section_id))
    return sections


class Guide:
    def __init__(self, data, project, prince_cmd=None, prince_dir=None):
        self.project = project
        self.path = project.find_file(data['path'])
        self.id = data['id']
        self.data = data
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
        html = html.replace("{{a4_empty}}", str(files.guide_dir / 'guide_a4_empty.webp'))
        html = html.replace("{{a4_title}}", str(files.guide_dir / 'guide_a4_title.webp'))
        html = html.replace("{{resolution_glyph_top}}", str(files.guide_dir / 'resolution_glyph_top.png'))
        html = html.replace("{{resolution_glyph_bottom}}", str(files.guide_dir / 'resolution_glyph_bottom.png'))
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
        soup = BeautifulSoup(html, 'html.parser')
        sections = _parse_sections_from_html(html)
        head = str(soup.find('head'))
        preamble = f'<!DOCTYPE html>\n<html>\n{head}\n<body>'
        postamble = '</body>\n</html>'
        return preamble, sections, postamble

    def save_sections(self, preamble: str, sections: list, postamble: str):
        """Serialize sections back to HTML and save."""
        sections_html = '\n'.join(s.to_html() for s in sections)
        html = f'{preamble}\n{sections_html}\n{postamble}'
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
