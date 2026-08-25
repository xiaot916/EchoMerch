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
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.tmall_session import add_session_source_arguments, resolve_runtime_session  # noqa: E402


SECTION_CONFIG = {
    "core": {
        "domainCode": "tao.shop.customer.mbranalysis.retailer",
        "showType": "overview",
        "indexCodes": "totalMbrCnt,paidMbrCnt,mbrPayAmt,mbrUnitPrice,repurMbrRate",
        "extra": {"extMap": '{"needPeriodsCrc":true}'},
        "card": "客户-会员分析|核心指标",
    },
    "asset": {
        "domainCode": "tao.shop.customer.mbranalysis.asset",
        "showType": "overview",
        "indexCodes": (
            "highFreqBuyerMemberAssets,highFreqBuyerMemberPayAmtRate,"
            "highFreqBuyerMemberAssetsRatio,twoOrderBuyerMemberAssets,"
            "twoOrderBuyerMemberPayAmtRate,twoOrderBuyerMemberAssetsRatio,"
            "firstTimeBuyerMemberAssets,firstTimeBuyerMemberLyrAssetsRatio,"
            "firstTimeBuyerMemberPayAmtRate,activeNonBuyerMemberAssets,"
            "activeNonBuyerMemberLyrAssetsRatio,inactiveMemberAssets,"
            "inactiveMemberLyrAssetsRatio,inactiveMemberAssetsPortion,"
            "activeNonBuyerMemberAssetsPortion,highFreqBuyerMemberAssetsPortion,"
            "twoOrderBuyerMemberAssetsPortion,firstTimeBuyerMemberAssetsPortion"
        ),
        "extra": {"needPeriodsCrc": "true"},
        "card": "客户-会员分析|会员资产分布",
    },
    "repurchase": {
        "domainCode": "tao.shop.customer.mbranalysis.retailer",
        "showType": "overview",
        "indexCodes": (
            "repurMbrCnt,repurPayAmt,repurOrdCnt,repurUnitPrice,"
            "repurCycle,repurMbrRate,repurFrequency"
        ),
        "extra": {"extMap": '{"needPeriodsCrc":true}'},
        "card": "客户-会员分析|会员运营-会员复购-数据概览",
    },
    "acquisition": {
        "domainCode": "tao.shop.customer.mbranalysis.retailer",
        "showType": "overview",
        "indexCodes": (
            "incrMbrCnt,incrPaidMbrCnt,recConvertRate,"
            "incrPayOrdAmt,incrUnitPrice,oldNewMemberCount"
        ),
        "extra": {"extMap": '{"needPeriodsCrc":true}'},
        "card": "客户-会员分析|会员运营-会员拉新-数据概览",
    },
    "channel": {
        "domainCode": "tao.shop.customer.mbranalysis.channel",
        "showType": "list",
        "indexCodes": "incrMbrCnt,incrPaidMbrCnt,recConvertRate,incrPayOrdAmt,incrUnitPrice",
        "extra": {
            "extMap": '{"needPeriodsCrc":true}',
            "pageSize": "10",
            "page": "1",
            "order": "desc",
            "orderBy": "incrMbrCnt",
        },
        "card": "客户-会员分析|会员运营-会员拉新-招募渠道拉新",
    },
}

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


def fetch_sycm_member_analysis(
    *,
    day: date,
    section: str,
    output: Path,
    cookie: str,
    token: str = "",
    timeout: int = 30,
) -> FetchResult:
    config = SECTION_CONFIG[section]
    params = {
        "domainCode": config["domainCode"],
        "dateType": "day",
        "dateRange": f"{day.isoformat()}|{day.isoformat()}",
        "bizCode": "sycm_pc",
        "showType": config["showType"],
        "device": "0",
        "indexCodes": config["indexCodes"],
        "_": str(int(time.time() * 1000)),
    }
    params.update(config["extra"])
    if token:
        params["token"] = token

    request = Request(
        f"https://sycm.taobao.com/domain/oneQuery.json?{urlencode(params)}",
        headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "bx-v": "2.5.37",
            "cache-control": "no-cache",
            "cookie": cookie,
            "onetrace-card-id": quote(str(config["card"]), safe="|"),
            "priority": "u=1, i",
            "referer": "https://sycm.taobao.com/cc/customer/member",
            "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "sycm-referer": "/cc/customer/member",
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch SYCM member analysis data with runtime cookies.")
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--section", choices=sorted(SECTION_CONFIG), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--token", default=os.getenv("SYCM_TOKEN", ""))
    add_session_source_arguments(parser)
    args = parser.parse_args()

    session = resolve_runtime_session(
        source=args.session_source,
        cookie_env=args.cookie_env,
        browser_port=args.browser_port,
    )

    result = fetch_sycm_member_analysis(
        day=args.day,
        section=args.section,
        output=args.output,
        cookie=session.cookie_header,
        token=args.token,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def _response_code_and_message(payload: object) -> tuple[int | None, str | None]:
    if not isinstance(payload, dict):
        return None, "unexpected response payload"
    content = payload.get("content")
    if isinstance(content, dict):
        return _as_int(content.get("code")), _as_text(
            content.get("message") or content.get("msg")
        )
    return _as_int(payload.get("code")), _as_text(
        payload.get("message") or payload.get("msg")
    )


def _as_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: object) -> str | None:
    return None if value is None else str(value)


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
