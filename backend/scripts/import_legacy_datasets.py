from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from sqlalchemy import text
from sqlalchemy.engine import Engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import settings  # noqa: E402
from app.core.local_database import (  # noqa: E402
    BRAND_ZONE_CLICK_RATE,
    BRAND_ZONE_CLICK_VISITORS,
    BRAND_ZONE_CLICKS,
    BRAND_ZONE_CONVERSION_RATE,
    BRAND_ZONE_IMPRESSIONS,
    BRAND_ZONE_ITEM_CART_COUNT,
    BRAND_ZONE_PAID_AMOUNT,
    BRAND_ZONE_PAID_ORDER_COUNT,
    BRAND_ZONE_SEARCH_REQUESTS,
    BRAND_ZONE_COLUMNS,
    BUSINESS_DAY,
    BYBT_COLUMNS,
    CPS_COLUMNS,
    CUSTOMER_UNIT_PRICE,
    FLOW_PRODUCT_VISITORS,
    LIVE_OVERVIEW_COLUMNS,
    LIVE_STORE_PERFORMANCE_COLUMNS,
    LIVE_TALENT_COLUMNS,
    LIVE_TALENT_ID,
    LIVE_TALENT_NAME,
    LIVE_TALENT_TABLE,
    MEMBER_ANALYSIS_OVERVIEW_FIELDS,
    MEMBER_CORE_REPURCHASE_RATE,
    MEMBER_PAID_AMOUNT,
    MEMBER_PAID_COUNT,
    MEMBER_TOTAL_COUNT,
    MEMBER_UNIT_PRICE,
    PAID_AMOUNT,
    PAID_BUYERS,
    PRODUCT_RANKING_COLUMNS,
    PRODUCT_RANKING_ITEM_ID,
    PRODUCT_RANKING_ITEM_NAME,
    PRODUCT_RANKING_ITEM_STATUS,
    PRODUCT_RANKING_TABLE,
    PROMOTION_CAMPAIGN_COLUMNS,
    PROMOTION_CAMPAIGN_ID,
    PROMOTION_CAMPAIGN_METRICS,
    PROMOTION_CAMPAIGN_NAME,
    PROMOTION_CAMPAIGN_TABLE,
    PROMOTION_SCENE_NAME,
    SHOPPING_GOLD_COLUMNS,
    SOURCE_LEVEL,
    STORE_ID,
    TAOBAO_FLASH_SALE_COLUMNS,
    TRAFFIC_SOURCE_LEVEL_1,
    TRAFFIC_SOURCE_LEVEL_2,
    TRAFFIC_SOURCE_LEVEL_3,
    CONVERSION_RATE,
    q,
    LocalDatabase,
)
from scripts.import_legacy_daily_overviews import (  # noqa: E402
    DEFAULT_PLATFORM_STORE_ID,
    DEFAULT_STORE_NAME,
    _business_day,
    _ensure_store_reference,
    _numeric_text,
    build_legacy_engine,
)


@dataclass(frozen=True)
class DailyDataset:
    key: str
    source_table: str
    source_day_column: str
    target_table: str
    target_columns: tuple[str, ...]
    source_columns: tuple[tuple[str, str], ...]


