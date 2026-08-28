# -*- coding: utf-8 -*-
"""定时调度引擎：程序运行期间扫描触发点，串行执行采集+分析+导出。"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Callable

from scraper import has_login_state
from scheduler import store


class ScheduleEngine:
    """
    后台扫描线程。
    - 默认不补跑：仅当当前 HH:MM 恰好等于触发时刻时触发
    - 到点执行 cmd_run（采集 → 分析 → 导出），与手动「一条龙」相同
    - 与 TaskRunner 互斥：busy 时记 skipped
    """

    def __init__(
        self,
        *,
        is_busy: Callable[[], bool],
        start_job: Callable[[str, object, object], bool],
        log: Callable[[str], None],
        can_run: Callable[[], bool] | None = None,
        interval_sec: float = 15.0,
    ):
        self._is_busy = is_busy
        self._start_job = start_job
        self._log = log
        self._can_run = can_run or (lambda: True)
        self._interval = max(5.0, float(interval_sec))
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._active = False
        self._pending: tuple[int, str, str] | None = None  # id, date, time

    @property
    def running(self) -> bool:
        return self._active and self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        with self._lock:
            if self.running:
                return
            store.init_schedule_tables()
            self._stop.clear()
            self._active = True
            self._thread = threading.Thread(
                target=self._loop, name="ScheduleEngine", daemon=True
            )
            self._thread.start()
        self._log(
            "[定时] 调度已启动（需保持本程序运行；到点执行采集+分析+导出，不补跑已错过的时刻）"
        )

    def stop(self) -> None:
        with self._lock:
            self._active = False
            self._stop.set()
            t = self._thread
            self._thread = None
        if t and t.is_alive():
            t.join(timeout=2.0)
        self._log("[定时] 调度已停止")

    def on_job_finished(self, rc: int) -> None:
        """由 GUI 在 TaskRunner 完成回调中调用。"""
        pending = self._pending
        self._pending = None
        if not pending:
            return
        sid, run_date, trigger = pending
        status = "ok" if (rc or 0) == 0 else "fail"
        msg = None if status == "ok" else f"退出码 {rc}"
        try:
            store.finish_run(sid, trigger, status, message=msg, run_date=run_date)
        except Exception as e:
            self._log(f"[定时] 更新运行记录失败：{e}")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                self._log(f"[定时] 扫描异常：{e}")
            self._stop.wait(self._interval)

    def _tick(self) -> None:
        if not self._active:
            return
        if not self._can_run():
            return

        now = datetime.now()
        hhmm = now.strftime("%H:%M")
        today = now.date()
        weekday = today.weekday()
        run_date = today.isoformat()

        for sched in store.list_schedules():
            if not sched.enabled or sched.id is None:
                continue
            if weekday not in (sched.days_of_week or []):
                continue
            if hhmm not in (sched.times or []):
                continue
            if store.has_run_today(sched.id, hhmm, run_date=run_date):
                continue

            if self._is_busy() or self._pending is not None:
                if store.begin_run(sched.id, hhmm, run_date=run_date):
                    store.finish_run(
                        sched.id,
                        hhmm,
                        "skipped",
                        message="当时有其他任务在运行",
                        run_date=run_date,
                    )
                    self._log(f"[定时] 跳过「{sched.name}」{hhmm}：已有任务在运行")
                continue

            if not has_login_state():
                if store.begin_run(sched.id, hhmm, run_date=run_date):
                    store.finish_run(
                        sched.id,
                        hhmm,
                        "skipped",
                        message="网站未登录",
                        run_date=run_date,
                    )
                    self._log(f"[定时] 跳过「{sched.name}」{hhmm}：请先网站登录")
                continue

            try:
                args = store.schedule_to_collect_args(sched)
            except Exception as e:
                if store.begin_run(sched.id, hhmm, run_date=run_date):
                    store.finish_run(
                        sched.id, hhmm, "fail", message=str(e), run_date=run_date
                    )
                self._log(f"[定时] 「{sched.name}」参数错误：{e}")
                continue

            if not store.begin_run(sched.id, hhmm, run_date=run_date):
                continue

            label = f"定时·{sched.name}·{hhmm}"
            self._log(
                f"[定时] 触发「{sched.name}」{hhmm} | {sched.city} | "
                f"{len(sched.hotels)} 家 | {args.start}~{args.end} | 采集+分析+导出"
            )
            self._pending = (sched.id, run_date, hhmm)

            import main as app_main

            ok = self._start_job(label, app_main.cmd_run, args)
            if not ok:
                self._pending = None
                store.finish_run(
                    sched.id,
                    hhmm,
                    "skipped",
                    message="无法启动任务（可能正忙）",
                    run_date=run_date,
                )
                self._log(f"[定时] 未能启动「{sched.name}」{hhmm}")

    def next_hint(self) -> str:
        now = datetime.now()
        today = now.date()
        items: list[tuple[str, str]] = []
        for sched in store.list_schedules():
            if not sched.enabled:
                continue
            if today.weekday() not in (sched.days_of_week or []):
                continue
            for t in sched.times or []:
                if t > now.strftime("%H:%M"):
                    items.append((t, sched.name))
        if not items:
            return "今日已无后续触发点（或未启用任务）"
        items.sort()
        t, name = items[0]
        return f"下次约 {t} · {name}"
