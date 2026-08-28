# -*- coding: utf-8 -*-
"""生成可分享包：排除登录态、调试 HTML、数据库。"""
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT.parent / "hotel-price-analyzer-分享包"

COPY_FILES = [
    "main.py",
    "scraper.py",
    "config.py",
    "storage.py",
    "analyzer.py",
    "exporter.py",
    "business_report.py",
    "mailer.py",
    "requirements.txt",
    "README.md",
    "启动.bat",
    "启动GUI.bat",
    "一键安装.bat",
    "说明.txt",
    "打包.bat",
    "start.bat",
    "setup.bat",
    "pack_share.py",
    "build_exe.bat",
    "build_exe.py",
    "hotel_analyzer.spec",
]


def _copy_tree(name: str, src: Path, out: Path, missing: list):
    if not src.exists():
        missing.append(name)
        return
    if src.is_dir():
        shutil.copytree(src, out / name)
    else:
        shutil.copy2(src, out / name)
    print(f"  + {name}")


def main():
    print("=" * 46)
    print("  正在生成可分享文件夹（不含登录态）")
    print("=" * 46)
    print()

    if OUT.exists():
        print(f"清理旧目录: {OUT}")
        shutil.rmtree(OUT)

    OUT.mkdir(parents=True)
    (OUT / "data").mkdir()
    (OUT / "输出").mkdir()
    (OUT / "data" / ".gitkeep").write_text("", encoding="utf-8")

    missing = []
    for name in COPY_FILES:
        _copy_tree(name, ROOT / name, OUT, missing)
    _copy_tree("gui", ROOT / "gui", OUT, missing)
    _copy_tree("assets", ROOT / "assets", OUT, missing)
    _copy_tree("scheduler", ROOT / "scheduler", OUT, missing)

    if missing:
        print()
        print("警告：以下文件缺失，未复制：")
        for m in missing:
            print(f"  - {m}")

    print()
    print("=" * 46)
    print(f"已生成：{OUT}")
    print("=" * 46)
    print()
    print("请检查后再发给朋友：")
    print("  - 已排除：ctrip_state.json / browser_profile / debug HTML / 数据库")
    print("  - 把该文件夹打成 zip 发给她")
    print("  - 让她先读「说明.txt」，再双击「启动GUI.bat」（图形界面）")
    print()

    try:
        import os
        os.startfile(str(OUT))  # Windows: 打开资源管理器
    except Exception:
        pass

    return 0 if not missing else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"打包失败：{e}")
        raise SystemExit(1)
