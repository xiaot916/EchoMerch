from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import require_permission, resolve_store_scope
from app.integrations.legacy_ador.repository import LegacyDatabaseNotConfigured
from app.modules.analytics.schemas import DashboardResponse, FlashSaleAnalysisResponse, ProductAnalysisResponse, ProductMetric, PromotionProductListResponse, PromotionWorkbenchResponse, TrafficTreeNode, UtryAnalysisResponse
from app.modules.analytics.service import AnalyticsService
from app.modules.access.service import Principal
from app.modules.market.schemas import MarketInsightResponse
from app.modules.market.service import MarketInsightService
from app.core.config import settings

router = APIRouter()


def get_analytics_service() -> AnalyticsService:
    return AnalyticsService()


def get_market_insight_service() -> MarketInsightService:
    from pathlib import Path

    return MarketInsightService(Path(settings.local_database_path))


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    store_id: int | None = Query(default=None, ge=1),
    service: AnalyticsService = Depends(get_analytics_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> DashboardResponse:
    try:
        return service.get_dashboard(
            start_date=start_date,
            end_date=end_date,
            store_id=resolve_store_scope(principal, store_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LegacyDatabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/market", response_model=MarketInsightResponse)
def get_market_insights(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    rank_type: str = Query(default="all", pattern="^(all|shop|item|content)$"),
    keyword_type: str = Query(default="all", pattern="^(all|core|search|trend|modify)$"),
    query: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=20, ge=5, le=100),
    service: MarketInsightService = Depends(get_market_insight_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> MarketInsightResponse:
    # Market snapshots are platform scoped and intentionally do not accept a
    # store_id: a store's own sales facts must not be mixed with category rank.
    del principal
    try:
        return MarketInsightResponse.model_validate(service.get_insights(
            start_date=start_date,
            end_date=end_date,
            rank_type=rank_type,
            keyword_type=keyword_type,
            query=query,
            limit=limit,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/promotions", response_model=PromotionWorkbenchResponse)
def get_promotion_workbench(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    store_id: int | None = Query(default=None, ge=1),
    service: AnalyticsService = Depends(get_analytics_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> PromotionWorkbenchResponse:
    try:
        source = service._source_for_store(resolve_store_scope(principal, store_id))
        minimum, maximum = source.get_date_bounds()
        default_start, default_end = source.default_range(maximum)
        selected_start = start_date or default_start
        selected_end = end_date or default_end
        if selected_start < minimum or selected_end > maximum or selected_start > selected_end:
            raise ValueError("推广分析日期范围无效")
        getter = getattr(source, "get_promotion_workbench", None)
        if getter is None:
            raise RuntimeError("当前数据源不支持推广工作台")
        return getter(selected_start, selected_end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LegacyDatabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/marketing/flash-sale", response_model=FlashSaleAnalysisResponse)
def get_flash_sale_analysis(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    store_id: int | None = Query(default=None, ge=1),
    service: AnalyticsService = Depends(get_analytics_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> FlashSaleAnalysisResponse:
    try:
        source = service._source_for_store(resolve_store_scope(principal, store_id))
        getter = getattr(source, "get_flash_sale_analysis", None)
        if getter is None:
            raise RuntimeError("当前数据源不支持淘宝秒杀分析")
        minimum, maximum = source.get_date_bounds()
        flash_minimum, flash_maximum = minimum, maximum
        warehouse = getattr(source, "_warehouse", None)
        if warehouse is not None:
            rows = source._rows(
                '''select min("业务日期") as first_date, max("业务日期") as latest_date
                   from store_daily_taobao_flash_sale_overviews where "店铺ID" = ?''',
                source._store_id,
            )
            if rows and rows[0].get("first_date"):
                flash_minimum = date.fromisoformat(str(rows[0]["first_date"]))
            if rows and rows[0].get("latest_date"):
                flash_maximum = date.fromisoformat(str(rows[0]["latest_date"]))
        selected_end = end_date or flash_maximum
        selected_start = start_date or max(flash_minimum, selected_end - timedelta(days=29))
        if selected_start > selected_end:
            raise ValueError("淘宝秒杀日期范围无效")
        if selected_start < flash_minimum or selected_end > flash_maximum:
            raise ValueError(f"淘宝秒杀可用日期为 {flash_minimum.isoformat()} 至 {flash_maximum.isoformat()}")
        return getter(selected_start, selected_end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LegacyDatabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/marketing/utry", response_model=UtryAnalysisResponse)
def get_utry_analysis(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    store_id: int | None = Query(default=None, ge=1),
    service: AnalyticsService = Depends(get_analytics_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> UtryAnalysisResponse:
    try:
        source = service._source_for_store(resolve_store_scope(principal, store_id))
        getter = getattr(source, "get_utry_analysis", None)
        if getter is None:
            raise RuntimeError("当前数据源不支持 U先分析")
        rows = source._rows(
            '''select min(first_date) as first_date, max(latest_date) as latest_date
               from (
                   select min("业务日期") as first_date, max("业务日期") as latest_date
                   from store_daily_utry_sample_overviews where "店铺ID" = ?
                   union all
                   select min("业务日期") as first_date, max("业务日期") as latest_date
                   from store_daily_utry_repurchase_overviews where "店铺ID" = ?
               )''',
            source._store_id, source._store_id,
        )
        if not rows or not rows[0].get("latest_date"):
            raise RuntimeError("当前店铺没有 U先派样或复购数据")
        minimum = date.fromisoformat(str(rows[0]["first_date"]))
        maximum = date.fromisoformat(str(rows[0]["latest_date"]))
        selected_end = end_date or maximum
        selected_start = start_date or max(minimum, selected_end - timedelta(days=29))
        if selected_start > selected_end:
            raise ValueError("U先分析日期范围无效")
        if selected_start < minimum or selected_end > maximum:
            raise ValueError(f"U先可用日期为 {minimum.isoformat()} 至 {maximum.isoformat()}")
        return getter(selected_start, selected_end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LegacyDatabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _get_promotion_product_items(
    dataset: str,
    *,
    start_date: date | None,
    end_date: date | None,
    store_id: int | None,
    search: str | None,
    page: int,
    page_size: int,
    sort: str,
    service: AnalyticsService,
    principal: Principal,
) -> PromotionProductListResponse:
    try:
        source = service._source_for_store(resolve_store_scope(principal, store_id))
        bounds_getter = getattr(source, "get_promotion_product_item_bounds", None)
        items_getter = getattr(source, "get_promotion_product_items", None)
        if bounds_getter is None or items_getter is None:
            raise RuntimeError("当前数据源不支持营销商品明细")
        minimum, maximum = bounds_getter(dataset)
        selected_end = end_date or maximum
        selected_start = start_date or max(minimum, selected_end - timedelta(days=29))
        if selected_start > selected_end:
            raise ValueError("商品明细日期范围无效")
        requested_start, requested_end = selected_start, selected_end
        selected_start = max(selected_start, minimum)
        selected_end = min(selected_end, maximum)
        if selected_start > selected_end:
            raise ValueError(f"商品明细可用日期为 {minimum.isoformat()} 至 {maximum.isoformat()}")
        result = items_getter(dataset, selected_start, selected_end, search=search, page=page, page_size=page_size, sort=sort)
        result.available_start = minimum
        result.available_end = maximum
        result.missing_dates = [
            requested_day
            for offset in range((requested_end - requested_start).days + 1)
            if (requested_day := requested_start + timedelta(days=offset)) < minimum or requested_day > maximum
        ]
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LegacyDatabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/marketing/bybt/items", response_model=PromotionProductListResponse)
def get_bybt_product_items(
    start_date: date | None = Query(default=None), end_date: date | None = Query(default=None),
    store_id: int | None = Query(default=None, ge=1), search: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100),
    sort: str = Query(default="paid_amount", pattern="^(paid_amount|paid_order_count|visitors)$"),
    service: AnalyticsService = Depends(get_analytics_service), principal: Principal = Depends(require_permission("analytics.read")),
) -> PromotionProductListResponse:
    return _get_promotion_product_items("bybt", start_date=start_date, end_date=end_date, store_id=store_id, search=search, page=page, page_size=page_size, sort=sort, service=service, principal=principal)


@router.get("/marketing/flash-sale/items", response_model=PromotionProductListResponse)
def get_flash_sale_product_items(
    start_date: date | None = Query(default=None), end_date: date | None = Query(default=None),
    store_id: int | None = Query(default=None, ge=1), search: str | None = Query(default=None, max_length=80),
    page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=100),
    sort: str = Query(default="paid_amount", pattern="^(paid_amount|paid_order_count|visitors)$"),
    service: AnalyticsService = Depends(get_analytics_service), principal: Principal = Depends(require_permission("analytics.read")),
) -> PromotionProductListResponse:
    return _get_promotion_product_items("flash_sale", start_date=start_date, end_date=end_date, store_id=store_id, search=search, page=page, page_size=page_size, sort=sort, service=service, principal=principal)


def _product_range(source: object, start_date: date | None, end_date: date | None) -> tuple[date, date]:
    minimum, maximum = source.get_product_date_bounds()
    default_start, default_end = source.default_range(maximum)
    selected_start = start_date or default_start
    selected_end = end_date or default_end
    if selected_start < minimum or selected_end > maximum or selected_start > selected_end:
        raise ValueError("商品分析日期范围无效")
    return selected_start, selected_end


@router.get("/products", response_model=list[ProductMetric])
def list_products(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    store_id: int | None = Query(default=None, ge=1),
    service: AnalyticsService = Depends(get_analytics_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> list[ProductMetric]:
    try:
        source = service._source_for_store(resolve_store_scope(principal, store_id))
        selected_start, selected_end = _product_range(source, start_date, end_date)
        getter = getattr(source, "get_products", None)
        if getter is None:
            return source.get_top_products(selected_start, selected_end)
        return getter(selected_start, selected_end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LegacyDatabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/traffic-tree", response_model=list[TrafficTreeNode])
def get_traffic_tree(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    store_id: int | None = Query(default=None, ge=1),
    service: AnalyticsService = Depends(get_analytics_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> list[TrafficTreeNode]:
    try:
        source = service._source_for_store(resolve_store_scope(principal, store_id))
        minimum, maximum = source.get_date_bounds()
        default_start, default_end = source.default_range(maximum)
        selected_start = start_date or default_start
        selected_end = end_date or default_end
        if selected_start < minimum or selected_end > maximum or selected_start > selected_end:
            raise ValueError("流量分析日期范围无效")
        getter = getattr(source, "get_traffic_tree", None)
        if getter is None:
            return [
                TrafficTreeNode(
                    id=f"traffic-1-{item.source_name}",
                    level=1,
                    name=item.source_name,
                    path=[item.source_name],
                    visitors=item.visitors,
                    paid_amount=item.paid_amount,
                    buyers=item.buyers,
                    new_visitors=item.new_visitors,
                    add_cart_users=item.add_cart_users,
                    favorite_users=item.favorite_users,
                    conversion_rate=item.conversion_rate,
                    uv_value=item.uv_value,
                )
                for item in source.get_traffic_sources(selected_start, selected_end)
            ]
        return getter(selected_start, selected_end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LegacyDatabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/products/{product_id}", response_model=ProductAnalysisResponse)
def get_product_analysis(
    product_id: str,
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    store_id: int | None = Query(default=None, ge=1),
    service: AnalyticsService = Depends(get_analytics_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> ProductAnalysisResponse:
    try:
        source = service._source_for_store(resolve_store_scope(principal, store_id))
        selected_start, selected_end = _product_range(source, start_date, end_date)
        getter = getattr(source, "get_product_analysis", None)
        if getter is None:
            raise RuntimeError("当前数据源不支持单品分析")
        response = getter(selected_start, selected_end, product_id)
        if response.product is None:
            raise HTTPException(status_code=404, detail="未找到该商品或所选日期没有商品数据")
        return response
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LegacyDatabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
