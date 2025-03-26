from time import time
from kivy.config import Config
from kivy.uix.colorpicker import ListProperty

from project import Project
Config.set('graphics', 'width', '1700')
Config.set('graphics', 'height', '900')
Config.set('input', 'mouse', 'mouse,disable_multitouch')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.splitter import Splitter
from kivy.uix.treeview import TreeView, TreeViewLabel
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.popup import Popup
from kivy.uix.image import Image
from kivy.properties import ObjectProperty, StringProperty, BooleanProperty
from kivy.clock import Clock
from kivy.core.window import Window
from editor import CardEditor, EncounterEditor, ProjectEditor

import os
import json
from pathlib import Path

from renderer import CardRenderer
from file_monitor import FileMonitor
from card import Card

from kivy.storage.jsonstore import JsonStore


class ShogothRoot(BoxLayout):
    """Root widget for the Shoggoth application"""

    def __init__(self, **kwargs):
        super(ShogothRoot, self).__init__(**kwargs)
        Window.bind(on_key_down=self.on_keyboard)

    def on_keyboard(self, instance, keyboard, keycode, text, modifiers):
        # Handle keyboard shortcuts
        if 'ctrl' in modifiers:
            if keycode == 115:  # 's' key
                App.get_running_app().save_current_card()
                return True
            elif keycode == 111:  # 'o' key
                App.get_running_app().open_project_dialog()
                return True

        return False

class FileBrowser(BoxLayout):
    """File browser widget showing project files"""
    files = ListProperty()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(files=self.refresh)

    def refresh(self, *args):
        print('clearing tree, files is now', self.files)
        # Clear tree
        for node in self.tree.root.nodes:
            self.tree.remove_node(node)

        # Recursively add files and folders
        self._add_nodes()

    def _add_nodes(self):
        # Add folder contents to tree
        for file in self.files:
            p_node = self.tree.add_node(TreeViewButton(text=file['name'], element=file, element_type='project'))
            for encounter_set in file.encounter_sets:
                e_node = self.tree.add_node(TreeViewButton(text=encounter_set.name, element=encounter_set, element_type='encounter'), p_node)
                for card in encounter_set.cards:
                    c_node = self.tree.add_node(TreeViewButton(text=card.name, element=card, element_type='card'), e_node)

    def on_tree_select(self, instance, node):
        if hasattr(node, 'full_path') and node.full_path.endswith('.json'):
            self.parent.parent.load_card(node.full_path)


class TreeViewButton(Button, TreeViewLabel):
    element = ObjectProperty()
    element_type = StringProperty('')

    def select(self, *args, **kwargs):
        app = App.get_running_app()
        if self.element_type == 'project':
            app.show_project(self.element)
        elif self.element_type == 'encounter':
            app.show_encounter(self.element)
        elif self.element_type == 'card':
            app.show_card(self.element)


class CardPreview(BoxLayout):
    """Widget for displaying card previews"""
    def set_card_images(self, front_image, back_image):
        self.ids.front_preview.texture = front_image
        self.ids.back_preview.texture = back_image

class FileChooserPopup(Popup):
    """Popup for selecting files/folders"""
    def __init__(self, on_selection):
        super().__init__()
        self.on_selection = on_selection

    def select(self, *args):
        selected = self.ids.chooser.selection
        self.dismiss()
        self.on_selection(selected)

