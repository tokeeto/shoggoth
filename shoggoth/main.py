import os
import shutil
import threading
import json
from tokenize import String
import shoggoth
from time import time

from kivy.config import Config

if not Config.get('graphics', 'width'):
    Config.set('input', 'mouse', 'mouse,disable_multitouch')
    Config.set('kivy', 'log_enable', '0')
    Config.set('graphics', 'width', '800')
    Config.set('graphics', 'height', '600')
    Config.set('kivy', 'exit_on_escape', 0)
    Config.write()

from kivy.app import App  # noqa: E402
from kivy.uix.boxlayout import BoxLayout    # noqa: E402
from kivy.uix.floatlayout import FloatLayout    # noqa: E402
from kivy.uix.treeview import TreeView, TreeViewLabel    # noqa: E402
from kivy.uix.image import CoreImage    # noqa: E402
from kivy.properties import ObjectProperty, StringProperty  # noqa: E402
from kivy.clock import Clock, mainthread    # noqa: E402
from kivy.core.window import Window    # noqa: E402
from kivy.base import ExceptionHandler, ExceptionManager    # noqa: E402
from kivy.logger import Logger, LOG_LEVELS    # noqa: E402
from kivy.graphics.transformation import Matrix    # noqa: E402

from shoggoth.editor import CardEditor, EncounterEditor, ProjectEditor, NewCardPopup, GuideEditor  # noqa: E402
from shoggoth.project import Project  # noqa: E402
from shoggoth.files import defaults_dir, asset_dir, font_dir, tts_dir  # noqa: E402
from shoggoth.renderer import CardRenderer  # noqa: E402
from shoggoth.file_monitor import FileMonitor  # noqa: E402
from shoggoth.ui import GotoPopup, OkPopup  # noqa: E402

from kivy.storage.jsonstore import JsonStore  # noqa: E402
from shoggoth.ui import show_file_select, Thumbnail  # noqa: E402
from pathlib import Path  # noqa: E402
from kivy.modules import inspector  # noqa: E402

try:
    from ctypes import windll
    windll.user32.SetProcessDpiAwarenessContext(-4)
except ImportError:
    pass

Logger.setLevel(LOG_LEVELS["warning"])


class ShoggothRoot(FloatLayout):
    """Root widget for the Shoggoth application"""
    bg_path = StringProperty("")

    def __init__(self, **kwargs):
        super(ShoggothRoot, self).__init__(**kwargs)
        Window.bind(on_key_down=self.on_keyboard)
        Window.bind(on_resize=self.on_resize)
        Window.bind(on_maximize=self.on_maximize)
        Window.bind(on_restore=self.on_restore)
        bg_file = asset_dir/'parchment2.png'
        try:
            self.bg_path = str(bg_file)
        except Exception as e:
            print(f"Error loading background image: {e}")
        ExceptionManager.add_handler(Wing())

    def on_maximize(self, window):
        Config.set('graphics', 'maximized', True)
        Config.write()

    def on_restore(self, window):
        Config.set('graphics', 'maximized', False)
        Config.write()

    def on_resize(self, window, width, height):
        Config.set('graphics', 'width', width)
        Config.set('graphics', 'height', height)
        Config.write()

    def on_keyboard(self, instance, keyboard, keycode, text, modifiers):
        # Handle keyboard shortcuts
        if 'ctrl' in modifiers:
            if text == 's':
                if 'shift' in modifiers:
                    f = shoggoth.app.save_changes
                else:
                    f = shoggoth.app.save_current
                Clock.schedule_once(lambda x: f())
                return True
            if text == 'n':
                f = shoggoth.app.open_new_card_dialog
                Clock.schedule_once(lambda x: f())
                return True
            if text == 'm':
                shoggoth.app.number_cards()
                return True
            if text == 'e':
                if 'shift' in modifiers:
                    Clock.schedule_once(lambda x: shoggoth.app.export_all(bleed=True, format='png', quality=100))
                    return True
                else:
                    Clock.schedule_once(lambda x: shoggoth.app.export_current(bleed=False, format='png', quality=100))
                    return True
            if text == 'o':
                f = shoggoth.app.open_project_dialog
                Clock.schedule_once(lambda x: f())
                return True
            if text == 'p':
                f = shoggoth.app.show_goto_dialog
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
        if isinstance(exception, KeyboardInterrupt):
            return ExceptionManager.RAISE
        # Everything else, is expected to be unhandled exceptions that
        # Should then pop up in front of the user
        shoggoth.app.show_ok_dialog(f'Something unexpected happened. This is a last effort to show you what happened. Maybe Shoggoth will crash after this.\n\n{exception}\n\n{traceback.format_exc(limit=-5)}')
        return ExceptionManager.PASS


