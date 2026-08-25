from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.tmall_session import (  # noqa: E402
    add_session_source_arguments,
    resolve_alimama_runtime_context,
)


ALIMAMA_REPORT_URL = "https://one.alimama.com/report/query.json"
ALIMAMA_REPORT_HOME = "https://one.alimama.com/index.html#!/report/campaign?rptType=campaign"
ADGROUP_REPORT_FIELDS = (
    "adPv",
    "click",
    "charge",
    "ctr",
    "ecpc",
    "alipayInshopAmt",
    "alipayInshopNum",
    "cvr",
    "cartInshopNum",
    "itemColInshopNum",
    "shopColDirNum",
    "colNum",
    "itemColInshopCost",
)
BIDWORD_REPORT_FIELDS = (
    "adPv",
    "click",
    "ctr",
    "charge",
    "ecpc",
    "wwNum",
    "cartDirNum",
    "cartInshopNum",
    "colNum",
    "cartRate",
    "cartCost",
    "alipayDirNum",
    "alipayInshopNum",
    "alipayDirAmt",
    "alipayInshopAmt",
    "alipayInshopUv",
    "alipayInshopAmtAvg",
    "roi",
    "alipayInshopCost",
    "rhNum",
    "rhRate",
    "hySgUv",
    "hyPayAmt",
    "newAlipayInshopUv",
    "newAlipayInshopUvRate",
)
CROWD_REPORT_FIELDS = (
    "adPv",
    "click",
    "ctr",
    "charge",
    "ecpc",
    "wwNum",
    "cartDirNum",
    "cartInshopNum",
    "colNum",
    "cartRate",
    "cartCost",
    "alipayDirNum",
    "alipayInshopNum",
    "alipayDirAmt",
    "alipayInshopAmt",
    "roi",
    "alipayInshopCost",
    "cvr",
    "alipayInshopAmtAvg",
    "rhNum",
    "rhRate",
    "hySgUv",
    "hyPayAmt",
    "newAlipayInshopUv",
    "newAlipayInshopUvRate",
)
CAMPAIGN_REPORT_FIELDS = (
    "charge",
    "click",
    "ecpc",
    "ctr",
    "cartInshopNum",
    "cartRate",
    "alipayInshopNum",
    "alipayInshopAmt",
    "roi",
    "colNum",
    "adPv",
    "itemColInshopRate",
    "ecpm",
    "prepayInshopAmt",
    "prepayInshopNum",
    "prepayDirAmt",
    "prepayDirNum",
    "prepayIndirAmt",
    "prepayIndirNum",
    "gmvInshopNum",
    "gmvInshopAmt",
    "alipayDirAmt",
    "alipayIndirAmt",
    "alipayDirNum",
    "alipayIndirNum",
    "cvr",
    "alipayInshopCost",
    "inshopPotentialUv",
    "alipayInshopUv",
    "alipayInshopNumAvg",
    "alipayInshopAmtAvg",
    "cartDirNum",
    "cartIndirNum",
    "itemColInshopNum",
    "shopColDirNum",
    "shopColInshopCost",
    "colCartNum",
    "colCartCost",
    "itemColCart",
    "itemColCartCost",
    "itemColInshopCost",
    "cartCost",
    "itemColDirNum",
    "itemColIndirNum",
    "couponShopNum",
    "shoppingNum",
    "shoppingAmt",
    "wwNum",
    "inshopPv",
    "inshopUv",
    "inshopPotentialUvRate",
    "inshopPvRate",
    "deepInshopPv",
    "avgAccessPageNum",
    "rhRate",
    "rhNum",
    "hySgUv",
    "hyPayAmt",
    "hyPayNum",
    "newAlipayInshopUv",
    "newAlipayInshopUvRate",
    "naturalPayAmt",
    "orgNaturalPv",
)
CAMPAIGN_FALLBACK_BIZ_CODES = (
    "onebpSearch",
    "onebpSite",
    "onebpShortVideo",
    "onebpDisplay",
    "onebpLive",
)
REPORT_CONFIG = {
    "adgroup": {
        "fields": ADGROUP_REPORT_FIELDS,
        "domains": ("adgroup", "date", "campaign"),
        "biz_codes": ("onebpSearch",),
        "by_page_without_count": False,
    },
    "bidword": {
        "fields": BIDWORD_REPORT_FIELDS,
        "domains": ("word", "date", "campaign", "adgroup"),
        "biz_codes": ("onebpSearch",),
        "by_page_without_count": True,
        "extra_body": {
            "isKeyWordNotContainChase": "true",
        },
    },
    "campaign": {
        "fields": CAMPAIGN_REPORT_FIELDS,
        "domains": ("campaign",),
        "biz_codes": None,
        "fallback_biz_codes": CAMPAIGN_FALLBACK_BIZ_CODES,
    },
    "crowd": {
        "fields": CROWD_REPORT_FIELDS,
        "domains": ("crowd", "promotion", "date", "campaign", "adgroup"),
        "biz_codes": None,
        "by_page_without_count": True,
        "extra_body": {
            "filterAppendSubwayChannel": True,
            "filterNullCrowdSubwayTag": True,
        },
    },
    "item_promotion": {
        "fields": (
            "adPv", "click", "ctr", "charge", "ecpc", "wwNum", "cartDirNum",
            "cartInshopNum", "colNum", "cartRate", "cartCost", "alipayDirNum",
            "alipayInshopNum", "alipayDirAmt", "alipayInshopAmt", "cvr", "roi",
            "alipayInshopCost", "alipayInshopUv", "alipayInshopNumAvg",
            "alipayInshopAmtAvg", "rhNum", "rhRate", "hySgUv", "hyPayNum",
            "hyPayAmt", "newAlipayInshopUv", "newAlipayInshopUvRate",
            "naturalPayAmt", "orgNaturalPv",
        ),
        "domains": ("promotion", "campaign", "date"),
        "biz_codes": None,
        "extra_body": {"subPromotionTypes": ["ITEM"]},
    },
    "other_promotion": {
        "fields": (
            "adPv", "click", "charge", "ctr", "ecpc", "alipayInshopAmt",
            "alipayInshopNum", "cvr", "cartInshopNum", "itemColInshopNum",
            "shopColDirNum", "colNum", "itemColInshopCost",
        ),
        "domains": ("promotion", "date", "campaign"),
        "biz_codes": None,
        "extra_body": {
            "strategySubPromotionTypeNotIn": ["11"],
            "needCountAccelerate": False,
        },
    },
}


