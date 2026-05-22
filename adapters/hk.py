"""
港股适配器（富途 OpenAPI）
依赖：pip install futu-api
需本地运行 FutuOpenD 客户端（免费下载：https://www.futunn.com/download/openAPI）
文档：https://openapi.futunn.com/futu-api-doc/
"""
import asyncio
import time
import logging
from threading import Thread

from .base import BaseAdapter

logger = logging.getLogger(__name__)


class HKStockAdapter(BaseAdapter):

    async def _run_loop(self, params: dict):
        """
        params:
          host:    str  (默认"127.0.0.1"，FutuOpenD地址)
          port:    int  (默认11111)
          symbol:  str  e.g. "HK.00700"（腾讯）或 "00700"
          levels:  int  (默认10，最多10档)
        """
        try:
            import futu as ft
        except ImportError:
            self._emit({"type": "error", "msg": "未安装futu-api：pip install futu-api"})
            return

        host   = params.get("host", "127.0.0.1")
        port   = int(params.get("port", 11111))
        symbol = params.get("symbol", "HK.00700")
        levels = int(params.get("levels", 10))

        # 补全前缀
        if not symbol.startswith("HK."):
            symbol = f"HK.{symbol}"

        logger.info(f"[HK] 连接 FutuOpenD {host}:{port} 订阅 {symbol}")

        # 富途API是同步阻塞的，放到线程中运行
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_futu_sync, params, symbol, levels, host, port)

    def _run_futu_sync(self, params, symbol, levels, host, port):
        """在线程中同步运行富途行情订阅"""
        try:
            import futu as ft
        except ImportError:
            return

        class OrderBookHandler(ft.OrderBookHandlerBase):
            def __init__(self, adapter, sym, lvls):
                self._adapter = adapter
                self._symbol = sym
                self._levels = lvls

            def on_recv_rsp(self, rsp_str):
                ret_code, content = super().on_recv_rsp(rsp_str)
                if ret_code != ft.RET_OK:
                    return ret_code, content
                try:
                    # content格式：{'code': 'HK.00700', 'svr_recv_time_bid': ...,
                    #               'Ask': [(price, size, num_orders), ...],
                    #               'Bid': [(price, size, num_orders), ...]}
                    bids = [[float(p), float(s)] for p, s, _ in content.get("Bid", [])
                            if float(p) > 0 and float(s) > 0][:self._levels]
                    asks = [[float(p), float(s)] for p, s, _ in content.get("Ask", [])
                            if float(p) > 0 and float(s) > 0][:self._levels]
                    bids.sort(key=lambda x: -x[0])
                    asks.sort(key=lambda x: x[0])
                    self._adapter._emit({
                        "market": "hk",
                        "symbol": self._symbol,
                        "bids": bids,
                        "asks": asks,
                        "ts": int(time.time() * 1000)
                    })
                except Exception as e:
                    logger.error(f"[HK] 解析错误: {e}")
                return ret_code, content

        quote_ctx = ft.OpenQuoteContext(host=host, port=port)
        handler = OrderBookHandler(self, symbol, levels)
        quote_ctx.set_handler(handler)

        ret, data = quote_ctx.subscribe([symbol], [ft.SubType.ORDER_BOOK])
        if ret != ft.RET_OK:
            self._emit({"type": "error", "msg": f"富途订阅失败: {data}"})
            quote_ctx.close()
            return

        logger.info(f"[HK] 订阅成功 {symbol}")

        try:
            import time as _time
            while self._running:
                _time.sleep(0.1)
        except Exception:
            pass
        finally:
            quote_ctx.unsubscribe([symbol], [ft.SubType.ORDER_BOOK])
            quote_ctx.close()
            logger.info(f"[HK] 断开 {symbol}")
