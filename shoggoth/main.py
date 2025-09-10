import os
import json
import shutil
import threading
from time import time

from kivy.config import Config

Config.set('input', 'mouse', 'mouse,disable_multitouch')
Config.set('kivy', 'log_enable', '0')
Config.set('graphics', 'width', '1600')
Config.set('graphics', 'height', '900')
os.environ['KIVY_IMAGE'] = 'pil'

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.treeview import TreeView, TreeViewLabel
from kivy.uix.popup import Popup
from kivy.uix.image import Image, CoreImage
from kivy.uix.behaviors import ButtonBehavior, FocusBehavior, DragBehavior
from kivy.properties import ObjectProperty, StringProperty, BooleanProperty, ListProperty
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.base import ExceptionHandler, ExceptionManager
from kivy.logger import Logger, LOG_LEVELS
from kivy.graphics.transformation import Matrix

from shoggoth.editor import CardEditor, EncounterEditor, ProjectEditor, NewCardPopup
from shoggoth.project import Project
from shoggoth.files import defaults_dir, asset_dir
from shoggoth.renderer import CardRenderer
from shoggoth.file_monitor import FileMonitor
from shoggoth.ui import GotoPopup, OkPopup

from kivy.storage.jsonstore import JsonStore
from shoggoth.ui import show_file_select, Thumbnail
from pathlib import Path
from kivy.core.clipboard import Clipboard


Logger.setLevel(LOG_LEVELS["info"])

class ShoggothRoot(FloatLayout):
    """Root widget for the Shoggoth application"""
    bg_path = StringProperty("")

    def __init__(self, **kwargs):
        super(ShoggothRoot, self).__init__(**kwargs)
        Window.bind(on_key_down=self.on_keyboard)
        bg_file = asset_dir/'parchment2.png'
        try:
            self.bg_path = str(bg_file)
        except Exception as e:
            print(f"Error loading background image: {e}")
        ExceptionManager.add_handler(Wing())

    def on_keyboard(self, instance, keyboard, keycode, text, modifiers):
        # Handle keyboard shortcuts
        if 'ctrl' in modifiers:
            if text == 's':
                f = App.get_running_app().save_changes
                Clock.schedule_once(lambda x: f())
                return True
            if text == 'n':
                f = App.get_running_app().open_new_card_dialog
                Clock.schedule_once(lambda x: f())
                return True
            if text == 'm':
                App.get_running_app().number_cards()
                return True
            if text == 'e':
                if 'shift' in modifiers:
                    f = App.get_running_app().export_all
                    Clock.schedule_once(lambda x: f())
                    return True
                else:
                    f = App.get_running_app().export_current
                    Clock.schedule_once(lambda x: f())
                    return True
            if text == 'o':
                f = App.get_running_app().open_project_dialog
                Clock.schedule_once(lambda x: f())
                return True
            if text == 'p':
                f = App.get_running_app().show_goto_dialog
                Clock.schedule_once(lambda x: f())
                return True
        return False

class Wing(ExceptionHandler):
    """ Exception handle, that carries off
        unhandled exceptions to a central location
    """
    def __init__(self):
        super().__init__()

    def handle_exception(self, exception):
        import traceback
        print("*** Exception handled by Wing ***")
        print(exception)
        print("*********************************")
        # Keyboard Interrupts should just kill the application.
        if type(exception) == KeyboardInterrupt:
            return ExceptionManager.RAISE
        # Everything else, is expected to be unhandled exceptions that
        # Should then pop up in front of the user
        App.get_running_app().show_ok_dialog(f'Something unexpected happened. This is a last effort to show you what happened. Maybe Shoggoth will crash after this.\n\n{exception}\n\n{traceback.format_exc(limit=-5)}')
        return ExceptionManager.PASS


