"""
core/exporter.py
================
订单簿数据导出工具。

提供：
  · to_json_str  — 序列化为 JSON 字符串
  · to_csv_str   — 单快照 CSV 字符串
  · timeseries_csv_stream — 时序 CSV 生成器（逐行流式输出，不占内存）
"""

from __future__ import annotations

import csv
import io
import json
from typing import Iterator, List


def to_json_str(bids: list, asks: list, meta: dict | None = None) -> str:
    obj = {
        "bids": bids,
        "asks": asks,
    }
    if meta:
        obj.update(meta)
    return json.dumps(obj, ensure_ascii=False)


def to_csv_str(bids: list, asks: list) -> str:
    """将单快照导出为 side,price,qty CSV 字符串。"""
    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(["side", "price", "qty"])
    for r in bids:
        w.writerow(["bid", r["price"], r["qty"]])
    for r in asks:
        w.writerow(["ask", r["price"], r["qty"]])
    return buf.getvalue()


def timeseries_csv_stream(
    frames: Iterator[dict],
    levels: int = 20,
) -> Iterator[str]:
    """
    将 iter_frames() 返回的帧序列流式转换为 CSV 行。

    CSV 格式（宽表）：
      timestamp, bid1_p, bid1_q, ..., bidN_p, bidN_q,
                 ask1_p, ask1_q, ..., askN_p, askN_q

    使用生成器，调用方可直接接入 StreamingResponse。
    """
    # 写表头
    cols = ["timestamp"]
    for i in range(1, levels + 1):
        cols += [f"bid{i}_p", f"bid{i}_q"]
    for i in range(1, levels + 1):
        cols += [f"ask{i}_p", f"ask{i}_q"]
    yield ",".join(cols) + "\n"

    for frame in frames:
        bids = frame.get("bids", [])
        asks = frame.get("asks", [])
        row  = [frame.get("ts", "")]
        for i in range(levels):
            if i < len(bids):
                row += [bids[i]["price"], bids[i]["qty"]]
            else:
                row += ["", ""]
        for i in range(levels):
            if i < len(asks):
                row += [asks[i]["price"], asks[i]["qty"]]
            else:
                row += ["", ""]
        yield ",".join(str(v) for v in row) + "\n"
