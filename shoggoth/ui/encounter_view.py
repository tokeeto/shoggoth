"""
Encounter View - an encounter set's encounter deck at a glance.

Three columns: Enemies, Treacheries and Other (the rest of the set's
Encounter group, flippable with F / Shift+F). Enemies and treacheries are
dealt out one item per copy, each copy overlapping the previous one like a
fanned hand of cards, so the copy count is visible; the next card starts a
new row.

Above the columns, stats counted per copy:
  * Enemies: total health, share of the encounter deck (enemies / (enemies
    + treacheries)), and bar charts of combat and evade (X, 1 … 5, 6+) with
    median and mean.
  * Treacheries: skill tests found in the text ("Test <willpower> (3)" -
    a plain text search for now), charted by difficulty and colored by
    skill, plus each skill's count and share of the treachery copies; and
    how many treachery copies deal damage / horror (a number right before
    the word, "take 2 horror" - so "heal all damage" doesn't count), or let
    the player choose ("1 damage or horror", "1 damage or 1 horror").
"""
import re
from statistics import mean, median

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPen
from PySide6.QtWidgets import QGraphicsItem

from shoggoth.export_helpers import parse_per_value
from shoggoth.i18n import tr
from shoggoth.ui.card_board import (
    CARD_LONG, COLUMN_GAP, DIM_TEXT_COLOR, CardBoardView, CardBoardWidget, amount_html, side_size,
)


BUCKETS = ['X', '1', '2', '3', '4', '5', '6+']
OVERLAP = 0.85          # how much of a copy the next copy covers
ROW_GAP = 24            # between two different cards in a column
MIN_COLUMN_WIDTH = 340  # room for the charts
CHART_HEIGHT = 120

SKILLS = ['willpower', 'intellect', 'combat', 'agility']
SKILL_ALIASES = {'wil': 'willpower', 'int': 'intellect', 'com': 'combat', 'agi': 'agility'}
SKILL_COLORS = {
    'willpower': QColor(70, 130, 215),
    'intellect': QColor(230, 145, 40),
    'combat': QColor(215, 60, 55),
    'agility': QColor(60, 170, 85),
}
SKILL_NAMES = {'willpower': 'Willpower', 'intellect': 'Intellect', 'combat': 'Combat', 'agility': 'Agility'}

_TEST_RE = re.compile(
    r'test\s*<(willpower|intellect|combat|agility|wil|int|com|agi)>\s*\(\s*([^)]*?)\s*\)',
    re.IGNORECASE,
)

# "<number> damage/horror": deals it, as opposed to "heal all damage" or
# "the enemy with the most damage"
_HARM_RE = re.compile(r'\b\d+\s+(damage|horror)\b', re.IGNORECASE)
# the player's choice: "1 damage or horror", "1 horror or 1 damage"
_EITHER_RE = re.compile(r'\b\d+\s+(?:damage\s+or\s+(?:\d+\s+)?horror|horror\s+or\s+(?:\d+\s+)?damage)\b',
                        re.IGNORECASE)
HARM_TYPES = ['damage', 'horror', 'either']
HARM_COLORS = {'damage': QColor(200, 70, 60), 'horror': QColor(70, 110, 200), 'either': QColor(150, 100, 190)}
HARM_NAMES = {'damage': 'Damage', 'horror': 'Horror', 'either': 'Damage or horror'}


def encounter_cards(encounter_set):
    """The cards of an encounter set's Encounter group in the classic tree"""
    return [card for card in encounter_set.cards if card.card_type in ('treachery', 'enemy')]


def split_encounter_cards(cards):
    """(enemies, treacheries, others), each in encounter set order"""
    enemies, treacheries, others = [], [], []
    for card in cards:
        if card.card_type == 'enemy':
            enemies.append(card)
        elif card.card_type == 'treachery':
            treacheries.append(card)
        else:
            others.append(card)
    return enemies, treacheries, others


def copies(card):
    try:
        return max(1, int(card.amount))
    except (TypeError, ValueError):
        return 1


