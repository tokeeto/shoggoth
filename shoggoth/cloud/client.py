"""Thin HTTP client for the Shoggoth Cloud API (the ``shoggoth_web`` backend).

Pure logic, no Qt -- same style as updater.py. Every function is synchronous;
callers that need progress reporting or non-blocking behaviour (the Settings
dialog, the Publish worker) provide a plain callback and/or run these calls on
a background thread themselves.

The functions below the "Storage projects" marker talk to a second, separate
cloud-project category (private/shared work-in-progress projects, distinct
from the publish-category functions above) -- see shoggoth_web's
app/storage_projects.py and CLOUD.md for the full picture.
"""
import io
from pathlib import Path

import requests

_METADATA_TIMEOUT = 15
_UPLOAD_TIMEOUT = 3600  # large PDFs can take a while; matches the server's
                        # own NEXTCLOUD_UPLOAD_TIMEOUT_SECONDS default.


class PublishError(Exception):
    """A user-facing publish/login failure. The message is always safe to
    show directly in a dialog (short, no stack traces)."""


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _raise_for_status(resp, what: str, status_messages: dict | None = None) -> None:
    if resp.ok:
        return
    status_messages = status_messages or {}
    if resp.status_code in status_messages:
        raise PublishError(status_messages[resp.status_code])
    raise PublishError(f"{what} failed: HTTP {resp.status_code} {resp.text[:200]}")


