# -*- coding: utf-8 -*-
"""
酒店房价工具 — 桌面 GUI（CustomTkinter）

双击 exe 或运行：python gui/app.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from tkinter import messagebox
from types import SimpleNamespace

# Windows：必须在 import GUI / 创建窗口之前设置，否则任务栏一直显示 pythonw 图标
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "HotelPriceAnalyzer.Desktop.1"
        )
    except Exception:
        pass

import customtkinter as ctk

# 项目根目录加入 path（开发模式 python gui/app.py）
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
import main as app_main
import storage
from gui.datepicker import DatePickerEntry
from gui.mail_window import MailWindow
from gui.schedule_window import ScheduleWindow
from gui.tasks import TaskRunner
from scraper import has_login_state
from scheduler.engine import ScheduleEngine
from scheduler import store as schedule_store

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")



def _today() -> str:
    return date.today().isoformat()


def _week_later() -> str:
    return (date.today() + timedelta(days=6)).isoformat()


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _icon_candidates() -> list[Path]:
    """开发态 / 打包态下可能的图标路径。"""
    names = ("app_icon.ico", "app_icon.png", "app_icon.ico", "app_icon.png")
    bases = [ROOT / "assets"]
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", ""))
        bases.extend([Path(sys.executable).resolve().parent / "assets", meipass / "assets", meipass])
    out: list[Path] = []
    seen: set[Path] = set()
    for base in bases:
        for name in names:
            p = base / name
            if p.is_file() and p not in seen:
                out.append(p)
                seen.add(p)
    return out


def _win_toplevel_hwnd(widget_hwnd: int) -> int:
    """Tk 的 winfo_id() 是子窗口；任务栏图标在顶层父窗口 HWND 上。"""
    import ctypes

    user32 = ctypes.windll.user32
    GA_ROOT = 2
    root = user32.GetAncestor(widget_hwnd, GA_ROOT)
    if root:
        return int(root)
    parent = user32.GetParent(widget_hwnd)
    return int(parent or widget_hwnd)


def _win_set_hwnd_icon(hwnd: int, ico_path: Path) -> tuple[int, int]:
    """通过 Win32 WM_SETICON 设置图标；返回需长期持有的句柄。"""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    IMAGE_ICON = 1
    LR_LOADFROMFILE = 0x0010
    WM_SETICON = 0x0080
    ICON_SMALL = 0
    ICON_BIG = 1

    user32.LoadImageW.argtypes = [
        wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
        ctypes.c_int, ctypes.c_int, wintypes.UINT,
    ]
    user32.LoadImageW.restype = wintypes.HANDLE
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = wintypes.LPARAM

    path = str(ico_path.resolve())
    h_default = user32.LoadImageW(None, path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE)
    h_big = user32.LoadImageW(None, path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE) or h_default
    h_small = user32.LoadImageW(None, path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE) or h_big
    if h_big:
        user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_big)
    if h_small:
        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_small)
    return int(h_big or 0), int(h_small or 0)


def _apply_window_icon(win: ctk.CTk) -> None:
    """设置窗口图标（只执行一次，避免 <Map>/after 反复加载导致卡死闪退）。"""
    if getattr(win, "_app_icon_done", False):
        return
    win._app_icon_done = True

    paths = _icon_candidates()
    if not paths:
        return
    ico = next((p for p in paths if p.suffix.lower() == ".ico"), None)

    # Windows：只用 .ico + WM_SETICON。不要用 PhotoImage 加载大 PNG（1024px 极易卡死/闪退）
    if sys.platform == "win32" and ico is not None:
        try:
            win.iconbitmap(default=str(ico))
            win.iconbitmap(str(ico))
        except Exception:
            pass
        try:
            top_hwnd = _win_toplevel_hwnd(int(win.winfo_id()))
            win._app_icon_handles = _win_set_hwnd_icon(top_hwnd, ico)
            win._app_icon_path = str(ico)
        except Exception:
            pass
        return

    if ico is not None:
        try:
            win.iconbitmap(str(ico))
        except Exception:
            pass


class HotelAnalyzerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("酒店房价采集与分析")
        self.geometry("920x680")
        self.minsize(820, 600)
        storage.init_db()
        schedule_store.init_schedule_tables()
        # 必须用 _log（after 回主线程），不能把 _append_log 直接给后台线程，否则易卡死/闪退
        self.runner = TaskRunner(self._log, on_done=self._on_task_done)
        self.schedule_engine = ScheduleEngine(
            is_busy=lambda: self.runner.running,
            start_job=self._start_scheduled_job,
            log=self._log,
            can_run=lambda: bool(self.agree_var.get()) if hasattr(self, "agree_var") else False,
        )
        self._schedule_win = None
        self._mail_win = None

        self._build_ui()
        self._refresh_status()
        self._log("就绪。请先勾选底部免责声明，再点击「登录」。")
        self._log("提示：可在「定时任务」中配置多时段自动采集+分析+导出（程序需保持运行）。")
        self._log("提示：可在「邮件设置」中配置导出后自动发到 QQ 邮箱。")
        # 窗口真正显示后再设图标一次（避免启动阶段阻塞）
        self.after_idle(lambda: _apply_window_icon(self))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="酒店房价工具",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=10)

        self.status_label = ctk.CTkLabel(header, text="", font=ctk.CTkFont(size=13))
        self.status_label.grid(row=0, column=1, sticky="e", padx=12, pady=10)

        self.login_btn = ctk.CTkButton(
            header, text="登录", width=100, command=self._on_login
        )
        self.login_btn.grid(row=0, column=2, padx=(0, 12), pady=10)

        form = ctk.CTkFrame(self)
        form.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        for c in range(6):
            form.grid_columnconfigure(c, weight=1 if c in (1, 3, 5) else 0)

        ctk.CTkLabel(form, text="城市").grid(row=0, column=0, padx=(12, 4), pady=8, sticky="w")
        self.city_var = ctk.StringVar(value=config.CITIES[0] if config.CITIES else "上海")
        self.city_menu = ctk.CTkComboBox(
            form, values=list(config.CITIES), variable=self.city_var, width=140
        )
        self.city_menu.grid(row=0, column=1, padx=4, pady=8, sticky="ew")

        ctk.CTkLabel(
            form,
            text="指定酒店\n(一行一个)",
        ).grid(row=1, column=0, padx=(12, 4), pady=8, sticky="nw")
        self.hotels_box = ctk.CTkTextbox(form, height=68)
        self.hotels_box.grid(row=1, column=1, columnspan=5, padx=(4, 12), pady=8, sticky="ew")

        ctk.CTkLabel(form, text="入住开始").grid(row=2, column=0, padx=(12, 4), pady=8, sticky="w")
        self.start_entry = DatePickerEntry(
            form,
            initial=date.today(),
            mindate=date.today(),
            width=160,
            command=self._on_start_date_changed,
        )
        self.start_entry.grid(row=2, column=1, padx=4, pady=8, sticky="ew")

        ctk.CTkLabel(form, text="入住结束").grid(row=2, column=2, padx=(12, 4), pady=8, sticky="w")
        self.end_entry = DatePickerEntry(
            form,
            initial=date.today() + timedelta(days=6),
            mindate=date.today(),
            width=160,
        )
        self.end_entry.grid(row=2, column=3, padx=4, pady=8, sticky="ew")

        opts = ctk.CTkFrame(form, fg_color="transparent")
        opts.grid(row=3, column=0, columnspan=6, sticky="ew", padx=8, pady=(0, 8))
        self.debug_var = ctk.BooleanVar(value=False)
        self.force_var = ctk.BooleanVar(value=False)
        self.list_only_var = ctk.BooleanVar(value=False)
        self.all_cities_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(opts, text="有头模式（调试/过验证码）", variable=self.debug_var).pack(
            side="left", padx=8
        )
        ctk.CTkCheckBox(opts, text="强制重采", variable=self.force_var).pack(side="left", padx=8)
        ctk.CTkCheckBox(opts, text="仅列表页首推房型", variable=self.list_only_var).pack(
            side="left", padx=8
        )
        ctk.CTkCheckBox(
            opts,
            text="批量：全部配置城市",
            variable=self.all_cities_var,
            state="disabled",
        ).pack(side="left", padx=8)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=2, column=0, sticky="ew", padx=16, pady=8)

        self._action_btns: list[ctk.CTkButton] = []
        self._always_disabled: set[ctk.CTkButton] = set()
        buttons = [
            ("一条龙", self._on_run, {"fg_color": "#1a7f37", "hover_color": "#146c2e"}, False),
            ("采集", self._on_collect, {}, False),
            ("批量采集", self._on_collect_all, {}, True),
            ("分析", self._on_analyze, {}, False),
            ("导出 Excel", self._on_export, {}, False),
            ("定时任务", self._on_schedule, {"fg_color": "#0e639c", "hover_color": "#0b507c"}, False),
            ("邮件设置", self._on_mail, {"fg_color": "#6b4f9c", "hover_color": "#5a4183"}, False),
            ("打开导出目录", self._on_open_export, {"fg_color": "gray40", "hover_color": "gray30"}, False),
        ]
        for i, (text, cmd, kw, always_off) in enumerate(buttons):
            btn = ctk.CTkButton(btn_row, text=text, width=100, command=cmd, **kw)
            btn.grid(row=0, column=i, padx=4, pady=4)
            self._action_btns.append(btn)
            if always_off:
                self._always_disabled.add(btn)

        log_frame = ctk.CTkFrame(self)
        log_frame.grid(row=3, column=0, sticky="nsew", padx=16, pady=(8, 8))
        log_frame.grid_columnconfigure(0, weight=1)
        log_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(log_frame, text="运行日志", anchor="w").grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 4)
        )
        self.log_box = ctk.CTkTextbox(log_frame, font=ctk.CTkFont(family="Consolas", size=12))
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.log_box.configure(state="disabled")

        notice = ctk.CTkFrame(self, fg_color=("gray92", "gray20"))
        notice.grid(row=4, column=0, sticky="ew", padx=16, pady=(0, 6))
        ctk.CTkLabel(
            notice,
            text=(
                "免责声明：本工具仅供个人学习与数据分析使用，请勿将采集数据用于任何商业用途；"
                "未经作者书面授权，禁止复制、传播、二次分发本工具或相关数据。"
            ),
            font=ctk.CTkFont(size=11),
            text_color=("#8a4b08", "#e6b35a"),
            wraplength=860,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=12, pady=(8, 2))
        self.agree_var = ctk.BooleanVar(value=False)
        self.agree_chk = ctk.CTkCheckBox(
            notice,
            text="我已阅读并同意上述免责声明（勾选后才可使用本工具）",
            variable=self.agree_var,
            command=self._on_agree_changed,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.agree_chk.pack(anchor="w", padx=12, pady=(2, 10))

        footer = ctk.CTkLabel(
            self,
            text=f"数据：{config.DB_PATH.name}  |  导出：{config.OUTPUT_EXCEL_DIR}",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        footer.grid(row=5, column=0, sticky="w", padx=20, pady=(0, 10))

        self._busy = False
        self._apply_agree_state()


    def _on_agree_changed(self):
        self._apply_agree_state()
        if self.agree_var.get():
            self._log("已同意免责声明，可以使用本工具。")
        else:
            self._log("未勾选免责声明，功能已锁定。")

    def _apply_agree_state(self):
        """未勾选免责声明时锁定全部操作；勾选后恢复（批量功能仍禁用）。"""
        agreed = bool(self.agree_var.get())
        if self._busy:
            return
        state = "normal" if agreed else "disabled"
        self.login_btn.configure(state=state)
        self.city_menu.configure(state=state)
        self.hotels_box.configure(state=state)
        self.start_entry.configure(state=state)
        self.end_entry.configure(state=state)
        for btn in self._action_btns:
            if btn in self._always_disabled:
                btn.configure(state="disabled")
            else:
                btn.configure(state=state)

    def _ensure_agreed(self) -> bool:
        if self.agree_var.get():
            return True
        messagebox.showwarning(
            "请先同意免责声明",
            "请先勾选底部「我已阅读并同意上述免责声明」后，再使用本工具。",
        )
        return False

    def _on_start_date_changed(self, d: date):
        """开始日期变更时，若结束日期更早则自动对齐。"""
        end = self.end_entry.get_date()
        if end is None or end < d:
            self.end_entry.set_date(d)
        self.end_entry.set_mindate(d)

    def _get_hotel_input(self) -> str | None:
        raw = self.hotels_box.get("1.0", "end")
        parts = []
        for line in raw.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                parts.append(line)
        if not parts:
            return None
        return "\n".join(parts)

    def _set_busy(self, busy: bool):
        self._busy = busy
        if busy:
            state = "disabled"
            self.login_btn.configure(state=state)
            self.city_menu.configure(state=state)
            self.hotels_box.configure(state=state)
            self.start_entry.configure(state=state)
            self.end_entry.configure(state=state)
            for btn in self._action_btns:
                btn.configure(state=state)
            self.agree_chk.configure(state=state)
        else:
            self.agree_chk.configure(state="normal")
            self._apply_agree_state()

    def _refresh_status(self):
        n = storage.count_records()
        if has_login_state():
            login = "已登录"
            color = "#1a7f37"
        else:
            login = "未登录"
            color = "#c0392b"
        self.status_label.configure(
            text=f"登录：{login}  |  库内 {n} 条  |  最早可采 {date.today()}",
            text_color=color,
        )

    def _log(self, msg: str):
        # m=msg 避免闭包延迟取值；必须回主线程再改控件
        self.after(0, lambda m=msg: self._append_log(m))

    def _append_log(self, msg: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _on_task_done(self, rc: int):
        def finish():
            try:
                self.schedule_engine.on_job_finished(rc)
            except Exception:
                pass
            self._set_busy(False)
            self._refresh_status()

        self.after(0, finish)

    def _start_scheduled_job(self, label: str, fn, args) -> bool:
        """供调度引擎调用：与手动任务共用 TaskRunner（全局互斥）。
        注意：可能在后台线程调用，禁止弹 messagebox。
        """
        if not getattr(self, "agree_var", None) or not self.agree_var.get():
            return False
        ok = self.runner.run(label, fn, args)
        if ok:
            self.after(0, lambda: self._set_busy(True))
        return ok

    def _on_schedule(self):
        if not self._ensure_agreed():
            return
        if self._schedule_win is not None and self._schedule_win.winfo_exists():
            self._schedule_win.lift()
            self._schedule_win.focus_force()
            return
        self._schedule_win = ScheduleWindow(
            self,
            engine=self.schedule_engine,
            log_fn=self._log,
            ensure_agreed=self._ensure_agreed,
        )

    def _on_mail(self):
        if not self._ensure_agreed():
            return
        if self._mail_win is not None and self._mail_win.winfo_exists():
            self._mail_win.lift()
            self._mail_win.focus_force()
            return
        self._mail_win = MailWindow(self, log_fn=self._log)

    def _on_close(self):
        try:
            if self.schedule_engine.running:
                self.schedule_engine.stop()
        except Exception:
            pass
        self.destroy()

    def _build_args(self, *, require_city: bool = True) -> SimpleNamespace | None:
        start = self.start_entry.get_date()
        end = self.end_entry.get_date()
        if not start or not end:
            messagebox.showerror("日期错误", "请填写 YYYY-MM-DD 格式的开始/结束日期。")
            return None
        if end < start:
            start, end = end, start
        if end < date.today():
            messagebox.showerror("日期错误", f"不能采集过去日期，最早可选 {date.today()}。")
            return None

        city = self.city_var.get().strip()
        if require_city and not self.all_cities_var.get() and not city:
            messagebox.showerror("参数错误", "请选择城市。")
            return None

        keyword = self._get_hotel_input()
        return SimpleNamespace(
            city=city if not self.all_cities_var.get() else None,
            keyword=keyword,
            date=None,
            start=start.isoformat(),
            end=end.isoformat(),
            debug=self.debug_var.get(),
            force=self.force_var.get(),
            list_only=self.list_only_var.get(),
            output=None,
        )

    def _start_task(self, label: str, fn, args: SimpleNamespace | None):
        if args is None:
            return
        if not self._ensure_agreed():
            return
        if not self.runner.run(label, fn, args):
            return
        self._set_busy(True)

    def _on_login(self):
        if not self._ensure_agreed():
            return
        if self.runner.running:
            return
        if not messagebox.askokcancel(
            "登录",
            "将弹出浏览器窗口，请用你自己的账号扫码或验证码登录。\n\n继续？",
        ):
            return
        self._start_task("登录", app_main.cmd_login, SimpleNamespace())

    def _on_collect(self):
        args = self._build_args(require_city=True)
        if args:
            self.all_cities_var.set(False)
            args.city = self.city_var.get().strip()
        self._start_task("采集", app_main.cmd_collect, args)

    def _on_collect_all(self):
        args = self._build_args(require_city=not self.all_cities_var.get())
        if args and not self.all_cities_var.get():
            args.city = self.city_var.get().strip() or None
        self._start_task("批量采集", app_main.cmd_collect_all, args)

    def _on_analyze(self):
        args = SimpleNamespace(
            city=None,
            keyword=None,
            date=None,
            start=None,
            end=None,
            debug=False,
            force=False,
            list_only=False,
            output=None,
        )
        self._start_task("统计分析", app_main.cmd_analyze, args)

    def _on_export(self):
        args = SimpleNamespace(
            city=None,
            keyword=None,
            date=None,
            start=None,
            end=None,
            debug=False,
            force=False,
            list_only=False,
            output=None,
        )
        self._start_task("导出 Excel", app_main.cmd_export, args)

    def _on_run(self):
        if not has_login_state():
            if not messagebox.askyesno("未登录", "尚未登录，是否继续？（采集可能失败）"):
                return
        args = self._build_args(require_city=True)
        if args:
            args.city = self.city_var.get().strip()
        self._start_task("一条龙", app_main.cmd_run, args)

    def _on_open_export(self):
        if not self._ensure_agreed():
            return
        today_dir = config.OUTPUT_EXCEL_DIR / date.today().isoformat()
        today_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(today_dir))
        except Exception:
            subprocess.Popen(["explorer", str(today_dir)])


def main():
    # pythonw 无控制台，崩溃时写日志便于排查
    log_path = ROOT / "data" / "gui_crash.log"

    def _excepthook(exc_type, exc, tb):
        import traceback
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "".join(traceback.format_exception(exc_type, exc, tb)),
                encoding="utf-8",
            )
        except Exception:
            pass
        try:
            messagebox.showerror("程序异常", f"{exc_type.__name__}: {exc}\n\n详情见:\n{log_path}")
        except Exception:
            pass

    sys.excepthook = _excepthook
    try:
        app = HotelAnalyzerApp()
        app.mainloop()
    except Exception as e:
        _excepthook(type(e), e, e.__traceback__)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
