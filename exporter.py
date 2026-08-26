# -*- coding: utf-8 -*-
"""
Excel 导出模块：明细 / 城市汇总 / 价格趋势图 / 波动率排行 四个 Sheet。
"""
import io
from datetime import datetime
from pathlib import Path

import analyzer
import matplotlib

matplotlib.use("Agg")  # 无界面后端，避免 GUI 弹窗
import matplotlib.pyplot as plt
from matplotlib import font_manager

import config

# ------------------------------------------------------------------
# 中文字体配置（Windows 常见中文字体）
# ------------------------------------------------------------------
def _setup_cn_font():
    candidates = ["Microsoft YaHei", "SimHei", "SimSun", "PingFang SC", "Noto Sans CJK SC"]
    for name in candidates:
        try:
            font_manager.findfont(name, fallback_to_default=False)
            plt.rcParams["font.sans-serif"] = [name]
            plt.rcParams["axes.unicode_minus"] = False
            return
        except Exception:
            continue
    # 兜底：尝试注册本机字体
    for fp in [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
    ]:
        p = Path(fp)
        if p.exists():
            font_manager.fontManager.addfont(str(p))
            name = font_manager.FontProperties(fname=str(p)).get_name()
            plt.rcParams["font.sans-serif"] = [name]
            plt.rcParams["axes.unicode_minus"] = False
            return
    print("警告：未找到中文字体，趋势图中文可能显示为方框")


_setup_cn_font()

# ------------------------------------------------------------------
# 导出路径（统一归纳到 输出/excel/YYYY-MM-DD/）
# ------------------------------------------------------------------
def _safe_filename(text, max_len=30):
    """去掉 Windows 文件名非法字符并截断。"""
    if not text:
        return ""
    for ch in '\\/:*?"<>|':
        text = text.replace(ch, "_")
    text = text.strip().strip(".")
    return text[:max_len] if max_len else text


def resolve_export_path(output_path=None, *, city=None, start_date=None, end_date=None, keyword=None):
    """
    解析最终导出路径。
    - 未指定路径：输出/excel/今天/城市_日期范围_时间.xlsx
    - 仅文件名：输出/excel/今天/文件名.xlsx
    - 绝对路径：按用户指定
    - 含子目录的相对路径：相对于 输出/ 目录
    """
    today_dir = config.OUTPUT_EXCEL_DIR / datetime.now().strftime("%Y-%m-%d")
    today_dir.mkdir(parents=True, exist_ok=True)

    if output_path:
        p = Path(output_path)
        if p.suffix.lower() != ".xlsx":
            p = p.with_suffix(".xlsx")
        if p.is_absolute():
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        if len(p.parts) == 1:
            return today_dir / p.name
        out = config.OUTPUT_DIR / p
        out.parent.mkdir(parents=True, exist_ok=True)
        return out

    parts = []
    if city:
        parts.append(_safe_filename(city, 20))
    if keyword:
        parts.append(_safe_filename(keyword, 24))
    if start_date:
        s = start_date.replace("-", "")
        e = (end_date or start_date).replace("-", "")
        parts.append(s if s == e else f"{s}-{e}")
    parts.append(datetime.now().strftime("%H%M%S"))
    if parts:
        name = "_".join(parts) + ".xlsx"
    else:
        name = config.EXPORT_FILENAME_TEMPLATE.format(
            date=datetime.now().strftime("%Y%m%d_%H%M%S")
        )
    return today_dir / name


# ------------------------------------------------------------------
# 图表颜色（浅色背景 + 可读深色线条，每城市一色）
# ------------------------------------------------------------------
TREND_COLORS = [
    "#185FA5", "#0F6E56", "#993C1D", "#854F0B",
    "#534AB7", "#993556", "#3B6D11", "#A32D2D",
]


