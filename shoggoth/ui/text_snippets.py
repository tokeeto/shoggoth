"""
Data for Ctrl+Space snippet sequences: short mnemonic key-chains that expand
into standard Arkham Horror card-text phrases (see ui/snippet_input.py for the
input handling and ui/snippet_overlay.py for the on-screen key reminder).

The sequence space is a tree: each key press either descends into a Branch
(another set of key choices) or lands on a Leaf (the text to insert, which
ends the sequence). ROOT is the tree entered right after Ctrl+Space.
"""

DIGITS = [str(d) for d in range(10)]


class Leaf:
    """A terminal node: pressing its key inserts text and ends the sequence."""
    __slots__ = ('build',)

    def __init__(self, text_or_build):
        self.build = text_or_build if callable(text_or_build) else (lambda: text_or_build)


class CallLeaf:
    """A terminal node backed by a user-supplied function (see snippet_loader.py).

    Called as fn(face, card, project) when reached. A string return value is
    inserted at the cursor like a plain Leaf; any other return value is
    ignored, letting the function make its own changes to the card instead.
    """
    __slots__ = ('fn',)

    def __init__(self, fn):
        self.fn = fn


class Branch:
    """A non-terminal node: a set of key -> (label, child node) choices.

    `hint` may be None for branches created dynamically while merging user
    snippets in - see snippet_loader.merge_snippets(), which fills it in
    once the full set of children at that branch is known.
    """
    __slots__ = ('title', 'hint', 'options')

    def __init__(self, title, hint, options):
        self.title = title
        self.hint = hint
        self.options = options


def _digit_options(make_child):
    """dict: '0'..'9' -> (digit, make_child(digit))"""
    return {d: (d, make_child(d)) for d in DIGITS}


# ---------------------------------------------------------------------------
# T - Test: stat -> value (0-9 or X) -> fail/succeed
# ---------------------------------------------------------------------------

def _result_branch(stat, value):
    return Branch('Result', '[F]ail  [S]ucceed', {
        'f': ('Fail', Leaf(f'test <{stat}> ({value}). If you fail ')),
        's': ('Succeed', Leaf(f'test <{stat}> ({value}). If you succeed ')),
    })


def _value_branch(stat):
    options = _digit_options(lambda d, s=stat: _result_branch(s, d))
    options['x'] = ('X', _result_branch(stat, 'X'))
    return Branch('Value', '0-9 or [X]', options)


def _test_branch():
    stats = [('w', 'willpower'), ('i', 'intellect'), ('c', 'combat'), ('a', 'agility')]
    return Branch('Stat', '[W]illpower  [I]ntellect  [C]ombat  [A]gility', {
        key: (word.capitalize(), _value_branch(word)) for key, word in stats
    })


# ---------------------------------------------------------------------------
# C - Class: class -> level (0-5)
# ---------------------------------------------------------------------------

def _class_text(cls, level):
    label = cls.capitalize()
    if cls == 'neutral':
        return f'{label} cards level 0-{level}.'
    return f'{label} cards (<{cls}>) level 0-{level}.'


def _level_branch(cls):
    options = {str(d): (str(d), Leaf(_class_text(cls, str(d)))) for d in range(6)}
    return Branch('Level', '0-5', options)


def _class_branch():
    classes = [('g', 'guardian'), ('s', 'seeker'), ('u', 'survivor'),
               ('m', 'mystic'), ('r', 'rogue'), ('n', 'neutral')]
    return Branch('Class', '[G]uardian  [S]eeker  s[U]rvivor  [M]ystic  [R]ogue  [N]eutral', {
        key: (cls.capitalize(), _level_branch(cls)) for key, cls in classes
    })


# ---------------------------------------------------------------------------
# L - Limit: once-per / group / max / skill-test / commit-only / in-play
# ---------------------------------------------------------------------------

