from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.tmall_session import (  # noqa: E402
    add_session_source_arguments,
    resolve_brandsearch_runtime_context,
)


BRANDSEARCH_REPORT_URL = (
    "https://brandsearch.taobao.com/report/query/rptAdvertiserSubListNew.json"
)
BRANDSEARCH_REPORT_HOME = "https://branding.taobao.com/#!/report/index?productid=101005201"
DEFAULT_PRODUCT_ID = "101005201"
DEFAULT_QUERY_PARAMS = {
    "r": "mx_548",
    "attribution": "impression",
    "effectConversionCycle": "30",
    "trafficType": "[1,2,4,5]",
}


def brandsearch_browser_fallback_port(source: str, port: int) -> int | None:
    value = str(port) if source == "drissionpage" else os.getenv("ECHO_BATCH_BRANDSEARCH_BROWSER_PORT", "")
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if 1 <= parsed <= 65535 else None


def fetch_brandsearch_report(
    *,
    business_day: date,
    output: Path,
    cookie: str,
    csrf_id: str,
    product_id: str = DEFAULT_PRODUCT_ID,
    query_params: dict[str, str] | None = None,
    timeout: int = 30,
    browser_port: int | None = None,
) -> tuple[int, int | None, str | None, int]:
    params = dict(DEFAULT_QUERY_PARAMS)
    if query_params:
        params.update(query_params)
    params.update(
        {
            "productId": product_id,
            "csrfID": csrf_id,
            "startDate": business_day.isoformat(),
            "endDate": business_day.isoformat(),
        }
    )
    request = Request(
        f"{BRANDSEARCH_REPORT_URL}?{urlencode(params)}",
        method="GET",
        headers={
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "cache-control": "no-cache",
            "cookie": cookie,
            "origin": "https://branding.taobao.com",
            "pragma": "no-cache",
            "referer": BRANDSEARCH_REPORT_HOME,
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36"
            ),
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

    if _response_status(response_body)[1] == "non-json response" and browser_port is not None:
        try:
            status, response_body = _fetch_in_brandsearch_tab(
                browser_port, request.full_url, timeout=timeout,
            )
        except RuntimeError:
            output.write_bytes(response_body)
            raise
    output.write_bytes(response_body)
    code, message = _response_status(response_body)
    return status, code, message, len(response_body)


def _fetch_in_brandsearch_tab(browser_port: int, url: str, *, timeout: int) -> tuple[int, bytes]:
    from app.integrations.session.core import DrissionPageBrowser, RuntimeSessionUnavailable, open_browser_platform_session

    parsed = urlparse(url)
    if parsed.scheme != "https" or f"{parsed.scheme}://{parsed.netloc}{parsed.path}" != BRANDSEARCH_REPORT_URL:
        raise ValueError("品销宝浏览器回退只支持已登记的只读报表接口。")
    browser = DrissionPageBrowser(browser_port)
    tab = browser.find_tab(("branding.taobao.com",))
    if tab is None:
        open_browser_platform_session(browser_port, "brandsearch", timeout=timeout, keep_open_on_success=True)
        tab = browser.find_tab(("branding.taobao.com",))
    if tab is None:
        raise RuntimeSessionUnavailable("品销宝直连失败，且品牌专区页面未能打开。")
    script = """(async () => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), %d);
      try {
        const response = await fetch(%s, {credentials: 'include', signal: controller.signal});
        return {status: response.status, body: await response.text()};
      } catch (_) { return {error: 'request_failed'}; }
      finally { clearTimeout(timer); }
    })()""" % (max(1000, timeout * 1000), json.dumps(url))
    result: list[object] = []

    def evaluate() -> None:
        try:
            result.append(tab.run_cdp("Runtime.evaluate", expression=script, awaitPromise=True, returnByValue=True))
        except Exception:
            result.append(None)

    worker = threading.Thread(target=evaluate, daemon=True, name="brandsearch-browser-fetch")
    worker.start()
    worker.join(timeout=max(1, timeout) + 5)
    value = result[0].get("result", {}).get("value") if result and isinstance(result[0], dict) else None
    if worker.is_alive() or not isinstance(value, dict) or not isinstance(value.get("body"), str):
        raise RuntimeSessionUnavailable("品销宝页面内报表请求失败，请检查登录和网络状态。")
    return int(value["status"]), value["body"].encode("utf-8")


def _response_status(response_body: bytes) -> tuple[int | None, str | None]:
    try:
        payload: Any = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "non-json response"
    if not isinstance(payload, dict):
        return None, "unexpected response payload"
    for value in (payload, payload.get("data"), payload.get("info")):
        if isinstance(value, dict) and value.get("code") is not None:
            return _as_int(value.get("code")), _as_text(value.get("message") or value.get("msg"))
    return None, _as_text(payload.get("message") or payload.get("msg"))


def _as_int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None


def _as_text(value: Any) -> str | None:
    return None if value is None else str(value)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch one daily PZ brand-search report response."
    )
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--product-id", default=DEFAULT_PRODUCT_ID)
    parser.add_argument("--csrf-id", default=os.getenv("PZ_CSRF_ID", ""))
    parser.add_argument("--timeout", type=int, default=30)
    add_session_source_arguments(parser)
    args = parser.parse_args()

    if not args.product_id:
        raise ValueError("--product-id cannot be empty.")
    if args.timeout < 1:
        raise ValueError("--timeout must be positive.")

    runtime = resolve_brandsearch_runtime_context(
        source=args.session_source,
        cookie_env=args.cookie_env,
        csrf_id=args.csrf_id,
        browser_port=args.browser_port,
        report_home_url=BRANDSEARCH_REPORT_HOME.replace(
            "101005201", args.product_id
        ),
        timeout=args.timeout,
    )
    status, code, message, body_size = fetch_brandsearch_report(
        business_day=args.day,
        output=args.output,
        cookie=runtime.session.cookie_header,
        csrf_id=runtime.csrf_id,
        product_id=args.product_id,
        query_params=dict(runtime.query_params),
        timeout=args.timeout,
        browser_port=brandsearch_browser_fallback_port(args.session_source, args.browser_port),
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
        print(f"Brand-search fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
