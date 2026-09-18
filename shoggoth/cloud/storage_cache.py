"""Resolves `cloud://<storage_project_id>/<rel/path>` resource references to
a local cached file, downloading on first use -- the storage-project
equivalent of a raw filesystem path or an http(s) URL, wired into
`Project.find_file()` (see project.py) as the single resolution point for
every illustration/image/font path field in the codebase.

Deliberately Qt-free (reads credentials straight off the same `QSettings`
store `shoggoth.settings.SettingsManager` writes to, via `QtCore.QSettings`
directly rather than importing the full `SettingsManager` class, which pulls
in QtWidgets) -- `find_file()` is called from `renderer/card_renderer.py`,
which CLAUDE.md documents as having zero Qt dependency so it can run in
headless render mode (`-r`, no QApplication at all). `QtCore.QSettings`
itself needs no display/QApplication, so this stays safe there too.

No per-render network re-check once a resource is cached locally -- a
`cloud://` reference resolves instantly after the first download, same
posture as this codebase's local-path/http(s)-URL cases. Cache entries are
only refreshed by an explicit sync event (see shoggoth.cloud.sync), never
proactively invalidated here.

**Blocking vs. async on a cache miss**: by default `get_cached()` blocks
until the download finishes -- correct behavior for exports and headless
render mode (`-r`), where silently producing an image-less result would be
a real bug, and for the already-backgrounded debounced preview re-render
thread, where blocking doesn't freeze anything. The two exceptions are the
*synchronous, main-thread* first-paint paths -- `PreviewController.
render_current_sync()` and `IllustrationWidget`'s pan/zoom preview -- where
blocking on a slow connection freezes the whole UI for however long the
download takes. Those wrap their call in the `prefer_async` context manager
below: a cache miss there returns `None` immediately (rendering proceeds
without that image, same as any other "not found" case) and kicks off a
background download; `on_download_complete` listeners (see
shoggoth.cloud.sync.CloudSyncController) get notified once it lands so the
UI can re-render and pick it up.
"""
import contextvars
import threading
from pathlib import Path

from shoggoth import files
from shoggoth.cloud import client

_SCHEME = 'cloud://'

_prefer_async = contextvars.ContextVar('cloud_prefer_async', default=False)
_in_flight: set[tuple[str, str]] = set()
_in_flight_lock = threading.Lock()
_listeners: list = []


class prefer_async:
    """Context manager: within this call stack (same thread only --
    contextvars don't cross a `threading.Thread` boundary on their own), a
    `cloud://` cache miss becomes non-blocking. See module docstring."""

    def __enter__(self):
        self._token = _prefer_async.set(True)
        return self

    def __exit__(self, exc_type, exc, tb):
        _prefer_async.reset(self._token)


def on_download_complete(callback) -> None:
    """Registers `callback()` (no args) to be invoked -- from whatever
    background thread the download happened to run on -- every time a
    `cloud://` fetch finishes, success or failure. Deliberately Qt-free
    here; CloudSyncController is the one caller, and hands this a callable
    that just re-emits a Qt Signal (itself thread-safe), which is how the
    cross-thread hop to the main/GUI thread actually happens."""
    _listeners.append(callback)


def _notify_listeners() -> None:
    for callback in _listeners:
        try:
            callback()
        except Exception:  # noqa: BLE001 -- a misbehaving listener must not break the fetch
            pass


def is_cloud_uri(path) -> bool:
    return str(path).startswith(_SCHEME)


def _credentials() -> tuple[str, str]:
    from PySide6.QtCore import QSettings

    settings = QSettings("Shoggoth", "Shoggoth")
    base_url = settings.value("publish_base_url", "https://celaeno.cards")
    token = settings.value("publish_token", "")
    return base_url, token


def _parse(uri: str) -> tuple[str, str] | None:
    rest = uri[len(_SCHEME):]
    if '/' not in rest:
        return None
    storage_project_id, rel_path = rest.split('/', 1)
    if not storage_project_id or not rel_path:
        return None
    return storage_project_id, rel_path


def cache_path(storage_project_id: str, rel_path: str) -> Path:
    return files.cloud_cache_dir / storage_project_id / rel_path


def _fetch_in_background(base_url: str, token: str, storage_project_id: str, rel_path: str, dest: Path):
    key = (storage_project_id, rel_path)
    with _in_flight_lock:
        if key in _in_flight:
            return  # already downloading -- the caller already in flight will notify on completion
        _in_flight.add(key)

    def run():
        try:
            client.download_storage_file(base_url, token, storage_project_id, rel_path, dest)
        except client.PublishError:
            pass
        finally:
            with _in_flight_lock:
                _in_flight.discard(key)
            _notify_listeners()

    threading.Thread(target=run, daemon=True).start()


def get_cached(uri: str, base_url: str | None = None, token: str | None = None) -> Path | None:
    """Returns the local cached `Path` for a `cloud://...` reference,
    downloading it first if it's not already cached. `None` if the uri is
    malformed, no token is available, or the download fails (e.g. offline,
    file deleted server-side, no access) -- callers already treat a `None`
    find_file() result as "couldn't resolve this path", same as a missing
    local file. Also `None` (without waiting) on a cache miss inside a
    `prefer_async` block -- see module docstring."""
    parsed = _parse(uri)
    if parsed is None:
        return None
    storage_project_id, rel_path = parsed

    dest = cache_path(storage_project_id, rel_path)
    if dest.exists():
        return dest

    if base_url is None or token is None:
        base_url, token = _credentials()
    if not token:
        return None

    if _prefer_async.get():
        _fetch_in_background(base_url, token, storage_project_id, rel_path, dest)
        return None

    try:
        return client.download_storage_file(base_url, token, storage_project_id, rel_path, dest)
    except client.PublishError:
        return None


def invalidate(storage_project_id: str, rel_path: str) -> None:
    """Drops one cached file so the next resolve re-downloads it -- called
    when a sync event (shoggoth.cloud.sync) reports a resource changed."""
    path = cache_path(storage_project_id, rel_path)
    path.unlink(missing_ok=True)
