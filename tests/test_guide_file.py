"""Guides stored in their own .guide.md files (shoggoth/guide_file.py): the
format round-trips exactly, reads hand-written files sensibly, and a project
reads and writes them without ever losing a guide."""
import itertools
import json

import pytest

from shoggoth import guide_file
from shoggoth.cloud import folder, sync
from shoggoth.guide import GuideSection
from shoggoth.modification import ModificationProject
from shoggoth.project import Project

from conftest import project_data

GUIDE_TEXT = '''---
name: The Night of the Zealot
format: a4
chapter: ch1
---

[section cover: Cover]

# The Night of the Zealot

[section scenario: The Gathering | set: es-1]

# Scenario I: The Gathering

:::story
*The fog rolls in...*
:::
'''


# ── The format ───────────────────────────────────────────────────────────

MARKDOWNS = ['', 'a', 'a\n', '\na', '\n\na\n\n', '# T\n\n:::story\nx\n:::\n',
             '[section blank: looks like a marker]', '\\[section y]\n\\\\[section z: q]']
NAMES = ['', 'Intro', 'A | B', 'x]y', '1929', 'true', ' padded ', '"quoted"', 'Æblegrød 日本']


@pytest.mark.parametrize('markdown, name', list(itertools.product(MARKDOWNS, NAMES)))
@pytest.mark.parametrize('count', [1, 2])
def test_roundtrip(markdown, name, count):
    entry = {
        'name': name or 'Guide', 'format': 'a4', 'number': 5, 'text_number': '5', 'nested': {'a': [1]},
        'sections': [{'type': 'scenario', 'name': name, 'markdown': markdown, 'encounter_set_id': 'es|1'}] * count,
    }
    text = guide_file.serialize(entry)
    assert guide_file.parse(text) == entry
    assert guide_file.serialize(guide_file.parse(text)) == text


def test_project_keys_stay_out_of_the_file():
    text = guide_file.serialize({'id': 'g', 'file': 'x.guide.md', 'meta': {'modified': 1}, 'name': 'G',
                                 'sections': []})
    assert 'modified' not in text and 'x.guide.md' not in text and 'id:' not in text


def test_reads_the_documented_example():
    entry = guide_file.parse(GUIDE_TEXT)
    assert entry['name'] == 'The Night of the Zealot'
    assert [(s['type'], s['name']) for s in entry['sections']] == [('cover', 'Cover'), ('scenario', 'The Gathering')]
    assert entry['sections'][1]['encounter_set_id'] == 'es-1'
    assert entry['sections'][1]['markdown'] == '# Scenario I: The Gathering\n\n:::story\n*The fog rolls in...*\n:::'
    assert guide_file.serialize(entry) == GUIDE_TEXT


def test_hand_written_files():
    # no header, text before any marker, CRLF, a numeric-looking name, no blank lines
    entry = guide_file.parse('Some intro\r\n[section intro: 1929]\r\nBody\r\n', default_name='mine')
    assert entry == {'name': 'mine', 'sections': [
        {'type': 'blank', 'name': '', 'markdown': 'Some intro'},
        {'type': 'intro', 'name': '1929', 'markdown': 'Body'},
    ]}
    assert guide_file.parse('---\nname: 1929\n---\n')['name'] == '1929'
    # an unclosed header is just text
    assert guide_file.parse('---\nname: x\n')['sections'][0]['markdown'] == '---\nname: x'


# ── In a project ─────────────────────────────────────────────────────────

@pytest.fixture
def file_project(tmp_path, load_project):
    (tmp_path / 'guides').mkdir()
    (tmp_path / 'guides' / 'zealot.guide.md').write_text(GUIDE_TEXT, encoding='utf-8')
    return load_project(project_data(guides=[{'id': 'g', 'file': 'guides/zealot.guide.md'}]))


def stored(project):
    return json.loads(open(project.file_path, encoding='utf-8').read())


def test_load_reads_the_file(file_project):
    guide = file_project.get_guide('g')
    assert guide.is_in_file and guide.name == 'The Night of the Zealot'
    assert [s.id for s in guide.sections] == ['s1', 's2']  # by position


def test_save_keeps_project_file_to_a_reference(file_project, tmp_path):
    guide = file_project.get_guide('g')
    sections = guide.sections
    sections[0].markdown = '# Changed'
    guide.save_sections(sections)
    assert stored(file_project)['guides'] == [{'id': 'g', 'file': 'guides/zealot.guide.md'}]
    text = (tmp_path / 'guides' / 'zealot.guide.md').read_text(encoding='utf-8')
    assert '# Changed' in text and 'id' not in text.split('---')[1]
    assert Project.load(file_project.file_path).get_guide('g').sections[0].markdown == '# Changed'


def test_unchanged_guide_file_is_not_rewritten(file_project, tmp_path):
    path = tmp_path / 'guides' / 'zealot.guide.md'
    path.write_text(GUIDE_TEXT.replace('Cover', 'Edited elsewhere'), encoding='utf-8')
    file_project.save_all()  # the guide wasn't edited here: the outside edit stays
    assert 'Edited elsewhere' in path.read_text(encoding='utf-8')
    assert file_project.changed_guide_files() == ['g']


