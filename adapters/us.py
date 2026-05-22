"""
美股适配器
支持两种接入方式：
  A. Alpaca Markets（alpaca-py）— 免费L1，$99/月L2
     pip install alpaca-py
  B. Interactive Brokers（ib_insync）— 需本地运行TWS或IB Gateway
     pip install ib_insync

通过 params["provider"] 区分使用哪种
"""
import asyncio
import time
import logging

from .base import BaseAdapter

logger = logging.getLogger(__name__)


class USStockAdapter(BaseAdapter):

    async def _run_loop(self, params: dict):
        """
        params:
          provider:    "alpaca" | "ibkr"

          --- Alpaca ---
          apiKey:      str
          secret:      str
          symbol:      str  e.g. "AAPL"
          levels:      int  (默认10，免费版只有L1=1档)

          --- IBKR ---
          host:        str  (默认"127.0.0.1")
          port:        int  (默认7497 TWS实盘；7496模拟；4001 Gateway实盘)
          clientId:    int  (默认1)
          symbol:      str  e.g. "AAPL"
          levels:      int  (默认10)
        """
        provider = params.get("provider", "alpaca")
        if provider == "ibkr":
            await self._run_ibkr(params)
        else:
            await self._run_alpaca(params)

    # ----------------------------------------------------------------
    # Alpaca
    # ----------------------------------------------------------------
    async def _run_alpaca(self, params: dict):
        try:
            from alpaca.data.live import StockDataStream
            from alpaca.data.requests import StockLatestOrderbookRequest
            from alpaca.data.historical import StockHistoricalDataClient
        except ImportError:
            self._emit({"type": "error", "msg": "未安装alpaca-py：pip install alpaca-py"})
            return

        api_key = params.get("apiKey", "")
        secret  = params.get("secret", "")
        symbol  = params.get("symbol", "AAPL").upper()
        levels  = int(params.get("levels", 10))

        if not api_key or not secret:
            self._emit({"type": "error", "msg": "请填写Alpaca API Key和Secret"})
            return

        logger.info(f"[US/Alpaca] 订阅 {symbol}")

        # Alpaca免费版只有NBBO（1档），付费版有L2多档
        # 使用WebSocket Stream
        last_snapshot = {}

        def on_orderbook(data):
            try:
                bids = sorted([[float(b.p), float(b.s)] for b in (data.bids or [])],
                              key=lambda x: -x[0])[:levels]
                asks = sorted([[float(a.p), float(a.s)] for a in (data.asks or [])],
                              key=lambda x: x[0])[:levels]
                last_snapshot.update({"bids": bids, "asks": asks})
                self._emit({
                    "market": "us",
                    "symbol": symbol,
                    "bids": bids,
                    "asks": asks,
                    "ts": int(time.time() * 1000)
                })
            except Exception as e:
                logger.error(f"[US/Alpaca] 解析错误: {e}")

        stream = StockDataStream(api_key, secret)
        stream.subscribe_orderbooks(on_orderbook, symbol)
        try:
            await asyncio.get_event_loop().run_in_executor(None, stream.run)
        except asyncio.CancelledError:
            stream.stop()
        except Exception as e:
            logger.error(f"[US/Alpaca] 错误: {e}")
            self._emit({"type": "error", "msg": f"Alpaca错误: {e}"})

    # ----------------------------------------------------------------
    # Interactive Brokers (ib_insync)
    # ----------------------------------------------------------------
    async def _run_ibkr(self, params: dict):
        try:
            from ib_insync import IB, Stock
        except ImportError:
            self._emit({"type": "error", "msg": "未安装ib_insync：pip install ib_insync"})
            return

        host      = params.get("host", "127.0.0.1")
        port      = int(params.get("port", 7497))
        client_id = int(params.get("clientId", 1))
        symbol    = params.get("symbol", "AAPL").upper()
        levels    = int(params.get("levels", 10))

        ib = IB()
        logger.info(f"[US/IBKR] 连接 {host}:{port} 订阅 {symbol}")
        try:
            await ib.connectAsync(host, port, clientId=client_id)
            contract = Stock(symbol, "SMART", "USD")
            await ib.qualifyContractsAsync(contract)
            ib.reqMktDepth(contract, numRows=levels)

            while self._running:
                await asyncio.sleep(0.2)
                ticker = ib.ticker(contract)
                if ticker is None:
                    continue
                bids = sorted([[d.price, d.size] for d in (ticker.domBids or [])
                               if d.price > 0 and d.size > 0],
                              key=lambda x: -x[0])[:levels]
                asks = sorted([[d.price, d.size] for d in (ticker.domAsks or [])
                               if d.price > 0 and d.size > 0],
                              key=lambda x: x[0])[:levels]
                if bids or asks:
                    self._emit({
                        "market": "us",
                        "symbol": symbol,
                        "bids": bids,
                        "asks": asks,
                        "ts": int(time.time() * 1000)
                    })
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[US/IBKR] 错误: {e}")
            self._emit({"type": "error", "msg": f"IBKR错误: {e}"})
        finally:
            try:
                ib.disconnect()
            except Exception:
                pass
