"""
Card-specific widgets (icons, illustration) for Shoggoth using PySide6
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer, QPointF, QRectF
from PySide6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QPen, QTransform

from shoggoth.ui.field_widgets import LabeledLineEdit
from shoggoth.files import overlay_dir
from shoggoth.i18n import tr


class IconsWidget(QWidget):
    """Widget for skill icons with +/- buttons for each icon type.

    Each icon has a single signed count. Positive counts map to the positive
    letter (W, I, C, A, Q); negative counts map to the negative letter
    (V, H, B, Z, P). The user just sees a number going from negative to positive.

    If a card's icons string contains both the positive AND negative letter for
    the same icon type (e.g. "WWVV"), that is an unsupported GUI state and the
    widget is disabled — the user should edit it via JSON directly.
    """

    # (positive_letter, negative_letter, display_name)
    ICONS = [
        ('W', 'V', 'Willpower'),
        ('I', 'H', 'Intellect'),
        ('C', 'B', 'Combat'),
        ('A', 'Z', 'Agility'),
        ('Q', 'P', 'Wild'),
    ]
    # Map negative letters back to their canonical (positive) key
    NEG_TO_POS = {'V': 'W', 'H': 'I', 'B': 'C', 'Z': 'A', 'P': 'Q'}
    MAX_COUNT = 8

    iconsChanged = Signal(str)

    def __init__(self):
        super().__init__()
        # Signed counts keyed by the positive letter (W, I, C, A, Q)
        self.counts = {pos: 0 for pos, neg, _ in self.ICONS}
        self.labels = {}
        self._updating = False

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        icons_label = QLabel(tr("LABEL_ICONS"))
        layout.addWidget(icons_label)

        self._conflict_label = QLabel(tr("ICONS_CONFLICT_WARNING"))
        self._conflict_label.setStyleSheet("color: orange;")
        self._conflict_label.setVisible(False)
        layout.addWidget(self._conflict_label)

        # Container for interactive rows (disabled as a unit when conflict)
        self._rows_widget = QWidget()
        rows_layout = QVBoxLayout()
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(2)

        for pos, neg, name in self.ICONS:
            row = QHBoxLayout()
            row.setSpacing(4)

            # Icon image
            icon_label = QLabel()
            icon_label.setToolTip(name)
            icon_path = overlay_dir / 'svg' / f"skill_icon_{pos}.svg"
            if icon_path.exists():
                pixmap = QPixmap(str(icon_path)).scaled(
                    20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                icon_label.setPixmap(pixmap)
            else:
                icon_label.setText(pos)
            icon_label.setFixedSize(20, 20)
            row.addWidget(icon_label)

            minus_btn = QPushButton("-")
            minus_btn.setFixedSize(24, 24)
            minus_btn.clicked.connect(lambda checked, k=pos: self._decrement(k))
            row.addWidget(minus_btn)

            count_label = QLabel("0")
            count_label.setAlignment(Qt.AlignCenter)
            count_label.setFixedWidth(24)
            self.labels[pos] = count_label
            row.addWidget(count_label)

            plus_btn = QPushButton("+")
            plus_btn.setFixedSize(24, 24)
            plus_btn.clicked.connect(lambda checked, k=pos: self._increment(k))
            row.addWidget(plus_btn)

            name_label = QLabel(name)
            row.addWidget(name_label)

            row.addStretch()
            rows_layout.addLayout(row)

        self._rows_widget.setLayout(rows_layout)
        layout.addWidget(self._rows_widget)
        self.setLayout(layout)

    def _update_label(self, key):
        v = self.counts[key]
        self.labels[key].setText(str(v))
        self.labels[key].setStyleSheet("color: #cc4444;" if v < 0 else "")

    def _increment(self, key):
        if self.counts[key] < self.MAX_COUNT:
            self.counts[key] += 1
            self._update_label(key)
            if not self._updating:
                self.iconsChanged.emit(self.get_icons_string())

    def _decrement(self, key):
        if self.counts[key] > -self.MAX_COUNT:
            self.counts[key] -= 1
            self._update_label(key)
            if not self._updating:
                self.iconsChanged.emit(self.get_icons_string())

    def get_icons_string(self):
        """Return icons as an ordered string.

        Positive counts produce the positive letter repeated (W, I, C, A, Q).
        Negative counts produce the negative letter repeated (V, H, B, Z, P).
        """
        result = ''
        for pos, neg, _ in self.ICONS:
            v = self.counts[pos]
            if v > 0:
                result += pos * v
            elif v < 0:
                result += neg * (-v)
        return result

    def set_icons_string(self, icons_str):
        """Set icons from a string.

        Disables the widget if both the positive and negative letter for any
        icon type appear in the string simultaneously (unsupported GUI state).
        """
        self._updating = True

        pos_set = {pos for pos, neg, _ in self.ICONS}

        # Count raw occurrences of each letter
        raw_pos = {pos: 0 for pos, neg, _ in self.ICONS}
        raw_neg = {pos: 0 for pos, neg, _ in self.ICONS}
        if icons_str:
            for char in icons_str.upper():
                if char in pos_set:
                    raw_pos[char] = min(raw_pos[char] + 1, self.MAX_COUNT)
                elif char in self.NEG_TO_POS:
                    key = self.NEG_TO_POS[char]
                    raw_neg[key] = min(raw_neg[key] + 1, self.MAX_COUNT)

        conflict = any(raw_pos[pos] > 0 and raw_neg[pos] > 0 for pos, neg, _ in self.ICONS)

        for pos, neg, _ in self.ICONS:
            self.counts[pos] = raw_pos[pos] - raw_neg[pos]
            self._update_label(pos)

        self._conflict_label.setVisible(conflict)
        self._rows_widget.setEnabled(not conflict)

        self._updating = False


class IllustrationPositionView(QWidget):
    """Crop-style viewport for positioning a face's illustration.

    Shows the whole artwork with the illustration region overlaid as a fixed
    frame; everything outside the region is dimmed, mimicking how the template
    window crops the art. Drag to pan, scroll to zoom (anchored at the cursor),
    double-click to reset to automatic fit.

    All values are in card coordinates (the 1500x2100-plus-bleed space that
    `illustration_region` and the pan/scale fields are defined in). Committed
    values are absolute, seeded from the same effective pan/scale the renderer
    uses, so the first interaction never makes the illustration jump.
    """

    pan_committed = Signal(float, float)  # absolute pan_x, pan_y
    scale_committed = Signal(float)       # absolute illustration scale
    reset_requested = Signal()

    COMMIT_INTERVAL_MS = 120  # throttle for live commits during a gesture
    MAX_DISPLAY_DIM = 1600    # artwork is pre-scaled to this for cheap repaints

    def __init__(self):
        super().__init__()
        self.setFixedHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip(tr("TOOLTIP_POSITION_VIEW"))

        # Artwork
        self._art = None            # display QPixmap (possibly downscaled)
        self._art_mirrored = None   # lazily-built mirrored variant
        self._art_path = None
        self._art_size = None       # original pixel dimensions (QSize)

        # Face state (card coordinates)
        self._region = QRectF()
        self._card_rect = QRectF(72, 72, 1500, 2100)
        self._pan = QPointF()
        self._scale = 1.0
        self._mirror = False
        self._rotation = 0.0

        # View transform: widget = card * _view_scale + _view_offset
        self._view_scale = 1.0
        self._view_offset = QPointF()

        # Gesture state
        self._dragging = False
        self._drag_pos = QPointF()
        self._pan_dirty = False
        self._scale_dirty = False

        self._commit_timer = QTimer(self)
        self._commit_timer.setSingleShot(True)
        self._commit_timer.setInterval(self.COMMIT_INTERVAL_MS)
        self._commit_timer.timeout.connect(self._commit)

        # Refit the view a moment after the last wheel tick, so zooming out
        # far never leaves the artwork clipped by the viewport
        self._refit_timer = QTimer(self)
        self._refit_timer.setSingleShot(True)
        self._refit_timer.setInterval(400)
        self._refit_timer.timeout.connect(self._refit_idle)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def has_image(self):
        return self._art is not None

    def set_state(self, path, region, pan_x, pan_y, scale, mirror, rotation,
                  orientation='vertical'):
        """Update the viewport from face data.

        `path` is a resolved image path or None. `pan_x`/`pan_y`/`scale` are
        the explicit values or None where unset; the effective values are
        derived here exactly as the renderer does.
        """
        if self._dragging:
            return

        if str(path) != str(self._art_path):
            self._art_path = path
            self._art = None
            self._art_mirrored = None
            self._art_size = None
            if path:
                pixmap = QPixmap(str(path))
                if not pixmap.isNull():
                    self._art_size = pixmap.size()
                    if max(pixmap.width(), pixmap.height()) > self.MAX_DISPLAY_DIM:
                        pixmap = pixmap.scaled(
                            self.MAX_DISPLAY_DIM, self.MAX_DISPLAY_DIM,
                            Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                    self._art = pixmap

        region = region or {}
        self._region = QRectF(
            region.get('x', 0), region.get('y', 0),
            region.get('width', 0), region.get('height', 0)
        )
        if orientation == 'horizontal':
            self._card_rect = QRectF(72, 72, 2100, 1500)
        else:
            self._card_rect = QRectF(72, 72, 1500, 2100)

        self._mirror = bool(mirror)
        self._rotation = float(rotation or 0)

        auto = self._auto_scale()
        self._scale = scale if scale else (auto or 1.0)
        self._pan = QPointF(
            self._region.x() if pan_x is None else pan_x,
            self._region.y() if pan_y is None else pan_y,
        )

        self.setCursor(Qt.OpenHandCursor if self._art else Qt.ArrowCursor)
        self._refit()
        self.update()

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    def _auto_scale(self):
        """Cover-fit scale, matching the renderer's implicit scale."""
        if not self._art_size or self._region.isEmpty():
            return None
        if self._art_size.width() <= 0 or self._art_size.height() <= 0:
            return None
        return max(
            self._region.height() / self._art_size.height(),
            self._region.width() / self._art_size.width(),
        )

    def _art_rect(self):
        """The artwork's bounding rect in card coordinates."""
        if not self._art_size:
            return QRectF()
        return QRectF(
            self._pan.x(), self._pan.y(),
            self._art_size.width() * self._scale,
            self._art_size.height() * self._scale,
        )

    def _to_widget(self, rect):
        return QRectF(
            rect.x() * self._view_scale + self._view_offset.x(),
            rect.y() * self._view_scale + self._view_offset.y(),
            rect.width() * self._view_scale,
            rect.height() * self._view_scale,
        )

    def _to_card(self, pos):
        if self._view_scale <= 0:
            return QPointF()
        return (pos - self._view_offset) / self._view_scale

    def _refit(self):
        """Fit the artwork and the region into the viewport with a margin."""
        content = self._art_rect().united(self._region)
        if content.isEmpty():
            content = self._card_rect
        margin = 0.06 * max(content.width(), content.height())
        content = content.adjusted(-margin, -margin, margin, margin)

        if content.width() <= 0 or content.height() <= 0:
            return
        self._view_scale = min(
            self.width() / content.width(),
            self.height() / content.height(),
        )
        self._view_offset = QPointF(
            self.width() / 2 - content.center().x() * self._view_scale,
            self.height() / 2 - content.center().y() * self._view_scale,
        )

    def _refit_idle(self):
        if not self._dragging:
            self._refit()
            self.update()

    # ------------------------------------------------------------------
    # Committing
    # ------------------------------------------------------------------

    def _schedule_commit(self):
        if not self._commit_timer.isActive():
            self._commit_timer.start()

    def _commit(self):
        self._commit_timer.stop()
        if self._pan_dirty:
            self._pan_dirty = False
            self.pan_committed.emit(self._pan.x(), self._pan.y())
        if self._scale_dirty:
            self._scale_dirty = False
            self.scale_committed.emit(self._scale)

    # ------------------------------------------------------------------
    # Qt event overrides
    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refit()

    def mousePressEvent(self, event):
        if self._art and event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._dragging = True
            self._drag_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if not self._dragging or self._view_scale <= 0:
            return
        delta = event.position() - self._drag_pos
        self._drag_pos = event.position()
        self._pan += delta / self._view_scale
        self._pan_dirty = True
        self._schedule_commit()
        self.update()

    def mouseReleaseEvent(self, event):
        if self._dragging and event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._dragging = False
            self._commit()
            self.setCursor(Qt.OpenHandCursor)
            self._refit()
            self.update()

    def mouseDoubleClickEvent(self, event):
        if self._art and event.button() == Qt.LeftButton:
            self._commit_timer.stop()
            self._pan_dirty = self._scale_dirty = False
            self.reset_requested.emit()

    def wheelEvent(self, event):
        if not self._art:
            event.ignore()
            return
        event.accept()

        steps = event.angleDelta().y() / 120.0
        if not steps:
            return

        auto = self._auto_scale() or self._scale or 1.0
        new_scale = self._scale * (1.08 ** steps)
        new_scale = max(auto * 0.05, min(auto * 10.0, new_scale))
        if new_scale == self._scale or self._scale <= 0:
            return

        # Keep the artwork point under the cursor fixed while zooming
        cursor_card = self._to_card(event.position())
        ratio = new_scale / self._scale
        self._pan = cursor_card - (cursor_card - self._pan) * ratio
        self._scale = new_scale

        self._pan_dirty = self._scale_dirty = True
        self._schedule_commit()
        self._refit_timer.start()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(42, 42, 42))
        if not self._art:
            return
        painter.setRenderHints(
            QPainter.Antialiasing | QPainter.SmoothPixmapTransform
        )

        # Card boundary, for context
        painter.setPen(QPen(QColor(110, 110, 110), 1, Qt.DashLine))
        painter.drawRect(self._to_widget(self._card_rect))

        # Artwork (rotation matches PIL: counterclockwise about the art's
        # center, cropped to the unrotated canvas)
        target = self._to_widget(self._art_rect())
        pixmap = self._mirrored_art() if self._mirror else self._art
        if self._rotation:
            painter.save()
            painter.setClipRect(target)
            center = target.center()
            painter.translate(center)
            painter.rotate(-self._rotation)
            painter.translate(-center)
            painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
            painter.restore()
        else:
            painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))

        # Dim everything outside the region, then frame it
        if not self._region.isEmpty():
            region_rect = self._to_widget(self._region)
            outside = QPainterPath()
            outside.addRect(QRectF(self.rect()))
            inner = QPainterPath()
            inner.addRect(region_rect)
            painter.fillPath(outside - inner, QColor(0, 0, 0, 140))
            painter.setPen(QPen(QColor(74, 158, 255), 1.5))
            painter.drawRect(region_rect)

    def _mirrored_art(self):
        if self._art_mirrored is None and self._art is not None:
            self._art_mirrored = self._art.transformed(QTransform().scale(-1, 1))
        return self._art_mirrored


