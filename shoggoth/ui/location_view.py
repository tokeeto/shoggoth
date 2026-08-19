"""
Location View - Visual editor for location connections in encounter sets
"""
from shoggoth.i18n import tr
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsPixmapItem,
    QGraphicsPathItem, QGraphicsEllipseItem, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QMenu, QCheckBox,
    QApplication, QDialog, QDialogButtonBox, QGridLayout,
    QScrollArea, QFrame, QTabBar, QInputDialog,
)
from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QSize, QTimer
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPainterPath, QPainterPathStroker,
    QPolygonF, QPixmap, QFont, QCursor, QIcon, QImage
)
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from shoggoth import files
from shoggoth.files import overlay_dir


class ConnectionArrow(QGraphicsPathItem):
    """Arrow representing a connection between two locations.

    A single arrow can represent either a one-way connection (arrowhead on
    the target end only) or a two-way connection (arrowhead on both ends),
    when `reverse_symbol` is set.
    """

    LINE_WIDTH = 4
    OUTLINE_WIDTH = 4
    LINE_COLOR = QColor(156, 0, 0)  # maroon
    OUTLINE_COLOR = QColor(255, 255, 255)
    HOVER_LINE_COLOR = QColor(200, 40, 40)
    ARROW_SIZE = 16

    def __init__(self, source_node, target_node, connection_symbol, reverse_symbol=None):
        super().__init__()
        self.source_node = source_node
        self.target_node = target_node
        self.connection_symbol = connection_symbol
        self.reverse_symbol = reverse_symbol
        self.hovered = False
        self._fill_path = QPainterPath()

        # The outline is drawn as a mitered (pointy-cornered) stroke around
        # the outside of the filled arrow shape, not a separate rounded pen
        # along the centerline - that's what keeps the shaft and head as one
        # continuous piece instead of two overlapping strokes.
        self.outline_pen = QPen(self.OUTLINE_COLOR, self.OUTLINE_WIDTH * 2)
        self.outline_pen.setJoinStyle(Qt.MiterJoin)
        self.outline_pen.setMiterLimit(5)

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setZValue(1)  # Draw on top of location cards

        self.update_path()

    @property
    def bidirectional(self):
        return self.reverse_symbol is not None

    def _rect_edge_intersection(self, center, rect_width, rect_height, direction_x, direction_y):
        """Calculate where a ray from center intersects the rectangle edge"""
        # Half dimensions
        hw = rect_width / 2
        hh = rect_height / 2

        # Avoid division by zero
        if abs(direction_x) < 0.0001 and abs(direction_y) < 0.0001:
            return center

        # Calculate intersection with each edge and find the closest one
        # For a ray from center in direction (dx, dy), find t where it hits the edge
        t_values = []

        if abs(direction_x) > 0.0001:
            # Right edge (x = hw)
            t = hw / direction_x
            if t > 0:
                y_at_t = direction_y * t
                if abs(y_at_t) <= hh:
                    t_values.append(t)
            # Left edge (x = -hw)
            t = -hw / direction_x
            if t > 0:
                y_at_t = direction_y * t
                if abs(y_at_t) <= hh:
                    t_values.append(t)

        if abs(direction_y) > 0.0001:
            # Bottom edge (y = hh)
            t = hh / direction_y
            if t > 0:
                x_at_t = direction_x * t
                if abs(x_at_t) <= hw:
                    t_values.append(t)
            # Top edge (y = -hh)
            t = -hh / direction_y
            if t > 0:
                x_at_t = direction_x * t
                if abs(x_at_t) <= hw:
                    t_values.append(t)

        if not t_values:
            return center

        t = min(t_values)
        return QPointF(center.x() + direction_x * t, center.y() + direction_y * t)

    def update_path(self):
        """Update the arrow's filled shape based on node positions.

        The shaft and arrowhead(s) are traced as a single simple polygon in
        one pass, rather than built as separate shaft/arrowhead QPainterPaths
        combined with `united()`. That boolean union can, at certain angles,
        leave a stray internal edge where the thin shaft meets the much wider
        arrowhead base - invisible under the fill, but the outline pass still
        strokes it, producing a small rectangular white glitch right at that
        junction. Tracing one outline by hand sidesteps the boolean clip
        entirely so there's nothing left to mis-merge.
        """
        if not self.source_node or not self.target_node:
            return

        # Get center points of nodes
        source_rect = self.source_node.boundingRect()
        target_rect = self.target_node.boundingRect()

        source_center = self.source_node.scenePos() + source_rect.center()
        target_center = self.target_node.scenePos() + target_rect.center()

        # Calculate direction
        dx = target_center.x() - source_center.x()
        dy = target_center.y() - source_center.y()
        length = (dx * dx + dy * dy) ** 0.5

        if length == 0:
            return

        # Normalize direction
        dir_x = dx / length
        dir_y = dy / length

        # Calculate edge intersections for proper arrow endpoints
        start = self._rect_edge_intersection(
            source_center, source_rect.width(), source_rect.height(), dir_x, dir_y
        )
        end = self._rect_edge_intersection(
            target_center, target_rect.width(), target_rect.height(), -dir_x, -dir_y
        )

        arrow_size = self.ARROW_SIZE
        hw = self.LINE_WIDTH / 2
        half_width = arrow_size * 0.55
        perp_x, perp_y = -dir_y, dir_x

        # "Shoulder" = where the shaft's edge steps out to the arrowhead's
        # (wider) back edge, at each end that has an arrowhead.
        end_shoulder = QPointF(end.x() - dir_x * arrow_size, end.y() - dir_y * arrow_size)

        # Trace the outline once: out along the +perp side from the end tip
        # to the start end, then back along the -perp side to close the loop.
        points = [
            end,
            QPointF(end_shoulder.x() + perp_x * half_width, end_shoulder.y() + perp_y * half_width),
            QPointF(end_shoulder.x() + perp_x * hw, end_shoulder.y() + perp_y * hw),
        ]
        if self.bidirectional:
            start_shoulder = QPointF(start.x() + dir_x * arrow_size, start.y() + dir_y * arrow_size)
            points += [
                QPointF(start_shoulder.x() + perp_x * hw, start_shoulder.y() + perp_y * hw),
                QPointF(start_shoulder.x() + perp_x * half_width, start_shoulder.y() + perp_y * half_width),
                start,
                QPointF(start_shoulder.x() - perp_x * half_width, start_shoulder.y() - perp_y * half_width),
                QPointF(start_shoulder.x() - perp_x * hw, start_shoulder.y() - perp_y * hw),
            ]
        else:
            points += [
                QPointF(start.x() + perp_x * hw, start.y() + perp_y * hw),
                QPointF(start.x() - perp_x * hw, start.y() - perp_y * hw),
            ]
        points += [
            QPointF(end_shoulder.x() - perp_x * hw, end_shoulder.y() - perp_y * hw),
            QPointF(end_shoulder.x() - perp_x * half_width, end_shoulder.y() - perp_y * half_width),
        ]

        fill_path = QPainterPath()
        fill_path.addPolygon(QPolygonF(points))
        fill_path.closeSubpath()

        self._fill_path = fill_path
        self.setPath(fill_path)
        self.prepareGeometryChange()

    def boundingRect(self):
        margin = self.OUTLINE_WIDTH + 1
        return self._fill_path.boundingRect().adjusted(-margin, -margin, margin, margin)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(self.OUTLINE_WIDTH * 2)
        stroker.setJoinStyle(Qt.MiterJoin)
        outline = stroker.createStroke(self._fill_path)
        return self._fill_path.united(outline)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)

        # White outline, stroked around the outside of the filled shape so
        # the shaft and arrowhead(s) share one continuous silhouette.
        painter.setPen(self.outline_pen)
        painter.setBrush(QBrush(self.OUTLINE_COLOR))
        painter.drawPath(self._fill_path)

        # Maroon (or hover red) fill on top, same shape, no border.
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(self.HOVER_LINE_COLOR if self.hovered else self.LINE_COLOR))
        painter.drawPath(self._fill_path)

    def hoverEnterEvent(self, event):
        self.hovered = True
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.hovered = False
        self.unsetCursor()
        self.update()
        super().hoverLeaveEvent(event)


