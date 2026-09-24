from __future__ import annotations

"""Fetch SYCM home board (增长因子 / 月度经营 / 体验分 / 类目) for one business day.

All endpoints use the standard jycmToken + cookie session, mirroring the
``fetch_sycm_overview`` request contract. The response files are parsed by
``app.warehouse.sycm_home_board``.
"""

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.tmall_session import add_session_source_arguments, resolve_runtime_session  # noqa: E402


SENSITIVE_KEYS = {"token", "cookie", "authorization"}
REFERER = "https://sycm.taobao.com/portal/home.htm"


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


def _build_request(
    url: str,
    *,
    cookie: str,
    token: str,
) -> Request:
    params = {"_": str(int(time.time() * 1000))}
    if token:
        params["token"] = token
    full_url = f"{url}?{urlencode(params)}" if "?" not in url else url
    return Request(
        full_url,
        headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "bx-v": "2.5.37",
            "cache-control": "no-cache",
            "cookie": cookie,
            "onetrace-card-id": "pc%E6%96%B0%E9%A6%96%E9%A1%B5%7C%E6%95%B0%E6%8D%AE%E6%A6%82%E8%A7%88",
            "pragma": "no-cache",
            "referer": REFERER,
            "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sycm-referer": "/portal/home.htm",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/150.0.0.0 Safari/537.36"
            ),
        },
    )


def _fetch_one(
    url: str,
    *,
    output: Path,
    cookie: str,
    token: str,
    timeout: int = 30,
) -> FetchResult:
    output.parent.mkdir(parents=True, exist_ok=True)
    request = _build_request(url, cookie=cookie, token=token)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
    except HTTPError as exc:
        body = exc.read()
        status = exc.code

    try:
        payload: Any = json.loads(body.decode("utf-8"))
        output_body = json.dumps(
            _scrub_sensitive(payload),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        code, message = _response_code_and_message(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        output_body = body
        code = None
        message = "non-json response"

    output.write_bytes(output_body)
    return FetchResult(
        status=status,
        code=code,
        message=message,
        output=str(output),
        bytes=len(output_body),
    )


def fetch_sycm_home_board(
    *,
    day: date,
    output_dir: Path,
    cookie: str,
    token: str = "",
    timeout: int = 30,
) -> dict[str, FetchResult]:
    """Fetch the home-board endpoint group for one business day."""
    day_str = day.isoformat()
    range_url = f"{day_str}%7C{day_str}"
    # `portal/month/trend.json` is a rolling 30-day series that always ends on
    # the *previous* closed day, so it rejects a range whose end date is the
    # requested (not yet closed) business day:
    #   month_trend: HTTP 200, code 1009, validate end date error,
    #   Params: statDate=2026-09-18, endDate=2026-09-19
    # Verified 2026-09-20 against captured responses: requesting 09-18 returns
    # statDate 08-19..09-17; requesting 09-19 returns 08-20..09-18 — i.e. the
    # series lags the request by one day, and asking for today is invalid.
    # The warehouse parser skips the `statDate` dimension and attributes every
    # metric to the requested business_day, so shifting this one request back a
    # day only removes the invalid end date; it does not move the stored rows.
    month_trend_end = (day - timedelta(days=1)).isoformat()
    month_trend_range = f"{month_trend_end}%7C{month_trend_end}"
    base = "https://sycm.taobao.com"

    endpoints: dict[str, str] = {
        "grow_factor": f"{base}/portal/board/grow/factor/overview.json?dateType=day&dateRange={range_url}&device=2",
        "grow_trend": f"{base}/portal/board/grow/factor/trend.json?dateType=day&dateRange={range_url}",
        "month_overview": f"{base}/portal/month/overview.json?dateType=day&dateRange={range_url}&sellerType=online",
        "month_trend": f"{base}/portal/month/trend.json?dateType=day&dateRange={month_trend_range}&sellerType=online",
        "experience_scorecard": f"{base}/portal/new/experience/scorecard.json",
        "main_cate_info": f"{base}/portal/shop/getMainCateInfo.json",
        "level_info": f"{base}/portal/level/info/v3.json?dateType=day&dateRange={range_url}",
    }

    results: dict[str, FetchResult] = {}
    for name, url in endpoints.items():
        output_path = output_dir / f"sycm_home_board_{name}_{day_str.replace('-', '')}.json"
        results[name] = _fetch_one(
            url,
            output=output_path,
            cookie=cookie,
            token=token,
            timeout=timeout,
        )
        time.sleep(1.0)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch SYCM home board endpoints for one day.")
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--token", default=os.getenv("SYCM_TOKEN", ""))
    add_session_source_arguments(parser)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    session = resolve_runtime_session(
        source=args.session_source,
        cookie_env=args.cookie_env,
        browser_port=args.browser_port,
    )

    results = fetch_sycm_home_board(
        day=args.day,
        output_dir=args.output_dir,
        cookie=session.cookie_header,
        token=args.token,
        timeout=args.timeout,
    )

    for name, result in results.items():
        print(
            json.dumps(
                {"endpoint": name, **asdict(result)},
                ensure_ascii=False,
            )
        )

    all_ok = all(r.ok for r in results.values())
    print(json.dumps({"all_ok": all_ok}, ensure_ascii=False))
    return 0 if all_ok else 1


def _response_code_and_message(payload: Any) -> tuple[int | None, str | None]:
    if not isinstance(payload, dict):
        return None, "unexpected response payload"
    content = payload.get("content")
    if isinstance(content, dict):
        code = _as_int(content.get("code"))
        message = _as_text(content.get("message") or content.get("msg"))
        return code, message
    code = _as_int(payload.get("code"))
    message = _as_text(payload.get("message") or payload.get("msg"))
    return code, message or "missing content object"


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _scrub_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        scrubbed: dict[str, Any] = {}
        for key, child in value.items():
            lowered = key.lower()
            if lowered in SENSITIVE_KEYS or lowered.endswith("token"):
                scrubbed[key] = "<removed>"
            else:
                scrubbed[key] = _scrub_sensitive(child)
        return scrubbed
    if isinstance(value, list):
        return [_scrub_sensitive(item) for item in value]
    return value


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"Fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
