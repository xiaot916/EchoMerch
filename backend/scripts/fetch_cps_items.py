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
    CPS_ITEM_ANALYSIS_URL,
    CPS_ITEM_LIST_REFERER,
    DEFAULT_CPS_REPORT_HOME_URL,
    add_session_source_arguments,
    resolve_cps_runtime_context,
)
from app.integrations.session.cps import browser_fallback_port, fetch_cps_browser_json  # noqa: E402


def fetch_cps_items_page(
    *,
    business_day: date,
    page_num: int,
    page_size: int,
    output: Path | None,
    cookie: str,
    tb_token: str,
    timeout: int = 30,
    order_metric: str = "alipayAmt",
    order_type: str = "desc",
    browser_port: int | None = None,
) -> tuple[int, Any, int]:
    """Fetch one page of the CPS item-analysis report for one business day.

    Returns (http_status, parsed_payload, body_bytes).
    """
    params = {
        "t": str(int(time.time() * 1000)),
        "_tb_token_": tb_token,
        "startDate": business_day.isoformat(),
        "endDate": business_day.isoformat(),
        "pageNum": str(page_num),
        "pageSize": str(page_size),
        "period": "1d",
        "level3Dim": "",
        "orderMetric": order_metric,
        "orderType": order_type,
    }
    request = Request(
        f"{CPS_ITEM_ANALYSIS_URL}?{urlencode(params)}",
        method="GET",
        headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "cookie": cookie,
            "referer": f"{CPS_ITEM_LIST_REFERER}?pageNo={page_num}",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/153.0.0.0 Safari/537.36"
            ),
            "x-requested-with": "XMLHttpRequest",
        },
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            response_body = response.read()
            status = response.status
    except HTTPError as exc:
        response_body = exc.read()
        status = exc.code
    try:
        payload: Any = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    if payload is None and browser_port is not None:
        status, response_body = fetch_cps_browser_json(
            browser_port, CPS_ITEM_ANALYSIS_URL, params, timeout=timeout,
        )
        try:
            payload = json.loads(response_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(response_body)
    return status, payload, len(response_body)


def _extract_rows(payload: Any) -> list[Any]:
    """Best-effort row extraction mirroring the warehouse parser."""
    if not isinstance(payload, dict):
        return []

    def _walk(value: Any, depth: int) -> list[Any] | None:
        if depth > 4:
            return None
        if isinstance(value, dict):
            for key in ("list", "rows", "result", "items", "pageData"):
                candidate = value.get(key)
                if isinstance(candidate, list):
                    return candidate
            for key in ("data", "result", "content"):
                candidate = value.get(key)
                if isinstance(candidate, dict):
                    found = _walk(candidate, depth + 1)
                    if found is not None:
                        return found
        return None

    rows = _walk(payload, 0)
    return rows if isinstance(rows, list) else []


def _extract_total(payload: Any) -> int | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    for source in (payload, data if isinstance(data, dict) else {}):
        for key in ("total", "totalCount", "count", "totalNum"):
            value = source.get(key)
            if isinstance(value, int):
                return value
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch CPS item-analysis pages for one day.")
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Merged one-day payload output.")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=50)
    parser.add_argument("--tb-token", default=os.getenv("CPS_TB_TOKEN", ""))
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Fetch page 1 only and print the detected row shape instead of writing output.",
    )
    add_session_source_arguments(parser)
    args = parser.parse_args()
    if args.timeout < 1:
        raise ValueError("--timeout must be positive.")
    if not 1 <= args.page_size <= 200 or args.max_pages < 1:
        raise ValueError("Invalid page-size or max-pages.")

    runtime = resolve_cps_runtime_context(
        source=args.session_source,
        cookie_env=args.cookie_env,
        tb_token=args.tb_token,
        browser_port=args.browser_port,
        report_home_url=DEFAULT_CPS_REPORT_HOME_URL,
        timeout=args.timeout,
    )

    if args.probe:
        status, payload, size = fetch_cps_items_page(
            business_day=args.day,
            page_num=1,
            page_size=min(args.page_size, 20),
            output=None,
            cookie=runtime.session.cookie_header,
            tb_token=runtime.tb_token,
            timeout=args.timeout,
            browser_port=browser_fallback_port(args.session_source, args.browser_port),
        )
        rows = _extract_rows(payload)
        first = rows[0] if rows and isinstance(rows[0], dict) else None
        print(json.dumps({
            "status": status,
            "bytes": size,
            "rows_on_page": len(rows),
            "total": _extract_total(payload),
            "first_row_keys": sorted(first.keys()) if first else [],
            "first_row": first,
        }, ensure_ascii=False, indent=2, default=str))
        return 0 if 200 <= status < 300 and rows else 1

    all_rows: list[Any] = []
    total: int | None = None
    pages_fetched = 0
    pages_dir = args.output.parent / f"_pages_{args.day.isoformat()}"
    for page_number in range(1, args.max_pages + 1):
        status, payload, size = fetch_cps_items_page(
            business_day=args.day,
            page_num=page_number,
            page_size=args.page_size,
            output=pages_dir / f"page_{page_number:03d}.json",
            cookie=runtime.session.cookie_header,
            tb_token=runtime.tb_token,
            timeout=args.timeout,
            browser_port=browser_fallback_port(args.session_source, args.browser_port),
        )
        if not 200 <= status < 300:
            raise RuntimeError(f"page {page_number} fetch failed: HTTP {status} ({size} bytes)")
        if payload is None:
            raise RuntimeError(f"page {page_number} returned non-JSON body ({size} bytes)")
        rows = _extract_rows(payload)
        total = _extract_total(payload) if total is None else total
        all_rows.extend(rows)
        pages_fetched = page_number
        print(f"page {page_number}: {len(rows)} rows (accumulated {len(all_rows)})", flush=True)
        if not rows:
            break
        if total is not None and len(all_rows) >= total:
            break
        time.sleep(0.8)

    merged = {
        "data": {"list": all_rows, "total": total if total is not None else len(all_rows)},
        "sourcePages": pages_fetched,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "status": 200,
        "day": args.day.isoformat(),
        "rows": len(all_rows),
        "total": total,
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"CPS items fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
