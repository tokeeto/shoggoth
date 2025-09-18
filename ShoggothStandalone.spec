# -*- mode: python ; coding: utf-8 -*-
import importlib.util;
import os
from pathlib import Path

# not automatically included
cm_path = Path(importlib.util.find_spec('kivy_garden.contextmenu').origin)

import os
import platform

# Files to include
datas = [('shoggoth/viewer.kv', 'shoggoth/'), ('shoggoth/shoggoth.kv', 'shoggoth/'), (cm_path.parent / '*.kv', 'kivy_garden/contextmenu')]

# windows needs to manually download a version of sdl2
if platform.system() == 'Windows':
    os.environ['KIVY_SDL2_PATH'] = "C:\\SDL2-2.26.0\\lib\\x64\\"
    datas.append(("C:\\SDL2-2.26.0\\lib\\x64\\SDL2.dll", '.'))
# Kivy tries to open up a window during compilation.
# Setting this makes it "fail" succesfully.
os.environ['KIVY_WINDOW'] = "None"

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
pyz = PYZ(a.pure)

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