class FileBrowser(BoxLayout):
    """File browser widget showing project files"""
    project = ObjectProperty()
    selected_item = ObjectProperty(None)
    tree: TreeView

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(project=self.refresh)

    def on_selected_node(self):
        app = shoggoth.app
        if self.tree.selected_node.element_type == 'project':
            app.show_project(self.tree.selected_node.element)
        elif self.tree.selected_node.element_type == 'encounter':
            app.show_encounter(self.tree.selected_node.element)
        elif self.tree.selected_node.element_type == 'card':
            app.show_card(self.tree.selected_node.element)
        elif self.tree.selected_node.element_type == 'guide':
            app.show_guide(self.tree.selected_node.element)
        if self.tree.selected_node.element:
            self.selected_item = self.tree.selected_node.element

    def refresh(self, *args):
        opens = set()
        for node in self.tree.iterate_open_nodes():
            if not isinstance(node, TreeViewButton):
                continue
            print('node is open:', node.name_path)
            opens.add(node.name_path)
        # Clear tree
        for node in self.tree.root.nodes:
            self.tree.remove_node(node)

        # Recursively add files and folder
        self._add_nodes()
        for node in self.tree.iterate_all_nodes():
            if not isinstance(node, TreeViewButton):
                continue
            if node.name_path in opens:
                if not node.parent_node.is_open:
                    self.tree.toggle_node(node.parent_node)

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
                self.tree.add_node(TreeViewButton(text=card.name, element=card, element_type='card'), target_node)

        class_nodes = {}
        class_labels = {
            'investigators': 'Investigators',
            'seeker': f'[size=24][color=#c3901b][font={str(font_dir / "AHLCGSymbol.otf")}]K[/font][/color][/size] Seeker',
            'rogue': f'[size=24][color=#0f703f][font={str(font_dir / "AHLCGSymbol.otf")}]R[/font][/color][/size] Rogue',
            'guardian': f'[size=24][color=#3a75c3][font={str(font_dir / "AHLCGSymbol.otf")}]G[/font][/color][/size] Guardian',
            'mystic': f'[size=24][color=#473e7e][font={str(font_dir / "AHLCGSymbol.otf")}]M[/font][/color][/size] Mystic',
            'survivor':  f'[size=24][color=#c12830][font={str(font_dir / "AHLCGSymbol.otf")}]V[/font][/color][/size] Survivor',
            'neutral': 'Neutral',
            'other': 'Other',
        }
        for cls in ('investigators', 'seeker', 'rogue', 'guardian', 'mystic', 'survivor', 'neutral', 'other'):
            class_nodes[cls] = self.tree.add_node(TreeViewButton(text=class_labels[cls], element=None, element_type=''), player_node)

        investigator_nodes = {}

        for card in self.project.player_cards:
            if group := card.data.get('investigator', False):
                target_node = class_nodes.get('investigators')
                if not investigator_nodes.get(group):
                    investigator_nodes[group] = self.tree.add_node(TreeViewButton(text=group, element=None, element_type=''), target_node)
                target_node = investigator_nodes[group]
            else:
                target_node = class_nodes.get(card.get_class(), class_nodes['other'])
            display_name = f'{card.name} ({card.front.get("level")})' if str(card.front.get('level', '0')) != '0' else card.name
            self.tree.add_node(TreeViewButton(text=display_name, element=card, element_type='card'), target_node)

        if self.project.guides:
            guide_node = self.tree.add_node(TreeViewButton(text='Guides', element=None, element_type=''), p_node)

        for guide in self.project.guides:
            self.tree.add_node(TreeViewButton(text=guide.name, element=guide, element_type='guide'), guide_node)


    # def on_tree_select(self, instance, node):
    #     if hasattr(node, 'full_path') and node.full_path.endswith('.json'):
    #         self.parent.parent.load_card(node.full_path)


class TreeViewButton(TreeViewLabel):
    element = ObjectProperty()
    element_type = StringProperty('')
    _name_path = None

    def __init__(self, *args, **kwargs):
        self._name_path = None
        super().__init__(*args, **kwargs)

    @property
    def name_path(self):
        if not self._name_path:
            if not isinstance(self.parent_node, TreeViewButton):
                self._name_path = self.text
            else:
                self._name_path = self.parent_node.name_path + '/' + self.text
        return self._name_path