def make_trend_chart(trend):
    """生成价格趋势折线图，返回 PNG 字节。trend = {city: [(date, mean, n)]}"""
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=110)
    for i, (city, series) in enumerate(trend.items()):
        dates = [d for d, _, _ in series]
        means = [m for _, m, _ in series]
        ax.plot(dates, means, marker="o", linewidth=1.8, markersize=5,
                color=TREND_COLORS[i % len(TREND_COLORS)], label=city)

    ax.set_title("各城市酒店日均价趋势", fontsize=14, fontweight="bold", pad=14)
    ax.set_xlabel("入住日期")
    ax.set_ylabel("平均房价（元/晚）")
    ax.grid(True, linestyle="--", alpha=0.35)
    ax.legend(loc="best", frameon=False)

    fig.autofmt_xdate()
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def export_excel(rows, output_path=None, trend=None, volatility=None, mom=None,
                 *, city=None, start_date=None, end_date=None, keyword=None):
    """导出多 Sheet Excel。rows 为 storage 查询结果。"""
    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Font

    output_path = resolve_export_path(
        output_path, city=city, start_date=start_date, end_date=end_date, keyword=keyword,
    )

    trend = trend if trend is not None else analyzer.price_trend(rows)
    volatility = volatility if volatility is not None else analyzer.hotel_volatility(rows)
    mom = mom if mom is not None else analyzer.price_mom(rows)

    wb = Workbook()

    # ---------- Sheet 1: 明细数据 ----------
    ws = wb.active
    ws.title = "明细数据"
    headers = ["城市", "酒店名称", "入住日期", "房型", "价格(元/晚)", "来源", "采集时间"]
    ws.append(headers)
    for r in rows:
        ws.append([r["city"], r["hotel_name"], r["checkin_date"], r["room_type"],
                   r["price"], r["source"], r["crawled_at"]])
    _style_header(ws, headers)

    # ---------- Sheet 2: 城市汇总 ----------
    ws2 = wb.create_sheet("城市汇总")
    h2 = ["城市", "入住日期", "样本数", "均价(元)", "中位数", "最低价", "最高价", "标准差", "变异系数CV"]
    ws2.append(h2)
    summary = analyzer.city_date_summary(rows)
    for s in summary:
        ws2.append([s["city"], s["date"], s["count"], s["mean"], s["median"],
                    s["min"], s["max"], s["std"], s["cv"]])
    _style_header(ws2, h2)

    # ---------- Sheet 3: 价格趋势图 ----------
    ws3 = wb.create_sheet("价格趋势")
    if trend:
        png = make_trend_chart(trend)
        img = XLImage(io.BytesIO(png))
        img.width = 900
        img.height = 500
        ws3.add_image(img, "A1")
        ws3["A35"] = "说明：折线为各城市酒店日均价（每个入住日期的均价）"
        ws3["A35"].font = Font(size=10, color="666666")

    # ---------- Sheet 4: 波动率排行 ----------
    ws4 = wb.create_sheet("波动率排行")
    h4 = ["排名", "城市", "酒店名称", "有效日期数", "均价(元)", "标准差", "变异系数CV", "最低价", "最高价"]
    ws4.append(h4)
    for i, v in enumerate(volatility, 1):
        ws4.append([i, v["city"], v["hotel_name"], v["count"], v["mean"],
                    v["std"], v["cv"], v["min"], v["max"]])
    _style_header(ws4, h4)
    ws4.append([])
    ws4.append(["环比说明", "相邻采集日期的均价变化率"])
    ws4["A12"] = "环比变化"
    ws4["A12"].font = Font(bold=True, size=12)
    for i, m in enumerate(mom[:30], 1):
        ws4.append([f"  {m['city']}", f"{m['from_date']} → {m['to_date']}",
                    f"均价 {m['prev_mean']} → {m['cur_mean']}",
                    f"{m['change_pct']}%"])

    wb.save(output_path)
    return output_path


def _style_header(ws, headers):
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    fill = PatternFill("solid", fgColor="185FA5")
    for col_idx, _ in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill
        cell.alignment = Alignment(horizontal="center")
    # 自动列宽（粗略）
    for col_idx in range(1, len(headers) + 1):
        letter = get_column_letter(col_idx)
        max_len = 0
        for row in ws.iter_rows(min_col=col_idx, max_col=col_idx):
            v = row[0].value
            if v is not None:
                max_len = max(max_len, len(str(v)))
        ws.column_dimensions[letter].width = min(max_len + 4, 60)
