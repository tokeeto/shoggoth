"""
Card-specific widgets (icons, illustration) for Shoggoth using PySide6
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap

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


class IllustrationWidget(QWidget):
    """Widget for illustration settings"""

    # Signal emitted when illustration mode is toggled (enabled, face_side)
    illustration_mode_changed = Signal(bool, str)

    def __init__(self, face_side='front', project=None):
        super().__init__()
        self.face_side = face_side
        self.project = project
        self.illustration_mode = False
        layout = QVBoxLayout()

        # Image path
        path_layout = QHBoxLayout()
        self.path_input = LabeledLineEdit(tr("FIELD_IMAGE_PATH"))
        path_layout.addWidget(self.path_input)
        browse_btn = QPushButton(tr("BTN_BROWSE"))
        browse_btn.clicked.connect(self.browse_image)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        # Pan and scale with edit button
        pan_scale_layout = QHBoxLayout()
        self.pan_y_input = LabeledLineEdit(tr("FIELD_PAN_Y"))
        self.pan_x_input = LabeledLineEdit(tr("FIELD_PAN_X"))
        self.scale_input = LabeledLineEdit(tr("FIELD_SCALE"))
        pan_scale_layout.addWidget(self.pan_y_input)
        pan_scale_layout.addWidget(self.pan_x_input)
        pan_scale_layout.addWidget(self.scale_input)

        # Edit position button
        self.edit_position_btn = QPushButton(tr("BTN_EDIT_POSITION"))
        self.edit_position_btn.setCheckable(True)
        self.edit_position_btn.setToolTip(tr("TOOLTIP_DRAG_PREVIEW"))
        self.edit_position_btn.clicked.connect(self.toggle_illustration_mode)
        pan_scale_layout.addWidget(self.edit_position_btn)

        layout.addLayout(pan_scale_layout)

        # Artist
        self.artist_input = LabeledLineEdit(tr("FIELD_ARTIST"))
        layout.addWidget(self.artist_input)

        self.setLayout(layout)

    def toggle_illustration_mode(self, checked):
        """Toggle illustration positioning mode"""
        self.illustration_mode = checked
        if checked:
            self.edit_position_btn.setText(tr("BTN_DONE"))
            self.edit_position_btn.setStyleSheet("background-color: #4a9eff; color: white;")
        else:
            self.edit_position_btn.setText(tr("BTN_EDIT_POSITION"))
            self.edit_position_btn.setStyleSheet("")
        self.illustration_mode_changed.emit(checked, self.face_side)

    def set_illustration_mode(self, enabled):
        """Set illustration mode programmatically"""
        self.edit_position_btn.setChecked(enabled)
        self.toggle_illustration_mode(enabled)

    def update_pan(self, delta_x, delta_y):
        """Update pan values from external input (e.g., preview drag)"""
        try:
            current_x = int(self.pan_x_input.text() or 0)
            current_y = int(self.pan_y_input.text() or 0)
            self.pan_x_input.setText(str(current_x + delta_x))
            self.pan_y_input.setText(str(current_y + delta_y))
        except ValueError:
            pass

    def update_scale(self, delta):
        """Update scale value from external input (e.g., preview scroll)"""
        try:
            current_scale = float(self.scale_input.text() or 1.0)
            new_scale = max(0.1, current_scale + delta)
            self.scale_input.setText(f"{new_scale:.3f}")
        except ValueError:
            pass

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
