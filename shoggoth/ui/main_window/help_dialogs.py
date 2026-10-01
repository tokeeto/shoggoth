"""
Help-menu dialogs: manual, about, text options, and asset location.
"""
import re
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLineEdit, QPushButton,
    QTextBrowser, QVBoxLayout,
)

import shoggoth
from shoggoth.files import asset_dir
from shoggoth.i18n import tr


def _heading_slug(text):
    """GitHub-style anchor for a heading, which is what the manual's links use."""
    return re.sub(r'[^\w\- ]', '', text.strip().lower()).replace(' ', '-')


def _scroll_to_heading(browser, fragment):
    """Qt's Markdown import doesn't create anchors for headings, so find the
    heading whose GitHub-style slug matches the link's fragment."""
    block = browser.document().begin()
    while block.isValid():
        if block.blockFormat().headingLevel() and _heading_slug(block.text()) == fragment:
            browser.setTextCursor(QTextCursor(block))
            browser.verticalScrollBar().setValue(
                int(browser.document().documentLayout().blockBoundingRect(block).top()))
            return
        block = block.next()


def show_manual(parent):
    manual_path = Path(shoggoth.__file__).parent.parent / "documentation" / "manual.md"
    if not manual_path.exists():
        QDesktopServices.openUrl(QUrl("https://github.com/tokeeto/shoggoth/blob/manual/documentation/manual.md"))
        return

    dialog = QDialog(parent)
    dialog.setWindowTitle(tr("MENU_MANUAL"))
    dialog.resize(960, 720)
    layout = QVBoxLayout()

    # The manual is split into one Markdown file per chapter; links between
    # them are followed in place, so the browser keeps its own back history.
    browser = QTextBrowser()
    browser.setOpenLinks(False)

    def show_source(url):
        browser.setSource(url, QTextDocument.MarkdownResource)
        if url.fragment():
            _scroll_to_heading(browser, url.fragment())

    def on_link_clicked(url):
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
            return
        target = browser.source().resolved(url)
        if target.isLocalFile() and Path(target.toLocalFile()).is_file():
            if target.toLocalFile() == browser.source().toLocalFile():
                _scroll_to_heading(browser, target.fragment())
            else:
                show_source(target)
        else:
            QDesktopServices.openUrl(QUrl(
                "https://github.com/tokeeto/shoggoth/blob/manual/documentation/" + url.path()
            ))

    browser.anchorClicked.connect(on_link_clicked)
    show_source(QUrl.fromLocalFile(str(manual_path)))
    layout.addWidget(browser)

    button_box = QDialogButtonBox(QDialogButtonBox.Close)
    back_button = button_box.addButton("←", QDialogButtonBox.ActionRole)
    back_button.setEnabled(False)
    back_button.clicked.connect(browser.backward)
    browser.backwardAvailable.connect(back_button.setEnabled)
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


def open_shoggoth_location(parent):
    """Open the folder containing the currently running Shoggoth executable"""
    import sys
    exe_dir = Path(sys.executable).parent
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(exe_dir)))


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
