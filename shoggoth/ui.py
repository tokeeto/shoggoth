from kivy.uix.colorpicker import StringProperty
from kivy.uix.popup import Popup
from kivy.uix.dropdown import DropDown
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ObjectProperty
from kivy_garden.contextmenu import ContextMenu, ContextMenuTextItem
import filedialpy
from pathlib import Path
from kivy.clock import Clock
import threading
from kivy.uix.scatterlayout import ScatterLayout
from shoggoth import files
from shoggoth.project import Project
import json
import shoggoth
from collections.abc import Callable


about_text = """[size=40]Shoggoth[/size]
[b]Version 0.0.23[/b]
[i](This text doesn't auto-update yet)[/i]

Created by Toke Ivø.

You can support the development of Shoggoth by [u][ref=contrib]contribution[/ref][/u], [u][ref=patreon]donation[/ref][/u], or [u][ref=tip]tips[/ref][/u].

Various images and templates by the Mythos Busters community.

Thanks to CGJennings for creating Strange Eons, and pilunte23/JaqenZann for the original AHLCG plugin, without which we'd all be so much more bored.

Special thanks to Coldtoes, felice, Chr1Z, MickeyTheQ and Morvael for helping this project becoming a reality.
"""


class Zoom(ScatterLayout):
    def on_touch_down(self, touch):
        if not touch.is_mouse_scrolling:
            return super().on_touch_down(touch)

        if not self.collide_point(touch.x, touch.y):
            return False

        if touch.button == 'scrolldown':
            ## zoom in
            if self.scale < 10:
                self.scale = self.scale * 1.1
                return True
        elif touch.button == 'scrollup':
            ## zoom out
            if self.scale > 1:
                self.scale = self.scale * 0.8
                return True
        return False

def set_target(target):
    """ Convinience method for setting fields """
    def method(value):
        target.text = value
    return method


def _save_project_file(target=None, title="expansion.json", name='save_project'):
    """ Returns a file location """
    path = filedialpy.saveFile(
        initial_dir=str(files.get_last_path(name)),
        initial_file=title,
        title="Project file location",
        filter=["*.json","*"],
        confirm_overwrite=True,
    )
    if not path:
        return
    if target:
        def wrapper(*args, **kwargs):
            target.text = path
        Clock.schedule_once(wrapper)
    files.set_last_path(name, path)
    return path


def open_image(target=None, name='open_folder'):
    initial_dir = Path.home
    if files.get_last_path(name).exists():
        initial_dir = files.get_last_path(name)
    if target and target.text:
        if Path(target.text).exists():
            initial_dir = Path(target.text)

    path = filedialpy.openFile(
        initial_dir=str(initial_dir),
        filter=["*.png *.jpg *.jpeg *.webp *.jxl", "*"],
    )
    if not path:
        return
    if target:
        def wrapper(*args, **kwargs):
            target.text = path
        Clock.schedule_once(wrapper)
    files.set_last_path(name, path)
    return path

def open_folder(target=None, name='open_folder'):
    """ Returns a folder location """
    path = filedialpy.openDir(
        initial_dir=str(files.get_last_path(name)),
    )
    if not path:
        return
    if target:
        def wrapper(*args, **kwargs):
            target.text = path
        Clock.schedule_once(wrapper)
    files.set_last_path(name, path)
    return path

def open_file(target=None, name='open_file'):
    """ Returns a file location """
    path = filedialpy.openFile(
        initial_dir=str(files.get_last_path(name)),
    )
    if not path:
        return
    if target:
        def wrapper(*args, **kwargs):
            target.text = path
        Clock.schedule_once(wrapper)
    files.set_last_path(name, path)
    return path

def save_project_file(target, title=''):
    thread = threading.Thread(target=_save_project_file, args=(target, f'{title}.json'))
    thread.start()

def browse_file(target):
    thread = threading.Thread(target=open_file, args=(target,))
    thread.start()

def browse_image(target):
    thread = threading.Thread(target=open_image, args=(target,))
    thread.start()

def browse_folder(target):
    thread = threading.Thread(target=open_folder, args=(target,))
    thread.start()


class StrangeEonsImporter(Popup):
    def submit(self):
        from shoggoth import strange_eons

        project_path = self.ids.se_path.text
        jar_path = shoggoth.app.config.get('Shoggoth', 'strange_eons')
        java_path = shoggoth.app.config.get('Shoggoth', 'java')
        output_path = self.ids.new_path.text

        threading.Thread(target=strange_eons.run_conversion, args=(java_path, jar_path, project_path, output_path)).start()


class Thumbnail(ButtonBehavior, Image):
    card_id = StringProperty("")


class ClassSelectDropdown(DropDown):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def select_value(self, value):
        self.callback(value)


