"""
Executes an export profile's entries, in order, against a project.

Shared by ProjectExportDialog (built from live widget state) and the
Export -> Setups quick-run menu (built straight from a saved profile), so
both paths behave identically.

Entries run strictly in list order and each one blocks until its own threads
have joined before the next starts -- so a later entry can rely on an
earlier one's output already being on disk (e.g. a TTS entry with
`export_images=False` reusing images an earlier Images entry just rendered
to the same folder), and a `publish` entry uploads exactly the window of
content produced by entries since the previous `publish` entry (or the start
of the run) -- see the `produced`/`manifest_cards` reset in run_profile.
"""
import json
import multiprocessing
import threading
import traceback
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QProgressDialog

from shoggoth import telemetry
from shoggoth.export_profile import ExportEntry, USES_SCOPE
from shoggoth.files import default_export_folder, safe_filename
from shoggoth.i18n import tr
from shoggoth.renderer import renderer_for_card
from shoggoth.settings import EXPORT_SIZES
from shoggoth.ui.export_widgets import resolve_scope_cards, run_image_export

_MBPRINT_FORMAT, _MBPRINT_QUALITY = 'png', 100


def _resolve_size(label):
    for lbl, size in EXPORT_SIZES:
        if lbl == label:
            return size
    return EXPORT_SIZES[1][1]


def _default_folder(project):
    return default_export_folder(project)


def _resolve_path(project, value):
    """Resolve a user-supplied path against the project folder, so relative
    paths (e.g. './exports') stay meaningful when a profile is shared between
    machines instead of depending on the app's current working directory."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else project.folder / path


def _folder_from(project, setting):
    return _resolve_path(project, setting) if setting else _default_folder(project)


def _export_numbered_cards(parent, renderer, cards, folder, kwargs):
    """Like export_widgets.run_image_export, but assigns each card a running
    `number` (needed by some filename_format patterns), matching the
    original per-card numbering the Images section always used.

    Returns (entries, card_faces):
      - entries: (card, path) for every path `export_card_images` reported
        writing (see export_widgets.run_image_export's docstring re:
        duplicates) -- the card is kept alongside its path so the Publish
        section can group each image's remote upload by encounter set.
      - card_faces: {card.id: {'front': path|None, 'back': path|None}}, one
        entry per card, for the Publish section's card manifest sync (see
        _build_card_manifest). `export_card_images` doesn't label which
        output is which face, but its front/back loop always appends exactly
        two entries per version in that order -- outputs[0]/outputs[1] are
        reliably the *first* version's front/back (a card's other versions,
        if any, are only relevant to print layout, not this id->name/image
        mapping, so they're not tracked here)."""
    if not cards:
        return [], {}
    progress = QProgressDialog(tr("STATUS_EXPORTING"), tr("BTN_CANCEL"), 0, len(cards), parent)
    progress.setWindowModality(Qt.WindowModal)
    progress.setMinimumDuration(0)
    cores = max(4, multiprocessing.cpu_count() - 1)
    threads = []
    entries = []
    card_faces = {}
    number = 1
    for i, card in enumerate(cards):
        if progress.wasCanceled():
            break
        if i >= cores:
            threads[i - cores].join()
            progress.setValue(i - cores)
        progress.setLabelText(tr("MSG_EXPORTING_CARD").format(name=card.name))

        def _target(card=card, kw=dict(kwargs, number=number)):
            outputs = renderer_for_card(renderer, card).export_card_images(card, str(folder), **kw)
            if outputs:
                entries.extend((card, p) for p in outputs)
                card_faces[card.id] = {
                    "front": outputs[0],
                    "back": outputs[1] if len(outputs) > 1 else None,
                }

        t = threading.Thread(target=_target)
        threads.append(t)
        t.start()
        number += card.amount
    for t in threads:
        t.join()
    progress.setValue(len(cards))
    return entries, card_faces


def _run_images(parent, project, renderer, cards, d):
    """Returns (entries, card_faces) -- see _export_numbered_cards."""
    from shoggoth.card import natural_sort_key
    cards = sorted(cards, key=lambda c: natural_sort_key(c.project_number))
    folder = _folder_from(project, d['folder'])
    folder.mkdir(parents=True, exist_ok=True)
    size = _resolve_size(d['size_label'])
    kwargs = {
        "size": size,
        "bleed": d['bleed'],
        "format": d['format'],
        "quality": d['quality'],
        "include_backs": d['include_backs'],
        "separate_versions": d['separate_versions'],
        "rotate": d['rotate'],
        "filename_format": d['filename_format'],
        "rounded": d.get('rounded', False),
    }
    return _export_numbered_cards(parent, renderer, cards, folder, kwargs)


