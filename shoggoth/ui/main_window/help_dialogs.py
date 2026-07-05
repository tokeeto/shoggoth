"""
Help-menu dialogs: manual, about, text options, and asset location.
"""
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLineEdit, QPushButton,
    QTextBrowser, QVBoxLayout,
)

import shoggoth
from shoggoth.files import asset_dir
from shoggoth.i18n import tr


def show_manual(parent):
    manual_path = Path(shoggoth.__file__).parent.parent / "documentation" / "manual.md"
    if not manual_path.exists():
        QDesktopServices.openUrl(QUrl("https://github.com/tokeeto/shoggoth/blob/manual/documentation/manual.md"))
        return

    dialog = QDialog(parent)
    dialog.setWindowTitle(tr("MENU_MANUAL"))
    dialog.resize(960, 720)
    layout = QVBoxLayout()

    browser = QTextBrowser()
    browser.setSearchPaths([str(manual_path.parent)])
    browser.setMarkdown(manual_path.read_text(encoding="utf-8"))
    browser.setOpenLinks(False)

    def on_link_clicked(url):
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
        elif not url.path() and url.fragment():
            browser.scrollToAnchor(url.fragment())
        else:
            QDesktopServices.openUrl(QUrl(
                "https://github.com/tokeeto/shoggoth/blob/manual/documentation/" + url.path()
            ))

    browser.anchorClicked.connect(on_link_clicked)
    layout.addWidget(browser)

    button_box = QDialogButtonBox(QDialogButtonBox.Close)
    button_box.rejected.connect(dialog.reject)
    layout.addWidget(button_box)

    dialog.setLayout(layout)
    dialog.exec()


def show_about(parent):
    """Show about dialog"""
    # Get version from package metadata
    try:
        from importlib.metadata import version
        app_version = version("shoggoth")
    except Exception:
        app_version = "unknown"

    # URLs for links
    urls = {
        'contrib': 'https://github.com/tokeeto/shoggoth',
        'patreon': 'https://www.patreon.com/tokeeto',
        'tips': 'https://ko-fi.com/tokeeto',
    }

    about_html = f"""
    <div style="text-align: center;">
        <h1 style="font-size: 32pt; margin-bottom: 5px;">Shoggoth</h1>
        <p style="font-size: 14pt; color: #666;">{tr("ABOUT_VERSION").format(version=app_version)}</p>
    </div>
    <hr>
    <p>{tr("ABOUT_CREATED_BY")}</p>
    <p>{tr("ABOUT_SUPPORT_TEXT").format(
        contributing=f'<a href="{urls["contrib"]}">{tr("ABOUT_CONTRIBUTING")}</a>',
        donating=f'<a href="{urls["patreon"]}">{tr("ABOUT_DONATING")}</a>',
        tipping=f'<a href="{urls["tips"]}">{tr("ABOUT_TIPPING")}</a>'
    )}</p>
    <p>{tr("ABOUT_IMAGES_CREDIT")}</p>
    <p>{tr("ABOUT_THANKS_SE")}</p>
    <p>{tr("ABOUT_SPECIAL_THANKS")}</p>
    """

    dialog = QDialog(parent)
    dialog.setWindowTitle(tr("DLG_ABOUT_TITLE"))
    dialog.setMinimumSize(450, 350)

    layout = QVBoxLayout()

    # Use QTextBrowser for clickable links
    text_browser = QTextBrowser()
    text_browser.setOpenExternalLinks(True)
    text_browser.setHtml(about_html)
    text_browser.setStyleSheet("background: transparent; border: none;")
    layout.addWidget(text_browser)

    # OK button
    button_box = QDialogButtonBox(QDialogButtonBox.Ok)
    button_box.accepted.connect(dialog.accept)
    layout.addWidget(button_box)

    dialog.setLayout(layout)
    dialog.exec()


def open_asset_location(parent):
    """Show the current asset folder location, with an option to open it"""
    dialog = QDialog(parent)
    dialog.setWindowTitle(tr("DLG_ASSET_LOCATION_TITLE"))
    dialog.setMinimumWidth(450)

    layout = QVBoxLayout()

    path_edit = QLineEdit(str(asset_dir))
    path_edit.setReadOnly(True)
    layout.addWidget(path_edit)

    button_row = QHBoxLayout()

    open_button = QPushButton(tr("DLG_ASSET_LOCATION_OPEN"))
    open_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(asset_dir))))
    button_row.addWidget(open_button)

    button_row.addStretch()

    button_box = QDialogButtonBox(QDialogButtonBox.Ok)
    button_box.accepted.connect(dialog.accept)
    button_row.addWidget(button_box)

    layout.addLayout(button_row)

    dialog.setLayout(layout)
    dialog.exec()


def show_text_options(window):
    """Show text formatting options"""
    from PySide6.QtWidgets import QPlainTextEdit
    from PySide6.QtGui import QFontDatabase

    help_text = window.card_renderer.rich_text.get_help_text()

    dialog = QDialog(window)
    dialog.setWindowTitle(tr("DLG_TEXT_OPTIONS"))
    dialog.resize(560, 650)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(12, 12, 12, 12)

    text_edit = QPlainTextEdit()
    text_edit.setReadOnly(True)
    text_edit.setPlainText(help_text)
    mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    mono.setPointSize(10)
    text_edit.setFont(mono)
    layout.addWidget(text_edit)

    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    buttons.rejected.connect(dialog.accept)
    layout.addWidget(buttons)

    dialog.exec()
