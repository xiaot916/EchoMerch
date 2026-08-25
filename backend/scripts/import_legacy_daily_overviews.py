from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, URL


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.local_database import (  # noqa: E402
    ADD_CART_BUYERS,
    ADD_CART_ITEMS,
    ALL_SITE_PROMOTION_SPEND,
    BUSINESS_DAY,
    CONVERSION_RATE,
    CUSTOMER_UNIT_PRICE,
    DAILY_OVERVIEW_COLUMNS,
    KEYWORD_PROMOTION_SPEND,
    OLDER_PAID_AMOUNT,
    OLDER_PAID_BUYERS,
    OLDER_REPURCHASE_RATE,
    PAGE_VIEWS,
    PAID_AMOUNT,
    PAID_BUYERS,
    PAID_ITEMS,
    PAID_SUB_ORDER_COUNT,
    PLATFORM_CODE,
    PLATFORM_ID,
    PLATFORM_NAME,
    PRECISION_AUDIENCE_PROMOTION_SPEND,
    PRODUCT_FAVORITE_BUYERS,
    REFUND_FINISHED_AMOUNT,
    SMART_SCENE_SPEND,
    STATUS,
    STORE_ID,
    STORE_NAME,
    STORE_SUBJECT_ID,
    TAOKE_COMMISSION,
    LocalDatabase,
    q,
)


DEFAULT_STORE_NAME = "碧芭宝贝旗舰店"
DEFAULT_PLATFORM_STORE_ID = "2200573698992"
SOURCE_TABLE = "dailyshopdata"
LEGACY_FIELDS = (
    ("paid_amount", "支付金额", PAID_AMOUNT),
    ("visitors", "访客数", "访客数"),
    ("conversion_rate", "支付转化率", CONVERSION_RATE),
    ("customer_unit_price", "客单价", CUSTOMER_UNIT_PRICE),
    ("refund_finished_amount", "成功退款金额", REFUND_FINISHED_AMOUNT),
    ("all_site_promotion_spend", "全站推广花费", ALL_SITE_PROMOTION_SPEND),
    ("keyword_promotion_spend", "关键词推广花费", KEYWORD_PROMOTION_SPEND),
    (
        "precision_audience_promotion_spend",
        "精准人群推广花费",
        PRECISION_AUDIENCE_PROMOTION_SPEND,
    ),
    ("smart_scene_spend", "智能场景花费", SMART_SCENE_SPEND),
    ("taoke_commission", "淘宝客佣金", TAOKE_COMMISSION),
    ("paid_buyers", "支付买家数", PAID_BUYERS),
    ("older_repurchase_rate", "老客复购率", OLDER_REPURCHASE_RATE),
    ("older_paid_buyers", "支付老买家数", OLDER_PAID_BUYERS),
    ("older_paid_amount", "老买家支付金额", OLDER_PAID_AMOUNT),
    ("paid_sub_order_count", "支付子订单数", PAID_SUB_ORDER_COUNT),
    ("paid_items", "支付件数", PAID_ITEMS),
    ("add_cart_buyers", "加购人数", ADD_CART_BUYERS),
    ("add_cart_items", "加购件数", ADD_CART_ITEMS),
    ("product_favorite_buyers", "收藏人数", PRODUCT_FAVORITE_BUYERS),
    ("page_views", "浏览量", PAGE_VIEWS),
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy historical dailyshopdata rows from the legacy database into the local overview table."
    )
    parser.add_argument("--legacy-database-url", default=os.getenv("LEGACY_DATABASE_URL", ""))
    parser.add_argument("--legacy-env-file", type=Path)
    parser.add_argument("--source-table", default=SOURCE_TABLE)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--store-id", type=int, default=1)
    parser.add_argument("--store-name", default=DEFAULT_STORE_NAME)
    parser.add_argument("--platform-store-id", default=DEFAULT_PLATFORM_STORE_ID)
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--database-path",
        type=Path,
        default=Path(settings.local_database_path),
    )
    args = parser.parse_args()

    if args.end is not None and args.start is not None and args.end < args.start:
        raise ValueError("--end must be greater than or equal to --start.")
    if not re.fullmatch(r"[A-Za-z0-9_]+", args.source_table):
        raise ValueError("--source-table may contain only letters, digits, and underscores.")

    source_engine = build_legacy_engine(
        database_url=args.legacy_database_url,
        env_file=args.legacy_env_file,
    )
    try:
        rows = list(
            fetch_legacy_rows(
                source_engine,
                source_table=args.source_table,
                start=args.start,
                end=args.end,
            )
        )
    finally:
        source_engine.dispose()

    database_path = args.database_path.expanduser().resolve()
    if args.dry_run:
        print(
            {
                "status": "dry_run",
                "source_rows": len(rows),
                "first_day": rows[0][BUSINESS_DAY] if rows else None,
                "last_day": rows[-1][BUSINESS_DAY] if rows else None,
                "database_path": str(database_path),
            }
        )
        return 0

    result = import_rows(
        database_path=database_path,
        rows=rows,
        store_id=args.store_id,
        store_name=args.store_name,
        platform_store_id=args.platform_store_id,
        refresh_existing=args.refresh_existing,
    )
    print(result)
    return 0


