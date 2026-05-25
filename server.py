"""
多市场订单簿重构工具 — Python Web 服务 v3.0
============================================
启动方式：  python server.py
浏览器访问：http://localhost:5000

功能：
  GET  /                                   — 主页面
  GET  /api/status                         — 服务状态
  POST /api/tbt/upload                     — 上传 TBT CSV → file_id + 文件信息
  POST /api/tbt/reconstruct                — 重构指定时刻快照
  GET  /api/tbt/export/timeseries/{fid}    — 流式下载时序 CSV
  GET  /api/tbt/replay/frame               — 获取指定帧（回放用）
  POST /api/orderbook/clean                — 前端手动数据清洗
  WS   /ws                                 — 实时行情推送
"""
import asyncio
import json
import logging
import os
import shutil
import threading
import time
import uuid
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional, Set

from fastapi import (
    BackgroundTasks, FastAPI, File, HTTPException,
    Query, UploadFile, WebSocket, WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
import uvicorn

# ── 核心模块 ────────────────────────────────────────────────────────
from core.tbt_parser import TBTParser
from core.exporter   import timeseries_csv_stream, to_csv_str, to_json_str

# ── 适配器（按需导入，缺失依赖不影响其他功能） ─────────────────────
try:
    from adapters.crypto import CryptoAdapter
except ImportError as e:
    CryptoAdapter = None
    logging.warning(f"加密货币适配器不可用: {e}")

try:
    from adapters.ashare import AShareAdapter
except ImportError:
    AShareAdapter = None

try:
    from adapters.us import USStockAdapter
except ImportError:
    USStockAdapter = None

try:
    from adapters.hk import HKStockAdapter
except ImportError:
    HKStockAdapter = None

try:
    from adapters.futures import FuturesAdapter
except ImportError:
    FuturesAdapter = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("server")

# ═══════════════════════════════════════════════════════════════════
# FastAPI 应用
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(title="多市场订单簿重构工具", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

BASE_DIR    = Path(__file__).parent
TMPL_FILE   = BASE_DIR / "templates" / "index.html"
UPLOAD_DIR  = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# ── 全局状态 ────────────────────────────────────────────────────────
active_connections: Set[WebSocket] = set()
current_adapter    = None
adapter_market     = None

# TBT 文件会话：file_id -> {path, info, parser}
tbt_sessions: Dict[str, Dict[str, Any]] = {}

ADAPTER_MAP = {k: v for k, v in {
    "crypto":  CryptoAdapter,
    "ashare":  AShareAdapter,
    "us":      USStockAdapter,
    "hk":      HKStockAdapter,
    "futures": FuturesAdapter,
}.items() if v is not None}


# ═══════════════════════════════════════════════════════════════════
# HTTP — 页面 & 状态
# ═══════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index():
    if not TMPL_FILE.exists():
        raise HTTPException(404, "templates/index.html 未找到，请确认项目完整性")
    return HTMLResponse(TMPL_FILE.read_text(encoding="utf-8"))


@app.get("/api/status")
async def api_status():
    return {
        "ok":      True,
        "version": "3.0",
        "port":    PORT,
        "clients": len(active_connections),
        "market":  adapter_market,
        "markets": list(ADAPTER_MAP.keys()),
        "sessions": len(tbt_sessions),
    }


# ═══════════════════════════════════════════════════════════════════
# HTTP — TBT 文件处理
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/tbt/upload")
async def tbt_upload(file: UploadFile = File(...)):
    """
    接收 TBT CSV 文件，保存到 uploads/，返回 file_id 和文件基本信息。
    前端凭 file_id 调用后续重构/时序接口。
    """
    # 校验格式
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "仅支持 .csv 格式的 TBT 文件")

    file_id   = str(uuid.uuid4())
    save_path = UPLOAD_DIR / f"{file_id}.csv"

    # 保存文件
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # 解析文件信息
    try:
        parser = TBTParser(save_path)
        info   = parser.file_info()
        tbt_sessions[file_id] = {"path": save_path, "info": info, "parser": parser}
    except Exception as e:
        save_path.unlink(missing_ok=True)
        raise HTTPException(500, f"文件解析失败: {e}")

    logger.info(f"TBT 文件上传: {file.filename} → {file_id}, 行数={info['row_count']}")
    return {"file_id": file_id, "info": info}


@app.post("/api/tbt/reconstruct")
async def tbt_reconstruct(body: dict):
    """
    重构订单簿快照。
    请求体: {"file_id": "...", "snap_time": "HH:MM:SS"（可选）, "levels": 20}
    """
    file_id   = body.get("file_id", "")
    snap_time = body.get("snap_time") or None
    levels    = int(body.get("levels", 20))

    session = tbt_sessions.get(file_id)
    if not session:
        raise HTTPException(404, f"会话 {file_id} 不存在，请先上传文件")

    try:
        parser = TBTParser(session["path"])  # 每次重构用新实例，保证幂等
        progress_store = {}

        def on_progress(p):
            progress_store["pct"] = p

        bids, asks, stats = await asyncio.get_event_loop().run_in_executor(
            None, lambda: parser.reconstruct(snap_time, on_progress)
        )
    except Exception as e:
        logger.error(f"重构失败: {e}", exc_info=True)
        raise HTTPException(500, f"重构失败: {e}")

    return {
        "file_id":  file_id,
        "snap_time": snap_time,
        "symbol":   session["info"].get("symbol", ""),
        "bids":     bids[:levels],
        "asks":     asks[:levels],
        "stats":    stats,
    }


@app.get("/api/tbt/export/timeseries/{file_id}")
async def tbt_export_timeseries(
    file_id: str,
    levels:  int = Query(20, ge=1, le=50),
):
    """
    流式下载全量时序 CSV。
    文件名：orderbook_timeseries_{symbol}_{file_id[:8]}.csv
    """
    session = tbt_sessions.get(file_id)
    if not session:
        raise HTTPException(404, f"会话 {file_id} 不存在")

    symbol   = session["info"].get("symbol", "unknown")
    filename = f"orderbook_timeseries_{symbol}_{file_id[:8]}.csv"

    def stream():
        parser = TBTParser(session["path"])
        frames = parser.iter_frames(levels=levels)
        yield from timeseries_csv_stream(frames, levels=levels)

    return StreamingResponse(
        stream(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/tbt/replay/frame")
async def tbt_replay_frame(
    file_id: str,
    index:   int  = Query(..., ge=0),
    levels:  int  = Query(20, ge=1, le=50),
):
    """
    获取指定帧的订单簿快照（用于前端逐帧回放）。
    注意：index 从 0 开始，每次调用都会重新计算（适合小文件跳转）。
    大文件建议用时序 CSV 下载后在前端回放。
    """
    session = tbt_sessions.get(file_id)
    if not session:
        raise HTTPException(404, f"会话 {file_id} 不存在")

    try:
        parser = TBTParser(session["path"])
        frame  = None
        for i, f in enumerate(parser.iter_frames(levels=levels)):
            if i == index:
                frame = f
                break
        if frame is None:
            raise HTTPException(404, f"帧 {index} 不存在（文件共 {i+1} 帧）")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

    return frame


@app.get("/api/tbt/info/{file_id}")
async def tbt_info(file_id: str):
    """获取已上传文件的信息。"""
    session = tbt_sessions.get(file_id)
    if not session:
        raise HTTPException(404, f"会话 {file_id} 不存在")
    return session["info"]


@app.get("/api/tbt/export/frames/{file_id}")
async def tbt_export_frames(
    file_id: str,
    levels: int = Query(20, ge=1, le=50),
):
    """
    NDJSON 流式输出全量回放帧（供前端缓存后本地回放）。
    每行一个 JSON 对象：{"ts": "HH:MM:SS.mmm", "bids": [{price, qty}...], "asks": [...]}
    """
    session = tbt_sessions.get(file_id)
    if not session:
        raise HTTPException(404, f"会话 {file_id} 不存在")

    def stream():
        parser = TBTParser(session["path"])
        for frame in parser.iter_frames(levels=levels):
            yield json.dumps(frame, ensure_ascii=False) + "\n"

    return StreamingResponse(
        stream(),
        media_type="application/x-ndjson",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


# ═══════════════════════════════════════════════════════════════════
# HTTP — 前端手动数据清洗
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/orderbook/clean")
async def orderbook_clean(body: dict):
    """
    清洗前端传入的 bids/asks 数组。
    请求体: {
      "bids": [{"price": float, "qty": float}, ...],
      "asks": [...],
      "filter_pct": 3,   // 异常过滤阈值（%），0=不过滤
      "merge": true,
      "levels": 20
    }
    """
    bids       = body.get("bids", [])
    asks       = body.get("asks", [])
    filter_pct = float(body.get("filter_pct", 3))
    merge      = bool(body.get("merge", True))
    levels     = int(body.get("levels", 20))

    # 验证并转换
    def parse_rows(rows):
        out = {}
        for r in rows:
            p = float(r.get("price", 0))
            q = float(r.get("qty",   0))
            if p > 0 and q > 0:
                out[p] = out.get(p, 0) + q if merge else q
        return out

    bid_map = parse_rows(bids)
    ask_map = parse_rows(asks)

    # 过滤异常档位
    if bid_map and ask_map and filter_pct > 0:
        best_bid = max(bid_map)
        best_ask = min(ask_map)
        mid      = (best_bid + best_ask) / 2
        thr      = mid * filter_pct / 100
        bid_map  = {p: q for p, q in bid_map.items() if abs(p - mid) <= thr * 10}
        ask_map  = {p: q for p, q in ask_map.items() if abs(p - mid) <= thr * 10}

    out_bids = sorted(
        [{"price": p, "qty": round(q, 4)} for p, q in bid_map.items()],
        key=lambda x: -x["price"]
    )[:levels]
    out_asks = sorted(
        [{"price": p, "qty": round(q, 4)} for p, q in ask_map.items()],
        key=lambda x: x["price"]
    )[:levels]

    # 统计
    best_bid = out_bids[0]["price"] if out_bids else 0
    best_ask = out_asks[0]["price"] if out_asks else 0
    spread   = round(best_ask - best_bid, 6) if best_bid and best_ask else 0
    mid      = round((best_bid + best_ask) / 2, 6) if best_bid and best_ask else 0
    bid_vol  = round(sum(r["qty"] for r in out_bids), 4)
    ask_vol  = round(sum(r["qty"] for r in out_asks), 4)
    imbal    = round((bid_vol - ask_vol) / (bid_vol + ask_vol), 4) if (bid_vol + ask_vol) > 0 else 0

    return {
        "bids": out_bids,
        "asks": out_asks,
        "stats": {
            "spread": spread,
            "midPrice": mid,
            "bidTotal": bid_vol,
            "askTotal": ask_vol,
            "imbalance": imbal,
        }
    }


# ═══════════════════════════════════════════════════════════════════
# WebSocket — 实时行情
# ═══════════════════════════════════════════════════════════════════

async def broadcast(data: dict):
    msg  = json.dumps(data, ensure_ascii=False)
    dead = set()
    for ws in list(active_connections):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    active_connections.difference_update(dead)


def sync_broadcast(data: dict):
    """从同步/线程上下文安全广播（适配器回调用）"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(broadcast(data))
    except RuntimeError:
        pass


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global current_adapter, adapter_market

    await ws.accept()
    active_connections.add(ws)
    logger.info(f"WebSocket 客户端连接: {ws.client}")

    await ws.send_text(json.dumps({
        "type": "status",
        "state": "ready",
        "msg": "Python 服务已就绪 v3.0",
        "markets": list(ADAPTER_MAP.keys()),
        "version": "3.0",
    }))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                cmd = json.loads(raw)
                await _handle_ws_cmd(ws, cmd)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"type": "error", "msg": "无效 JSON"}))
            except Exception as e:
                logger.error(f"指令处理错误: {e}", exc_info=True)
                await ws.send_text(json.dumps({"type": "error", "msg": str(e)}))
    except WebSocketDisconnect:
        pass
    finally:
        active_connections.discard(ws)
        logger.info("WebSocket 客户端断开")


async def _handle_ws_cmd(ws: WebSocket, cmd: dict):
    global current_adapter, adapter_market

    action = cmd.get("cmd")
    market = cmd.get("market", "crypto")
    params = cmd.get("params", {})

    if action in ("connect", "aggregate"):
        if current_adapter:
            await current_adapter.disconnect()
            current_adapter = None

        if market not in ADAPTER_MAP:
            await ws.send_text(json.dumps({
                "type": "error",
                "msg": f"未知市场: {market}，可用: {list(ADAPTER_MAP.keys())}"
            }))
            return

        adapter = ADAPTER_MAP[market]()
        adapter.on_snapshot = sync_broadcast
        current_adapter  = adapter
        adapter_market   = market

        if action == "aggregate":
            params["mode"] = "aggregate"

        await ws.send_text(json.dumps({
            "type": "status", "state": "connecting",
            "msg": f"正在连接 {market}..."
        }))
        await adapter.connect(params)
        await ws.send_text(json.dumps({
            "type": "status", "state": "connected",
            "msg": f"已连接 {market}"
        }))

    elif action == "disconnect":
        if current_adapter:
            await current_adapter.disconnect()
            current_adapter = None
            adapter_market  = None
        await ws.send_text(json.dumps({
            "type": "status", "state": "disconnected", "msg": "已断开"
        }))

    elif action == "ping":
        await ws.send_text(json.dumps({"type": "pong"}))

    else:
        await ws.send_text(json.dumps({
            "type": "error", "msg": f"未知指令: {action}"
        }))


# ═══════════════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════════════

PORT = int(os.environ.get("PORT", 5000))


def main():
    os.makedirs("ctp_flow", exist_ok=True)

    logger.info("=" * 55)
    logger.info(" 多市场订单簿重构工具 v3.0  (Python-First)")
    logger.info(f" 浏览器访问: http://localhost:{PORT}")
    logger.info(f" 可用市场适配器: {list(ADAPTER_MAP.keys())}")
    logger.info("=" * 55)

    def _open():
        time.sleep(1.2)
        webbrowser.open(f"http://localhost:{PORT}")
    threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