SIMPLE_DATASETS = (
    DailyDataset(
        key="bybt",
        source_table="statistics",
        source_day_column="日期",
        target_table="store_daily_bybt_overviews",
        target_columns=BYBT_COLUMNS,
        source_columns=(
            ("百补访客数", "百补访客数"),
            ("百补支付买家数", "百补支付买家数"),
            ("百补在线商品数量", "百补在线商品数量"),
            ("百补支付金额", "百补支付金额"),
            ("百补子订单数", "百补子订单数"),
            ("百补支付成交件数", "百补支付成交件数"),
        ),
    ),
    DailyDataset(
        key="taobao_flash_sale",
        source_table="taobao_seckill",
        source_day_column="日期",
        target_table="store_daily_taobao_flash_sale_overviews",
        target_columns=TAOBAO_FLASH_SALE_COLUMNS,
        source_columns=(
            ("活动中商品量级", "秒杀商品量级"),
            ("活动商品IPV", "秒杀商品PV"),
            ("活动商品IPVUV", "秒杀商品UV"),
            ("活动商品成交笔数", "秒杀成交笔数"),
            ("活动商品成交金额", "秒杀成交金额"),
            ("活动商品引导店铺新客", "秒杀引导店铺新客"),
            ("活动商品最高爆发系数", "秒杀商品最高爆发系数"),
        ),
    ),
    DailyDataset(
        key="member_core",
        source_table="member_overview",
        source_day_column="日期",
        target_table="store_daily_member_analysis_overviews",
        target_columns=(
            STORE_ID,
            BUSINESS_DAY,
            *[column for column, _ in MEMBER_ANALYSIS_OVERVIEW_FIELDS],
        ),
        source_columns=(
            (MEMBER_TOTAL_COUNT, "会员总数"),
            (MEMBER_PAID_COUNT, "会员成交人数"),
            (MEMBER_PAID_AMOUNT, "会员成交金额"),
            (MEMBER_UNIT_PRICE, "会员客单价"),
            (MEMBER_CORE_REPURCHASE_RATE, "会员复购率"),
        ),
    ),
    DailyDataset(
        key="shopping_gold",
        source_table="shopping_gold",
        source_day_column="统计日期",
        target_table="store_daily_shopping_gold_overviews",
        target_columns=SHOPPING_GOLD_COLUMNS,
        source_columns=(
            ("人均充值金额", "人均充值金额"),
            ("充值总金额", "充值总金额"),
            (PAID_BUYERS, "支付买家数"),
            ("充值件数", "充值件数"),
            ("充值成功退款金额", "充值成功退款金额"),
            (PAID_AMOUNT, "支付金额"),
            (CUSTOMER_UNIT_PRICE, "客单价"),
            ("充值本金金额", "充值本金金额"),
            ("充值买家数", "充值买家数"),
            ("充值转化率", "充值转化率"),
            (FLOW_PRODUCT_VISITORS, "商品访客数"),
            ("充值子订单数", "充值子订单数"),
        ),
    ),
    DailyDataset(
        key="cps",
        source_table="cps_overview",
        source_day_column="日期",
        target_table="store_daily_cps_overviews",
        target_columns=CPS_COLUMNS,
        source_columns=(
            ("CPS付款佣金支出", "付款佣金支出"),
            ("CPS付款服务费支出", "付款服务费支出"),
            ("CPS付款佣金率", "付款佣金率"),
            ("CPS付款服务费率", "付款服务费率"),
            ("CPS付款笔数", "付款笔数"),
            ("CPS付款金额", "付款金额"),
            ("CPS点击人数", "点击数（即进店量）"),
            ("CPS结算支出费用", "结算支出费用"),
            ("CPS结算笔数", "结算笔数"),
            ("CPS结算金额", "结算金额"),
            ("CPS预售定金笔数", "预售定金笔数"),
            ("CPS预售定金金额", "预售定金金额"),
            ("CPS预估预售尾款金额", "预估预售尾款金额"),
            ("CPS预估预售整单金额", "预估预售整单金额"),
            ("CPS付款营销服务费支出", "付款营销服务费支出"),
            ("CPS结算营销服务费支出", "结算营销服务费支出"),
        ),
    ),
    DailyDataset(
        key="brand_zone",
        source_table="brand_zone_data",
        source_day_column="日期",
        target_table="store_daily_brand_zone_overviews",
        target_columns=BRAND_ZONE_COLUMNS,
        source_columns=(
            (BRAND_ZONE_IMPRESSIONS, "展现量"),
            (BRAND_ZONE_SEARCH_REQUESTS, "搜索量"),
            (BRAND_ZONE_CLICKS, "点击量"),
            (BRAND_ZONE_CLICK_RATE, "点击率"),
            (BRAND_ZONE_CLICK_VISITORS, "点击访客数"),
            (BRAND_ZONE_ITEM_CART_COUNT, "宝贝加购数"),
            (BRAND_ZONE_PAID_AMOUNT, "成交金额"),
            (BRAND_ZONE_PAID_ORDER_COUNT, "成交笔数"),
            (BRAND_ZONE_CONVERSION_RATE, "转化率"),
        ),
    ),
    DailyDataset(
        key="live_overview",
        source_table="live_overview",
        source_day_column="日期",
        target_table="store_daily_live_overviews",
        target_columns=LIVE_OVERVIEW_COLUMNS,
        source_columns=tuple((column, column) for column in LIVE_OVERVIEW_COLUMNS[2:]),
    ),
    DailyDataset(
        key="live_store_performance",
        source_table="store_living_data",
        source_day_column="日期",
        target_table="store_daily_live_store_performance",
        target_columns=LIVE_STORE_PERFORMANCE_COLUMNS,
        source_columns=tuple(
            (column, column) for column in LIVE_STORE_PERFORMANCE_COLUMNS[2:]
        ),
    ),
)

