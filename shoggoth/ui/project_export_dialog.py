"""
Unified Project Export dialog: an ordered list of export entries (Images/
PDF/TTS/arkham.build/Guides/Publish), each with its own card scope and
settings, saved as named profiles inside the project file
(project.data['export_profiles']). Entries run top to bottom -- see
export_runner.py's module docstring for what that buys (reusing earlier
output, windowed Publish uploads). Opened in two modes:

  persist=True   "Export Project"   - the edited profile is saved back to the
                                       project on export.
  persist=False  "One-Time Export"  - identical UI, starting from the same
                                       saved profiles, but nothing is written
                                       back to the project.

Profile data is deep-copied out of the project at construction time and only
ever written back (via project.save_all()) on a successful persisted export,
so cancelling -- or running in one-time mode -- never mutates the live
project, even in memory.

Entry execution itself lives in export_runner.py, shared with the
Export -> Setups quick-run menu.
"""
import copy
from uuid import uuid4

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QMessageBox, QDialogButtonBox, QInputDialog, QFrame, QScrollArea,
    QListWidget, QListWidgetItem, QStackedWidget, QMenu,
)
from PySide6.QtCore import Qt

from shoggoth.export_profile import default_scope, default_settings_for
from shoggoth.i18n import tr
from shoggoth.ui.export_entry_widgets import build_entry_widget

_KIND_LABEL_KEYS = {
    'images': 'PE_SECTION_IMAGES',
    'pdf': 'PE_SECTION_PDF',
    'tts': 'PE_SECTION_TTS',
    'arkham_build': 'PE_SECTION_ARKHAM_BUILD',
    'guides': 'PE_SECTION_GUIDES',
    'publish': 'PE_SECTION_PUBLISH',
}

_ADDABLE_KINDS = ('images', 'pdf', 'tts', 'arkham_build', 'guides')


def _entry_kind_label(kind):
    return tr(_KIND_LABEL_KEYS.get(kind, kind))


