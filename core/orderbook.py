"""
core/orderbook.py
=================
A股 Level-2 逐笔（TBT）订单簿状态机。

支持四种动作：
  add     — 新增委托（entrust_orderStatus=0）
  cancel  — 撤销委托（entrust_orderStatus=1）
  trade   — 成交减量（type='trade'）
  modify  — 修改（预留，当前同 add 处理）

快照生成规则：
  · 买盘 降序  · 卖盘 升序  · 合并同价  · 过滤零量档位
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
import math


@dataclass
class _Order:
    side: int       # 1=买, 2=卖
    price: float
    remaining: float


class OrderBook:
    """维护单只标的的完整订单簿状态。"""

    def __init__(self):
        self._orders: Dict[str, _Order] = {}   # orderNum -> Order
        self._bids: Dict[float, float] = {}     # price -> qty
        self._asks: Dict[float, float] = {}     # price -> qty
        self.stats = {"totalOrders": 0, "totalCancels": 0, "totalTrans": 0}

    # ------------------------------------------------------------------ #
    #  公开操作接口
    # ------------------------------------------------------------------ #

    def add(self, order_num: str, side: int, price: float, vol: float):
        """新增委托，加入订单簿。"""
        if price <= 0 or vol <= 0:
            return
        self.stats["totalOrders"] += 1
        self._orders[order_num] = _Order(side=side, price=price, remaining=vol)
        if side == 1:
            self._bids[price] = self._bids.get(price, 0.0) + vol
        else:
            self._asks[price] = self._asks.get(price, 0.0) + vol

    def cancel(self, order_num: str, side: int = 0, price: float = 0.0, vol: float = 0.0):
        """撤销委托，从订单簿减去剩余量。"""
        self.stats["totalCancels"] += 1
        orig = self._orders.pop(order_num, None)
        if orig:
            self._reduce_level(orig.side, orig.price, orig.remaining)
        elif price > 0 and vol > 0 and side in (1, 2):
            # 兜底：撤单未命中 orderNum，按行内 dir/price/vol 减量
            self._reduce_level(side, price, vol)

    def trade(self, buy_num: str, sell_num: str, tx_vol: float):
        """成交，减去买卖两侧已成交量。"""
        self.stats["totalTrans"] += 1
        self._apply_trade_side(buy_num, tx_vol)
        self._apply_trade_side(sell_num, tx_vol)

    def reset(self):
        """清空所有状态（回放从头开始时使用）。"""
        self._orders.clear()
        self._bids.clear()
        self._asks.clear()
        self.stats = {"totalOrders": 0, "totalCancels": 0, "totalTrans": 0}

    # ------------------------------------------------------------------ #
    #  快照生成
    # ------------------------------------------------------------------ #

    def snapshot(self, levels: int = 0) -> Tuple[List[dict], List[dict]]:
        """
        生成买盘/卖盘快照。
        returns: (bids_list, asks_list)
          bids: [{"price": float, "qty": float}, ...]  降序
          asks: [{"price": float, "qty": float}, ...]  升序
        levels=0 表示返回全部档位。
        """
        bids = [
            {"price": p, "qty": round(q, 4)}
            for p, q in self._bids.items()
            if q > 1e-9
        ]
        asks = [
            {"price": p, "qty": round(q, 4)}
            for p, q in self._asks.items()
            if q > 1e-9
        ]
        bids.sort(key=lambda x: -x["price"])
        asks.sort(key=lambda x: x["price"])
        if levels > 0:
            bids = bids[:levels]
            asks = asks[:levels]
        return bids, asks

    # ------------------------------------------------------------------ #
    #  内部辅助
    # ------------------------------------------------------------------ #

    def _reduce_level(self, side: int, price: float, qty: float):
        book = self._bids if side == 1 else self._asks
        if price in book:
            book[price] = max(0.0, book[price] - qty)

    def _apply_trade_side(self, order_num: str, tx_vol: float):
        order = self._orders.get(order_num)
        if not order:
            return
        reduce = min(order.remaining, tx_vol)
        order.remaining -= reduce
        self._reduce_level(order.side, order.price, reduce)
        if order.remaining <= 1e-9:
            del self._orders[order_num]
