# 📊 多市场订单簿重构工具

> Python Web 服务版 · 双击 `start.bat` 即用 · 支持实时行情接入

一款面向金融量化研究的订单簿重构与分析工具，支持 A股、美股、港股、期货、加密货币全品类数据。前端为纯 HTML5 + 原生 JavaScript，后端为 FastAPI Python 服务，提供实时行情 WebSocket 推送。

---

## ✨ 功能亮点

| 功能 | 说明 |
|------|------|
| 🗂️ TBT 逐笔数据解析 | 兼容深交所 Level2 TBT CSV 格式，支持 order/trade 全事件类型 |
| 📈 订单簿重构 | 精确维护买卖盘 Map，正确处理新增/撤单/成交，生成任意时刻盘口快照 |
| 🎞️ 回放 + 进度条 | 按时间戳分帧回放，支持拖拽跳转任意位置，前跳/后跳均可，倍速可调 |
| 📊 时序CSV导出 | 重构完成后自动生成全交易时段时序数据，每帧一行（宽表格式），一键导出 |
| 🕐 交易时段感知 | 自动识别各市场交易时段（A股集合竞价、连续竞价等），彩色标签实时标注 |
| 📡 实时行情接入 | WebSocket / HTTP轮询 + Python本地服务三种模式，内置主流交易所预设 |
| 🐍 Python 行情服务 | FastAPI 后端，ccxt.pro 接入 150+ 加密货币交易所，支持单交易所与多交易所聚合 |
| 🧹 数据清洗 | 合并同价档位、异常价过滤、crossed-book 保护、涨跌停上下限识别 |
| 📉 盘口深度图 | Chart.js 渲染买卖盘累计深度曲线（阶梯图），实时同步更新 |
| 💾 多格式导出 | JSON快照 / CSV快照 / 时序CSV，所有数据在本地处理，不上传 |
| ✏️ 手动编辑 | 可直接在表格中修改价格/数量，实时重算统计指标 |

---

## 🚀 快速开始

### 方式一：Python Web 服务（推荐，支持实时行情）

**环境要求：Python 3.9+**

```bash
# Windows
双击 start.bat

# Linux / macOS
chmod +x start.sh && ./start.sh
```

`start.bat` 会自动安装依赖并启动服务，浏览器自动打开 `http://localhost:8765`。

### 方式二：纯静态（无实时行情）

```
直接双击 orderbook-tool.html 用浏览器打开
```

TBT解析、订单簿重构、文件导入导出、回放等功能在纯静态模式下均可用。实时Python行情服务不可用。

---

## 📁 项目结构

```
.
├── orderbook-tool.html      # 前端页面（含全部UI逻辑，纯静态可独立运行）
├── server.py                # FastAPI 后端（提供HTTP页面 + WebSocket行情推送）
├── start.bat                # Windows 一键启动脚本
├── start.sh                 # Linux/macOS 启动脚本
├── requirements.txt         # Python 依赖
└── adapters/
    ├── base.py              # 适配器抽象基类
    ├── crypto.py            # 加密货币（ccxt.pro，单所/多所聚合）
    ├── ashare.py            # A股（xtquant/QMT Level2）
    ├── us.py                # 美股（Alpaca / Interactive Brokers）
    ├── hk.py                # 港股（富途 OpenAPI）
    └── futures.py           # 期货（openctp/CTP MdApi）
```

---

## 📋 支持的数据格式

### TBT 逐笔委托 CSV（A股 Level2）

深交所标准逐笔格式：

```
type,clock,clock_int,symbol,entrust_volume,entrust_dir,entrust_orderType,
entrust_orderStatus,entrust_price,entrust_orderNum,...,
transaction_volume,transaction_buyNum,transaction_sellNum,...
```

| 字段 | 说明 |
|------|------|
| `type` | `order`（委托）/ `trade`（成交） |
| `entrust_dir` | `1` = 买，`2` = 卖 |
| `entrust_orderStatus` | `0` = 新增，`1` = 撤销 |
| `clock_int` | 9位整数，格式 `HHMMSSMMM` |

### 标准 JSON 快照

```json
{ "bids": [[10.00, 1000], [9.99, 2000]], "asks": [[10.01, 800]] }
```

### Binance / OKX WebSocket 格式

直接粘贴或通过预设一键填充接口地址，工具自动适配各格式。

---

## 🌐 支持市场与交易时段

| 市场 | 时段规则 |
|------|---------|
| **A股** | 集中竞价 09:15–09:25 → 集合竞价 09:25–09:30 → 连续竞价 09:30–11:30 / 13:00–14:57 → 收盘竞价 14:57–15:00 |
| **美股** | 盘前 04:00–09:30 → 正常交易 09:30–16:00 → 盘后 16:00–20:00 |
| **港股** | 开盘竞价 09:00–09:30 → 持续交易 09:30–12:00 / 13:00–16:00 → 收市竞价 16:00–16:10 |
| **期货** | 夜盘 21:00–02:30 → 日盘① 09:00–10:15 → 日盘② 10:30–11:30 → 日盘③ 13:30–15:00 |
| **加密货币** | 全天 24h 不间断 |

---

## 📡 实时数据接入

### 模式一：浏览器直连 WebSocket

内置预设，在"实时数据接口"面板选择预设后一键填充：

