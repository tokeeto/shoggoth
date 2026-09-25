import os
import sys
import json
import time
import tempfile
import hashlib
import logging
import requests
import zipfile
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import quote
from shoggoth.files import asset_dir

# App update API endpoints
GITHUB_API_URL = "https://api.github.com/repos/tokeeto/shoggoth/releases/latest"
GITHUB_RELEASES_LIST_URL = "https://api.github.com/repos/tokeeto/shoggoth/releases?per_page=100"
PYPI_API_URL = "https://pypi.org/pypi/shoggoth/json"

# Asset pack constants
ASSETS_REPO = "tokeeto/shoggoth_assets"
ASSETS_API = f"https://api.github.com/repos/{ASSETS_REPO}"
ASSETS_RAW_BASE = f"https://raw.githubusercontent.com/{ASSETS_REPO}"
ASSETS_STATE_FILE = ".asset_state"
ASSET_BRANCH = "v3" # keep in sync with [tool.shoggoth] asset-version in pyproject.toml
_RETRIES = 2              # extra attempts for an asset file that failed to update
_RETRY_DELAY = 2.0        # seconds between attempts, for locks / virus scans to let go
_COMPARE_FILE_LIMIT = 300  # GitHub's compare API lists at most this many files
GITHUB_HEADERS = {"Accept": "application/vnd.github.v3+json", "User-Agent": "Shoggoth-AssetManager"}

logger = logging.getLogger(__name__)


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_blob_sha(data: bytes) -> str:
    """Git's object id for a file's contents. GitHub reports it for every file,
    so a local file can be checked against the remote without downloading it."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _get_local_asset_state() -> tuple[Optional[str], Optional[str], dict]:
    """Return (branch, sha, file_hashes) from the local state file.

    file_hashes maps each asset path to the SHA-256 of what Shoggoth last
    installed there; a file whose contents differ has been changed by the user.
    """
    state_file = asset_dir / ASSETS_STATE_FILE
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text())
            return data.get("branch"), data.get("sha"), data.get("files", {})
        except Exception:
            pass
    return None, None, {}


def _save_local_asset_state(branch: str, sha: Optional[str], file_hashes: Optional[dict] = None) -> None:
    asset_dir.mkdir(parents=True, exist_ok=True)
    data: dict = {"branch": branch, "sha": sha}
    if file_hashes is not None:
        data["files"] = file_hashes
    # write-then-rename: a crash mid-write must not corrupt the state
    state_file = asset_dir / ASSETS_STATE_FILE
    tmp = state_file.with_name(state_file.name + ".part")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, state_file)


def _get_remote_asset_sha(branch: str) -> Optional[str]:
    try:
        response = requests.get(f"{ASSETS_API}/commits/{branch}", headers=GITHUB_HEADERS, timeout=15)
        response.raise_for_status()
        return response.json().get("sha")
    except Exception as e:
        logger.warning(f"Failed to fetch remote asset SHA: {e}")
        return None


def assets_available() -> bool:
    """Return True if a complete asset pack is present locally."""
    if os.environ.get("SHOGGOTH_UNMANAGED_ASSETS"):
        return True
    local_branch, local_sha, _ = _get_local_asset_state()
    return (
        asset_dir.is_dir()
        and local_sha is not None
        and local_branch == ASSET_BRANCH
    )


def _write_verified(target: Path, data: bytes) -> str:
    """Replace `target` with `data` and check that it actually landed on disk.

    The write goes to a temporary file that is renamed over the target, so an
    interrupted write never leaves a half-written asset behind. Reading the
    file back catches everything else (a file locked by another program, a
    virus scanner interfering, ...). Raises on failure; returns the SHA-256.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")
    try:
        tmp.write_bytes(data)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    if _hash_file(target) != digest:
        raise OSError(f"{target} does not contain the new version after writing it")
    return digest


def _retrying(items, action, label: str) -> list:
    """Call action(item) for each item, retrying the ones that raise up to
    _RETRIES more times with a pause in between (a locked file is usually
    released within seconds). Returns the items that still failed."""
    pending = list(items)
    for attempt in range(1 + _RETRIES):
        if attempt:
            time.sleep(_RETRY_DELAY)
            logger.info(f"Retrying {len(pending)} asset file(s) (attempt {attempt + 1})...")
        failed = []
        for item in pending:
            try:
                action(item)
            except Exception as e:
                logger.warning(f"Could not update {label(item)}: {e}")
                failed.append(item)
        pending = failed
        if not pending:
            break
    return pending


