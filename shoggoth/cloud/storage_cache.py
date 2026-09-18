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
"""
from pathlib import Path

from shoggoth import files
from shoggoth.cloud import client

_SCHEME = 'cloud://'


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


def get_cached(uri: str, base_url: str | None = None, token: str | None = None) -> Path | None:
    """Returns the local cached `Path` for a `cloud://...` reference,
    downloading it first if it's not already cached. `None` if the uri is
    malformed, no token is available, or the download fails (e.g. offline,
    file deleted server-side, no access) -- callers already treat a `None`
    find_file() result as "couldn't resolve this path", same as a missing
    local file."""
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

    try:
        return client.download_storage_file(base_url, token, storage_project_id, rel_path, dest)
    except client.PublishError:
        return None


def invalidate(storage_project_id: str, rel_path: str) -> None:
    """Drops one cached file so the next resolve re-downloads it -- called
    when a sync event (shoggoth.cloud.sync) reports a resource changed."""
    path = cache_path(storage_project_id, rel_path)
    path.unlink(missing_ok=True)
