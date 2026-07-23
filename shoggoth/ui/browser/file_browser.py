"""
File browser widget showing the open projects' cards, encounter sets,
and guides, in either a grouped tree view or a flat sortable list.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QStackedWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from shoggoth.card import natural_sort_key
from shoggoth.i18n import tr
from shoggoth.ui.browser.drag_drop import CompactLeafDelegate, DraggableTreeWidget
from shoggoth.ui.browser.tree_spec import build_tree_spec, card_display_name
from shoggoth.ui.browser.tree_sync import TreeSync


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
        layout.setContentsMargins(0, 0, 0, 0)

        # Title
        title = QLabel(tr("TREE_CARDS"))
        title.setStyleSheet("font-size: 20pt; font-weight: bold; padding: 4px;")
        layout.addWidget(title)

        # Sort controls (card list view only, hidden by default)
        self.sort_row = QWidget()
        sort_layout = QHBoxLayout(self.sort_row)
        sort_layout.setContentsMargins(4, 0, 4, 4)
        sort_layout.addWidget(QLabel(tr("SORT_BY")))
        self.sort_combo = QComboBox()
        self.sort_combo.addItem(tr("SORT_PROJECT_NUMBER"), "project_number")
        self.sort_combo.addItem(tr("SORT_NAME"), "name")
        sort_layout.addWidget(self.sort_combo)
        self.sort_row.hide()
        layout.addWidget(self.sort_row)

        # Filter controls (card list view only, hidden by default)
        self.filter_row = QWidget()
        filter_layout = QHBoxLayout(self.filter_row)
        filter_layout.setContentsMargins(4, 0, 4, 4)
        filter_layout.addWidget(QLabel(tr("TREE_FILTER_TYPE")))
        self.type_filter_combo = QComboBox()
        self.type_filter_combo.addItem(tr("TREE_FILTER_ALL_TYPES"), None)
        filter_layout.addWidget(self.type_filter_combo)
        self.name_filter_edit = QLineEdit()
        self.name_filter_edit.setPlaceholderText(tr("TREE_FILTER_NAME_PLACEHOLDER"))
        self.name_filter_edit.setClearButtonEnabled(True)
        filter_layout.addWidget(self.name_filter_edit, 1)
        self.filter_row.hide()
        layout.addWidget(self.filter_row)

        # Tree widget with drag and drop support
        self.tree = DraggableTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setItemDelegate(CompactLeafDelegate(self.tree))
        self.tree.currentItemChanged.connect(self._on_tree_current_changed)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.on_context_menu)

        # Flat card list tree
        self.list_tree = QTreeWidget(self)
        self.list_tree.setHeaderHidden(True)
        self.list_tree.currentItemChanged.connect(self._on_list_current_changed)

        # Stack the two views
        self.stacked = QStackedWidget()
        self.stacked.addWidget(self.tree)       # index 0: tree view
        self.stacked.addWidget(self.list_tree)  # index 1: card list view
        layout.addWidget(self.stacked)

        self.setLayout(layout)
        self._projects = []  # List of open projects
        self._active_project = None  # The active project for operations
        self.sync = TreeSync()  # node_id -> item map and incremental updates
        self._view_mode = 'tree'  # 'tree' or 'list'
        self._programmatic_select = False  # suppresses currentItemChanged during setCurrentItem

        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        self.type_filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        self.name_filter_edit.textChanged.connect(self._on_filter_changed)

        # Context menu handler
        from shoggoth.ui.tree_context_menu import TreeContextMenu
        self.context_menu = TreeContextMenu(self)

    @property
    def _project(self):
        """Compatibility property - returns active project"""
        return self._active_project

    def set_project(self, project):
        """Set a single project (clears others) - for backward compatibility"""
        self._projects = [project] if project else []
        self._active_project = project
        self.sync.clear()
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
            if node_id in self.sync.node_map:
                item = self.sync.node_map[node_id]
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
        if self._view_mode == 'list':
            self._build_card_list()
            return

        if not self._projects:
            self.tree.clear()
            self.sync.clear()
            return

        # If tree is empty, do a full rebuild
        if self.tree.topLevelItemCount() == 0:
            self._full_rebuild()
            return

        # Build desired tree specification for all projects
        desired_specs = [build_tree_spec(project) for project in self._projects]

        # Remove extra projects if any were closed
        while self.tree.topLevelItemCount() > len(desired_specs):
            removed_item = self.tree.takeTopLevelItem(self.tree.topLevelItemCount() - 1)
            self.sync.forget_item(removed_item)

        # Apply incremental updates to each project root
        for i, spec in enumerate(desired_specs):
            if i < self.tree.topLevelItemCount():
                root_item = self.tree.topLevelItem(i)
                self.sync.sync_item(root_item, spec)
            else:
                # New project added
                root_item = self.sync.create_item(spec)
                self.tree.addTopLevelItem(root_item)
                root_item.setExpanded(True)

    def _full_rebuild(self):
        """Do a complete tree rebuild (used for initial load or project change)"""
        self.tree.clear()
        self.sync.clear()

        if not self._projects:
            if self._view_mode == 'list':
                self._build_card_list()
            return

        for project in self._projects:
            spec = build_tree_spec(project)
            root_item = self.sync.create_item(spec)
            self.tree.addTopLevelItem(root_item)
            root_item.setExpanded(True)

            # Set bold for active project
            if project == self._active_project:
                font = root_item.font(0)
                font.setBold(True)
                root_item.setFont(0, font)

        if self._view_mode == 'list':
            self._build_card_list()

    def update_card_node(self, card_id):
        """Update a single card node by its ID without rebuilding the tree"""
        node_id = f'card:{card_id}'
        if node_id not in self.sync.node_map:
            # Card not in tree, might need full refresh
            return False

        item = self.sync.node_map[node_id]
        data = item.data(0, Qt.UserRole)
        if not data or data.get('type') != 'card':
            return False

        card = data.get('data')
        if not card:
            return False

        include_level = not card.encounter
        display_name = '● ' + card_display_name(card, include_level)

        # Update only if changed
        if item.text(0) != display_name:
            item.setText(0, display_name)

        return True

    def get_card_item(self, card_id):
        """Get the tree item for a card by ID"""
        node_id = f'card:{card_id}'
        return self.sync.node_map.get(node_id)

    def select_item_in_tree(self, item_id):
        """Find and select an item in the tree by ID, expanding parents"""
        for item in self._iterate_items(self.tree.invisibleRootItem()):
            data = item.data(0, Qt.UserRole)
            if data and data.get('data'):
                if hasattr(data['data'], 'id') and str(data['data'].id) == str(item_id):
                    self._expand_to_item(item)
                    self._programmatic_select = True
                    try:
                        self.tree.setCurrentItem(item)
                        self.tree.scrollToItem(item)
                    finally:
                        self._programmatic_select = False
                    return True
        return False

    def _iterate_items(self, root_item):
        """Recursively iterate all items in tree"""
        for i in range(root_item.childCount()):
            child = root_item.child(i)
            yield child
            yield from self._iterate_items(child)

    @staticmethod
    def _expand_to_item(item):
        """Expand all parent items to make item visible"""
        parent = item.parent()
        while parent:
            parent.setExpanded(True)
            parent = parent.parent()

    def _on_tree_current_changed(self, current, previous):
        if current and not self._programmatic_select:
            self.on_item_clicked(current, 0)

    def _on_list_current_changed(self, current, previous):
        if current and not self._programmatic_select:
            self._on_list_item_clicked(current, 0)

    def switch_view(self, mode, sort_order=None):
        """Switch sidebar between 'tree' and 'list' view."""
        self._view_mode = mode
        if sort_order is not None:
            idx = self.sort_combo.findData(sort_order)
            if idx >= 0:
                self.sort_combo.blockSignals(True)
                self.sort_combo.setCurrentIndex(idx)
                self.sort_combo.blockSignals(False)
        if mode == 'list':
            self.stacked.setCurrentIndex(1)
            self.sort_row.show()
            self.filter_row.show()
            self._build_card_list()
        else:
            self.stacked.setCurrentIndex(0)
            self.sort_row.hide()
            self.filter_row.hide()
            self._full_rebuild()

    def _on_filter_changed(self, *_args):
        """Handle name/type filter changes; rebuild list if in list mode."""
        if self._view_mode == 'list':
            self._build_card_list()

    def _populate_type_filter(self, all_cards):
        """Refresh the type filter dropdown with the front-face types
        present across open projects, preserving the current selection."""
        current = self.type_filter_combo.currentData()
        types = sorted({
            card.front.data.get('type')
            for card in all_cards
            if card.front.data.get('type')
        })

        self.type_filter_combo.blockSignals(True)
        self.type_filter_combo.clear()
        self.type_filter_combo.addItem(tr("TREE_FILTER_ALL_TYPES"), None)
        for card_type in types:
            self.type_filter_combo.addItem(card_type.replace('_', ' ').title(), card_type)
        idx = self.type_filter_combo.findData(current)
        self.type_filter_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.type_filter_combo.blockSignals(False)

    def _build_card_list(self):
        """Populate the flat card list view, one section per project."""
        self.list_tree.clear()
        sort_order = self.sort_combo.currentData()
        name_filter = self.name_filter_edit.text().strip().lower()

        cards_by_project = [(project, list(project.cards)) for project in self._projects]
        self._populate_type_filter([card for _, cards in cards_by_project for card in cards])
        type_filter = self.type_filter_combo.currentData()

        for project, cards in cards_by_project:
            proj_item = QTreeWidgetItem([project.name])
            proj_item.setData(0, Qt.UserRole, {
                'type': 'project', 'data': project,
                'node_id': f'project:{project.file_path}'
            })
            font = proj_item.font(0)
            font.setBold(project == self._active_project)
            proj_item.setFont(0, font)

            if sort_order == 'name':
                cards.sort(key=lambda c: c.name.lower())
            else:
                cards.sort(key=lambda c: (natural_sort_key(c.data.get('project_number') or 0), c.name.lower()))

            for card in cards:
                if type_filter and card.front.data.get('type') != type_filter:
                    continue
                if name_filter and name_filter not in card.name.lower():
                    continue

                pnum = card.data.get('project_number', '')
                if pnum and sort_order == 'project_number':
                    display = f"{pnum}: {card.name}"
                else:
                    display = card.name
                if card.dirty:
                    display = '● ' + display
                card_item = QTreeWidgetItem([display])
                card_item.setData(0, Qt.UserRole, {
                    'type': 'card', 'data': card,
                    'node_id': f'card:{card.id}'
                })
                proj_item.addChild(card_item)

            self.list_tree.addTopLevelItem(proj_item)
            proj_item.setExpanded(True)
            if proj_item.childCount() == 0 and (name_filter or type_filter):
                proj_item.setHidden(True)

    def _on_list_item_clicked(self, item, column):
        """Handle click in card list view."""
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        item_type = data['type']
        item_data = data['data']
        if item_type == 'card':
            self.card_selected.emit(item_data)
        elif item_type == 'project':
            self.set_active_project(item_data)
            self.project_selected.emit(item_data)

    def _on_sort_changed(self, index):
        """Handle sort order change; rebuild list if in list mode."""
        if self._view_mode == 'list':
            self._build_card_list()

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
