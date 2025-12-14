from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.properties import ObjectProperty
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from shoggoth.card import Card, TEMPLATES
import threading
from collections.abc import Callable
import shoggoth
from kivy.uix.image import CoreImage    # noqa: E402


class BoxContainer(GridLayout):
    pass


class NewCardPopup(Popup):
    """Popup for creating new card"""
    target = ObjectProperty(None, allownone=True)
    name: TextInput
    error: TextInput

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if card := shoggoth.app.current_card:
            if card.encounter:
                self.name.target = self.set_encounter_set(card.encounter)
                self.ids.template.text = 'treachery'

    def create(self):
        if self.name.text == '':
            self.error.text = 'You must choose a name'
            return

        template = TEMPLATES.get(self.ids.template.text)
        template['name'] = self.name.text
        project = shoggoth.app.current_project
        new_card = Card(data=template, expansion=project, encounter=self.target)

        project.add_card(new_card)
        shoggoth.app._refresh_tree()
        shoggoth.app.goto_card(new_card.id)
        self.dismiss()

    def set_template(self, value):
        self.ids.template.text = value

    def set_encounter_set(self, value):
        self.target = value
        self.ids.set_text.text = value.name if value else 'Player card'


class NewEncounterPopup(Popup):
    """Popup for creating new Encounter Set"""
    project = ObjectProperty()
    name: TextInput
    error: TextInput

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def create(self):
        if self.name.text:
            self.project.add_encounter_set(self.name.text)
            shoggoth.app.refresh_tree()
            self.dismiss()
        else:
            self.error.text = 'You must choose a name for the encounter set.'


class GuideEditor(BoxLayout):
    """ Widget for editing campaign guides """
    guide = ObjectProperty()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from pygments.lexers import html
        self.ids.code_input.lexer = html.HtmlLexer()
        self.load_html()
        self.ids.front_page_fields.ids.file_path.bind(text=self.set_front_page)

    def load_html(self):
        self.ids.code_input.text = self.guide.get_html()

    def get_page(self, page):
        img = self.guide.get_page(page, html=self.ids.code_input.text)
        texture = CoreImage(img, ext='jpeg').texture
        shoggoth.app.root.ids.card_preview.set_card_images(texture, None)

    def set_front_page(self, *args):
        self.guide.front_page = args[1]

    def export(self):
        self.guide.render_to_file()


class ProjectEditor(BoxLayout):
    """Widget for editing card data"""
    project = ObjectProperty()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        threading.Thread(target=self.show_thumbnails).start()

    def show_thumbnails(self):
        try:
            for index, card in enumerate(self.project.get_all_cards()):
                shoggoth.app.render_thumbnail(card, self.ids.thumbnail_grid)
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
        self.fields = []
        self._setup_fields()
        self.load_card(self.encounter)
        threading.Thread(target=self.show_thumbnails).start()

    def load_card(self, card_data):
        for field in self.fields:
            field.update_from_card(self.encounter)

    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            CardField(self.ids.name.input, 'name'),
            CardField(self.ids.icon.input, 'icon'),
            CardField(self.ids.order.input, 'order', int),
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))

    def _on_field_changed(self, field, text):
        field.update_card(self.encounter, text)

    def show_thumbnails(self):
        try:
            for index, card in enumerate(self.encounter.cards):
                threading.Thread(target=shoggoth.app.render_thumbnail, args=(card, self.ids.thumbnail_grid)).start()

        except Exception as e:
            print("failure in show_thumbnails", self.encounter, e)


