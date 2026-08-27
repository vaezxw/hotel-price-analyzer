# 酒店房价采集与分析工具

个人非商用工具：采集指定城市/酒店的房价，积累时间序列数据，生成 **Excel 表格 + 价格趋势图 + 波动率统计**，用于了解市场波动与数据分析。

## 功能

- **采集**：Playwright 访问列表页定位酒店，**默认进入详情页采集全部可售房型**（也可 `--list-only` 仅采列表首推）
- **存储**：SQLite 落库，重复采集同一酒店同一日期自动更新价格（时间序列累积）
- **分析**：城市×日期 均值/中位数/极值、标准差、变异系数（波动率）、环比变化
- **导出**：Excel 四个 Sheet —— 明细数据 / 城市汇总 / 价格趋势折线图 / 波动率排行

## 重要：首次使用必须先登录

2025 年起，酒店列表页对**匿名访问强制重定向到登录页**（桌面端和移动端都会拦截）。本工具因此采用「登录态持久化」方案：

1. 你用自己的账号登录一次
2. 工具自动保存登录态到 `data/ctrip_state.json`
3. 后续 `collect` / `collect-all` / `run` 都会自动复用该状态，无需重复登录

```bash
python main.py login
```

执行后：
- 会弹出真实的 Chrome 浏览器窗口
- 请在窗口内完成登录：扫码 或 手机验证码
- 登录成功后工具会自动关闭窗口并保存状态
- 登录态默认 7-30 天内有效（取决于网站策略），失效时重新执行即可

## 给朋友用（开箱包）

**图形界面（推荐）：**

1. 解压 → 双击 `一键安装.bat` → 双击 `启动GUI.bat`
2. 首次点击「登录」，扫码登录
3. 填城市/日期 → 点「一条龙」

**或 exe 版（无需 Python）：**

1. 本机运行 `build_exe.bat` 生成 `dist/hotel-analyzer/`
2. 将整个文件夹 zip 发给用户，解压后双击 `hotel-analyzer.exe`

**源码分享包：**

1. 双击 **`打包.bat`**（或 `python pack_share.py`）→ 生成 `hotel-price-analyzer-分享包`
2. zip 发送（**不要**附带 `data/ctrip_state.json`）

## 环境准备

**Windows 推荐（双击）：**

1. 双击 `一键安装.bat`（自动装依赖 + Chromium）
2. 双击 `启动.bat`（进入菜单）

**命令行：**

```bash
# 安装依赖（已使用清华镜像加速）
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
playwright install chromium
```

## 使用方法

```bash
# 1. 首次登录（必须）
python main.py login

# 2. 采集单个城市单个入住日期（核心命令）
python main.py collect --city 上海 --date 2026-09-01

# 2b. 采集单个城市自定义日期范围（逐日采集该范围内房价）
python main.py collect --city 上海 --start 2026-09-01 --end 2026-09-07

# 3. 批量采集：多个城市 × 日期范围（城市列表见 config.py）
python main.py collect-all --start 2026-09-01 --end 2026-09-07

# 3b. 批量采集：单个城市 × 日期范围
python main.py collect-all --city 上海 --start 2026-09-01 --end 2026-09-07

# 4. 统计分析库内数据
python main.py analyze

# 5. 导出 Excel（含趋势图和波动率排行，保存到 输出/excel/日期/）
python main.py export

# 5b. 自定义文件名（仍保存到 输出/excel/今天/）
python main.py export --output 我的报告.xlsx

# 6. 一条龙：采集 + 分析 + 导出（支持日期范围）
python main.py run --city 上海 --start 2026-09-01 --end 2026-09-07
python main.py run --city 上海 --date 2026-09-01
```

常用参数：

| 参数 | 说明 |
|------|------|
| `--debug` | 有头模式运行（调试 / 手动过验证码） |
| `--date` | 单个入住日期（与 `--start`/`--end` 二选一） |
| `--start` / `--end` | 自定义入住日期范围；`--end` 缺省时等于 `--start` |
| `--force` | 强制重采（默认已采集过的日期跳过） |
| `--city` | 指定城市（`collect-all` 缺省为配置全部城市） |
| `--keyword` | 酒店名关键词（按名称精确采集某家/某几家酒店） |
| `--list-only` | 仅采列表页首推房型（更快；默认进详情页采全部房型） |

## 配置文件 `config.py`

| 配置项 | 说明 |
|--------|------|
| `CITIES` | 采集城市列表（默认：上海/北京/广州/深圳/成都/杭州/三亚） |
| `HOTELS_PER_CITY` | 每城最多采集前 N 家酒店 |
| `COLLECT_ALL_ROOMS` | 默认 `True`：进详情页采全部房型；改 `False` 则仅采列表首推 |
| `MAX_ROOMS_PER_HOTEL` | 单酒店最多保留房型数（防止异常页面膨胀） |
| `DETAIL_DELAY_RANGE` | 详情页之间的随机延迟（秒） |
| `REQUEST_DELAY_RANGE` | 请求间随机延迟（秒），反爬人性化 |
| `SELECTORS` | 列表页/详情页元素选择器，网站改版时改这里 |

## 导出目录

所有 Excel 报告统一保存在：

```
输出/
  excel/
    2026-08-26/
      上海_xxxxxxxxxxxxx酒店_20260827-20260831_143015.xlsx
      hotel_prices_20260826_150030.xlsx
    2026-08-27/
      ...
```

- **一条龙 / 带城市与日期范围的导出**：按 `城市_关键词_入住日期范围_时间.xlsx` 自动命名
- **仅导出**：自动命名或 `--output 文件名.xlsx`，均放入 `输出/excel/当天日期/`
- 数据库仍在 `data/hotel_prices.db`

## 数据说明

- 登录后采集**公开列表价格**，不采会员价、不使用优惠券价
- **可采集今天及以后入住日**；昨天及更早会被自动跳过
- 数据从首次运行日起累积：隔几天跑一次，时间序列越丰富，波动分析越准
- 数据库文件：`data/hotel_prices.db`，重复运行 upsert 更新，不会重复堆积

## 注意事项

1. **合规**：数据仅个人分析使用，请勿二次分发或对外展示
2. **频率**：默认 5-10 秒随机延迟，请勿调太低，避免给目标站点造成压力
3. **验证码**：登录态失效或触发风控时，工具会停止并提示，重新 `login` 或稍后再试
4. **页面改版**：若提取不到数据，检查 `config.py` 的 `SELECTORS`，必要时用 `--debug` 观察页面结构
5. **登录态**：`data/ctrip_state.json` 包含你的登录 cookies，请勿上传或共享