def login_with_password(base_url: str, email: str, password: str) -> str:
    """Log in with email + password. Returns the raw bearer token."""
    try:
        resp = requests.post(
            f"{base_url}/auth/login",
            json={"email": email, "password": password},
            timeout=_METADATA_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PublishError(f"Could not reach {base_url}: {exc}") from exc
    _raise_for_status(resp, "Login", {401: "Incorrect email or password."})
    data = resp.json()
    token = data.get("token")
    if not token:
        raise PublishError("Login succeeded but no token was returned.")
    return token


def verify_token(base_url: str, token: str) -> dict:
    """Return the /users/me payload ({'email', 'has_access', ...}) for token."""
    try:
        resp = requests.get(
            f"{base_url}/users/me", headers=_auth_headers(token), timeout=_METADATA_TIMEOUT
        )
    except requests.RequestException as exc:
        raise PublishError(f"Could not reach {base_url}: {exc}") from exc
    _raise_for_status(resp, "Verify", {401: "That token is not valid or has expired."})
    return resp.json()


def _project_payload(project) -> dict:
    return {
        "title": project.name,
        "description": project.get_meta("description") or None,
        "author": project.get_meta("author") or None,
        "banner_url": project.get_meta("banner_url") or None,
    }


def ensure_project(base_url: str, token: str, project) -> tuple[str, str | None]:
    """Return (server-side project id, public_url) for `project`, syncing its
    title/description/author/banner_url every time this is called (not just
    at first creation) -- so meta changes reach the server even on a publish
    run where no files ended up selected.

    `public_url` is populated as soon as the server has minted the project's
    Nextcloud share (at creation time now -- see shoggoth_web's
    storage.ensure_share), independent of whether an admin has published it:
    the desktop no longer self-publishes, so this is the only way it learns
    the share link (needed for TTS URL rewriting).

    Reuses `project.get_meta('cloud_project_id')` if it still resolves (exists
    and is owned by this token); otherwise mints a new server-side project and
    stores its id back onto the local project.
    """
    payload = _project_payload(project)
    existing_id = project.get_meta("cloud_project_id")
    if existing_id:
        try:
            resp = requests.patch(
                f"{base_url}/projects/{existing_id}",
                json=payload,
                headers=_auth_headers(token),
                timeout=_METADATA_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise PublishError(f"Could not reach {base_url}: {exc}") from exc
        if resp.ok:
            return existing_id, resp.json().get("public_url")
        if resp.status_code != 404:
            _raise_for_status(resp, "Project update")
        # 404: stale/not owned by this token -- fall through and create a new one.

    try:
        resp = requests.post(
            f"{base_url}/projects",
            json=payload,
            headers=_auth_headers(token),
            timeout=_METADATA_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PublishError(f"Could not reach {base_url}: {exc}") from exc
    _raise_for_status(resp, "Create project")
    data = resp.json()
    new_id = data["id"]
    project.set_meta("cloud_project_id", new_id)
    project.save_all()
    return new_id, data.get("public_url")


class _ProgressFile:
    """Wraps an open binary file object, reporting read progress."""

    def __init__(self, file_obj, total_size: int, progress_cb=None):
        self._file = file_obj
        self._total = total_size
        self._progress_cb = progress_cb
        self._read = 0

    def read(self, size=-1):
        chunk = self._file.read(size)
        self._read += len(chunk)
        if self._progress_cb:
            self._progress_cb(self._read, self._total)
        return chunk

    def __len__(self):
        return self._total


def _do_upload(url: str, token: str, size: int, file_obj, filename: str, progress_cb) -> dict:
    headers = {**_auth_headers(token), "Content-Length": str(size)}
    wrapped = _ProgressFile(file_obj, size, progress_cb)
    try:
        resp = requests.put(url, data=wrapped, headers=headers, timeout=_UPLOAD_TIMEOUT)
    except requests.RequestException as exc:
        raise PublishError(f"Upload of {filename} failed: {exc}") from exc
    _raise_for_status(
        resp,
        f"Upload of {filename}",
        {
            401: "Not logged in or token expired.",
            402: "Storage quota exceeded.",
            404: "Project not found (it may have been deleted or belongs to a different account).",
        },
    )
    return resp.json()


def upload_file(
    base_url: str,
    token: str,
    project_id: str,
    kind: str,
    filename: str,
    path,
    progress_cb=None,
) -> dict:
    """Stream-upload the local file at `path` to the project's `kind` bucket
    ('images' | 'pdf' | 'data' | 'tts' | 'root'). Returns the server's
    ProjectFileOut-shaped dict."""
    path = Path(path)
    size = path.stat().st_size
    url = f"{base_url}/projects/{project_id}/files/{kind}/{filename}"
    with open(path, "rb") as f:
        return _do_upload(url, token, size, f, filename, progress_cb)


def upload_bytes(
    base_url: str,
    token: str,
    project_id: str,
    kind: str,
    filename: str,
    data: bytes,
    progress_cb=None,
) -> dict:
    """Same as upload_file, but for small in-memory content (e.g. a generated
    ABOUT.md) that doesn't warrant writing a temp file first."""
    url = f"{base_url}/projects/{project_id}/files/{kind}/{filename}"
    return _do_upload(url, token, len(data), io.BytesIO(data), filename, progress_cb)


def ensure_translation(base_url: str, token: str, project_id: str, translation) -> str:
    """Return the server-side translation id for `translation` (a
    shoggoth.project.Translation), creating one if
    `translation.get_meta('cloud_translation_id')` doesn't resolve (missing,
    or 404s -- deleted, or belonging to a different project/account).

    Unlike ensure_project, there's nothing to sync on an already-resolved
    translation: a translation has no title/description/banner_url of its
    own, just the language it was created with, which never changes after
    creation.
    """
    existing_id = translation.get_meta('cloud_translation_id')
    if existing_id:
        try:
            resp = requests.get(
                f"{base_url}/projects/{project_id}/translations/{existing_id}",
                headers=_auth_headers(token),
                timeout=_METADATA_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise PublishError(f"Could not reach {base_url}: {exc}") from exc
        if resp.ok:
            return existing_id
        if resp.status_code != 404:
            _raise_for_status(resp, "Translation lookup")
        # 404: stale/not owned by this token -- fall through and create a new one.

    try:
        resp = requests.post(
            f"{base_url}/projects/{project_id}/translations",
            json={"language": translation.language},
            headers=_auth_headers(token),
            timeout=_METADATA_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PublishError(f"Could not reach {base_url}: {exc}") from exc
    _raise_for_status(resp, "Create translation")
    new_id = resp.json()["id"]
    translation.set_meta('cloud_translation_id', new_id)
    translation.save_all()
    return new_id


def upload_translation_file(
    base_url: str,
    token: str,
    project_id: str,
    translation_id: str,
    kind: str,
    filename: str,
    path,
    progress_cb=None,
) -> dict:
    """Same as upload_file, but into a translation's own subfolder (see
    app.storage's module docstring on the shoggoth_web side)."""
    path = Path(path)
    size = path.stat().st_size
    url = f"{base_url}/projects/{project_id}/translations/{translation_id}/files/{kind}/{filename}"
    with open(path, "rb") as f:
        return _do_upload(url, token, size, f, filename, progress_cb)


def upload_translation_bytes(
    base_url: str,
    token: str,
    project_id: str,
    translation_id: str,
    kind: str,
    filename: str,
    data: bytes,
    progress_cb=None,
) -> dict:
    """Same as upload_bytes, but into a translation's own subfolder."""
    url = f"{base_url}/projects/{project_id}/translations/{translation_id}/files/{kind}/{filename}"
    return _do_upload(url, token, len(data), io.BytesIO(data), filename, progress_cb)


def sync_cards(base_url: str, token: str, project_id: str, cards: list[dict]) -> list[dict]:
    """Replace the project's whole card manifest (id -> name/encounter set/
    image-path mapping, for the cloud review browser -- see CardEntry in
    shoggoth_web's models.py) with `cards` (export_runner._build_card_manifest's
    shape). A no-op with an empty list is still a valid call -- it just clears
    the manifest, same as any other resync."""
    try:
        resp = requests.put(
            f"{base_url}/projects/{project_id}/cards",
            json={"cards": cards},
            headers=_auth_headers(token),
            timeout=_METADATA_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PublishError(f"Could not reach {base_url}: {exc}") from exc
    _raise_for_status(resp, "Card sync")
    return resp.json()


def sync_translation_cards(
    base_url: str, token: str, project_id: str, translation_id: str, cards: list[dict]
) -> list[dict]:
    """Same as sync_cards, but for a translation's own manifest."""
    try:
        resp = requests.put(
            f"{base_url}/projects/{project_id}/translations/{translation_id}/cards",
            json={"cards": cards},
            headers=_auth_headers(token),
            timeout=_METADATA_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PublishError(f"Could not reach {base_url}: {exc}") from exc
    _raise_for_status(resp, "Card sync")
    return resp.json()


# --------------------------------------------------------------------------- #
# Storage projects (private, work-in-progress -- see module docstring)
# --------------------------------------------------------------------------- #
def create_storage_project(base_url: str, token: str, title: str, data: dict) -> dict:
    """Returns the created project's StorageProjectDetail dict (id/role/
    version/... + the echoed `data`)."""
    try:
        resp = requests.post(
            f"{base_url}/storage/projects",
            json={"title": title, "data": data},
            headers=_auth_headers(token),
            timeout=_METADATA_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PublishError(f"Could not reach {base_url}: {exc}") from exc
    _raise_for_status(resp, "Create storage project")
    return resp.json()


def list_storage_projects(base_url: str, token: str) -> list[dict]:
    """Owned + shared-with-me, each carrying the caller's own `role`."""
    try:
        resp = requests.get(
            f"{base_url}/storage/projects", headers=_auth_headers(token), timeout=_METADATA_TIMEOUT
        )
    except requests.RequestException as exc:
        raise PublishError(f"Could not reach {base_url}: {exc}") from exc
    _raise_for_status(resp, "List storage projects")
    return resp.json()


def get_storage_project(base_url: str, token: str, storage_project_id: str) -> dict:
    """Full StorageProjectDetail (including `data`, the whole project blob)."""
    try:
        resp = requests.get(
            f"{base_url}/storage/projects/{storage_project_id}",
            headers=_auth_headers(token),
            timeout=_METADATA_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PublishError(f"Could not reach {base_url}: {exc}") from exc
    _raise_for_status(
        resp, "Get storage project", {404: "Project not found, or you don't have access to it."}
    )
    return resp.json()


def patch_storage_project(base_url: str, token: str, storage_project_id: str, patch: dict) -> dict:
    """`patch['cards']` merges key-by-key (null deletes); any other key
    wholesale-replaces that key in the stored project -- see
    shoggoth_web's storage_projects.apply_patch. Returns the new
    StorageProjectOut (with the bumped `version`)."""
    try:
        resp = requests.patch(
            f"{base_url}/storage/projects/{storage_project_id}",
            json=patch,
            headers=_auth_headers(token),
            timeout=_METADATA_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PublishError(f"Could not reach {base_url}: {exc}") from exc
    _raise_for_status(resp, "Sync storage project", {404: "You no longer have write access."})
    return resp.json()


def upload_storage_file(
    base_url: str,
    token: str,
    storage_project_id: str,
    kind: str,
    filename: str,
    path,
    progress_cb=None,
) -> dict:
    """Stream-upload the local file at `path` into a storage project's
    `kind` bucket ('images' | 'fonts' | 'other')."""
    path = Path(path)
    size = path.stat().st_size
    url = f"{base_url}/storage/projects/{storage_project_id}/files/{kind}/{filename}"
    with open(path, "rb") as f:
        return _do_upload(url, token, size, f, filename, progress_cb)


def download_storage_file(base_url: str, token: str, storage_project_id: str, rel_path: str, dest_path) -> Path:
    """GET .../files/{rel_path} (a 307 redirect to a presigned Nextcloud
    link -- `requests` follows it automatically, dropping the bearer header
    on that cross-host hop, which is fine since the presigned link needs no
    auth of its own) and stream the bytes to `dest_path`. Used by
    shoggoth.cloud.storage_cache to resolve a cloud:// resource reference."""
    url = f"{base_url}/storage/projects/{storage_project_id}/files/{rel_path}"
    try:
        resp = requests.get(
            url, headers=_auth_headers(token), timeout=_UPLOAD_TIMEOUT, stream=True
        )
    except requests.RequestException as exc:
        raise PublishError(f"Could not reach {base_url}: {exc}") from exc
    _raise_for_status(resp, f"Download of {rel_path}", {404: "File not found."})
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
    return dest_path


def add_storage_share(base_url: str, token: str, storage_project_id: str, email: str, role: str) -> dict:
    try:
        resp = requests.post(
            f"{base_url}/storage/projects/{storage_project_id}/shares",
            json={"email": email, "role": role},
            headers=_auth_headers(token),
            timeout=_METADATA_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PublishError(f"Could not reach {base_url}: {exc}") from exc
    _raise_for_status(
        resp, "Share project", {404: "No account with that email.", 400: "Invalid share."}
    )
    return resp.json()


def list_storage_shares(base_url: str, token: str, storage_project_id: str) -> list[dict]:
    try:
        resp = requests.get(
            f"{base_url}/storage/projects/{storage_project_id}/shares",
            headers=_auth_headers(token),
            timeout=_METADATA_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PublishError(f"Could not reach {base_url}: {exc}") from exc
    _raise_for_status(resp, "List shares")
    return resp.json()


def remove_storage_share(base_url: str, token: str, storage_project_id: str, user_id: str) -> None:
    try:
        resp = requests.delete(
            f"{base_url}/storage/projects/{storage_project_id}/shares/{user_id}",
            headers=_auth_headers(token),
            timeout=_METADATA_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise PublishError(f"Could not reach {base_url}: {exc}") from exc
    _raise_for_status(resp, "Remove share")
