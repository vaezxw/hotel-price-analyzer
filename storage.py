# -*- coding: utf-8 -*-
"""
SQLite 存储模块：建表、upsert 去重、采集进度记录。
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import config

TIME_SLOTS = ("10:00", "14:00", "18:00", "22:00")
BREAKFAST_WITH = "有早餐"
BREAKFAST_WITHOUT = "无早餐"
BREAKFAST_LABELS = (BREAKFAST_WITH, BREAKFAST_WITHOUT)


def infer_time_slot(dt: datetime | None = None) -> str:
    """按采集时刻归入 10:00 / 14:00 / 18:00 / 22:00 四档。"""
    dt = dt or datetime.now()
    h = dt.hour
    if h < 12:
        return "10:00"
    if h < 16:
        return "14:00"
    if h < 20:
        return "18:00"
    return "22:00"


def classify_breakfast(room_type: str | None) -> str:
    """根据房型名判断有无早餐（房型常带 ·无早餐 / ·1份早餐 等后缀）。"""
    rt = room_type or ""
    if any(k in rt for k in ("无早餐", "不含早餐", "不含早", "无早")):
        return BREAKFAST_WITHOUT
    if any(k in rt for k in ("早餐", "含早", "单早", "双早")):
        return BREAKFAST_WITH
    return BREAKFAST_WITHOUT


def get_conn(db_path=None):
    db_path = Path(db_path) if db_path else config.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_prices_table(conn):
    """旧库补 time_slot 列，并扩展唯一键以支持同日四档采集。"""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(prices)").fetchall()}
    if "time_slot" in cols:
        return
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS prices_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL,
            hotel_name TEXT NOT NULL,
            checkin_date TEXT NOT NULL,
            room_type TEXT,
            price REAL,
            source TEXT DEFAULT 'ctrip',
            crawled_at TEXT DEFAULT (datetime('now','localtime')),
            time_slot TEXT NOT NULL DEFAULT '10:00',
            UNIQUE(city, hotel_name, checkin_date, room_type, time_slot)
        );
        INSERT INTO prices_new (
            id, city, hotel_name, checkin_date, room_type, price, source, crawled_at, time_slot
        )
        SELECT id, city, hotel_name, checkin_date, room_type, price, source, crawled_at, '10:00'
        FROM prices;
        DROP TABLE prices;
        ALTER TABLE prices_new RENAME TO prices;
    """)


def init_db(db_path=None):
    conn = get_conn(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            city TEXT NOT NULL,
            hotel_name TEXT NOT NULL,
            checkin_date TEXT NOT NULL,
            room_type TEXT,
            price REAL,
            source TEXT DEFAULT 'ctrip',
            crawled_at TEXT DEFAULT (datetime('now','localtime')),
            time_slot TEXT NOT NULL DEFAULT '10:00',
            UNIQUE(city, hotel_name, checkin_date, room_type, time_slot)
        )
    """)
    _migrate_prices_table(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crawl_progress (
            city TEXT NOT NULL,
            checkin_date TEXT NOT NULL,
            status TEXT NOT NULL,          -- ok / failed
            records INTEGER DEFAULT 0,
            crawled_at TEXT DEFAULT (datetime('now','localtime')),
            PRIMARY KEY (city, checkin_date)
        )
    """)
    conn.commit()
    conn.close()


def upsert_price(
    city, hotel_name, checkin_date, room_type, price,
    source="ctrip", time_slot=None, db_path=None,
):
    """同酒店、入住日、房型、采集时段重复采集时更新价格。"""
    time_slot = time_slot or infer_time_slot()
    conn = get_conn(db_path)
    conn.execute("""
        INSERT INTO prices (city, hotel_name, checkin_date, room_type, price, source, time_slot)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(city, hotel_name, checkin_date, room_type, time_slot)
        DO UPDATE SET price = excluded.price,
                      source = excluded.source,
                      crawled_at = datetime('now','localtime')
    """, (city, hotel_name, checkin_date, room_type, price, source, time_slot))
    conn.commit()
    conn.close()


def mark_progress(city, checkin_date, status, records=0, db_path=None):
    conn = get_conn(db_path)
    conn.execute("""
        INSERT INTO crawl_progress (city, checkin_date, status, records)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(city, checkin_date)
        DO UPDATE SET status = excluded.status,
                      records = excluded.records,
                      crawled_at = datetime('now','localtime')
    """, (city, checkin_date, status, records))
    conn.commit()
    conn.close()


def has_crawled(city, checkin_date, db_path=None):
    conn = get_conn(db_path)
    row = conn.execute(
        "SELECT status FROM crawl_progress WHERE city=? AND checkin_date=?",
        (city, checkin_date),
    ).fetchone()
    conn.close()
    return row is not None and row["status"] == "ok"


def query_prices(city=None, start_date=None, end_date=None, keyword=None, hotel_names=None, db_path=None):
    """查询价格记录。可按城市、入住日起止、酒店名（单个/多个）过滤。"""
    conn = get_conn(db_path)
    clauses = []
    params = []
    if city:
        clauses.append("city=?")
        params.append(city)
    if start_date:
        clauses.append("checkin_date>=?")
        params.append(str(start_date)[:10])
    if end_date:
        clauses.append("checkin_date<=?")
        params.append(str(end_date)[:10])
    names = list(hotel_names) if hotel_names else []
    if not names and keyword:
        from scraper import parse_hotel_names
        names = parse_hotel_names(keyword)
    if len(names) > 1:
        like_parts = ["hotel_name LIKE ?"] * len(names)
        clauses.append("(" + " OR ".join(like_parts) + ")")
        params.extend(f"%{n}%" for n in names)
    elif len(names) == 1:
        clauses.append("hotel_name LIKE ?")
        params.append(f"%{names[0]}%")
    elif keyword:
        clauses.append("hotel_name LIKE ?")
        params.append(f"%{keyword}%")
    sql = "SELECT * FROM prices"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY city, checkin_date, hotel_name, room_type, time_slot"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def count_records(db_path=None):
    conn = get_conn(db_path)
    n = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    conn.close()
    return n
