# -*- mode: python ; coding: utf-8 -*-
import importlib.util;
from pathlib import Path
cm_path = Path(importlib.util.find_spec('kivy_garden.contextmenu').origin)


a = Analysis(
    ['shoggoth/tool.py'],
    pathex=[],
    binaries=[],
    datas=[('shoggoth/viewer.kv', 'shoggoth/'), ('shoggoth/shoggoth.kv', 'shoggoth/'), (cm_path.parent / '*.kv', 'kivy_garden/contextmenu')],
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
    [],
    exclude_binaries=True,
    name='Shoggoth',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
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
