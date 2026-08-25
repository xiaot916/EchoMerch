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


INDEX_CODES = ",".join(
    [
        "sellerId",
        "statDate",
        "shopCustomer",
        "newVisitorCnt",
        "shopCustomerAvgGood",
        "newVisitorCntAvgGood",
        "hasPurchaseCntAvgGood",
        "noPurchaseCntAvgGood",
        "newVisitorBuyCnt",
        "newVisitorInShopCnt",
        "newVisitorPayRate",
        "newVisitorPct",
        "newVisitorVipRate",
        "newVisitorFansRate",
        "newVisitorPayAmtRatio",
        "newVisitorReCall",
        "noPurchaseCnt",
        "noPurchaseBuyCnt",
        "noBuyInShopCnt",
        "noPurchasePayRate",
        "noPurchasePct",
        "noPurchaseFansRate",
        "noPurchaseVipRate",
        "noPurchasePayAmtRatio",
        "noPurchaseReCall",
        "hasPurchaseCnt",
        "hasPurchaseUbyCnt",
        "hasBuyInShopCnt",
        "hasPurchasePayRate",
        "hasPurchasePayAmtRatio",
        "hasPurchasePct",
        "hasPurchaseFansRate",
        "hasPurchaseVipRate",
        "hasPurchaseReCall",
        "noPurchaseBuyCntRate",
        "hasPurchaseUbyCntRate",
    ]
)

SENSITIVE_KEYS = {"token", "cookie", "authorization"}


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch SYCM customer overview with runtime cookies.")
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

    result = fetch_sycm_customer_overview(
        day=args.day,
        output=args.output,
        cookie=session.cookie_header,
        token=args.token,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def fetch_sycm_customer_overview(
    *,
    day: date,
    output: Path,
    cookie: str,
    token: str = "",
    timeout: int = 30,
) -> FetchResult:
    params = {
        "domainCode": "tao.shop.customer.overview",
        "dateType": "day",
        "dateRange": f"{day.isoformat()}|{day.isoformat()}",
        "bizCode": "sycm_pc",
        "pluginFlag": "customerOverview",
        "showType": "overview",
        "needPeriodsCrc": "true",
        "device": "0",
        "indexCodes": INDEX_CODES,
        "_": str(int(time.time() * 1000)),
    }
    if token:
        params["token"] = token

    url = f"https://sycm.taobao.com/domain/oneQuery.json?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "bx-v": "2.5.37",
            "cache-control": "no-cache",
            "cookie": cookie,
            "onetrace-card-id": "%E5%AE%A2%E6%88%B7-%E5%AE%A2%E6%88%B7%E6%A6%82%E5%86%B5%7C%E5%BA%97%E9%93%BA%E5%AE%A2%E6%88%B7",
            "referer": "https://sycm.taobao.com/cc/customer/overview",
            "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sycm-referer": "/cc/customer/overview",
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

    output_body = body
    try:
        payload = json.loads(body.decode("utf-8"))
        output_body = json.dumps(
            _scrub_sensitive(payload),
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        code = payload.get("code") if isinstance(payload, dict) else None
        message = payload.get("message") if isinstance(payload, dict) else None
    except json.JSONDecodeError:
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
