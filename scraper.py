# -*- coding: utf-8 -*-
"""
携程酒店房价采集核心（Playwright）。

设计要点：
- 选择器集中在 config.SELECTORS，携程改版只改 config
- 提取失败时用「整卡文本 + 正则」兜底，增强对页面改版的鲁棒性
- 随机 UA / 随机延迟，反爬人性化
- 验证码检测：命中即停止并提示，不硬闯
- 结果直接 upsert 进 SQLite，可断点续采
- 2025 年起携程酒店列表强制登录：先 python main.py login 保存登录态，
  采集时自动复用；若登录态失效会提示重新登录
"""
import asyncio
import json
import random
import re
from pathlib import Path

from playwright.async_api import async_playwright

import config
import storage

# 浏览器指纹档案（登录时保存 UA/视口，采集时复用，避免指纹变化导致会话失效）
PROFILE_PATH = config.BASE_DIR / "data" / "browser_profile.json"

# 弱化自动化特征：隐藏 navigator.webdriver，降低被风控识别概率
LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]

# 价格正则：兼容 ¥123、¥123起、1,234、123.5 等
_PRICE_RE = re.compile(r"[\d,]+\.?\d*")
# 详情页内嵌 JSON 中的房型+价格（SSR 数据，比 DOM 更完整）
_ROOM_JSON_RE = [
    re.compile(
        r'\\"saleRoomName\\":\\"([^\\"]+)\\".{0,1200}?\\"price\\":(\d+(?:\.\d+)?)',
        re.S,
    ),
    re.compile(
        r'"saleRoomName":"([^"]+)".{0,1200}?"price":(\d+(?:\.\d+)?)',
        re.S,
    ),
    re.compile(
        r'\\"physicsName\\":\\"([^\\"]+)\\".{0,1200}?\\"price\\":(\d+(?:\.\d+)?)',
        re.S,
    ),
]


def clean_price(text):
    """从价格文本中提取数字，失败返回 None。"""
    if not text:
        return None
    m = _PRICE_RE.search(text.replace(",", ""))
    if not m:
        return None
    try:
        return round(float(m.group()), 2)
    except ValueError:
        return None


def _dedupe_rooms(rooms):
    """同名房型保留最低价；返回 [(room_type, price), ...]。"""
    best = {}
    for name, price in rooms:
        if not name or price is None:
            continue
        name = re.sub(r"\s+", " ", str(name)).strip()[:80]
        if not name:
            continue
        if name not in best or price < best[name]:
            best[name] = price
    items = list(best.items())
    items.sort(key=lambda x: x[1])
    return items[: config.MAX_ROOMS_PER_HOTEL]


_TAGTITLE_RE = re.compile(
    r'(?:\\"tagtitle\\":\\"|&quot;tagtitle&quot;:&quot;)([^\\"&]+?)(?:\\"|&quot;)'
)


def _sale_row_tags(row_html):
    """从详情页售卖行 data-exposure 中提取 tagtitle（如 无早餐、在线付）。"""
    tags = _TAGTITLE_RE.findall(row_html)
    return [t.strip() for t in tags if t.strip()]


def _detail_room_label(base_name, tags):
    """组合物理房型名 + 早餐标签；同标签多价格由 _dedupe_rooms 保留最低价。"""
    breakfast = next((t for t in tags if "早餐" in t), "")
    if breakfast:
        return f"{base_name}·{breakfast}"
    return base_name


