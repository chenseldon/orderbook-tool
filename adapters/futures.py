"""
期货适配器（openctp / vnpy CTP）
依赖：pip install openctp-ctp（仿真环境可直接测试）
     或 vnpy-ctp（需券商CTP接入资格）

openctp免费仿真：http://openctp.cn/
"""
import asyncio
import time
import logging
from threading import Thread, Event

from .base import BaseAdapter

logger = logging.getLogger(__name__)


class FuturesAdapter(BaseAdapter):

    async def _run_loop(self, params: dict):
        """
        params:
          mdServer:   str  行情前置地址 e.g. "tcp://180.168.146.187:10211"（openctp仿真）
          brokerId:   str  e.g. "9999"（simnow仿真）
          userId:     str  账号
          password:   str  密码
          symbol:     str  合约代码 e.g. "IF2412"
          levels:     int  档位数（CTP最多5档，默认5）
        """
        try:
            import openctp_ctp as ctp
        except ImportError:
            try:
                from vnpy_ctp import MdApi
                await self._run_vnpy_ctp(params)
                return
            except ImportError:
                self._emit({"type": "error",
                            "msg": "未安装CTP库：pip install openctp-ctp 或 pip install vnpy-ctp"})
                return

        await self._run_openctp(params, ctp)

    async def _run_openctp(self, params: dict, ctp):
        md_server = params.get("mdServer", "tcp://180.168.146.187:10211")
        broker_id = params.get("brokerId", "9999")
        user_id   = params.get("userId", "")
        password  = params.get("password", "")
        symbol    = params.get("symbol", "IF2412")
        levels    = int(params.get("levels", 5))

        adapter = self
        ready_event = Event()
        loop = asyncio.get_event_loop()

        class MdSpi(ctp.CThostFtdcMdSpi):
            def OnFrontConnected(self):
                req = ctp.CThostFtdcReqUserLoginField()
                req.BrokerID = broker_id
                req.UserID   = user_id
                req.Password = password
                self._api.ReqUserLogin(req, 0)

            def OnRspUserLogin(self, pRspUserLogin, pRspInfo, nRequestID, bIsLast):
                if pRspInfo and pRspInfo.ErrorID != 0:
                    adapter._emit({"type": "error", "msg": f"CTP登录失败: {pRspInfo.ErrorMsg}"})
                    return
                self._api.SubscribeMarketData([symbol.encode()])
                logger.info(f"[Futures] CTP登录成功，订阅 {symbol}")
                ready_event.set()

            def OnRtnDepthMarketData(self, pDepthMarketData):
                try:
                    p = pDepthMarketData
                    bids, asks = [], []
                    for i in range(1, 6):
                        bp = getattr(p, f"BidPrice{i}", 0)
                        bv = getattr(p, f"BidVolume{i}", 0)
                        ap = getattr(p, f"AskPrice{i}", 0)
                        av = getattr(p, f"AskVolume{i}", 0)
                        if bp and bp < 1e15 and bv > 0:
                            bids.append([float(bp), float(bv)])
                        if ap and ap < 1e15 and av > 0:
                            asks.append([float(ap), float(av)])
                    bids = sorted(bids, key=lambda x: -x[0])[:levels]
                    asks = sorted(asks, key=lambda x: x[0])[:levels]
                    adapter._emit({
                        "market": "futures",
                        "symbol": symbol,
                        "bids": bids,
                        "asks": asks,
                        "ts": int(time.time() * 1000)
                    })
                except Exception as e:
                    logger.error(f"[Futures] 行情解析错误: {e}")

        def run_ctp():
            api = ctp.CThostFtdcMdApi.CreateFtdcMdApi("./ctp_flow/")
            spi = MdSpi()
            spi._api = api
            api.RegisterSpi(spi)
            api.RegisterFront(md_server)
            api.Init()
            api.Join()

        thread = Thread(target=run_ctp, daemon=True)
        thread.start()

        try:
            while self._running:
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    async def _run_vnpy_ctp(self, params: dict):
        """vnpy-ctp版本（接口略有不同，未来扩展）"""
        self._emit({"type": "error", "msg": "vnpy-ctp模式暂未实现，请使用openctp-ctp"})
