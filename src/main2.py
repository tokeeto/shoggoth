from kivy.app import App
from kivy.uix.floatlayout import FloatLayout
from kivy.factory import Factory
from kivy.properties import ObjectProperty
from kivy.uix.popup import Popup

import os

class Root(FloatLayout):
    loadfile = ObjectProperty(None)
    savefile = ObjectProperty(None)
    text_input = ObjectProperty(None)

    def load(self, path, filename):
        with open(os.path.join(path, filename[0])) as stream:
            self.document.text = stream.read()


class Editor(App):
    pass


Factory.register('Root', cls=Root)


if __name__ == '__main__':
    Editor().run()
