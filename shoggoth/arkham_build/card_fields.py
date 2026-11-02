import re
from collections.abc import Mapping
from html import unescape
from typing import TypedDict

from shoggoth.arkham_build.text import (
    ImageMapper,
    card_labels,
    map_text,
    resolve_text,
)
from shoggoth.card import Card, Face, base_class
from shoggoth.card_translations import load_card_translations

# Numeric fields and their per-investigator flags.
type NumericFields = dict[str, int | bool | None]


_NUMERICAL_MAP: dict[str, int | None] = {
    "<dash>": None,
    "---": None,
    "X": -2,
    "<star>": -3,
    "?": -4,
}


_PER_INVESTIGATOR_MAP = {
    "clues": ("clues_fixed", False),
    "doom": ("doom_per_investigator", True),
    "enemy_evade": ("enemy_evade_per_investigator", True),
    "enemy_fight": ("enemy_fight_per_investigator", True),
    "health": ("health_per_investigator", True),
    "shroud": ("shroud_per_investigator", True),
}


_SKILL_MAP = {
    "W": "skill_willpower",
    "I": "skill_intellect",
    "C": "skill_combat",
    "A": "skill_agility",
    "Q": "skill_wild",
}


_ENCOUNTER_ROLES = {
    "enemy",
    "enemy_location",
    "treachery",
    "location",
    "act",
    "agenda",
    "chaos",
    "scenario",
    "story",
}


_FACTIONS = (
    "guardian",
    "seeker",
    "rogue",
    "mystic",
    "survivor",
    "neutral",
    "mythos",
)


# Chaos tokens are named after Shoggoth's chaos_<token>.png overlays.
_CHAOS_TOKEN_ICONS = {
    "fail": "auto_fail",
    "blessing": "bless",
}


type _ChaosToken = str | int | None


class _ChaosEntry(TypedDict, total=False):
    """A row of a chaos or scenario reference card's token list."""

    token: _ChaosToken | list[_ChaosToken]
    text: str | None


# Weakness templates print their type label as the subtitle.
_WEAKNESS_LABELS = {"%:WEAKNESS", "%:BASIC WEAKNESS"}


_SLOT_MAP = {
    "hands": "Hand x2",
    "arcanes": "Arcane x2",
}


def compact[V](values: Mapping[str, V | None]) -> dict[str, V]:
    return {key: value for key, value in values.items() if value is not None}


def export_face_fields(
    face: Face, *, image_mapper: ImageMapper | None = None
) -> dict[str, object]:
    text = _text(face, image_mapper)
    keywords = _keywords(face, text)
    return {
        **keywords,
        **compact(
            {
                "name": _name(face, image_mapper),
                "subname": _subname(face, image_mapper),
                "subtype_code": _subtype(face),
                "traits": _optional_text(face, "traits", image_mapper),
                "text": text,
                "deck_limit": _deck_limit(face, keywords.get("exceptional", False)),
                "is_unique": _is_unique(face),
                "illustrator": _optional_text(face, "illustrator", image_mapper),
                "flavor": _optional_text(face, "flavor_text", image_mapper),
                "position": _parse_position(face.card.project_number) or 0,
                "quantity": face.card.amount,
                "encounter_code": face.card.get("encounter_set") or None,
                "encounter_position": _encounter_position(face),
                "bonded_to": face.card.get_meta("bonded") or None,
                "bonded_count": (
                    face.card.amount if face.card.get_meta("bonded") else None
                ),
                "stage": _stage(face),
                "slot": _slots(face),
                **_factions(face),
            }
        ),
        **_numeric_field(face, "cost"),
        **_xp(face),
        **_numeric_field(face, "health"),
        **_numeric_field(face, "attack", target="enemy_fight"),
        **_numeric_field(face, "evade", target="enemy_evade"),
        **_numeric_field(face, "damage", target="enemy_damage"),
        **_numeric_field(face, "horror", target="enemy_horror"),
        **_numeric_field(face, "clues"),
        **_numeric_field(face, "doom"),
        **_numeric_field(face, "shroud"),
        **_victory(face),
        **_numeric_field(face, "sanity"),
        **_skills(face),
    }


