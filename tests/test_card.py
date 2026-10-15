"""How a face resolves its values: stored data, inheritance, the defaults
chain with its variant blocks, legacy class suffixes and '<copy>'."""
import pytest

from shoggoth.card import matches, natural_sort_key
from shoggoth.project import Project, parse_legacy_collection, migrate_legacy_collection_fields

from conftest import card_data, project_data


def make_project(*cards, **extra):
    return Project('unused.shoggoth', project_data(cards=cards, **extra))


# ── matches() ────────────────────────────────────────────────────────────

@pytest.mark.parametrize('when, tags, expected', [
    (None, set(), True),
    ('', {'guardian'}, True),
    ('guardian', {'guardian'}, True),
    ('guardian', {'seeker'}, False),
    (['seeker', 'guardian'], {'guardian'}, True),
    ('encounter & !story', {'encounter'}, True),
    ('encounter & !story', {'encounter', 'story'}, False),
    ('encounter&!story', {'encounter'}, True),
    ('multi & multi2', {'multi', 'multi2'}, True),
    ('multi & multi3', {'multi', 'multi2'}, False),
    ('basic weakness', {'basic weakness'}, True),
    ('!weakness', set(), True),
])
def test_matches(when, tags, expected):
    assert matches(when, tags) is expected


def test_natural_sort_key_orders_numbers_numerically():
    values = ['10', '2', '2a', '1', '128b', '128a', 'x']
    assert sorted(values, key=natural_sort_key) == ['1', '2', '2a', '10', '128a', '128b', 'x']


# ── Defaults chain ───────────────────────────────────────────────────────

def test_stored_value_beats_defaults(defaults):
    defaults('asset', {'text': 'default text'})
    project = make_project(card_data('a', front={'type': 'asset', 'text': 'mine'}))
    assert project.get_card('a').front['text'] == 'mine'


def test_missing_value_comes_from_defaults(defaults):
    defaults('asset', {'text': 'default text'})
    project = make_project(card_data('a'))
    face = project.get_card('a').front
    assert face['text'] == 'default text'
    assert face.get('nothing', 'fallback') == 'fallback'
    with pytest.raises(KeyError):
        face['nothing']


def test_parent_chain_child_overrides(defaults):
    defaults('base', {'a': 'base a', 'b': 'base b'})
    defaults('asset', {'parent': 'base', 'b': 'asset b'})
    face = make_project(card_data('x')).get_card('x').front
    assert face['a'] == 'base a'
    assert face['b'] == 'asset b'


def test_variants_match_class_and_later_blocks_win(defaults):
    defaults('asset', {
        'text1': 'plain',
        'variants': [
            {'when': ['weakness', 'basic weakness'], 'set': {'text1': 'WEAKNESS'}},
            {'when': 'basic weakness', 'set': {'text1': 'BASIC WEAKNESS'}},
        ],
    })
    project = make_project(
        card_data('plain', front={'type': 'asset', 'classes': ['guardian']}),
        card_data('weak', front={'type': 'asset', 'classes': ['weakness']}),
        card_data('basic', front={'type': 'asset', 'classes': ['basic weakness']}),
    )
    assert project.get_card('plain').front['text1'] == 'plain'
    assert project.get_card('weak').front['text1'] == 'WEAKNESS'
    assert project.get_card('basic').front['text1'] == 'BASIC WEAKNESS'


def test_child_variants_win_over_parent_variants(defaults):
    defaults('base', {'variants': [{'when': 'seeker', 'set': {'k': 'from base'}}]})
    defaults('asset', {'parent': 'base', 'variants': [{'when': 'seeker', 'set': {'k': 'from asset'}}]})
    face = make_project(card_data('x', front={'type': 'asset', 'classes': ['seeker']})).get_card('x').front
    assert face['k'] == 'from asset'


def test_multi_class_tags(defaults):
    defaults('asset', {
        'k': 'single',
        'variants': [
            {'when': 'multi', 'set': {'k': 'multi'}},
            {'when': 'multi3', 'set': {'k': 'three'}},
            {'when': 'guardian', 'set': {'k': 'guardian'}},
        ],
    })
    project = make_project(
        card_data('two', front={'type': 'asset', 'classes': ['guardian', 'seeker']}),
        card_data('three', front={'type': 'asset', 'classes': ['guardian', 'seeker', 'rogue']}),
    )
    two = project.get_card('two').front
    # individual classes are deliberately not tags on multi-class cards
    assert two.tags() == {'multi', 'multi2', 'multi1+', 'multi2+'}
    assert two['k'] == 'multi'
    assert project.get_card('three').front['k'] == 'three'


def test_encounter_pseudo_tag(defaults):
    defaults('treachery', {'collection': 'player', 'variants': [
        {'when': 'encounter & !story', 'set': {'collection': 'encounter'}},
    ]})
    project = make_project(
        card_data('p', front={'type': 'treachery'}),
        card_data('e', front={'type': 'treachery'}, encounter_set='set'),
    )
    assert project.get_card('p').front['collection'] == 'player'
    assert project.get_card('e').front['collection'] == 'encounter'


def test_legacy_class_suffix_keys(defaults):
    defaults('asset', {'name': 'plain', 'name_weakness': 'weak', 'template_multi3': 'm3', 'template_multi2+': 'm2+', 'template': 't'})
    project = make_project(
        card_data('w', front={'type': 'asset', 'classes': ['weakness']}),
        card_data('m3', front={'type': 'asset', 'classes': ['a', 'b', 'c']}),
        card_data('m4', front={'type': 'asset', 'classes': ['a', 'b', 'c', 'd']}),
        card_data('one', front={'type': 'asset', 'classes': ['a']}),
    )
    assert project.get_card('w').front['name'] == 'weak'
    assert project.get_card('m3').front['template'] == 'm3'
    assert project.get_card('m4').front['template'] == 'm2+'
    assert project.get_card('one').front['template'] == 't'


