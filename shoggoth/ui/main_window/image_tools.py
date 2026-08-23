"""
Tools -> Add Faded Edge action: pick a source image, then hand off to
FadeEdgeDialog (shoggoth/ui/image_tools_dialog.py) for live preview/tuning
and saving. Not tied to a project or card.
"""
from pathlib import Path

from PIL import Image
from PySide6.QtWidgets import QFileDialog, QMessageBox

from shoggoth.files import get_last_path, set_last_path
from shoggoth.i18n import tr
from shoggoth.ui.image_tools_dialog import FadeEdgeDialog


def open_fade_edge_dialog(window):
    file_path, _ = QFileDialog.getOpenFileName(
        window, tr("DLG_SELECT_IMAGE"), str(get_last_path("fade_edge_source")), tr("FILTER_RASTER_IMAGES")
    )
    if not file_path:
        return

    try:
        image = Image.open(file_path).convert("RGBA")
    except Exception as e:
        QMessageBox.critical(window, tr("DLG_ERROR"), tr("ERR_FADE_EDGE_TOOL").format(error=e))
        return

    set_last_path("fade_edge_source", Path(file_path).parent)

    dialog = FadeEdgeDialog(file_path, image, window)
    dialog.exec()
