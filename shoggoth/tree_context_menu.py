"""
Context menu system for the file browser tree
"""
from PySide6.QtWidgets import QMenu
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
import json


class TreeContextMenu:
    """Manages context menus for tree items"""
    
    # Signals
    card_copy = Signal(object)
    card_duplicate = Signal(object)
    card_delete = Signal(object)
    card_paste = Signal(object, object)  # target, card_data
    new_card = Signal(object, dict)  # target (encounter/group), template
    
    def __init__(self, parent):
        self.parent = parent
        self.clipboard = None  # Stores copied card data
    
    def show_context_menu(self, item, position):
        """Show appropriate context menu for the item"""
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        item_type = data.get('type')
        item_data = data.get('data')

        menu = QMenu(self.parent)

        if item_type == 'card':
            self._create_card_menu(menu, item_data)
        elif item_type == 'encounter':
            self._create_encounter_menu(menu, item_data)
        elif item_type == 'project':
            self._create_project_menu(menu, item_data)
        elif item_type == 'campaign_cards':
            self._create_campaign_cards_menu(menu, item_data)
        elif item_type == 'player_cards':
            self._create_player_cards_menu(menu, item_data)
        elif item_type == 'category':
            # Category nodes (Story, Locations, Encounter, Class groups, etc.)
            category_name = item.text(0)
            parent_data = item.parent().data(0, Qt.UserRole) if item.parent() else None
            self._create_category_menu(menu, category_name, parent_data, data)

        if not menu.isEmpty():
            menu.exec(position)
    
    def _create_card_menu(self, menu, card):
        """Create context menu for a card"""
        # Copy
        copy_action = QAction("Copy", self.parent)
        copy_action.triggered.connect(lambda: self.copy_card(card))
        menu.addAction(copy_action)
        
        # Duplicate
        duplicate_action = QAction("Duplicate", self.parent)
        duplicate_action.triggered.connect(lambda: self.duplicate_card(card))
        menu.addAction(duplicate_action)
        
        menu.addSeparator()
        
        # Delete
        delete_action = QAction("Delete", self.parent)
        delete_action.triggered.connect(lambda: self.delete_card(card))
        menu.addAction(delete_action)
    
    def _create_encounter_menu(self, menu, encounter):
        """Create context menu for an encounter set"""
        # New Card
        new_card_action = QAction("New Card", self.parent)
        new_card_action.triggered.connect(lambda: self.new_card_in_encounter(encounter))
        menu.addAction(new_card_action)
        
        # Paste (if we have something in clipboard)
        if self.clipboard:
            menu.addSeparator()
            paste_action = QAction("Paste Card", self.parent)
            paste_action.triggered.connect(lambda: self.paste_card(encounter, None))
            menu.addAction(paste_action)
        
        menu.addSeparator()
        
        # Delete Encounter Set
        delete_action = QAction("Delete Encounter Set", self.parent)
        delete_action.triggered.connect(lambda: self.delete_encounter(encounter))
        menu.addAction(delete_action)
    
    def _create_project_menu(self, menu, project):
        """Create context menu for project root"""
        import shoggoth

        # Set as Active (only show if not already active)
        if shoggoth.app and shoggoth.app.active_project != project:
            set_active_action = QAction("Set as Active", self.parent)
            set_active_action.triggered.connect(lambda: self.set_active_project(project))
            menu.addAction(set_active_action)
            menu.addSeparator()

        # New Encounter Set
        new_encounter_action = QAction("New Encounter Set", self.parent)
        new_encounter_action.triggered.connect(lambda: self.new_encounter_set(project))
        menu.addAction(new_encounter_action)

        # New Player Card
        new_player_action = QAction("New Player Card", self.parent)
        new_player_action.triggered.connect(lambda: self.new_player_card(project))
        menu.addAction(new_player_action)

        menu.addSeparator()

        # Close Project
        close_action = QAction("Close Project", self.parent)
        close_action.triggered.connect(lambda: self.close_project(project))
        menu.addAction(close_action)

    def _create_campaign_cards_menu(self, menu, project):
        """Create context menu for Campaign cards node"""
        new_encounter_action = QAction("New Encounter Set", self.parent)
        new_encounter_action.triggered.connect(lambda: self.new_encounter_set(project))
        menu.addAction(new_encounter_action)

    def _create_player_cards_menu(self, menu, project):
        """Create context menu for Player cards node"""
        new_card_action = QAction("New Card", self.parent)
        new_card_action.triggered.connect(lambda: self.new_player_card(project))
        menu.addAction(new_card_action)
    
    def _create_category_menu(self, menu, category_name, parent_data, item_data):
        """Create context menu for category nodes (Story, Locations, etc.)"""
        # Check if this is a class category node (Guardian, Seeker, etc.)
        class_type = item_data.get('class') if item_data else None

        if class_type == 'investigators':
            # Investigators node - add new investigator option
            new_inv_action = QAction("New Investigator", self.parent)
            new_inv_action.triggered.connect(self.new_investigator)
            menu.addAction(new_inv_action)
            return

        if class_type == 'other':
            # Other node - add new card option
            new_card_action = QAction("New Card", self.parent)
            new_card_action.triggered.connect(lambda: self.new_player_card(None))
            menu.addAction(new_card_action)
            return

        if class_type in ('guardian', 'seeker', 'rogue', 'mystic', 'survivor', 'neutral'):
            # Class nodes - add asset/event/skill options
            for card_type in ['Asset', 'Event', 'Skill']:
                action = QAction(f"New {card_type}", self.parent)
                action.triggered.connect(
                    lambda checked=False, ct=card_type.lower(), cls=class_type: self.new_class_card(cls, ct)
                )
                menu.addAction(action)

            # Paste (if we have something in clipboard)
            if self.clipboard:
                menu.addSeparator()
                paste_action = QAction("Paste Card", self.parent)
                paste_action.triggered.connect(
                    lambda: self.paste_class_card(class_type)
                )
                menu.addAction(paste_action)
            return

        # Encounter set categories (Story, Locations, Encounter)
        template = self._get_template_for_category(category_name, parent_data)

        if template:
            new_card_action = QAction(f"New {category_name} Card", self.parent)
            new_card_action.triggered.connect(
                lambda: self.new_card_with_template(parent_data.get('data'), template)
            )
            menu.addAction(new_card_action)

            # Paste (if we have something in clipboard)
            if self.clipboard:
                menu.addSeparator()
                paste_action = QAction("Paste Card", self.parent)
                paste_action.triggered.connect(
                    lambda: self.paste_card(parent_data.get('data'), template)
                )
                menu.addAction(paste_action)
    
    def _get_template_for_category(self, category_name, parent_data):
        """Get the appropriate template for a category"""
        if not parent_data:
            return None
        
        parent_type = parent_data.get('type')
        
        # Encounter set categories
        if parent_type == 'encounter':
            templates = {
                'Story': {'front': {'type': 'story'}, 'back': {'type': 'story'}},
                'Locations': {'front': {'type': 'location'}, 'back': {'type': 'location_back'}},
                'Encounter': {'front': {'type': 'treachery'}, 'back': {'type': 'encounter'}},
            }
            return templates.get(category_name)
        
        # Player card categories
        if category_name in ('Guardian', 'Seeker', 'Rogue', 'Mystic', 'Survivor', 'Neutral'):
            class_name = category_name.lower()
            return {
                'front': {'type': 'asset', 'classes': [class_name]},
                'back': {'type': 'player'}
            }
        
        # Investigator groups
        if category_name == 'Investigators':
            return {
                'front': {'type': 'investigator'},
                'back': {'type': 'investigator_back'}
            }
        
        # Specific investigator group (signatures/weaknesses)
        if parent_type == 'category' and parent_data.get('data', {}).get('investigator'):
            investigator = parent_data.get('data', {}).get('investigator')
            return {
                'front': {'type': 'asset'},
                'back': {'type': 'player'},
                'investigator': investigator
            }
        
        return None
    
    def copy_card(self, card):
        """Copy card to clipboard"""
        # Deep copy the card data
        self.clipboard = json.loads(json.dumps(card.data))
        # Remove ID so paste creates new card
        if 'id' in self.clipboard:
            del self.clipboard['id']
        print(f"Copied card: {card.name}")
    
    def duplicate_card(self, card):
        """Duplicate a card in the same location"""
        from uuid import uuid4
        
        # Create a copy of the card data
        new_data = json.loads(json.dumps(card.data))
        
        # Generate new ID
        new_data['id'] = str(uuid4())
        
        # Append "Copy" to name
        new_data['name'] = f"{card.name} (Copy)"
        
        # Add to project
        card.expansion.add_card(new_data)
        
        print(f"Duplicated card: {card.name}")
        
        # Trigger refresh
        import shoggoth
        shoggoth.app.refresh_tree()
    
    def delete_card(self, card):
        """Delete a card"""
        from PySide6.QtWidgets import QMessageBox
        
        reply = QMessageBox.question(
            self.parent,
            "Delete Card",
            f"Are you sure you want to delete '{card.name}'?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Remove from project
            card.expansion.data['cards'].remove(card.data)
            
            print(f"Deleted card: {card.name}")
            
            # Trigger refresh
            import shoggoth
            shoggoth.app.refresh_tree()
    
    def paste_card(self, target, template=None):
        """Paste clipboard card to target location"""
        if not self.clipboard:
            return
        
        from uuid import uuid4
        
        # Create new card data from clipboard
        new_data = json.loads(json.dumps(self.clipboard))
        
        # Generate new ID
        new_data['id'] = str(uuid4())
        
        # Apply template if provided (for categories)
        if template:
            if 'front' in template:
                new_data.setdefault('front', {}).update(template['front'])
            if 'back' in template:
                new_data.setdefault('back', {}).update(template['back'])
            if 'investigator' in template:
                new_data['investigator'] = template['investigator']
        
        # Set encounter set if target is an encounter
        from shoggoth.encounter_set import EncounterSet
        if isinstance(target, EncounterSet):
            new_data['encounter_set'] = target.id
        
        # Add to project
        import shoggoth
        project = shoggoth.app.current_project
        project.add_card(new_data)
        
        print(f"Pasted card: {new_data['name']}")
        
        # Trigger refresh
        shoggoth.app.refresh_tree()
    
    def new_card_in_encounter(self, encounter):
        """Create new card in encounter set"""
        import shoggoth
        from shoggoth.card import TEMPLATES
        
        # Get default template (treachery)
        template = TEMPLATES.get('treachery')
        template['name'] = 'New Card'
        
        # Create card
        from shoggoth.card import Card
        new_card = Card(data=template, expansion=shoggoth.app.current_project, encounter=encounter)
        
        # Add to project
        shoggoth.app.current_project.add_card(new_card)
        
        # Refresh and open
        shoggoth.app.refresh_tree()
        shoggoth.app.show_card(new_card)
        shoggoth.app.select_item_in_tree(new_card.id)
    
    def new_card_with_template(self, target, template):
        """Create new card with specific template"""
        import shoggoth
        from uuid import uuid4
        
        # Build card data
        new_data = {
            'id': str(uuid4()),
            'name': 'New Card',
            'front': template.get('front', {'type': 'asset'}),
            'back': template.get('back', {'type': 'player'}),
        }
        
        # Add investigator if specified
        if 'investigator' in template:
            new_data['investigator'] = template['investigator']
        
        # Set encounter set if target is an encounter
        from shoggoth.encounter_set import EncounterSet
        if isinstance(target, EncounterSet):
            new_data['encounter_set'] = target.id
        
        # Add to project
        project = shoggoth.app.current_project
        project.add_card(new_data)
        
        # Refresh and open
        shoggoth.app.refresh_tree()
        
        # Find and show the new card
        from shoggoth.card import Card
        new_card = Card(new_data, expansion=project, encounter=target if isinstance(target, EncounterSet) else None)
        shoggoth.app.show_card(new_card)
        shoggoth.app.select_item_in_tree(new_card.id)
    
    def new_encounter_set(self, project):
        """Create new encounter set"""
        from PySide6.QtWidgets import QInputDialog
        
        name, ok = QInputDialog.getText(
            self.parent,
            "New Encounter Set",
            "Encounter Set Name:"
        )
        
        if ok and name:
            project.add_encounter_set(name)
            
            import shoggoth
            shoggoth.app.refresh_tree()
    
    def new_player_card(self, project):
        """Create new player card"""
        import shoggoth
        shoggoth.app.new_card_dialog()
    
    def delete_encounter(self, encounter):
        """Delete an encounter set"""
        from PySide6.QtWidgets import QMessageBox
        
        reply = QMessageBox.question(
            self.parent,
            "Delete Encounter Set",
            f"Are you sure you want to delete '{encounter.name}'?\n\n"
            f"This will delete all {len(encounter.cards)} cards in this set.\n"
            f"This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Remove all cards in the encounter set
            import shoggoth
            project = shoggoth.app.current_project
            
            # Remove cards
            cards_to_remove = [c for c in project.data['cards'] if c.get('encounter_set') == encounter.id]
            for card in cards_to_remove:
                project.data['cards'].remove(card)
            
            # Remove encounter set
            project.data['encounter_sets'].remove(encounter.data)
            
            print(f"Deleted encounter set: {encounter.name}")

            # Trigger refresh
            shoggoth.app.refresh_tree()

    def new_investigator(self):
        """Create new investigator card"""
        import shoggoth
        shoggoth.app.add_investigator_template()

    def new_class_card(self, class_type, card_type):
        """Create new card with specific class and type"""
        import shoggoth
        from uuid import uuid4

        # Build card data
        new_data = {
            'id': str(uuid4()),
            'name': 'New Card',
            'front': {
                'type': card_type,
                'classes': [class_type],
            },
            'back': {'type': 'player'},
        }

        # Add to project
        project = shoggoth.app.current_project
        project.add_card(new_data)

        # Refresh and open
        shoggoth.app.refresh_tree()

        # Find and show the new card
        new_card = project.get_card(new_data['id'])
        if new_card:
            shoggoth.app.show_card(new_card)
            shoggoth.app.select_item_in_tree(new_card.id)

    def paste_class_card(self, class_type):
        """Paste clipboard card with specific class"""
        if not self.clipboard:
            return

        import shoggoth
        from uuid import uuid4

        # Create new card data from clipboard
        new_data = json.loads(json.dumps(self.clipboard))

        # Generate new ID
        new_data['id'] = str(uuid4())

        # Set class on front face
        new_data.setdefault('front', {})['classes'] = [class_type]

        # Add to project
        project = shoggoth.app.current_project
        project.add_card(new_data)

        print(f"Pasted card: {new_data.get('name', 'New Card')}")

        # Trigger refresh
        shoggoth.app.refresh_tree()

    def set_active_project(self, project):
        """Set a project as the active project"""
        import shoggoth
        if shoggoth.app:
            shoggoth.app.file_browser.set_active_project(project)

    def close_project(self, project):
        """Close a project"""
        import shoggoth
        if shoggoth.app:
            shoggoth.app.close_project(project)