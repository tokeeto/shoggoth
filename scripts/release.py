"""Make a release: check everything, bump the version, tag and push.

    uv run python scripts/release.py              # next patch version (0.10.11 -> 0.10.12)
    uv run python scripts/release.py minor        # 0.10.11 -> 0.11.0
    uv run python scripts/release.py 1.0.0        # an exact version
    uv run python scripts/release.py --dry-run    # only run the checks

In order, stopping at the first thing that isn't right:

1. git: on main, no uncommitted changes to tracked files, not behind origin,
   the new tag doesn't exist yet.
2. ruff and the test suite, including the tests that need the asset pack.
3. The visual check (scripts/visual_check.py): renders the test project and
   asks you to approve any difference from the last approved renders.
4. Release notes: written in your editor ($VISUAL / $EDITOR, else you're asked
   to edit a file), prefilled with the commits since the last release. They
   become the tag message, which CI publishes as the GitHub release text.
5. After a last confirmation: bump the version in pyproject.toml (and uv.lock),
   commit, make the annotated tag, push both. CI then builds and publishes.

The tag CI receives always matches pyproject.toml (CI checks that too), so a
release can't go out with the wrong version number.
"""
import argparse
import os
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYPROJECT = REPO / 'pyproject.toml'
NOTES_FILE = REPO / '.release_notes.txt'
RELEASE_BRANCH = 'main'

sys.path.insert(0, str(REPO / 'scripts'))


def git(*args, check=True):
    result = subprocess.run(['git', *args], cwd=REPO, capture_output=True, text=True)
    if check and result.returncode != 0:
        fail(f'git {" ".join(args)} failed:\n{result.stderr.strip()}')
    return result.stdout.strip()


def fail(message):
    print(f'\n✗ {message}\n\nRelease aborted.')
    sys.exit(1)


def ok(message):
    print(f'✓ {message}')


def ask(question):
    try:
        return input(f'{question} [y/N] ').strip().lower() in ('y', 'yes')
    except EOFError:
        return False


def current_version():
    return tomllib.loads(PYPROJECT.read_text(encoding='utf-8'))['project']['version']


def next_version(current, bump):
    if re.fullmatch(r'\d+\.\d+\.\d+', bump):
        return bump
    major, minor, patch = (int(part) for part in current.split('.'))
    if bump == 'major':
        return f'{major + 1}.0.0'
    if bump == 'minor':
        return f'{major}.{minor + 1}.0'
    if bump == 'patch':
        return f'{major}.{minor}.{patch + 1}'
    fail(f'Unknown version "{bump}": use patch, minor, major or X.Y.Z')


def check_git(tag):
    branch = git('rev-parse', '--abbrev-ref', 'HEAD')
    if branch != RELEASE_BRANCH:
        fail(f'You are on "{branch}". Releases are made from {RELEASE_BRANCH}.')
    dirty = git('status', '--porcelain', '--untracked-files=no')
    if dirty:
        fail(f'Uncommitted changes -- commit or stash them first:\n{dirty}')
    git('fetch', '--quiet', '--tags', 'origin')
    behind = git('rev-list', '--count', f'HEAD..origin/{RELEASE_BRANCH}')
    if behind != '0':
        fail(f'{RELEASE_BRANCH} is {behind} commit(s) behind origin -- pull first.')
    if git('tag', '-l', tag):
        fail(f'Tag {tag} already exists.')
    ok(f'git: on {RELEASE_BRANCH}, clean, up to date, {tag} is free')


def run_step(label, command, env=None):
    print(f'\n── {label} ──')
    if subprocess.run(command, cwd=REPO, env={**os.environ, **(env or {})}).returncode != 0:
        fail(f'{label} failed.')
    ok(label)


def last_tag():
    return git('describe', '--tags', '--abbrev=0', '--match', 'v*', check=False) or None


def write_notes(version):
    """Lets you write the release notes; returns them (comment lines removed)."""
    previous = last_tag()
    log = git('log', '--no-merges', '--format=%s', f'{previous}..HEAD' if previous else 'HEAD')
    lines = [
        f'# Release notes for v{version}. Lines starting with # are ignored.',
        '# These become the GitHub release text. Commits since '
        f'{previous or "the beginning"}:',
        *(f'#   {subject}' for subject in log.splitlines()),
        '',
        '- ',
    ]
    NOTES_FILE.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    editor = os.environ.get('VISUAL') or os.environ.get('EDITOR')
    if editor:
        print(f'\nOpening {editor} for the release notes (save and close to continue).')
        print('  (GUI editors need a wait flag, e.g. EDITOR="zed --wait" or "subl -w".)')
        subprocess.run([*shlex.split(editor), str(NOTES_FILE)])
    else:
        input(f'\nWrite the release notes in {NOTES_FILE}, save, then press Enter here. ')
    text = NOTES_FILE.read_text(encoding='utf-8')
    NOTES_FILE.unlink()
    notes = '\n'.join(line for line in text.splitlines() if not line.startswith('#')).strip()
    if not notes or notes == '-':
        fail('No release notes.')
    return notes


def bump_files(version):
    text = PYPROJECT.read_text(encoding='utf-8')
    new_text, count = re.subn(r'(?m)^(version\s*=\s*")[^"]+(")', rf'\g<1>{version}\g<2>', text, count=1)
    if count != 1:
        fail('Could not find the version line in pyproject.toml')
    PYPROJECT.write_text(new_text, encoding='utf-8')
    if subprocess.run(['uv', 'lock', '--quiet'], cwd=REPO).returncode != 0:
        fail('uv lock failed (pyproject.toml has been bumped; revert it with git checkout pyproject.toml)')
    if current_version() != version:
        fail('pyproject.toml did not end up with the new version')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('version', nargs='?', default='patch', help='patch (default), minor, major or X.Y.Z')
    parser.add_argument('--dry-run', action='store_true', help='run the checks only; change nothing')
    args = parser.parse_args()
    sys.stdout.reconfigure(line_buffering=True)  # keep our lines in order with the subprocesses'

    old = current_version()
    new = next_version(old, args.version)
    tag = f'v{new}'
    print(f'Releasing {old} -> {new}' + (' (dry run)' if args.dry_run else ''))

    if args.dry_run:
        print(f'(dry run: skipping the git checks for {RELEASE_BRANCH})')
    else:
        check_git(tag)
    run_step('Lint', ['uv', 'run', 'ruff', 'check'])
    # tests marked `assets` skip without the asset pack; a release runs them all
    run_step('Tests', ['uv', 'run', 'pytest'], env={'SHOGGOTH_REQUIRE_ASSETS': '1'})

    print('\n── Visual check ──')
    import visual_check
    if not visual_check.run('ask'):
        fail('Visual check not approved.')
    ok('Visual check')

    if args.dry_run:
        print('\nAll checks passed. Dry run: nothing changed.')
        return

    notes = write_notes(new)
    print(f'\n── About to release {tag} ──\n{notes}\n')
    if not ask(f'Bump to {new}, commit, tag {tag} and push to origin?'):
        fail('Not confirmed.')

    bump_files(new)
    # uv.lock only when the repository tracks it (it's gitignored at the moment)
    git('add', 'pyproject.toml', *(['uv.lock'] if git('ls-files', 'uv.lock') else []))
    git('commit', '-m', f'Release {tag}')
    git('tag', '-a', tag, '-m', notes)
    git('push', 'origin', RELEASE_BRANCH)
    git('push', 'origin', tag)
    ok(f'Released {tag}. CI is building it: https://github.com/tokeeto/shoggoth/actions')


if __name__ == '__main__':
    main()