class CardEditor(BoxLayout):
    """Widget for editing card data"""
    card = ObjectProperty()
    front_editor_container: BoxLayout
    back_editor_container: BoxLayout

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.front_editor = MAPPING.get(self.card.front.get('type'), BaseEditor)(face=self.card.front, type_change=self.update_card_face_type)
        self.back_editor = MAPPING.get(self.card.back.get('type'), BaseEditor)(face=self.card.back, type_change=self.update_card_face_type)
        self.front_editor_container.add_widget(self.front_editor)
        self.back_editor_container.add_widget(self.back_editor)

        # Works a bit like a face editor, despite being core data only
        self.fields = []
        self._setup_fields()
        self.load_card(self.card)

    def load_card(self, card_data):
        for field in self.fields:
            print('loading card data for', field)
            field.update_from_card(self.card)

    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            CardField(self.ids.name.input, 'name'),
            CardField(self.ids.copyright.input, 'copyright'),
            CardField(self.ids.amount.input, 'amount', int),
            CardField(self.ids.collection_number.input, 'expansion_number'),
            CardField(self.ids.encounter_number.input, 'encounter_number'),
            CardField(self.ids.collection.input, 'investigator'),
            CardField(self.ids.card_id.input, 'id'),
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))

    def _on_field_changed(self, field, text):
        field.update_card(self.card, text)

    def update_card_face_type(self, widget):
        if widget is self.front_editor:
            self.front_editor_container.remove_widget(self.front_editor)
            self.front_editor = MAPPING.get(self.card.front.get('type'), FaceEditor)(face=self.card.front, type_change=self.update_card_face_type)
            self.front_editor_container.add_widget(self.front_editor)
        elif widget is self.back_editor:
            self.back_editor_container.remove_widget(self.back_editor)
            self.back_editor = MAPPING.get(self.card.back.get('type'), FaceEditor)(face=self.card.back, type_change=self.update_card_face_type)
            self.back_editor_container.add_widget(self.back_editor)


class CardField:
    def __init__(self, widget, card_key, converter: Callable = str, deconverter: Callable = str):
        self.widget = widget
        self.card_key = card_key
        self.converter = converter
        self.deconverter = deconverter
        self._updating = False

    def update_from_card(self, card_data):
        self._updating = True
        value = None
        if self.card_key in card_data.data:
            value = card_data.data[self.card_key]
        if value == '<copy>':
            self.widget.text = value
        else:
            self.widget.text = self.deconverter(value) if value else ''
        self._updating = False

    def update_card(self, card_data, value):
        if self._updating:
            return False

        try:
            if value == '<copy>':
                card_data.set(self.card_key, value)
            else:
                card_data.set(self.card_key, self.converter(value) if value else None)
            return True
        except ValueError as e:
            print('tried updating the card, it failed with', e)
            return False


class WidgetLink():
    def __init__(self, parent):
        self.parent = parent

    def bind(self, *args, **kwargs):
        for widget in self.parent.widgets:
            widget.bind(*args, **kwargs)


class CardFieldComposite():
    def __init__(self, widgets, card_key, converter, deconverter, secondary_key="", secondary_converter=None):
        self.widgets = widgets
        self.widget = WidgetLink(self)
        self.card_key = card_key
        self.converter = converter
        self.deconverter = deconverter
        self.secondary_key = secondary_key
        self.secondary_converter = secondary_converter
        self._updating = False

    def update_from_card(self, card_data):
        self._updating = True
        value = None
        if self.card_key in card_data.data:
            value = card_data.data[self.card_key]
        for index, output in enumerate(self.deconverter(value)):
            self.widgets[index].text = str(output)
        self._updating = False

    def update_card(self, card_data, _):
        if self._updating:
            return False

        try:
            value = [w.text for w in self.widgets]
            card_data.set(self.card_key, self.converter(value) if value else None)
            if self.secondary_key and self.secondary_converter:
                card_data.set(self.secondary_key, self.secondary_converter(value) if value else None)
            return True
        except ValueError as e:
            print('tried updating the card, it failed with', e)
            return False


def list_converter(string) -> list:
    result = [n.strip() for n in string.split(',')]
    return result


def list_deconverter(value:list) -> str:
    result = ', '.join(value)
    return result


def chaos_entry_converter(value:list[str]) -> list:
    result = []
    # parse as pairs
    for token, text in zip(value[::2], value[1::2]):
        if "," in token:
            result.append({
                'token': [t.strip() for t in token.split(",")],
                'text': text,
            })
        else:
            result.append({'token': token.strip(), 'text': text})
    return result


def chaos_entry_deconverter(value:list[dict]) -> list[str]:
    result = []
    if not value:
        return result

    for entry in value:
        if isinstance(entry['token'], list):
            result.append(', '.join(entry['token']))
        else:
            result.append(entry['token'])
        result.append(entry['text'])
    return result