def parse_rooms_from_detail_html(html):
    """
    解析携程酒店详情页房型列表（commonRoomCard / commonRoomCardHidden + saleRoomItemBox）。
    详情页 DOM/JSON 与列表页不同，不使用 saleRoomName。
    """
    if not html:
        return []
    if "commonRoomCard__" not in html and "commonRoomCardHidden__" not in html:
        return []

    blocks = []
    for marker in ('class="commonRoomCard__', 'class="commonRoomCardHidden__'):
        blocks.extend(html.split(marker)[1:])

    rooms = []
    for block in blocks:
        title_m = re.search(
            r'commonRoomCard-title__[^"]*"[^>]*aria-label="([^"]+)"',
            block,
        )
        if not title_m:
            continue
        base_name = re.sub(r"\s+", " ", title_m.group(1)).strip()
        if not base_name:
            continue

        for row_m in re.finditer(r'class="saleRoomItemBox__[^"]*"', block):
            row = block[row_m.start(): row_m.start() + 12000]
            price_m = re.search(r'aria-label="Current price ¥([\d,]+)"', row)
            if not price_m:
                continue
            price = clean_price(price_m.group(1))
            if price is None:
                continue
            tags = _sale_row_tags(row)
            room_type = _detail_room_label(base_name, tags)
            rooms.append((room_type, price))

    return _dedupe_rooms(rooms)


def parse_rooms_from_page_json(html):
    """从列表页内嵌 JSON（saleRoomName / physicsName + price）解析房型。"""
    if not html:
        return []
    rooms = []
    for pattern in _ROOM_JSON_RE:
        for name, price in pattern.findall(html):
            p = clean_price(price)
            if p is not None:
                rooms.append((name, p))
    return _dedupe_rooms(rooms)


def parse_rooms_from_html(html):
    """统一入口：优先详情页结构，其次列表页 JSON。"""
    rooms = parse_rooms_from_detail_html(html)
    if rooms:
        return rooms
    return parse_rooms_from_page_json(html)


async def extract_card_meta(card):
    """从列表卡片提取 hotel_id 与酒店名。"""
    hotel_id = await card.get_attribute("id")
    name_el = await card.query_selector(config.SELECTORS["hotel_name"])
    name = (await name_el.inner_text()).strip() if name_el else ""
    name = re.sub(r"\s+", " ", name).strip()
    return hotel_id, name


async def parse_rooms_from_detail_dom(page):
    """从详情页解析房型（HTML 结构解析 + DOM 选择器兜底）。"""
    html = await page.content()
    rooms = parse_rooms_from_detail_html(html)
    if rooms:
        return rooms

    blocks = await page.query_selector_all(config.SELECTORS["detail_room_block"])
    for block in blocks:
        name = price = None
        name_el = await block.query_selector(config.SELECTORS["detail_room_name"])
        if name_el:
            name = (await name_el.inner_text()).strip()
        price_el = await block.query_selector(config.SELECTORS["detail_room_price"])
        if price_el:
            price = clean_price(await price_el.inner_text())
        if not price:
            line_el = await block.query_selector(config.SELECTORS["price_line"])
            if line_el:
                price = clean_price(await line_el.inner_text())
        if name and price is not None:
            rooms.append((name, price))

    # aria-label 兜底（详情页价格常用此属性）
    if not rooms:
        titles = re.findall(
            r'commonRoomCard-title__[^"]*"[^>]*aria-label="([^"]+)"',
            html,
        )
        prices = re.findall(r'aria-label="Current price ¥([\d,]+)"', html)
        if titles and prices:
            base = titles[0]
            used = set()
            for p in prices:
                price = clean_price(p)
                if price is None:
                    continue
                label = base if base not in used else f"{base}·¥{int(price)}"
                used.add(label)
                rooms.append((label, price))

    return _dedupe_rooms(rooms)


