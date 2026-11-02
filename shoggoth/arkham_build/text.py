import re
from collections.abc import Callable

from shoggoth.card import Card, Face
from shoggoth.card_translations import CARD_KEYWORD_DEFAULTS, load_card_translations
from shoggoth.i18n import load_catalog

# Maps an <image> tag to HTML.
type ImageMapper = Callable[[str], str | None]

# The card, face data, field, and raw value of a text reference being resolved.
type _ReferenceKey = tuple[str, int, str, str]


_VALUE_MAP: dict[str, Callable[[Face], int | str | None]] = {
    "<exn>": lambda face: face.card.project_number,
    "<esn>": lambda face: face.card.encounter_number,
    "<est>": lambda face: getattr(face.card.encounter, "total_cards", None),
    "<copyright>": lambda face: face.card.get("copyright"),
}
_VALUE_PATTERN = re.compile(
    r"<name>|<copy>|<:(?P<element_id>[^ >]*) (?P<field>[^>]+)>|"
    + "|".join(re.escape(tag) for tag in _VALUE_MAP),
    re.IGNORECASE,
)

_ICON_TAG_PATTERN = re.compile(
    r"""<(exi|esi|project\.icon|encounter\.icon)(?=\s|>)((?:[^<>"']|"[^"]*"|'[^']*')*)>""",
    re.IGNORECASE,
)

_ICON_SPAN_PATTERN = r"<icon>[\s\S]*?</icon>"

_TAG_PATTERN = re.compile(
    _ICON_SPAN_PATTERN + r"""|<(?:[^<>"']|"[^"]*"|'[^']*')*>""", re.IGNORECASE
)
_TAG_REMOVALS = re.compile(
    "|".join(
        (
            _ICON_SPAN_PATTERN,
            "<icon>",
            "</icon>",
            "<unique>",
            "<center>",
            "</center>",
            "<left>",
            "</left>",
            "<right>",
            "</right>",
            r"<size\s+\d+>",
            "</size>",
            r'<font\s+"[^"\n]+">',
            "</font>",
            r"<indent\s+\d+>",
            "</indent>",
            r"<margin\s+\d+(?:\s+\d+)*>",
            r"<spacing\s+(?:\d+(?:\.\d*)?|\.\d+)>",
            "<valign>",
            r"<align\s+(?:top|center|bottom)>",
            r"<image(?:\s+[^>]*)?>",
            "<resource>",
            "<clues>",
            "<doom>",
            "<entry>",
            "<open>",
        )
    ),
    re.IGNORECASE,
)
_TAG_MAP = {
    "<bi>": "<b><i>",
    "</bi>": "</i></b>",
    "<t>": "[[",
    "</t>": "]]",
    "<dbl>": "<u>",
    "</dbl>": "</u>",
    "<quote>": "'",
    "<quoteend>": "'",
    "<dquote>": '"',
    "<dquoteend>": '"',
    "<action>": "[action]",
    "<act>": "[action]",
    "<free>": "[fast]",
    "<reaction>": "[reaction]",
    "<willpower>": "[willpower]",
    "<wil>": "[willpower]",
    "<intellect>": "[intellect]",
    "<int>": "[intellect]",
    "<combat>": "[combat]",
    "<com>": "[combat]",
    "<agility>": "[agility]",
    "<agi>": "[agility]",
    "<wild>": "[wild]",
    "<skull>": "[skull]",
    "<cultist>": "[cultist]",
    "<tablet>": "[tablet]",
    "<elder_thing>": "[elder_thing]",
    "<elder_sign>": "[elder_sign]",
    "<auto_fail>": "[auto_fail]",
    "<blessing>": "[bless]",
    "<curse>": "[curse]",
    "<frost>": "[frost]",
    "<guardian>": "[guardian]",
    "<seeker>": "[seeker]",
    "<rogue>": "[rogue]",
    "<mystic>": "[mystic]",
    "<survivor>": "[survivor]",
    "<per>": "[per_investigator]",
    "<investigator>": "[per_investigator]",
    "<per_large>": "[per_investigator]",
    "<damage>": "[health]",
    "<horror>": "[sanity]",
    "<bullet>": "[bullet]",
    "<resolution>": "→",
    "<codex>": "[codex]",
    "<day>": "[day]",
    "<night>": "[night]",
    "<blood>": "[blood]",
    "<fleur>": "\u269c\ufe0e",
    "<star>": "[star]",
    "<dash>": "-",
    "<sign_1>": "[seal_a]",
    "<sign_2>": "[seal_b]",
    "<sign_3>": "[seal_c]",
    "<sign_4>": "[seal_d]",
    "<sign_5>": "[seal_e]",
}

# Printed keywords read "<b>Forced –</b>", arkham.build uses "<b>Forced</b> -".
_KEYWORD_LABEL_PATTERN = re.compile(r"<b>\s*(.*?)\s*[–—-]\s*</b>\s*", re.IGNORECASE)

_TEXT_MAP = {
    "---": "—",
    "--": "–",
    r"\"": '"',
    r"\'": "'",
}
_TEXT_PATTERN = re.compile(
    _TAG_PATTERN.pattern
    + "|"
    + "|".join(re.escape(text) for text in sorted(_TEXT_MAP, key=len, reverse=True)),
    re.IGNORECASE,
)