class LocationNode(QGraphicsItem):
    """Node representing a location card in the view"""

    # Card thumbnail size
    CARD_WIDTH = 120
    CARD_HEIGHT = 168

    # Icon mode size
    ICON_SIZE = 60

    def __init__(self, card, face, face_side, renderer, view):
        super().__init__()
        self.card = card
        self.face = face
        self.face_side = face_side  # 'front' or 'back'
        self.renderer = renderer
        self.view = view
        self.thumbnail = None
        self._icon_mode = False
        self._connection_icon = None
        self._flip_scale_x = 1.0
        self.hidden = False  # marked hidden by the user (see LocationView hide mode)
        self.default_pos = QPointF(0, 0)  # grid fallback position, set in LocationView._build_view

        # Stable key for this node
        self.node_key = f"{card.id}_{face_side}"

        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        # For connection dragging
        self.drag_start_pos = None

        # Generate thumbnail and load connection icon
        self._generate_thumbnail()
        self._load_connection_icon()

    def _generate_thumbnail(self):
        """Generate a thumbnail of the location card"""
        try:
            image = self.renderer.render_card_side(self.card, self.face, include_bleed=False)
            image = image.resize((self.CARD_WIDTH, self.CARD_HEIGHT))

            # Convert to QPixmap
            buffer = BytesIO()
            image.save(buffer, format='PNG')
            buffer.seek(0)

            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue())
            self.thumbnail = pixmap
        except Exception as e:
            print(f"Error generating thumbnail: {e}")
            self.thumbnail = None

    def _load_connection_icon(self):
        """Load the connection symbol icon"""
        connection = self.face.get('connection')
        if connection:
            icon_path = overlay_dir / 'svg' / f"connection_{connection}.svg"
            if icon_path.exists():
                self._connection_icon = QPixmap(str(icon_path))

    @property
    def icon_mode(self):
        return self._icon_mode

    @icon_mode.setter
    def icon_mode(self, value):
        if self._icon_mode != value:
            self.prepareGeometryChange()
            self._icon_mode = value
            self.update()

    def boundingRect(self):
        if self._icon_mode:
            return QRectF(0, 0, self.ICON_SIZE, self.ICON_SIZE)
        return QRectF(0, 0, self.CARD_WIDTH, self.CARD_HEIGHT)

    def can_flip(self):
        other = self.card.back if self.face_side == 'front' else self.card.front
        return other is not None

    def _swap_face(self):
        """Swap face/face_side and refresh visuals, without rebuilding arrows or persisting"""
        if self.face_side == 'front':
            self.face = self.card.back
            self.face_side = 'back'
        else:
            self.face = self.card.front
            self.face_side = 'front'
        self._generate_thumbnail()
        self._load_connection_icon()

    def _do_flip(self):
        """Swap to the opposite card face, rebuild connections, and persist the flip"""
        self._swap_face()
        self.view._build_arrows()
        self.view.save_node_position(self)

    def hoverEnterEvent(self, event):
        self.view._hovered_node = self
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self.view._hovered_node is self:
            self.view._hovered_node = None
        super().hoverLeaveEvent(event)

    def paint(self, painter, option, widget):
        if self._flip_scale_x < 1.0:
            cx = (self.ICON_SIZE if self._icon_mode else self.CARD_WIDTH) / 2
            painter.save()
            painter.translate(cx, 0)
            painter.scale(self._flip_scale_x, 1.0)
            painter.translate(-cx, 0)

        if self._icon_mode:
            self._paint_icon_mode(painter)
        else:
            self._paint_card_mode(painter)

        if self.hidden:
            self._paint_hidden_overlay(painter)

        if self._flip_scale_x < 1.0:
            painter.restore()

    def _paint_hidden_overlay(self, painter):
        """Dim the node and draw a badge to mark it as hidden (shown only in 'show' mode)"""
        rect = self.boundingRect()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(20, 20, 20, 140)))
        painter.drawRect(rect)

        badge_size = 22
        bx = rect.width() - badge_size - 4
        by = 4
        painter.setPen(QPen(QColor(0, 0, 0)))
        painter.setBrush(QBrush(QColor(220, 60, 60, 235)))
        painter.drawEllipse(QRectF(bx, by, badge_size, badge_size))

        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor(255, 255, 255)))
        painter.drawText(QRectF(bx, by, badge_size, badge_size), Qt.AlignCenter, "H")

    def _paint_card_mode(self, painter):
        """Paint in card thumbnail mode"""
        # Draw thumbnail or placeholder
        if self.thumbnail:
            painter.drawPixmap(0, 0, self.thumbnail)
        else:
            painter.setBrush(QBrush(QColor(200, 200, 200)))
            painter.drawRect(0, 0, self.CARD_WIDTH, self.CARD_HEIGHT)

        # Draw selection highlight
        if self.isSelected():
            painter.setPen(QPen(QColor(0, 120, 255), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(0, 0, self.CARD_WIDTH, self.CARD_HEIGHT)

    def _paint_icon_mode(self, painter):
        """Paint in icon mode - just show connection symbol"""
        # Draw circular background
        painter.setPen(QPen(QColor(80, 80, 80), 2))
        painter.setBrush(QBrush(QColor(240, 240, 230)))
        painter.drawEllipse(2, 2, self.ICON_SIZE - 4, self.ICON_SIZE - 4)

        # Draw connection icon or text
        if self._connection_icon:
            # Scale and center the icon
            icon_size = self.ICON_SIZE - 12
            scaled = self._connection_icon.scaled(icon_size, icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            x = (self.ICON_SIZE - scaled.width()) // 2
            y = (self.ICON_SIZE - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            # Draw text fallback
            connection = self.face.get('connection', '?')
            font = QFont()
            font.setPointSize(14)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.drawText(QRectF(0, 0, self.ICON_SIZE, self.ICON_SIZE), Qt.AlignCenter, connection[:3])

        # Draw selection highlight
        if self.isSelected():
            painter.setPen(QPen(QColor(0, 120, 255), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(2, 2, self.ICON_SIZE - 4, self.ICON_SIZE - 4)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.view.snap_enabled:
            return QPointF(
                round(value.x() / SNAP_STEP_X) * SNAP_STEP_X,
                round(value.y() / SNAP_STEP_Y) * SNAP_STEP_Y,
            )
        if change == QGraphicsItem.ItemPositionHasChanged:
            # Update all connected arrows
            self.view.update_arrows()
            # Save position
            self.view.save_node_position(self)
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        """Double-click to edit the card"""
        self.view.card_double_clicked.emit(self.card)
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.drag_start_pos = event.scenePos()
            self.view.start_connection_drag(self, event.scenePos())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.RightButton and self.drag_start_pos:
            self.view.end_connection_drag(event.scenePos())
            self.drag_start_pos = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)


# Invisible global snap grid: ~3x5 points per card footprint, in scene units.
SNAP_STEP_X = LocationNode.CARD_WIDTH / 3
SNAP_STEP_Y = LocationNode.CARD_HEIGHT / 5


class ConnectionDragLine(QGraphicsPathItem):
    """Temporary line shown while dragging to create a connection"""

    def __init__(self):
        super().__init__()
        pen = QPen(QColor(100, 150, 255), 2, Qt.DashLine)
        self.setPen(pen)
        self.setZValue(100)
        self.start_pos = QPointF()

    def update_line(self, start, end):
        self.start_pos = start
        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        self.setPath(path)


class PickConnectionSymbolDialog(QDialog):
    """Dialog for picking a connection symbol to assign to a location"""

    def __init__(self, card_name, parent=None):
        super().__init__(parent)
        from shoggoth.ui.editor_widgets import IconComboBox

        self.chosen_symbol = None
        self.setWindowTitle(tr("DLG_SET_CONNECTION_SYMBOL"))

        layout = QVBoxLayout(self)

        msg = QLabel(tr("MSG_PICK_SYMBOL_FOR").format(card_name=card_name))
        msg.setWordWrap(True)
        layout.addWidget(msg)

        # Grid of icon buttons
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(4)

        symbols = [s for s in IconComboBox.CONNECTION_SYMBOLS if s != 'None']
        cols = 8
        for i, symbol in enumerate(symbols):
            btn = QPushButton()
            icon_path = overlay_dir / 'svg' / f"connection_{symbol}.svg"
            if icon_path.exists():
                btn.setIcon(QIcon(str(icon_path)))
                btn.setIconSize(QSize(32, 32))
            else:
                btn.setText(symbol[:3])
            btn.setFixedSize(48, 48)
            btn.setToolTip(symbol)
            btn.clicked.connect(lambda checked, s=symbol: self._pick(s))
            grid.addWidget(btn, i // cols, i % cols)

        layout.addWidget(grid_widget)

        btn_box = QDialogButtonBox(QDialogButtonBox.Cancel)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _pick(self, symbol):
        self.chosen_symbol = symbol
        self.accept()


class LocationView(QGraphicsView):
    """Main view for editing location connections"""

    # Signals
    card_double_clicked = Signal(object)  # Emits card when double-clicked
    connections_changed = Signal(list)  # Emitted when connections are modified; carries list of affected cards
    hidden_locations_changed = Signal()  # Emitted when a node is hidden/unhidden, or nodes are (re)built
    hide_mode_changed = Signal(bool)  # Emitted when hide mode is toggled
    layouts_changed = Signal()  # Emitted when layouts are added/removed/renamed/switched

    def __init__(self, encounter_set, renderer, parent=None):
        super().__init__(parent)
        self.encounter_set = encounter_set
        self.renderer = renderer

        # Setup scene
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        # View settings
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setBackgroundBrush(QBrush(QColor(40, 40, 45)))

        # Storage
        self.location_nodes = {}  # card.id -> LocationNode
        self.arrows = []  # List of ConnectionArrow
        self.connection_drag_line = None
        self.drag_source_node = None
        self._hovered_node = None
        self._load_layouts()

        # Flip animation state
        self._flip_animations = {}
        self._flip_timer = QTimer(self)
        self._flip_timer.setInterval(15)
        self._flip_timer.timeout.connect(self._flip_step)

        self.setFocusPolicy(Qt.StrongFocus)

        # Build the view
        self._build_view()

    def _build_view(self):
        """Build the location nodes and connections"""
        self.scene.clear()
        self.location_nodes.clear()
        self.arrows.clear()

        # Find all location cards using the same grouping logic as the tree view
        locations = []
        for card in self.encounter_set.cards:
            if card.grouping == 'location':
                locations.append((card, card.front, 'front'))

        # Load saved positions from the active layout
        saved_positions = self._get_saved_positions()

        # Create nodes with grid layout (default) or saved positions
        cols = max(3, int(len(locations) ** 0.5) + 1)
        spacing_x = LocationNode.CARD_WIDTH + 80
        spacing_y = LocationNode.CARD_HEIGHT + 60

        for i, (card, face, face_side) in enumerate(locations):
            node = LocationNode(card, face, face_side, self.renderer, self)

            # Default grid position, used whenever a layout has no saved entry
            col = i % cols
            row = i // cols
            node.default_pos = QPointF(col * spacing_x, row * spacing_y)

            node_key = f"{card.id}_{face_side}"
            if node_key in saved_positions:
                pos = saved_positions[node_key]
                # Set hidden/flipped before setPos: setPos can trigger itemChange ->
                # save_node_position (ItemSendsGeometryChanges is already set),
                # which would otherwise persist the wrong (default) hidden/flipped value.
                node.hidden = bool(pos.get('hidden', False))
                if pos.get('flipped', False) and node.can_flip():
                    node._swap_face()
                node.setPos(pos['x'], pos['y'])
            else:
                node.setPos(node.default_pos)

            self.scene.addItem(node)
            self.location_nodes[node_key] = node

        # Create connection arrows
        self._build_arrows()

        # Fit view to content
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-50, -50, 50, 50))

        self.hidden_locations_changed.emit()

    def _build_arrows(self):
        """Build arrows based on connection data.

        When a connection exists in both directions between the same pair of
        nodes, it is collapsed into a single two-way arrow rather than two
        overlapping one-way arrows.
        """
        # Remove existing arrows
        for arrow in self.arrows:
            self.scene.removeItem(arrow)
        self.arrows.clear()

        # Build connection symbol -> nodes mapping
        # Only include nodes that have a connection symbol (can be traveled to)
        symbol_to_nodes = {}
        for key, node in self.location_nodes.items():
            connection = node.face.get('connection')
            # Skip nodes without a connection symbol - they cannot be traveled to
            if connection and connection != 'None':
                if connection not in symbol_to_nodes:
                    symbol_to_nodes[connection] = []
                symbol_to_nodes[connection].append(node)

        # Build directed edges: (source_key, target_key) -> symbol matched
        # (the target's own connection symbol, listed in source's connections)
        directed = {}
        for key, source_node in self.location_nodes.items():
            connections = source_node.face.get('connections', []) or []
            for symbol in connections:
                for target_node in symbol_to_nodes.get(symbol, []):
                    if target_node is not source_node:
                        directed[(key, target_node.node_key)] = symbol

        # Collapse reciprocal pairs into a single two-way arrow
        seen_pairs = set()
        for (src_key, tgt_key), symbol in directed.items():
            pair = frozenset((src_key, tgt_key))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            source_node = self.location_nodes[src_key]
            target_node = self.location_nodes[tgt_key]
            reverse_symbol = directed.get((tgt_key, src_key))

            arrow = ConnectionArrow(source_node, target_node, symbol, reverse_symbol)
            self.scene.addItem(arrow)
            self.arrows.append(arrow)

        self._apply_visibility()

    def update_arrows(self):
        """Update all arrow positions"""
        for arrow in self.arrows:
            arrow.update_path()

    def _apply_visibility(self):
        """Show/hide nodes and arrows according to hide mode, show_arrows, and each node's hidden flag"""
        for node in self.location_nodes.values():
            node.setVisible(not (self.hide_mode and node.hidden))
        show_arrows = self.show_arrows
        for arrow in self.arrows:
            arrow.setVisible(show_arrows and not (
                self.hide_mode and (arrow.source_node.hidden or arrow.target_node.hidden)
            ))

    def get_hidden_nodes(self):
        """Return the list of nodes currently marked hidden (regardless of hide mode)"""
        return [node for node in self.location_nodes.values() if node.hidden]

    def toggle_hide_mode(self):
        """Swap between 'show' (hidden locations dimmed but visible) and 'hide' modes"""
        self.hide_mode = not self.hide_mode
        self._apply_visibility()
        self.hide_mode_changed.emit(self.hide_mode)

    def set_node_hidden(self, node, hidden):
        """Mark a location node hidden/unhidden and persist it"""
        if node.hidden == hidden:
            return
        node.hidden = hidden
        self.save_node_position(node)
        node.update()
        self._apply_visibility()
        self.hidden_locations_changed.emit()

    def toggle_node_hidden(self, node):
        self.set_node_hidden(node, not node.hidden)

    def start_connection_drag(self, source_node, pos):
        """Start dragging to create a new connection"""
        self.drag_source_node = source_node
        self.connection_drag_line = ConnectionDragLine()
        self.connection_drag_line.update_line(
            source_node.scenePos() + source_node.boundingRect().center(),
            pos
        )
        self.scene.addItem(self.connection_drag_line)

    def end_connection_drag(self, pos):
        """End connection drag - check if over a valid target"""
        if self.connection_drag_line:
            self.scene.removeItem(self.connection_drag_line)
            self.connection_drag_line = None

        if not self.drag_source_node:
            return

        # Find target node under cursor
        target_node = None
        for item in self.scene.items(pos):
            if isinstance(item, LocationNode) and item != self.drag_source_node and item.isVisible():
                target_node = item
                break

        if target_node:
            self._add_connection(self.drag_source_node, target_node)

        self.drag_source_node = None

    def _refresh_node_thumbnail(self, node):
        """Regenerate the thumbnail for a node and repaint it"""
        node._generate_thumbnail()
        node.update()

    def _add_connection(self, source_node, target_node):
        """Add a connection from source to target"""
        target_symbol = target_node.face.get('connection')
        affected_cards = [source_node.card]

        if not target_symbol or target_symbol == 'None':
            # Target has no connection symbol — ask the user to assign one
            dlg = PickConnectionSymbolDialog(target_node.card.name, self)
            if dlg.exec_() != QDialog.Accepted or not dlg.chosen_symbol:
                return
            target_symbol = dlg.chosen_symbol
            target_node.face.set('connection', target_symbol)
            target_node._load_connection_icon()
            self._refresh_node_thumbnail(target_node)
            affected_cards.append(target_node.card)

        # Get current connections
        connections = source_node.face.get('connections', []) or []
        connections = list(connections)  # Make a copy

        # Add the symbol if not already present
        if target_symbol not in connections:
            connections.append(target_symbol)
            source_node.face.set('connections', connections)
            self._refresh_node_thumbnail(source_node)
            self._build_arrows()
            self.connections_changed.emit(affected_cards)

    def _remove_connection_symbol(self, node, symbol, affected_cards):
        """Remove a single symbol from a node's connections list, if present"""
        connections = node.face.get('connections', []) or []
        connections = list(connections)

        if symbol in connections:
            connections.remove(symbol)
            node.face.set('connections', connections if connections else None)
            self._refresh_node_thumbnail(node)
            if node.card not in affected_cards:
                affected_cards.append(node.card)

    def remove_connection(self, arrow):
        """Remove a connection arrow.

        For a two-way arrow this removes the connection in both directions —
        the user can redraw one or both directions again if they want to.
        """
        affected_cards = []
        self._remove_connection_symbol(arrow.source_node, arrow.connection_symbol, affected_cards)
        if arrow.bidirectional:
            self._remove_connection_symbol(arrow.target_node, arrow.reverse_symbol, affected_cards)

        if affected_cards:
            self._build_arrows()
            self.connections_changed.emit(affected_cards)

    def flip_node(self, node):
        """Start a flip animation for a node"""
        if not node.can_flip() or node.node_key in self._flip_animations:
            return
        steps = 10
        shrink = [1.0 - i / steps for i in range(steps + 1)]
        grow = [i / steps for i in range(1, steps + 1)]
        self._flip_animations[node.node_key] = {
            'node': node,
            'steps': shrink + grow,
            'midpoint': len(shrink),
            'idx': 0,
            'swapped': False,
        }
        if not self._flip_timer.isActive():
            self._flip_timer.start()

    def _flip_step(self):
        done = []
        for key, anim in self._flip_animations.items():
            node = anim['node']
            idx = anim['idx']
            if idx >= len(anim['steps']):
                node._flip_scale_x = 1.0
                node.update()
                done.append(key)
                continue
            node._flip_scale_x = anim['steps'][idx]
            if idx == anim['midpoint'] and not anim['swapped']:
                anim['swapped'] = True
                node._do_flip()
            anim['idx'] += 1
            node.update()
        for key in done:
            del self._flip_animations[key]
        if not self._flip_animations:
            self._flip_timer.stop()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F:
            if event.modifiers() & Qt.ShiftModifier:
                for node in self.location_nodes.values():
                    self.flip_node(node)
            elif self._hovered_node:
                self.flip_node(self._hovered_node)
            event.accept()
            return
        if event.key() == Qt.Key_H:
            if event.modifiers() & Qt.ShiftModifier:
                self.toggle_hide_mode()
            elif self._hovered_node:
                self.toggle_node_hidden(self._hovered_node)
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle mouse move for connection dragging"""
        if self.connection_drag_line and self.drag_source_node:
            scene_pos = self.mapToScene(event.pos())
            self.connection_drag_line.update_line(
                self.drag_source_node.scenePos() + self.drag_source_node.boundingRect().center(),
                scene_pos
            )
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Handle mouse release"""
        if event.button() == Qt.RightButton and self.drag_source_node:
            self.end_connection_drag(self.mapToScene(event.pos()))
        super().mouseReleaseEvent(event)

    def mousePressEvent(self, event):
        """Handle clicks on arrows"""
        self.setFocus()
        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            items = self.scene.items(scene_pos)

            for item in items:
                if isinstance(item, ConnectionArrow) and item.isVisible():
                    # Show context menu for arrow
                    self._show_arrow_context_menu(item, event.globalPos())
                    return

        super().mousePressEvent(event)

    def _show_arrow_context_menu(self, arrow, global_pos):
        """Show context menu for connection arrow"""
        menu = QMenu(self)
        remove_action = menu.addAction(tr("CTX_REMOVE_CONNECTION"))
        action = menu.exec_(global_pos)

        if action == remove_action:
            self.remove_connection(arrow)

    def wheelEvent(self, event):
        """Handle zoom with mouse wheel"""
        factor = 1.15
        if event.angleDelta().y() > 0:
            self.scale(factor, factor)
        else:
            self.scale(1 / factor, 1 / factor)

    # --- Layout persistence -------------------------------------------------

    def _load_layouts(self):
        """Load (migrating if necessary) the list of layouts from encounter set meta"""
        meta = self.encounter_set.data.setdefault('meta', {})

        if 'location_layouts' not in meta:
            old_nodes = meta.pop('location_graph', {})
            old_hide_mode = meta.pop('location_hide_mode', False)
            layout_id = str(uuid4())
            meta['location_layouts'] = [{
                'id': layout_id,
                'name': tr('LABEL_LAYOUT_NAME').format(n=1),
                'show_arrows': True,
                'snap_enabled': False,
                'hide_mode': old_hide_mode,
                'nodes': old_nodes,
            }]
            meta['location_active_layout'] = layout_id
            self.encounter_set.dirty = True

        self.layouts = meta['location_layouts']
        self.active_layout_id = meta.get('location_active_layout')
        if not any(l['id'] == self.active_layout_id for l in self.layouts):
            self.active_layout_id = self.layouts[0]['id']
            meta['location_active_layout'] = self.active_layout_id

    @property
    def active_layout(self):
        for layout in self.layouts:
            if layout['id'] == self.active_layout_id:
                return layout
        # Stale id (shouldn't normally happen) - repair and fall back
        self.active_layout_id = self.layouts[0]['id']
        self.encounter_set.data['meta']['location_active_layout'] = self.active_layout_id
        return self.layouts[0]

    @property
    def hide_mode(self):
        return bool(self.active_layout.get('hide_mode', False))

    @hide_mode.setter
    def hide_mode(self, value):
        self.active_layout['hide_mode'] = bool(value)
        self.encounter_set.dirty = True

    @property
    def snap_enabled(self):
        return bool(self.active_layout.get('snap_enabled', False))

    @snap_enabled.setter
    def snap_enabled(self, value):
        self.active_layout['snap_enabled'] = bool(value)
        self.encounter_set.dirty = True

    @property
    def show_arrows(self):
        return bool(self.active_layout.get('show_arrows', True))

    @show_arrows.setter
    def show_arrows(self, value):
        self.active_layout['show_arrows'] = bool(value)
        self.encounter_set.dirty = True
        self._apply_visibility()

    def _get_saved_positions(self):
        """Get saved node positions from the active layout"""
        return self.active_layout.get('nodes', {})

    def save_node_position(self, node):
        """Save a single node's position, hidden state, and flip state into the active layout"""
        nodes = self.active_layout.setdefault('nodes', {})

        pos = node.scenePos()
        nodes[node.node_key] = {
            'x': pos.x(),
            'y': pos.y(),
            'hidden': node.hidden,
            'flipped': node.face_side != 'front',
        }

        self.encounter_set.dirty = True

    def save_all_positions(self):
        """Save all node positions"""
        for node in self.location_nodes.values():
            self.save_node_position(node)

    def switch_layout(self, layout_id):
        """Switch the active layout, repositioning existing nodes (no rebuild)"""
        if layout_id == self.active_layout_id:
            return
        if not any(l['id'] == layout_id for l in self.layouts):
            return

        self.active_layout_id = layout_id
        self.encounter_set.data['meta']['location_active_layout'] = layout_id
        self.encounter_set.dirty = True

        saved_positions = self._get_saved_positions()
        for node in self.location_nodes.values():
            entry = saved_positions.get(node.node_key)
            if entry:
                # hidden/flipped before setPos - see comment in _build_view
                node.hidden = bool(entry.get('hidden', False))
                if entry.get('flipped', False) != (node.face_side != 'front') and node.can_flip():
                    node._swap_face()
                node.setPos(entry['x'], entry['y'])
            else:
                node.hidden = False
                if node.face_side != 'front' and node.can_flip():
                    node._swap_face()
                node.setPos(node.default_pos)
            node.update()

        # Rebuild (not just reposition) arrows: flip state may have changed
        # each node's connection data.
        self._build_arrows()
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-50, -50, 50, 50))
        self.hidden_locations_changed.emit()
        self.layouts_changed.emit()

    def add_layout(self, name=None):
        """Create a new, empty layout and switch to it"""
        layout_id = str(uuid4())
        self.layouts.append({
            'id': layout_id,
            'name': name or tr('LABEL_LAYOUT_NAME').format(n=len(self.layouts) + 1),
            'show_arrows': True,
            'snap_enabled': False,
            'hide_mode': False,
            'nodes': {},
        })
        self.encounter_set.dirty = True
        self.switch_layout(layout_id)

    def remove_layout(self, layout_id):
        """Remove a layout (refusing to remove the last remaining one)"""
        if len(self.layouts) <= 1:
            return
        index = next((i for i, l in enumerate(self.layouts) if l['id'] == layout_id), None)
        if index is None:
            return
        was_active = layout_id == self.active_layout_id
        del self.layouts[index]
        self.encounter_set.dirty = True
        if was_active:
            self.switch_layout(self.layouts[0]['id'])
        else:
            self.layouts_changed.emit()

    def rename_layout(self, layout_id, name):
        """Rename a layout"""
        for layout in self.layouts:
            if layout['id'] == layout_id:
                layout['name'] = name
                self.encounter_set.dirty = True
                self.layouts_changed.emit()
                return

    def init_simulation(self):
        """Initialize or reset simulation velocities"""
        self._sim_velocities = {node.node_key: QPointF(0, 0) for node in self.location_nodes.values()}

    def simulation_step(self):
        """Run a single step of the force-directed layout simulation"""
        nodes = list(self.location_nodes.values())
        if len(nodes) < 2:
            return

        # Initialize velocities if needed
        if not hasattr(self, '_sim_velocities') or not self._sim_velocities:
            self.init_simulation()

        # Ensure all nodes have velocities (handles new nodes)
        for node in nodes:
            if node.node_key not in self._sim_velocities:
                self._sim_velocities[node.node_key] = QPointF(0, 0)

        # Layout parameters - increased repulsion for more spacing
        repulsion_strength = 150000  # Increased to prevent overlap
        attraction_strength = 0.03
        damping = 0.85
        min_distance = 200  # Minimum distance between card centers

        forces = {node.node_key: QPointF(0, 0) for node in nodes}

        # Repulsion between all pairs
        for i, node1 in enumerate(nodes):
            for node2 in nodes[i + 1:]:
                pos1 = node1.scenePos() + node1.boundingRect().center()
                pos2 = node2.scenePos() + node2.boundingRect().center()

                dx = pos1.x() - pos2.x()
                dy = pos1.y() - pos2.y()
                dist_sq = dx * dx + dy * dy
                dist = max(dist_sq ** 0.5, 1)

                # Stronger repulsion when too close
                if dist < min_distance:
                    force = repulsion_strength / max(dist_sq, 100)
                else:
                    force = repulsion_strength / dist_sq

                fx = (dx / dist) * force
                fy = (dy / dist) * force

                forces[node1.node_key] += QPointF(fx, fy)
                forces[node2.node_key] -= QPointF(fx, fy)

        # Attraction along edges
        for arrow in self.arrows:
            node1 = arrow.source_node
            node2 = arrow.target_node

            pos1 = node1.scenePos() + node1.boundingRect().center()
            pos2 = node2.scenePos() + node2.boundingRect().center()

            dx = pos2.x() - pos1.x()
            dy = pos2.y() - pos1.y()
            dist = max((dx * dx + dy * dy) ** 0.5, 1)

            # Only attract if beyond minimum distance
            if dist > min_distance:
                force = (dist - min_distance) * attraction_strength
                fx = (dx / dist) * force
                fy = (dy / dist) * force

                forces[node1.node_key] += QPointF(fx, fy)
                forces[node2.node_key] -= QPointF(fx, fy)

        # Apply forces with damping
        for node in nodes:
            vel = self._sim_velocities[node.node_key]
            force = forces[node.node_key]

            vel = QPointF(
                (vel.x() + force.x()) * damping,
                (vel.y() + force.y()) * damping
            )
            self._sim_velocities[node.node_key] = vel

            # Update position
            new_pos = node.scenePos() + vel
            node.setPos(new_pos)

        # Update scene rect
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-50, -50, 50, 50))

    def refresh(self):
        """Refresh the view"""
        self._build_view()

    def set_icon_mode(self, enabled):
        """Toggle icon mode for all location nodes"""
        for node in self.location_nodes.values():
            node.icon_mode = enabled
        # Update arrows since node sizes changed
        self.update_arrows()
        # Update scene rect
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-50, -50, 50, 50))

    def capture_screenshot(self):
        """Capture the current view as an image with transparent background"""
        # Get the bounding rect of all items
        rect = self.scene.itemsBoundingRect()
        if rect.isEmpty():
            return None

        # Add some padding
        padding = 20
        rect = rect.adjusted(-padding, -padding, padding, padding)

        # Create image with transparent background
        image = QImage(int(rect.width()), int(rect.height()), QImage.Format_ARGB32)
        image.fill(Qt.transparent)

        # Render scene to image
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        self.scene.render(painter, QRectF(image.rect()), rect)
        painter.end()

        return image


