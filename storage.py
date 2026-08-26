# -*- coding: utf-8 -*-
"""
SQLite 存储模块：建表、upsert 去重、采集进度记录。
"""
import sqlite3
from datetime import datetime
from pathlib import Path

import config


def get_conn(db_path=None):
    db_path = Path(db_path) if db_path else config.DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


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
            UNIQUE(city, hotel_name, checkin_date, room_type)
        )
    """)
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


def upsert_price(city, hotel_name, checkin_date, room_type, price, source="ctrip", db_path=None):
    """同酒店同日期同房型重复采集时更新价格，天然支持时间序列累积。"""
    conn = get_conn(db_path)
    conn.execute("""
        INSERT INTO prices (city, hotel_name, checkin_date, room_type, price, source)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(city, hotel_name, checkin_date, room_type)
        DO UPDATE SET price = excluded.price,
                      source = excluded.source,
                      crawled_at = datetime('now','localtime')
    """, (city, hotel_name, checkin_date, room_type, price, source))
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


def query_prices(city=None, start_date=None, end_date=None, keyword=None, db_path=None):
    """查询价格记录。可按城市、入住日起止、酒店名关键词过滤。"""
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
    if keyword:
        clauses.append("hotel_name LIKE ?")
        params.append(f"%{keyword}%")
    sql = "SELECT * FROM prices"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY city, checkin_date, hotel_name, room_type"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def count_records(db_path=None):
    conn = get_conn(db_path)
    n = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    conn.close()
    return n