def _icon_image(face: Face, match: re.Match[str]) -> str:
    kind = match[1].lower()
    project = face.card.project

    if kind in {"exi", "project.icon"}:
        source = project.icon
    else:
        encounter = face.card.encounter
        source = encounter.icon if encounter else None

    if not source:
        return ""

    source = project.find_file(source) or source
    attributes = ' color="inverted"' if kind in {"exi", "esi"} else match[2]
    return f'<image src="{source}"{attributes}>'


def map_text(
    face: Face, field: str, value: str, *, image_mapper: ImageMapper | None = None
) -> str:
    mapper = _TextMapper(image_mapper)
    resolved_text = mapper.resolve_values(face, field, value)
    return _replace_plain_text(mapper.map_tags(face, resolved_text))


def resolve_text(face: Face, field: str, value: str) -> str:
    return _TextMapper(None).resolve_values(face, field, value)


def _replace_plain_text(value: str) -> str:
    return _TEXT_PATTERN.sub(
        lambda match: _TEXT_MAP.get(match.group(0), match.group(0)), value
    )


class _TextMapper:
    def __init__(self, image_mapper: ImageMapper | None) -> None:
        self._image_mapper = image_mapper

    def resolve_values(
        self,
        face: Face,
        field: str,
        value: str,
        reference_path: frozenset[_ReferenceKey] = frozenset(),
    ) -> str:
        reference_key: _ReferenceKey = (face.card.id, id(face.data), field, value)

        if reference_key in reference_path:
            raise ValueError(
                f"Circular text reference on card {face.card.id}, field {field}"
            )

        reference_path = reference_path | {reference_key}

        resolved_text = _VALUE_PATTERN.sub(
            lambda match: self._resolve_value(face, field, match, reference_path), value
        )

        return self._translate_asset_keys(face, resolved_text)

    def _resolve_value(
        self,
        face: Face,
        field: str,
        match: re.Match[str],
        reference_path: frozenset[_ReferenceKey],
    ) -> str:
        tag = match.group(0).lower()

        if tag in _VALUE_MAP:
            resolved_value = _VALUE_MAP[tag](face)
            return "" if resolved_value is None else str(resolved_value)

        if tag == "<name>":
            return self.resolve_values(face, "name", face.card.name, reference_path)

        if tag == "<copy>":
            other_face = face.other_side
            default = other_face.card.name if field == "name" else ""
            copied_value = other_face.get(field) or default
            return self.resolve_values(other_face, field, copied_value, reference_path)

        return self._resolve_reference(face, match, reference_path)

    def _resolve_reference(
        self,
        face: Face,
        match: re.Match[str],
        reference_path: frozenset[_ReferenceKey],
    ) -> str:
        element_id = match.group("element_id") or face.card.id

        element = face.card.project.get_by_id(element_id)
        if element is None:
            raise ValueError(f"Unknown text reference: {match.group(0)}")

        referenced_value: object = element.data

        field_path = match.group("field").strip().split(".")
        for part in field_path:
            if not isinstance(referenced_value, dict) or part not in referenced_value:
                raise ValueError(f"Unknown text reference: {match.group(0)}")
            referenced_value = referenced_value[part]

        if not isinstance(referenced_value, (str, int, float)):
            raise ValueError(f"Invalid text reference: {match.group(0)}")

        referenced_face = face
        if isinstance(element, Card):
            referenced_face = element.back if field_path[0] == "back" else element.front

        return self.resolve_values(
            referenced_face, field_path[-1], str(referenced_value), reference_path
        )

    def map_tags(
        self, face: Face, value: str, keyword_path: frozenset[str] = frozenset()
    ) -> str:
        return _TAG_PATTERN.sub(
            lambda match: self._map_tag(face, match.group(0), keyword_path), value
        )

    def _map_tag(self, face: Face, tag: str, keyword_path: frozenset[str]) -> str:
        key = tag.lower()

        icon = _ICON_TAG_PATTERN.fullmatch(tag)
        if icon is not None:
            return self.map_tags(face, _icon_image(face, icon), keyword_path)

        if self._image_mapper is not None:
            image = self._image_mapper(tag)
            if image is not None:
                return image

        if _TAG_REMOVALS.fullmatch(tag):
            return ""

        if key in CARD_KEYWORD_DEFAULTS:
            return self._expand_keyword(face, key, keyword_path)

        return _TAG_MAP.get(key, tag)

    def _expand_keyword(
        self, face: Face, key: str, keyword_path: frozenset[str]
    ) -> str:
        if key in keyword_path:
            raise ValueError(f"Circular keyword translation: {key}")

        catalog = load_card_translations(face.card.effective_language or "en")
        translated_text = catalog.get(key, CARD_KEYWORD_DEFAULTS[key])
        label = _KEYWORD_LABEL_PATTERN.fullmatch(translated_text)
        if label is not None:
            translated_text = f"<b>{label[1]}</b> -"

        return self.map_tags(face, translated_text, keyword_path | {key})

    def _translate_asset_keys(self, face: Face, value: str) -> str:
        if "%:" not in value:
            return value

        language = face.card.effective_language or "en"
        catalog = load_card_translations("en") | load_card_translations(language)

        keys = sorted((key for key in catalog if key), key=len, reverse=True)
        if not keys:
            return value

        pattern = re.compile(
            r"%:(?:" + "|".join(re.escape(key) for key in keys) + r")(?!\w)"
        )
        return pattern.sub(lambda match: catalog[match.group(0)[2:]], value)


def card_labels(face: Face, key: str) -> set[str]:
    language = face.card.effective_language or "en"
    values = (load_catalog("en").get(key, ""), load_catalog(language).get(key, ""))
    return {label for value in values for label in value.split("|") if label}
