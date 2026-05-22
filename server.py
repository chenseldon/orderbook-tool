"""
多市场订单簿重构工具 — Python后端服务
启动命令：python server.py
WebSocket地址：ws://localhost:8765
HTTP状态：http://localhost:8765/status

前端通过WebSocket发送控制指令，服务端推送订单簿快照
"""
import asyncio
import json
import logging
import os
import signal
import sys
from typing import Set

import websockets
from websockets.server import WebSocketServerProtocol
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ── 适配器 ──────────────────────────────────────────────────────────
from adapters.crypto import CryptoAdapter
from adapters.ashare import AShareAdapter
from adapters.us import USStockAdapter
from adapters.hk import HKStockAdapter
from adapters.futures import FuturesAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("server")

# ── 全局状态 ────────────────────────────────────────────────────────
clients: Set[WebSocketServerProtocol] = set()
current_adapter = None
adapter_market  = None

ADAPTER_MAP = {
    "crypto":  CryptoAdapter,
    "ashare":  AShareAdapter,
    "us":      USStockAdapter,
    "hk":      HKStockAdapter,
    "futures": FuturesAdapter,
}


# ── 广播 ─────────────────────────────────────────────────────────────
def broadcast(data: dict):
    """同步回调：把快照广播给所有连接的前端"""
    if not clients:
        return
    msg = json.dumps(data, ensure_ascii=False)
    # 在事件循环中调度（从非async回调安全广播）
    loop = asyncio.get_event_loop()
    loop.call_soon_threadsafe(_schedule_broadcast, msg)


def _schedule_broadcast(msg: str):
    asyncio.ensure_future(_do_broadcast(msg))


async def _do_broadcast(msg: str):
    dead = set()
    for ws in list(clients):
        try:
            await ws.send(msg)
        except Exception:
            dead.add(ws)
    clients.difference_update(dead)


# ── 指令处理 ──────────────────────────────────────────────────────────
async def handle_command(ws: WebSocketServerProtocol, cmd: dict):
    global current_adapter, adapter_market

    action = cmd.get("cmd")
    market = cmd.get("market", "crypto")
    params = cmd.get("params", {})

    if action == "connect":
        # 断开旧适配器
        if current_adapter:
            await current_adapter.disconnect()
            current_adapter = None

        cls = ADAPTER_MAP.get(market)
        if cls is None:
            await ws.send(json.dumps({"type": "error", "msg": f"未知市场: {market}"}))
            return

        adapter = cls()
        adapter.on_snapshot = broadcast
        current_adapter = adapter
        adapter_market  = market

        await ws.send(json.dumps({"type": "status", "state": "connecting",
                                  "msg": f"正在连接 {market}..."}))
        await adapter.connect(params)
        await ws.send(json.dumps({"type": "status", "state": "connected",
                                  "msg": f"已连接 {market}"}))

    elif action == "aggregate":
        # 多交易所聚合（只有crypto支持）
        if current_adapter:
            await current_adapter.disconnect()
        adapter = CryptoAdapter()
        adapter.on_snapshot = broadcast
        current_adapter = adapter
        adapter_market  = "crypto"
        params["mode"] = "aggregate"
        await ws.send(json.dumps({"type": "status", "state": "connecting",
                                  "msg": f"正在聚合 {params.get('exchanges')} {params.get('symbol')}..."}))
        await adapter.connect(params)

    elif action == "disconnect":
        if current_adapter:
            await current_adapter.disconnect()
            current_adapter = None
            adapter_market  = None
        await ws.send(json.dumps({"type": "status", "state": "disconnected", "msg": "已断开"}))

    elif action == "ping":
        await ws.send(json.dumps({"type": "pong"}))

    else:
        await ws.send(json.dumps({"type": "error", "msg": f"未知指令: {action}"}))


# ── WebSocket处理器 ────────────────────────────────────────────────────
async def ws_handler(ws: WebSocketServerProtocol, path: str):
    clients.add(ws)
    logger.info(f"客户端连接: {ws.remote_address}")
    # 发送欢迎消息
    await ws.send(json.dumps({
        "type": "status",
        "state": "ready",
        "msg": "Python服务已就绪",
        "markets": list(ADAPTER_MAP.keys())
    }))
    try:
        async for raw in ws:
            try:
                cmd = json.loads(raw)
                await handle_command(ws, cmd)
            except json.JSONDecodeError:
                await ws.send(json.dumps({"type": "error", "msg": "无效JSON"}))
            except Exception as e:
                logger.error(f"指令处理错误: {e}", exc_info=True)
                await ws.send(json.dumps({"type": "error", "msg": str(e)}))
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(ws)
        logger.info(f"客户端断开: {ws.remote_address}")


# ── FastAPI HTTP（状态查询）────────────────────────────────────────────
app = FastAPI(title="订单簿服务", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"])


@app.get("/status")
async def status():
    return {
        "ok": True,
        "clients": len(clients),
        "market": adapter_market,
        "markets": list(ADAPTER_MAP.keys())
    }


# ── 启动入口 ──────────────────────────────────────────────────────────
WS_PORT   = int(os.environ.get("WS_PORT",   8765))
HTTP_PORT = int(os.environ.get("HTTP_PORT", 8766))


async def main():
    # 创建CTP流目录
    os.makedirs("ctp_flow", exist_ok=True)

    logger.info(f"WebSocket服务启动 ws://localhost:{WS_PORT}")
    logger.info(f"HTTP状态接口启动 http://localhost:{HTTP_PORT}/status")

    ws_server = await websockets.serve(ws_handler, "localhost", WS_PORT)

    # 同时启动uvicorn（HTTP状态）
    config = uvicorn.Config(app, host="127.0.0.1", port=HTTP_PORT,
                            log_level="warning", loop="none")
    userver = uvicorn.Server(config)
    await asyncio.gather(
        ws_server.wait_closed(),
        userver.serve()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("服务已停止")
