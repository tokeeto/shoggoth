"""
Shared building blocks for the Project Export dialog: the folder-picker and
profile-scope widgets, a collapsible section container, scope-to-card-list
resolution, and the threaded "render N cards with a progress dialog" runner
used by every section that exports card images.
"""
import threading
import multiprocessing
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QRadioButton, QButtonGroup,
    QLabel, QLineEdit, QPushButton, QFileDialog, QToolButton,
    QCheckBox, QProgressDialog, QFrame, QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt

from shoggoth.i18n import tr


class FolderPicker(QGroupBox):
    """Project-folder-vs-custom-folder radio pair with a browse button."""

    def __init__(self, title, default_folder, parent=None):
        super().__init__(title, parent)
        self._default_folder = Path(default_folder)

        layout = QVBoxLayout(self)

        self._btn_group = QButtonGroup(self)
        self._rb_project = QRadioButton(tr("TTS_FOLDER_PROJECT"))
        self._rb_custom = QRadioButton(tr("TTS_FOLDER_CUSTOM"))
        self._rb_project.setChecked(True)
        self._btn_group.addButton(self._rb_project)
        self._btn_group.addButton(self._rb_custom)
        self._rb_project.toggled.connect(self._on_toggled)
        layout.addWidget(self._rb_project)

        hint = QLabel(f"  {self._default_folder}")
        hint.setStyleSheet("color: #888; font-size: 9pt;")
        layout.addWidget(hint)

        layout.addWidget(self._rb_custom)

        row = QHBoxLayout()
        self._custom_input = QLineEdit()
        self._custom_input.setEnabled(False)
        row.addWidget(self._custom_input)
        self._browse_btn = QPushButton(tr("BTN_BROWSE"))
        self._browse_btn.setEnabled(False)
        self._browse_btn.clicked.connect(self._browse)
        row.addWidget(self._browse_btn)
        layout.addLayout(row)

    def _on_toggled(self, project_selected):
        self._custom_input.setEnabled(not project_selected)
        self._browse_btn.setEnabled(not project_selected)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(
            self, tr("TTS_DLG_SELECT_FOLDER"),
            self._custom_input.text().strip() or str(self._default_folder.parent)
        )
        if folder:
            self._custom_input.setText(folder)

    def selected_folder(self):
        if self._rb_custom.isChecked():
            custom = self._custom_input.text().strip()
            if custom:
                return Path(custom)
        return self._default_folder

    def set_folder(self, value):
        """value: None/'' selects the project folder, else a custom path string."""
        if value:
            self._rb_custom.setChecked(True)
            self._custom_input.setText(value)
        else:
            self._rb_project.setChecked(True)
            self._custom_input.clear()

    def folder_setting(self):
        """None if the project folder is selected, else the custom path string."""
        return str(self._custom_input.text().strip()) if self._rb_custom.isChecked() else None


def resolve_scope_cards(project, scope):
    """The list of Card objects a scope dict ({'type', 'encounter_set_ids',
    'card_ids'}) resolves to for the given project."""
    scope_type = scope.get('type', 'all')
    if scope_type == 'player':
        return list(project.player_cards)
    if scope_type == 'campaign':
        cards = []
        for es in project.encounter_sets:
            cards.extend(es.cards)
        return cards
    if scope_type == 'encounter_sets':
        ids = set(scope.get('encounter_set_ids', []))
        cards = []
        for es in project.encounter_sets:
            if es.id in ids:
                cards.extend(es.cards)
        return cards
    if scope_type == 'cards':
        ids = set(scope.get('card_ids', []))
        return [c for c in project.get_all_cards() if c.id in ids]
    return list(project.get_all_cards())


