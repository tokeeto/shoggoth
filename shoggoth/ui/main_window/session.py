"""
Persistence of window layout, open projects, and last selection.

SessionManager owns the settings dict backed by shoggoth.json in the
user data directory (distinct from SettingsManager, which handles the
INI-style application preferences).
"""
import base64
import json

from PySide6.QtCore import QByteArray, QTimer

from shoggoth.files import root_dir


class SessionManager:
    def __init__(self, window):
        self.window = window

        settings_file = root_dir / 'shoggoth.json'
        if settings_file.exists():
            with open(settings_file, 'r') as f:
                self.settings = json.load(f)
        else:
            self.settings = {'session': {}, 'last_paths': {}}

        # Debounce timer for persisting layout changes
        self._layout_save_timer = QTimer()
        self._layout_save_timer.setSingleShot(True)
        self._layout_save_timer.setInterval(500)
        self._layout_save_timer.timeout.connect(self.save_layout)

    def save(self):
        """Flush self.settings to disk. Does not snapshot live window state."""
        with open(root_dir / 'shoggoth.json', 'w') as f:
            json.dump(self.settings, f)

    def schedule_layout_save(self):
        """Restart the debounce timer; saves the layout 500ms after the last change."""
        self._layout_save_timer.start()

    def capture_layout(self):
        """Snapshot current window/splitter state into self.settings (no I/O)."""
        window = self.window
        session = self.settings.setdefault('session', {})
        session['window_geometry'] = base64.b64encode(bytes(window.saveGeometry())).decode('ascii')
        session['window_state'] = base64.b64encode(bytes(window.saveState())).decode('ascii')
        session['splitter_sizes'] = window.main_splitter.sizes()

    def save_layout(self):
        """Capture layout and flush to disk (called by the debounce timer)."""
        self.capture_layout()
        self.save()

    def set_last_selected(self, element_id, element_type):
        """Record the last viewed element and persist the session."""
        self.settings['session']['last_id'] = element_id
        self.settings['session']['last_type'] = element_type
        self.save_session()

    def save_session(self):
        """Save current session state (open projects and active project)"""
        window = self.window
        regular = [p.file_path for p in window.open_projects
                   if not getattr(p, '_translation', None)]
        trans = [p._node_id_path for p in window.open_projects
                 if getattr(p, '_translation', None)]
        active_path = (getattr(window.active_project, '_node_id_path', window.active_project.file_path)
                       if window.active_project else None)
        self.settings['session']['open_projects'] = regular
        self.settings['session']['open_translations'] = trans
        self.settings['session']['active_project'] = active_path
        # Keep legacy 'project' key for backward compatibility
        self.settings['session']['project'] = active_path
        self.save()

    def restore(self):
        """Restore previous session"""
        from shoggoth.ui.main_window import projects

        window = self.window
        session = self.settings.get('session', {})

        # Support for multiple open projects
        open_project_paths = session.get('open_projects', [])
        open_translation_paths = session.get('open_translations', [])
        active_project_path = session.get('active_project', session.get('project'))

        # Fallback for old sessions that stored only a single project path.
        # Only apply when there are no translations recorded; if the active path
        # matches a translation we must not open it as a plain project.
        if not open_project_paths and not open_translation_paths and active_project_path:
            open_project_paths = [active_project_path]

        for project_path in open_project_paths:
            try:
                projects.open_project(window, project_path)
            except Exception as e:
                print(f"Error restoring project {project_path}: {e}")

        for trans_path in open_translation_paths:
            try:
                projects.open_translation(window, trans_path)
            except Exception as e:
                print(f"Error restoring translation {trans_path}: {e}")

        # Set the active project — match by _node_id_path for translations,
        # file_path for regular projects.
        if active_project_path:
            for project in window.open_projects:
                path = getattr(project, '_node_id_path', project.file_path)
                if path == active_project_path:
                    window.file_browser.set_active_project(project)
                    break

        # Restore window geometry before show() so it appears at the right size.
        if geo := session.get('window_geometry'):
            window.restoreGeometry(QByteArray(base64.b64decode(geo)))

        # Dock state and splitter sizes must be deferred: Qt resets them when
        # the window is shown for the first time, so we apply them after show().
        state = session.get('window_state')
        sizes = session.get('splitter_sizes')

        def _restore_layout():
            if state:
                window.restoreState(QByteArray(base64.b64decode(state)))
            if sizes:
                window.main_splitter.setSizes(sizes)
        QTimer.singleShot(0, _restore_layout)

        # Restore last selected element
        if last_id := session.get('last_id'):
            last_type = session.get('last_type', 'card')
            QTimer.singleShot(100, lambda: self._restore_last_element(last_id, last_type))

    def _restore_last_element(self, element_id, element_type):
        """Restore the last selected element by ID and type"""
        window = self.window
        if not window.active_project:
            return

        element = None
        if element_type == 'card':
            element = window.active_project.get_card(element_id)
            if element:
                window.show_card(element)
        elif element_type == 'encounter':
            element = window.active_project.get_encounter_set(element_id)
            if element:
                window.show_encounter(element)
        elif element_type == 'guide':
            element = window.active_project.get_guide(element_id)
            if element:
                window.show_guide(element)
        elif element_type == 'locations':
            element = window.active_project.get_encounter_set(element_id)
            if element:
                window.show_locations(element)

        # Select in tree if element was found
        if element:
            window.select_item_in_tree(element_id)
