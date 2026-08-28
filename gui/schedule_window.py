# -*- coding: utf-8 -*-
"""定时任务管理窗口。"""
from __future__ import annotations

from datetime import date, timedelta
from tkinter import messagebox

import customtkinter as ctk

import config
from gui.datepicker import DatePickerEntry
from scheduler import store
from scheduler.engine import ScheduleEngine

_WEEKDAYS = (("一", 0), ("二", 1), ("三", 2), ("四", 3), ("五", 4), ("六", 5), ("日", 6))


class ScheduleWindow(ctk.CTkToplevel):
    def __init__(self, master, *, engine: ScheduleEngine, log_fn, ensure_agreed):
        super().__init__(master)
        self.title("定时采集任务")
        self.geometry("960x640")
        self.minsize(880, 560)
        self.transient(master)

        self.engine = engine
        self._log = log_fn
        self._ensure_agreed = ensure_agreed
        self._selected_id: int | None = None
        self._times: list[str] = ["10:00", "14:00", "18:00"]

        store.init_schedule_tables()
        self._build()
        self._load_blank()
        self._refresh_list()
        self._refresh_engine_ui()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(150, self._focus)

    def _focus(self):
        try:
            self.lift()
            self.focus_force()
        except Exception:
            pass

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self)
        left.grid(row=0, column=0, sticky="nsw", padx=(12, 6), pady=12)
        left.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(left, text="任务列表", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 4)
        )
        self.list_frame = ctk.CTkScrollableFrame(left, width=260, height=420)
        self.list_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        ctk.CTkButton(left, text="新建任务", command=self._load_blank).grid(
            row=2, column=0, sticky="ew", padx=8, pady=(8, 4)
        )
        ctk.CTkButton(
            left,
            text="删除选中",
            fg_color="#a32d2d",
            hover_color="#7f1d1d",
            command=self._delete,
        ).grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 10))

        right = ctk.CTkFrame(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        right.grid_columnconfigure(1, weight=1)

        r = 0
        ctk.CTkLabel(right, text="任务名称").grid(row=r, column=0, sticky="w", padx=10, pady=6)
        self.name_var = ctk.StringVar()
        ctk.CTkEntry(right, textvariable=self.name_var).grid(
            row=r, column=1, sticky="ew", padx=10, pady=6
        )

        r += 1
        ctk.CTkLabel(right, text="城市").grid(row=r, column=0, sticky="w", padx=10, pady=6)
        self.city_var = ctk.StringVar(value=config.CITIES[0] if config.CITIES else "上海")
        ctk.CTkComboBox(right, values=list(config.CITIES), variable=self.city_var).grid(
            row=r, column=1, sticky="ew", padx=10, pady=6
        )

        r += 1
        ctk.CTkLabel(right, text="酒店\n(一行一个)").grid(
            row=r, column=0, sticky="nw", padx=10, pady=6
        )
        self.hotels_box = ctk.CTkTextbox(right, height=90)
        self.hotels_box.grid(row=r, column=1, sticky="ew", padx=10, pady=6)

        r += 1
        ctk.CTkLabel(right, text="日期模式").grid(row=r, column=0, sticky="w", padx=10, pady=6)
        mode_row = ctk.CTkFrame(right, fg_color="transparent")
        mode_row.grid(row=r, column=1, sticky="ew", padx=10, pady=6)
        self.date_mode = ctk.StringVar(value="rolling")
        ctk.CTkRadioButton(
            mode_row,
            text="滚动（今天起 N 天）",
            variable=self.date_mode,
            value="rolling",
            command=self._on_mode,
        ).pack(side="left", padx=(0, 12))
        ctk.CTkRadioButton(
            mode_row,
            text="固定区间",
            variable=self.date_mode,
            value="fixed",
            command=self._on_mode,
        ).pack(side="left")

        r += 1
        self.rolling_frame = ctk.CTkFrame(right, fg_color="transparent")
        self.rolling_frame.grid(row=r, column=0, columnspan=2, sticky="ew", padx=10, pady=2)
        ctk.CTkLabel(self.rolling_frame, text="滚动天数").pack(side="left", padx=(0, 8))
        self.rolling_var = ctk.StringVar(value="7")
        ctk.CTkEntry(self.rolling_frame, textvariable=self.rolling_var, width=80).pack(side="left")

        r += 1
        self.fixed_frame = ctk.CTkFrame(right, fg_color="transparent")
        self.fixed_frame.grid(row=r, column=0, columnspan=2, sticky="ew", padx=10, pady=2)
        ctk.CTkLabel(self.fixed_frame, text="开始").pack(side="left", padx=(0, 4))
        self.start_picker = DatePickerEntry(
            self.fixed_frame, initial=date.today(), mindate=date.today(), width=150
        )
        self.start_picker.pack(side="left", padx=4)
        ctk.CTkLabel(self.fixed_frame, text="结束").pack(side="left", padx=(12, 4))
        self.end_picker = DatePickerEntry(
            self.fixed_frame,
            initial=date.today() + timedelta(days=6),
            mindate=date.today(),
            width=150,
        )
        self.end_picker.pack(side="left", padx=4)

        r += 1
        ctk.CTkLabel(right, text="触发时刻").grid(row=r, column=0, sticky="nw", padx=10, pady=6)
        times_wrap = ctk.CTkFrame(right, fg_color="transparent")
        times_wrap.grid(row=r, column=1, sticky="ew", padx=10, pady=6)
        self.times_bar = ctk.CTkFrame(times_wrap, fg_color="transparent")
        self.times_bar.pack(anchor="w")
        add_row = ctk.CTkFrame(times_wrap, fg_color="transparent")
        add_row.pack(anchor="w", pady=(6, 0))
        self.time_input = ctk.CTkEntry(add_row, width=80, placeholder_text="10:00")
        self.time_input.pack(side="left")
        ctk.CTkButton(add_row, text="添加", width=60, command=self._add_time).pack(
            side="left", padx=6
        )
        ctk.CTkLabel(
            add_row, text="可多个，如 10:00 / 14:00 / 18:00", text_color="gray"
        ).pack(side="left")

        r += 1
        ctk.CTkLabel(right, text="星期").grid(row=r, column=0, sticky="w", padx=10, pady=6)
        week = ctk.CTkFrame(right, fg_color="transparent")
        week.grid(row=r, column=1, sticky="w", padx=10, pady=6)
        self.weekday_vars: dict[int, ctk.BooleanVar] = {}
        for label, idx in _WEEKDAYS:
            var = ctk.BooleanVar(value=True)
            self.weekday_vars[idx] = var
            ctk.CTkCheckBox(week, text=label, variable=var, width=42).pack(side="left", padx=2)

        r += 1
        opts = ctk.CTkFrame(right, fg_color="transparent")
        opts.grid(row=r, column=0, columnspan=2, sticky="w", padx=10, pady=6)
        self.enabled_var = ctk.BooleanVar(value=True)
        self.force_var = ctk.BooleanVar(value=False)
        self.headless_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(opts, text="启用该任务", variable=self.enabled_var).pack(
            side="left", padx=(0, 12)
        )
        ctk.CTkCheckBox(opts, text="强制重采", variable=self.force_var).pack(
            side="left", padx=(0, 12)
        )
        ctk.CTkCheckBox(
            opts, text="无头模式（定时建议勾选）", variable=self.headless_var
        ).pack(side="left")

        r += 1
        ctk.CTkButton(right, text="保存任务", width=120, command=self._save).grid(
            row=r, column=0, columnspan=2, sticky="w", padx=10, pady=12
        )

        bar = ctk.CTkFrame(self)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 12))
        self.engine_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(
            bar,
            text="启动调度（程序需保持运行）",
            variable=self.engine_var,
            command=self._toggle_engine,
        ).pack(side="left", padx=12, pady=10)
        self.hint_label = ctk.CTkLabel(bar, text="", text_color="gray")
        self.hint_label.pack(side="left", padx=8)
        ctk.CTkLabel(
            bar,
            text="不补跑已错过的时刻；休眠或退出程序时不会触发。",
            text_color="gray",
            font=ctk.CTkFont(size=11),
        ).pack(side="right", padx=12)

        self._on_mode()
        self._render_times()

    def _on_mode(self):
        if self.date_mode.get() == "rolling":
            self.rolling_frame.grid()
            self.fixed_frame.grid_remove()
        else:
            self.rolling_frame.grid_remove()
            self.fixed_frame.grid()

    def _render_times(self):
        for w in self.times_bar.winfo_children():
            w.destroy()
        for t in self._times:
            chip = ctk.CTkFrame(self.times_bar, fg_color=("gray85", "gray30"))
            chip.pack(side="left", padx=3, pady=2)
            ctk.CTkLabel(chip, text=t, width=48).pack(side="left", padx=(6, 0), pady=2)
            ctk.CTkButton(
                chip,
                text="×",
                width=24,
                height=24,
                fg_color="transparent",
                command=lambda x=t: self._remove_time(x),
            ).pack(side="left", padx=2)

    def _add_time(self):
        t = store.normalize_time(self.time_input.get())
        if not t:
            messagebox.showerror("时刻格式", "请输入 HH:MM，例如 10:00", parent=self)
            return
        self._times = store.parse_times_list(self._times + [t])
        self._render_times()
        self.time_input.delete(0, "end")

    def _remove_time(self, t: str):
        self._times = [x for x in self._times if x != t]
        self._render_times()

    def _refresh_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        for s in store.list_schedules():
            mark = "●" if s.enabled else "○"
            text = f"{mark} {s.name}\n  {s.city} · {', '.join(s.times)}"
            selected = s.id == self._selected_id
            ctk.CTkButton(
                self.list_frame,
                text=text,
                anchor="w",
                height=48,
                fg_color=("#1f6aa5", "#144870") if selected else ("gray80", "gray30"),
                command=lambda i=s.id: self._select(i),
            ).pack(fill="x", padx=4, pady=3)

    def _select(self, schedule_id: int):
        s = store.get_schedule(schedule_id)
        if not s:
            return
        self._selected_id = schedule_id
        self.name_var.set(s.name)
        self.city_var.set(s.city)
        self.hotels_box.delete("1.0", "end")
        self.hotels_box.insert("1.0", s.hotels_text())
        self.date_mode.set(s.date_mode)
        self.rolling_var.set(str(s.rolling_days))
        if s.start_date:
            try:
                self.start_picker.set_date(date.fromisoformat(s.start_date))
            except ValueError:
                pass
        if s.end_date:
            try:
                self.end_picker.set_date(date.fromisoformat(s.end_date))
            except ValueError:
                pass
        self._times = list(s.times)
        self._render_times()
        for i, var in self.weekday_vars.items():
            var.set(i in (s.days_of_week or []))
        self.enabled_var.set(s.enabled)
        self.force_var.set(s.force)
        self.headless_var.set(s.headless)
        self._on_mode()
        self._refresh_list()

    def _load_blank(self):
        self._selected_id = None
        self.name_var.set("")
        self.city_var.set(config.CITIES[0] if config.CITIES else "上海")
        self.hotels_box.delete("1.0", "end")
        self.date_mode.set("rolling")
        self.rolling_var.set("7")
        self.start_picker.set_date(date.today())
        self.end_picker.set_date(date.today() + timedelta(days=6))
        self._times = ["10:00", "14:00", "18:00"]
        self._render_times()
        for var in self.weekday_vars.values():
            var.set(True)
        self.enabled_var.set(True)
        self.force_var.set(False)
        self.headless_var.set(True)
        self._on_mode()
        self._refresh_list()

    def _form_schedule(self) -> store.Schedule:
        try:
            rolling_days = int(self.rolling_var.get().strip())
        except ValueError:
            rolling_days = 7
        start_d = self.start_picker.get_date()
        end_d = self.end_picker.get_date()
        return store.Schedule(
            id=self._selected_id,
            name=self.name_var.get().strip(),
            enabled=bool(self.enabled_var.get()),
            city=self.city_var.get().strip(),
            hotels=store.parse_hotels_text(self.hotels_box.get("1.0", "end")),
            date_mode=self.date_mode.get(),
            start_date=start_d.isoformat() if start_d else None,
            end_date=end_d.isoformat() if end_d else None,
            rolling_days=rolling_days,
            times=list(self._times),
            days_of_week=[i for i, v in self.weekday_vars.items() if v.get()],
            force=bool(self.force_var.get()),
            headless=bool(self.headless_var.get()),
        )

    def _save(self):
        if not self._ensure_agreed():
            return
        try:
            saved = store.save_schedule(self._form_schedule())
        except ValueError as e:
            messagebox.showerror("保存失败", str(e), parent=self)
            return
        self._selected_id = saved.id
        self._log(f"[定时] 已保存任务：{saved.name}")
        self._refresh_list()
        self._refresh_engine_ui()
        messagebox.showinfo("已保存", f"任务「{saved.name}」已保存。", parent=self)

    def _delete(self):
        if self._selected_id is None:
            messagebox.showwarning("未选择", "请先选择要删除的任务。", parent=self)
            return
        s = store.get_schedule(self._selected_id)
        name = s.name if s else str(self._selected_id)
        if not messagebox.askyesno("确认删除", f"确定删除任务「{name}」？", parent=self):
            return
        store.delete_schedule(self._selected_id)
        self._log(f"[定时] 已删除任务：{name}")
        self._load_blank()

    def _toggle_engine(self):
        if not self._ensure_agreed():
            self.engine_var.set(False)
            return
        if self.engine_var.get():
            if not store.list_schedules():
                messagebox.showwarning(
                    "无任务", "请先创建并保存至少一个定时任务。", parent=self
                )
                self.engine_var.set(False)
                return
            self.engine.start()
        else:
            self.engine.stop()
        self._refresh_engine_ui()

    def _refresh_engine_ui(self):
        self.engine_var.set(self.engine.running)
        try:
            hint = self.engine.next_hint()
        except Exception:
            hint = ""
        state = "调度中" if self.engine.running else "未启动"
        self.hint_label.configure(text=f"{state} · {hint}")
