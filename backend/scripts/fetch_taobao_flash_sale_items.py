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

from app.integrations.tmall_session import add_session_source_arguments, resolve_runtime_session  # noqa: E402
from scripts.fetch_taobao_flash_sale import FLASH_SALE_HOME_URL  # noqa: E402


@dataclass(frozen=True)
class FetchResult:
    status: int
    code: int | None
    message: str | None
    output: str
    bytes: int

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and self.code in (0, None)


def fetch_taobao_flash_sale_items(
    *, day: date, output: Path, cookie: str, page: int = 1, page_size: int = 50, timeout: int = 30,
) -> FetchResult:
    timestamp = int(datetime.combine(day, day_time.min, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp() * 1000)
    token = _cookie_value(cookie, "_tb_token_", "tb_token", "tb-token")
    params = {
        "_tb_token_": token, "pageSize": str(page_size), "pageNo": str(page),
        "startTime": str(timestamp), "endTime": str(timestamp), "__sm_request__": "true",
        "_": str(int(time.time() * 1000)),
    }
    request = Request(
        "https://sale.taobao.com/extend/api/tbhjItemDataQuery.json?" + urlencode(params),
        headers={
            "accept": "*/*", "accept-language": "zh-CN,zh;q=0.9,en;q=0.8", "cookie": cookie,
            "origin": "https://myseller.taobao.com", "referer": "https://myseller.taobao.com/home.htm/ltao-home/",
            "sec-fetch-dest": "empty", "sec-fetch-mode": "cors", "sec-fetch-site": "same-site",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
        },
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urlopen(request, timeout=timeout) as response:
            body, status = response.read(), response.status
    except HTTPError as exc:
        body, status = exc.read(), exc.code
    output.write_bytes(body)
    try:
        payload = json.loads(body.decode("utf-8"))
        code, message = _response_status(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        code, message = None, "non-json response"
    return FetchResult(status, code, message, str(output), len(body))


def _cookie_value(header: str, *names: str) -> str:
    wanted = {name.lower() for name in names}
    for part in header.split(";"):
        if "=" in part:
            name, value = part.strip().split("=", 1)
            if name.lower() in wanted:
                return value.strip()
    return ""


def _response_status(payload: object) -> tuple[int | None, str | None]:
    if not isinstance(payload, dict):
        return None, "unexpected response payload"
    if payload.get("success") is False:
        return 1, str(payload.get("message") or payload.get("msg") or "request failed")
    code = payload.get("code")
    try:
        normalized = int(code) if code is not None else 0
    except (TypeError, ValueError):
        normalized = None
    return normalized, str(payload.get("message") or payload.get("msg") or "") or None


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch one page of Taobao flash-sale item data.")
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--timeout", type=int, default=30)
    add_session_source_arguments(parser)
    args = parser.parse_args()
    if args.page < 1 or not 1 <= args.page_size <= 100:
        raise ValueError("page must be positive and page-size must be 1..100")
    session = resolve_runtime_session(
        source=args.session_source,
        cookie_env=args.cookie_env,
        browser_port=args.browser_port,
        home_url=FLASH_SALE_HOME_URL,
        platform_name="淘宝秒杀",
        expected_hosts=("myseller.taobao.com",),
    )
    result = fetch_taobao_flash_sale_items(day=args.day, output=args.output, cookie=session.cookie_header, page=args.page, page_size=args.page_size, timeout=args.timeout)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
