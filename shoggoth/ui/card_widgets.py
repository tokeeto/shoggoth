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
    """Widget for skill icons with +/- buttons for each icon type (WICAQ)"""

    # Icon order and their full names
    ICONS = [
        ('W', 'Willpower'),
        ('I', 'Intellect'),
        ('C', 'Combat'),
        ('A', 'Agility'),
        ('Q', 'Wild'),
    ]
    MAX_COUNT = 8

    iconsChanged = Signal(str)

    def __init__(self):
        super().__init__()
        self.counts = {letter: 0 for letter, _ in self.ICONS}
        self.labels = {}
        self._updating = False

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Label
        icons_label = QLabel(tr("LABEL_ICONS"))
        layout.addWidget(icons_label)

        # Create one row per icon
        for letter, name in self.ICONS:
            row = QHBoxLayout()
            row.setSpacing(4)

            # Icon image
            icon_label = QLabel()
            icon_label.setToolTip(name)
            icon_path = overlay_dir / 'svg' / f"skill_icon_{letter}.svg"
            if icon_path.exists():
                pixmap = QPixmap(str(icon_path)).scaled(
                    20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                icon_label.setPixmap(pixmap)
            else:
                icon_label.setText(letter)
            icon_label.setFixedSize(20, 20)
            row.addWidget(icon_label)

            # Minus button
            minus_btn = QPushButton("-")
            minus_btn.setFixedSize(24, 24)
            minus_btn.clicked.connect(lambda checked, l=letter: self.decrement(l))
            row.addWidget(minus_btn)

            # Count label
            count_label = QLabel("0")
            count_label.setAlignment(Qt.AlignCenter)
            count_label.setFixedWidth(20)
            self.labels[letter] = count_label
            row.addWidget(count_label)

            # Plus button
            plus_btn = QPushButton("+")
            plus_btn.setFixedSize(24, 24)
            plus_btn.clicked.connect(lambda checked, l=letter: self.increment(l))
            row.addWidget(plus_btn)

            # Name label
            name_label = QLabel(name)
            row.addWidget(name_label)

            row.addStretch()
            layout.addLayout(row)

        self.setLayout(layout)

    def increment(self, letter):
        """Increment count for an icon"""
        if self.counts[letter] < self.MAX_COUNT:
            self.counts[letter] += 1
            self.labels[letter].setText(str(self.counts[letter]))
            if not self._updating:
                self.iconsChanged.emit(self.get_icons_string())

    def decrement(self, letter):
        """Decrement count for an icon"""
        if self.counts[letter] > 0:
            self.counts[letter] -= 1
            self.labels[letter].setText(str(self.counts[letter]))
            if not self._updating:
                self.iconsChanged.emit(self.get_icons_string())

    def get_icons_string(self):
        """Get the icons as an ordered string like 'WWICQQ'"""
        result = ''
        for letter, _ in self.ICONS:
            result += letter * self.counts[letter]
        return result

    def set_icons_string(self, icons_str):
        """Set icons from a string like 'WWICQQ'"""
        self._updating = True
        # Reset all counts
        for letter, _ in self.ICONS:
            self.counts[letter] = 0

        # Count occurrences of each letter
        if icons_str:
            for char in icons_str.upper():
                if char in self.counts:
                    self.counts[char] = min(self.counts[char] + 1, self.MAX_COUNT)

        # Update labels
        for letter, _ in self.ICONS:
            self.labels[letter].setText(str(self.counts[letter]))

        self._updating = False


class IllustrationWidget(QWidget):
    """Widget for illustration settings"""

    # Signal emitted when illustration mode is toggled (enabled, face_side)
    illustration_mode_changed = Signal(bool, str)

    def __init__(self, face_side='front'):
        super().__init__()
        self.face_side = face_side
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

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("DLG_SELECT_IMAGE"),
            str(Path.home()),
            tr("FILTER_IMAGES")
        )
        if file_path:
            self.path_input.setText(file_path)
