from kivy.uix.popup import Popup
from kivy.uix.dropdown import DropDown
from kivy.uix.button import Button
from kivy.app import App
from kivy.properties import ObjectProperty
from kivy_garden.contextmenu import ContextMenu, ContextMenuTextItem
import os
from shoggoth import card


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
    pop = FileChooserPopup(target, callback=callback)
    pop.open()

def show_file_save(target, callback=None):
    pop = FileSavePopup(target, callback=callback)
    pop.open()

def show_class_select(parent, callback):
    dropdown = ClassSelectDropdown(callback=callback)
    dropdown.open(parent)
