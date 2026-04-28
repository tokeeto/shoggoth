import io
import sys
import json
import hashlib
import logging
import requests
import zipfile
from pathlib import Path
from enum import Enum
from dataclasses import dataclass
from typing import Optional
from shoggoth.files import asset_dir

# App update API endpoints
GITHUB_API_URL = "https://api.github.com/repos/tokeeto/shoggoth/releases/latest"
PYPI_API_URL = "https://pypi.org/pypi/shoggoth/json"

# Asset pack constants
ASSETS_REPO = "tokeeto/shoggoth_assets"
ASSETS_API = f"https://api.github.com/repos/{ASSETS_REPO}"
ASSETS_RAW_BASE = f"https://raw.githubusercontent.com/{ASSETS_REPO}"
ASSETS_STATE_FILE = ".asset_state"
ASSET_BRANCH = "v1"  # keep in sync with [tool.shoggoth] asset-version in pyproject.toml
GITHUB_HEADERS = {"Accept": "application/vnd.github.v3+json", "User-Agent": "Shoggoth-AssetManager"}

logger = logging.getLogger(__name__)


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_git_repo(directory: Path) -> bool:
    return (directory / ".git").exists()


def _get_local_asset_state() -> tuple[Optional[str], Optional[str], dict]:
    """Return (branch, sha, file_hashes) from the local state file."""
    state_file = asset_dir / ASSETS_STATE_FILE
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text())
            return data.get("branch"), data.get("sha"), data.get("files", {})
        except Exception:
            pass
    return None, None, {}


def _save_local_asset_state(branch: str, sha: str, file_hashes: Optional[dict] = None) -> None:
    asset_dir.mkdir(parents=True, exist_ok=True)
    data: dict = {"branch": branch, "sha": sha}
    if file_hashes is not None:
        data["files"] = file_hashes
    (asset_dir / ASSETS_STATE_FILE).write_text(json.dumps(data))


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
    local_branch, local_sha, _ = _get_local_asset_state()
    return (
        asset_dir.is_dir()
        and local_sha is not None
        and local_branch == ASSET_BRANCH
    )


