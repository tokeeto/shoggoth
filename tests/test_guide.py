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
