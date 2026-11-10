"""Upload adapters for arkham.build exports."""
import json
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from shoggoth.arkham_build.data import ExportedProject
from shoggoth.cloud import client
from shoggoth.files import default_export_folder
from shoggoth.i18n import tr
from shoggoth.project import Project


def export_folder(project: Project) -> Path:
    return default_export_folder(project) / "arkham-build"


class UploadAdapter(Protocol):
    @property
    def images_enabled(self) -> bool: ...

    def export_file(self, filename: str) -> Path: ...

    def image_url(self, filename: str) -> str: ...

    def publish(self, path: Path, data: ExportedProject) -> None: ...


def _write_json(path: Path, data: ExportedProject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


class ManualUploadAdapter:
    def __init__(self, project: Project, url_prefix: str):
        self.project = project
        self.url_prefix = url_prefix.strip().rstrip("/")

    @property
    def images_enabled(self) -> bool:
        return bool(self.url_prefix)

    def export_file(self, filename: str) -> Path:
        destination = export_folder(self.project) / self.project.id / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination

    def image_url(self, filename: str) -> str:
        return f"{self.url_prefix}/{self.project.id}/{quote(filename)}"

    def publish(self, path: Path, data: ExportedProject) -> None:
        _write_json(path, data)


class CelaenoUploadAdapter:
    images_enabled = True

    def __init__(self, project: Project, base_url: str, token: str, *, report, check_cancelled):
        self.project = project
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.report = report
        self.check_cancelled = check_cancelled

        check_cancelled()
        report(tr("MSG_PUBLISH_ENSURING_PROJECT"))

        self.project_id, self.public_url = client.ensure_artifact_target(
            self.base_url, token, f"arkham-build/{project.id}"
        )

        if not self.public_url:
            raise client.PublishError(tr("AB_CLOUD_NO_PUBLIC_URL"))
        self.public_url = self.public_url.rstrip("/")

    def _upload(self, kind: str, name: str, path: Path) -> str:
        self.check_cancelled()
        self.report(tr("MSG_PUBLISH_UPLOADING").format(name=name))
        result = client.upload_file(
            self.base_url, self.token, self.project_id, kind, name, path
        )
        return f"{self.public_url}/download?path=/{quote(result['path'], safe='/')}"

    def export_file(self, filename: str) -> Path:
        destination = export_folder(self.project) / self.project.id / filename
        destination.parent.mkdir(parents=True, exist_ok=True)
        return destination

    def image_url(self, filename: str) -> str:
        return self._upload(
            "images", Path(filename).name, self.export_file(filename),
        )

    def publish(self, path: Path, data: ExportedProject) -> None:
        _write_json(path, data)
        url = self._upload("data", path.name, path)
        # The first response gives the exact public path for this export.
        data["meta"]["url"] = url
        _write_json(path, data)
        self._upload("data", path.name, path)


def create_upload_adapter(
    project, settings, *, config=None, report=None, check_cancelled=None,
) -> UploadAdapter:
    adapter = settings.get("upload_adapter", "manual")
    if adapter == "manual":
        return ManualUploadAdapter(project, settings.get("url_prefix") or "")
    if adapter != "celaeno":
        raise ValueError(f"Unknown arkham.build upload adapter: {adapter}")

    if config is None:
        raise client.PublishError(tr("PUBLISH_NOT_LOGGED_IN"))

    token = config.get("Shoggoth", "publish_token", "")
    if not token or not config.getboolean("Shoggoth", "publish_has_access", False):
        raise client.PublishError(tr("PUBLISH_NOT_LOGGED_IN"))

    base_url = config.get("Shoggoth", "publish_base_url", "").strip()
    if not base_url:
        raise client.PublishError(tr("AB_CLOUD_NO_BASE_URL"))

    return CelaenoUploadAdapter(
        project, base_url, token,
        report=report or _noop, check_cancelled=check_cancelled or _noop,
    )


def _noop(*args: object) -> None:
    pass
