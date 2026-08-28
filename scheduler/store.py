# -*- coding: utf-8 -*-
"""定时任务 CRUD（复用 hotel_prices.db）。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import storage

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


@dataclass
class Schedule:
    id: int | None = None
    name: str = ""
    enabled: bool = True
    city: str = "上海"
    hotels: list[str] = field(default_factory=list)
    date_mode: str = "rolling"  # rolling | fixed
    start_date: str | None = None
    end_date: str | None = None
    rolling_days: int = 7
    times: list[str] = field(default_factory=lambda: ["10:00", "14:00", "18:00"])
    days_of_week: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])  # Mon=0
    force: bool = False
    headless: bool = True
    last_run_at: str | None = None
    last_run_status: str | None = None
    last_error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    def hotels_text(self) -> str:
        return "\n".join(self.hotels)


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_schedule_tables(db_path=None) -> None:
    storage.init_db(db_path)
    conn = storage.get_conn(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                city TEXT NOT NULL,
                hotels_json TEXT NOT NULL DEFAULT '[]',
                date_mode TEXT NOT NULL DEFAULT 'rolling',
                start_date TEXT,
                end_date TEXT,
                rolling_days INTEGER NOT NULL DEFAULT 7,
                times_json TEXT NOT NULL DEFAULT '["10:00","14:00","18:00"]',
                days_of_week_json TEXT NOT NULL DEFAULT '[0,1,2,3,4,5,6]',
                force INTEGER NOT NULL DEFAULT 0,
                headless INTEGER NOT NULL DEFAULT 1,
                last_run_at TEXT,
                last_run_status TEXT,
                last_error TEXT,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS schedule_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_id INTEGER NOT NULL,
                run_date TEXT NOT NULL,
                trigger_time TEXT NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                started_at TEXT,
                finished_at TEXT,
                UNIQUE(schedule_id, run_date, trigger_time)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_schedule(row) -> Schedule:
    return Schedule(
        id=row["id"],
        name=row["name"] or "",
        enabled=bool(row["enabled"]),
        city=row["city"] or "",
        hotels=json.loads(row["hotels_json"] or "[]"),
        date_mode=row["date_mode"] or "rolling",
        start_date=row["start_date"],
        end_date=row["end_date"],
        rolling_days=int(row["rolling_days"] or 7),
        times=json.loads(row["times_json"] or "[]"),
        days_of_week=json.loads(row["days_of_week_json"] or "[]"),
        force=bool(row["force"]),
        headless=bool(row["headless"]),
        last_run_at=row["last_run_at"],
        last_run_status=row["last_run_status"],
        last_error=row["last_error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_schedules(db_path=None) -> list[Schedule]:
    init_schedule_tables(db_path)
    conn = storage.get_conn(db_path)
    try:
        rows = conn.execute("SELECT * FROM schedules ORDER BY id").fetchall()
        return [_row_to_schedule(r) for r in rows]
    finally:
        conn.close()


def get_schedule(schedule_id: int, db_path=None) -> Schedule | None:
    init_schedule_tables(db_path)
    conn = storage.get_conn(db_path)
    try:
        row = conn.execute("SELECT * FROM schedules WHERE id=?", (schedule_id,)).fetchone()
        return _row_to_schedule(row) if row else None
    finally:
        conn.close()


def normalize_time(s: str) -> str | None:
    s = (s or "").strip()
    m = _TIME_RE.match(s)
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def parse_hotels_text(text: str) -> list[str]:
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def parse_times_list(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        t = normalize_time(raw)
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return sorted(out)


def save_schedule(sched: Schedule, db_path=None) -> Schedule:
    init_schedule_tables(db_path)
    if not sched.name.strip():
        raise ValueError("任务名称不能为空")
    if not sched.city.strip():
        raise ValueError("城市不能为空")
    hotels = [h for h in sched.hotels if h.strip()]
    if not hotels:
        raise ValueError("请至少填写一家酒店")
    times = parse_times_list(sched.times)
    if not times:
        raise ValueError("请至少设置一个触发时刻（如 10:00）")
    days = sorted({int(d) for d in sched.days_of_week if 0 <= int(d) <= 6})
    if not days:
        raise ValueError("请至少选择一个星期")
    if sched.date_mode not in ("rolling", "fixed"):
        raise ValueError("日期模式无效")
    if sched.date_mode == "rolling":
        if sched.rolling_days < 1 or sched.rolling_days > 60:
            raise ValueError("滚动天数需在 1～60 之间")
    else:
        if not sched.start_date or not sched.end_date:
            raise ValueError("固定模式需填写开始/结束日期")
        try:
            d0 = datetime.strptime(sched.start_date, "%Y-%m-%d").date()
            d1 = datetime.strptime(sched.end_date, "%Y-%m-%d").date()
        except ValueError as e:
            raise ValueError("日期格式应为 YYYY-MM-DD") from e
        if d1 < d0:
            raise ValueError("结束日期不能早于开始日期")

    now = _now_str()
    hotels_json = json.dumps(hotels, ensure_ascii=False)
    times_json = json.dumps(times, ensure_ascii=False)
    days_json = json.dumps(days, ensure_ascii=False)
    conn = storage.get_conn(db_path)
    try:
        if sched.id is None:
            cur = conn.execute(
                """
                INSERT INTO schedules (
                    name, enabled, city, hotels_json, date_mode, start_date, end_date,
                    rolling_days, times_json, days_of_week_json, force, headless,
                    created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    sched.name.strip(),
                    1 if sched.enabled else 0,
                    sched.city.strip(),
                    hotels_json,
                    sched.date_mode,
                    sched.start_date,
                    sched.end_date,
                    int(sched.rolling_days),
                    times_json,
                    days_json,
                    1 if sched.force else 0,
                    1 if sched.headless else 0,
                    now,
                    now,
                ),
            )
            sched.id = int(cur.lastrowid)
        else:
            conn.execute(
                """
                UPDATE schedules SET
                    name=?, enabled=?, city=?, hotels_json=?, date_mode=?,
                    start_date=?, end_date=?, rolling_days=?, times_json=?,
                    days_of_week_json=?, force=?, headless=?, updated_at=?
                WHERE id=?
                """,
                (
                    sched.name.strip(),
                    1 if sched.enabled else 0,
                    sched.city.strip(),
                    hotels_json,
                    sched.date_mode,
                    sched.start_date,
                    sched.end_date,
                    int(sched.rolling_days),
                    times_json,
                    days_json,
                    1 if sched.force else 0,
                    1 if sched.headless else 0,
                    now,
                    sched.id,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return get_schedule(sched.id, db_path)  # type: ignore[return-value]


def delete_schedule(schedule_id: int, db_path=None) -> None:
    init_schedule_tables(db_path)
    conn = storage.get_conn(db_path)
    try:
        conn.execute("DELETE FROM schedule_runs WHERE schedule_id=?", (schedule_id,))
        conn.execute("DELETE FROM schedules WHERE id=?", (schedule_id,))
        conn.commit()
    finally:
        conn.close()


def update_schedule_run_meta(
    schedule_id: int,
    *,
    status: str,
    error: str | None = None,
    db_path=None,
) -> None:
    init_schedule_tables(db_path)
    conn = storage.get_conn(db_path)
    try:
        conn.execute(
            """
            UPDATE schedules
            SET last_run_at=?, last_run_status=?, last_error=?, updated_at=?
            WHERE id=?
            """,
            (_now_str(), status, error, _now_str(), schedule_id),
        )
        conn.commit()
    finally:
        conn.close()


def has_run_today(
    schedule_id: int,
    trigger_time: str,
    run_date: str | None = None,
    db_path=None,
) -> bool:
    """今天该触发点是否已有记录（含 running/ok/fail/skipped）。默认不补跑。"""
    init_schedule_tables(db_path)
    run_date = run_date or date.today().isoformat()
    conn = storage.get_conn(db_path)
    try:
        row = conn.execute(
            """
            SELECT 1 FROM schedule_runs
            WHERE schedule_id=? AND run_date=? AND trigger_time=?
            LIMIT 1
            """,
            (schedule_id, run_date, trigger_time),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def begin_run(
    schedule_id: int,
    trigger_time: str,
    run_date: str | None = None,
    db_path=None,
) -> bool:
    """标记开始；若今日该点已存在则返回 False。"""
    init_schedule_tables(db_path)
    run_date = run_date or date.today().isoformat()
    conn = storage.get_conn(db_path)
    try:
        conn.execute(
            """
            INSERT INTO schedule_runs
                (schedule_id, run_date, trigger_time, status, started_at)
            VALUES (?, ?, ?, 'running', ?)
            """,
            (schedule_id, run_date, trigger_time, _now_str()),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def finish_run(
    schedule_id: int,
    trigger_time: str,
    status: str,
    message: str | None = None,
    run_date: str | None = None,
    db_path=None,
) -> None:
    init_schedule_tables(db_path)
    run_date = run_date or date.today().isoformat()
    conn = storage.get_conn(db_path)
    try:
        conn.execute(
            """
            UPDATE schedule_runs
            SET status=?, message=?, finished_at=?
            WHERE schedule_id=? AND run_date=? AND trigger_time=?
            """,
            (status, message, _now_str(), schedule_id, run_date, trigger_time),
        )
        conn.commit()
    finally:
        conn.close()
    update_schedule_run_meta(
        schedule_id,
        status=status,
        error=message if status not in ("ok", "skipped") else None,
        db_path=db_path,
    )


def resolve_date_range(sched: Schedule, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    if sched.date_mode == "fixed":
        d0 = datetime.strptime(sched.start_date, "%Y-%m-%d").date()  # type: ignore[arg-type]
        d1 = datetime.strptime(sched.end_date, "%Y-%m-%d").date()  # type: ignore[arg-type]
        if d0 < today:
            d0 = today
        if d1 < today:
            d1 = today
        if d1 < d0:
            d1 = d0
        return d0, d1
    days = max(1, int(sched.rolling_days))
    return today, today + timedelta(days=days - 1)


def schedule_to_collect_args(sched: Schedule) -> Any:
    from types import SimpleNamespace

    start, end = resolve_date_range(sched)
    return SimpleNamespace(
        city=sched.city,
        keyword="\n".join(sched.hotels),
        date=None,
        start=start.isoformat(),
        end=end.isoformat(),
        debug=not sched.headless,
        force=sched.force,
        list_only=False,
        output=None,
    )
