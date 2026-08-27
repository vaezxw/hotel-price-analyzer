# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：桌面 GUI 版 → Windows onedir 目录。"""
from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

pw_datas, pw_binaries, pw_hidden = collect_all("playwright")
ctk_datas, ctk_binaries, ctk_hidden = collect_all("customtkinter")

hidden = (
    list(pw_hidden)
    + list(ctk_hidden)
    + collect_submodules("playwright")
    + [
        "greenlet",
        "pyee",
        "openpyxl",
        "openpyxl.cell._writer",
        "matplotlib.backends.backend_agg",
        "customtkinter",
        "tkinter",
        "tkinter.ttk",
    ]
)

a = Analysis(
    ["gui/app.py"],
    pathex=[],
    binaries=pw_binaries + ctk_binaries,
    datas=pw_datas + ctk_datas,
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
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="hotel-analyzer",
)
