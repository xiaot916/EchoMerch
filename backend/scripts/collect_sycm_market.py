from __future__ import annotations

"""Collect SYCM market rankings for one fixed category into local SQLite.

This is deliberately separate from store-operation and advertising facts: the
market pages describe the category, not the signed-in shop's own performance.
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.error import URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.integrations.tmall_session import resolve_runtime_session  # noqa: E402


MARKET_TABLE = "sycm_market_rankings"
KEYWORD_TABLE = "sycm_market_keywords"
PARENT_CATE_ID = "50014812"
CATE_ID = "201207402"
CATE_FLAG = "1"


def _v(value: Any) -> str | None:
    if isinstance(value, dict) and "value" in value:
        value = value["value"]
    return None if value is None else str(value)


def _num(value: Any) -> int | None:
    try:
        return int(_v(value)) if _v(value) is not None else None
    except (TypeError, ValueError):
        return None


def _get(obj: dict[str, Any], key: str) -> Any:
    return obj.get(key)


def _request_json(
    path: str,
    params: dict[str, Any],
    *,
    cookie: str,
    referer: str,
    max_attempts: int = 8,
    request_delay: float = 1.2,
) -> dict[str, Any]:
    params = dict(params)
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            if attempt:
                # SYCM occasionally returns an HTML challenge or an empty
                # response while rate limiting. Back off before retrying.
                time.sleep(min(30.0, 4.0 * attempt))
            request = Request(
                "https://sycm.taobao.com" + path + "?" + urlencode({**params, "_": str(int(time.time() * 1000))}),
                headers={
                    "accept": "*/*",
                    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "cache-control": "no-cache",
                    "cookie": cookie,
                    "referer": referer,
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
                },
            )
            with urlopen(request, timeout=40) as response:
                body = response.read()
            if not body.strip():
                raise ValueError("SYCM returned an empty response")
            payload = json.loads(body.decode("utf-8-sig"))
            if not isinstance(payload, dict) or int(payload.get("code", -1)) != 0:
                raise RuntimeError(f"SYCM request failed: {payload!r}")
            if request_delay:
                time.sleep(request_delay)
            return payload
        except (URLError, TimeoutError, ConnectionError, UnicodeDecodeError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt == max_attempts - 1:
                raise RuntimeError(f"SYCM request failed after {max_attempts} attempts: {last_error}") from exc
    raise RuntimeError(f"SYCM request failed after retries: {last_error}")


def _period(day: date, date_type: str) -> tuple[str, str]:
    end = day
    if date_type == "day":
        start = day
    elif date_type == "recent7":
        start = day - timedelta(days=6)
    elif date_type == "recent30":
        start = day - timedelta(days=29)
    else:
        raise ValueError("date_type must be day, recent7, or recent30")
    return start.isoformat(), end.isoformat()


def _base_params(start: str, end: str, date_type: str) -> dict[str, str]:
    return {
        "dateRange": f"{start}|{end}",
        "dateType": date_type,
        "pageSize": "100",
        "page": "1",
        "marketVersion": "free",
        "cateId": CATE_ID,
    }


def collect_rankings(*, day: date, date_type: str, cookie: str, max_attempts: int, request_delay: float) -> list[dict[str, Any]]:
    start, end = _period(day, date_type)
    referer = f"https://sycm.taobao.com/mc/free/market_rank?dateRange={start}%7C{end}&dateType={date_type}&parentCateId={PARENT_CATE_ID}&cateId={CATE_ID}&cateFlag={CATE_FLAG}"
    specs = (
        ("item", "/mc/mq/mkt/item/offline/rank.json", {"rankType": "gmv", "minPrice": "", "maxPrice": "", "priceSeg": "", "sellerType": "-1", "keyWord": "", "cateFlag": CATE_FLAG, "indexCode": "payByrCnt,uv"}),
        ("shop", "/mc/mq/mkt/shop/offline/rank.json", {"priceSeg": "", "rankType": "gmv", "sellerType": "-1", "cateFlag": CATE_FLAG, "keyWord": ""}),
        ("content", "/mc/mq/mkt/content/rank.json", {"rankType": "tradeLive", "cateFlag": CATE_FLAG}),
    )
    rows: list[dict[str, Any]] = []
    for rank_type, path, extra in specs:
        page = 1
        while True:
            payload = _request_json(path, {**_base_params(start, end, date_type), **extra, "page": str(page)}, cookie=cookie, referer=referer, max_attempts=max_attempts, request_delay=request_delay)
            data = payload.get("data") or {}
            page_rows = data.get("data") or []
            for raw in page_rows:
                if rank_type == "item":
                    item, shop = raw.get("item") or {}, raw.get("shop") or {}
                    entity_id, entity_name = _v(raw.get("itemId")), _v(item.get("title"))
                    row = dict(entity_type="item", entity_id=entity_id, entity_name=entity_name, shop_id=_v(raw.get("item", {}).get("userId") or shop.get("userId")), shop_name=_v(shop.get("title")), keyword=_v(raw.get("coreKeyWord")), paid_buyers_range=_v(raw.get("payByrCnt")), visitors_range=_v(raw.get("uv")), sale_item_count=None, content_id=None, content_title=None, content_start_time=None, fan_count_range=None, grass_paid_amount_range=None, goods_clicks_range=None, live_views_range=None, rank_change=None)
                elif rank_type == "shop":
                    shop = raw.get("shop") or {}
                    entity_id, entity_name = _v(raw.get("sellerId") or shop.get("userId")), _v(shop.get("title"))
                    row = dict(entity_type="shop", entity_id=entity_id, entity_name=entity_name, shop_id=entity_id, shop_name=entity_name, keyword=None, paid_buyers_range=_v(raw.get("payByrCnt")), visitors_range=_v(raw.get("uv")), sale_item_count=_num(raw.get("saleItemCnt")), content_id=None, content_title=None, content_start_time=None, fan_count_range=None, grass_paid_amount_range=None, goods_clicks_range=None, live_views_range=None, rank_change=None)
                else:
                    shop = raw.get("shop") or {}
                    entity_id, entity_name = _v(raw.get("contentId")), _v(raw.get("sessionTitle"))
                    row = dict(entity_type="content", entity_id=entity_id, entity_name=entity_name, shop_id=_v(raw.get("sellerId") or shop.get("userId")), shop_name=_v(shop.get("title")), keyword=None, paid_buyers_range=None, visitors_range=None, sale_item_count=None, content_id=entity_id, content_title=_v(raw.get("sessionTitle")), content_start_time=_v(raw.get("startTime")), fan_count_range=_v(raw.get("vermicelliCnt")), grass_paid_amount_range=_v(raw.get("grassPayOrdAmt")), goods_clicks_range=_v(raw.get("goodsClickPv")), live_views_range=_v(raw.get("liveLookPv")), rank_change=None)
                rank_obj = raw.get("cateRankId") or {}
                if isinstance(rank_obj, dict):
                    rank_no, row["rank_change"] = _num(rank_obj.get("value")), _num(rank_obj.get("cycleCqc"))
                else:
                    rank_no = _num(rank_obj)
                row.update(stat_start=start, stat_end=end, date_type=date_type, parent_cate_id=PARENT_CATE_ID, cate_id=CATE_ID, cate_flag=CATE_FLAG, rank_type=rank_type, rank_metric="gmv" if rank_type != "content" else "tradeLive", rank_no=rank_no, raw_json=json.dumps(raw, ensure_ascii=False))
                rows.append(row)
            if not page_rows or len(rows) >= 900 or page * 100 >= int(data.get("recordCount") or 0):
                break
            page += 1
    return rows


def collect_keywords(*, day: date, date_type: str, cookie: str, max_attempts: int, request_delay: float) -> list[dict[str, Any]]:
    start, end = _period(day, date_type)
    referer = f"https://sycm.taobao.com/mc/free/search_rank?dateRange={start}%7C{end}&dateType={date_type}&cateId={CATE_ID}&cateFlag={CATE_FLAG}"
    rows: list[dict[str, Any]] = []
    # SYCM uses ``prop`` for the UI's "修饰词" tab. Keep the warehouse
    # vocabulary as ``modify`` so downstream consumers do not depend on the
    # platform's internal parameter name.
    for api_kw_type, kw_type in (("search", "search"), ("trend", "trend"), ("core", "core"), ("prop", "modify")):
        page = 1
        while True:
            params = {**_base_params(start, end, date_type), "order": "desc", "orderBy": "seIpvUvHits", "kwType": api_kw_type, "rankType": "hot", "keyWord": "", "device": "0", "page": str(page)}
            payload = _request_json("/mc/mq/mkt/keyword/rank/pro.json", params, cookie=cookie, referer=referer, max_attempts=max_attempts, request_delay=request_delay)
            data = payload.get("data") or {}
            page_rows = data.get("data") or []
            for raw in page_rows:
                rows.append(dict(stat_start=start, stat_end=end, date_type=date_type, parent_cate_id=PARENT_CATE_ID, cate_id=CATE_ID, cate_flag=CATE_FLAG, keyword_type=kw_type, rank_metric="hot", rank_no=_num(raw.get("rn")), keyword=_v(raw.get("searchWord")), search_popularity_range=_v(raw.get("seIpvUvHits")), click_rate=_v(raw.get("clickThroughRate") or raw.get("freeClkRate")), pay_conversion_rate=_v(raw.get("payRate")), raw_json=json.dumps(raw, ensure_ascii=False)))
            if not page_rows or page * 100 >= int(data.get("recordCount") or 0):
                break
            page += 1
    return rows


def _schema(conn: sqlite3.Connection) -> None:
    conn.execute(f"""create table if not exists {MARKET_TABLE} (
        stat_start text not null, stat_end text not null, date_type text not null,
        parent_cate_id text not null, cate_id text not null, cate_flag text not null,
        rank_type text not null, rank_metric text not null, rank_no integer not null,
        rank_change integer, entity_type text not null, entity_id text,
        entity_name text, shop_id text, shop_name text, keyword text,
        paid_buyers_range text, visitors_range text, sale_item_count integer,
        content_id text, content_title text, content_start_time text,
        fan_count_range text, grass_paid_amount_range text, goods_clicks_range text,
        live_views_range text, raw_json text not null, fetched_at text not null,
        primary key(stat_start, stat_end, date_type, cate_id, rank_type, rank_metric, rank_no, entity_id)
    )""")
    conn.execute(f"""create table if not exists {KEYWORD_TABLE} (
        stat_start text not null, stat_end text not null, date_type text not null,
        parent_cate_id text not null, cate_id text not null, cate_flag text not null,
        keyword_type text not null, rank_metric text not null, rank_no integer not null,
        keyword text not null, search_popularity_range text, click_rate text,
        pay_conversion_rate text, raw_json text not null, fetched_at text not null,
        primary key(stat_start, stat_end, date_type, cate_id, keyword_type, rank_metric, rank_no)
    )""")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", type=date.fromisoformat, help="Collect one day (legacy shortcut).")
    parser.add_argument("--start", type=date.fromisoformat, help="First business day, inclusive.")
    parser.add_argument("--end", type=date.fromisoformat, help="Last business day, inclusive.")
    parser.add_argument("--date-type", choices=("day", "recent7", "recent30"), default="day")
    parser.add_argument("--session-source", choices=("env", "drissionpage"), default="drissionpage")
    parser.add_argument("--cookie-env", default="SYCM_COOKIE")
    parser.add_argument("--browser-port", type=int, default=9222)
    parser.add_argument("--database", type=Path, default=Path(settings.local_database_path))
    parser.add_argument("--skip-existing", action="store_true", help="Skip dates already having both market and keyword rows.")
    parser.add_argument("--max-attempts", type=int, default=8, help="Maximum attempts for each SYCM request.")
    parser.add_argument("--request-delay", type=float, default=1.2, help="Delay after each successful request to reduce rate limiting.")
    parser.add_argument("--continue-on-error", action="store_true", help="Record failed dates and continue with the remaining range.")
    args = parser.parse_args()
    if args.day is not None and (args.start is not None or args.end is not None):
        parser.error("--day cannot be combined with --start/--end")
    if args.day is not None:
        start_day = end_day = args.day
    else:
        start_day = args.start or date(2026, 5, 1)
        end_day = args.end or date.today()
    if end_day < start_day:
        parser.error("--end must be greater than or equal to --start")
    session = resolve_runtime_session(source=args.session_source, cookie_env=args.cookie_env, browser_port=args.browser_port)
    args.database.parent.mkdir(parents=True, exist_ok=True)
    if args.max_attempts < 1:
        parser.error("--max-attempts must be at least 1")
    if args.request_delay < 0:
        parser.error("--request-delay must be non-negative")
    total_market = total_keywords = 0
    failed_days: list[dict[str, str]] = []
    current = start_day
    while current <= end_day:
        if args.skip_existing:
            with sqlite3.connect(args.database) as conn:
                market_exists = conn.execute(
                    f"select 1 from {MARKET_TABLE} where stat_start=? and stat_end=? and date_type=? and cate_id=? limit 1",
                    (*_period(current, args.date_type), args.date_type, CATE_ID),
                ).fetchone()
                keyword_exists = conn.execute(
                    f"select 1 from {KEYWORD_TABLE} where stat_start=? and stat_end=? and date_type=? and cate_id=? limit 1",
                    (*_period(current, args.date_type), args.date_type, CATE_ID),
                ).fetchone()
            if market_exists and keyword_exists:
                print(json.dumps({"day": current.isoformat(), "status": "skipped_existing"}, ensure_ascii=False), flush=True)
                current += timedelta(days=1)
                continue
        try:
            rankings = collect_rankings(day=current, date_type=args.date_type, cookie=session.cookie_header, max_attempts=args.max_attempts, request_delay=args.request_delay)
            keywords = collect_keywords(day=current, date_type=args.date_type, cookie=session.cookie_header, max_attempts=args.max_attempts, request_delay=args.request_delay)
        except Exception as exc:
            failure = {"day": current.isoformat(), "status": "retry_pending", "error": str(exc)}
            failed_days.append(failure)
            print(json.dumps(failure, ensure_ascii=False), flush=True)
            if not args.continue_on_error:
                raise
            current += timedelta(days=1)
            continue
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(args.database) as conn:
            _schema(conn)
            conn.execute(f"delete from {MARKET_TABLE} where stat_start=? and stat_end=? and date_type=? and cate_id=?", (*_period(current, args.date_type), args.date_type, CATE_ID))
            conn.execute(f"delete from {KEYWORD_TABLE} where stat_start=? and stat_end=? and date_type=? and cate_id=?", (*_period(current, args.date_type), args.date_type, CATE_ID))
            market_cols = "stat_start,stat_end,date_type,parent_cate_id,cate_id,cate_flag,rank_type,rank_metric,rank_no,rank_change,entity_type,entity_id,entity_name,shop_id,shop_name,keyword,paid_buyers_range,visitors_range,sale_item_count,content_id,content_title,content_start_time,fan_count_range,grass_paid_amount_range,goods_clicks_range,live_views_range,raw_json"
            conn.executemany(f"insert into {MARKET_TABLE} ({market_cols},fetched_at) values ({','.join('?' for _ in market_cols.split(','))},?)", [tuple(row.get(c) for c in market_cols.split(',')) + (now,) for row in rankings])
            kw_cols = "stat_start,stat_end,date_type,parent_cate_id,cate_id,cate_flag,keyword_type,rank_metric,rank_no,keyword,search_popularity_range,click_rate,pay_conversion_rate,raw_json"
            conn.executemany(f"insert into {KEYWORD_TABLE} ({kw_cols},fetched_at) values ({','.join('?' for _ in kw_cols.split(','))},?)", [tuple(row.get(c) for c in kw_cols.split(',')) + (now,) for row in keywords])
            conn.commit()
        total_market += len(rankings)
        total_keywords += len(keywords)
        print(json.dumps({"day": current.isoformat(), "market_rows": len(rankings), "keyword_rows": len(keywords)}, ensure_ascii=False), flush=True)
        current += timedelta(days=1)
    print(json.dumps({"database": str(args.database), "market_rows": total_market, "keyword_rows": total_keywords, "start": start_day.isoformat(), "end": end_day.isoformat(), "category": CATE_ID, "failed_days": failed_days, "status": "partial" if failed_days else "complete"}, ensure_ascii=False, indent=2))
    return 2 if failed_days else 0


if __name__ == "__main__":
    raise SystemExit(main())