async def scrape_hotel_all_rooms(page, hotel_id, city_id, check_in, check_out, hotel_name, progress):
    """
    打开酒店详情页，采集全部可售房型。
    返回 (blocked, rooms)；blocked 为 False / 'login_required' / 'captcha'。
    """
    url = config.HOTEL_DETAIL_URL.format(
        hotel_id=hotel_id,
        city_id=city_id,
        check_in=check_in,
        check_out=check_out,
    )
    progress(f"  → {hotel_name} 详情页采集房型...")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)
    except Exception as e:
        progress(f"  详情页打开失败：{e}")
        return False, []

    await asyncio.sleep(2)
    if is_login_url(page.url):
        return "login_required", []
    if await detect_captcha(page):
        return "captcha", []

    try:
        await page.wait_for_selector(
            '[class*="commonRoomCard-title"], [class*="saleRoomItemBox"]',
            timeout=config.WAIT_SELECTOR_MS,
        )
    except Exception:
        pass

    # 点击「展示额外N个房型价格」展开折叠房型（失败忽略）
    try:
        expand_btns = page.locator("text=/展示额外\\d+个房型价格/")
        n = await expand_btns.count()
        for i in range(min(n, 20)):
            btn = expand_btns.nth(i)
            if await btn.is_visible():
                await btn.click(timeout=2000)
                await asyncio.sleep(0.3)
    except Exception:
        pass

    prev_count = 0
    for _ in range(config.DETAIL_SCROLL_TIMES):
        await page.mouse.wheel(0, 2500)
        await asyncio.sleep(random.uniform(0.8, 1.3))
        html = await page.content()
        cur_count = len(parse_rooms_from_detail_html(html))
        if cur_count > 0 and cur_count == prev_count and _ > 1:
            break
        prev_count = cur_count

    html = await page.content()
    rooms = parse_rooms_from_html(html)
    if not rooms:
        rooms = await parse_rooms_from_detail_dom(page)
    if rooms:
        progress(f"  ← {hotel_name} 解析到 {len(rooms)} 个房型/价格")
    if not rooms:
        await _dump_page_html(
            page,
            config.BASE_DIR / "data" / f"debug_detail_{hotel_id}_{check_in}.html",
            progress,
        )
        progress(f"  警告：{hotel_name} 详情页未解析到房型")
    return False, rooms


async def extract_card(card):
    """从一张酒店卡片中提取 (name, price, room_type)。按 2026-08 携程真实 DOM 校准。

    结构：div.hotel-card > span.hotelName / div.room-info > div.room-name + div.room-price > .price-line > .sale
    .sale 是现价（span.sale，aria-label="Current price ¥302"）；.delete 是原价。
    """
    # 酒店名
    name_el = await card.query_selector(config.SELECTORS["hotel_name"])
    name = (await name_el.inner_text()).strip() if name_el else ""

    # 房型名（列表卡片通常展示一个推荐房型）
    room_el = await card.query_selector(config.SELECTORS["room_type"])
    room_type = (await room_el.inner_text()).strip() if room_el else ""

    # 现价：优先 span.sale；失败退到整条 price-line（从中正则取最末价格）
    price = None
    price_el = await card.query_selector(config.SELECTORS["hotel_price"])
    if price_el:
        price = clean_price(await price_el.inner_text())
    if price is None:
        line_el = await card.query_selector(config.SELECTORS["price_line"])
        if line_el:
            price = clean_price(await line_el.inner_text())

    # 兜底：class 全失效时，从整卡文本正则提取
    if not name or price is None:
        card_text = (await card.inner_text()) or ""
        lines = [ln.strip() for ln in card_text.splitlines() if ln.strip()]
        if not name and lines:
            name = lines[0]
        if price is None:
            for ln in lines:
                if "¥" in ln or "￥" in ln:
                    price = clean_price(ln)
                    if price is not None:
                        break
    if not room_type:
        try:
            card_text = (await card.inner_text()) or ""
            for ln in card_text.splitlines():
                ln = ln.strip()
                if any(k in ln for k in ("房", "床", "套")) and "¥" not in ln and 2 < len(ln) <= 40:
                    room_type = ln
                    break
        except Exception:
            pass

    name = re.sub(r"\s+", " ", name).strip()
    room_type = re.sub(r"\s+", " ", room_type).strip()[:80]
    return name, price, room_type


async def detect_captcha(page):
    """检测验证码/风控特征，命中返回 True。"""
    for sel in config.SELECTORS["captcha"]:
        try:
            if await page.query_selector(sel):
                return True
        except Exception:
            continue
    return False


