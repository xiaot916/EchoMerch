from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.local_database import LocalDatabase  # noqa: E402


REQUIRED_HEADERS = ("系列", "规格", "尺码", "编码")


def clean(value: object) -> str:
    return "" if value is None else str(value).replace("\ufeff", "").strip()


def pieces(value: str) -> int | None:
    value = clean(value)
    if not value or value.casefold() in {"#n/a", "n/a", "na", "-"}:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def infer_pieces(code: str, specification: str = "", series: str = "") -> int | None:
    """Infer package pieces when the source only supplies a goods code.

    The store's compact code convention puts the piece count at the end,
    e.g. ``Z125NB60``.  ``R2`` means two packs of the base count, as in
    ``Z125NB60R2``.  This inference is only a catalog convenience; warehouse
    available quantity always comes from the ERP snapshot.
    """
    value = clean(code).upper()
    if not value:
        return None
    repeat = 1
    repeated = re.search(r"R(?P<count>\d+)$", value, re.IGNORECASE)
    if repeated:
        repeat = int(repeated.group("count"))
        value = value[: repeated.start()]
    match = re.search(r"(\d+)$", value)
    if not match:
        return None
    base_count = int(match.group(1))
    # R-pack diaper codes represent multiple base packs. Other R-suffixed
    # goods (for example paper goods) should retain the suffix count itself.
    if repeated and any(token in clean(specification) for token in ("纸尿裤", "拉拉裤")):
        return base_count * repeat
    return repeat if repeated else base_count


def display_name(series: str, specification: str, size: str, piece_count: int | None) -> str | None:
    if not any((series, specification, size)):
        return None
    label = " ".join(value for value in (series, specification) if value).strip()
    if size:
        label = f"{label} {size}码".strip()
    if piece_count is not None:
        label = f"{label} {piece_count}片".strip()
    return label or None


def read_rows(path: Path) -> tuple[list[dict[str, object]], dict[str, int]]:
    previous_series = ""
    previous_specification = ""
    rows: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    seen_codes: dict[str, tuple[object, ...]] = {}
    counters = {"source_rows": 0, "duplicate_rows": 0, "invalid_rows": 0}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = [clean(value) for value in next(reader, [])]
        positions = {name: header.index(name) for name in REQUIRED_HEADERS if name in header}
        display_position = header.index("商品展示名称") if "商品展示名称" in header else None
        missing = [name for name in REQUIRED_HEADERS if name not in positions]
        if missing:
            raise ValueError(f"缺少字段: {', '.join(missing)}")
        for line_number, source in enumerate(reader, start=2):
            counters["source_rows"] += 1
            values = {name: clean(source[index] if index < len(source) else "") for name, index in positions.items()}
            values["商品展示名称"] = clean(source[display_position] if display_position is not None and display_position < len(source) else "")
            if values["系列"]:
                previous_series = values["系列"]
            else:
                values["系列"] = previous_series
            if values["规格"]:
                previous_specification = values["规格"]
            else:
                values["规格"] = previous_specification
            code = values["编码"]
            if not code:
                counters["invalid_rows"] += 1
                continue
            piece_count = pieces(values.get("片数", "")) if "片数" in positions else None
            piece_count = piece_count if piece_count is not None else infer_pieces(code, values["规格"], values["系列"])
            row = {
                "series": values["系列"],
                "specification": values["规格"],
                "size": values["尺码"],
                "goods_no": code,
                "pieces": piece_count,
                "display_name": values["商品展示名称"] or display_name(values["系列"], values["规格"], values["尺码"], piece_count),
                "source_line": line_number,
            }
            key = tuple(row[field] for field in ("series", "specification", "size", "goods_no", "pieces"))
            if key in seen:
                counters["duplicate_rows"] += 1
                continue
            code_key = str(row["goods_no"]).casefold()
            previous = seen_codes.get(code_key)
            if previous is not None and previous != key:
                # The source contains one legacy code reused by two series
                # (Z79NB32). Keep both catalog mappings so a snapshot can be
                # surfaced as an ambiguous code instead of silently dropping
                # one series.
                counters.setdefault("duplicate_code_rows", 0)
                counters["duplicate_code_rows"] += 1
            seen.add(key)
            seen_codes[code_key] = key
            rows.append(row)
    counters["rows"] = len(rows)
    counters["code_count"] = len({str(row["goods_no"]).casefold() for row in rows})
    counters["series_count"] = len({str(row["series"]) for row in rows if row["series"]})
    return rows, counters


def main() -> int:
    parser = argparse.ArgumentParser(description="导入店铺日常商品编码映射表")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--store-id", type=int, default=1)
    parser.add_argument("--database-path", type=Path, default=Path(settings.local_database_path))
    parser.add_argument("--replace-store", action="store_true", help="清空该店铺旧目录后导入；默认增量合并")
    args = parser.parse_args()

    source = args.input.expanduser().resolve()
    database_path = args.database_path.expanduser().resolve()
    rows, counters = read_rows(source)
    database = LocalDatabase(database_path)
    database.initialize_schema()
    updated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    with database.connect(initialize=True, read_only=False) as conn:
        existing_keys = {
            tuple(row)
            for row in conn.execute(
                "select series, specification, size, goods_no, pieces from inventory_product_catalog where store_id = ?",
                (args.store_id,),
            ).fetchall()
        }
        if args.replace_store:
            conn.execute("delete from inventory_product_catalog where store_id = ?", (args.store_id,))
            existing_keys = set()
        conn.executemany(
            """
            insert into inventory_product_catalog
                (store_id, series, specification, size, goods_no, pieces,
                 display_name, source, source_line, is_active, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            on conflict (store_id, series, specification, size, goods_no, pieces)
            do update set display_name=excluded.display_name, source=excluded.source,
                source_line=excluded.source_line, is_active=1, updated_at=excluded.updated_at
            """,
            [(
                args.store_id, row["series"], row["specification"], row["size"], row["goods_no"],
                row["pieces"], row["display_name"], str(source), row["source_line"], updated_at,
            ) for row in rows],
        )
        conn.commit()
    print(json.dumps({
        "status": "imported",
        "database": str(database_path),
        "store_id": args.store_id,
        "source": str(source),
        "mode": "replace" if args.replace_store else "merge",
        "inserted_rows": sum(tuple(row[field] for field in ("series", "specification", "size", "goods_no", "pieces")) not in existing_keys for row in rows),
        **counters,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
