"""
A股适配器（QMT / xtquant）
依赖：pip install xtquant（需安装迅投QMT客户端）
文档：https://dict.thinktrader.net/nativeApi/xtquant.html

注意：本模块只有安装了QMT客户端才能运行。
若未安装，server.py会捕获ImportError并返回友好错误提示。
"""
import asyncio
import time
import logging
from typing import Optional

from .base import BaseAdapter

logger = logging.getLogger(__name__)


class AShareAdapter(BaseAdapter):

    async def _run_loop(self, params: dict):
        """
        params:
          symbol:   str   e.g. "000001.SZ"
          mode:     str   "snapshot" | "tick"（默认snapshot）
          account:  str   QMT账户（可选，获取快照不需要）
          levels:   int   档位数（默认10）
        """
        try:
            from xtquant import xtdata
        except ImportError:
            self._emit({"type": "error", "msg": "未安装xtquant，请先安装迅投QMT客户端和xtquant包"})
            return

        symbol = params.get("symbol", "000001.SZ")
        levels = int(params.get("levels", 10))
        # 确保格式正确：加后缀
        if "." not in symbol:
            # 默认猜测交易所
            code = symbol
            symbol = f"{code}.SZ" if code.startswith(("0", "3")) else f"{code}.SH"

        logger.info(f"[AShare] 订阅 {symbol} Level2快照")

        # 订阅行情
        xtdata.subscribe_quote(symbol, period="tick", callback=None)

        try:
            while self._running:
                await asyncio.sleep(0.3)  # 约3次/秒
                data = xtdata.get_market_data(
                    field_list=[], stock_list=[symbol],
                    period="tick", count=1
                )
                if not data:
                    continue

                # 解析L2盘口数据
                # xtdata返回格式：{"bidPrice": [[p1,p2,...,p10]], "bidVol": [...], "askPrice": [...], "askVol": [...]}
                bid_prices = data.get("bidPrice", {}).get(symbol, [[]])[0] or []
                bid_vols   = data.get("bidVol",   {}).get(symbol, [[]])[0] or []
                ask_prices = data.get("askPrice", {}).get(symbol, [[]])[0] or []
                ask_vols   = data.get("askVol",   {}).get(symbol, [[]])[0] or []

                bids = [[float(p), float(v)] for p, v in zip(bid_prices, bid_vols)
                        if p and v and float(p) > 0 and float(v) > 0][:levels]
                asks = [[float(p), float(v)] for p, v in zip(ask_prices, ask_vols)
                        if p and v and float(p) > 0 and float(v) > 0][:levels]

                if not bids and not asks:
                    continue

                # 买盘降序，卖盘升序
                bids.sort(key=lambda x: -x[0])
                asks.sort(key=lambda x: x[0])

                self._emit({
                    "market": "ashare",
                    "symbol": symbol,
                    "bids": bids,
                    "asks": asks,
                    "ts": int(time.time() * 1000)
                })
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[AShare] 错误: {e}")
            self._emit({"type": "error", "msg": f"A股行情错误: {e}"})
        finally:
            try:
                xtdata.unsubscribe_quote(symbol)
            except Exception:
                pass
