from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.tmall_session import add_session_source_arguments, resolve_runtime_session
from scripts.fetch_taobao_operational_snapshots import fetch_activity_items


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch one page of a Taobao online-activity item snapshot.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--snapshot-type", choices=("bybt_online", "bybt_pending", "flash_sale_online"), required=True)
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=30)
    add_session_source_arguments(parser)
    args = parser.parse_args()
    if args.page < 1 or not 1 <= args.page_size <= 200:
        raise ValueError("page must be positive and page-size must be 1..200")
    session = resolve_runtime_session(source=args.session_source, cookie_env=args.cookie_env, browser_port=args.browser_port)
    result = fetch_activity_items(output=args.output, cookie=session.cookie_header, snapshot_type=args.snapshot_type, page=args.page, page_size=args.page_size, timeout=args.timeout)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
