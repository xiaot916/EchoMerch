from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from app.core.local_database import (
    BRAND_ASSET_DIMENSION_TABLE,
    BRAND_ASSET_METRICS_TABLE,
    BRAND_ASSET_FLOW_TABLE,
    BRAND_ASSET_OVERVIEW_TABLE,
    BRAND_ASSET_STAGE_TABLE,
    BRAND_BENCHMARK_TABLE,
    BRAND_ACTIVITY_TABLE,
    BRAND_CONSUMER_COUNT,
    BRAND_CONSUMER_SHARE,
    BRAND_CONVERSION_RATE,
    BRAND_DIMENSION_CODE,
    BRAND_DIMENSION_NAME,
    BRAND_DIMENSION_TYPE,
    BRAND_ID,
    BRAND_NAME,
    BRAND_PRODUCT_ASSET_CONSUMERS,
    BRAND_PRODUCT_CATEGORY,
    BRAND_PRODUCT_CONTRIBUTION_RATE,
    BRAND_PRODUCT_DAILY_TABLE,
    BRAND_PRODUCT_DIMENSION_TABLE,
    BRAND_PRODUCT_ID,
    BRAND_PRODUCT_LAUNCH_DATE,
    BRAND_PRODUCT_LINE,
    BRAND_PRODUCT_NAME,
    BRAND_PRODUCT_NEW_ASSET_CONSUMERS,
    BRAND_PRODUCT_POSITIONING,
    BRAND_PRODUCT_SERIES,
    BRAND_PRODUCT_SPU_ID,
    BRAND_PRODUCT_STATUS,
    BRAND_PRODUCT_TABLE,
    BRAND_STATUS,
    BRAND_STORE_SCOPE_TABLE,
    BRAND_SUBJECT_ID,
    BRAND_TRANSACTION_AMOUNT,
    BRAND_TRANSACTION_BUYER_COUNT,
    BUSINESS_DAY,
    LocalDatabase,
    STORE_ID,
    q,
)
from app.modules.access.service import AccessDenied, Principal
from app.modules.brand_assets.schemas import (
    BrandAssetSummary,
    BrandDatasetStatus,
    BrandProductAnalysis,
    BrandProductRecord,
    BrandRecord,
)


class BrandNotFound(LookupError):
    pass


