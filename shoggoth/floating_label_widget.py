"""
Floating label widgets - Material Design style inputs
"""
from PySide6.QtWidgets import QWidget, QLineEdit, QTextEdit, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QRect, Property
from PySide6.QtGui import QFont


class FloatingLabelLineEdit(QWidget):
    """LineEdit with floating label that moves up when focused/filled"""
    
    def __init__(self, label_text="", parent=None):
        super().__init__(parent)
        self.label_text = label_text
        
        # Create layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)
        
        # Create label
        self.label = QLabel(label_text)
        self.label.setStyleSheet("""
            QLabel {
                color: #999;
                background: rgba(0,0,0,0);
                padding: 0px 4px;
            }
        """)

        # Position label absolutely
        self.label.setParent(self)
        self.label_font_normal = QFont()
        self.label_font_normal.setPointSize(10)
        self.label_font_small = QFont()
        self.label_font_small.setPointSize(8)

        # Create input
        self.input = QLineEdit()
        self.input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 8px;
                margin-top: 5px;
                background: rgba(0,0,0,0);
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #4CAF50;
                padding: 7px;
            }
        """)
        layout.addWidget(self.input)
        
        # Track state
        self.is_floating = False
        
        # Connect events
        self.input.textChanged.connect(self.on_text_changed)
        self.input.installEventFilter(self)
        
        # Initial position (inside the input)
        self.position_label_inside()
    
    def position_label_inside(self):
        """Position label inside the input field"""
        self.label.setFont(self.label_font_normal)
        self.label.adjustSize()
        self.label.move(12, 24)
        self.label.setStyleSheet("""
            QLabel {
                color: #999;
                background: rgba(0,0,0,0);
                padding: 0px 4px;
            }
        """)
        self.is_floating = False
    
    def position_label_outside(self):
        """Position label above the input field (floating)"""
        self.label.setFont(self.label_font_small)
        self.label.adjustSize()
        self.label.move(8, 0)
        self.label.setStyleSheet("""
            QLabel {
                color: #4CAF50;
                background: rgba(0,0,0,0);
                padding: 0px 4px;
            }
        """)
        self.is_floating = True
    
    def animate_label_float(self):
        """Animate label moving up"""
        if self.is_floating:
            return
        
        # Create animation
        self.anim = QPropertyAnimation(self.label, b"geometry")
        self.anim.setDuration(200)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        
        # Start position (inside)
        start_rect = QRect(12, 24, self.label.width(), self.label.height())
        
        # Change font to small
        self.label.setFont(self.label_font_small)
        self.label.adjustSize()
        
        # End position (outside/above)
        end_rect = QRect(8, 0, self.label.width(), self.label.height())
        
        self.anim.setStartValue(start_rect)
        self.anim.setEndValue(end_rect)
        self.anim.start()
        
        # Update color
        self.label.setStyleSheet("""
            QLabel {
                color: #4CAF50;
                background: rgba(0,0,0,0);
                padding: 0px 4px;
            }
        """)
        self.is_floating = True
    
    def animate_label_sink(self):
        """Animate label moving down"""
        if not self.is_floating or self.input.text():
            return
        
        # Create animation
        self.anim = QPropertyAnimation(self.label, b"geometry")
        self.anim.setDuration(200)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        
        # Start position (outside)
        start_rect = QRect(8, 0, self.label.width(), self.label.height())
        
        # Change font to normal
        self.label.setFont(self.label_font_normal)
        self.label.adjustSize()
        
        # End position (inside)
        end_rect = QRect(12, 24, self.label.width(), self.label.height())
        
        self.anim.setStartValue(start_rect)
        self.anim.setEndValue(end_rect)
        self.anim.start()
        
        # Update color
        self.label.setStyleSheet("""
            QLabel {
                color: #999;
                background: rgba(0,0,0,0);
                padding: 0px 4px;
            }
        """)
        self.is_floating = False
    
    def on_text_changed(self, text):
        """Handle text changes"""
        if text and not self.is_floating:
            self.animate_label_float()
        elif not text and not self.input.hasFocus():
            self.animate_label_sink()
    
    def eventFilter(self, obj, event):
        """Handle focus events"""
        if obj == self.input:
            if event.type() == event.Type.FocusIn:
                self.animate_label_float()
            elif event.type() == event.Type.FocusOut:
                if not self.input.text():
                    self.animate_label_sink()
        return super().eventFilter(obj, event)
    
    def text(self):
        """Get text from input"""
        return self.input.text()
    
    def setText(self, text):
        """Set text in input"""
        self.input.setText(text)
        if text:
            self.position_label_outside()
        else:
            self.position_label_inside()
    
    def setPlaceholderText(self, text):
        """Set placeholder (not used with floating labels)"""
        pass


class FloatingLabelTextEdit(QWidget):
    """TextEdit with floating label that moves up when focused/filled"""
    
    def __init__(self, label_text="", parent=None):
        super().__init__(parent)
        self.label_text = label_text
        
        # Create layout
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)
        
        # Create label
        self.label = QLabel(label_text)
        self.label.setStyleSheet("""
            QLabel {
                color: #999;
                background: transparent;
                padding: 0px 4px;
            }
        """)
        
        # Position label absolutely
        self.label.setParent(self)
        self.label_font_normal = QFont()
        self.label_font_normal.setPointSize(10)
        self.label_font_small = QFont()
        self.label_font_small.setPointSize(8)
        
        # Create input
        self.input = QTextEdit()
        self.input.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 8px;
                margin-top: 5px;
                background-color: rgba(0,0,0,0);
                font-size: 14px;
            }
            QTextEdit:focus {
                border: 2px solid #4CAF50;
                padding: 7px;
            }
        """)
        self.input.setMinimumHeight(100)
        layout.addWidget(self.input)
        
        # Track state
        self.is_floating = False
        
        # Connect events
        self.input.textChanged.connect(self.on_text_changed)
        self.input.installEventFilter(self)
        
        # Initial position (inside the input)
        self.position_label_inside()
    
    def position_label_inside(self):
        """Position label inside the input field"""
        self.label.setFont(self.label_font_normal)
        self.label.adjustSize()
        self.label.move(12, 24)
        self.label.setStyleSheet("""
            QLabel {
                color: #999;
                background: rgba(0,0,0,0);
                padding: 0px 4px;
            }
        """)
        self.is_floating = False
    
    def position_label_outside(self):
        """Position label above the input field (floating)"""
        self.label.setFont(self.label_font_small)
        self.label.adjustSize()
        self.label.move(8, 0)
        self.label.setStyleSheet("""
            QLabel {
                color: #4CAF50;
                background-color: rgba(0,0,0,0);
                padding: 0px 4px;
            }
        """)
        self.is_floating = True
    
    def animate_label_float(self):
        """Animate label moving up"""
        if self.is_floating:
            return
        
        # Create animation
        self.anim = QPropertyAnimation(self.label, b"geometry")
        self.anim.setDuration(200)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        
        # Start position (inside)
        start_rect = QRect(12, 24, self.label.width(), self.label.height())
        
        # Change font to small
        self.label.setFont(self.label_font_small)
        self.label.adjustSize()
        
        # End position (outside/above)
        end_rect = QRect(8, 0, self.label.width(), self.label.height())
        
        self.anim.setStartValue(start_rect)
        self.anim.setEndValue(end_rect)
        self.anim.start()
        
        # Update color
        self.label.setStyleSheet("""
            QLabel {
                color: #4CAF50;
                background-color: rgba(0,0,0,0);
                padding: 0px 4px;
            }
        """)
        self.is_floating = True
    
    def animate_label_sink(self):
        """Animate label moving down"""
        if not self.is_floating or self.input.toPlainText():
            return
        
        # Create animation
        self.anim = QPropertyAnimation(self.label, b"geometry")
        self.anim.setDuration(200)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        
        # Start position (outside)
        start_rect = QRect(8, 0, self.label.width(), self.label.height())
        
        # Change font to normal
        self.label.setFont(self.label_font_normal)
        self.label.adjustSize()
        
        # End position (inside)
        end_rect = QRect(12, 24, self.label.width(), self.label.height())
        
        self.anim.setStartValue(start_rect)
        self.anim.setEndValue(end_rect)
        self.anim.start()
        
        # Update color
        self.label.setStyleSheet("""
            QLabel {
                color: #999;
                background-color: rgba(0,0,0,0);
                padding: 0px 4px;
            }
        """)
        self.is_floating = False
    
    def on_text_changed(self):
        """Handle text changes"""
        text = self.input.toPlainText()
        if text and not self.is_floating:
            self.animate_label_float()
        elif not text and not self.input.hasFocus():
            self.animate_label_sink()
    
    def eventFilter(self, obj, event):
        """Handle focus events"""
        if obj == self.input:
            if event.type() == event.Type.FocusIn:
                self.animate_label_float()
            elif event.type() == event.Type.FocusOut:
                if not self.input.toPlainText():
                    self.animate_label_sink()
        return super().eventFilter(obj, event)
    
    def toPlainText(self):
        """Get text from input"""
        return self.input.toPlainText()
    
    def setPlainText(self, text):
        """Set text in input"""
        self.input.setPlainText(text)
        if text:
            self.position_label_outside()
        else:
            self.position_label_inside()
    
    def setPlaceholderText(self, text):
        """Set placeholder (not used with floating labels)"""
        pass