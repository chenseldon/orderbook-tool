"""
适配器基类
所有市场适配器继承此类，统一输出标准订单簿快照格式
"""
import asyncio
from abc import ABC, abstractmethod
from typing import Callable, Optional


class BaseAdapter(ABC):
    """
    标准适配器接口
    子类实现 _run_loop() 持续推送快照到 on_snapshot 回调
    """

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self.on_snapshot: Optional[Callable] = None  # 由server.py注入

    @abstractmethod
    async def _run_loop(self, params: dict):
        """
        主循环：持续获取行情并调用 self._emit(snapshot)
        snapshot 标准格式：
        {
          "market":  str,            # crypto / ashare / us / hk / futures
          "symbol":  str,            # 交易代码
          "bids":    [[price, qty]], # 买盘，降序
          "asks":    [[price, qty]], # 卖盘，升序
          "ts":      int             # 毫秒时间戳
        }
        """
        raise NotImplementedError

    async def connect(self, params: dict):
        """启动适配器循环"""
        await self.disconnect()
        self._running = True
        self._task = asyncio.create_task(self._run_loop(params))

    async def disconnect(self):
        """停止适配器循环"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    def _emit(self, snapshot: dict):
        """推送快照到server广播函数"""
        if self.on_snapshot:
            self.on_snapshot(snapshot)
