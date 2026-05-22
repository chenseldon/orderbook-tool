"""
加密货币适配器
支持：
  1. 单交易所实时订单簿（ccxt.pro watchOrderBook）
  2. 多交易所聚合订单簿（多路并发，按价位合并量）
依赖：pip install ccxt[pro]
"""
import asyncio
import time
import logging
from collections import defaultdict
from typing import Dict, List, Tuple

import ccxt.pro as ccxtpro
import ccxt

from .base import BaseAdapter

logger = logging.getLogger(__name__)

# 支持的交易所列表（公开行情无需API Key）
SUPPORTED_EXCHANGES = [
    "binance", "okx", "bybit", "coinbase", "kraken",
    "gate", "kucoin", "mexc", "htx", "bitget"
]


def _make_exchange(name: str, api_key: str = "", secret: str = "") -> ccxtpro.Exchange:
    """创建ccxt.pro交易所实例"""
    cls = getattr(ccxtpro, name, None)
    if cls is None:
        raise ValueError(f"不支持的交易所: {name}")
    config = {"enableRateLimit": True}
    if api_key:
        config["apiKey"] = api_key
    if secret:
        config["secret"] = secret
    return cls(config)


def _merge_orderbooks(books: Dict[str, dict], levels: int = 20) -> Tuple[List, List]:
    """
    将多个交易所的订单簿按价位合并
    相同价格的数量相加，返回 (bids_desc, asks_asc)
    """
    bid_map: Dict[float, float] = defaultdict(float)
    ask_map: Dict[float, float] = defaultdict(float)

    for ex_name, ob in books.items():
        for price, qty in (ob.get("bids") or []):
            bid_map[float(price)] += float(qty)
        for price, qty in (ob.get("asks") or []):
            ask_map[float(price)] += float(qty)

    bids = sorted(bid_map.items(), key=lambda x: -x[0])[:levels]
    asks = sorted(ask_map.items(), key=lambda x: x[0])[:levels]
    return [[p, q] for p, q in bids], [[p, q] for p, q in asks]


class CryptoAdapter(BaseAdapter):

    async def _run_loop(self, params: dict):
        """
        params:
          mode:      "single" | "aggregate"
          exchange:  str           (single模式)
          exchanges: list[str]     (aggregate模式)
          symbol:    str           e.g. "BTC/USDT"
          apiKey:    str (可选)
          secret:    str (可选)
          levels:    int (默认20)
        """
        mode = params.get("mode", "single")
        symbol = params.get("symbol", "BTC/USDT")
        levels = int(params.get("levels", 20))
        api_key = params.get("apiKey", "")
        secret = params.get("secret", "")

        if mode == "aggregate":
            await self._run_aggregate(params, symbol, levels)
        else:
            await self._run_single(
                params.get("exchange", "binance"),
                symbol, levels, api_key, secret
            )

    # ----------------------------------------------------------------
    # 单交易所模式
    # ----------------------------------------------------------------
    async def _run_single(self, ex_name: str, symbol: str, levels: int,
                          api_key: str, secret: str):
        ex = _make_exchange(ex_name, api_key, secret)
        logger.info(f"[Crypto/single] 连接 {ex_name} {symbol}")
        try:
            while self._running:
                ob = await ex.watch_order_book(symbol, levels)
                snapshot = {
                    "market": "crypto",
                    "symbol": symbol,
                    "exchange": ex_name,
                    "bids": [[p, q] for p, q in (ob.get("bids") or [])[:levels]],
                    "asks": [[p, q] for p, q in (ob.get("asks") or [])[:levels]],
                    "ts": int(time.time() * 1000)
                }
                self._emit(snapshot)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[Crypto/single] 错误: {e}")
            self._emit({"type": "error", "msg": f"交易所错误: {e}"})
        finally:
            await ex.close()

    # ----------------------------------------------------------------
    # 多交易所聚合模式
    # ----------------------------------------------------------------
    async def _run_aggregate(self, params: dict, symbol: str, levels: int):
        exchanges_names = params.get("exchanges", ["binance", "okx", "bybit"])
        api_key = params.get("apiKey", "")
        secret = params.get("secret", "")

        exchanges = {}
        for name in exchanges_names:
            try:
                exchanges[name] = _make_exchange(name, api_key, secret)
            except Exception as e:
                logger.warning(f"跳过 {name}: {e}")

        # 每个交易所维护最新快照
        latest: Dict[str, dict] = {}
        lock = asyncio.Lock()

        async def watch_one(name: str, ex):
            try:
                while self._running:
                    ob = await ex.watch_order_book(symbol, levels)
                    async with lock:
                        latest[name] = ob
                        # 每次任意一个交易所更新就重新聚合并推送
                        bids, asks = _merge_orderbooks(latest, levels)
                        snapshot = {
                            "market": "crypto",
                            "symbol": symbol,
                            "mode": "aggregate",
                            "exchanges": list(latest.keys()),
                            "bids": bids,
                            "asks": asks,
                            "ts": int(time.time() * 1000)
                        }
                        self._emit(snapshot)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"[Crypto/aggregate/{name}] {e}")
            finally:
                await ex.close()

        logger.info(f"[Crypto/aggregate] 连接 {list(exchanges.keys())} {symbol}")
        tasks = [asyncio.create_task(watch_one(n, ex)) for n, ex in exchanges.items()]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for t in tasks:
                t.cancel()
