from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ObjectProperty, StringProperty, DictProperty
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.floatlayout import FloatLayout
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


class CardField:
    def __init__(self, widget, card_key, converter=str):
        self.widget = widget
        self.card_key = card_key
        self.converter = converter
        self._updating = False

    def update_from_card(self, card_data):
        self._updating = True
        value = card_data.get(self.card_key, '')
        self.widget.text = str(value) if value else ''
        self._updating = False

    def update_card(self, card_data, value):
        if self._updating:
            return False

        try:
            card_data.set(self.card_key, self.converter(value) if value else None)
            return True
        except ValueError:
            return False


class FaceEditor(FloatLayout):
    face = ObjectProperty()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields = []
        self._setup_fields()
        self.load_card(self.face)

    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            CardField(self.ids.type.input, 'type'),
            CardField(self.ids.amount.input, 'amount'),
            CardField(self.ids.collection_number.input, 'collection_number'),
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))

    def load_card(self, card_data):
        for field in self.fields:
            field.update_from_card(self.face)

    def _on_field_changed(self, field, value):
        field.update_card(self.face, value)


class AssetEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            CardField(self.ids.type.input, 'type'),
            CardField(self.ids.name.input, 'name'),
            CardField(self.ids.subtitle.input, 'subtitle'),
            CardField(self.ids.traits.input, 'traits'),
            CardField(self.ids.card_class.input, 'class'),
            CardField(self.ids.classes.input, 'classes', list),
            CardField(self.ids.cost.input, 'cost'),
            CardField(self.ids.level.input, 'level'),
            CardField(self.ids.stamina.input, 'stamina'),
            CardField(self.ids.sanity.input, 'sanity'),
            CardField(self.ids.text.input, 'text'),
            CardField(self.ids.flavor_text.input, 'flavor_text'),
            CardField(self.ids.illustration.input, 'illustration'),
            CardField(self.ids.illustration_pan_y.input, 'illustration_pan_y', int),
            CardField(self.ids.illustration_pan_x.input, 'illustration_pan_x', int),
            CardField(self.ids.illustration_scale.input, 'illustration_scale', float),
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))


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