class FileBrowser(BoxLayout):
    """File browser widget showing project files"""
    project = ObjectProperty()
    tree: TreeView

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(project=self.refresh)

    def on_selected_node(self):
        app = App.get_running_app()
        if self.tree.selected_node.element_type == 'project':
            app.show_project(self.tree.selected_node.element)
        elif self.tree.selected_node.element_type == 'encounter':
            app.show_encounter(self.tree.selected_node.element)
        elif self.tree.selected_node.element_type == 'card':
            app.show_card(self.tree.selected_node.element)

    def refresh(self, *args):
        opens = set()
        for node in self.tree.iterate_open_nodes():
            opens.add((node.level, node.text))
        print('clearing tree, project is now', self.project)
        # Clear tree
        for node in self.tree.root.nodes:
            self.tree.remove_node(node)

        # Recursively add files and folder
        self._add_nodes()
        for node in self.tree.iterate_all_nodes():
            if (node.level, node.text) in opens:
                self.tree.toggle_node(node)

    def _add_nodes(self):
        # Add folder contents to tree
        p_node = self.tree.add_node(TreeViewButton(text=self.project['name'], element=self.project, element_type='project'))

        if self.project.encounter_sets and self.project.cards:
            campaign_node = self.tree.add_node(TreeViewButton(text='Campaign cards', element=None, element_type=''), p_node)
            player_node = self.tree.add_node(TreeViewButton(text='Player cards', element=None, element_type=''), p_node)
        else:
            campaign_node = player_node = p_node

        for encounter_set in self.project.encounter_sets:
            e_node = self.tree.add_node(TreeViewButton(text=encounter_set.name, element=encounter_set, element_type='encounter'), campaign_node)
            story_node = self.tree.add_node(TreeViewButton(text='Story', element=None, element_type=''), e_node)
            location_node = self.tree.add_node(TreeViewButton(text='Locations', element=None, element_type=''), e_node)
            encounter_node = self.tree.add_node(TreeViewButton(text='Encounter', element=None, element_type=''), e_node)
            for card in encounter_set.cards:
                if card.front.get('type') == 'location':
                    target_node = location_node
                elif card.back.get('type') == 'encounter':
                    target_node = encounter_node
                else:
                    target_node = story_node
                c_node = self.tree.add_node(TreeViewButton(text=card.name, element=card, element_type='card'), target_node)

        class_nodes = {}
        for cls in ('investigators', 'seeker', 'rogue', 'guardian', 'mystic', 'survivor', 'neutral', 'other'):
            class_nodes[cls] = self.tree.add_node(TreeViewButton(text=cls, element=None, element_type=''), player_node)

        investigator_nodes = {}

        for card in self.project.player_cards:
            if group := card.data.get('investigator', False):
                target_node = class_nodes.get('investigators')
                if not investigator_nodes.get(group):
                    investigator_nodes[group] = self.tree.add_node(TreeViewButton(text=group, element=None, element_type=''), target_node)
                target_node = investigator_nodes[group]
            else:
                target_node = class_nodes.get(card.get_class(), class_nodes['other'])
            c_node = self.tree.add_node(TreeViewButton(text=card.name, element=card, element_type='card'), target_node)

    def on_tree_select(self, instance, node):
        if hasattr(node, 'full_path') and node.full_path.endswith('.json'):
            self.parent.parent.load_card(node.full_path)


class TreeViewButton(TreeViewLabel):
    element = ObjectProperty()
    element_type = StringProperty('')


class CardPreview(BoxLayout):
    """Widget for displaying card previews"""
    def set_card_images(self, front_image, back_image):
        self.ids.front_preview.texture = front_image
        self.ids.back_preview.texture = back_image

    def touch_scatter(self, touch, target):
        if touch.is_mouse_scrolling:
            factor = None
            if touch.button == 'scrolldown':
                if target.scale < target.scale_max:
                    factor = 1.1
            elif touch.button == 'scrollup':
                if target.scale > target.scale_min:
                    factor = 1 / 1.1
            if factor is not None:
                target.apply_transform(Matrix().scale(factor, factor, factor), anchor=touch.pos)


