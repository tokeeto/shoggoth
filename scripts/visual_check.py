"""Visual regression check: render the test project and compare it with the
images you approved last time.

    uv run python scripts/visual_check.py            # render, compare, ask
    uv run python scripts/visual_check.py --check    # never ask: exit 1 on any difference
    uv run python scripts/visual_check.py --accept   # take the new renders as the baseline
    uv run python scripts/visual_check.py --card ID  # only one card (quick look; nothing is approved)

Everything lives in the user data folder (next to the asset pack), not in the
repository, because the result depends on the installed asset pack and on
this machine's fonts and libraries:

    <user data>/visual_check/baseline/   approved renders + manifest.json
    <user data>/visual_check/current/    the renders from this run
    <user data>/visual_check/review/     side-by-side images + index.html of what changed

Each card of test_case/test_case.json is rendered at half size, and compared
pixel by pixel with its baseline. Any difference -- or any error the renderer
logged while rendering, since it carries on after a failing step -- is shown,
and you decide: approve (the new renders become the baseline) or reject
(exit code 1, which stops a release).
"""
import argparse
import hashlib
import html
import json
import logging
import shutil
import sys
import time
import webbrowser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Same asset folder as `uv run shoggoth` (tool.py loads .env too), e.g. a
# SHOGGOTH_ASSET_DIR pointing at a checkout of the asset repository
from dotenv import load_dotenv  # noqa: E402
load_dotenv(REPO / '.env')

TEST_PROJECT = REPO / 'test_case' / 'test_case.json'

# A pixel counts as changed when a channel differs by more than this (out of
# 255), and an image as changed when more than MAX_CHANGED_PIXELS do. Renders
# are deterministic on one machine, so these only absorb rounding noise.
PIXEL_TOLERANCE = 8
MAX_CHANGED_PIXELS = 0


class _ErrorCollector(logging.Handler):
    """Collects the errors the renderer logs (and otherwise shrugs off)."""

    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _paths():
    from shoggoth.files import root_dir
    base = root_dir / 'visual_check'
    return base / 'baseline', base / 'current', base / 'review'


