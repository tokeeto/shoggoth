import json
import os
import shutil
from contextlib import contextmanager
from pathlib import Path

import pytest
from PIL import Image

from shoggoth import arkham_build
from shoggoth.arkham_build import text
from shoggoth.project import Project

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SNAPSHOT_DIR = Path(__file__).parent / "snapshots"
UPDATE_SNAPSHOTS = os.environ.get("UPDATE_SNAPSHOTS") == "1"


class _StubRenderer:
    """Render every face as a blank card, so exports with images stay fast."""

    locale = "en"

    @contextmanager
    def render_card_side(self, card, side, include_bleed=True):
        horizontal = side.get("orientation", "vertical") == "horizontal"
        yield Image.new("RGB", (2100, 1500) if horizontal else (1500, 2100))


def _normalize(data):
    """Replace values that change between runs."""
    data["meta"]["date_updated"] = "<date_updated>"
    data["meta"]["generator"] = "<generator>"
    return data


@pytest.fixture
def export(tmp_path):
    """Export a project dict to arkham.build JSON."""

    def run(project_data, settings=None):
        project = Project(str(tmp_path / "project.json"), project_data)
        data = arkham_build.export_project(
            project,
            settings or {},
            _StubRenderer(),
            card_executor=lambda cards, export_card: [
                export_card(card) for card in cards
            ],
        )
        return _normalize(data)

    return run


@pytest.fixture
def snapshot(request):
    """Compare data to the test's JSON snapshot; UPDATE_SNAPSHOTS=1 rewrites it."""
    path = SNAPSHOT_DIR / f"{request.node.name}.json"

    def check(data):
        actual = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        if UPDATE_SNAPSHOTS:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(actual, encoding="utf-8")
            return

        assert path.exists(), (
            f"Missing snapshot {path.name}, run with UPDATE_SNAPSHOTS=1"
        )
        assert actual == path.read_text(encoding="utf-8")

    return check


def _project(**overrides):
    return {
        "id": "TST",
        "name": "Snapshot Test",
        "icon": "",
        "encounter_sets": [
            {"id": "enc-cult", "name": "Cult of Testing", "icon": "", "cards": []},
            {"id": "enc-rats", "name": "Swarm of Rats", "icon": "", "cards": []},
        ],
        "cards": [],
        **overrides,
    }


def test_project_meta_and_groups(export, snapshot):
    project = _project(
        meta={
            "author": "Test Author",
            "banner_url": "https://example.com/banner.png",
            "banner_credit": "Test Artist",
            "description": "A project used by the snapshot tests.",
            "website_url": "https://example.com/snapshot-test",
            # Not a known status, exported as "draft".
            "status": "playtesting",
            "tags": ["campaign", "fan-made"],
            # Unknown content types are dropped.
            "types": ["campaign", "player_cards", "expansion"],
        },
    )

    snapshot(export(project))


def test_player_asset(export, snapshot):
    card = {
        "id": "asset-01",
        "name": "Codex of Testing",
        "amount": 2,
        "project_number": "12",
        "front": {
            "type": "asset",
            "name": "<unique><name>",
            "subtitle": "Proof of Concept",
            "classes": ["seeker", "mystic"],
            "level": "2",
            "cost": "3",
            "icons": "WWI",
            "traits": "Item. Tome.",
            "slots": ["hand", "arcane"],
            "text": "<action>: Investigate.",
            "flavor_text": "Every page is a test.",
            "illustrator": "Test Illustrator",
        },
        "back": {"type": "player"},
    }

    snapshot(export(_project(cards=[card]))["data"]["cards"])


def test_enemy_special_values(export, snapshot):
    card = {
        "id": "enemy-01",
        "name": "Test Acolyte",
        "amount": 2,
        "project_number": "20",
        "encounter_set": "enc-cult",
        "encounter_number": "4",
        "front": {
            "type": "enemy",
            "traits": "Humanoid. Cultist.",
            "attack": "X",
            "evade": "<dash>",
            "health": "3<per>",
            "damage": "1",
            "horror": "0",
            "victory": "Victory 1.",
            "text": "X is the number of cultists in play.",
        },
        "back": {"type": "encounter"},
    }

    snapshot(export(_project(cards=[card]))["data"]["cards"])


def test_text_conversion(export, snapshot):
    card = {
        "id": "event-01",
        "name": "Stand Firm",
        "amount": 2,
        "project_number": "30",
        "front": {
            "type": "event",
            "classes": ["guardian"],
            "cost": "1",
            "level": "0",
            "icons": "W",
            "traits": "Spirit.",
            "text": (
                "Exceptional.\n"
                "<free> When a <t>Cultist</t> enemy attacks you, play <name>: "
                "Cancel that attack---it gets -1 <willpower>.\n"
                "<for> After this card is played: "
                "<center><dquote>Not today.<dquoteend></center>"
            ),
        },
        "back": {"type": "player"},
    }

    snapshot(export(_project(cards=[card]))["data"]["cards"])


