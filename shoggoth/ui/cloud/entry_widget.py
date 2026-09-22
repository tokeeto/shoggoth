"""
Settings panel for a 'publish' export entry: which registered CloudProvider
to publish through (only shown as a dropdown when more than one is
available) and which content kinds it should upload, generic over whatever
`CloudProvider.content_kinds` the selected provider declares -- a second
provider needs no changes here, just its own CloudProvider subclass.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QFormLayout, QComboBox, QCheckBox, QLabel

from shoggoth.cloud import registry
from shoggoth.i18n import tr

_KIND_LABELS = {
    'images': 'PE_SECTION_IMAGES',
    'pdf': 'PE_SECTION_PDF',
    'tts': 'PE_SECTION_TTS',
    'guides': 'PE_SECTION_GUIDES',
    'arkham_build': 'PE_SECTION_ARKHAM_BUILD',
}


class PublishEntryWidget(QWidget):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self._entry_settings = {}

        import shoggoth
        self._providers = registry.available_providers(shoggoth.app.config)

        layout = QVBoxLayout(self)

        self._provider_combo = None
        if not self._providers:
            hint = QLabel(tr("PE_PUBLISH_NONE_AVAILABLE"))
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #888; font-style: italic;")
            layout.addWidget(hint)
        else:
            if len(self._providers) > 1:
                form = QFormLayout()
                self._provider_combo = QComboBox()
                for p in self._providers:
                    self._provider_combo.addItem(p.display_name, p.key)
                self._provider_combo.currentIndexChanged.connect(self._rebuild_kind_checkboxes)
                form.addRow(tr("PE_PUBLISH_PROVIDER_LABEL"), self._provider_combo)
                layout.addLayout(form)

            import shoggoth as _shoggoth
            email = _shoggoth.app.config.get('Shoggoth', 'publish_email', '')
            as_label = QLabel(tr("PE_PUBLISH_AS").format(email=email))
            as_label.setStyleSheet("color: #888; font-style: italic;")
            layout.addWidget(as_label)

        self._kind_checks = {}
        self._kind_layout = QVBoxLayout()
        layout.addLayout(self._kind_layout)
        self._rebuild_kind_checkboxes()

        layout.addStretch()

    def _current_provider(self):
        if self._provider_combo is not None:
            key = self._provider_combo.currentData()
        elif self._providers:
            key = self._providers[0].key
        else:
            return None
        return registry.get_provider(key)

    def _rebuild_kind_checkboxes(self):
        for cb in list(self._kind_checks.values()):
            self._kind_layout.removeWidget(cb)
            cb.deleteLater()
        self._kind_checks.clear()

        provider = self._current_provider()
        if provider is None:
            return
        for kind in provider.content_kinds:
            cb = QCheckBox(tr(_KIND_LABELS.get(kind, kind)))
            cb.setChecked(self._entry_settings.get(kind, True))
            self._kind_layout.addWidget(cb)
            self._kind_checks[kind] = cb

    def apply(self, entry):
        self._entry_settings = dict(entry.get('settings', {}))
        provider_key = self._entry_settings.get('provider')
        if self._provider_combo is not None and provider_key:
            idx = self._provider_combo.findData(provider_key)
            if idx >= 0:
                self._provider_combo.setCurrentIndex(idx)
        self._rebuild_kind_checkboxes()

    def read(self):
        provider = self._current_provider()
        if provider is None:
            # No provider available this session (e.g. logged out) -- keep
            # whatever was saved rather than dropping it.
            return {'scope': None, 'settings': self._entry_settings}
        settings = {'provider': provider.key}
        settings.update({kind: cb.isChecked() for kind, cb in self._kind_checks.items()})
        return {'scope': None, 'settings': settings}
