"""Guide preview page map: script injection and log parsing."""
from shoggoth.guide import parse_page_map, with_page_map_script


def test_script_goes_at_end_of_body():
    html = '<html><body><p>a</p></body></html>'
    out = with_page_map_script(html)
    assert out.startswith('<html><body><p>a</p><script>')
    assert out.endswith('</script></body></html>')
    assert 'Prince.trackBoxes = true' in out


def test_script_appended_without_body():
    assert with_page_map_script('<p>a</p>').startswith('<p>a</p><script>')


def test_parse_structured_log():
    log = ('wrn|some.css|ignored property\n'
           'msg|out|SHOGGOTH_PAGES {"pages":53,"sections":{"s0":1,"s1":6}}\n'
           'fin|success\n')
    assert parse_page_map(log) == (53, {'s0': 1, 's1': 6})


def test_parse_without_page_count():
    assert parse_page_map('SHOGGOTH_PAGES {"pages":null,"sections":{}}') == (None, {})


def test_parse_nothing_reported():
    assert parse_page_map('fin|success\n') is None
    assert parse_page_map('msg|out|SHOGGOTH_PAGES {broken') is None


def test_change_type_keeps_text_and_drops_link():
    from shoggoth.guide import GuideSection
    s = GuideSection('scenario', 'Scenario', '# [encounter:a:name]\n', encounter_set_id='a')
    s.change_type('interlude')
    assert (s.type, s.encounter_set_id) == ('interlude', None)
    assert s.markdown == '# [encounter:a:name]\n'


def test_relinking_scenario_rewrites_old_set_references():
    from shoggoth.guide import GuideSection
    text = '[encounter:a:name] [enc:a] [encounter:ab:icon] [card:a]'
    s = GuideSection('scenario', 'Scenario', text, encounter_set_id='a')
    s.change_type('scenario', 'b')
    assert s.encounter_set_id == 'b'
    assert s.markdown == '[encounter:b:name] [enc:b] [encounter:ab:icon] [card:a]'


def test_blank_to_scenario_links_set():
    from shoggoth.guide import GuideSection
    s = GuideSection('blank', 'Blank', 'hi')
    s.change_type('scenario', 'x')
    assert (s.type, s.encounter_set_id, s.markdown) == ('scenario', 'x', 'hi')


def test_guide_edits_mark_it_changed(tmp_path):
    """Cloud sync only sends what was marked changed (and stamped)."""
    from shoggoth.guide import GuideSection
    from shoggoth.project import Project
    data = {'id': 'p', 'name': 'P', 'cards': [], 'encounter_sets': [],
            'guides': [{'id': 'g', 'name': 'Guide', 'sections': []}],
            'meta': {'celaeno_id': 'cloud'}}
    project = Project(str(tmp_path / 'project.shoggoth'), data)
    heard = []
    Project._change_listeners.append(lambda p, kind, i, changed: heard.append((kind, i, changed)))
    try:
        guide = project.guides[0]
        guide.name = 'Guide'  # unchanged: nothing to mark
        assert not guide.dirty and not heard
        guide.front_page = 'cover.png'
        assert guide.dirty and heard == [('guides', 'g', True)]
        assert data['guides'][0]['meta']['modified'] > 0
        heard.clear()
        guide.save_sections([GuideSection.new('blank', 'Intro')])
        assert heard == [('guides', 'g', True)]
    finally:
        Project._change_listeners.pop()
