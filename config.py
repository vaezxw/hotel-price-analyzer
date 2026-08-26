# -*- coding: utf-8 -*-
"""
全局配置：城市、采集参数、路径。
按需修改这里，无需改其他代码。
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# ------------------------------------------------------------------
# 城市配置（携程列表页按城市名搜索）
# ------------------------------------------------------------------
CITIES = [
    "上海",
    "北京",
    "广州",
    "深圳",
    "成都",
    "杭州",
    "三亚",
]

# 携程城市数字 ID（列表页 URL 需要 cityId，cityName 已不被识别）
# 未知城市可在首次使用时通过页面搜索框反向解析并补充到这里。
CITY_IDS = {
    "北京": 1,
    "上海": 2,
    "深圳": 30,
    "广州": 32,
    "杭州": 17,
    "三亚": 43,
    "成都": 28,
}

# 每个城市列表页最多采集前 N 家酒店
HOTELS_PER_CITY = 20

# ------------------------------------------------------------------
# 房型采集模式
# ------------------------------------------------------------------
# True：进入酒店详情页采集全部可售房型（较慢，数据完整）
# False：仅采列表页卡片上展示的首个推荐房型（较快）
COLLECT_ALL_ROOMS = True

# 详情页最多保留房型数（防止异常页面无限膨胀）
MAX_ROOMS_PER_HOTEL = 80

# 详情页 URL（hotelId / cityId / 入住退房日期）
HOTEL_DETAIL_URL = (
    "https://hotels.ctrip.com/hotels/detail/"
    "?hotelId={hotel_id}&checkIn={check_in}&checkOut={check_out}"
    "&cityId={city_id}&adult=1&children=0&crn=1"
)

# 详情页滚动次数（懒加载更多房型）
DETAIL_SCROLL_TIMES = 6

# 每家酒店详情页之间的随机延迟（秒，请勿调太低）
DETAIL_DELAY_RANGE = (3, 6)

# ------------------------------------------------------------------
# 采集行为参数（反爬人性化，请勿调太低）
# ------------------------------------------------------------------
REQUEST_DELAY_RANGE = (5, 10)      # 每次翻页/换城市之间的随机延迟（秒）
ITEM_DELAY_RANGE = (0.5, 2.0)      # 单张酒店卡片解析后的随机延迟（秒）
PAGE_TIMEOUT_MS = 30000            # 页面加载超时（毫秒）
WAIT_SELECTOR_MS = 15000           # 等待酒店卡片出现的最长等待（毫秒）

# 可用 User-Agent 池，随机轮换
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]

# ------------------------------------------------------------------
# 存储与输出路径
# ------------------------------------------------------------------
DB_PATH = BASE_DIR / "data" / "hotel_prices.db"
OUTPUT_DIR = BASE_DIR / "输出"
# 所有 Excel 导出统一放在 输出/excel/YYYY-MM-DD/ 下
OUTPUT_EXCEL_DIR = OUTPUT_DIR / "excel"

# 携程登录态存储文件（首次 python main.py login 生成）
LOGIN_STATE_PATH = BASE_DIR / "data" / "ctrip_state.json"

# 登录等待：最多等多久用户完成登录（秒）
LOGIN_MAX_WAIT = 300
# 登录检测轮询间隔（秒）
LOGIN_POLL_INTERVAL = 3

# 无上下文时的默认导出文件名（strftime 可用）
EXPORT_FILENAME_TEMPLATE = "hotel_prices_{date}.xlsx"

# ------------------------------------------------------------------
# 携程列表页 URL 模板
# 必须使用数字 cityId（cityName 参数已不被识别，会返回全国推荐列表）。
# 注意：2025 年起携程酒店列表页强制登录（匿名访问重定向到 passport），
# 需先执行 python main.py login 保存登录态。
# ------------------------------------------------------------------
CTRIP_LIST_URL = (
    "https://hotels.ctrip.com/hotels/list"
    "?countryId=1&city={city_id}&checkIn={check_in}&checkOut={check_out}"
)

# ------------------------------------------------------------------
# 页面元素选择器（已按 2026-08 携程真实 DOM 校准，改版时只需改这里）
# 结构：div.hotel-card > span.hotelName / div.room-info > div.room-name + div.room-price > .price-line > .sale
# ------------------------------------------------------------------
SELECTORS = {
    "hotel_card": ".hotel-card",                            # 酒店卡片容器
    "hotel_name": ".hotelName",                             # 酒店名（span）
    "hotel_price": ".room-price .price-line .sale",         # 现价（span.sale，如 ¥302）
    "price_line": ".room-price .price-line",                # 价格行兜底（含原价+现价）
    "room_type": ".room-name",                              # 房型名
    "search_input": "input#destinationInput:visible",       # 顶部搜索框（位置/品牌/酒店）
    "search_btn": 'button.tripui-online-btn-solid-primary:has-text("搜索")',  # 搜索按钮
    "captcha": [                                            # 验证码/风控特征（任一命中即视为被拦）
        ".captcha-container",
        "#slide-verify",
        "text=拖动滑块",
        "text=安全验证",
    ],
    "no_result": "text=没有找到相关酒店",
    # 详情页房型块（2026-08 详情页：commonRoomCard + saleRoomItemBox）
    "detail_room_block": '[class*="commonRoomCard__"], [class*="saleRoomItemBox__"]',
    "detail_room_name": '[class*="commonRoomCard-title"], .room-name',
    "detail_room_price": '[aria-label*="Current price"], .sale',
}

# 每个城市列表页需要滚动的次数（页面懒加载更多酒店）
SCROLL_TIMES = 5
