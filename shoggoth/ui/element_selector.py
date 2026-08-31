"""
Shared searchable element picker.

Lists every ID-bearing project element - cards, encounter sets, guides and the
project itself - with fuzzy search, keyboard navigation and lazily-rendered
thumbnails. Two callers share it:

* the Go-to dialog (Ctrl+R) - selecting an entry navigates to it;
* the Insert Link action (Ctrl+L, see ``insert_link.py``) - selecting an entry
  inserts a ``<:{id} >`` text reference at the cursor.

Thumbnails are rendered on daemon threads by :class:`ThumbnailLoader`, which only
ever works on the handful of rows that matter right now (the current selection
plus the top few results); renders for rows that scrolled out of that set before
finishing are simply discarded.
"""
from __future__ import annotations

from dataclasses import dataclass
import threading

from PySide6.QtCore import Qt, Signal, QObject, QTimer, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QLabel, QWidget,
)

import shoggoth
from shoggoth.files import overlay_dir, icon_dir
from shoggoth.i18n import tr
from shoggoth.ui.goto_dialog import fuzzy_match

KIND_CARD = "Card"
KIND_ENCOUNTER = "Encounter Set"
KIND_GUIDE = "Guide"
KIND_PROJECT = "Project"

# How many leading result rows keep a live thumbnail (plus the selected row).
_THUMB_LEADING = 3

_THUMB_W, _THUMB_H = 46, 64


@dataclass(eq=False)
class ElementEntry:
    """One selectable project element."""
    id: str
    name: str
    kind: str            # one of the KIND_* constants (also shown as the label)
    path: str            # breadcrumb / category, shown under the name
    obj: object          # Card / EncounterSet / Guide / Project wrapper

    @property
    def search_text(self) -> str:
        return f"{self.name} {self.path}"


# ── element collection ───────────────────────────────────────────────────────

def _card_path(project, card) -> str:
    """Breadcrumb string for a card, matching the old Go-to dialog grouping."""
    encounter_id = card.data.get('encounter_set')
    if encounter_id:
        es = project.get_encounter_set(encounter_id)
        es_name = es.name if es else "?"
        if card.front.get('type') == 'location':
            subcategory = "Locations"
        elif card.back.get('type') == 'encounter':
            subcategory = "Encounter"
        else:
            subcategory = "Story"
        return f"Campaign Cards / {es_name} / {subcategory}"

    if investigator := card.data.get('investigator'):
        return f"Player Cards / Investigators / {investigator}"

    card_class = card.get_class()
    if card_class:
        class_name = {
            'guardian': 'Guardian', 'seeker': 'Seeker', 'rogue': 'Rogue',
            'mystic': 'Mystic', 'survivor': 'Survivor', 'neutral': 'Neutral',
            'multi': 'Multi-class',
        }.get(card_class, 'Other')
        return f"Player Cards / {class_name}"
    return "Player Cards / Other"


def collect_elements(project, kinds=None) -> list[ElementEntry]:
    """All ID-bearing elements of ``project``. ``kinds`` optionally filters to a
    subset of the KIND_* constants."""
    entries: list[ElementEntry] = []

    def want(kind):
        return kinds is None or kind in kinds

    if want(KIND_CARD):
        for card in project.cards:
            entries.append(ElementEntry(card.id, card.name, KIND_CARD,
                                        _card_path(project, card), card))

    if want(KIND_ENCOUNTER):
        for es in project.encounter_sets:
            entries.append(ElementEntry(es.id, es.name, KIND_ENCOUNTER,
                                        "Campaign Cards", es))

    if want(KIND_GUIDE):
        for guide in project.guides:
            entries.append(ElementEntry(guide.id, guide.name, KIND_GUIDE,
                                        "Guides", guide))

    if want(KIND_PROJECT):
        entries.append(ElementEntry(project.id, project.name, KIND_PROJECT,
                                    "", project))

    return entries


