"""
Main window for Shoggoth.

ShoggothMainWindow is a thin coordinator: it owns the application state
(open projects, current card, renderer) and the top-level layout, and it
is the stable facade the rest of the app reaches through `shoggoth.app`.
The actual behavior lives in the sibling modules:

    menus.py         menu bar construction
    commands.py      command palette population
    views.py         content-area switching (show_card, show_guide, ...)
    preview.py       debounced background preview rendering
    exports.py       image/PDF/TTS export actions
    projects.py      project lifecycle, translations, templates
    session.py       layout + session persistence (shoggoth.json)
    navigation.py    back/forward history
    help_dialogs.py  manual/about/asset-location dialogs
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter, QStatusBar,
    QMessageBox, QDockWidget,
)
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QIcon

import shoggoth
from shoggoth import telemetry
from shoggoth.renderer import CardRenderer
from shoggoth.file_monitor import FileWatcher
from shoggoth.files import asset_dir, path_key
from shoggoth.i18n import load_language, tr
from shoggoth.ui.browser import FileBrowser
from shoggoth.ui.preview_widget import ImprovedCardPreview
from shoggoth.ui.element_selector import (
    ElementSelectorDialog, KIND_ENCOUNTER, KIND_GUIDE, KIND_PROJECT,
)
from shoggoth.ui.command_palette import CommandPaletteDialog
from shoggoth.ui.main_window import commands, exports, menus, projects, views
from shoggoth.cloud.sync import CloudSyncController
from shoggoth.project import Project
from shoggoth.ui.main_window.navigation import NavigationHistory
from shoggoth.ui.main_window.preview import PreviewController
from shoggoth.ui.main_window.session import SessionManager


class ShoggothMainWindow(QMainWindow):
    """Main window for Shoggoth application"""

    # Signal for file changes (emitted from background thread, handled on main thread)
    file_changed_signal = Signal(object)  # set of changed paths

    def __init__(self):
        super().__init__()

        # Settings manager - must be before shoggoth.app assignment
        from shoggoth.settings import SettingsManager
        self.config = SettingsManager()

        shoggoth.app = self

        self.setWindowTitle(tr("APP_TITLE"))
        self.setMinimumSize(1400, 900)

        # Set application icon
        icon_path = asset_dir / "elder_sign_neon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Application state
        self.open_projects = []  # List of all open projects
        self.active_project = None  # The currently active project
        self.current_card = None
        self.current_editor = None
        self.current_guide = None
        self.current_guide_editor = None
        card_lang = self.config.get('Shoggoth', 'language', 'en')
        self.card_renderer = CardRenderer(locale=card_lang, hyphenation_enabled=True)
        self.file_watcher = None

        # Subsystems
        self.session = SessionManager(self)
        self.nav = NavigationHistory(self)
        self.preview = PreviewController(self)
        self.cloud = CloudSyncController(self)

        # The model tells us when an element's dirty state changes (see
        # Project.add_change_listener); re-rendering and tree refreshes are
        # decided here, in the UI, rather than by card.py reaching into the app.
        Project.add_change_listener(self._on_element_changed)

        # Connect file change signal to handler (for thread-safe UI updates)
        self.file_changed_signal.connect(self._handle_file_changed)

        # Initialize update manager (before setup_ui so menu can reference it)
        from shoggoth.ui.updater_ui import UpdateManager
        self.update_manager = UpdateManager(self.config, self)

        self.setup_ui()
        self.setup_file_monitoring()
        self.session.restore()

        # Opt-in usage data collection: report the projects restored above
        # (no-ops unless a telemetry session is already running -- see
        # ui/app.py, which starts one before this window is constructed).
        telemetry.record_startup(self.open_projects)

        # Check for updates after UI is ready (deferred)
        QTimer.singleShot(2000, self._check_for_updates_startup)

    def setup_ui(self):
        """Setup the user interface"""
        menus.create_menus(self)

        # Create central widget
        central = QWidget()
        self.setCentralWidget(central)

        # Main layout - just file browser + content area
        main_layout = QHBoxLayout()

        # Create main splitter (2 panels: browser + content)
        self.main_splitter = QSplitter(Qt.Horizontal)

        # Left panel - File browser
        self.file_browser = FileBrowser()
        self.file_browser.card_selected.connect(self.show_card)
        self.file_browser.encounter_selected.connect(self.show_encounter)
        self.file_browser.project_selected.connect(self.show_project)
        self.file_browser.guide_selected.connect(self.show_guide)
        self.file_browser.locations_selected.connect(self.show_locations)
        self.file_browser.active_project_changed.connect(self._on_active_project_changed)
        self.main_splitter.addWidget(self.file_browser)

        # Restore sidebar view mode from settings
        sidebar_mode = self.config.get('Shoggoth', 'sidebar_view', 'tree')
        card_sort = self.config.get('Shoggoth', 'card_sort_order', 'project_number')
        self.file_browser.switch_view(sidebar_mode, sort_order=card_sort)
        if sidebar_mode == 'list':
            self.sidebar_list_action.setChecked(True)
        else:
            self.sidebar_tree_action.setChecked(True)

        self.sidebar_tree_action.triggered.connect(lambda: self._set_sidebar_view('tree'))
        self.sidebar_list_action.triggered.connect(lambda: self._set_sidebar_view('list'))
        self.file_browser.sort_combo.currentIndexChanged.connect(self._on_card_sort_changed)

        # Right panel - Content area (will contain editor + preview for cards)
        self.content_container = QWidget()
        self.content_layout = QVBoxLayout()
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_container.setLayout(self.content_layout)
        self.main_splitter.addWidget(self.content_container)

        # Card preview dock (detachable)
        self.preview_dock = QDockWidget(tr("CARD_PREVIEW"), self)
        self.preview_dock.setObjectName("preview_dock")
        self.preview_dock.setFeatures(
            QDockWidget.DockWidgetFloatable |
            QDockWidget.DockWidgetMovable |
            QDockWidget.DockWidgetClosable
        )
        self.card_preview = ImprovedCardPreview()
        self.card_preview.set_trim(self.preview.trim)
        self.card_preview.trim_changed.connect(self.preview.set_trim)
        self.preview_dock.setWidget(self.card_preview)

        # Add dock widget to right side (hidden initially)
        self.addDockWidget(Qt.RightDockWidgetArea, self.preview_dock)
        self.preview_dock.hide()

        # Guide preview dock (shown when editing a guide)
        from shoggoth.ui.guide_editor import GuidePDFPreviewWidget
        self.guide_preview_dock = QDockWidget(tr("GUIDE_PREVIEW"), self)
        self.guide_preview_dock.setObjectName("guide_preview_dock")
        self.guide_preview_dock.setFeatures(
            QDockWidget.DockWidgetFloatable |
            QDockWidget.DockWidgetMovable |
            QDockWidget.DockWidgetClosable
        )
        self.guide_preview_widget = GuidePDFPreviewWidget()
        self.guide_preview_dock.setWidget(self.guide_preview_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, self.guide_preview_dock)
        self.guide_preview_dock.hide()

        # Set initial splitter sizes
        self.main_splitter.setCollapsible(0, True)
        self.main_splitter.setSizes([300, 700])
        self._tree_width = 300

        # Persist layout changes (debounced by the session manager)
        self.main_splitter.splitterMoved.connect(self._on_layout_changed)
        self.preview_dock.dockLocationChanged.connect(self._on_layout_changed)
        self.preview_dock.topLevelChanged.connect(self._on_layout_changed)
        self.guide_preview_dock.dockLocationChanged.connect(self._on_layout_changed)
        self.guide_preview_dock.topLevelChanged.connect(self._on_layout_changed)

        main_layout.addWidget(self.main_splitter)
        central.setLayout(main_layout)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage(tr("STATUS_READY"))

    # ── Facade: views ─────────────────────────────────────────────────────
    # Kept as window methods because the rest of the app (and shoggoth.app
    # users) call them; implementations live in views.py.

    def show_card(self, card):
        views.show_card(self, card)

    def show_encounter(self, encounter):
        views.show_encounter(self, encounter)

    def show_encounter_set(self, encounter_set):
        """Show encounter set editor (alias for show_encounter)"""
        views.show_encounter(self, encounter_set)

    def show_project(self, project):
        views.show_project(self, project)

    def show_guide(self, guide):
        views.show_guide(self, guide)

    def show_locations(self, encounter_set):
        views.show_locations(self, encounter_set)

    def clear_editor(self):
        views.clear_editor(self)

    def goto_card(self, card_id):
        """Navigate to a specific card by ID"""
        if not self.active_project:
            return
        card = self.active_project.get_card(card_id)
        if card:
            self.show_card(card)
            self.select_item_in_tree(card_id)

    # ── Facade: tree ──────────────────────────────────────────────────────

    def refresh_tree(self):
        self.file_browser.refresh()

    def update_card_in_tree(self, card_id):
        """Update a single card's display in the tree (for name/dirty changes)"""
        return self.file_browser.update_card_node(card_id)

    def select_item_in_tree(self, item_id):
        return self.file_browser.select_item_in_tree(item_id)

    # ── Facade: projects & exports ────────────────────────────────────────

    def open_project(self, file_path):
        projects.open_project(self, file_path)

    def close_project(self, project=None):
        projects.close_project(self, project)

    def new_card_dialog(self):
        projects.new_card_dialog(self)

    def save_changes(self):
        projects.save_changes(self)

    def add_investigator_template(self):
        projects.add_investigator_template(self)

    def open_transfer_cards_dialog(self):
        projects.open_transfer_cards_dialog(self)

    def export_encounter_set(self, encounter_set):
        exports.export_encounter_set(self, encounter_set)

    def open_encounter_set_export_dialog(self, encounter_set=None):
        exports.open_encounter_set_export_dialog(self, encounter_set)

    # ── Facade: preview & persistence ─────────────────────────────────────

    def schedule_preview_update(self):
        self.preview.schedule_update()

    def _on_element_changed(self, project, kind, element_id, changed):
        """Project change-listener. Only the card being shown needs a
        re-render, and only when it actually changed -- so editing (or
        bulk-changing) other cards doesn't trigger a render at all."""
        if kind != 'cards':
            return
        self.update_card_in_tree(element_id)
        if changed and self.current_card and self.current_card.id == element_id:
            self.preview.schedule_update()

    def on_assets_updated(self):
        """Called (on the main thread) after a background asset update writes new files.

        The card shown at startup was rendered (and its defaults loaded) before
        the update finished, so drop everything cached from the old files and
        redraw -- otherwise the update only shows after a restart.
        """
        self.clear_cache()

    def clear_cache(self):
        """Tools -> Clear Cache: drop renderer image/font caches and the
        current card's cached defaults (fallback), then redraw the preview.
        Other cards need no reset: Project.cards builds fresh Card objects
        (and so fresh fallbacks) on every access."""
        self.card_renderer.clear_asset_caches()
        self.card_renderer.clear_illustration_caches()
        if self.current_card:
            self.current_card.reload_fallback()
        self.preview.rerender_now()

    def on_location_connections_changed(self, affected_cards):
        """Refresh preview if the currently-selected card was affected by a connection change"""
        if self.current_card and any(c.id == self.current_card.id for c in affected_cards):
            self.schedule_preview_update()

    @property
    def settings(self):
        """The persistent shoggoth.json settings dict (owned by the session manager)."""
        return self.session.settings

    def save_settings(self):
        self.session.save()

    @property
    def current_project(self):
        """Backward compatibility property"""
        return self.active_project

    # ── Dialogs ───────────────────────────────────────────────────────────

    def show_goto_dialog(self):
        """Show the Go to Card dialog"""
        if not self.active_project:
            QMessageBox.information(self, tr("DLG_NO_PROJECT"), tr("MSG_OPEN_PROJECT_FIRST"))
            return

        dialog = ElementSelectorDialog(
            self.active_project, title=tr("DLG_GOTO_CARD"),
            instructions=tr("HELP_NAVIGATION"), parent=self,
        )
        dialog.element_chosen.connect(self.on_goto_element_selected)
        dialog.exec()

    def on_goto_element_selected(self, entry):
        """Navigate to the element picked in the Go-to dialog."""
        if entry.kind == KIND_GUIDE:
            self.show_guide(entry.obj)
        elif entry.kind == KIND_ENCOUNTER:
            self.show_encounter(entry.obj)
        elif entry.kind == KIND_PROJECT:
            self.show_project(entry.obj)
        else:
            self.show_card(entry.obj)
        self.select_item_in_tree(entry.id)

    def show_command_palette(self):
        """Show the command palette."""
        dialog = CommandPaletteDialog(commands.build_commands(self), self)
        dialog.exec()

    def open_settings(self):
        """Open settings dialog"""
        from shoggoth.settings import SettingsDialog
        dialog = SettingsDialog(self.config, self)
        dialog.exec()

    def reset_assets_dialog(self):
        from shoggoth.ui.updater_ui import ResetAssetsDialog
        confirm = QMessageBox.question(
            self,
            tr("DLG_RESET_ASSETS"),
            tr("MSG_RESET_ASSETS_CONFIRM"),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        dialog = ResetAssetsDialog(self)
        dialog.start_reset()
        dialog.exec()

    # ── View-menu handlers ────────────────────────────────────────────────

    def toggle_preview(self, checked):
        """Toggle the preview dock visibility"""
        if checked:
            self.preview_dock.show()
        else:
            self.preview_dock.hide()

    def toggle_project_tree(self, checked):
        if checked:
            self.main_splitter.setSizes([self._tree_width or 300, 700])
        else:
            self._tree_width = self.main_splitter.sizes()[0] or 300
            self.main_splitter.setSizes([0, 1000])

    def _set_sidebar_view(self, mode):
        """Switch sidebar view mode and persist the setting."""
        self.file_browser.switch_view(mode)
        self.config.set('Shoggoth', 'sidebar_view', mode)
        self.config.save()

    def _on_card_sort_changed(self, index):
        """Persist the card sort order when the user changes it."""
        order = self.file_browser.sort_combo.currentData()
        self.config.set('Shoggoth', 'card_sort_order', order)
        self.config.save()

    def change_language(self, lang_code: str):
        """Change the application language"""
        # Update checkmarks in menu
        for action in self.language_actions:
            action.setChecked(action.data() == lang_code)

        # Save setting
        self.config.set('Shoggoth', 'language', lang_code)
        self.config.save()

        # Load the new language
        load_language(lang_code)

        # Show restart message
        QMessageBox.information(
            self,
            tr("DLG_LANGUAGE_CHANGED"),
            tr("MSG_RESTART_FOR_LANGUAGE")
        )

    # ── File monitoring ───────────────────────────────────────────────────

    def setup_file_monitoring(self):
        """Watch the asset pack for good; the files the shown card uses are added
        as it renders (PreviewController) and dropped when the view changes."""
        self.file_watcher = FileWatcher(self.on_files_changed, trees=[asset_dir])
        self.file_watcher.start()

    def watch_project_file(self, project):
        """Watch an open project's file for outside changes, for as long as it stays open"""
        if project.is_file_backed:
            self.file_watcher.watch_file(project.file_path, pinned=True)

    def unwatch_project_file(self, project):
        if project.is_file_backed:
            self.file_watcher.unwatch_file(project.file_path)

    def on_files_changed(self, paths):
        """Called from the file watcher (background thread) - emit signal for main thread handling"""
        self.file_changed_signal.emit(paths)

    @Slot(object)
    def _handle_file_changed(self, paths):
        """Handle file system changes on main thread - refresh preview when relevant files change"""
        # Project files aren't render inputs; they're checked for outside edits
        project_files = {path_key(p.file_path): p for p in self.open_projects if p.is_file_backed}
        changed_projects = [project_files[k] for k in {path_key(p) for p in paths} if k in project_files]
        if changed_projects:
            paths = {p for p in paths if path_key(p) not in project_files}
            for project in changed_projects:
                projects.check_external_change(self, project)
            if not paths:
                return
        # Read via self: the renderer is replaced on language change
        self.card_renderer.invalidate_files(paths)
        if self.current_card:
            if any(str(p).lower().endswith('.json') for p in paths):
                # template/defaults changes
                self.current_card.reload_fallback()
            self.preview.rerender_now()

    def _check_for_updates_startup(self):
        """Check for updates after startup (deferred to avoid blocking)"""
        if self.update_manager.should_check_for_updates():
            self.update_manager.check_for_updates_async()

    # ── Window events ─────────────────────────────────────────────────────

    def _on_active_project_changed(self, project):
        """Handle active project change from file browser"""
        self.active_project = project
        if project:
            self.status_bar.showMessage(tr("STATUS_ACTIVE").format(name=project['name']))

    def _on_layout_changed(self, *args):
        self.session.schedule_layout_save()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._on_layout_changed()

    def moveEvent(self, event):
        super().moveEvent(event)
        self._on_layout_changed()

    def mousePressEvent(self, event):
        """Handle mouse button presses for back/forward navigation"""
        if event.button() == Qt.BackButton:
            self.nav.back()
            event.accept()
        elif event.button() == Qt.ForwardButton:
            self.nav.forward()
            event.accept()
        else:
            super().mousePressEvent(event)

    def has_unsaved_changes(self):
        """Check if there are any unsaved changes in the active project"""
        return bool(self.active_project and self.active_project.has_unsaved_changes())

    def closeEvent(self, event):
        """Handle window close event - check for unsaved changes"""
        if self.file_watcher:
            self.file_watcher.stop()
        self.cloud.stop_all()
        telemetry.stop_session()
        self.session.capture_layout()
        self.session.save()

        if self.has_unsaved_changes():
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle(tr("DLG_UNSAVED_CHANGES"))
            msg_box.setText(tr("CONFIRM_SAVE_BEFORE_EXIT"))
            msg_box.setIcon(QMessageBox.Question)
            save_btn = msg_box.addButton(tr("DLG_SAVE"), QMessageBox.AcceptRole)
            discard_btn = msg_box.addButton(tr("DLG_DISCARD"), QMessageBox.DestructiveRole)
            msg_box.addButton(tr("DLG_CANCEL"), QMessageBox.RejectRole)
            msg_box.setDefaultButton(save_btn)
            msg_box.exec()

            if msg_box.clickedButton() == save_btn:
                self.save_changes()
                event.accept()
            elif msg_box.clickedButton() == discard_btn:
                event.accept()
            else:  # Cancel
                event.ignore()
        else:
            event.accept()
