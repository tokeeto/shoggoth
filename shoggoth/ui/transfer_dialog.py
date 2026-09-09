"""
Dialog for transferring (moving or copying) cards between projects.

Reachable from Project -> Transfer Cards..., and opened pre-filled whenever
a card is dragged from one open project's tree onto another in
shoggoth/ui/browser/drag_drop.py.
"""
import json
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPushButton, QRadioButton, QVBoxLayout,
)

from shoggoth.i18n import tr
from shoggoth.ui.browser.tree_spec import card_display_name


class TransferCardsDialog(QDialog):
    """Move or copy a set of cards from one open project into another."""

    def __init__(
        self, window, *, source_project=None, selected_cards=None,
        destination_project=None, target_encounter=None, move=True, parent=None,
    ):
        super().__init__(parent or window)
        self.window = window
        self._preselected_ids = {c.id for c in (selected_cards or [])}
        self._target_encounter = target_encounter
        self._encounter_set_cache = {}

        self.setWindowTitle(tr("DLG_TRANSFER_CARDS"))
        self.setMinimumSize(560, 620)

        self._build_ui(move)

        self._populate_source_projects(source_project)
        self._populate_destination_projects(destination_project)
        self._refresh_card_list()
        self._refresh_specific_encounter_combo()

    # ── UI construction ─────────────────────────────────────────────────

    def _build_ui(self, move):
        layout = QVBoxLayout()

        # Source project + card picker
        layout.addWidget(QLabel(tr("FIELD_SOURCE_PROJECT")))
        self.source_combo = QComboBox()
        self.source_combo.currentIndexChanged.connect(self._on_source_changed)
        layout.addWidget(self.source_combo)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(tr("PLACEHOLDER_FILTER_CARDS"))
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._refresh_card_list)
        layout.addWidget(self.filter_edit)

        self.card_list = QListWidget()
        self.card_list.setSelectionMode(QAbstractItemView.NoSelection)
        layout.addWidget(self.card_list, 1)

        select_row = QHBoxLayout()
        select_all_btn = QPushButton(tr("BTN_SELECT_ALL"))
        select_all_btn.clicked.connect(lambda: self._set_all_checked(True))
        select_row.addWidget(select_all_btn)
        select_none_btn = QPushButton(tr("BTN_SELECT_NONE"))
        select_none_btn.clicked.connect(lambda: self._set_all_checked(False))
        select_row.addWidget(select_none_btn)
        select_row.addStretch(1)
        layout.addLayout(select_row)

        # Mode
        mode_box = QGroupBox(tr("FIELD_TRANSFER_MODE"))
        mode_layout = QHBoxLayout(mode_box)
        self.move_radio = QRadioButton(tr("OPT_MOVE_CARDS"))
        self.copy_radio = QRadioButton(tr("OPT_COPY_CARDS"))
        self.move_radio.setChecked(bool(move))
        self.copy_radio.setChecked(not move)
        mode_layout.addWidget(self.move_radio)
        mode_layout.addWidget(self.copy_radio)
        layout.addWidget(mode_box)

        # Destination
        layout.addWidget(QLabel(tr("FIELD_DESTINATION_PROJECT")))
        dest_row = QHBoxLayout()
        self.dest_combo = QComboBox()
        self.dest_combo.currentIndexChanged.connect(self._on_destination_changed)
        dest_row.addWidget(self.dest_combo, 1)
        browse_btn = QPushButton(tr("BTN_BROWSE"))
        browse_btn.clicked.connect(self._browse_destination)
        dest_row.addWidget(browse_btn)
        layout.addLayout(dest_row)

        # Encounter set handling
        enc_box = QGroupBox(tr("FIELD_ENCOUNTER_HANDLING"))
        enc_layout = QVBoxLayout(enc_box)
        self.enc_copy_radio = QRadioButton(tr("OPT_ENC_COPY"))
        self.enc_lose_radio = QRadioButton(tr("OPT_ENC_LOSE"))
        self.enc_specific_radio = QRadioButton(tr("OPT_ENC_SPECIFIC"))
        self.enc_group = QButtonGroup(self)
        for btn in (self.enc_copy_radio, self.enc_lose_radio, self.enc_specific_radio):
            self.enc_group.addButton(btn)
        enc_layout.addWidget(self.enc_copy_radio)
        enc_layout.addWidget(self.enc_lose_radio)
        specific_row = QHBoxLayout()
        specific_row.addWidget(self.enc_specific_radio)
        self.enc_specific_combo = QComboBox()
        specific_row.addWidget(self.enc_specific_combo, 1)
        enc_layout.addLayout(specific_row)
        layout.addWidget(enc_box)

        self.enc_copy_radio.setChecked(True)

        # Error label
        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: red;")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        # Buttons
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.button(QDialogButtonBox.Ok).setText(tr("BTN_TRANSFER"))
        self.button_box.accepted.connect(self._do_transfer)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.setLayout(layout)

    # ── Population helpers ──────────────────────────────────────────────

    def _populate_source_projects(self, preselect):
        self.source_combo.blockSignals(True)
        self.source_combo.clear()
        for project in self.window.open_projects:
            self.source_combo.addItem(project.name, project)
        idx = self.source_combo.findData(preselect) if preselect else -1
        if idx < 0:
            active = self.window.active_project
            idx = self.source_combo.findData(active) if active else -1
        self.source_combo.setCurrentIndex(max(idx, 0))
        self.source_combo.blockSignals(False)

    def _populate_destination_projects(self, preselect):
        self.dest_combo.blockSignals(True)
        self.dest_combo.clear()
        for project in self.window.open_projects:
            self.dest_combo.addItem(project.name, project)
        idx = self.dest_combo.findData(preselect) if preselect else -1
        self.dest_combo.setCurrentIndex(max(idx, 0))
        self.dest_combo.blockSignals(False)
        self._refresh_specific_encounter_combo()

    def _on_source_changed(self, _index):
        self._refresh_card_list()

    def _on_destination_changed(self, _index):
        self._refresh_specific_encounter_combo()

    def _current_source_project(self):
        return self.source_combo.currentData()

    def _current_destination_project(self):
        return self.dest_combo.currentData()

    def _refresh_card_list(self):
        self.card_list.clear()
        project = self._current_source_project()
        if not project:
            return

        name_filter = self.filter_edit.text().strip().lower()
        for card in project.cards:
            if name_filter and name_filter not in card.name.lower():
                continue

            group = card.encounter.name if card.encounter else tr("TYPE_PLAYER_CARD")
            label = f"[{group}] {card_display_name(card, include_level=not card.encounter)}"

            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            checked = card.id in self._preselected_ids
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            item.setData(Qt.UserRole, card)
            self.card_list.addItem(item)

    def _refresh_specific_encounter_combo(self):
        self.enc_specific_combo.clear()
        project = self._current_destination_project()
        sets = list(project.encounter_sets) if project else []
        for encounter_set in sets:
            self.enc_specific_combo.addItem(encounter_set.name, encounter_set)

        self.enc_specific_radio.setEnabled(bool(sets))
        if not sets and self.enc_specific_radio.isChecked():
            self.enc_copy_radio.setChecked(True)

        if self._target_encounter is not None:
            # findData() can't rely on EncounterSet's custom __eq__ across
            # QVariant boundaries reliably, so match by id explicitly - the
            # combo's entries are freshly-wrapped EncounterSet instances,
            # not the same object identity as self._target_encounter.
            idx = next(
                (i for i in range(self.enc_specific_combo.count())
                 if self.enc_specific_combo.itemData(i).id == self._target_encounter.id),
                -1,
            )
            if idx >= 0:
                self.enc_specific_combo.setCurrentIndex(idx)
                self.enc_specific_radio.setChecked(True)
            self._target_encounter = None  # only applies to the initial prefill

    def _set_all_checked(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.card_list.count()):
            self.card_list.item(i).setCheckState(state)

    def _checked_cards(self):
        """Return [(card, source_project)] for every checked row."""
        project = self._current_source_project()
        result = []
        for i in range(self.card_list.count()):
            item = self.card_list.item(i)
            if item.checkState() == Qt.Checked:
                result.append((item.data(Qt.UserRole), project))
        return result

    # ── Destination browsing ────────────────────────────────────────────

    def _browse_destination(self):
        start_dir = str(self.window.active_project.folder) if self.window.active_project else str(Path.home())
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("DLG_OPEN_PROJECT"), start_dir, tr("FILTER_SHOGGOTH_PROJECTS")
        )
        if not file_path:
            return

        for project in self.window.open_projects:
            if project.file_path == file_path:
                self._populate_destination_projects(project)
                return

        self.window.open_project(file_path)
        for project in self.window.open_projects:
            if project.file_path == file_path:
                self._populate_destination_projects(project)
                return

    # ── Transfer execution ──────────────────────────────────────────────

    def _encounter_mode(self):
        if self.enc_lose_radio.isChecked():
            return 'lose'
        if self.enc_specific_radio.isChecked():
            return 'specific'
        return 'copy'

    def _apply_encounter_policy(self, data, source_project, destination_project):
        mode = self._encounter_mode()

        if mode == 'lose':
            data.pop('encounter_set', None)
            return

        if mode == 'specific':
            target_set = self.enc_specific_combo.currentData()
            if target_set:
                data['encounter_set'] = target_set.id
            else:
                data.pop('encounter_set', None)
            return

        # mode == 'copy': carry the card's own encounter set across, reusing
        # a same-named set in the destination or creating one.
        current_id = data.get('encounter_set')
        if not current_id:
            return
        if source_project is destination_project:
            return  # id is already valid in this project

        dest_set = self._get_or_create_dest_encounter_set(current_id, source_project, destination_project)
        if dest_set:
            data['encounter_set'] = dest_set.id
        else:
            data.pop('encounter_set', None)

    def _get_or_create_dest_encounter_set(self, source_set_id, source_project, destination_project):
        cache_key = (id(source_project), source_set_id)
        if cache_key in self._encounter_set_cache:
            return self._encounter_set_cache[cache_key]

        source_set = source_project.get_encounter_set(source_set_id)
        if not source_set:
            return None

        dest_set = next((es for es in destination_project.encounter_sets if es.name == source_set.name), None)
        if not dest_set:
            dest_set = destination_project.add_encounter_set(source_set.name)

        self._encounter_set_cache[cache_key] = dest_set
        return dest_set

    def _do_transfer(self):
        cards = self._checked_cards()
        if not cards:
            self.error_label.setText(tr("MSG_NO_CARDS_SELECTED"))
            return

        destination_project = self._current_destination_project()
        if not destination_project:
            self.error_label.setText(tr("MSG_NO_DESTINATION_SELECTED"))
            return

        if self._encounter_mode() == 'specific' and not self.enc_specific_combo.currentData():
            self.error_label.setText(tr("MSG_NO_ENCOUNTER_SET_SELECTED"))
            return

        self.error_label.setText("")
        self._encounter_set_cache = {}
        copy_mode = self.copy_radio.isChecked()
        # Project defines __eq__ without __hash__ (unhashable) - track touched
        # projects by identity in a plain list instead of a set.
        touched_projects = [destination_project]

        def _touch(project):
            if not any(p is project for p in touched_projects):
                touched_projects.append(project)

        for card, source_project in cards:
            if copy_mode:
                new_data = json.loads(json.dumps(card.data))
                new_data['id'] = str(uuid4())
                self._apply_encounter_policy(new_data, source_project, destination_project)
                destination_project.add_card(new_data)
                destination_project.set_dirty(new_data['id'], True)
            else:
                if source_project is destination_project:
                    self._apply_encounter_policy(card.data, source_project, destination_project)
                else:
                    source_project.data['cards'].remove(card.data)
                    self._apply_encounter_policy(card.data, source_project, destination_project)
                    destination_project.add_card(card.data)
                    _touch(source_project)
                destination_project.set_dirty(card.id, True)

        for project in touched_projects:
            project.dirty = True

        self.window.refresh_tree()
        self.window.status_bar.showMessage(
            tr("STATUS_CARDS_TRANSFERRED").format(count=len(cards), name=destination_project.name)
        )
        self.accept()
