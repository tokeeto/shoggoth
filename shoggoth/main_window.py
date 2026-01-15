"""
Main window implementation for Shoggoth using PySide6
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QLabel, QMenuBar, QMenu,
    QFileDialog, QMessageBox, QStatusBar, QScrollArea, QDialog,
    QLineEdit, QPushButton, QDialogButtonBox
)
from PySide6.QtCore import QUrl, Qt, QTimer, Signal, Slot
from PySide6.QtGui import (
    QPixmap, QAction, QImage, QKeySequence, QShortcut, QIcon, QDesktopServices
)
from pathlib import Path
import json
import threading
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
    locations_selected = Signal(object)  # Emits encounter set for location view

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
        self._node_map = {}  # Maps node_id -> QTreeWidgetItem for fast lookup

        # Context menu handler
        from shoggoth.tree_context_menu import TreeContextMenu
        self.context_menu = TreeContextMenu(self)

    def set_project(self, project):
        """Set the project and do a full tree rebuild"""
        self._project = project
        self._node_map.clear()
        self._full_rebuild()

    def refresh(self):
        """Smart refresh - only update what has changed"""
        if not self._project:
            return

        # Build desired tree specification
        desired_spec = self._build_tree_spec()

        # If tree is empty, do a full rebuild
        if self.tree.topLevelItemCount() == 0:
            self._full_rebuild()
            return

        # Apply incremental updates
        root_item = self.tree.topLevelItem(0)
        self._sync_tree_node(root_item, desired_spec)

    def _full_rebuild(self):
        """Do a complete tree rebuild (used for initial load or project change)"""
        if not self._project:
            return

        self.tree.clear()
        self._node_map.clear()

        spec = self._build_tree_spec()
        root_item = self._create_tree_item(spec)
        self.tree.addTopLevelItem(root_item)
        root_item.setExpanded(True)

    def _build_tree_spec(self):
        """Build a specification of the desired tree state"""
        if not self._project:
            return None

        # Root node
        root_spec = {
            'node_id': f'project:{self._project.file_path}',
            'text': self._project['name'],
            'type': 'project',
            'data': self._project,
            'icon': None,
            'children': []
        }

        # Determine if we need campaign/player split
        has_encounters = bool(self._project.encounter_sets)
        has_player_cards = any(c for c in self._project.cards if not c.encounter)

        if has_encounters and has_player_cards:
            campaign_spec = {
                'node_id': 'category:campaign_cards',
                'text': 'Campaign cards',
                'type': 'campaign_cards',
                'data': self._project,
                'icon': None,
                'children': []
            }
            player_spec = {
                'node_id': 'category:player_cards',
                'text': 'Player cards',
                'type': 'player_cards',
                'data': self._project,
                'icon': None,
                'children': []
            }
            root_spec['children'].append(campaign_spec)
            root_spec['children'].append(player_spec)
        else:
            campaign_spec = player_spec = root_spec

        # Add encounter sets
        for encounter_set in self._project.encounter_sets:
            e_spec = {
                'node_id': f'encounter:{encounter_set.name}',
                'text': encounter_set.name,
                'type': 'encounter',
                'data': encounter_set,
                'icon': None,
                'children': []
            }

            story_spec = {
                'node_id': f'category:{encounter_set.name}:story',
                'text': 'Story',
                'type': 'category',
                'data': encounter_set,
                'icon': None,
                'children': []
            }
            location_spec = {
                'node_id': f'locations:{encounter_set.name}',
                'text': 'Locations',
                'type': 'locations',
                'data': encounter_set,
                'icon': None,
                'children': []
            }
            encounter_cat_spec = {
                'node_id': f'category:{encounter_set.name}:encounter',
                'text': 'Encounter',
                'type': 'category',
                'data': encounter_set,
                'icon': None,
                'children': []
            }
            e_spec['children'] = [story_spec, location_spec, encounter_cat_spec]

            # Add cards to appropriate categories
            for card in encounter_set.cards:
                card_spec = self._build_card_spec(card)

                if card.front.get('type') == 'location':
                    location_spec['children'].append(card_spec)
                elif card.back.get('type') == 'encounter':
                    encounter_cat_spec['children'].append(card_spec)
                else:
                    story_spec['children'].append(card_spec)

            campaign_spec['children'].append(e_spec)

        # Add player cards
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
        classes_with_icons = {'guardian', 'seeker', 'rogue', 'mystic', 'survivor'}

        class_specs = {}
        for cls in ['investigators', 'seeker', 'rogue', 'guardian', 'mystic', 'survivor', 'neutral', 'other']:
            icon_path = None
            if cls in classes_with_icons:
                path = overlay_dir / f"class_symbol_{cls}.png"
                if path.exists():
                    icon_path = str(path)

            class_spec = {
                'node_id': f'class:{cls}',
                'text': class_labels[cls],
                'type': 'category',
                'data': None,
                'class': cls,
                'icon': icon_path,
                'children': []
            }
            class_specs[cls] = class_spec
            player_spec['children'].append(class_spec)

        investigator_specs = {}

        for card in self._project.player_cards:
            if group := card.data.get('investigator', False):
                if group not in investigator_specs:
                    inv_spec = {
                        'node_id': f'investigator:{group}',
                        'text': group,
                        'type': 'category',
                        'data': None,
                        'investigator': group,
                        'icon': None,
                        'children': []
                    }
                    investigator_specs[group] = inv_spec
                    class_specs['investigators']['children'].append(inv_spec)
                target_spec = investigator_specs[group]
            else:
                card_class = card.get_class() or 'other'
                target_spec = class_specs.get(card_class, class_specs['other'])

            card_spec = self._build_card_spec(card, include_level=True)
            target_spec['children'].append(card_spec)

        # Add guides
        if self._project.guides:
            guide_parent = {
                'node_id': 'category:guides',
                'text': 'Guides',
                'type': 'category',
                'data': None,
                'icon': None,
                'children': []
            }
            for guide in self._project.guides:
                guide_spec = {
                    'node_id': f'guide:{guide.id}',
                    'text': guide.name,
                    'type': 'guide',
                    'data': guide,
                    'icon': None,
                    'children': []
                }
                guide_parent['children'].append(guide_spec)
            root_spec['children'].append(guide_parent)

        return root_spec

    def _build_card_spec(self, card, include_level=False):
        """Build a specification for a card node"""
        if include_level and str(card.front.get('level', '0')) != '0':
            display_name = f'{card.name} ({card.front.get("level")})'
        else:
            display_name = card.name

        # Add dirty indicator
        if card.dirty:
            display_name = '● ' + display_name

        return {
            'node_id': f'card:{card.id}',
            'text': display_name,
            'type': 'card',
            'data': card,
            'icon': None,
            'children': []
        }

    def _create_tree_item(self, spec):
        """Create a QTreeWidgetItem from a spec, recursively"""
        item = QTreeWidgetItem([spec['text']])

        # Build user data
        user_data = {'type': spec['type'], 'data': spec['data']}
        if 'class' in spec:
            user_data['class'] = spec['class']
        if 'investigator' in spec:
            user_data['investigator'] = spec['investigator']
        item.setData(0, Qt.UserRole, user_data)

        # Set icon if specified
        if spec.get('icon'):
            item.setIcon(0, QIcon(spec['icon']))

        # Store in node map for fast lookup
        self._node_map[spec['node_id']] = item

        # Create children
        for child_spec in spec.get('children', []):
            child_item = self._create_tree_item(child_spec)
            item.addChild(child_item)

        return item

    def _sync_tree_node(self, item, spec):
        """Synchronize an existing tree item with a spec, updating only what changed"""
        if spec is None:
            return

        # Update text if changed
        if item.text(0) != spec['text']:
            item.setText(0, spec['text'])

        # Update user data
        user_data = {'type': spec['type'], 'data': spec['data']}
        if 'class' in spec:
            user_data['class'] = spec['class']
        if 'investigator' in spec:
            user_data['investigator'] = spec['investigator']
        item.setData(0, Qt.UserRole, user_data)

        # Update node map
        self._node_map[spec['node_id']] = item

        # Build maps of current and desired children
        current_children = {}
        for i in range(item.childCount()):
            child = item.child(i)
            child_data = child.data(0, Qt.UserRole)
            if child_data:
                # Build node_id from current item
                child_id = self._get_node_id_from_item(child)
                if child_id:
                    current_children[child_id] = (i, child)

        desired_children = {child_spec['node_id']: child_spec for child_spec in spec.get('children', [])}
        desired_order = [child_spec['node_id'] for child_spec in spec.get('children', [])]

        # Find nodes to remove (in current but not in desired)
        to_remove = set(current_children.keys()) - set(desired_children.keys())

        # Find nodes to add (in desired but not in current)
        to_add = set(desired_children.keys()) - set(current_children.keys())

        # Find nodes to update (in both)
        to_update = set(current_children.keys()) & set(desired_children.keys())

        # Remove nodes (in reverse order to maintain indices)
        remove_indices = sorted([current_children[node_id][0] for node_id in to_remove], reverse=True)
        for idx in remove_indices:
            removed_item = item.takeChild(idx)
            # Clean up node map
            self._remove_from_node_map(removed_item)

        # Update existing nodes
        for node_id in to_update:
            _, child_item = current_children[node_id]
            child_spec = desired_children[node_id]
            self._sync_tree_node(child_item, child_spec)

        # Add new nodes
        for node_id in to_add:
            child_spec = desired_children[node_id]
            new_item = self._create_tree_item(child_spec)
            item.addChild(new_item)  # Add at end for now

        # Reorder children to match desired order
        self._reorder_children(item, desired_order)

    def _get_node_id_from_item(self, item):
        """Extract or construct a node_id from an existing tree item"""
        data = item.data(0, Qt.UserRole)
        if not data:
            return None

        item_type = data.get('type')
        item_data = data.get('data')

        if item_type == 'card' and item_data:
            return f'card:{item_data.id}'
        elif item_type == 'guide' and item_data:
            return f'guide:{item_data.id}'
        elif item_type == 'encounter' and item_data:
            return f'encounter:{item_data.name}'
        elif item_type == 'project' and item_data:
            return f'project:{item_data.path}'
        elif item_type == 'locations' and item_data:
            return f'locations:{item_data.name}'
        elif item_type == 'campaign_cards':
            return 'category:campaign_cards'
        elif item_type == 'player_cards':
            return 'category:player_cards'
        elif item_type == 'category':
            if data.get('class'):
                return f'class:{data["class"]}'
            elif data.get('investigator'):
                return f'investigator:{data["investigator"]}'
            elif item_data:  # Encounter category (Story/Encounter)
                text = item.text(0).lower()
                return f'category:{item_data.name}:{text}'
            elif item.text(0) == 'Guides':
                return 'category:guides'
        return None

    def _remove_from_node_map(self, item):
        """Recursively remove an item and its children from the node map"""
        node_id = self._get_node_id_from_item(item)
        if node_id and node_id in self._node_map:
            del self._node_map[node_id]

        for i in range(item.childCount()):
            self._remove_from_node_map(item.child(i))

    def _reorder_children(self, parent_item, desired_order):
        """Reorder children of a parent item to match desired order"""
        if not desired_order:
            return

        # Build current order map
        current_order = []
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            node_id = self._get_node_id_from_item(child)
            current_order.append(node_id)

        # Check if reordering is needed
        if current_order == desired_order:
            return

        # Remove all children while preserving expansion state
        children_with_expansion = []
        while parent_item.childCount() > 0:
            child = parent_item.takeChild(0)
            node_id = self._get_node_id_from_item(child)
            children_with_expansion.append((node_id, child, child.isExpanded()))

        # Create lookup
        child_lookup = {node_id: (child, expanded) for node_id, child, expanded in children_with_expansion}

        # Re-add in correct order
        for node_id in desired_order:
            if node_id in child_lookup:
                child, expanded = child_lookup[node_id]
                parent_item.addChild(child)
                child.setExpanded(expanded)

    def update_card_node(self, card_id):
        """Update a single card node by its ID without rebuilding the tree"""
        node_id = f'card:{card_id}'
        if node_id not in self._node_map:
            # Card not in tree, might need full refresh
            return False

        item = self._node_map[node_id]
        data = item.data(0, Qt.UserRole)
        if not data or data.get('type') != 'card':
            return False

        card = data.get('data')
        print('update_card_node, card', card)
        if not card:
            return False

        # Determine if this is a player card (needs level in name)
        include_level = not card.encounter

        # Build new display name
        if include_level and str(card.front.get('level', '0')) != '0':
            display_name = f'{card.name} ({card.front.get("level")})'
        else:
            display_name = card.name

        # Add dirty indicator
        if card.dirty:
            print('update_card_node, dirty:', card.dirty)
            display_name = '● ' + display_name
        else:
            print('update_card_node, false dirty:', card.dirty)

        # Update only if changed
        if item.text(0) != display_name:
            item.setText(0, display_name)

        return True

    def get_card_item(self, card_id):
        """Get the tree item for a card by ID"""
        node_id = f'card:{card_id}'
        return self._node_map.get(node_id)

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
        elif item_type == 'locations':
            self.locations_selected.emit(item_data)

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

    # Signal for render results (version, front_image, back_image)
    render_result_signal = Signal(int, object, object)

    def __init__(self):
        super().__init__()

        # Connect file change signal to handler (for thread-safe UI updates)
        self.file_changed_signal.connect(self._handle_file_changed)

        # Connect render result signal to handler
        self.render_result_signal.connect(self._handle_render_result)

        # Settings manager - must be before shoggoth.app assignment
        from shoggoth.settings import SettingsManager
        self.config = SettingsManager()

        shoggoth.app = self

        self.setWindowTitle("Shoggoth Card Creator")
        self.setMinimumSize(1400, 900)

        # Set application icon
        icon_path = asset_dir / "elder_sign_neon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Initialize components
        self.current_project = None
        self.current_card = None
        self.current_editor = None
        self.card_renderer = CardRenderer()
        self.card_file_monitor = None

        # Preview rendering with debounce
        self.render_timer = QTimer()
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self._start_background_render)
        self.render_version = 0  # Tracks render requests, stale results are discarded

        # Navigation history (browser-like back/forward)
        self._nav_history = []  # List of (type, id) tuples
        self._nav_index = -1    # Current position in history
        self._nav_navigating = False  # Prevent recursive history updates during navigation

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
        self.file_browser.locations_selected.connect(self.show_locations)
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

        asset_location_action = QAction("&Asset file location", self)
        asset_location_action.triggered.connect(self.open_asset_location)
        help_menu.addAction(asset_location_action)

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
                if last_id := session.get('last_id'):
                    last_type = session.get('last_type', 'card')
                    QTimer.singleShot(100, lambda: self._restore_last_element(last_id, last_type))
            except Exception as e:
                print(f"Error restoring session: {e}")

    def _restore_last_element(self, element_id, element_type):
        """Restore the last selected element by ID and type"""
        if not self.current_project:
            return

        element = None
        if element_type == 'card':
            element = self.current_project.get_card(element_id)
            if element:
                self.show_card(element)
        elif element_type == 'encounter':
            element = self.current_project.get_encounter_set(element_id)
            if element:
                self.show_encounter(element)
        elif element_type == 'guide':
            element = self.current_project.get_guide(element_id)
            if element:
                self.show_guide(element)
        elif element_type == 'locations':
            element = self.current_project.get_encounter_set(element_id)
            if element:
                self.show_locations(element)

        # Select in tree if element was found
        if element:
            self.select_item_in_tree(element_id)

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
            # Clear navigation history for new project
            self._nav_history.clear()
            self._nav_index = -1
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
            # Note: Card.save() already clears dirty flags and updates tree node
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
        self._push_nav_history('card', card.id)

        # Clean up previous editor
        self.clear_editor()

        self.current_card = card
        self.current_editor = None
        self.settings['session']['last_id'] = card.id
        self.settings['session']['last_type'] = 'card'
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
        self.current_editor = editor

        # Connect data change signal to debounced preview update
        editor.data_changed.connect(self.schedule_preview_update)

        # Connect illustration mode signals
        self._connect_illustration_mode(editor)

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

    def _disconnect_illustration_mode(self):
        """Disconnect illustration mode signals"""
        try:
            self.card_preview.illustration_pan_changed.disconnect(self._on_illustration_pan)
            self.card_preview.illustration_scale_changed.disconnect(self._on_illustration_scale)
        except RuntimeError:
            pass  # Signals weren't connected

        # Reset illustration mode on preview
        self.card_preview.set_illustration_mode(False)

    def _connect_illustration_mode(self, editor):
        """Connect illustration mode signals between editor and preview"""
        # Disconnect any previous connections first
        self._disconnect_illustration_mode()

        # Connect preview pan/scale signals to editor
        self.card_preview.illustration_pan_changed.connect(self._on_illustration_pan)
        self.card_preview.illustration_scale_changed.connect(self._on_illustration_scale)

        # Connect editor illustration mode signals to preview
        for face_editor in [editor.front_editor, editor.back_editor]:
            if face_editor and hasattr(face_editor, 'illustration_widget'):
                widget = face_editor.illustration_widget
                widget.illustration_mode_changed.connect(self._on_illustration_mode_changed)

    def _on_illustration_mode_changed(self, enabled, side):
        """Handle illustration mode toggle from editor"""
        self.card_preview.set_illustration_mode(enabled, side)

    def _on_illustration_pan(self, side, delta_x, delta_y):
        """Handle pan changes from preview"""
        if not self.current_editor:
            return

        # Find the right face editor and illustration widget
        face_editor = self.current_editor.front_editor if side == 'front' else self.current_editor.back_editor
        if face_editor and hasattr(face_editor, 'illustration_widget'):
            face_editor.illustration_widget.update_pan(delta_x, delta_y)

    def _on_illustration_scale(self, side, delta):
        """Handle scale changes from preview"""
        if not self.current_editor:
            return

        # Find the right face editor and illustration widget
        face_editor = self.current_editor.front_editor if side == 'front' else self.current_editor.back_editor
        if face_editor and hasattr(face_editor, 'illustration_widget'):
            face_editor.illustration_widget.update_scale(delta)

    def show_encounter(self, encounter):
        """Display an encounter set in the editor"""
        self._push_nav_history('encounter', encounter.id)

        # Clear current editor
        self.clear_editor()

        # Save selection
        self.settings['session']['last_id'] = encounter.id
        self.settings['session']['last_type'] = 'encounter'
        self.save_settings()

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
        self._push_nav_history('project', project.file_path)

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
        self._push_nav_history('guide', guide.id)

        # Clear current editor
        self.clear_editor()

        # Save selection
        self.settings['session']['last_id'] = guide.id
        self.settings['session']['last_type'] = 'guide'
        self.save_settings()

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

    def show_locations(self, encounter_set):
        """Display location connection editor for an encounter set"""
        self._push_nav_history('locations', encounter_set.id)

        # Clear current editor
        self.clear_editor()

        # Save selection
        self.settings['session']['last_id'] = encounter_set.id
        self.settings['session']['last_type'] = 'locations'
        self.save_settings()

        # Hide preview for non-card views
        self.preview_dock.hide()

        # Clear content layout
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

        # Create and add location view
        from shoggoth.location_view import LocationViewWidget
        self.location_view = LocationViewWidget(encounter_set, self.card_renderer)
        self.location_view.card_selected.connect(self.show_card)
        self.content_layout.addWidget(self.location_view)

        self.status_bar.showMessage(f"Editing locations: {encounter_set.name}")

    def schedule_preview_update(self):
        """Schedule a debounced preview update (400ms delay)"""
        if not self.current_card:
            return
        # Increment version to invalidate any in-progress renders
        self.render_version += 1
        # Restart the debounce timer
        self.render_timer.start(100)

    def _start_background_render(self):
        """Start rendering in background thread"""
        if not self.current_card:
            return

        # Capture current state for the background thread
        card = self.current_card
        version = self.render_version
        bleed = 'mark' if self.config.getboolean('Shoggoth', 'show_bleed', True) else False
        renderer = self.card_renderer

        def render_task():
            try:
                front_image, back_image = renderer.get_card_textures(card, bleed=bleed)
                # Emit result signal (will be handled on main thread)
                self.render_result_signal.emit(version, front_image, back_image)
            except Exception as e:
                # Emit with None images to signal error
                print(f"Render error: {e}")
                self.render_result_signal.emit(version, None, None)

        thread = threading.Thread(target=render_task, daemon=True)
        thread.start()

    @Slot(int, object, object)
    def _handle_render_result(self, version, front_image, back_image):
        """Handle render result on main thread"""
        # Discard stale results
        if version != self.render_version:
            return

        if front_image is not None:
            self.card_preview.set_card_images(front_image, back_image)
        else:
            self.status_bar.showMessage("Error rendering card")

    def update_card_preview(self):
        """Update the card preview immediately (synchronous, for initial load)"""
        if not self.current_card:
            return

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

    def update_card_in_tree(self, card_id):
        """Update a single card's display in the tree (for name/dirty changes)"""
        return self.file_browser.update_card_node(card_id)

    # --- Navigation History (browser-like back/forward) ---

    def _push_nav_history(self, nav_type, nav_id):
        """Push a navigation item to history, truncating any forward history"""
        if self._nav_navigating:
            return  # Don't record history during back/forward navigation

        nav_item = (nav_type, nav_id)

        # Don't add duplicates if we're already at this item
        if self._nav_history and self._nav_index >= 0:
            if self._nav_history[self._nav_index] == nav_item:
                return

        # Truncate forward history
        self._nav_history = self._nav_history[:self._nav_index + 1]

        # Add new item
        self._nav_history.append(nav_item)
        self._nav_index = len(self._nav_history) - 1

    def navigate_back(self):
        """Navigate to the previous item in history"""
        if self._nav_index <= 0:
            return  # Nothing to go back to

        self._nav_index -= 1
        self._navigate_to_history_item(self._nav_history[self._nav_index])

    def navigate_forward(self):
        """Navigate to the next item in history"""
        if self._nav_index >= len(self._nav_history) - 1:
            return  # Nothing to go forward to

        self._nav_index += 1
        self._navigate_to_history_item(self._nav_history[self._nav_index])

    def _navigate_to_history_item(self, nav_item):
        """Navigate to a history item without adding to history"""
        nav_type, nav_id = nav_item
        self._nav_navigating = True
        try:
            if nav_type == 'card':
                card = self.current_project.get_card(nav_id)
                if card:
                    self.show_card(card)
                    self.select_item_in_tree(nav_id)
            elif nav_type == 'encounter':
                encounter = self.current_project.get_encounter_set(nav_id)
                if encounter:
                    self.show_encounter(encounter)
                    self.select_item_in_tree(nav_id)
            elif nav_type == 'project':
                self.show_project(self.current_project)
            elif nav_type == 'guide':
                guide = self.current_project.get_guide(nav_id)
                if guide:
                    self.show_guide(guide)
                    self.select_item_in_tree(nav_id)
            elif nav_type == 'locations':
                encounter = self.current_project.get_encounter_set(nav_id)
                if encounter:
                    self.show_locations(encounter)
        finally:
            self._nav_navigating = False

    def mousePressEvent(self, event):
        """Handle mouse button presses for back/forward navigation"""
        from PySide6.QtCore import Qt
        if event.button() == Qt.BackButton:
            self.navigate_back()
            event.accept()
        elif event.button() == Qt.ForwardButton:
            self.navigate_forward()
            event.accept()
        else:
            super().mousePressEvent(event)

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

            # Update the preview (increment version and start background render immediately)
            self.render_version += 1
            self._start_background_render()

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

    def open_asset_location(self):
        """Open the asset folder in the system file explorer"""
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(asset_dir)))

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
