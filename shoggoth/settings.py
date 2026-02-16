"""
Settings system for Shoggoth using QSettings
"""
from PySide6.QtCore import QSettings, QLocale
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QCheckBox, QLabel,
    QFileDialog, QTabWidget, QWidget, QDialogButtonBox,
    QGroupBox, QComboBox, QSpinBox
)
from pathlib import Path
from shoggoth.i18n import tr, get_available_languages


def detect_system_language() -> str:
    """
    Detect the system language and return the language code if available.
    
    Returns:
        Language code (e.g., 'es', 'en') or 'en' as fallback.
    """
    try:
        # Get system locale using Qt
        system_locale = QLocale.system()
        # Get the language code (e.g., 'es', 'en', 'fr')
        lang_code = system_locale.name().split('_')[0].lower()
        
        # Check if this language is available in our translations
        available = get_available_languages()
        if lang_code in available:
            return lang_code
        
        # Fallback to English
        return 'en'
    except Exception:
        # Any error, fallback to English
        return 'en'


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
            # Export settings
            'export_format': 'png',
            'export_quality': 95,
            'export_bleed': True,
            'export_separate_versions': False,
            # Update settings
            'auto_check_updates': True,
            'skipped_version': '',
            # Language settings - detect from system
            'language': detect_system_language(),
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
        self.setWindowTitle(tr("DLG_SETTINGS"))
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
        tabs.addTab(apps_tab, tr("TAB_EXTERNAL_APPS"))

        # Display tab
        display_tab = self.create_display_tab()
        tabs.addTab(display_tab, tr("TAB_DISPLAY"))

        # Export tab
        export_tab = self.create_export_tab()
        tabs.addTab(export_tab, tr("TAB_EXPORT"))

        # Updates tab
        updates_tab = self.create_updates_tab()
        tabs.addTab(updates_tab, tr("TAB_UPDATES"))

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
        prince_group = QGroupBox(tr("GROUP_PRINCE_XML"))
        prince_layout = QFormLayout()
        
        # Prince command
        prince_cmd_layout = QHBoxLayout()
        self.prince_cmd_input = QLineEdit()
        self.prince_cmd_input.setPlaceholderText(tr("PLACEHOLDER_PRINCE"))
        prince_cmd_layout.addWidget(self.prince_cmd_input)
        
        prince_cmd_label = QLabel(tr("HELP_PRINCE_COMMAND"))
        prince_layout.addRow(tr("LABEL_PRINCE_COMMAND"), prince_cmd_layout)
        prince_layout.addRow("", QLabel(tr("EXAMPLE_PRINCE_PATH")))
        
        # Prince directory
        prince_dir_layout = QHBoxLayout()
        self.prince_dir_input = QLineEdit()
        self.prince_dir_input.setPlaceholderText(tr("PLACEHOLDER_PRINCE_DIR"))
        prince_dir_layout.addWidget(self.prince_dir_input)
        
        browse_prince_btn = QPushButton(tr("BTN_BROWSE"))
        browse_prince_btn.clicked.connect(self.browse_prince_dir)
        prince_dir_layout.addWidget(browse_prince_btn)
        
        prince_layout.addRow(tr("LABEL_PRINCE_DIRECTORY"), prince_dir_layout)
        prince_layout.addRow("", QLabel(tr("HELP_PRINCE_DIRECTORY")))
        
        prince_group.setLayout(prince_layout)
        layout.addWidget(prince_group)
        
        # Strange Eons group
        se_group = QGroupBox(tr("GROUP_STRANGE_EONS"))
        se_layout = QFormLayout()
        
        # Strange Eons JAR
        se_jar_layout = QHBoxLayout()
        self.se_jar_input = QLineEdit()
        self.se_jar_input.setPlaceholderText(tr("PLACEHOLDER_SE_JAR"))
        se_jar_layout.addWidget(self.se_jar_input)
        
        browse_se_btn = QPushButton(tr("BTN_BROWSE"))
        browse_se_btn.clicked.connect(self.browse_se_jar)
        se_jar_layout.addWidget(browse_se_btn)
        
        se_layout.addRow(tr("LABEL_SE_JAR"), se_jar_layout)
        se_layout.addRow("", QLabel(tr("HELP_SE_JAR")))
        
        # Java command
        java_cmd_layout = QHBoxLayout()
        self.java_cmd_input = QLineEdit()
        self.java_cmd_input.setPlaceholderText(tr("PLACEHOLDER_JAVA"))
        java_cmd_layout.addWidget(self.java_cmd_input)
        
        se_layout.addRow(tr("LABEL_JAVA_COMMAND"), java_cmd_layout)
        se_layout.addRow("", QLabel(tr("EXAMPLE_JAVA_PATH")))
        
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
        preview_group = QGroupBox(tr("GROUP_PREVIEW_SETTINGS"))
        preview_layout = QFormLayout()

        # Show bleed checkbox
        self.show_bleed_checkbox = QCheckBox(tr("OPT_SHOW_BLEED"))
        self.show_bleed_checkbox.setToolTip(
            tr("HELP_BLEED_AREA")
        )
        preview_layout.addRow(tr("LABEL_BLEED_DISPLAY"), self.show_bleed_checkbox)

        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_export_tab(self):
        """Create export settings tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Format group
        format_group = QGroupBox(tr("GROUP_EXPORT_FORMAT"))
        format_layout = QFormLayout()

        # Format dropdown
        self.export_format_combo = QComboBox()
        self.export_format_combo.addItems(['png', 'jpeg', 'webp'])
        self.export_format_combo.setToolTip(
            tr("HELP_FORMAT_OPTIONS")
        )
        self.export_format_combo.currentTextChanged.connect(self._on_format_changed)
        format_layout.addRow(tr("LABEL_FORMAT"), self.export_format_combo)

        # Quality spinbox
        quality_layout = QHBoxLayout()
        self.export_quality_spin = QSpinBox()
        self.export_quality_spin.setRange(1, 100)
        self.export_quality_spin.setValue(95)
        self.export_quality_spin.setSuffix("%")
        self.export_quality_spin.setToolTip(
            tr("HELP_QUALITY")
        )
        quality_layout.addWidget(self.export_quality_spin)
        quality_layout.addStretch()
        format_layout.addRow(tr("LABEL_QUALITY"), quality_layout)

        format_group.setLayout(format_layout)
        layout.addWidget(format_group)

        # Options group
        options_group = QGroupBox(tr("GROUP_EXPORT_OPTIONS"))
        options_layout = QFormLayout()

        # Include bleed checkbox
        self.export_bleed_checkbox = QCheckBox(tr("OPT_INCLUDE_BLEED"))
        self.export_bleed_checkbox.setToolTip(
            tr("HELP_INCLUDE_BLEED")
        )
        options_layout.addRow(tr("LABEL_INCLUDE_BLEED"), self.export_bleed_checkbox)

        # Separate versions checkbox
        self.export_separate_versions_checkbox = QCheckBox(tr("OPT_SEPARATE_VERSIONS"))
        self.export_separate_versions_checkbox.setToolTip(
            tr("HELP_SEPARATE_VERSIONS")
        )
        options_layout.addRow(tr("LABEL_SEPARATE_VERSIONS"), self.export_separate_versions_checkbox)

        options_group.setLayout(options_layout)
        layout.addWidget(options_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def create_updates_tab(self):
        """Create updates settings tab"""
        widget = QWidget()
        layout = QVBoxLayout()

        # Auto-update group
        update_group = QGroupBox(tr("GROUP_AUTO_UPDATES"))
        update_layout = QFormLayout()

        # Auto-check checkbox
        self.auto_check_updates_checkbox = QCheckBox(tr("OPT_CHECK_UPDATES_STARTUP"))
        self.auto_check_updates_checkbox.setToolTip(
            tr("HELP_AUTO_CHECK")
        )
        update_layout.addRow(tr("LABEL_AUTO_CHECK"), self.auto_check_updates_checkbox)

        # Current version display
        from shoggoth.updater import get_current_version, detect_installation_type
        version_text = get_current_version()
        install_type = detect_installation_type()
        version_label = QLabel(f"{version_text} ({install_type.value})")
        version_label.setStyleSheet("color: #666;")
        update_layout.addRow(tr("LABEL_CURRENT_VERSION"), version_label)

        # Manual check button
        check_now_btn = QPushButton(tr("BTN_CHECK_UPDATES_NOW"))
        check_now_btn.clicked.connect(self._check_for_updates_now)
        update_layout.addRow("", check_now_btn)

        update_group.setLayout(update_layout)
        layout.addWidget(update_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _check_for_updates_now(self):
        """Trigger manual update check from settings"""
        import shoggoth
        if hasattr(shoggoth, 'app') and shoggoth.app:
            if hasattr(shoggoth.app, 'update_manager'):
                shoggoth.app.update_manager.check_for_updates_manual()

    def _on_format_changed(self, format_text):
        """Handle format change - enable/disable quality based on format"""
        # PNG is lossless, so quality doesn't apply
        is_lossy = format_text.lower() in ('jpeg', 'webp')
        self.export_quality_spin.setEnabled(is_lossy)
    
    def browse_prince_dir(self):
        """Browse for Prince directory"""
        directory = QFileDialog.getExistingDirectory(
            self,
            tr("DLG_SELECT_PRINCE_DIR"),
            str(Path.home())
        )
        if directory:
            self.prince_dir_input.setText(directory)
    
    def browse_se_jar(self):
        """Browse for Strange Eons JAR file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("DLG_SELECT_SE_JAR"),
            str(Path.home()),
            tr("FILTER_JAR_FILES")
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

        # Export settings
        export_format = self.settings.get('Shoggoth', 'export_format', 'png')
        index = self.export_format_combo.findText(export_format)
        if index >= 0:
            self.export_format_combo.setCurrentIndex(index)
        self._on_format_changed(export_format)  # Update quality spinbox state

        self.export_quality_spin.setValue(
            self.settings.getint('Shoggoth', 'export_quality', 95)
        )
        self.export_bleed_checkbox.setChecked(
            self.settings.getboolean('Shoggoth', 'export_bleed', True)
        )
        self.export_separate_versions_checkbox.setChecked(
            self.settings.getboolean('Shoggoth', 'export_separate_versions', False)
        )

        # Update settings
        self.auto_check_updates_checkbox.setChecked(
            self.settings.getboolean('Shoggoth', 'auto_check_updates', True)
        )

    def save_settings(self):
        """Save settings and close dialog"""
        self.settings.set('Shoggoth', 'prince_cmd', self.prince_cmd_input.text())
        self.settings.set('Shoggoth', 'prince_dir', self.prince_dir_input.text())
        self.settings.set('Shoggoth', 'strange_eons', self.se_jar_input.text())
        self.settings.set('Shoggoth', 'java', self.java_cmd_input.text())
        self.settings.set('Shoggoth', 'show_bleed', self.show_bleed_checkbox.isChecked())

        # Export settings
        self.settings.set('Shoggoth', 'export_format', self.export_format_combo.currentText())
        self.settings.set('Shoggoth', 'export_quality', self.export_quality_spin.value())
        self.settings.set('Shoggoth', 'export_bleed', self.export_bleed_checkbox.isChecked())
        self.settings.set('Shoggoth', 'export_separate_versions', self.export_separate_versions_checkbox.isChecked())

        # Update settings
        self.settings.set('Shoggoth', 'auto_check_updates', self.auto_check_updates_checkbox.isChecked())

        self.settings.save()
        self.accept()