def _once_suffix_branch(stat):
    options = {' ': ('none', Leaf(f'(Limit once per {stat}.)'))}
    for key, noun in [('i', 'investigator'), ('v', 'vehicle'), ('e', 'enemy'), ('l', 'location')]:
        options[key] = (noun.capitalize(), Leaf(f'(Limit once per {stat}, for each {noun}.)'))
    return Branch('For each', '[Space] none  [I]nvestigator [V]ehicle [E]nemy [L]ocation', options)


def _once_branch():
    stats = [('r', 'round'), ('p', 'phase'), ('g', 'game'), ('t', 'turn'),
             ('s', 'test'), ('i', 'investigator')]
    return Branch('Per', '[R]ound [P]hase [G]ame [T]urn te[S]t [I]nvestigator', {
        key: (stat.capitalize(), _once_suffix_branch(stat)) for key, stat in stats
    })


_GROUP_MAX_STATS = [('r', 'round'), ('p', 'phase'), ('g', 'game'), ('t', 'turn'), ('i', 'investigator')]
_GROUP_MAX_HINT = '[R]ound [P]hase [G]ame [T]urn [I]nvestigator'


def _stat_leaf_options(template):
    return {key: (stat.capitalize(), Leaf(template.format(stat))) for key, stat in _GROUP_MAX_STATS}


def _inplay_branch():
    return Branch('Scope', '[P]er deck/investigator  [I]n play by trait', {
        'p': ('Per', Branch('Per', '[D]eck [I]nvestigator', {
            'd': ('Deck', Leaf('Limit 1 per deck.')),
            'i': ('Investigator', Leaf('Limit 1 per investigator.')),
        })),
        'i': ('Trait', Leaf('Limit 1 <t>trait</t> in play.')),
    })


def _limit_branch():
    return Branch('Limit', '[O]nce per..  [G]roup  [M]ax  [S]kill-test  [C]ommit-only  [L]imit in play', {
        'o': ('Once', _once_branch()),
        'g': ('Group', Branch('Per', _GROUP_MAX_HINT, _stat_leaf_options('(Group limit once per {}.)'))),
        'm': ('Max', Branch('Per', _GROUP_MAX_HINT, _stat_leaf_options('(Max once per {}.)'))),
        's': ('Skill test', Leaf('Max 1 committed per skill test.')),
        'c': ('Commit only', Leaf('Commit only to a skill test you are performing.')),
        'l': ('In play', _inplay_branch()),
    })


# ---------------------------------------------------------------------------
# E - Elder sign effect: +number
# ---------------------------------------------------------------------------

def _elder_branch():
    return Branch('Number', '0-9', _digit_options(lambda d: Leaf(f'<elder_sign> effect: +{d}. ')))


# ---------------------------------------------------------------------------
# A - Attack: +combat bonus / +damage bonus (0 omits that clause), or no AoO
# ---------------------------------------------------------------------------

def _attack_text(combat_bonus, damage_bonus):
    parts = []
    if combat_bonus != '0':
        parts.append(f'You get +{combat_bonus} <combat> for this attack.')
    if damage_bonus != '0':
        parts.append(f'This attack deals +{damage_bonus} damage.')
    return ' '.join(parts)


def _attack_branch():
    def make_damage_branch(combat_bonus):
        return Branch('Damage', '0-9', _digit_options(
            lambda d, c=combat_bonus: Leaf(_attack_text(c, d))
        ))

    options = _digit_options(make_damage_branch)
    options['o'] = ('No AoO', Leaf('This action does not provoke attacks of opportunity.'))
    return Branch('Bonus', '0-9 combat bonus, or [O] no AoO', options)


# ---------------------------------------------------------------------------
# U - Uses: resource type -> count
# ---------------------------------------------------------------------------

_USES_RESOURCES = [('c', 'charges'), ('s', 'secrets'), ('a', 'ammo'), ('u', 'supplies'), ('e', 'evidence')]