PRODUCT_DATASET = DailyDataset(
    key="product_rankings",
    source_table="product_sales_daily",
    source_day_column="日期",
    target_table=PRODUCT_RANKING_TABLE,
    target_columns=PRODUCT_RANKING_COLUMNS,
    source_columns=(
        (PRODUCT_RANKING_ITEM_ID, "商品ID"),
        (PRODUCT_RANKING_ITEM_NAME, "商品名称"),
        ("支付金额", "支付金额"),
        ("总支付金额", "总支付金额"),
        ("退款金额（完结时间）", "成功退款金额"),
        ("支付件数", "支付件数"),
        ("总支付商品件数", "总支付商品件数"),
        (PAID_BUYERS, "支付买家数"),
        ("支付转化率", "商品支付转化率"),
        ("支付新买家数", "支付新买家数"),
        ("支付老买家数", "支付老买家数"),
        ("老客复购金额", "老买家支付金额"),
        ("聚划算支付金额", "聚划算支付金额"),
        ("月累计支付金额", "月累计支付金额"),
        ("月累计支付件数", "月累计支付件数"),
        ("年累计支付金额", "年累计支付金额"),
        (PRODUCT_RANKING_ITEM_STATUS, "商品状态"),
        ("商品加购件数", "商品加购件数"),
        ("商品加购人数", "商品加购人数"),
        ("商品收藏人数", "商品收藏人数"),
        ("商品访客数", "商品访客数"),
        ("商品浏览量", "商品浏览量"),
        ("平均停留时长", "平均停留时长"),
        ("商品详情页跳出率", "商品详情页跳出率"),
        ("搜索引导访客数", "搜索引导访客数"),
        ("搜索引导支付买家数", "搜索引导支付买家数"),
        ("搜索引导支付转化率", "搜索引导支付转化率"),
        ("访客平均价值", "访客平均价值"),
    ),
)

TRAFFIC_DATASET = DailyDataset(
    key="traffic_sources",
    source_table="traffic_source",
    source_day_column="日期",
    target_table="store_daily_traffic_sources",
    target_columns=(
        STORE_ID,
        BUSINESS_DAY,
        TRAFFIC_SOURCE_LEVEL_1,
        TRAFFIC_SOURCE_LEVEL_2,
        TRAFFIC_SOURCE_LEVEL_3,
        SOURCE_LEVEL,
        "访客数",
        "新访客数",
        "加购人数",
        "商品收藏人数",
        PAID_BUYERS,
        "支付转化率",
        PAID_AMOUNT,
        "支付金额占比",
        "UV价值",
        "下单买家数",
        "下单金额",
        "下单转化率",
    ),
    source_columns=(
        (TRAFFIC_SOURCE_LEVEL_1, "一级来源"),
        (TRAFFIC_SOURCE_LEVEL_2, "二级来源"),
        (TRAFFIC_SOURCE_LEVEL_3, "三级来源"),
        ("访客数", "访客数"),
        ("新访客数", "新访客数"),
        ("加购人数", "加购人数"),
        ("商品收藏人数", "商品收藏人数"),
        (PAID_BUYERS, "支付买家数"),
        ("支付转化率", "支付转化率"),
        (PAID_AMOUNT, "支付金额"),
        ("支付金额占比", "支付金额占比"),
        ("UV价值", "UV价值"),
        ("下单买家数", "下单买家数"),
        ("下单金额", "下单金额"),
        ("下单转化率", "下单转化率"),
    ),
)

