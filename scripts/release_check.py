#!/usr/bin/env python3
"""
The check to run before tagging a release:

    uv run python scripts/release_check.py

It runs the whole test suite -- including the tests that need the asset pack
in SHOGGOTH_ASSET_DIR (usually set in .env), which the build on GitHub can't
run -- and refuses to pass if that folder has no pack, or if a
`RELEASE-BLOCKER` note is left in the code. When
everything passes it writes release_check.json, a record of exactly which
code was checked. Commit that file with the release.

The build verifies the record (`--verify`, no dependencies needed): a tag
whose code differs from what was checked doesn't get built. So does a tag
that was never checked at all.

Leave a note for yourself wherever something isn't finished:

    # RELEASE-BLOCKER: the PDF path still uses the old field name
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORD = ROOT / 'release_check.json'
# What the record covers: the code that ships, and the tests that vouch for it.
CHECKED = ('shoggoth', 'tests')
IGNORED_DIRS = {'__pycache__', 'render_output', '.pytest_cache'}
BLOCKER = re.compile(r'RELEASE-BLOCKER\b:?\s*(.*)')


def checked_files():
    for folder in CHECKED:
        for path in sorted((ROOT / folder).rglob('*')):
            if path.is_file() and not IGNORED_DIRS & set(path.parts) and path.suffix != '.pyc':
                yield path


def source_fingerprint():
    """ One hash over every checked file (line endings normalised, so a
        Windows checkout gives the same answer).
    """
    digest = hashlib.sha256()
    for path in checked_files():
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(b'\0')
        digest.update(path.read_bytes().replace(b'\r\n', b'\n'))
        digest.update(b'\0')
    return digest.hexdigest()


def release_blockers():
    found = []
    for path in (ROOT / 'shoggoth').rglob('*.py'):
        for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
            if match := BLOCKER.search(line):
                found.append(f'{path.relative_to(ROOT)}:{number}: {match.group(1).strip()}')
    return found


def verify():
    blockers = release_blockers()
    if blockers:
        print('Unfinished work is marked in the code:\n  ' + '\n  '.join(blockers))
        return 1
    if not RECORD.exists():
        print('release_check.json is missing: run `uv run python scripts/release_check.py` and commit the result.')
        return 1
    record = json.loads(RECORD.read_text(encoding='utf-8'))
    if record.get('source') != source_fingerprint():
        print('The code has changed since the release check last passed.\n'
              'Run `uv run python scripts/release_check.py` and commit release_check.json.')
        return 1
    print(f"Release check on record for this code (Shoggoth {record.get('shoggoth')}, "
          f"asset pack {str(record.get('assets'))[:7]}).")
    return 0


def run(pytest_args):
    blockers = release_blockers()
    if blockers:
        print('Unfinished work is marked in the code:\n  ' + '\n  '.join(blockers))
        return 1

    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
    sys.path.insert(0, str(ROOT))
    from shoggoth import files, updater
    if not files.custom_asset_dir or not files.defaults_dir.is_dir():
        print(f'No asset pack to test against ({files.asset_dir}): set SHOGGOTH_ASSET_DIR in .env.')
        return 1

    env = {**os.environ, 'SHOGGOTH_REQUIRE_ASSETS': '1'}
    result = subprocess.run([sys.executable, '-m', 'pytest', *pytest_args], cwd=ROOT, env=env)
    if result.returncode != 0:
        print('\nThe release check failed. Nothing was recorded.')
        return result.returncode

    _, commit, _ = updater._get_local_asset_state()
    record = {'source': source_fingerprint(), 'shoggoth': updater.get_current_version(), 'assets': commit}
    RECORD.write_text(json.dumps(record, indent=4) + '\n', encoding='utf-8')
    print(f'\nAll checks passed. Recorded in {RECORD.name} -- commit it with the release.')
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--verify', action='store_true', help='Only check that the record matches the code (what the build does).')
    args, pytest_args = parser.parse_known_args()
    sys.exit(verify() if args.verify else run(pytest_args))
