"""
ExportProfile: a named, saved bundle of export settings for a project's
Images/PDF/TTS/arkham.build/Guides exports, persisted in the project's own
`export_profiles` list (round-trips via project_writer.py like any other
top-level project key).

A profile has exactly one scope (which cards it applies to), shared by every
card-scoped section (Images/PDF/TTS); arkham.build and Guides always operate
on the whole project regardless of scope.
"""

DEFAULT_SCOPE = {
    'type': 'all',  # 'all' | 'player' | 'campaign' | 'encounter_sets' | 'cards'
    'encounter_set_ids': [],  # used when type == 'encounter_sets'
    'card_ids': [],  # used when type == 'cards'
}

DEFAULT_SECTIONS = {
    'images': {
        'enabled': True,
        'folder': None,
        'size_label': None,
        'format': 'png',
        'quality': 95,
        'filename_format': 'id',
        'rotate': False,
        'bleed': True,
        'separate_versions': False,
        'include_backs': False,
    },
    'pdf': {
        'enabled': False,
        'flavor': 'pdf',
        'folder': None,
        'size_label': None,  # resolved to EXPORT_SIZES[0][0] (FFG 100%) lazily, see default_sections()
        'format': 'png',
        'quality': 100,
        'include_backs': False,
        'vector_text': True,
        'export_images': True,
        'output_path': None,
        'back_output_path': None,
    },
    'tts': {
        'enabled': False,
        'folder': None,
        'export_images': True,
        'sync': False,
    },
    'arkham_build': {
        'enabled': False,
        'url_pattern': None,
        'export_thumbnails': False,  # placeholder checkbox, not yet implemented
    },
    'guides': {
        'enabled': False,
        'export_pdf': True,
        'export_html': True,
    },
}


def _default_pdf_size_label():
    from shoggoth.settings import EXPORT_SIZES
    return EXPORT_SIZES[0][0]  # FFG 100% (1453x2079, with bleed)


def default_sections():
    """A fresh, independent copy of DEFAULT_SECTIONS."""
    sections = {key: dict(value) for key, value in DEFAULT_SECTIONS.items()}
    sections['pdf']['size_label'] = _default_pdf_size_label()
    return sections


def default_scope():
    """A fresh, independent copy of DEFAULT_SCOPE."""
    return dict(DEFAULT_SCOPE, encounter_set_ids=[], card_ids=[])


class ExportProfile:
    """Thin wrapper around one entry of a project's `export_profiles` list."""

    def __init__(self, data, project):
        self.project = project
        self.data = data
        if 'sections' not in self.data:
            self.data['sections'] = default_sections()
        else:
            # backfill any section keys missing from an older/partial profile
            for key, defaults in DEFAULT_SECTIONS.items():
                self.data['sections'].setdefault(key, dict(defaults))
        self.data.setdefault('scope', default_scope())

    @property
    def id(self):
        return self.data['id']

    @property
    def name(self):
        return self.data.get('name', 'Profile')

    @name.setter
    def name(self, value):
        self.data['name'] = value

    @property
    def scope(self):
        return self.data['scope']

    def section(self, key):
        """The mutable settings dict for one section ('images', 'pdf', ...)."""
        return self.data['sections'][key]