def download_full_assets(branch: Optional[str] = None, progress_callback=None) -> dict:
    """Download and extract the complete asset pack from GitHub.

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
    chunks = []
    for chunk in response.iter_content(chunk_size=65536):
        if chunk:
            chunks.append(chunk)
            downloaded += len(chunk)
            if progress_callback:
                progress_callback(downloaded, total_size)
    data = b"".join(chunks)
    file_hashes: dict = {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for member in zf.infolist():
            parts = Path(member.filename).parts
            if len(parts) <= 1:
                continue  # skip the root directory entry itself
            rel_path = Path(*parts[1:])  # strip 'shoggoth_assets-{branch}/' prefix
            target = asset_dir / rel_path
            if member.filename.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src:
                    target.write_bytes(src.read())
                file_hashes[rel_path.as_posix()] = _hash_file(target)
    logger.info("Full asset pack downloaded successfully.")
    return file_hashes


def _update_changed_assets(old_sha: str, new_sha: str, local_hashes: dict) -> dict:
    """Download only files changed between two commits.

    Skips files whose on-disk hash differs from the stored hash (user-modified).
    Returns an updated copy of local_hashes.
    """
    logger.info(f"Checking for asset updates ({old_sha[:8]}...{new_sha[:8]})...")
    response = requests.get(
        f"{ASSETS_API}/compare/{old_sha}...{new_sha}",
        headers=GITHUB_HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    files = response.json().get("files", [])
    if not files:
        logger.info("No asset files changed.")
        return local_hashes
    logger.info(f"Updating {len(files)} changed asset file(s)...")
    updated_hashes = dict(local_hashes)
    for file_info in files:
        status = file_info.get("status")
        filename = file_info.get("filename", "")
        target = asset_dir / filename
        if status == "removed":
            if target.exists():
                stored_hash = local_hashes.get(filename)
                if stored_hash and _hash_file(target) != stored_hash:
                    logger.info(f"Skipping removal of user-modified file: {filename}")
                    continue
                target.unlink()
                logger.info(f"Removed: {filename}")
            updated_hashes.pop(filename, None)
        else:
            stored_hash = local_hashes.get(filename)
            if stored_hash and target.exists() and _hash_file(target) != stored_hash:
                logger.info(f"Skipping user-modified file: {filename}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            raw_url = f"{ASSETS_RAW_BASE}/{new_sha}/{filename}"
            file_resp = requests.get(raw_url, timeout=30)
            file_resp.raise_for_status()
            target.write_bytes(file_resp.content)
            updated_hashes[filename] = _hash_file(target)
            if status == "renamed":
                prev = file_info.get("previous_filename", "")
                if prev:
                    old_target = asset_dir / prev
                    if old_target.exists():
                        old_target.unlink()
                    updated_hashes.pop(prev, None)
                logger.info(f"Renamed: {prev} -> {filename}")
            else:
                logger.info(f"{status.capitalize()}: {filename}")
    return updated_hashes


def _repair_missing_assets(file_hashes: dict, sha: str) -> None:
    """Re-download any files recorded in file_hashes that are absent from disk.

    Skips everything if the asset directory is a git repo (developer workflow).
    """
    if _is_git_repo(asset_dir):
        return
    missing = [p for p in file_hashes if not (asset_dir / p).exists()]
    if not missing:
        return
    logger.info(f"Repairing {len(missing)} missing asset file(s)...")
    for path in missing:
        target = asset_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        raw_url = f"{ASSETS_RAW_BASE}/{sha}/{path}"
        resp = requests.get(raw_url, timeout=30)
        resp.raise_for_status()
        target.write_bytes(resp.content)
        logger.info(f"Repaired: {path}")


def reset_assets(branch: Optional[str] = None, progress_callback=None) -> None:
    """Force a full re-download of the asset pack, overwriting all local files."""
    if branch is None:
        branch = ASSET_BRANCH
    remote_sha = _get_remote_asset_sha(branch)
    if remote_sha is None:
        raise RuntimeError("Cannot reset assets: network unavailable.")
    file_hashes = download_full_assets(branch, progress_callback=progress_callback)
    _save_local_asset_state(branch, remote_sha, file_hashes)


def ensure_assets_current() -> bool:
    """Ensure the asset pack is downloaded and up to date.

    - First run or branch change (app upgrade): downloads the full repo zip.
    - Subsequent runs: fetches only changed files via the GitHub compare API,
      skipping any file whose on-disk hash differs from the stored hash (user-modified).
    - If assets are current, checks for missing files and re-downloads them.
    - If the asset directory is a git repo, all integrity/repair checks are skipped.
    - If the network is unavailable and assets already exist, continues with existing files.

    Returns True if any asset files were added or updated, False otherwise.
    """
    branch = ASSET_BRANCH
    local_branch, local_sha, local_hashes = _get_local_asset_state()

    has_assets = assets_available()
    remote_sha = _get_remote_asset_sha(branch)

    if not has_assets:
        if remote_sha is None:
            raise RuntimeError("Cannot download assets: network unavailable and no local assets found.")
        if local_branch != branch:
            logger.info(f"Asset branch changed ({local_branch} -> {branch}); re-downloading.")
        file_hashes = download_full_assets(branch)
        _save_local_asset_state(branch, remote_sha, file_hashes)
        return True
    elif remote_sha is None:
        logger.warning("Could not check for asset updates; using existing files.")
        if local_sha and local_hashes:
            try:
                _repair_missing_assets(local_hashes, local_sha)
            except Exception as e:
                logger.warning(f"Asset repair failed: {e}")
        return False
    elif remote_sha != local_sha:
        try:
            updated_hashes = _update_changed_assets(local_sha, remote_sha, local_hashes)
            _save_local_asset_state(branch, remote_sha, updated_hashes)
            return updated_hashes != local_hashes
        except Exception as e:
            logger.warning(f"Incremental asset update failed ({e}); falling back to full download.")
            try:
                file_hashes = download_full_assets(branch)
                _save_local_asset_state(branch, remote_sha, file_hashes)
                return True
            except Exception as e2:
                logger.error(f"Full asset download also failed: {e2}; using existing files.")
                return False
    else:
        logger.info("Assets are up to date.")
        if local_hashes:
            try:
                _repair_missing_assets(local_hashes, local_sha)
            except Exception as e:
                logger.warning(f"Asset integrity check failed: {e}")
        return False


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
