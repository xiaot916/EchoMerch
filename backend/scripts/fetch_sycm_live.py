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
    resolve_runtime_session,
)


LIVE_OVERVIEW_URL = "https://sycm.taobao.com/s_content/shop/broadcast/amount/compose/overview.json"
LIVE_STORE_URL = "https://sycm.taobao.com/s_content/shop/broadcast/click/transform.json"
LIVE_TALENT_URL = "https://sycm.taobao.com/s_content/live/cooperate/room/list.json"


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


def fetch_live_overview(*, day: date, output: Path, cookie: str, token: str = "", timeout: int = 30) -> FetchResult:
    return _fetch(
        url=LIVE_OVERVIEW_URL,
        params=_date_params(day, token),
        output=output,
        cookie=cookie,
        referer="https://sycm.taobao.com/xsite/frame/live",
        timeout=timeout,
    )


def fetch_live_store_performance(*, day: date, output: Path, cookie: str, token: str = "", timeout: int = 30) -> FetchResult:
    return _fetch(
        url=LIVE_STORE_URL,
        params=_date_params(day, token),
        output=output,
        cookie=cookie,
        referer="https://sycm.taobao.com/xsite/frame/live",
        timeout=timeout,
    )


def fetch_live_talent_page(
    *,
    day: date,
    output: Path,
    cookie: str,
    page: int,
    page_size: int,
    token: str = "",
    timeout: int = 30,
) -> FetchResult:
    params = {
        **_date_params(day, token),
        "pageSize": str(page_size),
        "page": str(page),
        "order": "desc",
        "orderBy": "liveSessionCount",
        "coopActId": "",
    }
    return _fetch(
        url=LIVE_TALENT_URL,
        params=params,
        output=output,
        cookie=cookie,
        referer="https://sycm.taobao.com/xsite/frame/live",
        timeout=timeout,
    )


def _date_params(day: date, token: str) -> dict[str, str]:
    params = {
        "dateType": "day",
        "dateRange": f"{day.isoformat()}|{day.isoformat()}",
        "_": str(int(time.time() * 1000)),
    }
    if token:
        params["token"] = token
    return params


def _fetch(*, url: str, params: dict[str, str], output: Path, cookie: str, referer: str, timeout: int) -> FetchResult:
    request = Request(
        f"{url}?{urlencode(params)}",
        headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "bx-v": "2.5.37",
            "cache-control": "no-cache",
            "cookie": cookie,
            "referer": referer,
            "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sycm-referer": "/xsite/frame/live",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/150.0.0.0 Safari/537.36"
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
    try:
        payload = json.loads(body.decode("utf-8"))
        normalized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        code = _as_int(payload.get("code")) if isinstance(payload, dict) else None
        message = str(payload.get("message") or payload.get("msg") or "") or None if isinstance(payload, dict) else "unexpected response payload"
    except (UnicodeDecodeError, json.JSONDecodeError):
        normalized = body
        code = None
        message = "non-json response"
    output.write_bytes(normalized)
    return FetchResult(status, code, message, str(output), len(normalized))


def _as_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch one day of SYCM live data.")
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--overview-output", type=Path, required=True)
    parser.add_argument("--store-output", type=Path, required=True)
    parser.add_argument("--talent-output", type=Path, required=True)
    parser.add_argument("--token", default=os.getenv("SYCM_TOKEN", ""))
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=30)
    add_session_source_arguments(parser)
    args = parser.parse_args()
    session = resolve_runtime_session(source=args.session_source, cookie_env=args.cookie_env, browser_port=args.browser_port)
    overview = fetch_live_overview(day=args.day, output=args.overview_output, cookie=session.cookie_header, token=args.token, timeout=args.timeout)
    store = fetch_live_store_performance(day=args.day, output=args.store_output, cookie=session.cookie_header, token=args.token, timeout=args.timeout)
    talent = fetch_live_talent_page(day=args.day, output=args.talent_output, cookie=session.cookie_header, page=1, page_size=args.page_size, token=args.token, timeout=args.timeout)
    print(json.dumps({"overview": asdict(overview), "store": asdict(store), "talent": asdict(talent)}, ensure_ascii=False, indent=2))
    return 0 if overview.ok and store.ok and talent.ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"Live fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