def _parse_position(value: int | str | None) -> int | None:
    match = re.match(r"\d+", str(value).strip())
    return int(match[0]) if match else None


def _encounter_position(face: Face) -> int | None:
    if not face.card.get("encounter_set"):
        return None
    return _parse_position(face.card.get("encounter_number"))


def _stage(face: Face) -> int | None:
    if not {"act", "agenda"}.intersection(face.card_types):
        return None
    return _parse_position(face.get("index", None))


def _factions(face: Face) -> dict[str, str]:
    classes = face.get("classes", [])
    # Encounter templates may default to a class that doesn't apply to the card.
    if "classes" not in face.data and _is_encounter_card(face.card):
        classes = []
    classes = [base_class(c) for c in classes]
    factions = list(dict.fromkeys(c for c in classes if c in _FACTIONS))
    factions = factions or [_default_faction(face)]
    return dict(zip(("faction_code", "faction2_code", "faction3_code"), factions))


def _subtype(face: Face) -> str | None:
    classes = face.get("classes", [])
    if "basic weakness" in classes:
        return "basicweakness"
    if "weakness" in classes:
        return "weakness"
    return None


def _default_faction(face: Face) -> str:
    return "mythos" if _is_encounter_card(face.card) else "neutral"


def _is_encounter_card(card: Card) -> bool:
    return bool(card.get("encounter_set")) and bool(
        _ENCOUNTER_ROLES.intersection(card.card_types)
        or card.back.card_type == "encounter"
    )


def _raw_name(face: Face) -> str:
    return face.get("name") or face.card.name


def _name(face: Face, image_mapper: ImageMapper | None) -> str:
    # Scenario templates underline the name, which is styling, not markup.
    name = re.sub(r"</?dbl>", "", _raw_name(face), flags=re.IGNORECASE)
    return map_text(face, "name", name, image_mapper=image_mapper).strip()


def _is_unique(face: Face) -> bool | None:
    name = resolve_text(face, "name", _raw_name(face))
    return "<unique>" in name.lower() or None


def _subname(face: Face, image_mapper: ImageMapper | None) -> str | None:
    if str(face.get("subtitle", None) or "").strip() in _WEAKNESS_LABELS:
        return None
    return _optional_text(face, "subtitle", image_mapper)


def _optional_text(
    face: Face, field: str, image_mapper: ImageMapper | None = None
) -> str | None:
    value = face.get(field, None)
    if value is None:
        return None
    return map_text(face, field, value, image_mapper=image_mapper).strip() or None


def _text(face: Face, image_mapper: ImageMapper | None) -> str | None:
    text = _optional_text(face, "text", image_mapper)
    if text is not None:
        return text

    entries = face.get("entries", [])
    lines = []
    if face.card_type == "investigator":
        for header, value in entries:
            if value is not None and str(value).strip():
                lines.append(f"{header or ''} {value}".strip())
    elif face.card_type in {"chaos", "scenario"}:
        difficulty = face.get("difficulty", None)
        if difficulty:
            lines.append(difficulty)

        lines.extend(_chaos_entry(entry) for entry in entries)
    else:
        return None

    text = "\n".join(line for line in lines if line)
    return map_text(face, "text", text, image_mapper=image_mapper).strip() or None


def _chaos_entry(entry: _ChaosEntry) -> str:
    tokens = entry.get("token", [])
    if not isinstance(tokens, list):
        tokens = [tokens]

    labels = []
    for token in tokens:
        if token is None or not str(token).strip():
            continue
        token = str(token).strip()
        token = _CHAOS_TOKEN_ICONS.get(token, token)
        labels.append(token if re.fullmatch(r"[+-]?\d+", token) else f"[{token}]")

    label = ", ".join(labels)
    text = entry.get("text") or ""
    return f"{label}: {text}".strip() if label else text.strip()


def _collapse_tags(text: str) -> str:
    return " ".join(re.sub(r"<[^>]*>", "", text).split())