def _ui_is_dark() -> bool:
    """Whether the current Qt palette is dark (matches the project tree's check)."""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPalette
    app = QApplication.instance()
    if not app:
        return False
    return app.palette().color(QPalette.ColorRole.Window).lightness() < 128


def _invert_rgb_keep_alpha(img):
    """Invert the RGB channels of an RGBA PIL image, leaving alpha untouched."""
    from PIL import Image, ImageOps
    r, g, b, a = img.split()
    rgb = ImageOps.invert(Image.merge('RGB', (r, g, b)))
    return Image.merge('RGBA', (*rgb.split(), a))


def _load_icon_image(path):
    """RGBA PIL image for an encounter/project icon file (.png/.svg/...)."""
    from PIL import Image
    spath = str(path)
    if spath.lower().endswith('.svg'):
        import pyvips
        probe = pyvips.Image.new_from_file(spath)
        scale = min(_THUMB_W * 3 / probe.width, _THUMB_H * 3 / probe.height)
        vips_image = pyvips.Image.new_from_file(spath, scale=scale)
        mode = 'RGBA' if vips_image.bands == 4 else 'RGB'
        img = Image.frombytes(
            mode, (vips_image.width, vips_image.height),
            vips_image.write_to_memory(),
        )
        return img.convert('RGBA')
    with Image.open(spath) as img:
        return img.convert('RGBA')


def _resolve_icon_path(project, icon):
    """Best-effort filesystem path for an encounter-set / project ``icon`` value
    (may be a project-relative path or an asset-pack name). Returns ``None`` when
    nothing is found - the icon field is allowed to be empty."""
    if not icon:
        return None
    found = project.find_file(icon)
    if found:
        return found
    for base in (overlay_dir, icon_dir):
        candidate = base / icon
        if candidate.exists():
            return candidate
    return None


# ── thumbnail loading ────────────────────────────────────────────────────────

class ThumbnailLoader(QObject):
    """Renders element thumbnails on daemon threads.

    Only the entries passed to the most recent :meth:`request` are considered
    "wanted"; a worker whose entry is no longer wanted by the time it finishes
    drops its result. Finished ids are cached so re-requesting is free.
    """

    thumbnail_ready = Signal(str, object)  # (entry_id, PIL.Image | None)

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self._dark_ui = _ui_is_dark()  # read the palette now, on the main thread
        self._lock = threading.Lock()
        self._wanted: set[str] = set()
        self._inflight: set[str] = set()
        self._done: set[str] = set()
        self._stopped = False

    def stop(self):
        """Stop emitting results (call when the dialog closes)."""
        with self._lock:
            self._stopped = True
            self._wanted.clear()

    def request(self, entries: list[ElementEntry]):
        """Declare the currently-relevant entries; spawn workers for any that
        are neither done nor already running."""
        with self._lock:
            if self._stopped:
                return
            self._wanted = {e.id for e in entries}
            to_start = [e for e in entries
                        if e.id not in self._done and e.id not in self._inflight]
            for e in to_start:
                self._inflight.add(e.id)

        for entry in to_start:
            threading.Thread(target=self._work, args=(entry,), daemon=True).start()

    def _work(self, entry: ElementEntry):
        image = None
        try:
            image = self._render(entry)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Thumbnail render failed for {entry.name!r}: {exc}")
        with self._lock:
            self._inflight.discard(entry.id)
            self._done.add(entry.id)
            emit = not self._stopped and entry.id in self._wanted
        if emit:
            self.thumbnail_ready.emit(entry.id, image)

    def _render(self, entry: ElementEntry):
        if entry.kind == KIND_CARD:
            app = getattr(shoggoth, 'app', None)
            renderer = getattr(app, 'card_renderer', None) if app else None
            if renderer is None:
                return None
            return renderer.get_thumbnail(entry.obj)

        if entry.kind in (KIND_ENCOUNTER, KIND_PROJECT):
            path = _resolve_icon_path(self.project, getattr(entry.obj, 'icon', ''))
            if not path:
                return None
            icon = _load_icon_image(path)
            # Encounter/project icons are typically black-on-transparent; the
            # project tree inverts RGB on dark themes so they read as white.
            # Match that here so they don't vanish against the dark row.
            return _invert_rgb_keep_alpha(icon) if self._dark_ui else icon

        return None  # guides have no thumbnail