def _run_pdf(parent, project, renderer, cards, d):
    """Returns (result_path_str, produced_pdf_paths) -- the supporting card
    images rendered for the layout aren't returned, since they're
    print-layout-specific renders (rotated, un-bled, etc.), not standalone
    publishable images."""
    import shoggoth
    from shoggoth import pdf_exporter
    folder = _folder_from(project, d['folder'])
    size = _resolve_size(d['size_label'])
    output_path = str(_resolve_path(project, d['output_path']))
    back_output_path = str(_resolve_path(project, d['back_output_path'])) if d.get('back_output_path') else None
    cmyk_profile = shoggoth.app.config.get('Shoggoth', 'cmyk_profile') or None

    if d['flavor'] == 'pdf':
        fmt, quality, backs = d['format'], d['quality'], d['include_backs']
    elif d['flavor'] == 'azao':
        fmt, quality, backs = d.get('azao_format', 'jpeg'), d.get('azao_quality', 95), False
    else:
        fmt, quality, backs = _MBPRINT_FORMAT, _MBPRINT_QUALITY, False

    # Rounded corners only apply to the plain flavor, and only make sense
    # without a bleed margin/cut guides -- a rounded, exact-size card is an
    # alternative to trimming, not an addition to it.
    rounded = d['flavor'] == 'pdf' and d.get('rounded', False)
    if d['export_images']:
        run_image_export(
            parent, renderer, cards, folder,
            size=size, bleed=not rounded, format=fmt, quality=quality,
            include_backs=backs, rotate=True, text_as_html=d['vector_text'],
            rounded=rounded,
        )

    if d['flavor'] == 'azao':
        pdf_exporter.azao_pdf(cards, output_path, back_output_path, folder, size=size,
                               format=fmt, cmyk_profile=cmyk_profile)
        return f"{output_path}, {back_output_path}", [output_path, back_output_path]
    if d['flavor'] == 'mbprint':
        pdf_exporter.create_mbprint_pdf(cards, output_path, folder, size=size, cmyk_profile=cmyk_profile)
    else:
        pdf_exporter.export(cards, output_path, folder, size=size,
                             format=d['format'], include_backs=d['include_backs'], cmyk_profile=cmyk_profile)
    return output_path, [output_path]


def _run_tts(parent, project, renderer, cards, scope_type, d):
    """Returns (message, card_image_paths, wrapper_output_path). The image
    paths and wrapper path are needed separately by the Publish section:
    the images get uploaded, then the *already-written* wrapper JSON gets
    read back, rewritten to point at the uploaded URLs, and re-saved -- see
    export_runner's caller / publish_dialog.py."""
    from shoggoth import tts_lib
    folder = _folder_from(project, d['folder'])
    if d['export_images']:
        _cancelled, image_paths = run_image_export(
            parent, renderer, cards, folder,
            size=tts_lib.TTS_IMAGE_SIZE, bleed=False, separate_versions=False,
            format=tts_lib.TTS_IMAGE_FORMAT, quality=tts_lib.TTS_IMAGE_QUALITY,
            include_backs=False, rotate='tts', rounded=True,
        )
    else:
        # Images weren't (re-)rendered this run, but Publish still needs to
        # know their expected paths to upload/rewrite whatever's already on
        # disk from a previous export -- compute them the same way
        # tts_lib.card_to_tts does internally. Generic player/encounter/
        # upgradesheet backs are rendered to one shared file per type (not
        # this per-card naming scheme) and their URL is overridden by
        # tts_lib.DEFAULT_IMAGES anyway, so the computed path for those is
        # never actually referenced -- filter to files that really exist
        # rather than trying to replicate that override logic here.
        from shoggoth.renderer import CardRenderer
        image_paths = [
            p for card in cards
            for p in CardRenderer.expected_export_paths(
                card, folder, include_backs=True, format=tts_lib.TTS_IMAGE_FORMAT,
                separate_versions=False,
            )
            if Path(p).exists()
        ]
    sync = d['sync']
    update_file = d['update_file']
    # 'campaign'/'all' keep tts_lib's dedicated bag structure (grouped by
    # encounter set); every other scope (player cards, or the new specific
    # encounter-sets/cards scopes) exports the resolved card list as one
    # flat TTS bag via export_player_cards, which accepts any card list.
    if update_file and Path(update_file).exists():
        status = tts_lib.update_file(cards, folder, update_file)
        path = update_file
    elif scope_type == 'campaign':
        status, path = tts_lib.export_campaign(project, folder, sync=sync)
    elif scope_type == 'all':
        status, path = tts_lib.export_all(project, folder, sync=sync)
    else:
        status, path = tts_lib.export_player_cards(cards, folder, sync=sync)

    key = "TTS_RESULT_TTS_DIR"
    if update_file and Path(update_file).exists():
        key = "TTS_RESULT_UPDATED_FILE"
    elif status != 1:
        key = "TTS_RESULT_PROJECT_DIR"
    return tr(key).format(path=path), image_paths, str(path)


def _run_arkham_build(project, renderer, d):
    """Returns (result_path_str, produced_paths)."""
    from shoggoth import arkham_build
    # d['export_thumbnails'] is a placeholder for a not-yet-implemented
    # feature and has no effect yet. arkham.build always exports the whole
    # project's JSON regardless of the profile's card scope -- the schema
    # describes the full project, not a card subset.
    data = arkham_build.export_project(project, renderer, image_pattern=d['url_pattern'])
    output_path = project.folder / f"{project.name}_arkham_build.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return str(output_path), [str(output_path)]


