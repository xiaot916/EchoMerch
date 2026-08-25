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
    CPS_OVERVIEW_URL,
    DEFAULT_CPS_REPORT_HOME_URL,
    add_session_source_arguments,
    resolve_cps_runtime_context,
)


def fetch_cps_overview(
    *,
    business_day: date,
    output: Path,
    cookie: str,
    tb_token: str,
    timeout: int = 30,
) -> tuple[int, int | None, str | None, int]:
    params = {
        "t": str(int(time.time() * 1000)),
        "_tb_token_": tb_token,
        "split": "0",
        "startDate": business_day.isoformat(),
        "endDate": business_day.isoformat(),
    }
    request = Request(
        f"{CPS_OVERVIEW_URL}?{urlencode(params)}",
        method="GET",
        headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "cache-control": "no-cache",
            "cookie": cookie,
            "pragma": "no-cache",
            "referer": DEFAULT_CPS_REPORT_HOME_URL,
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
    data = payload.get("data")
    for value in (payload, data):
        if isinstance(value, dict) and value.get("code") is not None:
            return _as_int(value.get("code")), _as_text(
                value.get("message") or value.get("msg")
            )
    if payload.get("resultCode") is not None:
        return _as_int(payload.get("resultCode")), _as_text(
            payload.get("message") or payload.get("msg")
        )
    return None, _as_text(payload.get("message") or payload.get("msg"))


def _as_int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str | None:
    return None if value is None else str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch one daily CPS overview response.")
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tb-token", default=os.getenv("CPS_TB_TOKEN", ""))
    parser.add_argument("--timeout", type=int, default=30)
    add_session_source_arguments(parser)
    args = parser.parse_args()

    if args.timeout < 1:
        raise ValueError("--timeout must be positive.")

    runtime = resolve_cps_runtime_context(
        source=args.session_source,
        cookie_env=args.cookie_env,
        tb_token=args.tb_token,
        browser_port=args.browser_port,
        report_home_url=DEFAULT_CPS_REPORT_HOME_URL,
        timeout=args.timeout,
    )
    status, code, message, body_size = fetch_cps_overview(
        business_day=args.day,
        output=args.output,
        cookie=runtime.session.cookie_header,
        tb_token=runtime.tb_token,
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
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"CPS fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
