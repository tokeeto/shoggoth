"""
Story View - read through an encounter set's story cards at a glance.

Three columns: agendas and acts (each shown front then back, so the whole
deck reads top to bottom) and every other card of the set's Story group
(front only; F / Shift+F flips them, as in the location view). Zoom, pan,
rendering and double-click come from card_board.CardBoardView.

Scenarios with several agenda / act lines (1a/1b -> 2a/2b alongside
1c/1d -> 2c/2d, or a split like 3a / 3d / 3e) are shown by putting every
card with the same index number side by side in one row (see index_rows);
a lone card is centered in its column. How the lines actually connect is
scenario specific, so this is only a best effort. The doom / clue totals
still add up every card.

Under the Agenda and Act headers, a label totals the doom / clue thresholds
and colors them by how they compare with the standard 15 doom scenario (see
doom_rating / clue_rating).
"""
import re

from PySide6.QtGui import QColor

from shoggoth.export_helpers import parse_per_value
from shoggoth.i18n import tr
from shoggoth.ui.card_board import (
    CARD_GAP, CARD_LONG, COLUMN_GAP, CardBoardView, CardBoardWidget, amount_html, side_size,
)


COLUMN_WIDTH = CARD_LONG
SIDE_GAP = 8         # between the front and back of one act/agenda
PAIR_GAP = 24        # between act/agendas side by side in one row
HEADER_HEIGHT = 100  # column title + threshold total

# A <per> value counts as this many for the doom / clue ratings (3 players)
PER_AS = 3
STANDARD_DOOM = 15
RATING_COLORS = {
    'ok': QColor(235, 235, 240),
    'warn': QColor(240, 200, 60),
    'bad': QColor(235, 85, 70),
    None: QColor(150, 150, 155),  # nothing to rate against
}


def story_cards(encounter_set):
    """The cards of an encounter set's Story group in the classic tree:
    everything that is neither a location nor an encounter card."""
    return [card for card in encounter_set.cards
            if card.card_type not in ('location', 'treachery', 'enemy')]


def split_story_cards(cards):
    """(agendas, acts, others), each in encounter set order"""
    agendas, acts, others = [], [], []
    for card in cards:
        if card.card_type == 'agenda':
            agendas.append(card)
        elif card.card_type == 'act':
            acts.append(card)
        else:
            others.append(card)
    return agendas, acts, others


_INDEX_RE = re.compile(r'\s*(\d+)\s*([a-z]*)', re.IGNORECASE)


def index_key(card):
    """(number, letters) of the index stored on the card's front ("3d" ->
    (3, 'd')); number is None without a stored index. The defaults' "2a"
    placeholder doesn't count, or every unnumbered card would be "2"."""
    match = _INDEX_RE.match(str(card.front.data.get('index') or ''))
    if not match:
        return None, ''
    return int(match.group(1)), match.group(2).lower()


def index_rows(cards):
    """Rows of cards to show side by side: cards sharing an index number
    form one row, ordered by letter. Cards without an index get a row each,
    after the numbered ones."""
    keyed = sorted(((index_key(card), card) for card in cards),
                   key=lambda kc: (kc[0][0] is None, kc[0][0] or 0, kc[0][1]))
    rows = []
    previous = None
    for (number, _), card in keyed:
        if number is not None and number == previous:
            rows[-1].append(card)
        else:
            rows.append([card])
        previous = number
    return rows


def threshold_total(cards, field):
    """(n, x) for a doom/clue field over the cards' fronts: n sums the plain
    values, x the <per> ones. Missing or non-numeric values (<dash>, X) are
    left out."""
    n = x = 0
    for card in cards:
        value, per = parse_per_value(card.front.get(field))
        if value is None:
            continue
        if per:
            x += value
        else:
            n += value
    return n, x


def doom_rating(n, x):
    """Exactly 15 doom is standard, 16-18 a little long, anything else off"""
    total = n + PER_AS * x
    if total == STANDARD_DOOM:
        return 'ok'
    if STANDARD_DOOM < total <= 18:
        return 'warn'
    return 'bad'


def clue_rating(n, x, doom_n, doom_x):
    """Clues in <per> (a plain value counts as a third of one) against the
    total doom: 0.6-0.75 per doom is standard (15 doom = 9<per> clues), up to
    1.0 is tight, anything else off."""
    doom = doom_n + PER_AS * doom_x
    if doom <= 0:
        return None
    ratio = (x + n / PER_AS) / doom
    eps = 1e-9
    if 0.6 - eps <= ratio <= 0.75 + eps:
        return 'ok'
    if 0.75 < ratio <= 1.0 + eps:
        return 'warn'
    return 'bad'


def threshold_html(n, x, unit):
    """"n + x<per> doom", or just "n doom" / "x<per> doom" when a part is 0"""
    return amount_html(n, x, unit)


class StoryView(CardBoardView):
    """Agendas / acts (both sides) / other story cards (flippable)"""

    def _build(self):
        agendas, acts, others = split_story_cards(story_cards(self.encounter_set))

        doom = threshold_total(agendas, 'doom')
        clues = threshold_total(acts, 'clues')
        self.threshold_labels = {}
        if agendas:
            self.threshold_labels[0] = (threshold_html(*doom, tr('doom')), doom_rating(*doom))
        if acts:
            rating = clue_rating(*clues, *doom) if agendas else None
            self.threshold_labels[1] = (threshold_html(*clues, tr('clues')), rating)

        # Agendas / acts: rows of cards sharing an index number; others one per row
        columns = [
            (tr('Agenda'), index_rows(agendas), True),
            (tr('Act'), index_rows(acts), True),
            (tr('Other'), [[card] for card in others], False),
        ]
        x = 0
        for index, (title, rows, both_sides) in enumerate(columns):
            width = max([COLUMN_WIDTH] + [self._row_width(row) for row in rows])
            bottom = self.add_header(x, width, title)
            if index in self.threshold_labels:
                html, rating = self.threshold_labels[index]
                self.add_html(x, width, bottom + 2, html, color=RATING_COLORS[rating])

            y = HEADER_HEIGHT
            for row in rows:
                y = self._add_row(row, x, width, y, both_sides)
            x += width + COLUMN_GAP

        self.fit_scene()

    @staticmethod
    def _row_width(row):
        return sum(side_size(card.front)[0] for card in row) + PAIR_GAP * (len(row) - 1)

    def _add_row(self, row, x, width, y, both_sides):
        """Cards side by side, the row centered in the column; each card's back
        (for acts / agendas) right under its front. Returns the next row's y."""
        cx = x + (width - self._row_width(row)) / 2
        bottom = y
        for card in row:
            card_y = y
            card_width = side_size(card.front)[0]
            sides = ['front', 'back'] if both_sides and card.back is not None else ['front']
            for i, side in enumerate(sides):
                item = self.add_card(card, side, 0, card_y, flippable=not both_sides)
                item.setX(cx + (card_width - item.width) / 2)
                card_y += item.height + (SIDE_GAP if i < len(sides) - 1 else 0)
            bottom = max(bottom, card_y)
            cx += card_width + PAIR_GAP
        return bottom + CARD_GAP


class StoryViewWidget(CardBoardWidget):
    """Content-area widget for the story view"""

    def __init__(self, encounter_set, renderer, parent=None):
        super().__init__(StoryView(encounter_set, renderer), parent)
        self.story_view = self.view
