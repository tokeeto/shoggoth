"""
Browser-like back/forward navigation over the window's views.
"""


class NavigationHistory:
    """History of visited elements as (nav_type, nav_id) tuples."""

    def __init__(self, window):
        self.window = window
        self._history = []
        self._index = -1  # Current position in history
        self._navigating = False  # Prevent recursive pushes during back/forward

    def clear(self):
        self._history.clear()
        self._index = -1

    def push(self, nav_type, nav_id):
        """Push a navigation item to history, truncating any forward history"""
        if self._navigating:
            return  # Don't record history during back/forward navigation

        nav_item = (nav_type, nav_id)

        # Don't add duplicates if we're already at this item
        if self._history and self._index >= 0:
            if self._history[self._index] == nav_item:
                return

        # Truncate forward history
        self._history = self._history[:self._index + 1]

        # Add new item
        self._history.append(nav_item)
        self._index = len(self._history) - 1

    def back(self):
        """Navigate to the previous item in history"""
        if self._index <= 0:
            return  # Nothing to go back to

        self._index -= 1
        self._go(self._history[self._index])

    def forward(self):
        """Navigate to the next item in history"""
        if self._index >= len(self._history) - 1:
            return  # Nothing to go forward to

        self._index += 1
        self._go(self._history[self._index])

    def _go(self, nav_item):
        """Navigate to a history item without adding to history"""
        nav_type, nav_id = nav_item
        window = self.window
        self._navigating = True
        try:
            if nav_type == 'card':
                card = window.active_project.get_card(nav_id)
                if card:
                    window.show_card(card)
                    window.select_item_in_tree(nav_id)
            elif nav_type == 'encounter':
                encounter = window.active_project.get_encounter_set(nav_id)
                if encounter:
                    window.show_encounter(encounter)
                    window.select_item_in_tree(nav_id)
            elif nav_type == 'project':
                window.show_project(window.active_project)
            elif nav_type == 'guide':
                guide = window.active_project.get_guide(nav_id)
                if guide:
                    window.show_guide(guide)
                    window.select_item_in_tree(nav_id)
            elif nav_type == 'locations':
                encounter = window.active_project.get_encounter_set(nav_id)
                if encounter:
                    window.show_locations(encounter)
        finally:
            self._navigating = False
