"""Build arkham.build export documents and run export dialogs."""
import datetime
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import CancelledError, ThreadPoolExecutor
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from PySide6.QtCore import QCoreApplication, QEvent, Signal
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

import shoggoth

from shoggoth.arkham_build.assets import ImageAssetExporter
from shoggoth.arkham_build.card_fields import compact
from shoggoth.arkham_build.cards import ImageTarget, apply_card_metadata, export_card
from shoggoth.arkham_build.data import ExportedGroup, ExportedProject
from shoggoth.arkham_build.deckbuilding import add_deckbuilding_fields
from shoggoth.arkham_build.images import export_card_images
from shoggoth.arkham_build.upload_adapters import UploadAdapter, create_upload_adapter, export_folder
from shoggoth.card import Card
from shoggoth.i18n import tr
from shoggoth.project import Project
from shoggoth.renderer.card_renderer import CardRenderer
from shoggoth.updater import get_current_version as shoggoth_version

type CardExecutor = Callable[[list[Card], Callable[[Card], None]], None]


class _GroupData(TypedDict):
    id: str
    name: str
    icon: NotRequired[str]


_STATUSES = {"draft", "alpha", "beta", "complete", "final"}
_CONTENT_TYPES = {"campaign", "investigators", "player_cards", "rework", "scenario"}


def export_project(
    project: Project,
    settings: Mapping[str, Any],
    renderer: CardRenderer,
    *,
    card_executor: CardExecutor,
    adapter: UploadAdapter | None = None,
) -> ExportedProject:
    assert renderer is not None, "A configured renderer is required"
    assert callable(card_executor), "A card executor is required"

    data = project.data
    if adapter is None:
        adapter = create_upload_adapter(project, settings)

    assets = ImageAssetExporter(project, adapter)

    return {
        "meta": _project_meta(data),
        "data": {
            "cards": _export_cards(
                project, adapter, renderer, card_executor, assets
            ),
            "packs": [_export_group(data, assets)],
            "encounter_sets": [
                _export_group(encounter_set, assets)
                for encounter_set in data.get("encounter_sets", [])
            ],
        },
    }


def _export_group(data: _GroupData, assets: ImageAssetExporter) -> ExportedGroup:
    group: ExportedGroup = {"code": data["id"], "name": data["name"]}

    icon_url = assets.export(data.get("icon"))
    if icon_url is not None:
        group["icon_url"] = icon_url

    return group


def _export_cards(
    project: Project,
    adapter: UploadAdapter,
    renderer: CardRenderer,
    card_executor: CardExecutor,
    assets: ImageAssetExporter,
) -> list[dict[str, object]]:
    cards = [Card(data, project) for data in project.data["cards"]]
    records_by_id = {}
    targets_by_id: dict[str, list[ImageTarget]] = {}

    for card in cards:
        records_by_id[card.id], targets_by_id[card.id] = export_card(
            card, image_mapper=assets.map_tag
        )

    def export_images(card: Card) -> None:
        export_card_images(card, targets_by_id[card.id], adapter, renderer)

    image_cards = [card for card in cards if adapter.images_enabled and targets_by_id[card.id]]
    if image_cards:
        card_executor(image_cards, export_images)

    add_deckbuilding_fields(cards, records_by_id)
    for card in cards:
        apply_card_metadata(card, records_by_id[card.id])

    return [record for records in records_by_id.values() for record in records]


def _project_meta(data: Mapping[str, Any]) -> dict[str, object]:
    meta = data.get("meta", {})
    language = meta.get("language") or "en"
    status = meta.get("status")
    types = [t for t in meta.get("types") or [] if t in _CONTENT_TYPES]

    return {
        "author": meta.get("author", ""),
        "code": data["id"],
        "date_updated": datetime.datetime.now().isoformat(),
        "language": language,
        "generator": f"Shoggoth/{shoggoth_version()}",
        "name": data["name"],
        **compact(
            {
                "banner_url": meta.get("banner_url"),
                "banner_credit": meta.get("banner_credit"),
                "description": meta.get("description"),
                "external_link": meta.get("website_url"),
                "status": status if status in _STATUSES else "draft",
                "tags": meta.get("tags"),
                "types": types or None,
            }
        ),
    }


class _ExportDialog(QDialog):
    _status = Signal(str)
    _finished = Signal()

    def __init__(
        self,
        project: Project,
        settings: Mapping[str, Any],
        renderer: CardRenderer,
        parent: QWidget | None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("PE_SECTION_ARKHAM_BUILD"))
        self._cancelled = threading.Event()
        self.error: Exception | None = None
        self.output_path: Path = export_folder(project) / f"{project.id}.json"
        self.result_location: str = str(self.output_path)

        layout = QVBoxLayout(self)
        label = QLabel(tr("STATUS_EXPORTING"))
        label.setWordWrap(True)
        layout.addWidget(label)
        progress = QProgressBar()
        progress.setRange(0, 0)
        layout.addWidget(progress)
        self._cancel = QPushButton(tr("BTN_CANCEL"))
        self._cancel.clicked.connect(self.reject)
        layout.addWidget(self._cancel)
        self.resize(self.sizeHint() * 1.5)
        self._status.connect(label.setText)
        self._finished.connect(self.accept)
        self._thread = threading.Thread(
            target=self._run, args=(project, settings, renderer), daemon=True
        )

    def reject(self) -> None:
        self._cancelled.set()
        self._cancel.setEnabled(False)

    def _check_cancelled(self) -> None:
        if self._cancelled.is_set():
            raise CancelledError()

    def _execute_cards(
        self, cards: list[Card], export_card: Callable[[Card], None],
    ) -> None:
        def execute(card: Card) -> None:
            self._check_cancelled()
            self._status.emit(tr("MSG_EXPORTING_CARD").format(name=card.name))
            export_card(card)

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(execute, cards))
        self._check_cancelled()

    def _run(
        self, project: Project, settings: Mapping[str, Any], renderer: CardRenderer,
    ) -> None:
        try:
            app = shoggoth.app
            config = app.config if app is not None and settings.get("upload_adapter") == "celaeno" else None

            adapter = create_upload_adapter(
                project, settings, config=config,
                report=self._status.emit, check_cancelled=self._check_cancelled,
            )
            data = export_project(
                project, settings, renderer,
                card_executor=self._execute_cards, adapter=adapter,
            )

            self._check_cancelled()

            adapter.publish(self.output_path, data)
            url = data["meta"].get("url")

            self.result_location = url if isinstance(url, str) and url else str(self.output_path)
        except Exception as error:
            self.error = error
        finally:
            self._finished.emit()


def run_arkham_build_export(
    project: Project,
    settings: Mapping[str, Any],
    renderer: CardRenderer,
    parent: QWidget | None = None,
) -> tuple[str, list[str]]:
    dialog = _ExportDialog(project, settings, renderer, parent)
    dialog._thread.start()
    dialog.exec()
    dialog._thread.join()
    try:
        if dialog.error is not None:
            raise dialog.error
        return dialog.result_location, [str(dialog.output_path)]
    finally:
        # Delete Qt objects here, not when a worker next collects Python cycles.
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(dialog, QEvent.Type.DeferredDelete)
