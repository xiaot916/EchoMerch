from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from app.core.local_database import (
    AVERAGE_STAY_TIME,
    BUSINESS_DAY,
    BRAND_ZONE_COLUMNS,
    BYBT_COLUMNS,
    BYBT_ITEM_COLUMNS,
    BYBT_ITEM_TABLE,
    CPS_COLUMNS,
    CONTENT_OVERVIEW_COLUMNS,
    CONTENT_OVERVIEW_FIELDS,
    CUSTOMER_SERVICE_ACCOUNT_COLUMNS,
    CUSTOMER_SERVICE_OVERVIEW_COLUMNS,
    CUSTOMER_SERVICE_OVERVIEW_FIELDS,
    ADD_CART_BUYERS,
    ARTIFACT_ID,
    CONTENT_SHA256,
    CONVERSION_RATE,
    DAILY_OVERVIEW_FIELDS,
    CUSTOMER_OVERVIEW_FIELDS,
    ENDPOINT_KEY,
    FETCHED_AT,
    FILE_SIZE,
    FLOW_OVERVIEW_COLUMNS,
    HTTP_STATUS,
    ACTIVITY_END_TIME,
    ACTIVITY_ID,
    ACTIVITY_LEVEL,
    ACTIVITY_NAME,
    ACTIVITY_STAGE,
    ACTIVITY_STATUS,
    ACTIVITY_START_TIME,
    ACTIVITY_TAG,
    ACTIVITY_TYPE,
    MEMBER_ANALYSIS_OVERVIEW_FIELDS,
    SHOP_PARTICIPATION_STATUS,
    SHOPPING_GOLD_COLUMNS,
    LIVE_OVERVIEW_COLUMNS,
    LIVE_STORE_PERFORMANCE_COLUMNS,
    LIVE_TALENT_COLUMNS,
    LIVE_TALENT_ID,
    LIVE_TALENT_NAME,
    LIVE_TALENT_TABLE,
    PLATFORM_CODE,
    PLATFORM_ID,
    PLATFORM_NAME,
    PARSER_VERSION,
    PRODUCT_RANKING_COLUMNS,
    PRODUCT_RANKING_ITEM_ID,
    PRODUCT_RANKING_TABLE,
    UTRY_REPURCHASE_COLUMNS,
    UTRY_REPURCHASE_TABLE,
    UTRY_SAMPLE_COLUMNS,
    UTRY_SAMPLE_TABLE,
    PROMOTION_CAMPAIGN_COLUMNS,
    PROMOTION_CAMPAIGN_TABLE,
    PROMOTION_ADGROUP_COLUMNS,
    PROMOTION_ADGROUP_TABLE,
    PROMOTION_CROWD_COLUMNS,
    PROMOTION_CROWD_TABLE,
    PROMOTION_BIDWORD_COLUMNS,
    PROMOTION_BIDWORD_TABLE,
    PROMOTION_CONTENT_COLUMNS,
    PROMOTION_CONTENT_TABLE,
    PROMOTION_ITEM_COLUMNS,
    PROMOTION_ITEM_TABLE,
    STATUS,
    CREATED_AT,
    FIRST_SEEN_AT,
    FLOW_AVERAGE_PAGE_VIEWS,
    FLOW_BOUNCE_RATE,
    FLOW_FOLLOW_STORE_BUYERS,
    FLOW_IMAGE_TEXT_VISITORS,
    FLOW_LIVE_ROOM_VISITORS,
    FLOW_NEW_VISITORS,
    FLOW_OLD_VISITORS,
    FLOW_PRODUCT_VISITORS,
    FLOW_SHOP_PAGE_VISITORS,
    FLOW_SHORT_VIDEO_VISITORS,
    MEMBER_CHANNEL_NAME,
    MEMBER_NEW_COUNT,
    MEMBER_NEW_PAID_AMOUNT,
    MEMBER_NEW_PAID_COUNT,
    MEMBER_NEW_UNIT_PRICE,
    MEMBER_RECRUIT_CONVERSION_RATE,
    NEW_VISITORS,
    NEW_CUSTOMER_DISCOUNT_PAID_AMOUNT,
    NEW_CUSTOMER_DISCOUNT_PAID_AMOUNT_RATIO,
    NEW_CUSTOMER_DISCOUNT_PAID_BUYERS,
    NEW_CUSTOMER_DISCOUNT_PAID_BUYER_RATIO,
    NEW_CUSTOMER_DISCOUNT_PAY_RATE,
    NEW_CUSTOMER_DISCOUNT_PRODUCT_NEW_VISITORS,
    NEW_CUSTOMER_DISCOUNT_SHOP_PAID_AMOUNT,
    NEW_CUSTOMER_DISCOUNT_SHOP_PAID_BUYERS,
    NEW_CUSTOMER_DISCOUNT_SHOP_PAY_RATE,
    NEW_CUSTOMER_DISCOUNT_SHOP_VISITORS,
    ORDER_AMOUNT,
    ORDER_BUYERS,
    ORDER_CONVERSION_RATE,
    PAGE_VIEWS,
    PAID_AMOUNT,
    PAID_AMOUNT_SHARE,
    PAID_BUYERS,
    PRODUCT_FAVORITE_BUYERS,
    RESPONSE_CODE,
    SIGNUP_END_TIME,
    SIGNUP_START_TIME,
    SOURCE_LEVEL,
    SOURCE_FILE,
    STORE_ID,
    STORE_NAME,
    STORE_SUBJECT_ID,
    TAOBAO_FLASH_SALE_COLUMNS,
    TAOBAO_FLASH_SALE_FIELDS,
    TAOBAO_FLASH_SALE_ITEM_COLUMNS,
    TAOBAO_FLASH_SALE_ITEM_TABLE,
    TAOBAO_RISK_PRICE_ITEM_COLUMNS,
    TAOBAO_RISK_PRICE_ITEM_TABLE,
    TAOBAO_CURRENT_PRICE_ITEM_COLUMNS,
    TAOBAO_CURRENT_PRICE_ITEM_TABLE,
    TAOBAO_ACTIVITY_ITEM_SNAPSHOT_COLUMNS,
    TAOBAO_ACTIVITY_ITEM_SNAPSHOT_TABLE,
    TAOJINBI_COLUMNS,
    TAOJINBI_FIELDS,
    TRAFFIC_SOURCE_LEVEL_1,
    TRAFFIC_SOURCE_LEVEL_2,
    TRAFFIC_SOURCE_LEVEL_3,
    UPDATED_AT,
    UV_VALUE,
    VISITORS,
    LocalDatabase,
    q,
)
from app.warehouse.schemas import (
    StoreActivityCalendarEvent,
    MetricDefinition,
    PlatformRecord,
    ProductRankingIngestResult,
    StoreDailyFlowOverview,
    StoreDailyFlowOverviewMetric,
    StoreDailyOverview,
    StoreRecord,
    WarehouseIngestResult,
    WarehouseMetricIngestResult,
)
from app.warehouse.sycm_flow_overview import (
    METRIC_PREFIX as FLOW_METRIC_PREFIX,
    load_and_parse as load_and_parse_flow_overview,
)
from app.warehouse.sycm_customer_overview import (
    METRIC_PREFIX as CUSTOMER_METRIC_PREFIX,
    load_and_parse as load_and_parse_customer_overview,
)
from app.warehouse.sycm_member_analysis import (
    SECTION_PREFIXES as MEMBER_SECTION_PREFIXES,
    load_and_parse_channel as load_and_parse_member_channel,
    load_and_parse_metrics as load_and_parse_member_metrics,
)
from app.warehouse.sycm_activity_calendar import (
    load_and_parse as load_and_parse_activity_calendar,
)
from app.warehouse.sycm_new_customer_discount import (
    load_and_parse as load_and_parse_new_customer_discount,
)
from app.warehouse.sycm_shopping_gold import (
    load_and_parse as load_and_parse_shopping_gold,
)
from app.warehouse.sycm_bybt import load_and_parse as load_and_parse_bybt
from app.warehouse.sycm_bybt_items import load_and_parse as load_and_parse_bybt_items
from app.warehouse.sycm_live import (
    load_and_parse_overview as load_and_parse_live_overview,
    load_and_parse_store_performance as load_and_parse_live_store_performance,
    load_and_parse_talent as load_and_parse_live_talent,
)
from app.warehouse.brandsearch_report import (
    load_and_parse as load_and_parse_brandsearch_report,
)
from app.warehouse.alimama_campaign import (
    load_and_parse as load_and_parse_alimama_campaign,
)
from app.warehouse.alimama_adgroup import (
    load_and_parse as load_and_parse_alimama_adgroup,
)
from app.warehouse.alimama_bidword import (
    load_and_parse as load_and_parse_alimama_bidword,
)
from app.warehouse.alimama_crowd import (
    load_and_parse as load_and_parse_alimama_crowd,
)
from app.warehouse.alimama_promotion_detail import (
    load_and_parse_content as load_and_parse_alimama_promotion_content,
    load_and_parse_item as load_and_parse_alimama_promotion_item,
)
from app.warehouse.utry_overviews import (
    load_and_parse_repurchase as load_and_parse_utry_repurchase,
    load_and_parse_sample as load_and_parse_utry_sample,
)
from app.warehouse.cps_overview import (
    load_and_parse as load_and_parse_cps_overview,
)
from app.warehouse.taobao_flash_sale import (
    load_and_parse as load_and_parse_taobao_flash_sale,
)
from app.warehouse.taobao_flash_sale_items import load_and_parse as load_and_parse_taobao_flash_sale_items
from app.warehouse.taobao_risk_price_items import load_and_parse as load_and_parse_taobao_risk_price_items
from app.warehouse.taobao_current_price_items import load_and_parse as load_and_parse_taobao_current_price_items
from app.warehouse.taobao_activity_item_snapshots import load_and_parse as load_and_parse_taobao_activity_item_snapshots
from app.warehouse.mtop_content_overview import (
    load_and_parse as load_and_parse_content_overview,
)
from app.warehouse.mtop_taojinbi import (
    load_and_parse as load_and_parse_taojinbi,
)
from app.warehouse.mtop_customer_service_overview import (
    load_and_parse as load_and_parse_customer_service_overview,
)
from app.warehouse.sycm_customer_service_accounts import (
    load_and_parse as load_and_parse_customer_service_accounts,
)
from app.warehouse.sycm_overview import load_and_parse
from app.warehouse.sycm_traffic_source import load_and_parse as load_and_parse_traffic_source
from app.warehouse.sycm_item_ranking import load_and_parse as load_and_parse_item_ranking


class WarehouseDataNotAvailable(RuntimeError):
    pass


FLOW_OVERVIEW_FIELDS = (
    (VISITORS, "flow.uv", "人", "已确认"),
    (FLOW_PRODUCT_VISITORS, "flow.itmUv", "人", "已确认"),
    (PAID_BUYERS, "flow.payByrCnt", "人", "已确认"),
    (PAGE_VIEWS, "flow.pv", "次", "已确认"),
    (FLOW_BOUNCE_RATE, None, "%", "待确认"),
    (FLOW_AVERAGE_PAGE_VIEWS, "flow.avgPv", "次/人", "已确认"),
    (AVERAGE_STAY_TIME, "flow.stayTime / stayTime", "秒", "待确认"),
    (FLOW_OLD_VISITORS, "flow.oldUv", "人", "已确认"),
    (FLOW_NEW_VISITORS, "flow.newUv", "人", "已确认"),
    (FLOW_FOLLOW_STORE_BUYERS, "flow.shopCltByrCnt", "人", "已确认"),
    (FLOW_LIVE_ROOM_VISITORS, "flow.liveRoomUv", "人", "已确认"),
    (FLOW_SHORT_VIDEO_VISITORS, "flow.shortVideoUv", "人", "已确认"),
    (FLOW_IMAGE_TEXT_VISITORS, "flow.imageUv", "人", "已确认"),
    (FLOW_SHOP_PAGE_VISITORS, "flow.shopVisitUv", "人", "已确认"),
)

FLOW_STORAGE_FIELDS = (
    (VISITORS, ("uv",)),
    (FLOW_PRODUCT_VISITORS, ("itmUv",)),
    (PAID_BUYERS, ("payByrCnt",)),
    (PAGE_VIEWS, ("pv",)),
    (
        FLOW_BOUNCE_RATE,
        (
            "bounceRate",
            "bounceUvRate",
            "bounceRate1d",
            "bounceUvRate1d",
            "avgBounceUvRate",
            "bounce_uv_rate_1d_002",
        ),
    ),
    (FLOW_AVERAGE_PAGE_VIEWS, ("avgPv",)),
    (AVERAGE_STAY_TIME, ("stayTime", "stayTimeLen", "stay_time_len_1d_001")),
    (FLOW_OLD_VISITORS, ("oldUv",)),
    (FLOW_NEW_VISITORS, ("newUv",)),
    (FLOW_FOLLOW_STORE_BUYERS, ("shopCltByrCnt",)),
    (FLOW_LIVE_ROOM_VISITORS, ("liveRoomUv",)),
    (FLOW_SHORT_VIDEO_VISITORS, ("shortVideoUv",)),
    (FLOW_IMAGE_TEXT_VISITORS, ("imageUv",)),
    (FLOW_SHOP_PAGE_VISITORS, ("shopVisitUv",)),
)


DAILY_OVERVIEW_RESPONSE_FIELDS = {
    "payAmt": "paid_amount",
    "netPaymentAmount": "net_paid_amount",
    "uv": "visitors",
    "payByrCnt": "paid_buyers",
    "payRate": "conversion_rate",
    "realPayrealRfdRate": "sign_refund_rate",
    "rfdSucAmt": "refund_finished_amount",
    "p4pExpendAmt": "keyword_promotion_spend",
    "cubeAmt": "precision_audience_promotion_spend",
    "feedCharge": "smart_scene_spend",
    "admCostFamtQzt": "all_site_promotion_spend",
    "tkExpendAmt": "taoke_commission",
    "subPayOrdAmt": "total_paid_amount",
    "payShopRfdAmt": "refund_paid_time_amount",
    "payAmtRfdRate": "amount_refund_rate",
    "cartByrCnt": "add_cart_buyers",
    "cltItmCnt": "product_favorite_buyers",
    "pv": "page_views",
    "stayTime": "average_stay_time",
    "cartItemCnt": "add_cart_items",
    "payOrdCnt": "paid_sub_order_count",
    "subPayOrdSubCnt": "total_paid_sub_order_count",
    "ordRfdRate": "order_refund_rate",
    "payItmCnt": "paid_items",
    "payPct": "customer_unit_price",
    "olderPayAmt": "older_paid_amount",
    "payOldByrCnt": "older_paid_buyers",
    "hasPurchaseUbyCntRate": "older_repurchase_rate",
    "rfdFinshDur": "refund_process_days",
    "wwReplyManualAvgTimeLen": "wangwang_manual_response_seconds",
    "consultRate": "consultation_rate",
    "disputeDutyRatio": "platform_duty_rate",
    "gotInTime24hRate": "pickup_24h_rate",
    "avgSignTimeHh": "logistics_arrival_hours",
}


class WarehouseStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self._database = LocalDatabase(database_path)

    def ingest_sycm_overview(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        http_status: int = 200,
    ) -> WarehouseIngestResult:
        parsed = load_and_parse(source_path, business_day)
        artifact_id = f"{parsed.endpoint_key}:{parsed.source_sha256[:20]}"
        now = self._now()

        with self._connect(initialize=True, artifact_table=True) as conn:
            self._seed_metric_definitions(conn, now)
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn,
                platform_id,
                parsed.platform_store_id,
                store_name,
                now,
            )
            conn.execute(
                """
                insert into raw_response_artifacts (
                    "证据ID", "平台ID", "店铺ID", "接口标识", "业务日期",
                    "抓取时间", "HTTP状态码", "响应码", "来源文件", "内容SHA256",
                    "文件大小", "解析器版本", "创建时间"
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict("内容SHA256") do update set
                    "店铺ID" = excluded."店铺ID",
                    "业务日期" = excluded."业务日期",
                    "抓取时间" = excluded."抓取时间",
                    "HTTP状态码" = excluded."HTTP状态码",
                    "响应码" = excluded."响应码",
                    "来源文件" = excluded."来源文件",
                    "文件大小" = excluded."文件大小",
                    "解析器版本" = excluded."解析器版本"
                """,
                (
                    artifact_id,
                    platform_id,
                    store_id,
                    parsed.endpoint_key,
                    business_day.isoformat(),
                    now,
                    http_status,
                    parsed.response_code,
                    str(source_path),
                    parsed.source_sha256,
                    parsed.source_bytes,
                    parsed.parser_version,
                    now,
                ),
            )
            artifact_id = self._resolve_artifact_id(conn, parsed.source_sha256, artifact_id)
            overview_columns = [STORE_ID, BUSINESS_DAY] + [
                column for column, _ in DAILY_OVERVIEW_FIELDS
            ]
            overview_values = self._daily_overview_metric_values(parsed.metrics)
            update_assignments = ", ".join(
                f"{q(column)} = excluded.{q(column)}"
                for column in overview_columns[2:]
            )
            conn.execute(
                f"""
                insert into store_daily_overviews (
                    {", ".join(q(column) for column in overview_columns)}
                ) values ({", ".join("?" for _ in overview_columns)})
                on conflict({q(STORE_ID)}, {q(BUSINESS_DAY)}) do update set
                    {update_assignments}
                """,
                (
                    store_id,
                    business_day.isoformat(),
                    *[
                        overview_values.get(column) or "0"
                        for column, _ in DAILY_OVERVIEW_FIELDS
                    ],
                ),
            )
            conn.commit()

        overview = self.get_daily_overview(store_id=store_id, business_day=business_day)
        if overview is None:
            raise WarehouseDataNotAvailable("The ingested daily overview could not be read back.")
        return WarehouseIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=len(parsed.metrics),
            overview=overview,
            warnings=[
                "business_day uses the requested date; trend responses are sliced by self.statDate",
                "platform_store_id is sourced from self.userId.value in this endpoint",
                "all_site_promotion_spend is mapped from self.admCostFamtQzt",
            ],
        )

    def ingest_sycm_flow_overview(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_flow_overview(source_path, business_day)
        artifact_id = f"{parsed.endpoint_key}:{parsed.source_sha256[:20]}"
        now = self._now()

        with self._connect(initialize=True, artifact_table=True) as conn:
            self._seed_metric_definitions(conn, now)
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn,
                platform_id,
                platform_store_id,
                store_name,
                now,
            )
            conn.execute(
                """
                insert into raw_response_artifacts (
                    "证据ID", "平台ID", "店铺ID", "接口标识", "业务日期",
                    "抓取时间", "HTTP状态码", "响应码", "来源文件", "内容SHA256",
                    "文件大小", "解析器版本", "创建时间"
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict("内容SHA256") do update set
                    "店铺ID" = excluded."店铺ID",
                    "业务日期" = excluded."业务日期",
                    "抓取时间" = excluded."抓取时间",
                    "HTTP状态码" = excluded."HTTP状态码",
                    "响应码" = excluded."响应码",
                    "来源文件" = excluded."来源文件",
                    "文件大小" = excluded."文件大小",
                    "解析器版本" = excluded."解析器版本"
                """,
                (
                    artifact_id,
                    platform_id,
                    store_id,
                    parsed.endpoint_key,
                    business_day.isoformat(),
                    now,
                    http_status,
                    parsed.response_code,
                    str(source_path),
                    parsed.source_sha256,
                    parsed.source_bytes,
                    parsed.parser_version,
                    now,
                ),
            )
            flow_metrics = {
                metric.code.removeprefix(FLOW_METRIC_PREFIX): metric.numeric_value
                for metric in parsed.metrics
            }
            self._upsert_daily_fact_row(
                conn,
                table="store_daily_flow_overviews",
                columns=FLOW_OVERVIEW_COLUMNS,
                store_id=store_id,
                business_day=business_day,
                values={
                    column: self._first_metric_value(flow_metrics, codes)
                    for column, codes in FLOW_STORAGE_FIELDS
                },
            )
            conn.commit()

        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=len(parsed.metrics),
            warnings=[
                "flow overview metrics are stored in store_daily_flow_overviews",
                "platform_store_id is supplied by the local store config for this endpoint",
                "the same store and business day is replaced atomically",
            ],
        )

    def ingest_sycm_customer_overview(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_customer_overview(source_path, business_day)
        artifact_id = f"{parsed.endpoint_key}:{parsed.source_sha256[:20]}"
        now = self._now()

        with self._connect(initialize=True, artifact_table=True) as conn:
            self._seed_metric_definitions(conn, now)
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn,
                platform_id,
                parsed.platform_store_id,
                store_name,
                now,
            )
            conn.execute(
                f"""
                insert into raw_response_artifacts (
                    {q(ARTIFACT_ID)}, {q(PLATFORM_ID)}, {q(STORE_ID)}, {q(ENDPOINT_KEY)},
                    {q(BUSINESS_DAY)}, {q(FETCHED_AT)}, {q(HTTP_STATUS)}, {q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)}, {q(CONTENT_SHA256)}, {q(FILE_SIZE)},
                    {q(PARSER_VERSION)}, {q(CREATED_AT)}
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict({q(CONTENT_SHA256)}) do update set
                    {q(STORE_ID)} = excluded.{q(STORE_ID)},
                    {q(BUSINESS_DAY)} = excluded.{q(BUSINESS_DAY)},
                    {q(FETCHED_AT)} = excluded.{q(FETCHED_AT)},
                    {q(HTTP_STATUS)} = excluded.{q(HTTP_STATUS)},
                    {q(RESPONSE_CODE)} = excluded.{q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)} = excluded.{q(SOURCE_FILE)},
                    {q(FILE_SIZE)} = excluded.{q(FILE_SIZE)},
                    {q(PARSER_VERSION)} = excluded.{q(PARSER_VERSION)}
                """,
                (
                    artifact_id,
                    platform_id,
                    store_id,
                    parsed.endpoint_key,
                    business_day.isoformat(),
                    now,
                    http_status,
                    parsed.response_code,
                    str(source_path),
                    parsed.source_sha256,
                    parsed.source_bytes,
                    parsed.parser_version,
                    now,
                ),
            )
            artifact_id = self._resolve_artifact_id(conn, parsed.source_sha256, artifact_id)
            customer_metrics = {
                metric.code.removeprefix(CUSTOMER_METRIC_PREFIX): metric.numeric_value
                for metric in parsed.metrics
            }
            self._upsert_daily_fact_row(
                conn,
                table="store_daily_customer_overviews",
                columns=(STORE_ID, BUSINESS_DAY, *[column for column, _ in CUSTOMER_OVERVIEW_FIELDS]),
                store_id=store_id,
                business_day=business_day,
                values={
                    column: customer_metrics.get(code)
                    for column, code in CUSTOMER_OVERVIEW_FIELDS
                },
            )
            conn.commit()

        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=len(parsed.metrics),
            warnings=[
                "customer overview metrics are stored in store_daily_customer_overviews",
                "sellerId is used as the platform_store_id for this endpoint",
                "AvgGood and rival metrics are ignored; only self metrics are stored",
            ],
        )

    def ingest_sycm_traffic_source(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_traffic_source(source_path, business_day)
        artifact_id = f"{parsed.endpoint_key}:{parsed.source_sha256[:20]}"
        now = self._now()

        with self._connect(initialize=True, artifact_table=True) as conn:
            self._seed_metric_definitions(conn, now)
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn,
                platform_id,
                platform_store_id,
                store_name,
                now,
            )
            conn.execute(
                """
                insert into raw_response_artifacts (
                    "证据ID", "平台ID", "店铺ID", "接口标识", "业务日期",
                    "抓取时间", "HTTP状态码", "响应码", "来源文件", "内容SHA256",
                    "文件大小", "解析器版本", "创建时间"
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict("内容SHA256") do update set
                    "店铺ID" = excluded."店铺ID",
                    "业务日期" = excluded."业务日期",
                    "抓取时间" = excluded."抓取时间",
                    "HTTP状态码" = excluded."HTTP状态码",
                    "响应码" = excluded."响应码",
                    "来源文件" = excluded."来源文件",
                    "文件大小" = excluded."文件大小",
                    "解析器版本" = excluded."解析器版本"
                """,
                (
                    artifact_id,
                    platform_id,
                    store_id,
                    parsed.endpoint_key,
                    business_day.isoformat(),
                    now,
                    http_status,
                    parsed.response_code,
                    str(source_path),
                    parsed.source_sha256,
                    parsed.source_bytes,
                    parsed.parser_version,
                    now,
                ),
            )
            artifact_id = self._resolve_artifact_id(conn, parsed.source_sha256, artifact_id)
            conn.execute(
                f"""
                delete from store_daily_traffic_sources
                where {q(STORE_ID)} = ? and {q(BUSINESS_DAY)} = ?
                """,
                (store_id, business_day.isoformat()),
            )
            conn.executemany(
                f"""
                insert into store_daily_traffic_sources (
                    {q(STORE_ID)}, {q(BUSINESS_DAY)},
                    {q(TRAFFIC_SOURCE_LEVEL_1)}, {q(TRAFFIC_SOURCE_LEVEL_2)},
                    {q(TRAFFIC_SOURCE_LEVEL_3)}, {q(SOURCE_LEVEL)},
                    {q(VISITORS)}, {q(NEW_VISITORS)}, {q(ADD_CART_BUYERS)},
                    {q(PRODUCT_FAVORITE_BUYERS)}, {q(PAID_BUYERS)}, {q(CONVERSION_RATE)},
                    {q(PAID_AMOUNT)}, {q(PAID_AMOUNT_SHARE)}, {q(UV_VALUE)},
                    {q(ORDER_BUYERS)}, {q(ORDER_AMOUNT)}, {q(ORDER_CONVERSION_RATE)}
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._traffic_source_insert_rows(
                    parsed.rows,
                    store_id=store_id,
                    business_day=business_day.isoformat(),
                ),
            )
            conn.commit()

        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=len(parsed.rows),
            warnings=[
                "traffic source rows are stored in store_daily_traffic_sources",
                "platform_store_id is supplied by the local store config for this endpoint",
                "existing traffic source rows for the same store/day are replaced atomically",
            ],
        )

    def ingest_sycm_item_ranking(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
    ) -> ProductRankingIngestResult:
        parsed = load_and_parse_item_ranking(source_path, business_day)
        now = self._now()
        insert_columns = ", ".join(q(column) for column in PRODUCT_RANKING_COLUMNS)
        placeholders = ", ".join("?" for _ in PRODUCT_RANKING_COLUMNS)

        with self._connect(initialize=True) as conn:
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn,
                platform_id,
                platform_store_id,
                store_name,
                now,
            )
            conn.execute(
                f"""
                delete from {PRODUCT_RANKING_TABLE}
                where {q(STORE_ID)} = ? and {q(BUSINESS_DAY)} = ?
                """,
                (store_id, business_day.isoformat()),
            )
            conn.executemany(
                f"""
                insert into {PRODUCT_RANKING_TABLE} (
                    {insert_columns}
                ) values ({placeholders})
                """,
                [
                    (
                        store_id,
                        business_day.isoformat(),
                        *[row.get(column) for column in PRODUCT_RANKING_COLUMNS[2:]],
                    )
                    for row in parsed.rows
                ],
            )
            conn.commit()

        return ProductRankingIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            row_count=len(parsed.rows),
            warnings=[
                "item ranking rows are stored in store_daily_product_rankings",
                "the daily product snapshot is replaced atomically for the same store/day",
                "pagination excludes the first and all following rows with payment item count equal to zero",
            ],
        )

    def ingest_utry_sample_overview(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_utry_sample(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        return self._ingest_utry_overview(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table=UTRY_SAMPLE_TABLE,
            columns=UTRY_SAMPLE_COLUMNS,
            dimensions=lambda row: (
                row.product_id,
                row.product_name,
                row.leaf_category_name,
                row.industry_group_name,
                row.first_category_name,
                row.second_category_name,
            ),
        )

    def ingest_utry_repurchase_overview(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_utry_repurchase(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        return self._ingest_utry_overview(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table=UTRY_REPURCHASE_TABLE,
            columns=UTRY_REPURCHASE_COLUMNS,
            dimensions=lambda row: (
                row.product_id,
                row.product_name,
                row.ju_id,
                row.leaf_category,
                row.industry_group,
                row.first_category,
                row.second_category,
                row.bind_regular_product,
                row.configured_repurchase_coupon,
                row.configured_repurchase_gift,
            ),
        )

    def _ingest_utry_overview(
        self,
        *,
        parsed,
        source_path: Path,
        business_day: date,
        store_name: str,
        http_status: int,
        table: str,
        columns: tuple[str, ...],
        dimensions,
    ) -> WarehouseMetricIngestResult:
        artifact_id = f"{parsed.endpoint_key}:{parsed.source_sha256[:20]}"
        now = self._now()
        with self._connect(initialize=True, artifact_table=True) as conn:
            self._seed_metric_definitions(conn, now)
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn, platform_id, parsed.platform_store_id, store_name, now
            )
            self._insert_raw_artifact(
                conn=conn,
                artifact_id=artifact_id,
                platform_id=platform_id,
                store_id=store_id,
                parsed=parsed,
                source_path=source_path,
                business_day=business_day,
                http_status=http_status,
                now=now,
            )
            artifact_id = self._resolve_artifact_id(conn, parsed.source_sha256, artifact_id)
            conn.execute(
                f"delete from {table} where {q(STORE_ID)}=? and {q(BUSINESS_DAY)}=?",
                (store_id, business_day.isoformat()),
            )
            conn.executemany(
                f"insert into {table} ({', '.join(q(column) for column in columns)}) "
                f"values ({', '.join('?' for _ in columns)})",
                [
                    (
                        store_id,
                        business_day.isoformat(),
                        *dimensions(row),
                        *[self._optional_decimal(value) for value in row.metrics],
                    )
                    for row in parsed.rows
                ],
            )
            conn.commit()
        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=parsed.metric_count,
            warnings=[
                f"U先 rows replace the same store and business day in {table}",
                "U先 product facts are kept separate from store product rankings",
            ],
        )

    def ingest_sycm_member_metrics(
        self,
        source_path: Path,
        business_day: date,
        section: str,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_member_metrics(
            source_path,
            business_day,
            section=section,
            platform_store_id=platform_store_id,
        )
        artifact_id = f"{parsed.endpoint_key}:{parsed.source_sha256[:20]}"
        now = self._now()
        metric_prefix = MEMBER_SECTION_PREFIXES[section]

        with self._connect(initialize=True, artifact_table=True) as conn:
            self._seed_metric_definitions(conn, now)
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn,
                platform_id,
                parsed.platform_store_id,
                store_name,
                now,
            )
            conn.execute(
                f"""
                insert into raw_response_artifacts (
                    {q(ARTIFACT_ID)}, {q(PLATFORM_ID)}, {q(STORE_ID)}, {q(ENDPOINT_KEY)},
                    {q(BUSINESS_DAY)}, {q(FETCHED_AT)}, {q(HTTP_STATUS)}, {q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)}, {q(CONTENT_SHA256)}, {q(FILE_SIZE)},
                    {q(PARSER_VERSION)}, {q(CREATED_AT)}
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict({q(CONTENT_SHA256)}) do update set
                    {q(STORE_ID)} = excluded.{q(STORE_ID)},
                    {q(BUSINESS_DAY)} = excluded.{q(BUSINESS_DAY)},
                    {q(FETCHED_AT)} = excluded.{q(FETCHED_AT)},
                    {q(HTTP_STATUS)} = excluded.{q(HTTP_STATUS)},
                    {q(RESPONSE_CODE)} = excluded.{q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)} = excluded.{q(SOURCE_FILE)},
                    {q(FILE_SIZE)} = excluded.{q(FILE_SIZE)},
                    {q(PARSER_VERSION)} = excluded.{q(PARSER_VERSION)}
                """,
                (
                    artifact_id,
                    platform_id,
                    store_id,
                    parsed.endpoint_key,
                    business_day.isoformat(),
                    now,
                    http_status,
                    parsed.response_code,
                    str(source_path),
                    parsed.source_sha256,
                    parsed.source_bytes,
                    parsed.parser_version,
                    now,
                ),
            )
            artifact_id = self._resolve_artifact_id(conn, parsed.source_sha256, artifact_id)
            member_metrics = {
                metric.code: metric.numeric_value
                for metric in parsed.metrics
            }
            section_fields = [
                (column, code)
                for column, code in MEMBER_ANALYSIS_OVERVIEW_FIELDS
                if code.startswith(metric_prefix)
            ]
            self._upsert_daily_fact_row(
                conn,
                table="store_daily_member_analysis_overviews",
                columns=(STORE_ID, BUSINESS_DAY, *[column for column, _ in section_fields]),
                store_id=store_id,
                business_day=business_day,
                values={
                    column: member_metrics.get(code)
                    for column, code in section_fields
                },
            )
            conn.commit()

        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=len(parsed.metrics),
            warnings=[
                f"member {section} metrics are stored in store_daily_member_analysis_overviews",
                "the matching member section is replaced atomically",
            ],
        )

    def ingest_sycm_member_channel(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_member_channel(
            source_path,
            business_day,
            platform_store_id=platform_store_id,
        )
        artifact_id = f"{parsed.endpoint_key}:{parsed.source_sha256[:20]}"
        now = self._now()

        with self._connect(initialize=True, artifact_table=True) as conn:
            self._seed_metric_definitions(conn, now)
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn,
                platform_id,
                parsed.platform_store_id,
                store_name,
                now,
            )
            conn.execute(
                f"""
                insert into raw_response_artifacts (
                    {q(ARTIFACT_ID)}, {q(PLATFORM_ID)}, {q(STORE_ID)}, {q(ENDPOINT_KEY)},
                    {q(BUSINESS_DAY)}, {q(FETCHED_AT)}, {q(HTTP_STATUS)}, {q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)}, {q(CONTENT_SHA256)}, {q(FILE_SIZE)},
                    {q(PARSER_VERSION)}, {q(CREATED_AT)}
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict({q(CONTENT_SHA256)}) do update set
                    {q(STORE_ID)} = excluded.{q(STORE_ID)},
                    {q(BUSINESS_DAY)} = excluded.{q(BUSINESS_DAY)},
                    {q(FETCHED_AT)} = excluded.{q(FETCHED_AT)},
                    {q(HTTP_STATUS)} = excluded.{q(HTTP_STATUS)},
                    {q(RESPONSE_CODE)} = excluded.{q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)} = excluded.{q(SOURCE_FILE)},
                    {q(FILE_SIZE)} = excluded.{q(FILE_SIZE)},
                    {q(PARSER_VERSION)} = excluded.{q(PARSER_VERSION)}
                """,
                (
                    artifact_id,
                    platform_id,
                    store_id,
                    parsed.endpoint_key,
                    business_day.isoformat(),
                    now,
                    http_status,
                    parsed.response_code,
                    str(source_path),
                    parsed.source_sha256,
                    parsed.source_bytes,
                    parsed.parser_version,
                    now,
                ),
            )
            artifact_id = self._resolve_artifact_id(conn, parsed.source_sha256, artifact_id)
            conn.execute(
                f"""
                delete from store_daily_member_channels
                where {q(STORE_ID)} = ? and {q(BUSINESS_DAY)} = ?
                """,
                (store_id, business_day.isoformat()),
            )
            conn.executemany(
                f"""
                insert into store_daily_member_channels (
                    {q(STORE_ID)}, {q(BUSINESS_DAY)}, {q(MEMBER_CHANNEL_NAME)},
                    {q(MEMBER_NEW_COUNT)}, {q(MEMBER_NEW_PAID_COUNT)},
                    {q(MEMBER_RECRUIT_CONVERSION_RATE)}, {q(MEMBER_NEW_PAID_AMOUNT)},
                    {q(MEMBER_NEW_UNIT_PRICE)}
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict({q(STORE_ID)}, {q(BUSINESS_DAY)}, {q(MEMBER_CHANNEL_NAME)}) do update set
                    {q(MEMBER_NEW_COUNT)} = excluded.{q(MEMBER_NEW_COUNT)},
                    {q(MEMBER_NEW_PAID_COUNT)} = excluded.{q(MEMBER_NEW_PAID_COUNT)},
                    {q(MEMBER_RECRUIT_CONVERSION_RATE)} = excluded.{q(MEMBER_RECRUIT_CONVERSION_RATE)},
                    {q(MEMBER_NEW_PAID_AMOUNT)} = excluded.{q(MEMBER_NEW_PAID_AMOUNT)},
                    {q(MEMBER_NEW_UNIT_PRICE)} = excluded.{q(MEMBER_NEW_UNIT_PRICE)}
                """,
                [
                    (
                        store_id,
                        business_day.isoformat(),
                        row.channel_name,
                        self._decimal(row.new_members),
                        self._decimal(row.paid_new_members),
                        self._decimal(row.recruit_conversion_rate),
                        self._decimal(row.new_member_paid_amount),
                        self._decimal(row.new_member_unit_price),
                    )
                    for row in parsed.rows
                ],
            )
            conn.commit()

        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=len(parsed.rows),
            warnings=[
                "member channel rows are stored in store_daily_member_channels",
                "existing member channel rows for the same store/day are replaced atomically",
            ],
        )

    def ingest_sycm_activity_calendar(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_activity_calendar(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        artifact_id = f"{parsed.endpoint_key}:{parsed.source_sha256[:20]}"
        now = self._now()

        with self._connect(initialize=True, artifact_table=True) as conn:
            self._seed_metric_definitions(conn, now)
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn,
                platform_id,
                parsed.platform_store_id,
                store_name,
                now,
            )
            conn.execute(
                f"""
                insert into raw_response_artifacts (
                    {q(ARTIFACT_ID)}, {q(PLATFORM_ID)}, {q(STORE_ID)}, {q(ENDPOINT_KEY)},
                    {q(BUSINESS_DAY)}, {q(FETCHED_AT)}, {q(HTTP_STATUS)}, {q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)}, {q(CONTENT_SHA256)}, {q(FILE_SIZE)},
                    {q(PARSER_VERSION)}, {q(CREATED_AT)}
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict({q(CONTENT_SHA256)}) do update set
                    {q(STORE_ID)} = excluded.{q(STORE_ID)},
                    {q(BUSINESS_DAY)} = excluded.{q(BUSINESS_DAY)},
                    {q(FETCHED_AT)} = excluded.{q(FETCHED_AT)},
                    {q(HTTP_STATUS)} = excluded.{q(HTTP_STATUS)},
                    {q(RESPONSE_CODE)} = excluded.{q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)} = excluded.{q(SOURCE_FILE)},
                    {q(FILE_SIZE)} = excluded.{q(FILE_SIZE)},
                    {q(PARSER_VERSION)} = excluded.{q(PARSER_VERSION)}
                """,
                (
                    artifact_id,
                    platform_id,
                    store_id,
                    parsed.endpoint_key,
                    parsed.query_date.isoformat(),
                    now,
                    http_status,
                    parsed.response_code,
                    str(source_path),
                    parsed.source_sha256,
                    parsed.source_bytes,
                    parsed.parser_version,
                    now,
                ),
            )
            artifact_id = self._resolve_artifact_id(conn, parsed.source_sha256, artifact_id)

            conn.execute(
                f"""
                delete from store_activity_calendar_events
                where {q(STORE_ID)} = ?
                """,
                (store_id,),
            )
            conn.executemany(
                f"""
                insert into store_activity_calendar_events (
                    {q(STORE_ID)}, {q(BUSINESS_DAY)}, {q(ACTIVITY_ID)},
                    {q(ACTIVITY_NAME)}, {q(ACTIVITY_TYPE)}, {q(ACTIVITY_STATUS)},
                    {q(ACTIVITY_START_TIME)}, {q(ACTIVITY_END_TIME)},
                    {q(SIGNUP_START_TIME)}, {q(SIGNUP_END_TIME)},
                    {q(ACTIVITY_TAG)}, {q(ACTIVITY_LEVEL)}, {q(ACTIVITY_STAGE)},
                    {q(SHOP_PARTICIPATION_STATUS)}
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict({q(STORE_ID)}, {q(BUSINESS_DAY)}, {q(ACTIVITY_ID)}) do update set
                    {q(ACTIVITY_NAME)} = excluded.{q(ACTIVITY_NAME)},
                    {q(ACTIVITY_TYPE)} = excluded.{q(ACTIVITY_TYPE)},
                    {q(ACTIVITY_STATUS)} = excluded.{q(ACTIVITY_STATUS)},
                    {q(ACTIVITY_START_TIME)} = excluded.{q(ACTIVITY_START_TIME)},
                    {q(ACTIVITY_END_TIME)} = excluded.{q(ACTIVITY_END_TIME)},
                    {q(SIGNUP_START_TIME)} = excluded.{q(SIGNUP_START_TIME)},
                    {q(SIGNUP_END_TIME)} = excluded.{q(SIGNUP_END_TIME)},
                    {q(ACTIVITY_TAG)} = excluded.{q(ACTIVITY_TAG)},
                    {q(ACTIVITY_LEVEL)} = excluded.{q(ACTIVITY_LEVEL)},
                    {q(ACTIVITY_STAGE)} = excluded.{q(ACTIVITY_STAGE)},
                    {q(SHOP_PARTICIPATION_STATUS)} = excluded.{q(SHOP_PARTICIPATION_STATUS)}
                """,
                [
                    (
                        store_id,
                        event.business_day.isoformat(),
                        event.activity_id,
                        event.activity_name,
                        event.activity_type,
                        event.activity_status,
                        event.activity_start_time,
                        event.activity_end_time,
                        event.signup_start_time,
                        event.signup_end_time,
                        event.activity_tag,
                        event.activity_level,
                        event.activity_stage,
                        event.shop_participation_status,
                    )
                    for event in parsed.events
                ],
            )
            conn.commit()

        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=len(parsed.events),
            warnings=[
                "activity calendar rows are stored in store_activity_calendar_events",
                "same-store activity calendar snapshot is replaced atomically before insert",
                "missing activityId values are replaced with a deterministic generated id",
            ],
        )

    def ingest_sycm_new_customer_discount(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_new_customer_discount(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        artifact_id = f"{parsed.endpoint_key}:{parsed.source_sha256[:20]}"
        now = self._now()

        with self._connect(initialize=True, artifact_table=True) as conn:
            self._seed_metric_definitions(conn, now)
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn,
                platform_id,
                parsed.platform_store_id,
                store_name,
                now,
            )
            conn.execute(
                f"""
                insert into raw_response_artifacts (
                    {q(ARTIFACT_ID)}, {q(PLATFORM_ID)}, {q(STORE_ID)}, {q(ENDPOINT_KEY)},
                    {q(BUSINESS_DAY)}, {q(FETCHED_AT)}, {q(HTTP_STATUS)}, {q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)}, {q(CONTENT_SHA256)}, {q(FILE_SIZE)},
                    {q(PARSER_VERSION)}, {q(CREATED_AT)}
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict({q(CONTENT_SHA256)}) do update set
                    {q(STORE_ID)} = excluded.{q(STORE_ID)},
                    {q(BUSINESS_DAY)} = excluded.{q(BUSINESS_DAY)},
                    {q(FETCHED_AT)} = excluded.{q(FETCHED_AT)},
                    {q(HTTP_STATUS)} = excluded.{q(HTTP_STATUS)},
                    {q(RESPONSE_CODE)} = excluded.{q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)} = excluded.{q(SOURCE_FILE)},
                    {q(FILE_SIZE)} = excluded.{q(FILE_SIZE)},
                    {q(PARSER_VERSION)} = excluded.{q(PARSER_VERSION)}
                """,
                (
                    artifact_id,
                    platform_id,
                    store_id,
                    parsed.endpoint_key,
                    business_day.isoformat(),
                    now,
                    http_status,
                    parsed.response_code,
                    str(source_path),
                    parsed.source_sha256,
                    parsed.source_bytes,
                    parsed.parser_version,
                    now,
                ),
            )
            artifact_id = self._resolve_artifact_id(conn, parsed.source_sha256, artifact_id)
            conn.execute(
                f"""
                insert into store_daily_new_customer_discount_overviews (
                    {q(STORE_ID)}, {q(BUSINESS_DAY)},
                    {q(NEW_CUSTOMER_DISCOUNT_SHOP_VISITORS)},
                    {q(NEW_CUSTOMER_DISCOUNT_PRODUCT_NEW_VISITORS)},
                    {q(NEW_CUSTOMER_DISCOUNT_PAID_BUYERS)},
                    {q(NEW_CUSTOMER_DISCOUNT_PAID_BUYER_RATIO)},
                    {q(NEW_CUSTOMER_DISCOUNT_PAID_AMOUNT)},
                    {q(NEW_CUSTOMER_DISCOUNT_PAID_AMOUNT_RATIO)},
                    {q(NEW_CUSTOMER_DISCOUNT_PAY_RATE)},
                    {q(NEW_CUSTOMER_DISCOUNT_SHOP_PAID_BUYERS)},
                    {q(NEW_CUSTOMER_DISCOUNT_SHOP_PAID_AMOUNT)},
                    {q(NEW_CUSTOMER_DISCOUNT_SHOP_PAY_RATE)}
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict({q(STORE_ID)}, {q(BUSINESS_DAY)}) do update set
                    {q(NEW_CUSTOMER_DISCOUNT_SHOP_VISITORS)} =
                        excluded.{q(NEW_CUSTOMER_DISCOUNT_SHOP_VISITORS)},
                    {q(NEW_CUSTOMER_DISCOUNT_PRODUCT_NEW_VISITORS)} =
                        excluded.{q(NEW_CUSTOMER_DISCOUNT_PRODUCT_NEW_VISITORS)},
                    {q(NEW_CUSTOMER_DISCOUNT_PAID_BUYERS)} =
                        excluded.{q(NEW_CUSTOMER_DISCOUNT_PAID_BUYERS)},
                    {q(NEW_CUSTOMER_DISCOUNT_PAID_BUYER_RATIO)} =
                        excluded.{q(NEW_CUSTOMER_DISCOUNT_PAID_BUYER_RATIO)},
                    {q(NEW_CUSTOMER_DISCOUNT_PAID_AMOUNT)} =
                        excluded.{q(NEW_CUSTOMER_DISCOUNT_PAID_AMOUNT)},
                    {q(NEW_CUSTOMER_DISCOUNT_PAID_AMOUNT_RATIO)} =
                        excluded.{q(NEW_CUSTOMER_DISCOUNT_PAID_AMOUNT_RATIO)},
                    {q(NEW_CUSTOMER_DISCOUNT_PAY_RATE)} =
                        excluded.{q(NEW_CUSTOMER_DISCOUNT_PAY_RATE)},
                    {q(NEW_CUSTOMER_DISCOUNT_SHOP_PAID_BUYERS)} =
                        excluded.{q(NEW_CUSTOMER_DISCOUNT_SHOP_PAID_BUYERS)},
                    {q(NEW_CUSTOMER_DISCOUNT_SHOP_PAID_AMOUNT)} =
                        excluded.{q(NEW_CUSTOMER_DISCOUNT_SHOP_PAID_AMOUNT)},
                    {q(NEW_CUSTOMER_DISCOUNT_SHOP_PAY_RATE)} =
                        excluded.{q(NEW_CUSTOMER_DISCOUNT_SHOP_PAY_RATE)}
                """,
                (
                    store_id,
                    business_day.isoformat(),
                    self._optional_decimal(parsed.shop_visitors),
                    self._optional_decimal(parsed.product_new_visitors),
                    self._optional_decimal(parsed.new_customer_paid_buyers),
                    self._optional_decimal(parsed.new_customer_paid_buyer_ratio),
                    self._optional_decimal(parsed.new_customer_paid_amount),
                    self._optional_decimal(parsed.new_customer_paid_amount_ratio),
                    self._optional_decimal(parsed.new_customer_paid_conversion_rate),
                    self._optional_decimal(parsed.shop_new_customer_paid_buyers),
                    self._optional_decimal(parsed.shop_new_customer_paid_amount),
                    self._optional_decimal(parsed.shop_new_customer_paid_conversion_rate),
                ),
            )
            conn.commit()

        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=parsed.metric_count,
            warnings=[
                "new customer discount metrics are stored in a dedicated daily table",
                f"response channelId={parsed.channel_id or 'unknown'} is endpoint metadata",
                "cycleCrc comparison values are intentionally not stored in the business table",
            ],
        )

    def ingest_sycm_shopping_gold(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_shopping_gold(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        return self._ingest_simple_daily_fact(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table="store_daily_shopping_gold_overviews",
            columns=SHOPPING_GOLD_COLUMNS,
            metric_values=(
                parsed.average_recharge_amount,
                parsed.recharge_amount,
                parsed.paid_buyers,
                parsed.recharge_items,
                parsed.recharge_refund_amount,
                parsed.paid_amount,
                parsed.customer_unit_price,
                parsed.recharge_capital_amount,
                parsed.recharge_buyers,
                parsed.recharge_rate,
                parsed.product_visitors,
                parsed.recharge_sub_order_count,
            ),
            warnings=[
                "shopping gold metrics are stored in a dedicated daily table",
                "the business table contains only store id, business day, and confirmed metrics",
            ],
        )

    def ingest_sycm_bybt(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_bybt(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        return self._ingest_simple_daily_fact(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table="store_daily_bybt_overviews",
            columns=BYBT_COLUMNS,
            metric_values=(
                parsed.visitors,
                parsed.paid_buyers,
                parsed.online_items,
                parsed.paid_amount,
                parsed.paid_sub_order_count,
                parsed.paid_items,
            ),
            warnings=[
                "BYBT metrics are stored in a dedicated daily table",
                "unrelated promotion fields are not inferred or copied into this table",
            ],
        )

    def ingest_sycm_bybt_items(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_bybt_items(
            source_path, business_day, fallback_platform_store_id=platform_store_id
        )
        return self._ingest_product_snapshot(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table=BYBT_ITEM_TABLE,
            columns=BYBT_ITEM_COLUMNS,
            dimensions=lambda row: (
                row.item_id, row.marketing_id, row.item_name, row.category_name,
                row.business_scenario, row.sales_method, row.race_type, row.play_type,
            ),
            metrics=lambda row: (
                row.paid_amount, row.paid_items, row.paid_sub_order_count,
                row.visitors, row.conversion_rate,
            ),
            warning="BYBT item rows replace the same store and business day atomically",
        )

    def ingest_brandsearch_report(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_brandsearch_report(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        return self._ingest_simple_daily_fact(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table="store_daily_brand_zone_overviews",
            columns=BRAND_ZONE_COLUMNS,
            metric_values=(
                parsed.impressions,
                parsed.search_requests,
                parsed.clicks,
                parsed.click_rate,
                parsed.click_visitors,
                parsed.item_cart_count,
                parsed.paid_amount,
                parsed.paid_order_count,
                parsed.conversion_rate,
                parsed.destination_clicks,
                parsed.interaction_clicks,
                parsed.destination_click_rate,
                parsed.shop_favorites,
                parsed.item_favorites,
                parsed.item_page_views,
                parsed.research_impressions,
                parsed.shop_page_views,
            ),
            warnings=[
                "PZ brand-zone metrics are stored in a dedicated daily table",
                "business table contains only store id, business day, and confirmed metrics",
                "transactiontotal is normalized from cents to currency units",
                "cost and view_time are intentionally excluded until their units are confirmed",
            ],
        )

    def ingest_alimama_campaign_report(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_alimama_campaign(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        artifact_id = f"{parsed.endpoint_key}:{parsed.source_sha256[:20]}"
        now = self._now()

        with self._connect(initialize=True, artifact_table=True) as conn:
            self._seed_metric_definitions(conn, now)
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn,
                platform_id,
                parsed.platform_store_id,
                store_name,
                now,
            )
            conn.execute(
                f"""
                insert into raw_response_artifacts (
                    {q(ARTIFACT_ID)}, {q(PLATFORM_ID)}, {q(STORE_ID)}, {q(ENDPOINT_KEY)},
                    {q(BUSINESS_DAY)}, {q(FETCHED_AT)}, {q(HTTP_STATUS)}, {q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)}, {q(CONTENT_SHA256)}, {q(FILE_SIZE)},
                    {q(PARSER_VERSION)}, {q(CREATED_AT)}
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict({q(CONTENT_SHA256)}) do update set
                    {q(STORE_ID)} = excluded.{q(STORE_ID)},
                    {q(BUSINESS_DAY)} = excluded.{q(BUSINESS_DAY)},
                    {q(FETCHED_AT)} = excluded.{q(FETCHED_AT)},
                    {q(HTTP_STATUS)} = excluded.{q(HTTP_STATUS)},
                    {q(RESPONSE_CODE)} = excluded.{q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)} = excluded.{q(SOURCE_FILE)},
                    {q(FILE_SIZE)} = excluded.{q(FILE_SIZE)},
                    {q(PARSER_VERSION)} = excluded.{q(PARSER_VERSION)}
                """,
                (
                    artifact_id,
                    platform_id,
                    store_id,
                    parsed.endpoint_key,
                    business_day.isoformat(),
                    now,
                    http_status,
                    parsed.response_code,
                    str(source_path),
                    parsed.source_sha256,
                    parsed.source_bytes,
                    parsed.parser_version,
                    now,
                ),
            )
            artifact_id = self._resolve_artifact_id(conn, parsed.source_sha256, artifact_id)
            conn.execute(
                f"delete from {PROMOTION_CAMPAIGN_TABLE} where {q(STORE_ID)}=? and {q(BUSINESS_DAY)}=?",
                (store_id, business_day.isoformat()),
            )
            conn.executemany(
                f"""
                insert into {PROMOTION_CAMPAIGN_TABLE} (
                    {", ".join(q(column) for column in PROMOTION_CAMPAIGN_COLUMNS)}
                ) values ({", ".join("?" for _ in PROMOTION_CAMPAIGN_COLUMNS)})
                """,
                [
                    (
                        store_id,
                        business_day.isoformat(),
                        row.scene_name,
                        row.campaign_id,
                        row.campaign_name,
                        *[self._optional_decimal(value) for value in row.metrics],
                    )
                    for row in parsed.rows
                ],
            )
            conn.commit()

        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=parsed.metric_count,
            warnings=[
                "Alimama campaign rows replace the same store and business day atomically",
                "campaign facts contain only store, day, campaign dimensions, and confirmed metrics",
            ],
        )

    def ingest_alimama_crowd_report(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_alimama_crowd(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        artifact_id = f"{parsed.endpoint_key}:{parsed.source_sha256[:20]}"
        now = self._now()

        with self._connect(initialize=True, artifact_table=True) as conn:
            self._seed_metric_definitions(conn, now)
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn,
                platform_id,
                parsed.platform_store_id,
                store_name,
                now,
            )
            conn.execute(
                f"""
                insert into raw_response_artifacts (
                    {q(ARTIFACT_ID)}, {q(PLATFORM_ID)}, {q(STORE_ID)}, {q(ENDPOINT_KEY)},
                    {q(BUSINESS_DAY)}, {q(FETCHED_AT)}, {q(HTTP_STATUS)}, {q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)}, {q(CONTENT_SHA256)}, {q(FILE_SIZE)},
                    {q(PARSER_VERSION)}, {q(CREATED_AT)}
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict({q(CONTENT_SHA256)}) do update set
                    {q(STORE_ID)} = excluded.{q(STORE_ID)},
                    {q(BUSINESS_DAY)} = excluded.{q(BUSINESS_DAY)},
                    {q(FETCHED_AT)} = excluded.{q(FETCHED_AT)},
                    {q(HTTP_STATUS)} = excluded.{q(HTTP_STATUS)},
                    {q(RESPONSE_CODE)} = excluded.{q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)} = excluded.{q(SOURCE_FILE)},
                    {q(FILE_SIZE)} = excluded.{q(FILE_SIZE)},
                    {q(PARSER_VERSION)} = excluded.{q(PARSER_VERSION)}
                """,
                (
                    artifact_id,
                    platform_id,
                    store_id,
                    parsed.endpoint_key,
                    business_day.isoformat(),
                    now,
                    http_status,
                    parsed.response_code,
                    str(source_path),
                    parsed.source_sha256,
                    parsed.source_bytes,
                    parsed.parser_version,
                    now,
                ),
            )
            artifact_id = self._resolve_artifact_id(conn, parsed.source_sha256, artifact_id)
            conn.execute(
                f"delete from {PROMOTION_CROWD_TABLE} where {q(STORE_ID)}=? and {q(BUSINESS_DAY)}=?",
                (store_id, business_day.isoformat()),
            )
            conn.executemany(
                f"""
                insert into {PROMOTION_CROWD_TABLE} (
                    {", ".join(q(column) for column in PROMOTION_CROWD_COLUMNS)}
                ) values ({", ".join("?" for _ in PROMOTION_CROWD_COLUMNS)})
                """,
                [
                    (
                        store_id,
                        business_day.isoformat(),
                        row.scene_name,
                        row.campaign_id,
                        row.campaign_name,
                        row.adgroup_id,
                        row.adgroup_name,
                        row.crowd_id,
                        row.crowd_name,
                        row.subject_id,
                        row.subject_name,
                        row.subject_type,
                        *[self._optional_decimal(value) for value in row.metrics],
                    )
                    for row in parsed.rows
                ],
            )
            conn.commit()

        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=parsed.metric_count,
            warnings=[
                "Alimama crowd rows replace the same store and business day atomically",
                "crowd facts are stored separately from campaign facts to prevent double counting",
            ],
        )

    def ingest_alimama_adgroup_report(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_alimama_adgroup(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        return self._ingest_alimama_promotion_hierarchy(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table=PROMOTION_ADGROUP_TABLE,
            columns=PROMOTION_ADGROUP_COLUMNS,
            endpoint_warning="adgroup facts are stored separately from campaign totals",
        )

    def ingest_alimama_bidword_report(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_alimama_bidword(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        return self._ingest_alimama_promotion_hierarchy(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table=PROMOTION_BIDWORD_TABLE,
            columns=PROMOTION_BIDWORD_COLUMNS,
            endpoint_warning="bidword facts are stored separately from campaign and adgroup totals",
        )

    def _ingest_alimama_promotion_hierarchy(
        self,
        *,
        parsed,
        source_path: Path,
        business_day: date,
        store_name: str,
        http_status: int,
        table: str,
        columns: tuple[str, ...],
        endpoint_warning: str,
    ) -> WarehouseMetricIngestResult:
        artifact_id = f"{parsed.endpoint_key}:{parsed.source_sha256[:20]}"
        now = self._now()
        with self._connect(initialize=True, artifact_table=True) as conn:
            self._seed_metric_definitions(conn, now)
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn, platform_id, parsed.platform_store_id, store_name, now
            )
            self._insert_raw_artifact(
                conn=conn,
                artifact_id=artifact_id,
                platform_id=platform_id,
                store_id=store_id,
                parsed=parsed,
                source_path=source_path,
                business_day=business_day,
                http_status=http_status,
                now=now,
            )
            artifact_id = self._resolve_artifact_id(conn, parsed.source_sha256, artifact_id)
            conn.execute(
                f"delete from {table} where {q(STORE_ID)}=? and {q(BUSINESS_DAY)}=?",
                (store_id, business_day.isoformat()),
            )
            conn.executemany(
                f"insert into {table} ({', '.join(q(column) for column in columns)}) "
                f"values ({', '.join('?' for _ in columns)})",
                [
                    (
                        store_id,
                        business_day.isoformat(),
                        *self._promotion_hierarchy_dimensions(row, table),
                        *[self._optional_decimal(value) for value in row.metrics],
                    )
                    for row in parsed.rows
                ],
            )
            conn.commit()
        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=parsed.metric_count,
            warnings=[endpoint_warning, f"rows replace the same store and business day in {table}"],
        )

    @staticmethod
    def _promotion_hierarchy_dimensions(row, table: str) -> tuple[str, ...]:
        if table == PROMOTION_ADGROUP_TABLE:
            return (
                row.scene_name,
                row.campaign_id,
                row.campaign_name,
                row.adgroup_id,
                row.adgroup_name,
                row.product_id,
                row.product_name,
            )
        return (
            row.scene_name,
            row.campaign_id,
            row.campaign_name,
            row.adgroup_id,
            row.adgroup_name,
            row.bidword_id,
            row.bidword_name,
            row.bidword_package_id,
            row.bidword_package_name,
            row.bidword_type,
            row.automatch_type,
            row.product_id,
            row.product_name,
        )

    @staticmethod
    def _insert_raw_artifact(
        *,
        conn: sqlite3.Connection,
        artifact_id: str,
        platform_id: int,
        store_id: int,
        parsed,
        source_path: Path,
        business_day: date,
        http_status: int,
        now: str,
    ) -> None:
        conn.execute(
            f"""
            insert into raw_response_artifacts (
                {q(ARTIFACT_ID)}, {q(PLATFORM_ID)}, {q(STORE_ID)}, {q(ENDPOINT_KEY)},
                {q(BUSINESS_DAY)}, {q(FETCHED_AT)}, {q(HTTP_STATUS)}, {q(RESPONSE_CODE)},
                {q(SOURCE_FILE)}, {q(CONTENT_SHA256)}, {q(FILE_SIZE)},
                {q(PARSER_VERSION)}, {q(CREATED_AT)}
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict({q(CONTENT_SHA256)}) do update set
                {q(STORE_ID)} = excluded.{q(STORE_ID)},
                {q(BUSINESS_DAY)} = excluded.{q(BUSINESS_DAY)},
                {q(FETCHED_AT)} = excluded.{q(FETCHED_AT)},
                {q(HTTP_STATUS)} = excluded.{q(HTTP_STATUS)},
                {q(RESPONSE_CODE)} = excluded.{q(RESPONSE_CODE)},
                {q(SOURCE_FILE)} = excluded.{q(SOURCE_FILE)},
                {q(FILE_SIZE)} = excluded.{q(FILE_SIZE)},
                {q(PARSER_VERSION)} = excluded.{q(PARSER_VERSION)}
            """,
            (
                artifact_id,
                platform_id,
                store_id,
                parsed.endpoint_key,
                business_day.isoformat(),
                now,
                http_status,
                parsed.response_code,
                str(source_path),
                parsed.source_sha256,
                parsed.source_bytes,
                parsed.parser_version,
                now,
            ),
        )

    def ingest_alimama_promotion_item_report(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_alimama_promotion_item(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        return self._ingest_alimama_promotion_detail(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table=PROMOTION_ITEM_TABLE,
            columns=PROMOTION_ITEM_COLUMNS,
        )

    def ingest_alimama_promotion_content_report(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_alimama_promotion_content(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        return self._ingest_alimama_promotion_detail(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table=PROMOTION_CONTENT_TABLE,
            columns=PROMOTION_CONTENT_COLUMNS,
        )

    def _ingest_alimama_promotion_detail(
        self,
        *,
        parsed,
        source_path: Path,
        business_day: date,
        store_name: str,
        http_status: int,
        table: str,
        columns: tuple[str, ...],
    ) -> WarehouseMetricIngestResult:
        artifact_id = f"{parsed.endpoint_key}:{parsed.source_sha256[:20]}"
        now = self._now()

        with self._connect(initialize=True, artifact_table=True) as conn:
            self._seed_metric_definitions(conn, now)
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn,
                platform_id,
                parsed.platform_store_id,
                store_name,
                now,
            )
            conn.execute(
                f"""
                insert into raw_response_artifacts (
                    {q(ARTIFACT_ID)}, {q(PLATFORM_ID)}, {q(STORE_ID)}, {q(ENDPOINT_KEY)},
                    {q(BUSINESS_DAY)}, {q(FETCHED_AT)}, {q(HTTP_STATUS)}, {q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)}, {q(CONTENT_SHA256)}, {q(FILE_SIZE)},
                    {q(PARSER_VERSION)}, {q(CREATED_AT)}
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict({q(CONTENT_SHA256)}) do update set
                    {q(STORE_ID)} = excluded.{q(STORE_ID)},
                    {q(BUSINESS_DAY)} = excluded.{q(BUSINESS_DAY)},
                    {q(FETCHED_AT)} = excluded.{q(FETCHED_AT)},
                    {q(HTTP_STATUS)} = excluded.{q(HTTP_STATUS)},
                    {q(RESPONSE_CODE)} = excluded.{q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)} = excluded.{q(SOURCE_FILE)},
                    {q(FILE_SIZE)} = excluded.{q(FILE_SIZE)},
                    {q(PARSER_VERSION)} = excluded.{q(PARSER_VERSION)}
                """,
                (
                    artifact_id,
                    platform_id,
                    store_id,
                    parsed.endpoint_key,
                    business_day.isoformat(),
                    now,
                    http_status,
                    parsed.response_code,
                    str(source_path),
                    parsed.source_sha256,
                    parsed.source_bytes,
                    parsed.parser_version,
                    now,
                ),
            )
            artifact_id = self._resolve_artifact_id(conn, parsed.source_sha256, artifact_id)
            conn.execute(
                f"delete from {table} where {q(STORE_ID)}=? and {q(BUSINESS_DAY)}=?",
                (store_id, business_day.isoformat()),
            )
            conn.executemany(
                f"""
                insert into {table} ({", ".join(q(column) for column in columns)})
                values ({", ".join("?" for _ in columns)})
                """,
                [
                    (
                        store_id,
                        business_day.isoformat(),
                        row.scene_name,
                        row.campaign_id,
                        row.campaign_name,
                        row.subject_id,
                        row.subject_name,
                        row.subject_type,
                        *[self._optional_decimal(value) for value in row.metrics],
                    )
                    for row in parsed.rows
                ],
            )
            conn.commit()

        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=parsed.metric_count,
            warnings=[
                f"Alimama promotion detail rows replace the same day in {table}",
                "promotion detail facts are stored separately from campaign facts",
            ],
        )

    def ingest_cps_overview(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_cps_overview(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        return self._ingest_simple_daily_fact(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table="store_daily_cps_overviews",
            columns=CPS_COLUMNS,
            metric_values=tuple(
                getattr(parsed, attribute)
                for attribute in (
                    "payment_commission_expense",
                    "payment_service_fee_expense",
                    "payment_commission_rate",
                    "payment_service_fee_rate",
                    "payment_order_count",
                    "payment_amount",
                    "click_visitors",
                    "settlement_total_expense",
                    "settlement_order_count",
                    "settlement_amount",
                    "preorder_deposit_order_count",
                    "preorder_deposit_amount",
                    "preorder_remaining_amount",
                    "preorder_total_amount",
                    "payment_marketing_service_fee_expense",
                    "settlement_marketing_service_fee_expense",
                )
            ),
            warnings=[
                "CPS metrics are stored in a dedicated daily table",
                "the business table contains only store id, business day, and CPS metrics",
                "live response confirms amount values are already in currency units; no cents conversion is applied",
                "rate values remain decimal fractions and are multiplied by 100 only for display",
            ],
        )

    def ingest_taobao_flash_sale(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_taobao_flash_sale(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        return self._ingest_simple_daily_fact(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table="store_daily_taobao_flash_sale_overviews",
            columns=TAOBAO_FLASH_SALE_COLUMNS,
            metric_values=tuple(
                parsed.metrics.get(code)
                for _, code in TAOBAO_FLASH_SALE_FIELDS
            ),
            warnings=[
                "Taobao flash sale metrics are stored in a dedicated daily table",
                "qoq and peer-level display fields are not stored in the business table",
                "amount values are normalized to two decimal places",
            ],
        )

    def ingest_taobao_flash_sale_items(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_taobao_flash_sale_items(
            source_path, business_day, fallback_platform_store_id=platform_store_id
        )
        return self._ingest_product_snapshot(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table=TAOBAO_FLASH_SALE_ITEM_TABLE,
            columns=TAOBAO_FLASH_SALE_ITEM_COLUMNS,
            dimensions=lambda row: (
                row.item_id, row.activity_id, row.item_name, row.activity_name,
                row.activity_status, row.activity_start_time, row.activity_end_time,
            ),
            metrics=lambda row: (
                row.ipv, row.ipv_uv, row.paid_order_count, row.paid_amount,
                row.new_customers, row.conversion_rate,
            ),
            warning="Taobao flash-sale item rows replace the same store and business day atomically",
        )

    def ingest_taobao_risk_price_items(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_taobao_risk_price_items(
            source_path, business_day, fallback_platform_store_id=platform_store_id
        )
        return self._ingest_product_snapshot(
            parsed=parsed, source_path=source_path, business_day=business_day,
            store_name=store_name, http_status=http_status,
            table=TAOBAO_RISK_PRICE_ITEM_TABLE, columns=TAOBAO_RISK_PRICE_ITEM_COLUMNS,
            dimensions=lambda row: (
                row.item_id, row.item_name, row.modified_at, row.risk_type,
                row.risk_description, row.promotion_details, row.risk_sub_description,
            ),
            metrics=lambda row: (row.low_price, row.original_price, row.low_price_sku_count),
            warning="Taobao risk-price rows replace the same store and business day atomically",
        )

    def ingest_taobao_current_price_items(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_taobao_current_price_items(
            source_path, business_day, fallback_platform_store_id=platform_store_id
        )
        return self._ingest_product_snapshot(
            parsed=parsed, source_path=source_path, business_day=business_day,
            store_name=store_name, http_status=http_status,
            table=TAOBAO_CURRENT_PRICE_ITEM_TABLE, columns=TAOBAO_CURRENT_PRICE_ITEM_COLUMNS,
            dimensions=lambda row: (
                row.item_id, row.item_title, row.attention, row.risk_tag,
                row.normal_promotion_details, row.predicted_promotion_details,
                row.risk_promotion_details, row.item_detail_url, row.main_picture,
            ),
            metrics=lambda row: (
                row.low_price, row.low_price_lower_bound, row.low_price_upper_bound,
                row.original_price_lower_bound, row.original_price_upper_bound,
                row.normal_predict_price_lower_bound, row.normal_predict_price_upper_bound,
                row.predict_price_lower_bound, row.predict_price_upper_bound, row.sku_count,
            ),
            warning="Taobao current-price rows replace the same store and business day atomically",
        )

    def ingest_taobao_activity_item_snapshots(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_taobao_activity_item_snapshots(
            source_path, business_day, fallback_platform_store_id=platform_store_id
        )
        return self._ingest_product_snapshot(
            parsed=parsed, source_path=source_path, business_day=business_day,
            store_name=store_name, http_status=http_status,
            table=TAOBAO_ACTIVITY_ITEM_SNAPSHOT_TABLE,
            columns=TAOBAO_ACTIVITY_ITEM_SNAPSHOT_COLUMNS,
            dimensions=lambda row: (
                row.snapshot_type, row.marketing_id, row.item_id, row.item_name,
                row.status, row.status_name, row.activity_name, row.start_time,
                row.end_time, row.sign_time, row.item_link, row.activity_url,
                row.item_picture, row.activity_price_name, row.supply_price_name,
                row.common_activity_tags, row.material_status_name, row.ic_status_name,
            ),
            metrics=lambda row: (
                row.original_price, row.activity_price, row.supply_price, row.inventory,
                row.sold_count, row.limit_count, row.signed_count, row.unsigned_count,
            ),
            warning="Taobao activity item snapshots replace all snapshot types for the same store and day atomically",
        )

    def ingest_taobao_operational_snapshots(
        self,
        *,
        risk_price_path: Path,
        current_price_path: Path,
        activity_snapshot_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        """Replace the three operational snapshot families as one transaction.

        All files are parsed before opening the write transaction.  A failed
        endpoint or malformed page therefore leaves every prior snapshot
        family untouched for that store and day.
        """
        risk = load_and_parse_taobao_risk_price_items(
            risk_price_path, business_day, fallback_platform_store_id=platform_store_id
        )
        current = load_and_parse_taobao_current_price_items(
            current_price_path, business_day, fallback_platform_store_id=platform_store_id
        )
        activity = load_and_parse_taobao_activity_item_snapshots(
            activity_snapshot_path, business_day, fallback_platform_store_id=platform_store_id
        )
        now = self._now()
        parsed_items = (
            (risk, risk_price_path, TAOBAO_RISK_PRICE_ITEM_TABLE, TAOBAO_RISK_PRICE_ITEM_COLUMNS,
             lambda row: (row.item_id, row.item_name, row.modified_at, row.risk_type, row.risk_description, row.promotion_details, row.risk_sub_description),
             lambda row: (row.low_price, row.original_price, row.low_price_sku_count)),
            (current, current_price_path, TAOBAO_CURRENT_PRICE_ITEM_TABLE, TAOBAO_CURRENT_PRICE_ITEM_COLUMNS,
             lambda row: (row.item_id, row.item_title, row.attention, row.risk_tag, row.normal_promotion_details, row.predicted_promotion_details, row.risk_promotion_details, row.item_detail_url, row.main_picture),
             lambda row: (row.low_price, row.low_price_lower_bound, row.low_price_upper_bound, row.original_price_lower_bound, row.original_price_upper_bound, row.normal_predict_price_lower_bound, row.normal_predict_price_upper_bound, row.predict_price_lower_bound, row.predict_price_upper_bound, row.sku_count)),
            (activity, activity_snapshot_path, TAOBAO_ACTIVITY_ITEM_SNAPSHOT_TABLE, TAOBAO_ACTIVITY_ITEM_SNAPSHOT_COLUMNS,
             lambda row: (row.snapshot_type, row.marketing_id, row.item_id, row.item_name, row.status, row.status_name, row.activity_name, row.start_time, row.end_time, row.sign_time, row.item_link, row.activity_url, row.item_picture, row.activity_price_name, row.supply_price_name, row.common_activity_tags, row.material_status_name, row.ic_status_name),
             lambda row: (row.original_price, row.activity_price, row.supply_price, row.inventory, row.sold_count, row.limit_count, row.signed_count, row.unsigned_count)),
        )
        with self._connect(initialize=True, artifact_table=True) as conn:
            self._seed_metric_definitions(conn, now)
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(conn, platform_id, platform_store_id, store_name, now)
            artifacts = []
            for parsed, source_path, _, _, _, _ in parsed_items:
                artifact_id = f"{getattr(parsed, 'endpoint_key')}:{getattr(parsed, 'source_sha256')[:20]}"
                self._insert_raw_artifact(
                    conn=conn, artifact_id=artifact_id, platform_id=platform_id, store_id=store_id,
                    parsed=parsed, source_path=source_path, business_day=business_day,
                    http_status=http_status, now=now,
                )
                artifacts.append(self._resolve_artifact_id(conn, getattr(parsed, "source_sha256"), artifact_id))
            for parsed, _, table, columns, dimensions, metrics in parsed_items:
                conn.execute(
                    f"delete from {q(table)} where {q(STORE_ID)}=? and {q(BUSINESS_DAY)}=?",
                    (store_id, business_day.isoformat()),
                )
                conn.executemany(
                    f"insert into {q(table)} ({', '.join(q(column) for column in columns)}) values ({', '.join('?' for _ in columns)})",
                    [
                        (store_id, business_day.isoformat(), *dimensions(row), *[self._optional_decimal(value) for value in metrics(row)])
                        for row in getattr(parsed, "rows")
                    ],
                )
            conn.commit()
        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id), store=self.get_store(store_id), business_day=business_day,
            source_artifact_id=artifacts[-1], metric_count=sum(int(getattr(parsed, "metric_count")) for parsed, *_ in parsed_items),
            warnings=["Taobao operational snapshots are parsed first and replaced in one transaction", "risk-price, current-price, and activity snapshot tables are kept separate"],
        )

    def ingest_mtop_content_overview(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_content_overview(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        return self._ingest_simple_daily_fact(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table="store_daily_content_overviews",
            columns=CONTENT_OVERVIEW_COLUMNS,
            metric_values=tuple(
                parsed.metrics.get(code)
                for _, code in CONTENT_OVERVIEW_FIELDS
            ),
            warnings=[
                "content overview metrics are stored in a dedicated daily table",
                "ratio values remain raw decimals and should be multiplied by 100 only for display",
            ],
        )

    def ingest_mtop_taojinbi(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_taojinbi(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        return self._ingest_simple_daily_fact(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table="store_daily_taojinbi_overviews",
            columns=TAOJINBI_COLUMNS,
            metric_values=tuple(
                parsed.metrics.get(code)
                for _, code in TAOJINBI_FIELDS
            ),
            preserve_existing_values=True,
            warnings=[
                f"Taojinbi {parsed.section} metrics were merged into the daily row",
                "general and detailed MTop responses can be ingested in either order",
                "MTop ratio and amount values are stored as returned after numeric normalization",
            ],
        )

    def ingest_mtop_customer_service_overview(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_customer_service_overview(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        return self._ingest_simple_daily_fact(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table="store_daily_customer_service_overviews",
            columns=CUSTOMER_SERVICE_OVERVIEW_COLUMNS,
            metric_values=tuple(
                parsed.metrics.get(code)
                for _, code in CUSTOMER_SERVICE_OVERVIEW_FIELDS
            ),
            warnings=[
                "customer-service KPI values are stored in a dedicated daily table",
                "ratio values remain raw decimals and should be multiplied by 100 only for display",
                "missing KPI values remain null instead of being converted to zero",
            ],
        )

    def ingest_sycm_customer_service_accounts(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_customer_service_accounts(
            source_path,
            business_day,
            fallback_platform_store_id=platform_store_id,
        )
        artifact_id = f"{parsed.endpoint_key}:{parsed.source_sha256[:20]}"
        now = self._now()

        with self._connect(initialize=True, artifact_table=True) as conn:
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn,
                platform_id,
                parsed.platform_store_id,
                store_name,
                now,
            )
            conn.execute(
                f"""
                insert into raw_response_artifacts (
                    {q(ARTIFACT_ID)}, {q(PLATFORM_ID)}, {q(STORE_ID)}, {q(ENDPOINT_KEY)},
                    {q(BUSINESS_DAY)}, {q(FETCHED_AT)}, {q(HTTP_STATUS)}, {q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)}, {q(CONTENT_SHA256)}, {q(FILE_SIZE)},
                    {q(PARSER_VERSION)}, {q(CREATED_AT)}
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict({q(CONTENT_SHA256)}) do update set
                    {q(STORE_ID)} = excluded.{q(STORE_ID)},
                    {q(BUSINESS_DAY)} = excluded.{q(BUSINESS_DAY)},
                    {q(FETCHED_AT)} = excluded.{q(FETCHED_AT)},
                    {q(HTTP_STATUS)} = excluded.{q(HTTP_STATUS)},
                    {q(RESPONSE_CODE)} = excluded.{q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)} = excluded.{q(SOURCE_FILE)},
                    {q(FILE_SIZE)} = excluded.{q(FILE_SIZE)},
                    {q(PARSER_VERSION)} = excluded.{q(PARSER_VERSION)}
                """,
                (
                    artifact_id,
                    platform_id,
                    store_id,
                    parsed.endpoint_key,
                    business_day.isoformat(),
                    now,
                    http_status,
                    parsed.response_code,
                    str(source_path),
                    parsed.source_sha256,
                    parsed.source_bytes,
                    parsed.parser_version,
                    now,
                ),
            )
            artifact_id = self._resolve_artifact_id(
                conn,
                parsed.source_sha256,
                artifact_id,
            )
            conn.execute(
                f"""
                delete from store_daily_customer_service_accounts
                where {q(STORE_ID)} = ? and {q(BUSINESS_DAY)} = ?
                """,
                (store_id, business_day.isoformat()),
            )
            conn.executemany(
                f"""
                insert into store_daily_customer_service_accounts (
                    {", ".join(q(column) for column in CUSTOMER_SERVICE_ACCOUNT_COLUMNS)}
                ) values (
                    {", ".join("?" for _ in CUSTOMER_SERVICE_ACCOUNT_COLUMNS)}
                )
                """,
                [
                    (
                        store_id,
                        business_day.isoformat(),
                        row.nickname,
                        self._optional_decimal(row.consult_users),
                        self._optional_decimal(row.valid_reception_users),
                        self._optional_decimal(row.consult_order_users),
                        self._optional_decimal(row.order_users),
                        self._optional_decimal(row.order_amount),
                        self._optional_decimal(row.sale_users),
                        self._optional_decimal(row.sale_amount),
                        self._optional_decimal(row.sale_quantity),
                        self._optional_decimal(row.order_count),
                        self._optional_decimal(row.sale_amount_ratio),
                        self._optional_decimal(row.refund_amount),
                        self._optional_decimal(row.net_sale_amount),
                    )
                    for row in parsed.rows
                ],
            )
            conn.commit()

        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=parsed.metric_count,
            warnings=[
                "customer-service account rows replace the same store and business day atomically",
                "summary rows and rows without a Wangwang nickname are not stored",
                "the business table contains no raw response, evidence id, or update timestamp",
            ],
        )

    def ingest_sycm_live_overview(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_live_overview(source_path, platform_store_id)
        return self._ingest_simple_daily_fact(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table="store_daily_live_overviews",
            columns=LIVE_OVERVIEW_COLUMNS,
            metric_values=parsed.metrics,
            warnings=["live overview metrics are stored as one daily fact row"],
        )

    def ingest_sycm_live_store_performance(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_live_store_performance(source_path, platform_store_id)
        return self._ingest_simple_daily_fact(
            parsed=parsed,
            source_path=source_path,
            business_day=business_day,
            store_name=store_name,
            http_status=http_status,
            table="store_daily_live_store_performance",
            columns=LIVE_STORE_PERFORMANCE_COLUMNS,
            metric_values=parsed.metrics,
            warnings=["live store performance metrics are stored as one daily fact row"],
        )

    def ingest_sycm_live_talent(
        self,
        source_path: Path,
        business_day: date,
        store_name: str,
        platform_store_id: str = "2200573698992",
        http_status: int = 200,
    ) -> WarehouseMetricIngestResult:
        parsed = load_and_parse_live_talent(source_path, platform_store_id)
        artifact_id = f"{parsed.endpoint_key}:{parsed.source_sha256[:20]}"
        now = self._now()
        with self._connect(initialize=True, artifact_table=True) as conn:
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(conn, platform_id, parsed.platform_store_id, store_name, now)
            conn.execute(
                f"""
                insert into raw_response_artifacts (
                    {q(ARTIFACT_ID)}, {q(PLATFORM_ID)}, {q(STORE_ID)}, {q(ENDPOINT_KEY)},
                    {q(BUSINESS_DAY)}, {q(FETCHED_AT)}, {q(HTTP_STATUS)}, {q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)}, {q(CONTENT_SHA256)}, {q(FILE_SIZE)},
                    {q(PARSER_VERSION)}, {q(CREATED_AT)}
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict({q(CONTENT_SHA256)}) do update set
                    {q(STORE_ID)} = excluded.{q(STORE_ID)},
                    {q(BUSINESS_DAY)} = excluded.{q(BUSINESS_DAY)},
                    {q(FETCHED_AT)} = excluded.{q(FETCHED_AT)},
                    {q(HTTP_STATUS)} = excluded.{q(HTTP_STATUS)},
                    {q(RESPONSE_CODE)} = excluded.{q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)} = excluded.{q(SOURCE_FILE)},
                    {q(FILE_SIZE)} = excluded.{q(FILE_SIZE)},
                    {q(PARSER_VERSION)} = excluded.{q(PARSER_VERSION)}
                """,
                (
                    artifact_id,
                    platform_id,
                    store_id,
                    parsed.endpoint_key,
                    business_day.isoformat(),
                    now,
                    http_status,
                    parsed.response_code,
                    str(source_path),
                    parsed.source_sha256,
                    parsed.source_bytes,
                    parsed.parser_version,
                    now,
                ),
            )
            artifact_id = self._resolve_artifact_id(conn, parsed.source_sha256, artifact_id)
            conn.execute(
                f"delete from {LIVE_TALENT_TABLE} where {q(STORE_ID)}=? and {q(BUSINESS_DAY)}=?",
                (store_id, business_day.isoformat()),
            )
            conn.executemany(
                f"""
                insert into {LIVE_TALENT_TABLE} ({", ".join(q(column) for column in LIVE_TALENT_COLUMNS)})
                values ({", ".join("?" for _ in LIVE_TALENT_COLUMNS)})
                """,
                [
                    (
                        store_id,
                        business_day.isoformat(),
                        row.talent_id,
                        row.talent_name,
                        *[self._optional_decimal(value) for value in row.metrics],
                    )
                    for row in parsed.rows
                ],
            )
            conn.commit()
        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=parsed.metric_count,
            warnings=["live talent rows replace the same store and business day atomically"],
        )

    def _ingest_simple_daily_fact(
        self,
        *,
        parsed: object,
        source_path: Path,
        business_day: date,
        store_name: str,
        http_status: int,
        table: str,
        columns: tuple[str, ...],
        metric_values: tuple[object, ...],
        warnings: list[str],
        preserve_existing_values: bool = False,
    ) -> WarehouseMetricIngestResult:
        if len(metric_values) != len(columns) - 2:
            raise ValueError(
                f"{table} expected {len(columns) - 2} metrics, got {len(metric_values)}."
            )

        endpoint_key = str(getattr(parsed, "endpoint_key"))
        source_sha256 = str(getattr(parsed, "source_sha256"))
        artifact_id = f"{endpoint_key}:{source_sha256[:20]}"
        now = self._now()

        with self._connect(initialize=True, artifact_table=True) as conn:
            self._seed_metric_definitions(conn, now)
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn,
                platform_id,
                str(getattr(parsed, "platform_store_id")),
                store_name,
                now,
            )
            conn.execute(
                f"""
                insert into raw_response_artifacts (
                    {q(ARTIFACT_ID)}, {q(PLATFORM_ID)}, {q(STORE_ID)}, {q(ENDPOINT_KEY)},
                    {q(BUSINESS_DAY)}, {q(FETCHED_AT)}, {q(HTTP_STATUS)}, {q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)}, {q(CONTENT_SHA256)}, {q(FILE_SIZE)},
                    {q(PARSER_VERSION)}, {q(CREATED_AT)}
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict({q(CONTENT_SHA256)}) do update set
                    {q(STORE_ID)} = excluded.{q(STORE_ID)},
                    {q(BUSINESS_DAY)} = excluded.{q(BUSINESS_DAY)},
                    {q(FETCHED_AT)} = excluded.{q(FETCHED_AT)},
                    {q(HTTP_STATUS)} = excluded.{q(HTTP_STATUS)},
                    {q(RESPONSE_CODE)} = excluded.{q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)} = excluded.{q(SOURCE_FILE)},
                    {q(FILE_SIZE)} = excluded.{q(FILE_SIZE)},
                    {q(PARSER_VERSION)} = excluded.{q(PARSER_VERSION)}
                """,
                (
                    artifact_id,
                    platform_id,
                    store_id,
                    endpoint_key,
                    business_day.isoformat(),
                    now,
                    http_status,
                    int(getattr(parsed, "response_code")),
                    str(source_path),
                    source_sha256,
                    int(getattr(parsed, "source_bytes")),
                    str(getattr(parsed, "parser_version")),
                    now,
                ),
            )
            artifact_id = self._resolve_artifact_id(conn, source_sha256, artifact_id)
            if preserve_existing_values:
                update_assignments = ", ".join(
                    f"{q(column)} = coalesce(excluded.{q(column)}, {table}.{q(column)})"
                    for column in columns[2:]
                )
            else:
                update_assignments = ", ".join(
                    f"{q(column)} = excluded.{q(column)}"
                    for column in columns[2:]
                )
            conn.execute(
                f"""
                insert into {table} (
                    {", ".join(q(column) for column in columns)}
                ) values ({", ".join("?" for _ in columns)})
                on conflict({q(STORE_ID)}, {q(BUSINESS_DAY)}) do update set
                    {update_assignments}
                """,
                (
                    store_id,
                    business_day.isoformat(),
                    *[self._optional_decimal(value) for value in metric_values],
                ),
            )
            conn.commit()

        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=int(getattr(parsed, "metric_count")),
            warnings=warnings,
        )

    def _ingest_product_snapshot(
        self,
        *,
        parsed: object,
        source_path: Path,
        business_day: date,
        store_name: str,
        http_status: int,
        table: str,
        columns: tuple[str, ...],
        dimensions,
        metrics,
        warning: str,
    ) -> WarehouseMetricIngestResult:
        endpoint_key = str(getattr(parsed, "endpoint_key"))
        source_sha256 = str(getattr(parsed, "source_sha256"))
        artifact_id = f"{endpoint_key}:{source_sha256[:20]}"
        now = self._now()
        with self._connect(initialize=True, artifact_table=True) as conn:
            self._seed_metric_definitions(conn, now)
            platform_id = self._ensure_platform(conn, "tmall", "天猫", now)
            store_id = self._ensure_store(
                conn, platform_id, str(getattr(parsed, "platform_store_id")), store_name, now
            )
            self._insert_raw_artifact(
                conn=conn, artifact_id=artifact_id, platform_id=platform_id, store_id=store_id,
                parsed=parsed, source_path=source_path, business_day=business_day,
                http_status=http_status, now=now,
            )
            artifact_id = self._resolve_artifact_id(conn, source_sha256, artifact_id)
            conn.execute(
                f"delete from {q(table)} where {q(STORE_ID)}=? and {q(BUSINESS_DAY)}=?",
                (store_id, business_day.isoformat()),
            )
            insert_columns = ", ".join(q(column) for column in columns)
            placeholders = ", ".join("?" for _ in columns)
            conn.executemany(
                f"insert into {q(table)} ({insert_columns}) values ({placeholders})",
                [
                    (
                        store_id, business_day.isoformat(), *dimensions(row),
                        *[self._optional_decimal(value) for value in metrics(row)],
                    )
                    for row in getattr(parsed, "rows")
                ],
            )
            conn.commit()
        return WarehouseMetricIngestResult(
            platform=self.get_platform(platform_id),
            store=self.get_store(store_id),
            business_day=business_day,
            source_artifact_id=artifact_id,
            metric_count=int(getattr(parsed, "metric_count")),
            warnings=[warning, f"{len(getattr(parsed, 'rows'))} product rows stored in {table}"],
        )

    def _upsert_daily_fact_row(
        self,
        conn: sqlite3.Connection,
        *,
        table: str,
        columns: tuple[str, ...],
        store_id: int,
        business_day: date,
        values: dict[str, object],
    ) -> None:
        if len(columns) < 3:
            raise ValueError(f"{table} must have at least one business metric column.")
        update_columns = columns[2:]
        conn.execute(
            f"""
            insert into {table} ({", ".join(q(column) for column in columns)})
            values ({", ".join("?" for _ in columns)})
            on conflict({q(STORE_ID)}, {q(BUSINESS_DAY)}) do update set
                {", ".join(f'{q(column)} = excluded.{q(column)}' for column in update_columns)}
            """,
            (
                store_id,
                business_day.isoformat(),
                *[self._optional_decimal(values.get(column)) for column in update_columns],
            ),
        )

    @staticmethod
    def _first_metric_value(
        metrics: dict[str, object],
        codes: tuple[str, ...],
    ) -> object | None:
        for code in codes:
            if code in metrics:
                return metrics[code]
        return None

    def list_platforms(self) -> list[PlatformRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select "平台ID" as platform_id, "平台编码" as code,
                       "平台名称" as name, "状态" as status
                from platforms
                order by "平台名称"
                """
            ).fetchall()
        return [PlatformRecord(**dict(row)) for row in rows]

    def list_stores(self) -> list[StoreRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select s."店铺ID" as store_id, s."平台ID" as platform_id,
                       p."平台名称" as platform_name,
                       s."平台主体ID" as platform_store_id,
                       s."店铺名称" as store_name, s."状态" as status,
                       s."首次发现时间" as first_seen_at,
                       s."更新时间" as updated_at
                from stores s
                join platforms p on p."平台ID" = s."平台ID"
                order by s."店铺名称"
                """
            ).fetchall()
        return [StoreRecord(**dict(row)) for row in rows]

    def get_platform(self, platform_id: int) -> PlatformRecord:
        with self._connect() as conn:
            row = conn.execute(
                """
                select "平台ID" as platform_id, "平台编码" as code,
                       "平台名称" as name, "状态" as status
                from platforms
                where "平台ID" = ?
                """,
                (platform_id,),
            ).fetchone()
        if row is None:
            raise WarehouseDataNotAvailable(f"Platform not found: {platform_id}")
        return PlatformRecord(**dict(row))

    def get_store(self, store_id: int) -> StoreRecord:
        with self._connect() as conn:
            row = conn.execute(
                """
                select s."店铺ID" as store_id, s."平台ID" as platform_id,
                       p."平台名称" as platform_name,
                       s."平台主体ID" as platform_store_id,
                       s."店铺名称" as store_name, s."状态" as status,
                       s."首次发现时间" as first_seen_at,
                       s."更新时间" as updated_at
                from stores s
                join platforms p on p."平台ID" = s."平台ID"
                where s."店铺ID" = ?
                """,
                (store_id,),
            ).fetchone()
        if row is None:
            raise WarehouseDataNotAvailable(f"Store not found: {store_id}")
        return StoreRecord(**dict(row))

    def get_daily_overview(
        self,
        store_id: int | None = None,
        business_day: date | None = None,
    ) -> StoreDailyOverview | None:
        with self._connect() as conn:
            conditions = []
            params: list[object] = []
            if store_id:
                conditions.append('o."店铺ID" = ?')
                params.append(store_id)
            if business_day:
                conditions.append('o."业务日期" = ?')
                params.append(business_day.isoformat())
            where = f"where {' and '.join(conditions)}" if conditions else ""
            row = conn.execute(
                f"""
                select o.*
                from store_daily_overviews o
                {where}
                order by o."业务日期" desc
                limit 1
                """,
                params,
            ).fetchone()
        if row is None:
            return None
        values: dict[str, object] = {
            "store_id": int(row[STORE_ID]),
            "business_day": date.fromisoformat(row[BUSINESS_DAY]),
        }
        for column, code in DAILY_OVERVIEW_FIELDS:
            field_name = DAILY_OVERVIEW_RESPONSE_FIELDS[code]
            values[field_name] = row[column] if row[column] is not None else "0"
        return StoreDailyOverview(**values)

    def get_daily_flow_overview(
        self,
        store_id: int,
        business_day: date | None = None,
    ) -> StoreDailyFlowOverview | None:
        with self._connect() as conn:
            conditions = [f"{q(STORE_ID)} = ?"]
            params: list[object] = [store_id]
            if business_day:
                conditions.append(f"{q(BUSINESS_DAY)} = ?")
                params.append(business_day.isoformat())
            row = conn.execute(
                f"""
                select *
                from store_daily_flow_overviews
                where {" and ".join(conditions)}
                order by {q(BUSINESS_DAY)} desc
                limit 1
                """,
                params,
            ).fetchone()
        if row is None:
            return None

        values = dict(row)
        metrics = [
            StoreDailyFlowOverviewMetric(
                label=label,
                metric_code=metric_code,
                value=Decimal(str(values[label])) if values.get(label) is not None else None,
                unit=unit,
                confirmation_status=confirmation_status,
            )
            for label, metric_code, unit, confirmation_status in FLOW_OVERVIEW_FIELDS
        ]
        return StoreDailyFlowOverview(
            store_id=int(values[STORE_ID]),
            business_day=date.fromisoformat(str(values[BUSINESS_DAY])),
            metrics=metrics,
        )

    def get_activity_calendar_events(
        self,
        store_id: int,
        business_day: date | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[StoreActivityCalendarEvent]:
        with self._connect() as conn:
            if business_day is not None:
                start_date = business_day
                end_date = business_day
            elif start_date is None and end_date is None:
                row = conn.execute(
                    f"""
                    select max({q(BUSINESS_DAY)}) as business_day
                    from store_activity_calendar_events
                    where {q(STORE_ID)} = ?
                    """,
                    (store_id,),
                ).fetchone()
                if row is None or row["business_day"] is None:
                    return []
                start_date = date.fromisoformat(str(row["business_day"]))
                end_date = start_date
            elif start_date is None:
                start_date = end_date
            elif end_date is None:
                end_date = start_date

            rows = conn.execute(
                f"""
                select
                    {q(STORE_ID)} as store_id,
                    {q(BUSINESS_DAY)} as business_day,
                    {q(ACTIVITY_ID)} as activity_id,
                    {q(ACTIVITY_NAME)} as activity_name,
                    {q(ACTIVITY_TYPE)} as activity_type,
                    {q(ACTIVITY_STATUS)} as activity_status,
                    {q(ACTIVITY_START_TIME)} as activity_start_time,
                    {q(ACTIVITY_END_TIME)} as activity_end_time,
                    {q(SIGNUP_START_TIME)} as signup_start_time,
                    {q(SIGNUP_END_TIME)} as signup_end_time,
                    {q(ACTIVITY_TAG)} as activity_tag,
                    {q(ACTIVITY_LEVEL)} as activity_level,
                    {q(ACTIVITY_STAGE)} as activity_stage
                from store_activity_calendar_events
                where {q(STORE_ID)} = ?
                  and substr(
                        coalesce(nullif({q(ACTIVITY_START_TIME)}, ''), {q(BUSINESS_DAY)}),
                        1, 10
                      ) <= ?
                  and substr(
                        coalesce(
                            nullif({q(ACTIVITY_END_TIME)}, ''),
                            nullif({q(ACTIVITY_START_TIME)}, ''),
                            {q(BUSINESS_DAY)}
                        ),
                        1, 10
                      ) >= ?
                order by {q(BUSINESS_DAY)}, {q(ACTIVITY_START_TIME)}, {q(ACTIVITY_NAME)}, {q(ACTIVITY_ID)}
                """,
                (store_id, end_date.isoformat(), start_date.isoformat()),
            ).fetchall()
        return [
            StoreActivityCalendarEvent(
                store_id=row["store_id"],
                business_day=date.fromisoformat(row["business_day"]),
                activity_id=row["activity_id"],
                activity_name=row["activity_name"] or "",
                activity_type=row["activity_type"] or "",
                activity_status=row["activity_status"] or "",
                activity_start_time=row["activity_start_time"] or "",
                activity_end_time=row["activity_end_time"] or "",
                signup_start_time=row["signup_start_time"] or "",
                signup_end_time=row["signup_end_time"] or "",
                activity_tag=row["activity_tag"] or "",
                activity_level=row["activity_level"] or "",
                activity_stage=row["activity_stage"] or "",
            )
            for row in rows
        ]

    def list_metric_definitions(self) -> list[MetricDefinition]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                select "指标编码" as metric_code, "指标名称" as metric_name,
                       "指标分类" as metric_group, "单位" as unit,
                       "说明" as description, "确认状态" as confirmation_status,
                       "更新时间" as updated_at
                from metric_definitions
                order by "指标分类", "指标名称"
                """
            ).fetchall()
        return [MetricDefinition(**dict(row)) for row in rows]

    def get_date_bounds(self, store_id: int | None = None) -> tuple[date, date]:
        where_clause = "where \"店铺ID\" = ?" if store_id is not None else ""
        params: tuple[object, ...] = (store_id,) if store_id is not None else ()
        with self._connect() as conn:
            row = conn.execute(
                f"""
                select min("业务日期") as minimum, max("业务日期") as maximum
                from store_daily_overviews
                {where_clause}
                """,
                params,
            ).fetchone()
        if row is None or row["maximum"] is None:
            if store_id is None:
                raise WarehouseDataNotAvailable("No local store daily overview has been ingested.")
            raise WarehouseDataNotAvailable(f"No daily overview has been ingested for store {store_id}.")
        return date.fromisoformat(row["minimum"]), date.fromisoformat(row["maximum"])

    @contextmanager
    def _connect(
        self,
        *,
        initialize: bool = False,
        artifact_table: bool = False,
    ) -> Iterator[sqlite3.Connection]:
        conn = self._database.connect(initialize=initialize)
        try:
            if artifact_table:
                self._ensure_transient_artifact_table(conn)
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _ensure_transient_artifact_table(conn: sqlite3.Connection) -> None:
        conn.execute(
            f"""
            create temp table if not exists raw_response_artifacts (
                {q(ARTIFACT_ID)} text primary key,
                {q(PLATFORM_ID)} integer not null,
                {q(STORE_ID)} integer not null,
                {q(ENDPOINT_KEY)} text not null,
                {q(BUSINESS_DAY)} text not null,
                {q(FETCHED_AT)} text not null,
                {q(HTTP_STATUS)} integer not null,
                {q(RESPONSE_CODE)} integer not null,
                {q(SOURCE_FILE)} text not null,
                {q(CONTENT_SHA256)} text not null unique,
                {q(FILE_SIZE)} integer not null,
                {q(PARSER_VERSION)} text not null,
                {q(CREATED_AT)} text not null
            )
            """
        )

    @staticmethod
    def _ensure_platform(
        conn: sqlite3.Connection,
        code: str,
        name: str,
        now: str,
    ) -> int:
        row = conn.execute(
            f"select {q(PLATFORM_ID)} as platform_id from platforms "
            f"where {q(PLATFORM_CODE)} = ?",
            (code,),
        ).fetchone()
        if row is not None:
            platform_id = int(row["platform_id"])
            conn.execute(
                f"update platforms set {q(PLATFORM_NAME)} = ?, {q(STATUS)} = ?, "
                f"{q(UPDATED_AT)} = ? where {q(PLATFORM_ID)} = ?",
                (name, "active", now, platform_id),
            )
            return platform_id

        row = conn.execute(
            f"select coalesce(max({q(PLATFORM_ID)}), 0) + 1 as next_id from platforms"
        ).fetchone()
        platform_id = int(row["next_id"])
        conn.execute(
            f"insert into platforms ({q(PLATFORM_ID)}, {q(PLATFORM_CODE)}, "
            f"{q(PLATFORM_NAME)}, {q(STATUS)}, {q(CREATED_AT)}, {q(UPDATED_AT)}) "
            "values (?, ?, ?, ?, ?, ?)",
            (platform_id, code, name, "active", now, now),
        )
        return platform_id

    @staticmethod
    def _ensure_store(
        conn: sqlite3.Connection,
        platform_id: int,
        platform_subject_id: str,
        store_name: str,
        now: str,
    ) -> int:
        row = conn.execute(
            f"select {q(STORE_ID)} as store_id from stores "
            f"where {q(PLATFORM_ID)} = ? and {q(STORE_SUBJECT_ID)} = ?",
            (platform_id, platform_subject_id),
        ).fetchone()
        if row is not None:
            store_id = int(row["store_id"])
            conn.execute(
                f"update stores set {q(STORE_NAME)} = ?, {q(STATUS)} = ?, "
                f"{q(UPDATED_AT)} = ? where {q(STORE_ID)} = ?",
                (store_name, "active", now, store_id),
            )
            return store_id

        row = conn.execute(
            f"select coalesce(max({q(STORE_ID)}), 0) + 1 as next_id from stores"
        ).fetchone()
        store_id = int(row["next_id"])
        conn.execute(
            f"insert into stores ({q(STORE_ID)}, {q(PLATFORM_ID)}, "
            f"{q(STORE_SUBJECT_ID)}, {q(STORE_NAME)}, {q(STATUS)}, "
            f"{q(FIRST_SEEN_AT)}, {q(UPDATED_AT)}) values (?, ?, ?, ?, ?, ?, ?)",
            (
                store_id,
                platform_id,
                platform_subject_id,
                store_name,
                "active",
                now,
                now,
            ),
        )
        return store_id

    @staticmethod
    def _seed_metric_definitions(conn: sqlite3.Connection, now: str) -> None:
        definitions = [
            ("payAmt", "支付金额", "交易金额", "元", "平台概览中的支付金额。", "已确认"),
            ("netPaymentAmount", "净支付金额", "交易金额", "元", "扣除退款等口径后的净支付金额。", "已确认"),
            ("payByrCnt", "支付买家数", "交易人数", "人", "发生支付的买家数量。", "已确认"),
            ("uv", "访客数", "流量", "人", "店铺访客数量。", "已确认"),
            ("payRate", "支付转化率", "转化率", "%", "原始值为比例，展示时乘以 100。", "已确认"),
            ("admCostFamtQzt", "全站推广花费", "推广", "元", "截图中的全站推广花费。", "已确认"),
            ("p4pExpendAmt", "关键词推广花费", "推广", "元", "截图中的关键词推广花费。", "已确认"),
            ("cubeAmt", "精准人群推广花费", "推广", "元", "截图中的精准人群推广花费。", "已确认"),
            ("feedCharge", "智能场景花费", "推广", "元", "截图中当前为空，等待更多样本确认。", "待确认"),
            ("tkExpendAmt", "淘宝客佣金", "推广", "元", "截图中的淘宝客佣金。", "已确认"),
            ("subPayOrdAmt", "总支付金额", "交易金额", "元", "截图中的总支付金额。", "已确认"),
            ("payShopRfdAmt", "退款金额（支付时间）", "退款", "元", "按支付时间归因的退款金额。", "已确认"),
            ("payAmtRfdRate", "金额退款率", "退款", "%", "原始值为比例，展示时乘以 100。", "已确认"),
            ("cartByrCnt", "加购人数", "行为", "人", "发生加购的买家数量。", "已确认"),
            ("cltItmCnt", "商品收藏人数", "行为", "人", "收藏商品的用户数量。", "已确认"),
            ("pv", "浏览量", "流量", "次", "店铺页面浏览量。", "已确认"),
            ("stayTime", "平均停留时长", "流量", "秒", "店铺平均停留时长。", "已确认"),
            ("cartItemCnt", "加购件数", "行为", "件", "加入购物车的商品件数。", "已确认"),
            ("payOrdCnt", "支付子订单数", "订单", "笔", "发生支付的子订单数量。", "已确认"),
            ("subPayOrdSubCnt", "总支付子订单数", "订单", "笔", "截图中的总支付子订单数。", "已确认"),
            ("ordRfdRate", "订单退款率", "退款", "%", "原始值为比例，展示时乘以 100。", "已确认"),
            ("payItmCnt", "支付件数", "订单", "件", "支付商品件数。", "已确认"),
            ("payPct", "客单价", "交易金额", "元", "支付金额除以支付买家数的客单价。", "已确认"),
            ("olderPayAmt", "老客复购金额", "复购", "元", "老客产生的复购支付金额。", "已确认"),
            ("payOldByrCnt", "老客复购人数", "复购", "人", "老客复购买家数量。", "已确认"),
            ("hasPurchaseUbyCntRate", "老客复购率", "复购", "%", "原始值为比例，展示时乘以 100。", "已确认"),
            ("rfdFinshDur", "退款处理时长", "退款", "天", "退款处理平均时长。", "已确认"),
            ("wwReplyManualAvgTimeLen", "旺旺人工响应时长", "客服", "秒", "人工客服平均响应时长。", "已确认"),
            ("consultRate", "咨询率", "客服", "%", "原始值为比例，展示时乘以 100。", "已确认"),
            ("disputeDutyRatio", "平台判责率", "售后", "%", "截图有该卡片，但当前样本值为空，等待更多样本确认。", "待确认"),
            ("gotInTime24hRate", "24小时揽收及时率", "物流", "%", "原始值为比例，展示时乘以 100。", "已确认"),
            ("avgSignTimeHh", "物流到货时长", "物流", "小时", "物流平均到货时长。", "已确认"),
            ("rfdSucAmt", "退款金额（完结时间）", "退款", "元", "按退款完结时间归因的退款金额。", "已确认"),
            ("realPayrealRfdRate", "签收退款率", "退款", "%", "已用 2026-07-04 数据概览截图校验，原始值 0.006334459 展示为 0.63%。", "已确认"),
            ("sucRefundRate", "成功退款率", "退款", "%", "成功退款订单/退款成功口径，和数据概览卡片的签收退款率不是同一字段。", "已确认"),
            ("flow.uv", "访客数", "流量总览", "人", "流量看板-流量总览中的访问店铺访客数。", "已确认"),
            ("flow.itmUv", "商品访客数", "流量总览", "人", "流量看板-流量总览中的访问商品访客数。", "已确认"),
            ("flow.payByrCnt", "支付买家数", "流量总览", "人", "流量看板-流量总览中的支付买家数。", "已确认"),
            ("flow.pv", "浏览量", "流量总览", "次", "流量看板-流量总览中的页面浏览量。", "已确认"),
            ("flow.avgPv", "人均浏览量", "流量总览", "次/人", "流量看板-流量总览中的人均浏览量。", "已确认"),
            ("flow.stayTime", "平均停留时长", "流量总览", "秒", "流量看板-流量总览中的平均停留时长；若该接口缺失，可从首页概览 stayTime 兜底展示。", "待确认"),
            ("flow.bounceRate", "跳失率", "流量总览", "%", "流量看板-流量总览中的跳失率，等待实际响应字段最终确认。", "待确认"),
            ("flow.bounceUvRate", "跳失率", "流量总览", "%", "跳失率可能字段，等待实际响应字段最终确认。", "待确认"),
            ("flow.bounceRate1d", "跳失率", "流量总览", "%", "跳失率可能字段，等待实际响应字段最终确认。", "待确认"),
            ("flow.bounceUvRate1d", "跳失率", "流量总览", "%", "跳失率可能字段，等待实际响应字段最终确认。", "待确认"),
            ("flow.avgBounceUvRate", "跳失率", "流量总览", "%", "跳失率可能字段，等待实际响应字段最终确认。", "待确认"),
            ("flow.bounce_uv_rate_1d_002", "跳失率", "流量总览", "%", "从指标元数据中发现的跳失率字段名，等待数值接口确认。", "待确认"),
            ("flow.stayTimeLen", "平均停留时长", "流量总览", "秒", "平均停留时长可能字段，等待实际响应字段最终确认。", "待确认"),
            ("flow.stay_time_len_1d_001", "平均停留时长", "流量总览", "秒", "从指标元数据中发现的平均停留时长字段名，等待数值接口确认。", "待确认"),
            ("flow.oldUv", "老访客数", "流量总览", "人", "流量看板-流量总览中的老访客数。", "已确认"),
            ("flow.newUv", "新访客数", "流量总览", "人", "流量看板-流量总览中的新访客数。", "已确认"),
            ("flow.shopCltByrCnt", "关注店铺人数", "流量总览", "人", "流量看板-流量总览中的关注店铺人数。", "已确认"),
            ("flow.liveRoomUv", "直播间访客数", "流量总览", "人", "流量看板-流量总览中的直播间访客数。", "已确认"),
            ("flow.shortVideoUv", "短视频访客数", "流量总览", "人", "流量看板-流量总览中的短视频访客数。", "已确认"),
            ("flow.imageUv", "图文访客数", "流量总览", "人", "流量看板-流量总览中的图文访客数。", "已确认"),
            ("flow.shopVisitUv", "店铺页访客数", "流量总览", "人", "流量看板-流量总览中的店铺页访客数。", "已确认"),
            ("flow.cartByrCnt", "加购人数", "流量总览", "人", "流量总览响应中的加购人数。", "已确认"),
            ("flow.payAmt", "支付金额", "流量总览", "元", "流量总览响应中的支付金额。", "已确认"),
            ("flow.payRate", "支付转化率", "流量总览", "%", "流量总览响应中的支付转化率，原始值为比例。", "已确认"),
            ("flow.payPct", "客单价", "流量总览", "元", "流量总览响应中的客单价。", "已确认"),
            ("flow.uvValue", "访客价值", "流量总览", "元/人", "流量总览响应中的访客价值。", "已确认"),
            ("flow.itmPv", "商品浏览量", "流量总览", "次", "流量总览响应中的商品浏览量。", "已确认"),
            ("flow.miniDetailUv", "微详情访客数", "流量总览", "人", "流量总览响应中的微详情访客数。", "已确认"),
            ("flow.cltCnt", "收藏人数", "流量总览", "人", "流量总览响应中的收藏人数。", "已确认"),
            ("flow.itmCltByrCnt", "商品收藏人数", "流量总览", "人", "流量总览响应中的商品收藏人数。", "已确认"),
            ("flow.itmAvgPv", "商品人均浏览量", "流量总览", "次/人", "流量总览响应中的商品人均浏览量。", "已确认"),
            ("flow.crtByrCnt", "下单买家数", "流量总览", "人", "流量总览响应中的下单买家数。", "已确认"),
            ("flow.crtRate", "下单转化率", "流量总览", "%", "流量总览响应中的下单转化率，原始值为比例。", "已确认"),
            ("customer.shopCustomer", "店铺客户数", "客户概况", "人", "统计时间内，店铺访客、有互动行为客户、支付买家的去重人数。", "已确认"),
            ("customer.newVisitorCnt", "客户新访", "客户概况-新访", "人", "统计时间内，首次与店铺产生访问、互动、支付行为的人数。", "已确认"),
            ("customer.newVisitorBuyCnt", "新访成交", "客户概况-新访", "人", "首次产生访问或互动行为，且当天产生支付行为的客户。", "已确认"),
            ("customer.newVisitorInShopCnt", "新访未成交", "客户概况-新访", "人", "首次产生访问或互动行为，但当天未产生支付行为的客户。", "已确认"),
            ("customer.newVisitorPayRate", "新访支付转化率", "客户概况-新访", "%", "新访成交人数/客户新访人数，原始值为比例。", "已确认"),
            ("customer.newVisitorPayAmtRatio", "新访支付金额占比", "客户概况-新访", "%", "新访成交金额/全店支付金额，原始值为比例。", "已确认"),
            ("customer.newVisitorPct", "新访客单价", "客户概况-新访", "元", "新访成交金额/新访成交人数。", "已确认"),
            ("customer.newVisitorFansRate", "新访粉丝占比", "客户概况-新访", "%", "客户新访中的粉丝占比，原始值为比例。", "已确认"),
            ("customer.newVisitorVipRate", "新访会员占比", "客户概况-新访", "%", "客户新访中的会员占比，原始值为比例。", "已确认"),
            ("customer.newVisitorReCall", "新访潜客召回率", "客户概况-新访", "%", "客户新访中潜在客户人数/潜在客户人数，原始值为比例。", "已确认"),
            ("customer.noPurchaseCnt", "未购客户回访", "客户概况-未购回访", "人", "未购客户中，在统计时间内再次与店铺产生访问、互动、支付行为的人数。", "已确认"),
            ("customer.noPurchaseBuyCnt", "回访成交", "客户概况-未购回访", "人", "之前产生过访问或互动行为的未购客户中，在统计时间内产生支付行为的人数。", "已确认"),
            ("customer.noBuyInShopCnt", "回访未成交", "客户概况-未购回访", "人", "之前产生过访问或互动行为的未购客户中，再次产生访问或互动但未支付的人数。", "已确认"),
            ("customer.noPurchasePayRate", "未购回访支付转化率", "客户概况-未购回访", "%", "回访成交人数/未购客户回访人数，原始值为比例。", "已确认"),
            ("customer.noPurchasePayAmtRatio", "未购回访支付金额占比", "客户概况-未购回访", "%", "回访成交金额/全店支付金额，原始值为比例。", "已确认"),
            ("customer.noPurchasePct", "未购回访客单价", "客户概况-未购回访", "元", "回访成交金额/回访成交人数。", "已确认"),
            ("customer.noPurchaseFansRate", "未购回访粉丝占比", "客户概况-未购回访", "%", "未购客户回访中的粉丝占比，原始值为比例。", "已确认"),
            ("customer.noPurchaseVipRate", "未购回访会员占比", "客户概况-未购回访", "%", "未购客户回访中的会员占比，原始值为比例。", "已确认"),
            ("customer.noPurchaseReCall", "未购客户召回率", "客户概况-未购回访", "%", "未购客户回访人数/未购客户人数，原始值为比例。", "已确认"),
            ("customer.noPurchaseBuyCntRate", "未购回访成交率", "客户概况-未购回访", "%", "未购客户回访召回率*支付转化率，原始值为比例。", "已确认"),
            ("customer.hasPurchaseCnt", "已购客户回访", "客户概况-已购回访", "人", "过去365天内买过的客户中，在统计时间内再次与店铺产生访问、互动、支付行为的人数。", "已确认"),
            ("customer.hasPurchaseUbyCnt", "老客复购", "客户概况-已购回访", "人", "过去365天内买过的客户中，在统计时间内再次产生支付行为的人数。", "已确认"),
            ("customer.hasBuyInShopCnt", "老客未复购", "客户概况-已购回访", "人", "过去365天内买过的客户中，在统计时间内访问或互动但未再次支付的人数。", "已确认"),
            ("customer.hasPurchasePayRate", "已购回访支付转化率", "客户概况-已购回访", "%", "老客复购人数/已购客户回访人数，原始值为比例。", "已确认"),
            ("customer.hasPurchasePayAmtRatio", "已购回访支付金额占比", "客户概况-已购回访", "%", "老客复购金额/全店支付金额，原始值为比例。", "已确认"),
            ("customer.hasPurchasePct", "老客复购客单价", "客户概况-已购回访", "元", "老客复购金额/老客复购人数。", "已确认"),
            ("customer.hasPurchaseFansRate", "已购回访粉丝占比", "客户概况-已购回访", "%", "已购客户回访中的粉丝占比，原始值为比例。", "已确认"),
            ("customer.hasPurchaseVipRate", "已购回访会员占比", "客户概况-已购回访", "%", "已购客户回访中的会员占比，原始值为比例。", "已确认"),
            ("customer.hasPurchaseReCall", "已购客户召回率", "客户概况-已购回访", "%", "已购客户回访人数/已购客户人数，原始值为比例。", "已确认"),
            ("customer.hasPurchaseUbyCntRate", "老客复购率", "客户概况-已购回访", "%", "老客复购人数/老客数，原始值为比例。", "已确认"),
            ("member.core.totalMbrCnt", "会员总数", "会员分析-核心指标", "人", "当前生效的全部会员关系。", "已确认"),
            ("member.core.paidMbrCnt", "会员成交人数", "会员分析-核心指标", "人", "统计周期内，完成店铺订单支付的去重会员人数。", "已确认"),
            ("member.core.mbrPayAmt", "会员成交金额", "会员分析-核心指标", "元", "统计周期内会员成交金额汇总。", "已确认"),
            ("member.core.mbrUnitPrice", "会员客单价", "会员分析-核心指标", "元", "会员成交金额/会员成交人数。", "已确认"),
            ("member.core.repurMbrRate", "会员复购率", "会员分析-核心指标", "%", "会员复购率，原始值为比例。", "已确认"),
            ("member.asset.highFreqBuyerMemberAssets", "高频复购会员", "会员分析-资产分布", "人", "高频复购会员资产数。", "已确认"),
            ("member.asset.highFreqBuyerMemberPayAmtRate", "高频复购成交金额占比", "会员分析-资产分布", "%", "高频复购会员支付金额占比，原始值为比例。", "已确认"),
            ("member.asset.highFreqBuyerMemberAssetsPortion", "高频复购本店占比", "会员分析-资产分布", "%", "高频复购会员资产数本店占比，原始值为比例。", "已确认"),
            ("member.asset.highFreqBuyerMemberAssetsRatio", "高频复购同行占比", "会员分析-资产分布", "%", "高频复购会员资产数同行同层优秀占比，原始值为比例。", "已确认"),
            ("member.asset.twoOrderBuyerMemberAssets", "2单复购会员", "会员分析-资产分布", "人", "2单复购会员资产数。", "已确认"),
            ("member.asset.twoOrderBuyerMemberPayAmtRate", "2单复购成交金额占比", "会员分析-资产分布", "%", "2单复购会员支付金额占比，原始值为比例。", "已确认"),
            ("member.asset.twoOrderBuyerMemberAssetsPortion", "2单复购本店占比", "会员分析-资产分布", "%", "2单复购会员资产数本店占比，原始值为比例。", "已确认"),
            ("member.asset.twoOrderBuyerMemberAssetsRatio", "2单复购同行占比", "会员分析-资产分布", "%", "2单复购会员资产数同行同层优秀占比，原始值为比例。", "已确认"),
            ("member.asset.firstTimeBuyerMemberAssets", "首购会员", "会员分析-资产分布", "人", "首购会员资产数。", "已确认"),
            ("member.asset.firstTimeBuyerMemberPayAmtRate", "首购成交金额占比", "会员分析-资产分布", "%", "首购会员支付金额占比，原始值为比例。", "已确认"),
            ("member.asset.firstTimeBuyerMemberAssetsPortion", "首购本店占比", "会员分析-资产分布", "%", "首购会员资产数本店占比，原始值为比例。", "已确认"),
            ("member.asset.firstTimeBuyerMemberLyrAssetsRatio", "首购同行占比", "会员分析-资产分布", "%", "首购会员资产数同行同层优秀占比，原始值为比例。", "已确认"),
            ("member.asset.activeNonBuyerMemberAssets", "活跃未购会员", "会员分析-资产分布", "人", "活跃未购会员资产数。", "已确认"),
            ("member.asset.activeNonBuyerMemberAssetsPortion", "活跃未购本店占比", "会员分析-资产分布", "%", "活跃未购会员资产数本店占比，原始值为比例。", "已确认"),
            ("member.asset.activeNonBuyerMemberLyrAssetsRatio", "活跃未购同行占比", "会员分析-资产分布", "%", "活跃未购会员资产数同行同层优秀占比，原始值为比例。", "已确认"),
            ("member.asset.inactiveMemberAssets", "沉默会员", "会员分析-资产分布", "人", "沉默会员资产数。", "已确认"),
            ("member.asset.inactiveMemberAssetsPortion", "沉默会员本店占比", "会员分析-资产分布", "%", "沉默会员资产数本店占比，原始值为比例。", "已确认"),
            ("member.asset.inactiveMemberLyrAssetsRatio", "沉默会员同行占比", "会员分析-资产分布", "%", "沉默会员资产数同行同层优秀占比，原始值为比例。", "已确认"),
            ("member.repurchase.repurMbrCnt", "复购会员数", "会员分析-会员复购", "人", "统计周期内再次产生购买的会员数。", "已确认"),
            ("member.repurchase.repurPayAmt", "会员复购金额", "会员分析-会员复购", "元", "统计周期内会员复购订单总金额。", "已确认"),
            ("member.repurchase.repurOrdCnt", "复购订单数", "会员分析-会员复购", "笔", "统计周期内会员复购子订单数。", "已确认"),
            ("member.repurchase.repurUnitPrice", "复购会员客单价", "会员分析-会员复购", "元", "会员复购金额/复购会员数。", "已确认"),
            ("member.repurchase.repurCycle", "复购周期", "会员分析-会员复购", "天", "复购会员最近一笔订单距上一笔订单日期的平均值。", "已确认"),
            ("member.repurchase.repurMbrRate", "复购页会员复购率", "会员分析-会员复购", "%", "复购页会员复购率，原始值为比例。", "已确认"),
            ("member.repurchase.repurFrequency", "人均复购笔数", "会员分析-会员复购", "笔/人", "复购订单数/复购会员数。", "已确认"),
            ("member.acquisition.incrMbrCnt", "新增会员数", "会员分析-会员拉新", "人", "统计周期内通过各招募渠道新增入会的去重会员数。", "已确认"),
            ("member.acquisition.incrPaidMbrCnt", "新会员成交人数", "会员分析-会员拉新", "人", "统计周期内新增入会会员中完成成交的去重人数。", "已确认"),
            ("member.acquisition.recConvertRate", "招募转化率", "会员分析-会员拉新", "%", "新会员成交人数/新增会员数，原始值为比例。", "已确认"),
            ("member.acquisition.incrPayOrdAmt", "新会员成交金额", "会员分析-会员拉新", "元", "新增入会会员完成成交的订单总金额。", "已确认"),
            ("member.acquisition.incrUnitPrice", "新会员客单价", "会员分析-会员拉新", "元", "新会员成交金额/新会员成交人数。", "已确认"),
            ("member.acquisition.oldNewMemberCount", "老客入会人数", "会员分析-会员拉新", "人", "老客新增入会人数。", "已确认"),
        ]
        conn.executemany(
            """
            insert into metric_definitions (
                "指标编码", "指标名称", "指标分类", "单位",
                "说明", "确认状态", "更新时间"
            ) values (?, ?, ?, ?, ?, ?, ?)
            on conflict("指标编码") do update set
                "指标名称" = excluded."指标名称",
                "指标分类" = excluded."指标分类",
                "单位" = excluded."单位",
                "说明" = excluded."说明",
                "确认状态" = excluded."确认状态",
                "更新时间" = excluded."更新时间"
            """,
            [(*item, now) for item in definitions],
        )
        conn.commit()

    @staticmethod
    def _decimal(value: object) -> str:
        return str(value if isinstance(value, Decimal) else Decimal(str(value or 0)))

    @staticmethod
    def _optional_decimal(value: object) -> str | None:
        if value is None:
            return None
        return str(value if isinstance(value, Decimal) else Decimal(str(value)))

    @staticmethod
    def _traffic_source_insert_rows(
        rows: list[object],
        store_id: int,
        business_day: str,
    ) -> list[tuple[object, ...]]:
        grouped: dict[tuple[str, str, str, int], dict[str, Decimal | int]] = {}
        for row in rows:
            key = (row.level1, row.level2, row.level3, row.source_level)
            bucket = grouped.setdefault(
                key,
                {
                    "order": row.row_order,
                    "visitors": Decimal("0"),
                    "new_visitors": Decimal("0"),
                    "cart_buyers": Decimal("0"),
                    "product_favorite_buyers": Decimal("0"),
                    "paid_buyers": Decimal("0"),
                    "paid_amount": Decimal("0"),
                    "paid_amount_share": Decimal("0"),
                    "order_buyers": Decimal("0"),
                    "order_amount": Decimal("0"),
                },
            )
            bucket["order"] = min(int(bucket["order"]), row.row_order)
            for metric in (
                "visitors",
                "new_visitors",
                "cart_buyers",
                "product_favorite_buyers",
                "paid_buyers",
                "paid_amount",
                "paid_amount_share",
                "order_buyers",
                "order_amount",
            ):
                bucket[metric] = Decimal(str(bucket[metric])) + Decimal(str(getattr(row, metric)))

        insert_rows: list[tuple[object, ...]] = []
        for (level1, level2, level3, source_level), metrics in sorted(
            grouped.items(),
            key=lambda item: int(item[1]["order"]),
        ):
            visitors = Decimal(str(metrics["visitors"]))
            paid_buyers = Decimal(str(metrics["paid_buyers"]))
            paid_amount = Decimal(str(metrics["paid_amount"]))
            order_buyers = Decimal(str(metrics["order_buyers"]))
            insert_rows.append(
                (
                    store_id,
                    business_day,
                    level1,
                    level2,
                    level3,
                    source_level,
                    WarehouseStore._decimal(visitors),
                    WarehouseStore._decimal(metrics["new_visitors"]),
                    WarehouseStore._decimal(metrics["cart_buyers"]),
                    WarehouseStore._decimal(metrics["product_favorite_buyers"]),
                    WarehouseStore._decimal(paid_buyers),
                    WarehouseStore._decimal(WarehouseStore._ratio(paid_buyers, visitors)),
                    WarehouseStore._decimal(paid_amount),
                    WarehouseStore._decimal(metrics["paid_amount_share"]),
                    WarehouseStore._decimal(WarehouseStore._ratio(paid_amount, visitors)),
                    WarehouseStore._decimal(order_buyers),
                    WarehouseStore._decimal(metrics["order_amount"]),
                    WarehouseStore._decimal(WarehouseStore._ratio(order_buyers, visitors)),
                )
            )
        return insert_rows

    @staticmethod
    def _ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
        return numerator / denominator if denominator else Decimal("0")

    @staticmethod
    def _daily_overview_metric_values(metrics: list[object]) -> dict[str, str | None]:
        by_code = {
            metric.code: metric.numeric_value
            for metric in metrics
            if getattr(metric, "scope", None) == "self"
        }
        return {
            column: WarehouseStore._optional_decimal(by_code.get(code))
            for column, code in DAILY_OVERVIEW_FIELDS
        }

    @staticmethod
    def _resolve_artifact_id(
        conn: sqlite3.Connection,
        content_sha256: str,
        fallback: str,
    ) -> str:
        row = conn.execute(
            f"select {q(ARTIFACT_ID)} as artifact_id from raw_response_artifacts "
            f"where {q(CONTENT_SHA256)} = ?",
            (content_sha256,),
        ).fetchone()
        if row is None:
            return fallback
        return str(row["artifact_id"])

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")
