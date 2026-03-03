"""
Go to Card dialog with fuzzy search
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QLabel, QWidget, QHBoxLayout
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from shoggoth.i18n import tr


def fuzzy_match(pattern, text):
    """
    Fuzzy match pattern against text.
    Returns (match_score, matched_indices) or (0, []) if no match.
    
    Higher score = better match
    """
    pattern = pattern.lower()
    text = text.lower()
    
    if not pattern:
        return (0, [])
    
    # Exact match gets highest score
    if pattern in text:
        start = text.index(pattern)
        indices = list(range(start, start + len(pattern)))
        return (1000 + len(pattern), indices)
    
    # Fuzzy match
    pattern_idx = 0
    text_idx = 0
    matched_indices = []
    score = 0
    consecutive = 0
    
    while pattern_idx < len(pattern) and text_idx < len(text):
        if pattern[pattern_idx] == text[text_idx]:
            matched_indices.append(text_idx)
            pattern_idx += 1
            consecutive += 1
            score += 1 + consecutive  # Bonus for consecutive matches
        else:
            consecutive = 0
        text_idx += 1
    
    # All pattern characters must be matched
    if pattern_idx != len(pattern):
        return (0, [])
    
    # Bonus for matches at word boundaries
    for idx in matched_indices:
        if idx == 0 or text[idx-1] in (' ', '_', '-', '/'):
            score += 5
    
    return (score, matched_indices)


class CardListItem(QWidget):
    """Custom widget for displaying card in the list"""
    
    def __init__(self, card, path, search_term=""):
        super().__init__()
        self.card = card
        self.path = path
        
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 3, 5, 3)
        layout.setSpacing(2)
        
        # Card name (larger, bold)
        self.name_label = QLabel()
        name_font = QFont()
        name_font.setPointSize(11)
        name_font.setBold(True)
        self.name_label.setFont(name_font)
        
        # Highlight matching characters
        self.set_name_with_highlight(card.name, search_term)
        
        layout.addWidget(self.name_label)
        
        # Path (smaller, gray)
        path_label = QLabel(path)
        path_font = QFont()
        path_font.setPointSize(9)
        path_label.setFont(path_font)
        path_label.setStyleSheet("color: #666666;")
        layout.addWidget(path_label)
        
        self.setLayout(layout)
    
    def set_name_with_highlight(self, name, search_term):
        """Set the name with highlighted matching characters"""
        if not search_term:
            self.name_label.setText(name)
            return
        
        score, indices = fuzzy_match(search_term, name)
        if score == 0:
            self.name_label.setText(name)
            return
        
        # Build HTML with highlighted characters
        html = ""
        for i, char in enumerate(name):
            if i in indices:
                html += f'<span style="background-color: #ffeb3b; color: #000;">{char}</span>'
            else:
                html += char
        
        self.name_label.setText(html)


class GotoCardDialog(QDialog):
    """Dialog for quickly navigating to cards with fuzzy search"""
    
    card_selected = Signal(object)  # Emits the selected card
    
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.all_cards = []
        self.filtered_cards = []
        
        self.setWindowTitle(tr("DLG_GOTO_CARD"))
        self.setModal(True)
        self.resize(600, 400)
        
        # Setup UI
        self.setup_ui()
        
        # Build card list
        self.build_card_list()
        
        # Show all cards initially
        self.update_results("")
        
        # Focus the search box
        self.search_input.setFocus()
    
    def setup_ui(self):
        """Setup the dialog UI"""
        layout = QVBoxLayout()
        
        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(tr("MSG_TYPE_TO_SEARCH"))
        self.search_input.textChanged.connect(self.on_search_changed)
        
        # Make search input larger
        search_font = QFont()
        search_font.setPointSize(12)
        self.search_input.setFont(search_font)
        self.search_input.setMinimumHeight(35)
        
        layout.addWidget(self.search_input)
        
        # Results count label
        self.count_label = QLabel()
        self.count_label.setStyleSheet("color: #666666; font-size: 10pt;")
        layout.addWidget(self.count_label)
        
        # Results list
        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.results_list)
        
        # Instructions
        instructions = QLabel(
            tr("MSG_GOTO_INSTRUCTIONS")
        )
        instructions.setStyleSheet("color: #999999; font-size: 9pt; padding: 5px;")
        instructions.setAlignment(Qt.AlignCenter)
        layout.addWidget(instructions)
        
        self.setLayout(layout)
    
    def build_card_list(self):
        """Build the list of all cards with their paths"""
        if not self.project:
            return
        
        # Process encounter sets (campaign cards)
        for encounter_set in self.project.encounter_sets:
            for card in encounter_set.cards:
                # Determine subcategory
                if card.front.get('type') == 'location':
                    subcategory = "Locations"
                elif card.back.get('type') == 'encounter':
                    subcategory = "Encounter"
                else:
                    subcategory = "Story"
                
                path = f"Campaign Cards / {encounter_set.name} / {subcategory}"
                self.all_cards.append((card, path))
        
        # Process player cards
        for card in self.project.player_cards:
            # Check if it's part of an investigator set
            if investigator := card.data.get('investigator'):
                path = f"Player Cards / Investigators / {investigator}"
            else:
                # Get card class
                card_class = card.get_class()
                if card_class:
                    class_name = {
                        'guardian': 'Guardian',
                        'seeker': 'Seeker',
                        'rogue': 'Rogue',
                        'mystic': 'Mystic',
                        'survivor': 'Survivor',
                        'neutral': 'Neutral',
                        'multi': 'Multi-class'
                    }.get(card_class, 'Other')
                    path = f"Player Cards / {class_name}"
                else:
                    path = "Player Cards / Other"
            
            self.all_cards.append((card, path))
        
        # Process guides
        for guide in self.project.guides:
            path = "Guides"
            # Create a pseudo-card object for guides
            class GuideWrapper:
                def __init__(self, guide):
                    self.guide = guide
                    self.name = guide.name
                    self.id = guide.id
                    self.is_guide = True
            
            self.all_cards.append((GuideWrapper(guide), path))
    
    def on_search_changed(self, text):
        """Handle search text changes"""
        # Debounce search for performance
        if hasattr(self, 'search_timer'):
            self.search_timer.stop()
        
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(lambda: self.update_results(text))
        self.search_timer.start(100)  # 100ms debounce
    
    def update_results(self, search_term):
        """Update the results list based on search term"""
        self.results_list.clear()
        
        if not search_term:
            # No search term - show all cards
            results = [(card, path, 0) for card, path in self.all_cards]
        else:
            # Fuzzy search
            results = []
            for card, path in self.all_cards:
                score, _ = fuzzy_match(search_term, card.name)
                if score > 0:
                    results.append((card, path, score))
            
            # Sort by score (highest first)
            results.sort(key=lambda x: x[2], reverse=True)
        
        # Limit results to top 100 for performance
        results = results[:100]
        
        # Update count label
        total = len([c for c, p in self.all_cards])
        shown = len(results)
        if search_term:
            self.count_label.setText(tr("MSG_SHOWING_CARDS").format(shown=shown, total=total))
        else:
            self.count_label.setText(tr("MSG_TOTAL_CARDS").format(total=total))
        
        # Add results to list
        for card, path, score in results:
            item = QListWidgetItem(self.results_list)
            widget = CardListItem(card, path, search_term)
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.UserRole, card)  # Store card object
            self.results_list.addItem(item)
            self.results_list.setItemWidget(item, widget)
        
        # Select first item
        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)
    
    def keyPressEvent(self, event):
        """Handle key presses"""
        if event.key() == Qt.Key_Escape:
            self.reject()
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.select_current_item()
        elif event.key() in (Qt.Key_Down, Qt.Key_Up):
            # Let the list widget handle it
            self.results_list.setFocus()
            self.results_list.keyPressEvent(event)
            self.search_input.setFocus()
        else:
            super().keyPressEvent(event)
    
    def on_item_double_clicked(self, item):
        """Handle double-click on item"""
        self.select_current_item()
    
    def select_current_item(self):
        """Select the currently highlighted item"""
        current_item = self.results_list.currentItem()
        if current_item:
            card = current_item.data(Qt.UserRole)
            self.card_selected.emit(card)
            self.accept()
    
    def showEvent(self, event):
        """Handle show event"""
        super().showEvent(event)
        # Focus search input when dialog is shown
        self.search_input.setFocus()
        self.search_input.selectAll()