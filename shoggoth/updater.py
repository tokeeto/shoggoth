import io
import sys
import json
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


def _get_local_asset_state() -> tuple[Optional[str], Optional[str]]:
    """Return (branch, sha) from the local state file, or (None, None) if absent."""
    state_file = asset_dir / ASSETS_STATE_FILE
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text())
            return data.get("branch"), data.get("sha")
        except Exception:
            pass
    return None, None


def _save_local_asset_state(branch: str, sha: str) -> None:
    asset_dir.mkdir(parents=True, exist_ok=True)
    (asset_dir / ASSETS_STATE_FILE).write_text(json.dumps({"branch": branch, "sha": sha}))


def _get_remote_asset_sha(branch: str) -> Optional[str]:
    try:
        response = requests.get(f"{ASSETS_API}/commits/{branch}", headers=GITHUB_HEADERS, timeout=15)
        response.raise_for_status()
        return response.json().get("sha")
    except Exception as e:
        logger.warning(f"Failed to fetch remote asset SHA: {e}")
        return None


def download_full_assets(branch: Optional[str] = None) -> None:
    """Download and extract the complete asset pack from GitHub."""
    if branch is None:
        branch = ASSET_BRANCH
    zip_url = f"https://github.com/{ASSETS_REPO}/archive/refs/heads/{branch}.zip"
    logger.info(f"Downloading full asset pack from GitHub (branch {branch})...")
    response = requests.get(zip_url, timeout=120)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
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
    logger.info("Full asset pack downloaded successfully.")


def _update_changed_assets(old_sha: str, new_sha: str) -> None:
    """Download only files changed between two commits."""
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
        return
    logger.info(f"Updating {len(files)} changed asset file(s)...")
    for file_info in files:
        status = file_info.get("status")
        filename = file_info.get("filename", "")
        target = asset_dir / filename
        if status == "removed":
            if target.exists():
                target.unlink()
                logger.info(f"Removed: {filename}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            raw_url = f"{ASSETS_RAW_BASE}/{new_sha}/{filename}"
            file_resp = requests.get(raw_url, timeout=30)
            file_resp.raise_for_status()
            target.write_bytes(file_resp.content)
            if status == "renamed":
                prev = file_info.get("previous_filename", "")
                if prev:
                    old_target = asset_dir / prev
                    if old_target.exists():
                        old_target.unlink()
                logger.info(f"Renamed: {prev} -> {filename}")
            else:
                logger.info(f"{status.capitalize()}: {filename}")


def ensure_assets_current() -> None:
    """Ensure the asset pack is downloaded and up to date.

    - First run or branch change (app upgrade): downloads the full repo zip.
    - Subsequent runs: fetches only changed files via the GitHub compare API.
    - If the network is unavailable and assets already exist, continues with existing files.
    """
    branch = ASSET_BRANCH
    local_branch, local_sha = _get_local_asset_state()

    # Treat a branch mismatch (app upgraded to new asset schema) as a fresh install
    has_assets = asset_dir.is_dir() and local_sha is not None and local_branch == branch

    remote_sha = _get_remote_asset_sha(branch)

    if not has_assets:
        if remote_sha is None:
            raise RuntimeError("Cannot download assets: network unavailable and no local assets found.")
        if local_branch != branch:
            logger.info(f"Asset branch changed ({local_branch} -> {branch}); re-downloading.")
        download_full_assets(branch)
        _save_local_asset_state(branch, remote_sha)
    elif remote_sha is None:
        logger.warning("Could not check for asset updates; using existing files.")
    elif remote_sha != local_sha:
        try:
            _update_changed_assets(local_sha, remote_sha)
            _save_local_asset_state(branch, remote_sha)
        except Exception as e:
            logger.warning(f"Incremental asset update failed ({e}); falling back to full download.")
            try:
                download_full_assets(branch)
                _save_local_asset_state(branch, remote_sha)
            except Exception as e2:
                logger.error(f"Full asset download also failed: {e2}; using existing files.")
    else:
        logger.info("Assets are up to date.")


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
