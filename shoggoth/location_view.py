"""
Location View - Visual editor for location connections in encounter sets
"""
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsPixmapItem,
    QGraphicsPathItem, QGraphicsEllipseItem, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QMenu, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QPainterPath, QPixmap, QFont,
    QCursor
)
from io import BytesIO


class ConnectionArrow(QGraphicsPathItem):
    """Arrow representing a connection between two locations"""

    def __init__(self, source_node, target_node, connection_symbol):
        super().__init__()
        self.source_node = source_node
        self.target_node = target_node
        self.connection_symbol = connection_symbol
        self.hovered = False

        # Styling
        self.default_pen = QPen(QColor(100, 100, 100), 2)
        self.hover_pen = QPen(QColor(255, 100, 100), 3)
        self.setPen(self.default_pen)

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setZValue(-1)  # Draw behind nodes

        self.update_path()

    def update_path(self):
        """Update the arrow path based on node positions"""
        if not self.source_node or not self.target_node:
            return

        # Get center points of nodes
        source_rect = self.source_node.boundingRect()
        target_rect = self.target_node.boundingRect()

        source_center = self.source_node.scenePos() + source_rect.center()
        target_center = self.target_node.scenePos() + target_rect.center()

        # Calculate direction and offset to edge of nodes
        dx = target_center.x() - source_center.x()
        dy = target_center.y() - source_center.y()
        length = (dx * dx + dy * dy) ** 0.5

        if length == 0:
            return

        # Normalize
        dx /= length
        dy /= length

        # Offset from center to edge (approximate)
        source_offset = min(source_rect.width(), source_rect.height()) / 2
        target_offset = min(target_rect.width(), target_rect.height()) / 2

        start = QPointF(
            source_center.x() + dx * source_offset,
            source_center.y() + dy * source_offset
        )
        end = QPointF(
            target_center.x() - dx * target_offset,
            target_center.y() - dy * target_offset
        )

        # Create curved path
        path = QPainterPath()
        path.moveTo(start)

        # Control point for curve (offset perpendicular to line)
        mid = QPointF((start.x() + end.x()) / 2, (start.y() + end.y()) / 2)
        # Add slight curve
        ctrl_offset = 20
        ctrl = QPointF(mid.x() - dy * ctrl_offset, mid.y() + dx * ctrl_offset)

        path.quadTo(ctrl, end)

        # Add arrowhead
        arrow_size = 10
        angle = 2.5  # ~150 degrees in radians

        # Calculate arrowhead points
        arrow_p1 = QPointF(
            end.x() - arrow_size * (dx * 0.866 + dy * 0.5),
            end.y() - arrow_size * (dy * 0.866 - dx * 0.5)
        )
        arrow_p2 = QPointF(
            end.x() - arrow_size * (dx * 0.866 - dy * 0.5),
            end.y() - arrow_size * (dy * 0.866 + dx * 0.5)
        )

        path.moveTo(end)
        path.lineTo(arrow_p1)
        path.moveTo(end)
        path.lineTo(arrow_p2)

        self.setPath(path)

    def hoverEnterEvent(self, event):
        self.hovered = True
        self.setPen(self.hover_pen)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.hovered = False
        self.setPen(self.default_pen)
        self.unsetCursor()
        super().hoverLeaveEvent(event)


