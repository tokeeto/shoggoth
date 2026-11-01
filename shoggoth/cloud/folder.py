"""Where cloud projects live on disk, and the small per-project state files
that sync keeps next to them.

A cloud project is an ordinary project folder that happens to sit under
`files.cloud_cache_dir / <provider> /` (e.g. `.../cloud_cache/celaeno/<id>/`).
Because it's a real folder, a relative path like `images/foo.png` in a card
needs no special handling anywhere in the app -- `Project.find_file()`
resolves it against the project folder like it always has, and sync's only
job is keeping that folder in step with the server. Pure logic, no Qt.
"""
import json
import os
from pathlib import Path

from shoggoth import files
from shoggoth.guide_file import SUFFIX as GUIDE_SUFFIX

PROVIDER = 'celaeno'
PROJECT_FILE = 'project.shoggoth'
STATE_DIR = '.celaeno'
_MANIFEST = 'files.json'
_BASE = 'base.json'


def provider_dir(provider: str = PROVIDER) -> Path:
    return files.cloud_cache_dir / provider


def project_dir(cloud_id: str, provider: str = PROVIDER) -> Path:
    return provider_dir(provider) / cloud_id


def project_file(cloud_id: str, provider: str = PROVIDER) -> Path:
    return project_dir(cloud_id, provider) / PROJECT_FILE


def is_in_cloud_cache(path, provider: str = PROVIDER) -> bool:
    """Whether a path lies inside the provider's cloud folder -- how opening
    a project decides it should be attached to cloud sync at all."""
    try:
        Path(path).resolve().relative_to(provider_dir(provider).resolve())
        return True
    except ValueError:
        return False


def is_ignored(rel_path: str, project_name: str = PROJECT_FILE) -> bool:
    """Files sync must never upload/download as resources: dotfiles and
    dot-folders (including our own state dir), atomic-write temp files, and
    the project file itself and guide files (which travel inside the
    project's JSON, not as resources)."""
    parts = Path(rel_path).parts
    if any(part.startswith('.') for part in parts):
        return True
    name = parts[-1] if parts else ''
    return name.endswith('.tmp') or name.endswith(GUIDE_SUFFIX) or rel_path == project_name


def rel_posix(root: Path, path) -> str | None:
    """`path` relative to `root` as a '/'-separated string (the server's
    path shape), or None if it isn't inside root."""
    try:
        return Path(path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def local_files(root: Path, project_name: str = PROJECT_FILE):
    """Yields the rel-posix path of every syncable file currently in a
    project folder."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith('.')]
        for filename in filenames:
            rel = rel_posix(root, Path(dirpath) / filename)
            if rel and not is_ignored(rel, project_name):
                yield rel


# --- the resource manifest --------------------------------------------------
# What we last knew about each synced file: the server's etag plus the local
# size/mtime we observed right after writing (downloading) or uploading it.
# A file whose current size/mtime still matches its record hasn't been touched
# since -- that's how the folder monitor tells "a file we just downloaded"
# apart from "a file the user added or edited", which must go up to the server.

def _manifest_path(root: Path) -> Path:
    return root / STATE_DIR / _MANIFEST


def read_manifest(root: Path) -> dict:
    try:
        return json.loads(_manifest_path(root).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def write_manifest(root: Path, manifest: dict) -> None:
    path = _manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(manifest), encoding='utf-8')
    os.replace(tmp, path)


def observe(root: Path, rel_path: str, etag) -> dict:
    """A manifest record for a file as it currently sits on disk."""
    stat = (root / rel_path).stat()
    return {'etag': etag, 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def is_untouched(root: Path, rel_path: str, manifest: dict) -> bool:
    """True if the file on disk still matches what sync last wrote/uploaded
    for it (so it needs no upload)."""
    record = manifest.get(rel_path)
    if not record:
        return False
    try:
        stat = (root / rel_path).stat()
    except OSError:
        return False
    return record.get('size') == stat.st_size and record.get('mtime_ns') == stat.st_mtime_ns


# --- the sync base ----------------------------------------------------------
# What the cloud held for each element when we last agreed on it, as content
# fingerprints (see shoggoth.cloud.merge). Kept beside the project rather than
# in it, so editing the project file by hand can't touch it.

def read_base(root: Path) -> dict:
    try:
        base = json.loads((root / STATE_DIR / _BASE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return base if isinstance(base, dict) else {}


def write_base(root: Path, base: dict) -> None:
    path = root / STATE_DIR / _BASE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(base), encoding='utf-8')
    os.replace(tmp, path)
