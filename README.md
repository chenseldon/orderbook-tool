# 📊 多市场订单簿重构工具

> 纯前端单文件工具 · 双击即用 · 零安装 · 零后端

一款基于纯 HTML5 + 原生 JavaScript 构建的金融量化工具，支持 A股、美股、港股、期货、加密货币全品类订单簿数据的本地化重构、可视化与回放分析。

---

## ✨ 功能亮点

| 功能 | 说明 |
|------|------|
| 🗂️ TBT 逐笔数据解析 | 兼容深交所 Level2 TBT CSV 格式，支持 order/trade/cancel 全事件类型 |
| 📈 订单簿重构 | 精确维护买卖盘 Map，正确处理新增/撤单/成交，生成任意时刻快照 |
| 🎞️ 回放 + 进度条 | 按时间戳分帧回放，支持拖拽进度条跳转任意位置，前跳/后跳均可 |
| 🕐 交易时段感知 | 自动识别 A股集合竞价 / 连续竞价 / 收盘竞价等时段，彩色标签实时显示 |
| 📡 实时 API 接入 | WebSocket / HTTP 轮询双模式，内置 Binance / OKX 交易所预设，一键填充 |
| 🧹 数据清洗 | 合并同价档位、异常价过滤、crossed-book 保护、涨跌停上下限识别 |
| 📉 盘口深度图 | Chart.js 渲染买卖盘累计深度曲线（阶梯图），实时同步更新 |
| 💾 导入 / 导出 | 支持 JSON / CSV 导入导出，所有计算在浏览器本地完成，数据不上传 |
| ✏️ 手动编辑 | 可直接在表格中修改价格/数量，实时重算统计指标 |

---

## 🚀 快速开始

**无需安装，无需服务器。**

```
下载 orderbook-tool.html
双击用浏览器打开
```

推荐浏览器：Chrome / Edge（最新版）

---

## 📁 项目结构

```
.
├── orderbook-tool.html      # 完整工具（单文件，即开即用）
└── TBT_300308_20251231.csv  # 示例数据（深交所 300308 逐笔委托，可选）
```

---

## 📋 支持的数据格式

### 1. TBT 逐笔委托 CSV（A股 Level2）

深交所标准逐笔格式，字段示例：

```
type,clock,clock_int,symbol,entrust_volume,entrust_dir,entrust_orderType,
entrust_orderStatus,entrust_price,entrust_orderNum,...,
transaction_volume,transaction_buyNum,transaction_sellNum,...
```

- `type`：`order`（委托）/ `trade`（成交）
- `entrust_dir`：`1` = 买，`2` = 卖
- `entrust_orderStatus`：`0` = 新增，`1` = 撤销
- `clock_int`：9位整数，格式 `HHMMSSMMM`

### 2. 标准 JSON 快照

```json
{
  "bids": [[10.00, 1000], [9.99, 2000]],
  "asks": [[10.01, 800], [10.02, 1500]]
}
```

### 3. Binance 深度格式

```json
{
  "bids": [["43250.50", "0.245"]],
  "asks": [["43251.00", "0.180"]]
}
```

### 4. OKX Books 频道格式

```json
{
  "data": [{"bids": [["43250.5", "0.245", "0", "1"]], "asks": [...]}]
}
```

### 5. 增量更新（Delta）

```json
{
  "bids": [[10.00, 1500], [9.98, 0]],
  "asks": [[10.01, 0], [10.02, 900]]
}
```

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

### 加密货币（浏览器直连）

| 交易所 | 说明 |
|--------|------|
| Binance 现货 | `wss://stream.binance.com:9443/ws/btcusdt@depth20@100ms` |
| Binance 合约 | `wss://fstream.binance.com/ws/btcusdt@depth20@100ms` |
| OKX 现货 | `wss://ws.okx.com:8443/ws/v5/public`，自动发送订阅报文 |

### A股 / 期货 / 美股 / 港股

需在本地部署行情转发服务（CTP / QMT / Alpaca / Futu），将数据转为标准 JSON 格式后通过 HTTP 或 WebSocket 推送至工具。

---

## 🛠️ 技术栈

| 层 | 技术 |
|----|------|
| 结构 | HTML5 |
| 逻辑 | 原生 JavaScript（无任何框架依赖） |
| 样式 | Tailwind CSS（CDN） |
| 图表 | Chart.js 4.x（CDN） |

全部通过 CDN 引入，本地**零安装**，断网环境下需手动替换为本地资源。

---

## ⚙️ 核心模块说明

```
MarketConfig      — 五市场配置（Tick大小、价格精度、涨跌停比例等）
TradingSessions   — 各市场交易时段定义与当前时段识别
MarketAPIPresets  — 交易所 API 预设（Binance / OKX 等）
TBTParser         — TBT CSV 解析、订单簿重构、回放分组
DataCleaner       — 清洗、crossed-book保护、档位过滤、统计计算
OrderBookRenderer — 买卖盘表格渲染（背景条可视化）
ChartRenderer     — Chart.js 深度图渲染
RealtimeAPI       — WebSocket / HTTP轮询 / TBT回放 / Seek跳转
App               — 主控制器，绑定所有 UI 事件
```

---

## 📸 界面预览

- 左侧：市场选择 Tab、模拟数据生成、文件导入、JSON 粘贴、手动编辑
- 中部：买卖盘深度图（Chart.js 阶梯曲线）
- 右侧：订单簿表格（买盘/卖盘，含数量背景条）
- 下方：TBT 回放控制台（进度条拖拽 + 时段标签 + 倍速调节）
- 底部：统计信息（价差、价差bps、买卖盘总量、多空比）

---

## 📝 开发说明

- 单文件架构，所有代码内联，便于分发与离线使用
- 数据处理全部在浏览器内存中完成，**不产生任何网络请求**（除 CDN 加载和用户主动配置的 API）
- TBT 大文件（>30MB）采用分批异步处理，每批 8000 行 yield 一次，避免 UI 冻结
- 回放引擎采用 `setTimeout` 调度，支持暂停/继续/跳转，帧率可配

---

## 📄 License

MIT License — 自由使用、修改、分发，保留出处即可。
