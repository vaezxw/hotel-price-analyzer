# -*- coding: utf-8 -*-
"""
携程酒店房价采集与分析工具 — CLI 入口

首次使用（重要）：
  python main.py login         # 弹出浏览器窗口，扫码/手机验证码登录携程，保存登录态
                               # 2025 年起携程酒店列表强制登录，未登录无法采集

用法示例：
  python main.py collect --city 上海 --date 2026-09-01
  python main.py collect --city 上海 --start 2026-09-01 --end 2026-09-07   # 自定义日期范围
  python main.py collect --city 上海 --date 2026-09-01 --debug   # 有头模式，调试/过验证码
  python main.py collect-all --start 2026-09-01 --end 2026-09-07
  python main.py analyze
  python main.py export
  python main.py export --output 我的报告.xlsx
  python main.py run --city 上海 --start 2026-09-01 --end 2026-09-07         # 采集+分析+导出一条龙
"""
import argparse
import random
import sys
import time
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import config
import storage


def _progress(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ------------------------------------------------------------------
# 交互式菜单（无参数运行 / 双击 run.bat 时进入）
# ------------------------------------------------------------------
def _ask(prompt, default=None, allow_empty=False):
    """询问输入，回车用默认值。"""
    tip = f"{prompt}" + (f"（回车={default}）" if default is not None else "")
    while True:
        s = input(f"{tip}: ").strip()
        if s:
            return s
        if default is not None:
            return default
        if allow_empty:
            return ""
        print("  输入不能为空，请重新输入")


def _ask_date(prompt, default=None):
    """询问日期，校验 YYYY-MM-DD 格式，回车用默认值。"""
    while True:
        s = _ask(prompt, default=default).strip()
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except ValueError:
            print("  日期格式应为 YYYY-MM-DD，例如 2026-09-01，请重新输入")


def _min_checkin_date():
    """最早可采入住日（今天，含当日）。"""
    return date.today()


def _ask_future_date(prompt, default=None):
    """询问入住日，拒绝昨天及更早的日期（今天可采）。"""
    earliest = _min_checkin_date()
    if default is None:
        default = earliest.isoformat()
    while True:
        d = _ask_date(prompt, default=default)
        if d < date.today():
            print(f"  不能采集过去日期，最早可选 {earliest}（今天可采）")
            continue
        return d


def _ask_future_date_range():
    """询问开始/结束入住日（今天及以后）。"""
    earliest = _min_checkin_date()
    start = _ask_future_date(f"开始日期（最早={earliest}）", default=earliest.isoformat())
    end = _ask_future_date("结束日期（回车=与开始相同）", default=start.isoformat())
    if end < start:
        start, end = end, start
        print(f"  已自动调整：{start} ~ {end}")
    return start, end


def _ask_yes_no(prompt, default=False):
    d = "Y/n" if default else "y/N"
    s = input(f"{prompt}（{d}）: ").strip().lower()
    if not s:
        return default
    return s in ("y", "yes", "是")


def _ensure_login():
    """确保登录态存在：已保存返回 True；没有则引导立即登录。"""
    from scraper import has_login_state

    if has_login_state():
        return True
    print("未检测到携程登录态（采集必须先登录一次）。")
    if _ask_yes_no("现在登录？（弹出浏览器窗口，扫码即可）", default=True):
        return cmd_login(SimpleNamespace()) == 0
    print("已跳过登录。")
    return False


def _run_collect(cmd, args):
    """执行采集命令；若登录态失效（返回码 3），引导重新登录并自动重试一次。"""
    rc = cmd(args)
    if rc == 3:
        print("登录态缺失或已过期。")
        if _ask_yes_no("现在重新登录并自动重试采集？", default=True):
            if cmd_login(SimpleNamespace()) == 0:
                rc = cmd(args)
    return rc


def interactive_menu():
    """无参数运行时的交互式菜单。"""
    storage.init_db()

    while True:
        n = storage.count_records()
        print()
        print("=" * 46)
        print("     携程酒店房价采集与分析工具")
        print("=" * 46)
        print(f"  配置城市：{'/'.join(config.CITIES)}")
        print(f"  库内数据：{n} 条记录")
        print(f"  采集范围：今天及以后入住日（最早 { _min_checkin_date() }）")
        print(f"  导出目录：{config.OUTPUT_EXCEL_DIR / date.today().isoformat()}")
        print("-" * 46)
        print("  1. 登录携程（首次使用必做）")
        print("  2. 采集 单个城市（支持日期范围）")
        print("  3. 批量采集（配置城市 × 日期范围）")
        print("  4. 统计分析库内数据")
        print("  5. 导出 Excel（明细/汇总/趋势图/波动率）")
        print("  6. 一条龙：采集 + 分析 + 导出")
        print("  0. 退出")
        print("=" * 46)

        choice = _ask("请选择", default="0")

        try:
            if choice == "1":
                cmd_login(SimpleNamespace())

            elif choice == "2":
                if not _ensure_login():
                    continue
                city = _ask("城市（如 上海）")
                keyword = _ask("酒店名关键词（回车=该城市酒店列表）", default=None, allow_empty=True)
                start, end = _ask_future_date_range()
                debug = _ask_yes_no("有头模式（调试/过验证码）？", default=False)
                force = _ask_yes_no("强制重采（已采过也重新采）？", default=False)
                list_only = _ask_yes_no("仅采列表页首推房型？（选否=进详情页采全部房型）", default=False)
                _run_collect(cmd_collect, SimpleNamespace(
                    city=city, date=None, start=start.isoformat(), end=end.isoformat(),
                    keyword=keyword or None, debug=debug, force=force, list_only=list_only,
                ))

            elif choice == "3":
                if not _ensure_login():
                    continue
                start, end = _ask_future_date_range()
                city = _ask("只采单个城市？输入城市名（回车=全部配置城市）", default=None, allow_empty=True)
                debug = _ask_yes_no("有头模式（调试/过验证码）？", default=False)
                force = _ask_yes_no("强制重采？", default=False)
                list_only = _ask_yes_no("仅采列表页首推房型？（选否=进详情页采全部房型）", default=False)
                _run_collect(cmd_collect_all, SimpleNamespace(
                    city=city or None,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    debug=debug,
                    force=force,
                    list_only=list_only,
                ))

            elif choice == "4":
                cmd_analyze(SimpleNamespace())

            elif choice == "5":
                today_excel = config.OUTPUT_EXCEL_DIR / date.today().isoformat()
                print(f"  文件将保存到：{today_excel}")
                name = _ask("输出文件名（回车=自动命名，仅填文件名即可）", default=None, allow_empty=True)
                cmd_export(SimpleNamespace(output=(name or None)))

            elif choice == "6":
                if not _ensure_login():
                    continue
                city = _ask("城市（如 上海）")
                keyword = _ask("酒店名关键词（回车=该城市酒店列表）", default=None, allow_empty=True)
                start, end = _ask_future_date_range()
                debug = _ask_yes_no("有头模式？", default=False)
                force = _ask_yes_no("强制重采？", default=False)
                list_only = _ask_yes_no("仅采列表页首推房型？（选否=进详情页采全部房型）", default=False)
                _run_collect(cmd_run, SimpleNamespace(
                    city=city, date=None, start=start.isoformat(), end=end.isoformat(),
                    keyword=keyword or None, debug=debug, force=force, list_only=list_only,
                ))

            elif choice == "0":
                print("再见。")
                return 0

            else:
                print("无效选项，请输入 0-6")
        except KeyboardInterrupt:
            print("\n已取消当前操作，回到主菜单")
        except SystemExit as e:
            # _parse_date 等内部 sys.exit 时回到菜单
            if e.code not in (0, None):
                print(f"操作失败（码 {e.code}），回到主菜单")


def _future_dates_in_range(start, end, *, report=True):
    """返回 [start, end] 内今天及以后的入住日（跳过昨天及更早）。"""
    if start > end:
        start, end = end, start
    days = []
    skipped = []
    d = start
    while d <= end:
        if d >= date.today():
            days.append(d)
        else:
            skipped.append(d)
        d += timedelta(days=1)

    if report:
        if skipped:
            print(
                f"提示：已跳过 {len(skipped)} 个过去日期"
                f"（{skipped[0]} ~ {skipped[-1]}），仅采集今天及以后。"
            )
        if days:
            if len(days) == 1:
                print(f"将采集 1 个入住日：{days[0]}")
            else:
                print(f"将采集 {len(days)} 个入住日：{days[0]} ~ {days[-1]}")
    return days


def _resolve_collect_dates(args):
    """从 args 解析入住日期列表。支持 --date 或 --start [--end]，保留今天及以后。"""
    if getattr(args, "date", None):
        d = _parse_date(args.date)
        if d < date.today():
            print(f"错误：{d} 是过去日期（今天={date.today()}，最早可采 {_min_checkin_date()}）")
            return []
        return _future_dates_in_range(d, d)
    if getattr(args, "start", None):
        start = _parse_date(args.start)
        end = _parse_date(args.end) if getattr(args, "end", None) else start
        return _future_dates_in_range(start, end)
    print("请指定 --date 或 --start [--end]")
    return None


def _collect_days(cities, days, *, headless, force, keyword=None, full_rooms=None):
    """按城市 × 日期循环采集，返回 (exit_code, total_hotels, total_records)。"""
    from scraper import collect_city

    if not days:
        print(f"没有可采集的入住日（最早可选 {_min_checkin_date()}，含今天）。")
        return 1, 0, 0

    if full_rooms is None:
        full_rooms = config.COLLECT_ALL_ROOMS
    mode = "详情页全房型" if full_rooms else "列表页首推"
    print(f"采集模式：{mode}")

    total_hotels = total_records = 0
    keyword = keyword or None

    for city in cities:
        for d in days:
            ci = d.isoformat()
            co = (d + timedelta(days=1)).isoformat()
            task_label = f"{city}{'·' + keyword if keyword else ''}"

            if not force and storage.has_crawled(city, ci):
                print(f"[{task_label} {ci}] 已采集过，跳过（--force 可强制重采）")
                continue

            print(f"开始采集：{task_label} 入住 {ci}（{co} 退房）")
            n_hotels, n_records, blocked = collect_city(
                city, ci, co,
                headless=headless,
                progress=_progress,
                keyword=keyword,
                full_rooms=full_rooms,
            )
            total_hotels += n_hotels
            total_records += n_records

            if blocked == "login_required":
                print("需要携程登录态，请先执行：python main.py login")
                return 3, total_hotels, total_records
            if blocked:
                print(f"!! [{task_label} {ci}] 触发验证码/风控，停止后续采集")
                return 2, total_hotels, total_records

            print(f"  完成：{n_hotels} 家酒店 / {n_records} 条价格记录 已入库")
            time.sleep(random.uniform(*config.REQUEST_DELAY_RANGE))

    print(f"全部完成：{total_hotels} 家酒店 / {total_records} 条记录")
    return 0, total_hotels, total_records


def cmd_collect(args):
    """采集单个城市：单日（--date）或日期范围（--start [--end]），可带酒店名关键词。"""
    storage.init_db()
    days = _resolve_collect_dates(args)
    if days is None:
        return 1
    rc, _, _ = _collect_days(
        [args.city], days,
        headless=not args.debug,
        force=args.force,
        keyword=getattr(args, "keyword", None),
        full_rooms=not getattr(args, "list_only", False),
    )
    return rc


def cmd_collect_all(args):
    """按配置批量采集：城市 × 日期范围。"""
    storage.init_db()
    days = _resolve_collect_dates(args)
    if days is None:
        return 1
    cities = [args.city] if args.city else config.CITIES
    rc, _, _ = _collect_days(
        cities, days,
        headless=not args.debug,
        force=args.force,
        keyword=getattr(args, "keyword", None),
        full_rooms=not getattr(args, "list_only", False),
    )
    return rc


def cmd_login(args):
    """有头模式打开携程，用户手动登录，保存登录态。"""
    import asyncio

    from scraper import login_and_save_state

    print("即将打开携程登录窗口（有头模式）...")
    print("请在浏览器中完成登录：扫码 或 手机验证码")
    # login_and_save_state 是协程，必须 asyncio.run 驱动，否则浏览器不会启动
    ok = asyncio.run(login_and_save_state(progress=_progress))
    if ok:
        print("登录态已保存，之后采集会自动复用。")
        return 0
    print("登录未完成，未保存登录态。")
    return 1


def _filter_from_args(args):
    """从命令参数取出城市/日期/关键词筛选条件。"""
    start = getattr(args, "start", None) or getattr(args, "date", None)
    end = getattr(args, "end", None) or getattr(args, "date", None)
    return {
        "city": getattr(args, "city", None) or None,
        "start_date": start,
        "end_date": end,
        "keyword": getattr(args, "keyword", None) or None,
    }


def _query_for_report(args):
    """按本次操作的筛选条件查库；菜单里的「全库分析/导出」不带条件则查全部。"""
    filters = _filter_from_args(args)
    rows = storage.query_prices(**filters)
    total = storage.count_records()
    if any(filters.values()) and rows:
        bits = []
        if filters["city"]:
            bits.append(filters["city"])
        if filters["keyword"]:
            bits.append(filters["keyword"])
        if filters["start_date"] or filters["end_date"]:
            bits.append(f"{filters['start_date'] or '最早'} ~ {filters['end_date'] or '最晚'}")
        print(f"本次筛选：{' · '.join(bits)}  → {len(rows)} 条（库内共 {total} 条）")
    return rows


def cmd_analyze(args):
    """对库内数据做统计分析并打印摘要。"""
    storage.init_db()
    import analyzer

    rows = _query_for_report(args)
    if not rows:
        print("没有符合条件的数据。若刚采集过，请核对城市/酒店名/入住日期。")
        return 1

    summary = analyzer.city_date_summary(rows)
    vol = analyzer.hotel_volatility(rows)
    mom = analyzer.price_mom(rows)

    print(f"库中共 {len(rows)} 条记录 / {len(summary)} 个城市×日期组合")
    print()
    print("=== 城市 × 日期 均价摘要 ===")
    for s in summary[:20]:
        print(f"  {s['city']} {s['date']}: 均价 ¥{s['mean']}  中位 ¥{s['median']}  "
              f"[{s['min']} ~ {s['max']}]  n={s['count']}  CV={s['cv']}")
    if len(summary) > 20:
        print(f"  ... 共 {len(summary)} 行")

    print()
    print("=== 波动率 TOP 10（变异系数最大）===")
    for v in vol[:10]:
        print(f"  {v['city']} {v['hotel_name']}: CV={v['cv']} 均值¥{v['mean']} "
              f"范围 [{v['min']}~{v['max']}] n={v['count']}")

    if mom:
        print()
        print("=== 环比变化（最近 5 组）===")
        for m in mom[-5:]:
            chg = f"{m['change_pct']}%" if m["change_pct"] is not None else "N/A"
            print(f"  {m['city']} {m['from_date']}→{m['to_date']}: "
                  f"¥{m['prev_mean']} → ¥{m['cur_mean']} ({chg})")
    return 0


def cmd_export(args):
    """导出 Excel（明细/汇总/趋势图/波动率）。"""
    storage.init_db()
    from exporter import export_excel

    rows = _query_for_report(args)
    if not rows:
        print("没有符合条件的数据。若刚采集过，请核对城市/酒店名/入住日期。")
        return 1

    filters = _filter_from_args(args)
    out = export_excel(
        rows,
        output_path=getattr(args, "output", None),
        city=filters["city"],
        start_date=filters["start_date"],
        end_date=filters["end_date"],
        keyword=filters["keyword"],
    )
    print(f"已导出：{out}")
    print(f"保存目录：{out.parent}")
    return 0


def cmd_run(args):
    """采集 + 分析 + 导出 一条龙。"""
    rc = cmd_collect(args)
    if rc != 0:
        return rc
    cmd_analyze(args)
    return cmd_export(args)


def _parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        print(f"日期格式错误：{s}（应为 YYYY-MM-DD）")
        sys.exit(1)


def main():
    # 无参数运行（双击 run.bat）→ 交互式菜单
    if len(sys.argv) == 1:
        try:
            sys.exit(interactive_menu())
        except (KeyboardInterrupt, EOFError):
            print("\n再见。")
            sys.exit(0)

    parser = argparse.ArgumentParser(
        description="携程酒店房价采集与分析工具（个人非商用）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_login = sub.add_parser("login", help="首次使用：登录携程并保存登录态")
    p_login.set_defaults(func=cmd_login)

    p_collect = sub.add_parser("collect", help="采集单个城市（单日或日期范围）")
    p_collect.add_argument("--city", required=True, help="城市名，如 上海")
    p_collect.add_argument("--keyword", default=None, help="酒店名关键词（精确采集某家酒店）")
    collect_dates = p_collect.add_mutually_exclusive_group(required=True)
    collect_dates.add_argument("--date", help="单个入住日期 YYYY-MM-DD")
    collect_dates.add_argument("--start", help="开始日期 YYYY-MM-DD（与 --end 搭配指定范围）")
    p_collect.add_argument("--end", help="结束日期 YYYY-MM-DD（缺省与 --start 相同）")
    p_collect.add_argument("--debug", action="store_true", help="有头模式（调试/过验证码）")
    p_collect.add_argument("--force", action="store_true", help="强制重采")
    p_collect.add_argument("--list-only", action="store_true",
                           help="仅采列表页首推房型（默认进详情页采全部房型）")
    p_collect.set_defaults(func=cmd_collect)

    p_all = sub.add_parser("collect-all", help="批量采集：城市 × 日期范围")
    p_all.add_argument("--city", default=None, help="指定单个城市，缺省为配置全部城市")
    p_all.add_argument("--keyword", default=None, help="酒店名关键词（精确采集某家酒店）")
    p_all.add_argument("--start", required=True, help="开始日期 YYYY-MM-DD")
    p_all.add_argument("--end", help="结束日期 YYYY-MM-DD（缺省与 --start 相同）")
    p_all.add_argument("--debug", action="store_true")
    p_all.add_argument("--force", action="store_true")
    p_all.add_argument("--list-only", action="store_true",
                         help="仅采列表页首推房型（默认进详情页采全部房型）")
    p_all.set_defaults(func=cmd_collect_all)

    p_an = sub.add_parser("analyze", help="统计分析库内数据")
    p_an.set_defaults(func=cmd_analyze)

    p_exp = sub.add_parser("export", help="导出 Excel")
    p_exp.add_argument("--output", default=None, help="输出文件路径")
    p_exp.set_defaults(func=cmd_export)

    p_run = sub.add_parser("run", help="采集+分析+导出 一条龙")
    p_run.add_argument("--city", required=True, help="城市名，如 上海")
    p_run.add_argument("--keyword", default=None, help="酒店名关键词（精确采集某家酒店）")
    run_dates = p_run.add_mutually_exclusive_group(required=True)
    run_dates.add_argument("--date", help="单个入住日期 YYYY-MM-DD")
    run_dates.add_argument("--start", help="开始日期 YYYY-MM-DD（与 --end 搭配指定范围）")
    p_run.add_argument("--end", help="结束日期 YYYY-MM-DD（缺省与 --start 相同）")
    p_run.add_argument("--debug", action="store_true")
    p_run.add_argument("--force", action="store_true")
    p_run.add_argument("--list-only", action="store_true",
                         help="仅采列表页首推房型（默认进详情页采全部房型）")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