PROMOTION_CAMPAIGN_DATASET = DailyDataset(
    key="promotion_campaigns",
    source_table="rtb_plan_data",
    source_day_column="日期",
    target_table=PROMOTION_CAMPAIGN_TABLE,
    target_columns=PROMOTION_CAMPAIGN_COLUMNS,
    source_columns=(
        (PROMOTION_SCENE_NAME, "场景名字"),
        (PROMOTION_CAMPAIGN_ID, "计划ID"),
        (PROMOTION_CAMPAIGN_NAME, "计划名字"),
        *(
            (
                column,
                {
                    "宝贝收藏数": "收藏宝贝数",
                    "店铺收藏数": "收藏店铺数",
                }.get(column, column),
            )
            for column in PROMOTION_CAMPAIGN_METRICS
        ),
    ),
)

LIVE_TALENT_DATASET = DailyDataset(
    key="live_talent_reports",
    source_table="live_talent_data",
    source_day_column="日期",
    target_table=LIVE_TALENT_TABLE,
    target_columns=LIVE_TALENT_COLUMNS,
    source_columns=(
        (LIVE_TALENT_ID, LIVE_TALENT_ID),
        (LIVE_TALENT_NAME, LIVE_TALENT_NAME),
        *((column, column) for column in LIVE_TALENT_COLUMNS[4:]),
    ),
)

ALL_DATASETS = (
    *SIMPLE_DATASETS,
    PRODUCT_DATASET,
    TRAFFIC_DATASET,
    PROMOTION_CAMPAIGN_DATASET,
    LIVE_TALENT_DATASET,
)
TRAFFIC_SUM_COLUMNS = (
    "访客数",
    "新访客数",
    "加购人数",
    "商品收藏人数",
    PAID_BUYERS,
    PAID_AMOUNT,
    "下单买家数",
    "下单金额",
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy compatible historical data from the legacy MySQL database into local fact tables."
    )
    parser.add_argument("--legacy-database-url", default="")
    parser.add_argument("--legacy-env-file", type=Path)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--dataset", action="append", choices=[item.key for item in ALL_DATASETS])
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

    if args.start and args.end and args.end < args.start:
        raise ValueError("--end must be greater than or equal to --start.")
    selected = tuple(
        item for item in ALL_DATASETS if not args.dataset or item.key in set(args.dataset)
    )
    source_engine = build_legacy_engine(
        database_url=args.legacy_database_url,
        env_file=args.legacy_env_file,
    )
    try:
        source_rows = {
            item.key: list(fetch_dataset_rows(source_engine, item, args.start, args.end))
            for item in selected
        }
    finally:
        source_engine.dispose()

    if args.dry_run:
        print({"status": "dry_run", "datasets": {key: len(rows) for key, rows in source_rows.items()}})
        return 0

    result = import_datasets(
        database_path=args.database_path.expanduser().resolve(),
        datasets=selected,
        source_rows=source_rows,
        store_id=args.store_id,
        store_name=args.store_name,
        platform_store_id=args.platform_store_id,
        refresh_existing=args.refresh_existing,
    )
    print(result)
    return 0


def fetch_dataset_rows(
    engine: Engine,
    dataset: DailyDataset,
    start: date | None,
    end: date | None,
) -> Iterable[dict[str, str | None]]:
    source_names = (dataset.source_day_column, *[source for _, source in dataset.source_columns])
    selected_names = tuple(dict.fromkeys(source_names))
    filters: list[str] = []
    params: dict[str, object] = {}
    if start is not None:
        filters.append(f"{_mysql_q(dataset.source_day_column)} >= :start_day")
        params["start_day"] = start
    if end is not None:
        filters.append(f"{_mysql_q(dataset.source_day_column)} <= :end_day")
        params["end_day"] = end
    where_clause = f"where {' and '.join(filters)}" if filters else ""
    statement = text(
        f"""
        select {', '.join(_mysql_q(column) for column in selected_names)}
        from `{dataset.source_table}`
        {where_clause}
        order by {_mysql_q(dataset.source_day_column)}
        """
    )
    with engine.connect() as connection:
        connection.execute(text("SET SESSION TRANSACTION READ ONLY"))
        for row in connection.execute(statement, params).mappings():
            yield map_source_row(dataset, row)