def download_full_assets(branch: Optional[str] = None, progress_callback=None) -> dict:
    """Download and extract the complete asset pack from GitHub, overwriting
    every file in it. Raises if any file could not be written.

    Args:
        branch: Asset branch to download. Defaults to ASSET_BRANCH.
        progress_callback: Optional callable(downloaded_bytes: int, total_bytes: int)
            called periodically during the HTTP download phase.

    Returns:
        Dict mapping posix-path strings to SHA-256 hex digests for all extracted files.
    """
    if branch is None:
        branch = ASSET_BRANCH
    zip_url = f"https://github.com/{ASSETS_REPO}/archive/refs/heads/{branch}.zip"
    logger.info(f"Downloading full asset pack from GitHub (branch {branch})...")
    response = requests.get(zip_url, stream=True, timeout=300)
    response.raise_for_status()
    total_size = int(response.headers.get("content-length", 0))
    downloaded = 0
    file_hashes: dict = {}
    # The pack is several hundred MB: spool it to disk, not memory
    with tempfile.TemporaryFile() as archive:
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                archive.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total_size)
        archive.seek(0)
        with zipfile.ZipFile(archive) as zf:
            members = []
            for member in zf.infolist():
                parts = Path(member.filename).parts
                if len(parts) <= 1 or member.filename.endswith("/"):
                    continue  # the root directory entry, or a directory
                members.append((member, Path(*parts[1:])))  # strip 'shoggoth_assets-{branch}/'

            def extract(item):
                member, rel_path = item
                file_hashes[rel_path.as_posix()] = _write_verified(asset_dir / rel_path, zf.read(member))

            failed = _retrying(members, extract, label=lambda item: item[1].as_posix())
    if failed:
        raise RuntimeError(
            "Could not write asset file(s): " + ", ".join(rel.as_posix() for _, rel in failed))
    logger.info("Full asset pack downloaded successfully.")
    return file_hashes


@dataclass
class _Change:
    """One file an asset update touches."""
    path: str
    remove: bool = False
    blob: Optional[str] = None  # git blob sha of the new contents (None: unknown)
    state: str = "update"       # 'update', 'current' (already has the new contents) or 'modified' (changed by the user)
    disk_hash: Optional[str] = None  # SHA-256 of the file on disk, when state == 'current'


@dataclass
class AssetUpdatePlan:
    """What an asset update will do. Built by check_asset_update() (network, no
    writes), carried out by apply_asset_update() -- so the UI can ask the user
    about `modified` files in between."""
    branch: str
    old_sha: Optional[str]
    new_sha: str
    local_hashes: dict
    changes: list = field(default_factory=list)
    full: bool = False  # no usable local pack: download the whole thing

    @property
    def modified(self) -> list[str]:
        """Files the user changed, which this update would overwrite or delete."""
        return [c.path for c in self.changes if c.state == "modified"]


@dataclass
class AssetUpdateResult:
    changed: bool = False                        # files on disk were added, updated or removed
    failed: list = field(default_factory=list)   # paths that could not be updated, even after retries
    skipped: list = field(default_factory=list)  # user-modified paths left alone


def _classify(change: _Change, stored_hash: Optional[str]) -> None:
    """Set change.state by comparing the file on disk with what we last
    installed (stored_hash) and with the new version (change.blob)."""
    target = asset_dir / change.path
    if not target.is_file():
        change.state = "current" if change.remove else "update"
        return
    data = target.read_bytes()
    if not change.remove and change.blob and _git_blob_sha(data) == change.blob:
        # already the new version, e.g. written by an update that got interrupted
        change.state = "current"
        change.disk_hash = hashlib.sha256(data).hexdigest()
    elif stored_hash is None or hashlib.sha256(data).hexdigest() != stored_hash:
        change.state = "modified"
    else:
        change.state = "update"


def _compare_changes(old_sha: str, new_sha: str) -> Optional[list[_Change]]:
    """Files changed between two commits, from GitHub's compare API. Returns
    None when the compare can't be trusted as a list of changes: it lists at
    most _COMPARE_FILE_LIMIT files, and after a force-push the old commit is
    no longer an ancestor of the new one."""
    response = requests.get(f"{ASSETS_API}/compare/{old_sha}...{new_sha}", headers=GITHUB_HEADERS, timeout=30)
    response.raise_for_status()
    data = response.json()
    files = data.get("files", [])
    if data.get("status") != "ahead" or len(files) >= _COMPARE_FILE_LIMIT:
        logger.info(f"Asset compare is {data.get('status')} with {len(files)} file(s); checking every file.")
        return None
    changes = []
    for info in files:
        status, filename = info.get("status"), info.get("filename", "")
        if status == "removed":
            changes.append(_Change(filename, remove=True))
        else:
            changes.append(_Change(filename, blob=info.get("sha")))
            if status == "renamed" and info.get("previous_filename"):
                changes.append(_Change(info["previous_filename"], remove=True))
    return changes


