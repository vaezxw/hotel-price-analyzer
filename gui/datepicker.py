# -*- coding: utf-8 -*-
"""CustomTkinter 日期选择组件：输入框 + 日历弹窗。"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Callable

import customtkinter as ctk


def _parse(s: str) -> date | None:
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


class DatePickerEntry(ctk.CTkFrame):
    """显示 YYYY-MM-DD，点击右侧按钮弹出月历选择。"""

    def __init__(
        self,
        master,
        *,
        initial: date | str | None = None,
        mindate: date | None = None,
        width: int = 140,
        command: Callable[[date], None] | None = None,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._mindate = mindate
        self._command = command
        self._popup: ctk.CTkToplevel | None = None
        self._view_year = date.today().year
        self._view_month = date.today().month

        if isinstance(initial, date):
            init_s = initial.isoformat()
        elif isinstance(initial, str) and initial:
            init_s = initial
        else:
            init_s = date.today().isoformat()

        d0 = _parse(init_s) or date.today()
        self._view_year, self._view_month = d0.year, d0.month

        self.grid_columnconfigure(0, weight=1)

        self._entry = ctk.CTkEntry(self, width=max(width - 36, 100), justify="center")
        self._entry.insert(0, init_s)
        self._entry.grid(row=0, column=0, sticky="ew")

        self._btn = ctk.CTkButton(
            self,
            text="▾",
            width=32,
            command=self._toggle_popup,
        )
        self._btn.grid(row=0, column=1, padx=(4, 0))

    # ---- public API (兼容 CTkEntry 用法) ----
    def get(self) -> str:
        return self._entry.get().strip()

    def get_date(self) -> date | None:
        return _parse(self.get())

    def set_date(self, d: date) -> None:
        self._entry.configure(state="normal")
        self._entry.delete(0, "end")
        self._entry.insert(0, d.isoformat())
        self._view_year, self._view_month = d.year, d.month
        if self._command:
            self._command(d)

    def set_mindate(self, d: date | None) -> None:
        self._mindate = d

    def configure(self, **kwargs):
        state = kwargs.pop("state", None)
        if state is not None:
            self._entry.configure(state=state)
            self._btn.configure(state=state)
        if kwargs:
            super().configure(**kwargs)

    def cget(self, key):
        if key == "state":
            return self._entry.cget("state")
        return super().cget(key)

    # ---- popup ----
    def _toggle_popup(self):
        if self._popup is not None and self._popup.winfo_exists():
            self._close_popup()
            return
        self._open_popup()

    def _close_popup(self):
        if self._popup is not None:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None

    def _open_popup(self):
        self._close_popup()
        cur = self.get_date() or date.today()
        self._view_year, self._view_month = cur.year, cur.month

        pop = ctk.CTkToplevel(self)
        pop.title("选择日期")
        pop.resizable(False, False)
        pop.transient(self.winfo_toplevel())
        pop.attributes("-topmost", True)
        self._popup = pop

        # 定位到输入框下方
        self.update_idletasks()
        x = self.winfo_rootx()
        y = self.winfo_rooty() + self.winfo_height() + 4
        pop.geometry(f"280x300+{x}+{y}")

        header = ctk.CTkFrame(pop, fg_color="transparent")
        header.pack(fill="x", padx=8, pady=(8, 4))

        ctk.CTkButton(header, text="‹", width=36, command=self._prev_month).pack(side="left")
        self._title_lbl = ctk.CTkLabel(header, text="", font=ctk.CTkFont(size=14, weight="bold"))
        self._title_lbl.pack(side="left", expand=True)
        ctk.CTkButton(header, text="›", width=36, command=self._next_month).pack(side="right")

        week = ctk.CTkFrame(pop, fg_color="transparent")
        week.pack(fill="x", padx=8)
        for i, name in enumerate(("一", "二", "三", "四", "五", "六", "日")):
            ctk.CTkLabel(week, text=name, width=34).grid(row=0, column=i, padx=1, pady=2)

        self._days = ctk.CTkFrame(pop, fg_color="transparent")
        self._days.pack(fill="both", expand=True, padx=8, pady=4)

        foot = ctk.CTkFrame(pop, fg_color="transparent")
        foot.pack(fill="x", padx=8, pady=(0, 8))
        ctk.CTkButton(foot, text="今天", width=70, command=self._pick_today).pack(side="left")
        ctk.CTkButton(foot, text="关闭", width=70, command=self._close_popup).pack(side="right")

        pop.bind("<Escape>", lambda _e: self._close_popup())
        pop.protocol("WM_DELETE_WINDOW", self._close_popup)
        # 失去焦点时关闭（略延迟，避免按钮点击被吞）
        pop.bind("<FocusOut>", self._on_focus_out)

        self._render_days()
        pop.focus_force()

    def _on_focus_out(self, _event=None):
        pop = self._popup
        if pop is None or not pop.winfo_exists():
            return
        try:
            focused = pop.focus_get()
        except Exception:
            focused = None
        if focused is None:
            # 稍后再查，给日历按钮一点时间抢焦点
            pop.after(150, self._maybe_close_if_unfocused)

    def _maybe_close_if_unfocused(self):
        pop = self._popup
        if pop is None or not pop.winfo_exists():
            return
        try:
            focused = pop.focus_get()
        except Exception:
            focused = None
        if focused is None:
            self._close_popup()

    def _prev_month(self):
        if self._view_month == 1:
            self._view_year -= 1
            self._view_month = 12
        else:
            self._view_month -= 1
        self._render_days()

    def _next_month(self):
        if self._view_month == 12:
            self._view_year += 1
            self._view_month = 1
        else:
            self._view_month += 1
        self._render_days()

    def _pick_today(self):
        self._select(date.today())

    def _select(self, d: date):
        if self._mindate and d < self._mindate:
            return
        self.set_date(d)
        self._close_popup()

    def _render_days(self):
        for w in self._days.winfo_children():
            w.destroy()

        self._title_lbl.configure(text=f"{self._view_year} 年 {self._view_month} 月")
        selected = self.get_date()
        today = date.today()
        cal = calendar.Calendar(firstweekday=0)  # Monday
        weeks = cal.monthdayscalendar(self._view_year, self._view_month)

        for r, week in enumerate(weeks):
            for c, day in enumerate(week):
                if day == 0:
                    ctk.CTkLabel(self._days, text="", width=34).grid(row=r, column=c, padx=1, pady=1)
                    continue
                d = date(self._view_year, self._view_month, day)
                disabled = bool(self._mindate and d < self._mindate)
                is_sel = selected == d
                is_today = d == today

                fg = None
                text_color = None
                if disabled:
                    text_color = "gray50"
                elif is_sel:
                    fg = ("#3B8ED0", "#1F6AA5")
                elif is_today:
                    fg = ("#DCE4EE", "#2B2B2B")

                btn = ctk.CTkButton(
                    self._days,
                    text=str(day),
                    width=34,
                    height=28,
                    fg_color=fg or "transparent",
                    text_color=text_color,
                    hover=not disabled,
                    state="disabled" if disabled else "normal",
                    command=(lambda dd=d: self._select(dd)),
                )
                btn.grid(row=r, column=c, padx=1, pady=1)
