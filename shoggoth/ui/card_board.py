"""
Card board - the shared base of the read-only "overview" views (story view,
encounter view): rendered cards laid out in columns on a zoomable, pannable
QGraphicsView, with headers and stats above each column.

  * Cards render on one background thread, so a view opens immediately with
    placeholders that fill in as each side finishes. Items showing the same
    card side (several copies of a card) share one render.
  * Flippable items turn over with F (the card under the mouse) / Shift+F
    (all of them), animated like the location view.
  * Double-clicking a card emits card_double_clicked(card).

Subclasses implement _build(), placing items with add_header()/add_card()/
add_html() and finishing with fit_scene().
"""
import threading
from io import BytesIO

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsScene, QGraphicsSimpleTextItem, QGraphicsTextItem, QGraphicsView,
    QVBoxLayout, QWidget,
)

from shoggoth.renderer import renderer_for_card
from shoggoth.ui.tag_buttons import _icon_font_family


# Scene size of a card side (vertical; horizontal cards swap the two)
CARD_SHORT = 250
CARD_LONG = 350
COLUMN_GAP = 80
CARD_GAP = 48      # between two cards in a column

# Render resolution, in render_card_side's width units (1500 = full size).
# Twice the on-screen size at 100% zoom, so zooming in stays legible.
RENDER_WIDTH = 750

TEXT_COLOR = QColor(220, 220, 225)
DIM_TEXT_COLOR = QColor(150, 150, 155)


def side_size(face):
    """(width, height) in scene units of a card side"""
    if face is not None and face.get('orientation') == 'horizontal':
        return CARD_LONG, CARD_SHORT
    return CARD_SHORT, CARD_LONG


def per_html():
    """The <per> icon as HTML, in the card icon font when it's available"""
    family = _icon_font_family()
    return f'<span style="font-family:\'{family}\'">p</span>' if family else '&lt;per&gt;'


def amount_html(n, x, unit=''):
    """"n + x<per> unit", or just "n unit" / "x<per> unit" when a part is 0"""
    parts = []
    if n or not x:
        parts.append(_number(n))
    if x:
        parts.append(f'{_number(x)}{per_html()}')
    text = ' + '.join(parts)
    return f'{text} {unit}' if unit else text


def _number(value):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value)


class BoardCardItem(QGraphicsItem):
    """One rendered card side. Flippable items swap to the other side."""

    def __init__(self, view, card, side, flippable=False):
        super().__init__()
        self.view = view
        self.card = card
        self.side = side  # 'front' or 'back'
        self.flippable = flippable
        self._flip_scale_x = 1.0
        self.width, self.height = side_size(self.face)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)

    @property
    def face(self):
        return self.card.front if self.side == 'front' else self.card.back

    def can_flip(self):
        other = self.card.back if self.side == 'front' else self.card.front
        return self.flippable and other is not None

    def swap_side(self):
        self.side = 'back' if self.side == 'front' else 'front'
        self.view.request_render(self.card, self.side)
        self.update()

    def boundingRect(self):
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter, option, widget=None):
        if self._flip_scale_x < 1.0:
            painter.save()
            painter.translate(self.width / 2, 0)
            painter.scale(self._flip_scale_x, 1.0)
            painter.translate(-self.width / 2, 0)

        pixmap = self.view.pixmap_for(self.card, self.side)
        rect = self.boundingRect()
        if pixmap is not None and not pixmap.isNull():
            # Fit the render into the slot, keeping its aspect ratio
            size = pixmap.size().scaled(int(rect.width()), int(rect.height()), Qt.KeepAspectRatio)
            target = QRectF(
                (rect.width() - size.width()) / 2, (rect.height() - size.height()) / 2,
                size.width(), size.height(),
            )
            painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))
        else:
            painter.setPen(QPen(QColor(90, 90, 95)))
            painter.setBrush(QBrush(QColor(60, 60, 66)))
            painter.drawRoundedRect(rect, 8, 8)
            painter.setPen(QPen(QColor(170, 170, 175)))
            painter.drawText(rect.adjusted(10, 10, -10, -10), Qt.AlignCenter | Qt.TextWordWrap,
                             self.card.name or '')

        if self._flip_scale_x < 1.0:
            painter.restore()

    def hoverEnterEvent(self, event):
        self.view._hovered_item = self
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self.view._hovered_item is self:
            self.view._hovered_item = None
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.view.card_double_clicked.emit(self.card)
        event.accept()


class _RenderSignals(QObject):
    rendered = Signal(object, str, bytes)  # card, side, PNG bytes