def bucket(value):
    """The chart bucket of a stat value: a plain number 1 … 5 or 6+ (0 counts
    as 1), anything else that is set - X, ?, <dash>, a <per> value - is X.
    None for no value."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        number = int(text)
        return '6+' if number >= 6 else str(max(1, number))
    return 'X'


def plain_number(value):
    text = str(value).strip() if value is not None else ''
    return int(text) if text.isdigit() else None


def stat_summary(values):
    """{'buckets': {bucket: count}, 'median', 'mean'} over per-copy values;
    median/mean only count plain numbers (None when there are none)."""
    buckets = {b: 0 for b in BUCKETS}
    numbers = []
    for value in values:
        b = bucket(value)
        if b is None:
            continue
        buckets[b] += 1
        number = plain_number(value)
        if number is not None:
            numbers.append(number)
    return {
        'buckets': buckets,
        'median': median(numbers) if numbers else None,
        'mean': mean(numbers) if numbers else None,
    }


def enemy_stats(enemies, treacheries):
    health_n = health_x = 0
    combat, evade = [], []
    for card in enemies:
        count = copies(card)
        value, per = parse_per_value(card.front.get('health'))
        if value is not None:
            if per:
                health_x += value * count
            else:
                health_n += value * count
        combat += [card.front.get('attack')] * count
        evade += [card.front.get('evade')] * count
    enemy_count = sum(copies(c) for c in enemies)
    deck = enemy_count + sum(copies(c) for c in treacheries)
    return {
        'health': (health_n, health_x),
        'count': enemy_count,
        'deck': deck,
        'share': enemy_count / deck if deck else None,
        'combat': stat_summary(combat),
        'evade': stat_summary(evade),
    }


def skill_tests(text):
    """[(skill, value)] for every "Test <skill> (value)" in a card text"""
    tests = []
    for skill, value in _TEST_RE.findall(text or ''):
        skill = skill.lower()
        tests.append((SKILL_ALIASES.get(skill, skill), value))
    return tests


def harm_types(text):
    """Which of damage / horror / either (the player's choice) a card text
    deals: "take 2 horror", "take 1 damage or (1) horror". A choice doesn't
    also count as damage or horror."""
    text = text or ''
    kinds = set()
    if _EITHER_RE.search(text):
        kinds.add('either')
        text = _EITHER_RE.sub(' ', text)
    kinds |= {match.lower() for match in _HARM_RE.findall(text)}
    return kinds


def treachery_stats(treacheries):
    by_bucket = {skill: {b: 0 for b in BUCKETS} for skill in SKILLS}
    counts = {skill: 0 for skill in SKILLS}
    harm = {kind: 0 for kind in HARM_TYPES}  # copies dealing it (once per card)
    for card in treacheries:
        count = copies(card)
        text = card.front.get('text')
        for skill, value in skill_tests(text):
            counts[skill] += count
            by_bucket[skill][bucket(value) or 'X'] += count
        for kind in harm_types(text):
            harm[kind] += count
    total = sum(copies(c) for c in treacheries)
    return {'by_bucket': by_bucket, 'counts': counts, 'harm': harm, 'total': total}


def _format_stat(value):
    if value is None:
        return '–'
    return f'{value:g}' if isinstance(value, int) else f'{value:.1f}'.rstrip('0').rstrip('.')


class BarChartItem(QGraphicsItem):
    """Stacked bar chart over BUCKETS: series is [(color, {bucket: count})]"""

    LABEL_HEIGHT = 20
    VALUE_HEIGHT = 18

    def __init__(self, width, height, series):
        super().__init__()
        self.width = width
        self.height = height
        self.series = series

    def boundingRect(self):
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter, option, widget=None):
        totals = {b: sum(counts[b] for _, counts in self.series) for b in BUCKETS}
        peak = max(totals.values()) or 1
        slot = self.width / len(BUCKETS)
        bar_width = slot * 0.7
        base = self.height - self.LABEL_HEIGHT
        usable = base - self.VALUE_HEIGHT

        font = QFont()
        font.setPointSize(10)
        painter.setFont(font)

        painter.setPen(QPen(QColor(110, 110, 115), 1))
        painter.drawLine(0, base, self.width, base)

        for i, b in enumerate(BUCKETS):
            x = i * slot + (slot - bar_width) / 2
            y = base
            painter.setPen(Qt.NoPen)
            for color, counts in self.series:
                h = usable * counts[b] / peak
                if h:
                    painter.setBrush(QBrush(color))
                    painter.drawRect(QRectF(x, y - h, bar_width, h))
                    y -= h
            painter.setPen(QPen(DIM_TEXT_COLOR))
            painter.drawText(QRectF(i * slot, base + 2, slot, self.LABEL_HEIGHT - 2),
                             Qt.AlignHCenter | Qt.AlignTop, b)
            if totals[b]:
                painter.setPen(QPen(QColor(220, 220, 225)))
                painter.drawText(QRectF(i * slot, y - self.VALUE_HEIGHT, slot, self.VALUE_HEIGHT),
                                 Qt.AlignHCenter | Qt.AlignBottom, str(totals[b]))


class EncounterView(CardBoardView):
    """Enemies / treacheries (one item per copy) / other encounter cards"""

    def _build(self):
        enemies, treacheries, others = split_encounter_cards(encounter_cards(self.encounter_set))
        self.enemy_stats = enemy_stats(enemies, treacheries)
        self.treachery_stats = treachery_stats(treacheries)

        columns = [
            (tr('Enemies'), enemies, True, self._enemy_header),
            (tr('Treacheries'), treacheries, True, self._treachery_header),
            (tr('Other'), others, False, None),
        ]

        widths = [max([MIN_COLUMN_WIDTH] + [self._row_width(c) for c in cards]) if fanned else CARD_LONG
                  for _, cards, fanned, _ in columns]
        xs = [sum(widths[:i]) + i * COLUMN_GAP for i in range(len(columns))]

        # Headers and stats first: the cards start below the tallest
        bottoms = []
        for (title, cards, _, header), x, width in zip(columns, xs, widths):
            bottom = self.add_header(x, width, title)
            if header and cards:
                bottom = header(x, width, bottom + 4)
            bottoms.append(bottom)
        top = max(bottoms) + 32

        for (title, cards, fanned, _), x, width in zip(columns, xs, widths):
            y = top
            for card in cards:
                if fanned:
                    y = self._add_fanned(card, x, y)
                else:
                    item = self.add_card(card, 'front', 0, y, flippable=True)
                    item.setX(x + (width - item.width) / 2)
                    y += item.height + ROW_GAP

        self.fit_scene()

    @staticmethod
    def _row_width(card):
        width, _ = side_size(card.front)
        return width + (copies(card) - 1) * width * (1 - OVERLAP)

    def _add_fanned(self, card, x, y):
        """One item per copy, each overlapping the previous by OVERLAP"""
        height = 0
        for i in range(copies(card)):
            item = self.add_card(card, 'front', 0, y, z=i)
            item.setX(x + i * item.width * (1 - OVERLAP))
            height = item.height
        return y + height + ROW_GAP

    def _chart(self, x, width, y, title, series, summary=None):
        y = self.add_html(x, width, y, f'<b>{title}</b>', size=12)
        chart = BarChartItem(width, CHART_HEIGHT, series)
        chart.setPos(x, y)
        self.scene.addItem(chart)
        y += CHART_HEIGHT
        if summary is not None:
            text = (f"{tr('Median')} {_format_stat(summary['median'])} · "
                    f"{tr('Mean')} {_format_stat(summary['mean'])}")
            y = self.add_html(x, width, y, text, color=DIM_TEXT_COLOR, size=11)
        return y + 6

    def _enemy_header(self, x, width, y):
        stats = self.enemy_stats
        y = self.add_html(x, width, y, f"{tr('Total health')}: {amount_html(*stats['health'])}")
        if stats['share'] is not None:
            share = f"{stats['count']} / {stats['deck']} ({stats['share']:.0%})"
            y = self.add_html(x, width, y, f"{tr('Share of the encounter deck')}: {share}", size=12)
        y += 8
        y = self._chart(x, width, y, tr('Combat'),
                        [(SKILL_COLORS['combat'], stats['combat']['buckets'])], stats['combat'])
        y = self._chart(x, width, y, tr('Evade'),
                        [(SKILL_COLORS['agility'], stats['evade']['buckets'])], stats['evade'])
        return y

    def _treachery_header(self, x, width, y):
        stats = self.treachery_stats
        y = self._chart(x, width, y, tr('Skill tests'),
                        [(SKILL_COLORS[s], stats['by_bucket'][s]) for s in SKILLS])
        lines = []
        for skill in SKILLS:
            count = stats['counts'][skill]
            if not count:
                continue
            color = SKILL_COLORS[skill].name()
            share = count / stats['total'] if stats['total'] else 0
            lines.append(f'<span style="color:{color}">■</span> '
                         f'{tr(SKILL_NAMES[skill])}: {count} ({share:.0%})')
        if not lines:
            lines.append(tr('No skill tests found'))
        y = self.add_html(x, width, y, '<br>'.join(lines), size=12) + 8

        lines = []
        for kind in HARM_TYPES:
            count = stats['harm'][kind]
            share = count / stats['total'] if stats['total'] else 0
            lines.append(f'<span style="color:{HARM_COLORS[kind].name()}">■</span> '
                         f'{tr(HARM_NAMES[kind])}: {count} ({share:.0%})')
        y = self.add_html(x, width, y, f"<b>{tr('Deals')}</b>", size=12)
        return self.add_html(x, width, y, '<br>'.join(lines), size=12)


class EncounterViewWidget(CardBoardWidget):
    """Content-area widget for the encounter view"""

    def __init__(self, encounter_set, renderer, parent=None):
        super().__init__(EncounterView(encounter_set, renderer), parent)
        self.encounter_view = self.view
