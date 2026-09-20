"""Cloud menu action handlers (window as first arg, mirroring exports.py/
projects.py) -- the actual dialogs live in ui/cloud/. See CLOUD.md's
"Cloud projects" section for the full picture.

Cloud projects live in `cloud_cache/<provider>/<id>/` (shoggoth.cloud.folder).
Everything here that "opens" or "creates" one just gets the project file into
that folder and opens it like any other project -- `window.open_project`
attaches sync, which does the rest in the background."""
import copy
import json
import time

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QMessageBox

from shoggoth.cloud import client, folder, merge, upload
from shoggoth.i18n import tr


def _attach_open_projects(window):
    for project in window.open_projects:
        window.cloud.attach(project)


def open_sign_in_dialog(window):
    from shoggoth.ui.cloud.signin_dialog import SignInDialog
    dialog = SignInDialog(window.config, window)
    if dialog.exec() == QDialog.Accepted:
        _attach_open_projects(window)  # projects opened while signed out start syncing now


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


def open_cloud_project(window, cloud_id, title, role='owner'):
    """Opens a cloud project by id. If it's never been opened on this machine
    a stub project file is written first -- the open itself is instant and
    purely local, and sync then fills the stub in from the cloud."""
    path = folder.project_file(cloud_id)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        stub = {
            'name': title, 'code': '', 'icon': '', 'encounter_sets': [], 'cards': [],
            'meta': {'celaeno_id': cloud_id, 'celaeno_version': 0, 'celaeno_synced_at': 0,
                     'celaeno_role': role},
        }
        path.write_text(json.dumps(stub, indent=4), encoding='utf-8')
    window.open_project(str(path))


def _create_cloud_project(window, name, source_project=None, data=None):
    """Creates the cloud project, builds its local folder (copying in the
    source project's resource files, if it has any), writes the project file
    and opens it. Returns True on success."""
    base_url = window.config.get('Shoggoth', 'publish_base_url', '')
    token = window.config.get('Shoggoth', 'publish_token', '')
    try:
        detail = client.create_storage_project(base_url, token, name, {})
    except client.PublishError as exc:
        QMessageBox.warning(window, tr("MENU_CLOUD_SAVE_TO_CLOUD"), str(exc))
        return False
    cloud_id = detail['id']
    root = folder.project_dir(cloud_id)
    root.mkdir(parents=True, exist_ok=True)

    local = upload.relocate_resources(source_project, root) if source_project else copy.deepcopy(data)
    try:
        # The relocated project is the real content -- send it now so anyone
        # the project is shared with sees the same relative paths we do.
        patched = client.patch_storage_project(base_url, token, cloud_id, merge.to_wire(local))
    except client.PublishError as exc:
        QMessageBox.warning(window, tr("MENU_CLOUD_SAVE_TO_CLOUD"), str(exc))
        return False
    local.setdefault('meta', {}).update({
        'celaeno_id': cloud_id, 'celaeno_version': patched['version'],
        'celaeno_synced_at': time.time(), 'celaeno_role': 'owner',
    })
    folder.project_file(cloud_id).write_text(json.dumps(local, indent=4), encoding='utf-8')

    if source_project is not None:
        source_project.clear_dirty()  # its content lives on in the cloud copy
        window.close_project(source_project)
    window.open_project(str(folder.project_file(cloud_id)))
    return True


def save_active_project_to_cloud(window):
    """Copies the active local project into a brand-new cloud project (its
    image files come along, paths rewritten to be relative), then closes the
    local one and opens the cloud copy -- from then on edits and files sync
    automatically. The original file is left untouched on disk."""
    project = window.active_project
    if project is None:
        QMessageBox.information(window, tr("DLG_NO_PROJECT"), tr("MSG_OPEN_PROJECT_FIRST"))
        return
    if project.is_cloud_project:
        QMessageBox.information(
            window, tr("MENU_CLOUD_SAVE_TO_CLOUD"), tr("MSG_ALREADY_CLOUD_PROJECT")
        )
        return
    if _create_cloud_project(window, project.name, source_project=project):
        QMessageBox.information(
            window, tr("MENU_CLOUD_SAVE_TO_CLOUD"), tr("MSG_CLOUD_PROJECT_CREATED")
        )


def new_cloud_project(window):
    """Creates a brand-new empty project as a cloud project."""
    from shoggoth.project import Project
    from shoggoth.ui.cloud.new_project_dialog import NewCloudProjectDialog
    dialog = NewCloudProjectDialog(window)
    if dialog.exec() != QDialog.Accepted:
        return
    name, code = dialog.get_result()
    _create_cloud_project(window, name, data=Project.new(name=name, code=code, icon=''))
