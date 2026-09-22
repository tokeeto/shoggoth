"""
ExportProfile: a named, saved export setup for a project, persisted in the
project's own `export_profiles` list (round-trips via project_writer.py like
any other top-level project key). A profile is an ordered list of
ExportEntry rows -- each one its own type (images/pdf/tts/arkham_build/
guides/publish), own card scope, and own settings -- executed top to bottom
by `shoggoth.ui.export_runner.run_profile`, so a later entry can reuse
output an earlier one produced (e.g. re-render images once, then export TTS
and publish without re-rendering).

Older saved profiles used a single profile-wide `scope` + a fixed `sections`
dict instead of `entries`. Those aren't converted -- a profile missing
`entries` just loads with an empty entry list (see ExportProfile.__init__).
"""

ENTRY_KINDS = ('images', 'pdf', 'tts', 'arkham_build', 'guides', 'publish')

# Whether an entry of this kind has its own card scope. arkham.build and
# Guides always operate on the whole project; Publish operates on whatever
# earlier entries in the run already produced, not a card selection of its
# own.
USES_SCOPE = {
    'images': True,
    'pdf': True,
    'tts': True,
    'arkham_build': False,
    'guides': False,
    'publish': False,
}

DEFAULT_SETTINGS = {
    'images': {
        'folder': None,
        'size_label': None,
        'format': 'png',
        'quality': 95,
        'filename_format': 'id',
        'rotate': False,
        'bleed': True,
        'rounded': False,
        'separate_versions': False,
        'include_backs': False,
    },
    'pdf': {
        'flavor': 'pdf',
        'folder': None,
        'size_label': None,  # resolved to EXPORT_SIZES[0][0] (FFG 100%) lazily, see default_settings_for()
        'format': 'png',
        'quality': 100,
        'azao_format': 'jpeg',
        'azao_quality': 95,
        'include_backs': False,
        'rounded': False,
        'vector_text': True,
        'export_images': True,
        'output_path': None,
        'back_output_path': None,
    },
    'tts': {
        'folder': None,
        'export_images': True,
        'sync': False,
    },
    'arkham_build': {
        'url_pattern': None,
        'export_thumbnails': False,  # placeholder checkbox, not yet implemented
    },
    'guides': {
        'export_pdf': True,
        'export_html': True,
    },
    'publish': {
        'provider': 'celaeno',
        'images': True,
        'pdf': True,
        'tts': True,
        'guides': True,
        'arkham_build': True,
    },
}


def default_settings_for(kind):
    """A fresh, independent settings dict for one entry kind."""
    settings = dict(DEFAULT_SETTINGS[kind])
    if kind == 'pdf' and settings['size_label'] is None:
        from shoggoth.settings import EXPORT_SIZES
        settings['size_label'] = EXPORT_SIZES[0][0]  # FFG 100% (1453x2079, with bleed)
    return settings


DEFAULT_SCOPE = {
    'type': 'all',  # 'all' | 'player' | 'campaign' | 'encounter_sets' | 'cards'
    'encounter_set_ids': [],  # used when type == 'encounter_sets'
    'card_ids': [],  # used when type == 'cards'
}


def default_scope():
    """A fresh, independent copy of DEFAULT_SCOPE."""
    return dict(DEFAULT_SCOPE, encounter_set_ids=[], card_ids=[])


class ExportEntry:
    """Thin wrapper around one entry of a profile's `entries` list."""

    def __init__(self, data, project):
        self.project = project
        self.data = data
        self.data.setdefault('scope', default_scope())
        kind = self.data.get('type')
        if 'settings' not in self.data:
            self.data['settings'] = default_settings_for(kind) if kind in DEFAULT_SETTINGS else {}
        elif kind in DEFAULT_SETTINGS:
            # backfill any settings keys missing from an older/partial entry
            for key, default in DEFAULT_SETTINGS[kind].items():
                self.data['settings'].setdefault(key, default)

    @property
    def id(self):
        return self.data['id']

    @property
    def type(self):
        return self.data['type']

    @property
    def scope(self):
        return self.data['scope']

    @property
    def settings(self):
        return self.data['settings']


class ExportProfile:
    """Thin wrapper around one entry of a project's `export_profiles` list."""

    def __init__(self, data, project):
        self.project = project
        self.data = data
        # Older profiles used a single profile-wide `scope` + fixed
        # `sections` dict -- not converted, just start empty (see module
        # docstring); their stale `scope`/`sections` keys are left alone
        # (harmless, unread) rather than stripped.
        self.data.setdefault('entries', [])

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
    def entries(self):
        return [ExportEntry(entry, self.project) for entry in self.data['entries']]
