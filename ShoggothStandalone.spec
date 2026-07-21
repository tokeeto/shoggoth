# -*- mode: python ; coding: utf-8 -*-
import os
import platform
import re
import shutil
import tomllib

# Files to include
datas = [('shoggoth/translations/*', 'shoggoth/translations/')]

# Read version from pyproject.toml
with open('pyproject.toml', 'rb') as f:
    version = tomllib.load(f)['project']['version']

# Code signing configuration (set via environment variable in CI)
codesign_id = os.environ.get('APPLE_SIGNING_IDENTITY', None) or None
entitlements = 'entitlements.plist' if codesign_id else None

# windows needs to manually download a version of sdl2
# if platform.system() == 'Windows':
#     os.environ['KIVY_SDL2_PATH'] = "C:\\SDL2-2.26.0\\lib\\x64\\"
#     datas.append(("C:\\SDL2-2.26.0\\lib\\x64\\SDL2.dll", '.'))
# Kivy tries to open up a window during compilation.
# Setting this makes it "fail" succesfully.

a = Analysis(
    ['shoggoth/tool.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy',              # only reachable via optional PIL/pyvips array APIs we don't call
        'PySide6.QtNetwork',  # networking goes through requests/sockets, not Qt
    ],
    noarchive=False,
    optimize=0,
)

# ---- size trimming ----
# The app imports only QtCore/QtGui/QtWidgets. QtQml/QtQuick/QtPdf and friends
# are dragged in as binary deps of optional plugins (virtualkeyboard -> Quick/Qml,
# imageformats qpdf -> QtPdf, platformthemes qgtk3 -> the whole GTK stack
# including a second 32MB copy of ICU data). Names differ per platform
# (libQt6Qml.so / Qt6Qml.dll / QtQml.framework), hence the regex.
_drop_binary = re.compile(
    r'Qt6?(Qml|Quick|VirtualKeyboard|Pdf)'
    r'|qtvirtualkeyboardplugin'
    r'|imageformats[/\\](lib)?qpdf'
    r'|platformthemes[/\\](lib)?qgtk3'
)
dropped = [b for b in a.binaries if _drop_binary.search(b[0])]
a.binaries = [b for b in a.binaries if b not in dropped]

# On Linux, PyInstaller bundled system libs that only the dropped plugins
# needed (libgtk-3 -> libglycin -> libxml2 -> libicudata.so.78, ...). Remove
# every root-level lib that is in the dropped plugins' dependency closure but
# not in any kept binary's closure.
if platform.system() == 'Linux' and dropped:
    import subprocess

    def _needed(path):
        try:
            out = subprocess.check_output(['objdump', '-p', path], text=True,
                                          stderr=subprocess.DEVNULL)
        except (OSError, subprocess.CalledProcessError):
            return set()
        return {line.split()[1] for line in out.splitlines()
                if line.strip().startswith('NEEDED')}

    _root_libs = {os.path.basename(b[0]): b for b in a.binaries if '/' not in b[0]}

    def _dep_closure(seed_paths):
        result, frontier = set(), list(seed_paths)
        while frontier:
            for name in _needed(frontier.pop()):
                if name in _root_libs and name not in result:
                    result.add(name)
                    frontier.append(_root_libs[name][1])
        return result

    _used = _dep_closure([b[1] for b in a.binaries if '/' in b[0]])
    _unused = _dep_closure([b[1] for b in dropped]) - _used
    a.binaries = [b for b in a.binaries
                  if '/' in b[0] or os.path.basename(b[0]) not in _unused]

# Qt translations: keep only the languages the app itself ships.
_keep_langs = ('en', 'de', 'es', 'fr', 'zh')

def _keep_translation(dest):
    dest = dest.replace('\\', '/')
    if '/translations/' not in dest or not dest.startswith('PySide6'):
        return True
    stem = os.path.basename(dest).rsplit('.', 1)[0]
    if stem.startswith('qt_help_'):
        return False
    lang = stem.split('_', 1)[1] if '_' in stem else ''
    return any(lang == k or lang.startswith(k + '_') for k in _keep_langs)

a.datas = [d for d in a.datas if _keep_translation(d[0])]

