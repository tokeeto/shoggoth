from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ObjectProperty, StringProperty, DictProperty
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from card import Card


class NewCardPopup(Popup):
    """Popup for creating new card"""
    target = ObjectProperty()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def create(self):
        if self.name.text == '':
            self.error.text = 'You must choose a name'
            return

        self.target.add_card(Card.new(self.name.text))
        App.get_running_app().refresh_tree()
        self.dismiss()


class NewEncounterPopup(Popup):
    """Popup for creating new Encounter Set"""
    project = ObjectProperty()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def create(self):
        if self.name.text != '':
            self.project.add_encounter_set(self.name.text)
            App.get_running_app().refresh_tree()
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

    def new_card(self):
        popup = NewCardPopup(
            target=self.encounter,
        )
        popup.open()


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

    def update_data(self, *args, **kwargs):
        import ast
        try:
            self.face.data = ast.literal_eval(self.raw_text.text)
        except:
            pass

class AssetEditor(FaceEditor):
    pass

class EventEditor(FaceEditor):
    pass

class SkillEditor(FaceEditor):
    pass

class InvestigatorEditor(FaceEditor):
    pass

class InvestigatorBackEditor(FaceEditor):
    pass

class LocationEditor(FaceEditor):
    pass

class TreaceryEditor(FaceEditor):
    pass

class EnemyEditor(FaceEditor):
    pass



# maps face types to editors
MAPPING = {
    'asset': AssetEditor,
    'event': EventEditor,
    'skill': SkillEditor,
    'investigator': InvestigatorEditor,
    'investigator_back': InvestigatorBackEditor,
    'location': LocationEditor,
    'treacery': TreaceryEditor,
    'enemy': EnemyEditor,
}
