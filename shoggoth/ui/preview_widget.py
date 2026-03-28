"""
Improved card preview widget with zoom, pan, and tabs
"""
from shoggoth.i18n import tr
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QLabel, QScrollArea,
    QSizePolicy, QHBoxLayout, QPushButton
)
from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QPixmap, QImage, QWheelEvent, QMouseEvent, QPainter, QGuiApplication


class ZoomableImageLabel(QLabel):
    """A label that displays an image with zoom and pan capabilities.

    Panning is implemented via a custom paintEvent so the image can be
    dragged freely beyond the widget bounds (useful for inspecting card edges).
    """

    illustration_pan_changed = Signal(int, int)   # delta_x, delta_y
    illustration_scale_changed = Signal(float)    # delta scale
    zoom_changed = Signal(float)                  # new zoom factor

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setScaledContents(False)

        # Zoom state
        self.zoom_factor = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 5.0
        self.zoom_step = 0.1

        # Pan state
        self.panning = False
        self.pan_start_pos = QPoint()
        self.current_offset = QPoint(0, 0)

        # Pixmaps
        self.original_pixmap = None
        self._display_pixmap = None  # pre-scaled for current zoom

        # Illustration mode
        self.illustration_mode = False
        self.card_scale_factor = 1.0

        self.setMouseTracking(True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def setPixmap(self, pixmap):
        """Set a new card image and reset zoom/pan."""
        self.original_pixmap = pixmap
        self.zoom_factor = 1.0
        self.current_offset = QPoint(0, 0)
        self._update_cursor()
        self._rebuild_scaled()

    def set_illustration_mode(self, enabled):
        """Enable/disable illustration-positioning mode."""
        self.illustration_mode = enabled
        self._update_cursor()

    def reset_zoom(self):
        self.zoom_factor = 1.0
        self.current_offset = QPoint(0, 0)
        self._rebuild_scaled()
        self.zoom_changed.emit(self.zoom_factor)

    def zoom_in(self):
        self.zoom_factor = min(self.max_zoom, self.zoom_factor + self.zoom_step)
        self._rebuild_scaled()
        self.zoom_changed.emit(self.zoom_factor)

    def zoom_out(self):
        self.zoom_factor = max(self.min_zoom, self.zoom_factor - self.zoom_step)
        self._rebuild_scaled()
        self.zoom_changed.emit(self.zoom_factor)

    def fit_to_window(self):
        self.reset_zoom()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rebuild_scaled(self):
        """Rebuild the pre-scaled pixmap for the current zoom level."""
        if not self.original_pixmap:
            self._display_pixmap = None
            self.update()
            return

        original_size = self.original_pixmap.size()
        available_size = self.size()

        # Fit to widget first
        fit_size = original_size.scaled(available_size, Qt.KeepAspectRatio)

        if original_size.width() > 0:
            self.card_scale_factor = fit_size.width() / original_size.width()
        else:
            self.card_scale_factor = 1.0

        final_w = int(fit_size.width() * self.zoom_factor)
        final_h = int(fit_size.height() * self.zoom_factor)

        self._display_pixmap = self.original_pixmap.scaled(
            final_w, final_h,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.update()

    def _update_cursor(self):
        if self.illustration_mode:
            self.setCursor(Qt.CrossCursor)
        elif self.original_pixmap:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    # ------------------------------------------------------------------
    # Qt event overrides
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        # Let QLabel draw the background / frame
        super().paintEvent(event)
        if not self._display_pixmap:
            return
        painter = QPainter(self)
        x = (self.width()  - self._display_pixmap.width())  // 2 + self.current_offset.x()
        y = (self.height() - self._display_pixmap.height()) // 2 + self.current_offset.y()
        painter.drawPixmap(x, y, self._display_pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.original_pixmap:
            self._rebuild_scaled()

    def wheelEvent(self, event: QWheelEvent):
        if not self.original_pixmap:
            return

        delta = event.angleDelta().y()

        if self.illustration_mode:
            scale_delta = 0.02 if delta > 0 else -0.02
            self.illustration_scale_changed.emit(scale_delta)
        else:
            new_zoom = self.zoom_factor + (self.zoom_step if delta > 0 else -self.zoom_step)
            new_zoom = max(self.min_zoom, min(self.max_zoom, new_zoom))
            if new_zoom != self.zoom_factor:
                self.zoom_factor = new_zoom
                self._rebuild_scaled()
                self.zoom_changed.emit(self.zoom_factor)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.panning = True
            self.pan_start_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
        elif event.button() == Qt.MiddleButton:
            self.panning = True
            self.pan_start_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.panning and event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self.panning = False
            self._update_cursor()

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self.panning:
            return

        delta = event.pos() - self.pan_start_pos
        self.pan_start_pos = event.pos()

        if self.illustration_mode:
            scale = self.zoom_factor * self.card_scale_factor
            if scale > 0:
                card_dx = int(delta.x() / scale)
                card_dy = int(delta.y() / scale)
                if card_dx != 0 or card_dy != 0:
                    self.illustration_pan_changed.emit(card_dx, card_dy)
        else:
            self.current_offset += delta
            self.update()  # No rescaling needed — just repaint at new position


class CardPreviewTab(QWidget):
    """A single tab for card preview with zoom controls"""

    illustration_pan_changed = Signal(int, int)
    illustration_scale_changed = Signal(float)

    def __init__(self, title):
        super().__init__()
        self.title = title

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # The image lives directly in the widget — no scroll area, so the
        # image can be panned freely beyond its own bounds.
        self.image_label = ZoomableImageLabel()
        self.image_label.setMinimumSize(400, 560)
        self.image_label.zoom_changed.connect(self._on_zoom_changed)

        self.image_label.illustration_pan_changed.connect(self.illustration_pan_changed)
        self.image_label.illustration_scale_changed.connect(self.illustration_scale_changed)

        layout.addWidget(self.image_label)

        # Zoom controls
        controls_layout = QHBoxLayout()

        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setMaximumWidth(30)
        zoom_out_btn.clicked.connect(self.image_label.zoom_out)
        controls_layout.addWidget(zoom_out_btn)

        zoom_reset_btn = QPushButton("100%")
        zoom_reset_btn.setMaximumWidth(50)
        zoom_reset_btn.clicked.connect(self.image_label.reset_zoom)
        controls_layout.addWidget(zoom_reset_btn)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setMaximumWidth(30)
        zoom_in_btn.clicked.connect(self.image_label.zoom_in)
        controls_layout.addWidget(zoom_in_btn)

        controls_layout.addStretch()

        self.zoom_label = QLabel("100%")
        controls_layout.addWidget(self.zoom_label)

        screenshot_btn = QPushButton(tr("BTN_SCREENSHOT"))
        screenshot_btn.setToolTip(tr("TOOLTIP_SCREENSHOT"))
        screenshot_btn.clicked.connect(self._copy_to_clipboard)
        controls_layout.addWidget(screenshot_btn)

        layout.addLayout(controls_layout)
        self.setLayout(layout)

    def _on_zoom_changed(self, factor):
        self.zoom_label.setText(f"{int(factor * 100)}%")

    def _copy_to_clipboard(self):
        pixmap = self.image_label.original_pixmap
        if pixmap:
            QGuiApplication.clipboard().setPixmap(pixmap)

    def set_illustration_mode(self, enabled):
        self.image_label.set_illustration_mode(enabled)

    def set_image(self, image_buffer):
        if not image_buffer:
            return
        data = image_buffer.read()
        image = QImage.fromData(data)
        pixmap = QPixmap.fromImage(image)
        self.image_label.setPixmap(pixmap)
        self.zoom_label.setText("100%")


class ImprovedCardPreview(QWidget):
    """Improved card preview with tabs for front/back and zoom capabilities"""

    illustration_pan_changed = Signal(str, int, int)
    illustration_scale_changed = Signal(str, float)

    def __init__(self):
        super().__init__()

        self.illustration_mode_side = None

        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        self.tabs = QTabWidget()

        self.front_tab = CardPreviewTab("Front")
        self.back_tab = CardPreviewTab("Back")

        self.front_tab.illustration_pan_changed.connect(
            lambda dx, dy: self.illustration_pan_changed.emit('front', dx, dy)
        )
        self.front_tab.illustration_scale_changed.connect(
            lambda d: self.illustration_scale_changed.emit('front', d)
        )
        self.back_tab.illustration_pan_changed.connect(
            lambda dx, dy: self.illustration_pan_changed.emit('back', dx, dy)
        )
        self.back_tab.illustration_scale_changed.connect(
            lambda d: self.illustration_scale_changed.emit('back', d)
        )

        self.tabs.addTab(self.front_tab, tr("TAB_FRONT"))
        self.tabs.addTab(self.back_tab, tr("TAB_BACK"))

        layout.addWidget(self.tabs)
        self.setLayout(layout)

    def set_illustration_mode(self, enabled, side='front'):
        self.front_tab.set_illustration_mode(False)
        self.back_tab.set_illustration_mode(False)

        if enabled:
            self.illustration_mode_side = side
            if side == 'front':
                self.front_tab.set_illustration_mode(True)
                self.tabs.setCurrentIndex(0)
            else:
                self.back_tab.set_illustration_mode(True)
                self.tabs.setCurrentIndex(1)
        else:
            self.illustration_mode_side = None

    def get_illustration_mode(self):
        return self.illustration_mode_side

    def set_card_images(self, front_buffer, back_buffer):
        if front_buffer:
            self.front_tab.set_image(front_buffer)
        if back_buffer:
            self.back_tab.set_image(back_buffer)

    def show_front(self):
        self.tabs.setCurrentIndex(0)

    def show_back(self):
        self.tabs.setCurrentIndex(1)