def alimama_report_home(rpt_type: str) -> str:
    if rpt_type == "bidword":
        return (
            "https://one.alimama.com/index.html#!/report/bidword?"
            "rptType=bidword&queryDomains=%5B%22word%22%2C%22campaign%22%2C%22date%22%2C%22adgroup%22%5D"
        )
    if rpt_type == "crowd":
        return "https://one.alimama.com/index.html#!/report/crowd?rptType=crowd"
    return ALIMAMA_REPORT_HOME


def fetch_alimama_report(
    *,
    start_day: date,
    end_day: date,
    output: Path,
    cookie: str,
    csrf_id: str,
    login_point_id: str,
    rpt_type: str = "adgroup",
    query_fields: tuple[str, ...] = ADGROUP_REPORT_FIELDS,
    query_domains: tuple[str, ...] = ("adgroup", "date", "campaign"),
    biz_codes: tuple[str, ...] | None = ("onebpSearch",),
    by_page_without_count: bool = False,
    extra_body: dict[str, Any] | None = None,
    offset: int = 0,
    page_size: int = 20,
    page: int = 1,
    timeout: int = 30,
) -> tuple[int, int | None, str | None, int]:
    query = {
        "csrfId": csrf_id,
        "bizCode": "universalBP",
    }
    body = {
        "bizCode": "universalBP",
        "fromRealTime": False,
        "source": "baseReport",
        "byPage": True,
        "totalTag": True,
        "needCountAccelerate": True,
        "byPageWithoutCount": by_page_without_count,
        "rptType": rpt_type,
        "pageSize": page_size,
        "havingList": [],
        "endTime": end_day.isoformat(),
        "from": "pcBaseReport",
        "unifyType": "zhai",
        "effectEqual": 15,
        "startTime": start_day.isoformat(),
        "splitType": "day",
        "queryFieldIn": list(query_fields),
        "queryDomains": list(query_domains),
        "csrfId": csrf_id,
        "loginPointId": login_point_id,
    }
    if biz_codes:
        body["bizCodeIn"] = list(biz_codes)
    if extra_body:
        body.update(extra_body)
    if offset > 0 or rpt_type in {"bidword", "crowd"}:
        body["offset"] = offset
    request = Request(
        f"{ALIMAMA_REPORT_URL}?{urlencode(query)}",
        data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        method="POST",
        headers={
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "zh-CN,zh;q=0.9",
            "bx-v": "2.5.37",
            "content-type": "application/json",
            "cookie": cookie,
            "origin": "https://one.alimama.com",
            "referer": "https://one.alimama.com/index.html",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36"
            ),
            "x-requested-with": "XMLHttpRequest",
        },
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urlopen(request, timeout=timeout) as response:
            response_body = response.read()
            status = response.status
    except HTTPError as exc:
        response_body = exc.read()
        status = exc.code

    output.write_bytes(response_body)
    code, message = _response_status(response_body)
    return status, code, message, len(response_body)