def _tree_changes(sha: str, local_hashes: dict) -> list[_Change]:
    """Every file of the pack at `sha`, plus removals of files we installed
    that are no longer in it. Classification sorts out which need work."""
    response = requests.get(f"{ASSETS_API}/git/trees/{sha}?recursive=1", headers=GITHUB_HEADERS, timeout=30)
    response.raise_for_status()
    data = response.json()
    if data.get("truncated"):
        raise RuntimeError("asset file list from GitHub is truncated")
    remote = {e["path"]: e["sha"] for e in data.get("tree", []) if e.get("type") == "blob"}
    changes = [_Change(path, blob=blob) for path, blob in remote.items()]
    changes += [_Change(path, remove=True) for path in local_hashes if path not in remote]
    return changes


def check_asset_update() -> Optional[AssetUpdatePlan]:
    """Work out what it takes to bring the asset pack up to date. Only reads:
    nothing is written until apply_asset_update().

    Returns None when there is nothing to do: assets are unmanaged
    (SHOGGOTH_UNMANAGED_ASSETS), up to date, or GitHub can't be reached and
    no files are missing. Raises if no local pack exists and it can't be
    downloaded, or if the list of changes can't be fetched.
    """
    if os.environ.get("SHOGGOTH_UNMANAGED_ASSETS"):
        logger.info("SHOGGOTH_UNMANAGED_ASSETS is set; skipping asset update.")
        return None

    branch = ASSET_BRANCH
    local_branch, local_sha, local_hashes = _get_local_asset_state()
    remote_sha = _get_remote_asset_sha(branch)

    if not assets_available():
        # First run, lost state, or a branch change (app upgrade)
        if remote_sha is None:
            raise RuntimeError("Cannot download assets: network unavailable and no local assets found.")
        if local_branch and local_branch != branch:
            logger.info(f"Asset branch changed ({local_branch} -> {branch}); re-downloading.")
        return AssetUpdatePlan(branch, local_sha, remote_sha, {}, full=True)

    if remote_sha is None or remote_sha == local_sha:
        if remote_sha is None:
            logger.warning("Could not check for asset updates; using existing files.")
        else:
            logger.info("Assets are up to date.")
        # still restore files that went missing (contents unknown, so no blob check)
        changes = [_Change(p) for p in local_hashes if not (asset_dir / p).exists()]
        if not changes:
            return None
        logger.info(f"{len(changes)} asset file(s) are missing; restoring them.")
        return AssetUpdatePlan(branch, local_sha, local_sha, local_hashes, changes)

    logger.info(f"Checking for asset updates ({local_sha[:8]}...{remote_sha[:8]})...")
    try:
        changes = _compare_changes(local_sha, remote_sha)
    except Exception as e:
        # e.g. 404: a force-push dropped our old commit
        logger.warning(f"Asset compare failed ({e}); checking every file.")
        changes = None
    if changes is None:
        changes = _tree_changes(remote_sha, local_hashes)

    # A case-only rename (Foo.png -> foo.png) is the same file on Windows and
    # macOS: removing the old name would delete the new file.
    written = {c.path.lower() for c in changes if not c.remove}
    changes = [c for c in changes if not (c.remove and c.path.lower() in written)]

    by_lower = {p.lower(): h for p, h in local_hashes.items()}
    for change in changes:
        _classify(change, local_hashes.get(change.path, by_lower.get(change.path.lower())))
    return AssetUpdatePlan(branch, local_sha, remote_sha, local_hashes, changes)


def apply_asset_update(plan: AssetUpdatePlan, overwrite_modified: bool = False) -> AssetUpdateResult:
    """Carry out a plan from check_asset_update().

    User-modified files are left alone unless `overwrite_modified`. Files that
    fail to update (locked, interrupted, not what we wrote) are retried
    _RETRIES more times. The state file only moves to the new commit when
    every change landed, so skipped or failed files are picked up again on
    the next launch; progress is saved as we go, so an update that gets
    interrupted (e.g. the app is closed) resumes cleanly.
    """
    result = AssetUpdateResult()
    if plan.full:
        file_hashes = download_full_assets(plan.branch)
        _save_local_asset_state(plan.branch, plan.new_sha, file_hashes)
        result.changed = True
        return result

    hashes = dict(plan.local_hashes)
    pending = []
    for change in plan.changes:
        if change.state == "modified" and not overwrite_modified:
            logger.info(f"Keeping user-modified asset file: {change.path}")
            result.skipped.append(change.path)
        elif change.state == "current":
            if change.remove:
                hashes.pop(change.path, None)
            else:
                hashes[change.path] = change.disk_hash
        else:
            pending.append(change)

    if pending:
        logger.info(f"Updating {len(pending)} asset file(s)...")
    done = 0

    def apply(change: _Change):
        nonlocal done
        target = asset_dir / change.path
        if change.remove:
            target.unlink(missing_ok=True)
            if target.exists():
                raise OSError("file is still there after deleting it")
            hashes.pop(change.path, None)
            logger.info(f"Removed: {change.path}")
        else:
            response = requests.get(f"{ASSETS_RAW_BASE}/{plan.new_sha}/{quote(change.path)}", timeout=30)
            response.raise_for_status()
            if change.blob and _git_blob_sha(response.content) != change.blob:
                raise OSError("downloaded contents don't match GitHub's checksum")
            hashes[change.path] = _write_verified(target, response.content)
            # a case-only rename leaves the old spelling in the state
            for stale in [p for p in hashes if p != change.path and p.lower() == change.path.lower()]:
                del hashes[stale]
            logger.info(f"Updated: {change.path}")
        result.changed = True
        done += 1
        if done % 20 == 0:
            _save_local_asset_state(plan.branch, plan.old_sha, hashes)

    failed = _retrying(pending, apply, label=lambda c: c.path)
    result.failed = [c.path for c in failed]

    complete = not (result.failed or result.skipped)
    _save_local_asset_state(plan.branch, plan.new_sha if complete else plan.old_sha, hashes)
    if result.failed:
        logger.error(f"{len(result.failed)} asset file(s) could not be updated: {', '.join(result.failed)}")
    return result