class ProfileScopeSelector(QGroupBox):
    """The single scope (which cards) an export profile applies to: all
    cards, player cards, campaign cards, a checked list of encounter sets, or
    a checked list of specific cards."""

    def __init__(self, project, parent=None):
        super().__init__(tr("TTS_SCOPE_LABEL"), parent)
        self.project = project

        layout = QVBoxLayout(self)
        self._btn_group = QButtonGroup(self)
        self._rb_all = QRadioButton(tr("TTS_SCOPE_ALL"))
        self._rb_player = QRadioButton(tr("TTS_SCOPE_PLAYER"))
        self._rb_campaign = QRadioButton(tr("TTS_SCOPE_CAMPAIGN"))
        self._rb_encounter_sets = QRadioButton(tr("PE_SCOPE_ENCOUNTER_SETS"))
        self._rb_cards = QRadioButton(tr("PE_SCOPE_CARDS"))
        self._rb_all.setChecked(True)

        for rb in (self._rb_all, self._rb_player, self._rb_campaign,
                   self._rb_encounter_sets, self._rb_cards):
            self._btn_group.addButton(rb)
            layout.addWidget(rb)
            rb.toggled.connect(self._update_visibility)

        self._es_list = QListWidget()
        self._es_list.setMaximumHeight(120)
        for es in project.encounter_sets:
            item = QListWidgetItem(es.name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, es.id)
            self._es_list.addItem(item)
        layout.addWidget(self._es_list)

        self._card_filter = QLineEdit()
        self._card_filter.setPlaceholderText(tr("PE_SCOPE_CARD_FILTER_PLACEHOLDER"))
        self._card_filter.textChanged.connect(self._filter_cards)
        layout.addWidget(self._card_filter)

        self._card_list = QListWidget()
        self._card_list.setMaximumHeight(160)
        for card in project.get_all_cards():
            item = QListWidgetItem(card.name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            item.setData(Qt.UserRole, card.id)
            self._card_list.addItem(item)
        layout.addWidget(self._card_list)

        self._update_visibility()

    def _update_visibility(self):
        self._es_list.setVisible(self._rb_encounter_sets.isChecked())
        self._card_filter.setVisible(self._rb_cards.isChecked())
        self._card_list.setVisible(self._rb_cards.isChecked())

    def _filter_cards(self, text):
        text = text.lower()
        for i in range(self._card_list.count()):
            item = self._card_list.item(i)
            item.setHidden(bool(text) and text not in item.text().lower())

    @staticmethod
    def _checked_ids(list_widget):
        return [
            list_widget.item(i).data(Qt.UserRole)
            for i in range(list_widget.count())
            if list_widget.item(i).checkState() == Qt.Checked
        ]

    @staticmethod
    def _set_checked_ids(list_widget, ids):
        ids = set(ids)
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in ids else Qt.Unchecked)

    def selected_type(self):
        if self._rb_player.isChecked():
            return 'player'
        if self._rb_campaign.isChecked():
            return 'campaign'
        if self._rb_encounter_sets.isChecked():
            return 'encounter_sets'
        if self._rb_cards.isChecked():
            return 'cards'
        return 'all'

    def read_scope(self):
        return {
            'type': self.selected_type(),
            'encounter_set_ids': self._checked_ids(self._es_list),
            'card_ids': self._checked_ids(self._card_list),
        }

    def set_scope(self, scope):
        radios = {
            'all': self._rb_all, 'player': self._rb_player, 'campaign': self._rb_campaign,
            'encounter_sets': self._rb_encounter_sets, 'cards': self._rb_cards,
        }
        radios.get(scope.get('type', 'all'), self._rb_all).setChecked(True)
        self._set_checked_ids(self._es_list, scope.get('encounter_set_ids', []))
        self._set_checked_ids(self._card_list, scope.get('card_ids', []))
        self._update_visibility()

    def cards_for(self, project):
        return resolve_scope_cards(project, self.read_scope())


class CollapsibleSection(QWidget):
    """A toggleable header (title + enabled checkbox + expand arrow) over a body widget."""

    def __init__(self, title, expanded=True, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        header = QHBoxLayout()
        self._toggle_btn = QToolButton()
        self._toggle_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._toggle_btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self._toggle_btn.setText(title)
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(expanded)
        self._toggle_btn.setStyleSheet("QToolButton { border: none; font-weight: bold; }")
        self._toggle_btn.clicked.connect(self._on_toggle_clicked)
        header.addWidget(self._toggle_btn)
        header.addStretch()

        self._enabled_checkbox = QCheckBox(tr("PE_SECTION_INCLUDE"))
        header.addWidget(self._enabled_checkbox)
        layout.addLayout(header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(20, 4, 0, 4)
        self.body.setVisible(expanded)
        layout.addWidget(self.body)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #444;")
        layout.addWidget(line)

    def _on_toggle_clicked(self, checked):
        self.set_expanded(checked)

    def set_expanded(self, expanded):
        self._toggle_btn.setChecked(expanded)
        self._toggle_btn.setArrowType(Qt.DownArrow if expanded else Qt.RightArrow)
        self.body.setVisible(expanded)

    def is_enabled(self):
        return self._enabled_checkbox.isChecked()

    def set_enabled_checked(self, value):
        self._enabled_checkbox.setChecked(value)


def run_image_export(parent, renderer, cards, folder, **export_kwargs):
    """Render `cards` to `folder` on a small thread pool with a progress dialog.

    Returns False if the user cancelled, True otherwise (including when
    `cards` is empty).
    """
    if not cards:
        return True

    folder.mkdir(parents=True, exist_ok=True)

    progress = QProgressDialog(
        tr("STATUS_EXPORTING"), tr("BTN_CANCEL"), 0, len(cards), parent
    )
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(0)

    cores = max(4, multiprocessing.cpu_count() - 1)
    threads = []
    cancelled = False

    for i, card in enumerate(cards):
        if progress.wasCanceled():
            cancelled = True
            break

        if i >= cores:
            threads[i - cores].join()
            progress.setValue(i - cores)

        progress.setLabelText(tr("MSG_EXPORTING_CARD").format(name=card.name))

        t = threading.Thread(
            target=renderer.export_card_images,
            args=(card, str(folder)),
            kwargs=export_kwargs,
        )
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    progress.setValue(len(cards))
    return not cancelled
