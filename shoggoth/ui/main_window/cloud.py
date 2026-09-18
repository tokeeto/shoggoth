"""Cloud menu action handlers (window as first arg, mirroring exports.py/
projects.py) -- the actual dialogs live in ui/cloud/. See CLOUD.md's
"Storage projects" section for the full picture."""
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QMessageBox

from shoggoth.cloud import client, sync
from shoggoth.i18n import tr


def open_sign_in_dialog(window):
    from shoggoth.ui.cloud.signin_dialog import SignInDialog
    dialog = SignInDialog(window.config, window)
    dialog.exec()


def sign_out(window):
    window.cloud.stop_all()
    window.config.set('Shoggoth', 'publish_token', '')
    window.config.set('Shoggoth', 'publish_email', '')
    window.config.set('Shoggoth', 'publish_has_access', False)
    window.config.save()


def open_account_page(window):
    base_url = window.config.get('Shoggoth', 'publish_base_url', 'https://celaeno.cards')
    QDesktopServices.openUrl(QUrl(f"{base_url}/account"))


def open_shared_project_dialog(window):
    from shoggoth.ui.cloud.open_storage_dialog import OpenStorageProjectDialog
    dialog = OpenStorageProjectDialog(window, window.config)
    dialog.exec()


def save_active_project_to_cloud(window):
    """Uploads the active local project as a brand-new cloud storage
    project, then marks this same local project cloud-backed (sets
    cloud_storage_location + starts live sync) -- from now on, edits push
    automatically (see CloudSyncController.schedule_push). Distinct from
    new_cloud_project below: this acts on whatever project is already open,
    it doesn't create one."""
    project = window.active_project
    if project is None:
        QMessageBox.information(window, tr("DLG_NO_PROJECT"), tr("MSG_OPEN_PROJECT_FIRST"))
        return
    if project.get_meta('cloud_storage_location'):
        QMessageBox.information(
            window, tr("MENU_CLOUD_SAVE_TO_CLOUD"), tr("MSG_ALREADY_CLOUD_PROJECT")
        )
        return

    base_url = window.config.get('Shoggoth', 'publish_base_url', '')
    token = window.config.get('Shoggoth', 'publish_token', '')
    wire_data = sync.project_data_to_wire(project.data)
    try:
        detail = client.create_storage_project(base_url, token, project.name, wire_data)
    except client.PublishError as exc:
        QMessageBox.warning(window, tr("MENU_CLOUD_SAVE_TO_CLOUD"), str(exc))
        return

    project.set_meta('cloud_storage_location', f"cloud://{detail['id']}")
    project.save_all()
    window.cloud.start(detail['id'])
    QMessageBox.information(window, tr("MENU_CLOUD_SAVE_TO_CLOUD"), tr("MSG_CLOUD_PROJECT_CREATED"))


def new_cloud_project(window):
    """Creates a brand-new local project through the normal "New Project"
    flow (name/code/icon + a save location, same as File > New Project),
    then immediately backs the result with a new cloud storage project --
    reuses save_active_project_to_cloud once the new project is open and
    active, rather than duplicating the upload step."""
    from shoggoth.ui.dialogs import NewProjectDialog
    dialog = NewProjectDialog(window)
    if dialog.exec() != QDialog.Accepted:
        return
    # NewProjectDialog.create_project() already called window.open_project()
    # on success, so the freshly created project is now window.active_project.
    save_active_project_to_cloud(window)
