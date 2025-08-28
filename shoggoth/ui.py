from kivy.uix.colorpicker import StringProperty
from kivy.uix.popup import Popup
from kivy.uix.dropdown import DropDown
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.behaviors import ButtonBehavior
from kivy.app import App
from kivy.properties import ObjectProperty
from kivy_garden.contextmenu import ContextMenu, ContextMenuTextItem
import os
from shoggoth import card
import filedialpy
from pathlib import Path
from kivy.clock import Clock
import threading


about_text = """
Created by Toke Ivø.

You can support the development of Shoggoth by [u][ref=contrib]contribution[/ref][/u], [u][ref=patreon]donation[/ref][/u], or [u][ref=tip]tips[/ref][/u].

Various images by the Mythos Busters community.

Special thanks to Coldtoes, felice, Chr1Z and MickeyTheQ.
"""


def save_project_dialog():
    """ Returns a file location """
    return filedialpy.saveFile(
        initial_dir=str(Path.home()),
        initial_file="expansion.json",
        title="Project file location",
        filter=["*.json","*"],
        confirm_overwrite=True,
    )

def async_open_image(target):
    path = filedialpy.openFile(
        initial_dir=str(Path.home()),
        filter=["*.png *.jpg *.jpeg", "*"],
    )
    if not path:
        return
    def wrapper(*args, **kwargs):
        target.text = path
    Clock.schedule_once(wrapper)

def browse_image(target):
    thread = threading.Thread(target=async_open_image, args=(target,))
    thread.start()

def open_image():
    """ Returns a file location """
    return filedialpy.openFile(
        initial_dir=str(Path.home()),
        filter=["*.png *.jpg *.jpeg", "*"],
    )

def open_file():
    """ Returns a file location """
    return filedialpy.openFile(
        initial_dir=str(Path.home()),
    )

class Thumbnail(ButtonBehavior, Image):
    card_id = StringProperty("")

class FileChooserPopup(Popup):
    """Popup for selecting files/folders"""
    def __init__(self, field, callback=None):
        super().__init__()
        self.field = field
        self.callback = callback
        self.ids.filechooser.path = os.path.expanduser("~/Documents")

    def select(self, path, file_name):
        self.dismiss()
        if self.callback:
            self.callback(os.path.join(path, file_name))
            return
        self.field.text = os.path.join(path, file_name)


class FileSavePopup(Popup):
    """Popup for selecting files/folders"""
    def __init__(self, field, callback=None):
        super().__init__()
        self.field = field
        self.callback = callback
        self.ids.filechooser.path = os.path.expanduser("~/Documents")

    def select(self, path, file_name):
        self.dismiss()
        if self.callback:
            self.callback(os.path.join(path, file_name))
            return
        self.field.text = os.path.join(path, file_name)

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
        project = App.get_running_app().current_project
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



class TypeSelectDropdown(ContextMenu):
    target = ObjectProperty()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.create_values()

    def select(self, widget):
        print('select with', widget)
        self.target.input.text = widget.text
        self.hide()

    def create_values(self):
        from shoggoth import files

        for file in files.defaults_dir.iterdir():
            self.add_widget(
                ContextMenuTextItem(
                    text=file.stem,
                    on_release=self.select,
                )
            )


def show_file_select(target, callback=None):
    target = filedialpy.openFile(
        initial_dir=str(Path.home()),
        filter=['*.json', '*'],
    )
    if target:
        callback(target)

def show_file_save(target, callback=None):
    target = filedialpy.saveFile(
        initial_dir=str(Path.home()),
        filter=['*.json', '*'],
    )
    if target:
        callback(target)

def show_class_select(parent, callback):
    dropdown = ClassSelectDropdown(callback=callback)
    dropdown.open(parent)
