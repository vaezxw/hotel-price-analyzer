# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec：桌面 GUI 版 → Windows onedir 目录。"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None
ROOT = Path(SPECPATH)

pw_datas, pw_binaries, pw_hidden = collect_all("playwright")
ctk_datas, ctk_binaries, ctk_hidden = collect_all("customtkinter")

icon_ico = ROOT / "assets" / "app_icon.ico"
icon_png = ROOT / "assets" / "app_icon.png"
asset_datas = []
if icon_ico.is_file():
    asset_datas.append((str(icon_ico), "assets"))
if icon_png.is_file():
    asset_datas.append((str(icon_png), "assets"))

hidden = (
    list(pw_hidden)
    + list(ctk_hidden)
    + collect_submodules("playwright")
    + [
        "greenlet",
        "pyee",
        "openpyxl",
        "openpyxl.cell._writer",
        "business_report",
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
    datas=pw_datas + ctk_datas + asset_datas,
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
    icon=str(icon_ico) if icon_ico.is_file() else None,
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