def build_legacy_engine(*, database_url: str, env_file: Path | None) -> Engine:
    if database_url.strip():
        return create_engine(database_url.strip(), pool_pre_ping=True, future=True)
    if env_file is None:
        raise ValueError(
            "Set LEGACY_DATABASE_URL or pass --legacy-env-file for the one-time historical import."
        )

    values = parse_env_file(env_file)
    required = (
        "DATABASE_HOST",
        "DATABASE_USER",
        "DATABASE_PASSWORD",
        "DATABASE_NAME",
        "DATABASE_PORT",
    )
    missing = [name for name in required if not values.get(name)]
    if missing:
        raise ValueError(f"Legacy environment file is missing: {', '.join(missing)}")
    url = URL.create(
        "mysql+pymysql",
        username=values["DATABASE_USER"],
        password=values["DATABASE_PASSWORD"],
        host=values["DATABASE_HOST"],
        port=int(values["DATABASE_PORT"]),
        database=values["DATABASE_NAME"],
        query={"charset": "utf8mb4"},
    )
    return create_engine(url, pool_pre_ping=True, future=True)


def parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"Legacy environment file was not found: {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped.removeprefix("export ").lstrip()
        name, separator, value = stripped.partition("=")
        if not separator or not name.strip():
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[name.strip()] = value
    return values


def fetch_legacy_rows(
    engine: Engine,
    *,
    source_table: str,
    start: date | None,
    end: date | None,
) -> Iterable[dict[str, str | None]]:
    filters: list[str] = []
    params: dict[str, object] = {}
    if start is not None:
        filters.append("`日期` >= :start_day")
        params["start_day"] = start
    if end is not None:
        filters.append("`日期` <= :end_day")
        params["end_day"] = end
    where_clause = f"where {' and '.join(filters)}" if filters else ""
    select_fields = ["`日期` as business_day"]
    select_fields.extend(f"`{source}` as {alias}" for alias, source, _ in LEGACY_FIELDS)
    statement = text(
        f"""
        select {', '.join(select_fields)}
        from `{source_table}`
        {where_clause}
        order by `日期`
        """
    )
    with engine.connect() as connection:
        connection.execute(text("SET SESSION TRANSACTION READ ONLY"))
        for row in connection.execute(statement, params).mappings():
            yield legacy_row_to_overview_values(row)


def legacy_row_to_overview_values(row: Mapping[str, object]) -> dict[str, str | None]:
    business_day = _business_day(row.get("business_day"))
    values = {column: None for column in DAILY_OVERVIEW_COLUMNS}
    values[BUSINESS_DAY] = business_day.isoformat()
    for alias, _source_column, target_column in LEGACY_FIELDS:
        values[target_column] = _numeric_text(row.get(alias))
    return values