def test_outside_edit_is_found_and_reloaded(file_project, tmp_path):
    assert file_project.changed_guide_files() == []
    path = tmp_path / 'guides' / 'zealot.guide.md'
    path.write_text(GUIDE_TEXT.replace('# The Night', '# The Long Night'), encoding='utf-8')
    assert file_project.changed_guide_files() == ['g']
    guide = file_project.get_guide('g')
    file_project.reload_guide('g')
    assert guide.sections[0].markdown == '# The Long Night of the Zealot'  # same dict, updated
    assert file_project.changed_guide_files() == []


def test_keep_my_version_overwrites_on_next_save(file_project, tmp_path):
    path = tmp_path / 'guides' / 'zealot.guide.md'
    path.write_text('outside', encoding='utf-8')
    file_project.acknowledge_guide_file('g')
    assert file_project.changed_guide_files() == []
    guide = file_project.get_guide('g')
    guide.name = 'Mine'
    file_project.save_all()
    assert 'name: Mine' in path.read_text(encoding='utf-8')


def test_missing_file_is_never_written_over(tmp_path, load_project):
    project = load_project(project_data(guides=[{'id': 'g', 'file': 'gone.guide.md'}]))
    assert 'g' in project.missing_guide_files
    project.save_all()
    assert not (tmp_path / 'gone.guide.md').exists()
    assert stored(project)['guides'] == [{'id': 'g', 'file': 'gone.guide.md'}]


def test_missing_file_with_inline_content_is_written(tmp_path, load_project):
    """A guide taken from the cloud (or a fresh cloud copy) carries its content."""
    project = load_project(project_data(guides=[{'id': 'g', 'file': 'new.guide.md', 'name': 'N', 'sections': []}]))
    assert not project.missing_guide_files
    project.save_all()
    assert guide_file.parse((tmp_path / 'new.guide.md').read_text(encoding='utf-8'))['name'] == 'N'


def test_move_into_file_and_back(tmp_path, load_project):
    project = load_project(project_data(guides=[{
        'id': 'g', 'name': 'G', 'meta': {'modified': 5},
        'sections': [{'id': 'abc', 'type': 'intro', 'name': 'I', 'markdown': 'text'}]}]))
    project.store_guide_in_file('g', tmp_path / 'sub' / 'g.guide.md')
    project.save_all()
    assert stored(project)['guides'][0]['file'] == 'sub/g.guide.md'
    assert stored(project)['guides'][0]['meta'] == {'modified': 5}  # bookkeeping stays in the project file
    assert 'text' in (tmp_path / 'sub' / 'g.guide.md').read_text(encoding='utf-8')

    project.store_guide_inline('g')
    project.save_all()
    entry = stored(project)['guides'][0]
    assert 'file' not in entry and entry['sections'][0]['markdown'] == 'text'
    assert (tmp_path / 'sub' / 'g.guide.md').exists()  # left on disk


def test_save_as_keeps_pointing_at_the_same_file(file_project, tmp_path):
    (tmp_path / 'elsewhere').mkdir()
    file_project.save_as(tmp_path / 'elsewhere' / 'copy.shoggoth')
    assert stored(file_project)['guides'][0]['file'] == '../guides/zealot.guide.md'
    assert Project.load(file_project.file_path).get_guide('g').name == 'The Night of the Zealot'


def test_adding_a_section_gives_it_its_positional_id(file_project):
    guide = file_project.get_guide('g')
    sections = guide.sections
    new = GuideSection.new('blank', 'New')
    sections.insert(0, new)
    guide.save_sections(sections)
    assert new.id == 's1'
    assert guide.sections[0].name == 'New'


def test_modification_of_a_project_with_guide_files(file_project, tmp_path):
    guide_text = (tmp_path / 'guides' / 'zealot.guide.md').read_text(encoding='utf-8')
    mod = ModificationProject.create(tmp_path / 'da.shoggoth', file_project.file_path, language='da')
    guide = mod.get_guide('g')
    assert guide.name == 'The Night of the Zealot'
    guide.name = 'Zelotens nat'
    mod.save_all()
    changes = json.loads((tmp_path / 'da.shoggoth').read_text(encoding='utf-8'))['guides']
    assert changes['g']['name'] == 'Zelotens nat'
    assert (tmp_path / 'guides' / 'zealot.guide.md').read_text(encoding='utf-8') == guide_text
    assert mod.guide_file_paths() == {}  # the parent's files, watched as the parent's


# ── Cloud ────────────────────────────────────────────────────────────────

def test_guide_files_are_not_synced_as_resources():
    assert folder.is_ignored('guides/zealot.guide.md')
    assert not folder.is_ignored('guides/notes.md')


def test_missing_guide_is_left_out_of_the_merge(tmp_path, load_project):
    project = load_project(project_data(guides=[{'id': 'g', 'file': 'gone.guide.md'},
                                               {'id': 'h', 'name': 'H', 'sections': []}]))
    assert [g['id'] for g in sync._local_data(project)['guides']] == ['h']
