from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.tmall_session import (  # noqa: E402
    DEFAULT_DATABANK_HOME_URL,
    add_session_source_arguments,
    resolve_databank_runtime_context,
)

CORE_PATH = "/api/v1/home/queryCoreVolume"
VOLUME_PATH = "/api/v1/home/queryVolume"
PAY_PATH = "/api/v1/home/queryPayAnalyse"
CHL_PATH = "/api/v1/home/queryChlAnalyse"
CHANNEL_PATH = "/api/v1/home/queryChannelAnalyse"
TOUCH_PATH = "/api/v1/home/queryTouchAnalyse"
CROWD_PATH = "/api/v1/home/queryCrowdAnalyse"

# New homepage APIs use dateType=d and xcatId on the same paas gateway.
HOMEPAGE_PATHS = {
    "homepage_panel": "/homepage/queryPanel",
    "homepage_growth_strategy": "/homepage/queryGrowthStrategy",
    "homepage_panel_detail_active": "/homepage/queryPanelDetail",
    "homepage_panel_detail_aipl": "/homepage/queryPanelDetail",
    "homepage_panel_detail_deal": "/homepage/queryPanelDetail",
    "homepage_growth_map_touch": "/homepage/queryGrowthStrategyMap",
    "homepage_growth_map_avg_touch": "/homepage/queryGrowthStrategyMap",
    "homepage_growth_map_active_time": "/homepage/queryGrowthStrategyMap",
    "homepage_growth_map_ctr": "/homepage/queryGrowthStrategyMap",
    "homepage_growth_map_cvr": "/homepage/queryGrowthStrategyMap",
}


def _query(path: str, day: date, *, category_id: str = "-999", data_type: str | None = None) -> str:
    values = {
        "path": path,
        "dateType": "day",
        "ds": day.strftime("%Y%m%d"),
        "dateRange": f"{day.isoformat()}|{day.isoformat()}",
        "cateId": category_id,
        "_": str(int(time.time() * 1000)),
    }
    if data_type is not None:
        values["dataType"] = data_type
    return "/api/paasapi?" + urlencode(values)


def _homepage_query(path: str, day: date, *, brand_id: str, panel_type: str | None = None) -> str:
    values = {
        "path": path,
        "brandId": brand_id,
        "dateType": "d",
        "ds": day.strftime("%Y%m%d"),
        "xcatId": "-999",
        "_": str(int(time.time() * 1000)),
    }
    if panel_type is not None:
        values["panelType"] = panel_type
    return "/api/paasapi?" + urlencode(values)