def import_rows(
    *,
    database_path: Path,
    rows: list[dict[str, str | None]],
    store_id: int,
    store_name: str,
    platform_store_id: str,
    refresh_existing: bool,
) -> dict[str, object]:
    database = LocalDatabase(database_path)
    database.initialize_schema()
    with database.connect(initialize=True) as connection:
        _ensure_store_reference(
            connection,
            store_id=store_id,
            store_name=store_name,
            platform_store_id=platform_store_id,
        )
        existing_days = {
            str(row["business_day"])
            for row in connection.execute(
                f"select {q(BUSINESS_DAY)} as business_day from store_daily_overviews "
                f"where {q(STORE_ID)} = ?",
                (store_id,),
            )
        }
        selected_rows = rows if refresh_existing else [
            row for row in rows if row[BUSINESS_DAY] not in existing_days
        ]
        insert_columns = list(DAILY_OVERVIEW_COLUMNS)
        update_columns = insert_columns[2:]
        statement = f"""
            insert into store_daily_overviews (
                {', '.join(q(column) for column in insert_columns)}
            ) values ({', '.join('?' for _ in insert_columns)})
            on conflict({q(STORE_ID)}, {q(BUSINESS_DAY)}) do update set
                {', '.join(f'{q(column)} = excluded.{q(column)}' for column in update_columns)}
        """
        connection.executemany(
            statement,
            [
                (
                    store_id,
                    row[BUSINESS_DAY],
                    *[row[column] for column in insert_columns[2:]],
                )
                for row in selected_rows
            ],
        )
        connection.commit()

    return {
        "status": "completed",
        "source_rows": len(rows),
        "inserted": len(selected_rows),
        "skipped_existing": len(rows) - len(selected_rows),
        "first_day": rows[0][BUSINESS_DAY] if rows else None,
        "last_day": rows[-1][BUSINESS_DAY] if rows else None,
        "database_path": str(database_path),
    }


def _ensure_store_reference(
    connection: Any,
    *,
    store_id: int,
    store_name: str,
    platform_store_id: str,
) -> None:
    platform = connection.execute(
        f"select {q(PLATFORM_ID)} as platform_id from platforms "
        f"where {q(PLATFORM_CODE)} = ?",
        ("tmall",),
    ).fetchone()
    if platform is None:
        platform_id = int(
            connection.execute(
                f"select coalesce(max({q(PLATFORM_ID)}), 0) + 1 as platform_id from platforms"
            ).fetchone()["platform_id"]
        )
        connection.execute(
            f"insert into platforms ({q(PLATFORM_ID)}, {q(PLATFORM_CODE)}, {q(PLATFORM_NAME)}, "
            f"{q(STATUS)}, \"创建时间\", \"更新时间\") values (?, ?, ?, ?, datetime('now'), datetime('now'))",
            (platform_id, "tmall", "天猫", "active"),
        )
    else:
        platform_id = int(platform["platform_id"])

    store = connection.execute(
        f"select {q(STORE_ID)} as store_id from stores where {q(STORE_ID)} = ?",
        (store_id,),
    ).fetchone()
    if store is None:
        connection.execute(
            f"insert into stores ({q(STORE_ID)}, {q(PLATFORM_ID)}, {q(STORE_SUBJECT_ID)}, "
            f"{q(STORE_NAME)}, {q(STATUS)}, \"首次发现时间\", \"更新时间\") "
            "values (?, ?, ?, ?, ?, datetime('now'), datetime('now'))",
            (store_id, platform_id, platform_store_id, store_name, "active"),
        )
        return
    connection.execute(
        f"update stores set {q(PLATFORM_ID)} = ?, {q(STORE_SUBJECT_ID)} = ?, "
        f"{q(STORE_NAME)} = ?, {q(STATUS)} = ?, \"更新时间\" = datetime('now') "
        f"where {q(STORE_ID)} = ?",
        (platform_id, platform_store_id, store_name, "active", store_id),
    )


def _business_day(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Legacy dailyshopdata contains an invalid business day: {value!r}") from exc


def _numeric_text(value: object) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return str(Decimal(str(value)))
    except Exception as exc:
        raise ValueError(f"Legacy dailyshopdata contains a non-numeric metric: {value!r}") from exc


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"Legacy overview import failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