def map_source_row(dataset: DailyDataset, row: Mapping[str, object]) -> dict[str, str | None]:
    values = {column: None for column in dataset.target_columns[2:]}
    values[BUSINESS_DAY] = _business_day(row.get(dataset.source_day_column)).isoformat()
    for target_column, source_column in dataset.source_columns:
        if target_column in values:
            values[target_column] = _value_for_column(target_column, row.get(source_column))
    if dataset.key == "traffic_sources":
        level_2 = values[TRAFFIC_SOURCE_LEVEL_2] or ""
        level_3 = values[TRAFFIC_SOURCE_LEVEL_3] or ""
        values[TRAFFIC_SOURCE_LEVEL_2] = level_2
        values[TRAFFIC_SOURCE_LEVEL_3] = level_3
        values[SOURCE_LEVEL] = "3" if level_3 else "2" if level_2 else "1"
    elif dataset.key == "promotion_campaigns":
        for column in (
            PROMOTION_SCENE_NAME,
            PROMOTION_CAMPAIGN_ID,
            PROMOTION_CAMPAIGN_NAME,
        ):
            values[column] = values[column] or ""
    elif dataset.key == "live_talent_reports":
        values[LIVE_TALENT_ID] = values[LIVE_TALENT_ID] or ""
        values[LIVE_TALENT_NAME] = values[LIVE_TALENT_NAME] or ""
    return values


def import_datasets(
    *,
    database_path: Path,
    datasets: tuple[DailyDataset, ...],
    source_rows: Mapping[str, list[dict[str, str | None]]],
    store_id: int,
    store_name: str,
    platform_store_id: str,
    refresh_existing: bool,
) -> dict[str, object]:
    database = LocalDatabase(database_path)
    database.initialize_schema()
    results: dict[str, dict[str, int]] = {}
    with database.connect(initialize=True) as connection:
        _ensure_store_reference(
            connection,
            store_id=store_id,
            store_name=store_name,
            platform_store_id=platform_store_id,
        )
        for dataset in datasets:
            rows = source_rows[dataset.key]
            results[dataset.key] = _upsert_dataset_rows(
                connection=connection,
                dataset=dataset,
                rows=rows,
                store_id=store_id,
                refresh_existing=refresh_existing,
            )
        connection.commit()
    return {"status": "completed", "datasets": results, "database_path": str(database_path)}


def _upsert_dataset_rows(
    *,
    connection: Any,
    dataset: DailyDataset,
    rows: list[dict[str, str | None]],
    store_id: int,
    refresh_existing: bool,
) -> dict[str, int]:
    if not rows:
        return {"source_rows": 0, "inserted": 0, "skipped_existing": 0}
    key_columns = _key_columns(dataset)
    source_unique = (
        _aggregate_traffic_rows(rows)
        if dataset.key == "traffic_sources"
        else _unique_rows(rows, key_columns)
    )
    existing = {
        tuple(str(row[column]) for column in key_columns[1:])
        for row in connection.execute(
            f"select {', '.join(q(column) for column in key_columns[1:])} "
            f"from {dataset.target_table} where {q(STORE_ID)} = ?",
            (store_id,),
        )
    }
    selected = source_unique if refresh_existing else [
        row for row in source_unique if tuple(row[column] or "" for column in key_columns[1:]) not in existing
    ]
    insert_columns = dataset.target_columns
    update_columns = insert_columns[len(key_columns) :]
    statement = f"""
        insert into {dataset.target_table} ({', '.join(q(column) for column in insert_columns)})
        values ({', '.join('?' for _ in insert_columns)})
        on conflict({', '.join(q(column) for column in key_columns)}) do update set
            {', '.join(f'{q(column)} = excluded.{q(column)}' for column in update_columns)}
    """
    connection.executemany(
        statement,
        [
            (store_id, *[row.get(column) for column in insert_columns[1:]])
            for row in selected
        ],
    )
    return {
        "source_rows": len(rows),
        "unique_rows": len(source_unique),
        "inserted": len(selected),
        "skipped_existing": len(source_unique) - len(selected),
    }


