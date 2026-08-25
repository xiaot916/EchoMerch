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

from app.integrations.tmall_session import add_session_source_arguments, resolve_runtime_session  # noqa: E402


ITEM_RANK_INDEX_CODES = ",".join(
    [
        "payAmt",
        "subPayOrdAmt",
        "sucRefundAmt",
        "payItmCnt",
        "subPayOrdItmQty",
        "payByrCnt",
        "payRate",
        "newPayByrCnt",
        "payOldByrCnt",
        "olderPayAmt",
        "juPayAmt",
        "mtdPayAmt",
        "mtdPayItmCnt",
        "ytdPayAmt",
        "itemStatus",
        "itemCartCnt",
        "itemCartByrCnt",
        "itemCltByrCnt",
        "visitCartRate",
        "visitCltRate",
        "itmUv",
        "itmPv",
        "itmStayTime",
        "itmBounceRate",
        "seGuideUv",
        "seGuidePayByrCnt",
        "seGuidePayRate",
        "uvAvgValue",
        "starLevel001",
        "itemUnitPrice1",
        "fCharge",
        "pDROI",
    ]
)


def fetch_item_ranking(
    *,
    day: date,
    output: Path,
    cookie: str,
    token: str = "",
    page: int = 1,
    page_size: int = 10,
    timeout: int = 30,
) -> tuple[int, int | None, str | None, int]:
    params = {
        "dateRange": f"{day.isoformat()}|{day.isoformat()}",
        "dateType": "day",
        "pageSize": str(page_size),
        "page": str(page),
        "order": "desc",
        "orderBy": "payAmt",
        "device": "0",
        "compareType": "cycle",
        "keyword": "",
        "follow": "false",
        "cateId": "",
        "cateLevel": "",
        "indexCode": ITEM_RANK_INDEX_CODES,
        "_": str(int(time.time() * 1000)),
    }
    if token:
        params["token"] = token

    url = f"https://sycm.taobao.com/cc/item/view/top.json?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "bx-v": "2.5.37",
            "cache-control": "no-cache",
            "cookie": cookie,
            "referer": (
                "https://sycm.taobao.com/cc/item_rank?"
                f"dateRange={day.isoformat()}%7C{day.isoformat()}&dateType=day"
            ),
            "sec-ch-ua": '"Not=A?Brand";v="99", "Google Chrome";v="151", "Chromium";v="151"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sycm-referer": "/cc/item_rank",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36"
            ),
        },
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
    except HTTPError as exc:
        body = exc.read()
        status = exc.code

    output.write_bytes(body)
    code, message = _response_status(body)
    return status, code, message, len(body)


def _response_status(body: bytes) -> tuple[int | None, str | None]:
    try:
        payload: Any = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "non-json response"
    if not isinstance(payload, dict):
        return None, "unexpected response payload"
    return _as_int(payload.get("code")), _as_text(payload.get("message") or payload.get("msg"))


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str | None:
    return None if value is None else str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch one page of the SYCM item ranking with runtime cookies.")
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--token", default=os.getenv("SYCM_TOKEN", ""))
    parser.add_argument("--timeout", type=int, default=30)
    add_session_source_arguments(parser)
    args = parser.parse_args()

    if args.page < 1:
        raise ValueError("--page must be at least 1.")
    if not 1 <= args.page_size <= 100:
        raise ValueError("--page-size must be between 1 and 100.")

    session = resolve_runtime_session(
        source=args.session_source,
        cookie_env=args.cookie_env,
        browser_port=args.browser_port,
    )
    status, code, message, body_size = fetch_item_ranking(
        day=args.day,
        output=args.output,
        cookie=session.cookie_header,
        token=args.token,
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
