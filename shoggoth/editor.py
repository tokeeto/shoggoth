from argparse import Action
from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ObjectProperty, StringProperty, DictProperty
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from shoggoth.card import Card
import threading


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
        threading.Thread(target=self.show_thumbnails).start()

    def show_thumbnails(self):
        try:
            app = App.get_running_app()
            for index, card in enumerate(self.project.get_all_cards()):
                app.render_thumbnail(card, self.ids.thumbnail_grid)
        except Exception as e:
           print("failure in on_project", self.project, e)

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
        threading.Thread(target=self.show_thumbnails).start()

    def show_thumbnails(self):
        try:
            app = App.get_running_app()
            for index, card in enumerate(self.encounter.cards):
                app.render_thumbnail(card, self.ids.thumbnail_grid)
        except Exception as e:
           print("failure in on_project", self.project, e)

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
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))

    def load_card(self, card_data):
        for field in self.fields:
            field.update_from_card(self.face)

    def _on_field_changed(self, field, value):
        field.update_card(self.face, value)


def base_fields(editor):
    return [
        CardField(editor.ids.type.input, 'type'),
        CardField(editor.ids.name.input, 'name'),
        CardField(editor.ids.subtitle.input, 'subtitle'),
        CardField(editor.ids.traits.input, 'traits'),
    ]


def illustration_fields(editor):
    return [
        CardField(editor.ids.illustration.input, 'illustration'),
        CardField(editor.ids.illustration_pan_y.input, 'illustration_pan_y', int),
        CardField(editor.ids.illustration_pan_x.input, 'illustration_pan_x', int),
        CardField(editor.ids.illustration_scale.input, 'illustration_scale', float),
    ]

def player_card_fields(editor):
    return [
        CardField(editor.ids.card_class.input, 'class'),
        CardField(editor.ids.classes.input, 'classes', list),
        CardField(editor.ids.cost.input, 'cost'),
        CardField(editor.ids.level.input, 'level'),
    ]

class AssetEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            *base_fields(self),
            *player_card_fields(self),
            CardField(self.ids.stamina.input, 'stamina'),
            CardField(self.ids.sanity.input, 'sanity'),
            CardField(self.ids.text.input, 'text'),
            CardField(self.ids.flavor_text.input, 'flavor_text'),
            *illustration_fields(self),
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))


class EventEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            *base_fields(self),
            *player_card_fields(self),
            CardField(self.ids.text.input, 'text'),
            CardField(self.ids.flavor_text.input, 'flavor_text'),
            *illustration_fields(self),
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))


class SkillEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            *base_fields(self),
            *player_card_fields(self),
            CardField(self.ids.text.input, 'text'),
            CardField(self.ids.flavor_text.input, 'flavor_text'),
            *illustration_fields(self),
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))


class InvestigatorEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            *base_fields(self),
            CardField(self.ids.card_class.input, 'class'),
            CardField(self.ids.classes.input, 'classes', list),
            CardField(self.ids.text.input, 'text'),
            CardField(self.ids.flavor_text.input, 'flavor_text'),

            CardField(self.ids.agility.input, 'agility'),
            CardField(self.ids.combat.input, 'combat'),
            CardField(self.ids.willpower.input, 'willpower'),
            CardField(self.ids.intellect.input, 'intellect'),

            CardField(self.ids.health.input, 'health'),
            CardField(self.ids.sanity.input, 'sanity'),
            *illustration_fields(self),
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))


class InvestigatorBackEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            *base_fields(self),
            CardField(self.ids.card_class.input, 'class'),
            CardField(self.ids.classes.input, 'classes', list),
            CardField(self.ids.text.input, 'text'),
            CardField(self.ids.flavor_text.input, 'flavor_text'),

            *illustration_fields(self),
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))


class LocationEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            *base_fields(self),
            CardField(self.ids.text.input, 'text'),
            CardField(self.ids.flavor_text.input, 'flavor_text'),
            CardField(self.ids.shroud.input, 'shroud'),
            CardField(self.ids.clues.input, 'clues'),
            CardField(self.ids.connection.input, 'connection'),
            CardField(self.ids.connections.input, 'connections', list),
            *illustration_fields(self)
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))

class LocationBackEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            *base_fields(self),
            CardField(self.ids.text.input, 'text'),
            CardField(self.ids.flavor_text.input, 'flavor_text'),
            CardField(self.ids.connection.input, 'connection'),
            CardField(self.ids.connections.input, 'connections', list),
            *illustration_fields(self)
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))


class TreacheryEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            *base_fields(self),
            CardField(self.ids.text.input, 'text'),
            CardField(self.ids.flavor_text.input, 'flavor_text'),
            *illustration_fields(self)
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))


class EnemyEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            *base_fields(self),
            CardField(self.ids.text.input, 'text'),
            CardField(self.ids.flavor_text.input, 'flavor_text'),

            CardField(self.ids.attack.input, 'attack'),
            CardField(self.ids.health.input, 'health'),
            CardField(self.ids.evade.input, 'evade'),

            CardField(self.ids.damage.input, 'damage'),
            CardField(self.ids.horror.input, 'horror'),

            *illustration_fields(self)
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))

class ActEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            CardField(self.ids.type.input, 'type'),
            CardField(self.ids.name.input, 'name'),
            CardField(self.ids.index.input, 'index'),
            CardField(self.ids.text.input, 'text'),
            CardField(self.ids.flavor_text.input, 'flavor_text'),
            CardField(self.ids.clues.input, 'clues'),
            *illustration_fields(self)
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))

class ActBackEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            CardField(self.ids.type.input, 'type'),
            CardField(self.ids.name.input, 'name'),
            CardField(self.ids.index.input, 'index'),
            CardField(self.ids.text.input, 'text'),
            CardField(self.ids.flavor_text.input, 'flavor_text'),
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))


class AgendaEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            CardField(self.ids.type.input, 'type'),
            CardField(self.ids.name.input, 'name'),
            CardField(self.ids.index.input, 'index'),
            CardField(self.ids.text.input, 'text'),
            CardField(self.ids.flavor_text.input, 'flavor_text'),
            CardField(self.ids.doom.input, 'doom'),
            *illustration_fields(self)
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))

class AgendaBackEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            CardField(self.ids.type.input, 'type'),
            CardField(self.ids.name.input, 'name'),
            CardField(self.ids.index.input, 'index'),
            CardField(self.ids.text.input, 'text'),
            CardField(self.ids.flavor_text.input, 'flavor_text'),
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))


# maps face types to editors
MAPPING = {
    'asset': AssetEditor,
    'event': EventEditor,
    'skill': SkillEditor,
    'investigator': InvestigatorEditor,
    'investigator_back': InvestigatorBackEditor,
    'location': LocationEditor,
    'location_back': LocationBackEditor,
    'treachery': TreacheryEditor,
    'weakness_treachery': TreacheryEditor,
    'enemy': EnemyEditor,
    'act': ActEditor,
    'act_back': ActBackEditor,
    'agenda': AgendaEditor,
    'agenda_back': AgendaBackEditor,
}
