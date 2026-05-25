"""
core/tbt_parser.py
==================
深交所 Level-2 逐笔（TBT）CSV 解析与订单簿重构。

字段布局（自动从文件头检测）：
  type, clock, clock_int, symbol,
  entrust_volume, entrust_dir(1买/2卖),
  entrust_orderType, entrust_orderStatus(0新增/1撤销),
  entrust_price, entrust_orderNum,
  transaction_volume, transaction_buyNum, transaction_sellNum

使用示例：
  parser = TBTParser(file_path)
  info   = parser.file_info()                           # 文件基本信息
  bids, asks, stats = parser.reconstruct(snap_time)     # 快照重构
  frames = list(parser.iter_frames())                   # 全量时序帧
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterator, List, Optional, Tuple, Dict

from .orderbook import OrderBook


# ═══════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════

def _parse_clock_int(v: str) -> str:
    """
    将 clock_int（如 91500040）格式化为可读字符串 "09:15:00.040"。
    支持 6-9 位整数。
    """
    s = str(v).strip().lstrip("0") or "0"
    s = s.zfill(9)
    return f"{s[0:2]}:{s[2:4]}:{s[4:6]}.{s[6:9]}"


def _hm(clock_str: str) -> int:
    """从 'HH:MM:SS.mmm' 中提取 HHMM 整数，用于时段匹配。"""
    parts = clock_str.split(":")
    if len(parts) < 2:
        return 0
    return int(parts[0]) * 100 + int(parts[1])


# ═══════════════════════════════════════════════════════════════════════
# TBTParser
# ═══════════════════════════════════════════════════════════════════════

class TBTParser:
    """解析单个 TBT CSV 文件，支持快照重构与全量时序生成。"""

    def __init__(self, file_path: str | Path):
        self.path = Path(file_path)
        self._header: Optional[List[str]] = None
        self._idx: Optional[Dict[str, int]] = None
        self._first_ts: str = ""
        self._last_ts: str = ""
        self._symbol: str = ""
        self._row_count: int = 0
        self._scanned = False

    # ------------------------------------------------------------------ #
    #  文件基本信息（快速扫描，只读头尾两行）
    # ------------------------------------------------------------------ #

    def file_info(self) -> dict:
        """返回文件基本信息（不全量解析）。"""
        if not self._scanned:
            self._quick_scan()
        return {
            "path":      str(self.path),
            "symbol":    self._symbol,
            "first_ts":  self._first_ts,
            "last_ts":   self._last_ts,
            "row_count": self._row_count,
            "size_mb":   round(self.path.stat().st_size / 1024 / 1024, 2),
        }

    def _quick_scan(self):
        """仅读文件头两行 + 最后一行来获取元信息。"""
        with open(self.path, encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            header = next(reader, [])
            self._header = header
            self._idx    = {h: i for i, h in enumerate(header)}

            first_row = next(reader, None)
            last_row  = first_row
            count = 1
            for row in reader:
                if any(row):
                    last_row = row
                    count += 1

        self._row_count = count
        if first_row:
            self._first_ts = self._extract_ts(first_row)
            sym_i = self._idx.get("symbol", -1)
            if sym_i >= 0:
                self._symbol = first_row[sym_i].lstrip("0.")
        if last_row:
            self._last_ts = self._extract_ts(last_row)
        self._scanned = True

    def _extract_ts(self, row: List[str]) -> str:
        idx = self._idx or {}
        ci = idx.get("clock_int", idx.get("clock", -1))
        if ci >= 0 and ci < len(row):
            v = row[ci].strip()
            if v.isdigit():
                return _parse_clock_int(v)
            return v
        return ""

    # ------------------------------------------------------------------ #
    #  字段索引（懒加载）
    # ------------------------------------------------------------------ #

    def _ensure_idx(self):
        if self._idx is None:
            with open(self.path, encoding="utf-8", errors="replace") as f:
                header = next(csv.reader(f))
            self._header = header
            self._idx    = {h: i for i, h in enumerate(header)}

    def _get_idx(self) -> Dict[str, int]:
        self._ensure_idx()
        return self._idx  # type: ignore

    # ------------------------------------------------------------------ #
    #  快照重构
    # ------------------------------------------------------------------ #

    def reconstruct(
        self,
        snap_time: Optional[str] = None,
        on_progress=None,
    ) -> Tuple[List[dict], List[dict], dict]:
        """
        重构到指定时刻的订单簿快照。

        Parameters
        ----------
        snap_time : "HH:MM:SS" 或 None（全量）
        on_progress : callable(pct: float) | None

        Returns
        -------
        (bids, asks, stats)
        """
        idx = self._get_idx()
        ob  = OrderBook()

        I_type   = idx.get("type",               0)
        I_clock  = idx.get("clock",              -1)
        I_clockI = idx.get("clock_int",          -1)
        I_sym    = idx.get("symbol",             -1)
        I_vol    = idx.get("entrust_volume",     -1)
        I_dir    = idx.get("entrust_dir",        -1)
        I_status = idx.get("entrust_orderStatus",-1)
        I_price  = idx.get("entrust_price",      -1)
        I_oNum   = idx.get("entrust_orderNum",   -1)
        I_txVol  = idx.get("transaction_volume", -1)
        I_txBuy  = idx.get("transaction_buyNum", -1)
        I_txSell = idx.get("transaction_sellNum",-1)

        cutoff = None
        if snap_time:
            # snap_time 格式 "HH:MM:SS"，转换为 clock_int 整数上界
            try:
                parts = snap_time.replace(".", ":").split(":")
                h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
                ms = int(parts[3]) if len(parts) > 3 else 999
                cutoff = h * 10_000_000 + m * 100_000 + s * 1000 + ms
            except Exception:
                cutoff = None

        total = self._row_count or 1
        processed = 0

        with open(self.path, encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            next(reader)  # skip header

            for row in reader:
                if not row:
                    continue

                # 时间检查
                if cutoff is not None and I_clockI >= 0:
                    ci_val = row[I_clockI].strip()
                    if ci_val.isdigit() and int(ci_val) > cutoff:
                        break

                # 提取 symbol（一次即可）
                if not self._symbol and I_sym >= 0:
                    self._symbol = row[I_sym].lstrip("0.")

                row_type = row[I_type].strip() if I_type < len(row) else ""

                if row_type == "order":
                    side   = self._int(row, I_dir)
                    status = self._int(row, I_status)
                    price  = self._float(row, I_price)
                    vol    = self._float(row, I_vol)
                    onum   = row[I_oNum].strip() if I_oNum >= 0 and I_oNum < len(row) else ""

                    if status == 0:
                        ob.add(onum, side, price, vol)
                    elif status == 1:
                        ob.cancel(onum, side, price, vol)

                elif row_type == "trade":
                    tx_vol  = self._float(row, I_txVol)
                    tx_buy  = row[I_txBuy].strip()  if I_txBuy  >= 0 and I_txBuy  < len(row) else ""
                    tx_sell = row[I_txSell].strip() if I_txSell >= 0 and I_txSell < len(row) else ""
                    ob.trade(tx_buy, tx_sell, tx_vol)

                processed += 1
                if on_progress and processed % 50_000 == 0:
                    on_progress(min(processed / total, 0.99))

        if on_progress:
            on_progress(1.0)

        bids, asks = ob.snapshot()
        return bids, asks, dict(ob.stats)

    # ------------------------------------------------------------------ #
    #  全量时序帧迭代（内存友好，生成器）
    # ------------------------------------------------------------------ #

    def iter_frames(
        self,
        levels: int = 20,
        on_progress=None,
    ) -> Iterator[dict]:
        """
        按 clock_int 分组，逐帧生成订单簿快照。
        每个时间戳生成一帧 {"ts": "HH:MM:SS.mmm", "bids": [...], "asks": [...]}.
        使用生成器，不在内存中持有全部帧。
        """
        idx = self._get_idx()

        I_type   = idx.get("type",               0)
        I_clockI = idx.get("clock_int",          -1)
        I_clock  = idx.get("clock",              -1)
        I_vol    = idx.get("entrust_volume",     -1)
        I_dir    = idx.get("entrust_dir",        -1)
        I_status = idx.get("entrust_orderStatus",-1)
        I_price  = idx.get("entrust_price",      -1)
        I_oNum   = idx.get("entrust_orderNum",   -1)
        I_txVol  = idx.get("transaction_volume", -1)
        I_txBuy  = idx.get("transaction_buyNum", -1)
        I_txSell = idx.get("transaction_sellNum",-1)

        total = self._row_count or 1
        processed = 0
        ob = OrderBook()

        prev_key  = None
        prev_ts   = ""

        with open(self.path, encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            next(reader)  # skip header

            for row in reader:
                if not row:
                    continue

                cur_key = row[I_clockI].strip() if I_clockI >= 0 and I_clockI < len(row) else ""
                cur_ts  = row[I_clock].strip()  if I_clock  >= 0 and I_clock  < len(row) else ""

                # 当 clock_int 变化时，先 yield 上一个时间戳的快照
                if prev_key is not None and cur_key != prev_key:
                    bids, asks = ob.snapshot(levels)
                    yield {"ts": prev_ts, "bids": bids, "asks": asks}

                prev_key = cur_key
                prev_ts  = cur_ts

                # 处理当前行
                row_type = row[I_type].strip() if I_type < len(row) else ""

                if row_type == "order":
                    side   = self._int(row, I_dir)
                    status = self._int(row, I_status)
                    price  = self._float(row, I_price)
                    vol    = self._float(row, I_vol)
                    onum   = row[I_oNum].strip() if I_oNum >= 0 and I_oNum < len(row) else ""
                    if status == 0:
                        ob.add(onum, side, price, vol)
                    elif status == 1:
                        ob.cancel(onum, side, price, vol)

                elif row_type == "trade":
                    tx_vol  = self._float(row, I_txVol)
                    tx_buy  = row[I_txBuy].strip()  if I_txBuy  >= 0 and I_txBuy  < len(row) else ""
                    tx_sell = row[I_txSell].strip() if I_txSell >= 0 and I_txSell < len(row) else ""
                    ob.trade(tx_buy, tx_sell, tx_vol)

                processed += 1
                if on_progress and processed % 50_000 == 0:
                    on_progress(min(processed / total, 0.99))

        # 最后一个时间戳
        if prev_key is not None:
            bids, asks = ob.snapshot(levels)
            yield {"ts": prev_ts, "bids": bids, "asks": asks}

        if on_progress:
            on_progress(1.0)

    # ------------------------------------------------------------------ #
    #  内部辅助
    # ------------------------------------------------------------------ #

    @staticmethod
    def _int(row: List[str], idx: int, default: int = 0) -> int:
        if idx < 0 or idx >= len(row):
            return default
        try:
            return int(row[idx])
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _float(row: List[str], idx: int, default: float = 0.0) -> float:
        if idx < 0 or idx >= len(row):
            return default
        try:
            return float(row[idx])
        except (ValueError, TypeError):
            return default