# Fix dylib conflict: Pillow bundles libharfbuzz without CoreText support,
# but pyvips (via libpangocairo) needs _hb_coretext_font_create.
# Replace Pillow's version with Homebrew's which has CoreText enabled,
# and bundle its transitive dependencies.
# This runs per-platform in CI, so Homebrew paths are always arch-correct.
if platform.system() == 'Darwin':
    import subprocess
    try:
        homebrew_prefix = subprocess.check_output(['brew', '--prefix'], text=True).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        homebrew_prefix = '/opt/homebrew'

    homebrew_harfbuzz = f'{homebrew_prefix}/opt/harfbuzz/lib/libharfbuzz.0.dylib'
    if os.path.exists(homebrew_harfbuzz):
        a.binaries = [b for b in a.binaries if 'libharfbuzz' not in b[0]]
        a.binaries.append(('PIL/.dylibs/libharfbuzz.0.dylib', homebrew_harfbuzz, 'BINARY'))

        # Bundle all transitive Homebrew deps (recursive).
        # Walk the dependency tree via otool so we catch indirect deps
        # (e.g. harfbuzz -> glib -> pcre2).
        bundled_names = {b[0] for b in a.binaries}
        to_scan = [homebrew_harfbuzz]
        seen = set()
        while to_scan:
            dylib = to_scan.pop()
            if dylib in seen:
                continue
            seen.add(dylib)
            try:
                needed = subprocess.check_output(
                    ['otool', '-L', dylib], text=True
                )
            except (FileNotFoundError, subprocess.CalledProcessError):
                continue
            for line in needed.splitlines():
                line = line.strip()
                if not line.startswith(homebrew_prefix):
                    continue
                dep_path = line.split(' (')[0].strip()
                dep_name = os.path.basename(dep_path)
                if dep_name in bundled_names or not os.path.exists(dep_path):
                    continue
                a.binaries.append((dep_name, dep_path, 'BINARY'))
                bundled_names.add(dep_name)
                to_scan.append(dep_path)

pyz = PYZ(a.pure)

if platform.system() == 'Darwin':
    # macOS: onedir mode required for .app bundle (onefile is deprecated with BUNDLE)
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='Shoggoth',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=codesign_id,
        entitlements_file=entitlements,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='Shoggoth',
    )
    app = BUNDLE(
        coll,
        name='Shoggoth.app',
        icon='Shoggoth.icns',
        bundle_identifier='com.tokeeto.shoggoth',
        info_plist={
            'CFBundleName': 'Shoggoth',
            'CFBundleDisplayName': 'Shoggoth',
            'CFBundleVersion': version,
            'CFBundleShortVersionString': version,
            'NSHighResolutionCapable': True,
        },
        codesign_identity=codesign_id,
        entitlements_file=entitlements,
    )
elif platform.system() == 'Windows':
    # Windows: onedir build, not onefile. Onefile self-extracts the whole
    # payload to %TEMP% on every launch, which is both slow and exactly the
    # pattern AV/SmartScreen heuristics flag as dropper-like. onedir also
    # lets the self-update launcher (below) swap the install folder in place
    # without ever needing to touch a locked, currently-running exe.
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='Shoggoth',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='Shoggoth',
    )

    # Self-update launcher: a tiny, dependency-free companion exe that ships
    # inside the same onedir folder as Shoggoth.exe. The main app spawns it
    # (and only it, never the other way around) when an update has been
    # staged, then exits; the launcher performs the actual file swap once
    # Shoggoth.exe has released its file lock. See shoggoth/launcher.py for
    # the handoff contract (root_dir/pending_update.json).
    launcher_a = Analysis(
        ['shoggoth/launcher.py'],
        pathex=[],
        binaries=[],
        datas=[],
        hiddenimports=['tkinter', 'tkinter.messagebox'],
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        excludes=['numpy', 'PySide6', 'pyvips', 'PIL'],
        noarchive=False,
        optimize=0,
    )
    launcher_pyz = PYZ(launcher_a.pure)
    launcher_exe = EXE(
        launcher_pyz,
        launcher_a.scripts,
        launcher_a.binaries,
        launcher_a.datas,
        [],
        name='ShoggothLauncher',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    # EXE() writes its output synchronously (same reason BUNDLE() above can
    # read COLLECT()'s finished output), so by this point both
    # dist/Shoggoth/ and dist/ShoggothLauncher.exe already exist on disk.
    # Move (not copy) the launcher into the main app's onedir folder so every
    # install ships the executable it needs for its *next* self-update, and
    # the loose top-level dist/ShoggothLauncher.exe doesn't also end up in
    # the release zip alongside it.
    _launcher_src = os.path.join('dist', 'ShoggothLauncher.exe')
    _launcher_dst = os.path.join('dist', 'Shoggoth', 'ShoggothLauncher.exe')
    if os.path.exists(_launcher_src):
        shutil.move(_launcher_src, _launcher_dst)
else:
    # Linux: onefile standalone executable
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name='Shoggoth',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
