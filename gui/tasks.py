# -*- coding: utf-8 -*-
"""后台任务：在独立线程中运行 CLI 逻辑，日志回传到 GUI。"""
from __future__ import annotations

import sys
import threading
from types import SimpleNamespace


class TaskRunner:
    def __init__(self, log_fn, on_done=None):
        self._log = log_fn
        self._on_done = on_done
        self._running = False
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def run(self, label: str, fn, args: SimpleNamespace) -> bool:
        with self._lock:
            if self._running:
                self._log("已有任务在运行，请等待完成后再操作。")
                return False
            self._running = True

        def worker():
            import main

            log_fn = self._log

            class _Writer:
                def write(self, s):
                    for line in s.splitlines():
                        if line.strip():
                            log_fn(line.rstrip())

                def flush(self):
                    pass

            self._log(f"--- 开始：{label} ---")
            main.set_log_callback(self._log)
            old_stdout = sys.stdout
            sys.stdout = _Writer()
            rc = 1
            try:
                rc = fn(args) or 0
                if rc == 0:
                    self._log(f"--- 完成：{label} ---")
                else:
                    self._log(f"--- 结束：{label}（退出码 {rc}）---")
            except Exception as e:
                self._log(f"错误：{e}")
            finally:
                sys.stdout = old_stdout
                main.clear_log_callback()
                with self._lock:
                    self._running = False
                if self._on_done:
                    self._on_done(rc)

        threading.Thread(target=worker, daemon=True).start()
        return True
