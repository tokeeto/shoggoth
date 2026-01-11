"""
Encounter Set Editor widget with thumbnails
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QScrollArea, QFrame, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QSize, QThread
from PySide6.QtGui import QPixmap, QImage, QCursor
import threading
from io import BytesIO


class ThumbnailWidget(QFrame):
    """A clickable thumbnail widget for a card"""
    
    clicked = Signal(str)  # Emits card ID
    
    def __init__(self, card_id, card_name):
        super().__init__()
        self.card_id = card_id
        self.card_name = card_name
        
        # Setup frame
        self.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.setLineWidth(1)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        
        # Layout
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Image label - don't use setScaledContents, we'll handle aspect ratio manually
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumSize(200, 280)
        self.image_label.setText("Loading...")
        layout.addWidget(self.image_label)
        
        # Name label
        name_label = QLabel(card_name)
        name_label.setAlignment(Qt.AlignCenter)
        name_label.setWordWrap(True)
        name_label.setMaximumWidth(200)
        layout.addWidget(name_label)
        
        self.setLayout(layout)
    
    def set_image(self, image_buffer):
        """Set the thumbnail image from a BytesIO buffer with proper aspect ratio"""
        if not image_buffer:
            self.image_label.setText("Error")
            return
        
        try:
            image_buffer.seek(0)
            data = image_buffer.read()
            image = QImage.fromData(data)
            pixmap = QPixmap.fromImage(image)
            
            # Scale pixmap to fit in the label while maintaining aspect ratio
            scaled_pixmap = pixmap.scaled(
                200, 280,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            self.image_label.setPixmap(scaled_pixmap)
            
            # Adjust frame size based on actual image orientation
            if pixmap.width() > pixmap.height():
                # Horizontal card
                self.image_label.setMinimumSize(280, 200)
                self.setMinimumWidth(290)
            else:
                # Vertical card
                self.image_label.setMinimumSize(200, 280)
                self.setMinimumWidth(210)
                
        except Exception as e:
            print(f"Error setting thumbnail: {e}")
            self.image_label.setText("Error")
    
    def mousePressEvent(self, event):
        """Handle mouse click"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.card_id)
        super().mousePressEvent(event)


class ThumbnailGenerator(QThread):
    """Thread for generating thumbnails in the background"""
    
    thumbnail_ready = Signal(str, object)  # card_id, image_buffer
    
    def __init__(self, cards, renderer):
        super().__init__()
        self.cards = cards
        self.renderer = renderer
        self._stop = False
    
    def run(self):
        """Generate thumbnails for all cards"""
        for card in self.cards:
            if self._stop:
                break
            
            try:
                # Generate thumbnail
                thumbnail = self.renderer.get_thumbnail(card)
                # Only emit if we haven't been stopped
                if not self._stop:
                    self.thumbnail_ready.emit(card.id, thumbnail)
            except Exception as e:
                print(f"Error generating thumbnail for {card.name}: {e}")
    
    def stop(self):
        """Stop the thumbnail generation"""
        self._stop = True
        # Don't wait for thread to finish here - parent will call wait() if needed


