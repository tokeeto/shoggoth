"""
Menu bar construction for the main window.

create_menus(window) builds every menu and wires actions to the handler
modules. Actions that need to be reachable later (toggles, the PDF action
group, language checkmarks) are stored as attributes on the window.
"""
from PySide6.QtGui import QAction, QActionGroup

from shoggoth.files import translation_dir
from shoggoth.i18n import get_available_languages, get_available_languages_from_dir, tr
from shoggoth.ui.main_window import exports, help_dialogs, projects


def create_menus(window):
    """Create the full menu bar"""
    menubar = window.menuBar()

    _create_file_menu(window, menubar)
    _create_project_menu(window, menubar)
    _create_export_menu(window, menubar)
    _create_tools_menu(window, menubar)
    _create_help_menu(window, menubar)
    _create_view_menu(window, menubar)
    _create_language_menu(window, menubar)


def _add_action(window, menu, text, handler, shortcut=None):
    action = QAction(text, window)
    if shortcut:
        action.setShortcut(shortcut)
    action.triggered.connect(handler)
    menu.addAction(action)
    return action


def _create_file_menu(window, menubar):
    file_menu = menubar.addMenu(tr("MENU_FILE"))

    _add_action(window, file_menu, tr("MENU_OPEN_PROJECT"),
                lambda: projects.open_project_dialog(window), shortcut="Ctrl+O")
    _add_action(window, file_menu, tr("MENU_NEW_PROJECT"),
                lambda: projects.new_project_dialog(window))
    _add_action(window, file_menu, tr("MENU_CLOSE_PROJECT"),
                lambda: projects.close_project(window))

    file_menu.addSeparator()

    _add_action(window, file_menu, tr("MENU_SAVE"),
                lambda: projects.save_changes(window), shortcut="Ctrl+S")
    _add_action(window, file_menu, tr("MENU_NEW_CARD"),
                lambda: projects.new_card_dialog(window), shortcut="Ctrl+N")
    _add_action(window, file_menu, tr("MENU_GOTO_CARD"),
                window.show_goto_dialog, shortcut="Ctrl+R")

    file_menu.addSeparator()

    _add_action(window, file_menu, tr("MENU_GATHER_IMAGES"),
                lambda: projects.gather_images(window))
    _add_action(window, file_menu, tr("MENU_GATHER_UPDATE"),
                lambda: projects.gather_images(window, update=True))

    file_menu.addSeparator()

    _add_action(window, file_menu, tr("MENU_SETTINGS"), window.open_settings)

    file_menu.addSeparator()

    _add_action(window, file_menu, tr("MENU_EXIT"), window.close)


def _create_project_menu(window, menubar):
    project_menu = menubar.addMenu(tr("MENU_PROJECT"))

    _add_action(window, project_menu, tr("MENU_AUTO_ENUMERATE"),
                lambda: projects.auto_enumerate(window), shortcut="Ctrl+M")
    _add_action(window, project_menu, tr("CTX_NEW_ENCOUNTER_SET"),
                lambda: projects.add_encounter_set(window))
    _add_action(window, project_menu, tr("MENU_ADD_GUIDE"),
                lambda: projects.add_guide(window))
    _add_action(window, project_menu, tr("MENU_ADD_SCENARIO"),
                lambda: projects.add_scenario_template(window))
    _add_action(window, project_menu, tr("MENU_ADD_CAMPAIGN"),
                lambda: projects.add_campaign_template(window))
    _add_action(window, project_menu, tr("MENU_ADD_INVESTIGATOR"),
                lambda: projects.add_investigator_template(window))
    _add_action(window, project_menu, tr("MENU_ADD_INV_PROJECT"),
                lambda: projects.add_investigator_project_template(window))

    project_menu.addSeparator()

    _add_action(window, project_menu, tr("MENU_ADD_TRANSLATION"),
                lambda: projects.add_translation_dialog(window))
    _add_action(window, project_menu, tr("MENU_LOAD_TRANSLATION"),
                lambda: projects.load_translation_dialog(window))


def _create_export_menu(window, menubar):
    export_menu = menubar.addMenu(tr("MENU_EXPORT"))

    _add_action(window, export_menu, tr("MENU_QUICK_EXPORT_CURRENT"),
                lambda: exports.export_current(window), shortcut="Ctrl+E")
    _add_action(window, export_menu, tr("MENU_EXPORT_IMAGES"),
                lambda: exports.open_image_export_dialog(window), shortcut="Ctrl+Shift+E")

    # The 3×3 grid of PDF exports: one group per flavor, one entry per scope.
    # Kept as a list so Prince availability can enable/disable them together.
    window._pdf_actions = []
    for flavor in ('pdf', 'mbprint', 'azao'):
        export_menu.addSeparator()
        for scope in exports.PDF_SCOPES:
            action = _add_action(
                window, export_menu, tr(f"MENU_{scope.upper()}_TO_{flavor.upper()}"),
                lambda checked=False, s=scope, f=flavor: exports.export_pdf(window, s, f),
            )
            window._pdf_actions.append(action)

    export_menu.addSeparator()

    # Install Prince (shown when not installed)
    window._install_prince_action = _add_action(
        window, export_menu, tr("MENU_INSTALL_PRINCE"),
        lambda: exports.open_prince_installer(window),
    )

    export_menu.addSeparator()

    _add_action(window, export_menu, tr("MENU_EXPORT_TTS"),
                lambda: exports.open_tts_export_dialog(window))
    _add_action(window, export_menu, tr("MENU_EXPORT_ARKHAM_BUILD"),
                lambda: exports.open_arkham_build_dialog(window))

    exports.refresh_pdf_actions(window)


