"""
Improved card preview widget with zoom, pan, and tabs
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QLabel, QScrollArea,
    QSizePolicy
)
from PySide6.QtCore import Qt, QPoint, QSize
from PySide6.QtGui import QPixmap, QImage, QWheelEvent, QMouseEvent, QPainter


class ZoomableImageLabel(QLabel):
    """A label that displays an image with zoom and pan capabilities"""
    
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.setScaledContents(False)  # We'll handle scaling ourselves
        
        # Zoom and pan state
        self.zoom_factor = 1.0
        self.min_zoom = 0.1
        self.max_zoom = 5.0
        self.zoom_step = 0.1
        
        # For panning
        self.panning = False
        self.pan_start_pos = QPoint()
        self.current_offset = QPoint(0, 0)
        
        # Original pixmap
        self.original_pixmap = None
        
        # Enable mouse tracking for panning
        self.setMouseTracking(True)
    
    def setPixmap(self, pixmap):
        """Set the pixmap and reset zoom/pan"""
        self.original_pixmap = pixmap
        self.zoom_factor = 1.0
        self.current_offset = QPoint(0, 0)
        self.update_display()
    
    def update_display(self):
        """Update the displayed image with current zoom and pan"""
        if not self.original_pixmap:
            super().setPixmap(QPixmap())
            return
        
        # Calculate scaled size preserving aspect ratio
        original_size = self.original_pixmap.size()
        available_size = self.size()
        
        # Fit to widget size first
        scaled_size = original_size.scaled(
            available_size,
            Qt.KeepAspectRatio
        )
        
        # Apply zoom
        final_width = int(scaled_size.width() * self.zoom_factor)
        final_height = int(scaled_size.height() * self.zoom_factor)
        
        # Scale the pixmap
        scaled_pixmap = self.original_pixmap.scaled(
            final_width,
            final_height,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
        super().setPixmap(scaled_pixmap)
    
    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse wheel for zooming"""
        if not self.original_pixmap:
            return
        
        # Get wheel delta
        delta = event.angleDelta().y()
        
        # Calculate new zoom factor
        if delta > 0:
            new_zoom = self.zoom_factor + self.zoom_step
        else:
            new_zoom = self.zoom_factor - self.zoom_step
        
        # Clamp zoom factor
        new_zoom = max(self.min_zoom, min(self.max_zoom, new_zoom))
        
        if new_zoom != self.zoom_factor:
            self.zoom_factor = new_zoom
            self.update_display()
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press for panning"""
        if event.button() == Qt.MiddleButton or (event.button() == Qt.LeftButton and event.modifiers() & Qt.ControlModifier):
            self.panning = True
            self.pan_start_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
    
    def mouseReleaseEvent(self, event: QMouseEvent):
        """Handle mouse release"""
        if event.button() == Qt.MiddleButton or event.button() == Qt.LeftButton:
            self.panning = False
            self.setCursor(Qt.ArrowCursor)
    
    def mouseMoveEvent(self, event: QMouseEvent):
        """Handle mouse move for panning"""
        if self.panning:
            delta = event.pos() - self.pan_start_pos
            self.current_offset += delta
            self.pan_start_pos = event.pos()
            # Note: For true panning, we'd need to use QGraphicsView
            # For now, zoom is the main feature
    
    def resizeEvent(self, event):
        """Handle resize to update display"""
        super().resizeEvent(event)
        if self.original_pixmap:
            self.update_display()
    
    def reset_zoom(self):
        """Reset zoom to 100%"""
        self.zoom_factor = 1.0
        self.current_offset = QPoint(0, 0)
        self.update_display()
    
    def zoom_in(self):
        """Zoom in"""
        self.zoom_factor = min(self.max_zoom, self.zoom_factor + self.zoom_step)
        self.update_display()
    
    def zoom_out(self):
        """Zoom out"""
        self.zoom_factor = max(self.min_zoom, self.zoom_factor - self.zoom_step)
        self.update_display()
    
    def fit_to_window(self):
        """Fit image to window"""
        self.zoom_factor = 1.0
        self.current_offset = QPoint(0, 0)
        self.update_display()


class CardPreviewTab(QWidget):
    """A single tab for card preview with zoom controls"""
    
    def __init__(self, title):
        super().__init__()
        self.title = title
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Create scroll area for the image
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Create zoomable image label
        self.image_label = ZoomableImageLabel()
        self.image_label.setMinimumSize(400, 560)
        
        scroll_area.setWidget(self.image_label)
        layout.addWidget(scroll_area)
        
        # Zoom controls
        from PySide6.QtWidgets import QHBoxLayout, QPushButton, QLabel as QLabeln
        controls_layout = QHBoxLayout()
        
        zoom_out_btn = QPushButton("−")
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
        
        self.zoom_label = QLabeln("100%")
        controls_layout.addWidget(self.zoom_label)
        
        layout.addLayout(controls_layout)
        
        self.setLayout(layout)
    
    def set_image(self, image_buffer):
        """Set the image from a BytesIO buffer"""
        if not image_buffer:
            return
        
        image_buffer.seek(0)
        data = image_buffer.read()
        image = QImage.fromData(data)
        pixmap = QPixmap.fromImage(image)
        self.image_label.setPixmap(pixmap)
        self.update_zoom_label()
    
    def update_zoom_label(self):
        """Update the zoom percentage label"""
        zoom_percent = int(self.image_label.zoom_factor * 100)
        self.zoom_label.setText(f"{zoom_percent}%")


class ImprovedCardPreview(QWidget):
    """Improved card preview with tabs for front/back and zoom capabilities"""
    
    def __init__(self):
        super().__init__()
        
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Create tab widget
        self.tabs = QTabWidget()
        
        # Create front and back tabs
        self.front_tab = CardPreviewTab("Front")
        self.back_tab = CardPreviewTab("Back")
        
        self.tabs.addTab(self.front_tab, "Front")
        self.tabs.addTab(self.back_tab, "Back")
        
        layout.addWidget(self.tabs)
        
        self.setLayout(layout)
    
    def set_card_images(self, front_buffer, back_buffer):
        """Set the front and back card images from BytesIO buffers"""
        if front_buffer:
            self.front_tab.set_image(front_buffer)
        
        if back_buffer:
            self.back_tab.set_image(back_buffer)
    
    def show_front(self):
        """Switch to front tab"""
        self.tabs.setCurrentIndex(0)
    
    def show_back(self):
        """Switch to back tab"""
        self.tabs.setCurrentIndex(1)