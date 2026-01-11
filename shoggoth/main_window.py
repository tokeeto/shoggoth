"""
Main window implementation for Shoggoth using PySide6
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QLabel, QMenuBar, QMenu,
    QFileDialog, QMessageBox, QStatusBar, QScrollArea, QDialog,
    QLineEdit, QPushButton, QDialogButtonBox
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QPixmap, QAction, QImage, QKeySequence, QShortcut, QIcon
from pathlib import Path
import json
from io import BytesIO

import shoggoth
from shoggoth.project import Project
from shoggoth.renderer import CardRenderer
from shoggoth.file_monitor import CardFileMonitor
from shoggoth.files import defaults_dir, asset_dir, font_dir, overlay_dir
from shoggoth.preview_widget import ImprovedCardPreview
from shoggoth.goto_dialog import GotoCardDialog
from shoggoth.encounter_editor import EncounterSetEditor


class FileBrowser(QWidget):
    """File browser widget showing project files"""

    card_selected = Signal(object)  # Emits card object
    encounter_selected = Signal(object)  # Emits encounter object
    project_selected = Signal(object)  # Emits project object
    guide_selected = Signal(object)  # Emits guide object

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        # Title
        title = QLabel("Cards")
        title.setStyleSheet("font-size: 20pt; font-weight: bold;")
        layout.addWidget(title)

        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self.on_item_clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.on_context_menu)
        layout.addWidget(self.tree)

        self.setLayout(layout)
        self._project = None

        # Context menu handler
        from shoggoth.tree_context_menu import TreeContextMenu
        self.context_menu = TreeContextMenu(self)

    def set_project(self, project):
        """Set the project and refresh the tree"""
        self._project = project
        self.refresh()

    def refresh(self):
        """Rebuild the tree from the project"""
        if not self._project:
            return

        self.tree.clear()

        # Create root node
        root = QTreeWidgetItem([self._project['name']])
        root.setData(0, Qt.UserRole, {'type': 'project', 'data': self._project})
        self.tree.addTopLevelItem(root)

        # Determine if we need campaign/player split
        has_encounters = bool(self._project.encounter_sets)
        has_player_cards = any(c for c in self._project.cards if not c.encounter)

        if has_encounters and has_player_cards:
            campaign_node = QTreeWidgetItem(['Campaign cards'])
            player_node = QTreeWidgetItem(['Player cards'])
            root.addChild(campaign_node)
            root.addChild(player_node)
        else:
            campaign_node = player_node = root

        # Add encounter sets
        for encounter_set in self._project.encounter_sets:
            e_node = QTreeWidgetItem([encounter_set.name])
            e_node.setData(0, Qt.UserRole, {'type': 'encounter', 'data': encounter_set})
            campaign_node.addChild(e_node)

            # Add category nodes
            story_node = QTreeWidgetItem(['Story'])
            story_node.setData(0, Qt.UserRole, {'type': 'category', 'data': encounter_set})
            location_node = QTreeWidgetItem(['Locations'])
            location_node.setData(0, Qt.UserRole, {'type': 'category', 'data': encounter_set})
            encounter_node = QTreeWidgetItem(['Encounter'])
            encounter_node.setData(0, Qt.UserRole, {'type': 'category', 'data': encounter_set})
            e_node.addChild(story_node)
            e_node.addChild(location_node)
            e_node.addChild(encounter_node)

            # Add cards to appropriate categories
            for card in encounter_set.cards:
                # Add dirty indicator if card has unsaved changes
                display_name = card.name
                if hasattr(card, 'dirty') and card.dirty:
                    display_name = '● ' + display_name
                elif (hasattr(card, 'front') and hasattr(card.front, 'dirty') and card.front.dirty) or \
                     (hasattr(card, 'back') and hasattr(card.back, 'dirty') and card.back.dirty):
                    display_name = '● ' + display_name

                card_node = QTreeWidgetItem([display_name])
                card_node.setData(0, Qt.UserRole, {'type': 'card', 'data': card})

                if card.front.get('type') == 'location':
                    location_node.addChild(card_node)
                elif card.back.get('type') == 'encounter':
                    encounter_node.addChild(card_node)
                else:
                    story_node.addChild(card_node)

        # Add player cards
        class_nodes = {}
        class_labels = {
            'investigators': 'Investigators',
            'seeker': 'Seeker',
            'rogue': 'Rogue',
            'guardian': 'Guardian',
            'mystic': 'Mystic',
            'survivor': 'Survivor',
            'neutral': 'Neutral',
            'other': 'Other',
        }

        # Classes that have icon files
        classes_with_icons = {'guardian', 'seeker', 'rogue', 'mystic', 'survivor'}

        for cls in ['investigators', 'seeker', 'rogue', 'guardian', 'mystic', 'survivor', 'neutral', 'other']:
            class_node = QTreeWidgetItem([class_labels[cls]])
            class_node.setData(0, Qt.UserRole, {'type': 'category', 'data': None, 'class': cls})

            # Set icon for classes that have them
            if cls in classes_with_icons:
                icon_path = overlay_dir / f"class_symbol_{cls}.png"
                if icon_path.exists():
                    class_node.setIcon(0, QIcon(str(icon_path)))

            class_nodes[cls] = class_node
            player_node.addChild(class_node)

        investigator_nodes = {}

        for card in self._project.player_cards:
            if group := card.data.get('investigator', False):
                if group not in investigator_nodes:
                    inv_node = QTreeWidgetItem([group])
                    inv_node.setData(0, Qt.UserRole, {'type': 'category', 'data': None, 'investigator': group})
                    investigator_nodes[group] = inv_node
                    class_nodes['investigators'].addChild(inv_node)
                target_node = investigator_nodes[group]
            else:
                card_class = card.get_class() or 'other'
                target_node = class_nodes.get(card_class, class_nodes['other'])

            display_name = f'{card.name} ({card.front.get("level")})' if str(card.front.get('level', '0')) != '0' else card.name

            # Add dirty indicator if card has unsaved changes
            if hasattr(card, 'dirty') and card.dirty:
                display_name = '● ' + display_name
            elif (hasattr(card, 'front') and hasattr(card.front, 'dirty') and card.front.dirty) or \
                 (hasattr(card, 'back') and hasattr(card.back, 'dirty') and card.back.dirty):
                display_name = '● ' + display_name

            card_node = QTreeWidgetItem([display_name])
            card_node.setData(0, Qt.UserRole, {'type': 'card', 'data': card})
            target_node.addChild(card_node)

        # Add guides
        if self._project.guides:
            guide_node = QTreeWidgetItem(['Guides'])
            root.addChild(guide_node)

            for guide in self._project.guides:
                g_node = QTreeWidgetItem([guide.name])
                g_node.setData(0, Qt.UserRole, {'type': 'guide', 'data': guide})
                guide_node.addChild(g_node)

        root.setExpanded(True)

    def on_item_clicked(self, item, column):
        """Handle tree item click"""
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        item_type = data['type']
        item_data = data['data']

        if item_type == 'project':
            self.project_selected.emit(item_data)
        elif item_type == 'encounter':
            self.encounter_selected.emit(item_data)
        elif item_type == 'card':
            self.card_selected.emit(item_data)
        elif item_type == 'guide':
            self.guide_selected.emit(item_data)

    def on_context_menu(self, position):
        """Handle context menu request"""
        item = self.tree.itemAt(position)
        if item:
            # Convert position to global coordinates
            global_pos = self.tree.viewport().mapToGlobal(position)
            self.context_menu.show_context_menu(item, global_pos)



class ShoggothMainWindow(QMainWindow):
    """Main window for Shoggoth application"""

    # Signal for file changes (emitted from background thread, handled on main thread)
    file_changed_signal = Signal(str)

    def __init__(self):
        super().__init__()

        # Connect file change signal to handler (for thread-safe UI updates)
        self.file_changed_signal.connect(self._handle_file_changed)

        # Settings manager - must be before shoggoth.app assignment
        from shoggoth.settings import SettingsManager
        self.config = SettingsManager()

        shoggoth.app = self

        self.setWindowTitle("Shoggoth Card Creator")
        self.setMinimumSize(1200, 800)

        # Set application icon
        icon_path = asset_dir / "elder_sign_neon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Initialize components
        self.current_project = None
        self.current_card = None
        self.card_renderer = CardRenderer()
        self.card_file_monitor = None

        # Load settings
        self.load_settings()

        # Setup UI
        self.setup_ui()

        # Setup file monitoring
        self.setup_file_monitoring()

        # Restore session
        self.restore_session()

    def setup_ui(self):
        """Setup the user interface"""
        # Create menu bar
        self.create_menus()

        # Create central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Main layout - just file browser + content area
        main_layout = QHBoxLayout()

        # Create main splitter (2 panels: browser + content)
        self.main_splitter = QSplitter(Qt.Horizontal)

        # Left panel - File browser
        self.file_browser = FileBrowser()
        self.file_browser.card_selected.connect(self.show_card)
        self.file_browser.encounter_selected.connect(self.show_encounter)
        self.file_browser.project_selected.connect(self.show_project)
        self.file_browser.guide_selected.connect(self.show_guide)
        self.main_splitter.addWidget(self.file_browser)

        # Right panel - Content area (will contain editor + preview for cards)
        self.content_container = QWidget()
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_container.setLayout(self.content_layout)
        self.main_splitter.addWidget(self.content_container)

        # Create the editor and preview containers (hidden by default)
        # Editor container
        self.editor_container = QScrollArea()
        self.editor_container.setWidgetResizable(True)
        self.editor_widget = QLabel("Open or create a project to get started")
        self.editor_widget.setAlignment(Qt.AlignCenter)
        self.editor_container.setWidget(self.editor_widget)

        # Preview container (detachable)
        from PySide6.QtWidgets import QDockWidget
        self.preview_dock = QDockWidget("Card Preview", self)
        self.preview_dock.setFeatures(
            QDockWidget.DockWidgetFloatable |
            QDockWidget.DockWidgetMovable |
            QDockWidget.DockWidgetClosable
        )
        self.card_preview = ImprovedCardPreview()
        self.preview_dock.setWidget(self.card_preview)

        # Add dock widget to right side (hidden initially)
        self.addDockWidget(Qt.RightDockWidgetArea, self.preview_dock)
        self.preview_dock.hide()

        # Set initial splitter sizes
        self.main_splitter.setSizes([300, 700])

        main_layout.addWidget(self.main_splitter)
        central.setLayout(main_layout)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

        # Setup global shortcuts
        self.setup_shortcuts()

    def setup_shortcuts(self):
        """Setup global keyboard shortcuts"""
        # Ctrl+P - Go to Card
        # TODO: Re-enable shortcuts once issues are resolved
        # goto_shortcut = QShortcut(QKeySequence("Ctrl+P"), self)
        # goto_shortcut.activated.connect(self.show_goto_dialog)
        pass

    def show_goto_dialog(self):
        """Show the Go to Card dialog"""
        if not self.current_project:
            QMessageBox.information(self, "No Project", "Please open a project first")
            return

        dialog = GotoCardDialog(self.current_project, self)
        dialog.card_selected.connect(self.on_goto_card_selected)
        dialog.exec()

    def on_goto_card_selected(self, card):
        """Handle card selection from goto dialog"""
        # Check if it's a guide
        if hasattr(card, 'is_guide') and card.is_guide:
            self.show_guide(card.guide)
            # Find and select in tree
            self.select_item_in_tree(card.id)
        else:
            # It's a card
            self.show_card(card)
            # Find and select in tree
            self.select_item_in_tree(card.id)

    def select_item_in_tree(self, item_id):
        """Find and select an item in the tree by ID, expanding parents"""
        tree = self.file_browser.tree
        for item in self.iterate_tree_items(tree.invisibleRootItem()):
            data = item.data(0, Qt.UserRole)
            if data and data.get('data'):
                if hasattr(data['data'], 'id') and str(data['data'].id) == str(item_id):
                    # Expand all parent items
                    self.expand_to_item(item)
                    # Select and scroll to the item
                    tree.setCurrentItem(item)
                    tree.scrollToItem(item)
                    return True
        return False

    def iterate_tree_items(self, root_item):
        """Recursively iterate all items in tree"""
        for i in range(root_item.childCount()):
            child = root_item.child(i)
            yield child
            yield from self.iterate_tree_items(child)

    def expand_to_item(self, item):
        """Expand all parent items to make item visible"""
        parent = item.parent()
        while parent:
            parent.setExpanded(True)
            parent = parent.parent()

    def create_menus(self):
        """Create comprehensive menu bar based on shoggoth.kv"""
        menubar = self.menuBar()

        # ==================== FILE MENU ====================
        file_menu = menubar.addMenu("&File")

        # Open Project
        open_action = QAction("&Open Project", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_project_dialog)
        file_menu.addAction(open_action)

        # New Project
        new_action = QAction("&New Project", self)
        new_action.triggered.connect(self.new_project_dialog)
        file_menu.addAction(new_action)

        # Save
        save_action = QAction("&Save (Ctrl+S)", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_changes)
        file_menu.addAction(save_action)

        # New Card
        new_card_action = QAction("New &Card (Ctrl+N)", self)
        new_card_action.setShortcut("Ctrl+N")
        new_card_action.triggered.connect(self.new_card_dialog)
        file_menu.addAction(new_card_action)

        # Go to Card
        goto_card_action = QAction("&Go to Card... (Ctrl+P)", self)
        goto_card_action.setShortcut("Ctrl+P")
        goto_card_action.triggered.connect(self.show_goto_dialog)
        file_menu.addAction(goto_card_action)

        file_menu.addSeparator()

        # Gather images
        gather_action = QAction("Gather images", self)
        gather_action.triggered.connect(self.gather_images)
        file_menu.addAction(gather_action)

        gather_update_action = QAction("Gather images and update", self)
        gather_update_action.triggered.connect(lambda: self.gather_images(update=True))
        file_menu.addAction(gather_update_action)

        file_menu.addSeparator()

        # Export Current Card
        export_current = QAction("Export &Current Card (Ctrl+E)", self)
        export_current.setShortcut("Ctrl+E")
        export_current.triggered.connect(self.export_current)
        file_menu.addAction(export_current)

        # Export All Cards
        export_all = QAction("Export &All Cards (Ctrl+Shift+E)", self)
        export_all.setShortcut("Ctrl+Shift+E")
        export_all.triggered.connect(self.export_all)
        file_menu.addAction(export_all)

        file_menu.addSeparator()

        # Settings
        settings_action = QAction("Se&ttings", self)
        settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        # Exit
        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # ==================== PROJECT MENU ====================
        project_menu = menubar.addMenu("&Project")

        # Add Guide
        add_guide_action = QAction("Add &Guide", self)
        add_guide_action.triggered.connect(self.add_guide)
        project_menu.addAction(add_guide_action)

        # Add Scenario template
        add_scenario_action = QAction("Add &Scenario template", self)
        add_scenario_action.triggered.connect(self.add_scenario_template)
        project_menu.addAction(add_scenario_action)

        # Add Campaign template
        add_campaign_action = QAction("Add &Campaign template", self)
        add_campaign_action.triggered.connect(self.add_campaign_template)
        project_menu.addAction(add_campaign_action)

        # Add Investigator template
        add_investigator_action = QAction("Add &Investigator template", self)
        add_investigator_action.triggered.connect(self.add_investigator_template)
        project_menu.addAction(add_investigator_action)

        # Add Investigator Expansion template
        add_inv_exp_action = QAction("Add Investigator &Expansion template", self)
        add_inv_exp_action.triggered.connect(self.add_investigator_expansion_template)
        project_menu.addAction(add_inv_exp_action)

        # ==================== EXPORT MENU ====================
        export_menu = menubar.addMenu("E&xport")

        # Card To PDF
        card_pdf_action = QAction("Card To &PDF", self)
        card_pdf_action.triggered.connect(self.export_card_to_pdf)
        export_menu.addAction(card_pdf_action)

        # Cards To PDF
        cards_pdf_action = QAction("Cards To PDF", self)
        cards_pdf_action.triggered.connect(self.export_cards_to_pdf)
        export_menu.addAction(cards_pdf_action)

        # Project To PDF
        project_pdf_action = QAction("&Project To PDF", self)
        project_pdf_action.triggered.connect(self.export_project_to_pdf)
        export_menu.addAction(project_pdf_action)

        export_menu.addSeparator()

        # Export card to TTS object
        tts_card_action = QAction("Export card to &TTS object", self)
        tts_card_action.triggered.connect(self.export_card_to_tts)
        export_menu.addAction(tts_card_action)

        # Export all campaign cards to TTS object
        tts_campaign_action = QAction("Export all &campaign cards to TTS object", self)
        tts_campaign_action.triggered.connect(self.export_campaign_to_tts)
        export_menu.addAction(tts_campaign_action)

        # Export all player cards to TTS object
        tts_player_action = QAction("Export all &player cards to TTS object", self)
        tts_player_action.triggered.connect(self.export_player_to_tts)
        export_menu.addAction(tts_player_action)

        # ==================== TOOLS MENU ====================
        tools_menu = menubar.addMenu("&Tools")

        # Convert SE Project
        convert_se_action = QAction("&Convert Strange Eons Project", self)
        convert_se_action.triggered.connect(self.convert_strange_eons)
        tools_menu.addAction(convert_se_action)

        # ==================== HELP MENU ====================
        help_menu = menubar.addMenu("&Help")

        # Text options
        text_options_action = QAction("&Text options", self)
        text_options_action.triggered.connect(self.show_text_options)
        help_menu.addAction(text_options_action)

        # About
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        # Toggle Preview
        self.toggle_preview_action = QAction("Show Card &Preview", self)
        self.toggle_preview_action.setCheckable(True)
        self.toggle_preview_action.setChecked(False)
        self.toggle_preview_action.triggered.connect(self.toggle_preview)
        view_menu.addAction(self.toggle_preview_action)

    def toggle_preview(self, checked):
        """Toggle the preview dock visibility"""
        if checked:
            self.preview_dock.show()
        else:
            self.preview_dock.hide()

    def load_settings(self):
        """Load application settings"""
        settings_file = Path('shoggoth.json')
        if settings_file.exists():
            with open(settings_file, 'r') as f:
                self.settings = json.load(f)
        else:
            self.settings = {'session': {}, 'last_paths': {}}

    def save_settings(self):
        """Save application settings"""
        with open('shoggoth.json', 'w') as f:
            json.dump(self.settings, f)

    def setup_file_monitoring(self):
        """Setup file system monitoring for assets and card files"""
        self.card_file_monitor = CardFileMonitor(asset_dir, self.on_file_changed)
        self.card_file_monitor.start()

    def restore_session(self):
        """Restore previous session"""
        session = self.settings.get('session', {})
        if project_path := session.get('project'):
            try:
                self.open_project(project_path)
                if card_id := session.get('last_id'):
                    QTimer.singleShot(100, lambda: self.goto_card(card_id))
            except Exception as e:
                print(f"Error restoring session: {e}")

    def open_project_dialog(self):
        """Show dialog to open a project"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Project",
            str(Path.home()),
            "JSON Files (*.json)"
        )
        if file_path:
            self.open_project(file_path)

    def open_project(self, file_path):
        """Open a project file"""
        try:
            self.current_project = Project.load(file_path)
            self.file_browser.set_project(self.current_project)
            self.settings['session']['project'] = file_path
            self.save_settings()
            self.status_bar.showMessage(f"Opened: {self.current_project['name']}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open project: {e}")

    def new_project_dialog(self):
        """Show dialog to create a new project"""
        from shoggoth.dialogs import NewProjectDialog
        dialog = NewProjectDialog(self)
        dialog.exec()

    def clear_editor(self):
        """Clear and cleanup the current editor"""
        # Clear all widgets in content layout
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                # Call cleanup if the widget has it (recursively for nested widgets)
                self._cleanup_widget(widget)
                widget.setParent(None)
                widget.deleteLater()

    def _cleanup_widget(self, widget):
        """Recursively cleanup a widget and its children"""
        # Check if this widget has cleanup method
        if hasattr(widget, 'cleanup'):
            try:
                widget.cleanup()
            except Exception as e:
                print(f"Error during widget cleanup: {e}")

        # Recursively cleanup children
        for child in widget.findChildren(QWidget):
            if hasattr(child, 'cleanup'):
                try:
                    child.cleanup()
                except Exception as e:
                    print(f"Error during child cleanup: {e}")

    def save_changes(self):
        """Save the entire project"""
        if not self.current_project:
            return

        try:
            self.current_project.save()

            # Mark all cards as clean
            for card in self.current_project.get_all_cards():
                card.dirty = False
                if hasattr(card, 'front') and hasattr(card.front, 'dirty'):
                    card.front.dirty = False
                if hasattr(card, 'back') and hasattr(card.back, 'dirty'):
                    card.back.dirty = False

            # Update tree to remove dirty indicators
            self.file_browser.refresh()

            self.status_bar.showMessage("Project saved", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save project:\n{e}")

    def save_current(self):
        """Save only the current card"""
        if not self.current_card:
            return

        try:
            self.current_card.save()
            self.current_card.dirty = False
            if hasattr(self.current_card, 'front') and hasattr(self.current_card.front, 'dirty'):
                self.current_card.front.dirty = False
            if hasattr(self.current_card, 'back') and hasattr(self.current_card.back, 'dirty'):
                self.current_card.back.dirty = False

            # Update tree to remove dirty indicator
            self.file_browser.refresh()

            self.status_bar.showMessage(f"Saved: {self.current_card.name}", 3000)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to save card:\n{e}")

    def export_all(self, bleed=None, format=None, quality=None, separate_versions=None):
        """Export all cards in the project using settings from preferences"""
        if not self.current_project:
            QMessageBox.warning(self, "Error", "No project loaded")
            return

        # Use settings if not explicitly provided
        if bleed is None:
            bleed = self.config.getboolean('Shoggoth', 'export_bleed', True)
        if format is None:
            format = self.config.get('Shoggoth', 'export_format', 'png')
        if quality is None:
            quality = self.config.getint('Shoggoth', 'export_quality', 95)
        if separate_versions is None:
            separate_versions = self.config.getboolean('Shoggoth', 'export_separate_versions', False)

        try:
            export_folder = Path(self.current_project.file_path).parent / f'Export of {self.current_project.name}'
            export_folder.mkdir(parents=True, exist_ok=True)

            cards = self.current_project.get_all_cards()

            # Show progress
            from PySide6.QtWidgets import QProgressDialog
            progress = QProgressDialog(
                "Exporting cards...", "Cancel", 0, len(cards), self
            )
            progress.setWindowModality(Qt.WindowModal)

            # Export each card
            import threading
            threads = []
            for i, card in enumerate(cards):
                if progress.wasCanceled():
                    break

                progress.setValue(i)
                progress.setLabelText(f"Exporting {card.name}...")

                # Export in thread
                thread = threading.Thread(
                    target=self.card_renderer.export_card_images,
                    args=(card, str(export_folder)),
                    kwargs={
                        'include_backs': False,
                        'bleed': bleed,
                        'format': format,
                        'quality': quality,
                        'separate_versions': separate_versions
                    }
                )
                threads.append(thread)
                thread.start()

            # Wait for all threads
            for thread in threads:
                thread.join()

            progress.setValue(len(cards))

            QMessageBox.information(
                self,
                "Export Complete",
                f"Exported {len(cards)} cards to:\n{export_folder}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export cards:\n{e}")

    def new_card_dialog(self):
        """Show dialog to create a new card"""
        if not self.current_project:
            QMessageBox.warning(self, "Error", "No project open")
            return

        from shoggoth.dialogs import NewCardDialog
        dialog = NewCardDialog(self)
        dialog.exec()

    def show_card(self, card):
        """Display a card in the editor"""
        # Clean up previous editor
        self.clear_editor()

        self.current_card = card
        self.settings['session']['last_id'] = card.id
        self.save_settings()

        # Update file monitoring for this card's dependencies
        if self.card_file_monitor:
            card_files = self.card_file_monitor.get_card_file_dependencies(card)
            self.card_file_monitor.set_card_files(card_files)

        # Clear content layout
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Create a splitter for editor + preview
        card_splitter = QSplitter(Qt.Horizontal)

        # Load card editor
        from shoggoth.editors import CardEditor
        editor = CardEditor(card)

        # Connect data change signal to preview update
        editor.data_changed.connect(self.update_card_preview)

        # Wrap editor in scroll area
        editor_scroll = QScrollArea()
        editor_scroll.setWidgetResizable(True)
        editor_scroll.setWidget(editor)

        card_splitter.addWidget(editor_scroll)

        # Show preview dock
        self.preview_dock.show()
        self.toggle_preview_action.setChecked(True)

        # Set splitter sizes (60% editor, 40% would be preview but it's docked)
        card_splitter.setSizes([600, 400])

        # Add splitter to content area
        self.content_layout.addWidget(card_splitter)

        # Update preview
        self.update_card_preview()

    def show_encounter(self, encounter):
        """Display an encounter set in the editor"""
        # Clear current editor
        self.clear_editor()

        # Hide preview for non-card views
        self.preview_dock.hide()

        # Clear content layout
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Create and show encounter set editor
        editor = EncounterSetEditor(encounter, self.card_renderer)
        editor.card_clicked.connect(self.show_card)

        # Wrap in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(editor)

        self.content_layout.addWidget(scroll)

        # Update status
        self.status_bar.showMessage(f"Editing encounter set: {encounter.name}")

    def show_encounter_set(self, encounter_set):
        """Show encounter set editor (alias for show_encounter)"""
        self.show_encounter(encounter_set)

    def show_project(self, project):
        """Display project editor"""
        # Clear current editor
        self.clear_editor()

        # Hide preview for non-card views
        self.preview_dock.hide()
        self.toggle_preview_action.setChecked(False)

        # Clear content layout
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Create project editor
        from shoggoth.project_editor import ProjectEditor
        editor = ProjectEditor(project, self.card_renderer)

        # Wrap in scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(editor)

        self.content_layout.addWidget(scroll)
        self.status_bar.showMessage(f"Editing project: {project['name']}")

    def show_guide(self, guide):
        """Display guide editor"""
        # Clear current editor
        self.clear_editor()

        # Hide preview for non-card views
        self.preview_dock.hide()

        # Clear content layout
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Create and add guide editor
        from shoggoth.guide_editor import GuideEditor
        editor = GuideEditor(guide)
        self.content_layout.addWidget(editor)

        self.current_guide = guide

    def update_card_preview(self):
        """Update the card preview"""
        if not self.current_card:
            return

        # Update file monitoring in case illustration paths changed
        if self.card_file_monitor:
            card_files = self.card_file_monitor.get_card_file_dependencies(self.current_card)
            self.card_file_monitor.set_card_files(card_files)

        try:
            # Get bleed setting
            bleed = False
            if self.config.getboolean('Shoggoth', 'show_bleed', True):
                bleed = 'mark'

            front_image, back_image = self.card_renderer.get_card_textures(
                self.current_card, bleed=bleed
            )
            self.card_preview.set_card_images(front_image, back_image)
        except Exception as e:
            self.status_bar.showMessage(f"Error rendering card: {e}")

    def goto_card(self, card_id):
        """Navigate to a specific card by ID"""
        if not self.current_project:
            return

        card = self.current_project.get_card(card_id)
        if card:
            self.show_card(card)
            self.select_item_in_tree(card_id)

    def refresh_tree(self):
        """Refresh the file browser tree"""
        self.file_browser.refresh()

    def export_current(self, bleed=None, format=None, quality=None, separate_versions=None):
        """Export the current card using settings from preferences"""
        if not self.current_card:
            QMessageBox.warning(self, "Error", "No card selected")
            return

        # Use settings if not explicitly provided
        if bleed is None:
            bleed = self.config.getboolean('Shoggoth', 'export_bleed', True)
        if format is None:
            format = self.config.get('Shoggoth', 'export_format', 'png')
        if quality is None:
            quality = self.config.getint('Shoggoth', 'export_quality', 95)
        if separate_versions is None:
            separate_versions = self.config.getboolean('Shoggoth', 'export_separate_versions', False)

        try:
            export_folder = Path(self.current_project.file_path).parent / f'Export of {self.current_project.name}'
            export_folder.mkdir(parents=True, exist_ok=True)

            # Export card
            self.card_renderer.export_card_images(
                self.current_card,
                str(export_folder),
                include_backs=False,
                bleed=bleed,
                format=format,
                quality=quality,
                separate_versions=separate_versions
            )

            QMessageBox.information(
                self,
                "Export Complete",
                f"Card exported to:\n{export_folder}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export card:\n{e}")

    def on_file_changed(self, file_path):
        """Called from file monitor (background thread) - emit signal for main thread handling"""
        # Emit signal to handle on main thread (Qt requires UI updates on main thread)
        self.file_changed_signal.emit(file_path)

    @Slot(str)
    def _handle_file_changed(self, file_path):
        """Handle file system changes on main thread - refresh preview when relevant files change"""
        if self.current_card:
            # Invalidate the renderer cache for the changed file
            self.card_renderer.invalidate_cache(file_path)

            # Reload fallback data (for template/defaults changes)
            self.current_card.reload_fallback()

            # Update the preview
            self.update_card_preview()

    def show_about(self):
        """Show about dialog"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QDialogButtonBox
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl

        # Get version from package metadata
        try:
            from importlib.metadata import version
            app_version = version("shoggoth")
        except Exception:
            app_version = "unknown"

        # URLs for links
        urls = {
            'contrib': 'https://github.com/tokeeto/shoggoth',
            'patreon': 'https://www.patreon.com/tokeeto',
            'tips': 'https://ko-fi.com/tokeeto',
        }

        about_html = f"""
        <div style="text-align: center;">
            <h1 style="font-size: 32pt; margin-bottom: 5px;">Shoggoth</h1>
            <p style="font-size: 14pt; color: #666;">Version {app_version}</p>
        </div>
        <hr>
        <p>Created by <b>Toke Ivø</b></p>
        <p>
            You can support the development of Shoggoth by
            <a href="{urls['contrib']}">contributing</a>,
            <a href="{urls['patreon']}">donating on Patreon</a>, or
            <a href="{urls['tips']}">leaving a tip</a>.
        </p>
        <p>Various images and templates by the <b>Mythos Busters</b> community - especially <b>Coldtoes</b> and <b>Hauke</b>.</p>
        <p>
            Thanks to <b>CGJennings</b> for creating Strange Eons, and
            <b>pilunte23/JaqenZann</b> for the original AHLCG plugin,
            without which we'd all be so much more bored.
        </p>
        <p>
            Special thanks to <b>Coldtoes</b>, <b>felice</b>, <b>Chr1Z</b>,
            <b>MickeyTheQ</b> and <b>Morvael</b> for helping this project become a reality.
        </p>
        """

        dialog = QDialog(self)
        dialog.setWindowTitle("About Shoggoth")
        dialog.setMinimumSize(450, 350)

        layout = QVBoxLayout()

        # Use QTextBrowser for clickable links
        text_browser = QTextBrowser()
        text_browser.setOpenExternalLinks(True)
        text_browser.setHtml(about_html)
        text_browser.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(text_browser)

        # OK button
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)

        dialog.setLayout(layout)
        dialog.exec()

    def closeEvent(self, event):
        """Handle window close event - check for unsaved changes"""
        if self.card_file_monitor:
            self.card_file_monitor.stop()
        self.save_settings()

        if self.has_unsaved_changes():
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Do you want to save before exiting?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save
            )

            if reply == QMessageBox.Save:
                self.save_changes()
                event.accept()
            elif reply == QMessageBox.Discard:
                event.accept()
            else:  # Cancel
                event.ignore()
        else:
            event.accept()

    def has_unsaved_changes(self):
        """Check if there are any unsaved changes in the project"""
        if not self.current_project:
            return False

        for card in self.current_project.get_all_cards():
            if hasattr(card, 'dirty') and card.dirty:
                return True
            if hasattr(card, 'front') and hasattr(card.front, 'dirty') and card.front.dirty:
                return True
            if hasattr(card, 'back') and hasattr(card.back, 'dirty') and card.back.dirty:
                return True

        return False

    # ==================== PROJECT MENU ACTIONS ====================

    def add_guide(self):
        """Add a guide to the project"""
        if not self.current_project:
            QMessageBox.warning(self, "Error", "No project open")
            return
        self.current_project.add_guide()
        self.file_browser.refresh()
        self.status_bar.showMessage("Guide added")

    def add_scenario_template(self):
        """Add a scenario template"""
        if not self.current_project:
            QMessageBox.warning(self, "Error", "No project open")
            return
        name, ok = self.get_text_input("Scenario Name", "Enter scenario name:", "Placeholder")
        if ok and name:
            self.current_project.create_scenario(name)
            self.file_browser.refresh()
            self.status_bar.showMessage(f"Scenario '{name}' created")

    def add_campaign_template(self):
        """Add a campaign template"""
        if not self.current_project:
            QMessageBox.warning(self, "Error", "No project open")
            return
        self.current_project.create_campaign()
        self.file_browser.refresh()
        self.status_bar.showMessage("Campaign template created")

    def add_investigator_template(self):
        """Add an investigator template"""
        if not self.current_project:
            QMessageBox.warning(self, "Error", "No project open")
            return
        name, ok = self.get_text_input("Investigator Name", "Enter investigator name:", "John Doe")
        if ok and name:
            self.current_project.add_investigator_set(name)
            self.file_browser.refresh()
            self.status_bar.showMessage(f"Investigator '{name}' created")

    def add_investigator_expansion_template(self):
        """Add an investigator expansion template"""
        if not self.current_project:
            QMessageBox.warning(self, "Error", "No project open")
            return
        self.current_project.create_player_expansion()
        self.file_browser.refresh()
        self.status_bar.showMessage("Player expansion template created")

    # ==================== EXPORT MENU ACTIONS ====================

    def export_card_to_pdf(self):
        """Export current card to PDF"""
        if not self.current_card:
            QMessageBox.warning(self, "Error", "No card selected")
            return
        # TODO: Implement PDF export
        QMessageBox.information(self, "TODO", "PDF export not yet implemented")

    def export_cards_to_pdf(self):
        """Export all cards to PDF"""
        if not self.current_project:
            QMessageBox.warning(self, "Error", "No project open")
            return
        # TODO: Implement PDF export
        QMessageBox.information(self, "TODO", "PDF export not yet implemented")

    def export_project_to_pdf(self):
        """Export entire project to PDF"""
        if not self.current_project:
            QMessageBox.warning(self, "Error", "No project open")
            return
        # TODO: Implement PDF export
        QMessageBox.information(self, "TODO", "PDF export not yet implemented")

    def export_card_to_tts(self):
        """Export card to Tabletop Simulator"""
        if not self.current_card:
            QMessageBox.warning(self, "Error", "No card selected")
            return
        try:
            from shoggoth import tts_lib
            tts_lib.export_card(self.current_card)
            self.status_bar.showMessage("Card exported to TTS")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export to TTS: {e}")

    def export_campaign_to_tts(self):
        """Export campaign cards to Tabletop Simulator"""
        if not self.current_project:
            QMessageBox.warning(self, "Error", "No project open")
            return
        try:
            from shoggoth import tts_lib
            tts_lib.export_campaign(self.current_project)
            self.status_bar.showMessage("Campaign exported to TTS")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export to TTS: {e}")

    def export_player_to_tts(self):
        """Export player cards to Tabletop Simulator"""
        if not self.current_project:
            QMessageBox.warning(self, "Error", "No project open")
            return
        try:
            from shoggoth import tts_lib
            tts_lib.export_player_cards(self.current_project.player_cards)
            self.status_bar.showMessage("Player cards exported to TTS")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export to TTS: {e}")

    # ==================== TOOLS MENU ACTIONS ====================

    def convert_strange_eons(self):
        """Convert a Strange Eons project"""
        QMessageBox.information(self, "TODO", "Strange Eons converter not yet implemented")

    # ==================== FILE MENU ACTIONS ====================

    def gather_images(self, update=False):
        """Gather all images from the project"""
        if not self.current_project:
            QMessageBox.warning(self, "Error", "No project open")
            return

        try:
            self.current_project.gather_images(update=update)
            action = "gathered and updated" if update else "gathered"
            self.status_bar.showMessage(f"Images {action}")
            QMessageBox.information(self, "Success", f"Images {action} successfully")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to gather images: {e}")

    def open_settings(self):
        """Open settings dialog"""
        from shoggoth.settings import SettingsDialog
        dialog = SettingsDialog(self.config, self)
        dialog.exec()

    # ==================== HELP MENU ACTIONS ====================

    def show_text_options(self):
        """Show text formatting options"""
        help_text = self.card_renderer.rich_text.get_help_text()
        msg = QMessageBox(self)
        msg.setWindowTitle("Text Options")
        msg.setText("Rich text formatting options:")
        msg.setDetailedText(help_text)
        msg.exec()

    # ==================== UTILITY METHODS ====================

    def get_text_input(self, title, label, default=""):
        """Show a text input dialog"""
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, title, label, text=default)
        return text, ok