class IllustrationWidget(QWidget):
    """Widget for illustration settings"""

    def __init__(self, project=None, face=None):
        super().__init__()
        self.project = project
        self.face = face
        self.scale_resolver = None
        self._committing = False
        layout = QVBoxLayout()

        # Image path
        path_layout = QHBoxLayout()
        self.path_input = LabeledLineEdit(tr("FIELD_IMAGE_PATH"))
        path_layout.addWidget(self.path_input)
        browse_btn = QPushButton(tr("BTN_BROWSE"))
        browse_btn.clicked.connect(self.browse_image)
        path_layout.addWidget(browse_btn)
        self.mirror_checkbox = QCheckBox(tr("FIELD_MIRROR"))
        path_layout.addWidget(self.mirror_checkbox)
        layout.addLayout(path_layout)

        # Pan and scale
        pan_scale_layout = QHBoxLayout()
        self.pan_y_input = LabeledLineEdit(tr("FIELD_PAN_Y"))
        self.pan_x_input = LabeledLineEdit(tr("FIELD_PAN_X"))
        self.scale_input = LabeledLineEdit(tr("FIELD_SCALE"))
        pan_scale_layout.addWidget(self.pan_y_input)
        pan_scale_layout.addWidget(self.pan_x_input)
        pan_scale_layout.addWidget(self.scale_input)

        # Scale quality warning indicator
        self.scale_warning = QLabel("?")
        self.scale_warning.setFixedSize(18, 18)
        self.scale_warning.setAlignment(Qt.AlignCenter)
        self.scale_warning.hide()
        pan_scale_layout.addWidget(self.scale_warning)

        layout.addLayout(pan_scale_layout)

        # Positioning viewport
        self.position_view = IllustrationPositionView()
        self.position_view.pan_committed.connect(self._on_view_pan)
        self.position_view.scale_committed.connect(self._on_view_scale)
        self.position_view.reset_requested.connect(self._on_view_reset)
        layout.addWidget(self.position_view)

        self.scale_input.input.textChanged.connect(self.update_scale_warning)
        self.path_input.input.textChanged.connect(self.update_scale_warning)

        # Any field edit re-syncs the viewport (values are read from the
        # fields, not the face, so ordering against FaceEditor's own
        # textChanged handlers doesn't matter)
        self.path_input.input.textChanged.connect(self.sync_viewport)
        self.pan_x_input.input.textChanged.connect(self.sync_viewport)
        self.pan_y_input.input.textChanged.connect(self.sync_viewport)
        self.scale_input.input.textChanged.connect(self.sync_viewport)
        self.mirror_checkbox.toggled.connect(self.sync_viewport)

        # Artist
        self.artist_input = LabeledLineEdit(tr("FIELD_ARTIST"))
        layout.addWidget(self.artist_input)

        self.setLayout(layout)

        self.sync_viewport()

    def update_scale_warning(self):
        """Show/hide a colored warning indicator based on the effective illustration scale."""
        scale_text = self.scale_input.text().strip()
        scale = None
        if scale_text:
            try:
                scale = float(scale_text)
            except ValueError:
                pass
        if scale is None and self.scale_resolver is not None:
            try:
                scale = self.scale_resolver()
            except Exception:
                pass

        if scale is None or scale <= 1.0:
            self.scale_warning.hide()
        else:
            color = "#e8a000" if scale <= 2.0 else "#c83030"
            self.scale_warning.setStyleSheet(
                f"QLabel {{ background-color: {color}; color: white;"
                " border-radius: 9px; font-weight: bold; font-size: 11px; }"
            )
            self.scale_warning.setToolTip(tr("TOOLTIP_SCALE_WARNING", scale=f"{scale:.2f}"))
            self.scale_warning.show()

    def _field_float(self, field):
        """Parse a field as float, returning None when empty or invalid."""
        text = field.text().strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _resolve_image_path(self):
        """Resolve the illustration path the same way the renderer does."""
        raw = self.path_input.text().strip()
        if not raw and self.face is not None:
            raw = self.face.get('illustration') or ''
        if not raw:
            return None
        path = Path(raw)
        if not path.is_absolute():
            if self.project is None:
                return None
            return self.project.find_file(path)
        return path if path.exists() else None

    def sync_viewport(self):
        """Push the current field/face state into the positioning viewport."""
        if self._committing:
            return
        if self.face is None:
            self.position_view.setVisible(False)
            return

        self.position_view.set_state(
            path=self._resolve_image_path(),
            region=self.face.get('illustration_region'),
            pan_x=self._field_float(self.pan_x_input),
            pan_y=self._field_float(self.pan_y_input),
            scale=self._field_float(self.scale_input) or None,
            mirror=self.mirror_checkbox.isChecked(),
            rotation=self.face.get('illustration_rotation', 0),
            orientation=self.face.get('orientation', 'vertical'),
        )
        self.position_view.setVisible(self.position_view.has_image())

    def _on_view_pan(self, pan_x, pan_y):
        """Write an absolute pan from the viewport into the fields."""
        self._committing = True
        try:
            self.pan_x_input.setText(str(int(round(pan_x))))
            self.pan_y_input.setText(str(int(round(pan_y))))
        finally:
            self._committing = False

    def _on_view_scale(self, scale):
        """Write an absolute scale from the viewport into the field."""
        self._committing = True
        try:
            self.scale_input.setText(f"{scale:.3f}")
        finally:
            self._committing = False

    def _on_view_reset(self):
        """Clear explicit pan/scale so the automatic fit applies again."""
        self._committing = True
        try:
            self.pan_x_input.setText('')
            self.pan_y_input.setText('')
            self.scale_input.setText('')
        finally:
            self._committing = False
        self.sync_viewport()

    def browse_image(self):
        """Browse for image file"""
        from PySide6.QtWidgets import QFileDialog
        from pathlib import Path

        current = self.path_input.text().strip()
        if current:
            p = Path(current)
            if not p.is_absolute() and self.project:
                p = self.project.folder / p
            if p.parent.exists():
                start_dir = str(p.parent)
            elif self.project:
                start_dir = str(self.project.folder)
            else:
                start_dir = str(Path.home())
        elif self.project:
            start_dir = str(self.project.folder)
        else:
            start_dir = str(Path.home())

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("DLG_SELECT_IMAGE"),
            start_dir,
            tr("FILTER_IMAGES")
        )
        if file_path:
            self.path_input.setText(file_path)
