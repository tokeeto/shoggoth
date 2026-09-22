"""File-change detection for the live card preview.

One `FileWatcher` owns the app's single watchdog Observer (on Linux: one
inotify instance, which is a scarce per-user resource) and serves two needs:

- *trees*: directories watched recursively where any change counts (the asset
  pack);
- *files*: individual files the current card depends on (illustrations, icons,
  fonts, project-local defaults). The renderer reports them as it uses them
  (`CardRenderer.track_files`); only their parent directories are watched, and
  only until `clear_files()` is called (when the user leaves the card).
  *Pinned* files (`watch_file(path, pinned=True)`, e.g. open project files)
  are the exception: they stay watched until `unwatch_file()`.

Events are coalesced: the callback fires once, `debounce` seconds after the
last event, so a file that is still being written (or an asset-pack update
touching hundreds of files) produces a single refresh, after it settled.
"""

import logging
import os
import threading

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from shoggoth.files import path_key

logging.getLogger('watchdog').setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Only these change a file. Opened/closed events are emitted by *reading* a
# file too, so reacting to them would turn every re-render into a new trigger.
_CHANGE_EVENTS = ('created', 'modified', 'deleted', 'moved')


class _Handler(FileSystemEventHandler):
    def __init__(self, watcher):
        super().__init__()
        self.watcher = watcher

    def on_any_event(self, event):
        if event.is_directory or event.event_type not in _CHANGE_EVENTS:
            return
        self.watcher._on_event(event.src_path)
        # Atomic saves (write temp file, rename over the target) arrive as a move
        if event.event_type == 'moved' and event.dest_path:
            self.watcher._on_event(event.dest_path)


class FileWatcher:
    """Thread-safe. `callback(paths)` is called on a background timer thread
    with a set of path strings: for a watched file, the path exactly as it was
    registered (so it matches the caller's own cache keys); for a change inside
    a watched tree, the path of the changed file."""

    def __init__(self, callback, trees=(), debounce=0.15):
        self.callback = callback
        self.debounce = debounce
        # Two locks, never nested. `_lock` guards what the event handler reads
        # (the watched files, the pending batch). `_observer_lock` serializes
        # calls into the observer: watchdog dispatches events while holding its
        # own lock, so calling schedule()/unschedule() with `_lock` held would
        # deadlock against a handler waiting for `_lock`.
        self._lock = threading.Lock()
        self._observer_lock = threading.Lock()
        self._observer = None
        self._handler = _Handler(self)
        self._trees = [str(t) for t in trees]
        self._tree_keys = [path_key(t) for t in self._trees]
        self._registered = set()   # paths as given to watch_file (fast duplicate check)
        self._pinned = set()       # registered paths that clear_files() keeps
        self._files = {}           # path_key(real path) -> {paths as given}
        self._dir_watches = {}     # path_key(real dir) -> ObservedWatch (or None)
        self._pending = set()
        self._timer = None

    # ── lifecycle ─────────────────────────────────────────────────────────

    def start(self):
        with self._observer_lock:
            if self._observer:
                return
            observer = Observer()
            observer.daemon = True
            for tree in self._trees:
                if os.path.isdir(tree):
                    observer.schedule(self._handler, tree, recursive=True)
            observer.start()
            self._observer = observer
        with self._lock:
            registered = list(self._registered)
        for path in registered:
            self._watch_parent(path)

    def stop(self):
        with self._observer_lock:
            observer, self._observer = self._observer, None
            self._dir_watches.clear()
        with self._lock:
            if self._timer:
                self._timer.cancel()
                self._timer = None
            self._pending.clear()
        if observer:
            observer.stop()
            observer.join()

    # ── file registration ─────────────────────────────────────────────────

    def watch_file(self, path, pinned=False):
        """Start watching a file (idempotent, cheap when already watched, and
        safe to call from any thread). A pinned file survives `clear_files()`."""
        path = str(path)
        if path in self._registered and (not pinned or path in self._pinned):
            return
        real = os.path.realpath(path)
        with self._lock:
            self._registered.add(path)
            if pinned:
                self._pinned.add(path)
            self._files.setdefault(path_key(real), set()).add(path)
        self._watch_parent(path)

    def unwatch_file(self, path):
        """Stop watching a file, pinned or not, and release its directory watch
        if nothing else needs it."""
        path = str(path)
        key = path_key(os.path.realpath(path))
        with self._lock:
            self._pinned.discard(path)
            self._registered.discard(path)
            paths = self._files.get(key)
            if paths:
                paths.discard(path)
                if not paths:
                    del self._files[key]
        self._release_unneeded_dirs()

    def clear_files(self):
        """Forget every watched file except the pinned ones, and release the
        directory watches that only existed for the others."""
        with self._lock:
            self._registered = set(self._pinned)
            self._files = {}
            for path in self._pinned:
                self._files.setdefault(path_key(os.path.realpath(path)), set()).add(path)
        self._release_unneeded_dirs()

    def _release_unneeded_dirs(self):
        with self._lock:
            registered = list(self._registered)
        keep = {path_key(os.path.dirname(os.path.realpath(p))) for p in registered}
        with self._observer_lock:
            for key in [k for k in self._dir_watches if k not in keep]:
                watch = self._dir_watches.pop(key)
                if watch and self._observer:
                    self._observer.unschedule(watch)

    def _watch_parent(self, path):
        """Watch `path`'s directory (non-recursively) unless a tree covers it."""
        directory = os.path.dirname(os.path.realpath(path))
        key = path_key(directory)
        with self._observer_lock:
            if not self._observer or key in self._dir_watches or self._in_tree(key):
                return
            try:
                self._dir_watches[key] = self._observer.schedule(
                    self._handler, directory, recursive=False)
            except OSError as e:
                # Missing directory, or the system's inotify watch limit
                logger.warning('Cannot watch %s: %s', directory, e)
                self._dir_watches[key] = None  # don't retry on every render

    def _in_tree(self, key):
        return any(key == root or key.startswith(root + os.sep) for root in self._tree_keys)

    # ── events ────────────────────────────────────────────────────────────

    def _on_event(self, path):
        key = path_key(path)
        with self._lock:
            hits = set(self._files.get(key, ()))
            if not hits and self._in_tree(key):
                hits.add(path)
            if not hits:
                return
            self._pending |= hits
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce, self._flush)
            self._timer.daemon = True
            self._timer.start()

    def _flush(self):
        with self._lock:
            paths, self._pending = self._pending, set()
            self._timer = None
        if paths:
            try:
                self.callback(paths)
            except Exception:
                logger.exception('file change callback failed')