@pytest.mark.assets
def test_investigator_deckbuilding(export, snapshot):
    investigator = {
        "id": "inv-01",
        "name": "Tess Tester",
        "amount": 1,
        "project_number": "1",
        "front": {
            "type": "investigator",
            "name": "<unique><name>",
            "subtitle": "The Examiner",
            "classes": ["guardian"],
            "traits": "Agency. Detective.",
            "willpower": "3",
            "intellect": "4",
            "combat": "2",
            "agility": "1",
            "health": "7",
            "sanity": "8",
            "text": "<reaction> After you pass a test: Draw 1 card.",
        },
        "back": {
            "type": "investigator_back",
            "entries": [
                ["<b>Deck Size:</b>", "30."],
                [
                    "<b>Deckbuilding Options:</b>",
                    "Guardian cards (<guardian>) level 0-5.",
                ],
                ["<b>Deckbuilding Restrictions:</b>", ""],
            ],
            "flavor_text": "She never skips a step.",
        },
    }
    signature = {
        "id": "sig-01",
        "name": "Tess's Checklist",
        "amount": 1,
        "project_number": "2",
        "investigator": "Tess Tester",
        "front": {
            "type": "asset",
            "classes": ["neutral"],
            "cost": "1",
            "level": "None",
            "text": "Tess Tester deck only.",
        },
        "back": {"type": "player"},
    }
    # Restricted to the investigator, but not a deck requirement.
    bonded = {
        "id": "bond-01",
        "name": "Margin Note",
        "amount": 3,
        "project_number": "3",
        "investigator": "Tess Tester",
        "meta": {"bonded": "sig-01"},
        "front": {
            "type": "event",
            "classes": ["neutral"],
            "cost": "0",
            "level": "None",
            "text": "Bonded (Tess's Checklist).",
        },
        "back": {"type": "player"},
    }
    weakness = {
        "id": "weak-01",
        "name": "Missed Deadline",
        "amount": 1,
        "project_number": "4",
        "investigator": "Tess Tester",
        "front": {
            "type": "treachery",
            "classes": ["weakness"],
            "traits": "Flaw.",
            "text": "<rev> Lose 2 actions.",
        },
        "back": {"type": "player"},
    }
    # Not linked to an investigator, so it has no restriction.
    basic_weakness = {
        "id": "basic-weak-01",
        "name": "Paperwork",
        "amount": 1,
        "project_number": "5",
        "front": {
            "type": "treachery",
            "classes": ["basic weakness"],
            "traits": "Task.",
            "text": "<rev> Discard 1 card from your hand.",
        },
        "back": {"type": "player"},
    }
    project = _project(
        cards=[investigator, signature, bonded, weakness, basic_weakness]
    )

    snapshot(export(project)["data"]["cards"])


def test_linked_back(export, snapshot):
    card = {
        "id": "story-01",
        "name": "The Rat King Awakens",
        "amount": 1,
        "project_number": "40",
        "encounter_set": "enc-rats",
        "encounter_number": "1",
        "front": {
            "type": "story",
            "text": "Flip this card over. The Rat King enters play.",
            "flavor_text": "Something stirs beneath the floorboards.",
        },
        "back": {
            "type": "enemy",
            "name": "The Rat King",
            "traits": "Creature. Elite.",
            "attack": "3",
            "evade": "2",
            "health": "4",
            "damage": "1",
            "horror": "1",
            "text": "Hunter.",
        },
    }

    snapshot(export(_project(cards=[card]))["data"]["cards"])


def test_act_and_agenda(export, snapshot):
    act = {
        "id": "act-01",
        "name": "Into the Sewers",
        "amount": 1,
        "project_number": "50",
        "encounter_set": "enc-rats",
        "encounter_number": "2",
        "front": {
            "type": "act",
            "index": "1a",
            "clues": "2",
            "text": "Objective - If each investigator is in the Sewers, advance.",
        },
        "back": {
            "type": "act_back",
            "name": "The Nest",
            "index": "1b",
            "text": "Put the Rat King into play.",
            "flavor_text": "The squeaking grows louder.",
        },
    }
    agenda = {
        "id": "agenda-01",
        "name": "The Swarm Gathers",
        "amount": 1,
        "project_number": "51",
        "encounter_set": "enc-rats",
        "encounter_number": "3",
        "front": {
            "type": "agenda",
            "index": "1a",
            "doom": "4<per>",
            "text": "<for> At the end of the round, place 1 doom here.",
        },
        "back": {
            "type": "agenda_back",
            "index": "1b",
            "text": "The rats overwhelm you.",
        },
    }

    snapshot(export(_project(cards=[act, agenda]))["data"]["cards"])


