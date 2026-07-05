"""
Incremental synchronization between tree specs and live QTreeWidgetItems.

TreeSync owns the node_id -> QTreeWidgetItem map and knows how to create,
update, remove, and reorder items so the widget matches a desired spec
(see tree_spec.py) without rebuilding the whole tree.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QTreeWidgetItem


class TreeSync:
    def __init__(self):
        self.node_map = {}  # Maps node_id -> QTreeWidgetItem for fast lookup

    def clear(self):
        self.node_map.clear()

    def create_item(self, spec):
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
            icon = spec['icon']
            item.setIcon(0, icon if isinstance(icon, QIcon) else QIcon(icon))

        # Store in node map for fast lookup
        self.node_map[spec['node_id']] = item

        # Create children
        for child_spec in spec.get('children', []):
            child_item = self.create_item(child_spec)
            item.addChild(child_item)

        return item

    def sync_item(self, item, spec):
        """Synchronize an existing tree item with a spec, updating only what changed"""
        if spec is None:
            return

        # Update text if changed
        if item.text(0) != spec['text']:
            item.setText(0, spec['text'])

        # Update icon
        if spec.get('icon'):
            icon = spec['icon']
            item.setIcon(0, icon if isinstance(icon, QIcon) else QIcon(icon))
        else:
            item.setIcon(0, QIcon())

        # Update user data
        user_data = {'type': spec['type'], 'data': spec['data'], 'node_id': spec['node_id']}
        if 'class' in spec:
            user_data['class'] = spec['class']
        if 'investigator' in spec:
            user_data['investigator'] = spec['investigator']
        item.setData(0, Qt.UserRole, user_data)

        # Update node map
        self.node_map[spec['node_id']] = item

        # Build maps of current and desired children
        current_children = {}
        for i in range(item.childCount()):
            child = item.child(i)
            child_data = child.data(0, Qt.UserRole)
            if child_data:
                child_id = self.node_id_for_item(child)
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
            self.forget_item(removed_item)

        # Update existing nodes
        for node_id in to_update:
            _, child_item = current_children[node_id]
            child_spec = desired_children[node_id]
            self.sync_item(child_item, child_spec)

        # Add new nodes
        for node_id in to_add:
            child_spec = desired_children[node_id]
            new_item = self.create_item(child_spec)
            item.addChild(new_item)  # Add at end for now

        # Reorder children to match desired order
        self.reorder_children(item, desired_order)

    def node_id_for_item(self, item):
        """Extract or construct a node_id from an existing tree item"""
        data = item.data(0, Qt.UserRole)
        if not data:
            return None

        # Use the stored node_id if available (avoids depending on translated display text)
        if 'node_id' in data:
            return data['node_id']

        item_type = data.get('type')
        item_data = data.get('data')

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

    def forget_item(self, item):
        """Recursively remove an item and its children from the node map"""
        node_id = self.node_id_for_item(item)
        if node_id and node_id in self.node_map:
            del self.node_map[node_id]

        for i in range(item.childCount()):
            self.forget_item(item.child(i))

    def reorder_children(self, parent_item, desired_order):
        """Reorder children of a parent item to match desired order"""
        if not desired_order:
            return

        # Build current order map
        current_order = []
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            node_id = self.node_id_for_item(child)
            current_order.append(node_id)

        # Check if reordering is needed
        if current_order == desired_order:
            return

        # Remove all children while preserving expanded state
        children_with_state = []
        while parent_item.childCount() > 0:
            child = parent_item.takeChild(0)
            node_id = self.node_id_for_item(child)
            children_with_state.append((node_id, child, child.isExpanded()))

        # Create lookup
        child_lookup = {node_id: (child, expanded) for node_id, child, expanded in children_with_state}

        # Re-add in correct order
        for node_id in desired_order:
            if node_id in child_lookup:
                child, expanded = child_lookup[node_id]
                parent_item.addChild(child)
                child.setExpanded(expanded)
