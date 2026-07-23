"""
Export actions: the quick, dialog-free image exports (Ctrl+E, encounter-set
right-click, "export all") plus the entry points into the unified
ProjectExportDialog (Images/PDF/TTS/arkham.build/Guides).
"""
import multiprocessing
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox, QProgressDialog

from shoggoth.i18n import tr


def get_export_size(window):
    """Return the size dict selected in export settings."""
    from shoggoth.settings import EXPORT_SIZES
    index = window.config.getint('Shoggoth', 'export_size', 1)
    index = min(index, len(EXPORT_SIZES) - 1)
    return EXPORT_SIZES[index][1]


def _read_export_prefs(window, bleed=None, format=None, quality=None, separate_versions=None):
    """Collect image export options, falling back to preferences for any not given."""
    config = window.config
    if bleed is None:
        bleed = config.getboolean('Shoggoth', 'export_bleed', True)
    if format is None:
        format = config.get('Shoggoth', 'export_format', 'png')
    if quality is None:
        quality = config.getint('Shoggoth', 'export_quality', 95)
    if separate_versions is None:
        separate_versions = config.getboolean('Shoggoth', 'export_separate_versions', False)
    return {
        'size': get_export_size(window),
        'include_backs': config.getboolean('Shoggoth', 'export_include_backs', False),
        'bleed': bleed,
        'format': format,
        'quality': quality,
        'separate_versions': separate_versions,
    }


def _export_folder(window):
    folder = Path(window.active_project.file_path).parent / f'Export of {window.active_project.name}'
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _export_card_images(window, cards, prefs):
    """Render cards to image files on a small thread pool with a progress dialog."""
    start_time = time.time()
    cores = max(4, multiprocessing.cpu_count() - 1)
    export_folder = _export_folder(window)

    progress = QProgressDialog(
        tr("STATUS_EXPORTING"), tr("BTN_CANCEL"), 0, len(cards), window
    )
    progress.setWindowModality(Qt.WindowModal)

    threads = []
    for i, card in enumerate(cards):
        if progress.wasCanceled():
            break

        if i >= cores:
            threads[i - cores].join()
            progress.setValue(i - cores)

        progress.setLabelText(tr("MSG_EXPORTING_CARD").format(name=card.name))

        thread = threading.Thread(
            target=window.card_renderer.export_card_images,
            args=(card, str(export_folder)),
            kwargs=prefs,
        )
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()
    print(f'Exported {len(cards)} cards in:', time.time() - start_time)

    progress.setValue(len(cards))

    QMessageBox.information(
        window,
        tr("DLG_EXPORT_COMPLETE"),
        tr("MSG_EXPORTED_CARDS").format(count=len(cards), folder=export_folder)
    )


def export_all(window, bleed=None, format=None, quality=None, separate_versions=None):
    """Export all cards in the project using settings from preferences"""
    if not window.active_project:
        QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_LOADED"))
        return

    prefs = _read_export_prefs(window, bleed, format, quality, separate_versions)
    try:
        _export_card_images(window, window.active_project.get_all_cards(), prefs)
    except Exception as e:
        QMessageBox.critical(window, tr("DLG_EXPORT_ERROR"), tr("ERR_EXPORT_CARDS").format(error=e))


def export_encounter_set(window, encounter_set):
    """Export all cards in an encounter set using settings from preferences"""
    cards = encounter_set.cards
    if not cards:
        QMessageBox.information(window, tr("DLG_EXPORT_COMPLETE"), tr("MSG_NO_CARDS_IN_SET"))
        return

    prefs = _read_export_prefs(window)
    try:
        _export_card_images(window, cards, prefs)
    except Exception as e:
        QMessageBox.critical(window, tr("DLG_EXPORT_ERROR"), tr("ERR_EXPORT_CARDS").format(error=e))


def export_current(window, bleed=None, format=None, quality=None, separate_versions=None):
    """Export the current card using settings from preferences"""
    if not window.current_card:
        QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_NO_CARD_SELECTED"))
        return

    prefs = _read_export_prefs(window, bleed, format, quality, separate_versions)
    try:
        export_folder = _export_folder(window)
        window.card_renderer.export_card_images(window.current_card, str(export_folder), **prefs)
        QMessageBox.information(
            window,
            tr("DLG_EXPORT_COMPLETE"),
            tr("MSG_CARD_EXPORTED").format(folder=export_folder)
        )
    except Exception as e:
        QMessageBox.critical(window, tr("DLG_EXPORT_ERROR"), tr("ERR_EXPORT_CARD").format(error=e))


def open_project_export_dialog(window):
    """Open the unified Project Export dialog; edits are saved to the project."""
    if not window.active_project:
        QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_LOADED"))
        return
    from shoggoth.ui.project_export_dialog import ProjectExportDialog
    dialog = ProjectExportDialog(window.active_project, window.card_renderer, window, persist=True)
    dialog.exec()


def open_one_time_export_dialog(window):
    """Open the unified Project Export dialog without saving edits back to the project."""
    if not window.active_project:
        QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_LOADED"))
        return
    from shoggoth.ui.project_export_dialog import ProjectExportDialog
    dialog = ProjectExportDialog(window.active_project, window.card_renderer, window, persist=False)
    dialog.exec()


def open_encounter_set_export_dialog(window, encounter_set=None):
    """Open a one-time, images-only Project Export dialog scoped to a single
    encounter set (the tree's right-click "Export Set" quick action)."""
    if not window.active_project:
        QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_LOADED"))
        return
    from shoggoth.ui.project_export_dialog import ProjectExportDialog
    dialog = ProjectExportDialog(window.active_project, window.card_renderer, window, persist=False)
    dialog._images_section.set_enabled_checked(True)
    dialog._pdf_section.set_enabled_checked(False)
    dialog._tts_section.set_enabled_checked(False)
    dialog._ab_section.set_enabled_checked(False)
    dialog._guides_section.set_enabled_checked(False)
    if encounter_set is not None:
        dialog._scope_selector.set_scope({'type': 'encounter_sets', 'encounter_set_ids': [encounter_set.id]})
        dialog._images_section.set_expanded(True)
    dialog.exec()


def run_export_profile(window, profile_id):
    """Run one saved export profile immediately, with no dialog and no
    changes to save (Export -> Setups quick-run menu)."""
    project = window.active_project
    if not project:
        QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_LOADED"))
        return
    profile = next((p for p in project.export_profiles if p.id == profile_id), None)
    if profile is None:
        return

    from shoggoth.ui.export_runner import run_profile, summarize
    results, errors = run_profile(window, project, window.card_renderer, profile.data)
    QMessageBox.information(window, profile.name, summarize(results, errors))


def open_prince_installer(window):
    """Open the Prince installer dialog."""
    from shoggoth.ui.prince_installer import PrinceInstallerDialog
    from PySide6.QtWidgets import QDialog
    dialog = PrinceInstallerDialog(parent=window)
    dialog.exec()