def _run_guides(project, d):
    """Returns (count, pdf_paths) -- HTML exports aren't published (the
    server has no bucket for them; the PDF is the distributable artifact)."""
    count = 0
    pdf_paths = []
    for guide in project.guides:
        base = safe_filename(guide.name)
        if d['export_pdf']:
            out = project.folder / f'{base}.pdf'
            guide.render_to_file(output_path=out)
            pdf_paths.append(str(out))
        if d['export_html']:
            html = guide.to_html()
            (project.folder / f'{base}.html').write_text(html, encoding='utf-8')
        count += 1
    return count, pdf_paths


def run_profile(parent, project, renderer, profile_data):
    """Run every entry of profile_data ({'entries': [...]}) against project,
    in order. Returns (results, errors): lists of user-facing message
    strings for a summary dialog."""
    results, errors = [], []
    # Content produced so far in the current "window" (since the run started
    # or the last `publish` entry, whichever is most recent) -- a `publish`
    # entry uploads exactly this window, then it's reset, so entries after it
    # start a fresh window (see module docstring). produced['images'] is
    # (card, path) pairs (see _run_images); every other list is plain local
    # paths.
    produced = {'images': [], 'pdf': [], 'data': [], 'guides': []}
    manifest_cards = []  # cards contributed by Images entries in the current window
    card_faces = {}  # {card.id: {'front', 'back'}}, for the card manifest
    tts_result = None  # {'image_paths', 'wrapper_path', 'sync'} from the most recent TTS entry this window
    attempted_kinds = set()  # actual export kinds run this call, for telemetry ('publish' excluded)

    for raw_entry in profile_data.get('entries', []):
        entry = ExportEntry(raw_entry, project)
        kind, settings = entry.type, entry.settings
        cards = resolve_scope_cards(project, entry.scope) if USES_SCOPE.get(kind) else None
        if kind != 'publish':
            attempted_kinds.add(kind)

        if kind == 'pdf':
            from shoggoth.pdf_exporter import check_prince_installed
            if not check_prince_installed():
                errors.append(tr("PE_PRINCE_NOT_INSTALLED"))
                continue
            try:
                path, pdf_paths = _run_pdf(parent, project, renderer, cards, settings)
                produced['pdf'].extend(pdf_paths)
                results.append(tr("PE_RESULT_PDF").format(path=path))
            except Exception as e:
                errors.append(tr("PE_RESULT_ERROR_PDF").format(error=e))

        elif kind == 'tts':
            try:
                msg, image_paths, wrapper_path = _run_tts(
                    parent, project, renderer, cards, entry.scope.get('type', 'all'), settings
                )
                tts_result = {
                    'image_paths': image_paths,
                    'wrapper_path': wrapper_path,
                    'sync': settings['sync'],
                    'update_file': settings['update_file']
                }
                results.append(msg)
            except Exception as e:
                traceback.print_exc()
                errors.append(tr("PE_RESULT_ERROR_TTS").format(error=e))

        elif kind == 'arkham_build':
            try:
                path, data_paths = _run_arkham_build(project, renderer, settings)
                produced['data'].extend(data_paths)
                results.append(tr("PE_RESULT_ARKHAM_BUILD").format(path=path))
            except Exception as e:
                errors.append(tr("PE_RESULT_ERROR_ARKHAM_BUILD").format(error=e))

        elif kind == 'guides':
            try:
                count, guide_paths = _run_guides(project, settings)
                produced['guides'].extend(guide_paths)
                results.append(tr("PE_RESULT_GUIDES").format(count=count))
            except Exception as e:
                errors.append(tr("PE_RESULT_ERROR_GUIDES").format(error=e))

        elif kind == 'images':
            try:
                image_paths, faces = _run_images(parent, project, renderer, cards, settings)
                produced['images'].extend(image_paths)
                card_faces.update(faces)
                manifest_cards.extend(cards)
                results.append(tr("PE_RESULT_IMAGES"))
            except Exception as e:
                errors.append(tr("PE_RESULT_ERROR_IMAGES").format(error=e))

        elif kind == 'publish':
            from shoggoth.cloud import registry
            provider = registry.get_provider(settings.get('provider'))
            if provider is None:
                errors.append(tr("PE_RESULT_ERROR_PUBLISH").format(
                    error=tr("PE_PUBLISH_UNKNOWN_PROVIDER").format(provider=settings.get('provider'))
                ))
                continue
            try:
                msg = provider.run(parent, project, manifest_cards, card_faces, produced, tts_result, settings)
                if msg:
                    results.append(msg)
            except Exception as e:
                traceback.print_exc()
                errors.append(tr("PE_RESULT_ERROR_PUBLISH").format(error=e))
            finally:
                produced = {'images': [], 'pdf': [], 'data': [], 'guides': []}
                manifest_cards, card_faces, tts_result = [], {}, None

    if attempted_kinds:
        telemetry.record_export(attempted_kinds)

    return results, errors


def summarize(results, errors):
    summary = '\n'.join(results) if results else tr("PE_RESULT_NONE")
    if errors:
        summary += '\n\n' + tr("PE_RESULT_ERRORS_HEADER") + '\n' + '\n'.join(errors)
    return summary