def _response_status(response_body: bytes) -> tuple[int | None, str | None]:
    try:
        payload: Any = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "non-json response"
    if not isinstance(payload, dict):
        return None, "unexpected response payload"
    info = payload.get("info")
    if isinstance(info, dict) and info.get("ok") is True:
        return 0, _as_text(info.get("message") or info.get("msg"))
    for value in (payload, payload.get("data"), payload.get("content")):
        if isinstance(value, dict) and value.get("code") is not None:
            return _as_int(value.get("code")), _as_text(value.get("message") or value.get("msg"))
    return None, _as_text(payload.get("message") or payload.get("msg"))


def _as_int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str | None:
    return None if value is None else str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch one Alimama universalBP report page.")
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rpt-type", choices=sorted(REPORT_CONFIG), default="adgroup")
    parser.add_argument("--csrf-id", default=os.getenv("RTB_CSRF_ID", ""))
    parser.add_argument("--login-point-id", default=os.getenv("RTB_LOGIN_POINT_ID", ""))
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=30)
    add_session_source_arguments(parser)
    args = parser.parse_args()

    if args.end < args.start:
        raise ValueError("--end must be greater than or equal to --start.")
    if args.page < 1 or args.offset < 0 or not 1 <= args.page_size <= 100:
        raise ValueError(
            "--page must be at least 1, --offset cannot be negative, "
            "and --page-size must be between 1 and 100."
        )

    config = REPORT_CONFIG[args.rpt_type]

    runtime = resolve_alimama_runtime_context(
        source=args.session_source,
        cookie_env=args.cookie_env,
        csrf_id=args.csrf_id,
        login_point_id=args.login_point_id,
        browser_port=args.browser_port,
        report_home_url=alimama_report_home(args.rpt_type),
        timeout=args.timeout,
    )
    status, code, message, body_size = fetch_alimama_report(
        start_day=args.start,
        end_day=args.end,
        output=args.output,
        cookie=runtime.session.cookie_header,
        csrf_id=runtime.csrf_id,
        login_point_id=runtime.login_point_id,
        rpt_type=args.rpt_type,
        query_fields=config["fields"],
        query_domains=config["domains"],
        biz_codes=config["biz_codes"],
        by_page_without_count=bool(config.get("by_page_without_count", False)),
        extra_body=config.get("extra_body"),
        offset=args.offset,
        page=args.page,
        page_size=args.page_size,
        timeout=args.timeout,
    )
    print(
        json.dumps(
            {
                "status": status,
                "code": code,
                "message": message,
                "output": str(args.output),
                "bytes": body_size,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if 200 <= status < 300 and code == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"Fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
