"""
Guide Editor with HTML syntax highlighting and PDF preview
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSpinBox, QTextEdit, QSplitter, QFileDialog, QScrollArea,
    QFrame, QToolBar, QComboBox
)
from PySide6.QtCore import Qt, Signal, QThread, QTimer
from PySide6.QtGui import (
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont,
    QPixmap, QImage, QPainter, QTransform
)
import re
from pathlib import Path


class HTMLHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for HTML"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Define highlighting rules
        self.highlighting_rules = []
        
        # HTML tags
        tag_format = QTextCharFormat()
        tag_format.setForeground(QColor("#0000ff"))  # Blue
        tag_format.setFontWeight(QFont.Bold)
        tag_patterns = [
            r'<[^>]+>',  # Any tag
        ]
        for pattern in tag_patterns:
            self.highlighting_rules.append((re.compile(pattern), tag_format))
        
        # Attributes
        attr_format = QTextCharFormat()
        attr_format.setForeground(QColor("#ff0000"))  # Red
        self.highlighting_rules.append((
            re.compile(r'\b\w+(?=\s*=)'), attr_format
        ))
        
        # Attribute values (in quotes)
        value_format = QTextCharFormat()
        value_format.setForeground(QColor("#008000"))  # Green
        self.highlighting_rules.append((
            re.compile(r'"[^"]*"'), value_format
        ))
        self.highlighting_rules.append((
            re.compile(r"'[^']*'"), value_format
        ))
        
        # Comments
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#808080"))  # Gray
        comment_format.setFontItalic(True)
        self.highlighting_rules.append((
            re.compile(r'<!--.*?-->'), comment_format
        ))
        
        # DOCTYPE
        doctype_format = QTextCharFormat()
        doctype_format.setForeground(QColor("#800080"))  # Purple
        doctype_format.setFontWeight(QFont.Bold)
        self.highlighting_rules.append((
            re.compile(r'<!DOCTYPE[^>]*>', re.IGNORECASE), doctype_format
        ))
        
        # CSS in style tags
        css_format = QTextCharFormat()
        css_format.setForeground(QColor("#804000"))  # Brown
        self.highlighting_rules.append((
            re.compile(r'(?<=<style>).*?(?=</style>)', re.DOTALL), css_format
        ))
    
    def highlightBlock(self, text):
        """Apply syntax highlighting to a block of text"""
        for pattern, format in self.highlighting_rules:
            for match in pattern.finditer(text):
                start = match.start()
                length = match.end() - start
                self.setFormat(start, length, format)


class PDFPageRenderer(QThread):
    """Thread for rendering PDF pages to images"""
    
    page_ready = Signal(int, object)  # page_number, QPixmap
    
    def __init__(self, guide, page_number, html=None):
        super().__init__()
        self.guide = guide
        self.page_number = page_number
        self.html = html
        self._stop = False
    
    def run(self):
        """Render the PDF page"""
        if self._stop:
            return
        
        try:
            # Get page image from guide
            image_buffer = self.guide.get_page(self.page_number, html=self.html)
            
            if self._stop:
                return
            
            # Convert to QPixmap
            image_buffer.seek(0)
            data = image_buffer.read()
            qimage = QImage.fromData(data)
            pixmap = QPixmap.fromImage(qimage)
            
            if not self._stop:
                self.page_ready.emit(self.page_number, pixmap)
        except Exception as e:
            print(f"Error rendering page {self.page_number}: {e}")
    
    def stop(self):
        """Stop rendering"""
        self._stop = True


class ZoomablePDFViewer(QFrame):
    """PDF viewer with zoom and pan controls"""
    
    def __init__(self):
        super().__init__()
        self.pixmap = None
        self.zoom_level = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self._panning = False
        self._last_pos = None
        
        self.setFrameStyle(QFrame.Box | QFrame.Sunken)
        self.setMinimumSize(400, 600)
        
        # Enable mouse tracking for panning
        self.setMouseTracking(True)
    
    def set_pixmap(self, pixmap):
        """Set the PDF page pixmap"""
        self.pixmap = pixmap
        self.update()
    
    def paintEvent(self, event):
        """Paint the PDF page with zoom and pan"""
        super().paintEvent(event)
        
        if not self.pixmap:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        # Apply zoom
        scaled_pixmap = self.pixmap.scaled(
            int(self.pixmap.width() * self.zoom_level),
            int(self.pixmap.height() * self.zoom_level),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        
        # Calculate position (centered + pan offset)
        x = (self.width() - scaled_pixmap.width()) // 2 + self.pan_x
        y = (self.height() - scaled_pixmap.height()) // 2 + self.pan_y
        
        # Draw pixmap
        painter.drawPixmap(x, y, scaled_pixmap)
    
    def wheelEvent(self, event):
        """Handle mouse wheel for zooming"""
        delta = event.angleDelta().y()
        
        if delta > 0:
            # Zoom in
            self.zoom_level = min(self.zoom_level * 1.1, 5.0)
        else:
            # Zoom out
            self.zoom_level = max(self.zoom_level / 1.1, 0.1)
        
        self.update()
    
    def mousePressEvent(self, event):
        """Start panning"""
        if event.button() == Qt.LeftButton:
            self._panning = True
            self._last_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
    
    def mouseMoveEvent(self, event):
        """Handle panning"""
        if self._panning and self._last_pos:
            delta = event.pos() - self._last_pos
            self.pan_x += delta.x()
            self.pan_y += delta.y()
            self._last_pos = event.pos()
            self.update()
    
    def mouseReleaseEvent(self, event):
        """Stop panning"""
        if event.button() == Qt.LeftButton:
            self._panning = False
            self._last_pos = None
            self.setCursor(Qt.ArrowCursor)
    
    def reset_view(self):
        """Reset zoom and pan"""
        self.zoom_level = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.update()


class GuideEditor(QWidget):
    """Editor for campaign guides with HTML editing and PDF preview"""
    
    def __init__(self, guide):
        super().__init__()
        self.guide = guide
        self.current_page = 1
        self.total_pages = 1  # Will be updated
        self.render_thread = None
        self.render_timer = None
        
        self.setup_ui()
        self.load_data()
    
    def setup_ui(self):
        """Setup the UI"""
        # Main layout - splitter for editor and preview
        main_splitter = QSplitter(Qt.Horizontal)
        
        # Left side - Editor
        editor_widget = QWidget()
        editor_layout = QVBoxLayout()
        
        # Title
        title = QLabel(f"Guide: {self.guide.name}")
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        editor_layout.addWidget(title)
        
        # Front page image
        front_page_layout = QHBoxLayout()
        front_page_layout.addWidget(QLabel("Front Page Image:"))
        self.front_page_input = QTextEdit()
        self.front_page_input.setMaximumHeight(30)
        self.front_page_input.setPlainText(self.guide.front_page)
        self.front_page_input.textChanged.connect(self.on_front_page_changed)
        front_page_layout.addWidget(self.front_page_input)
        
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self.browse_front_page)
        front_page_layout.addWidget(browse_btn)
        editor_layout.addLayout(front_page_layout)
        
        # HTML editor
        html_label = QLabel("HTML Content:")
        html_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        editor_layout.addWidget(html_label)
        
        self.html_editor = QTextEdit()
        self.html_editor.setAcceptRichText(False)
        self.html_editor.setLineWrapMode(QTextEdit.NoWrap)
        self.html_editor.setFont(QFont("Courier", 10))
        
        # Apply syntax highlighting
        self.highlighter = HTMLHighlighter(self.html_editor.document())
        
        # Debounced text change
        self.html_editor.textChanged.connect(self.on_html_changed)
        
        editor_layout.addWidget(self.html_editor)
        
        # Action buttons
        button_layout = QHBoxLayout()
        
        export_btn = QPushButton("Export PDF")
        export_btn.clicked.connect(self.export_pdf)
        button_layout.addWidget(export_btn)
        
        button_layout.addStretch()
        
        editor_layout.addLayout(button_layout)
        
        editor_widget.setLayout(editor_layout)
        main_splitter.addWidget(editor_widget)
        
        # Right side - PDF Preview (detachable would be via dock widget in main window)
        preview_widget = QWidget()
        preview_layout = QVBoxLayout()
        
        # Preview title
        preview_title = QLabel("Preview")
        preview_title.setStyleSheet("font-size: 14pt; font-weight: bold;")
        preview_layout.addWidget(preview_title)
        
        # Zoom controls
        zoom_toolbar = QHBoxLayout()
        
        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setMaximumWidth(40)
        zoom_out_btn.clicked.connect(self.zoom_out)
        zoom_toolbar.addWidget(zoom_out_btn)
        
        zoom_reset_btn = QPushButton("100%")
        zoom_reset_btn.setMaximumWidth(60)
        zoom_reset_btn.clicked.connect(self.reset_zoom)
        zoom_toolbar.addWidget(zoom_reset_btn)
        
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setMaximumWidth(40)
        zoom_in_btn.clicked.connect(self.zoom_in)
        zoom_toolbar.addWidget(zoom_in_btn)
        
        zoom_toolbar.addStretch()
        preview_layout.addLayout(zoom_toolbar)
        
        # PDF viewer
        self.pdf_viewer = ZoomablePDFViewer()
        preview_layout.addWidget(self.pdf_viewer)
        
        # Page controls
        page_controls = QHBoxLayout()
        
        prev_btn = QPushButton("◀ Previous")
        prev_btn.clicked.connect(self.previous_page)
        page_controls.addWidget(prev_btn)
        
        page_controls.addStretch()
        
        page_controls.addWidget(QLabel("Page:"))
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(999)
        self.page_spin.setValue(1)
        self.page_spin.valueChanged.connect(self.on_page_changed)
        page_controls.addWidget(self.page_spin)
        
        self.page_label = QLabel("of ?")
        page_controls.addWidget(self.page_label)
        
        page_controls.addStretch()
        
        next_btn = QPushButton("Next ▶")
        next_btn.clicked.connect(self.next_page)
        page_controls.addWidget(next_btn)
        
        preview_layout.addLayout(page_controls)
        
        preview_widget.setLayout(preview_layout)
        main_splitter.addWidget(preview_widget)
        
        # Set splitter sizes (50/50)
        main_splitter.setSizes([500, 500])
        
        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(main_splitter)
        self.setLayout(main_layout)
    
    def load_data(self):
        """Load guide data"""
        # Load HTML
        html = self.guide.get_html()
        self.html_editor.setPlainText(html)
        
        # Render first page
        self.render_page(1)
    
    def on_front_page_changed(self):
        """Handle front page path change"""
        self.guide.front_page = self.front_page_input.toPlainText()
    
    def browse_front_page(self):
        """Browse for front page image"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Front Page Image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp)"
        )
        if file_path:
            self.front_page_input.setPlainText(file_path)
    
    def on_html_changed(self):
        """Handle HTML content change (debounced)"""
        # Cancel previous timer
        if self.render_timer:
            self.render_timer.stop()
        
        # Start new timer (1 second delay)
        self.render_timer = QTimer()
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(lambda: self.render_page(self.current_page))
        self.render_timer.start(1000)
    
    def render_page(self, page_number):
        """Render a PDF page"""
        # Stop any existing render
        if self.render_thread and self.render_thread.isRunning():
            self.render_thread.stop()
            self.render_thread.wait(500)
        
        # Get current HTML
        html = self.html_editor.toPlainText()
        
        # Start new render thread
        self.render_thread = PDFPageRenderer(self.guide, page_number, html)
        self.render_thread.page_ready.connect(self.on_page_rendered)
        self.render_thread.start()
    
    def on_page_rendered(self, page_number, pixmap):
        """Handle page render completion"""
        if page_number == self.current_page:
            self.pdf_viewer.set_pixmap(pixmap)
    
    def on_page_changed(self, page_number):
        """Handle page number change"""
        self.current_page = page_number
        self.render_page(page_number)
    
    def previous_page(self):
        """Go to previous page"""
        if self.current_page > 1:
            self.page_spin.setValue(self.current_page - 1)
    
    def next_page(self):
        """Go to next page"""
        self.page_spin.setValue(self.current_page + 1)
    
    def zoom_in(self):
        """Zoom in"""
        self.pdf_viewer.zoom_level = min(self.pdf_viewer.zoom_level * 1.2, 5.0)
        self.pdf_viewer.update()
    
    def zoom_out(self):
        """Zoom out"""
        self.pdf_viewer.zoom_level = max(self.pdf_viewer.zoom_level / 1.2, 0.1)
        self.pdf_viewer.update()
    
    def reset_zoom(self):
        """Reset zoom to 100%"""
        self.pdf_viewer.reset_view()
    
    def export_pdf(self):
        """Export guide to PDF file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export PDF",
            str(Path(self.guide.path).parent / "guide.pdf"),
            "PDF Files (*.pdf)"
        )
        
        if file_path:
            # Render to file
            self.guide.render_to_file()
            
            # Copy to selected location if different
            import shutil
            if str(file_path) != str(self.guide.target_path):
                shutil.copy(self.guide.target_path, file_path)
            
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Export Complete", f"PDF exported to:\n{file_path}")
    
    def cleanup(self):
        """Cleanup resources"""
        if self.render_thread and self.render_thread.isRunning():
            self.render_thread.stop()
            self.render_thread.wait(1000)
            if self.render_thread.isRunning():
                self.render_thread.terminate()
                self.render_thread.wait()
        
        if self.render_timer:
            self.render_timer.stop()