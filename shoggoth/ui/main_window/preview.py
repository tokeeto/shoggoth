"""
Card preview rendering: debounced background renders with stale-result
discarding, plus the illustration-mode wiring between editor and preview.
"""
import threading

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from shoggoth.i18n import tr

PREVIEW_SIZE = {'width': 1500, 'height': 2100, 'bleed': 72}


class PreviewController(QObject):
    # Emitted from the render thread; Qt queues delivery onto the main thread.
    render_result = Signal(int, object, object)  # version, front_image, back_image

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.render_version = 0  # Tracks render requests, stale results are discarded

        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self._start_background_render)

        self.render_result.connect(self._handle_render_result)

    def schedule_update(self):
        """Schedule a debounced background render of the current card"""
        if not self.window.current_card:
            return
        # Increment version to invalidate any in-progress renders
        self.render_version += 1
        # Restart the debounce timer
        self.render_timer.start(10)

    def rerender_now(self):
        """Invalidate any in-flight renders and start a new one immediately"""
        self.render_version += 1
        self._start_background_render()

    def _render_options(self):
        config = self.window.config
        bleed = 'mark' if config.getboolean('Shoggoth', 'show_bleed', True) else False
        show_regions = config.getboolean('Shoggoth', 'show_regions', False)
        return bleed, show_regions

    def _start_background_render(self):
        """Start rendering in background thread"""
        window = self.window
        if not window.current_card:
            return

        # Capture current state for the background thread
        card = window.current_card
        version = self.render_version
        bleed, show_regions = self._render_options()
        renderer = window.card_renderer

        def render_task():
            try:
                front_image, back_image = renderer.get_card_textures(
                    card, PREVIEW_SIZE, bleed=bleed, show_regions=show_regions
                )
                # Emit result signal (will be handled on main thread)
                self.render_result.emit(version, front_image, back_image)
            except Exception as e:
                # Emit with None images to signal error
                print(f"Render error: {e}")
                self.render_result.emit(version, None, None)

        thread = threading.Thread(target=render_task, daemon=True)
        thread.start()

    @Slot(int, object, object)
    def _handle_render_result(self, version, front_image, back_image):
        """Handle render result on main thread"""
        # Discard stale results
        if version != self.render_version:
            return

        if front_image is not None:
            self.window.card_preview.update_card_images(front_image, back_image)
        else:
            self.window.status_bar.showMessage(tr("ERR_RENDER_CARD"))

    def render_current_sync(self):
        """Render the current card synchronously (used on initial card load)"""
        window = self.window
        if not window.current_card:
            return

        try:
            bleed, show_regions = self._render_options()
            front_image, back_image = window.card_renderer.get_card_textures(
                window.current_card, PREVIEW_SIZE, bleed=bleed, show_regions=show_regions
            )
            window.card_preview.set_card_images(front_image, back_image)
        except Exception as e:
            window.status_bar.showMessage(tr("ERR_RENDER_CARD_DETAIL").format(error=e))

    # ── Illustration mode ─────────────────────────────────────────────────

    def connect_illustration_mode(self, editor):
        """Connect illustration mode signals between editor and preview"""
        window = self.window

        # Disconnect any previous connections first
        self.disconnect_illustration_mode()

        # Connect preview pan/scale signals to editor
        window.card_preview.illustration_pan_changed.connect(self._on_illustration_pan)
        window.card_preview.illustration_scale_changed.connect(self._on_illustration_scale)

        # Connect editor illustration mode signals to preview
        for face_editor in [editor.front_editor, editor.back_editor]:
            if face_editor and hasattr(face_editor, 'illustration_widget'):
                widget = face_editor.illustration_widget
                widget.illustration_mode_changed.connect(self._on_illustration_mode_changed)
                face = face_editor.face
                widget.scale_resolver = lambda f=face: window.card_renderer.get_implicit_illustration_scale(f)
                widget.update_scale_warning()

    def disconnect_illustration_mode(self):
        """Disconnect illustration mode signals"""
        try:
            self.window.card_preview.illustration_pan_changed.disconnect(self._on_illustration_pan)
            self.window.card_preview.illustration_scale_changed.disconnect(self._on_illustration_scale)
        except RuntimeError:
            pass  # Signals weren't connected

        # Reset illustration mode on preview
        self.window.card_preview.set_illustration_mode(False)

    def _on_illustration_mode_changed(self, enabled, side):
        """Handle illustration mode toggle from editor"""
        self.window.card_preview.set_illustration_mode(enabled, side)

    def _face_illustration_widget(self, side):
        editor = self.window.current_editor
        if not editor:
            return None
        face_editor = editor.front_editor if side == 'front' else editor.back_editor
        if face_editor and hasattr(face_editor, 'illustration_widget'):
            return face_editor.illustration_widget
        return None

    def _on_illustration_pan(self, side, delta_x, delta_y):
        """Handle pan changes from preview"""
        widget = self._face_illustration_widget(side)
        if widget:
            widget.update_pan(delta_x, delta_y)

    def _on_illustration_scale(self, side, delta):
        """Handle scale changes from preview"""
        widget = self._face_illustration_widget(side)
        if widget:
            widget.update_scale(delta)
