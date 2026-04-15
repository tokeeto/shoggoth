# -*- mode: python ; coding: utf-8 -*-
import os
import platform
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
    excludes=[],
    noarchive=False,
    optimize=0,
)

# Fix dylib conflict: Pillow bundles libharfbuzz without CoreText support,
# but pyvips (via libpangocairo) needs it. Replace Pillow's version with
# Homebrew's which has CoreText enabled. Must keep the same relative path
# so PyInstaller's symlinks resolve correctly.
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
else:
    # Windows/Linux: onefile standalone executable
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
