from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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


APP_KEY = "12574478"
API_NAME = "mtop.hd.marketing.seller.home"
ENDPOINT = f"https://h5api.m.taobao.com/h5/{API_NAME}/1.0/"
JSONP_CALLBACK = "mtopjsonp20"


@dataclass(frozen=True)
class FetchResult:
    status: int
    code: int | None
    message: str | None
    output: str
    bytes: int
    section: str

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and self.code == 0


def fetch_mtop_taojinbi(
    *,
    day: date,
    section: str,
    output: Path,
    cookie: str,
    timeout: int = 30,
) -> FetchResult:
    if section not in {"general", "detailed"}:
        raise ValueError("section must be general or detailed")

    date_range = f"{day.isoformat()}|{day.isoformat()}"
    scene_code = "shopGeneralInfo" if section == "general" else "shopDetailedInfo"
    data_payload = {
        "dateType": "day",
        "dateRange": date_range,
        "dtUpdateTime": True,
        "indexCode": "",
        "requestType": "mtop",
        "scenes": json.dumps(
            [{"sceneCode": scene_code}],
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "resultKey": scene_code,
        "params": json.dumps(
            {"dateRange": date_range, "dateType": "day"},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    data_json = json.dumps(data_payload, ensure_ascii=False, separators=(",", ":"))
    timestamp = str(int(time.time() * 1000))
    token = _mtop_token(cookie)
    if not token:
        raise RuntimeError("The browser session has no usable _m_h5_tk cookie for MTop signing.")
    sign = hashlib.md5(
        f"{token}&{timestamp}&{APP_KEY}&{data_json}".encode("utf-8")
    ).hexdigest()
    params = {
        "jsv": "2.6.1",
        "appKey": APP_KEY,
        "t": timestamp,
        "sign": sign,
        "api": API_NAME,
        "v": "1.0",
        "ttid": "11320@taobao_WEB_9.9.99",
        "dataType": "originaljsonp",
        "type": "originaljsonp",
        "callback": JSONP_CALLBACK,
        "data": data_json,
    }
    request = Request(
        f"{ENDPOINT}?{urlencode(params)}",
        headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "cache-control": "no-cache",
            "cookie": cookie,
            "referer": "https://sycm.taobao.com/",
            "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "script",
            "sec-fetch-mode": "no-cors",
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

    payload, message = _decode_response(body)
    output_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    output.write_bytes(output_body)
    code, response_message = _response_code_and_message(payload)
    return FetchResult(
        status=status,
        code=code,
        message=response_message or message,
        output=str(output),
        bytes=len(output_body),
        section=section,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch one day of Taojinbi MTop data.")
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--section", choices=("general", "detailed"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    add_session_source_arguments(parser)
    args = parser.parse_args()
    session = resolve_runtime_session(
        source=args.session_source,
        cookie_env=args.cookie_env,
        browser_port=args.browser_port,
    )
    result = fetch_mtop_taojinbi(
        day=args.day,
        section=args.section,
        output=args.output,
        cookie=session.cookie_header,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def _mtop_token(cookie_header: str) -> str:
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        name, value = part.strip().split("=", 1)
        if name.strip().lower() in {"_m_h5_tk", "m_h5_tk"}:
            return value.split("_", 1)[0].strip()
    return ""


def _decode_response(body: bytes) -> tuple[dict[str, object], str | None]:
    text = body.decode("utf-8", errors="replace").strip()
    match = re.match(r"^(?:[\w$]+)\((.*)\)\s*;?\s*$", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"ret": ["ERROR::non-json response"], "data": {}}, "non-json response"
    if not isinstance(payload, dict):
        return {"ret": ["ERROR::unexpected response payload"], "data": {}}, "unexpected response payload"
    return payload, None


def _response_code_and_message(payload: dict[str, object]) -> tuple[int | None, str | None]:
    ret = payload.get("ret")
    if isinstance(ret, list):
        for item in ret:
            text = str(item)
            if text.startswith("SUCCESS::"):
                return 0, text.split("::", 1)[1] or None
        return 1, str(ret[0]) if ret else "MTop request failed"
    return None, "MTop response has no ret field"


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Taojinbi fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
