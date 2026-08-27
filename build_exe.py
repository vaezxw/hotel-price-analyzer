# -*- coding: utf-8 -*-
"""
PyInstaller 打包脚本（方案 2：打成 exe 目录分发）

前置（本机只需做一次）：
  pip install -r requirements.txt
  pip install pyinstaller
  playwright install chromium

打包：
  python build_exe.py

产出：
  dist/hotel-analyzer/          可整个文件夹 zip 发给朋友
    hotel-analyzer.exe
    _internal/                  依赖（勿删）
    browsers/                   Chromium（约 150MB）
    data/  输出/
    start.bat  说明.txt
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST_APP = ROOT / "dist" / "hotel-analyzer"
SPEC = ROOT / "hotel_analyzer.spec"


def _run(cmd: list[str], **kwargs) -> None:
    print(f"\n>>> {' '.join(cmd)}\n")
    subprocess.run(cmd, check=True, cwd=ROOT, **kwargs)


def _playwright_browsers_root() -> Path:
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env:
        return Path(env)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        p = Path(local) / "ms-playwright"
        if p.is_dir():
            return p
    return Path.home() / "AppData" / "Local" / "ms-playwright"


def _ensure_chromium_cached() -> Path:
    root = _playwright_browsers_root()
    chromium_dirs = sorted(root.glob("chromium-*"))
    if chromium_dirs:
        return root
    print("未检测到 Chromium 缓存，正在执行 playwright install chromium …")
    _run([sys.executable, "-m", "playwright", "install", "chromium"])
    chromium_dirs = sorted(root.glob("chromium-*"))
    if not chromium_dirs:
        raise SystemExit(
            f"Chromium 仍未找到，请手动运行：{sys.executable} -m playwright install chromium"
        )
    return root


def _copy_browsers(src_root: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    copied = 0
    for pattern in ("chromium-*", "ffmpeg-*", "winldd-*"):
        for item in src_root.glob(pattern):
            if item.is_dir():
                shutil.copytree(item, dest / item.name)
                print(f"  + browsers/{item.name}")
                copied += 1
    if copied == 0:
        raise SystemExit(f"未在 {src_root} 找到 chromium-* 目录")


def _write_start_bat() -> None:
    (DIST_APP / "start.bat").write_text(
        """@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0browsers"
hotel-analyzer.exe %*
if errorlevel 1 echo.
if errorlevel 1 echo [ERROR] Program exited with error.
echo.
echo Press any key to close...
pause >nul
endlocal
""",
        encoding="ascii",
    )


def _prepare_data_dirs() -> None:
    (DIST_APP / "data").mkdir(exist_ok=True)
    (DIST_APP / "输出").mkdir(exist_ok=True)
    keep = DIST_APP / "data" / ".gitkeep"
    if not keep.exists():
        keep.write_text("", encoding="utf-8")


def _copy_readme() -> None:
    src = ROOT / "说明.txt"
    if src.exists():
        shutil.copy2(src, DIST_APP / "说明.txt")


def main() -> int:
    print("=" * 50)
    print("  PyInstaller 打包：hotel-analyzer")
    print("=" * 50)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("安装 PyInstaller …")
        _run([sys.executable, "-m", "pip", "install", "pyinstaller"])

    browser_root = _ensure_chromium_cached()

    if DIST_APP.exists():
        print(f"清理旧目录: {DIST_APP}")
        shutil.rmtree(DIST_APP)

    _run([sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm", "--clean"])

    if not (DIST_APP / "hotel-analyzer.exe").exists():
        raise SystemExit(f"未找到 {DIST_APP / 'hotel-analyzer.exe'}")

    print("\n复制 Chromium 到 browsers/ …")
    _copy_browsers(browser_root, DIST_APP / "browsers")

    _prepare_data_dirs()
    _write_start_bat()
    _copy_readme()

    size_mb = sum(f.stat().st_size for f in DIST_APP.rglob("*") if f.is_file()) / (1024 * 1024)

    print()
    print("=" * 50)
    print(f"打包完成：{DIST_APP}")
    print(f"总体积约 {size_mb:.0f} MB（含 Chromium）")
    print("=" * 50)
    print()
    print("发给朋友：")
    print("  1. 将整个 dist/hotel-analyzer 文件夹打成 zip")
    print("  2. 解压后双击 start.bat（或 hotel-analyzer.exe）")
    print("  3. 首次使用选「登录」扫码保存登录态")
    print("  4. 无需安装 Python")
    print()

    try:
        os.startfile(str(DIST_APP))
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        print(f"\n命令失败，退出码 {e.returncode}")
        raise SystemExit(e.returncode)
    except Exception as e:
        print(f"\n打包失败：{e}")
        raise SystemExit(1)