def _key_columns(dataset: DailyDataset) -> tuple[str, ...]:
    if dataset.key == "product_rankings":
        return STORE_ID, BUSINESS_DAY, PRODUCT_RANKING_ITEM_ID
    if dataset.key == "traffic_sources":
        return (
            STORE_ID,
            BUSINESS_DAY,
            SOURCE_LEVEL,
            TRAFFIC_SOURCE_LEVEL_1,
            TRAFFIC_SOURCE_LEVEL_2,
            TRAFFIC_SOURCE_LEVEL_3,
        )
    if dataset.key == "promotion_campaigns":
        return STORE_ID, BUSINESS_DAY, PROMOTION_CAMPAIGN_ID
    if dataset.key == "live_talent_reports":
        return STORE_ID, BUSINESS_DAY, LIVE_TALENT_ID
    return STORE_ID, BUSINESS_DAY


def _aggregate_traffic_rows(rows: list[dict[str, str | None]]) -> list[dict[str, str | None]]:
    """Collapse old recursive rows that lost their third-level source label."""
    grouped: dict[tuple[str, ...], dict[str, Decimal]] = {}
    labels: dict[tuple[str, ...], dict[str, str | None]] = {}
    for row in rows:
        key = tuple(
            row.get(column) or ""
            for column in (
                BUSINESS_DAY,
                SOURCE_LEVEL,
                TRAFFIC_SOURCE_LEVEL_1,
                TRAFFIC_SOURCE_LEVEL_2,
                TRAFFIC_SOURCE_LEVEL_3,
            )
        )
        sums = grouped.setdefault(key, {column: Decimal("0") for column in TRAFFIC_SUM_COLUMNS})
        labels.setdefault(key, dict(row))
        for column in TRAFFIC_SUM_COLUMNS:
            sums[column] += _decimal_or_zero(row.get(column))

    result: list[dict[str, str | None]] = []
    day_totals: dict[str, Decimal] = {}
    for key, sums in grouped.items():
        day, source_level, *_ = key
        if source_level == "1":
            day_totals[day] = day_totals.get(day, Decimal("0")) + sums[PAID_AMOUNT]

    for key, sums in grouped.items():
        day, _source_level, *_ = key
        row = labels[key]
        for column, value in sums.items():
            row[column] = _decimal_text(value)
        visitors = sums["访客数"]
        row[CONVERSION_RATE] = _ratio_text(sums[PAID_BUYERS], visitors)
        row["UV价值"] = _ratio_text(sums[PAID_AMOUNT], visitors)
        row["下单转化率"] = _ratio_text(sums["下单买家数"], visitors)
        row["支付金额占比"] = _ratio_text(sums[PAID_AMOUNT], day_totals.get(day, Decimal("0")))
        result.append(row)
    return result


def _unique_rows(
    rows: list[dict[str, str | None]],
    key_columns: tuple[str, ...],
) -> list[dict[str, str | None]]:
    unique: dict[tuple[str, ...], dict[str, str | None]] = {}
    for row in rows:
        key = tuple(row[column] or "" for column in key_columns[1:])
        current = unique.get(key)
        if current is not None and current != row:
            raise ValueError(f"Legacy source contains conflicting duplicate rows for {key!r}.")
        unique[key] = row
    return list(unique.values())


def _value_for_column(column: str, value: object) -> str | None:
    if column in {
        PRODUCT_RANKING_ITEM_ID,
        PRODUCT_RANKING_ITEM_NAME,
        PRODUCT_RANKING_ITEM_STATUS,
        PROMOTION_SCENE_NAME,
        PROMOTION_CAMPAIGN_ID,
        PROMOTION_CAMPAIGN_NAME,
        LIVE_TALENT_ID,
        LIVE_TALENT_NAME,
        TRAFFIC_SOURCE_LEVEL_1,
        TRAFFIC_SOURCE_LEVEL_2,
        TRAFFIC_SOURCE_LEVEL_3,
    }:
        return _text_value(value)
    return _numeric_text(value)


def _text_value(value: object) -> str | None:
    if value is None:
        return None
    return str(value).strip()


def _decimal_or_zero(value: str | None) -> Decimal:
    return Decimal(value) if value is not None else Decimal("0")


def _decimal_text(value: Decimal) -> str:
    return str(value)


def _ratio_text(numerator: Decimal, denominator: Decimal) -> str:
    if denominator == 0:
        return "0"
    return str(numerator / denominator)


def _mysql_q(name: str) -> str:
    return f"`{name.replace('`', '``')}`"


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"Legacy dataset import failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