# ── list item widget ─────────────────────────────────────────────────────────

class ElementListItem(QWidget):
    """Thumbnail + highlighted name + kind/path row."""

    def __init__(self, entry: ElementEntry, search_term: str = ""):
        super().__init__()

        row = QHBoxLayout(self)
        row.setContentsMargins(6, 3, 6, 3)
        row.setSpacing(8)

        self.thumb = QLabel()
        self.thumb.setFixedSize(_THUMB_W, _THUMB_H)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet(
            "background: rgba(128,128,128,28); border-radius: 3px;"
        )
        row.addWidget(self.thumb)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        self.name_label = QLabel()
        name_font = QFont()
        name_font.setPointSize(11)
        name_font.setBold(True)
        self.name_label.setFont(name_font)
        self._set_name(entry.name, search_term)
        text_col.addWidget(self.name_label)

        sub = entry.kind if not entry.path else f"{entry.kind}  ·  {entry.path}"
        sub_label = QLabel(sub)
        sub_font = QFont()
        sub_font.setPointSize(9)
        sub_label.setFont(sub_font)
        sub_label.setStyleSheet("color: #888;")
        text_col.addWidget(sub_label)

        row.addLayout(text_col, stretch=1)

    def _set_name(self, name: str, search_term: str):
        if not search_term:
            self.name_label.setText(name)
            return
        score, indices = fuzzy_match(search_term, name)
        if score == 0:
            self.name_label.setText(name)
            return
        html = ""
        for i, ch in enumerate(name):
            esc = ch.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            if i in indices:
                html += f'<span style="background-color:#ffeb3b;color:#000;">{esc}</span>'
            else:
                html += esc
        self.name_label.setText(html)

    def set_thumbnail(self, pixmap):
        self.thumb.setPixmap(pixmap.scaled(
            _THUMB_W, _THUMB_H, Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))


# ── the dialog ───────────────────────────────────────────────────────────────

