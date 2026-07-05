"""
Export actions: card images (threaded batch export) and the PDF, TTS,
and arkham.build export dialogs.
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


def open_image_export_dialog(window):
    """Open the Export to Images modal dialog."""
    if not window.active_project:
        QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_LOADED"))
        return
    from shoggoth.ui.image_export_dialog import ImageExportDialog
    dialog = ImageExportDialog(window.active_project, window.card_renderer, window)
    dialog.exec()


def open_encounter_set_export_dialog(window, encounter_set=None):
    """Open the Export to Images modal dialog pre-scoped to an encounter set."""
    if not window.active_project:
        QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_LOADED"))
        return
    from shoggoth.ui.image_export_dialog import ImageExportDialog
    dialog = ImageExportDialog(window.active_project, window.card_renderer, window,
                               encounter_set=encounter_set)
    dialog.exec()


# ── PDF export ────────────────────────────────────────────────────────────
# The nine PDF menu entries form a grid: scope × flavor.

PDF_SCOPES = ('card', 'campaign', 'player')
PDF_FLAVORS = {
    'pdf':     {'mbprint': False, 'azao': False},
    'mbprint': {'mbprint': True,  'azao': False},
    'azao':    {'mbprint': False, 'azao': True},
}


def _pdf_cards(window, scope):
    if scope == 'card':
        return [window.current_card]
    if scope == 'campaign':
        cards = []
        for es in window.active_project.encounter_sets:
            cards.extend(es.cards)
        return cards
    return list(window.active_project.player_cards)


def _pdf_title(scope, flavor):
    key = f"PDF_DLG_TITLE_{scope.upper()}"
    if flavor != 'pdf':
        key += f"_{flavor.upper()}"
    return tr(key)


def _pdf_default_filename(window, scope, flavor):
    if flavor == 'azao':
        return "front.pdf"
    suffix = '_mbprint' if flavor == 'mbprint' else ''
    if scope == 'card':
        return f"{window.current_card.name}{suffix}.pdf"
    scope_name = 'campaign' if scope == 'campaign' else 'player cards'
    return f"{window.active_project.name} {scope_name}{suffix}.pdf"


def export_pdf(window, scope, flavor):
    """Open the PDF export dialog for a scope ('card', 'campaign', 'player')
    and flavor ('pdf', 'mbprint', 'azao')."""
    if scope == 'card':
        if not window.current_card:
            QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_NO_CARD_SELECTED"))
            return
    elif not window.active_project:
        QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
        return

    from shoggoth.ui.pdf_export_dialog import PDFExportDialog
    dialog = PDFExportDialog(
        window.active_project, window.card_renderer,
        _pdf_cards(window, scope), _pdf_title(scope, flavor),
        default_filename=_pdf_default_filename(window, scope, flavor),
        parent=window,
        **PDF_FLAVORS[flavor],
    )
    dialog.exec()


def refresh_pdf_actions(window):
    """Enable/disable PDF export actions based on whether Prince is installed."""
    from shoggoth.pdf_exporter import check_prince_installed
    installed = check_prince_installed()
    for action in window._pdf_actions:
        action.setEnabled(installed)
    window._install_prince_action.setVisible(not installed)


def open_prince_installer(window):
    """Open the Prince installer dialog; re-enable PDF actions on success."""
    from shoggoth.ui.prince_installer import PrinceInstallerDialog
    from PySide6.QtWidgets import QDialog
    dialog = PrinceInstallerDialog(parent=window)
    if dialog.exec() == QDialog.Accepted:
        refresh_pdf_actions(window)


# ── Other export targets ──────────────────────────────────────────────────

def open_tts_export_dialog(window):
    """Open the TTS export modal dialog."""
    if not window.active_project:
        QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
        return
    from shoggoth.ui.tts_export_dialog import TTSExportDialog
    dialog = TTSExportDialog(window.active_project, window.card_renderer, parent=window)
    dialog.exec()


def open_arkham_build_dialog(window):
    if not window.active_project:
        QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
        return
    from shoggoth.ui.arkham_build_dialog import ArkhamBuildExportDialog
    dialog = ArkhamBuildExportDialog(window.active_project, window.card_renderer, parent=window)
    dialog.exec()
