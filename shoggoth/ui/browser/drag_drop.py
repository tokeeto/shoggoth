"""
Drag & drop support and item delegates for the file browser tree.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QTreeWidget

import shoggoth


class CompactLeafDelegate(QStyledItemDelegate):
    """Shifts leaf nodes left by one indentation to remove expand-arrow dead space."""

    def __init__(self, tree):
        super().__init__(tree)
        self._tree = tree

    def paint(self, painter, option, index):
        if not index.model().hasChildren(index):
            opt = QStyleOptionViewItem(option)
            opt.rect = option.rect.adjusted(-self._tree.indentation(), 0, 0, 0)
            super().paint(painter, opt, index)
        else:
            super().paint(painter, option, index)


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

        # Class / investigator categories (player cards) — check before the
        # encounter sub-category branch; Project also has .id, so ordering matters.
        if item_type == 'category':
            cls = data.get('class')
            if cls:
                if cls == 'investigators':
                    return None, None  # Can't drop directly on Investigators
                elif cls == 'other':
                    return 'other', None
                else:
                    return 'class', cls

            investigator = data.get('investigator')
            if investigator:
                return 'investigator', investigator

        # Story/Location/Encounter sub-categories under an encounter set.
        # item_data is the EncounterSet object; guard with isinstance so we
        # don't accidentally match Project nodes (which also have .id).
        from shoggoth.encounter_set import EncounterSet
        if item_type in ('category', 'locations'):
            if isinstance(item_data, EncounterSet):
                return 'encounter', item_data

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
        node_map = self.file_browser.sync.node_map
        card_ids = event.mimeData().data('application/x-shoggoth-card').data().decode().split(',')
        for card_id in card_ids:
            node_id = f'card:{card_id}'
            if node_id in node_map:
                dragged_item = node_map[node_id]
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

        node_map = self.file_browser.sync.node_map
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
            if node_id in node_map:
                dragged_item = node_map[node_id]
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

        # Refresh the tree to reflect changes.
        # We set IgnoreAction before accepting so that QAbstractItemView::startDrag
        # sees a non-MoveAction result and skips its internal clearOrRemove() call.
        # Without this, Qt removes the dragged items AFTER our refresh_tree() has
        # already rebuilt the tree correctly, causing items to go missing.
        event.setDropAction(Qt.IgnoreAction)
        event.accept()
        shoggoth.app.refresh_tree()
