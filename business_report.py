# -*- coding: utf-8 -*-
"""
业务汇总表导出：按用户模板生成「酒店 × 房型 × 入住日期 × 采集时段」矩阵 Excel。

模板结构（每个酒店一块）：
  - 粉头：酒店名 + 入住日期（每日下分 10:00/14:00/18:00/22:00 四档）
  - 房型行：房间数量 + 各时段价格（红色高亮留空，由人工填写）
  - 流量：留空，由人工填写
  - 综合门市价：该酒店该入住日所有房型、所有时段价格的日均值（合并每日四列）
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import storage

TIME_SLOTS = storage.TIME_SLOTS
_WEEKDAY_CN = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

# 模板配色
_FILL_HOTEL = "F4CCCC"      # 粉头
_FILL_WEEK = "FCE4D6"       # 星期行
_FILL_SUMMARY = "FFF2CC"    # 流量 / 综合门市价


def _row_time_slot(row) -> str:
    ts = row["time_slot"] if "time_slot" in row.keys() else None
    if ts in TIME_SLOTS:
        return ts
    crawled = row["crawled_at"]
    if crawled:
        try:
            dt = datetime.fromisoformat(str(crawled).replace(" ", "T", 1))
            return storage.infer_time_slot(dt)
        except ValueError:
            pass
    return "10:00"


def _build_price_grid(rows):
    """
    grid[hotel][room_type][checkin_date][time_slot] = price
    同一键多条取 crawled_at 最新。
    """
    grid = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    meta = defaultdict(lambda: defaultdict(str))  # hotel -> room -> latest crawled

    for r in rows:
        if r["price"] is None:
            continue
        hotel = r["hotel_name"]
        room = r["room_type"] or "默认房型"
        d = str(r["checkin_date"])[:10]
        slot = _row_time_slot(r)
        crawled = str(r["crawled_at"] or "")
        prev = meta[hotel][room]
        if slot not in grid[hotel][room][d] or crawled >= prev:
            grid[hotel][room][d][slot] = float(r["price"])
            meta[hotel][room] = crawled
    return grid


def _sorted_dates(rows):
    return sorted({str(r["checkin_date"])[:10] for r in rows})


def _fmt_date_header(d: str) -> str:
    dt = datetime.strptime(d, "%Y-%m-%d")
    return f"{dt.month}月{dt.day}日"


def _fmt_weekday(d: str) -> str:
    dt = datetime.strptime(d, "%Y-%m-%d")
    return _WEEKDAY_CN[dt.weekday()]


def _daily_avg_price(grid_hotel, d: str) -> float | None:
    """综合门市价：该酒店该入住日所有房型、所有时段价格的均值。"""
    vals = []
    for room_prices in grid_hotel.values():
        for slot in TIME_SLOTS:
            p = room_prices.get(d, {}).get(slot)
            if p is not None:
                vals.append(p)
    return statistics.mean(vals) if vals else None


def resolve_business_report_path(detail_path: Path) -> Path:
    """与明细表同目录，文件名加 _业务汇总 后缀。"""
    return detail_path.with_name(f"{detail_path.stem}_业务汇总{detail_path.suffix}")


def export_business_report(rows, output_path: Path | None = None, *, detail_path: Path | None = None):
    """
    导出业务汇总矩阵 Excel。
    output_path 未指定时，由 detail_path 推导；二者都缺省时写入 输出/excel/今天/业务汇总_时间.xlsx
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    from exporter import resolve_export_path

    if not rows:
        raise ValueError("没有可导出的数据")

    if output_path is None:
        if detail_path is not None:
            output_path = resolve_business_report_path(Path(detail_path))
        else:
            output_path = resolve_export_path(None).with_name(
                f"业务汇总_{datetime.now().strftime('%H%M%S')}.xlsx"
            )
    else:
        output_path = Path(output_path)
        if output_path.suffix.lower() != ".xlsx":
            output_path = output_path.with_suffix(".xlsx")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    grid = _build_price_grid(rows)
    dates = _sorted_dates(rows)
    hotels = sorted(grid.keys())

    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "业务汇总"

    row_idx = 1
    slots_per_day = len(TIME_SLOTS)
    total_cols = 2 + len(dates) * slots_per_day  # A=房型 B=房间数量

    for hotel in hotels:
        hotel_grid = grid[hotel]
        room_types = sorted(
            hotel_grid.keys(),
            key=lambda rt: min(
                (p for day in hotel_grid[rt].values() for p in day.values()),
                default=0,
            ),
        )

        # ---- 行1：酒店名 + 日期（合并每 day 4 列）----
        ws.cell(row=row_idx, column=1, value=hotel)
        ws.cell(row=row_idx, column=2, value="日期")
        c = 3
        for d in dates:
            ws.merge_cells(
                start_row=row_idx, start_column=c,
                end_row=row_idx, end_column=c + slots_per_day - 1,
            )
            cell = ws.cell(row=row_idx, column=c, value=_fmt_date_header(d))
            cell.alignment = center
            c += slots_per_day
        for col in range(1, total_cols + 1):
            cell = ws.cell(row=row_idx, column=col)
            cell.fill = PatternFill("solid", fgColor=_FILL_HOTEL)
            cell.font = Font(bold=True, size=11)
            cell.border = border
            cell.alignment = center if col > 1 else left
        row_idx += 1

        # ---- 行2：星期 ----
        ws.cell(row=row_idx, column=1, value="")
        ws.cell(row=row_idx, column=2, value="星期")
        c = 3
        for d in dates:
            ws.merge_cells(
                start_row=row_idx, start_column=c,
                end_row=row_idx, end_column=c + slots_per_day - 1,
            )
            ws.cell(row=row_idx, column=c, value=_fmt_weekday(d)).alignment = center
            c += slots_per_day
        for col in range(1, total_cols + 1):
            cell = ws.cell(row=row_idx, column=col)
            cell.fill = PatternFill("solid", fgColor=_FILL_WEEK)
            cell.border = border
            cell.alignment = center if col > 1 else left
        row_idx += 1

        # ---- 行3：时段 ----
        ws.cell(row=row_idx, column=1, value="")
        ws.cell(row=row_idx, column=2, value="时段")
        c = 3
        for _d in dates:
            for slot in TIME_SLOTS:
                ws.cell(row=row_idx, column=c, value=slot).alignment = center
                c += 1
        for col in range(1, total_cols + 1):
            ws.cell(row=row_idx, column=col).border = border
            ws.cell(row=row_idx, column=col).alignment = center if col > 1 else left
        row_idx += 1

        # ---- 房型数据行 ----
        for rt in room_types:
            ws.cell(row=row_idx, column=1, value=rt).alignment = left
            ws.cell(row=row_idx, column=2, value=1).alignment = center
            c = 3
            for d in dates:
                for slot in TIME_SLOTS:
                    p = hotel_grid[rt].get(d, {}).get(slot)
                    cell = ws.cell(row=row_idx, column=c)
                    if p is not None:
                        cell.value = round(p, 2)
                    cell.alignment = center
                    cell.border = border
                    c += 1
            row_idx += 1

        # ---- 流量（留空，人工填写）----
        ws.cell(row=row_idx, column=1, value="流量")
        ws.cell(row=row_idx, column=2, value="")
        c = 3
        for _d in dates:
            ws.merge_cells(
                start_row=row_idx, start_column=c,
                end_row=row_idx, end_column=c + slots_per_day - 1,
            )
            ws.cell(row=row_idx, column=c, value="").alignment = center
            c += slots_per_day
        for col in range(1, total_cols + 1):
            cell = ws.cell(row=row_idx, column=col)
            cell.fill = PatternFill("solid", fgColor=_FILL_SUMMARY)
            cell.border = border
        row_idx += 1

        # ---- 综合门市价（每日均价，合并四列）----
        ws.cell(row=row_idx, column=1, value="综合门市价")
        ws.cell(row=row_idx, column=2, value="")
        c = 3
        for d in dates:
            ws.merge_cells(
                start_row=row_idx, start_column=c,
                end_row=row_idx, end_column=c + slots_per_day - 1,
            )
            avg = _daily_avg_price(hotel_grid, d)
            cell = ws.cell(row=row_idx, column=c)
            if avg is not None:
                cell.value = round(avg, 2)
            cell.alignment = center
            cell.border = border
            c += slots_per_day
        for col in range(1, total_cols + 1):
            cell = ws.cell(row=row_idx, column=col)
            cell.fill = PatternFill("solid", fgColor=_FILL_SUMMARY)
            cell.font = Font(bold=True)
            cell.border = border
        row_idx += 1  # 酒店块间隔

    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 10
    for col in range(3, total_cols + 1):
        ws.column_dimensions[get_column_letter(col)].width = 8

    wb.save(output_path)
    return output_path
