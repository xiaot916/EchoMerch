from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.tmall_session import (  # noqa: E402
    add_session_source_arguments,
    resolve_bybt_runtime_context,
)


INDEX_CODES = ",".join((
    "bybtCateFullName", "bybtPayAmt", "bybtPayOrdQty", "bybtPayOrdCntNew", "bybtItemUv",
    "bybtCvr", "businessScenario", "salesMethod", "raceType", "playType",
))


@dataclass(frozen=True)
class FetchResult:
    status: int
    code: int | None
    message: str | None
    output: str
    bytes: int

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and self.code == 0


def fetch_sycm_bybt_items(
    *, day: date, output: Path, cookie: str, token: str = "", page: int = 1,
    page_size: int = 50, timeout: int = 30,
) -> FetchResult:
    params = {
        "dateRange": f"{day.isoformat()}|{day.isoformat()}", "dateType": "day",
        "pageSize": str(page_size), "page": str(page), "salesMethod": "", "itemId": "",
        "raceType": "", "playType": "", "juId": "", "activityType": "", "bybtCateId": "",
        "indexCode": INDEX_CODES, "_": str(int(time.time() * 1000)),
    }
    if token:
        params["token"] = token
    request = Request(
        "https://sycm.taobao.com/mc/bybt/sellerData/item/list.json?" + urlencode(params),
        headers={
            "accept": "*/*", "accept-language": "zh-CN,zh;q=0.9,en;q=0.8", "bx-v": "2.5.37",
            "cache-control": "no-cache", "cookie": cookie,
            "referer": "https://sycm.taobao.com/xsite/frame/bybt?from=bybtzd",
            "sec-fetch-dest": "empty", "sec-fetch-mode": "cors", "sec-fetch-site": "same-origin",
            "sycm-referer": "/xsite/frame/bybt",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
        },
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urlopen(request, timeout=timeout) as response:
            body, status = response.read(), response.status
    except HTTPError as exc:
        body, status = exc.read(), exc.code
    try:
        payload = json.loads(body.decode("utf-8"))
        normalized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        code = _as_int(payload.get("code")) if isinstance(payload, dict) else None
        message = str(payload.get("message") or payload.get("msg") or "") or None if isinstance(payload, dict) else "unexpected response payload"
    except (UnicodeDecodeError, json.JSONDecodeError):
        normalized, code, message = body, None, "non-json response"
    output.write_bytes(normalized)
    return FetchResult(status, code, message, str(output), len(normalized))


def _as_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch one page of SYCM BYBT item data.")
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--token", default=os.getenv("SYCM_TOKEN", ""))
    parser.add_argument("--timeout", type=int, default=30)
    add_session_source_arguments(parser)
    args = parser.parse_args()
    if args.page < 1 or not 1 <= args.page_size <= 100:
        raise ValueError("page must be positive and page-size must be 1..100")
    runtime = resolve_bybt_runtime_context(
        source=args.session_source,
        cookie_env=args.cookie_env,
        token=args.token,
        browser_port=args.browser_port,
        timeout=args.timeout,
    )
    result = fetch_sycm_bybt_items(
        day=args.day,
        output=args.output,
        cookie=runtime.session.cookie_header,
        token=runtime.token,
        page=args.page,
        page_size=args.page_size,
        timeout=args.timeout,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
