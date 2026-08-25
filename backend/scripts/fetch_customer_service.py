from __future__ import annotations

import argparse
import hashlib
import json
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
from app.warehouse.mtop_sign import sign_mtop_data  # noqa: E402


APP_KEY = "12574478"
MTOP_API_NAME = "mtop.alibaba.sycm.domain.onequery"
MTOP_ENDPOINT = f"https://h5api.m.taobao.com/h5/{MTOP_API_NAME}/1.0/"
MTOP_CALLBACK = "mtopjsonp32"
CUSTOMER_SERVICE_INDEX_CODES = (
    "customerServiceGmv,customerServiceSaleCnt,customerServiceSaleRatio,"
    "customerServiceSalePrice,sucRefundAmount,netPayAmt,consultUserCnt,"
    "customerServiceRecUserCnt,wwConsultPayRate,avgReplyInterval,"
    "customerAllSateRate,wwUserReplayRate,jtkCaseEndAvgDur,"
    "thtkCaseEndAvgDur,pltfHelpRate,pltfRespRate"
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
        return 200 <= self.status < 300 and self.code in (0, 200)


def fetch_customer_service_overview(
    *,
    day: date,
    output: Path,
    cookie: str,
    timeout: int = 30,
) -> FetchResult:
    data_payload = {
        "domainCode": "tao.shop.qos.sellerkpi",
        "dateType": "day",
        "dateRange": f"{day.isoformat()}|{day.isoformat()}",
        "showType": "overview",
        "device": "0",
        "indexCodes": CUSTOMER_SERVICE_INDEX_CODES,
        "extMap": json.dumps(
            {"greyTag": "Y", "needCycleCrc": True},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    data_json = json.dumps(data_payload, ensure_ascii=False, separators=(",", ":"))
    timestamp, sign = _sign(data_json, cookie)
    params = {
        "jsv": "2.6.1",
        "appKey": APP_KEY,
        "t": timestamp,
        "sign": sign,
        "api": MTOP_API_NAME,
        "v": "1.0",
        "ttid": "11320@taobao_WEB_9.9.99",
        "type": "originaljsonp",
        "dataType": "originaljsonp",
        "callback": MTOP_CALLBACK,
        "data": data_json,
    }
    request = Request(
        f"{MTOP_ENDPOINT}?{urlencode(params)}",
        headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "bx-v": "2.5.37",
            "cache-control": "no-cache",
            "cookie": cookie,
            "referer": "https://myseller.taobao.com/home.htm/op-sycm-svc/overview",
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
    return _request_json(request, output=output, timeout=timeout)


def fetch_customer_service_accounts(
    *,
    day: date,
    output: Path,
    cookie: str,
    timeout: int = 30,
) -> FetchResult:
    date_text = day.strftime("%Y%m%d")
    params = {
        "orderBy": "validReplyUv1d",
        "order": "desc",
        "pageNo": "1",
        "pageSize": "100",
        "startDate": date_text,
        "endDate": date_text,
        "dateType": "day",
        "dateRange": "1d",
        "accountType": "1",
    }
    request = Request(
        "https://sycm.taobao.com/csp/api/user/sale/summary/list.json?"
        f"{urlencode(params)}",
        headers={
            "accept": "application/json, text/plain, */*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "bx-v": "2.5.37",
            "cache-control": "no-cache",
            "cookie": cookie,
            "referer": "https://sycm.taobao.com/qos/service/frame/customer/performance/new",
            "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
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
    return _request_json(request, output=output, timeout=timeout)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch one day of customer-service data.")
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--overview-output", type=Path, required=True)
    parser.add_argument("--accounts-output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=30)
    add_session_source_arguments(parser)
    args = parser.parse_args()
    session = resolve_runtime_session(
        source=args.session_source,
        cookie_env=args.cookie_env,
        browser_port=args.browser_port,
    )
    overview = fetch_customer_service_overview(
        day=args.day,
        output=args.overview_output,
        cookie=session.cookie_header,
        timeout=args.timeout,
    )
    accounts = fetch_customer_service_accounts(
        day=args.day,
        output=args.accounts_output,
        cookie=session.cookie_header,
        timeout=args.timeout,
    )
    print(
        json.dumps(
            {"overview": asdict(overview), "accounts": asdict(accounts)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if overview.ok and accounts.ok else 1


def _sign(data_json: str, cookie: str) -> tuple[str, str]:
    m_h5_tk = _cookie_value(cookie, "_m_h5_tk")
    if not m_h5_tk:
        raise RuntimeError("The browser session has no usable _m_h5_tk cookie for MTop signing.")
    return sign_mtop_data(data_json, m_h5_tk, app_key=APP_KEY)


def _request_json(request: Request, *, output: Path, timeout: int) -> FetchResult:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
    except HTTPError as exc:
        body = exc.read()
        status = exc.code

    payload, decode_message = _decode_response(body)
    output_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    output.write_bytes(output_body)
    code, response_message = _response_code_and_message(payload)
    return FetchResult(
        status=status,
        code=code,
        message=response_message or decode_message,
        output=str(output),
        bytes=len(output_body),
    )


def _cookie_value(cookie_header: str, name: str) -> str:
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        key, value = part.strip().split("=", 1)
        if key.strip().lower() == name.lower():
            return value.strip()
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
        return 1, str(ret[0]) if ret else "request failed"
    code = payload.get("code")
    try:
        normalized = int(code) if code is not None else None
    except (TypeError, ValueError):
        normalized = None
    message = payload.get("message") or payload.get("msg")
    return normalized, None if message is None else str(message)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Customer-service fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
