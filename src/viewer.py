import os
from time import time
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.core.window import Window
from kivy.properties import StringProperty
from kivy.clock import Clock
from kivy.lang import Builder

from file_monitor import FileMonitor
from project import Project
from renderer import CardRenderer
import json

class ViewerRoot(BoxLayout):
    """Root widget for the Viewer mode"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        Window.bind(on_key_down=self.on_keyboard)

    def on_keyboard(self, instance, keyboard, keycode, text, modifiers):
        print('on keyboard', keycode, modifiers)
        # Handle keyboard shortcuts
        if keycode == 27:  # Esc key
            App.get_running_app().stop()
            return True
        if keycode == 80:  # left
            App.get_running_app().select_card(-1)
            return True
        if keycode == 79:  # right
            App.get_running_app().select_card(1)
            return True
        if keycode == 8:
            if modifiers == ['ctrl']:
                f = App.get_running_app().export_all
                Clock.schedule_once(lambda x: f())
            else:
                f = App.get_running_app().export_current
                Clock.schedule_once(lambda x: f())
        return False

class ViewerApp(App):
    """Application class for Viewer Mode"""
    file_path = StringProperty("")
    status_message = StringProperty("Ready")

    def __init__(self, file_path, **kwargs):
        super().__init__(**kwargs)
        self.file_path = file_path

    def build(self):
        # Set window title and size
        self.icon = '/home/toke/Documents/elder_sign_neon.png'
        self.title = f"Shoggoth Card Viewer - {os.path.basename(self.file_path)}"
        Window.size = (800, 600)

        # Initialize the root widget
        self.root = ViewerRoot()
        self.data = {}

        # Create a status bar
        self.status_bar = Label(
            text=self.status_message,
            size_hint_y=None,
            height=24,
            halign='left',
            text_size=(Window.width, 24),
            padding=(10, 0),
            valign='middle',
            color=(1, 1, 1, 1)
        )
        self.root.add_widget(self.status_bar)

        # Initialize card renderer
        self.card_renderer = CardRenderer()
        self.card_index = 0

        # Initialize file monitoring
        self.file_monitor = FileMonitor(os.path.dirname(self.file_path), self.on_file_changed)
        self.file_monitor.add_file(self.file_path)
        self.file_monitor.start()
        self.file_monitor_settings = FileMonitor(os.path.dirname('assets/defaults/'), self.on_file_changed)
        self.file_monitor_settings.start()

        # Bind property changes
        self.bind(status_message=self._update_status_bar)

        # Load the initial card
        Clock.schedule_once(lambda dt: self.load_file(self.file_path), 0.5)

        return self.root

    def _update_status_bar(self, instance, value):
        """Update the status bar text"""
        self.status_bar.text = value

    def select_card(self, increment):
        if not self.cards:
            return
        self.card_index += increment
        self.card_index = self.card_index % len(self.cards)
        self.render_card(self.cards[self.card_index], None)
        self.status_message = 'Moved ' + ('left' if increment == -1 else 'right')

    def on_file_changed(self, file_path):
        """Handle file changes"""
        if file_path == self.file_path:
            self.load_file(file_path)
        else:
            self.load_file(self.file_path)

    def render_card(self, card, file_path=None):
        # Update card preview
        front_image, back_image = self.card_renderer.get_card_textures(card)
        target = self.root.ids.front_preview
        target.texture = front_image
        self.root.ids.back_preview.texture = back_image

        # Update status
        if file_path:
            self.status_message = f"Loaded: {os.path.basename(file_path)} (Last modified: {os.path.getmtime(file_path)})"

    def load_file(self, file_path):
        """Load a card from file and update the UI"""
        if not file_path or not os.path.exists(file_path):
            self.status_message = f"File not found: {file_path}"
            return

        try:
            # Check if file is a card file
            with open(file_path, 'r') as file:
                new_data = json.load(file)

            # look for card diffs
            if self.data:
                cards = Project(file_path, new_data).get_all_cards()
                for card in cards:
                    if card not in self.cards:
                        self.card_index = cards.index(card)
                        break
                self.cards = cards
            else:
                self.data = new_data
                self.cards = Project(file_path, new_data).get_all_cards()

            Clock.schedule_once(lambda x: self.render_card(self.cards[self.card_index], file_path))

        except Exception as e:
            self.status_message = f"Error loading file: {str(e)}"

    def on_stop(self):
        """Clean up when the application stops"""
        if self.file_monitor:
            self.file_monitor.stop()

    def export_current(self):
        export_folder = os.path.join(os.path.dirname(self.file_path), f'export_of_{os.path.basename(self.file_path).split(".")[1]}')
        if not os.path.exists(export_folder):
            os.mkdir(export_folder)
        t = time()
        card = self.cards[self.card_index]
        self.card_renderer.export_card_images(card, export_folder)
        print(f'Export of {card.name} cards done in {time()-t} seconds')


    def export_all(self):
        export_folder = os.path.join(os.path.dirname(self.file_path), f'export_of_{os.path.basename(self.file_path).split(".")[1]}')
        if not os.path.exists(export_folder):
            os.mkdir(export_folder)
        t = time()
        for card in self.cards:
            self.card_renderer.export_card_images(card, export_folder)
        print(f'Export of {len(self.cards)} cards done in {time()-t} seconds')
