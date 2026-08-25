from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.modules.captures.analyzer import analyze_capture_directory, write_markdown_report


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Reqable captures offline.")
    parser.add_argument("--capture-dir", required=True, type=Path)
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("artifacts/local/reqable_capture.sqlite3"),
    )
    parser.add_argument("--report", type=Path, default=Path("docs/REQABLE_CAPTURE_ANALYSIS.md"))
    parser.add_argument("--since", type=parse_date)
    parser.add_argument("--until", type=parse_date)
    args = parser.parse_args()

    summary = analyze_capture_directory(
        args.capture_dir,
        args.database,
        since=args.since,
        until=args.until,
    )
    write_markdown_report(args.report, summary)
    console_summary = {
        "window_start": summary.get("window_start"),
        "window_end": summary.get("window_end"),
        "file_count": summary.get("file_count"),
        "analyzed_count": summary.get("analyzed_count"),
        "daily": summary.get("daily", []),
        "families": summary.get("families", []),
        "endpoint_candidates": len(summary.get("endpoints", [])),
        "field_paths": len(summary.get("fields", [])),
    }
    print(json.dumps(console_summary, ensure_ascii=False, indent=2))
    print(f"report={args.report}")
    print(f"database={args.database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
