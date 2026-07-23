"""
Executes an export profile's enabled sections against a project.

Shared by ProjectExportDialog (built from live widget state) and the
Export -> Setups quick-run menu (built straight from a saved profile), so
both paths behave identically.

Runs PDF, TTS, arkham.build, and Guides first, then Images last: if two
sections' output happens to overlap in folder and filename, the plain image
export always "wins" as the final result on disk, and since every section
call below blocks until its own threads have joined, one section always
fully finishes before the next starts.
"""
import json
import multiprocessing
import re
import threading
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QProgressDialog

from shoggoth.i18n import tr
from shoggoth.settings import EXPORT_SIZES
from shoggoth.ui.export_widgets import resolve_scope_cards, run_image_export

_MBPRINT_FORMAT, _MBPRINT_QUALITY = 'png', 100
_AZAO_FORMAT, _AZAO_QUALITY = 'png', 100


def _resolve_size(label):
    for lbl, size in EXPORT_SIZES:
        if lbl == label:
            return size
    return EXPORT_SIZES[1][1]


def _safe_filename(name):
    return re.sub(r'[^\w\-. ]', '_', name).strip() or 'export'


def _default_folder(project):
    return project.folder / f'Export of {project.name}'


def _folder_from(project, setting):
    return Path(setting) if setting else _default_folder(project)


def _export_numbered_cards(parent, renderer, cards, folder, kwargs):
    """Like export_widgets.run_image_export, but assigns each card a running
    `number` (needed by some filename_format patterns), matching the
    original per-card numbering the Images section always used."""
    if not cards:
        return
    progress = QProgressDialog(tr("STATUS_EXPORTING"), tr("BTN_CANCEL"), 0, len(cards), parent)
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(0)
    cores = max(4, multiprocessing.cpu_count() - 1)
    threads = []
    number = 1
    for i, card in enumerate(cards):
        if progress.wasCanceled():
            break
        if i >= cores:
            threads[i - cores].join()
            progress.setValue(i - cores)
        progress.setLabelText(tr("MSG_EXPORTING_CARD").format(name=card.name))
        t = threading.Thread(
            target=renderer.export_card_images,
            args=(card, str(folder)),
            kwargs={**kwargs, 'number': number},
        )
        threads.append(t)
        t.start()
        number += card.amount
    for t in threads:
        t.join()
    progress.setValue(len(cards))


def _run_images(parent, project, renderer, cards, d):
    from shoggoth.card import natural_sort_key
    cards = sorted(cards, key=lambda c: natural_sort_key(c.project_number))
    folder = _folder_from(project, d['folder'])
    size = _resolve_size(d['size_label'])
    kwargs = dict(
        size=size, bleed=d['bleed'], format=d['format'], quality=d['quality'],
        include_backs=d['include_backs'], separate_versions=d['separate_versions'],
        rotate=d['rotate'], filename_format=d['filename_format'],
    )
    _export_numbered_cards(parent, renderer, cards, folder, kwargs)


def _run_pdf(parent, project, renderer, cards, d):
    from shoggoth import pdf_exporter
    folder = _folder_from(project, d['folder'])
    size = _resolve_size(d['size_label'])

    if d['export_images']:
        if d['flavor'] == 'pdf':
            fmt, quality, backs = d['format'], d['quality'], d['include_backs']
        else:
            fmt = _AZAO_FORMAT if d['flavor'] == 'azao' else _MBPRINT_FORMAT
            quality = _AZAO_QUALITY if d['flavor'] == 'azao' else _MBPRINT_QUALITY
            backs = False
        run_image_export(
            parent, renderer, cards, folder,
            size=size, bleed=True, format=fmt, quality=quality,
            include_backs=backs, rotate=True, text_as_html=d['vector_text'],
        )

    if d['flavor'] == 'azao':
        pdf_exporter.azao_pdf(cards, d['output_path'], d['back_output_path'], folder, size=size)
        return f"{d['output_path']}, {d['back_output_path']}"
    if d['flavor'] == 'mbprint':
        pdf_exporter.create_mbprint_pdf(cards, d['output_path'], folder, size=size)
    else:
        pdf_exporter.export(cards, d['output_path'], folder, size=size,
                             format=d['format'], include_backs=d['include_backs'])
    return d['output_path']