async def scrape_city(page, city, check_in, check_out, max_hotels=None, progress=None, keyword=None,
                      full_rooms=None):
    """
    采集单个城市单个入住日期的酒店价格。
    keyword：可选酒店名关键词，传入后在页面搜索框输入并点击搜索，精确采集某家/某几家酒店。
    full_rooms：True 时进入详情页采集全部房型；False 仅采列表页首推房型。
    返回 (酒店数, 记录数, 是否被验证码拦截)。
    """
    max_hotels = max_hotels or config.HOTELS_PER_CITY
    full_rooms = config.COLLECT_ALL_ROOMS if full_rooms is None else full_rooms
    city_id = _get_city_id(city)
    url = config.CTRIP_LIST_URL.format(
        city_id=city_id, check_in=check_in, check_out=check_out,
    )
    progress = progress or (lambda *a, **k: None)

    label = f"[{city}{f'·{keyword}' if keyword else ''} {check_in}]"
    progress(f"{label} 打开列表页...")
    await page.goto(url, wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)
    # 页面 React 组件需要一点初始化时间，否则搜索框/按钮可能可见但事件未绑定
    await asyncio.sleep(2)

    # 登录态失效 / 未登录：被硬重定向到 passport 登录页
    if is_login_url(page.url):
        progress(f"{label} 需要登录（或登录态已失效），请先执行: python main.py login")
        return 0, 0, "login_required"

    # 若有关键词，在页面搜索框输入并点击「搜索」按钮
    if keyword:
        try:
            # 页面上有 2 个 input#destinationInput（sticky header + 主体搜索栏），
            # 必须选主体搜索栏（x 坐标较大、宽度较大），否则输入无效。
            inputs = page.locator(config.SELECTORS["search_input"])
            n = await inputs.count()
            search_input = None
            best_x = -1
            for i in range(n):
                el = inputs.nth(i)
                if not await el.is_visible():
                    continue
                box = await el.bounding_box()
                if box and box.get("x", 0) > best_x:
                    best_x = box["x"]
                    search_input = el

            search_btn = page.locator(config.SELECTORS["search_btn"]).first
            if search_input and await search_btn.is_visible():
                progress(f"{label} 搜索关键词：{keyword}")
                await search_input.scroll_into_view_if_needed()
                await search_input.click()
                await search_input.fill("")
                await search_input.type(keyword, delay=30)
                await asyncio.sleep(0.8)
                await search_btn.click()
                # 等待搜索结果加载（URL 出现 searchWord 或卡片刷新）
                await page.wait_for_timeout(3000)
                try:
                    await page.wait_for_selector(
                        config.SELECTORS["hotel_card"],
                        timeout=config.WAIT_SELECTOR_MS,
                    )
                except Exception:
                    pass
            else:
                progress(f"{label} 警告：未找到页面搜索框，将按城市列表采集")
        except Exception as e:
            progress(f"{label} 关键词搜索失败：{e}，将按城市列表采集")

    # 等待卡片出现或验证码
    try:
        await page.wait_for_selector(
            config.SELECTORS["hotel_card"],
            timeout=config.WAIT_SELECTOR_MS,
        )
    except Exception:
        if await detect_captcha(page):
            progress(f"{label} !! 触发验证码/风控，已停止（建议稍后再试）")
            return 0, 0, "captcha"
        # JS 重定向可能发生在等待期间，再次检测
        if is_login_url(page.url):
            progress(f"{label} 需要登录（或登录态已失效），请先执行: python main.py login")
            return 0, 0, "login_required"
        # 输出当前页面信息便于诊断
        try:
            info_title = (await page.title()) or "(无标题)"
            progress(f"{label} 当前页面：{page.url}")
            progress(f"{label} 页面标题：{info_title}")
        except Exception:
            pass
        # 保存页面快照，便于核对真实 DOM 修正选择器
        await _dump_page_html(
            page, config.BASE_DIR / "data" / f"debug_collect_{city}_{check_in}.html", progress
        )
        progress(f"{label} 未找到酒店卡片（可能无结果或页面结构变化）")
        return 0, 0, False

    # 懒加载滚动几次（每次滚动后统计卡片数，数量稳定即停止）
    prev_count = len(await page.query_selector_all(config.SELECTORS["hotel_card"]))
    for i in range(config.SCROLL_TIMES):
        await page.mouse.wheel(0, 3000)
        await asyncio.sleep(random.uniform(1.0, 1.8))
        cur_count = len(await page.query_selector_all(config.SELECTORS["hotel_card"]))
        if cur_count == prev_count and i >= 1:
            break  # 数量不再增长，说明已到底
        prev_count = cur_count

    cards = await page.query_selector_all(config.SELECTORS["hotel_card"])
    mode = "详情页全房型" if full_rooms else "列表页首推"
    progress(f"{label} 共 {len(cards)} 张酒店卡片（取前 {min(max_hotels, len(cards))} 家，{mode}）")

    # 先从列表页收集目标酒店，再逐个进详情（避免反复返回列表页）
    targets = []
    seen = set()
    for card in cards[:max_hotels]:
        try:
            hotel_id, name = await extract_card_meta(card)
            if not name:
                name, _, _ = await extract_card(card)
            if not name or name in seen:
                continue
            if keyword and keyword not in name:
                continue
            seen.add(name)
            targets.append({"hotel_id": hotel_id, "name": name, "card": card})
        except Exception:
            continue

    saved = 0
    for idx, target in enumerate(targets):
        name = target["name"]
        hotel_id = target["hotel_id"]
        rooms = []

        if full_rooms and hotel_id:
            blocked, rooms = await scrape_hotel_all_rooms(
                page, hotel_id, city_id, check_in, check_out, name, progress,
            )
            if blocked == "login_required":
                return len(seen), saved, "login_required"
            if blocked == "captcha":
                return len(seen), saved, "captcha"
            await asyncio.sleep(random.uniform(*config.DETAIL_DELAY_RANGE))
        elif full_rooms:
            progress(f"  警告：{name} 无 hotelId，退回列表页首推房型")
            try:
                _, price, room_type = await extract_card(target["card"])
            except Exception:
                price, room_type = None, ""
            if price is not None:
                rooms = [(room_type or "默认房型", price)]
            await asyncio.sleep(random.uniform(*config.ITEM_DELAY_RANGE))
        else:
            try:
                _, price, room_type = await extract_card(target["card"])
            except Exception:
                price, room_type = None, ""
            if price is not None:
                rooms = [(room_type or "默认房型", price)]
            await asyncio.sleep(random.uniform(*config.ITEM_DELAY_RANGE))

        if not rooms:
            progress(f"  ✗ {name} | 未采集到房型")
            continue

        for room_type, price in rooms:
            storage.upsert_price(city, name, check_in, room_type, price)
            saved += 1
        if len(rooms) == 1:
            rt, pr = rooms[0]
            progress(f"  ✓ {name} | {rt or '默认房型'} | ¥{pr}")
        else:
            prices = ", ".join(f"{rt} ¥{pr}" for rt, pr in rooms[:5])
            more = f" 等{len(rooms)}个房型" if len(rooms) > 5 else ""
            progress(f"  ✓ {name} | {len(rooms)} 个房型：{prices}{more}")

    return len(seen), saved, False


