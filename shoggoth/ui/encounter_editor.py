"""
Encounter Set Editor widget with thumbnails
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QMessageBox, QTabWidget,
    QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QPixmap, QImage, QCursor
from shoggoth.i18n import tr
from shoggoth.renderer import renderer_for_card
from shoggoth.ui.field_widgets import LabeledLineEdit, FieldWidget
import shoggoth
from pathlib import Path
from PySide6.QtWidgets import QFileDialog
from PIL.ImageQt import ImageQt
from collections import Counter

THUMBNAIL_BATCH_SIZE = 10


class ThumbnailWidget(QFrame):
    """A clickable thumbnail widget for a card"""

    clicked = Signal(str)  # Emits card ID

    def __init__(self, card_id, card_name):
        super().__init__()
        self.card_id = card_id
        self.card_name = card_name

        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setLineWidth(1)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(200, 280)
        self.image_label.setText(tr("LOADING"))
        layout.addWidget(self.image_label)

        name_label = QLabel(card_name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setMaximumWidth(200)
        layout.addWidget(name_label)

        self.setLayout(layout)

    def set_image(self, image_buffer):
        """Set the thumbnail image from a BytesIO buffer with proper aspect ratio"""
        if not image_buffer:
            self.image_label.setText(tr("DLG_ERROR"))
            return

        try:
            image = ImageQt(image_buffer)
            pixmap = QPixmap.fromImage(image)

            scaled_pixmap = pixmap.scaled(
                200, 280,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)

            if pixmap.width() > pixmap.height():
                self.image_label.setMinimumSize(280, 200)
                self.setMinimumWidth(290)
            else:
                self.image_label.setMinimumSize(200, 280)
                self.setMinimumWidth(210)

        except Exception as e:
            print(f"Error setting thumbnail: {e}")
            self.image_label.setText(tr("MSG_ERROR"))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.card_id)
        super().mousePressEvent(event)


class ThumbnailGenerator(QThread):
    """Thread for generating thumbnails in batches"""

    thumbnail_ready = Signal(str, object)  # card_id, image_buffer

    def __init__(self, cards, renderer):
        super().__init__()
        self.cards = cards
        self.renderer = renderer
        self._stop = False

    def run(self):
        for i in range(0, len(self.cards), THUMBNAIL_BATCH_SIZE):
            if self._stop:
                break
            batch = self.cards[i:i + THUMBNAIL_BATCH_SIZE]
            for card in batch:
                if self._stop:
                    break
                try:
                    thumbnail = renderer_for_card(self.renderer, card).get_thumbnail(card)
                    if not self._stop:
                        self.thumbnail_ready.emit(card.id, thumbnail)
                except Exception as e:
                    print(f"Error generating thumbnail for {card.name}: {e}")

    def stop(self):
        self._stop = True


class EncounterSetEditor(QWidget):
    """Editor for encounter set with info and thumbnail tabs"""

    card_clicked = Signal(object)  # Emits card object when thumbnail is clicked

    def __init__(self, encounter_set, renderer):
        super().__init__()
        self.encounter_set = encounter_set
        self.renderer = renderer
        self.thumbnail_widgets = {}
        self.thumbnail_thread = None
        self._thumbnails_started = False
        self._loading_meta = False

        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_info_tab(), tr("TAB_INFO"))
        self.tabs.addTab(self._build_cards_tab(), tr("TAB_CARDS"))
        self.tabs.addTab(self._build_meta_tab(), tr("TAB_META"))
        self.tabs.currentChanged.connect(self._on_tab_changed)

        main_layout.addWidget(self.tabs)
        self.setLayout(main_layout)

        self.setup_fields()

    def _build_info_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()

        title = QLabel(tr("TITLE_ENCOUNTER_SET").format(name=self.encounter_set.name))
        title.setStyleSheet("font-size: 20pt; font-weight: bold;")
        layout.addWidget(title)

        self.name_input = LabeledLineEdit(tr("FIELD_NAME"))
        layout.addWidget(self.name_input)

        self.code_input = LabeledLineEdit(tr("FIELD_CODE"))
        layout.addWidget(self.code_input)

        self.order_input = LabeledLineEdit(tr("FIELD_ORDER"))
        layout.addWidget(self.order_input)

        icon_layout = QHBoxLayout()
        icon_layout.addWidget(QLabel(tr("FIELD_ICON")))
        self.icon_input = LabeledLineEdit("")
        icon_layout.addWidget(self.icon_input)
        browse_btn = QPushButton(tr("BTN_BROWSE"))
        browse_btn.clicked.connect(self.browse_icon)
        icon_layout.addWidget(browse_btn)

        self.icon_preview = QLabel()
        self.icon_preview.setFixedSize(64, 64)
        self.icon_preview.setAlignment(Qt.AlignCenter)
        self.icon_preview.setStyleSheet("border: 1px solid #aaa; background: #d4c3a0;")
        icon_layout.addWidget(self.icon_preview)

        layout.addLayout(icon_layout)

        cards_count = len(self.encounter_set.cards)
        total_amount = sum(card.amount for card in self.encounter_set.cards)
        stats_label = QLabel(tr("STATS_CARDS_IN_SET").format(unique=cards_count, total=total_amount))
        stats_label.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(stats_label)

        # Counts of cards by type
        # Loop through card types and get count/add widget
        self._encounter_set_stats(layout)

        layout.addStretch()

        # Action buttons
        button_layout = QHBoxLayout()

        new_card_btn = QPushButton(tr("BTN_NEW_CARD"))
        new_card_btn.clicked.connect(self.add_new_card)
        button_layout.addWidget(new_card_btn)

        export_btn = QPushButton(tr("BTN_EXPORT_SET"))
        export_btn.clicked.connect(self.export_set)
        button_layout.addWidget(export_btn)

        button_layout.addStretch()

        delete_btn = QPushButton(tr("BTN_DELETE_ENCOUNTER_SET"))
        delete_btn.setStyleSheet("background-color: #d32f2f; color: white;")
        delete_btn.clicked.connect(self.delete_encounter_set)
        button_layout.addWidget(delete_btn)

        layout.addLayout(button_layout)

        tab.setLayout(layout)
        return tab

    def _encounter_set_stats(self, layout):
        encounter_card_groups = ['player', 'story', 'location', 'treachery']

        cards_by_type = dict()
        card_traits = dict()
        for group in encounter_card_groups:
            card_traits[group] = []
            cards_by_type[group] = 0
        for card in self.encounter_set.cards:
            # If the back of the card has different traits from the front, treat it like a separate card for the purposes of counting traits.
            if (card.back.get('traits') != '' and card.front.get('traits') != card.back.get('traits')):
                group = card.back.get('grouping', card.back.get('type'))
                self._build_trait_list(card_traits, card, group, cards_by_type)

            group = card.front.get('grouping', card.front.get('type'))
            self._build_trait_list(card_traits, card, group, cards_by_type)


        for group in encounter_card_groups:
            self._add_trait_counts(card_traits, layout, group, cards_by_type)

    def _build_trait_list(self, card_traits, card, group, cards_by_type):
        player_cards = ['asset', 'event', 'skill', 'investigator', 'investigator_back', 'customizable', 'player']
        story_cards = ['act', 'act_back', 'agenda', 'agenda_back', 'scenario', 'chaos', 'story', 'act_agenda_full', 'act_agenda_full_back']
        encounter_cards = ['treachery', 'enemy']

        if (group in encounter_cards):
            self._get_traits(card, card_traits['treachery'])
            cards_by_type['treachery'] += card.amount
        elif (group == 'location'):
            self._get_traits(card, card_traits['location'])
            cards_by_type['location'] += card.amount
        elif (group in player_cards):
            self._get_traits(card, card_traits['player'])
            cards_by_type['player'] += card.amount
        elif (group in story_cards):
            self._get_traits(card, card_traits['story'])
            cards_by_type['story'] += card.amount

    def _add_trait_counts(self, traits, layout, group, cards_by_type):
        if cards_by_type[group] > 0:
            counter = Counter(traits[group])
            type_string = "TYPE_" + group.upper()
            tr_string = tr("CARDS_COUNT").format(type=tr(type_string).capitalize(), count=cards_by_type[group])
            if len(traits[group]) > 0:
                tr_string += ' ' + tr("TRAITS_COUNT")
            trait_list = "<b>" + tr_string + "</b> <ul>"
            for trait, count in counter.items():
                trait_list += "<li>" + str(trait) + ": " + str(count) + "</li>"
            trait_list += "</ul>"
            label = QLabel(trait_list)
            label.setStyleSheet("color: #666;")
            layout.addWidget(label)

    def _get_traits(self, card, trait_list):
        card_traits = card.front.get('traits').split('.')
        for trait in card_traits:
            trait = trait.strip()
            if trait != '':
                for copy in range(card.amount): 
                    trait_list.append(trait)

    def _build_cards_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.thumbnail_container = QWidget()
        self.thumbnail_grid = QGridLayout()
        self.thumbnail_grid.setSpacing(10)
        self.thumbnail_grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.thumbnail_container.setLayout(self.thumbnail_grid)

        scroll_area.setWidget(self.thumbnail_container)
        layout.addWidget(scroll_area)

        tab.setLayout(layout)
        return tab

    def _build_meta_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()

        note = QLabel(tr("META_TAB_NOTE"))
        note.setWordWrap(True)
        note.setStyleSheet("color: #888; font-style: italic;")
        layout.addWidget(note)

        self.tags_input = LabeledLineEdit(tr("FIELD_TAGS"))
        self.tags_input.setPlaceholderText(tr("PLACEHOLDER_TAGS"))
        self.tags_input.input.textChanged.connect(self.on_tags_changed)
        layout.addWidget(self.tags_input)

        label = QLabel(tr("FIELD_REQUIRED_SETS"))
        label.setStyleSheet("font-size: 14pt; font-weight: bold;")
        layout.addWidget(label)

        desc = QLabel(tr("HELP_REQUIRED_SETS"))
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(desc)

        # Kept at data['meta']['tts']['included_sets'] for backwards compatibility —
        # this list used to live on its own TTS tab (see guide_editor.py, which also
        # reads that path) before becoming a first-class "required sets" meta field.
        self.required_sets_list = QListWidget()
        self._populate_required_sets_list()
        self.required_sets_list.itemChanged.connect(self._on_required_set_toggled)
        layout.addWidget(self.required_sets_list)

        tab.setLayout(layout)
        return tab

    def _get_required_sets(self):
        """Return the list of required/included set IDs for this encounter set."""
        return (
            self.encounter_set.data
            .setdefault('meta', {})
            .setdefault('tts', {})
            .get('included_sets', [])
        )

    def _set_required_sets(self, set_ids):
        """Persist the list of required/included set IDs for this encounter set."""
        tts = (
            self.encounter_set.data
            .setdefault('meta', {})
            .setdefault('tts', {})
        )
        tts['included_sets'] = set_ids
        self.encounter_set.dirty = True

    def _populate_required_sets_list(self):
        self.required_sets_list.blockSignals(True)
        self.required_sets_list.clear()
        current_id = self.encounter_set.id
        selected_ids = self._get_required_sets()
        for es in self.encounter_set.project.encounter_sets:
            if es.id == current_id:
                continue
            item = QListWidgetItem(es.name)
            item.setData(Qt.UserRole, es.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if es.id in selected_ids else Qt.Unchecked)
            self.required_sets_list.addItem(item)
        self.required_sets_list.blockSignals(False)

    def _on_required_set_toggled(self, item):
        set_id = item.data(Qt.UserRole)
        current = list(self._get_required_sets())
        if item.checkState() == Qt.Checked:
            if set_id not in current:
                current.append(set_id)
        else:
            if set_id in current:
                current.remove(set_id)
        self._set_required_sets(current)

    def on_tags_changed(self, text):
        if self._loading_meta:
            return
        tags = [t.strip() for t in text.split(',') if t.strip()]
        self.encounter_set.set_meta('tags', tags or None)

    def _on_tab_changed(self, index):
        """Start thumbnail generation when the Cards tab is first shown"""
        if index == 1 and not self._thumbnails_started:
            self._thumbnails_started = True
            self._populate_thumbnails()

    def setup_fields(self):
        self.fields = [
            FieldWidget(self.name_input.input, 'name'),
            FieldWidget(self.code_input.input, 'code'),
            FieldWidget(self.order_input.input, 'order', int, str),
            FieldWidget(self.icon_input.input, 'icon'),
        ]
        for field in self.fields:
            field.widget.textChanged.connect(lambda v, f=field: self.on_field_changed(f, v))
        self.icon_input.input.textChanged.connect(self._update_icon_preview)

    def load_data(self):
        for field in self.fields:
            field.update_from_card(self.encounter_set)

        self._loading_meta = True
        self.tags_input.setText(', '.join(self.encounter_set.get_meta('tags') or []))
        self._loading_meta = False

    def on_field_changed(self, field, value):
        field.update_card(self.encounter_set, value)

    def _update_icon_preview(self, path_text):
        path = Path(path_text.strip()) if path_text.strip() else None
        if path and not path.is_absolute():
            project_folder = Path(self.encounter_set.project.file_path).parent
            path = project_folder / path
        if path and path.exists():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.icon_preview.setPixmap(
                    pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
                return
        self.icon_preview.setPixmap(QPixmap())
        self.icon_preview.setText("")

    def browse_icon(self):
        current = self.icon_input.input.text().strip()
        project_folder = self.encounter_set.project.folder
        if current:
            p = Path(current)
            if not p.is_absolute():
                p = project_folder / p
            start_dir = str(p.parent) if p.parent.exists() else str(project_folder)
        else:
            start_dir = str(project_folder)

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("DLG_SELECT_ICON"),
            start_dir,
            tr("FILTER_IMAGES")
        )
        if file_path:
            self.icon_input.input.setText(file_path)

    def _populate_thumbnails(self):
        """Create thumbnail widgets and start background generation"""
        cards = self.encounter_set.cards
        if not cards:
            return

        cols_per_row = 3
        for i, card in enumerate(cards):
            thumbnail = ThumbnailWidget(card.id, card.name)
            thumbnail.clicked.connect(lambda card_id, c=card: self.on_thumbnail_clicked(c))
            self.thumbnail_grid.addWidget(thumbnail, i // cols_per_row, i % cols_per_row)
            self.thumbnail_widgets[card.id] = thumbnail

        self.thumbnail_thread = ThumbnailGenerator(cards, self.renderer)
        self.thumbnail_thread.thumbnail_ready.connect(self.on_thumbnail_ready)
        self.thumbnail_thread.start()

    def on_thumbnail_ready(self, card_id, image_buffer):
        if card_id in self.thumbnail_widgets:
            self.thumbnail_widgets[card_id].set_image(image_buffer)

    def on_thumbnail_clicked(self, card):
        self.card_clicked.emit(card)

    def add_new_card(self):
        shoggoth.app.new_card_dialog()

    def export_set(self):
        shoggoth.app.export_encounter_set(self.encounter_set)

    def delete_encounter_set(self):
        reply = QMessageBox.question(
            self,
            tr("DLG_DELETE_ENCOUNTER_SET"),
            tr("CONFIRM_DELETE_ENCOUNTER_SET").format(name=self.encounter_set.name, count=len(self.encounter_set.cards)),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            QMessageBox.information(self, tr("DLG_NOT_IMPLEMENTED"), tr("MSG_ENCOUNTER_SET_DELETION_NOT_IMPLEMENTED"))

    def cleanup(self):
        if self.thumbnail_thread and self.thumbnail_thread.isRunning():
            try:
                self.thumbnail_thread.thumbnail_ready.disconnect(self.on_thumbnail_ready)
            except Exception:
                pass

            self.thumbnail_thread.stop()
            self.thumbnail_thread.wait(1000)

            if self.thumbnail_thread.isRunning():
                self.thumbnail_thread.terminate()
                self.thumbnail_thread.wait()

            self.thumbnail_thread = None

    def __del__(self):
        self.cleanup()