def _run_tts(parent, project, renderer, cards, scope_type, d):
    from shoggoth import tts_lib
    folder = _folder_from(project, d['folder'])
    if d['export_images']:
        run_image_export(
            parent, renderer, cards, folder,
            size=tts_lib.TTS_IMAGE_SIZE, bleed=False, separate_versions=False,
            format=tts_lib.TTS_IMAGE_FORMAT, quality=tts_lib.TTS_IMAGE_QUALITY,
            include_backs=False,
        )
    sync = d['sync']
    # 'campaign'/'all' keep tts_lib's dedicated bag structure (grouped by
    # encounter set); every other scope (player cards, or the new specific
    # encounter-sets/cards scopes) exports the resolved card list as one
    # flat TTS bag via export_player_cards, which accepts any card list.
    if scope_type == 'campaign':
        status, path = tts_lib.export_campaign(project, folder, sync=sync)
    elif scope_type == 'all':
        status, path = tts_lib.export_all(project, folder, sync=sync)
    else:
        status, path = tts_lib.export_player_cards(cards, folder, sync=sync)
    key = "TTS_RESULT_TTS_DIR" if status == 1 else "TTS_RESULT_PROJECT_DIR"
    return tr(key).format(path=path)


def _run_arkham_build(project, d):
    from shoggoth import arkham_build
    # d['export_thumbnails'] is a placeholder for a not-yet-implemented
    # feature and has no effect yet. arkham.build always exports the whole
    # project's JSON regardless of the profile's card scope -- the schema
    # describes the full project, not a card subset.
    data = arkham_build.export_project(project, image_pattern=d['url_pattern'])
    output_path = project.folder / f"{project.name}_arkham_build.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return str(output_path)


def _run_guides(project, d):
    count = 0
    for guide in project.guides:
        base = _safe_filename(guide.name)
        if d['export_pdf']:
            guide.render_to_file(output_path=project.folder / f'{base}.pdf')
        if d['export_html']:
            html = guide.to_html()
            (project.folder / f'{base}.html').write_text(html, encoding='utf-8')
        count += 1
    return count


def run_profile(parent, project, renderer, profile_data):
    """Run every enabled section of profile_data ({'scope', 'sections'})
    against project. Returns (results, errors): lists of user-facing
    message strings for a summary dialog."""
    scope = profile_data.get('scope', {'type': 'all'})
    sections = profile_data['sections']
    cards = resolve_scope_cards(project, scope)

    results, errors = [], []

    if sections['pdf']['enabled']:
        from shoggoth.pdf_exporter import check_prince_installed
        if not check_prince_installed():
            errors.append(tr("PE_PRINCE_NOT_INSTALLED"))
        else:
            try:
                path = _run_pdf(parent, project, renderer, cards, sections['pdf'])
                results.append(tr("PE_RESULT_PDF").format(path=path))
            except Exception as e:
                errors.append(tr("PE_RESULT_ERROR_PDF").format(error=e))

    if sections['tts']['enabled']:
        try:
            msg = _run_tts(parent, project, renderer, cards, scope.get('type', 'all'), sections['tts'])
            results.append(msg)
        except Exception as e:
            errors.append(tr("PE_RESULT_ERROR_TTS").format(error=e))

    if sections['arkham_build']['enabled']:
        try:
            path = _run_arkham_build(project, sections['arkham_build'])
            results.append(tr("PE_RESULT_ARKHAM_BUILD").format(path=path))
        except Exception as e:
            errors.append(tr("PE_RESULT_ERROR_ARKHAM_BUILD").format(error=e))

    if sections['guides']['enabled']:
        try:
            count = _run_guides(project, sections['guides'])
            results.append(tr("PE_RESULT_GUIDES").format(count=count))
        except Exception as e:
            errors.append(tr("PE_RESULT_ERROR_GUIDES").format(error=e))

    # Images always run last, see module docstring.
    if sections['images']['enabled']:
        try:
            _run_images(parent, project, renderer, cards, sections['images'])
            results.append(tr("PE_RESULT_IMAGES"))
        except Exception as e:
            errors.append(tr("PE_RESULT_ERROR_IMAGES").format(error=e))

    return results, errors


def summarize(results, errors):
    summary = '\n'.join(results) if results else tr("PE_RESULT_NONE")
    if errors:
        summary += '\n\n' + tr("PE_RESULT_ERRORS_HEADER") + '\n' + '\n'.join(errors)
    return summary
