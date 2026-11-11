"""
Card preview rendering: debounced background renders with stale-result
discarding, plus the illustration-mode wiring between editor and preview.
"""
import threading

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from shoggoth.i18n import tr
from shoggoth.settings import EXPORT_SIZES


class PreviewController(QObject):
    # Emitted from the render thread; Qt queues delivery onto the main thread.
    render_result = Signal(int, object, object)  # version, front_image, back_image

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.render_version = 0  # Tracks render requests, stale results are discarded
        self.trim = window.config.get('Shoggoth', 'preview_trim', 'ffg')
        # Render the parent's version of a modification's card instead
        self.show_original = False
        # Detached preview windows (View → New Preview Window), mirroring the dock
        self.extra_windows = []
        self._last_images = (None, None)

        self.render_timer = QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.timeout.connect(self._start_background_render)

        self.render_result.connect(self._handle_render_result)

    def set_trim(self, trim):
        """Switch the preview between the FFG and MTG physical trim and rerender."""
        if trim == self.trim:
            return
        self.trim = trim
        self.window.config.set('Shoggoth', 'preview_trim', trim)
        self.window.config.save()
        self.rerender_now()

    def set_show_original(self, show):
        if show == self.show_original:
            return
        self.show_original = show
        self.rerender_now()

    def _card_to_render(self, card=None):
        """The current card (or `card`), or its unmodified original when asked for."""
        if card is None:
            card = self.window.current_card
        if self.show_original and card is not None and card.project.is_modification:
            return card.project.original_card(card.id) or card
        return card

    def _preview_size(self):
        idx = self.window.config.getint('Shoggoth', 'preview_resolution', 0)
        if not (0 <= idx < len(EXPORT_SIZES)):
            idx = 0
        return dict(EXPORT_SIZES[idx][1], trim=self.trim)

    def schedule_update(self):
        """Schedule a debounced background render of the current card"""
        if not self.window.current_card:
            return
        # Increment version to invalidate any in-progress renders
        self.render_version += 1
        # Restart the debounce timer
        self.render_timer.start(10)

    def rerender_now(self):
        """Invalidate any in-flight renders and start a new one immediately
        (pinned preview windows included)"""
        self.render_version += 1
        self._start_background_render()
        for extra in list(self.extra_windows):
            if extra.pinned:
                self._render_pinned(extra)

    def _render_options(self):
        config = self.window.config
        bleed = 'mark' if config.getboolean('Shoggoth', 'show_bleed', True) else False
        show_regions = config.getboolean('Shoggoth', 'show_regions', False)
        rounded = config.getboolean('Shoggoth', 'show_rounded', False)
        return bleed, show_regions, rounded

    def _start_background_render(self):
        """Start rendering in background thread"""
        window = self.window
        if not window.current_card:
            return

        # Capture current state for the background thread
        card = self._card_to_render()
        version = self.render_version
        bleed, show_regions, rounded = self._render_options()
        renderer = window.card_renderer

        size = self._preview_size()

        def render_task():
            try:
                with renderer.track_files(lambda path: self._watch_file(version, path)):
                    front_image, back_image = renderer.get_card_textures(
                        card, size, bleed=bleed, show_regions=show_regions, rounded=rounded
                    )
                # Emit result signal (will be handled on main thread)
                self.render_result.emit(version, front_image, back_image)
            except Exception as e:
                # Emit with None images to signal error
                print(f"Render error: {e}")
                self.render_result.emit(version, None, None)

        thread = threading.Thread(target=render_task, daemon=True)
        thread.start()

    def _watch_file(self, version, path):
        """A render (on any thread) used `path`: keep watching it for changes.
        Ignored once that render is stale, so a card we already left in the
        meantime doesn't re-register its files."""
        if version == self.render_version:
            self.window.file_watcher.watch_file(path)

    @Slot(int, object, object)
    def _handle_render_result(self, version, front_image, back_image):
        """Handle render result on main thread"""
        # Discard stale results
        if version != self.render_version:
            return

        if front_image is not None:
            self.window.card_preview.update_card_images(front_image, back_image)
            self._update_extra_windows(front_image, back_image, keep_view=True)
        else:
            self.window.status_bar.showMessage(tr("ERR_RENDER_CARD"))

    def render_current_sync(self):
        """Render the current card synchronously (used on initial card load)"""
        window = self.window
        if not window.current_card:
            return

        # A new card is on screen: results/file reports of earlier renders are stale
        self.render_version += 1
        version = self.render_version
        renderer = window.card_renderer
        try:
            bleed, show_regions, rounded = self._render_options()
            with renderer.track_files(lambda path: self._watch_file(version, path)):
                front_image, back_image = renderer.get_card_textures(
                    self._card_to_render(), self._preview_size(), bleed=bleed, show_regions=show_regions, rounded=rounded
                )
            window.card_preview.set_card_images(front_image, back_image)
            self._update_extra_windows(front_image, back_image, keep_view=False)
        except Exception as e:
            window.status_bar.showMessage(tr("ERR_RENDER_CARD_DETAIL").format(error=e))

    # ── Detached preview windows ──────────────────────────────────────────

    def open_extra_window(self):
        """Open another, top-level preview window. It starts on the side the
        docked preview isn't showing, so the two together show both sides."""
        from shoggoth.ui.preview_widget import PreviewWindow
        window = self.window
        side = 1 - window.card_preview.tabs.currentIndex()
        extra = PreviewWindow(window, side=side)
        self.extra_windows.append(extra)
        extra.destroyed.connect(lambda *_: self._forget_extra_window(extra))
        extra.pin_toggled.connect(lambda pinned: self.set_pinned(extra, pinned))
        extra.render_result.connect(
            lambda version, front, back: self._handle_pinned_result(extra, version, front, back))
        front, back = self._last_images
        extra.preview.set_card_images(front, back)
        extra.set_card_title(self._card_title())
        extra.show()
        return extra

    def _forget_extra_window(self, extra):
        if extra in self.extra_windows:
            self.extra_windows.remove(extra)

    def _card_title(self, card=None):
        card = card if card is not None else self.window.current_card
        return card.name if card is not None else ''

    def _update_extra_windows(self, front_image, back_image, keep_view):
        """Show a finished render of the current card in every unpinned
        window too. `keep_view` keeps their zoom/pan (same card re-rendered);
        otherwise it resets."""
        self._last_images = (front_image, back_image)
        title = self._card_title()
        for extra in list(self.extra_windows):
            if extra.pinned:
                continue
            if keep_view:
                extra.preview.update_card_images(front_image, back_image)
            else:
                extra.preview.set_card_images(front_image, back_image)
            extra.set_card_title(title)

    # ── Pinned windows ────────────────────────────────────────────────────

    def set_pinned(self, extra, pinned):
        """Pin `extra` to the current card, or unpin it to follow the current
        card again."""
        card = self.window.current_card
        if pinned and card is not None:
            extra.pinned_project = card.project
            extra.pinned_card_id = card.id
            extra.set_card_title(card.name)
            self._render_pinned(extra)  # files get watched, settings match the card
        else:
            self._unpin(extra)
        extra.set_pinned_state(extra.pinned)

    def _unpin(self, extra):
        extra.pinned_project = None
        extra.pinned_card_id = None
        extra.render_version += 1  # drop in-flight renders of the pinned card
        extra.renderer = None
        extra.watched_files = set()  # forgotten at the next view change
        extra.set_pinned_state(False)
        front, back = self._last_images
        extra.preview.set_card_images(front, back)
        extra.set_card_title(self._card_title())

    def _pinned_card(self, extra):
        """The pinned card, freshly looked up (it may have been reloaded,
        deleted, or its project closed: then None)."""
        project = extra.pinned_project
        if project is None or project not in self.window.open_projects:
            return None
        return project.get_card(extra.pinned_card_id)

    def _renderer_for(self, extra, card):
        """The main renderer when it is set up for the card's project, else a
        renderer of the pinned window's own (language, hyphenation, French
        punctuation differ per project and the main one follows the view)."""
        from shoggoth.renderer import CardRenderer
        from shoggoth.ui.main_window.views import resolve_language
        project = card.project
        wanted = (resolve_language(self.window, project, card),
                  project.auto_hyphenate, project.french_punctuation)
        main = self.window.card_renderer
        if (main.locale, main.hyphenation_enabled, main.french_punctuation) == wanted:
            return main
        own = extra.renderer
        if own is None or (own.locale, own.hyphenation_enabled, own.french_punctuation) != wanted:
            own = extra.renderer = CardRenderer(
                locale=wanted[0], hyphenation_enabled=wanted[1], french_punctuation=wanted[2])
        return own

    def _render_pinned(self, extra):
        """Render a pinned window's card in the background."""
        card = self._pinned_card(extra)
        if card is None:
            self._unpin(extra)
            return
        extra.render_version += 1
        version = extra.render_version
        card = self._card_to_render(card)
        renderer = self._renderer_for(extra, card)
        bleed, show_regions, rounded = self._render_options()
        size = self._preview_size()

        def track(path):
            if version == extra.render_version:
                extra.watched_files.add(path)
                self.window.file_watcher.watch_file(path)

        def render_task():
            try:
                with renderer.track_files(track):
                    front, back = renderer.get_card_textures(
                        card, size, bleed=bleed, show_regions=show_regions, rounded=rounded)
                extra.render_result.emit(version, front, back)
            except Exception as e:
                print(f"Render error (pinned preview): {e}")
                extra.render_result.emit(version, None, None)

        threading.Thread(target=render_task, daemon=True).start()

    def _handle_pinned_result(self, extra, version, front, back):
        if version != extra.render_version or not extra.pinned:
            return
        if front is not None:
            extra.preview.update_card_images(front, back)
            card = self._pinned_card(extra)
            if card is not None:
                extra.set_card_title(card.name)
        else:
            self.window.status_bar.showMessage(tr("ERR_RENDER_CARD"))

    def on_element_changed(self, project, kind, element_id, changed):
        """Project change-listener (via the window): re-render pinned windows
        whose card changed, inherits from the changed card, or belongs to a
        changed encounter set."""
        if not changed:
            return
        for extra in list(self.extra_windows):
            if not extra.pinned or extra.pinned_project is not project:
                continue
            card_id = extra.pinned_card_id
            if kind == 'cards':
                hit = element_id == card_id or card_id in project.inheriting_card_ids(element_id)
            elif kind == 'encounter_sets':
                card = self._pinned_card(extra)
                hit = card is not None and card.data.get('encounter_set') == element_id
            else:
                hit = False
            if hit:
                self._render_pinned(extra)

    def on_project_closed(self, project):
        for extra in list(self.extra_windows):
            if extra.pinned_project is project:
                self._unpin(extra)

    def invalidate_files(self, paths):
        """Files changed on disk: drop them from the pinned windows' own renderers."""
        for extra in self.extra_windows:
            if extra.renderer is not None:
                extra.renderer.invalidate_files(paths)

    def clear_caches(self):
        """Tools → Clear Cache: pinned windows' own renderers start afresh."""
        for extra in self.extra_windows:
            extra.renderer = None

    def rewatch_pinned_files(self):
        """After a view change dropped the watched files, keep watching the
        ones the pinned windows' cards use."""
        for extra in self.extra_windows:
            if extra.pinned:
                for path in extra.watched_files:
                    self.window.file_watcher.watch_file(path)

    # ── Illustration widgets ──────────────────────────────────────────────

    def connect_illustration_widgets(self, editor):
        """Wire renderer-derived helpers into the editor's illustration widgets"""
        window = self.window
        for face_editor in [editor.front_editor, editor.back_editor]:
            if face_editor and hasattr(face_editor, 'illustration_widget'):
                widget = face_editor.illustration_widget
                face = face_editor.face
                widget.scale_resolver = lambda f=face: window.card_renderer.get_implicit_illustration_scale(f)
                widget.update_scale_warning()