class ShoggothApp(App):
    """Main application class for Shoggoth Card Creator"""
    current_card_id = StringProperty("")
    current_project = ObjectProperty(None)
    status_message = StringProperty("Ready")

    def build(self):
        self.icon = str(asset_dir / 'elder_sign_neon.png')
        # Initialize main components
        self.storage = JsonStore('shoggoth.json')
        self.root = ShoggothRoot()

        # Initialize card renderer
        self.card_renderer = CardRenderer()
        self.scheduled_redraw = None

        # Initialize file monitoring
        self.file_monitor = FileMonitor(None, self.on_file_changed)

        # Initialize asset monitoring
        self.assets_monitor = FileMonitor(defaults_dir, self.on_file_changed)
        self.assets_monitor.start()

        # build a session object if one doesn't exist
        if not self.storage.exists('session'):
            print('no defaults, creating new storage')
            self.storage.put('session', project=None, last_id=None)

        # restore the existing session
        try:
            if 'project' in self.storage.get('session'):
                self.current_project = Project.load(self.storage.get('session')['project'])
                self.root.ids.file_browser.project = self.current_project

            if 'last_id' in self.storage.get('session'):
                id = self.storage.get('session')['last_id']
                Clock.schedule_once(lambda x: self.goto_card(id), 1)
        except:
            pass

        return self.root

    def goto_project(self, project_id):
        self.current_project = Project.load(project_id)
        self.root.ids.file_browser.project = self.current_project

    def goto_set(self, set_id):
        self.current_project = Project.load(self.storage.get('session')['project'])
        self.root.ids.file_browser.project = self.current_project

    def goto_card(self, card_id):
        print(f'looking for card with id {card_id}')
        tree = self.root.ids.file_browser.tree
        for node in tree.iterate_all_nodes():
            try:
                if str(node.element.id) == str(card_id):
                    tree.select_node(node)
                    parent = node.parent_node
                    while parent:
                        if not parent.is_open:
                            tree.toggle_node(parent)
                        parent = parent.parent_node
                    return
            except AttributeError:
                continue
        print('Card not found')

    def show_goto_dialog(self):
        if not self.current_project:
            return
        goto_dialog = GotoPopup()
        goto_dialog.open()
        goto_dialog.ids.input.focus = True

    def show_ok_dialog(self, text):
        dialog = OkPopup(text=text)
        dialog.open()

    def open_project_dialog(self):
        """Show file chooser dialog to select project folder"""
        show_file_select(None, callback=self.add_project_file)

    def open_new_card_dialog(self):
        dialog = NewCardPopup()
        dialog.open()

    def add_project_file(self, path):
        """Set the project path and initialize monitoring"""
        if not path:
            return

        project = Project.load(path)
        self.root.ids.file_browser.project = project
        self.current_project = project
        self.current_card = None
        self.storage.put('session', project=path)

        self.status_message = f"Project opened: {self.current_project.get('name')}"
        self.root.ids.status_bar.text = self.status_message

    def on_file_changed(self, file_path):
        """Handle file changes outside the editor"""
        if self.current_card:
            self.current_card.reload_fallback()
            self.update_card_preview()

    def number_cards(self):
        self.current_card.expansion.assign_card_numbers()
        self.status_message = f"Updated card numbers"
        self.update_card_preview()

    def save_changes(self):
        self.current_project.save()

    def show_project(self, project):
        self.root.ids.editor_container.clear_widgets()
        self.root.ids.editor_container.add_widget(ProjectEditor(project=project))

    def show_encounter(self, encounter):
        self.root.ids.editor_container.clear_widgets()
        self.root.ids.editor_container.add_widget(EncounterEditor(encounter=encounter))

    def show_card(self, card):
        self.current_card = card
        self.current_card_id = card.id
        self.storage.put('session', project=self.current_project.file_path, last_id=card.id)
        self.root.ids.editor_container.clear_widgets()

        # TODO: Observe card specific files here.

        self.root.ids.editor_container.add_widget(CardEditor(card=self.current_card))
        self.update_card_preview()

    def update_texture(self, texture, container, card):
        img = Thumbnail(card_id=card.id)
        container.add_widget(img)
        img.texture = CoreImage(texture, ext='jpeg').texture

    def render_thumbnail(self, card, container):
        texture = self.card_renderer.get_thumbnail(card)
        Clock.schedule_once(lambda x:self.update_texture(texture, container, card))

    def update_card_data(self, face, field, value):
        print('update current card', face, field, value)
        if face.get(field, None) != value:
            self.current_card.set(face, field, value)

    def update_card_preview(self):
        if not self.current_card:
            return
        t = threading.Thread(target=self._update_card_preview)
        t.start()

    def _update_card_preview(self, *args, **kwargs):
        try:
            front_image, back_image = self.card_renderer.get_card_textures(self.current_card)
            self._update_card_preview_texture(front_image, back_image)
        except Exception as e:
            self.status_message = str(e)

    @mainthread
    def _update_card_preview_texture(self, front_image, back_image):
        front_texture = CoreImage(front_image, ext='webp').texture
        back_texture = CoreImage(back_image, ext='webp').texture
        self.root.ids.card_preview.set_card_images(front_texture, back_texture)

    def refresh_tree(self):
        self.root.ids.file_browser.refresh()

    def gather_images(self, output_folder=None, update=False):
        """ Gathers all images on cards

            All images are copied to the specified folder.
            If :update: is True, card references are update
            to point to the new output location.
        """
        print('gathering images', output_folder, update)

        def copy_gathered_image(path, folder) -> str:
            if not (folder / path.name).exists():
                shutil.copy(path, folder)
                return path.name

            i = 0
            new_name = f'{path.stem}_{i}{path.suffix}'
            while (folder/new_name).exists():
                i += 1
                new_name = f'{path.stem}_{i}{path.suffix}'

            shutil.copy(path, folder/new_name)
            return new_name

        parent_folder = Path(self.current_project.file_path).parent
        if not output_folder:
            output_folder = parent_folder / f'{self.current_project.name}_resources'
            if not output_folder.is_dir():
                os.mkdir(output_folder)
        else:
            output_folder = Path(output_folder)
        relative_folder = output_folder.relative_to(parent_folder) or output_folder

        # old path: new path
        gathered = {}

        # gather icon for project
        icon_path = Path(self.current_project.icon)
        if self.current_project.icon and icon_path.is_file():
            new_name = copy_gathered_image(icon_path, output_folder)
            gathered[icon_path] = str(relative_folder / new_name)
            if update:
                self.current_project.icon = gathered[icon_path]

        # gather all icons for sets
        for set in self.current_project.encounter_sets:
            icon_path = Path(set.icon)
            if not set.icon or not icon_path.is_file():
                continue

            if icon_path not in gathered:
                new_name = copy_gathered_image(icon_path, output_folder)
                gathered[icon_path] = str(relative_folder / new_name)
            if update:
                set.icon = gathered[icon_path]

        # gather illustrations, templates and defaults for cards
        for card in self.current_project.get_all_cards():
            for side in ('front', 'back'):
                for field in ('illustration', 'template', 'type'):
                    try:
                        img_path = Path(card.data[side][field])
                        if not img_path.is_file():
                            Logger.error(f'Path is not a file: {img_path}, on card: {card.name}')
                            continue
                        new_name = copy_gathered_image(img_path, output_folder)
                        gathered[img_path] = str(relative_folder / new_name)
                        if update:
                            card.data[side][field] = gathered[img_path]
                    except KeyError as e:
                        Logger.info(f'Field not found on card during gathering: {card.name}:{side}:{field}')
                    except Exception as e:
                        Logger.error(f'Something went wrong during gathering:', e)
        print(gathered)

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

    def export_current(self):
        export_folder = os.path.join(
            os.path.dirname(self.current_project.file_path),
            f'export_of_{os.path.basename(self.current_project.file_path).split(".")[1]}'
        )
        os.makedirs(export_folder, exist_ok=True)
        t = time()
        self.card_renderer.export_card_images(self.current_card, export_folder)
        print(f'Export of {self.current_card.name} done in {time()-t} seconds')

    def export_all(self):
        export_folder = os.path.join(
            os.path.dirname(self.current_project.file_path),
            f'export_of_{os.path.basename(self.current_project.file_path).split(".")[1]}'
        )
        os.makedirs(export_folder, exist_ok=True)
        cards = self.current_project.get_all_cards()
        t = time()

        # spawn threads to write card files
        threads = []
        for card in cards:
            Logger.debug(f'added {card.name} to queue')
            thread = threading.Thread(target=self.card_renderer.export_card_images, args=(card, export_folder))
            threads.append(thread)
            thread.start()

        # wait for all threads to finish
        for thread in threads:
            thread.join()

        print(f'Export of {len(cards)} cards done in {time()-t} seconds')


    def on_stop(self):
        """Clean up when the application stops"""
        if self.file_monitor:
            self.file_monitor.stop()

if __name__ == "__main__":
    ShoggothApp().run()
