"""Read-only quality evidence for Taobao's current-state item snapshots."""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path


def current_price_snapshot_error(database_path: Path, business_day: date) -> str | None:
    source = (
        Path(database_path).parent / "raw_responses" / "taobao_operational_snapshots"
        / business_day.isoformat() / "current_prices.json"
    )
    try:
        stat = source.stat()
    except FileNotFoundError:
        return None
    except OSError:
        return "商品当前价分页汇总无法读取，快照完整性待核实。"
    return _inspect_current_price_pages(str(source), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=128)
def _inspect_current_price_pages(path: str, mtime_ns: int, size: int) -> str | None:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "商品当前价分页汇总损坏，不能确认快照完整。"
    pages = payload.get("pages") if isinstance(payload, dict) else None
    if not isinstance(pages, list) or not pages:
        return "商品当前价分页汇总缺少有效页面，不能确认快照完整。"
    fetched = 0
    total: int | None = None
    for index, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            return f"商品当前价第 {index} 页响应异常，历史快照可能残缺。"
        ret = page.get("ret")
        if isinstance(ret, list) and (not ret or any(not str(value).upper().startswith("SUCCESS") for value in ret)):
            return f"商品当前价第 {index} 页平台返回异常，历史快照可能残缺。"
        data = page.get("data")
        model = data.get("model") if isinstance(data, dict) else None
        rows = model.get("items") if isinstance(model, dict) else None
        if not isinstance(rows, list):
            return f"商品当前价第 {index} 页缺少商品列表，历史快照可能残缺。"
        if index == 1 and model.get("totalCount") is not None:
            try:
                total = int(model["totalCount"])
            except (TypeError, ValueError):
                return "商品当前价总量字段异常，不能确认快照完整。"
        fetched += len(rows)
    if total is not None and fetched < total:
        return f"商品当前价分页仅取得 {fetched}/{total} 行，历史快照不完整且无法按过去日期重采。"
    return None
