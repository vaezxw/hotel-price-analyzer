# GitHub 发布文案（最新版）

> 复制到仓库 About / Release / README 即可使用。

---

## 1. 仓库 About（短简介，建议粘贴到 Description）

```
个人非商用：采集酒店房价时间序列，生成分析 Excel + 业务汇总矩阵表。支持 GUI / CLI / 可打包 exe。
```

**Website**：可留空，或填你的 Release 页  
**Topics 建议**：`hotel` `price-analysis` `excel` `playwright` `sqlite` `python` `desktop-gui` `customtkinter`

---

## 2. Release 标题（示例）

```
v1.1.0 — GUI 启动优化 · 业务汇总表 · 双文件导出
```

---

## 3. Release 正文（可直接粘贴）

### 酒店房价采集与分析工具 · 最新版

个人学习 / 数据分析用的 Windows 工具：按城市或指定酒店采集可订房价，写入本地 SQLite，并导出两份 Excel：

1. **分析表**：明细、城市汇总、价格趋势图、波动率排行  
2. **业务汇总表**：按「酒店 × 房型 × 入住日 × 采集时段（10:00 / 14:00 / 18:00 / 22:00）」矩阵排版；**综合门市价 = 当日均价**；流量与红色标记留空，供人工填写

原有分析导出逻辑保留，业务汇总为**额外单独文件**（文件名带 `_业务汇总`）。

#### 主要能力

- 图形界面（CustomTkinter）：登录、一条龙、采集、分析、导出、打开导出目录  
- 多酒店一次采集（指定酒店名，一行一个）  
- 日期范围采集（仅今天及以后可订日）  
- 登录态本地保存，避免每次扫码  
- 四档采集时段入库，支持同日多次采集覆盖对应时段  
- 源码运行 / 分享包 / PyInstaller exe 打包

#### 谁适合用

- 需要自己积累房价时间序列、做简单波动与对比的个人用户  
- 需要按业务模板整理「按日均价矩阵表」的分析场景  

#### 不适合

- 商用、批量贩卖数据、未授权对外传播  
- 需要回填「昨天及更早」历史房价（网站侧不可订则无法采集）

#### 快速开始

**源码 / 分享包**

1. 安装依赖：`一键安装.bat` 或 `pip install -r requirements.txt` + `playwright install chromium`  
2. 启动界面：双击 **`启动GUI.vbs`**（无黑框；`启动GUI.bat` 仅作转发）  
3. 勾选免责声明 → **登录** → 填城市/酒店/日期 → **一条龙**

**exe 包**

1. 解压后双击 `hotel-analyzer.exe`（或包内启动脚本）  
2. 同样先登录，再一条龙  

导出目录：`输出/excel/当天日期/`

#### 合规提醒

- 请使用**你自己的**账号登录；不要分享 `data` 下的登录态文件  
- 仅供个人学习与数据分析，禁止商用  
- 请保持默认采集间隔，勿高频、大批量抓取  

#### 资源

- 使用说明见仓库 / 包内 `说明.txt`、`README.md`  
- 若 GUI 异常退出，可查看 `data/gui_crash.log`

---

## 4. README 顶部「一句话 + 徽章位」可选替换段

````markdown
# 酒店房价采集与分析工具

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)]()
[![License](https://img.shields.io/badge/License-Personal%20Use-orange.svg)]()

个人非商用工具：用 Playwright 采集指定城市 / 酒店的可订房价，SQLite 累积时间序列，一键导出 **分析 Excel** 与 **业务汇总矩阵表**（酒店×房型×日期×时段；综合门市价为每日均价）。

提供 **桌面 GUI**、**命令行**，以及可打包的 **exe 分发包**。
````

---

## 5. 本版相对要点（写在 Release「What's Changed」）

- 新增业务汇总 Excel（模板化矩阵；流量 / 标红人工填写）  
- 导出同时生成分析表 + 业务汇总表  
- 数据库支持 `time_slot` 四档时段  
- GUI：任务栏图标、静默启动（`启动GUI.vbs`）、修复启动卡死 / 闪退  
- 多酒店指定采集、免责声明锁定功能  

---

## 6. 发布检查清单（给你自己用）

- [ ] 不要把 `data/*state*.json`、含账号的浏览器配置打进公开包  
- [ ] 不要提交 `输出/` 下个人 Excel、`__pycache__`、本地 `hotel_prices.db`（若含隐私）  
- [ ] Release 附件命名示例：`hotel-price-analyzer-win64-v1.1.0.zip`  
- [ ] 包内附带最新 `说明.txt`