def _uses_branch():
    options = {}
    for key, word in _USES_RESOURCES:
        options[key] = (
            word.capitalize(),
            Branch('Value', '0-9', _digit_options(lambda d, w=word: Leaf(f'Uses ({d} {w})'))),
        )
    return Branch('Resource', '[C]harges [S]ecrets [A]mmo s[U]pplies [E]vidence', options)


# ---------------------------------------------------------------------------
# F - Fast: turn / any window / except action / none
# ---------------------------------------------------------------------------

def _fast_branch():
    return Branch('Restriction', '[T]urn  [A]ny window  [E]xcept action  [Space] none', {
        't': ('Turn', Leaf('Fast. Play only during your turn.')),
        'a': ('Any window', Leaf('Fast. Play during any <free> window.')),
        'e': ('Except action', Leaf('Fast. Play during any <free> window except during an action.')),
        ' ': ('None', Leaf('Fast.')),
    })


# ---------------------------------------------------------------------------
# O - Objective: resign-to-advance / instructed
# ---------------------------------------------------------------------------

def _objective_branch():
    return Branch('Objective', '[R]esign-advance  [I]nstructed', {
        'r': ('Resign advance', Leaf('<objective> If each undefeated investigator has resigned, advance.')),
        'i': ('Instructed', Leaf('<i>(You will be instructed when to advance.)</i>')),
    })


# ---------------------------------------------------------------------------
# R - Reminder: browsed by (reassigned, unique) single-letter key
# ---------------------------------------------------------------------------

_REMINDERS = [
    ('e', 'Each investigator', 'In player order, each investigator ...'),
    ('i', 'Success by 2+', 'If this skill test is successful by 2 or more ...'),
    ('p', 'No AoO', 'Does not provoke attacks of opportunity.'),
    ('r', 'Uses (2 resources)', 'Uses (2 resources). Replenish these resources at the start of each round.'),
    ('o', 'Investigate by 2+', 'After you successfully investigate by 2 or more, exhaust <name>...'),
    ('m', 'Mythos draw step', 'Play when the "draw encounter cards" step of the mythos phase would begin.'),
    ('b', 'Prey bearer', '<prey> Bearer only.'),
    ('t', 'Choose a token', 'Choose one of those tokens to resolve, and ignore the rest.'),
    ('a', 'Ignore aloof/retaliate', 'Ignore the aloof and retaliate keywords for this attack'),
    ('s', 'Add skill', 'Add your <[skill]> to your skill value for this test.'),
    ('c', 'Either/choose one', 'Either (choose one):'),
    ('n', 'Connecting location', 'Move to a connecting location'),
    ('d', 'Bonded search', 'Search your bonded cards for [card name] and add it to your hand.'),
]


def _reminder_branch():
    hint = '  '.join(f'[{key.upper()}]{label}' for key, label, _text in _REMINDERS)
    options = {key: (label, Leaf(text)) for key, label, text in _REMINDERS}
    return Branch('Reminder', hint, options)


# ---------------------------------------------------------------------------
# Root registry
# ---------------------------------------------------------------------------

_TOP_LEVEL = [
    ('t', 'Test', _test_branch()),
    ('c', 'Class', _class_branch()),
    ('l', 'Limit', _limit_branch()),
    ('e', 'Elder sign', _elder_branch()),
    ('a', 'Attack', _attack_branch()),
    ('u', 'Uses', _uses_branch()),
    ('f', 'Fast', _fast_branch()),
    ('o', 'Objective', _objective_branch()),
    ('p', 'Put into play', Leaf('<rev> Put <name> into play in your threat area.')),
    ('r', 'Reminder', _reminder_branch()),
]

ROOT = Branch(
    title='Snippet',
    hint='  '.join(f'[{key.upper()}]{label[1:]}' for key, label, _node in _TOP_LEVEL),
    options={key: (label, node) for key, label, node in _TOP_LEVEL},
)