def test_scenario_reference(export, snapshot):
    card = {
        "id": "scenario-01",
        "name": "Rats in the Walls",
        "amount": 1,
        "project_number": "60",
        "encounter_set": "enc-rats",
        "encounter_number": "5",
        "front": {
            "type": "chaos",
            "difficulty": "Easy / Standard",
            "entries": [
                {"token": ["skull"], "text": "--1. If you fail, take 1 horror."},
                {"token": ["cultist", "tablet"], "text": "--2."},
            ],
        },
        "back": {
            "type": "chaos",
            "difficulty": "Hard / Expert",
            "entries": [
                {
                    "token": ["skull"],
                    "text": "--3. If you fail, take 1 horror and 1 damage.",
                },
                {"token": "elder_thing", "text": "Reveal another token."},
            ],
        },
    }

    snapshot(export(_project(cards=[card]))["data"]["cards"])


def test_skipped_cards(export, snapshot):
    player_back = {
        "id": "back-01",
        "name": "Player Card Back",
        "amount": 1,
        "front": {"type": "player"},
        "back": {"type": "player"},
    }
    unsupported = {
        "id": "scan-01",
        "name": "Scanning Sheet",
        "amount": 1,
        "front": {"type": "scanning"},
        "back": {"type": "scanning"},
    }
    # The unsupported back is still rendered onto the front record.
    unsupported_back = {
        "id": "skill-01",
        "name": "Quick Thinking",
        "amount": 1,
        "project_number": "70",
        "front": {
            "type": "skill",
            "classes": ["rogue"],
            "level": "0",
            "icons": "A",
            "text": "Commit only to a test you are performing.",
        },
        "back": {"type": "scanning"},
    }
    project = _project(cards=[player_back, unsupported, unsupported_back])
    settings = {"url_prefix": "https://example.com/cards"}

    snapshot(export(project, settings)["data"]["cards"])


def test_metadata_override(export, snapshot):
    card = {
        "id": "story-02",
        "name": "A Hidden Passage",
        "amount": 1,
        "project_number": "80",
        "encounter_set": "enc-cult",
        "encounter_number": "6",
        "meta": {
            "arkham_build": {
                "text": "Manually written text.",
                "back": {"hidden": False, "shroud": 3},
            },
        },
        "front": {
            "type": "story",
            "text": "Generated text that gets overridden.",
        },
        "back": {
            "type": "location",
            "name": "Secret Tunnel",
            "traits": "Underground.",
            "clues": "1<per>",
        },
    }

    snapshot(export(_project(cards=[card]))["data"]["cards"])


def test_image_assets(export, snapshot, tmp_path):
    # Asset URLs contain the file hash, so the images are fixed files.
    for name in ("project.png", "rune.png"):
        shutil.copyfile(FIXTURE_DIR / name, tmp_path / name)

    card = {
        "id": "treachery-01",
        "name": "Marked by the Cult",
        "amount": 1,
        "project_number": "90",
        "encounter_set": "enc-cult",
        "encounter_number": "7",
        "front": {
            "type": "treachery",
            "traits": "Curse.",
            # The rune is also the encounter set icon, so it's exported once.
            "text": (
                "<rev> Place <esi> on your location. "
                '<image src="rune.png"> <image src="missing.png">'
            ),
        },
        "back": {"type": "encounter"},
    }
    project = _project(
        icon="project.png",
        encounter_sets=[
            {
                "id": "enc-cult",
                "name": "Cult of Testing",
                "icon": "rune.png",
                "cards": [],
            },
            {"id": "enc-rats", "name": "Swarm of Rats", "icon": "", "cards": []},
        ],
        cards=[card],
    )
    settings = {"url_prefix": "https://example.com/cards"}

    snapshot(export(project, settings))