class ElementSelectorDialog(QDialog):
    """Modal fuzzy picker over a project's elements.

    Emits :attr:`element_chosen` with the selected :class:`ElementEntry` and
    accepts.
    """

    element_chosen = Signal(object)  # ElementEntry

    def __init__(self, project, *, title=None, kinds=None, instructions=None,
                 parent=None):
        super().__init__(parent)
        self.project = project
        self.entries = collect_elements(project, kinds)

        self.setWindowTitle(title or tr("DLG_GOTO_CARD"))
        self.setModal(True)
        self.resize(640, 460)

        self._thumb_cache: dict = {}          # entry_id -> QPixmap
        self._item_by_id: dict = {}           # entry_id -> QListWidgetItem

        self.loader = ThumbnailLoader(project, self)
        self.loader.thumbnail_ready.connect(self._on_thumbnail)

        self._setup_ui(instructions)
        self._update_results("")
        self.search_input.setFocus()

    # -- ui --

    def _setup_ui(self, instructions):
        layout = QVBoxLayout(self)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("MSG_TYPE_TO_SEARCH"))
        search_font = QFont()
        search_font.setPointSize(12)
        self.search_input.setFont(search_font)
        self.search_input.setMinimumHeight(35)
        self.search_input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.search_input)

        self.count_label = QLabel()
        self.count_label.setStyleSheet("color: #888; font-size: 10pt;")
        layout.addWidget(self.count_label)

        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(lambda *_: self._choose_current())
        self.results_list.currentItemChanged.connect(lambda *_: self._refresh_thumbnails())
        self.results_list.verticalScrollBar().valueChanged.connect(
            lambda *_: self._refresh_thumbnails()
        )
        layout.addWidget(self.results_list)

        hint = QLabel(instructions or tr("HELP_NAVIGATION"))
        hint.setStyleSheet("color: #999; font-size: 9pt; padding: 4px;")
        hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(hint)

    # -- search --

    def _on_text_changed(self, text):
        if hasattr(self, "_debounce"):
            self._debounce.stop()
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(lambda: self._update_results(text))
        self._debounce.start(90)

    def _update_results(self, term):
        self.results_list.clear()
        self._item_by_id.clear()

        if not term:
            ranked = list(self.entries)
        else:
            scored = []
            for entry in self.entries:
                score, _ = fuzzy_match(term, entry.name)
                if score == 0:
                    alt, _ = fuzzy_match(term, entry.search_text)
                    score = max(0, alt - 10)
                if score > 0:
                    scored.append((entry, score))
            scored.sort(key=lambda x: x[1], reverse=True)
            ranked = [e for e, _ in scored]

        ranked = ranked[:200]
        self.count_label.setText(f"{len(ranked)} / {len(self.entries)}")

        for entry in ranked:
            item = QListWidgetItem(self.results_list)
            widget = ElementListItem(entry, term)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.UserRole, entry)
            self.results_list.addItem(item)
            self.results_list.setItemWidget(item, widget)
            self._item_by_id[entry.id] = item
            cached = self._thumb_cache.get(entry.id)
            if cached is not None:
                widget.set_thumbnail(cached)

        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)
        self._refresh_thumbnails()

    # -- thumbnails --

    def _priority_entries(self) -> list[ElementEntry]:
        """Current selection + the first visible rows, deduped by id."""
        out: list[ElementEntry] = []
        seen: set[str] = set()

        def add(entry):
            if entry is not None and entry.id not in seen:
                seen.add(entry.id)
                out.append(entry)

        current = self.results_list.currentItem()
        if current:
            add(current.data(Qt.UserRole))

        first_visible = 0
        vp = self.results_list.viewport()
        top_item = self.results_list.itemAt(0, 0)
        if top_item is not None:
            first_visible = self.results_list.row(top_item)

        for row in range(first_visible, min(first_visible + _THUMB_LEADING,
                                            self.results_list.count())):
            item = self.results_list.item(row)
            if item:
                add(item.data(Qt.UserRole))
        return out

    def _refresh_thumbnails(self):
        wanted = self._priority_entries()
        # Paint anything already cached right away.
        for entry in wanted:
            cached = self._thumb_cache.get(entry.id)
            item = self._item_by_id.get(entry.id)
            if cached is not None and item is not None:
                widget = self.results_list.itemWidget(item)
                if widget is not None:
                    widget.set_thumbnail(cached)
        self.loader.request(wanted)

    @Slot(str, object)
    def _on_thumbnail(self, entry_id, pil_image):
        if pil_image is None:
            return
        from PIL.ImageQt import toqpixmap
        pixmap = toqpixmap(pil_image)
        self._thumb_cache[entry_id] = pixmap
        item = self._item_by_id.get(entry_id)
        if item is None:
            return
        widget = self.results_list.itemWidget(item)
        if widget is not None:
            widget.set_thumbnail(pixmap)

    # -- selection / keys --

    def _nudge(self, direction):
        count = self.results_list.count()
        if count == 0:
            return
        row = (self.results_list.currentRow() + direction) % count
        self.results_list.setCurrentRow(row)
        self.results_list.scrollToItem(self.results_list.currentItem())

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            self.reject()
        elif key in (Qt.Key_Return, Qt.Key_Enter):
            self._choose_current()
        elif key == Qt.Key_Down:
            self._nudge(1)
        elif key == Qt.Key_Up:
            self._nudge(-1)
        else:
            super().keyPressEvent(event)

    def _choose_current(self):
        item = self.results_list.currentItem()
        if not item:
            return
        entry = item.data(Qt.UserRole)
        if entry is not None:
            self.element_chosen.emit(entry)
            self.accept()

    # -- lifecycle --

    def showEvent(self, event):
        super().showEvent(event)
        self.search_input.setFocus()
        self.search_input.selectAll()

    def done(self, result):
        self.loader.stop()
        super().done(result)
