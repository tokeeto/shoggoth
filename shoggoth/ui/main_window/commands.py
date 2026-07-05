"""
Command palette population: menu actions, settings toggles, and
context-sensitive card commands.
"""
import re

from PySide6.QtGui import QKeySequence

from shoggoth.i18n import tr
from shoggoth.ui.command_palette import Command


def build_commands(window) -> list[Command]:
    """Build the full command list for the command palette."""
    commands: list[Command] = []

    # 1. All QActions from the menu bar
    for menu_action in window.menuBar().actions():
        menu = menu_action.menu()
        if menu:
            cat = menu_action.text().replace('&', '')
            commands.extend(_collect_menu_commands(menu, cat))

    # 2. Settings toggles
    commands.extend(_build_settings_commands(window))

    # 3. Context-sensitive card commands
    commands.extend(_build_card_commands(window))

    return commands


def _collect_menu_commands(menu, category: str) -> list[Command]:
    """Recursively collect QActions from a menu into Command objects."""
    commands: list[Command] = []
    for action in menu.actions():
        if action.isSeparator():
            continue
        if action.objectName() == "palette_skip":
            continue
        submenu = action.menu()
        if submenu:
            sub_cat = re.sub(r'&(.)', r'\1', action.text())
            commands.extend(_collect_menu_commands(submenu, sub_cat))
            continue
        raw = action.text()
        if not raw:
            continue
        # Strip accelerator marker and trailing (Shortcut) hints
        name = re.sub(r'&(.)', r'\1', raw)
        name = re.sub(r'\s*\([^)]*\)\s*$', '', name).strip()
        if not name:
            continue
        shortcut = action.shortcut().toString(QKeySequence.NativeText)
        act = action
        commands.append(Command(
            name=name,
            category=category,
            shortcut=shortcut,
            action=lambda a=act: a.trigger(),
            enabled=lambda a=act: a.isEnabled(),
        ))
    return commands


def _build_settings_commands(window) -> list[Command]:
    """Commands that directly toggle or set individual settings."""
    from shoggoth.settings import EXPORT_SIZES
    cat = tr("CMD_CATEGORY_SETTINGS")
    commands: list[Command] = []

    def toggle(key: str, after=None):
        def _run():
            current = window.config.getboolean('Shoggoth', key, False)
            window.config.set('Shoggoth', key, not current)
            window.config.save()
            if after:
                after()
        return _run

    commands.append(Command(
        name=tr("CMD_TOGGLE_SHOW_BLEED"),
        category=cat,
        action=toggle('show_bleed', window.schedule_preview_update),
    ))
    commands.append(Command(
        name=tr("CMD_TOGGLE_SHOW_REGIONS"),
        category=cat,
        action=toggle('show_regions', window.schedule_preview_update),
    ))

    def sync_hyphenation():
        window.card_renderer.set_hyphenation_enabled(
            window.config.getboolean('Shoggoth', 'hyphenation_enabled', True)
        )
        window.schedule_preview_update()

    commands.append(Command(
        name=tr("CMD_TOGGLE_HYPHENATION"),
        category=cat,
        action=toggle('hyphenation_enabled', sync_hyphenation),
    ))
    commands.append(Command(
        name=tr("CMD_TOGGLE_EXPORT_BLEED"),
        category=cat,
        action=toggle('export_bleed'),
    ))
    commands.append(Command(
        name=tr("CMD_TOGGLE_EXPORT_SEPARATE"),
        category=cat,
        action=toggle('export_separate_versions'),
    ))
    commands.append(Command(
        name=tr("CMD_TOGGLE_EXPORT_BACKS"),
        category=cat,
        action=toggle('export_include_backs'),
    ))
    commands.append(Command(
        name=tr("CMD_TOGGLE_AUTO_UPDATES"),
        category=cat,
        action=toggle('auto_check_updates'),
    ))

    for i, (label, _) in enumerate(EXPORT_SIZES):
        idx = i
        commands.append(Command(
            name=tr("CMD_SET_EXPORT_SIZE").format(size=label),
            category=cat,
            action=lambda i=idx: (
                window.config.set('Shoggoth', 'export_size', i),
                window.config.save(),
            ),
        ))

    for fmt in ('PNG', 'JPEG', 'WebP'):
        commands.append(Command(
            name=tr("CMD_SET_EXPORT_FORMAT").format(format=fmt),
            category=cat,
            action=lambda f=fmt.lower(): (
                window.config.set('Shoggoth', 'export_format', f),
                window.config.save(),
            ),
        ))

    return commands


def _build_card_commands(window) -> list[Command]:
    """Context-sensitive commands that operate on the currently viewed card."""
    cat = tr("CMD_CATEGORY_CARD")

    def has_card():
        return window.current_card is not None

    ctx = window.file_browser.context_menu
    return [
        Command(
            name=tr("CMD_COPY_CARD"),
            category=cat,
            action=lambda: ctx.copy_card(window.current_card),
            enabled=has_card,
        ),
        Command(
            name=tr("CMD_DUPLICATE_CARD"),
            category=cat,
            action=lambda: ctx.duplicate_card(window.current_card),
            enabled=has_card,
        ),
        Command(
            name=tr("CMD_DELETE_CARD"),
            category=cat,
            action=lambda: ctx.delete_card(window.current_card),
            enabled=has_card,
        ),
    ]