class ProjectExportDialog(QDialog):
    def __init__(self, project, renderer, parent=None, persist=True):
        super().__init__(parent)
        self.project = project
        self.renderer = renderer
        self.persist = persist

        self._profiles_data = [copy.deepcopy(p.data) for p in project.export_profiles]
        if not self._profiles_data:
            self._profiles_data = [self._new_profile_dict('Default', seed_images=True)]
        self._current_index = 0
        self._entry_widgets = {}  # entry id -> settings widget, current profile only

        self.setWindowTitle(tr("PE_DLG_TITLE") if persist else tr("PE_ONE_TIME_TITLE"))
        self.resize(820, 760)
        self.setWindowModality(Qt.ApplicationModal)

        self._build_ui()
        self._select_profile(0)

    # ------------------------------------------------------------------
    # Entry/profile factories
    # ------------------------------------------------------------------

    def _new_entry_dict(self, kind):
        return {
            'id': str(uuid4()), 'type': kind,
            'scope': default_scope(), 'settings': default_settings_for(kind),
        }

    def _new_profile_dict(self, name, seed_images=False):
        entries = [self._new_entry_dict('images')] if seed_images else []
        return {'id': str(uuid4()), 'name': name, 'entries': entries}

    def _current_profile_entries(self):
        return self._profiles_data[self._current_index]['entries']

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)

        picker_row = QHBoxLayout()
        picker_row.addWidget(QLabel(tr("PE_PROFILE_LABEL")))
        self._profile_combo = QComboBox()
        for data in self._profiles_data:
            self._profile_combo.addItem(data.get('name', 'Profile'))
        self._profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        picker_row.addWidget(self._profile_combo, 1)
        add_profile_btn = QPushButton(tr("PE_BTN_ADD_PROFILE"))
        add_profile_btn.clicked.connect(self._add_profile)
        picker_row.addWidget(add_profile_btn)
        outer.addLayout(picker_row)

        body = QHBoxLayout()

        left = QVBoxLayout()
        self._entry_list = QListWidget()
        self._entry_list.setMinimumWidth(200)
        self._entry_list.currentRowChanged.connect(self._on_entry_selected)
        left.addWidget(self._entry_list, 1)

        self._add_entry_btn = QPushButton(tr("PE_ADD_ENTRY"))
        menu = QMenu(self._add_entry_btn)
        menu.aboutToShow.connect(lambda: self._populate_add_entry_menu(menu))
        self._add_entry_btn.setMenu(menu)
        left.addWidget(self._add_entry_btn)

        move_row = QHBoxLayout()
        up_btn = QPushButton(tr("PE_MOVE_UP"))
        up_btn.clicked.connect(lambda: self._move_current_entry(-1))
        down_btn = QPushButton(tr("PE_MOVE_DOWN"))
        down_btn.clicked.connect(lambda: self._move_current_entry(1))
        move_row.addWidget(up_btn)
        move_row.addWidget(down_btn)
        left.addLayout(move_row)

        remove_btn = QPushButton(tr("PE_REMOVE_ENTRY"))
        remove_btn.clicked.connect(self._remove_current_entry)
        left.addWidget(remove_btn)

        body.addLayout(left, 0)

        self._stack = QStackedWidget()
        self._empty_page = QLabel(tr("PE_NO_ENTRIES_HINT"))
        self._empty_page.setAlignment(Qt.AlignCenter)
        self._empty_page.setWordWrap(True)
        self._empty_page.setStyleSheet("color: #888; font-style: italic;")
        self._stack.addWidget(self._empty_page)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(self._stack)
        body.addWidget(scroll, 1)

        outer.addLayout(body, 1)

        button_row = QHBoxLayout()
        buttons = QDialogButtonBox(Qt.Horizontal)
        export_label = tr("PE_BTN_EXPORT") if self.persist else tr("PE_BTN_EXPORT_ONCE")
        buttons.addButton(export_label, QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._run_export)
        buttons.rejected.connect(self.reject)
        button_row.addWidget(buttons)
        outer.addLayout(button_row)

    def _populate_add_entry_menu(self, menu):
        menu.clear()
        from shoggoth.pdf_exporter import check_prince_installed
        prince_ok = check_prince_installed()
        for kind in _ADDABLE_KINDS:
            action = menu.addAction(_entry_kind_label(kind))
            action.triggered.connect(lambda checked=False, k=kind: self._add_entry(k))
            if kind == 'pdf' and not prince_ok:
                action.setEnabled(False)
                action.setToolTip(tr("PE_PRINCE_NOT_INSTALLED"))

        import shoggoth
        from shoggoth.cloud import registry
        providers = registry.available_providers(shoggoth.app.config)
        if providers:
            menu.addSeparator()
            for provider in providers:
                action = menu.addAction(tr("PE_ADD_PUBLISH_ENTRY").format(provider=provider.display_name))
                action.triggered.connect(lambda checked=False: self._add_entry('publish'))

    # ------------------------------------------------------------------
    # Entry list management
    # ------------------------------------------------------------------

    def _rebuild_entry_list(self, select_id=None):
        self._entry_list.blockSignals(True)
        self._entry_list.clear()
        counts = {}
        for entry in self._current_profile_entries():
            counts[entry['type']] = counts.get(entry['type'], 0) + 1
            label = _entry_kind_label(entry['type'])
            if counts[entry['type']] > 1:
                label = f"{label} ({counts[entry['type']]})"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, entry['id'])
            self._entry_list.addItem(item)

        target_row = 0
        if select_id is not None:
            for i in range(self._entry_list.count()):
                if self._entry_list.item(i).data(Qt.UserRole) == select_id:
                    target_row = i
                    break
        if self._entry_list.count():
            self._entry_list.setCurrentRow(target_row)
        self._entry_list.blockSignals(False)
        self._on_entry_selected(self._entry_list.currentRow())

    def _on_entry_selected(self, row):
        entries = self._current_profile_entries()
        if row < 0 or row >= len(entries):
            self._stack.setCurrentWidget(self._empty_page)
            return
        entry = entries[row]
        widget = self._entry_widgets.get(entry['id'])
        if widget is None:
            widget = build_entry_widget(entry['type'], self.project, self._stack)
            widget.apply(entry)
            self._entry_widgets[entry['id']] = widget
            self._stack.addWidget(widget)
        self._stack.setCurrentWidget(widget)

    def _add_entry(self, kind):
        entry = self._new_entry_dict(kind)
        self._current_profile_entries().append(entry)
        self._rebuild_entry_list(select_id=entry['id'])

    def _remove_current_entry(self):
        row = self._entry_list.currentRow()
        if row < 0:
            return
        entry = self._current_profile_entries().pop(row)
        widget = self._entry_widgets.pop(entry['id'], None)
        if widget is not None:
            self._stack.removeWidget(widget)
            widget.deleteLater()
        self._rebuild_entry_list()

    def _move_current_entry(self, delta):
        row = self._entry_list.currentRow()
        entries = self._current_profile_entries()
        new_row = row + delta
        if row < 0 or not (0 <= new_row < len(entries)):
            return
        entries[row], entries[new_row] = entries[new_row], entries[row]
        self._rebuild_entry_list(select_id=entries[new_row]['id'])

    def seed_single_entry(self, kind, scope=None):
        """Replace the current profile's entries with exactly one entry of
        `kind` (optionally with a preset scope), discarding whatever entries
        were loaded/seeded by default -- used by quick one-time export
        actions (see main_window/exports.py)."""
        entry = self._new_entry_dict(kind)
        if scope is not None:
            entry['scope'] = scope
        self._clear_entry_widgets()
        self._current_profile_entries()[:] = [entry]
        self._rebuild_entry_list(select_id=entry['id'])

    def _clear_entry_widgets(self):
        for widget in self._entry_widgets.values():
            self._stack.removeWidget(widget)
            widget.deleteLater()
        self._entry_widgets.clear()

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------

    def _snapshot_current_profile(self):
        entries_by_id = {e['id']: e for e in self._current_profile_entries()}
        for entry_id, widget in self._entry_widgets.items():
            entry = entries_by_id.get(entry_id)
            if entry is None:
                continue
            result = widget.read()
            entry['settings'] = result['settings']
            if result['scope'] is not None:
                entry['scope'] = result['scope']

    def _select_profile(self, index):
        self._current_index = index
        self._clear_entry_widgets()
        self._rebuild_entry_list()

    def _on_profile_changed(self, index):
        if index < 0 or index == self._current_index:
            return
        self._snapshot_current_profile()
        self._select_profile(index)

    def _add_profile(self):
        name, ok = QInputDialog.getText(self, tr("PE_BTN_ADD_PROFILE"), tr("PE_NEW_PROFILE_NAME_PROMPT"))
        if not ok or not name.strip():
            return
        self._snapshot_current_profile()
        entry = self._new_profile_dict(name.strip())
        self._profiles_data.append(entry)
        self._profile_combo.addItem(entry['name'])
        self._profile_combo.setCurrentIndex(self._profile_combo.count() - 1)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _run_export(self):
        self._snapshot_current_profile()
        profile_data = self._profiles_data[self._current_index]

        from shoggoth.ui.export_runner import run_profile, summarize
        results, errors = run_profile(self, self.project, self.renderer, profile_data)

        if self.persist:
            self.project.data['export_profiles'] = self._profiles_data
            self.project.save_all()

        QMessageBox.information(self, self.windowTitle(), summarize(results, errors))
        self.accept()
