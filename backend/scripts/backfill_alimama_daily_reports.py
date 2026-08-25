from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.tmall_session import (  # noqa: E402
    add_session_source_arguments,
    resolve_alimama_runtime_context,
)
from scripts.fetch_alimama_rtb_report import (  # noqa: E402
    BIDWORD_REPORT_FIELDS,
    REPORT_CONFIG,
    alimama_report_home,
    fetch_alimama_report,
)


def _days(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _page_rows(payload: object) -> tuple[list[object], int | None]:
    if not isinstance(payload, dict):
        return [], None
    data = payload.get("data")
    if not isinstance(data, dict):
        return [], None
    rows = data.get("list")
    count = data.get("count")
    return (rows if isinstance(rows, list) else [], int(count) if count is not None else None)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Alimama reports one business day at a time with offset pagination."
    )
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--rpt-type", choices=sorted(REPORT_CONFIG), default="bidword")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--csrf-id", default=os.getenv("RTB_CSRF_ID", ""))
    parser.add_argument("--login-point-id", default=os.getenv("RTB_LOGIN_POINT_ID", ""))
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--max-pages", type=int, default=1000)
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--timeout", type=int, default=30)
    add_session_source_arguments(parser)
    args = parser.parse_args()

    if args.end < args.start:
        raise ValueError("--end must be greater than or equal to --start.")
    if not 1 <= args.page_size <= 100 or args.max_pages < 1 or args.sleep < 0:
        raise ValueError("Invalid page-size, max-pages, or sleep value.")

    config = REPORT_CONFIG[args.rpt_type]
    args.output_dir = args.output_dir.expanduser().resolve()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    runtime = resolve_alimama_runtime_context(
        source=args.session_source,
        cookie_env=args.cookie_env,
        csrf_id=args.csrf_id,
        login_point_id=args.login_point_id,
        browser_port=args.browser_port,
        report_home_url=alimama_report_home(args.rpt_type),
        timeout=args.timeout,
    )

    for business_day in _days(args.start, args.end):
        day_dir = args.output_dir / args.rpt_type / business_day.isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        pages: list[dict[str, object]] = []
        offset = 0
        stored_rows = 0
        stop_reason = "max_pages"

        for page_number in range(1, args.max_pages + 1):
            page_file = day_dir / f"page_{page_number:04d}_offset_{offset}.json"
            status, code, message, _ = fetch_alimama_report(
                start_day=business_day,
                end_day=business_day,
                output=page_file,
                cookie=runtime.session.cookie_header,
                csrf_id=runtime.csrf_id,
                login_point_id=runtime.login_point_id,
                rpt_type=args.rpt_type,
                query_fields=config["fields"],
                query_domains=config["domains"],
                biz_codes=config["biz_codes"],
                by_page_without_count=bool(config.get("by_page_without_count", False)),
                extra_body=config.get("extra_body"),
                offset=offset,
                page_size=args.page_size,
            )
            if not 200 <= status < 300 or code != 0:
                raise RuntimeError(
                    f"{business_day} page {page_number} failed: HTTP {status}, code {code}, message {message}."
                )
            payload = json.loads(page_file.read_text(encoding="utf-8"))
            pages.append(payload)
            rows, count = _page_rows(payload)
            stored_rows += len(rows)
            print(f"{business_day} page {page_number}: rows {len(rows)} offset {offset}")
            if not rows:
                stop_reason = "no_more_rows"
                break
            count_finished = (
                not config.get("by_page_without_count", False)
                and count is not None
                and offset + len(rows) >= count
            )
            if len(rows) < args.page_size or count_finished:
                stop_reason = "last_page"
                break
            offset += len(rows)
            if args.sleep:
                time.sleep(args.sleep)

        combined_file = args.output_dir / f"{args.rpt_type}_{business_day.isoformat()}.json"
        combined_file.write_text(
            json.dumps({"businessDay": business_day.isoformat(), "pages": pages}, ensure_ascii=False),
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "business_day": business_day.isoformat(),
                    "rpt_type": args.rpt_type,
                    "pages": len(pages),
                    "rows": stored_rows,
                    "stop_reason": stop_reason,
                    "output": str(combined_file),
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Daily Alimama import failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
