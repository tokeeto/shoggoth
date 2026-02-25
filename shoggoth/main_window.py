"""
Main window implementation for Shoggoth using PySide6
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QLabel, QMenuBar, QMenu,
    QFileDialog, QMessageBox, QStatusBar, QScrollArea, QDialog,
    QLineEdit, QPushButton, QDialogButtonBox, QTextBrowser
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
from shoggoth.files import defaults_dir, asset_dir, font_dir, overlay_dir, root_dir
from shoggoth.preview_widget import ImprovedCardPreview
from shoggoth.goto_dialog import GotoCardDialog
from shoggoth.encounter_editor import EncounterSetEditor
from shoggoth.i18n import get_available_languages, load_language, get_current_language, tr
from shoggoth.editors import CardEditor


class DraggableTreeWidget(QTreeWidget):
    """Tree widget with custom drag and drop for card organization"""

    def __init__(self, file_browser, parent=None):
        super().__init__(parent)
        self.file_browser = file_browser
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)

    def _get_item_data(self, item):
        """Get the user data from a tree item"""
        if item is None:
            return None
        return item.data(0, Qt.UserRole)

    def _is_ancestor_of(self, potential_ancestor, item):
        """Check if potential_ancestor is an ancestor of item"""
        parent = item.parent()
        while parent is not None:
            if parent is potential_ancestor:
                return True
            parent = parent.parent()
        return False

    def _get_drop_target_type(self, target_item):
        """Determine what kind of drop target this is and return relevant info"""
        if target_item is None:
            return None, None

        data = self._get_item_data(target_item)
        if not data:
            return None, None

        item_type = data.get('type')
        item_data = data.get('data')

        # Non-droppable targets
        if item_type in ('project', 'campaign_cards', 'player_cards', 'guide'):
            return None, None

        # Check for Guides category
        if item_type == 'category' and target_item.text(0) == 'Guides':
            return None, None

        # Encounter set - can drop cards here
        if item_type == 'encounter':
            return 'encounter', item_data

        # Story/Location/Encounter categories under encounter set
        if item_type in ('category', 'locations'):
            if item_data and hasattr(item_data, 'id'):
                # This is a category under an encounter set
                return 'encounter', item_data

        # Class categories (player cards)
        if item_type == 'category':
            cls = data.get('class')
            if cls:
                if cls == 'investigators':
                    return None, None  # Can't drop directly on Investigators
                elif cls == 'other':
                    return 'other', None
                else:
                    return 'class', cls

            # Investigator group
            investigator = data.get('investigator')
            if investigator:
                return 'investigator', investigator

        # Card - check if it's under an encounter or player section
        if item_type == 'card':
            # Can't drop on a card, but could drop on its parent
            return None, None

        return None, None

    def mimeTypes(self):
        return ['application/x-shoggoth-card']

    def mimeData(self, items):
        """Create mime data for dragged items"""
        from PySide6.QtCore import QMimeData, QByteArray
        mime_data = QMimeData()

        # Only allow dragging cards
        card_ids = []
        for item in items:
            data = self._get_item_data(item)
            if data and data.get('type') == 'card':
                card = data.get('data')
                if card:
                    card_ids.append(card.id)

        if card_ids:
            mime_data.setData('application/x-shoggoth-card',
                            QByteArray(','.join(card_ids).encode()))
        return mime_data

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat('application/x-shoggoth-card'):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not event.mimeData().hasFormat('application/x-shoggoth-card'):
            event.ignore()
            return

        target_item = self.itemAt(event.position().toPoint())
        drop_type, _ = self._get_drop_target_type(target_item)

        if drop_type is None:
            event.ignore()
            return

        # Check if dragging onto ancestor
        card_ids = event.mimeData().data('application/x-shoggoth-card').data().decode().split(',')
        for card_id in card_ids:
            node_id = f'card:{card_id}'
            if node_id in self.file_browser._node_map:
                dragged_item = self.file_browser._node_map[node_id]
                if self._is_ancestor_of(target_item, dragged_item):
                    event.ignore()
                    return

        event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat('application/x-shoggoth-card'):
            event.ignore()
            return

        target_item = self.itemAt(event.position().toPoint())
        drop_type, drop_data = self._get_drop_target_type(target_item)

        if drop_type is None:
            event.ignore()
            return

        card_ids = event.mimeData().data('application/x-shoggoth-card').data().decode().split(',')

        for card_id in card_ids:
            # Find the project that contains this card
            card = None
            for project in self.file_browser._projects:
                card = project.get_card(card_id)
                if card:
                    break

            if not card:
                continue

            # Check ancestor constraint
            node_id = f'card:{card_id}'
            if node_id in self.file_browser._node_map:
                dragged_item = self.file_browser._node_map[node_id]
                if self._is_ancestor_of(target_item, dragged_item):
                    continue

            # Apply the drop action
            if drop_type == 'encounter':
                # Moving to an encounter set
                card.set('encounter_set', drop_data.id)

            elif drop_type == 'class':
                # Moving to a class category
                card.set('encounter_set', None)
                card.set('investigator', None)
                card.front.set('classes', [drop_data])
                if card.back.get('type') == 'encounter':
                    card.back.set('type', 'player')

            elif drop_type == 'other':
                # Moving to "Other" category
                card.set('encounter_set', None)
                card.set('investigator', None)
                card.front.set('classes', ['guardian', 'seeker'])
                if card.back.get('type') == 'encounter':
                    card.back.set('type', 'player')

            elif drop_type == 'investigator':
                # Moving to an investigator group
                card.set('encounter_set', None)
                card.set('investigator', drop_data)

        # Refresh the tree to reflect changes
        # Use accept() instead of acceptProposedAction() to prevent Qt from
        # performing its own item move - we handle tree updates via refresh_tree()
        event.accept()
        shoggoth.app.refresh_tree()


class FileBrowser(QWidget):
    """File browser widget showing project files"""

    card_selected = Signal(object)  # Emits card object
    encounter_selected = Signal(object)  # Emits encounter object
    project_selected = Signal(object)  # Emits project object
    guide_selected = Signal(object)  # Emits guide object
    locations_selected = Signal(object)  # Emits encounter set for location view
    active_project_changed = Signal(object)  # Emits project when active project changes

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout()

        # Title
        title = QLabel(tr("TREE_CARDS"))
        title.setStyleSheet("font-size: 20pt; font-weight: bold;")
        layout.addWidget(title)

        # Tree widget with drag and drop support
        self.tree = DraggableTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self.on_item_clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.on_context_menu)
        layout.addWidget(self.tree)

        self.setLayout(layout)
        self._projects = []  # List of open projects
        self._active_project = None  # The active project for operations
        self._node_map = {}  # Maps node_id -> QTreeWidgetItem for fast lookup

        # Context menu handler
        from shoggoth.tree_context_menu import TreeContextMenu
        self.context_menu = TreeContextMenu(self)

    @property
    def _project(self):
        """Compatibility property - returns active project"""
        return self._active_project

    def set_project(self, project):
        """Set a single project (clears others) - for backward compatibility"""
        self._projects = [project] if project else []
        self._active_project = project
        self._node_map.clear()
        self._full_rebuild()

    def add_project(self, project):
        """Add a project to the browser. If first project, make it active."""
        if project in self._projects:
            # Already open - just make it active
            self.set_active_project(project)
            return

        self._projects.append(project)
        if self._active_project is None:
            self._active_project = project

        self._full_rebuild()
        self.active_project_changed.emit(self._active_project)

    def remove_project(self, project):
        """Remove a project from the browser"""
        if project not in self._projects:
            return

        self._projects.remove(project)

        # If we removed the active project, select another
        if self._active_project == project:
            self._active_project = self._projects[0] if self._projects else None
            self.active_project_changed.emit(self._active_project)

        self._full_rebuild()

    def set_active_project(self, project):
        """Set the active project for operations"""
        if project not in self._projects:
            return
        if self._active_project == project:
            return

        self._active_project = project
        self._update_active_project_display()
        self.active_project_changed.emit(project)

    def _update_active_project_display(self):
        """Update visual indicators for active project"""
        # Update all project nodes to show/hide bold
        for project in self._projects:
            node_id = f'project:{project.file_path}'
            if node_id in self._node_map:
                item = self._node_map[node_id]
                font = item.font(0)
                font.setBold(project == self._active_project)
                item.setFont(0, font)

    def get_project_for_card(self, card):
        """Find which project a card belongs to"""
        for project in self._projects:
            if project.get_card(card.id):
                return project
        return None

    def refresh(self):
        """Smart refresh - only update what has changed"""
        if not self._projects:
            self.tree.clear()
            self._node_map.clear()
            return

        # If tree is empty, do a full rebuild
        if self.tree.topLevelItemCount() == 0:
            self._full_rebuild()
            return

        # Build desired tree specification for all projects
        desired_specs = self._build_all_tree_specs()

        # Remove extra projects if any were closed
        while self.tree.topLevelItemCount() > len(desired_specs):
            removed_item = self.tree.takeTopLevelItem(self.tree.topLevelItemCount() - 1)
            self._remove_from_node_map(removed_item)

        # Apply incremental updates to each project root
        for i, spec in enumerate(desired_specs):
            if i < self.tree.topLevelItemCount():
                root_item = self.tree.topLevelItem(i)
                self._sync_tree_node(root_item, spec)
            else:
                # New project added
                root_item = self._create_tree_item(spec)
                self.tree.addTopLevelItem(root_item)
                root_item.setExpanded(True)

    def _full_rebuild(self):
        """Do a complete tree rebuild (used for initial load or project change)"""
        self.tree.clear()
        self._node_map.clear()

        if not self._projects:
            return

        for project in self._projects:
            spec = self._build_tree_spec(project)
            root_item = self._create_tree_item(spec)
            self.tree.addTopLevelItem(root_item)
            root_item.setExpanded(True)

            # Set bold for active project
            if project == self._active_project:
                font = root_item.font(0)
                font.setBold(True)
                root_item.setFont(0, font)

    def _build_all_tree_specs(self):
        """Build tree specs for all open projects"""
        return [self._build_tree_spec(project) for project in self._projects]

    def _build_tree_spec(self, project=None):
        """Build a specification of the desired tree state"""
        if project is None:
            project = self._active_project
        if not project:
            return None

        # Root node
        root_spec = {
            'node_id': f'project:{project.file_path}',
            'text': project['name'],
            'type': 'project',
            'data': project,
            'icon': None,
            'children': []
        }

        # Determine if we need campaign/player split
        has_encounters = bool(project.encounter_sets)
        has_player_cards = any(c for c in project.cards if not c.encounter)

        if has_encounters and has_player_cards:
            campaign_spec = {
                'node_id': f'category:campaign_cards:{project.file_path}',
                'text': tr('TREE_CAMPAIGN_CARDS'),
                'type': 'campaign_cards',
                'data': project,
                'icon': None,
                'children': []
            }
            player_spec = {
                'node_id': f'category:player_cards:{project.file_path}',
                'text': tr('TREE_PLAYER_CARDS'),
                'type': 'player_cards',
                'data': project,
                'icon': None,
                'children': []
            }
            root_spec['children'].append(campaign_spec)
            root_spec['children'].append(player_spec)
        else:
            campaign_spec = player_spec = root_spec

        # Add encounter sets
        for encounter_set in project.encounter_sets:
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
                'text': tr('TREE_STORY'),
                'type': 'category',
                'data': encounter_set,
                'icon': None,
                'children': []
            }
            location_spec = {
                'node_id': f'locations:{encounter_set.name}',
                'text': tr('TREE_LOCATIONS'),
                'type': 'locations',
                'data': encounter_set,
                'icon': None,
                'children': []
            }
            encounter_cat_spec = {
                'node_id': f'category:{encounter_set.name}:encounter',
                'text': tr('TREE_ENCOUNTER'),
                'type': 'category',
                'data': encounter_set,
                'icon': None,
                'children': []
            }
            # Add cards to appropriate categories
            for card in encounter_set.cards:
                card_spec = self._build_card_spec(card)

                if card.front.get('type') == 'location':
                    location_spec['children'].append(card_spec)
                elif card.back.get('type') == 'encounter':
                    encounter_cat_spec['children'].append(card_spec)
                else:
                    story_spec['children'].append(card_spec)

            # If only encounter cards exist (no story or location), show cards directly
            if not story_spec['children'] and not location_spec['children']:
                e_spec['children'] = encounter_cat_spec['children']
            else:
                e_spec['children'] = [story_spec, location_spec, encounter_cat_spec]

            campaign_spec['children'].append(e_spec)

        # Add player cards
        class_labels = {
            'investigators': tr('TREE_INVESTIGATORS'),
            'seeker': tr('CLASS_SEEKER'),
            'rogue': tr('CLASS_ROGUE'),
            'guardian': tr('CLASS_GUARDIAN'),
            'mystic': tr('CLASS_MYSTIC'),
            'survivor': tr('CLASS_SURVIVOR'),
            'neutral': tr('CLASS_NEUTRAL'),
            'other': tr('CLASS_OTHER'),
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
                'node_id': f'class:{cls}:{project.file_path}',
                'text': class_labels[cls],
                'type': 'category',
                'data': project,
                'class': cls,
                'icon': icon_path,
                'children': []
            }
            class_specs[cls] = class_spec
            player_spec['children'].append(class_spec)

        investigator_specs = {}

        for card in project.player_cards:
            if group := card.data.get('investigator', False):
                if group not in investigator_specs:
                    inv_spec = {
                        'node_id': f'investigator:{group}:{project.file_path}',
                        'text': group,
                        'type': 'category',
                        'data': project,
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
        if project.guides:
            guide_parent = {
                'node_id': f'category:guides:{project.file_path}',
                'text': tr('TREE_GUIDES'),
                'type': 'category',
                'data': project,
                'icon': None,
                'children': []
            }
            for guide in project.guides:
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
        user_data = {'type': spec['type'], 'data': spec['data'], 'node_id': spec['node_id']}
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
        user_data = {'type': spec['type'], 'data': spec['data'], 'node_id': spec['node_id']}
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

        # Use the stored node_id if available (avoids depending on translated display text)
        if 'node_id' in data:
            return data['node_id']

        item_type = data.get('type')
        item_data = data.get('data')

        # Get project path for unique IDs
        project_path = ''
        if item_data and hasattr(item_data, 'file_path'):
            project_path = item_data.file_path
        elif item_data and hasattr(item_data, 'expansion') and item_data.expansion:
            project_path = item_data.expansion.file_path

        if item_type == 'card' and item_data:
            return f'card:{item_data.id}'
        elif item_type == 'guide' and item_data:
            return f'guide:{item_data.id}'
        elif item_type == 'encounter' and item_data:
            return f'encounter:{item_data.name}'
        elif item_type == 'project' and item_data:
            return f'project:{item_data.file_path}'
        elif item_type == 'locations' and item_data:
            return f'locations:{item_data.name}'
        elif item_type == 'campaign_cards' and item_data:
            return f'category:campaign_cards:{item_data.file_path}'
        elif item_type == 'player_cards' and item_data:
            return f'category:player_cards:{item_data.file_path}'
        elif item_type == 'category':
            if data.get('class') and item_data:
                return f'class:{data["class"]}:{item_data.file_path}'
            elif data.get('investigator') and item_data:
                return f'investigator:{data["investigator"]}:{item_data.file_path}'
            elif item_data and hasattr(item_data, 'file_path'):
                # Project-level category (Guides) - item_data is Project
                if item.text(0) == 'Guides':
                    return f'category:guides:{item_data.file_path}'
            elif item_data and hasattr(item_data, 'name') and not hasattr(item_data, 'file_path'):
                # Encounter subcategory (Story/Encounter) - item_data is EncounterSet (no file_path)
                text = item.text(0).lower()
                return f'category:{item_data.name}:{text}'
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
            # Clicking a project sets it as active
            self.set_active_project(item_data)
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

        self.setWindowTitle(tr("APP_TITLE"))
        self.setMinimumSize(1400, 900)

        # Set application icon
        icon_path = asset_dir / "elder_sign_neon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Initialize components
        self.open_projects = []  # List of all open projects
        self.active_project = None  # The currently active project
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

        # Initialize update manager (before setup_ui so menu can reference it)
        from shoggoth.updater import UpdateManager
        self.update_manager = UpdateManager(self.config, self)

        # Setup UI
        self.setup_ui()

        # Setup file monitoring
        self.setup_file_monitoring()

        # Restore session
        self.restore_session()

        # Check for updates after UI is ready (deferred)
        QTimer.singleShot(2000, self._check_for_updates_startup)

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
        self.file_browser.active_project_changed.connect(self._on_active_project_changed)
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
        self.editor_widget = QLabel(tr("MSG_OPEN_OR_CREATE"))
        self.editor_widget.setAlignment(Qt.AlignCenter)
        self.editor_container.setWidget(self.editor_widget)

        # Preview container (detachable)
        from PySide6.QtWidgets import QDockWidget
        self.preview_dock = QDockWidget(tr("CARD_PREVIEW"), self)
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
        self.status_bar.showMessage(tr("STATUS_READY"))

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
        if not self.active_project:
            QMessageBox.information(self, tr("DLG_NO_PROJECT"), tr("MSG_OPEN_PROJECT_FIRST"))
            return

        dialog = GotoCardDialog(self.active_project, self)
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
        file_menu = menubar.addMenu(tr("MENU_FILE"))

        # Open Project
        open_action = QAction(tr("MENU_OPEN_PROJECT"), self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_project_dialog)
        file_menu.addAction(open_action)

        # New Project
        new_action = QAction(tr("MENU_NEW_PROJECT"), self)
        new_action.triggered.connect(self.new_project_dialog)
        file_menu.addAction(new_action)

        # Close Project
        close_project_action = QAction(tr("MENU_CLOSE_PROJECT"), self)
        close_project_action.triggered.connect(lambda: self.close_project())
        file_menu.addAction(close_project_action)

        file_menu.addSeparator()

        # Save
        save_action = QAction(tr("MENU_SAVE"), self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_changes)
        file_menu.addAction(save_action)

        # New Card
        new_card_action = QAction(tr("MENU_NEW_CARD"), self)
        new_card_action.setShortcut("Ctrl+N")
        new_card_action.triggered.connect(self.new_card_dialog)
        file_menu.addAction(new_card_action)

        # Go to Card
        goto_card_action = QAction(tr("MENU_GOTO_CARD"), self)
        goto_card_action.setShortcut("Ctrl+P")
        goto_card_action.triggered.connect(self.show_goto_dialog)
        file_menu.addAction(goto_card_action)

        file_menu.addSeparator()

        # Gather images
        gather_action = QAction(tr("MENU_GATHER_IMAGES"), self)
        gather_action.triggered.connect(self.gather_images)
        file_menu.addAction(gather_action)

        gather_update_action = QAction(tr("MENU_GATHER_UPDATE"), self)
        gather_update_action.triggered.connect(lambda: self.gather_images(update=True))
        file_menu.addAction(gather_update_action)

        file_menu.addSeparator()

        # Export Current Card
        export_current = QAction(tr("MENU_EXPORT_CURRENT"), self)
        export_current.setShortcut("Ctrl+E")
        export_current.triggered.connect(lambda: self.export_current())
        file_menu.addAction(export_current)

        # Export All Cards
        export_all = QAction(tr("MENU_EXPORT_ALL"), self)
        export_all.setShortcut("Ctrl+Shift+E")
        export_all.triggered.connect(self.export_all)
        file_menu.addAction(export_all)

        file_menu.addSeparator()

        # Settings
        settings_action = QAction(tr("MENU_SETTINGS"), self)
        settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(settings_action)

        file_menu.addSeparator()

        # Exit
        exit_action = QAction(tr("MENU_EXIT"), self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # ==================== PROJECT MENU ====================
        project_menu = menubar.addMenu(tr("MENU_PROJECT"))

        # Add Guide
        auto_enumerate_action = QAction(tr("MENU_AUTO_ENUMERATE"), self)
        auto_enumerate_action.setShortcut("Ctrl+M")
        auto_enumerate_action.triggered.connect(self.auto_enumerate)
        project_menu.addAction(auto_enumerate_action)

        # Add Guide
        add_guide_action = QAction(tr("MENU_ADD_GUIDE"), self)
        add_guide_action.triggered.connect(self.add_guide)
        project_menu.addAction(add_guide_action)

        # Add Scenario template
        add_scenario_action = QAction(tr("MENU_ADD_SCENARIO"), self)
        add_scenario_action.triggered.connect(self.add_scenario_template)
        project_menu.addAction(add_scenario_action)

        # Add Campaign template
        add_campaign_action = QAction(tr("MENU_ADD_CAMPAIGN"), self)
        add_campaign_action.triggered.connect(self.add_campaign_template)
        project_menu.addAction(add_campaign_action)

        # Add Investigator template
        add_investigator_action = QAction(tr("MENU_ADD_INVESTIGATOR"), self)
        add_investigator_action.triggered.connect(self.add_investigator_template)
        project_menu.addAction(add_investigator_action)

        # Add Investigator Expansion template
        add_inv_exp_action = QAction(tr("MENU_ADD_INV_EXPANSION"), self)
        add_inv_exp_action.triggered.connect(self.add_investigator_expansion_template)
        project_menu.addAction(add_inv_exp_action)

        # ==================== EXPORT MENU ====================
        export_menu = menubar.addMenu(tr("MENU_EXPORT"))

        # Card To PDF
        card_pdf_action = QAction(tr("MENU_CARD_TO_PDF"), self)
        card_pdf_action.triggered.connect(self.export_card_to_pdf)
        export_menu.addAction(card_pdf_action)

        # Cards To PDF
        cards_pdf_action = QAction(tr("MENU_CARDS_TO_PDF"), self)
        cards_pdf_action.triggered.connect(self.export_cards_to_pdf)
        export_menu.addAction(cards_pdf_action)

        # Project To PDF
        project_pdf_action = QAction(tr("MENU_PROJECT_TO_PDF"), self)
        project_pdf_action.triggered.connect(self.export_project_to_pdf)
        export_menu.addAction(project_pdf_action)

        export_menu.addSeparator()

        # Export card to TTS object
        tts_card_action = QAction(tr("MENU_EXPORT_TTS_CARD"), self)
        tts_card_action.triggered.connect(self.export_card_to_tts)
        export_menu.addAction(tts_card_action)

        # Export all campaign cards to TTS object
        tts_campaign_action = QAction(tr("MENU_EXPORT_TTS_CAMPAIGN"), self)
        tts_campaign_action.triggered.connect(self.export_campaign_to_tts)
        export_menu.addAction(tts_campaign_action)

        # Export all player cards to TTS object
        tts_player_action = QAction(tr("MENU_EXPORT_TTS_PLAYER"), self)
        tts_player_action.triggered.connect(self.export_player_to_tts)
        export_menu.addAction(tts_player_action)

        # ==================== TOOLS MENU ====================
        tools_menu = menubar.addMenu(tr("MENU_TOOLS"))

        # Convert SE Project
        convert_se_action = QAction(tr("MENU_CONVERT_SE"), self)
        convert_se_action.triggered.connect(self.convert_strange_eons)
        tools_menu.addAction(convert_se_action)

        tools_menu.addSeparator()

        # Check for Updates
        check_updates_action = QAction(tr("MENU_CHECK_UPDATES"), self)
        check_updates_action.triggered.connect(self.update_manager.check_for_updates_manual)
        tools_menu.addAction(check_updates_action)

        # ==================== HELP MENU ====================
        help_menu = menubar.addMenu(tr("MENU_HELP"))

        # Text options
        text_options_action = QAction(tr("MENU_TEXT_OPTIONS"), self)
        text_options_action.triggered.connect(self.show_text_options)
        help_menu.addAction(text_options_action)

        # About
        about_action = QAction(tr("MENU_ABOUT"), self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        asset_location_action = QAction(tr("MENU_ASSET_LOCATION"), self)
        asset_location_action.triggered.connect(self.open_asset_location)
        help_menu.addAction(asset_location_action)

        # View menu
        view_menu = menubar.addMenu(tr("MENU_VIEW"))

        # Toggle Preview
        self.toggle_preview_action = QAction(tr("MENU_SHOW_PREVIEW"), self)
        self.toggle_preview_action.setCheckable(True)
        self.toggle_preview_action.setChecked(False)
        self.toggle_preview_action.triggered.connect(self.toggle_preview)
        view_menu.addAction(self.toggle_preview_action)

        # ==================== LANGUAGE MENU ====================
        language_menu = menubar.addMenu(tr("MENU_LANGUAGE"))
        self.language_actions = []
        
        available_languages = get_available_languages()
        current_lang = self.config.get('Shoggoth', 'language', 'en')
        
        for lang_code, lang_name in available_languages.items():
            action = QAction(lang_name, self)
            action.setCheckable(True)
            action.setChecked(lang_code == current_lang)
            action.setData(lang_code)
            action.triggered.connect(lambda checked, code=lang_code: self.change_language(code))
            language_menu.addAction(action)
            self.language_actions.append(action)

    def toggle_preview(self, checked):
        """Toggle the preview dock visibility"""
        if checked:
            self.preview_dock.show()
        else:
            self.preview_dock.hide()

    def change_language(self, lang_code: str):
        """Change the application language"""
        # Update checkmarks in menu
        for action in self.language_actions:
            action.setChecked(action.data() == lang_code)
        
        # Save setting
        self.config.set('Shoggoth', 'language', lang_code)
        self.config.save()
        
        # Load the new language
        load_language(lang_code)
        
        # Show restart message
        QMessageBox.information(
            self,
            tr("DLG_LANGUAGE_CHANGED"),
            tr("MSG_RESTART_FOR_LANGUAGE")
        )

    def load_settings(self):
        """Load application settings"""
        settings_file = root_dir / 'shoggoth.json'
        if settings_file.exists():
            with open(settings_file, 'r') as f:
                self.settings = json.load(f)
        else:
            self.settings = {'session': {}, 'last_paths': {}}

    def save_settings(self):
        """Save application settings"""
        with open(root_dir / 'shoggoth.json', 'w') as f:
            json.dump(self.settings, f)

    def setup_file_monitoring(self):
        """Setup file system monitoring for assets and card files"""
        self.card_file_monitor = CardFileMonitor(asset_dir, self.on_file_changed)
        self.card_file_monitor.start()

    def restore_session(self):
        """Restore previous session"""
        session = self.settings.get('session', {})

        # Support for multiple open projects
        open_project_paths = session.get('open_projects', [])
        active_project_path = session.get('active_project', session.get('project'))

        # Fallback to single project if no list exists
        if not open_project_paths and active_project_path:
            open_project_paths = [active_project_path]

        for project_path in open_project_paths:
            try:
                self.open_project(project_path)
            except Exception as e:
                print(f"Error restoring project {project_path}: {e}")

        # Set the active project
        if active_project_path:
            for project in self.open_projects:
                if project.file_path == active_project_path:
                    self.file_browser.set_active_project(project)
                    break

        # Restore last selected element
        if last_id := session.get('last_id'):
            last_type = session.get('last_type', 'card')
            QTimer.singleShot(100, lambda: self._restore_last_element(last_id, last_type))

    def _save_session(self):
        """Save current session state"""
        self.settings['session']['open_projects'] = [p.file_path for p in self.open_projects]
        self.settings['session']['active_project'] = self.active_project.file_path if self.active_project else None
        # Keep legacy 'project' key for backward compatibility
        self.settings['session']['project'] = self.active_project.file_path if self.active_project else None
        self.save_settings()

    def _restore_last_element(self, element_id, element_type):
        """Restore the last selected element by ID and type"""
        if not self.active_project:
            return

        element = None
        if element_type == 'card':
            element = self.active_project.get_card(element_id)
            if element:
                self.show_card(element)
        elif element_type == 'encounter':
            element = self.active_project.get_encounter_set(element_id)
            if element:
                self.show_encounter(element)
        elif element_type == 'guide':
            element = self.active_project.get_guide(element_id)
            if element:
                self.show_guide(element)
        elif element_type == 'locations':
            element = self.active_project.get_encounter_set(element_id)
            if element:
                self.show_locations(element)

        # Select in tree if element was found
        if element:
            self.select_item_in_tree(element_id)

    def _check_for_updates_startup(self):
        """Check for updates after startup (deferred to avoid blocking)"""
        if self.update_manager.should_check_for_updates():
            self.update_manager.check_for_updates_async()

    def open_project_dialog(self):
        """Show dialog to open a project"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            tr("DLG_OPEN_PROJECT"),
            str(Path.home()),
            tr("FILTER_SHOGGOTH_PROJECTS")
        )
        if file_path:
            self.open_project(file_path)

    def open_project(self, file_path):
        """Open a project file"""
        try:
            # Check if project is already open
            for project in self.open_projects:
                if project.file_path == file_path:
                    # Already open - just make it active
                    self.file_browser.set_active_project(project)
                    self.status_bar.showMessage(tr("STATUS_SWITCHED_TO").format(name=project['name']))
                    return

            # Load new project
            project = Project.load(file_path)
            self.open_projects.append(project)
            self.active_project = project
            self.file_browser.add_project(project)
            self._save_session()
            # Clear navigation history for new project
            self._nav_history.clear()
            self._nav_index = -1
            self.status_bar.showMessage(tr("STATUS_OPENED").format(name=project['name']))
        except Exception as e:
            QMessageBox.critical(self, tr("DLG_ERROR"), tr("ERR_OPEN_PROJECT").format(error=e))

    def close_project(self, project=None):
        """Close a project"""
        if project is None:
            project = self.active_project
        if project is None:
            return

        # Check for unsaved changes in this project
        if self._project_has_unsaved_changes(project):
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle(tr("DLG_UNSAVED_CHANGES"))
            msg_box.setText(tr("CONFIRM_SAVE_BEFORE_CLOSE").format(name=project['name']))
            msg_box.setIcon(QMessageBox.Question)
            save_btn = msg_box.addButton(tr("DLG_SAVE"), QMessageBox.AcceptRole)
            discard_btn = msg_box.addButton(tr("DLG_DISCARD"), QMessageBox.DestructiveRole)
            cancel_btn = msg_box.addButton(tr("DLG_CANCEL"), QMessageBox.RejectRole)
            msg_box.setDefaultButton(save_btn)
            msg_box.exec()
            
            if msg_box.clickedButton() == save_btn:
                project.save()
            elif msg_box.clickedButton() == cancel_btn:
                return

        # Remove from open projects
        if project in self.open_projects:
            self.open_projects.remove(project)

        # Update file browser
        self.file_browser.remove_project(project)

        # Update active project
        if self.active_project == project:
            self.active_project = self.open_projects[0] if self.open_projects else None

        self._save_session()
        self.status_bar.showMessage(tr("STATUS_CLOSED").format(name=project['name']))

    def _project_has_unsaved_changes(self, project):
        """Check if a specific project has unsaved changes"""
        for card in project.get_all_cards():
            if hasattr(card, 'dirty') and card.dirty:
                return True
        return False

    def _on_active_project_changed(self, project):
        """Handle active project change from file browser"""
        self.active_project = project
        if project:
            self.status_bar.showMessage(tr("STATUS_ACTIVE").format(name=project['name']))

    @property
    def current_project(self):
        """Backward compatibility property"""
        return self.active_project

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
        if not self.active_project:
            return

        try:
            self.active_project.save()

            # Mark all cards as clean
            for card in self.active_project.get_all_cards():
                card.dirty = False
                if hasattr(card, 'front') and hasattr(card.front, 'dirty'):
                    card.front.dirty = False
                if hasattr(card, 'back') and hasattr(card.back, 'dirty'):
                    card.back.dirty = False

            # Update tree to remove dirty indicators
            self.file_browser.refresh()

            self.status_bar.showMessage(tr("STATUS_SAVED"), 3000)
        except Exception as e:
            QMessageBox.critical(self, tr("DLG_SAVE_ERROR"), tr("ERR_SAVE_PROJECT").format(error=e))

    def save_current(self):
        """Save only the current card"""
        if not self.current_card:
            return

        try:
            self.current_card.save()
            # Note: Card.save() already clears dirty flags and updates tree node
            self.status_bar.showMessage(tr("STATUS_SAVED_NAME").format(name=self.current_card.name), 3000)
        except Exception as e:
            QMessageBox.critical(self, tr("DLG_SAVE_ERROR"), tr("ERR_SAVE_CARD").format(error=e))

    def _get_export_size(self):
        """Return the size dict selected in export settings."""
        from shoggoth.settings import EXPORT_SIZES
        index = self.config.getint('Shoggoth', 'export_size', 1)
        index = min(index, len(EXPORT_SIZES) - 1)
        return EXPORT_SIZES[index][1]

    def export_all(self, bleed=None, format=None, quality=None, separate_versions=None):
        """Export all cards in the project using settings from preferences"""
        if not self.active_project:
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_LOADED"))
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
            export_folder = Path(self.active_project.file_path).parent / f'Export of {self.active_project.name}'
            export_folder.mkdir(parents=True, exist_ok=True)

            cards = self.active_project.get_all_cards()

            # Show progress
            from PySide6.QtWidgets import QProgressDialog
            progress = QProgressDialog(
                tr("STATUS_EXPORTING"), tr("BTN_CANCEL"), 0, len(cards), self
            )
            progress.setWindowModality(Qt.WindowModal)

            # Export each card
            import threading
            threads = []
            for i, card in enumerate(cards):
                if progress.wasCanceled():
                    break

                progress.setValue(i)
                progress.setLabelText(tr("MSG_EXPORTING_CARD").format(name=card.name))

                # Export in thread
                thread = threading.Thread(
                    target=self.card_renderer.export_card_images,
                    args=(card, str(export_folder)),
                    kwargs={
                        'size': self._get_export_size(),
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
                tr("DLG_EXPORT_COMPLETE"),
                tr("MSG_EXPORTED_CARDS").format(count=len(cards), folder=export_folder)
            )
        except Exception as e:
            QMessageBox.critical(self, tr("DLG_EXPORT_ERROR"), tr("ERR_EXPORT_CARDS").format(error=e))

    def new_card_dialog(self):
        """Show dialog to create a new card"""
        if not self.active_project:
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
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
        self._save_session()

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
        card_splitter.setSizes([200, 200])

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
        self._save_session()

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
        self.status_bar.showMessage(tr("STATUS_EDITING_ENCOUNTER_SET").format(name=encounter.name))

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
        self.status_bar.showMessage(tr("STATUS_EDITING_PROJECT").format(name=project['name']))

    def show_guide(self, guide):
        """Display guide editor"""
        self._push_nav_history('guide', guide.id)

        # Clear current editor
        self.clear_editor()

        # Save selection
        self.settings['session']['last_id'] = guide.id
        self.settings['session']['last_type'] = 'guide'
        self._save_session()

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
        self._save_session()

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

        self.status_bar.showMessage(tr("STATUS_EDITING_LOCATIONS").format(name=encounter_set.name))

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
                front_image, back_image = renderer.get_card_textures(
                    card, {'width': 750, 'height': 1050, 'bleed': 36}, bleed=bleed
                )
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
            self.status_bar.showMessage(tr("ERR_RENDER_CARD"))

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
                self.current_card, {'width': 750, 'height': 1050, 'bleed': 36}, bleed=bleed
            )
            self.card_preview.set_card_images(front_image, back_image)
        except Exception as e:
            self.status_bar.showMessage(tr("ERR_RENDER_CARD_DETAIL").format(error=e))

    def goto_card(self, card_id):
        """Navigate to a specific card by ID"""
        if not self.active_project:
            return

        card = self.active_project.get_card(card_id)
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
                card = self.active_project.get_card(nav_id)
                if card:
                    self.show_card(card)
                    self.select_item_in_tree(nav_id)
            elif nav_type == 'encounter':
                encounter = self.active_project.get_encounter_set(nav_id)
                if encounter:
                    self.show_encounter(encounter)
                    self.select_item_in_tree(nav_id)
            elif nav_type == 'project':
                self.show_project(self.active_project)
            elif nav_type == 'guide':
                guide = self.active_project.get_guide(nav_id)
                if guide:
                    self.show_guide(guide)
                    self.select_item_in_tree(nav_id)
            elif nav_type == 'locations':
                encounter = self.active_project.get_encounter_set(nav_id)
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
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("MSG_NO_CARD_SELECTED"))
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
            export_folder = Path(self.active_project.file_path).parent / f'Export of {self.active_project.name}'
            export_folder.mkdir(parents=True, exist_ok=True)

            # Export card
            self.card_renderer.export_card_images(
                self.current_card,
                str(export_folder),
                size=self._get_export_size(),
                include_backs=False,
                bleed=bleed,
                format=format,
                quality=quality,
                separate_versions=separate_versions
            )

            QMessageBox.information(
                self,
                tr("DLG_EXPORT_COMPLETE"),
                tr("MSG_CARD_EXPORTED").format(folder=export_folder)
            )
        except Exception as e:
            QMessageBox.critical(self, tr("DLG_EXPORT_ERROR"), tr("ERR_EXPORT_CARD").format(error=e))

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
            <p style="font-size: 14pt; color: #666;">{tr("ABOUT_VERSION").format(version=app_version)}</p>
        </div>
        <hr>
        <p>{tr("ABOUT_CREATED_BY")}</p>
        <p>{tr("ABOUT_SUPPORT_TEXT").format(
            contributing=f'<a href="{urls["contrib"]}">{tr("ABOUT_CONTRIBUTING")}</a>',
            donating=f'<a href="{urls["patreon"]}">{tr("ABOUT_DONATING")}</a>',
            tipping=f'<a href="{urls["tips"]}">{tr("ABOUT_TIPPING")}</a>'
        )}</p>
        <p>{tr("ABOUT_IMAGES_CREDIT")}</p>
        <p>{tr("ABOUT_THANKS_SE")}</p>
        <p>{tr("ABOUT_SPECIAL_THANKS")}</p>
        """

        dialog = QDialog(self)
        dialog.setWindowTitle(tr("DLG_ABOUT_TITLE"))
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
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle(tr("DLG_UNSAVED_CHANGES"))
            msg_box.setText(tr("CONFIRM_SAVE_BEFORE_EXIT"))
            msg_box.setIcon(QMessageBox.Question)
            save_btn = msg_box.addButton(tr("DLG_SAVE"), QMessageBox.AcceptRole)
            discard_btn = msg_box.addButton(tr("DLG_DISCARD"), QMessageBox.DestructiveRole)
            cancel_btn = msg_box.addButton(tr("DLG_CANCEL"), QMessageBox.RejectRole)
            msg_box.setDefaultButton(save_btn)
            msg_box.exec()

            if msg_box.clickedButton() == save_btn:
                self.save_changes()
                event.accept()
            elif msg_box.clickedButton() == discard_btn:
                event.accept()
            else:  # Cancel
                event.ignore()
        else:
            event.accept()

    def has_unsaved_changes(self):
        """Check if there are any unsaved changes in the project"""
        if not self.active_project:
            return False

        for card in self.active_project.get_all_cards():
            if hasattr(card, 'dirty') and card.dirty:
                return True
            if hasattr(card, 'front') and hasattr(card.front, 'dirty') and card.front.dirty:
                return True
            if hasattr(card, 'back') and hasattr(card.back, 'dirty') and card.back.dirty:
                return True

        return False

    # ==================== PROJECT MENU ACTIONS ====================

    def auto_enumerate(self):
        """Add a guide to the project"""
        if not self.active_project:
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
            return
        self.active_project.assign_card_numbers()
        self.status_bar.showMessage(tr("STATUS_PROJECT_ENUMERATED"))

    def add_guide(self):
        """Add a guide to the project"""
        if not self.active_project:
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
            return
        self.active_project.add_guide()
        self.file_browser.refresh()
        self.status_bar.showMessage(tr("STATUS_GUIDE_ADDED"))

    def add_scenario_template(self):
        """Add a scenario template"""
        if not self.active_project:
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
            return
        name, ok = self.get_text_input(tr("DLG_SCENARIO_NAME"), tr("MSG_ENTER_SCENARIO"), tr("PLACEHOLDER_SCENARIO"))
        if ok and name:
            self.active_project.create_scenario(name)
            self.file_browser.refresh()
            self.status_bar.showMessage(tr("STATUS_SCENARIO_CREATED").format(name=name))

    def add_campaign_template(self):
        """Add a campaign template"""
        if not self.active_project:
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
            return
        self.active_project.create_campaign()
        self.file_browser.refresh()
        self.status_bar.showMessage(tr("STATUS_CAMPAIGN_CREATED"))

    def add_investigator_template(self):
        """Add an investigator template"""
        if not self.active_project:
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
            return
        name, ok = self.get_text_input(tr("DLG_INVESTIGATOR_NAME"), tr("MSG_ENTER_INVESTIGATOR"), tr("PLACEHOLDER_ROLAN"))
        if ok and name:
            self.active_project.add_investigator_set(name)
            self.file_browser.refresh()
            self.status_bar.showMessage(tr("STATUS_INVESTIGATOR_CREATED").format(name=name))

    def add_investigator_expansion_template(self):
        """Add an investigator expansion template"""
        if not self.active_project:
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
            return
        self.active_project.create_player_expansion()
        self.file_browser.refresh()
        self.status_bar.showMessage(tr("STATUS_EXPANSION_CREATED"))

    # ==================== EXPORT MENU ACTIONS ====================

    def export_card_to_pdf(self):
        """Export current card to PDF"""
        if not self.current_card:
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("MSG_NO_CARD_SELECTED"))
            return
        # TODO: Implement PDF export
        QMessageBox.information(self, tr("DLG_TODO"), tr("MSG_PDF_NOT_IMPLEMENTED"))

    def export_cards_to_pdf(self):
        """Export all cards to PDF"""
        if not self.active_project:
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
            return
        # TODO: Implement PDF export
        QMessageBox.information(self, tr("DLG_TODO"), tr("MSG_PDF_NOT_IMPLEMENTED"))

    def export_project_to_pdf(self):
        """Export entire project to PDF"""
        if not self.active_project:
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
            return
        # TODO: Implement PDF export
        QMessageBox.information(self, tr("DLG_TODO"), tr("MSG_PDF_NOT_IMPLEMENTED"))

    def export_card_to_tts(self):
        """Export card to Tabletop Simulator"""
        if not self.current_card:
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("MSG_NO_CARD_SELECTED"))
            return
        try:
            from shoggoth import tts_lib
            tts_lib.export_card(self.current_card)
            self.status_bar.showMessage(tr("STATUS_TTS_CARD_EXPORTED"))
        except Exception as e:
            QMessageBox.critical(self, tr("DLG_ERROR"), tr("ERR_EXPORT_TTS").format(error=e))

    def export_campaign_to_tts(self):
        """Export campaign cards to Tabletop Simulator"""
        if not self.active_project:
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
            return
        try:
            from shoggoth import tts_lib
            tts_lib.export_campaign(self.active_project)
            self.status_bar.showMessage(tr("STATUS_TTS_CAMPAIGN_EXPORTED"))
        except Exception as e:
            QMessageBox.critical(self, tr("DLG_ERROR"), tr("ERR_EXPORT_TTS").format(error=e))

    def export_player_to_tts(self):
        """Export player cards to Tabletop Simulator"""
        if not self.active_project:
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
            return
        try:
            from shoggoth import tts_lib
            tts_lib.export_player_cards(self.active_project.player_cards)
            self.status_bar.showMessage(tr("STATUS_TTS_PLAYER_EXPORTED"))
        except Exception as e:
            QMessageBox.critical(self, tr("DLG_ERROR"), tr("ERR_EXPORT_TTS").format(error=e))

    # ==================== TOOLS MENU ACTIONS ====================

    def convert_strange_eons(self):
        """Convert a Strange Eons project"""
        pass

    # ==================== FILE MENU ACTIONS ====================

    def gather_images(self, update=False):
        """Gather all images from the project"""
        if not self.active_project:
            QMessageBox.warning(self, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
            return

        try:
            self.active_project.gather_images(update=update)
            action = tr("ACTION_GATHERED_UPDATED") if update else tr("ACTION_GATHERED")
            self.status_bar.showMessage(tr("STATUS_IMAGES_ACTION").format(action=action))
            QMessageBox.information(self, tr("DLG_SUCCESS"), tr("MSG_IMAGES_SUCCESS").format(action=action))
        except Exception as e:
            QMessageBox.critical(self, tr("DLG_ERROR"), tr("ERR_GATHER_IMAGES").format(error=e))

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
        msg.setWindowTitle(tr("DLG_TEXT_OPTIONS"))
        msg.setText(tr("MSG_RICH_TEXT_OPTIONS"))
        msg.setDetailedText(help_text)
        msg.exec()

    # ==================== UTILITY METHODS ====================

    def get_text_input(self, title, label, default=""):
        """Show a text input dialog"""
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, title, label, text=default)
        return text, ok