def _keywords(face: Face, text: str | None) -> dict[str, bool]:
    if text is None:
        return {}
    text = re.sub(
        r"<(?:br|hr)\b[^>]*>|</(?:p|div|blockquote)>",
        "\n",
        text,
        flags=re.IGNORECASE,
    )
    text = unescape(re.sub(r"<[^>]*>", "", text))
    first_line = text.split("\n", 1)[0]
    return {
        keyword: True
        for keyword in ("permanent", "exceptional", "myriad")
        if any(
            f"{label}{stop}" in first_line
            for label in card_labels(face, f"CARD_KEYWORD_{keyword.upper()}")
            for stop in ".。"
        )
    }


def _deck_limit(face: Face, is_exceptional: bool) -> int | None:
    card = face.card
    if card.back.card_type == "encounter":
        return None
    if card.back.card_type != "player" and not {
        "asset",
        "event",
        "skill",
        "investigator",
    }.intersection(card.card_types):
        return None
    return 1 if is_exceptional else card.amount


def _slots(face: Face) -> str | None:
    slots = [slot.strip().lower() for slot in face.get("slots", []) if slot.strip()]
    return ". ".join(_SLOT_MAP.get(slot, slot.title()) for slot in slots) or None


def _skills(face: Face) -> NumericFields:
    is_investigator = face.card_type == "investigator"
    icon_counts: dict[str, int] = {}

    for icon in face.get("icons", ""):
        key = _SKILL_MAP.get(icon)
        if key and (not is_investigator or key == "skill_wild"):
            icon_counts[key] = icon_counts.get(key, 0) + 1

    skills: NumericFields = {**icon_counts}
    if is_investigator:
        for skill in ("willpower", "intellect", "combat", "agility"):
            skills.update(_numeric_field(face, skill, target=f"skill_{skill}"))

    return skills


def _victory(face: Face) -> NumericFields:
    values = _numeric_field(face, "victory")
    if values:
        return values

    text = _optional_text(face, "victory")
    if text is None:
        return {}

    text = _collapse_tags(text)
    parsed = _parse_numeric_value(text)
    if parsed is not None:
        return {"victory": parsed[0]}

    translations = load_card_translations(face.card.effective_language or "en")
    return compact(
        {
            field: _labeled_points(text, label, field, translations)
            for field, label in (("victory", "Victory"), ("vengeance", "Vengeance"))
        }
    )


def _labeled_points(
    text: str, label: str, field: str, translations: Mapping[str, str]
) -> int | None:
    """Parse e.g. "Victory 2." using the English or translated label."""
    templates = (
        f"{label} {{input}}",
        f"{translations.get(field.upper(), label)} {{input}}",
        translations.get(f"{field} format", ""),
    )
    for template in dict.fromkeys(templates):
        if "{input}" not in template:
            continue
        pattern = re.escape(_collapse_tags(template)).replace(r"\{input\}", r"(\d+)")
        match = re.search(rf"(?<!\w){pattern}(?!\d)", text, re.IGNORECASE)
        if match:
            return int(match[1])
    return None


def _xp(face: Face) -> NumericFields:
    if face.get("level") in {"None", "Custom"}:
        return {"xp": None}
    return _numeric_field(face, "level", target="xp")


def _numeric_field(face: Face, key: str, *, target: str | None = None) -> NumericFields:
    parsed = _parse_numeric_value(face.get(key))
    if parsed is None:
        return {}

    value, per_investigator = parsed
    field = target or key
    values: NumericFields = {field: value}

    flag, flag_when = _PER_INVESTIGATOR_MAP.get(field, (None, None))
    if flag and value is not None and per_investigator == flag_when:
        values[flag] = True

    return values


def _parse_numeric_value(raw_value: object) -> tuple[int | None, bool] | None:
    if raw_value is None:
        return None

    text = str(raw_value).strip()
    per_investigator = text.endswith("<per>")
    text = text.removesuffix("<per>").strip()

    if text in _NUMERICAL_MAP:
        return _NUMERICAL_MAP[text], per_investigator

    try:
        return int(text), per_investigator
    except ValueError:
        return None
