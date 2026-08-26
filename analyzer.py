# -*- coding: utf-8 -*-
"""
统计分析模块：均值/中位数/极值/标准差/变异系数/环比变化。
输入为 storage.query_prices() 的行，输出纯 Python 结构，供 exporter 使用。
"""
import statistics
from collections import defaultdict


def _nums(rows):
    return [r["price"] for r in rows if r["price"] is not None]


def _summarize(rows):
    nums = _nums(rows)
    if not nums:
        return None
    return {
        "count": len(nums),
        "mean": round(statistics.mean(nums), 2),
        "median": round(statistics.median(nums), 2),
        "min": round(min(nums), 2),
        "max": round(max(nums), 2),
        "std": round(statistics.stdev(nums), 2) if len(nums) > 1 else 0.0,
        "cv": round(statistics.stdev(nums) / statistics.mean(nums), 4) if len(nums) > 1 else 0.0,
    }


def city_date_summary(rows):
    """城市 × 日期汇总。返回 { (city, date): {mean, median, min, max, count} }"""
    groups = defaultdict(list)
    for r in rows:
        groups[(r["city"], r["checkin_date"])].append(r)

    result = []
    for (city, date), g in sorted(groups.items()):
        s = _summarize(g)
        if s:
            result.append({"city": city, "date": date, **s})
    return result


def hotel_volatility(rows):
    """酒店级波动率：同一酒店跨日期的 CV。返回按 CV 降序的列表。"""
    groups = defaultdict(list)
    for r in rows:
        groups[(r["city"], r["hotel_name"])].append(r)

    result = []
    for (city, hotel), g in groups.items():
        s = _summarize(g)
        if s and s["count"] >= 2:  # 至少 2 个日期才有波动率意义
            result.append({
                "city": city,
                "hotel_name": hotel,
                "count": s["count"],
                "mean": s["mean"],
                "std": s["std"],
                "cv": s["cv"],
                "min": s["min"],
                "max": s["max"],
            })
    result.sort(key=lambda x: x["cv"], reverse=True)
    return result


def price_trend(rows):
    """按城市分组的日期价格序列（均价），供折线图使用。
    返回 { city: [ (date, mean_price, n_hotels), ... ] } 按日期排序
    """
    summary = city_date_summary(rows)
    trend = defaultdict(list)
    for item in summary:
        trend[item["city"]].append((item["date"], item["mean"], item["count"]))
    for city in trend:
        trend[city].sort(key=lambda x: x[0])
    return dict(trend)


def price_mom(rows):
    """环比变化率：同一城市相邻采集日期之间的均价变化。"""
    trend = price_trend(rows)
    result = []
    for city, series in trend.items():
        for i in range(1, len(series)):
            prev_date, prev_mean, _ = series[i - 1]
            cur_date, cur_mean, _ = series[i]
            if prev_mean:
                change = round((cur_mean - prev_mean) / prev_mean * 100, 2)
            else:
                change = None
            result.append({
                "city": city,
                "from_date": prev_date,
                "to_date": cur_date,
                "prev_mean": prev_mean,
                "cur_mean": cur_mean,
                "change_pct": change,
            })
    return result
