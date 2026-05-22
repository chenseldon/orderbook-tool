"""
多市场订单簿重构工具 — Python Web 服务
========================================
启动方式：  python server.py
浏览器访问：http://localhost:8765

功能：
  - 提供 orderbook-tool.html 页面（所有功能通过浏览器操作）
  - WebSocket /ws   — 实时市场行情推送（加密货币/A股/美股/港股/期货）
  - GET  /          — 主页面
  - GET  /api/status — 服务状态
"""
import asyncio
import io
import json
import logging
import os
import sys
import webbrowser
from pathlib import Path
from typing import Set, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

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

# ── FastAPI 应用 ────────────────────────────────────────────────────
app = FastAPI(title="多市场订单簿重构工具", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

BASE_DIR = Path(__file__).parent
HTML_FILE = BASE_DIR / "orderbook-tool.html"

# ── 全局状态 ────────────────────────────────────────────────────────
active_connections: Set[WebSocket] = set()
current_adapter    = None
adapter_market     = None

ADAPTER_MAP = {k: v for k, v in {
    "crypto":  CryptoAdapter,
    "ashare":  AShareAdapter,
    "us":      USStockAdapter,
    "hk":      HKStockAdapter,
    "futures": FuturesAdapter,
}.items() if v is not None}


# ── 广播快照到所有前端 ────────────────────────────────────────────────
async def broadcast(data: dict):
    msg = json.dumps(data, ensure_ascii=False)
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


# ═══════════════════════════════════════════════════════════════════
# HTTP 路由
# ═══════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index():
    """提供主页面"""
    if not HTML_FILE.exists():
        raise HTTPException(404, "orderbook-tool.html 未找到")
    return HTMLResponse(HTML_FILE.read_text(encoding="utf-8"))


@app.get("/api/status")
async def api_status():
    return {
        "ok": True,
        "clients": len(active_connections),
        "market": adapter_market,
        "markets": list(ADAPTER_MAP.keys()),
        "version": "2.0"
    }


# ═══════════════════════════════════════════════════════════════════
# WebSocket — 实时行情
# ═══════════════════════════════════════════════════════════════════

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    global current_adapter, adapter_market

    await ws.accept()
    active_connections.add(ws)
    logger.info(f"WebSocket客户端连接: {ws.client}")

    # 发送就绪消息
    await ws.send_text(json.dumps({
        "type": "status",
        "state": "ready",
        "msg": "Python服务已就绪",
        "markets": list(ADAPTER_MAP.keys())
    }))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                cmd = json.loads(raw)
                await _handle_ws_cmd(ws, cmd)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"type": "error", "msg": "无效JSON"}))
            except Exception as e:
                logger.error(f"指令处理错误: {e}", exc_info=True)
                await ws.send_text(json.dumps({"type": "error", "msg": str(e)}))
    except WebSocketDisconnect:
        pass
    finally:
        active_connections.discard(ws)
        logger.info(f"WebSocket客户端断开")


async def _handle_ws_cmd(ws: WebSocket, cmd: dict):
    global current_adapter, adapter_market

    action = cmd.get("cmd")
    market = cmd.get("market", "crypto")
    params = cmd.get("params", {})

    if action in ("connect", "aggregate"):
        # 停止旧适配器
        if current_adapter:
            await current_adapter.disconnect()
            current_adapter = None

        if market not in ADAPTER_MAP:
            await ws.send_text(json.dumps({"type": "error", "msg": f"未知市场: {market}，可用: {list(ADAPTER_MAP.keys())}"}))
            return

        adapter = ADAPTER_MAP[market]()
        adapter.on_snapshot = sync_broadcast
        current_adapter = adapter
        adapter_market  = market

        if action == "aggregate":
            params["mode"] = "aggregate"

        await ws.send_text(json.dumps({"type": "status", "state": "connecting", "msg": f"正在连接 {market}..."}))
        await adapter.connect(params)
        await ws.send_text(json.dumps({"type": "status", "state": "connected", "msg": f"已连接 {market}"}))

    elif action == "disconnect":
        if current_adapter:
            await current_adapter.disconnect()
            current_adapter = None
            adapter_market  = None
        await ws.send_text(json.dumps({"type": "status", "state": "disconnected", "msg": "已断开"}))

    elif action == "ping":
        await ws.send_text(json.dumps({"type": "pong"}))

    else:
        await ws.send_text(json.dumps({"type": "error", "msg": f"未知指令: {action}"}))


# ═══════════════════════════════════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════════════════════════════════

PORT = int(os.environ.get("PORT", 8765))


def main():
    os.makedirs("ctp_flow", exist_ok=True)

    logger.info("=" * 50)
    logger.info(" 多市场订单簿重构工具 v2.0")
    logger.info(f" 浏览器访问: http://localhost:{PORT}")
    logger.info(f" 可用市场适配器: {list(ADAPTER_MAP.keys())}")
    logger.info("=" * 50)

    # 延迟1秒后自动打开浏览器
    import threading
    def _open():
        import time; time.sleep(1.2)
        webbrowser.open(f"http://localhost:{PORT}")
    threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
