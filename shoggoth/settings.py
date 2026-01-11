"""
Settings system for Shoggoth using QSettings
"""
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QCheckBox, QLabel,
    QFileDialog, QTabWidget, QWidget, QDialogButtonBox,
    QGroupBox
)
from pathlib import Path


class SettingsManager:
    """Manages application settings using QSettings"""
    
    def __init__(self):
        # QSettings automatically handles platform-specific storage:
        # - Windows: Registry
        # - macOS: plist file
        # - Linux: ~/.config/Shoggoth/Shoggoth.conf
        self.settings = QSettings("Shoggoth", "Shoggoth")
        
        # Set default values if not already set
        self._set_defaults()
    
    def _set_defaults(self):
        """Set default values for settings"""
        defaults = {
            'prince_cmd': 'prince',
            'prince_dir': '',
            'strange_eons': '',
            'java': 'java',
            'show_bleed': True,
        }
        
        for key, value in defaults.items():
            if not self.settings.contains(key):
                self.settings.setValue(key, value)
    
    def get(self, section, key, default=''):
        """
        Get a setting value
        
        Args:
            section: Section name (for compatibility with Kivy config)
            key: Setting key
            default: Default value if not found
        
        Returns:
            Setting value
        """
        # Ignore section for now, just use key
        # This maintains compatibility with old code: config.get('Shoggoth', 'prince_cmd')
        return self.settings.value(key, default)
    
    def getint(self, section, key, default=0):
        """Get setting as integer"""
        value = self.settings.value(key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default
    
    def getboolean(self, section, key, default=False):
        """Get setting as boolean"""
        value = self.settings.value(key, default)
        # QSettings returns strings for some types
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes')
        return bool(value)
    
    def set(self, section, key, value):
        """Set a setting value"""
        self.settings.setValue(key, value)
    
    def save(self):
        """Save settings (QSettings auto-saves, but explicit is good)"""
        self.settings.sync()


class SettingsDialog(QDialog):
    """Settings dialog for configuring Shoggoth"""
    
    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.settings = settings_manager
        self.setWindowTitle("Settings")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        self.setup_ui()
        self.load_settings()
    
    def setup_ui(self):
        """Setup the UI"""
        layout = QVBoxLayout()
        
        # Tab widget for different setting categories
        tabs = QTabWidget()
        
        # External Applications tab
        apps_tab = self.create_apps_tab()
        tabs.addTab(apps_tab, "External Applications")
        
        # Display tab
        display_tab = self.create_display_tab()
        tabs.addTab(display_tab, "Display")
        
        layout.addWidget(tabs)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)
    
    def create_apps_tab(self):
        """Create external applications settings tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Prince XML group
        prince_group = QGroupBox("Prince XML (PDF Generation)")
        prince_layout = QFormLayout()
        
        # Prince command
        prince_cmd_layout = QHBoxLayout()
        self.prince_cmd_input = QLineEdit()
        self.prince_cmd_input.setPlaceholderText("prince")
        prince_cmd_layout.addWidget(self.prince_cmd_input)
        
        prince_cmd_label = QLabel("Command to run Prince")
        prince_layout.addRow("Prince Command:", prince_cmd_layout)
        prince_layout.addRow("", QLabel("e.g., 'prince' or '/usr/local/bin/prince'"))
        
        # Prince directory
        prince_dir_layout = QHBoxLayout()
        self.prince_dir_input = QLineEdit()
        self.prince_dir_input.setPlaceholderText("Leave empty for system-wide installation")
        prince_dir_layout.addWidget(self.prince_dir_input)
        
        browse_prince_btn = QPushButton("Browse")
        browse_prince_btn.clicked.connect(self.browse_prince_dir)
        prince_dir_layout.addWidget(browse_prince_btn)
        
        prince_layout.addRow("Prince Directory:", prince_dir_layout)
        prince_layout.addRow("", QLabel("Only needed if Prince is not installed system-wide"))
        
        prince_group.setLayout(prince_layout)
        layout.addWidget(prince_group)
        
        # Strange Eons group
        se_group = QGroupBox("Strange Eons (Import)")
        se_layout = QFormLayout()
        
        # Strange Eons JAR
        se_jar_layout = QHBoxLayout()
        self.se_jar_input = QLineEdit()
        self.se_jar_input.setPlaceholderText("Path to strange-eons.jar")
        se_jar_layout.addWidget(self.se_jar_input)
        
        browse_se_btn = QPushButton("Browse")
        browse_se_btn.clicked.connect(self.browse_se_jar)
        se_jar_layout.addWidget(browse_se_btn)
        
        se_layout.addRow("Strange Eons JAR:", se_jar_layout)
        se_layout.addRow("", QLabel("For importing Strange Eons projects"))
        
        # Java command
        java_cmd_layout = QHBoxLayout()
        self.java_cmd_input = QLineEdit()
        self.java_cmd_input.setPlaceholderText("java")
        java_cmd_layout.addWidget(self.java_cmd_input)
        
        se_layout.addRow("Java Command:", java_cmd_layout)
        se_layout.addRow("", QLabel("e.g., 'java' or path to Java 11"))
        
        se_group.setLayout(se_layout)
        layout.addWidget(se_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def create_display_tab(self):
        """Create display settings tab"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Preview group
        preview_group = QGroupBox("Preview Settings")
        preview_layout = QFormLayout()
        
        # Show bleed checkbox
        self.show_bleed_checkbox = QCheckBox("Show bleed area in preview")
        self.show_bleed_checkbox.setToolTip(
            "The bleed area is the margin for error in cutting/printing"
        )
        preview_layout.addRow("Bleed Display:", self.show_bleed_checkbox)
        
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def browse_prince_dir(self):
        """Browse for Prince directory"""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Prince Directory",
            str(Path.home())
        )
        if directory:
            self.prince_dir_input.setText(directory)
    
    def browse_se_jar(self):
        """Browse for Strange Eons JAR file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Strange Eons JAR",
            str(Path.home()),
            "JAR Files (*.jar);;All Files (*)"
        )
        if file_path:
            self.se_jar_input.setText(file_path)
    
    def load_settings(self):
        """Load current settings into the dialog"""
        self.prince_cmd_input.setText(
            self.settings.get('Shoggoth', 'prince_cmd', 'prince')
        )
        self.prince_dir_input.setText(
            self.settings.get('Shoggoth', 'prince_dir', '')
        )
        self.se_jar_input.setText(
            self.settings.get('Shoggoth', 'strange_eons', '')
        )
        self.java_cmd_input.setText(
            self.settings.get('Shoggoth', 'java', 'java')
        )
        self.show_bleed_checkbox.setChecked(
            self.settings.getboolean('Shoggoth', 'show_bleed', True)
        )
    
    def save_settings(self):
        """Save settings and close dialog"""
        self.settings.set('Shoggoth', 'prince_cmd', self.prince_cmd_input.text())
        self.settings.set('Shoggoth', 'prince_dir', self.prince_dir_input.text())
        self.settings.set('Shoggoth', 'strange_eons', self.se_jar_input.text())
        self.settings.set('Shoggoth', 'java', self.java_cmd_input.text())
        self.settings.set('Shoggoth', 'show_bleed', self.show_bleed_checkbox.isChecked())
        
        self.settings.save()
        self.accept()