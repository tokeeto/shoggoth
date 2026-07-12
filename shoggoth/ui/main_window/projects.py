"""
Project lifecycle actions: open/close/save, translation sidecars, and the
Project-menu template generators.
"""
import json
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

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
        window.session.save_session()
        # Clear navigation history for new project
        window.nav.clear()
        window.status_bar.showMessage(tr("STATUS_OPENED").format(name=project['name']))
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


def save_changes(window):
    """Save the entire project"""
    if not window.active_project:
        return

    try:
        window.active_project.save()

        # Mark all cards as clean
        for card in window.active_project.get_all_cards():
            card.dirty = False
            if hasattr(card, 'front') and hasattr(card.front, 'dirty'):
                card.front.dirty = False
            if hasattr(card, 'back') and hasattr(card.back, 'dirty'):
                card.back.dirty = False

        # Update tree to remove dirty indicators
        window.file_browser.refresh()

        window.status_bar.showMessage(tr("STATUS_SAVED"), 3000)
    except Exception as e:
        QMessageBox.critical(window, tr("DLG_SAVE_ERROR"), tr("ERR_SAVE_PROJECT").format(error=e))


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