class EncounterSetEditor(QWidget):
    """Editor for encounter set with thumbnails"""
    
    card_clicked = Signal(object)  # Emits card object when thumbnail is clicked
    
    def __init__(self, encounter_set, renderer):
        super().__init__()
        self.encounter_set = encounter_set
        self.renderer = renderer
        self.thumbnail_widgets = {}
        self.thumbnail_thread = None
        
        self.setup_ui()
        self.load_data()
        self.generate_thumbnails()
    
    def setup_ui(self):
        """Setup the UI"""
        main_layout = QVBoxLayout()
        
        # Header section
        header_layout = QVBoxLayout()
        
        # Title
        title = QLabel(f"Encounter Set: {self.encounter_set.name}")
        title.setStyleSheet("font-size: 20pt; font-weight: bold;")
        header_layout.addWidget(title)
        
        # Basic info form
        from shoggoth.editors import LabeledLineEdit
        
        self.name_input = LabeledLineEdit("Name")
        header_layout.addWidget(self.name_input)
        
        self.code_input = LabeledLineEdit("Code")
        header_layout.addWidget(self.code_input)
        
        self.order_input = LabeledLineEdit("Order")
        header_layout.addWidget(self.order_input)
        
        # Icon selection
        icon_layout = QHBoxLayout()
        icon_layout.addWidget(QLabel("Icon:"))
        self.icon_input = LabeledLineEdit("")
        icon_layout.addWidget(self.icon_input)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_icon)
        icon_layout.addWidget(browse_btn)
        header_layout.addLayout(icon_layout)
        
        # Stats
        stats_label = QLabel()
        stats_label.setStyleSheet("color: #666; font-style: italic;")
        cards_count = len(self.encounter_set.cards)
        total_amount = sum(card.amount for card in self.encounter_set.cards)
        stats_label.setText(f"{cards_count} unique cards, {total_amount} total cards in set")
        header_layout.addWidget(stats_label)
        
        main_layout.addLayout(header_layout)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)
        
        # Cards section label
        cards_label = QLabel("Cards in this set:")
        cards_label.setStyleSheet("font-size: 14pt; font-weight: bold; margin-top: 10px;")
        main_layout.addWidget(cards_label)
        
        # Scroll area for thumbnails
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Thumbnail grid container
        self.thumbnail_container = QWidget()
        self.thumbnail_grid = QGridLayout()
        self.thumbnail_grid.setSpacing(10)
        self.thumbnail_grid.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.thumbnail_container.setLayout(self.thumbnail_grid)
        
        scroll_area.setWidget(self.thumbnail_container)
        main_layout.addWidget(scroll_area)
        
        # Action buttons
        button_layout = QHBoxLayout()
        
        new_card_btn = QPushButton("Add New Card")
        new_card_btn.clicked.connect(self.add_new_card)
        button_layout.addWidget(new_card_btn)
        
        button_layout.addStretch()
        
        delete_btn = QPushButton("Delete Encounter Set")
        delete_btn.setStyleSheet("background-color: #d32f2f; color: white;")
        delete_btn.clicked.connect(self.delete_encounter_set)
        button_layout.addWidget(delete_btn)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
        
        # Setup field bindings
        self.setup_fields()
    
    def setup_fields(self):
        """Setup field bindings"""
        from shoggoth.editors import FieldWidget
        
        self.fields = [
            FieldWidget(self.name_input.input, 'name'),
            FieldWidget(self.code_input.input, 'code'),
            FieldWidget(self.order_input.input, 'order', int, str),
            FieldWidget(self.icon_input.input, 'icon'),
        ]
        
        # Connect signals
        for field in self.fields:
            widget = field.widget
            widget.textChanged.connect(lambda v, f=field: self.on_field_changed(f, v))
    
    def load_data(self):
        """Load encounter set data into fields"""
        for field in self.fields:
            field.update_from_card(self.encounter_set)
    
    def on_field_changed(self, field, value):
        """Handle field changes"""
        field.update_card(self.encounter_set, value)
    
    def browse_icon(self):
        """Browse for icon file"""
        from PySide6.QtWidgets import QFileDialog
        from pathlib import Path
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Icon",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg)"
        )
        if file_path:
            self.icon_input.input.setText(file_path)
    
    def generate_thumbnails(self):
        """Generate thumbnails for all cards in the set"""
        cards = self.encounter_set.cards
        if not cards:
            return
        
        # Create thumbnail widgets
        col = 0
        row = 0
        cols_per_row = 3  # 3 thumbnails per row
        
        for card in cards:
            # Create thumbnail widget
            thumbnail = ThumbnailWidget(card.id, card.name)
            thumbnail.clicked.connect(lambda card_id, c=card: self.on_thumbnail_clicked(c))
            
            # Add to grid
            self.thumbnail_grid.addWidget(thumbnail, row, col)
            self.thumbnail_widgets[card.id] = thumbnail
            
            # Update grid position
            col += 1
            if col >= cols_per_row:
                col = 0
                row += 1
        
        # Start background thumbnail generation
        self.thumbnail_thread = ThumbnailGenerator(cards, self.renderer)
        self.thumbnail_thread.thumbnail_ready.connect(self.on_thumbnail_ready)
        self.thumbnail_thread.start()
    
    def on_thumbnail_ready(self, card_id, image_buffer):
        """Handle thumbnail generation completion"""
        # Only update if the widget still exists
        if card_id in self.thumbnail_widgets:
            self.thumbnail_widgets[card_id].set_image(image_buffer)
    
    def on_thumbnail_clicked(self, card):
        """Handle thumbnail click"""
        self.card_clicked.emit(card)
    
    def add_new_card(self):
        """Add a new card to this encounter set"""
        # Import here to avoid circular imports
        import shoggoth
        shoggoth.app.open_new_card_dialog()
    
    def delete_encounter_set(self):
        """Delete this encounter set"""
        reply = QMessageBox.question(
            self,
            "Delete Encounter Set",
            f"Are you sure you want to delete the encounter set '{self.encounter_set.name}'?\n\n"
            f"This will also delete all {len(self.encounter_set.cards)} cards in this set.\n"
            f"This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # TODO: Implement deletion
            QMessageBox.information(self, "Not Implemented", "Encounter set deletion not yet implemented")
    
    def cleanup(self):
        """Cleanup resources when editor is closed"""
        if self.thumbnail_thread and self.thumbnail_thread.isRunning():
            # Disconnect signal to prevent updates after cleanup
            try:
                self.thumbnail_thread.thumbnail_ready.disconnect(self.on_thumbnail_ready)
            except:
                pass  # Already disconnected
            
            # Stop the thread
            self.thumbnail_thread.stop()
            
            # Wait for it to finish (with timeout)
            self.thumbnail_thread.wait(1000)  # Wait max 1 second
            
            # If still running, terminate it
            if self.thumbnail_thread.isRunning():
                self.thumbnail_thread.terminate()
                self.thumbnail_thread.wait()
            
            self.thumbnail_thread = None
    
    def __del__(self):
        """Destructor - ensure cleanup happens"""
        self.cleanup()