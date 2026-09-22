"""Moving a local project into the cloud folder.

A cloud project's resources are just files inside its folder, referenced by
relative path. A project that already exists elsewhere on disk references its
images by whatever path it happens to use (absolute, or relative to its old
folder), so before it can become a cloud project those files have to be copied
into the new folder and the references rewritten. Pure logic, no Qt.
"""
import copy
import shutil
from pathlib import Path

from shoggoth import files

# Card face fields that can point at a user-supplied file
IMAGE_KEYS = (
    'illustration', 'illustration_shape', 'template',
    'image0', 'image1', 'image2', 'image3', 'image4', 'image5',
)


def _inside(path: Path, folder: Path) -> bool:
    try:
        path.resolve().relative_to(folder.resolve())
        return True
    except ValueError:
        return False


def relocate_resources(project, dest_dir: Path) -> dict:
    """Returns a deep copy of `project.data` in which every referenced user
    file has been copied into `dest_dir/images/` and its reference rewritten
    to that relative path (e.g. `images/foo.png`). Files from the asset pack,
    values that don't resolve to a file (template names and the like), and
    files already inside `dest_dir` are left as they are. `project` itself is
    not modified."""
    data = copy.deepcopy(project.data)
    dest_dir = Path(dest_dir)
    images_dir = dest_dir / 'images'
    copied = {}  # resolved source path -> new relative path

    def relocate(value):
        if not isinstance(value, str) or not value:
            return value
        resolved = project.find_file(value)
        if resolved is None or not resolved.is_file() or _inside(resolved, files.asset_dir):
            return value
        if _inside(resolved, dest_dir):
            return resolved.resolve().relative_to(dest_dir.resolve()).as_posix()
        if resolved in copied:
            return copied[resolved]
        images_dir.mkdir(parents=True, exist_ok=True)
        target = images_dir / resolved.name
        counter = 1
        while target.exists():
            target = images_dir / f'{resolved.stem}_{counter}{resolved.suffix}'
            counter += 1
        shutil.copy2(resolved, target)
        copied[resolved] = f'images/{target.name}'
        return copied[resolved]

    if data.get('icon'):
        data['icon'] = relocate(data['icon'])
    for encounter_set in data.get('encounter_sets', []):
        if encounter_set.get('icon'):
            encounter_set['icon'] = relocate(encounter_set['icon'])
    for card in data.get('cards', []):
        for side in ('front', 'back'):
            face = card.get(side) or {}
            for key in IMAGE_KEYS:
                if face.get(key):
                    face[key] = relocate(face[key])
    return data


FONT_SUFFIXES = ('.ttf', '.otf')


def import_file(source, dest_dir: Path) -> str:
    """Copies a user-picked file into a cloud project folder and returns its
    project-relative path (e.g. `images/foo.png`) -- the form cards reference.
    Fonts go to `fonts/`, everything else to `images/`. A name that's already
    taken gets a counter appended rather than overwriting the existing file.
    Sync picks the new file up from there (see `CloudSyncController.add_files`)."""
    source, dest_dir = Path(source), Path(dest_dir)
    subdir = 'fonts' if source.suffix.lower() in FONT_SUFFIXES else 'images'
    target_dir = dest_dir / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    counter = 1
    while target.exists():
        target = target_dir / f'{source.stem}_{counter}{source.suffix}'
        counter += 1
    shutil.copy2(source, target)
    return f'{subdir}/{target.name}'