class HiddenLocationsPanel(QWidget):
    """List of hidden locations, each with an Unhide button.

    Meant to be embedded inside a larger scrollable sidebar (see
    LocationViewWidget), so it does not scroll or size itself independently.
    Only shown while there is at least one hidden location.
    """

    unhide_requested = Signal(object)  # emits the LocationNode to unhide

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setVisible(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        title = QLabel(f"<b>{tr('LABEL_HIDDEN_LOCATIONS')}</b>")
        outer.addWidget(title)

        self._list_layout = QVBoxLayout()
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self._list_layout)

    def set_nodes(self, nodes):
        """Rebuild the row list from the given LocationNodes"""
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        for node in nodes:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)

            name = getattr(node.card, 'name', None) or node.node_key
            label = QLabel(name)
            label.setWordWrap(True)
            row_layout.addWidget(label, 1)

            unhide_btn = QPushButton(tr("BTN_UNHIDE"))
            unhide_btn.setToolTip(tr("TOOLTIP_UNHIDE"))
            unhide_btn.clicked.connect(lambda checked=False, n=node: self.unhide_requested.emit(n))
            row_layout.addWidget(unhide_btn)

            self._list_layout.addWidget(row)

        self.setVisible(bool(nodes))


class LocationViewWidget(QWidget):
    """Container widget for LocationView: layout tabs on top, graphics view +
    right-hand control sidebar below."""

    card_selected = Signal(object)

    SIDEBAR_WIDTH = 230

    def __init__(self, encounter_set, renderer, parent=None):
        super().__init__(parent)
        self.encounter_set = encounter_set
        self.renderer = renderer

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Layout tabs
        tabs_row = QHBoxLayout()

        self.layout_tabs = QTabBar()
        self.layout_tabs.setExpanding(False)
        self.layout_tabs.currentChanged.connect(self._on_tab_changed)
        self.layout_tabs.tabCloseRequested.connect(self._delete_layout)
        self.layout_tabs.tabBarDoubleClicked.connect(self._rename_layout)
        tabs_row.addWidget(self.layout_tabs, 1)

        add_layout_btn = QPushButton(tr("SYMBOL_PLUS"))
        add_layout_btn.setFixedWidth(28)
        add_layout_btn.setToolTip(tr("TOOLTIP_ADD_LAYOUT"))
        add_layout_btn.clicked.connect(self._add_layout)
        tabs_row.addWidget(add_layout_btn)

        outer.addLayout(tabs_row)

        # Location view + right-hand sidebar
        body = QHBoxLayout()

        self.location_view = LocationView(encounter_set, renderer)
        self.location_view.card_double_clicked.connect(self.card_selected.emit)
        self.location_view.hidden_locations_changed.connect(self._refresh_hidden_panel)
        self.location_view.hide_mode_changed.connect(self._update_hide_mode_button)
        self.location_view.layouts_changed.connect(self._refresh_tabs)
        body.addWidget(self.location_view, 1)

        body.addWidget(self._build_sidebar(encounter_set))

        outer.addLayout(body)

        # Simulation timer (30 fps = ~33ms interval)
        self._sim_timer = QTimer(self)
        self._sim_timer.setInterval(33)
        self._sim_timer.timeout.connect(self._simulation_step)

        self._refresh_tabs()
        self._sync_controls_to_active_layout()
        self._refresh_hidden_panel()

    def _build_sidebar(self, encounter_set):
        sidebar = QWidget()
        sidebar.setFixedWidth(self.SIDEBAR_WIDTH)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        sidebar_layout.addWidget(scroll)

        content = QWidget()
        col = QVBoxLayout(content)
        col.setContentsMargins(6, 6, 6, 6)

        title = QLabel(f"<b>{tr('TITLE_LOCATIONS').format(name=encounter_set.name)}</b>")
        title.setWordWrap(True)
        col.addWidget(title)

        help_label = QLabel(tr("HELP_LOCATION_VIEW"))
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #888;")
        col.addWidget(help_label)

        self.icon_mode_cb = QCheckBox(tr("LABEL_ICONS"))
        self.icon_mode_cb.setToolTip(tr("TOOLTIP_ICON_MODE"))
        self.icon_mode_cb.toggled.connect(self._toggle_icon_mode)
        col.addWidget(self.icon_mode_cb)

        self.snap_cb = QCheckBox(tr("LABEL_SNAP_TO_GRID"))
        self.snap_cb.setToolTip(tr("TOOLTIP_SNAP_TO_GRID"))
        self.snap_cb.toggled.connect(self._toggle_snap)
        col.addWidget(self.snap_cb)

        self.show_arrows_cb = QCheckBox(tr("LABEL_SHOW_ARROWS"))
        self.show_arrows_cb.setToolTip(tr("TOOLTIP_SHOW_ARROWS"))
        self.show_arrows_cb.toggled.connect(self._toggle_show_arrows)
        col.addWidget(self.show_arrows_cb)

        self.hide_mode_btn = QPushButton()
        self.hide_mode_btn.setCheckable(True)
        self.hide_mode_btn.setToolTip(tr("TOOLTIP_HIDE_MODE"))
        self.hide_mode_btn.toggled.connect(self._on_hide_mode_btn_toggled)
        col.addWidget(self.hide_mode_btn)

        self.simulate_btn = QPushButton(tr("BTN_SIMULATE"))
        self.simulate_btn.setCheckable(True)
        self.simulate_btn.setToolTip(tr("TOOLTIP_SIMULATE"))
        self.simulate_btn.toggled.connect(self._toggle_simulation)
        col.addWidget(self.simulate_btn)

        screenshot_btn = QPushButton(tr("BTN_SCREENSHOT"))
        screenshot_btn.setToolTip(tr("TOOLTIP_SCREENSHOT"))
        screenshot_btn.clicked.connect(self._take_screenshot)
        col.addWidget(screenshot_btn)

        self._export_guide_btn = QPushButton(tr("BTN_EXPORT_LOCATION"))
        self._export_guide_btn.setToolTip(tr("TOOLTIP_EXPORT_LOCATION"))
        self._export_guide_btn.clicked.connect(self._export_to_guide)
        col.addWidget(self._export_guide_btn)

        refresh_btn = QPushButton(tr("BTN_REFRESH"))
        refresh_btn.clicked.connect(self._refresh)
        col.addWidget(refresh_btn)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        col.addWidget(separator)

        self.hidden_panel = HiddenLocationsPanel()
        self.hidden_panel.unhide_requested.connect(self._unhide_node)
        col.addWidget(self.hidden_panel)

        col.addStretch()
        scroll.setWidget(content)

        return sidebar

    def _refresh(self):
        self.location_view.refresh()
        self._refresh_tabs()
        self._sync_controls_to_active_layout()

    def _refresh_hidden_panel(self):
        self.hidden_panel.set_nodes(self.location_view.get_hidden_nodes())

    def _update_hide_mode_button(self, hide_mode):
        key = "LABEL_HIDE_MODE_ON" if hide_mode else "LABEL_HIDE_MODE_OFF"
        self.hide_mode_btn.blockSignals(True)
        self.hide_mode_btn.setChecked(hide_mode)
        self.hide_mode_btn.setText(tr(key))
        self.hide_mode_btn.blockSignals(False)

    def _on_hide_mode_btn_toggled(self, checked):
        if checked != self.location_view.hide_mode:
            self.location_view.toggle_hide_mode()

    def _unhide_node(self, node):
        self.location_view.set_node_hidden(node, False)

    # --- Layout tabs ---------------------------------------------------

    def _refresh_tabs(self):
        self.layout_tabs.blockSignals(True)
        while self.layout_tabs.count():
            self.layout_tabs.removeTab(0)
        for layout in self.location_view.layouts:
            index = self.layout_tabs.addTab(layout['name'])
            self.layout_tabs.setTabData(index, layout['id'])
        multiple = self.layout_tabs.count() > 1
        self.layout_tabs.setTabsClosable(multiple)
        active_index = next(
            (i for i in range(self.layout_tabs.count())
             if self.layout_tabs.tabData(i) == self.location_view.active_layout_id),
            0,
        )
        self.layout_tabs.setCurrentIndex(active_index)
        self.layout_tabs.blockSignals(False)

    def _sync_controls_to_active_layout(self):
        self.snap_cb.blockSignals(True)
        self.snap_cb.setChecked(self.location_view.snap_enabled)
        self.snap_cb.blockSignals(False)

        self.show_arrows_cb.blockSignals(True)
        self.show_arrows_cb.setChecked(self.location_view.show_arrows)
        self.show_arrows_cb.blockSignals(False)

        self._update_hide_mode_button(self.location_view.hide_mode)

    def _on_tab_changed(self, index):
        layout_id = self.layout_tabs.tabData(index)
        if layout_id and layout_id != self.location_view.active_layout_id:
            self.location_view.switch_layout(layout_id)
            self._sync_controls_to_active_layout()

    def _add_layout(self):
        self.location_view.add_layout()
        self._refresh_tabs()
        self._sync_controls_to_active_layout()

    def _delete_layout(self, index):
        layout_id = self.layout_tabs.tabData(index)
        if not layout_id or len(self.location_view.layouts) <= 1:
            return
        self.location_view.remove_layout(layout_id)
        self._refresh_tabs()
        self._sync_controls_to_active_layout()

    def _rename_layout(self, index):
        layout_id = self.layout_tabs.tabData(index)
        if not layout_id:
            return
        current_name = self.layout_tabs.tabText(index)
        name, ok = QInputDialog.getText(
            self, tr("DLG_RENAME_LAYOUT"), tr("MSG_ENTER_LAYOUT_NAME"), text=current_name
        )
        if ok and name.strip():
            self.location_view.rename_layout(layout_id, name.strip())
            self._refresh_tabs()

    def _toggle_snap(self, enabled):
        self.location_view.snap_enabled = enabled

    def _toggle_show_arrows(self, enabled):
        self.location_view.show_arrows = enabled

    def _toggle_simulation(self, enabled):
        """Toggle the simulation on/off"""
        if enabled:
            self.simulate_btn.setText(tr("BTN_STOP"))
            self.location_view.init_simulation()
            self._sim_timer.start()
        else:
            self.simulate_btn.setText(tr("BTN_SIMULATE"))
            self._sim_timer.stop()
            # Save positions when stopping
            self.location_view.save_all_positions()

    def _simulation_step(self):
        """Run a single simulation step"""
        self.location_view.simulation_step()

    def _toggle_icon_mode(self, enabled):
        """Toggle between card images and icon mode"""
        self.location_view.set_icon_mode(enabled)

    def _take_screenshot(self):
        """Capture screenshot and copy to clipboard"""
        image = self.location_view.capture_screenshot()
        if image:
            clipboard = QApplication.clipboard()
            clipboard.setImage(image)
            # Show brief confirmation in status bar if available
            import shoggoth
            if shoggoth.app:
                shoggoth.app.status_bar.showMessage(tr("MSG_SCREENSHOT_COPIED"), 3000)

    def _export_to_guide(self):
        """Export location overview image to the project export folder."""
        image = self.location_view.capture_screenshot()
        if not image:
            return

        project = self.encounter_set.project
        enc_id = self.encounter_set.id
        active_layout_id = self.location_view.active_layout_id
        # 0-based to match the [encounter:id:location_overview:index] guide tag,
        # which defaults to index 0 when omitted.
        layout_index = next(
            i for i, layout in enumerate(self.location_view.layouts)
            if layout['id'] == active_layout_id
        )

        export_folder = files.default_export_folder(project)
        export_folder.mkdir(parents=True, exist_ok=True)

        img_path = export_folder / f'{enc_id}_location_overview_{layout_index}.png'
        image.save(str(img_path))

        import shoggoth
        if shoggoth.app:
            shoggoth.app.status_bar.showMessage(tr("MSG_LOCATION_EXPORTED").format(path=str(img_path)), 4000)