def customizable_converter(value:list[str]) -> list[list]:
    result = []
    # parse as triplets
    for boxes, name, text in zip(value[::3], value[1::3], value[2::3]):
        if boxes or name or text:
            result.append([
                int(boxes) if boxes else 0,
                name,
                text,
            ])
    return result

def customizable_deconverter(value:list[list]) -> list[str]:
    result = []
    if not value:
        return result

    for entry in value:
        result.append(entry[0])
        result.append(entry[1])
        result.append(entry[2])
    return result

def investigator_back_converter(value:list) -> list[str]:
    if not value:
        return []
    result = []
    # parse as pairs
    for heading, text in zip(value[::2], value[1::2]):
        if heading or text:
            result.append([heading,text])
    return result

def investigator_back_second_converter(value:list) -> str:
    if not value:
        return ""
    result = ""
    # parse as pairs
    for heading, text in zip(value[::2], value[1::2]):
        if heading or text:
            result += f'{heading} {text}\n'
    return result[0:-1]

def investigator_back_deconverter(value:list[list[str]]) -> list[str]:
    result = []
    if not value:
        return result
    for entry in value:
        result.append(entry[0])
        result.append(entry[1])
    return result


class FaceEditor(BoxContainer):
    def __init__(self, *args, face={}, type_change=None, **kwargs):
        self.face = face
        super().__init__(*args, **kwargs)
        self.fields = []
        self._setup_fields()
        self.load_card(self.face)
        self.type_change = type_change

        self.ids.type.input.bind(text=self.type_changed)

    def type_changed(self, widget, text):
        """ Replaces the editor with another """
        new_editor = MAPPING.get(text)
        if new_editor and self.type_change and type(self) is not new_editor:
            try:
                self.type_change(self)
            except:  # noqa: E722
                pass # sometimes the events happen twice

    def _setup_fields(self):
        # Register all your fields
        self.fields = [
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))

    def load_card(self, card_data):
        for field in self.fields:
            field.update_from_card(self.face)

    def _on_field_changed(self, field, text):
        field.update_card(self.face, text)


def base_fields(editor):
    return [
        CardField(editor.ids.type.input, 'type'),
        CardField(editor.ids.name.input, 'name'),
        CardField(editor.ids.subtitle.input, 'subtitle'),
        CardField(editor.ids.traits.input, 'traits'),
    ]


def illustration_fields(editor):
    return [
        CardField(editor.ids.illustration.ids.path.input, 'illustration'),
        CardField(editor.ids.illustration.ids.pan_y.input, 'illustration_pan_y', int),
        CardField(editor.ids.illustration.ids.pan_x.input, 'illustration_pan_x', int),
        CardField(editor.ids.illustration.ids.scale.input, 'illustration_scale', float),
        CardField(editor.ids.illustration.ids.artist.input, 'illustrator'),
    ]


def player_card_fields(editor):
    return [
        CardField(editor.ids.classes.input, 'classes', list_converter, list_deconverter),
        CardField(editor.ids.level.input, 'level'),
        CardField(editor.ids.icons.input, 'icons'),
    ]

class BaseEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            CardField(self.ids.type.input, 'type'),
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))




class AssetEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            *base_fields(self),
            *player_card_fields(self),
            CardField(self.ids.cost.input, 'cost'),
            CardField(self.ids.health.input, 'health'),
            CardField(self.ids.sanity.input, 'sanity'),
            CardField(self.ids.slots.input, 'slots', list_converter, list_deconverter),
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
            CardField(self.ids.cost.input, 'cost'),
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
            CardField(self.ids.classes.input, 'classes', list_converter, list_deconverter),
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
            CardField(self.ids.subtitle.input, 'subtitle'),
            CardField(self.ids.classes.input, 'classes', list_converter, list_deconverter),
            CardFieldComposite(
                [
                    self.ids.heading1.input, self.ids.text1.input,
                    self.ids.heading2.input, self.ids.text2.input,
                    self.ids.heading3.input, self.ids.text3.input,
                    self.ids.heading4.input, self.ids.text4.input,
                    self.ids.heading5.input, self.ids.text5.input,
                ], 'entries',
                investigator_back_converter,
                investigator_back_deconverter,
                secondary_key='text',
                secondary_converter=investigator_back_second_converter,
            ),
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
            CardField(self.ids.victory.input, 'victory'),
            CardField(self.ids.connection.input, 'connection'),
            CardField(self.ids.connections.input, 'connections', list_converter, list_deconverter),
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
            CardField(self.ids.connections.input, 'connections', list_converter, list_deconverter),
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
            CardField(self.ids.classes.input, 'classes', list_converter, list_deconverter),
            CardField(self.ids.victory.input, 'victory'),
            *illustration_fields(self),
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
            CardField(self.ids.classes.input, 'classes', list_converter, list_deconverter),

            CardField(self.ids.attack.input, 'attack'),
            CardField(self.ids.health.input, 'health'),
            CardField(self.ids.evade.input, 'evade'),

            CardField(self.ids.damage.input, 'damage'),
            CardField(self.ids.horror.input, 'horror'),

            CardField(self.ids.victory.input, 'victory'),
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


class ChaosEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            CardField(self.ids.type.input, 'type'),
            CardField(self.ids.name.input, 'name'),
            CardField(self.ids.difficulty.input, 'difficulty'),
            CardFieldComposite(
                [
                    self.ids.token1.input, self.ids.text1.input,
                    self.ids.token2.input, self.ids.text2.input,
                    self.ids.token3.input, self.ids.text3.input,
                    self.ids.token4.input, self.ids.text4.input,
                    self.ids.token5.input, self.ids.text5.input,
                ],  'entries', chaos_entry_converter, chaos_entry_deconverter
            ),
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))

class CustomizableEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            CardField(self.ids.type.input, 'type'),
            CardField(self.ids.name.input, 'name'),
            CardField(self.ids.text.input, 'text'),
            CardFieldComposite(
                [
                    self.ids.boxes1.input, self.ids.name1.input, self.ids.text1.input,
                    self.ids.boxes2.input, self.ids.name2.input, self.ids.text2.input,
                    self.ids.boxes3.input, self.ids.name3.input, self.ids.text3.input,
                    self.ids.boxes4.input, self.ids.name4.input, self.ids.text4.input,
                    self.ids.boxes5.input, self.ids.name5.input, self.ids.text5.input,
                    self.ids.boxes6.input, self.ids.name6.input, self.ids.text6.input,
                    self.ids.boxes7.input, self.ids.name7.input, self.ids.text7.input,
                    self.ids.boxes8.input, self.ids.name8.input, self.ids.text8.input,
                    self.ids.boxes9.input, self.ids.name9.input, self.ids.text9.input,
                    self.ids.boxes10.input, self.ids.name10.input, self.ids.text10.input,
                ],  'entries', customizable_converter, customizable_deconverter
            ),
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))

class StoryEditor(FaceEditor):
    def _setup_fields(self):
        # Register all your fields
        self.fields = [
            CardField(self.ids.type.input, 'type'),
            CardField(self.ids.name.input, 'name'),
            CardField(self.ids.text.input, 'text'),
            CardField(self.ids.classes.input, 'classes', list_converter, list_deconverter),
        ]

        # Bind each field
        for field in self.fields:
            field.widget.bind(text=lambda instance, value, f=field: self._on_field_changed(f, value))


# maps face types to editors
MAPPING = {
    'player': BaseEditor,
    'asset': AssetEditor,
    'event': EventEditor,
    'skill': SkillEditor,

    'investigator': InvestigatorEditor,
    'investigator_back': InvestigatorBackEditor,

    'encounter': BaseEditor,
    'location': LocationEditor,
    'location_back': LocationBackEditor,
    'treachery': TreacheryEditor,
    'enemy': EnemyEditor,
    'act': ActEditor,
    'act_back': ActBackEditor,
    'agenda': AgendaEditor,
    'agenda_back': AgendaBackEditor,
    'chaos': ChaosEditor,
    'customizable': CustomizableEditor,
    'story': StoryEditor,
}