class CardBoardView(QGraphicsView):
    """Zoomable, pannable read-only layout of cards (see module docstring)"""

    card_double_clicked = Signal(object)

    def __init__(self, encounter_set, renderer, parent=None):
        super().__init__(parent)
        self.encounter_set = encounter_set
        self.renderer = renderer
        self._hovered_item = None
        self._fitted = False

        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QBrush(QColor(40, 40, 45)))
        self.setFocusPolicy(Qt.StrongFocus)

        # Background rendering: one worker drains a queue of (card, side)
        self._pixmaps = {}  # (card id, side) -> QPixmap
        self._items = {}    # (card id, side) -> items to repaint when it arrives
        self._signals = _RenderSignals()
        self._signals.rendered.connect(self._on_rendered)
        self._queue = []
        self._queued = set()
        self._queue_lock = threading.Lock()
        self._queue_event = threading.Event()
        self._stopped = False
        self._worker = threading.Thread(target=self._render_loop, daemon=True)

        # Flip animation state (same feel as the location view)
        self._flip_animations = {}
        self._flip_timer = QTimer(self)
        self._flip_timer.setInterval(15)
        self._flip_timer.timeout.connect(self._flip_step)

        self.card_items = []
        self.flippable_items = []
        self._build()
        self._worker.start()

    # --- Building blocks for _build() -------------------------------------------

    def _build(self):
        raise NotImplementedError

    def add_header(self, x, width, title, y=0):
        """A column title centered over [x, x + width]; returns its bottom"""
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        header = QGraphicsSimpleTextItem(title)
        header.setFont(font)
        header.setBrush(QBrush(TEXT_COLOR))
        header.setPos(x + (width - header.boundingRect().width()) / 2, y)
        self.scene.addItem(header)
        return y + header.boundingRect().height()

    def add_html(self, x, width, y, html, color=TEXT_COLOR, size=14, center=True):
        """A rich text label; returns its bottom"""
        font = QFont()
        font.setPointSize(size)
        label = QGraphicsTextItem()
        label.setFont(font)
        label.setDefaultTextColor(color)
        label.setHtml(html)
        if center:
            label.setPos(x + (width - label.boundingRect().width()) / 2, y)
        else:
            label.setTextWidth(width)
            label.setPos(x, y)
        self.scene.addItem(label)
        return y + label.boundingRect().height()

    def add_card(self, card, side, x, y, flippable=False, z=0):
        item = BoardCardItem(self, card, side, flippable=flippable)
        item.setPos(x, y)
        item.setZValue(z)
        self.scene.addItem(item)
        self.card_items.append(item)
        if flippable:
            self.flippable_items.append(item)
        self.request_render(card, side)
        return item

    def fit_scene(self):
        rect = self.scene.itemsBoundingRect()
        self.scene.setSceneRect(rect.adjusted(-COLUMN_GAP, -COLUMN_GAP / 2, COLUMN_GAP, COLUMN_GAP))

    # --- Initial zoom -------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._fitted:
            self._fitted = True
            QTimer.singleShot(0, self._fit_width)

    def _fit_width(self):
        """Start zoomed so all columns fit across, scrolled to the top"""
        rect = self.scene.sceneRect()
        viewport = self.viewport().width()
        if rect.width() <= 0 or viewport <= 0:
            return
        scale = min(1.0, viewport / rect.width())
        self.resetTransform()
        self.scale(scale, scale)
        self.centerOn(rect.center().x(), rect.top())
        self.verticalScrollBar().setValue(self.verticalScrollBar().minimum())

    # --- Rendering ------------------------------------------------------------

    def pixmap_for(self, card, side):
        return self._pixmaps.get((card.id, side))

    def request_render(self, card, side):
        """Queue a card side for rendering, unless it's done or queued"""
        key = (card.id, side)
        if key in self._pixmaps:
            return
        with self._queue_lock:
            if key in self._queued:
                return
            self._queued.add(key)
            self._queue.append((card, side))
        self._queue_event.set()

    def _render_loop(self):
        while not self._stopped:
            self._queue_event.wait()
            with self._queue_lock:
                if not self._queue:
                    self._queue_event.clear()
                    continue
                card, side = self._queue.pop(0)
            if self._stopped:
                return
            face = card.front if side == 'front' else card.back
            try:
                image = renderer_for_card(self.renderer, card).render_card_side(
                    card, face, include_bleed=False,
                    width=RENDER_WIDTH, height=int(RENDER_WIDTH * 1.4), bleed=36, rounded=True,
                )
                buffer = BytesIO()
                image.save(buffer, format='PNG', compress_level=1)
                data = buffer.getvalue()
            except Exception as e:
                print(f"Card board: error rendering {card.name} ({side}): {e}")
                data = b''
            if self._stopped:
                return
            try:
                self._signals.rendered.emit(card, side, data)
            except RuntimeError:
                return  # the view was deleted while rendering

    def _on_rendered(self, card, side, data):
        if self._stopped:
            return
        pixmap = QPixmap()
        if data:
            pixmap.loadFromData(data)
        self._pixmaps[(card.id, side)] = pixmap
        for item in self.card_items:
            if item.card.id == card.id and item.side == side:
                item.update()

    def stop(self):
        self._stopped = True
        self._queue_event.set()

    # --- Flipping -------------------------------------------------------------

    def flip_item(self, item):
        if not item.can_flip() or id(item) in self._flip_animations:
            return
        steps = 10
        shrink = [1.0 - i / steps for i in range(steps + 1)]
        grow = [i / steps for i in range(1, steps + 1)]
        self._flip_animations[id(item)] = {
            'item': item, 'steps': shrink + grow, 'midpoint': len(shrink), 'idx': 0,
        }
        if not self._flip_timer.isActive():
            self._flip_timer.start()

    def _flip_step(self):
        done = []
        for key, anim in self._flip_animations.items():
            item = anim['item']
            idx = anim['idx']
            if idx >= len(anim['steps']):
                item._flip_scale_x = 1.0
                item.update()
                done.append(key)
                continue
            item._flip_scale_x = anim['steps'][idx]
            if idx == anim['midpoint']:
                item.swap_side()
            anim['idx'] += 1
            item.update()
        for key in done:
            del self._flip_animations[key]
        if not self._flip_animations:
            self._flip_timer.stop()

    # --- Input ----------------------------------------------------------------

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F:
            if event.modifiers() & Qt.ShiftModifier:
                for item in self.flippable_items:
                    self.flip_item(item)
            elif self._hovered_item:
                self.flip_item(self._hovered_item)
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        self.setFocus()
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(factor, factor)
        else:
            self.scale(1 / factor, 1 / factor)


class CardBoardWidget(QWidget):
    """Content-area wrapper around a CardBoardView subclass"""

    card_selected = Signal(object)

    def __init__(self, view, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.view = view
        view.card_double_clicked.connect(self.card_selected.emit)
        layout.addWidget(view)

    def cleanup(self):
        self.view.stop()