class BrandAssetService:
    DATASETS = (
        ("overview", "消费者资产概览", BRAND_ASSET_OVERVIEW_TABLE, BUSINESS_DAY),
        ("stages", "消费者资产分层", BRAND_ASSET_STAGE_TABLE, BUSINESS_DAY),
        ("dimensions", "消费者资产维度", BRAND_ASSET_DIMENSION_TABLE, BUSINESS_DAY),
        ("metrics", "AIPL 日指标与行业对比", BRAND_ASSET_METRICS_TABLE, BUSINESS_DAY),
        ("flows", "消费者生命周期流转", BRAND_ASSET_FLOW_TABLE, BUSINESS_DAY),
        ("benchmarks", "行业竞争对标", BRAND_BENCHMARK_TABLE, "统计结束日期"),
        ("activities", "活动资产表现", BRAND_ACTIVITY_TABLE, "活动结束时间"),
        ("product_assets", "单品资产分析", BRAND_PRODUCT_DAILY_TABLE, BUSINESS_DAY),
        ("product_dimensions", "单品渠道与人群", BRAND_PRODUCT_DIMENSION_TABLE, BUSINESS_DAY),
    )

    def __init__(self, database_path: Path) -> None:
        self._database = LocalDatabase(database_path)

    def list_brands(self, principal: Principal) -> list[BrandRecord]:
        conn = self._database.connect()
        try:
            params: list[str] = []
            where = ""
            if principal.brand_ids is not None:
                if not principal.brand_ids:
                    return []
                placeholders = ",".join("?" for _ in principal.brand_ids)
                where = f"where b.{q(BRAND_ID)} in ({placeholders})"
                params.extend(sorted(principal.brand_ids))
            scope_exists = LocalDatabase._table_exists(conn, BRAND_STORE_SCOPE_TABLE)
            scope_select = (
                f"group_concat(scope.{q(STORE_ID)}) as store_ids"
                if scope_exists
                else "null as store_ids"
            )
            scope_join = (
                f"left join {q(BRAND_STORE_SCOPE_TABLE)} scope "
                f"on scope.{q(BRAND_ID)} = b.{q(BRAND_ID)}"
                if scope_exists
                else ""
            )
            rows = conn.execute(
                f"""
                select b.{q(BRAND_ID)}, b.{q(BRAND_SUBJECT_ID)}, b.{q(BRAND_NAME)}, b.{q(BRAND_STATUS)},
                       {scope_select}
                from brands b
                {scope_join}
                {where}
                group by b.{q(BRAND_ID)}, b.{q(BRAND_SUBJECT_ID)}, b.{q(BRAND_NAME)}, b.{q(BRAND_STATUS)}
                order by b.{q(BRAND_NAME)} collate nocase
                """,
                params,
            ).fetchall()
            return [
                BrandRecord(
                    brand_id=str(row[BRAND_ID]),
                    brand_subject_id=str(row[BRAND_SUBJECT_ID]),
                    brand_name=str(row[BRAND_NAME]),
                    status=str(row[BRAND_STATUS]),
                    store_ids=[int(value) for value in str(row["store_ids"]).split(",") if value] if row["store_ids"] else [],
                )
                for row in rows
            ]
        finally:
            conn.close()

    def get_summary(
        self,
        principal: Principal,
        *,
        brand_id: str | None,
        start_date: date | None,
        end_date: date | None,
    ) -> BrandAssetSummary:
        resolved_id = self._resolve_brand(principal, brand_id)
        brands = {brand.brand_id: brand for brand in self.list_brands(principal)}
        brand = brands.get(resolved_id)
        if brand is None:
            raise BrandNotFound("品牌不存在或当前账号没有该品牌权限。")
        if start_date and end_date and start_date > end_date:
            raise ValueError("开始日期不能晚于结束日期。")
        conn = self._database.connect()
        try:
            overview_rows = self._query_rows(
                conn, BRAND_ASSET_OVERVIEW_TABLE, resolved_id, start_date, end_date,
                order_by=f"{q(BUSINESS_DAY)} desc",
            )
            stage_rows = self._query_rows(
                conn, BRAND_ASSET_STAGE_TABLE, resolved_id, start_date, end_date,
                order_by=f"{q(BUSINESS_DAY)} desc, {q('消费者数')} desc",
                limit=100,
            )
            dimension_rows = self._query_rows(
                conn, BRAND_ASSET_DIMENSION_TABLE, resolved_id, start_date, end_date,
                order_by=f"{q(BUSINESS_DAY)} desc, {q('成交金额')} desc",
                limit=100,
            )
            metric_rows = self._query_rows(
                conn, BRAND_ASSET_METRICS_TABLE, resolved_id, start_date, end_date,
                order_by=f"{q(BUSINESS_DAY)} desc, {q(BRAND_DIMENSION_TYPE)}, {q(BRAND_DIMENSION_CODE)}",
                limit=200,
            ) if LocalDatabase._table_exists(conn, BRAND_ASSET_METRICS_TABLE) else []
            datasets = [
                self._dataset_status(conn, resolved_id, key, label, table, date_column)
                for key, label, table, date_column in self.DATASETS
            ]
        finally:
            conn.close()
        latest_day = str(overview_rows[0][BUSINESS_DAY]) if overview_rows else None
        latest_stage_day = str(stage_rows[0][BUSINESS_DAY]) if stage_rows else None
        latest_dimension_day = str(dimension_rows[0][BUSINESS_DAY]) if dimension_rows else None
        return BrandAssetSummary(
            brand=brand,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            latest_day=latest_day,
            data_status="available" if any((overview_rows, stage_rows, dimension_rows, metric_rows)) else "not_imported",
            overview={str(key): self._text(value) for key, value in (dict(overview_rows[0]).items() if overview_rows else [])},
            overview_trend=[
                {str(key): self._text(value) for key, value in dict(row).items()}
                for row in reversed(overview_rows)
            ],
            stages=[
                {str(key): self._text(value) for key, value in dict(row).items()}
                for row in stage_rows
                if str(row[BUSINESS_DAY]) == latest_stage_day
            ],
            dimensions=[
                {str(key): self._text(value) for key, value in dict(row).items()}
                for row in dimension_rows
                if str(row[BUSINESS_DAY]) == latest_dimension_day
            ],
            metrics=[{str(key): self._text(value) for key, value in dict(row).items()} for row in metric_rows],
            datasets=datasets,
        )

    def list_products(self, principal: Principal, *, brand_id: str | None) -> list[BrandProductRecord]:
        allowed_brand_ids = self._resolve_product_brand_scope(principal, brand_id)
        if allowed_brand_ids == []:
            return []
        where_sql = ""
        params: list[object] = []
        if allowed_brand_ids is not None:
            placeholders = ",".join("?" for _ in allowed_brand_ids)
            where_sql = f"where product.{q(BRAND_ID)} in ({placeholders})"
            params.extend(allowed_brand_ids)
        conn = self._database.connect()
        try:
            if not LocalDatabase._table_exists(conn, BRAND_PRODUCT_TABLE):
                return []
            daily_exists = LocalDatabase._table_exists(conn, BRAND_PRODUCT_DAILY_TABLE)
            fact_select = (
                f"count(fact.{q(BUSINESS_DAY)}) as row_count, "
                f"min(fact.{q(BUSINESS_DAY)}) as min_day, "
                f"max(fact.{q(BUSINESS_DAY)}) as max_day"
                if daily_exists
                else "0 as row_count, null as min_day, null as max_day"
            )
            fact_join = (
                f"left join {q(BRAND_PRODUCT_DAILY_TABLE)} fact "
                f"on fact.{q(BRAND_ID)} = product.{q(BRAND_ID)} "
                f"and fact.{q(BRAND_PRODUCT_ID)} = product.{q(BRAND_PRODUCT_ID)}"
                if daily_exists
                else ""
            )
            rows = conn.execute(
                f"""
                select product.*,
                       {fact_select}
                from {q(BRAND_PRODUCT_TABLE)} product
                {fact_join}
                {where_sql}
                group by product.{q(BRAND_ID)}, product.{q(BRAND_PRODUCT_ID)}
                order by product.{q(BRAND_PRODUCT_SERIES)} collate nocase,
                         product.{q(BRAND_PRODUCT_ID)} collate nocase
                """,
                params,
            ).fetchall()
            return [self._product_record(row) for row in rows]
        finally:
            conn.close()

    def get_product_analysis(
        self,
        principal: Principal,
        *,
        brand_id: str | None,
        product_id: str,
        start_date: date | None,
        end_date: date | None,
    ) -> BrandProductAnalysis:
        if start_date and end_date and start_date > end_date:
            raise ValueError("开始日期不能晚于结束日期。")
        products = [item for item in self.list_products(principal, brand_id=brand_id) if item.product_id == product_id]
        if not products:
            raise BrandNotFound("商品不存在或当前账号没有该商品权限。")
        if len(products) > 1:
            raise ValueError(f"商品 ID {product_id} 对应多个商品主体，无法按商品 ID 唯一分析。")
        product = products[0]
        resolved_id = product.brand_id
        brands = {brand.brand_id: brand for brand in self.list_brands(principal)}
        brand = brands.get(resolved_id)
        if brand is None:
            raise BrandNotFound("商品所属数据主体不存在或当前账号无权访问。")

        peer_brand_ids = self._resolve_product_brand_scope(principal, brand_id)
        peer_scope_sql = ""
        peer_scope_params: list[object] = []
        if peer_brand_ids is not None:
            placeholders = ",".join("?" for _ in peer_brand_ids)
            peer_scope_sql = f"and catalog.{q(BRAND_ID)} in ({placeholders})"
            peer_scope_params.extend(peer_brand_ids)

        conn = self._database.connect()
        try:
            trend_rows = self._query_product_rows(
                conn,
                BRAND_PRODUCT_DAILY_TABLE,
                resolved_id,
                product_id,
                start_date,
                end_date,
            )
            dimension_rows = self._query_product_rows(
                conn,
                BRAND_PRODUCT_DIMENSION_TABLE,
                resolved_id,
                product_id,
                start_date,
                end_date,
            )
            peer_rows = conn.execute(
                f"""
                select catalog.*, fact.*
                from {q(BRAND_PRODUCT_TABLE)} catalog
                left join {q(BRAND_PRODUCT_DAILY_TABLE)} fact
                  on fact.{q(BRAND_ID)} = catalog.{q(BRAND_ID)}
                 and fact.{q(BRAND_PRODUCT_ID)} = catalog.{q(BRAND_PRODUCT_ID)}
                where 1 = 1
                  {peer_scope_sql}
                  and ((? is null and catalog.{q(BRAND_PRODUCT_SERIES)} is null)
                       or catalog.{q(BRAND_PRODUCT_SERIES)} = ?)
                  and (? is null or fact.{q(BUSINESS_DAY)} >= ?)
                  and (? is null or fact.{q(BUSINESS_DAY)} <= ?)
                order by catalog.{q(BRAND_PRODUCT_ID)}, fact.{q(BUSINESS_DAY)}
                """,
                (
                    *peer_scope_params,
                    product.series,
                    product.series,
                    start_date.isoformat() if start_date else None,
                    start_date.isoformat() if start_date else None,
                    end_date.isoformat() if end_date else None,
                    end_date.isoformat() if end_date else None,
                ),
            ).fetchall()
        finally:
            conn.close()

        latest = dict(trend_rows[-1]) if trend_rows else {}
        return BrandProductAnalysis(
            brand=brand,
            product=product,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            latest_day=self._text(latest.get(BUSINESS_DAY)),
            data_status="available" if trend_rows else "not_imported",
            latest_metrics={str(key): self._text(value) for key, value in latest.items()},
            period_metrics=self._period_product_metrics(trend_rows),
            trend=[{str(key): self._text(value) for key, value in dict(row).items()} for row in trend_rows],
            dimensions=self._aggregate_product_dimensions(dimension_rows),
            peers=self._aggregate_product_peers(peer_rows),
        )

    @staticmethod
    def _text(value: object) -> str | None:
        return None if value is None else str(value)

    @staticmethod
    def _resolve_brand(principal: Principal, brand_id: str | None) -> str:
        try:
            resolved = principal.resolve_brand_id(brand_id)
        except AccessDenied:
            raise
        if resolved is None:
            raise ValueError("请先选择品牌后再查看品牌资产。")
        return resolved

    @staticmethod
    def _resolve_product_brand_scope(principal: Principal, brand_id: str | None) -> list[str] | None:
        if brand_id is not None:
            resolved = principal.resolve_brand_id(brand_id)
            if resolved is None:
                raise ValueError("指定的数据主体无效。")
            return [resolved]
        if principal.brand_ids is None:
            return None
        return sorted(principal.brand_ids)

    @staticmethod
    def _query_rows(
        conn: sqlite3.Connection,
        table: str,
        brand_id: str,
        start_date: date | None,
        end_date: date | None,
        *,
        order_by: str,
        limit: int | None = None,
    ) -> list[sqlite3.Row]:
        conditions = [f'{q(BRAND_ID)} = ?']
        params: list[object] = [brand_id]
        if start_date:
            conditions.append(f'{q(BUSINESS_DAY)} >= ?')
            params.append(start_date.isoformat())
        if end_date:
            conditions.append(f'{q(BUSINESS_DAY)} <= ?')
            params.append(end_date.isoformat())
        limit_sql = f" limit {limit}" if limit else ""
        return conn.execute(
            f"select * from {q(table)} where {' and '.join(conditions)} order by {order_by}{limit_sql}",
            params,
        ).fetchall()

    @staticmethod
    def _query_product_rows(
        conn: sqlite3.Connection,
        table: str,
        brand_id: str,
        product_id: str,
        start_date: date | None,
        end_date: date | None,
    ) -> list[sqlite3.Row]:
        conditions = [f'{q(BRAND_ID)} = ?', f'{q(BRAND_PRODUCT_ID)} = ?']
        params: list[object] = [brand_id, product_id]
        if start_date:
            conditions.append(f'{q(BUSINESS_DAY)} >= ?')
            params.append(start_date.isoformat())
        if end_date:
            conditions.append(f'{q(BUSINESS_DAY)} <= ?')
            params.append(end_date.isoformat())
        return conn.execute(
            f"select * from {q(table)} where {' and '.join(conditions)} order by {q(BUSINESS_DAY)}",
            params,
        ).fetchall()

    @staticmethod
    def _number(value: object) -> float:
        if value in (None, "", "--"):
            return 0.0
        try:
            return float(str(value).replace(",", "").replace("%", ""))
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _period_product_metrics(cls, rows: list[sqlite3.Row]) -> dict[str, float]:
        flow_columns = (
            BRAND_PRODUCT_NEW_ASSET_CONSUMERS,
            BRAND_TRANSACTION_BUYER_COUNT,
            BRAND_TRANSACTION_AMOUNT,
        )
        return {column: sum(cls._number(row[column]) for row in rows) for column in flow_columns}

    @classmethod
    def _aggregate_product_dimensions(cls, rows: list[sqlite3.Row]) -> list[dict[str, str | float | None]]:
        grouped: dict[tuple[str, str], dict[str, str | float | None]] = {}
        for row in rows:
            key = (str(row[BRAND_DIMENSION_TYPE]), str(row[BRAND_DIMENSION_CODE]))
            current = grouped.setdefault(
                key,
                {
                    BRAND_DIMENSION_TYPE: key[0],
                    BRAND_DIMENSION_CODE: key[1],
                    BRAND_DIMENSION_NAME: str(row[BRAND_DIMENSION_NAME]),
                    BUSINESS_DAY: str(row[BUSINESS_DAY]),
                    BRAND_CONSUMER_COUNT: 0.0,
                    BRAND_CONSUMER_SHARE: None,
                    BRAND_PRODUCT_NEW_ASSET_CONSUMERS: 0.0,
                    BRAND_TRANSACTION_BUYER_COUNT: 0.0,
                    BRAND_TRANSACTION_AMOUNT: 0.0,
                    BRAND_CONVERSION_RATE: None,
                },
            )
            current[BRAND_PRODUCT_NEW_ASSET_CONSUMERS] = cls._number(current[BRAND_PRODUCT_NEW_ASSET_CONSUMERS]) + cls._number(row[BRAND_PRODUCT_NEW_ASSET_CONSUMERS])
            current[BRAND_TRANSACTION_BUYER_COUNT] = cls._number(current[BRAND_TRANSACTION_BUYER_COUNT]) + cls._number(row[BRAND_TRANSACTION_BUYER_COUNT])
            current[BRAND_TRANSACTION_AMOUNT] = cls._number(current[BRAND_TRANSACTION_AMOUNT]) + cls._number(row[BRAND_TRANSACTION_AMOUNT])
            if str(row[BUSINESS_DAY]) >= str(current[BUSINESS_DAY]):
                current[BUSINESS_DAY] = str(row[BUSINESS_DAY])
                current[BRAND_CONSUMER_COUNT] = cls._number(row[BRAND_CONSUMER_COUNT])
                current[BRAND_CONSUMER_SHARE] = cls._text(row[BRAND_CONSUMER_SHARE])
                current[BRAND_CONVERSION_RATE] = cls._text(row[BRAND_CONVERSION_RATE])
        return sorted(grouped.values(), key=lambda item: cls._number(item[BRAND_TRANSACTION_AMOUNT]), reverse=True)

    @classmethod
    def _aggregate_product_peers(cls, rows: list[sqlite3.Row]) -> list[dict[str, str | float | None]]:
        grouped: dict[str, dict[str, str | float | None]] = {}
        for row in rows:
            product_id = str(row[BRAND_PRODUCT_ID])
            current = grouped.setdefault(
                product_id,
                {
                    BRAND_PRODUCT_ID: product_id,
                    BRAND_PRODUCT_NAME: str(row[BRAND_PRODUCT_NAME]),
                    BRAND_PRODUCT_SERIES: cls._text(row[BRAND_PRODUCT_SERIES]),
                    BUSINESS_DAY: None,
                    BRAND_PRODUCT_ASSET_CONSUMERS: 0.0,
                    BRAND_PRODUCT_NEW_ASSET_CONSUMERS: 0.0,
                    BRAND_TRANSACTION_BUYER_COUNT: 0.0,
                    BRAND_TRANSACTION_AMOUNT: 0.0,
                    BRAND_PRODUCT_CONTRIBUTION_RATE: None,
                },
            )
            if row[BUSINESS_DAY] is None:
                continue
            current[BRAND_PRODUCT_NEW_ASSET_CONSUMERS] = cls._number(current[BRAND_PRODUCT_NEW_ASSET_CONSUMERS]) + cls._number(row[BRAND_PRODUCT_NEW_ASSET_CONSUMERS])
            current[BRAND_TRANSACTION_BUYER_COUNT] = cls._number(current[BRAND_TRANSACTION_BUYER_COUNT]) + cls._number(row[BRAND_TRANSACTION_BUYER_COUNT])
            current[BRAND_TRANSACTION_AMOUNT] = cls._number(current[BRAND_TRANSACTION_AMOUNT]) + cls._number(row[BRAND_TRANSACTION_AMOUNT])
            if current[BUSINESS_DAY] is None or str(row[BUSINESS_DAY]) >= str(current[BUSINESS_DAY]):
                current[BUSINESS_DAY] = str(row[BUSINESS_DAY])
                current[BRAND_PRODUCT_ASSET_CONSUMERS] = cls._number(row[BRAND_PRODUCT_ASSET_CONSUMERS])
                current[BRAND_PRODUCT_CONTRIBUTION_RATE] = cls._text(row[BRAND_PRODUCT_CONTRIBUTION_RATE])
        return sorted(grouped.values(), key=lambda item: cls._number(item[BRAND_TRANSACTION_AMOUNT]), reverse=True)

    @staticmethod
    def _product_record(row: sqlite3.Row) -> BrandProductRecord:
        return BrandProductRecord(
            brand_id=str(row[BRAND_ID]),
            product_id=str(row[BRAND_PRODUCT_ID]),
            spu_id=str(row[BRAND_PRODUCT_SPU_ID]) if row[BRAND_PRODUCT_SPU_ID] else None,
            product_name=str(row[BRAND_PRODUCT_NAME]),
            series=str(row[BRAND_PRODUCT_SERIES]) if row[BRAND_PRODUCT_SERIES] else None,
            category=str(row[BRAND_PRODUCT_CATEGORY]) if row[BRAND_PRODUCT_CATEGORY] else None,
            product_line=str(row[BRAND_PRODUCT_LINE]) if row[BRAND_PRODUCT_LINE] else None,
            positioning=str(row[BRAND_PRODUCT_POSITIONING]) if row[BRAND_PRODUCT_POSITIONING] else None,
            status=str(row[BRAND_PRODUCT_STATUS]),
            launch_date=str(row[BRAND_PRODUCT_LAUNCH_DATE]) if row[BRAND_PRODUCT_LAUNCH_DATE] else None,
            row_count=int(row["row_count"]),
            min_day=str(row["min_day"]) if row["min_day"] else None,
            max_day=str(row["max_day"]) if row["max_day"] else None,
        )

    @staticmethod
    def _dataset_status(
        conn: sqlite3.Connection,
        brand_id: str,
        key: str,
        label: str,
        table: str,
        date_column: str,
    ) -> BrandDatasetStatus:
        if not LocalDatabase._table_exists(conn, table):
            return BrandDatasetStatus(
                key=key,
                label=label,
                table=table,
                row_count=0,
                min_day=None,
                max_day=None,
                imported=False,
            )
        row = conn.execute(
            f"select count(*) as row_count, min({q(date_column)}) as min_day, max({q(date_column)}) as max_day from {q(table)} where {q(BRAND_ID)} = ?",
            (brand_id,),
        ).fetchone()
        return BrandDatasetStatus(
            key=key,
            label=label,
            table=table,
            row_count=int(row["row_count"]),
            min_day=str(row["min_day"]) if row["min_day"] else None,
            max_day=str(row["max_day"]) if row["max_day"] else None,
            imported=int(row["row_count"]) > 0,
        )