def fetch_databank_daily(*, business_day: date, output: Path, cookie: str, csrf_token: str, timeout: int = 30, brand_id: str = "1917777264") -> tuple[int, int]:
    endpoints = {
        "core": _query(CORE_PATH, business_day),
        "volume": _query(VOLUME_PATH, business_day, data_type="all"),
        "pay": _query(PAY_PATH, business_day),
        "category": _query(CHL_PATH, business_day),
        "channel": _query(CHANNEL_PATH, business_day),
        "touch": _query(TOUCH_PATH, business_day),
        "crowd": _query(CROWD_PATH, business_day, data_type="exceed"),
        "homepage_panel": _homepage_query("/homepage/queryPanel", business_day, brand_id=brand_id),
        "homepage_growth_strategy": _homepage_query("/homepage/queryGrowthStrategy", business_day, brand_id=brand_id),
        "homepage_panel_detail_active": _homepage_query("/homepage/queryPanelDetail", business_day, brand_id=brand_id, panel_type="active"),
        "homepage_panel_detail_aipl": _homepage_query("/homepage/queryPanelDetail", business_day, brand_id=brand_id, panel_type="aipl"),
        "homepage_panel_detail_deal": _homepage_query("/homepage/queryPanelDetail", business_day, brand_id=brand_id, panel_type="deal"),
        "homepage_growth_map_touch": _homepage_query("/homepage/queryGrowthStrategyMap", business_day, brand_id=brand_id, panel_type="touch"),
        "homepage_growth_map_avg_touch": _homepage_query("/homepage/queryGrowthStrategyMap", business_day, brand_id=brand_id, panel_type="avgTouch"),
        "homepage_growth_map_active_time": _homepage_query("/homepage/queryGrowthStrategyMap", business_day, brand_id=brand_id, panel_type="activeTime"),
        "homepage_growth_map_ctr": _homepage_query("/homepage/queryGrowthStrategyMap", business_day, brand_id=brand_id, panel_type="ctr"),
        "homepage_growth_map_cvr": _homepage_query("/homepage/queryGrowthStrategyMap", business_day, brand_id=brand_id, panel_type="cvr"),
    }
    payload: dict[str, object] = {}
    status = 200
    for key, path in endpoints.items():
        request = Request(
            "https://databank.tmall.com" + path,
            headers={
                "accept": "*/*",
                "cookie": cookie,
                "referer": DEFAULT_DATABANK_HOME_URL,
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
                "x-csrf-token": csrf_token,
                "x-requested-with": "XMLHttpRequest",
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                status = response.status
                response_body = response.read()
        except HTTPError as exc:
            payload[key] = {
                "_echoMerchHttpStatus": exc.code,
                "_echoMerchRawBody": exc.read().decode("utf-8", errors="replace"),
            }
            _write_payload(output, payload)
            raise RuntimeError(f"品牌数据银行 {key} 请求失败: HTTP {exc.code}") from exc
        try:
            payload[key] = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            payload[key] = {
                "_echoMerchHttpStatus": status,
                "_echoMerchRawBody": response_body.decode("utf-8", errors="replace"),
                "_echoMerchDecodeError": str(exc),
            }
            _write_payload(output, payload)
            raise RuntimeError(f"品牌数据银行 {key} 返回了非 JSON 响应") from exc
        # Persist after each endpoint. A later endpoint may time out, but the
        # earlier platform envelopes still explain whether the day was valid.
        _write_payload(output, payload)
        # Always fetch the complete contract.  The newer homepage endpoints
        # can contain useful data even when the legacy core endpoint is empty.
    endpoint_errors = [
        f"{key}: {error}"
        for key, response in payload.items()
        if (error := _endpoint_error(response)) is not None
    ]
    if endpoint_errors:
        raise RuntimeError("品牌数据银行接口返回异常: " + "; ".join(endpoint_errors))
    return status, len(payload)


def _write_payload(output: Path, payload: dict[str, object]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def _endpoint_error(response: object) -> str | None:
    if not isinstance(response, dict):
        return "响应格式无效"
    error_code = response.get("errCode")
    if error_code not in (None, 0, "0"):
        return f"errCode={error_code}, errMsg={response.get('errMsg') or 'unknown'}"
    code_class = str(response.get("codeClass") or "").upper()
    if code_class and code_class not in {"SUCCESS", "OK"}:
        return f"codeClass={code_class}, errMsg={response.get('errMsg') or 'unknown'}"
    if response.get("success") is False:
        return str(response.get("message") or response.get("msg") or "success=false")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch one daily Tmall Brand Data Bank snapshot.")
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--brand-id", default=os.getenv("DATABANK_BRAND_ID", "1917777264"))
    parser.add_argument("--csrf-token", default=os.getenv("DATABANK_CSRF_TOKEN", ""))
    parser.add_argument("--timeout", type=int, default=30)
    add_session_source_arguments(parser)
    args = parser.parse_args()
    runtime = resolve_databank_runtime_context(
        source=args.session_source,
        cookie_env=args.cookie_env,
        csrf_token=args.csrf_token,
        browser_port=args.browser_port,
    )
    status, endpoint_count = fetch_databank_daily(
        business_day=args.day,
        output=args.output,
        cookie=runtime.session.cookie_header,
        csrf_token=runtime.csrf_token,
        timeout=args.timeout,
        brand_id=args.brand_id,
    )
    print(json.dumps({"status": status, "endpoint_count": endpoint_count, "output": str(args.output)}, ensure_ascii=False))
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
