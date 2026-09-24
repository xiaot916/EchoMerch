from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import date
from pathlib import Path
from typing import Callable
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


def fetch_databank_daily(*, business_day: date, output: Path, cookie: str, csrf_token: str, timeout: int = 30, brand_id: str = "1917777264", browser_port: int | None = None) -> tuple[int, int]:
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
            raw_body = exc.read().decode("utf-8", errors="replace")
            payload[key] = {
                "_echoMerchHttpStatus": exc.code,
                "_echoMerchRawBody": raw_body,
            }
            _write_payload(output, payload)
            raise RuntimeError(
                f"品牌数据银行 {key} 请求失败: HTTP {exc.code} {_describe_bad_request(raw_body)}"
            ) from exc
        try:
            payload[key] = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if browser_port is not None:
                direct_body = response_body
                try:
                    status, response_body = _fetch_in_existing_databank_tab(
                        browser_port, path, timeout=timeout,
                    )
                    payload[key] = json.loads(response_body.decode("utf-8"))
                    if not 200 <= status < 300:
                        raise RuntimeError(f"品牌数据银行 {key} 浏览器请求失败: HTTP {status}")
                    _write_payload(output, payload)
                    continue
                except (RuntimeError, UnicodeDecodeError, json.JSONDecodeError) as fallback_error:
                    payload[key] = {
                        "_echoMerchHttpStatus": status,
                        "_echoMerchRawBody": direct_body.decode("utf-8", errors="replace"),
                        "_echoMerchBrowserError": type(fallback_error).__name__,
                    }
                    _write_payload(output, payload)
                    raise RuntimeError(
                        f"品牌数据银行 {key} 直连非 JSON，浏览器内回退失败: {fallback_error}"
                    ) from fallback_error
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


def _fetch_in_existing_databank_tab(browser_port: int, path: str, *, timeout: int) -> tuple[int, bytes]:
    from app.integrations.session.core import DrissionPageBrowser, RuntimeSessionUnavailable

    if not path.startswith("/api/paasapi?"):
        raise ValueError("数据银行浏览器回退只支持已登记的只读报表接口。")
    tab = DrissionPageBrowser(browser_port).find_tab(("databank.tmall.com",))
    if tab is None:
        raise RuntimeSessionUnavailable("数据银行直连失败，且没有已打开的数据银行页面。")
    script = """(async () => {
      const token = document.cookie.split('; ').find(part => part.startsWith('_tb_token_='))?.slice(11);
      if (!token) return {error: 'missing_token'};
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), %d);
      try {
        const response = await fetch(%s, {
          credentials: 'include', signal: controller.signal,
          headers: {'x-csrf-token': decodeURIComponent(token), 'x-requested-with': 'XMLHttpRequest'},
        });
        return {status: response.status, body: await response.text()};
      } catch (_) { return {error: 'request_failed'}; }
      finally { clearTimeout(timer); }
    })()""" % (max(1000, timeout * 1000), json.dumps(path))
    result: list[object] = []

    def evaluate() -> None:
        try:
            result.append(tab.run_cdp("Runtime.evaluate", expression=script, awaitPromise=True, returnByValue=True))
        except Exception:
            result.append(None)

    worker = threading.Thread(target=evaluate, daemon=True, name="databank-browser-fetch")
    worker.start()
    worker.join(timeout=max(1, timeout) + 5)
    value = result[0].get("result", {}).get("value") if result and isinstance(result[0], dict) else None
    if worker.is_alive() or not isinstance(value, dict) or not isinstance(value.get("body"), str):
        raise RuntimeSessionUnavailable("数据银行页面内报表请求失败，请确认登录和网络状态。")
    return int(value["status"]), value["body"].encode("utf-8")


# Platform-level envelope codes that mean "this request was not accepted",
# not "the day has no data".  They are almost always produced by a stale
# session/csrf snapshot captured before the browser finished logging in, so a
# single session refresh + retry recovers them (verified live 2026-09-19).
_STALE_SESSION_ERR_CODES = (
    "477012030108",          # param illegal
    "77000001001",           # For input string: ""
    "4000000000000000000",
)
_STALE_SESSION_ERR_FRAGMENTS = (
    "param illegal",
    "for input string",
    "login",
    "not login",
    "session",
    "csrf",
)


def _describe_bad_request(raw_body: str) -> str:
    """Summarise a failed Brand Data Bank envelope for the log line."""

    try:
        envelope = json.loads(raw_body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return raw_body.strip()[:200]
    if isinstance(envelope, dict):
        code = envelope.get("errCode")
        message = envelope.get("errMsg") or envelope.get("message")
        if code is not None or message:
            return f"errCode={code}, errMsg={message or 'unknown'}"
    return raw_body.strip()[:200]


def is_stale_session_error(error: object) -> bool:
    """Return True when a failure looks like a stale session/csrf snapshot."""

    text = str(error or "").lower()
    if any(code.lower() in text for code in _STALE_SESSION_ERR_CODES):
        return True
    return any(fragment in text for fragment in _STALE_SESSION_ERR_FRAGMENTS)


def fetch_databank_daily_with_retry(
    *,
    business_day: date,
    output: Path,
    resolve_runtime: Callable[[], tuple[str, str]],
    timeout: int = 30,
    brand_id: str = "1917777264",
    browser_port: int | None = None,
    attempts: int = 2,
) -> tuple[int, int]:
    """Fetch one day, re-reading the live browser session when it looks stale.

    The 08:48 scheduled runs of 2026-09-15..09-18 all failed with
    ``errCode=477012030108 param illegal`` while identical parameters succeeded
    against a freshly navigated tab.  That proves the request contract is fine
    and the captured cookie/csrf snapshot had gone stale.  ``resolve_runtime``
    is re-invoked (which re-navigates databank.tmall.com and re-reads
    ``_tb_token_``) before the retry.
    """

    last_error: Exception | None = None
    for attempt in range(max(attempts, 1)):
        cookie, csrf_token = resolve_runtime()
        try:
            return fetch_databank_daily(
                business_day=business_day,
                output=output,
                cookie=cookie,
                csrf_token=csrf_token,
                timeout=timeout,
                brand_id=brand_id,
                browser_port=browser_port,
            )
        except RuntimeError as exc:
            last_error = exc
            if attempt + 1 >= attempts or not is_stale_session_error(exc):
                raise
            print(
                f"品牌数据银行会话疑似过期，重新读取浏览器会话后重试 "
                f"({attempt + 2}/{attempts}): {exc}",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(1.0)
    assert last_error is not None
    raise last_error


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
        browser_port=args.browser_port if args.session_source == "drissionpage" else None,
    )
    print(json.dumps({"status": status, "endpoint_count": endpoint_count, "output": str(args.output)}, ensure_ascii=False))
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