class LocationNode(QGraphicsItem):
    """Node representing a location card in the view"""

    WIDTH = 120
    HEIGHT = 168

    def __init__(self, card, face, face_side, renderer, view):
        super().__init__()
        self.card = card
        self.face = face
        self.face_side = face_side  # 'front' or 'back'
        self.renderer = renderer
        self.view = view
        self.thumbnail = None

        # Stable key for this node
        self.node_key = f"{card.id}_{face_side}"

        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)

        # For connection dragging
        self.drag_start_pos = None

        # Generate thumbnail
        self._generate_thumbnail()

    def _generate_thumbnail(self):
        """Generate a thumbnail of the location card"""
        try:
            image = self.renderer.render_card_side(self.card, self.face, include_bleed=False)
            image = image.resize((self.WIDTH, self.HEIGHT))

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

    def boundingRect(self):
        return QRectF(0, 0, self.WIDTH, self.HEIGHT)

    def paint(self, painter, option, widget):
        # Draw thumbnail or placeholder
        if self.thumbnail:
            painter.drawPixmap(0, 0, self.thumbnail)
        else:
            painter.setBrush(QBrush(QColor(200, 200, 200)))
            painter.drawRect(0, 0, self.WIDTH, self.HEIGHT)

        # Draw selection highlight
        if self.isSelected():
            painter.setPen(QPen(QColor(0, 120, 255), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(0, 0, self.WIDTH, self.HEIGHT)

        # Draw connection symbol indicator
        connection = self.face.get('connection')
        if connection:
            painter.setPen(QPen(QColor(0, 0, 0)))
            painter.setBrush(QBrush(QColor(255, 255, 200, 200)))
            painter.drawEllipse(self.WIDTH - 25, 5, 20, 20)

            font = QFont()
            font.setPointSize(8)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(QRectF(self.WIDTH - 25, 5, 20, 20), Qt.AlignCenter, connection[:2])

    def itemChange(self, change, value):
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


class LocationView(QGraphicsView):
    """Main view for editing location connections"""

    # Signals
    card_double_clicked = Signal(object)  # Emits card when double-clicked
    connections_changed = Signal()  # Emitted when connections are modified

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

        # Build the view
        self._build_view()

    def _build_view(self):
        """Build the location nodes and connections"""
        self.scene.clear()
        self.location_nodes.clear()
        self.arrows.clear()

        # Find all location cards
        locations = []
        for card in self.encounter_set.cards:
            if card.front.get('type') == 'location':
                locations.append((card, card.front, 'front'))
            if card.back.get('type') == 'location':
                locations.append((card, card.back, 'back'))

        # Load saved positions
        saved_positions = self._get_saved_positions()

        # Create nodes with grid layout (default) or saved positions
        cols = max(3, int(len(locations) ** 0.5) + 1)
        spacing_x = LocationNode.WIDTH + 80
        spacing_y = LocationNode.HEIGHT + 60

        for i, (card, face, face_side) in enumerate(locations):
            node = LocationNode(card, face, face_side, self.renderer, self)

            # Use saved position or default grid position
            node_key = f"{card.id}_{face_side}"
            if node_key in saved_positions:
                pos = saved_positions[node_key]
                node.setPos(pos['x'], pos['y'])
            else:
                col = i % cols
                row = i // cols
                node.setPos(col * spacing_x, row * spacing_y)

            self.scene.addItem(node)
            self.location_nodes[node_key] = node

        # Create connection arrows
        self._build_arrows()

        # Fit view to content
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-50, -50, 50, 50))

    def _build_arrows(self):
        """Build arrows based on connection data"""
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

        # Create arrows for each connection
        for key, source_node in self.location_nodes.items():
            connections = source_node.face.get('connections', [])
            if not connections:
                continue

            for symbol in connections:
                target_nodes = symbol_to_nodes.get(symbol, [])
                for target_node in target_nodes:
                    if target_node != source_node:
                        arrow = ConnectionArrow(source_node, target_node, symbol)
                        self.scene.addItem(arrow)
                        self.arrows.append(arrow)

    def update_arrows(self):
        """Update all arrow positions"""
        for arrow in self.arrows:
            arrow.update_path()

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
            if isinstance(item, LocationNode) and item != self.drag_source_node:
                target_node = item
                break

        if target_node:
            self._add_connection(self.drag_source_node, target_node)

        self.drag_source_node = None

    def _add_connection(self, source_node, target_node):
        """Add a connection from source to target"""
        target_symbol = target_node.face.get('connection')
        if not target_symbol or target_symbol == 'None':
            # Target has no connection symbol - can't connect to it
            location_name = target_node.card.name
            QMessageBox.warning(
                self,
                "Cannot Connect",
                f"Location \"{location_name}\" has no connection icon.\n\n"
            )
            return

        # Get current connections
        connections = source_node.face.get('connections', []) or []
        connections = list(connections)  # Make a copy

        # Add the symbol if not already present
        if target_symbol not in connections:
            connections.append(target_symbol)
            source_node.face.set('connections', connections)
            self._build_arrows()
            self.connections_changed.emit()

    def remove_connection(self, arrow):
        """Remove a connection arrow"""
        source_node = arrow.source_node
        symbol = arrow.connection_symbol

        connections = source_node.face.get('connections', []) or []
        connections = list(connections)

        if symbol in connections:
            connections.remove(symbol)
            if connections:
                source_node.face.set('connections', connections)
            else:
                source_node.face.set('connections', None)
            self._build_arrows()
            self.connections_changed.emit()

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
        if event.button() == Qt.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            items = self.scene.items(scene_pos)

            for item in items:
                if isinstance(item, ConnectionArrow):
                    # Show context menu for arrow
                    self._show_arrow_context_menu(item, event.globalPos())
                    return

        super().mousePressEvent(event)

    def _show_arrow_context_menu(self, arrow, global_pos):
        """Show context menu for connection arrow"""
        menu = QMenu(self)
        remove_action = menu.addAction("Remove Connection")
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

    def _get_saved_positions(self):
        """Get saved node positions from encounter set meta"""
        meta = self.encounter_set.data.get('meta', {})
        return meta.get('location_graph', {})

    def save_node_position(self, node):
        """Save a single node's position"""
        # Ensure meta structure exists
        if 'meta' not in self.encounter_set.data:
            self.encounter_set.data['meta'] = {}
        if 'location_graph' not in self.encounter_set.data['meta']:
            self.encounter_set.data['meta']['location_graph'] = {}

        # Save position
        pos = node.scenePos()
        self.encounter_set.data['meta']['location_graph'][node.node_key] = {
            'x': pos.x(),
            'y': pos.y()
        }

        # Mark as dirty
        self.encounter_set.dirty = True

    def save_all_positions(self):
        """Save all node positions"""
        for node in self.location_nodes.values():
            self.save_node_position(node)

    def auto_layout(self):
        """Apply force-directed layout algorithm"""
        nodes = list(self.location_nodes.values())
        if len(nodes) < 2:
            return

        # Build adjacency for attraction forces
        # Nodes connected by arrows should attract
        connected_pairs = set()
        for arrow in self.arrows:
            key1 = arrow.source_node.node_key
            key2 = arrow.target_node.node_key
            connected_pairs.add((key1, key2))
            connected_pairs.add((key2, key1))  # Bidirectional attraction

        # Layout parameters
        repulsion_strength = 50000
        attraction_strength = 0.05
        damping = 0.85
        iterations = 50

        # Initialize velocities
        velocities = {node.node_key: QPointF(0, 0) for node in nodes}

        for iteration in range(iterations):
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

                    # Repulsion force (inverse square)
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

                # Attraction force (linear)
                force = dist * attraction_strength
                fx = (dx / dist) * force
                fy = (dy / dist) * force

                forces[node1.node_key] += QPointF(fx, fy)
                forces[node2.node_key] -= QPointF(fx, fy)

            # Apply forces with damping
            for node in nodes:
                vel = velocities[node.node_key]
                force = forces[node.node_key]

                vel = QPointF(
                    (vel.x() + force.x()) * damping,
                    (vel.y() + force.y()) * damping
                )
                velocities[node.node_key] = vel

                # Update position
                new_pos = node.scenePos() + vel
                node.setPos(new_pos)

        # Save all positions after layout
        self.save_all_positions()

        # Update scene rect
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-50, -50, 50, 50))

        # Center view on content
        self.centerOn(self.scene.sceneRect().center())

    def refresh(self):
        """Refresh the view"""
        self._build_view()


class LocationViewWidget(QWidget):
    """Container widget for LocationView with toolbar"""

    card_selected = Signal(object)

    def __init__(self, encounter_set, renderer, parent=None):
        super().__init__(parent)
        self.encounter_set = encounter_set
        self.renderer = renderer

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()

        title = QLabel(f"<b>Locations: {encounter_set.name}</b>")
        toolbar.addWidget(title)

        toolbar.addStretch()

        help_label = QLabel("Drag nodes to arrange | Right-drag to connect | Click arrow to remove")
        help_label.setStyleSheet("color: #888;")
        toolbar.addWidget(help_label)

        auto_layout_btn = QPushButton("Auto Layout")
        auto_layout_btn.setToolTip("Automatically arrange locations using force-directed layout")
        auto_layout_btn.clicked.connect(self._auto_layout)
        toolbar.addWidget(auto_layout_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh)
        toolbar.addWidget(refresh_btn)

        layout.addLayout(toolbar)

        # Location view
        self.location_view = LocationView(encounter_set, renderer)
        self.location_view.card_double_clicked.connect(self.card_selected.emit)
        layout.addWidget(self.location_view)

    def _refresh(self):
        self.location_view.refresh()

    def _auto_layout(self):
        self.location_view.auto_layout()