class ShoggothApp(App):
    """Main application class for Shoggoth Card Creator"""

    project_path = StringProperty("")
    current_card_path = StringProperty("")
    status_message = StringProperty("Ready")

    def build(self):
        # Initialize main components
        self.storage = JsonStore('shoggoth.json')
        self.root = ShogothRoot()

        # Initialize card renderer
        self.card_renderer = CardRenderer()
        self.scheduled_redraw = None

        # Initialize file monitoring
        self.file_monitor = None
        self.card_data = None

        self.assets_monitor = FileMonitor('assets/defaults/', self.on_file_changed)
        #self.assets_monitor.start()

        # build a session object if one doesn't exist
        if not self.storage.exists('session'):
            print('no defaults, creating new storage')
            self.storage.put('session', projects=[])

        # restore the existing session
        self.root.ids.file_browser.files = [Project.load(p) for p in self.storage.get('session')['projects']]

        return self.root

    def open_project_dialog(self):
        """Show file chooser dialog to select project folder"""
        self.file_chooser = FileChooserPopup(
            on_selection=self.add_project_file
        )
        self.file_chooser.open()

    def add_project_file(self, path):
        """Set the project path and initialize monitoring"""
        if not path:
            return

        self.root.ids.file_browser.files.append(Project.load(path[0]))
        self.storage.put('session', projects=self.storage.get('session')['projects']+[path[0]] )

        self.status_message = f"Project opened: {os.path.basename(self.project_path)}"
        self.root.ids.status_bar.text = self.status_message

    def on_file_changed(self, file_path):
        """Handle file changes outside the editor"""
        self.load_file(self.current_card_path)

    def show_project(self, project):
        self.root.ids.editor_container.clear_widgets()
        self.root.ids.editor_container.add_widget(ProjectEditor(project=project))

    def show_encounter(self, encounter):
        self.root.ids.editor_container.clear_widgets()
        self.root.ids.editor_container.add_widget(EncounterEditor(encounter=encounter))

    def show_card(self, card):
        self.current_card = card
        self.root.ids.editor_container.clear_widgets()
        self.root.ids.editor_container.add_widget(CardEditor(card=card))
        self.update_card_preview()

    def update_card_data(self, face, field, value):
        print('update current card', face, field, value)
        if face.get(field, None) != value:
            self.current_card.set(face, field, value)

    def update_card_preview(self):
        print('update card preview', self.current_card)
        if self.scheduled_redraw:
            self.scheduled_redraw.cancel()
        self.scheduled_redraw = Clock.schedule_once(self._update_card_preview, 0.3)

    def _update_card_preview(self, *args, **kwargs):
        try:
            front_image, back_image = self.card_renderer.get_card_textures(self.current_card)
            self.root.ids.card_preview.set_card_images(front_image, back_image)
        except Exception as e:
            self.status_message = str(e)

    def refresh_tree(self):
        self.root.ids.file_browser.refresh()
        self.root.ids.file_browser.refresh()
        self.root.ids.file_browser.refresh()

    def load_project(self, path):
        """ Adds a project to the project explorer """
        if not path or not os.path.exists(path):
            return

        try:
            project = Project.load(path)

            # Update status
            self.status_message = f"Loaded: {os.path.basename(path)}"

        except Exception as e:
            print(e)
            self.status_message = f"Error loading project: {str(e)}"
            self.root.ids.status_bar.text = self.status_message

    def load_file(self, file_path):
        """Load a card from file and update the UI"""
        if not file_path or not os.path.exists(file_path):
            return

        self.current_card_path = file_path

        try:
            self.card_data = Card(file_path)

            # Update card preview
            front_image, back_image = self.card_renderer.get_card_textures(self.card_data)
            self.root.ids.card_preview.set_card_images(front_image, back_image)

            # Update editor
            self.root.ids.editor_container.clear_widgets()
            self.root.ids.editor_container.add_widget(CardEditor(card=self.card_data))

            # Update status
            self.status_message = f"Loaded: {os.path.basename(file_path)}"
            self.root.ids.status_bar.text = self.status_message

        except Exception as e:
            print(e)
            self.status_message = f"Error loading card: {str(e)}"
            self.root.ids.status_bar.text = self.status_message

    def save_current_card(self):
        """Save the currently loaded card"""
        if not self.current_card_path or not self.card_data:
            self.status_message = "No card loaded to save"
            self.root.ids.status_bar.text = self.status_message
            return

        try:
            # Get edited data from the editor
            self.card_data = self.root.ids.card_editor.get_card_data()

            # Save to file
            self.card_data.save()

            # Update preview
            front_image, back_image = self.card_renderer.render_card(self.card_data)
            self.root.ids.card_preview.set_card_images(front_image, back_image)

            self.status_message = f"Saved: {os.path.basename(self.current_card_path)}"
            self.root.ids.status_bar.text = self.status_message

        except Exception as e:
            self.status_message = f"Error saving card: {str(e)}"
            self.root.ids.status_bar.text = self.status_message

    def create_new_card(self):
        """Create a new card file"""
        if not self.project_path:
            self.status_message = "Please open a project folder first"
            self.root.ids.status_bar.text = self.status_message
            return

        # Create a new card file with default data
        new_card_path = os.path.join(self.project_path, "new_card.json")

        # If file exists, increment name
        counter = 1
        while os.path.exists(new_card_path):
            new_card_path = os.path.join(self.project_path, f"new_card_{counter}.json")
            counter += 1

        # Create with default template
        self.card_data = Card.create_default(new_card_path)
        self.card_data.save()

        # Refresh file browser and load the new card
        self.root.ids.file_browser.refresh()
        self.load_card(new_card_path)

        self.status_message = f"Created new card: {os.path.basename(new_card_path)}"
        self.root.ids.status_bar.text = self.status_message

    def export_card(self, file_path=None):
        """Export the current card as an image"""
        if not self.card_data:
            self.status_message = "No card loaded to export"
            self.root.ids.status_bar.text = self.status_message
            return

        try:
            # Generate file path if not provided
            if not file_path:
                basename = os.path.basename(self.current_card_path)
                export_name = os.path.splitext(basename)[0] + ".png"
                file_path = os.path.join(os.path.dirname(self.current_card_path), export_name)

            # Get card images
            front_image, _ = self.card_renderer.get_card_images(self.card_data)

            # Save to file
            front_image.save(file_path, "PNG")

            self.status_message = f"Card exported to: {file_path}"
            self.root.ids.status_bar.text = self.status_message

        except Exception as e:
            self.status_message = f"Error exporting card: {str(e)}"
            self.root.ids.status_bar.text = self.status_message

    def on_stop(self):
        """Clean up when the application stops"""
        if self.file_monitor:
            self.file_monitor.stop()

if __name__ == '__main__':
    ShoggothApp().run()
