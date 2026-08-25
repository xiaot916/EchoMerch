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


def fetch_sycm_new_customer_discount(
    *,
    day: date,
    output: Path,
    cookie: str,
    token: str = "",
    timeout: int = 30,
) -> FetchResult:
    params = {
        "dateType": "day",
        "dateRange": f"{day.isoformat()}|{day.isoformat()}",
        "channelId": "450",
        "_": str(int(time.time() * 1000)),
    }
    if token:
        params["token"] = token

    request = Request(
        "https://sycm.taobao.com/s_content/brandnewdiscount/overview.json?"
        f"{urlencode(params)}",
        headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "cache-control": "no-cache",
            "cookie": cookie,
            "referer": "https://sycm.taobao.com/xsite/promotion/promotion/sales?activeKey=promotionMethod",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
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
        output_body = json.dumps(
            _scrub_sensitive(payload), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        code, message = _response_code_and_message(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        output_body = body
        code, message = None, "non-json response"

    output.write_bytes(output_body)
    return FetchResult(
        status=status,
        code=code,
        message=message,
        output=str(output),
        bytes=len(output_body),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch one day of SYCM new customer discount data."
    )
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--token", default=os.getenv("SYCM_TOKEN", ""))
    add_session_source_arguments(parser)
    args = parser.parse_args()
    session = resolve_runtime_session(
        source=args.session_source,
        cookie_env=args.cookie_env,
        browser_port=args.browser_port,
    )
    result = fetch_sycm_new_customer_discount(
        day=args.day,
        output=args.output,
        cookie=session.cookie_header,
        token=args.token,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def _response_code_and_message(payload: object) -> tuple[int | None, str | None]:
    if not isinstance(payload, dict):
        return None, "unexpected response payload"
    root = payload.get("content") if isinstance(payload.get("content"), dict) else payload
    code = root.get("code")
    message = root.get("message") or root.get("msg")
    try:
        normalized_code = int(code) if code is not None else None
    except (TypeError, ValueError):
        normalized_code = None
    return normalized_code, None if message is None else str(message)


def _scrub_sensitive(value: object) -> object:
    if isinstance(value, dict):
        scrubbed: dict[str, object] = {}
        for key, child in value.items():
            lowered = key.lower()
            scrubbed[key] = (
                "<removed>"
                if lowered in {"token", "cookie", "authorization"}
                or lowered.endswith("token")
                else _scrub_sensitive(child)
            )
        return scrubbed
    if isinstance(value, list):
        return [_scrub_sensitive(item) for item in value]
    return value


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"New customer discount fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
