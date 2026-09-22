"""
Progress dialog for uploading a project's exports to Shoggoth Cloud for
review. The desktop no longer publishes projects itself -- an admin marks a
project "Published" (catalogue/frontpage visibility) from the website once
it's been vetted; this dialog only ever submits/syncs content.

Modeled directly on updater_ui.py's UpdateProgressDialog: network I/O runs on
a plain threading.Thread, reporting back to the UI thread purely through Qt
signals (never touching widgets from the background thread). Cancellation
only takes effect between files (uploads themselves aren't interrupted
mid-transfer), matching the cancel semantics export_widgets.run_image_export
already uses elsewhere in this dialog's own call chain.
"""
import json
import logging
import threading
from urllib.parse import quote

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPlainTextEdit, QPushButton,
)

from shoggoth import tts_sync
from shoggoth.cloud import client as publish_client
from shoggoth.i18n import tr

logger = logging.getLogger(__name__)


class PublishProgressDialog(QDialog):
    """`files` is a list of (kind, local_path, remote_name) tuples
    ('images'|'pdf'|'data'|'tts'). `remote_name` is the filename (or, for
    'images', "<encounter-set>/<filename>") the server sees -- see
    export_runner._image_remote_name. `tts_result`, if given, is
    {'image_paths', 'wrapper_path', 'sync'} from export_runner._run_tts --
    after uploading, the wrapper JSON at wrapper_path is read back, rewritten
    to the uploaded TTS image URLs, re-saved (and re-pushed live if `sync`
    was on), then uploaded itself to the project root as a fixed "tts.json".
    An ABOUT.md (author + description) is always uploaded to the root too,
    regardless of which content types were selected.

    `translation`, if given, is the local shoggoth.project.Translation
    currently active (see export_runner._run_publish) -- `project` is then
    still the *translation-view* Project (translated card text, name, etc.,
    used for ABOUT.md/TTS content), but every upload is routed into that
    translation's own subfolder under the base project instead of the
    project's own root, and the base project itself is never (re)published
    from here: a translation inherits the parent project's visibility for
    free once it's published (see app.storage's module docstring on the
    shoggoth_web side) -- there's nothing to mint per translation, and a
    non-owner translator couldn't publish the base project even if they
    wanted to (only the owner can).

    `card_manifest`, if given, is export_runner._build_card_manifest's
    output: the current run's whole id -> name/encounter-set/image-path
    mapping for the cloud review browser, synced via `publish_client.
    sync_cards`/`sync_translation_cards` (a full replace, not a merge) right
    after the project/translation id is resolved. Only built when the
    Images section actually ran this pass -- see _run_publish."""

    _progress_signal = Signal(int, int, str)  # bytes_done, bytes_total, filename
    _log_signal = Signal(str)
    _complete_signal = Signal(bool, bool, str)  # success, cancelled, message

    def __init__(
        self, project, base_url, token, files, tts_result, parent=None,
        translation=None, card_manifest=None,
    ):
        super().__init__(parent)
        self.project = project
        self.base_url = base_url
        self.token = token
        self.files = files
        self.tts_result = tts_result
        self.translation = translation
        self.card_manifest = card_manifest
        self._cancel_event = threading.Event()
        self._summary = ""

        self._progress_signal.connect(self._on_progress)
        self._log_signal.connect(self._on_log)
        self._complete_signal.connect(self._on_complete)

        self.setWindowTitle(tr("DLG_PUBLISHING"))
        self.setMinimumWidth(520)
        self.setModal(True)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.status_label = QLabel(tr("MSG_PUBLISH_STARTING"))
        self.status_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        self.output_log = QPlainTextEdit()
        self.output_log.setReadOnly(True)
        self.output_log.setMaximumHeight(150)
        layout.addWidget(self.output_log)

        layout.addStretch()

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_btn = QPushButton(tr("BTN_CANCEL"))
        self.cancel_btn.clicked.connect(self._on_cancel)
        button_layout.addWidget(self.cancel_btn)

        self.close_btn = QPushButton(tr("BTN_CLOSE"))
        self.close_btn.clicked.connect(self.accept)
        self.close_btn.setVisible(False)
        button_layout.addWidget(self.close_btn)

        layout.addLayout(button_layout)

    def start(self):
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def summary(self) -> str:
        return self._summary

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------

    def _run(self):
        try:
            # Always re-read the base project fresh from disk right before
            # resolving its cloud id -- never trust whatever in-memory copy
            # happens to be attached to this dialog. Two Project objects can
            # easily be open on the same underlying file at once (e.g. the
            # plain project in one tab, and Translation.project's own
            # separate load in another, opened via "Load Translation") --
            # publishing one persists cloud_project_id to disk, but does
            # nothing to update the *other* Python object's already-loaded
            # `.data`. Resolving from a fresh read is the only way to see a
            # sibling view's already-saved id, and it's what avoids minting a
            # second, duplicate cloud project out from under the first one.
            # (For a translation view specifically, this also sidesteps
            # TranslationWriter, which only ever persists a handful of
            # translation-specific fields -- writing cloud_project_id through
            # it would silently be dropped.)
            from shoggoth.project import Project
            base_project = Project.load(self.project.file_path)
            self._log_signal.emit(tr("MSG_PUBLISH_ENSURING_PROJECT"))
            project_id, ensured_public_url = publish_client.ensure_project(
                self.base_url, self.token, base_project
            )

            if self.translation is not None:
                self._log_signal.emit(tr("MSG_PUBLISH_ENSURING_TRANSLATION"))
                translation_id = publish_client.ensure_translation(
                    self.base_url, self.token, project_id, self.translation
                )
            else:
                translation_id = None

            if self.card_manifest is not None:
                self._log_signal.emit(tr("MSG_PUBLISH_SYNCING_CARDS"))
                if translation_id is not None:
                    publish_client.sync_translation_cards(
                        self.base_url, self.token, project_id, translation_id, self.card_manifest
                    )
                else:
                    publish_client.sync_cards(self.base_url, self.token, project_id, self.card_manifest)

            self._upload_about_md(project_id, translation_id)

            uploaded = {}  # remote path ("tts/x.png") -> local path, for uploaded TTS images
            tts_image_paths = set(self.tts_result['image_paths']) if self.tts_result else set()

            for kind, path, remote_name in self.files:
                if self._cancel_event.is_set():
                    self._complete_signal.emit(False, True, tr("MSG_PUBLISH_CANCELLED"))
                    return
                self._log_signal.emit(tr("MSG_PUBLISH_UPLOADING").format(name=remote_name))
                result = self._upload(project_id, translation_id, kind, remote_name, path)
                if path in tts_image_paths:
                    uploaded[result["path"]] = path

            if self._cancel_event.is_set():
                self._complete_signal.emit(False, True, tr("MSG_PUBLISH_CANCELLED"))
                return

            if translation_id is None:
                # public_url is reachable as soon as the server has minted the
                # project's share (ensure_project's own response, above) --
                # the desktop no longer self-publishes, so there's no separate
                # "publish" call to make here anymore.
                public_url = ensured_public_url
                if public_url and base_project.get_meta("cloud_public_url") != public_url:
                    # Cached so a *translation* publish (below) can build TTS
                    # download links without any live, authorized call back
                    # to the server -- the translator already has this exact
                    # file locally (translation.project_path points at it),
                    # which is the only way they could be translating this
                    # project at all.
                    base_project.set_meta("cloud_public_url", public_url)
                    base_project.save_all()
                published = {"public_url": public_url}
            else:
                # Translations inherit the parent project's share instead of
                # minting their own -- see this class's docstring. public_url
                # comes from the base project's own local cache (set above,
                # the last time *that* project was uploaded from any machine),
                # not a live call -- if the base project has never been
                # uploaded, or was uploaded from a copy of the file that never
                # made it back here, this is just None and TTS URL rewriting
                # below is skipped, same as before.
                published = {"public_url": base_project.get_meta("cloud_public_url")}

            if self.tts_result:
                if uploaded:
                    self._log_signal.emit(tr("MSG_PUBLISH_REWRITING_TTS"))
                    self._rewrite_tts_urls(published, uploaded)
                self._upload_tts_json(project_id, translation_id)

            count = len(self.files)
            if translation_id is not None:
                self._summary = tr("MSG_PUBLISH_TRANSLATION_SUCCESS").format(count=count)
            else:
                self._summary = tr("MSG_PUBLISH_SUCCESS").format(
                    count=count, url=published.get("public_url") or ""
                )
            self._complete_signal.emit(True, False, self._summary)
        except publish_client.PublishError as exc:
            self._complete_signal.emit(False, False, str(exc))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Publish failed")
            self._complete_signal.emit(False, False, str(exc))

    def _upload(self, project_id, translation_id, kind, remote_name, path):
        def progress_cb(done, total):
            self._progress_signal.emit(done, total, remote_name)

        if translation_id is not None:
            return publish_client.upload_translation_file(
                self.base_url, self.token, project_id, translation_id, kind, remote_name, path,
                progress_cb=progress_cb,
            )
        return publish_client.upload_file(
            self.base_url, self.token, project_id, kind, remote_name, path, progress_cb=progress_cb,
        )

    def _build_about_md(self) -> str:
        author = self.project.get_meta('author')
        description = self.project.get_meta('description')
        lines = [f"# {self.project.name}", ""]
        if author:
            lines += [f"By {author}", ""]
        if description:
            lines += [description, ""]
        return "\n".join(lines)

    def _upload_about_md(self, project_id, translation_id):
        """Uploaded unconditionally, regardless of which content types were
        selected for this publish run -- it's the author/description blurb,
        not a content export. self.project already carries the translated
        name (and, via get_meta, the same author/description as the base
        project -- Translation.apply() never touches those), so this needs
        no separate translation-specific content path."""
        self._log_signal.emit(tr("MSG_PUBLISH_UPLOADING").format(name="ABOUT.md"))
        content = self._build_about_md().encode("utf-8")
        if translation_id is not None:
            publish_client.upload_translation_bytes(
                self.base_url, self.token, project_id, translation_id, "root", "ABOUT.md", content,
            )
        else:
            publish_client.upload_bytes(
                self.base_url, self.token, project_id, "root", "ABOUT.md", content,
            )

    def _upload_tts_json(self, project_id, translation_id):
        """A copy of the TTS wrapper (post URL-rewrite, if that ran) at a
        fixed root-level filename, so the website can offer a direct download
        link independent of any per-image publish selection."""
        self._log_signal.emit(tr("MSG_PUBLISH_UPLOADING").format(name="tts.json"))
        if translation_id is not None:
            publish_client.upload_translation_file(
                self.base_url, self.token, project_id, translation_id, "root", "tts.json",
                self.tts_result["wrapper_path"],
            )
        else:
            publish_client.upload_file(
                self.base_url, self.token, project_id, "root", "tts.json",
                self.tts_result["wrapper_path"],
            )

    def _rewrite_tts_urls(self, published, uploaded):
        """uploaded: remote path ("tts/x.png") -> local path, for every
        uploaded TTS image this run. URLs are built the same way the server's
        own storage.public_file_url() does, off the project's public share
        base (`published["public_url"]`) -- no extra round trip needed."""
        public_url = published.get("public_url")
        if not public_url:
            return
        path_to_url = {
            local_path: f"{public_url}/download?path=/{quote(remote_path, safe='/')}"
            for remote_path, local_path in uploaded.items()
        }

        wrapper_path = self.tts_result["wrapper_path"]
        with open(wrapper_path, encoding="utf-8") as fh:
            wrapper = json.load(fh)
        changed = tts_sync.rewrite_urls(wrapper, path_to_url)
        if not changed:
            return
        with open(wrapper_path, "w", encoding="utf-8") as fh:
            json.dump(wrapper, fh, indent=2)
        if self.tts_result.get("sync"):
            tts_sync.push_to_tts(wrapper)

    # ------------------------------------------------------------------
    # Slot handlers (main thread)
    # ------------------------------------------------------------------

    def _on_progress(self, downloaded, total, filename):
        if total > 0:
            self.progress_bar.setRange(0, 100)
            percent = min(100, int(downloaded * 100 / total))
            self.progress_bar.setValue(percent)
        else:
            self.progress_bar.setRange(0, 0)
        self.status_label.setText(tr("MSG_PUBLISH_UPLOADING").format(name=filename))

    def _on_log(self, message):
        self.status_label.setText(message)
        self.output_log.appendPlainText(message)

    def _on_complete(self, success, cancelled, message):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100 if success else self.progress_bar.value())
        self.status_label.setText(message)
        self.output_log.appendPlainText(message)
        self._summary = message
        self.cancel_btn.setVisible(False)
        self.close_btn.setVisible(True)

    def _on_cancel(self):
        self._cancel_event.set()
        self.cancel_btn.setEnabled(False)
        self.status_label.setText(tr("MSG_PUBLISH_CANCELLING"))
