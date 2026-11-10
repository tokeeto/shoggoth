from typing import NotRequired, TypedDict


class ExportedGroup(TypedDict):
    code: str
    name: str
    icon_url: NotRequired[str]


class _ExportedData(TypedDict):
    cards: list[dict[str, object]]
    packs: list[ExportedGroup]
    encounter_sets: list[ExportedGroup]


class ExportedProject(TypedDict):
    meta: dict[str, object]
    data: _ExportedData