def _get_city_id(city):
    """返回城市对应的携程数字 cityId；未配置时报错提示补充。"""
    city_id = config.CITY_IDS.get(city)
    if city_id is None:
        raise ValueError(
            f"城市「{city}」的携程 cityId 未配置。"
            f"请在 config.CITY_IDS 中添加对应数字 ID 后重试。"
        )
    return city_id


def has_login_state():
    """是否存在已保存的携程登录态。"""
    return Path(config.LOGIN_STATE_PATH).exists()


def _load_profile():
    """读取登录时保存的浏览器指纹（UA/视口）；不存在返回 None。"""
    try:
        if PROFILE_PATH.exists():
            data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
            if data.get("user_agent"):
                return data
    except Exception:
        pass
    return None


def _save_profile(ctx_kwargs):
    """持久化浏览器指纹，与登录态文件配套使用。"""
    try:
        PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROFILE_PATH.write_text(
            json.dumps(
                {
                    "user_agent": ctx_kwargs.get("user_agent"),
                    "viewport": ctx_kwargs.get("viewport", {"width": 1920, "height": 1080}),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def _build_context_kwargs():
    """浏览器上下文参数：优先复用登录时的指纹，否则随机挑一个 UA。"""
    profile = _load_profile()
    if profile:
        return {
            "user_agent": profile["user_agent"],
            "viewport": profile.get("viewport", {"width": 1920, "height": 1080}),
            "locale": "zh-CN",
        }
    return {
        "user_agent": random.choice(config.USER_AGENTS),
        "viewport": {"width": 1920, "height": 1080},
        "locale": "zh-CN",
    }


def is_login_url(url):
    """硬判定：URL 被重定向到携程登录页。"""
    return "passport.ctrip.com" in url


async def is_login_redirected(page):
    """判断是否被重定向到携程登录页（URL 或页面内容双重判定）。"""
    if "passport.ctrip.com" in page.url:
        return True
    try:
        body = await page.inner_text("body", timeout=3000)
        title = await page.title() or ""
        keywords = ["账号密码登录", "手机号查单", "免费注册", "登录首页", "依据《网络安全法》", "请登录"]
        if any(k in title for k in ["登录", "Login"]):
            return True
        if body and any(k in body for k in keywords):
            return True
    except Exception:
        pass
    return False


async def _has_login_cookie(context):
    """检查 context 中是否出现携程登录标志 cookie。"""
    try:
        cookies = await context.cookies()
    except Exception:
        return False
    names = {c["name"] for c in cookies}
    # 携程 SSO 登录成功后种下的 cookie（任一命中即视为已登录）
    markers = {"login_uid", "IsLogged", "ibkuid", "login_type", "ticket"}
    return bool(names & markers)


async def _dump_page_html(page, path, progress=None):
    """保存当前页面 HTML 供选择器诊断。"""
    try:
        html = await page.content()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")
        if progress:
            progress(f"已保存页面快照供诊断：{p.name}（{len(html) // 1024}KB）")
    except Exception as e:
        if progress:
            progress(f"页面快照保存失败：{e}")


async def login_and_save_state(progress=None):
    """
    有头模式打开携程酒店列表页，等待用户手动登录（扫码/手机验证码），
    检测到登录成功后保存 storage state 到 config.LOGIN_STATE_PATH。

    登录成功判定（任一满足）：
    1. 出现携程登录标志 cookie（login_uid / IsLogged 等）
    2. 连续 2 次轮询（约 6s）都不在登录页 —— 覆盖 cookie 名变化的场景
    不依赖页面元素选择器，避免携程 DOM 改版导致检测失效。
    """
    progress = progress or (lambda *a, **k: None)
    import datetime as _dt

    check_in = (_dt.date.today() + _dt.timedelta(days=1)).isoformat()
    check_out = (_dt.date.today() + _dt.timedelta(days=2)).isoformat()
    url = config.CTRIP_LIST_URL.format(
        city_id=_get_city_id(config.CITIES[0]),
        check_in=check_in,
        check_out=check_out,
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=LAUNCH_ARGS)
        ctx_kwargs = _build_context_kwargs()
        context = await browser.new_context(**ctx_kwargs)
        page = await context.new_page()

        progress("打开携程酒店列表页（会自动跳转登录）...")
        progress("请在弹出的浏览器窗口完成登录：扫码 或 手机验证码")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT_MS)
        except Exception as e:
            progress(f"页面打开失败：{e}")
            await browser.close()
            return False

        waited = 0
        off_login_streak = 0
        logged_in = False
        while waited < config.LOGIN_MAX_WAIT:
            await asyncio.sleep(config.LOGIN_POLL_INTERVAL)
            waited += config.LOGIN_POLL_INTERVAL
            try:
                # URL 硬判定（不查页面内容，避免列表页弹窗含"登录"字样造成误判）
                on_login_page = is_login_url(page.url)
                cookie_ok = await _has_login_cookie(context)
            except Exception:
                # 用户手动关闭了浏览器窗口
                progress("检测到浏览器窗口被关闭，登录流程中止。")
                await browser.close()
                return False

            if on_login_page:
                off_login_streak = 0
            else:
                off_login_streak += 1

            if cookie_ok or off_login_streak >= 2:
                logged_in = True
                break

            if waited % 30 == 0:
                progress(f"等待登录中... 已等 {waited}s / {config.LOGIN_MAX_WAIT}s")

        if not logged_in:
            progress("登录超时，未检测到成功登录。请重试。")
            await browser.close()
            return False

        # 登录后停留的页面（通常是酒店列表页）保存快照，供选择器核对
        await _dump_page_html(
            page, config.BASE_DIR / "data" / "debug_list_page.html", progress
        )

        state_path = Path(config.LOGIN_STATE_PATH)
        state_path.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(state_path))
        _save_profile(ctx_kwargs)  # 指纹与登录态配套保存，采集时复用同一 UA
        progress("登录成功，登录态已保存，正在关闭浏览器...")
        await browser.close()
        progress("完成。之后采集会自动复用该登录态（无需再登录）。")
        return True


async def scrape_city_async(city, check_in, check_out, headless=True, max_hotels=None, progress=None,
                            keyword=None, full_rooms=None):
    """独立浏览器会话采集一个城市（每次调用新会话，避免状态累积）。
    keyword：可选酒店名关键词，按关键词搜索。
    若存在登录态则自动复用；被重定向到登录页时返回 (0, 0, 'login_required')。
    安全网：会话结束时若检测到登录 cookie（例如用户在有头采集途中手动登录了），
    自动保存登录态，避免重复登录。
    """
    progress = progress or (lambda *a, **k: None)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=LAUNCH_ARGS)
        ctx_kwargs = _build_context_kwargs()
        if has_login_state():
            ctx_kwargs["storage_state"] = str(config.LOGIN_STATE_PATH)
        context = await browser.new_context(**ctx_kwargs)
        page = await context.new_page()
        try:
            n_hotels, n_records, blocked = await scrape_city(
                page, city, check_in, check_out, max_hotels, progress,
                keyword=keyword, full_rooms=full_rooms,
            )
            if blocked == "login_required":
                return 0, 0, "login_required"
            status = "blocked" if blocked else ("ok" if n_hotels else "failed")
            storage.mark_progress(city, check_in, status, n_records)
            return n_hotels, n_records, blocked
        finally:
            # 安全网：会话内出现过登录 cookie 就持久化（覆盖旧文件 = 刷新有效期）
            try:
                if await _has_login_cookie(context):
                    state_path = Path(config.LOGIN_STATE_PATH)
                    state_path.parent.mkdir(parents=True, exist_ok=True)
                    await context.storage_state(path=str(state_path))
                    _save_profile(ctx_kwargs)
                    progress("（已自动保存/刷新登录态）")
            except Exception:
                pass
            await browser.close()


def collect_city(city, check_in, check_out, headless=True, max_hotels=None, progress=None, keyword=None,
                 full_rooms=None):
    """同步入口（供 CLI 调用）。"""
    return asyncio.run(
        scrape_city_async(
            city, check_in, check_out, headless, max_hotels, progress,
            keyword=keyword, full_rooms=full_rooms,
        )
    )
