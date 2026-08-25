from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.warehouse.store import WarehouseStore  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest a saved SYCM traffic source tree response.")
    parser.add_argument("--response-file", type=Path, required=True)
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--store-name", default="碧芭宝贝旗舰店")
    parser.add_argument("--platform-store-id", default="2200573698992")
    parser.add_argument("--http-status", type=int, default=200)
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path(settings.local_database_path),
    )
    args = parser.parse_args()

    result = WarehouseStore(args.database_path).ingest_sycm_traffic_source(
        source_path=args.response_file,
        business_day=args.day,
        store_name=args.store_name,
        platform_store_id=args.platform_store_id,
        http_status=args.http_status,
    )
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, ValidationError) as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
