from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.tmall_session import add_session_source_arguments, resolve_runtime_session  # noqa: E402


SENSITIVE_KEYS = {"token", "cookie", "authorization"}
ACTIVITY_CALENDAR_URL = "https://sycm.taobao.com/datawar/v4/activity/actList/getActivityCalendar.json"


@dataclass(frozen=True)
class FetchResult:
    status: int
    code: int | None
    message: str | None
    output: str
    bytes: int

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and self.code in (0, 200)


def fetch_sycm_activity_calendar(
    *,
    day: date,
    output: Path,
    cookie: str,
    token: str = "",
    timeout: int = 30,
) -> FetchResult:
    params = {
        "actType": "0",
        "date": day.isoformat(),
        "_": str(int(time.time() * 1000)),
    }
    if token:
        params["token"] = token
    request = Request(
        f"{ACTIVITY_CALENDAR_URL}?{urlencode(params)}",
        headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "bx-v": "2.5.37",
            "cache-control": "no-cache",
            "cookie": cookie,
            "onetrace-card-id": "am-activity-calendar",
            "pragma": "no-cache",
            "referer": "https://sycm.taobao.com/datawar/activity/analysis",
            "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sycm-referer": "/datawar/activity/analysis",
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
        normalized = json.dumps(
            _scrub_sensitive(payload), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        code, message = _response_code_and_message(payload)
    except (UnicodeDecodeError, json.JSONDecodeError):
        normalized = body
        code = None
        message = "non-json response"
    output.write_bytes(normalized)
    return FetchResult(status, code, message, str(output), len(normalized))


def _response_code_and_message(payload: Any) -> tuple[int | None, str | None]:
    if not isinstance(payload, dict):
        return None, "unexpected response payload"
    root = payload.get("content") if isinstance(payload.get("content"), dict) else payload
    if root.get("success") is False:
        return 1, _as_text(root.get("message") or root.get("msg")) or "request failed"
    code = _as_int(root.get("code"))
    message = _as_text(root.get("message") or root.get("msg"))
    return code, message


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
    text = str(value)
    return text or None


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch the current SYCM activity calendar snapshot.")
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--token", default=os.getenv("SYCM_TOKEN", ""))
    parser.add_argument("--timeout", type=int, default=30)
    add_session_source_arguments(parser)
    args = parser.parse_args()
    session = resolve_runtime_session(
        source=args.session_source,
        cookie_env=args.cookie_env,
        browser_port=args.browser_port,
    )
    result = fetch_sycm_activity_calendar(
        day=args.day,
        output=args.output,
        cookie=session.cookie_header,
        token=args.token,
        timeout=args.timeout,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"Activity calendar fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