def _create_tools_menu(window, menubar):
    tools_menu = menubar.addMenu(tr("MENU_TOOLS"))

    _add_action(window, tools_menu, tr("MENU_CHECK_UPDATES"),
                window.update_manager.check_for_updates_manual)
    _add_action(window, tools_menu, tr("MENU_RESET_ASSETS"),
                window.reset_assets_dialog)


def _create_help_menu(window, menubar):
    help_menu = menubar.addMenu(tr("MENU_HELP"))

    _add_action(window, help_menu, tr("MENU_MANUAL"),
                lambda: help_dialogs.show_manual(window))

    help_menu.addSeparator()

    _add_action(window, help_menu, tr("MENU_TEXT_OPTIONS"),
                lambda: help_dialogs.show_text_options(window))
    _add_action(window, help_menu, tr("MENU_ABOUT"),
                lambda: help_dialogs.show_about(window))
    _add_action(window, help_menu, tr("MENU_ASSET_LOCATION"),
                lambda: help_dialogs.open_asset_location(window))


def _create_view_menu(window, menubar):
    view_menu = menubar.addMenu(tr("MENU_VIEW"))

    _add_action(window, view_menu, tr("MENU_COMMAND_PALETTE"),
                window.show_command_palette, shortcut="Ctrl+P")

    view_menu.addSeparator()

    # Toggle Preview
    window.toggle_preview_action = QAction(tr("MENU_SHOW_PREVIEW"), window)
    window.toggle_preview_action.setCheckable(True)
    window.toggle_preview_action.setChecked(False)
    window.toggle_preview_action.triggered.connect(window.toggle_preview)
    view_menu.addAction(window.toggle_preview_action)

    # Toggle Project Tree
    window.toggle_tree_action = QAction("Show Project Tree", window)
    window.toggle_tree_action.setCheckable(True)
    window.toggle_tree_action.setChecked(True)
    window.toggle_tree_action.setShortcut("Ctrl+K")
    window.toggle_tree_action.triggered.connect(window.toggle_project_tree)
    view_menu.addAction(window.toggle_tree_action)

    # Sidebar view mode
    view_menu.addSeparator()
    sidebar_header = QAction(tr("MENU_SIDEBAR_VIEW"), window)
    sidebar_header.setEnabled(False)
    sidebar_header.setObjectName("palette_skip")
    view_menu.addAction(sidebar_header)

    sidebar_group = QActionGroup(window)
    sidebar_group.setExclusive(True)

    window.sidebar_tree_action = QAction(tr("MENU_SIDEBAR_TREE"), window)
    window.sidebar_tree_action.setCheckable(True)
    window.sidebar_tree_action.setChecked(True)
    sidebar_group.addAction(window.sidebar_tree_action)
    view_menu.addAction(window.sidebar_tree_action)

    window.sidebar_list_action = QAction(tr("MENU_SIDEBAR_LIST"), window)
    window.sidebar_list_action.setCheckable(True)
    sidebar_group.addAction(window.sidebar_list_action)
    view_menu.addAction(window.sidebar_list_action)


def _create_language_menu(window, menubar):
    language_menu = menubar.addMenu(tr("MENU_LANGUAGE"))
    window.language_actions = []

    # UI Language section header
    ui_lang_header = QAction(tr("MENU_UI_LANGUAGE"), window)
    ui_lang_header.setEnabled(False)
    ui_lang_header.setObjectName("palette_skip")
    language_menu.addAction(ui_lang_header)

    available_languages = get_available_languages()
    current_lang = window.config.get('Shoggoth', 'language', 'en')

    for lang_code, lang_name in available_languages.items():
        action = QAction(lang_name, window)
        action.setCheckable(True)
        action.setChecked(lang_code == current_lang)
        action.setData(lang_code)
        action.triggered.connect(lambda checked, code=lang_code: window.change_language(code))
        language_menu.addAction(action)
        window.language_actions.append(action)

    # Card Language section
    language_menu.addSeparator()
    card_lang_header = QAction(tr("MENU_CARD_LANGUAGE"), window)
    card_lang_header.setEnabled(False)
    card_lang_header.setObjectName("palette_skip")
    language_menu.addAction(card_lang_header)

    window.card_language_actions = []
    available_card_languages = get_available_languages_from_dir(translation_dir)
    current_card_lang = window.config.get('Shoggoth', 'card_language', 'en')

    for lang_code, lang_name in available_card_languages.items():
        action = QAction(lang_name, window)
        action.setCheckable(True)
        action.setChecked(lang_code == current_card_lang)
        action.setData(lang_code)
        action.triggered.connect(lambda checked, code=lang_code: window.change_card_language(code))
        language_menu.addAction(action)
        window.card_language_actions.append(action)
