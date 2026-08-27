from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, time as day_time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.tmall_session import (  # noqa: E402
    add_session_source_arguments,
    resolve_runtime_session,
)


FLASH_SALE_HOME_URL = "https://myseller.taobao.com/home.htm/ltao-home/"


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


def fetch_taobao_flash_sale(
    *,
    day: date,
    output: Path,
    cookie: str,
    timeout: int = 30,
) -> FetchResult:
    timestamp = int(
        datetime.combine(day, day_time.min, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()
        * 1000
    )
    params = {
        "startTime": str(timestamp),
        "endTime": str(timestamp),
        "__sm_request__": "true",
    }
    request = Request(
        "https://sale.taobao.com/extend/api/tbhjActivityDataQuery.json?"
        f"{urlencode(params)}",
        headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "cookie": cookie,
            "origin": "https://myseller.taobao.com",
            "priority": "u=1, i",
            "referer": "https://myseller.taobao.com/home.htm/ltao-home/",
            "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
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
    output.write_bytes(body)

    try:
        payload = json.loads(body.decode("utf-8"))
        code, message = _response_code_and_message(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        code, message = None, "non-json response"

    return FetchResult(status, code, message, str(output), len(body))


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Taobao flash-sale metrics for one day.")
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    add_session_source_arguments(parser)
    args = parser.parse_args()
    session = resolve_runtime_session(
        source=args.session_source,
        cookie_env=args.cookie_env,
        browser_port=args.browser_port,
        home_url=FLASH_SALE_HOME_URL,
        platform_name="淘宝秒杀",
        expected_hosts=("myseller.taobao.com",),
    )
    result = fetch_taobao_flash_sale(
        day=args.day,
        output=args.output,
        cookie=session.cookie_header,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def _response_code_and_message(payload: object) -> tuple[int | None, str | None]:
    if not isinstance(payload, dict):
        return None, "unexpected response payload"
    if payload.get("success") is False:
        return 1, str(payload.get("message") or payload.get("msg") or "request failed")
    code = payload.get("code")
    try:
        normalized_code = int(code) if code is not None else 0
    except (TypeError, ValueError):
        normalized_code = None
    return normalized_code, str(payload.get("message") or payload.get("msg") or "") or None


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"Fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
