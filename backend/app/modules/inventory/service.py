from __future__ import annotations

import json
import sqlite3
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_FLOOR
from pathlib import Path
from typing import Any, Iterable

from app.core.local_database import LocalDatabase
from app.core.config import settings


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def _first(row: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in row and row[name] is not None and row[name] != "":
            return row[name]
    return None


def _key(value: Any) -> str | None:
    value = _text(value)
    return value.casefold() if value else None


# Product/SKU codes in the source catalog are intentionally treated as
# opaque identifiers.  The pattern only requires a leading letter, at least
# one digit, and four characters so ordinary Chinese words are not promoted
# to codes.
_CODE_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?=[A-Za-z0-9_-]*\d)[A-Za-z][A-Za-z0-9_-]{3,}(?![A-Za-z0-9])")
_SIZE_PATTERN = re.compile(r"(?i)(XXXXL|XXXL|XXL|XL|NB|S|M|L)")


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


_NON_REGULAR_MARKERS = ("试用", "小样", "体验", "mini", "单片", "旅行装", "便携装")


def _is_regular_product(specification: Any) -> bool:
    """Classify the catalog's regular/full-size products conservatively.

    The catalog does not have a dependable standalone product-type field yet,
    so only explicit non-regular markers are excluded.  Unknown values remain
    eligible instead of being silently treated as trial products.
    """
    value = _compact(specification)
    return not any(_compact(marker) in value for marker in _NON_REGULAR_MARKERS)


def _matches_product_type(specification: Any, normalized_query: str) -> bool:
    """Match common natural-language diaper type aliases to catalog specs."""
    value = _compact(specification)
    query = _compact(normalized_query)
    if "纸尿裤" in query:
        return "纸尿裤" in value
    if "拉拉裤" in query:
        return "拉拉裤" in value
    if "尿裤" in query or "尿不湿" in query:
        return any(token in value for token in ("纸尿裤", "拉拉裤", "尿不湿"))
    return True


def _product_type_label(normalized_query: str) -> str | None:
    """Return the business label for a recognized diaper type alias."""
    query = _compact(normalized_query)
    if "纸尿裤" in query:
        return "纸尿裤"
    if "拉拉裤" in query:
        return "拉拉裤"
    if "尿裤" in query or "尿不湿" in query:
        return "尿裤"
    return None


def _stock_quantity(row: dict[str, Any]) -> Decimal:
    return _decimal(_first(
        row,
        "available_quantity", "availableQuantity", "canUseQuantity", "can_use_quantity",
        "residualQuantity", "residual_quantity", "stockQuan", "stock_quantity",
    ))