def test_variants_beat_legacy_suffixes(defaults):
    defaults('asset', {'name_weakness': 'legacy', 'variants': [{'when': 'weakness', 'set': {'name': 'variant'}}]})
    face = make_project(card_data('w', front={'type': 'asset', 'classes': ['weakness']})).get_card('w').front
    assert face['name'] == 'variant'


def test_project_local_defaults_file_wins(defaults, tmp_path):
    defaults('asset', {'k': 'asset pack'})
    local = tmp_path / 'my_type.json'
    local.write_text('{"k": "local"}', encoding='utf-8')
    project = Project(str(tmp_path / 'p.shoggoth'), project_data(cards=[card_data('x', front={'type': str(local)})]))
    face = project.get_card('x').front
    assert face['k'] == 'local'
    assert face.fallback_files == (local.resolve(),)


def test_changing_type_reloads_defaults(defaults):
    defaults('asset', {'k': 'asset'})
    defaults('event', {'k': 'event'})
    face = make_project(card_data('x')).get_card('x').front
    assert face['k'] == 'asset'
    face.set('type', 'event')
    assert face['k'] == 'event'
    with pytest.raises(ValueError):
        face.set('type', '')


def test_broken_defaults_file_does_not_crash(defaults, tmp_path):
    (tmp_path / 'defaults' / 'asset.json').write_text('{not json', encoding='utf-8')
    face = make_project(card_data('x')).get_card('x').front
    assert face.get('anything', 'default') == 'default'


# ── '<copy>' and inheritance ─────────────────────────────────────────────

def test_copy_takes_other_side(defaults):
    project = make_project(card_data('x', front={'type': 'asset', 'name': 'Front'}, back={'type': 'player', 'name': '<copy>'}))
    assert project.get_card('x').back['name'] == 'Front'


def test_mutual_copy_is_missing_not_a_loop(defaults):
    project = make_project(card_data('x', front={'type': 'asset', 'k': '<copy>'}, back={'type': 'player', 'k': '<copy>'}))
    assert project.get_card('x').front.get('k', 'none') == 'none'


def test_inherit_from_other_card(defaults):
    defaults('asset', {'text': 'default'})
    project = make_project(
        card_data('source', front={'type': 'asset', 'text': 'shared', 'traits': 'Item.'}),
        card_data('child', front={'type': 'asset', 'inherit': {'card': 'source', 'face': 'front'}, 'traits': 'Own.'}),
    )
    child = project.get_card('child').front
    assert child['text'] == 'shared'
    assert child['traits'] == 'Own.'
    assert project.inheriting_card_ids('source') == {'child'}


def test_inherit_from_deleted_card_falls_back_to_defaults(defaults):
    defaults('asset', {'text': 'default'})
    project = make_project(card_data('child', front={'type': 'asset', 'inherit': {'card': 'gone', 'face': 'front'}}))
    assert project.get_card('child').front['text'] == 'default'


def test_inheritance_cycle_does_not_loop(defaults):
    defaults('asset', {'text': 'default'})
    project = make_project(
        card_data('a', front={'type': 'asset', 'inherit': {'card': 'b', 'face': 'front'}}),
        card_data('b', front={'type': 'asset', 'inherit': {'card': 'a', 'face': 'front'}}),
    )
    assert project.get_card('a').front['text'] == 'default'
    assert project.inheriting_card_ids('a') == {'b'}


# ── Card types ───────────────────────────────────────────────────────────

def test_card_type_from_defaults_or_type_name(defaults):
    defaults('enemy_location', {'card_type': 'location', 'card_types': ['location', 'enemy']})
    project = make_project(
        card_data('blend', front={'type': 'enemy_location'}),
        card_data('plain', front={'type': 'asset'}),
        card_data('backonly', front={'type': ''}, back={'type': 'treachery_back'}),
    )
    assert project.get_card('blend').card_types == ['location', 'enemy']
    assert project.get_card('plain').card_type == 'asset'
    assert project.get_card('backonly').card_type == 'treachery'


def test_versions_split_encounter_number_range(defaults):
    project = make_project(card_data('x', encounter_number='3-5', encounter_set='set'),
                           encounter_sets=[{'id': 'set', 'name': 'Set', 'icon': ''}])
    card = project.get_card('x')
    assert [v.data['encounter_number'] for v in card.versions] == [3, 4, 5]
    assert card.data['encounter_number'] == '3-5'
    assert not card.dirty


# ── Legacy collection fields ─────────────────────────────────────────────

@pytest.mark.parametrize('value, expected', [
    ('12/30 <icon>   12', {'collection_total': '12/30', 'collection_icon': '<icon>', 'collection_number': '12'}),
    ('<icon>   7', {'collection_icon': '<icon>', 'collection_number': '7'}),
    ('<icon>', {'collection_icon': '<icon>', 'collection_number': ''}),
])
def test_parse_legacy_collection(value, expected):
    assert parse_legacy_collection(value) == expected


def test_migrate_legacy_collection_fields():
    data = {'cards': [{'front': {'collection': '1/2 x   1'}, 'back': {}}]}
    assert migrate_legacy_collection_fields(data) == 1
    assert data['cards'][0]['front'] == {'collection_total': '1/2', 'collection_icon': 'x', 'collection_number': '1'}
    assert migrate_legacy_collection_fields(data) == 0
