"""
Project lifecycle actions: open/close/save, translation sidecars, and the
Project-menu template generators.
"""
import json
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from shoggoth.files import path_key
from shoggoth.i18n import tr
from shoggoth.project import (
    Project, Translation,
    has_legacy_collection_fields, migrate_legacy_collection_fields,
)


def open_project_dialog(window):
    """Show dialog to open a project"""
    if window.active_project:
        start_dir = str(window.active_project.folder)
    else:
        start_dir = str(Path.home())
    file_path, _ = QFileDialog.getOpenFileName(
        window,
        tr("DLG_OPEN_PROJECT"),
        start_dir,
        tr("FILTER_SHOGGOTH_PROJECTS")
    )
    if file_path:
        open_project(window, file_path)


def open_project(window, file_path):
    """Open a project file"""
    try:
        # Check if project is already open
        for project in window.open_projects:
            if project.file_path == file_path:
                # Already open - just make it active
                window.file_browser.set_active_project(project)
                window.status_bar.showMessage(tr("STATUS_SWITCHED_TO").format(name=project['name']))
                return

        # Load new project
        project = Project.load(file_path)

        if has_legacy_collection_fields(project.data):
            reply = QMessageBox.question(
                window, tr("DLG_MIGRATE_COLLECTION_TITLE"),
                tr("CONFIRM_MIGRATE_COLLECTION"),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                count = migrate_legacy_collection_fields(project.data)
                project.save()
                window.status_bar.showMessage(tr("STATUS_MIGRATED_COLLECTION").format(count=count))

        window.open_projects.append(project)
        window.active_project = project
        window.file_browser.add_project(project)
        window.watch_project_file(project)
        window.session.save_session()
        # Clear navigation history for new project
        window.nav.clear()
        window.status_bar.showMessage(tr("STATUS_OPENED").format(name=project['name']))
        # A project living in the cloud folder syncs in the background --
        # opening it above was purely local, so this never delays the open.
        window.cloud.attach(project)
    except Exception as e:
        QMessageBox.critical(window, tr("DLG_ERROR"), tr("ERR_OPEN_PROJECT").format(error=e))


def close_project(window, project=None):
    """Close a project"""
    if project is None:
        project = window.active_project
    if project is None:
        return

    # Check for unsaved changes in this project
    if project.has_unsaved_changes():
        msg_box = QMessageBox(window)
        msg_box.setWindowTitle(tr("DLG_UNSAVED_CHANGES"))
        msg_box.setText(tr("CONFIRM_SAVE_BEFORE_CLOSE").format(name=project['name']))
        msg_box.setIcon(QMessageBox.Question)
        save_btn = msg_box.addButton(tr("DLG_SAVE"), QMessageBox.AcceptRole)
        msg_box.addButton(tr("DLG_DISCARD"), QMessageBox.DestructiveRole)
        cancel_btn = msg_box.addButton(tr("DLG_CANCEL"), QMessageBox.RejectRole)
        msg_box.setDefaultButton(save_btn)
        msg_box.exec()

        if msg_box.clickedButton() == save_btn:
            project.save()
        elif msg_box.clickedButton() == cancel_btn:
            return

    window.cloud.detach(project)
    window.unwatch_project_file(project)

    # Remove from open projects
    if project in window.open_projects:
        window.open_projects.remove(project)

    # Update file browser
    window.file_browser.remove_project(project)

    # Update active project
    if window.active_project == project:
        window.active_project = window.open_projects[0] if window.open_projects else None

    window.session.save_session()
    window.status_bar.showMessage(tr("STATUS_CLOSED").format(name=project['name']))


def new_project_dialog(window):
    """Show dialog to create a new project"""
    from shoggoth.ui.dialogs import NewProjectDialog
    dialog = NewProjectDialog(window)
    dialog.exec()


def new_card_dialog(window):
    """Show dialog to create a new card"""
    if not window.active_project:
        QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
        return

    from shoggoth.ui.dialogs import NewCardDialog
    dialog = NewCardDialog(window)
    dialog.exec()


def save_changes(window, project=None):
    """Save the entire project (the active one, unless given)"""
    project = project or window.active_project
    if not project:
        return

    try:
        project.save()
        _after_save(window, project)
        window.status_bar.showMessage(tr("STATUS_SAVED"), 3000)
    except Exception as e:
        QMessageBox.critical(window, tr("DLG_SAVE_ERROR"), tr("ERR_SAVE_PROJECT").format(error=e))


def _after_save(window, project):
    """Mark everything in a just-saved project clean and refresh the tree."""
    for card in project.get_all_cards():
        card.dirty = False
        if hasattr(card, 'front') and hasattr(card.front, 'dirty'):
            card.front.dirty = False
        if hasattr(card, 'back') and hasattr(card.back, 'dirty'):
            card.back.dirty = False

    # Update tree to remove dirty indicators
    window.file_browser.refresh()


def save_project_as(window, project=None):
    """Save a project (the active one, unless given) to a new file, and keep
    working on it there. Returns whether it was saved."""
    project = project or window.active_project
    if not project:
        QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
        return False
    if not project.is_file_backed:
        QMessageBox.information(window, tr("DLG_SAVE_PROJECT_AS"), tr("MSG_SAVE_AS_UNSUPPORTED"))
        return False

    file_path, _ = QFileDialog.getSaveFileName(
        window, tr("DLG_SAVE_PROJECT_AS"), str(project.file_path), tr("FILTER_SHOGGOTH_PROJECTS"))
    if not file_path:
        return False
    if not Path(file_path).suffix:
        file_path += '.json'

    if path_key(file_path) == path_key(project.file_path):
        # Same file: an ordinary save (which is also what "overwrite" means
        # when the file was changed outside)
        save_changes(window, project)
        return True
    for other in window.open_projects:
        if other is not project and path_key(other.file_path) == path_key(file_path):
            QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_SAVE_AS_ALREADY_OPEN").format(path=file_path))
            return False

    old_path = project.file_path
    try:
        project.save_as(file_path)
    except Exception as e:
        QMessageBox.critical(window, tr("DLG_SAVE_ERROR"), tr("ERR_SAVE_AS").format(path=file_path, error=e))
        return False

    window.file_watcher.unwatch_file(old_path)
    window.watch_project_file(project)
    _after_save(window, project)
    # Tree nodes are keyed by the project's file path
    window.file_browser.rebuild()
    window.session.save_session()
    window.status_bar.showMessage(tr("STATUS_SAVED_AS").format(path=file_path), 5000)
    QMessageBox.information(
        window, tr("DLG_SAVED_AS_TITLE"), tr("MSG_SAVED_AS_RELATIVE_FILES").format(path=file_path))
    return True


# ── The project file changed outside Shoggoth ─────────────────────────────

_prompting = set()  # id()s of projects with a "file changed" dialog open


def check_external_change(window, project):
    """Called when a watched project file changed on disk. Does nothing unless
    the content really changed (our own saves, `touch`, reformatting don't
    count); otherwise asks the user what to do about it."""
    if id(project) in _prompting or not any(p is project for p in window.open_projects):
        return
    if not project.has_external_changes():
        return
    _prompting.add(id(project))
    try:
        _resolve_external_change(window, project)
    finally:
        _prompting.discard(id(project))


def _resolve_external_change(window, project):
    while True:
        unsaved = project.dirty or project.has_unsaved_changes()
        box = QMessageBox(window)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(tr("DLG_PROJECT_FILE_CHANGED"))
        box.setText(tr("MSG_PROJECT_FILE_CHANGED_UNSAVED" if unsaved else "MSG_PROJECT_FILE_CHANGED")
                    .format(name=project['name'], path=project.file_path))
        save_as_btn = box.addButton(tr("BTN_SAVE_AS"), QMessageBox.AcceptRole)
        reload_btn = box.addButton(tr("BTN_RELOAD_FROM_DISK"), QMessageBox.DestructiveRole)
        keep_btn = box.addButton(tr("BTN_KEEP_MY_VERSION"), QMessageBox.RejectRole)
        box.setDefaultButton(save_as_btn if unsaved else reload_btn)
        box.setEscapeButton(keep_btn)
        box.exec()

        clicked = box.clickedButton()
        if clicked == reload_btn:
            reload_project(window, project)
            return
        if clicked == save_as_btn:
            if save_project_as(window, project):
                return
            continue  # cancelled the file dialog: ask again
        try:
            project.acknowledge_external_changes()
        except OSError:
            pass
        window.status_bar.showMessage(tr("STATUS_KEPT_OWN_VERSION").format(name=project['name']), 5000)
        return


def reload_project(window, project):
    """Replace a project's in-memory state with what's in its file, losing any
    unsaved changes."""
    try:
        project.reload()
    except Exception as e:
        QMessageBox.critical(window, tr("DLG_ERROR"), tr("ERR_RELOAD_PROJECT").format(error=e))
        return

    # Editors and the preview hold cards from before the reload, which now
    # belong to no project: put fresh ones in place of them
    showing = window.active_project is project
    if showing:
        from shoggoth.ui.main_window import views
        window.file_watcher.clear_files()
        views.clear_editor(window)
        window.current_card = None
        window.current_editor = None
        window.current_guide = None
        window.current_guide_editor = None
    window.file_browser.rebuild()
    if showing:
        window.nav.refresh_current()
    window.status_bar.showMessage(tr("STATUS_RELOADED").format(name=project['name']), 5000)


def save_current(window):
    """Save only the current card"""
    if not window.current_card:
        return

    try:
        window.current_card.save()
        # Note: Card.save() already clears dirty flags and updates tree node
        window.status_bar.showMessage(tr("STATUS_SAVED_NAME").format(name=window.current_card.name), 3000)
    except Exception as e:
        QMessageBox.critical(window, tr("DLG_SAVE_ERROR"), tr("ERR_SAVE_CARD").format(error=e))


def gather_images(window, update=False):
    """Gather all images from the project"""
    if not window.active_project:
        QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
        return

    try:
        window.active_project.gather_images(update=update)
        action = tr("ACTION_GATHERED_UPDATED") if update else tr("ACTION_GATHERED")
        window.status_bar.showMessage(tr("STATUS_IMAGES_ACTION").format(action=action))
        QMessageBox.information(window, tr("DLG_SUCCESS"), tr("MSG_IMAGES_SUCCESS").format(action=action))
    except Exception as e:
        QMessageBox.critical(window, tr("DLG_ERROR"), tr("ERR_GATHER_IMAGES").format(error=e))


# ── Project menu template actions ─────────────────────────────────────────

def _require_project(window):
    """Warn and return None if no project is open; else return the active project."""
    if not window.active_project:
        QMessageBox.warning(window, tr("DLG_ERROR"), tr("MSG_NO_PROJECT_OPEN"))
        return None
    return window.active_project


def _get_text_input(window, title, label, default=""):
    text, ok = QInputDialog.getText(window, title, label, text=default)
    return text, ok


def auto_enumerate(window):
    """Assign card numbers across the project"""
    project = _require_project(window)
    if not project:
        return
    project.assign_card_numbers()
    window.status_bar.showMessage(tr("STATUS_PROJECT_ENUMERATED"))


def open_transfer_cards_dialog(window):
    """Open the Transfer Cards dialog, pre-filled from the tree's current
    multi-selection (if any cards are selected) in the active project."""
    project = _require_project(window)
    if not project:
        return

    from PySide6.QtCore import Qt
    selected = []
    for item in window.file_browser.tree.selectedItems():
        data = item.data(0, Qt.UserRole)
        if data and data.get('type') == 'card':
            selected.append(data.get('data'))

    from shoggoth.ui.transfer_dialog import TransferCardsDialog
    dialog = TransferCardsDialog(window, source_project=project, selected_cards=selected)
    dialog.exec()


def add_encounter_set(window):
    project = _require_project(window)
    if not project:
        return
    name, ok = QInputDialog.getText(window, tr("DLG_NEW_ENCOUNTER_SET"), tr("MSG_ENTER_ENCOUNTER_SET"))
    if ok and name:
        project.add_encounter_set(name)
        window.refresh_tree()


def add_guide(window):
    """Add a guide to the project"""
    project = _require_project(window)
    if not project:
        return
    from shoggoth.ui.dialogs import NewGuideDialog
    dialog = NewGuideDialog(project.folder, parent=window)
    if dialog.exec() != NewGuideDialog.Accepted:
        return
    name, file_path = dialog.get_result()
    project.add_guide(name=name, file_location=file_path)
    window.file_browser.refresh()
    window.status_bar.showMessage(tr("STATUS_GUIDE_ADDED"))


def add_scenario_template(window):
    """Add a scenario template"""
    project = _require_project(window)
    if not project:
        return
    name, ok = _get_text_input(window, tr("DLG_SCENARIO_NAME"), tr("MSG_ENTER_SCENARIO"), tr("PLACEHOLDER_SCENARIO"))
    if ok and name:
        project.create_scenario(name)
        window.file_browser.refresh()
        window.status_bar.showMessage(tr("STATUS_SCENARIO_CREATED").format(name=name))


def add_campaign_template(window):
    """Add a campaign template"""
    project = _require_project(window)
    if not project:
        return
    project.create_campaign()
    window.file_browser.refresh()
    window.status_bar.showMessage(tr("STATUS_CAMPAIGN_CREATED"))


def add_investigator_template(window):
    """Add an investigator template"""
    project = _require_project(window)
    if not project:
        return
    name, ok = _get_text_input(window, tr("DLG_INVESTIGATOR_NAME"), tr("MSG_ENTER_INVESTIGATOR"), tr("PLACEHOLDER_ROLAN"))
    if ok and name:
        project.add_investigator_set(name)
        window.file_browser.refresh()
        window.status_bar.showMessage(tr("STATUS_INVESTIGATOR_CREATED").format(name=name))


def add_investigator_project_template(window):
    """Add an investigator project template"""
    project = _require_project(window)
    if not project:
        return
    project.create_player_project()
    window.file_browser.refresh()
    window.status_bar.showMessage(tr("STATUS_PROJECT_CREATED"))


# ── Translation management ────────────────────────────────────────────────

def add_translation_dialog(window):
    """Prompt for a language code and create a new translation sidecar file."""
    if not window.active_project:
        return
    lang, ok = QInputDialog.getText(
        window, tr("DLG_ADD_TRANSLATION"), tr("MSG_ENTER_LANGUAGE_CODE")
    )
    if not ok or not lang.strip():
        return
    lang = lang.strip().lower()
    if lang in window.active_project.data.get('translations', {}):
        QMessageBox.warning(window, tr("DLG_ADD_TRANSLATION"), tr("MSG_TRANSLATION_EXISTS").format(lang=lang))
        return

    project_path = Path(window.active_project.file_path)
    translation_path = project_path.parent / f"{project_path.stem}_{lang}.json"
    data = {
        'language': lang,
        'project': project_path.name,
        'project_name': window.active_project.name,
        'encounter_sets': {},
        'cards': {},
        'guides': window.active_project.data.get('guides', []),
    }
    with open(translation_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    window.active_project.add_translation(lang, translation_path.name)
    window.active_project.save_all()
    window.status_bar.showMessage(f"Translation '{lang}' added: {translation_path.name}")

    # Auto-open the new translation project
    open_translation(window, str(translation_path))


def load_translation_dialog(window):
    """Show dialog to load an existing registered translation."""
    if not window.active_project:
        QMessageBox.information(window, tr("DLG_LOAD_TRANSLATION"), tr("MSG_OPEN_PROJECT_FIRST_TRANSLATION"))
        return
    translations = window.active_project.translations  # {lang: Path}
    if not translations:
        QMessageBox.information(window, tr("DLG_LOAD_TRANSLATION"),
                                tr("MSG_NO_TRANSLATIONS"))
        return
    choices = [f"{lang}  ({path.name})" for lang, path in translations.items()]
    choice, ok = QInputDialog.getItem(
        window, tr("DLG_LOAD_TRANSLATION"), tr("MSG_CHOOSE_TRANSLATION"), choices, 0, False)
    if not ok:
        return
    lang = choice.split("  ")[0]
    open_translation(window, str(translations[lang]))


def open_translation(window, file_path):
    """Open a translation file and add its translated project to the tree."""
    try:
        # Avoid duplicate opens — keyed by translation file path
        for project in window.open_projects:
            if getattr(project, '_node_id_path', None) == file_path:
                window.file_browser.set_active_project(project)
                window.status_bar.showMessage(
                    f"Switched to {project._translation.language} translation")
                return

        translation = Translation.load(file_path)
        project = translation.project
        project._translation = translation      # ephemeral: language reference
        project._node_id_path = file_path       # ephemeral: unique node key

        window.open_projects.append(project)
        window.active_project = project
        window.file_browser.add_project(project)
        window.session.save_session()
        window.status_bar.showMessage(
            f"Opened {translation.language} translation of {project['name']}")
    except Exception as e:
        QMessageBox.critical(window, "Error", f"Could not open translation:\n{e}")