def _matching_stock_rows(component: dict[str, Any], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Match one component by the strongest available identifier.

    Jackyun component details are expected to contain ``skuId``. Barcode and
    goods number are fallbacks for legacy/incomplete rows. Once a stronger
    identifier has matches, weaker identifiers are not mixed into the result.
    """
    identifiers = (
        ("component_sku_id", ("sku_id", "skuId")),
        ("component_sku_barcode", ("sku_barcode", "skuBarcode")),
        ("component_goods_no", ("goods_no", "goodsNo")),
    )
    for component_key, stock_keys in identifiers:
        component_value = _key(component.get(component_key))
        if not component_value:
            continue
        matched = [
            row for row in rows
            if any(component_value == _key(row.get(stock_key)) for stock_key in stock_keys)
        ]
        if matched:
            return matched
    return []


def calculate_package_inventory(
    components: Iterable[dict[str, Any]],
    stock_rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate package inventory without mixing component stock across warehouses.

    For each warehouse: ``min(floor(available / required))``. The package total
    is the sum of those per-warehouse values. Missing component stock counts as
    zero, which makes a partial warehouse correctly unavailable for the bundle.
    """
    normalized_components = []
    for raw in components:
        component = {
            "component_sku_id": _text(_first(raw, "component_sku_id", "componentSkuId", "sku_id", "skuId")),
            "component_goods_no": _text(_first(raw, "component_goods_no", "componentGoodsNo", "goods_no", "goodsNo")),
            "component_sku_barcode": _text(_first(raw, "component_sku_barcode", "componentSkuBarcode", "sku_barcode", "skuBarcode")),
            "component_goods_name": _text(_first(raw, "component_goods_name", "componentGoodsName", "goods_name", "goodsName")),
            "required_quantity": _decimal(_first(raw, "required_quantity", "requiredQuantity", "goodsAmount", "amount"), Decimal("1")),
        }
        if component["required_quantity"] <= 0:
            component["required_quantity"] = Decimal("1")
        normalized_components.append(component)

    by_warehouse: dict[str, list[dict[str, Any]]] = {}
    warehouse_names: dict[str, str | None] = {}
    for raw in stock_rows:
        row = dict(raw)
        warehouse_id = _text(_first(row, "warehouse_id", "warehouseId", "warehouseID", "storehouseId")) or "__default__"
        warehouse_names[warehouse_id] = _text(_first(row, "warehouse_name", "warehouseName", "storehouseName"))
        by_warehouse.setdefault(warehouse_id, []).append(row)

    warehouses = []
    for warehouse_id, rows in by_warehouse.items():
        component_results = []
        assemblable_values: list[int] = []
        for component in normalized_components:
            matched_rows = _matching_stock_rows(component, rows)
            # A SKU can appear in multiple stock rows in the same warehouse
            # (for example, split inventory statuses). Aggregate it before
            # calculating how many complete packages the warehouse can build.
            available = sum((_stock_quantity(row) for row in matched_rows), Decimal("0"))
            units = int((available / component["required_quantity"]).to_integral_value(rounding=ROUND_FLOOR))
            assemblable_values.append(max(units, 0))
            component_results.append({
                **component,
                "required_quantity": float(component["required_quantity"]),
                "available_quantity": float(available),
                "assemblable_quantity": max(units, 0),
            })
        warehouses.append({
            "warehouse_id": warehouse_id,
            "warehouse_name": warehouse_names.get(warehouse_id),
            "assemblable_quantity": min(assemblable_values) if assemblable_values else 0,
            "components": component_results,
        })

    return {
        "assemblable_quantity": sum(item["assemblable_quantity"] for item in warehouses),
        "warehouses": warehouses,
        "formula": "各仓组合库存=min(floor(组成SKU可用库存/单套用量))，组合总库存=各仓组合库存之和",
    }


class InventoryService:
    def __init__(self, database_path: Path) -> None:
        self.database = LocalDatabase(database_path)
        self.database.initialize_schema()

    def upsert_inventory_snapshot(
        self,
        *,
        store_id: int | None,
        business_day: date,
        rows: Iterable[dict[str, Any]],
    ) -> int:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        values = []
        for raw in rows:
            row = dict(raw)
            values.append((
                store_id or 0,
                business_day.isoformat(),
                _text(_first(row, "warehouse_id", "warehouseId", "warehouseID", "storehouseId")) or "__default__",
                _text(_first(row, "warehouse_name", "warehouseName", "storehouseName")),
                _text(_first(row, "goods_id", "goodsId")) or "",
                _text(_first(row, "sku_id", "skuId")) or "",
                _text(_first(row, "goods_no", "goodsNo")) or "",
                _text(_first(row, "sku_no", "skuNo")) or "",
                _text(_first(row, "goods_name", "goodsName")),
                _text(_first(row, "sku_name", "skuName", "skuProperitesName")),
                _text(_first(row, "sku_barcode", "skuBarcode")) or "",
                float(_stock_quantity(row)),
                float(_decimal(_first(row, "stock_quantity", "stockQuantity", "stockQuan"))),
                json.dumps(row, ensure_ascii=False, default=str),
                now,
            ))
        if not values:
            return 0
        with self.database.connect(initialize=True, read_only=False) as conn:
            # The inventory endpoint represents a full point-in-time snapshot.
            # Replace the store/day slice so SKUs that disappeared upstream do
            # not remain as false stock after the next hourly refresh.
            conn.execute(
                "delete from jackyun_inventory_snapshots where store_id = ? and business_day = ?",
                (store_id or 0, business_day.isoformat()),
            )
            conn.executemany(
                """
                insert into jackyun_inventory_snapshots (
                    store_id, business_day, warehouse_id, warehouse_name, goods_id,
                    sku_id, goods_no, sku_no, goods_name, sku_name, sku_barcode,
                    available_quantity, stock_quantity, raw_json, fetched_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict (business_day, store_id, warehouse_id, sku_id, goods_no, sku_barcode)
                do update set warehouse_name=excluded.warehouse_name, goods_id=excluded.goods_id,
                    sku_no=excluded.sku_no, goods_name=excluded.goods_name, sku_name=excluded.sku_name,
                    available_quantity=excluded.available_quantity, stock_quantity=excluded.stock_quantity,
                    raw_json=excluded.raw_json, fetched_at=excluded.fetched_at
                """,
                values,
            )
            conn.commit()
        return len(values)

    def replace_goods_master(self, *, store_id: int | None, rows: Iterable[dict[str, Any]]) -> int:
        """Replace one store's ordinary ERP goods master after a full fetch.

        Goods master data is a daily dimension snapshot.  It is only replaced
        when the caller has received a non-empty, successful response, so an
        upstream empty response cannot erase the last known catalog.
        """
        store_key = store_id or 0
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        values: list[tuple[Any, ...]] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            goods_no = _text(_first(raw, "goods_no", "goodsNo")) or ""
            goods_id = _text(_first(raw, "goods_id", "goodsId", "id")) or goods_no
            if not goods_id and not goods_no:
                continue
            values.append((
                store_key, goods_id, goods_no,
                _text(_first(raw, "goods_name", "goodsName")),
                _text(_first(raw, "cate_name", "cateName")),
                _text(_first(raw, "brand_name", "brandName")),
                _text(_first(raw, "unit_name", "unitName")),
                _text(_first(raw, "assist_unit", "assistUnit")),
                _text(_first(raw, "owner_name", "ownerName")),
                int(_decimal(_first(raw, "package_good", "packageGood"))),
                _text(_first(raw, "audit_status", "aduitStatus", "auditStatus")),
                int(_decimal(_first(raw, "is_blockup", "isBlockup"))) if _first(raw, "is_blockup", "isBlockup") not in (None, "") else None,
                int(_decimal(_first(raw, "is_stop_selling", "isStopSelling"))) if _first(raw, "is_stop_selling", "isStopSelling") not in (None, "") else None,
                int(_decimal(_first(raw, "is_stop_purchasing", "isStopPurchasing"))) if _first(raw, "is_stop_purchasing", "isStopPurchasing") not in (None, "") else None,
                json.dumps(raw, ensure_ascii=False, default=str), now,
            ))
        if not values:
            return 0
        with self.database.connect(initialize=True, read_only=False) as conn:
            conn.execute("delete from jackyun_goods_master where store_id = ?", (store_key,))
            conn.executemany(
                """
                insert into jackyun_goods_master (
                    store_id, goods_id, goods_no, goods_name, cate_name, brand_name,
                    unit_name, assist_unit, owner_name, package_good, audit_status,
                    is_blockup, is_stop_selling, is_stop_purchasing, raw_json, fetched_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict (store_id, goods_id, goods_no) do update set
                    goods_name=excluded.goods_name, cate_name=excluded.cate_name,
                    brand_name=excluded.brand_name, unit_name=excluded.unit_name,
                    assist_unit=excluded.assist_unit, owner_name=excluded.owner_name,
                    package_good=excluded.package_good, audit_status=excluded.audit_status,
                    is_blockup=excluded.is_blockup, is_stop_selling=excluded.is_stop_selling,
                    is_stop_purchasing=excluded.is_stop_purchasing, raw_json=excluded.raw_json,
                    fetched_at=excluded.fetched_at
                """,
                values,
            )
            conn.commit()
        return len(values)

    def replace_package_master(self, *, store_id: int | None, records: Iterable[dict[str, Any]]) -> tuple[int, int]:
        """Replace combination products and their component relations atomically."""
        store_key = store_id or 0
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        products: list[tuple[Any, ...]] = []
        components: list[tuple[Any, ...]] = []
        for record in records:
            product = record.get("product") if isinstance(record, dict) else None
            raw_components = record.get("components") if isinstance(record, dict) else None
            if not isinstance(product, dict):
                continue
            goods_no = _text(_first(product, "goods_no", "goodsNo")) or ""
            sku_no = _text(_first(product, "sku_no", "skuNo")) or ""
            goods_id = _text(_first(product, "goods_id", "goodsId", "id")) or goods_no
            sku_id = _text(_first(product, "sku_id", "skuId")) or sku_no or goods_id
            if not goods_id and not goods_no:
                continue
            products.append((
                store_key, goods_id, sku_id, goods_no, sku_no,
                _text(_first(product, "goods_name", "goodsName")),
                _text(_first(product, "sku_name", "skuName", "skuProperitesName")),
                _text(_first(product, "sku_barcode", "skuBarcode")) or "", now,
            ))
            if isinstance(raw_components, list):
                for item in raw_components:
                    if not isinstance(item, dict):
                        continue
                    component_goods_no = _text(_first(item, "component_goods_no", "componentGoodsNo", "goods_no", "goodsNo")) or ""
                    component_goods_id = _text(_first(item, "component_goods_id", "componentGoodsId", "goods_id", "goodsId")) or component_goods_no
                    component_sku_no = _text(_first(item, "component_sku_no", "componentSkuNo", "sku_no", "skuNo")) or ""
                    component_sku_id = _text(_first(item, "component_sku_id", "componentSkuId", "sku_id", "skuId")) or component_sku_no or component_goods_id
                    components.append((
                        store_key, goods_id, sku_id, component_goods_id, component_sku_id,
                        component_goods_no,
                        _text(_first(item, "component_sku_barcode", "componentSkuBarcode", "sku_barcode", "skuBarcode")) or "",
                        _text(_first(item, "component_goods_name", "componentGoodsName", "goods_name", "goodsName")),
                        float(_decimal(_first(item, "required_quantity", "requiredQuantity", "goodsAmount", "amount"), Decimal("1"))), now,
                    ))
        if not products:
            return 0, 0
        products = list({(row[0], row[1], row[2]): row for row in products}.values())
        package_keys = {(row[1], row[2]) for row in products}
        components = [row for row in components if (row[1], row[2]) in package_keys]
        with self.database.connect(initialize=True, read_only=False) as conn:
            conn.execute("delete from jackyun_package_components where store_id = ?", (store_key,))
            conn.execute("delete from jackyun_package_products where store_id = ?", (store_key,))
            conn.executemany(
                """
                insert into jackyun_package_products (
                    store_id, goods_id, sku_id, goods_no, sku_no, goods_name,
                    sku_name, sku_barcode, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict (store_id, goods_id, sku_id) do update set
                    goods_no=excluded.goods_no, sku_no=excluded.sku_no,
                    goods_name=excluded.goods_name, sku_name=excluded.sku_name,
                    sku_barcode=excluded.sku_barcode, updated_at=excluded.updated_at
                """,
                products,
            )
            conn.executemany(
                """
                insert into jackyun_package_components (
                    store_id, package_goods_id, package_sku_id, component_goods_id,
                    component_sku_id, component_goods_no, component_sku_barcode,
                    component_goods_name, required_quantity, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                components,
            )
            conn.commit()
        return len(products), len(components)

    def record_master_sync(
        self,
        *,
        store_id: int,
        business_day: date,
        goods_status: str,
        package_status: str,
        goods_count: int = 0,
        package_count: int = 0,
        component_count: int = 0,
        error_message: str | None = None,
        finished: bool = False,
    ) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.database.connect(initialize=True, read_only=False) as conn:
            conn.execute(
                """
                insert into jackyun_inventory_master_sync_status (
                    store_id, business_day, goods_status, package_status, goods_count,
                    package_count, component_count, last_attempt_at, finished_at, error_message
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict (store_id, business_day) do update set
                    goods_status=excluded.goods_status, package_status=excluded.package_status,
                    goods_count=excluded.goods_count, package_count=excluded.package_count,
                    component_count=excluded.component_count, last_attempt_at=excluded.last_attempt_at,
                    finished_at=excluded.finished_at, error_message=excluded.error_message
                """,
                (store_id, business_day.isoformat(), goods_status, package_status, goods_count,
                 package_count, component_count, now, now if finished else None, error_message),
            )
            conn.commit()

    def get_master_sync(self, store_id: int | None) -> dict[str, Any]:
        with self.database.connect(initialize=True) as conn:
            row = conn.execute(
                "select * from jackyun_inventory_master_sync_status where (? is null or store_id = ?) order by business_day desc limit 1",
                (store_id, store_id),
            ).fetchone()
        return dict(row) if row else {}

    def upsert_package(
        self,
        *,
        store_id: int | None,
        product: dict[str, Any],
        components: Iterable[dict[str, Any]],
    ) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        store_key = store_id or 0
        package_sku_id = _text(_first(product, "sku_id", "skuId")) or ""
        package_goods_id = _text(_first(product, "goods_id", "goodsId")) or ""
        with self.database.connect(initialize=True, read_only=False) as conn:
            conn.execute(
                """
                insert into jackyun_package_products (
                    store_id, goods_id, sku_id, goods_no, sku_no, goods_name, sku_name,
                    sku_barcode, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict (store_id, goods_id, sku_id) do update set
                    goods_no=excluded.goods_no, sku_no=excluded.sku_no,
                    goods_name=excluded.goods_name, sku_name=excluded.sku_name,
                    sku_barcode=excluded.sku_barcode, updated_at=excluded.updated_at
                """,
                (store_key, package_goods_id, package_sku_id,
                 _text(_first(product, "goods_no", "goodsNo")) or "", _text(_first(product, "sku_no", "skuNo")) or "",
                 _text(_first(product, "goods_name", "goodsName")), _text(_first(product, "sku_name", "skuName", "skuProperitesName")),
                 _text(_first(product, "sku_barcode", "skuBarcode")) or "", now),
            )
            conn.execute(
                "delete from jackyun_package_components where store_id = ? and package_goods_id = ? and package_sku_id = ?",
                (store_key, package_goods_id, package_sku_id),
            )
            conn.executemany(
                """
                insert into jackyun_package_components (
                    store_id, package_goods_id, package_sku_id, component_goods_id,
                    component_sku_id, component_goods_no, component_sku_barcode,
                    component_goods_name, required_quantity, updated_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(
                    store_key, package_goods_id, package_sku_id,
                    _text(_first(item, "component_goods_id", "componentGoodsId", "goods_id", "goodsId")) or "",
                    _text(_first(item, "component_sku_id", "componentSkuId", "sku_id", "skuId")) or "",
                    _text(_first(item, "component_goods_no", "componentGoodsNo", "goods_no", "goodsNo")) or "",
                    _text(_first(item, "component_sku_barcode", "componentSkuBarcode", "sku_barcode", "skuBarcode")) or "",
                    _text(_first(item, "component_goods_name", "componentGoodsName", "goods_name", "goodsName")),
                    float(_decimal(_first(item, "required_quantity", "requiredQuantity", "goodsAmount", "amount"), Decimal("1"))), now,
                ) for item in components],
            )
            conn.commit()

    def query(self, *, store_id: int | None, query: str, business_day: date | None = None) -> dict[str, Any]:
        query = query.strip()
        if business_day is None:
            catalog_result = self._catalog_inventory_query(store_id=store_id, query=query)
            if catalog_result is not None:
                return catalog_result
        with self.database.connect() as conn:
            requested_day = business_day is not None
            if business_day is None:
                business_day = self._latest_day(conn, store_id)
            if business_day is None:
                reason = "not_configured" if not settings.jackyun_configured else "not_collected"
                warning = "吉客云库存接口或 Token 尚未配置。" if reason == "not_configured" else "吉客云已配置，但尚未成功采集库存快照。"
                return {
                    "status": "no_data", "reason": reason, "query": query, "business_day": None, "items": [], "snapshot_row_count": 0,
                    **self._freshness(conn, store_id, None),
                    "query_terms": self._candidate_terms(query), "matched_by": [], "match_type": "none", "ambiguous": False, "candidate_count": 0,
                    "warnings": [warning],
                }
            terms = self._candidate_terms(query)
            all_stock_rows = [dict(row) for row in conn.execute(
                """
                select * from jackyun_inventory_snapshots
                where (? is null or store_id = ?) and business_day = ?
                order by warehouse_id
                """, (store_id, store_id, business_day.isoformat()),
            ).fetchall()]
            if requested_day and not all_stock_rows:
                freshness = self._freshness(conn, store_id, business_day)
                return {
                    "status": "no_data", "reason": "date_not_available", "query": query,
                    "business_day": business_day, "items": [], "snapshot_row_count": 0, **freshness,
                    "warnings": [f"指定日期 {business_day.isoformat()} 没有吉客云库存快照；库存默认应查询最新时点快照。"],
                }
            package_rows = [dict(row) for row in conn.execute(
                """
                select distinct store_id, goods_id, sku_id, goods_no, sku_no, goods_name, sku_name, sku_barcode
                from jackyun_package_products where (? is null or store_id = ?)
                """, (store_id, store_id),
            ).fetchall()]
            products = [row for row in package_rows if self._matches_query(row, query, terms)]
            package_items = [self._package_result(conn, store_id, business_day, dict(row)) for row in products]
            stock_rows = [row for row in all_stock_rows if self._matches_query(row, query, terms)]
            package_products = [dict(row) for row in products]
            ordinary_rows = [row for row in stock_rows if not any(self._same_product(row, product) for product in package_products)]
            ordinary = self._ordinary_results(ordinary_rows, business_day)
            items = package_items + ordinary
            for item in items:
                self._attach_catalog(conn, store_id, item)
            freshness = self._freshness(conn, store_id, business_day)
            code_terms = [term for term in terms if self._looks_like_code(term)]
            candidate_count = len(items)
            top_matched_by: list[str] = []
            for item in items:
                item_terms = self._matched_by(item, terms)
                item["matched_by"] = item_terms
                item["match_type"] = "exact_code" if code_terms and item_terms else "identifier" if item_terms else "text"
                item["candidate_count"] = candidate_count
                top_matched_by.extend(item_terms)
            top_matched_by = list(dict.fromkeys(top_matched_by))
            catalog_ambiguous = code_terms and any(int(item.get("catalog_match_count") or 0) > 1 for item in items)
            reason = "ambiguous_code" if code_terms and (candidate_count > 1 or catalog_ambiguous) else "matched"
            if catalog_ambiguous:
                candidate_count = max(candidate_count, max(int(item.get("catalog_match_count") or 0) for item in items))
            if not items:
                non_size_terms = [term for term in terms if not self._is_size_term(term)]
                base_matches = []
                if non_size_terms and len(non_size_terms) < len(terms):
                    base_matches = [row for row in [*package_rows, *all_stock_rows] if self._matches_query(row, "", non_size_terms)]
                if code_terms:
                    known_package = [row for row in package_rows if self._row_has_code(row, code_terms)]
                    known_snapshot = [row for row in all_stock_rows if self._row_has_code(row, code_terms)]
                    reason = "code_known_no_snapshot" if known_package and not known_snapshot else "product_not_matched"
                else:
                    reason = "sku_not_matched" if base_matches else "product_not_matched"
            elif all(float(item.get("available_quantity") or 0) <= 0 for item in items):
                reason = "zero_stock" if reason != "ambiguous_code" else reason
            if reason == "sku_not_matched":
                warnings = [f"已匹配到商品，但没有匹配到“{query}”对应的尺码或 SKU。"]
            elif reason == "code_known_no_snapshot":
                warnings = [f"已识别货品编码，但当前库存快照没有该编码记录；不能把它当作 0 库存。"]
            elif reason == "ambiguous_code":
                warnings = [f"货品编码“{query}”对应 {candidate_count} 个库存候选，请结合系列、规格或尺码确认。"]
            elif reason == "product_not_matched":
                warnings = [f"库存业务日为 {business_day.isoformat()}，但没有匹配到“{query}”对应的商品。"]
            elif reason == "zero_stock":
                warnings = ["已匹配到商品和 SKU，但当前可用库存为 0。"]
            else:
                warnings = []
            if freshness.get("freshness_status") == "stale":
                warnings.append("库存快照已超过 1 小时，结果可能不是最新可用库存。")
            return {
                "status": "ok" if items else "no_data", "reason": reason, "query": query,
                "business_day": business_day, "items": items, "snapshot_row_count": len(all_stock_rows),
                "query_terms": terms, "matched_by": top_matched_by,
                "match_type": "exact_code" if code_terms and items else "identifier" if top_matched_by else "none",
                "ambiguous": reason == "ambiguous_code", "candidate_count": candidate_count,
                **freshness, "warnings": warnings,
            }

    def _catalog_inventory_query(self, *, store_id: int | None, query: str) -> dict[str, Any] | None:
        """Resolve natural-language catalog slices such as "正装的尿裤缺货".

        These questions describe a catalog slice rather than one free-form SKU
        name.  Resolve the slice against the maintained product catalog first,
        then use the latest inventory snapshot to distinguish real zero stock
        from a catalog row that was not returned by the inventory platform.
        """
        normalized = _compact(query)
        stockout_intent = any(token in normalized for token in ("缺货", "断货", "零库存", "没货"))
        size_scope = "尺码" in normalized or "哪些码" in normalized
        if not stockout_intent:
            return None

        # This is a read-only, bounded catalog query. It deliberately uses the
        # management service rather than exposing arbitrary SQL to the model.
        # Scope queries must use the complete catalog; the management endpoint's
        # 200-row page is only a presentation concern and can otherwise hide
        # stockouts after the first page.
        full = self.management(store_id=store_id, page=1, page_size=200, include_all=True)
        available_series = sorted(full.get("dimensions", {}).get("series", []), key=len, reverse=True)
        series = next((value for value in available_series if _compact(value) in normalized), None)

        rows = list(full.get("rows", []))
        if not rows and not full.get("dimensions", {}).get("series"):
            return None
        if series:
            rows = [row for row in rows if str(row.get("series") or "").strip() == series]
        regular_pack = "正装" in normalized
        if regular_pack:
            rows = [row for row in rows if _is_regular_product(row.get("specification"))]
        if not _matches_product_type(" ".join(str(row.get("specification") or "") for row in rows), normalized):
            return None
        rows = [row for row in rows if _matches_product_type(row.get("specification"), normalized)]

        # Product-type aliases are represented by the specification dimension
        # in today's catalog. Do not apply the same token twice ("纸尿裤"
        # should not become a redundant scope label "纸尿裤纸尿裤").
        type_label = _product_type_label(normalized) or ""
        specification = next((
            value for value in full.get("dimensions", {}).get("specification", [])
            if _compact(value) in normalized and _compact(value) != _compact(type_label)
        ), None)
        if specification:
            rows = [row for row in rows if str(row.get("specification") or "").strip() == specification]

        unmatched = [row for row in rows if row.get("stock_status") == "未匹配库存"]
        stockouts = [row for row in rows if row.get("stock_status") == "零库存"]
        checked = [row for row in rows if row.get("stock_status") != "未匹配库存"]
        scope_label = f"{series or '全店'}{type_label}{'正装' if regular_pack else ''}{specification or ''}"

        def result_item(row: dict[str, Any]) -> dict[str, Any]:
            row_business_day = row.get("business_day")
            return {
                "item_type": "sku",
                "goods_no": row.get("goods_no"),
                "goods_name": row.get("display_name"),
                "sku_name": row.get("display_name"),
                "series": row.get("series"),
                "specification": row.get("specification"),
                "size": row.get("size"),
                "pieces": row.get("pieces"),
                "display_name": row.get("display_name"),
                "business_day": row_business_day.isoformat() if isinstance(row_business_day, date) else row_business_day,
                "available_quantity": row.get("available_quantity"),
                "warehouses": [],
                "formula": "普通 SKU 库存=各仓可用库存之和",
                "warnings": [],
                "catalog_match_count": row.get("catalog_match_count") or 1,
                "catalog_candidates": [],
                "matched_by": [key for key, present in (("series", bool(series)), ("specification", bool(row.get("specification"))), ("size", bool(row.get("size")))) if present],
                "match_type": "catalog_scope",
                "candidate_count": len(rows),
            }

        items = [result_item(row) for row in stockouts]
        checked_items = [result_item(row) for row in checked]
        if unmatched:
            status = "partial"
            reason = "stockout_scope_partial"
            warnings = [f"{scope_label}有 {len(unmatched)} 个目录 SKU 未匹配到最新库存快照，不能把它们当作 0 库存。"]
        elif stockouts:
            status = "ok"
            reason = "stockouts_found"
            warnings = []
        else:
            status = "ok"
            reason = "no_stockouts"
            warnings = []

        latest_day = full.get("latest_business_day")
        latest_day_text = latest_day.isoformat() if isinstance(latest_day, date) else str(latest_day or "")
        with self.database.connect() as conn:
            row = conn.execute(
                "select count(*) as total from jackyun_inventory_snapshots where (? is null or store_id = ?) and business_day = ?",
                (store_id, store_id, latest_day_text),
            ).fetchone()
            snapshot_row_count = int(row["total"] or 0) if row else 0

        return {
            "status": status,
            "reason": reason,
            "query": query,
            "business_day": latest_day_text or None,
            "items": items,
            "checked_items": checked_items,
            "scope": {
                "series": series,
                "specification": specification,
                "pack_type": "正装" if regular_pack else None,
                "product_type": type_label or None,
                "label": scope_label,
                "checked_sku_count": len(checked),
                "stockout_sku_count": len(stockouts),
                "unmatched_sku_count": len(unmatched),
            },
            "snapshot_row_count": snapshot_row_count,
            "query_terms": [value for value in (series, type_label or None, "正装" if regular_pack else None, specification, "缺货") if value],
            "matched_by": ["inventory_product_catalog"],
            "match_type": "catalog_scope",
            "ambiguous": False,
            "candidate_count": len(rows),
            "latest_snapshot_at": full.get("latest_snapshot_at"),
            "latest_business_day": latest_day_text or None,
            "snapshot_age_minutes": full.get("snapshot_age_minutes"),
            "freshness_status": full.get("freshness_status", "unknown"),
            "warnings": warnings,
        }

    def management(
        self,
        *,
        store_id: int | None,
        query: str | None = None,
        series: str | None = None,
        specification: str | None = None,
        size: str | None = None,
        stock_status: str | None = None,
        page: int = 1,
        page_size: int = 50,
        include_all: bool = False,
    ) -> dict[str, Any]:
        """Return the catalog as the stable inventory-management surface.

        Catalog rows are preserved even when the latest snapshot has no row.
        That is the key distinction between an unmapped/uncollected SKU and a
        real zero-stock result.
        """
        page = max(1, page)
        # Public callers stay bounded at 200 rows. Internal analytical scope
        # queries can request the complete filtered set so totals and stockout
        # decisions are not affected by UI pagination.
        page_size = (max(1, page_size) if include_all else min(200, max(1, page_size)))
        store_key = store_id or 0
        with self.database.connect() as conn:
            latest_day = self._latest_day(conn, store_id)
            catalog_rows = [dict(row) for row in conn.execute(
                "select * from inventory_product_catalog where store_id = ? and is_active = 1 order by series, specification, size, goods_no, id",
                (store_key,),
            ).fetchall()]
            latest_stock = []
            if latest_day:
                latest_stock = [dict(row) for row in conn.execute(
                    "select * from jackyun_inventory_snapshots where store_id = ? and business_day = ?",
                    (store_key, latest_day.isoformat()),
                ).fetchall()]
            stock_index: dict[str, list[dict[str, Any]]] = {}
            for stock in latest_stock:
                for key in ("goods_no", "sku_no", "sku_barcode", "sku_id", "goods_id"):
                    compact = _compact(stock.get(key))
                    if compact:
                        stock_index.setdefault(compact, []).append(stock)

            def clean(value: Any) -> str:
                return str(value or "").strip()

            def match_catalog(row: dict[str, Any]) -> bool:
                if series and clean(row.get("series")) != clean(series):
                    return False
                if specification and clean(row.get("specification")) != clean(specification):
                    return False
                if size and clean(row.get("size")).casefold() != clean(size).casefold():
                    return False
                if query:
                    needle = clean(query).casefold().replace(" ", "")
                    haystack = "".join(clean(row.get(key)).casefold() for key in ("series", "specification", "size", "goods_no", "display_name"))
                    if needle not in haystack:
                        return False
                return True

            def stock_for(code: str) -> list[dict[str, Any]]:
                compact = _compact(code)
                rows = stock_index.get(compact, [])
                return list({id(row): row for row in rows}.values())

            all_rows: list[dict[str, Any]] = []
            for row in catalog_rows:
                if not match_catalog(row):
                    continue
                stocks = stock_for(row.get("goods_no") or "")
                quantities = [float(_decimal(item.get("available_quantity"))) for item in stocks]
                quantity = sum(quantities) if stocks else None
                warehouse_values: dict[str, float] = {}
                for item in stocks:
                    warehouse = clean(item.get("warehouse_id")) or "__default__"
                    warehouse_values[warehouse] = warehouse_values.get(warehouse, 0) + float(_decimal(item.get("available_quantity")))
                if not stocks:
                    status = "未匹配库存"
                elif quantity <= 0:
                    status = "零库存"
                elif quantity <= 10:
                    status = "低库存"
                else:
                    status = "有库存"
                candidate_count = sum(1 for item in catalog_rows if _compact(item.get("goods_no")) == _compact(row.get("goods_no")))
                item = {
                    "id": int(row["id"]),
                    "series": row.get("series") or "",
                    "specification": row.get("specification") or "",
                    "size": row.get("size") or "",
                    "goods_no": row.get("goods_no") or "",
                    "pieces": row.get("pieces"),
                    "display_name": row.get("display_name"),
                    "available_quantity": quantity,
                    "warehouse_count": len(warehouse_values),
                    "min_warehouse_quantity": min(warehouse_values.values()) if warehouse_values else None,
                    "stock_status": status,
                    "catalog_match_count": candidate_count,
                    "business_day": latest_day,
                    "snapshot_at": max((str(item.get("fetched_at")) for item in stocks if item.get("fetched_at")), default=None),
                }
                if not stock_status or status == stock_status:
                    all_rows.append(item)

            total = len(all_rows)
            offset = (page - 1) * page_size
            freshness = self._freshness(conn, store_id, latest_day)
            master_sync = self.get_master_sync(store_id)
            summary = {
                "catalog_count": len(catalog_rows),
                "matched_count": sum(1 for row in all_rows if row["stock_status"] != "未匹配库存"),
                "in_stock_count": sum(1 for row in all_rows if row["stock_status"] == "有库存"),
                "low_stock_count": sum(1 for row in all_rows if row["stock_status"] == "低库存"),
                "zero_stock_count": sum(1 for row in all_rows if row["stock_status"] == "零库存"),
                "unmatched_count": sum(1 for row in all_rows if row["stock_status"] == "未匹配库存"),
            }
            return {
                "summary": summary,
                "latest_business_day": latest_day,
                "latest_snapshot_at": freshness.get("latest_snapshot_at"),
                "freshness_status": freshness.get("freshness_status", "unknown"),
                "snapshot_age_minutes": freshness.get("snapshot_age_minutes"),
                "dimensions": {
                    "series": sorted({clean(row.get("series")) for row in catalog_rows if clean(row.get("series"))}),
                    "specification": sorted({clean(row.get("specification")) for row in catalog_rows if clean(row.get("specification"))}),
                    "size": sorted({clean(row.get("size")) for row in catalog_rows if clean(row.get("size"))}),
                },
                "total": total,
                "page": page,
                "page_size": page_size,
                "rows": all_rows if include_all else all_rows[offset:offset + page_size],
            }

    def analysis(
        self,
        *,
        store_id: int | None,
        query: str | None = None,
        stock_status: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Return company-wide stock and bundle diagnostics for the latest snapshot.

        This intentionally uses ERP snapshot rows rather than the paginated
        storefront catalog. The company view must include every SKU returned by
        the warehouse, including SKUs that have not yet been mapped to a shop
        product. Missing catalog mappings are reported as metadata, never as
        zero stock.
        """
        limit = min(1000, max(1, limit))
        store_key = store_id or 0
        with self.database.connect() as conn:
            latest_day = self._latest_day(conn, store_id)
            freshness = self._freshness(conn, store_id, latest_day)
            master_sync = self.get_master_sync(store_id)
            package_products = [dict(row) for row in conn.execute(
                "select * from jackyun_package_products where store_id = ? order by goods_no, sku_id",
                (store_key,),
            ).fetchall()]
            if latest_day is None:
                package_rows = []
                for product in package_products:
                    components = [dict(row) for row in conn.execute(
                        "select * from jackyun_package_components where store_id = ? and package_goods_id = ? and package_sku_id = ? order by component_id",
                        (store_key, product.get("goods_id"), product.get("sku_id")),
                    ).fetchall()]
                    package_rows.append({
                        "key": _compact(product.get("sku_id") or product.get("goods_no")) or "unknown",
                        "goods_no": product.get("goods_no") or "",
                        "sku_no": product.get("sku_no") or "",
                        "goods_name": product.get("goods_name"),
                        "sku_name": product.get("sku_name"),
                        "component_count": len(components),
                        "stock_status": "已同步明细" if components else "待同步明细",
                        "component_summary": [f"{item.get('component_goods_no') or item.get('component_sku_id') or '未命名'} × {float(item.get('required_quantity') or 1):g}" for item in components],
                        "business_day": None,
                    })
                return {
                    "latest_business_day": None, **freshness, "master_sync": master_sync, "company_summary": {},
                    "warehouse_summary": [], "company_rows": [], "stockout_rows": [],
                    "package_summary": {
                        "package_count": len(package_rows),
                        "with_components": sum(bool(row["component_count"]) for row in package_rows),
                        "without_components": sum(not row["component_count"] for row in package_rows),
                        "component_count": sum(row["component_count"] for row in package_rows),
                    },
                    "package_rows": package_rows[:limit],
                    "warnings": ["暂无库存快照；组合货品仅展示每日同步的主档和组成关系，不计算组合库存。"],
                }

            stock_rows = [dict(row) for row in conn.execute(
                "select * from jackyun_inventory_snapshots where store_id = ? and business_day = ? order by warehouse_id, goods_no, sku_id",
                (store_key, latest_day.isoformat()),
            ).fetchall()]
            catalog_rows = [dict(row) for row in conn.execute(
                "select * from inventory_product_catalog where store_id = ? and is_active = 1",
                (store_key,),
            ).fetchall()]
            catalog_by_code: dict[str, list[dict[str, Any]]] = {}
            for row in catalog_rows:
                code = _compact(row.get("goods_no"))
                if code:
                    catalog_by_code.setdefault(code, []).append(row)

            def matches(row: dict[str, Any]) -> bool:
                if not query:
                    return True
                terms = self._candidate_terms(query)
                return self._matches_query(row, query, terms)

            filtered_rows = [row for row in stock_rows if matches(row)]
            grouped: dict[str, list[dict[str, Any]]] = {}
            for row in filtered_rows:
                key = next((_compact(row.get(field)) for field in ("sku_id", "goods_no", "sku_barcode", "goods_id") if _compact(row.get(field))), "unknown")
                grouped.setdefault(key, []).append(row)

            company_rows: list[dict[str, Any]] = []
            for key, rows in grouped.items():
                first = rows[0]
                quantity = sum(float(_decimal(row.get("available_quantity"))) for row in rows)
                status = "零库存" if quantity <= 0 else "低库存" if quantity <= 10 else "有库存"
                catalog_matches = catalog_by_code.get(_compact(first.get("goods_no")), [])
                catalog = catalog_matches[0] if len(catalog_matches) == 1 else {}
                item = {
                    "key": key,
                    "goods_no": first.get("goods_no") or "",
                    "sku_no": first.get("sku_no") or "",
                    "goods_id": first.get("goods_id") or "",
                    "sku_id": first.get("sku_id") or "",
                    "goods_name": first.get("goods_name"),
                    "sku_name": first.get("sku_name"),
                    "sku_barcode": first.get("sku_barcode") or "",
                    "series": catalog.get("series") or "",
                    "specification": catalog.get("specification") or "",
                    "size": catalog.get("size") or "",
                    "pieces": catalog.get("pieces"),
                    "available_quantity": quantity,
                    "warehouse_count": len({_compact(row.get("warehouse_id")) for row in rows if _compact(row.get("warehouse_id"))}),
                    "stock_status": status,
                    "catalog_match_count": len(catalog_matches),
                    "business_day": latest_day,
                    "snapshot_at": max((str(row.get("fetched_at")) for row in rows if row.get("fetched_at")), default=None),
                }
                if not stock_status or status == stock_status:
                    company_rows.append(item)
            company_rows.sort(key=lambda row: (row["stock_status"] != "零库存", row["available_quantity"], row["goods_no"]))

            warehouse_groups: dict[str, list[dict[str, Any]]] = {}
            for row in filtered_rows:
                warehouse_key = _compact(row.get("warehouse_id")) or "__default__"
                warehouse_groups.setdefault(warehouse_key, []).append(row)
            warehouse_summary: list[dict[str, Any]] = []
            for warehouse_id, rows in warehouse_groups.items():
                sku_groups: dict[str, list[dict[str, Any]]] = {}
                for row in rows:
                    key = next((_compact(row.get(field)) for field in ("sku_id", "goods_no", "sku_barcode", "goods_id") if _compact(row.get(field))), "unknown")
                    sku_groups.setdefault(key, []).append(row)
                quantities = [sum(float(_decimal(row.get("available_quantity"))) for row in values) for values in sku_groups.values()]
                warehouse_summary.append({
                    "warehouse_id": str(rows[0].get("warehouse_id") or warehouse_id),
                    "warehouse_name": rows[0].get("warehouse_name"),
                    "sku_count": len(sku_groups),
                    "available_quantity": sum(quantities),
                    "in_stock_count": sum(value > 10 for value in quantities),
                    "low_stock_count": sum(0 < value <= 10 for value in quantities),
                    "zero_stock_count": sum(value <= 0 for value in quantities),
                })
            warehouse_summary.sort(key=lambda row: (-row["zero_stock_count"], -row["available_quantity"]))

            package_rows: list[dict[str, Any]] = []
            for product in package_products:
                if query and not self._matches_query(product, query, self._candidate_terms(query)):
                    continue
                components = [dict(row) for row in conn.execute(
                    "select * from jackyun_package_components where store_id = ? and package_goods_id = ? and package_sku_id = ? order by component_id",
                    (store_key, product.get("goods_id"), product.get("sku_id")),
                ).fetchall()]
                package_rows.append({
                    "key": _compact(product.get("sku_id") or product.get("goods_no")) or "unknown",
                    "goods_no": product.get("goods_no") or "",
                    "sku_no": product.get("sku_no") or "",
                    "goods_name": product.get("goods_name"),
                    "sku_name": product.get("sku_name"),
                    "component_count": len(components),
                    "stock_status": "已同步明细" if components else "待同步明细",
                    "component_summary": [f"{item.get('component_goods_no') or item.get('component_sku_id') or '未命名'} × {float(item.get('required_quantity') or 1):g}" for item in components],
                    "business_day": latest_day,
                })
            package_rows.sort(key=lambda row: (row["stock_status"] != "待同步明细", row["goods_no"]))
            package_summary = {
                "package_count": len(package_rows),
                "with_components": sum(row["stock_status"] == "已同步明细" for row in package_rows),
                "without_components": sum(row["stock_status"] == "待同步明细" for row in package_rows),
                "component_count": sum(row["component_count"] for row in package_rows),
            }
            warnings: list[str] = []
            if not package_products:
                warnings.append("当前没有同步到组合货品及组成明细。")
            if freshness.get("freshness_status") == "stale":
                warnings.append("库存快照已超过 1 小时，公司货品缺货判断可能不是最新状态；组合关系仍按每日主档同步。")
            if master_sync.get("error_message"):
                warnings.append(f"主档每日同步状态：{master_sync.get('error_message')}")
            return {
                "latest_business_day": latest_day,
                **freshness,
                "master_sync": master_sync,
                "company_summary": {
                    "sku_count": len(company_rows),
                    "available_quantity": sum(row["available_quantity"] for row in company_rows),
                    "in_stock_count": sum(row["stock_status"] == "有库存" for row in company_rows),
                    "low_stock_count": sum(row["stock_status"] == "低库存" for row in company_rows),
                    "zero_stock_count": sum(row["stock_status"] == "零库存" for row in company_rows),
                    "warehouse_count": len(warehouse_summary),
                    "mapped_count": sum(row["catalog_match_count"] > 0 for row in company_rows),
                    "unmapped_count": sum(row["catalog_match_count"] == 0 for row in company_rows),
                },
                "warehouse_summary": warehouse_summary,
                "company_rows": company_rows[:limit],
                "stockout_rows": [row for row in company_rows if row["stock_status"] == "零库存"][:limit],
                "package_summary": package_summary,
                "package_rows": package_rows[:limit],
                "warnings": warnings,
            }

    def _attach_catalog(self, conn: sqlite3.Connection, store_id: int | None, item: dict[str, Any]) -> None:
        codes = []
        for key in ("goods_no", "sku_no", "sku_barcode", "sku_id", "goods_id"):
            value = _compact(item.get(key))
            if value and value not in codes:
                codes.append(value)
        if not codes:
            item["catalog_match_count"] = 0
            item["catalog_candidates"] = []
            return
        rows = [dict(row) for row in conn.execute(
            "select series, specification, size, goods_no, pieces, display_name from inventory_product_catalog where store_id = ? and is_active = 1",
            (store_id or 0,),
        ).fetchall()]
        matches = [row for row in rows if _compact(row.get("goods_no")) in codes]
        item["catalog_match_count"] = len(matches)
        item["catalog_candidates"] = matches
        if len(matches) == 1:
            catalog = matches[0]
            item["series"] = catalog.get("series") or item.get("series")
            item["specification"] = catalog.get("specification") or item.get("specification")
            item["size"] = catalog.get("size") or item.get("size")
            item["pieces"] = catalog.get("pieces") if catalog.get("pieces") is not None else item.get("pieces")
            item["display_name"] = catalog.get("display_name") or item.get("display_name")

    @staticmethod
    def _candidate_terms(query: str) -> list[str]:
        normalized = query.casefold().replace("\u3000", " ")
        codes = [match.group(0) for match in _CODE_PATTERN.finditer(normalized)]
        normalized = _CODE_PATTERN.sub(" ", normalized)
        normalized = re.sub(r"(?:帮我|帮忙|麻烦|请问|请|查询|查一下|查下|查找|查|看一下|看下|看看|库存|数量|多少|还有|剩余|可用|现货|组合品|组合|商品|这个|那个|给我|一下|可以|能不能|想要|要)", " ", normalized)
        normalized = re.sub(r"([a-z0-9]+)\s*码", r"\1码", normalized)
        stop_words = {"的", "吗", "呢", "？", "?", "sku", "下", "请"}
        terms: list[str] = []
        for code in codes:
            compact_code = _compact(code)
            if compact_code not in terms:
                terms.append(compact_code)
        for token in re.findall(r"[a-z0-9_#-]+码|[a-z0-9_#-]+|[\u4e00-\u9fff]{2,}", normalized):
            token = token.casefold()
            if token in stop_words or len(token) < 2:
                continue
            if token not in terms:
                terms.append(token)
        return terms

    @staticmethod
    def _matches_query(row: dict[str, Any], query: str, terms: list[str]) -> bool:
        values = " ".join(str(row.get(key) or "") for key in (
            "goods_id", "sku_id", "goods_no", "sku_no", "goods_name", "sku_name", "sku_barcode",
        )).casefold()
        direct = _compact(query)
        compact = _compact(values)
        code_terms = [term for term in terms if InventoryService._looks_like_code(term)]
        if code_terms:
            # A code is a stronger identifier than surrounding prose such as
            # “这个库存给我”; match it exactly and ignore the prose tokens.
            return any(InventoryService._row_has_code(row, [term]) for term in code_terms)
        if direct and direct in compact:
            return True
        if not terms:
            return False
        return all(term.casefold().replace(" ", "") in compact for term in terms)

    @staticmethod
    def _looks_like_code(term: str) -> bool:
        return bool(_CODE_PATTERN.fullmatch(_compact(term)))

    @staticmethod
    def _row_has_code(row: dict[str, Any], code_terms: list[str]) -> bool:
        identifiers = ("goods_no", "sku_no", "sku_barcode", "sku_id", "goods_id")
        values = {_compact(row.get(field)) for field in identifiers if row.get(field)}
        return any(_compact(term) in values for term in code_terms)

    @staticmethod
    def _matched_by(row: dict[str, Any], terms: list[str]) -> list[str]:
        code_terms = [term for term in terms if InventoryService._looks_like_code(term)]
        labels = ("goods_no", "sku_no", "sku_barcode", "sku_id", "goods_id", "goods_name", "sku_name")
        matched: list[str] = []
        if code_terms:
            for field in labels[:5]:
                if InventoryService._row_has_code({field: row.get(field)}, code_terms):
                    matched.append(field)
            return matched
        compact_values = {field: _compact(row.get(field)) for field in labels}
        for term in terms:
            compact_term = _compact(term)
            for field, value in compact_values.items():
                if compact_term and compact_term in value and field not in matched:
                    matched.append(field)
        return matched

    @staticmethod
    def _is_size_term(term: str) -> bool:
        compact = term.casefold().replace(" ", "")
        return bool(re.fullmatch(r"(?:\d{1,3}|(?:\d)?x{0,3}[slm]|均)码", compact))

    def _freshness(self, conn: sqlite3.Connection, store_id: int | None, business_day: date | None) -> dict[str, Any]:
        params: tuple[Any, ...]
        if business_day is None:
            query = "select max(fetched_at) as fetched_at from jackyun_inventory_snapshots where (? is null or store_id = ?)"
            params = (store_id, store_id)
        else:
            query = "select max(fetched_at) as fetched_at from jackyun_inventory_snapshots where (? is null or store_id = ?) and business_day = ?"
            params = (store_id, store_id, business_day.isoformat())
        row = conn.execute(query, params).fetchone()
        latest = row["fetched_at"] if row and row["fetched_at"] else None
        latest_available_from_snapshots = None
        if not latest and business_day is not None:
            available_row = conn.execute(
                "select max(fetched_at) as fetched_at from jackyun_inventory_snapshots where (? is null or store_id = ?)",
                (store_id, store_id),
            ).fetchone()
            latest_available_from_snapshots = available_row["fetched_at"] if available_row and available_row["fetched_at"] else None
        status_row = conn.execute("select status, latest_business_day, latest_snapshot_at, last_attempt_at from jackyun_inventory_sync_status where store_id = ?", (store_id or 0,)).fetchone()
        status = dict(status_row) if status_row else {}
        if latest and status.get("latest_snapshot_at") and (business_day is None or status.get("latest_business_day") == business_day.isoformat()):
            # The sync status is recorded immediately after the full API
            # response is persisted, so it is the most accurate collection
            # timestamp for the current business-day snapshot.
            latest = max(str(latest), str(status["latest_snapshot_at"]))
        # For an explicitly requested day, never display the latest snapshot
        # from another day as if it belonged to the requested day.
        if not latest and (business_day is None or status.get("latest_business_day") == business_day.isoformat()):
            latest = status.get("latest_snapshot_at")
        age = None
        freshness_status = "unknown"
        if latest:
            try:
                parsed = datetime.fromisoformat(str(latest).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                age = max(0, int((datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() // 60))
                freshness_status = "fresh" if age <= 60 else "stale"
            except ValueError:
                freshness_status = "unknown"
        latest_available = None
        if not latest and business_day is not None:
            latest_available = status.get("latest_snapshot_at") or latest_available_from_snapshots
        latest_business_day = business_day.isoformat() if business_day else status.get("latest_business_day")
        return {
            "latest_snapshot_at": latest,
            "latest_available_snapshot_at": latest_available,
            "last_attempt_at": status.get("last_attempt_at"),
            "latest_business_day": latest_business_day,
            "snapshot_age_minutes": age,
            "freshness_status": freshness_status,
        }

    def record_sync_status(self, *, store_id: int, status: str, latest_business_day: date | None = None, latest_snapshot_at: str | None = None, row_count: int = 0, error_message: str | None = None) -> None:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.database.connect(initialize=True, read_only=False) as conn:
            conn.execute(
                """
                insert into jackyun_inventory_sync_status (store_id, status, latest_business_day, latest_snapshot_at, last_attempt_at, row_count, error_message)
                values (?, ?, ?, ?, ?, ?, ?)
                on conflict(store_id) do update set status=excluded.status,
                    latest_business_day=coalesce(excluded.latest_business_day, jackyun_inventory_sync_status.latest_business_day),
                    latest_snapshot_at=coalesce(excluded.latest_snapshot_at, jackyun_inventory_sync_status.latest_snapshot_at),
                    last_attempt_at=excluded.last_attempt_at,
                    row_count=excluded.row_count, error_message=excluded.error_message
                """,
                (store_id, status, latest_business_day.isoformat() if latest_business_day else None, latest_snapshot_at, now, row_count, error_message),
            )
            conn.commit()

    def get_sync_status(self, store_id: int | None) -> dict[str, Any]:
        with self.database.connect() as conn:
            if store_id is None:
                row = conn.execute(
                    "select * from jackyun_inventory_sync_status order by last_attempt_at desc limit 1"
                ).fetchone()
            else:
                row = conn.execute(
                    "select * from jackyun_inventory_sync_status where store_id = ?", (store_id,)
                ).fetchone()
            status = dict(row) if row else {
                "store_id": store_id,
                "status": "never_run",
                "latest_business_day": None,
                "latest_snapshot_at": None,
                "last_attempt_at": None,
                "row_count": 0,
                "error_message": None,
            }
            if status.get("error_message"):
                status["error_message"] = re.sub(r"https?://\S+", "[接口地址]", str(status["error_message"]))[:300]
            freshness = self._freshness(conn, store_id, None)
        master = self.get_master_sync(store_id)
        master_status = "success" if master.get("goods_status") == master.get("package_status") == "success" else "partial" if master else "never_run"
        return {
            **status, **freshness,
            "master_business_day": master.get("business_day"),
            "master_status": master_status,
            "goods_status": master.get("goods_status", "never_run"),
            "package_status": master.get("package_status", "never_run"),
            "goods_master_count": int(master.get("goods_count") or 0),
            "package_count": int(master.get("package_count") or 0),
            "component_count": int(master.get("component_count") or 0),
            "master_last_attempt_at": master.get("last_attempt_at"),
            "master_finished_at": master.get("finished_at"),
            "master_error_message": master.get("error_message"),
        }

    @staticmethod
    def _latest_day(conn: sqlite3.Connection, store_id: int | None) -> date | None:
        row = conn.execute("select max(business_day) as day from jackyun_inventory_snapshots where (? is null or store_id = ?)", (store_id, store_id)).fetchone()
        return date.fromisoformat(row["day"]) if row and row["day"] else None

    def _package_result(self, conn: sqlite3.Connection, store_id: int | None, business_day: date, product: dict[str, Any]) -> dict[str, Any]:
        package_store_id = int(product.get("store_id") or store_id or 0)
        components = [dict(row) for row in conn.execute(
            "select * from jackyun_package_components where store_id = ? and package_goods_id = ? and package_sku_id = ?",
            (package_store_id, product.get("goods_id"), product.get("sku_id")),
        ).fetchall()]
        stocks = [dict(row) for row in conn.execute(
            "select * from jackyun_inventory_snapshots where store_id = ? and business_day = ?",
            (package_store_id, business_day.isoformat()),
        ).fetchall()]
        calculation = calculate_package_inventory(components, stocks)
        # Kept for legacy AI/API compatibility. The inventory analysis page
        # intentionally does not expose or use these derived fields.
        result = {"item_type": "package", **product, "business_day": business_day, "available_quantity": calculation["assemblable_quantity"], "assemblable_quantity": calculation["assemblable_quantity"], **calculation, "components": components, "warnings": [] if components else ["组合货品主档已找到，但组成明细尚未同步。"]}
        return self._enrich_item(result)

    @staticmethod
    def _same_product(stock: dict[str, Any], product: dict[str, Any]) -> bool:
        for key in ("sku_id", "goods_id", "sku_barcode", "goods_no"):
            left, right = _key(stock.get(key)), _key(product.get(key))
            if left and right and left == right:
                return True
        return False

    @staticmethod
    def _ordinary_results(rows: list[dict[str, Any]], business_day: date) -> list[dict[str, Any]]:
        grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for row in rows:
            key = (row.get("goods_id"), row.get("sku_id"), row.get("goods_no"), row.get("sku_barcode"))
            grouped.setdefault(key, []).append(row)
        results = []
        for group in grouped.values():
            first = group[0]
            item = {
                "item_type": "sku", **{key: first.get(key) for key in ("goods_id", "sku_id", "goods_no", "sku_no", "goods_name", "sku_name", "sku_barcode")},
                "business_day": business_day,
                "available_quantity": float(sum(_decimal(row.get("available_quantity")) for row in group)),
                "warehouses": [{"warehouse_id": row.get("warehouse_id"), "warehouse_name": row.get("warehouse_name"), "assemblable_quantity": int(_decimal(row.get("available_quantity"))), "components": []} for row in group],
                "formula": "普通 SKU 库存=各仓可用库存之和",
                "warnings": [],
            }
            results.append(InventoryService._enrich_item(item))
        return results

    @staticmethod
    def _enrich_item(item: dict[str, Any]) -> dict[str, Any]:
        """Add stable business attributes without overriding platform fields.

        Some inventory APIs expose only opaque codes and a free-form SKU name.
        These derived fields make the result usable by the UI while keeping the
        original identifiers intact and leaving unknown attributes as null.
        """
        text_sources = [
            str(item.get("sku_name") or ""),
            str(item.get("goods_name") or ""),
            str(item.get("goods_no") or ""),
            str(item.get("sku_no") or ""),
        ]
        size = None
        for source in text_sources[:2]:
            match = _SIZE_PATTERN.search(source)
            if match:
                size = match.group(1).upper()
                break
        if not size:
            for source in text_sources[2:]:
                match = re.match(r"(?i)^[a-z]+\d{2}(XXXXL|XXXL|XXL|XL|NB|L|M|S)\d+$", source.strip())
                if match:
                    size = match.group(1).upper()
                    break

        pieces: int | None = None
        for source in text_sources[:2]:
            match = re.search(r"(?<!\d)(\d{1,4})\s*(?:片|抽|包)", source)
            if match:
                pieces = int(match.group(1))
                break
        if pieces is None and size:
            for source in text_sources[2:]:
                match = re.match(r"(?i)^[a-z]+\d{2}(?:XXXXL|XXXL|XXL|XL|NB|L|M|S)(\d+)$", source.strip())
                if match:
                    pieces = int(match.group(1))
                    break

        item.setdefault("series", item.get("product_series"))
        item.setdefault("specification", item.get("product_specification"))
        item["size"] = item.get("size") or size
        item["pieces"] = item.get("pieces") if item.get("pieces") is not None else pieces
        return item