def test_text_references(export, snapshot, tmp_path):
    shutil.copyfile(FIXTURE_DIR / "project.png", tmp_path / "project.png")

    target = {
        "id": "asset-02",
        "name": "Old Lantern",
        "amount": 1,
        "project_number": "95",
        "front": {
            "type": "asset",
            "classes": ["survivor"],
            "cost": "2",
            "level": "0",
            "text": "Uses (3 oil).",
        },
        "back": {"type": "player"},
    }
    location = {
        "id": "location-01",
        "name": "Abandoned Chapel",
        "amount": 2,
        "project_number": "96",
        "encounter_set": "enc-cult",
        "encounter_number": "8",
        "copyright": "© 2026 Snapshot Games",
        "front": {
            "type": "location",
            "shroud": "3",
            "clues": "2<per>",
            "text": (
                "<action>: Search the chapel for <:asset-02 name> "
                "(cost <:asset-02 front.cost>).\n"
                "Card <exn>, set card <esn> of <est> in <:enc-cult name>. "
                "<copyright> <exi>"
            ),
        },
        # The copied text resolves its references again. A field that is only
        # "<copy>" is resolved by the card model, so the tag is part of a text.
        "back": {"type": "location_back", "text": "Unrevealed. <copy>"},
    }
    project = _project(icon="project.png", cards=[target, location])
    settings = {"url_prefix": "https://example.com/cards"}

    snapshot(export(project, settings)["data"]["cards"])


def test_enemy_location(export, snapshot):
    card = {
        "id": "enemy-location-01",
        "name": "Writhing Nest",
        "amount": 1,
        "project_number": "100",
        "encounter_set": "enc-rats",
        "encounter_number": "9",
        "front": {
            "type": "enemy_location",
            "traits": "Lair. Monster.",
            "shroud": "2",
            "clues": "1<per>",
            "attack": "2",
            "evade": "3",
            "health": "2<per>",
            "damage": "1",
            "horror": "1",
            "victory": "Victory 1.",
            "text": "Massive.",
        },
        # A different type, so the back is a linked record.
        "back": {
            "type": "location_back",
            "traits": "Lair.",
            "text": "Something moves within.",
        },
    }
    settings = {"url_prefix": "https://example.com/cards"}

    snapshot(export(_project(cards=[card]), settings)["data"]["cards"])


@pytest.mark.assets
def test_full_art_act_and_agenda(export, snapshot):
    act = {
        "id": "act-02",
        "name": "The Grand Hall",
        "amount": 1,
        "project_number": "110",
        "encounter_set": "enc-cult",
        "encounter_number": "10",
        "front": {
            "type": "act_agenda_full",
            "index": "2a",
            "clues": "3<per>",
            "text": "Objective - Spend the requisite clues to advance.",
        },
        "back": {
            "type": "act_back",
            "name": "The Ritual Interrupted",
            "index": "2b",
            "text": "Each cultist is defeated.",
        },
    }
    # The back resolves the type to agenda, not the template's act default.
    agenda = {
        "id": "agenda-02",
        "name": "The Ritual Begins",
        "amount": 1,
        "project_number": "112",
        "encounter_set": "enc-cult",
        "encounter_number": "12",
        "front": {
            "type": "act_agenda_full",
            "index": "2a",
            "doom": "6",
            "text": (
                "<for> When this agenda advances, each investigator takes 1 horror."
            ),
        },
        "back": {
            "type": "agenda_back",
            "index": "2b",
            "text": "The cult completes the ritual.",
        },
    }
    # With two full-art sides the type is unknown, so the card is dropped.
    unresolved = {
        "id": "act-03",
        "name": "Final Confrontation",
        "amount": 1,
        "project_number": "111",
        "encounter_set": "enc-cult",
        "encounter_number": "11",
        "front": {
            "type": "act_agenda_full",
            "index": "3a",
            "text": "Defeat the High Priest.",
        },
        "back": {
            "type": "act_agenda_full_back",
            "index": "3b",
            "text": "The ritual ends.",
        },
    }
    project = _project(cards=[act, agenda, unresolved])
    settings = {"url_prefix": "https://example.com/cards"}

    snapshot(export(project, settings)["data"]["cards"])


def _treachery(text):
    return {
        "id": "treachery-02",
        "name": "Broken Text",
        "amount": 1,
        "front": {"type": "treachery", "text": text},
        "back": {"type": "encounter"},
    }


def test_circular_reference(export):
    project = _project(cards=[_treachery("Repeat <:treachery-02 front.text>")])

    with pytest.raises(ValueError, match="Circular text reference"):
        export(project)


@pytest.mark.parametrize(
    ("reference", "message"),
    [
        ("<:missing-card name>", "Unknown text reference"),
        ("<:treachery-02 front.missing>", "Unknown text reference"),
        ("<:treachery-02 front>", "Invalid text reference"),
    ],
)
def test_unknown_reference(export, reference, message):
    project = _project(cards=[_treachery(f"See {reference}.")])

    with pytest.raises(ValueError, match=message):
        export(project)


def test_circular_keyword(export, monkeypatch):
    translations = {"<for>": "<rev>", "<rev>": "<for>"}
    monkeypatch.setattr(text, "load_card_translations", lambda language: translations)
    project = _project(cards=[_treachery("<for> Take 1 horror.")])

    with pytest.raises(ValueError, match="Circular keyword translation"):
        export(project)