def _asset_version():
    """(asset folder, commit) of the asset pack in use: a git checkout's HEAD
    (+ '-dirty' with uncommitted changes), else the downloaded pack's commit."""
    import subprocess
    from shoggoth import updater
    from shoggoth.files import asset_dir

    def git(*args):
        result = subprocess.run(['git', '-C', str(asset_dir), *args], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else None

    if (asset_dir / '.git').exists() and (head := git('rev-parse', 'HEAD')):
        return str(asset_dir), head + ('-dirty' if git('status', '--porcelain') else '')
    _, sha, _ = updater._get_local_asset_state()
    return str(asset_dir), sha


def _manifest():
    """What the renders depend on, so a diff can be explained."""
    from shoggoth import updater
    asset_folder, asset_commit = _asset_version()
    return {
        'shoggoth': updater.get_current_version(),
        'asset_dir': asset_folder,
        'asset_commit': asset_commit,
        'test_project_sha256': hashlib.sha256(TEST_PROJECT.read_bytes()).hexdigest(),
        'rendered_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }


def render(folder, card_id=None):
    """Renders the test project into `folder`. Returns (file names, logged errors)."""
    from shoggoth.project import Project
    from shoggoth.renderer import CardRenderer, renderer_for_card
    from shoggoth.settings import EXPORT_SIZES

    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)

    collector = _ErrorCollector()
    logger = logging.getLogger('shoggoth')
    logger.addHandler(collector)
    try:
        project = Project.load(TEST_PROJECT)
        renderer = CardRenderer(locale=project.language)
        cards = [project.get_card(card_id)] if card_id else project.get_all_cards()
        if cards == [None]:
            sys.exit(f'No card with id {card_id} in {TEST_PROJECT}')
        size = EXPORT_SIZES[1][1]  # half size: plenty to spot a problem, 4x faster
        for card in cards:
            print(f'  rendering {card.name}')
            outputs = renderer_for_card(renderer, card).export_card_images(
                card, str(folder), size, include_backs=True, bleed=True, format='png', quality=100)
            if not outputs:
                logger.error('No images exported for card %s (%s)', card.name, card.id)
    finally:
        logger.removeHandler(collector)
    return sorted(p.name for p in folder.glob('*.png')), collector.records


def compare(baseline, current, names):
    """Returns (changed, added, removed): changed is [(name, changed pixel count)]."""
    from PIL import Image, ImageChops

    old_names = {p.name for p in baseline.glob('*.png')}
    changed = []
    for name in names:
        if name not in old_names:
            continue
        with Image.open(baseline / name) as old, Image.open(current / name) as new:
            old, new = old.convert('RGB'), new.convert('RGB')
            if old.size != new.size:
                changed.append((name, old.width * old.height))
                continue
            diff = ImageChops.difference(old, new).convert('L').point(lambda v: 255 if v > PIXEL_TOLERANCE else 0)
            count = diff.histogram()[255]
            if count > MAX_CHANGED_PIXELS:
                changed.append((name, count))
    added = [n for n in names if n not in old_names]
    removed = sorted(old_names - set(names))
    return changed, added, removed


def _side_by_side(old_path, new_path, out_path):
    """baseline | new | changed pixels in red over a faded copy of the new one."""
    from PIL import Image, ImageChops

    with Image.open(old_path) as old, Image.open(new_path) as new:
        old, new = old.convert('RGB'), new.convert('RGB')
        if old.size != new.size:
            old = old.resize(new.size)
        mask = ImageChops.difference(old, new).convert('L').point(lambda v: 255 if v > PIXEL_TOLERANCE else 0)
        faded = Image.blend(new.convert('L').convert('RGB'), Image.new('RGB', new.size, 'white'), 0.6)
        faded.paste(Image.new('RGB', new.size, (230, 0, 0)), mask=mask)
        sheet = Image.new('RGB', (new.width * 3 + 20, new.height), 'white')
        for i, image in enumerate((old, new, faded)):
            sheet.paste(image, (i * (new.width + 10), 0))
        sheet.save(out_path)


def write_review(baseline, current, review, changed, added, removed, errors):
    """Writes review/index.html (+ side-by-side images); returns its path."""
    if review.exists():
        shutil.rmtree(review)
    review.mkdir(parents=True)
    parts = ['<!doctype html><meta charset="utf-8"><title>Visual check</title>',
             '<style>body{font-family:sans-serif;margin:16px;background:#f4f4f4}'
             'img{max-width:100%;border:1px solid #ccc;background:white}'
             'section{margin-bottom:32px}pre{background:#fff;padding:8px;overflow:auto}</style>',
             '<h1>Visual check</h1>']
    if errors:
        parts.append(f'<h2>Renderer errors ({len(errors)})</h2>')
        for record in errors:
            parts.append(f'<pre>{html.escape(_format_error(record))}</pre>')
    if changed:
        parts.append(f'<h2>Changed ({len(changed)}) &mdash; approved | new | difference</h2>')
        for name, count in changed:
            _side_by_side(baseline / name, current / name, review / name)
            parts.append(f'<section><h3>{html.escape(name)} &mdash; {count} pixels</h3>'
                         f'<img src="{html.escape(name)}"></section>')
    if added:
        parts.append(f'<h2>New ({len(added)})</h2>')
        for name in added:
            shutil.copy(current / name, review / name)
            parts.append(f'<section><h3>{html.escape(name)}</h3><img src="{html.escape(name)}" style="max-width:400px"></section>')
    if removed:
        parts.append(f'<h2>No longer rendered ({len(removed)})</h2><ul>')
        parts.extend(f'<li>{html.escape(name)}</li>' for name in removed)
        parts.append('</ul>')
    index = review / 'index.html'
    index.write_text('\n'.join(parts), encoding='utf-8')
    return index


def _format_error(record):
    text = record.getMessage()
    if record.exc_info:
        text += '\n' + logging.Formatter().formatException(record.exc_info)
    return text


def _describe_manifest_change(old, new):
    notes = []
    for key, label in (('asset_dir', 'asset folder'), ('asset_commit', 'asset pack'), ('test_project_sha256', 'test project'), ('shoggoth', 'Shoggoth version')):
        if old.get(key) != new.get(key):
            notes.append(f'{label} changed since the baseline ({str(old.get(key))[:10]} -> {str(new.get(key))[:10]})')
    return notes


def accept(baseline, current, manifest):
    if baseline.exists():
        shutil.rmtree(baseline)
    shutil.copytree(current, baseline)
    (baseline / 'manifest.json').write_text(json.dumps(manifest, indent=4), encoding='utf-8')


def ask(question):
    try:
        return input(f'{question} [y/N] ').strip().lower() in ('y', 'yes')
    except EOFError:
        return False


def run(mode='ask', card_id=None, open_browser=True):
    """Returns True when the renders are approved (or unchanged)."""
    baseline, current, review = _paths()
    from shoggoth.files import asset_dir
    print(f'Rendering {TEST_PROJECT.relative_to(REPO)} into {current}')
    print(f'Assets: {asset_dir}')
    started = time.time()
    names, errors = render(current, card_id)
    manifest = _manifest()
    print(f'Rendered {len(names)} images in {time.time() - started:.1f}s')

    if card_id:
        print(f'Single card rendered to {current}; nothing compared or approved.')
        return not errors

    first_run = not (baseline / 'manifest.json').exists()
    if first_run:
        changed, added, removed = [], names, []
    else:
        changed, added, removed = compare(baseline, current, names)

    if mode == 'accept':
        accept(baseline, current, manifest)
        print(f'Accepted {len(names)} images as the new baseline.')
        return True

    if not (changed or added or removed or errors):
        print('No visual changes.')
        return True

    index = write_review(baseline, current, review, changed, added, removed, errors)
    print()
    if first_run:
        print(f'No baseline yet: {len(names)} new images.')
    else:
        old_manifest = json.loads((baseline / 'manifest.json').read_text(encoding='utf-8'))
        for note in _describe_manifest_change(old_manifest, manifest):
            print(f'  note: {note}')
        for name, count in changed:
            print(f'  changed  {name}  ({count} pixels)')
        for name in added:
            print(f'  new      {name}')
        for name in removed:
            print(f'  gone     {name}')
    for record in errors:
        print(f'  ERROR    {record.getMessage()}')
    print(f'\nReview: {index}')

    if mode == 'check':
        return False
    if open_browser:
        webbrowser.open(index.as_uri())
    if errors and not ask(f'The renderer logged {len(errors)} error(s). Continue anyway?'):
        return False
    if ask('Approve these renders as the new baseline?'):
        accept(baseline, current, manifest)
        print('Approved.')
        return True
    print('Rejected.')
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--check', action='store_true', help='never ask; exit 1 on any difference')
    group.add_argument('--accept', action='store_true', help='take the new renders as the baseline without asking')
    parser.add_argument('--card', metavar='ID', help='only render this card (nothing is compared)')
    parser.add_argument('--no-browser', action='store_true', help="don't open the review page")
    args = parser.parse_args()
    mode = 'check' if args.check else 'accept' if args.accept else 'ask'
    sys.exit(0 if run(mode, args.card, not args.no_browser) else 1)


if __name__ == '__main__':
    main()