class CardPreview(BoxLayout):
    """Widget for displaying card previews"""

    def set_card_images(self, front_image, back_image):
        if front_image:
            self.ids.front_preview.texture = front_image
            self.ids.front_preview.texture.mag_filter = 'nearest'
        if back_image:
            self.ids.back_preview.texture = back_image
            self.ids.back_preview.texture.mag_filter = 'nearest'

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
    current_card = ObjectProperty(None, allownone=True)
    status_message = StringProperty("Ready")

    def __init__(self, *args, **kwargs):
        shoggoth.app = self
        super().__init__(*args, **kwargs)

    def build(self):
        self.icon = str(asset_dir / 'elder_sign_neon.png')
        # Initialize main components
        self.storage = JsonStore('shoggoth.json')
        self.root = ShoggothRoot()

        # Initialize card renderer
        self.card_renderer = CardRenderer()
        self.scheduled_redraw = None

        self.refresh_tree_timer = None

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
        #inspector.create_inspector(Window, self.root)

        return self.root

    def build_config(self, config):
        config.setdefaults('Shoggoth', {
            'prince_cmd': 'prince',
            'prince_dir': '',
            'strange_eons': '',
            'java': 'java',
        })

    def build_settings(self, settings):
        data = [
            {
                "type": "title",
                "title": "External applications",
            },
            { 
                "type": "string",
                "title": "Prince command",
                "desc": "Command to run prince",
                "section": "Shoggoth",
                "key": "prince_cmd",
            },
            {
                "type": "path",
                "title": "Prince location",
                "desc": "Location of the Prince directory, if not installed system wide.",
                "section": "Shoggoth",
                "key": "prince_dir",
            },
            {
                "type": "path",
                "title": "Strange Eons",
                "desc": "Location of the Strange Eons jar file. For use with importing SE projects.",
                "section": "Shoggoth",
                "key": "strange_eons",
            },
            {
                "type": "string",
                "title": "Java command",
                "desc": "Command to run java. Used in conjunction with Strange Eons.",
                "section": "Shoggoth",
                "key": "java",
            },
        ]

        settings.add_json_panel(
            'Shoggoth',
            self.config,
            data=json.dumps(data)
        )

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

    def export_card_to_tts(self):
        if not self.current_card:
            return
        from shoggoth import tts_lib
        tts_lib.export_card(self.current_card)

    def export_player_to_tts(self):
        from shoggoth import tts_lib
        tts_lib.export_player_cards(self.current_project.player_cards)

    def export_campaign_to_tts(self):
        from shoggoth import tts_lib
        tts_lib.export_campaign(self.current_project)

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
        self.current_project.assign_card_numbers()
        self.status_message = "Updated card numbers"
        self.update_card_preview()

    def save_changes(self):
        """ Saves the entire project.
        """
        self.current_project.save()

    def save_current(self):
        """ Saves the currently selected item
            and no sub items.
        """
        self.root.ids.file_browser.selected_item.save()

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

    def show_guide(self, guide):
        self.current_guide = guide
        self.current_guide_id = guide.id
        self.storage.put('session', project=self.current_project.file_path, last_id=guide.id)
        self.root.ids.editor_container.clear_widgets()

        self.root.ids.editor_container.add_widget(GuideEditor(guide=self.current_guide))
        # self.update_card_preview()
        # todo: change to guide preview

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
            face.set(field, value)

    def update_card_preview(self):
        if not self.current_card:
            return
        t = threading.Thread(target=self._update_card_preview)
        t.start()

    def _update_card_preview(self, *args, **kwargs):
        try:
            t = time()
            front_image, back_image = self.card_renderer.get_card_textures(self.current_card, bleed=False)
            print(f'Generated images in {time()-t} seconds')
            self._update_card_preview_texture(front_image, back_image)
        except Exception as e:
            self.status_message = str(e)

    @mainthread
    def _update_card_preview_texture(self, front_image, back_image):
        t = time()
        front_texture = CoreImage(front_image, ext='jpeg').texture
        back_texture = CoreImage(back_image, ext='jpeg').texture
        print(f'Generated textures in {time()-t} seconds')
        self.root.ids.card_preview.set_card_images(front_texture, back_texture)

    def _refresh_tree(self, *args, **kwargs):
        self.root.ids.file_browser.refresh()

    def refresh_tree(self):
        if self.refresh_tree_timer:
            self.refresh_tree_timer.cancel()
        self.refresh_tree_timer = Clock.schedule_once(self._refresh_tree, 1)

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
                    except KeyError:
                        Logger.info(f'Field not found on card during gathering: {card.name}:{side}:{field}')
                    except Exception as e:
                        Logger.error(f'Something went wrong during gathering: {e}')
        print(gathered)

    def export_current(self, include_backs:bool=False, bleed:bool=True, format:str='png', quality:int=100):
        if not self.current_card:
            raise Exception("Cannot export a card, while no card is selected.")
        export_folder = os.path.join(
            os.path.dirname(self.current_project.file_path),
            f'Export of {self.current_project.name}'
        )
        os.makedirs(export_folder, exist_ok=True)
        t = time()
        self.card_renderer.export_card_images(
            self.current_card,
            export_folder,
            include_backs=include_backs,
            bleed=bleed,
            format=format,
            quality=quality
        )
        print(f'Export of {self.current_card.name} done in {time()-t} seconds')

    def export_all(self, include_backs:bool=False, bleed:bool=True, format:str='png', quality:int=100):
        export_folder = os.path.join(
            os.path.dirname(self.current_project.file_path),
            f'Export of {self.current_project.name}'
        )
        os.makedirs(export_folder, exist_ok=True)
        cards = self.current_project.get_all_cards()
        t = time()

        # spawn threads to write card files
        threads = []
        for card in cards:
            Logger.debug(f'added {card.name} to queue')
            thread = threading.Thread(
                target=self.card_renderer.export_card_images,
                args=(card, export_folder),
                kwargs={'include_backs': include_backs, 'bleed': bleed, 'format': format, 'quality': quality}
            )
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
