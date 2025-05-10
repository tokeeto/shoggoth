from kivy.uix.popup import Popup
from kivy.uix.dropdown import DropDown
import os


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

def show_file_select(target, callback=None):
    pop = FileChooserPopup(target, callback=callback)
    pop.open()

def show_file_save(target, callback=None):
    pop = FileSavePopup(target, callback=callback)
    pop.open()

def show_class_select(parent, callback):
    dropdown = ClassSelectDropdown(callback=callback)
    dropdown.open(parent)