def reset_assets(branch: Optional[str] = None, progress_callback=None) -> None:
    """Force a full re-download of the asset pack, overwriting all local files."""
    if branch is None:
        branch = ASSET_BRANCH
    remote_sha = _get_remote_asset_sha(branch)
    if remote_sha is None:
        raise RuntimeError("Cannot reset assets: network unavailable.")
    file_hashes = download_full_assets(branch, progress_callback=progress_callback)
    _save_local_asset_state(branch, remote_sha, file_hashes)


def ensure_assets_current(overwrite_modified: bool = False) -> bool:
    """Non-interactive update (CLI modes): check_asset_update() +
    apply_asset_update(). User-modified files are kept unless
    `overwrite_modified`. Returns True if any asset files changed on disk."""
    plan = check_asset_update()
    if plan is None:
        return False
    result = apply_asset_update(plan, overwrite_modified)
    if result.skipped:
        logger.warning(
            f"Kept {len(result.skipped)} user-modified asset file(s); the asset update "
            f"is incomplete until they are replaced: {', '.join(result.skipped)}")
    return result.changed


class InstallationType(Enum):
    """How Shoggoth was installed"""
    PYPI = "pypi"           # pip install shoggoth
    BINARY = "binary"       # PyInstaller frozen exe
    DEVELOPMENT = "dev"     # Running from source (uv run, pip -e)


@dataclass
class VersionInfo:
    """Information about an available version"""
    version: str
    download_url: Optional[str] = None
    release_notes: Optional[str] = None
    published_at: Optional[str] = None


def get_current_version() -> str:
    """Get current version from package metadata"""
    try:
        from importlib.metadata import version
        return version("shoggoth")
    except Exception:
        return "unknown"


def detect_installation_type() -> InstallationType:
    """Detect how Shoggoth was installed"""
    if getattr(sys, 'frozen', False):
        return InstallationType.BINARY

    try:
        from importlib.metadata import distribution
        dist = distribution('shoggoth')
        try:
            direct_url_text = dist.read_text('direct_url.json')
            if direct_url_text:
                direct_url = json.loads(direct_url_text)
                if direct_url.get('dir_info', {}).get('editable', False):
                    return InstallationType.DEVELOPMENT
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        return InstallationType.PYPI
    except Exception:
        return InstallationType.DEVELOPMENT


def cleanup_old_binary() -> None:
    """Delete leftover *_old.exe files from a previous Windows in-place update."""
    if not getattr(sys, 'frozen', False) or sys.platform != 'win32':
        return
    exe_dir = Path(sys.executable).parent
    for old_exe in exe_dir.glob('*_old.exe'):
        try:
            old_exe.unlink()
            logger.info(f"Cleaned up old binary: {old_exe.name}")
        except Exception as e:
            logger.warning(f"Could not remove old binary {old_exe.name}: {e}")


def compare_versions(current: str, latest: str) -> bool:
    """Return True if latest > current."""
    def normalize(v: str) -> tuple:
        v = v.lstrip('v')
        parts = v.replace('-', '.').replace('_', '.').split('.')
        result = []
        for part in parts:
            try:
                result.append((0, int(part)))
            except ValueError:
                result.append((1, part))
        return tuple(result)

    try:
        from packaging.version import Version
        return Version(latest.lstrip('v')) > Version(current.lstrip('v'))
    except ImportError:
        return normalize(latest) > normalize(current)
    except Exception:
        return latest.lstrip('v') != current.lstrip('v')
