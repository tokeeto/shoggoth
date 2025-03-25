from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ObjectProperty, StringProperty, DictProperty
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

class NewEncounterPopup(Popup):
    """Popup for creating new Encounter Set"""
    project = ObjectProperty()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def create(self):
        if self.name.text != '':
            self.project.add_encounter_set(self.name.text)
            self.dismiss()
        else:
            self.error.text = 'You must choose a name'

class ProjectEditor(BoxLayout):
    """Widget for editing card data"""
    project = ObjectProperty()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def callback(self, *args, **kwargs):
        print(args, kwargs)

    def show_new_encounter_popup(self):
        popup = NewEncounterPopup(
            project=self.project,
        )
        popup.open()

class EncounterEditor(BoxLayout):
    """Widget for editing card data"""
    encounter = ObjectProperty()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def callback(self, *args, **kwargs):
        print(args, kwargs)


class CardEditor(BoxLayout):
    """Widget for editing card data"""
    card = ObjectProperty()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.app = App.get_running_app()
        self.front_editor = MAPPING.get(self.card.front.get('type'), FaceEditor)(face=self.card.front)
        self.back_editor = MAPPING.get(self.card.back.get('type'), FaceEditor)(face=self.card.back)
        self.front_editor_container.add_widget(self.front_editor)
        self.back_editor_container.add_widget(self.back_editor)

    def get_card_data(self):
        pass


class FaceEditor(BoxLayout):
    face = ObjectProperty()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class AssetEditor(FaceEditor):
    def debug(self, msg):
        print(msg)


# maps face types to editors
MAPPING = {
    'asset': AssetEditor
}
