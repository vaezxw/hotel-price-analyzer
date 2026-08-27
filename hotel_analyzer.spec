# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：携程酒店房价工具 → Windows onedir 目录。"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

pw_datas, pw_binaries, pw_hidden = collect_all("playwright")

hidden = list(pw_hidden) + collect_submodules("playwright") + [
    "greenlet",
    "pyee",
    "openpyxl",
    "openpyxl.cell._writer",
    "matplotlib.backends.backend_agg",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=pw_binaries,
    datas=pw_datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="hotel-analyzer",
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="hotel-analyzer",
)