| 交易所 | 品种示例 |
|--------|---------|
| Binance 现货 | BTC/USDT、ETH/USDT、BNB/USDT（20档） |
| Binance U本位合约 | BTC、ETH |
| OKX 现货 | BTC-USDT、ETH-USDT（5档/400档） |
| Bybit 现货 | BTC/USDT、ETH/USDT |

> **注意：** 海外 IP 可直连上述接口。国内 IP 访问 Binance 需代理。

### 模式二：Python 本地服务（推荐用于量化研究）

启动 `start.bat` 后，在页面"实时数据接口"面板选择 **🐍 本地Python服务**：

**加密货币（无需账号，公开行情）：**
- 支持 10 个主流交易所：Binance、OKX、Bybit、Coinbase、Kraken、Gate、KuCoin、MEXC、HTX、Bitget
- **单交易所模式**：订阅指定交易所的实时订单簿
- **多所聚合模式**：同时订阅多个交易所，按价位合并为聚合订单簿

**传统市场（需对应券商账号/SDK）：**

| 市场 | 依赖 | 说明 |
|------|------|------|
| A股 Level2 | xtquant（迅投QMT）| 需安装 QMT 客户端 |
| 美股 | alpaca-py 或 ib_insync | Alpaca 免费账号可用；IBKR 需本地运行 TWS |
| 港股 | futu-api | 需本地运行 FutuOpenD |
| 期货 | openctp-ctp | 支持仿真环境测试 |

安装可选依赖：

```bash
# A股
pip install xtquant          # 需先安装 QMT 客户端

# 美股
pip install alpaca-py        # 或 ib_insync

# 港股
pip install futu-api

# 期货
pip install openctp-ctp
```

---

## 📊 时序CSV 导出格式

导入 TBT 文件点击"重构"后，工具自动遍历全部时间戳生成时序数据。点击"↓ 时序CSV"导出：

```
timestamp,bid1_p,bid1_q,bid2_p,bid2_q,...,ask1_p,ask1_q,ask2_p,ask2_q,...
09:15:00.000,10.05,5000,10.04,3200,...,10.06,2800,10.07,1500,...
09:15:00.100,10.05,4800,10.04,3200,...,10.06,3100,10.07,1500,...
...
```

每行代表一个时刻的完整盘口快照，适合后续量化回测使用。

---

## 🛠️ 技术栈

| 层 | 技术 |
|----|------|
| 前端结构 | HTML5 |
| 前端逻辑 | 原生 JavaScript（无框架） |
| 前端样式 | Tailwind CSS（CDN） |
| 图表 | Chart.js 4.x（CDN） |
| 后端服务 | Python 3.9+ / FastAPI / uvicorn |
| 实时行情 | ccxt.pro（WebSocket，支持 150+ 交易所） |

---

## ⚙️ 核心模块说明

### 前端（orderbook-tool.html）

```
MarketConfig      — 五市场配置（Tick大小、价格精度、涨跌停比例等）
TradingSessions   — 各市场交易时段定义与当前时段识别
TBTParser         — TBT CSV 解析、订单簿重构引擎、时序快照生成、回放分组
DataCleaner       — 清洗、crossed-book保护、档位过滤、统计计算
OrderBookRenderer — 买卖盘表格渲染（数量背景条可视化）
ChartRenderer     — Chart.js 深度图渲染
RealtimeAPI       — WebSocket / HTTP轮询 / Python服务 / TBT回放 / Seek跳转
Exporter          — JSON快照 / CSV快照 / 时序CSV 三种导出格式
App               — 主控制器，绑定所有 UI 事件
```

### 后端（server.py + adapters/）

```
server.py         — FastAPI 应用，GET / 提供页面，WS /ws 推送行情，GET /api/status 状态
adapters/base.py  — BaseAdapter 抽象类（connect/disconnect/_run_loop/_emit）
adapters/crypto   — ccxt.pro 单交易所 + 多交易所聚合
adapters/ashare   — QMT/xtquant A股 Level2
adapters/us       — Alpaca / Interactive Brokers 美股
adapters/hk       — 富途 OpenAPI 港股
adapters/futures  — openctp/CTP 期货
```

---

## 📸 界面说明

- **左侧面板**：市场 Tab 切换、模拟数据生成、本地文件导入（JSON/TBT CSV）、JSON 粘贴、手动编辑
- **中部**：Chart.js 买卖盘累计深度阶梯曲线
- **右侧**：订单簿双边表格（含数量背景条、统计区域）
- **导出栏**：↓ JSON / ↓ CSV快照 / ↓ 时序CSV
- **TBT 面板**：重构按钮 + 进度条 + 回放控制台（进度拖拽 / 倍速 / 时段标签）
- **实时API面板**：WebSocket / HTTP轮询 / 🐍 Python服务，内置交易所预设

---

## 📝 开发说明

- TBT 大文件采用分批异步处理（每批 8000 行 yield），避免 UI 冻结
- 时序生成每 500 帧 yield 一次，全量遍历不阻塞页面
- 回放引擎基于 `setTimeout` 调度，支持暂停/继续/Seek跳转
- 适配器导入采用 `try/except`，缺失可选依赖不影响其他市场功能
- WebSocket 标准快照格式：`{market, symbol, bids:[[p,q],...], asks:[[p,q],...], ts}`

---

## 📄 License

MIT License — 自由使用、修改、分发，保留出处即可。