def goto_ref(value):
    import webbrowser
    url = {
        'contrib': 'https://github.com/tokeeto/shoggoth',
        'patreon': 'https://www.patreon.com/tokeeto',
        'tip': 'https://ko-fi.com/tokeeto',
    }[value[1]]
    webbrowser.open_new_tab(url)


class ValueSelectPopup(Popup):
    def __init__(self, callback, **kwargs):
        super().__init__(**kwargs)
        self.callback = callback
        self.populate()

    def populate(self):
        """ empty method for populating data fields """
        pass

    def select(self, value):
        self.dismiss()
        self.callback(value)


class TemplateSelector(ValueSelectPopup):
    pass

class WeaknessTypeSelector(ValueSelectPopup):
    pass

class SetSelector(ValueSelectPopup):
    def populate(self):
        self.ids.option_container.add_widget(
            Button(
                text='Player card',
                on_release=lambda n: self.select(None),
                size_hint_y=None,
                height='32dp',
            )
        )
        project = shoggoth.app.current_project
        for encounter in project.encounter_sets:
            def action(*args, encounter=encounter, **kwargs):
                self.select(encounter)
            self.ids.option_container.add_widget(
                Button(
                    text=encounter.name,
                    on_release=action,
                    size_hint_y=None,
                    height='32dp',
                )
            )

class ValueButton(Button):
    value = ObjectProperty(None)


class TypeSelector(Popup):
    target = ObjectProperty()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.create_values()

    def select(self, widget):
        self.target.text = widget.value
        self.dismiss()

    def create_values(self):
        from shoggoth import files

        for file in files.defaults_dir.iterdir():
            self.ids.content_box.add_widget(
                ValueButton(
                    text=file.stem.capitalize(),
                    value=file.stem,
                    on_release=self.select,
                )
            )

class ExportPopup(Popup):
    pass

class NewProjectPopup(Popup):
    """Popup for selecting files/folders"""
    def save(self):
        data = Project.new(
            self.ids.name.text,
            self.ids.code.text,
            self.ids.icon.text,
        )
        with open(self.ids.file_name.text, 'w') as file:
            json.dump(data, file)

        self.dismiss()
        shoggoth.app.add_project_file(self.ids.file_name.text)

class AboutPopup(Popup):
    """ Information about the application """
    pass

class OkPopup(Popup):
    text = StringProperty("")
    """ Shows a text string, with no interaction """
    pass

class GotoEntryListItem(ButtonBehavior, BoxLayout):
    entry = ObjectProperty()
    callback = ObjectProperty()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class GotoEntry:
    def __init__(self, item, type):
        self.id = str(item.id)
        self.type = type

        if type == 'card':
            if item.encounter:
                self.name = f'{item.expansion.name}/{item.encounter.name}/{item.name}'
            else:
                self.name = f'{item.expansion.name}/{item.name}'
        elif type == 'set':
            self.name = f'{item.expansion.name}/{item.name}'
        elif type == 'project':
            self.name = f'{item.name}'

class GotoPopup(Popup):
    """Popup for selecting files/folders"""
    def __init__(self):
        super().__init__()
        self.entries = []
        self.shown_entries = []
        self.get_all_entries()
        self.ids.input.bind(text=self.filter_entries)

    def get_all_entries(self):
        self.entries = []
        self.entries.extend([GotoEntry(entry, type='card') for entry in shoggoth.app.current_project.get_all_cards()])
        self.entries.extend([GotoEntry(entry, type='set') for entry in shoggoth.app.current_project.encounter_sets])
        self.entries.extend([GotoEntry(shoggoth.app.current_project, type='project')])

    def filter_entries(self, instance, text):
        self.shown_entries = [entry for entry in self.entries if text.lower() in entry.name.lower() or text.lower() in entry.id.lower()]
        self.ids.list.clear_widgets()
        for entry in self.shown_entries:
            self.ids.list.add_widget(GotoEntryListItem(entry=entry, callback=self.go))

    def go(self, entry):
        if entry.type == 'card':
            shoggoth.app.goto_card(entry.id)
        elif entry.type == 'set':
            shoggoth.app.goto_set(entry.id)
        elif entry.type == 'project':
            shoggoth.app.goto_project(entry.id)
        self.dismiss()

def show_file_select(target, callback:Callable):
    target = filedialpy.openFile(
        initial_dir=str(Path.home()),
        filter=['*.json', '*'],
    )
    if target:
        callback(target)

def show_file_save(target, callback:Callable):
    target = filedialpy.saveFile(
        initial_dir=str(Path.home()),
        filter=['*.json', '*'],
    )
    if target:
        callback(target)

def show_class_select(parent, callback:Callable):
    dropdown = ClassSelectDropdown(callback=callback)
    dropdown.open(parent)
