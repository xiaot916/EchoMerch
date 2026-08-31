from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from app.modules.analytics.service import AnalyticsService
from app.modules.ai.catalog import DATASET_CATALOG, get_dataset
from app.modules.ai.query import AnalyticsQueryService
from app.modules.ai.schemas import (
    AnalysisContext,
    CoverageSummary,
    EvidenceRecord,
    MCPEnvelope,
    MCPToolDescriptor,
    MetricValue,
    MCPQueryRequest,
)
from app.core.config import settings
from app.modules.inventory.service import InventoryService
from app.modules.market.schemas import MarketInsightResponse
from app.modules.market.service import MarketInsightService
from app.modules.reviews.service import ReviewService


def _number(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (float, int)):
        return value
    return float(value)


def _optional_number(value: Any) -> float | int | None:
    if value is None or value == "":
        return None
    return _number(value)


class CommerceMCPService:
    """Read-only MCP boundary over EchoMerch's normalized analytics services."""

    _descriptors = (
        MCPToolDescriptor(
            name="data.catalog",
            description="列出全部可分析数据集，或描述指定数据集的维度、指标、口径和粒度。",
            input_schema={"type": "object", "properties": {"dataset": {"type": "string"}}},
        ),
        MCPToolDescriptor(
            name="data.query",
            description="按白名单数据集、维度、指标、过滤和排序执行只读聚合查询；不接受 SQL。",
            input_schema={"type": "object", "required": ["dataset"], "properties": {"dataset": {"type": "string"}, "dimensions": {"type": "array", "items": {"type": "string"}}, "measures": {"type": "array", "items": {"type": "string"}}, "filters": {"type": "object"}, "order_by": {"type": "array", "items": {"type": "string"}}, "limit": {"type": "integer", "minimum": 1, "maximum": 1000}, "store_id": {"type": "integer"}, "start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}, "history_scope": {"type": "string", "enum": ["selected", "all"]}}},
        ),
        MCPToolDescriptor(
            name="data.compare_periods",
            description="对当前区间和紧邻的等长上一周期做统一指标对比，可按维度分组；覆盖不完整时不输出误导性涨跌幅。",
            input_schema={"type": "object", "required": ["dataset", "measures"], "properties": {"dataset": {"type": "string"}, "dimensions": {"type": "array", "items": {"type": "string"}}, "measures": {"type": "array", "items": {"type": "string"}}, "filters": {"type": "object"}, "order_by": {"type": "array", "items": {"type": "string"}}, "limit": {"type": "integer", "minimum": 1, "maximum": 1000}, "store_id": {"type": "integer"}, "start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}}},
        ),
        MCPToolDescriptor(
            name="data.coverage",
            description="检查一个或多个数据集的日期覆盖、未采集日期和平台确认无数据日期。",
            input_schema={"type": "object", "properties": {"dataset": {"type": "string"}, "datasets": {"type": "array", "items": {"type": "string"}}, "store_id": {"type": "integer"}, "start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}, "history_scope": {"type": "string", "enum": ["selected", "all"]}}},
        ),
        MCPToolDescriptor(
            name="data.freshness",
            description="返回各数据集最新业务日期、首个业务日期和相对今天的业务延迟；用于区分数据尚未到达与平台无数据。",
            input_schema={"type": "object", "properties": {"datasets": {"type": "array", "items": {"type": "string"}}, "store_id": {"type": "integer"}}},
        ),
        MCPToolDescriptor(
            name="inventory.query",
            description="查询最新吉客云普通 SKU 库存，或查询组合货品主档及组成关系；组合货品不计算组合库存。",
            input_schema={"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}, "store_id": {"type": "integer"}, "business_day": {"type": "string", "format": "date"}}},
        ),
        MCPToolDescriptor(
            name="products.search",
            description="按商品 ID、商品名称、产品系列、类型或定位搜索商品主档，支持服务端分页。",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}, "product_id": {"type": "string"}, "product_name": {"type": "string"}, "series": {"type": "string"}, "product_type": {"type": "string"}, "positioning": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}, "offset": {"type": "integer", "minimum": 0}, "store_id": {"type": "integer"}}},
        ),
        MCPToolDescriptor(
            name="products.get_series_profile",
            description="按产品系列和可选商品类型聚合返回销售、转化、推广和商品明细画像。",
            input_schema={"type": "object", "required": ["series"], "properties": {"series": {"type": "string"}, "positioning": {"type": "string"}, "product_type": {"type": "string"}, "store_id": {"type": "integer"}, "start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}}},
        ),
        MCPToolDescriptor(
            name="products.get_profile",
            description="按商品 ID 返回商品主档、销售、推广、当前价格、红线价风险及百补/秒杀活动画像。",
            input_schema={"type": "object", "required": ["product_id"], "properties": {"product_id": {"type": "string"}, "store_id": {"type": "integer"}, "start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}}},
        ),
        MCPToolDescriptor(
            name="mini.get_diagnosis",
            description="识别店铺标题/属性中的 MINI、尝鲜装或试用装商品，并按商品 ID 联动成交、推广、评价、问大家、U先派样与复购证据。",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}, "product_id": {"type": "string"}, "positioning": {"type": "string"}, "store_id": {"type": "integer"}, "start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}}},
        ),
        MCPToolDescriptor(
            name="products.get_structure_profile",
            description="比较当前与上一周期的系列、类型、商品客单价和买家结构，定位客单价变化贡献。",
            input_schema={"type": "object", "properties": {"store_id": {"type": "integer"}, "start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}}},
        ),
        MCPToolDescriptor(
            name="customer_service.get_diagnosis",
            description="比较客服销售、咨询接待漏斗、响应满意度和客服账号表现。",
            input_schema={"type": "object", "properties": {"store_id": {"type": "integer"}, "start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}}},
        ),
        MCPToolDescriptor(
            name="customers.get_diagnosis",
            description="返回客户三段人群、总支付与老客差额推导的首次购买指标、客单结构和分类对账差异。",
            input_schema={"type": "object", "properties": {"store_id": {"type": "integer"}, "start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}}},
        ),
        MCPToolDescriptor(
            name="utry.get_repurchase_diagnosis",
            description="返回 U先最新回购快照、按日趋势、商品贡献、正装绑定与回购权益配置；滚动窗口不跨日累加。",
            input_schema={"type": "object", "properties": {"store_id": {"type": "integer"}, "start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}},
        ),
        MCPToolDescriptor(
            name="reviews.get_diagnosis",
            description="返回评价问题分类、风险系列/商品、代表评价以及问大家未回答情况，并与成交数据保持可关联的商品 ID。",
            input_schema={"type": "object", "properties": {"start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}, "product_id": {"type": "string"}, "series": {"type": "string"}}},
        ),
        MCPToolDescriptor(
            name="brand_assets.get_diagnosis",
            description="返回品牌消费者资产、关系深化、成交、会员成交及品牌指标的当前期/上一期证据。",
            input_schema={"type": "object", "properties": {"store_id": {"type": "integer"}, "brand_id": {"type": "string"}, "start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}}},
        ),
        MCPToolDescriptor(
            name="overview.get_store_summary",
            description="返回店铺支付、退款、推广分项、淘宝客佣金、总成本和经营费比。",
            input_schema={"type": "object", "properties": {"store_id": {"type": "integer"}, "start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}}},
        ),
        MCPToolDescriptor(
            name="overview.get_metric_trend",
            description="按业务日期返回经营概览核心指标趋势。",
            input_schema={"type": "object", "properties": {"store_id": {"type": "integer"}, "start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}}},
        ),
        MCPToolDescriptor(
            name="promotions.get_efficiency",
            description="返回全量推广投入产出、低效计划数量和低效花费占比。",
            input_schema={"type": "object", "properties": {"store_id": {"type": "integer"}, "start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}}},
        ),
        MCPToolDescriptor(
            name="promotions.get_drilldown",
            description="按场景、计划、商品、单元、关键词或人群筛选并分页下钻推广数据。",
            input_schema={"type": "object", "properties": {"level": {"type": "string"}, "scene": {"type": "string"}, "campaign_id": {"type": "string"}, "product_id": {"type": "string"}, "query": {"type": "string"}, "min_spend": {"type": "number"}, "max_roi": {"type": "number"}, "efficiency": {"type": "string"}, "order_by": {"type": "string"}, "page": {"type": "integer", "minimum": 1}, "page_size": {"type": "integer", "minimum": 1, "maximum": 200}, "store_id": {"type": "integer"}, "start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}}},
        ),
        MCPToolDescriptor(
            name="pricing.get_risk_items",
            description="返回淘宝红线价风险商品，支持商品和分页筛选。",
            input_schema={"type": "object", "properties": {"product_id": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}, "offset": {"type": "integer", "minimum": 0}, "store_id": {"type": "integer"}}},
        ),
        MCPToolDescriptor(
            name="pricing.get_current_prices",
            description="返回淘宝当前价格和关注标签，支持商品、关注状态和分页筛选。",
            input_schema={"type": "object", "properties": {"product_id": {"type": "string"}, "query": {"type": "string"}, "attention": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}, "offset": {"type": "integer", "minimum": 0}, "store_id": {"type": "integer"}}},
        ),
        MCPToolDescriptor(
            name="activities.get_snapshots",
            description="返回百补和秒杀商品活动快照，区分快照类型与平台状态。",
            input_schema={"type": "object", "properties": {"snapshot_type": {"type": "string"}, "product_id": {"type": "string"}, "status": {"type": "string"}, "query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 200}, "offset": {"type": "integer", "minimum": 0}, "store_id": {"type": "integer"}}},
        ),
        MCPToolDescriptor(
            name="market.get_insights",
            description="读取平台市场排行与搜索词快照，返回竞品、商品、内容、搜索需求、覆盖状态和可验证机会信号；平台观察不等于店铺成交。",
            input_schema={"type": "object", "properties": {"start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}, "rank_type": {"type": "string", "enum": ["all", "shop", "item", "content"]}, "keyword_type": {"type": "string", "enum": ["all", "core", "search", "trend", "modify"]}, "query": {"type": "string"}, "limit": {"type": "integer", "minimum": 5, "maximum": 100}}},
        ),
        MCPToolDescriptor(
            name="market.get_keyword_opportunities",
            description="按搜索词类型和可选指标筛选平台关键词机会，返回排名变化、持续天数、区间指标和验证动作；不代表本店成交增量。",
            input_schema={"type": "object", "properties": {"start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}, "keyword_type": {"type": "string", "enum": ["all", "core", "search", "trend", "modify"]}, "query": {"type": "string"}, "min_click_rate": {"type": "number"}, "min_pay_conversion": {"type": "number"}, "include_unrelated": {"type": "boolean"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}},
        ),
        MCPToolDescriptor(
            name="market.get_competitor_movements",
            description="返回市场店铺、商品或内容排名上升/下降样本，保留排名变化证据和覆盖状态；不把排名变化当作成交因果。",
            input_schema={"type": "object", "properties": {"start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}, "rank_type": {"type": "string", "enum": ["all", "shop", "item", "content"]}, "query": {"type": "string"}, "direction": {"type": "string", "enum": ["all", "rising", "falling", "stable"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}},
        ),
        MCPToolDescriptor(
            name="market.match_store_products",
            description="把市场关键词/竞品样本与本店商品主档、访客、支付和转化对照，明确无匹配、市场信号弱、对齐或较强承接；市场信号不等于本店增量。",
            input_schema={"type": "object", "properties": {"start_date": {"type": "string", "format": "date"}, "end_date": {"type": "string", "format": "date"}, "query": {"type": "string"}, "product_type": {"type": "string"}, "series": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}, "store_id": {"type": "integer"}}},
        ),
        # Compatibility aliases for clients created before the generic MCP
        # catalog existed. New Skills must use data.* tools above.
        MCPToolDescriptor(name="analytics.get_overview", description="兼容别名：店铺经营总览。请新调用使用 data.query/data.compare_periods。", input_schema={"type": "object"}),
        MCPToolDescriptor(name="analytics.get_traffic_sources", description="兼容别名：流量来源。请新调用使用 data.query。", input_schema={"type": "object"}),
        MCPToolDescriptor(name="analytics.get_promotions", description="兼容别名：推广投入产出。请新调用使用 data.query。", input_schema={"type": "object"}),
        MCPToolDescriptor(name="reports.build_period_report", description="兼容别名：周期报告视图。请新调用先用 data.coverage，再使用业务 Skill。", input_schema={"type": "object"}),
    )

    def __init__(self, analytics: AnalyticsService | None = None) -> None:
        self.analytics = analytics or AnalyticsService()
        self.query_service = AnalyticsQueryService(self.analytics)
        self.inventory = InventoryService(Path(settings.local_database_path))
        self.market = MarketInsightService(Path(settings.local_database_path))
        self._handlers: dict[str, Callable[[int | None, date | None, date | None], MCPEnvelope]] = {
            "analytics.get_overview": self.get_overview,
            "analytics.get_traffic_sources": self.get_traffic_sources,
            "analytics.get_promotions": self.get_promotions,
            "reports.build_period_report": self.build_period_report,
        }

    def list_tools(self) -> list[MCPToolDescriptor]:
        return list(self._descriptors)

    def execute(self, tool: str, arguments: dict[str, Any]) -> MCPEnvelope:
        if tool == "inventory.query":
            return self.inventory_query(arguments)
        if tool == "data.catalog":
            return self.data_catalog(arguments)
        if tool == "data.query":
            return self.data_query(arguments)
        if tool == "data.compare_periods":
            return self.data_compare_periods(arguments)
        if tool == "data.coverage":
            return self.data_coverage(arguments)
        if tool == "data.freshness":
            return self.data_freshness(arguments)
        if tool == "products.search":
            return self.products_search(arguments)
        if tool == "products.get_series_profile":
            return self.products_get_series_profile(arguments)
        if tool == "products.get_profile":
            return self.products_get_profile(arguments)
        if tool == "mini.get_diagnosis":
            return self.mini_get_diagnosis(arguments)
        if tool == "products.get_structure_profile":
            return self.products_get_structure_profile(arguments)
        if tool == "customer_service.get_diagnosis":
            return self.customer_service_get_diagnosis(arguments)
        if tool == "customers.get_diagnosis":
            return self.customers_get_diagnosis(arguments)
        if tool == "utry.get_repurchase_diagnosis":
            return self.utry_get_repurchase_diagnosis(arguments)
        if tool == "reviews.get_diagnosis":
            return self.reviews_get_diagnosis(arguments)
        if tool == "brand_assets.get_diagnosis":
            return self.brand_assets_get_diagnosis(arguments)
        if tool == "overview.get_store_summary":
            return self.overview_get_store_summary(arguments)
        if tool == "overview.get_metric_trend":
            return self.overview_get_metric_trend(arguments)
        if tool == "promotions.get_efficiency":
            return self.promotions_get_efficiency(arguments)
        if tool == "promotions.get_drilldown":
            return self.promotions_get_drilldown(arguments)
        if tool == "pricing.get_risk_items":
            return self.pricing_get_risk_items(arguments)
        if tool == "pricing.get_current_prices":
            return self.pricing_get_current_prices(arguments)
        if tool == "activities.get_snapshots":
            return self.activities_get_snapshots(arguments)
        if tool == "market.get_insights":
            return self.market_get_insights(arguments)
        if tool == "market.get_keyword_opportunities":
            return self.market_get_keyword_opportunities(arguments)
        if tool == "market.get_competitor_movements":
            return self.market_get_competitor_movements(arguments)
        if tool == "market.match_store_products":
            return self.market_match_store_products(arguments)
        handler = self._handlers.get(tool)
        if handler is None:
            raise ValueError(f"Unknown MCP tool: {tool}")
        if tool == "reports.build_period_report":
            return self.build_period_report(
                arguments.get("store_id"),
                self._parse_date(arguments.get("start_date")),
                self._parse_date(arguments.get("end_date")),
                str(arguments.get("report_type") or "daily"),
            )
        return handler(arguments.get("store_id"), self._parse_date(arguments.get("start_date")), self._parse_date(arguments.get("end_date")))

    def inventory_query(self, arguments: dict[str, Any]) -> MCPEnvelope:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("inventory.query requires query")
        selected_day = self._parse_date(arguments.get("business_day"))
        result = self.inventory.query(store_id=arguments.get("store_id"), query=query, business_day=selected_day)
        business_day = result.get("business_day")
        business_day_text = business_day.isoformat() if isinstance(business_day, date) else str(business_day) if business_day else None
        context_day = date.fromisoformat(business_day_text) if business_day_text else date.today()
        items = result.get("items", [])
        ordinary_items = [item for item in items if item.get("item_type") != "package"]
        has_snapshot = bool(result.get("snapshot_row_count") or result.get("latest_snapshot_at")) and result.get("reason") != "date_not_available"
        data = {
            **result,
            # Keep inventory's point-in-time semantics explicit.  The generic
            # coverage field remains for compatibility, while these names are
            # used by the inventory UI and AI prompt context.
            "inventory_business_day": business_day_text,
            "snapshot_collected_at": result.get("latest_snapshot_at"),
            "last_collection_attempt_at": result.get("last_attempt_at"),
        }
        return self._envelope(
            tool="inventory.query",
            context=self._context(arguments.get("store_id"), context_day, context_day),
            status=result["status"],
            data=data,
            metrics=[MetricValue(
                id="available_quantity",
                label="可用库存",
                value=sum(float(item.get("available_quantity") or 0) for item in ordinary_items),
                unit="item",
                formula="普通SKU为各仓可用库存之和；组合货品仅返回组成关系，库存请查询组成普通SKU。",
                source="jackyun_inventory_snapshots",
            )],
            coverage=CoverageSummary(expected_days=1, covered_days=1 if has_snapshot else 0, latest_data_date=business_day_text if has_snapshot else None),
            evidence=[EvidenceRecord(dataset="吉客云库存", table="jackyun_inventory_snapshots", date_range=[business_day_text, business_day_text] if business_day_text else [], row_count=int(result.get("snapshot_row_count") or 0), note=f"库存业务日 {business_day_text or '--'}；快照采集时间 {result.get('latest_snapshot_at') or '--'}；组合货品关系来自 jackyun_package_components")],
            warnings=result.get("warnings", []),
        )

    def market_get_insights(self, arguments: dict[str, Any]) -> MCPEnvelope:
        """Expose platform market observations through the common MCP contract."""
        start_date = self._parse_date(arguments.get("start_date"))
        end_date = self._parse_date(arguments.get("end_date"))
        response = MarketInsightResponse.model_validate(self.market.get_insights(
            start_date=start_date,
            end_date=end_date,
            rank_type=str(arguments.get("rank_type") or "all"),
            keyword_type=str(arguments.get("keyword_type") or "all"),
            query=str(arguments.get("query") or "").strip() or None,
            limit=int(arguments.get("limit") or 20),
        ))
        payload = response.model_dump(mode="json")
        coverage_items = response.coverage
        expected_days = max((item.expected_days for item in coverage_items), default=0)
        covered_days = min((item.covered_days for item in coverage_items), default=0) if coverage_items else 0
        missing_dates = sorted({value.isoformat() for item in coverage_items for value in item.missing_dates})
        partial_datasets = [item.dataset for item in coverage_items if item.status == "partial"]
        empty_datasets = [item.dataset for item in coverage_items if item.status == "empty"]
        latest_dates = [item.latest_date.isoformat() for item in coverage_items if item.latest_date]
        coverage = CoverageSummary(
            expected_days=expected_days,
            covered_days=covered_days,
            missing_dates=missing_dates,
            missing_datasets=empty_datasets,
            partial_datasets=partial_datasets,
            latest_data_date=max(latest_dates) if latest_dates else None,
        )
        summary = response.summary
        metrics = [
            MetricValue(id="market_ranking_rows", label="市场排行记录", value=summary.ranking_rows, unit="row", formula="最新市场日全量排行记录数", source="sycm_market_rankings"),
            MetricValue(id="market_keyword_rows", label="搜索词样本", value=summary.keyword_rows, unit="row", formula="最新市场日全量搜索词记录数", source="sycm_market_keywords"),
            MetricValue(id="market_shop_count", label="头部店铺样本数", value=summary.shop_count, unit="shop", formula="最新市场日去重店铺数", source="sycm_market_rankings"),
            MetricValue(id="market_item_count", label="头部商品样本数", value=summary.item_count, unit="item", formula="最新市场日去重商品数", source="sycm_market_rankings"),
            MetricValue(id="market_content_count", label="内容/直播样本数", value=summary.content_count, unit="content", formula="最新市场日内容排行记录数", source="sycm_market_rankings"),
            MetricValue(id="market_competitor_movers", label="竞品异动样本数", value=len(response.competitive_signals), unit="row", formula="最新市场日排名发生变化的重点样本", source="sycm_market_rankings"),
            MetricValue(id="market_keyword_segments", label="搜索词分层数", value=len(response.keyword_segments), unit="segment", formula="按核心/搜索/趋势/修饰词分层", source="sycm_market_keywords"),
        ]
        evidence = [
            EvidenceRecord(dataset="市场排行", table="sycm_market_rankings", date_range=[response.range_start.isoformat(), response.range_end.isoformat()], row_count=summary.ranking_rows, note="平台店铺/商品/内容相对排行；不等于店铺支付金额"),
            EvidenceRecord(dataset="市场搜索词", table="sycm_market_keywords", date_range=[response.range_start.isoformat(), response.range_end.isoformat()], row_count=summary.keyword_rows, note="热度、点击率和支付转化保留平台原始区间"),
        ]
        warnings = list(dict.fromkeys([*response.diagnostics, *response.data_quality_flags]))
        status = "partial" if missing_dates or partial_datasets else "no_data" if not summary.ranking_rows and not summary.keyword_rows else "ok"
        return self._envelope(
            tool="market.get_insights",
            context=self._context(None, response.range_start, response.range_end),
            status=status,
            data=payload,
            metrics=metrics,
            coverage=coverage,
            evidence=evidence,
            provenance={"scope": "platform_market", "rank_date": summary.latest_rank_date.isoformat() if summary.latest_rank_date else None, "keyword_date": summary.latest_keyword_date.isoformat() if summary.latest_keyword_date else None},
            warnings=warnings,
        )

    @staticmethod
    def _market_coverage(response: Any) -> CoverageSummary:
        coverage_items = response.get("coverage") if isinstance(response, dict) else []
        expected_days = max((int(item.get("expected_days") or 0) for item in coverage_items), default=0)
        covered_days = min((int(item.get("covered_days") or 0) for item in coverage_items), default=0) if coverage_items else 0
        missing_dates = sorted({str(value) for item in coverage_items for value in (item.get("missing_dates") or [])})
        return CoverageSummary(
            expected_days=expected_days,
            covered_days=covered_days,
            missing_dates=missing_dates,
            missing_datasets=[str(item.get("dataset")) for item in coverage_items if item.get("status") == "empty"],
            partial_datasets=[str(item.get("dataset")) for item in coverage_items if item.get("status") == "partial"],
            latest_data_date=max((str(item.get("latest_date")) for item in coverage_items if item.get("latest_date")), default=None),
        )

    def market_get_keyword_opportunities(self, arguments: dict[str, Any]) -> MCPEnvelope:
        response = self.market.get_keyword_opportunities(
            start_date=self._parse_date(arguments.get("start_date")),
            end_date=self._parse_date(arguments.get("end_date")),
            keyword_type=str(arguments.get("keyword_type") or "all"),
            query=str(arguments.get("query") or "").strip() or None,
            min_click_rate=float(arguments["min_click_rate"]) if arguments.get("min_click_rate") is not None else None,
            min_pay_conversion=float(arguments["min_pay_conversion"]) if arguments.get("min_pay_conversion") is not None else None,
            include_unrelated=bool(arguments.get("include_unrelated", False)),
            limit=int(arguments.get("limit") or 20),
        )
        rows = response.get("opportunities") or []
        coverage = self._market_coverage(response)
        status = "partial" if coverage.missing_dates or coverage.partial_datasets else "ok" if rows else "no_data"
        start = self._parse_date(response.get("range_start")) or date.today()
        end = self._parse_date(response.get("range_end")) or start
        return self._envelope(
            tool="market.get_keyword_opportunities",
            context=self._context(None, start, end),
            status=status,
            data=response,
            metrics=[MetricValue(id="market_keyword_opportunity_count", label="关键词机会数", value=len(rows), unit="keyword", formula="按平台点击/支付转化区间和排名趋势排序的样本数", source="sycm_market_keywords")],
            coverage=coverage,
            evidence=[EvidenceRecord(dataset="市场搜索词", table="sycm_market_keywords", date_range=[start.isoformat(), end.isoformat()], row_count=len(rows), note="平台搜索需求方向信号；区间指标不用于精确 GMV")],
            provenance={"scope": "platform_market", "signal_type": "keyword_opportunity"},
            warnings=list(dict.fromkeys([*(response.get("diagnostics") or []), *(response.get("data_quality_flags") or [])])),
        )

    def market_get_competitor_movements(self, arguments: dict[str, Any]) -> MCPEnvelope:
        response = self.market.get_competitor_movements(
            start_date=self._parse_date(arguments.get("start_date")),
            end_date=self._parse_date(arguments.get("end_date")),
            rank_type=str(arguments.get("rank_type") or "all"),
            query=str(arguments.get("query") or "").strip() or None,
            direction=str(arguments.get("direction") or "all"),
            limit=int(arguments.get("limit") or 20),
        )
        rows = response.get("movements") or []
        coverage = self._market_coverage(response)
        status = "partial" if coverage.missing_dates or coverage.partial_datasets else "ok" if rows else "no_data"
        start = self._parse_date(response.get("range_start")) or date.today()
        end = self._parse_date(response.get("range_end")) or start
        return self._envelope(
            tool="market.get_competitor_movements",
            context=self._context(None, start, end),
            status=status,
            data=response,
            metrics=[MetricValue(id="market_competitor_movement_count", label="竞品异动数", value=len(rows), unit="row", formula="市场排行快照中的上升/下降/稳定样本数", source="sycm_market_rankings")],
            coverage=coverage,
            evidence=[EvidenceRecord(dataset="市场排行", table="sycm_market_rankings", date_range=[start.isoformat(), end.isoformat()], row_count=len(rows), note="平台相对排名变化；不等于成交增量")],
            provenance={"scope": "platform_market", "signal_type": "competitor_movement"},
            warnings=list(dict.fromkeys([*(response.get("diagnostics") or []), *(response.get("data_quality_flags") or [])])),
        )

    def market_match_store_products(self, arguments: dict[str, Any]) -> MCPEnvelope:
        store_id = arguments.get("store_id")
        source = self.analytics._source_for_store(store_id)
        market_response = self.market.get_insights(
            start_date=self._parse_date(arguments.get("start_date")),
            end_date=self._parse_date(arguments.get("end_date")),
            rank_type="item",
            keyword_type="all",
            query=str(arguments.get("query") or "").strip() or None,
            limit=100,
        )
        market_data = MarketInsightResponse.model_validate(market_response)
        query = str(arguments.get("query") or "").strip().casefold()
        product_type = str(arguments.get("product_type") or "").strip()
        series = str(arguments.get("series") or "").strip()
        start = market_data.range_start
        end = market_data.range_end
        try:
            store_first, store_latest = source.get_date_bounds()
            store_start = max(start, store_first)
            store_end = min(end, store_latest)
        except Exception:
            store_start, store_end = start, end
        catalog_where = ['"店铺ID" = ?']
        catalog_params: list[Any] = [source._store_id]
        if product_type:
            catalog_where.append('coalesce("类型", \'\') like ?')
            catalog_params.append(f"%{product_type}%")
        if series:
            catalog_where.append('coalesce("系列", \'\') like ?')
            catalog_params.append(f"%{series}%")
        catalogs = source._rows(
            f'''select "商品ID" as product_id, "商品名称" as product_name, "类型" as product_type,
                       "系列" as series, "定位" as positioning
                  from store_product_catalog where {' and '.join(catalog_where)}''',
            *catalog_params,
        )
        catalog_by_id = {str(item.get("product_id")): item for item in catalogs if item.get("product_id") is not None}
        product_ids = list(catalog_by_id)
        sales_by_id: dict[str, dict[str, Any]] = {}
        store_dates: set[str] = set()
        if product_ids and store_start <= store_end:
            placeholders = ",".join("?" for _ in product_ids)
            rows = source._rows(
                f'''select "商品ID" as product_id, sum(cast(coalesce("支付金额", '0') as real)) as paid_amount,
                           sum(cast(coalesce("支付买家数", '0') as real)) as buyers,
                           sum(cast(coalesce("商品访客数", '0') as real)) as visitors,
                           count(distinct "业务日期") as covered_days
                      from store_daily_product_rankings
                     where "店铺ID" = ? and "业务日期" between ? and ? and "商品ID" in ({placeholders})
                     group by "商品ID"''',
                source._store_id, store_start.isoformat(), store_end.isoformat(), *product_ids,
            )
            sales_by_id = {str(row.get("product_id")): row for row in rows if row.get("product_id") is not None}
            observed = source._rows(
                '''select distinct "业务日期" as business_day from store_daily_product_rankings
                   where "店铺ID" = ? and "业务日期" between ? and ?''',
                source._store_id, store_start.isoformat(), store_end.isoformat(),
            )
            store_dates = {str(row["business_day"]) for row in observed if row.get("business_day")}

        signals: list[dict[str, Any]] = []
        for keyword in market_data.keywords:
            if not keyword.keyword or keyword.category_relevance == "unrelated":
                continue
            if query and query not in keyword.keyword.casefold():
                continue
            category_terms = [
                term for term in ("纸尿裤", "尿不湿", "拉拉裤", "尿片", "隔尿垫", "湿巾")
                if term in keyword.keyword
            ]
            match_terms = [keyword.keyword.casefold(), *(term.casefold() for term in category_terms)]
            matched = []
            for product_id, catalog in catalog_by_id.items():
                haystack = " ".join(str(catalog.get(key) or "") for key in ("product_name", "series", "product_type", "positioning")).casefold()
                matched_terms = [term for term in match_terms if term and term in haystack]
                if matched_terms:
                    sales = sales_by_id.get(product_id, {})
                    visitors = float(sales.get("visitors") or 0)
                    buyers = float(sales.get("buyers") or 0)
                    paid = float(sales.get("paid_amount") or 0)
                    conversion = buyers / visitors * 100 if visitors else None
                    market_conversion = keyword.pay_conversion_midpoint
                    relationship = "market_signal_store_weak" if visitors < 20 or not buyers else "market_signal_store_strong" if visitors >= 50 and market_conversion is not None and conversion is not None and conversion >= market_conversion else "market_signal_store_aligned"
                    matched.append({**catalog, "paid_amount": paid, "buyers": buyers, "visitors": visitors, "conversion_rate": conversion, "relationship": relationship, "matched_terms": matched_terms})
            signals.append({
                "keyword": keyword.keyword,
                "keyword_type": keyword.keyword_type,
                "rank_no": keyword.rank_no,
                "opportunity_score": keyword.opportunity_score,
                "category_relevance": keyword.category_relevance,
                "matched_products": matched[:10],
                "relationship": "no_match" if not matched else "market_signal_store_weak" if any(item["relationship"] == "market_signal_store_weak" for item in matched) else "market_signal_store_strong" if any(item["relationship"] == "market_signal_store_strong" for item in matched) else "market_signal_store_aligned",
                "evidence": "平台关键词与本店商品主档按文本字段匹配；经营指标仅统计所选区间。",
            })
        signals.sort(key=lambda item: (0 if item["relationship"] == "no_match" else 1, -(item.get("opportunity_score") or -1)))
        signals = signals[:min(50, max(1, int(arguments.get("limit") or 20)))]
        market_coverage = [item.model_dump(mode="json") for item in market_data.coverage]
        expected_store_days = max(0, (store_end - store_start).days + 1) if store_start <= store_end else 0
        missing_store_dates = [
            (store_start + timedelta(days=offset)).isoformat()
            for offset in range(expected_store_days)
            if (store_start + timedelta(days=offset)).isoformat() not in store_dates
        ] if expected_store_days else []
        payload = {
            "range_start": start.isoformat(), "range_end": end.isoformat(),
            "market_coverage": market_coverage,
            "store_coverage": {"range_start": store_start.isoformat(), "range_end": store_end.isoformat(), "expected_days": expected_store_days, "covered_days": len(store_dates), "missing_dates": missing_store_dates, "status": "empty" if not store_dates else "complete" if not missing_store_dates else "partial"},
            "signals": signals,
            "boundary": "relationship=no_match 表示市场词未匹配到本店商品；no_match 不生成商品机会结论。市场信号与本店商品对照只形成验证假设，不证明市场需求带来的本店新增成交。",
        }
        coverage = self._market_coverage(market_response)
        if missing_store_dates:
            coverage.missing_dates = sorted(set(coverage.missing_dates) | set(missing_store_dates))
            coverage.partial_datasets = list(dict.fromkeys([*coverage.partial_datasets, "本店商品排行"]))
            coverage.covered_days = min(coverage.covered_days, len(store_dates)) if coverage.expected_days else len(store_dates)
        elif not store_dates:
            coverage.missing_datasets = list(dict.fromkeys([*coverage.missing_datasets, "本店商品排行"]))
            coverage.covered_days = 0
        status = "partial" if coverage.missing_dates or coverage.partial_datasets or coverage.missing_datasets else "ok" if signals else "no_data"
        evidence = [
            EvidenceRecord(dataset="市场搜索词", table="sycm_market_keywords", date_range=[start.isoformat(), end.isoformat()], row_count=len(market_data.keywords), note="平台需求观察"),
            EvidenceRecord(dataset="商品主档", table="store_product_catalog", date_range=[], row_count=len(catalogs), note="文本匹配可能无匹配，不虚构商品关系"),
            EvidenceRecord(dataset="商品排行", table="store_daily_product_rankings", date_range=[store_start.isoformat(), store_end.isoformat()] if store_start <= store_end else [], row_count=len(sales_by_id), note="本店商品访客/支付指标"),
        ]
        return self._envelope(
            tool="market.match_store_products", context=self._context(store_id, start, end), status=status,
            data=payload, metrics=[MetricValue(id="market_store_product_signal_count", label="市场与本店对照信号数", value=len(signals), unit="row", formula="市场关键词与本店商品主档文本匹配后的信号数", source="sycm_market_keywords + store_product_catalog")],
            coverage=coverage, evidence=evidence, provenance={"scope": "platform_market_to_store", "store_id": store_id},
            warnings=list(dict.fromkeys([*(market_data.diagnostics or []), *(market_data.data_quality_flags or []), "没有匹配到本店商品时只能输出 no_match，不能生成商品机会结论。"])),
        )

    def data_catalog(self, arguments: dict[str, Any]) -> MCPEnvelope:
        dataset_key = arguments.get("dataset")
        if dataset_key:
            descriptors = [self.query_service.describe_dataset(str(dataset_key))]
        else:
            descriptors = self.query_service.list_datasets()
        today = date.today()
        return self._envelope(
            tool="data.catalog", context=self._context(arguments.get("store_id"), today, today), status="ok",
            data={"datasets": [item.model_dump(mode="json") for item in descriptors]}, metrics=[],
            coverage=CoverageSummary(), evidence=[], warnings=[],
        )

    def data_query(self, arguments: dict[str, Any]) -> MCPEnvelope:
        request = self._query_request(arguments)
        result = self.query_service.query(request)
        context = self._context(request.store_id, request.start_date or date.today(), request.end_date or date.today())
        if result.evidence and result.evidence[0].date_range:
            context = self._context(request.store_id, date.fromisoformat(result.evidence[0].date_range[0]), date.fromisoformat(result.evidence[0].date_range[1]))
        metrics = []
        dataset = get_dataset(request.dataset)
        for metric_id, value in result.aggregates.items():
            field = dataset.fields[metric_id]
            metrics.append(MetricValue(id=metric_id, label=field.label, value=_number(value), unit=field.unit, formula=result.formula.get(metric_id, ""), source=dataset.table))
        has_rows = bool(result.evidence and result.evidence[0].row_count)
        incomplete = bool(result.coverage.missing_dates or result.coverage.missing_datasets or result.coverage.partial_datasets)
        status = "partial" if incomplete else "ok" if has_rows else "no_data"
        return self._envelope(
            tool="data.query", context=context, status=status,
            data={"dataset": result.dataset, "columns": result.columns, "rows": result.rows, "aggregates": result.aggregates, "formula": result.formula},
            metrics=metrics, coverage=result.coverage, evidence=result.evidence, warnings=self._coverage_warnings(result.coverage),
        )

    def data_compare_periods(self, arguments: dict[str, Any]) -> MCPEnvelope:
        request = self._query_request(arguments)
        compared = self.query_service.compare_periods(request)
        current = compared["current"]
        coverage = CoverageSummary.model_validate(current["coverage"])
        dataset = get_dataset(request.dataset)
        metrics = []
        for metric_id, values in compared["comparisons"].items():
            field = dataset.fields[metric_id]
            metrics.append(MetricValue(id=metric_id, label=field.label, value=values["current"], unit=field.unit, formula=current.get("formula", {}).get(metric_id, f"{field.aggregation}({field.column})"), comparison=values, source=dataset.table))
        start_date, end_date = (date.fromisoformat(value) for value in compared["current_range"])
        warnings = self._coverage_warnings(coverage)
        if not compared["comparable"]:
            warnings.append("当前周期或上一周期覆盖不完整，未计算涨跌幅。")
        evidence = [EvidenceRecord.model_validate(item) for item in current["evidence"]]
        evidence.extend(EvidenceRecord.model_validate(item) for item in compared["previous"]["evidence"])
        return self._envelope(
            tool="data.compare_periods", context=self._context(request.store_id, start_date, end_date),
            status="partial" if not compared["comparable"] else self._status(coverage, bool(evidence and sum(item.row_count for item in evidence))),
            data=compared, metrics=metrics, coverage=coverage, evidence=evidence, warnings=list(dict.fromkeys(warnings)),
        )

    def data_coverage(self, arguments: dict[str, Any]) -> MCPEnvelope:
        dataset_keys = arguments.get("datasets") or ([arguments["dataset"]] if arguments.get("dataset") else list(DATASET_CATALOG))
        store_id = arguments.get("store_id")
        source, start_date, end_date = self._source_and_range(
            store_id,
            self._parse_date(arguments.get("start_date")),
            self._parse_date(arguments.get("end_date")),
            str(arguments.get("history_scope") or "selected"),
        )
        items = []
        for key in dataset_keys:
            descriptor = get_dataset(str(key))
            summary = self.query_service.coverage(str(key), source._store_id, start_date, end_date)
            items.append({"dataset": key, "label": descriptor.label, **summary.model_dump(mode="json")})
        missing = [item["label"] for item in items if item["missing_dates"] or item["missing_datasets"]]
        partial = [item["label"] for item in items if item["partial_datasets"]]
        no_data = [item["label"] for item in items if item["no_data_datasets"]]
        coverage = CoverageSummary(
            expected_days=(end_date - start_date).days + 1,
            covered_days=min((item["covered_days"] for item in items), default=0),
            missing_datasets=missing, partial_datasets=partial, no_data_datasets=no_data,
            latest_data_date=max((item["latest_data_date"] for item in items if item["latest_data_date"]), default=None),
        )
        return self._envelope(
            tool="data.coverage", context=self._context(store_id, start_date, end_date),
            status="partial" if missing or partial else "ok", data={"datasets": items}, metrics=[], coverage=coverage,
            evidence=[EvidenceRecord(dataset=get_dataset(str(key)).label, table=get_dataset(str(key)).table, date_range=[start_date.isoformat(), end_date.isoformat()]) for key in dataset_keys],
            warnings=self._coverage_warnings(coverage),
        )

    def data_freshness(self, arguments: dict[str, Any]) -> MCPEnvelope:
        source = self.analytics._source_for_store(arguments.get("store_id"))
        datasets = arguments.get("datasets") or list(DATASET_CATALOG)
        requested = {str(item) for item in datasets}
        labels = {key: descriptor.label for key, descriptor in DATASET_CATALOG.items()}
        try:
            raw = source.get_freshness()
        except Exception:
            raw = []
        by_label = {str(item.dataset): item for item in raw}
        today = date.today()
        rows = []
        missing = []
        latest_dates = []
        for key in requested:
            label = labels.get(key, key)
            item = by_label.get(label)
            if not item:
                missing.append(label)
                rows.append({"dataset": key, "label": label, "status": "no_observed_data", "first_date": None, "latest_date": None, "business_lag_days": None})
                continue
            latest = item.latest_date
            latest_dates.append(latest)
            lag = max((today - latest).days, 0)
            rows.append({"dataset": key, "label": label, "status": "fresh" if lag <= 1 else "stale", "first_date": item.first_date.isoformat() if item.first_date else None, "latest_date": latest.isoformat(), "business_lag_days": lag})
        latest = max(latest_dates) if latest_dates else today
        coverage = CoverageSummary(
            expected_days=0,
            covered_days=len(rows) - len(missing),
            missing_datasets=missing,
            latest_data_date=latest.isoformat() if latest_dates else None,
        )
        warnings = ["以下数据集没有观测到业务日期：" + "、".join(missing)] if missing else []
        return self._envelope(
            tool="data.freshness",
            context=self._context(arguments.get("store_id"), latest, latest),
            status="partial" if missing else "ok",
            data={"today": today.isoformat(), "datasets": rows},
            metrics=[], coverage=coverage,
            evidence=[EvidenceRecord(dataset=labels.get(key, key), table=DATASET_CATALOG[key].table if key in DATASET_CATALOG else "", date_range=[], row_count=1 if key not in missing else 0, note="最新业务日来自规范化数据源；业务延迟不等同采集任务失败") for key in requested],
            warnings=warnings,
        )

    def products_search(self, arguments: dict[str, Any]) -> MCPEnvelope:
        source = self.analytics._source_for_store(arguments.get("store_id"))
        store_id = source._store_id
        query = str(arguments.get("query") or "").strip()
        product_id = str(arguments.get("product_id") or "").strip()
        product_name = str(arguments.get("product_name") or "").strip()
        series = str(arguments.get("series") or "").strip()
        product_type = str(arguments.get("product_type") or "").strip()
        positioning = str(arguments.get("positioning") or "").strip()
        limit = min(max(int(arguments.get("limit") or 50), 1), 200)
        offset = max(int(arguments.get("offset") or 0), 0)
        where = ['"店铺ID" = ?']
        params: list[Any] = [store_id]
        if product_id:
            where.append('"商品ID" = ?')
            params.append(product_id)
        if product_name:
            where.append('"商品名称" like ?')
            params.append(f"%{product_name}%")
        if series:
            where.append('"系列" = ?')
            params.append(series)
        if product_type:
            where.append('"类型" = ?')
            params.append(product_type)
        if positioning:
            where.append('"定位" = ?')
            params.append(positioning)
        if query:
            where.append('(cast("商品ID" as text) = ? or "商品名称" like ? or "系列" like ? or "类型" like ? or "属性" like ? or "定位" like ?)')
            params.extend([query, f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%", f"%{query}%"])
        predicate = " and ".join(where)
        count = source._rows(f'select count(*) as total from store_product_catalog where {predicate}', *params)
        rows = source._rows(
            f'''select "商品ID" as product_id, "商品名称" as product_name,
                       "类型" as product_type, "属性" as attributes,
                       "系列" as series, "定位" as positioning, "渠道" as channel
                  from store_product_catalog where {predicate}
                 order by case when "商品名称" is null or "商品名称" = '' then 1 else 0 end, "商品名称"
                 limit ? offset ?''',
            *params, limit, offset,
        )
        _, latest = source.get_date_bounds()
        status = "ok" if rows else "no_data"
        return self._envelope(
            tool="products.search", context=self._context(store_id, latest, latest), status=status,
            data={"total": int(count[0].get("total") or 0) if count else 0, "limit": limit, "offset": offset, "rows": rows},
            metrics=[], coverage=CoverageSummary(expected_days=0, covered_days=1 if rows else 0),
            evidence=[EvidenceRecord(dataset="商品主档", table="store_product_catalog", date_range=[], row_count=len(rows), note="静态主档，无业务日期；商品 ID 精确匹配，名称/系列/类型/定位模糊匹配")],
            warnings=[] if rows else ["没有匹配到商品主档记录。"],
        )

    def products_get_series_profile(self, arguments: dict[str, Any]) -> MCPEnvelope:
        """Aggregate a series without pretending that one SKU represents it."""
        series = str(arguments.get("series") or "").strip()
        if not series:
            raise ValueError("products.get_series_profile requires series")
        source = self.analytics._source_for_store(arguments.get("store_id"))
        store_id = source._store_id
        start_date, end_date = self._bounded_range(source, arguments, days=30)
        where = ['c."店铺ID" = ?', 'c."系列" = ?']
        params: list[Any] = [store_id, series]
        positioning = str(arguments.get("positioning") or "").strip()
        product_type = str(arguments.get("product_type") or "").strip()
        if positioning:
            where.append('c."定位" = ?'); params.append(positioning)
        if product_type:
            where.append('c."类型" = ?'); params.append(product_type)
        predicate = " and ".join(where)
        catalog_rows = source._rows(
            f'''select c."商品ID" as product_id, c."商品名称" as product_name,
                       c."类型" as product_type, c."属性" as attributes,
                       c."系列" as series, c."定位" as positioning
                  from store_product_catalog c where {predicate}
                 order by c."商品名称"''', *params,
        )
        product_ids = [str(item.get("product_id")) for item in catalog_rows if item.get("product_id")]
        if not product_ids:
            return self._envelope(tool="products.get_series_profile", context=self._context(store_id, start_date, end_date), status="no_data", data={"series": series, "positioning": positioning or None, "product_type": product_type or None, "product_count": 0, "sales": {}, "products": []}, metrics=[], coverage=CoverageSummary(expected_days=(end_date-start_date).days+1, covered_days=0), evidence=[EvidenceRecord(dataset="商品主档", table="store_product_catalog", date_range=[], row_count=0)], warnings=["没有匹配到该系列或类型的商品主档。"])
        placeholders = ",".join("?" for _ in product_ids)
        rows = source._rows(
            f'''select "商品ID" as product_id,
                       count(*) as row_count,
                       sum(cast(coalesce("支付金额", '0') as real)) as paid_amount,
                       sum(cast(coalesce("退款金额（完结时间）", '0') as real)) as refund_amount,
                       sum(cast(coalesce("支付买家数", '0') as real)) as buyers,
                       sum(cast(coalesce("商品访客数", '0') as real)) as visitors,
                       sum(cast(coalesce("推广消耗", '0') as real)) as promotion_spend
                  from store_daily_product_rankings
                 where "店铺ID" = ? and "业务日期" between ? and ? and "商品ID" in ({placeholders})
                 group by "商品ID"''', store_id, start_date.isoformat(), end_date.isoformat(), *product_ids,
        )
        by_id = {str(item.get("product_id")): item for item in rows}
        detail_rows = []
        total_values: dict[str, list[float]] = {key: [] for key in ("paid_amount", "refund_amount", "buyers", "visitors", "promotion_spend")}
        for item in catalog_rows:
            stats = by_id.get(str(item.get("product_id")), {})
            detail = {**item, **{key: _optional_number(stats.get(key)) for key in total_values}, "row_count": int(stats.get("row_count") or 0)}
            for key in total_values:
                if detail.get(key) is not None:
                    total_values[key].append(float(detail[key]))
            detail["conversion_rate"] = (float(detail["buyers"]) / float(detail["visitors"]) * 100) if detail.get("visitors") else None
            detail["promotion_roi"] = (float(detail["paid_amount"]) / float(detail["promotion_spend"])) if detail.get("promotion_spend") else None
            detail_rows.append(detail)
        total = {key: (sum(values) if values else None) for key, values in total_values.items()}
        total["conversion_rate"] = total["buyers"] / total["visitors"] * 100 if total["visitors"] else None
        total["promotion_roi"] = total["paid_amount"] / total["promotion_spend"] if total["promotion_spend"] else None
        covered_rows = source._rows(
            f'''select count(distinct "业务日期") as covered_days
                  from store_daily_product_rankings
                 where "店铺ID" = ? and "业务日期" between ? and ? and "商品ID" in ({placeholders})''',
            store_id, start_date.isoformat(), end_date.isoformat(), *product_ids,
        )
        covered_days = int(covered_rows[0].get("covered_days") or 0) if covered_rows else 0
        expected_days = (end_date - start_date).days + 1
        profile_status = "ok" if rows and covered_days >= expected_days else "partial" if rows else "no_data"
        missing_dates: list[str] = []
        if covered_days < expected_days:
            observed_rows = source._rows(
                f'''select distinct "业务日期" as business_day
                      from store_daily_product_rankings
                     where "店铺ID" = ? and "业务日期" between ? and ? and "商品ID" in ({placeholders})
                     order by "业务日期"''',
                store_id, start_date.isoformat(), end_date.isoformat(), *product_ids,
            )
            observed = {str(item.get("business_day")) for item in observed_rows if item.get("business_day")}
            missing_dates = [
                (start_date + timedelta(days=offset)).isoformat()
                for offset in range(expected_days)
                if (start_date + timedelta(days=offset)).isoformat() not in observed
            ]
        warnings = ["系列商品排行在所选区间存在未覆盖日期，缺失日期未按 0 计入。"] if missing_dates else []
        return self._envelope(tool="products.get_series_profile", context=self._context(store_id, start_date, end_date), status=profile_status, data={"series": series, "positioning": positioning or None, "product_type": product_type or None, "product_count": len(catalog_rows), "sales": total, "products": detail_rows}, metrics=[MetricValue(id="paid_amount", label="系列支付金额", value=total["paid_amount"], unit="CNY", formula="系列商品支付金额合计", source="store_daily_product_rankings"), MetricValue(id="conversion_rate", label="系列支付转化率", value=total["conversion_rate"], unit="percent", formula="系列支付买家/系列商品访客", source="store_daily_product_rankings")], coverage=CoverageSummary(expected_days=expected_days, covered_days=covered_days, missing_dates=missing_dates, latest_data_date=end_date.isoformat() if covered_days else None), evidence=[EvidenceRecord(dataset="商品主档", table="store_product_catalog", date_range=[], row_count=len(catalog_rows)), EvidenceRecord(dataset="商品排行", table="store_daily_product_rankings", date_range=[start_date.isoformat(), end_date.isoformat()], row_count=len(rows))], warnings=warnings)

    def products_get_profile(self, arguments: dict[str, Any]) -> MCPEnvelope:
        product_id = str(arguments.get("product_id") or "").strip()
        if not product_id:
            raise ValueError("products.get_profile requires product_id")
        source = self.analytics._source_for_store(arguments.get("store_id"))
        store_id = source._store_id
        start_date, end_date = self._bounded_range(source, arguments, days=30)
        catalog_rows = source._rows(
            '''select "商品ID" as product_id, "商品名称" as product_name, "类型" as product_type,
                      "属性" as attributes, "系列" as series, "定位" as positioning, "渠道" as channel
                 from store_product_catalog where "店铺ID" = ? and "商品ID" = ? limit 1''',
            store_id, product_id,
        )
        catalog = catalog_rows[0] if catalog_rows else None

        def product_period(period_start: date, period_end: date) -> dict[str, Any]:
            rows = source._rows(
                '''select count(*) as row_count,
                          count(distinct "业务日期") as covered_days,
                          sum(cast(coalesce("支付金额", '0') as real)) as paid_amount,
                          sum(cast(coalesce("退款金额（完结时间）", '0') as real)) as refund_amount,
                          sum(cast(coalesce("支付买家数", '0') as real)) as buyers,
                          sum(cast(coalesce("商品访客数", '0') as real)) as visitors,
                          sum(cast(coalesce("推广消耗", '0') as real)) as promotion_spend
                     from store_daily_product_rankings
                    where "店铺ID" = ? and "商品ID" = ? and "业务日期" between ? and ?''',
                store_id, product_id, period_start.isoformat(), period_end.isoformat(),
            )
            row = rows[0] if rows else {}
            paid = _optional_number(row.get("paid_amount"))
            spend = _optional_number(row.get("promotion_spend"))
            return {"row_count": int(row.get("row_count") or 0), "covered_days": int(row.get("covered_days") or 0), "paid_amount": paid, "refund_amount": _optional_number(row.get("refund_amount")), "buyers": _optional_number(row.get("buyers")), "visitors": _optional_number(row.get("visitors")), "promotion_spend": spend, "promotion_roi": (paid / spend if paid is not None and spend not in (None, 0) else None)}

        sales = {"last_1_day": product_period(end_date, end_date), "last_7_days": product_period(max(start_date, end_date - timedelta(days=6)), end_date), "last_30_days": product_period(start_date, end_date)}
        promo_rows = source._rows(
            '''select sum(cast(coalesce("花费", '0') as real)) as spend,
                      sum(cast(coalesce("总成交金额", '0') as real)) as attributed_gmv,
                      sum(cast(coalesce("点击量", '0') as real)) as clicks
                 from store_daily_promotion_items
                where "店铺ID" = ? and "商品ID" = ? and "业务日期" between ? and ?''',
            store_id, product_id, start_date.isoformat(), end_date.isoformat(),
        )
        promo = promo_rows[0] if promo_rows else {}
        promo_spend = _optional_number(promo.get("spend")); promo_gmv = _optional_number(promo.get("attributed_gmv"))
        promotion = {"spend": promo_spend, "attributed_gmv": promo_gmv, "clicks": _optional_number(promo.get("clicks")), "roi": promo_gmv / promo_spend if promo_gmv is not None and promo_spend not in (None, 0) else None}
        price = self._latest_snapshot_row(source, "store_daily_taobao_current_price_items", product_id)
        risk = self._latest_snapshot_row(source, "store_daily_taobao_risk_price_items", product_id)
        activities = source._rows(
            '''select "快照类型" as snapshot_type, "营销ID" as marketing_id, "商品ID" as product_id,
                      "商品名称" as product_name, "状态" as status, "状态名称" as status_name,
                      "活动名称" as activity_name, "活动开始时间" as start_time, "活动结束时间" as end_time,
                      "活动价" as activity_price, "原价" as original_price, "库存" as inventory, "已售数量" as sold_count
                 from store_daily_taobao_activity_item_snapshots
                where "店铺ID" = ? and "商品ID" = ? order by "业务日期" desc''', store_id, product_id,
        )
        rows_found = bool(catalog or sales["last_30_days"]["row_count"] or price or risk or activities)
        _, latest = source.get_date_bounds()
        evidence = [EvidenceRecord(dataset="商品主档", table="store_product_catalog", date_range=[], row_count=1 if catalog else 0, note="静态主档，无业务日期")]
        evidence.extend([
            EvidenceRecord(dataset="商品排行", table="store_daily_product_rankings", date_range=[start_date.isoformat(), end_date.isoformat()], row_count=sales["last_30_days"]["row_count"]),
            EvidenceRecord(dataset="推广商品", table="store_daily_promotion_items", date_range=[start_date.isoformat(), end_date.isoformat()], row_count=1 if promo_spend is not None else 0),
            EvidenceRecord(dataset="淘宝当前价格", table="store_daily_taobao_current_price_items", date_range=[str(price.get("business_day"))] if price and price.get("business_day") else [], row_count=1 if price else 0),
            EvidenceRecord(dataset="淘宝红线价风险", table="store_daily_taobao_risk_price_items", date_range=[str(risk.get("business_day"))] if risk and risk.get("business_day") else [], row_count=1 if risk else 0),
            EvidenceRecord(dataset="淘宝活动商品快照", table="store_daily_taobao_activity_item_snapshots", date_range=[str(activities[0].get("business_day"))] if activities and activities[0].get("business_day") else [], row_count=len(activities)),
        ])
        return self._envelope(
            tool="products.get_profile", context=self._context(store_id, start_date, end_date), status="ok" if rows_found else "no_data",
            data={"product": catalog, "sales": sales, "promotion": promotion, "current_price": price, "price_risk": risk, "activities": activities, "latest_business_date": str(latest)},
            metrics=[], coverage=CoverageSummary(expected_days=(end_date-start_date).days+1, covered_days=int(sales["last_30_days"].get("covered_days") or 0), latest_data_date=str(latest)),
            evidence=evidence, warnings=[] if rows_found else ["没有找到该商品的主档或经营数据。"],
        )

    def mini_get_diagnosis(self, arguments: dict[str, Any]) -> MCPEnvelope:
        """Join MINI/trial product evidence by the store product ID.

        The catalog is the identity source.  Downstream facts are deliberately
        kept as separate domains so an empty U先 or VOC table cannot erase a
        real catalog match or be described as "no MINI products".
        """
        source, start_date, end_date = self._source_and_range(
            arguments.get("store_id"),
            self._parse_date(arguments.get("start_date")),
            self._parse_date(arguments.get("end_date")),
        )
        store_id = source._store_id
        query = str(arguments.get("query") or "").strip()
        product_id = str(arguments.get("product_id") or "").strip()
        positioning = str(arguments.get("positioning") or "").strip()
        limit = min(max(int(arguments.get("limit") or 100), 1), 200)
        where = ['"店铺ID" = ?']
        params: list[Any] = [store_id]
        if product_id:
            where.append('"商品ID" = ?'); params.append(product_id)
        else:
            # Match title, attributes and normalized catalog positioning.  The
            # default terms intentionally include both user-facing labels.
            terms = [part.strip() for part in (query.split(",") if query else ["mini", "MINI", "尝鲜", "试用装"]) if part.strip()]
            term_sql: list[str] = []
            for term in terms:
                like = f"%{term}%"
                term_sql.append('(coalesce("商品名称", \'\') like ? or coalesce("属性", \'\') like ? or coalesce("定位", \'\') like ? or coalesce("类型", \'\') like ?)')
                params.extend([like, like, like, like])
            where.append("(" + " or ".join(term_sql) + ")")
        if positioning:
            where.append('"定位" like ?'); params.append(f"%{positioning}%")
        predicate = " and ".join(where)
        catalog_rows = source._rows(
            f'''select "商品ID" as product_id, "商品名称" as product_name,
                       "类型" as product_type, "属性" as attributes,
                       "系列" as series, "定位" as positioning, "渠道" as channel
                  from store_product_catalog where {predicate}
                 order by "商品名称" limit ?''',
            *params, limit,
        )
        product_ids = [str(row.get("product_id")) for row in catalog_rows if row.get("product_id")]
        expected_days = (end_date - start_date).days + 1
        if not product_ids:
            return self._envelope(
                tool="mini.get_diagnosis", context=self._context(store_id, start_date, end_date), status="no_data",
                data={"selected_range": [start_date.isoformat(), end_date.isoformat()], "match_rule": query or "mini/MINI/尝鲜/试用装 标题、属性、定位或类型", "matched_count": 0, "products": [], "domain_status": {}},
                metrics=[], coverage=CoverageSummary(expected_days=expected_days, covered_days=0),
                evidence=[EvidenceRecord(dataset="商品主档", table="store_product_catalog", row_count=0, note="标题/属性/定位/类型未匹配到商品 ID")],
                warnings=["没有匹配到 MINI/尝鲜商品主档；这只表示当前匹配条件无结果，不表示店铺没有商品数据。"],
            )
        placeholders = ",".join("?" for _ in product_ids)
        base_params: list[Any] = [store_id, start_date.isoformat(), end_date.isoformat(), *product_ids]

        sales_rows = source._rows(
            f'''select "商品ID" as product_id, max("商品名称") as product_name, count(*) as row_count,
                       count(distinct "业务日期") as covered_days,
                       sum(cast(coalesce("支付金额", '0') as real)) as paid_amount,
                       sum(cast(coalesce("退款金额（完结时间）", '0') as real)) as refund_amount,
                       sum(cast(coalesce("支付买家数", '0') as real)) as buyers,
                       sum(cast(coalesce("商品访客数", '0') as real)) as visitors,
                       sum(cast(coalesce("商品加购人数", '0') as real)) as add_cart_users,
                       sum(cast(coalesce("商品收藏人数", '0') as real)) as favorite_users
                  from store_daily_product_rankings
                 where "店铺ID" = ? and "业务日期" between ? and ? and "商品ID" in ({placeholders})
                 group by "商品ID"''', *base_params,
        )
        promotion_rows = source._rows(
            f'''select "商品ID" as product_id, max("商品名称") as product_name, count(*) as row_count,
                       sum(cast(coalesce("花费", '0') as real)) as spend,
                       sum(cast(coalesce("总成交金额", '0') as real)) as attributed_gmv,
                       sum(cast(coalesce("点击量", '0') as real)) as clicks,
                       sum(cast(coalesce("总购物车数", '0') as real)) as carts
                  from store_daily_promotion_items
                 where "店铺ID" = ? and "业务日期" between ? and ? and "商品ID" in ({placeholders})
                 group by "商品ID"''', *base_params,
        )
        observed_rows = source._rows(
            f'''select distinct "业务日期" as business_day from store_daily_product_rankings
                 where "店铺ID" = ? and "业务日期" between ? and ? and "商品ID" in ({placeholders})''', *base_params,
        )
        observed_dates = {str(row.get("business_day")) for row in observed_rows if row.get("business_day")}
        missing_dates = [(start_date + timedelta(days=i)).isoformat() for i in range(expected_days) if (start_date + timedelta(days=i)).isoformat() not in observed_dates]
        sales_by_id = {str(row.get("product_id")): row for row in sales_rows}
        promotion_by_id = {str(row.get("product_id")): row for row in promotion_rows}

        # U先 is a rolling snapshot: take each product's latest row at or
        # before the selected end date, never sum snapshots across days.
        sample_rows = source._rows(
            f'''select s.* from store_daily_utry_sample_overviews s
                 join (select "商品ID" as pid, max("业务日期") as max_day
                         from store_daily_utry_sample_overviews
                        where "店铺ID" = ? and "业务日期" <= ? and "商品ID" in ({placeholders}) group by "商品ID") x
                   on s."商品ID" = x.pid and s."业务日期" = x.max_day
                where s."店铺ID" = ?''',
            store_id, end_date.isoformat(), *product_ids, store_id,
        )
        repurchase_rows = source._rows(
            f'''select r.* from store_daily_utry_repurchase_overviews r
                 join (select "商品ID" as pid, max("业务日期") as max_day
                         from store_daily_utry_repurchase_overviews
                        where "店铺ID" = ? and "业务日期" <= ? and "商品ID" in ({placeholders}) group by "商品ID") x
                   on r."商品ID" = x.pid and r."业务日期" = x.max_day
                where r."店铺ID" = ?''',
            store_id, end_date.isoformat(), *product_ids, store_id,
        )
        sample_by_id = {str(row.get("product_id") or row.get("商品ID")): row for row in sample_rows}
        repurchase_by_id = {str(row.get("product_id") or row.get("商品ID")): row for row in repurchase_rows}

        review_service = ReviewService(Path(settings.local_database_path))
        products: list[dict[str, Any]] = []
        review_count = ask_count = unanswered_count = 0
        for catalog in catalog_rows:
            pid = str(catalog.get("product_id"))
            sales = sales_by_id.get(pid, {})
            promo = promotion_by_id.get(pid, {})
            review_info: dict[str, Any] = {"review_count": 0, "negative_review_rate": None, "top_issues": []}
            ask_info: dict[str, Any] = {"question_count": 0, "unanswered_count": 0, "answer_rate": None, "representative_unanswered": []}
            try:
                analysis = review_service.analysis(product_id=pid, start_date=start_date.isoformat(), end_date=end_date.isoformat(), top_limit=5)
                review_info = {"review_count": int(analysis.total_reviews or 0), "negative_review_rate": analysis.negative_rate, "top_issues": [item.model_dump(mode="json") for item in analysis.category_counts[:5]]}
                asks = review_service.list_asks(product_id=pid, start_date=start_date.isoformat(), end_date=end_date.isoformat(), page=1, page_size=5)
                ask_total = asks.total
                unanswered = review_service.list_asks(product_id=pid, has_answer=False, start_date=start_date.isoformat(), end_date=end_date.isoformat(), page=1, page_size=5)
                ask_info = {"question_count": ask_total, "unanswered_count": unanswered.total, "answer_rate": round((ask_total - unanswered.total) / ask_total * 100, 2) if ask_total else None, "representative_unanswered": [item.model_dump(mode="json") for item in unanswered.items]}
            except Exception:
                # VOC tables can be absent in a fresh deployment; retain the
                # product identity and mark only this domain as unavailable.
                review_info["status"] = "unavailable"
                ask_info["status"] = "unavailable"
            review_count += int(review_info.get("review_count") or 0)
            ask_count += int(ask_info.get("question_count") or 0)
            unanswered_count += int(ask_info.get("unanswered_count") or 0)
            sales_data = {key: _optional_number(sales.get(key)) for key in ("paid_amount", "refund_amount", "buyers", "visitors", "add_cart_users", "favorite_users")}
            promo_spend = _optional_number(promo.get("spend")); promo_gmv = _optional_number(promo.get("attributed_gmv"))
            sample = sample_by_id.get(pid); repurchase = repurchase_by_id.get(pid)
            products.append({
                **catalog,
                "product_name": catalog.get("product_name") or sales.get("product_name") or promo.get("product_name") or pid,
                "sales": {**sales_data, "covered_days": int(sales.get("covered_days") or 0), "conversion_rate": (float(sales_data["buyers"]) / float(sales_data["visitors"]) * 100) if sales_data.get("buyers") is not None and sales_data.get("visitors") else None},
                "promotion": {"spend": promo_spend, "attributed_gmv": promo_gmv, "clicks": _optional_number(promo.get("clicks")), "carts": _optional_number(promo.get("carts")), "roi": promo_gmv / promo_spend if promo_gmv is not None and promo_spend not in (None, 0) else None},
                "reviews": review_info,
                "asks": ask_info,
                "utry_sample": {"status": "ok", "business_day": sample.get("业务日期") if sample else None, "sample_orders": _optional_number(sample.get("派样单量")) if sample else None, "sample_people": _optional_number(sample.get("派样人次")) if sample else None, "sample_gmv": _optional_number(sample.get("派样GMV")) if sample else None} if sample else {"status": "no_data"},
                "utry_repurchase": {"status": "ok", "business_day": repurchase.get("业务日期") if repurchase else None, "store_30d_repurchase_uv": _optional_number(repurchase.get("同店30日回购UV")) if repurchase else None, "store_30d_repurchase_amount": _optional_number(repurchase.get("同店30日回购金额")) if repurchase else None, "store_90d_repurchase_uv": _optional_number(repurchase.get("同店90日回购UV")) if repurchase else None, "store_365d_repurchase_uv": _optional_number(repurchase.get("同店365日回购UV")) if repurchase else None, "bind_regular_product": repurchase.get("是否绑定正装") if repurchase else None, "configured_repurchase_coupon": repurchase.get("是否配置回购券") if repurchase else None, "configured_repurchase_gift": repurchase.get("是否配置回购礼金") if repurchase else None} if repurchase else {"status": "no_data"},
            })
        domain_status = {
            "catalog": {"status": "ok", "matched_products": len(products)},
            "sales": {"status": "ok" if sales_rows and not missing_dates else "partial" if sales_rows else "no_data", "row_count": len(sales_rows), "missing_dates": missing_dates},
            "promotion": {"status": "ok" if promotion_rows else "no_data", "row_count": len(promotion_rows)},
            "reviews": {"status": "ok" if review_count else "no_data", "row_count": review_count},
            "asks": {"status": "ok" if ask_count else "no_data", "row_count": ask_count, "unanswered_count": unanswered_count},
            "utry_sample": {"status": "ok" if sample_rows else "no_data", "row_count": len(sample_rows)},
            "utry_repurchase": {"status": "ok" if repurchase_rows else "no_data", "row_count": len(repurchase_rows)},
        }
        warnings = ["评价/问大家与成交仅作描述性关联，不直接证明成交因果。", "U先复购 30/90/365 日是商品最新业务日滚动快照，不能跨日求和；没有 cohort 分母不计算回购率。"]
        if missing_dates:
            warnings.insert(0, "商品排行存在未覆盖日期，缺失日期未按 0 计入。")
        return self._envelope(
            tool="mini.get_diagnosis", context=self._context(store_id, start_date, end_date), status="partial" if missing_dates else "ok",
            data={"selected_range": [start_date.isoformat(), end_date.isoformat()], "match_rule": query or "mini/MINI/尝鲜/试用装 标题、属性、定位或类型", "matched_count": len(products), "products": products, "domain_status": domain_status, "rate_available": False, "rate_unavailable_reason": "缺少与商品当前回购窗口严格对应的首批派样 cohort 分母。"},
            metrics=[MetricValue(id="mini_product_count", label="匹配的 MINI/尝鲜商品数", value=len(products), unit="item", formula="商品主档标题/属性/定位/类型匹配后的商品 ID 数", source="store_product_catalog"), MetricValue(id="mini_review_count", label="匹配商品评价数", value=review_count, unit="review", formula="匹配商品 ID 的所选区间评价记录数", source="review_records"), MetricValue(id="mini_unanswered_question_count", label="匹配商品未回答问大家", value=unanswered_count, unit="question", formula="匹配商品 ID 的已采集未回答问题数", source="ask_records")],
            coverage=CoverageSummary(expected_days=expected_days, covered_days=len(observed_dates), missing_dates=missing_dates, latest_data_date=max(observed_dates) if observed_dates else None),
            evidence=[EvidenceRecord(dataset="商品主档", table="store_product_catalog", row_count=len(products), note="商品 ID 是跨域关联主键"), EvidenceRecord(dataset="商品排行", table="store_daily_product_rankings", date_range=[start_date.isoformat(), end_date.isoformat()], row_count=len(sales_rows)), EvidenceRecord(dataset="推广商品", table="store_daily_promotion_items", date_range=[start_date.isoformat(), end_date.isoformat()], row_count=len(promotion_rows)), EvidenceRecord(dataset="评价明细", table="review_records", date_range=[start_date.isoformat(), end_date.isoformat()], row_count=review_count), EvidenceRecord(dataset="问大家", table="ask_records", row_count=ask_count), EvidenceRecord(dataset="U先派样", table="store_daily_utry_sample_overviews", row_count=len(sample_rows)), EvidenceRecord(dataset="U先复购", table="store_daily_utry_repurchase_overviews", row_count=len(repurchase_rows))],
            warnings=warnings,
        )

    def products_get_structure_profile(self, arguments: dict[str, Any]) -> MCPEnvelope:
        """Compare product structure across periods for an AOV drill-down.

        This intentionally joins the static product catalog to the daily
        ranking fact table in the MCP layer. The UI and model receive the
        same current/previous grain and do not need to infer series/type from
        product names.
        """
        source = self.analytics._source_for_store(arguments.get("store_id"))
        store_id = source._store_id
        start_date, end_date = self._bounded_range(source, arguments, days=7)
        period_days = (end_date - start_date).days + 1
        previous_start = start_date - timedelta(days=period_days)
        previous_end = start_date - timedelta(days=1)

        def aggregate(period_start: date, period_end: date) -> tuple[list[dict[str, Any]], set[str]]:
            rows = source._rows(
                '''select "商品ID" as product_id,
                          sum(cast(coalesce("支付金额", '0') as real)) as paid_amount,
                          sum(cast(coalesce("支付买家数", '0') as real)) as buyers,
                          sum(cast(coalesce("商品访客数", '0') as real)) as visitors,
                          sum(cast(coalesce("退款金额（完结时间）", '0') as real)) as refund_amount,
                          count(distinct "业务日期") as covered_days
                     from store_daily_product_rankings
                    where "店铺ID" = ? and "业务日期" between ? and ?
                    group by "商品ID"''',
                store_id, period_start.isoformat(), period_end.isoformat(),
            )
            observed = source._rows(
                '''select distinct "业务日期" as business_day
                     from store_daily_product_rankings
                    where "店铺ID" = ? and "业务日期" between ? and ?''',
                store_id, period_start.isoformat(), period_end.isoformat(),
            )
            return rows, {str(item.get("business_day")) for item in observed if item.get("business_day")}

        current_rows, current_dates = aggregate(start_date, end_date)
        previous_rows, previous_dates = aggregate(previous_start, previous_end)
        current_by_id = {str(item.get("product_id")): item for item in current_rows if item.get("product_id") is not None}
        previous_by_id = {str(item.get("product_id")): item for item in previous_rows if item.get("product_id") is not None}
        product_ids = sorted(set(current_by_id) | set(previous_by_id))
        catalog_rows = source._rows(
            '''select "商品ID" as product_id, "商品名称" as product_name,
                      "类型" as product_type, "系列" as series, "定位" as positioning,
                      "渠道" as channel
                 from store_product_catalog where "店铺ID" = ?''',
            store_id,
        )
        catalog_by_id = {str(item.get("product_id")): item for item in catalog_rows if item.get("product_id") is not None}

        def num(row: dict[str, Any], key: str) -> float:
            return float(row.get(key) or 0)

        current_total_paid = sum(num(row, "paid_amount") for row in current_rows)
        previous_total_paid = sum(num(row, "paid_amount") for row in previous_rows)
        current_total_buyers = sum(num(row, "buyers") for row in current_rows)
        previous_total_buyers = sum(num(row, "buyers") for row in previous_rows)
        current_atv = current_total_paid / current_total_buyers if current_total_buyers else None
        previous_atv = previous_total_paid / previous_total_buyers if previous_total_buyers else None
        atv_change = current_atv - previous_atv if current_atv is not None and previous_atv is not None else None
        atv_change_percent = atv_change / abs(previous_atv) * 100 if atv_change is not None and previous_atv else None

        products: list[dict[str, Any]] = []
        unmapped_count = 0
        for product_id in product_ids:
            catalog = catalog_by_id.get(product_id) or {}
            if not catalog:
                unmapped_count += 1
            current = current_by_id.get(product_id) or {}
            previous = previous_by_id.get(product_id) or {}
            current_paid, previous_paid = num(current, "paid_amount"), num(previous, "paid_amount")
            current_buyers, previous_buyers = num(current, "buyers"), num(previous, "buyers")
            current_unit = current_paid / current_buyers if current_buyers else None
            previous_unit = previous_paid / previous_buyers if previous_buyers else None
            product = {
                "product_id": product_id,
                "product_name": catalog.get("product_name") or product_id,
                "product_type": catalog.get("product_type") or "待归类",
                "series": catalog.get("series") or "待归类",
                "positioning": catalog.get("positioning") or "待归类",
                "channel": catalog.get("channel") or "",
                "current_paid_amount": current_paid if product_id in current_by_id else None,
                "previous_paid_amount": previous_paid if product_id in previous_by_id else None,
                "current_buyers": current_buyers if product_id in current_by_id else None,
                "previous_buyers": previous_buyers if product_id in previous_by_id else None,
                "current_unit_price": current_unit,
                "previous_unit_price": previous_unit,
                "unit_price_delta": current_unit - previous_unit if current_unit is not None and previous_unit is not None else None,
                "current_buyer_share": current_buyers / current_total_buyers * 100 if current_total_buyers else None,
                "previous_buyer_share": previous_buyers / previous_total_buyers * 100 if previous_total_buyers else None,
                "buyer_share_delta_pp": (current_buyers / current_total_buyers - previous_buyers / previous_total_buyers) * 100 if current_total_buyers and previous_total_buyers else None,
                # This additive bridge partitions the overall AOV change by
                # group: current group GMV/current buyers minus previous group
                # GMV/previous buyers. It is descriptive, not causal.
                "aov_contribution": (current_paid / current_total_buyers - previous_paid / previous_total_buyers) if current_total_buyers and previous_total_buyers else None,
                "current_refund_amount": num(current, "refund_amount") if product_id in current_by_id else None,
            }
            products.append(product)

        def grouped(key: str) -> list[dict[str, Any]]:
            groups: dict[str, dict[str, Any]] = {}
            for product in products:
                group_name = str(product.get(key) or "待归类")
                bucket = groups.setdefault(group_name, {"name": group_name, "product_count": 0, "current_paid_amount": 0.0, "previous_paid_amount": 0.0, "current_buyers": 0.0, "previous_buyers": 0.0, "current_refund_amount": 0.0})
                bucket["product_count"] += 1
                for field in ("current_paid_amount", "previous_paid_amount", "current_buyers", "previous_buyers", "current_refund_amount"):
                    bucket[field] += float(product.get(field) or 0)
            output = []
            for bucket in groups.values():
                current_paid, previous_paid = bucket["current_paid_amount"], bucket["previous_paid_amount"]
                current_buyers, previous_buyers = bucket["current_buyers"], bucket["previous_buyers"]
                current_unit = current_paid / current_buyers if current_buyers else None
                previous_unit = previous_paid / previous_buyers if previous_buyers else None
                output.append({
                    **bucket,
                    "current_unit_price": current_unit,
                    "previous_unit_price": previous_unit,
                    "unit_price_delta": current_unit - previous_unit if current_unit is not None and previous_unit is not None else None,
                    "current_buyer_share": current_buyers / current_total_buyers * 100 if current_total_buyers else None,
                    "previous_buyer_share": previous_buyers / previous_total_buyers * 100 if previous_total_buyers else None,
                    "buyer_share_delta_pp": (current_buyers / current_total_buyers - previous_buyers / previous_total_buyers) * 100 if current_total_buyers and previous_total_buyers else None,
                    "aov_contribution": (current_paid / current_total_buyers - previous_paid / previous_total_buyers) if current_total_buyers and previous_total_buyers else None,
                    "current_refund_rate": bucket["current_refund_amount"] / current_paid * 100 if current_paid else None,
                })
            return sorted(output, key=lambda item: float(item.get("aov_contribution") or 0))

        missing_current = [(start_date + timedelta(days=offset)).isoformat() for offset in range(period_days) if (start_date + timedelta(days=offset)).isoformat() not in current_dates]
        missing_previous = [(previous_start + timedelta(days=offset)).isoformat() for offset in range(period_days) if (previous_start + timedelta(days=offset)).isoformat() not in previous_dates]
        warnings: list[str] = []
        if missing_current or missing_previous:
            warnings.append("商品排行存在未覆盖日期，缺失日期未按 0 计入客单价比较。")
        if unmapped_count:
            warnings.append(f"有 {unmapped_count} 个商品缺少主档映射，已归入待归类，不按商品名称猜测系列或类型。")
        data = {
            "current_range": [start_date.isoformat(), end_date.isoformat()],
            "previous_range": [previous_start.isoformat(), previous_end.isoformat()],
            "summary": {"current_paid_amount": current_total_paid, "previous_paid_amount": previous_total_paid, "current_buyers": current_total_buyers, "previous_buyers": previous_total_buyers, "current_unit_price": current_atv, "previous_unit_price": previous_atv, "unit_price_delta": atv_change, "unit_price_change_percent": atv_change_percent, "product_count": len(products), "unmapped_product_count": unmapped_count},
            "series": grouped("series"),
            "types": grouped("product_type"),
            "products": sorted(products, key=lambda item: float(item.get("aov_contribution") or 0)),
            "missing_current_dates": missing_current,
            "missing_previous_dates": missing_previous,
        }
        status = "partial" if missing_current or missing_previous else "ok" if products else "no_data"
        # Coverage describes the user-selected range only. The previous
        # period remains comparison evidence and can still downgrade status,
        # but must not double the visible expected-day count.
        coverage = CoverageSummary(expected_days=period_days, covered_days=len(current_dates), missing_dates=missing_current, latest_data_date=end_date.isoformat() if current_dates else None)
        return self._envelope(
            tool="products.get_structure_profile", context=self._context(store_id, start_date, end_date), status=status,
            data=data,
            metrics=[MetricValue(id="customer_unit_price", label="客单价", value=current_atv, unit="CNY", formula="商品支付金额合计/商品支付买家合计", comparison={"current": current_atv, "previous": previous_atv, "delta": atv_change, "change_percent": atv_change_percent}, source="store_daily_product_rankings")],
            coverage=coverage,
            evidence=[EvidenceRecord(dataset="商品排行", table="store_daily_product_rankings", date_range=[previous_start.isoformat(), end_date.isoformat()], row_count=len(current_rows) + len(previous_rows)), EvidenceRecord(dataset="商品主档", table="store_product_catalog", date_range=[], row_count=len(catalog_rows))],
            warnings=warnings,
        )

    def utry_get_repurchase_diagnosis(self, arguments: dict[str, Any]) -> MCPEnvelope:
        source, selected_start, selected_end = self._source_and_range(
            arguments.get("store_id"),
            self._parse_date(arguments.get("start_date")),
            self._parse_date(arguments.get("end_date")),
        )
        store_id = source._store_id
        limit = min(max(int(arguments.get("limit") or 20), 1), 100)
        days = source._rows(
            '''select distinct "业务日期" as business_day
               from store_daily_utry_repurchase_overviews
               where "店铺ID" = ? and "业务日期" between ? and ?
               order by "业务日期"''',
            store_id, selected_start.isoformat(), selected_end.isoformat(),
        )
        available_days = [str(row.get("business_day")) for row in days if row.get("business_day")]
        coverage = self.query_service.coverage("utry_repurchase", store_id, selected_start, selected_end)
        if not available_days:
            return self._envelope(
                tool="utry.get_repurchase_diagnosis",
                context=self._context(store_id, selected_start, selected_end),
                status="no_data",
                data={
                    "selected_range": [selected_start.isoformat(), selected_end.isoformat()],
                    "latest_business_day": None,
                    "current": {},
                    "previous": {},
                    "comparisons": {},
                    "daily_trend": [],
                    "top_products": [],
                    "sample_snapshot": {},
                    "snapshot_semantics": "30/90/365日指标是按业务日保存的滚动回购快照，不能跨日求和。",
                    "rate_available": False,
                },
                metrics=[], coverage=coverage,
                evidence=[EvidenceRecord(
                    dataset="U先复购", table="store_daily_utry_repurchase_overviews",
                    date_range=[selected_start.isoformat(), selected_end.isoformat()], row_count=0,
                    note="所选区间没有 U先回购快照；不代表店铺从未参与 U先。",
                )],
                warnings=[*self._coverage_warnings(coverage), "所选区间没有 U先回购快照记录。"],
            )

        latest_day = available_days[-1]
        previous_rows = source._rows(
            '''select max("业务日期") as business_day
               from store_daily_utry_repurchase_overviews
               where "店铺ID" = ? and "业务日期" < ?''',
            store_id, latest_day,
        )
        previous_day = str(previous_rows[0].get("business_day")) if previous_rows and previous_rows[0].get("business_day") else None

        aggregate_sql = '''select count(*) as product_count,
                   sum(case when trim(coalesce("是否绑定正装", '')) in ('1', '是', 'true', 'TRUE', 'yes', 'Y') then 1 else 0 end) as bound_regular_product_count,
                   sum(case when trim(coalesce("是否配置回购券", '')) in ('1', '是', 'true', 'TRUE', 'yes', 'Y') then 1 else 0 end) as configured_coupon_count,
                   sum(case when trim(coalesce("是否配置回购礼金", '')) in ('1', '是', 'true', 'TRUE', 'yes', 'Y') then 1 else 0 end) as configured_gift_count,
                   sum(cast(coalesce("同店30日回购UV", '0') as real)) as store_30d_repurchase_uv,
                   sum(cast(coalesce("同店30日回购金额", '0') as real)) as store_30d_repurchase_amount,
                   sum(cast(coalesce("同店90日回购UV", '0') as real)) as store_90d_repurchase_uv,
                   sum(cast(coalesce("同店90日回购金额", '0') as real)) as store_90d_repurchase_amount,
                   sum(cast(coalesce("同店365日回购UV", '0') as real)) as store_365d_repurchase_uv,
                   sum(cast(coalesce("同店365日回购金额", '0') as real)) as store_365d_repurchase_amount,
                   sum(cast(coalesce("同品牌30日回购UV", '0') as real)) as brand_30d_repurchase_uv,
                   sum(cast(coalesce("同品牌30日回购金额", '0') as real)) as brand_30d_repurchase_amount,
                   sum(cast(coalesce("同品牌90日回购UV", '0') as real)) as brand_90d_repurchase_uv,
                   sum(cast(coalesce("同品牌90日回购金额", '0') as real)) as brand_90d_repurchase_amount,
                   sum(cast(coalesce("同品牌365日回购UV", '0') as real)) as brand_365d_repurchase_uv,
                   sum(cast(coalesce("同品牌365日回购金额", '0') as real)) as brand_365d_repurchase_amount
            from store_daily_utry_repurchase_overviews
            where "店铺ID" = ? and "业务日期" = ?'''

        def snapshot(day_value: str | None) -> dict[str, Any]:
            if not day_value:
                return {}
            rows = source._rows(aggregate_sql, store_id, day_value)
            values = dict(rows[0]) if rows else {}
            for key, value in list(values.items()):
                values[key] = _number(value)
            product_count = float(values.get("product_count") or 0)
            values["bound_regular_product_share"] = float(values.get("bound_regular_product_count") or 0) / product_count * 100 if product_count else None
            values["unbound_regular_product_count"] = max(product_count - float(values.get("bound_regular_product_count") or 0), 0)
            values["configured_coupon_share"] = float(values.get("configured_coupon_count") or 0) / product_count * 100 if product_count else None
            values["configured_gift_share"] = float(values.get("configured_gift_count") or 0) / product_count * 100 if product_count else None
            for scope in ("store", "brand"):
                for window in (30, 90, 365):
                    uv = float(values.get(f"{scope}_{window}d_repurchase_uv") or 0)
                    amount = float(values.get(f"{scope}_{window}d_repurchase_amount") or 0)
                    values[f"{scope}_{window}d_repurchase_uv_value"] = amount / uv if uv else None
            values["business_day"] = day_value
            return values

        current = snapshot(latest_day)
        previous = snapshot(previous_day)
        compared_metrics = (
            "store_30d_repurchase_uv", "store_30d_repurchase_amount",
            "store_90d_repurchase_uv", "store_90d_repurchase_amount",
            "store_365d_repurchase_uv", "store_365d_repurchase_amount",
            "brand_30d_repurchase_uv", "brand_30d_repurchase_amount",
            "brand_90d_repurchase_uv", "brand_90d_repurchase_amount",
            "brand_365d_repurchase_uv", "brand_365d_repurchase_amount",
        )
        comparisons: dict[str, dict[str, float | int | None]] = {}
        for metric_id in compared_metrics:
            current_value = current.get(metric_id)
            previous_value = previous.get(metric_id)
            delta = current_value - previous_value if isinstance(current_value, (int, float)) and isinstance(previous_value, (int, float)) else None
            change_percent = delta / abs(previous_value) * 100 if delta is not None and previous_value else None
            comparisons[metric_id] = {
                "current": current_value, "previous": previous_value,
                "delta": delta, "change_percent": change_percent,
            }

        trend_start = max(selected_start, date.fromisoformat(latest_day) - timedelta(days=29))
        daily_rows = source._rows(
            '''select "业务日期" as business_day, count(*) as product_count,
                      sum(cast(coalesce("同店30日回购UV", '0') as real)) as store_30d_repurchase_uv,
                      sum(cast(coalesce("同店30日回购金额", '0') as real)) as store_30d_repurchase_amount,
                      sum(cast(coalesce("同店90日回购UV", '0') as real)) as store_90d_repurchase_uv,
                      sum(cast(coalesce("同店90日回购金额", '0') as real)) as store_90d_repurchase_amount,
                      sum(cast(coalesce("同店365日回购UV", '0') as real)) as store_365d_repurchase_uv,
                      sum(cast(coalesce("同店365日回购金额", '0') as real)) as store_365d_repurchase_amount,
                      sum(cast(coalesce("同品牌365日回购UV", '0') as real)) as brand_365d_repurchase_uv,
                      sum(cast(coalesce("同品牌365日回购金额", '0') as real)) as brand_365d_repurchase_amount
               from store_daily_utry_repurchase_overviews
               where "店铺ID" = ? and "业务日期" between ? and ?
               group by "业务日期" order by "业务日期"''',
            store_id, trend_start.isoformat(), latest_day,
        )
        daily_trend = [{key: _number(value) if key != "business_day" else value for key, value in dict(row).items()} for row in daily_rows]
        top_rows = source._rows(
            '''select "商品ID" as product_id, "商品名称" as product_name, "ju_id" as ju_id,
                      "叶子类目" as leaf_category, "是否绑定正装" as bind_regular_product,
                      "是否配置回购券" as configured_repurchase_coupon,
                      "是否配置回购礼金" as configured_repurchase_gift,
                      cast(coalesce("同店30日回购UV", '0') as real) as store_30d_repurchase_uv,
                      cast(coalesce("同店30日回购金额", '0') as real) as store_30d_repurchase_amount,
                      cast(coalesce("同店90日回购UV", '0') as real) as store_90d_repurchase_uv,
                      cast(coalesce("同店90日回购金额", '0') as real) as store_90d_repurchase_amount,
                      cast(coalesce("同店365日回购UV", '0') as real) as store_365d_repurchase_uv,
                      cast(coalesce("同店365日回购金额", '0') as real) as store_365d_repurchase_amount,
                      cast(coalesce("同品牌365日回购UV", '0') as real) as brand_365d_repurchase_uv,
                      cast(coalesce("同品牌365日回购金额", '0') as real) as brand_365d_repurchase_amount
               from store_daily_utry_repurchase_overviews
               where "店铺ID" = ? and "业务日期" = ?
               order by store_365d_repurchase_amount desc, store_365d_repurchase_uv desc limit ?''',
            store_id, latest_day, limit,
        )
        top_products = [{key: _number(value) if key.endswith(("_uv", "_amount")) else value for key, value in dict(row).items()} for row in top_rows]
        total_store_365_amount = float(current.get("store_365d_repurchase_amount") or 0)
        for row in top_products:
            amount = float(row.get("store_365d_repurchase_amount") or 0)
            uv = float(row.get("store_365d_repurchase_uv") or 0)
            row["store_365d_amount_share"] = amount / total_store_365_amount * 100 if total_store_365_amount else None
            row["store_365d_repurchase_uv_value"] = amount / uv if uv else None

        sample_day_rows = source._rows(
            '''select max("业务日期") as business_day from store_daily_utry_sample_overviews
               where "店铺ID" = ? and "业务日期" <= ?''', store_id, latest_day,
        )
        sample_day = str(sample_day_rows[0].get("business_day")) if sample_day_rows and sample_day_rows[0].get("business_day") else None
        sample_snapshot: dict[str, Any] = {}
        sample_row_count = 0
        if sample_day:
            sample_rows = source._rows(
                '''select count(*) as product_count,
                          sum(cast(coalesce("派样单量", '0') as real)) as sample_orders,
                          sum(cast(coalesce("派样人次", '0') as real)) as sample_people,
                          sum(cast(coalesce("派样GMV", '0') as real)) as sample_gmv,
                          sum(cast(coalesce("派样365天商家新客数", '0') as real)) as merchant_new_customers_365d,
                          sum(cast(coalesce("派样180天商家新客数", '0') as real)) as merchant_new_customers_180d,
                          sum(cast(coalesce("新会员数", '0') as real)) as new_members,
                          sum(cast(coalesce("新粉丝数", '0') as real)) as new_followers
                   from store_daily_utry_sample_overviews where "店铺ID" = ? and "业务日期" = ?''',
                store_id, sample_day,
            )
            sample_snapshot = {key: _number(value) for key, value in dict(sample_rows[0]).items()} if sample_rows else {}
            sample_snapshot["business_day"] = sample_day
            sample_row_count = int(sample_snapshot.get("product_count") or 0)

        metric_labels = {
            "store_30d_repurchase_uv": ("同店30日回购UV合计", "person"),
            "store_30d_repurchase_amount": ("同店30日回购金额", "CNY"),
            "store_90d_repurchase_uv": ("同店90日回购UV合计", "person"),
            "store_90d_repurchase_amount": ("同店90日回购金额", "CNY"),
            "store_365d_repurchase_uv": ("同店365日回购UV合计", "person"),
            "store_365d_repurchase_amount": ("同店365日回购金额", "CNY"),
            "brand_365d_repurchase_uv": ("同品牌365日回购UV合计", "person"),
            "brand_365d_repurchase_amount": ("同品牌365日回购金额", "CNY"),
        }
        metrics = [
            MetricValue(
                id=metric_id, label=label, value=current.get(metric_id), unit=unit,
                formula=f"最新业务日 {latest_day} 全量商品字段求和；不跨业务日累加",
                comparison=comparisons.get(metric_id, {}), source="store_daily_utry_repurchase_overviews",
            )
            for metric_id, (label, unit) in metric_labels.items()
        ]
        warnings = self._coverage_warnings(coverage)
        warnings.extend([
            "30/90/365日回购指标是每日滚动快照，趋势按日比较，不能跨日求和。",
            "回购UV按商品行汇总，跨商品可能重复，不代表店铺唯一回购买家数。",
            "当前没有首批派样 cohort 分母，不能计算 U先回购率。",
        ])
        return self._envelope(
            tool="utry.get_repurchase_diagnosis",
            context=self._context(store_id, selected_start, selected_end),
            status="partial" if coverage.missing_dates or coverage.missing_datasets or coverage.partial_datasets else "ok",
            data={
                "selected_range": [selected_start.isoformat(), selected_end.isoformat()],
                "latest_business_day": latest_day,
                "previous_business_day": previous_day,
                "current": current,
                "previous": previous,
                "comparisons": comparisons,
                "daily_trend": daily_trend,
                "top_products": top_products,
                "sample_snapshot": sample_snapshot,
                "snapshot_semantics": "每个业务日是一组30/90/365日滚动回购快照；总盘只使用最新业务日，趋势逐日比较。",
                "uv_semantics": "商品回购UV合计可能跨商品重复，不等于店铺唯一回购买家数。",
                "rate_available": False,
                "rate_unavailable_reason": "缺少与当前回购窗口严格对应的首批派样 cohort 人数分母。",
            },
            metrics=metrics,
            coverage=coverage,
            evidence=[
                EvidenceRecord(
                    dataset="U先复购", table="store_daily_utry_repurchase_overviews",
                    date_range=[selected_start.isoformat(), selected_end.isoformat()],
                    row_count=sum(int(row.get("product_count") or 0) for row in daily_trend),
                    note="最新业务日用于总盘；按日快照用于趋势；Top N 仅展示，全量最新日用于总计。",
                    metric_ids=list(metric_labels),
                ),
                EvidenceRecord(
                    dataset="U先派样", table="store_daily_utry_sample_overviews",
                    date_range=[sample_day] if sample_day else [], row_count=sample_row_count,
                    note="派样快照仅作当前活动规模背景，不作为回购率 cohort 分母。",
                ),
            ],
            provenance={"snapshot_day": latest_day, "comparison_day": previous_day, "aggregation": "latest_day_full_population"},
            warnings=list(dict.fromkeys(warnings)),
        )

    def customers_get_diagnosis(self, arguments: dict[str, Any]) -> MCPEnvelope:
        """Return reconciled customer lifecycle metrics from one shared derivation layer."""
        source = self.analytics._source_for_store(arguments.get("store_id"))
        store_id = source._store_id
        start_date, end_date = self._bounded_range(source, arguments, days=30)
        period_days = (end_date - start_date).days + 1
        previous_end = start_date - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_days - 1)
        getter = getattr(source, "get_analysis_snapshot", None)
        if getter is None:
            raise RuntimeError("客户诊断需要规范化本地分析数据源")
        current = getter(start_date, end_date).customer
        previous = getter(previous_start, previous_end).customer
        current_metrics = {item.id: item for item in current.derived_metrics}
        previous_metrics = {item.id: item for item in previous.derived_metrics}
        coverage = self.query_service.coverage("customers", store_id, start_date, end_date)
        previous_coverage = self.query_service.coverage("customers", store_id, previous_start, previous_end)
        comparable = self.query_service._coverage_complete(coverage) and self.query_service._coverage_complete(previous_coverage)
        comparisons: dict[str, dict[str, float | int | None]] = {}
        metrics: list[MetricValue] = []
        unit_labels = {"currency": "CNY", "count": "person", "percent": "percent", "ratio": "ratio"}
        for metric_id, item in current_metrics.items():
            current_value = _optional_number(item.value) if item.status == "available" else None
            previous_item = previous_metrics.get(metric_id)
            previous_value = _optional_number(previous_item.value) if previous_item and previous_item.status == "available" else None
            delta = current_value - previous_value if comparable and current_value is not None and previous_value is not None else None
            change_percent = delta / abs(previous_value) * 100 if delta is not None and previous_value not in (None, 0) else None
            comparison = {"current": current_value, "previous": previous_value, "delta": delta, "change_percent": change_percent}
            comparisons[metric_id] = comparison
            metrics.append(MetricValue(
                id=metric_id,
                label=item.label,
                value=current_value,
                unit=unit_labels.get(item.unit, item.unit),
                formula=item.formula,
                comparison=comparison,
                source="store_daily_overviews + store_daily_customer_overviews",
            ))
        warnings = [*self._coverage_warnings(coverage), *current.quality_warnings]
        if not comparable:
            warnings.append("当前周期或上一周期客户数据覆盖不完整，派生指标未计算涨跌幅。")
        data = {
            "current_range": [start_date.isoformat(), end_date.isoformat()],
            "previous_range": [previous_start.isoformat(), previous_end.isoformat()],
            "comparable": comparable,
            "raw": {
                "shop_customers": current.shop_customers,
                "shop_customers_stat_date": current.shop_customers_stat_date.isoformat() if current.shop_customers_stat_date else None,
                "new_visit_paid_buyers": current.new_customer_paid_buyers,
                "new_visit_paid_amount": _number(current.new_customer_paid_amount),
                "no_purchase_returners": current.no_purchase_returners,
                "no_purchase_paid_buyers": current.no_purchase_buyers,
                "repeat_paid_buyers": current.repeat_customers,
                "repeat_paid_amount": _number(current.repeat_customer_paid_amount),
            },
            "derived_metrics": [item.model_dump(mode="json") for item in current.derived_metrics],
            "comparisons": comparisons,
            "segments": [item.model_dump(mode="json") for item in current.segments],
            "daily": [item.model_dump(mode="json") for item in current.daily_metrics],
            "quality_warnings": current.quality_warnings,
            "semantics": {
                "first_purchase": "总支付减去已购回访支付，包含新访成交和未购回访后的首次成交。",
                "population": "区间人数为每日人数累计，不是手机号、地址或买家ID跨日去重人数。",
                "causal_boundary": "客户结构变化是描述性证据，不能单独证明营销动作产生增量。",
            },
        }
        return self._envelope(
            tool="customers.get_diagnosis",
            context=self._context(store_id, start_date, end_date),
            status="partial" if coverage.missing_dates or coverage.missing_datasets or coverage.partial_datasets else "ok" if current.daily_metrics else "no_data",
            data=data,
            metrics=metrics,
            coverage=coverage,
            evidence=[
                EvidenceRecord(dataset="店铺日概览", table="store_daily_overviews", date_range=[start_date.isoformat(), end_date.isoformat()], row_count=len(current.daily_metrics), note="提供总支付人数和总支付金额。", metric_ids=["buyers", "gmv"]),
                EvidenceRecord(dataset="客户分析", table="store_daily_customer_overviews", date_range=[start_date.isoformat(), end_date.isoformat()], row_count=len(current.daily_metrics), note="提供新访、未购回访和已购回访分层；人数为日累计。", metric_ids=list(current_metrics)),
            ],
            provenance={"derivation": "analytics.derived_metrics.CUSTOMER_DERIVED_METRICS", "comparable": comparable},
            warnings=list(dict.fromkeys(warnings)),
        )

    def customer_service_get_diagnosis(self, arguments: dict[str, Any]) -> MCPEnvelope:
        """Return service funnel, daily trend and account-level evidence."""
        source = self.analytics._source_for_store(arguments.get("store_id"))
        store_id = source._store_id
        start_date, end_date = self._bounded_range(source, arguments, days=7)
        period_days = (end_date - start_date).days + 1
        previous_start, previous_end = start_date - timedelta(days=period_days), start_date - timedelta(days=1)

        def overview(period_start: date, period_end: date) -> tuple[dict[str, Any], list[dict[str, Any]]]:
            daily = source._rows(
                '''select "业务日期" as business_day, "客服销售额" as sales_amount, "客服销售人数" as sale_users,
                          "咨询人数" as consult_users, "接待人数" as reception_users, "平均响应时长（秒）" as avg_reply_seconds,
                          "客户满意率" as satisfaction_rate, "成功退款金额" as refund_amount, "净销售额" as net_sales_amount
                     from store_daily_customer_service_overviews
                    where "店铺ID" = ? and "业务日期" between ? and ? order by "业务日期"''',
                store_id, period_start.isoformat(), period_end.isoformat(),
            )
            def total(key: str) -> float:
                return sum(float(row.get(key) or 0) for row in daily)
            sales = total("sales_amount"); buyers = total("sale_users"); consult = total("consult_users"); reception = total("reception_users")
            refund = total("refund_amount"); net = total("net_sales_amount") if any(row.get("net_sales_amount") not in (None, "") for row in daily) else sales - refund
            return ({"sales_amount": sales, "sale_users": buyers, "consult_users": consult, "reception_users": reception, "reception_rate": reception / consult * 100 if consult else None, "sales_conversion_rate": buyers / consult * 100 if consult else None, "sales_unit_price": sales / buyers if buyers else None, "avg_reply_seconds": sum(float(row.get("avg_reply_seconds") or 0) for row in daily) / len(daily) if daily else None, "satisfaction_rate": sum(float(row.get("satisfaction_rate") or 0) for row in daily) / len(daily) * 100 if daily else None, "refund_amount": refund, "net_sales_amount": net, "covered_days": len(daily)}, daily)

        current, daily = overview(start_date, end_date)
        previous, _ = overview(previous_start, previous_end)
        account_rows = source._rows(
            '''select "旺旺昵称" as account_name,
                      sum(cast(coalesce("咨询人数", '0') as real)) as consult_users,
                      sum(cast(coalesce("有效接待人数", '0') as real)) as reception_users,
                      sum(cast(coalesce("销售人数", '0') as real)) as sale_users,
                      sum(cast(coalesce("销售额", '0') as real)) as sales_amount,
                      sum(cast(coalesce("成功退款金额", '0') as real)) as refund_amount,
                      sum(cast(coalesce("净销售额", '0') as real)) as net_sales_amount
                 from store_daily_customer_service_accounts
                where "店铺ID" = ? and "业务日期" between ? and ?
                group by "旺旺昵称"''',
            store_id, start_date.isoformat(), end_date.isoformat(),
        )
        accounts = []
        for row in account_rows:
            consult = float(row.get("consult_users") or 0); reception = float(row.get("reception_users") or 0); buyers = float(row.get("sale_users") or 0); sales = float(row.get("sales_amount") or 0)
            accounts.append({**row, "reception_rate": reception / consult * 100 if consult else None, "sales_conversion_rate": buyers / consult * 100 if consult else None, "sales_unit_price": sales / buyers if buyers else None, "refund_rate": float(row.get("refund_amount") or 0) / sales * 100 if sales else None})
        accounts.sort(key=lambda item: float(item.get("sales_amount") or 0), reverse=True)
        comparison = {}
        for key in ("sales_amount", "sale_users", "consult_users", "reception_users", "reception_rate", "sales_conversion_rate", "sales_unit_price", "avg_reply_seconds", "satisfaction_rate", "refund_amount", "net_sales_amount"):
            cur, prev = current.get(key), previous.get(key)
            comparison[key] = {"current": cur, "previous": prev, "delta": cur - prev if cur is not None and prev is not None else None, "change_percent": (cur - prev) / abs(prev) * 100 if cur is not None and prev not in (None, 0) else None}
        data = {"current_range": [start_date.isoformat(), end_date.isoformat()], "previous_range": [previous_start.isoformat(), previous_end.isoformat()], "current": current, "previous": previous, "comparison": comparison, "daily": daily, "accounts": accounts[:100]}
        coverage_rows = source._rows('''select count(distinct "业务日期") as covered_days from store_daily_customer_service_overviews where "店铺ID" = ? and "业务日期" between ? and ?''', store_id, start_date.isoformat(), end_date.isoformat())
        covered_days = int(coverage_rows[0].get("covered_days") or 0) if coverage_rows else 0
        status = "partial" if covered_days < period_days else "ok" if daily else "no_data"
        warnings = ["客服概览存在未覆盖日期，缺失日期未按 0 计入比较。"] if covered_days < period_days else []
        return self._envelope(
            tool="customer_service.get_diagnosis", context=self._context(store_id, start_date, end_date), status=status, data=data,
            metrics=[MetricValue(id="customer_service_sales", label="客服销售额", value=current.get("sales_amount"), unit="CNY", formula="客服销售额合计", comparison=comparison["sales_amount"], source="store_daily_customer_service_overviews"), MetricValue(id="customer_service_conversion", label="询单转化率", value=current.get("sales_conversion_rate"), unit="percent", formula="客服销售人数/咨询人数", comparison=comparison["sales_conversion_rate"], source="store_daily_customer_service_overviews")],
            coverage=CoverageSummary(expected_days=period_days, covered_days=covered_days, missing_dates=[(start_date + timedelta(days=offset)).isoformat() for offset in range(period_days) if (start_date + timedelta(days=offset)).isoformat() not in {str(row.get("business_day")) for row in daily}], latest_data_date=end_date.isoformat() if daily else None),
            evidence=[EvidenceRecord(dataset="客服概览", table="store_daily_customer_service_overviews", date_range=[start_date.isoformat(), end_date.isoformat()], row_count=len(daily)), EvidenceRecord(dataset="客服账号明细", table="store_daily_customer_service_accounts", date_range=[start_date.isoformat(), end_date.isoformat()], row_count=len(account_rows))],
            warnings=warnings,
        )

    def reviews_get_diagnosis(self, arguments: dict[str, Any]) -> MCPEnvelope:
        """Expose review/VOC evidence without treating text frequency as sales causality."""
        start_date = self._parse_date(arguments.get("start_date"))
        end_date = self._parse_date(arguments.get("end_date"))
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date - timedelta(days=6)
        service = ReviewService(Path(settings.local_database_path))
        analysis = service.analysis(
            product_id=str(arguments.get("product_id") or "").strip() or None,
            series=str(arguments.get("series") or "").strip() or None,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            top_limit=20,
        )
        asks = service.ask_summary()
        unanswered = service.list_asks(has_answer=False, page=1, page_size=20)
        review_data = analysis.model_dump(mode="json")
        ask_data = asks.model_dump(mode="json")
        data = {
            "reviews": review_data,
            "asks": ask_data,
            "representative_unanswered_questions": [item.model_dump(mode="json") for item in unanswered.items],
            "scope_note": "评价按所选日期区间；问大家汇总按当前已采集全量。词频和问题率是用户反馈信号，不直接证明成交因果。",
        }
        total_reviews = int(analysis.total_reviews or 0)
        total_questions = int(asks.total_questions or 0)
        latest_candidates = [value for value in (analysis.end_date, asks.latest_question_date) if value]
        status = "ok" if total_reviews or total_questions else "no_data"
        warnings = ["评价/问大家为事件型数据，没有评价的日期不能按经营数据缺失处理。"]
        if not total_reviews:
            warnings.append("所选区间没有评价记录；不代表商品没有质量问题。")
        return self._envelope(
            tool="reviews.get_diagnosis",
            context=self._context(arguments.get("store_id"), start_date, end_date),
            status=status,
            data=data,
            metrics=[
                MetricValue(id="review_count", label="评价数", value=total_reviews, unit="review", formula="所选区间评价记录数", source="review_records"),
                MetricValue(id="negative_review_rate", label="问题评价率", value=analysis.negative_rate, unit="percent", formula="问题评价数/评价数", source="review_records"),
                MetricValue(id="unanswered_question_count", label="未回答问题数", value=asks.unanswered_questions, unit="question", formula="已采集问大家中未回答问题数", source="ask_records"),
            ],
            coverage=CoverageSummary(latest_data_date=max(latest_candidates) if latest_candidates else None),
            evidence=[
                EvidenceRecord(dataset="评价明细", table="review_records", date_range=[start_date.isoformat(), end_date.isoformat()], row_count=total_reviews, note="评价等级与文本问题分开统计"),
                EvidenceRecord(dataset="问大家", table="ask_records", row_count=total_questions, note="问大家汇总为当前已采集全量"),
            ],
            warnings=warnings,
        )

    def brand_assets_get_diagnosis(self, arguments: dict[str, Any]) -> MCPEnvelope:
        """Expose brand facts without forcing the store id to equal a brand id."""
        source = self.analytics._source_for_store(arguments.get("store_id"))
        store_id = source._store_id
        brand_id = str(arguments.get("brand_id") or "").strip()
        warnings: list[str] = []
        if not brand_id:
            scoped = source._rows(
                '''select "品牌ID" as brand_id from brand_store_scopes
                    where "店铺ID" = ? order by is_primary desc, "创建时间" limit 1''',
                store_id,
            )
            if scoped:
                brand_id = str(scoped[0].get("brand_id") or "")
            else:
                brands = source._rows('''select "品牌ID" as brand_id from brands where "品牌状态" = 'active' order by "更新时间" desc limit 2''')
                if len(brands) == 1:
                    brand_id = str(brands[0].get("brand_id") or "")
                    warnings.append("当前店铺未配置品牌范围，因本地仅有一个启用品牌，已使用该品牌；建议在品牌范围中建立店铺关联。")
        if not brand_id:
            today = date.today()
            return self._envelope(
                tool="brand_assets.get_diagnosis", context=self._context(store_id, today, today), status="no_data",
                data={"rows": []}, metrics=[], coverage=CoverageSummary(), evidence=[],
                warnings=["没有可用于当前店铺的品牌范围。"],
            )
        bounds = source._rows(
            '''select min("业务日期") as first_date, max("业务日期") as latest_date
                 from brand_asset_daily_overviews where "品牌ID" = ?''',
            brand_id,
        )
        latest = date.fromisoformat(str(bounds[0].get("latest_date"))) if bounds and bounds[0].get("latest_date") else date.today()
        start_date = self._parse_date(arguments.get("start_date")) or latest - timedelta(days=6)
        end_date = min(self._parse_date(arguments.get("end_date")) or latest, latest)
        period_days = (end_date - start_date).days + 1
        previous_start, previous_end = start_date - timedelta(days=period_days), start_date - timedelta(days=1)

        def aggregate(period_start: date, period_end: date) -> dict[str, Any]:
            rows = source._rows(
                '''select sum(cast(nullif("成交金额", '') as real)) as gmv,
                          sum(cast(nullif("成交人数", '') as real)) as buyers,
                          sum(cast(nullif("会员成交金额", '') as real)) as member_gmv,
                          avg(cast(nullif("消费者数", '') as real)) as consumers,
                          avg(cast(nullif("关系加深率", '') as real)) as relationship_deepening_rate,
                          avg(cast(nullif("蓄水购买比", '') as real)) as reservoir_purchase_ratio,
                          avg(cast(nullif("消费者价值预测", '') as real)) as predicted_consumer_value
                     from brand_asset_daily_overviews
                    where "品牌ID" = ? and "业务日期" between ? and ?''',
                brand_id, period_start.isoformat(), period_end.isoformat(),
            )
            return rows[0] if rows else {}

        current, previous = aggregate(start_date, end_date), aggregate(previous_start, previous_end)
        comparisons: dict[str, dict[str, float | None]] = {}
        for key in ("gmv", "buyers", "member_gmv", "consumers", "relationship_deepening_rate", "reservoir_purchase_ratio", "predicted_consumer_value"):
            cur, prev = _optional_number(current.get(key)), _optional_number(previous.get(key))
            comparisons[key] = {"current": cur, "previous": prev, "change_percent": (float(cur) - float(prev)) / abs(float(prev)) * 100 if cur is not None and prev not in (None, 0) else None}
        daily = source._rows(
            '''select "业务日期" as business_day, "统计范围" as statistic_scope,
                      cast(nullif("消费者数", '') as real) as consumers,
                      cast(nullif("关系加深率", '') as real) as relationship_deepening_rate,
                      cast(nullif("蓄水购买比", '') as real) as reservoir_purchase_ratio,
                      cast(nullif("成交金额", '') as real) as gmv,
                      cast(nullif("成交人数", '') as real) as buyers,
                      cast(nullif("会员成交金额", '') as real) as member_gmv,
                      cast(nullif("消费者价值预测", '') as real) as predicted_consumer_value
                 from brand_asset_daily_overviews
                where "品牌ID" = ? and "业务日期" between ? and ? order by "业务日期"''',
            brand_id, start_date.isoformat(), end_date.isoformat(),
        )
        metric_rows = source._rows(
            '''with ranked as (
                   select "业务日期" as business_day, "维度类型" as dimension_type,
                          "维度编码" as dimension_code, "指标名称" as metric_name,
                          cast(nullif("品牌值", '') as real) as brand_value,
                          row_number() over (partition by "维度类型", "维度编码" order by "业务日期" desc) as rn
                     from brand_asset_daily_metrics
                    where "品牌ID" = ? and "业务日期" between ? and ?
               ) select business_day, dimension_type, dimension_code, metric_name, brand_value
                   from ranked where rn = 1 order by dimension_type, metric_name limit 240''',
            brand_id, start_date.isoformat(), end_date.isoformat(),
        )
        brand_rows = source._rows('''select "品牌名称" as brand_name from brands where "品牌ID" = ? limit 1''', brand_id)
        observed = {str(item.get("business_day")) for item in daily if item.get("business_day")}
        missing = [(start_date + timedelta(days=offset)).isoformat() for offset in range(period_days) if (start_date + timedelta(days=offset)).isoformat() not in observed]
        status = "partial" if missing else "ok" if daily else "no_data"
        if missing:
            warnings.append("品牌资产存在未覆盖日期，缺失日期未按 0 参与比较。")
        return self._envelope(
            tool="brand_assets.get_diagnosis", context=self._context(store_id, start_date, end_date), status=status,
            data={
                "brand_id": brand_id, "brand_name": brand_rows[0].get("brand_name") if brand_rows else None,
                "current_range": [start_date.isoformat(), end_date.isoformat()], "previous_range": [previous_start.isoformat(), previous_end.isoformat()],
                "current": current, "previous": previous, "comparison": comparisons, "daily": daily, "rows": metric_rows,
                "scope_note": "品牌资产为品牌主体口径；与店铺成交的联动属于描述性观察，不自动代表因果。",
            },
            metrics=[
                MetricValue(id="brand_consumers", label="品牌消费者数", value=_optional_number(current.get("consumers")), unit="person", formula="所选区间品牌消费者数日均", comparison=comparisons["consumers"], source="brand_asset_daily_overviews"),
                MetricValue(id="brand_gmv", label="品牌成交金额", value=_optional_number(current.get("gmv")), unit="CNY", formula="所选区间品牌成交金额合计", comparison=comparisons["gmv"], source="brand_asset_daily_overviews"),
                MetricValue(id="brand_member_gmv", label="品牌会员成交金额", value=_optional_number(current.get("member_gmv")), unit="CNY", formula="所选区间品牌会员成交金额合计", comparison=comparisons["member_gmv"], source="brand_asset_daily_overviews"),
            ],
            coverage=CoverageSummary(expected_days=period_days, covered_days=len(observed), missing_dates=missing, latest_data_date=latest.isoformat()),
            evidence=[
                EvidenceRecord(dataset="品牌资产总览", table="brand_asset_daily_overviews", date_range=[start_date.isoformat(), end_date.isoformat()], row_count=len(daily)),
                EvidenceRecord(dataset="品牌资产指标", table="brand_asset_daily_metrics", date_range=[start_date.isoformat(), end_date.isoformat()], row_count=len(metric_rows)),
            ],
            warnings=warnings,
        )

    def overview_get_store_summary(self, arguments: dict[str, Any]) -> MCPEnvelope:
        source, start_date, end_date = self._source_and_range(arguments.get("store_id"), self._parse_date(arguments.get("start_date")), self._parse_date(arguments.get("end_date")))
        row = self._overview_row(source, start_date, end_date)
        paid = _optional_number(row.get("paid_amount")); refund = _optional_number(row.get("refund_amount")); net_paid = _optional_number(row.get("net_paid_amount"))
        spends = {"keyword_spend": _optional_number(row.get("keyword_spend")), "crowd_spend": _optional_number(row.get("crowd_spend")), "smart_scene_spend": _optional_number(row.get("smart_scene_spend")), "promotion_spend": _optional_number(row.get("promotion_spend")), "cps_commission": _optional_number(row.get("cps_commission"))}
        cost_values = [spends[key] for key in ("keyword_spend", "crowd_spend", "smart_scene_spend", "promotion_spend", "cps_commission")]
        total_cost = sum((float(value or 0) for value in cost_values), 0.0) if any(value is not None for value in cost_values) else None
        summary = {"paid_amount": paid, "net_paid_amount": net_paid if net_paid is not None else (paid - refund if paid is not None and refund is not None else None), "refund_amount": refund, "visitors": _optional_number(row.get("visitors")), "buyers": _optional_number(row.get("buyers")), "payment_conversion_rate": _optional_number(row.get("conversion_rate")), "customer_unit_price": (paid / row.get("buyers") if paid is not None and row.get("buyers") not in (None, 0) else None), **spends, "total_cost": total_cost, "fee_ratio": total_cost / paid if total_cost is not None and paid not in (None, 0) else None}
        coverage = self._coverage(getattr(source, "get_data_coverage", lambda *_: [])(start_date, end_date), start_date, end_date, "店铺日概览")
        metrics = [MetricValue(id=key, label=label, value=summary.get(key), unit="percent" if key == "fee_ratio" else "CNY" if key not in {"visitors", "buyers", "payment_conversion_rate"} else "percent" if key == "payment_conversion_rate" else "person", formula=formula, source="store_daily_overviews") for key, label, formula in (("paid_amount","支付金额","sum(支付金额)"),("net_paid_amount","净支付金额","支付金额-退款金额"),("refund_amount","退款金额","sum(退款金额)"),("total_cost","总成本","关键词+人群+智能场景+全站+淘宝客"),("fee_ratio","经营费比","总成本/支付金额"))]
        return self._envelope(tool="overview.get_store_summary", context=self._context(source._store_id, start_date, end_date), status=self._status(coverage, paid is not None), data={"summary": summary, "range": [start_date.isoformat(), end_date.isoformat()]}, metrics=metrics, coverage=coverage, evidence=[EvidenceRecord(dataset="店铺经营总览", table="store_daily_overviews", date_range=[start_date.isoformat(), end_date.isoformat()], row_count=int(row.get("row_count") or 0))], warnings=self._coverage_warnings(coverage))

    def overview_get_metric_trend(self, arguments: dict[str, Any]) -> MCPEnvelope:
        source, start_date, end_date = self._source_and_range(arguments.get("store_id"), self._parse_date(arguments.get("start_date")), self._parse_date(arguments.get("end_date")))
        rows = source._rows('''select "业务日期" as business_day, "支付金额" as paid_amount, "退款金额（支付时间）" as refund_amount, "净支付金额" as net_paid_amount, "访客数" as visitors, "支付买家数" as buyers, "支付转化率" as conversion_rate, "关键词推广花费" as keyword_spend, "精准人群推广花费" as crowd_spend, "智能场景花费" as smart_scene_spend, "全站推广花费" as promotion_spend, "淘宝客佣金" as cps_commission from store_daily_overviews where "店铺ID" = ? and "业务日期" between ? and ? order by "业务日期"''', source._store_id, start_date.isoformat(), end_date.isoformat())
        data_rows = []
        for row in rows:
            values = {key: _optional_number(row.get(key)) for key in ("paid_amount","refund_amount","net_paid_amount","visitors","buyers","conversion_rate","keyword_spend","crowd_spend","smart_scene_spend","promotion_spend","cps_commission")}
            costs = [values.get(key) for key in ("keyword_spend","crowd_spend","smart_scene_spend","promotion_spend","cps_commission")]
            values["total_cost"] = sum((float(value or 0) for value in costs), 0.0) if any(value is not None for value in costs) else None
            values["fee_ratio"] = values["total_cost"] / values["paid_amount"] if values["total_cost"] is not None and values["paid_amount"] not in (None, 0) else None
            data_rows.append({"business_day": row.get("business_day"), **values})
        coverage = self._coverage(getattr(source, "get_data_coverage", lambda *_: [])(start_date, end_date), start_date, end_date, "店铺日概览")
        return self._envelope(tool="overview.get_metric_trend", context=self._context(source._store_id, start_date, end_date), status=self._status(coverage, bool(rows)), data={"rows": data_rows}, metrics=[], coverage=coverage, evidence=[EvidenceRecord(dataset="店铺经营总览", table="store_daily_overviews", date_range=[start_date.isoformat(), end_date.isoformat()], row_count=len(rows))], warnings=self._coverage_warnings(coverage))

    def promotions_get_efficiency(self, arguments: dict[str, Any]) -> MCPEnvelope:
        source, start_date, end_date = self._source_and_range(arguments.get("store_id"), self._parse_date(arguments.get("start_date")), self._parse_date(arguments.get("end_date")))
        workbench = source.get_promotion_workbench(start_date, end_date)
        summary = workbench.summary.model_dump(mode="json")
        campaigns = [self._promotion_row(item) for item in workbench.campaigns]
        low = [item for item in campaigns if item["spend"] > 0 and item["roi"] < 1]
        low_spend = sum(float(item["spend"]) for item in low)
        summary.update({"roi": float(workbench.summary.roi), "low_efficiency_campaign_count": len(low), "low_efficiency_spend": low_spend, "low_efficiency_spend_share": low_spend / float(workbench.summary.spend) * 100 if workbench.summary.spend else None, "high_efficiency_campaign_count": sum(1 for item in campaigns if item["spend"] > 0 and item["roi"] >= 3)})
        coverage = CoverageSummary(expected_days=(end_date-start_date).days+1, covered_days=min((item.covered_days for item in workbench.coverage), default=0), latest_data_date=end_date.isoformat())
        return self._envelope(tool="promotions.get_efficiency", context=self._context(source._store_id, start_date, end_date), status="ok" if campaigns else "no_data", data={"summary": summary, "scenes": [self._promotion_row(item) for item in workbench.scenes], "campaigns": campaigns}, metrics=[MetricValue(id="promotion_spend", label="推广花费", value=float(workbench.summary.spend), unit="CNY", formula="sum(花费)", source="store_daily_promotion_campaigns"), MetricValue(id="promotion_roi", label="推广 ROI", value=float(workbench.summary.roi), unit="ratio", formula="总成交金额/花费", source="store_daily_promotion_campaigns")], coverage=coverage, evidence=[EvidenceRecord(dataset="推广计划", table="store_daily_promotion_campaigns", date_range=[start_date.isoformat(), end_date.isoformat()], row_count=len(campaigns))], warnings=[] if campaigns else ["所选区间没有推广计划数据。"])

    def promotions_get_drilldown(self, arguments: dict[str, Any]) -> MCPEnvelope:
        source, start_date, end_date = self._source_and_range(arguments.get("store_id"), self._parse_date(arguments.get("start_date")), self._parse_date(arguments.get("end_date")))
        workbench = source.get_promotion_workbench(start_date, end_date)
        level = str(arguments.get("level") or "campaign").lower()
        levels = {"scene": workbench.scenes, "campaign": workbench.campaigns, "product": workbench.items, "item": workbench.items, "adgroup": workbench.adgroups, "keyword": workbench.keywords, "audience": workbench.audiences}
        if level not in levels:
            raise ValueError("promotions.get_drilldown level must be scene, campaign, product, adgroup, keyword, or audience")
        rows = [self._promotion_row(item) for item in levels[level]]
        scene = str(arguments.get("scene") or "").strip(); campaign_id = str(arguments.get("campaign_id") or "").strip(); product_id = str(arguments.get("product_id") or "").strip(); query = str(arguments.get("query") or "").strip()
        for item in rows:
            item.setdefault("campaign_id", item.get("parent_id") if level not in {"scene", "campaign"} else item.get("dimension_id" if level == "campaign" else "campaign_id", ""))
        if scene: rows = [item for item in rows if item.get("scene_name") == scene]
        if campaign_id: rows = [item for item in rows if str(item.get("campaign_id") or item.get("parent_id") or item.get("dimension_id")) == campaign_id]
        if product_id: rows = [item for item in rows if str(item.get("subject_id") or item.get("dimension_id")) == product_id]
        if query: rows = [item for item in rows if query.casefold() in (str(item.get("dimension_name") or "") + str(item.get("subject_name") or "")).casefold() or query in str(item.get("dimension_id") or "")]
        min_spend = arguments.get("min_spend"); max_roi = arguments.get("max_roi"); efficiency = str(arguments.get("efficiency") or "").strip()
        if min_spend is not None: rows = [item for item in rows if float(item.get("spend") or 0) >= float(min_spend)]
        if max_roi is not None: rows = [item for item in rows if float(item.get("roi") or 0) <= float(max_roi)]
        if efficiency == "roi_below_1": rows = [item for item in rows if item["spend"] > 0 and item["roi"] < 1]
        elif efficiency == "below_target": rows = [item for item in rows if item["spend"] > 0 and item["roi"] < 1.5]
        elif efficiency == "high_spend_low_gmv": rows = [item for item in rows if item["spend"] > 0 and item["roi"] < 1]
        elif efficiency == "clicks_no_gmv": rows = [item for item in rows if item["clicks"] > 0 and item["paid_amount"] == 0]
        elif efficiency == "spend_no_gmv": rows = [item for item in rows if item["spend"] > 0 and item["paid_amount"] == 0]
        order_by = str(arguments.get("order_by") or "-spend"); reverse = order_by.startswith("-"); key = order_by[1:] if reverse else order_by
        allowed = {"spend", "paid_amount", "roi", "clicks", "buyers", "dimension_name"}
        if key not in allowed: raise ValueError(f"Unsupported promotion order_by: {key}")
        numeric_sort_keys = {"spend", "paid_amount", "roi", "clicks", "buyers"}
        if key in numeric_sort_keys:
            # Normalized warehouse rows can contain numeric strings when a
            # platform export was imported without type coercion.  Coerce at
            # the MCP boundary so one malformed row cannot crash a drilldown.
            rows.sort(key=lambda item: (item.get(key) is None, float(item.get(key) or 0)), reverse=reverse)
        else:
            rows.sort(key=lambda item: (item.get(key) is None, str(item.get(key) or "").casefold()), reverse=reverse)
        total = len(rows); page = max(int(arguments.get("page") or 1), 1); page_size = min(max(int(arguments.get("page_size") or 50), 1), 200); start = (page - 1) * page_size
        page_rows = rows[start:start + page_size]
        return self._envelope(tool="promotions.get_drilldown", context=self._context(source._store_id, start_date, end_date), status="ok" if page_rows else "no_data", data={"level": level, "total": total, "page": page, "page_size": page_size, "rows": page_rows}, metrics=[], coverage=CoverageSummary(expected_days=(end_date-start_date).days+1, covered_days=min((item.covered_days for item in workbench.coverage), default=0)), evidence=[EvidenceRecord(dataset=f"推广{level}", table="store_daily_promotion_" + ("campaigns" if level == "campaign" else "items" if level in {"item","product"} else "adgroups" if level == "adgroup" else "bidwords" if level == "keyword" else "crowds" if level == "audience" else "campaigns"), date_range=[start_date.isoformat(), end_date.isoformat()], row_count=total)], warnings=[] if page_rows else ["筛选条件下没有推广数据。"])

    def pricing_get_risk_items(self, arguments: dict[str, Any]) -> MCPEnvelope:
        return self._paged_snapshot(arguments, "pricing.get_risk_items", "store_daily_taobao_risk_price_items", {"product_id": "商品ID", "query": "商品名称"}, ["商品ID", "商品名称", "风险更新时间", "风险类型", "风险描述", "风险子描述", "最低风险价", "原价", "低价SKU数量"], order_column="最低风险价")

    def pricing_get_current_prices(self, arguments: dict[str, Any]) -> MCPEnvelope:
        return self._paged_snapshot(arguments, "pricing.get_current_prices", "store_daily_taobao_current_price_items", {"product_id": "商品ID", "query": "商品标题", "attention": "是否需关注"}, ["商品ID", "商品标题", "是否需关注", "风险标签", "最低价", "最低价下限", "最低价上限", "原价下限", "原价上限", "预测价格下限", "预测价格上限", "SKU数量"], order_column="最低价")

    def activities_get_snapshots(self, arguments: dict[str, Any]) -> MCPEnvelope:
        filters = {"snapshot_type": "快照类型", "product_id": "商品ID", "status": "状态", "query": "商品名称"}
        return self._paged_snapshot(arguments, "activities.get_snapshots", "store_daily_taobao_activity_item_snapshots", filters, ["快照类型", "营销ID", "商品ID", "商品名称", "状态", "状态名称", "活动名称", "活动开始时间", "活动结束时间", "签署时间", "活动价", "原价", "供货价", "库存", "已售数量", "限购数量", "营销玩法已报名数量", "营销玩法未报名数量"], order_column="活动价")

    def _paged_snapshot(self, arguments: dict[str, Any], tool: str, table: str, filters: dict[str, str], columns: list[str], *, order_column: str) -> MCPEnvelope:
        source = self.analytics._source_for_store(arguments.get("store_id")); store_id = source._store_id
        where = ['"店铺ID" = ?']; params: list[Any] = [store_id]
        for key, column in filters.items():
            value = str(arguments.get(key) or "").strip()
            if not value: continue
            if key == "query": where.append(f'"{column}" like ?'); params.append(f"%{value}%")
            else: where.append(f'"{column}" = ?'); params.append(value)
        predicate = " and ".join(where)
        count = source._rows(f'select count(*) as total from {table} where {predicate}', *params)
        limit = min(max(int(arguments.get("limit") or 50), 1), 200); offset = max(int(arguments.get("offset") or 0), 0)
        select = ", ".join(f'"{column}" as "{column}"' for column in columns)
        rows = source._rows(f'''select "业务日期" as business_day, {select} from {table} where {predicate} order by "业务日期" desc, "{order_column}" limit ? offset ?''', *params, limit, offset)
        _, latest = source.get_date_bounds(); total = int(count[0].get("total") or 0) if count else 0
        has_table_rows = source._rows(f'select count(*) as total from {table} where "店铺ID" = ?', store_id)
        table_has_data = bool(has_table_rows and int(has_table_rows[0].get("total") or 0))
        status = "ok" if rows else "no_data"
        warning = [] if rows else ["平台确认无数据。" if table_has_data else "尚未采集该快照数据。"]
        return self._envelope(tool=tool, context=self._context(store_id, latest, latest), status=status, data={"total": total, "limit": limit, "offset": offset, "latest_business_date": latest.isoformat(), "rows": rows}, metrics=[], coverage=CoverageSummary(expected_days=0, covered_days=1 if rows else 0, latest_data_date=latest.isoformat()), evidence=[EvidenceRecord(dataset=table, table=table, date_range=[str(rows[0].get("business_day"))] if rows else [], row_count=len(rows), note="快照数据按店铺与业务日替换")], warnings=warning)

    @staticmethod
    def _latest_snapshot_row(source: Any, table: str, product_id: str) -> dict[str, Any] | None:
        rows = source._rows(f'''select * from {table} where "店铺ID" = ? and "商品ID" = ? order by "业务日期" desc limit 1''', source._store_id, product_id)
        if not rows: return None
        return rows[0]

    @staticmethod
    def _bounded_range(source: Any, arguments: dict[str, Any], *, days: int) -> tuple[date, date]:
        _, latest = source.get_date_bounds()
        end = CommerceMCPService._parse_date(arguments.get("end_date")) or latest
        start = CommerceMCPService._parse_date(arguments.get("start_date")) or max(latest - timedelta(days=days - 1), source.get_date_bounds()[0])
        if start > end or end > latest: raise ValueError(f"Available date range is {source.get_date_bounds()[0].isoformat()} to {latest.isoformat()}")
        return start, end

    @staticmethod
    def _overview_row(source: Any, start_date: date, end_date: date) -> dict[str, Any]:
        rows = source._rows('''select count(*) as row_count,
            sum(cast(coalesce("支付金额", '0') as real)) as paid_amount,
            sum(cast(coalesce("退款金额（支付时间）", '0') as real)) as refund_amount,
            sum(cast(coalesce("净支付金额", '0') as real)) as net_paid_amount,
            sum(cast(coalesce("访客数", '0') as real)) as visitors,
            sum(cast(coalesce("支付买家数", '0') as real)) as buyers,
            avg(cast(nullif("支付转化率", '') as real)) as conversion_rate,
            sum(cast(coalesce("关键词推广花费", '0') as real)) as keyword_spend,
            sum(cast(coalesce("精准人群推广花费", '0') as real)) as crowd_spend,
            sum(cast(coalesce("智能场景花费", '0') as real)) as smart_scene_spend,
            sum(cast(coalesce("全站推广花费", '0') as real)) as promotion_spend,
            sum(cast(coalesce("淘宝客佣金", '0') as real)) as cps_commission
            from store_daily_overviews where "店铺ID" = ? and "业务日期" between ? and ?''', source._store_id, start_date.isoformat(), end_date.isoformat())
        return rows[0] if rows else {}

    def _query_request(self, arguments: dict[str, Any]) -> MCPQueryRequest:
        values = dict(arguments)
        values["start_date"] = self._parse_date(values.get("start_date"))
        values["end_date"] = self._parse_date(values.get("end_date"))
        return MCPQueryRequest.model_validate(values)

    def get_overview(self, store_id: int | None, start_date: date | None, end_date: date | None) -> MCPEnvelope:
        dashboard = self.analytics.get_dashboard(start_date, end_date, store_id)
        context = self._context(store_id, dashboard.range_start, dashboard.range_end)
        coverage = self._coverage(dashboard.coverage, dashboard.range_start, dashboard.range_end, "店铺日概览")
        status = self._status(coverage, bool(dashboard.daily_metrics))
        comparison = dashboard.comparison
        summary = dashboard.summary
        metrics = [
            self._metric("paid_amount", "支付金额", summary.paid_amount, "CNY", "sum(paid_amount)", comparison.paid_amount, "store_daily_overviews"),
            self._metric("net_paid_amount", "净支付金额", summary.net_paid_amount, "CNY", "paid_amount - refund_amount", None, "store_daily_overviews"),
            self._metric("refund_amount", "退款金额", summary.refund_amount, "CNY", "sum(refund_amount)", None, "store_daily_overviews"),
            self._metric("visitors", "访客数", summary.visitors, "person", "sum(visitors)", comparison.visitors, "store_daily_overviews"),
            self._metric("buyers", "支付买家数", summary.buyers, "person", "sum(buyers)", comparison.buyers, "store_daily_overviews"),
            self._metric("conversion_rate", "支付转化率", summary.conversion_rate, "percent", "buyers / visitors * 100", comparison.conversion_rate, "store_daily_overviews"),
            self._metric("customer_unit_price", "客单价", summary.customer_unit_price, "CNY", "paid_amount / buyers", None, "store_daily_overviews"),
            self._metric("promotion_spend", "推广花费", summary.promotion_plan_spend, "CNY", "sum(promotion_spend)", comparison.promotion_cost, "store_daily_promotion_campaigns"),
            self._metric("promotion_roi", "推广 ROI", summary.promotion_roi, "ratio", "attributed_paid_amount / promotion_spend", None, "store_daily_promotion_campaigns"),
        ]
        warnings = self._coverage_warnings(coverage)
        return self._envelope(
            tool="analytics.get_overview",
            context=context,
            status=status,
            data={
                "summary": summary.model_dump(mode="json"),
                "comparison": comparison.model_dump(mode="json"),
                "daily": [item.model_dump(mode="json") for item in dashboard.daily_metrics],
            },
            metrics=metrics,
            coverage=coverage,
            evidence=[EvidenceRecord(dataset="店铺经营总览", table="store_daily_overviews", date_range=[str(dashboard.range_start), str(dashboard.range_end)], row_count=len(dashboard.daily_metrics))],
            warnings=warnings,
        )

    def get_traffic_sources(self, store_id: int | None, start_date: date | None, end_date: date | None) -> MCPEnvelope:
        source, selected_start, selected_end = self._source_and_range(store_id, start_date, end_date)
        rows = source.get_traffic_sources(selected_start, selected_end)
        coverage_items = getattr(source, "get_data_coverage", lambda *_: [])(selected_start, selected_end)
        coverage = self._coverage(coverage_items, selected_start, selected_end, "流量来源")
        data_rows = []
        for item in rows:
            data_rows.append({
                **item.model_dump(mode="json"),
                "conversion_rate": float(item.buyers / item.visitors * 100) if item.visitors else 0,
                "uv_value": float(item.paid_amount / item.visitors) if item.visitors else 0,
                "new_visitor_rate": float(item.new_visitors / item.visitors * 100) if item.visitors else 0,
            })
        # The legacy report grouped paid traffic by level-3 scene. Keep that
        # useful view as an additional, non-overlapping dataset while the
        # primary source table remains the first-level attribution view.
        scene_rows = self._traffic_scene_rows(source, selected_start, selected_end)
        status = self._status(coverage, bool(rows))
        return self._envelope(
            tool="analytics.get_traffic_sources",
            context=self._context(store_id, selected_start, selected_end),
            status=status,
            data={"sources": data_rows, "paid_traffic_scenes": scene_rows},
            metrics=[
                MetricValue(id="traffic_visitors", label="来源访客数", value=sum(item.visitors for item in rows), unit="person", formula="sum(source.visitors)", source="store_daily_traffic_sources"),
                MetricValue(id="traffic_paid_amount", label="来源支付金额", value=float(sum((item.paid_amount for item in rows), Decimal("0"))), unit="CNY", formula="sum(source.paid_amount)", source="store_daily_traffic_sources"),
            ],
            coverage=coverage,
            evidence=[EvidenceRecord(dataset="流量来源", table="store_daily_traffic_sources", date_range=[str(selected_start), str(selected_end)], row_count=len(rows), note="一级来源聚合结果")],
            warnings=self._coverage_warnings(coverage),
        )

    def get_promotions(self, store_id: int | None, start_date: date | None, end_date: date | None) -> MCPEnvelope:
        source, selected_start, selected_end = self._source_and_range(store_id, start_date, end_date)
        getter = getattr(source, "get_promotion_workbench", None)
        if getter is None:
            raise RuntimeError("The selected analytics source does not support promotion analysis")
        workbench = getter(selected_start, selected_end)
        coverage_items = getattr(source, "get_data_coverage", lambda *_: [])(selected_start, selected_end)
        coverage = self._coverage(coverage_items, selected_start, selected_end, "推广计划")
        scenes = [self._promotion_row(item) for item in workbench.scenes]
        campaigns = [self._promotion_row(item) for item in workbench.campaigns]
        status = self._status(coverage, bool(workbench.daily_metrics or campaigns))
        return self._envelope(
            tool="analytics.get_promotions",
            context=self._context(store_id, selected_start, selected_end),
            status=status,
            data={
                "summary": workbench.summary.model_dump(mode="json"),
                "daily": [item.model_dump(mode="json") for item in workbench.daily_metrics],
                "scenes": scenes,
                "campaigns": campaigns,
                "layer_coverage": [item.model_dump(mode="json") for item in workbench.coverage],
            },
            metrics=[
                MetricValue(id="promotion_spend", label="推广花费", value=_number(workbench.summary.spend), unit="CNY", formula="sum(spend)", source="store_daily_promotion_campaigns"),
                MetricValue(id="promotion_paid_amount", label="推广归因成交", value=_number(workbench.summary.paid_amount), unit="CNY", formula="sum(attributed_paid_amount)", source="store_daily_promotion_campaigns"),
                MetricValue(id="promotion_roi", label="推广 ROI", value=_number(workbench.summary.roi), unit="ratio", formula="paid_amount / spend", source="store_daily_promotion_campaigns"),
            ],
            coverage=coverage,
            evidence=[EvidenceRecord(dataset="推广计划", table="store_daily_promotion_campaigns", date_range=[str(selected_start), str(selected_end)], row_count=len(campaigns), note="完整计划层聚合，未按展示条数截断")],
            warnings=self._coverage_warnings(coverage),
        )

    def build_period_report(
        self,
        store_id: int | None,
        start_date: date | None,
        end_date: date | None,
        report_type: str = "daily",
    ) -> MCPEnvelope:
        dashboard = self.analytics.get_dashboard(start_date, end_date, store_id)
        source = self.analytics._source_for_store(store_id)
        snapshot = dashboard.analysis
        if snapshot is None:
            getter = getattr(source, "get_analysis_snapshot", None)
            snapshot = getter(dashboard.range_start, dashboard.range_end) if getter else None
        promotion = self.get_promotions(store_id, dashboard.range_start, dashboard.range_end)

        summary = dashboard.summary
        paid_amount = float(summary.paid_amount)
        share = lambda value: round(float(value) / paid_amount * 100, 2) if paid_amount else None
        coverage_items = getattr(source, "get_data_coverage", lambda *_: dashboard.coverage)(dashboard.range_start, dashboard.range_end)
        coverage = self._coverage(coverage_items, dashboard.range_start, dashboard.range_end, "店铺日概览", include_all=True)
        dataset_coverage = {item.dataset: item for item in coverage_items}

        def has_dataset_rows(dataset: str) -> bool | None:
            tables = dict(getattr(source, "_dataset_tables", lambda: [])())
            table = tables.get(dataset)
            if not table or not hasattr(source, "_rows") or not hasattr(source, "_store_id"):
                return None
            try:
                rows = source._rows(
                    f'''select count(*) as row_count from {table}
                        where "店铺ID" = ? and "业务日期" between ? and ?''',
                    source._store_id, dashboard.range_start.isoformat(), dashboard.range_end.isoformat(),
                )
                return bool(rows and int(rows[0].get("row_count") or 0) > 0)
            except Exception:
                return None

        def available(dataset: str) -> bool:
            item = dataset_coverage.get(dataset)
            if item is None:
                return False
            return item.status in {"complete", "partial"}

        def dataset_status(dataset: str) -> str:
            item = dataset_coverage.get(dataset)
            if item is None:
                return "missing"
            actual_rows = has_dataset_rows(dataset)
            if actual_rows is False and item.no_data_dates and not item.missing_dates and item.covered_days == item.expected_days:
                return "no_data"
            return item.status

        customer = snapshot.customer if snapshot else None
        member = snapshot.member if snapshot else None
        live = snapshot.live if snapshot else None
        cps = snapshot.cps if snapshot else None
        bybt = snapshot.bybt if snapshot else None
        brand = snapshot.brand_zone if snapshot else None
        new_paid_buyers = customer.new_customer_paid_buyers if customer else 0
        new_customer_share = round(new_paid_buyers / summary.buyers * 100, 2) if summary.buyers and available("客户分析") else None

        operations = {
            "gmv": paid_amount,
            "net_gmv": float(summary.net_paid_amount),
            "refund_amount": float(summary.refund_amount),
            "refund_rate": round(float(summary.refund_amount) / paid_amount * 100, 2) if paid_amount else None,
            "visitors": summary.visitors,
            "buyers": summary.buyers,
            "conversion_rate": float(summary.conversion_rate),
            "customer_unit_price": float(summary.customer_unit_price),
            "new_customer_buyer_share": new_customer_share,
            "promotion_spend": float(summary.promotion_plan_spend),
            "promotion_roi": float(summary.promotion_roi),
        }
        operations.update(self._overview_behavior_metrics(source, dashboard.range_start, dashboard.range_end))
        comparison = dashboard.comparison.model_dump(mode="json")

        def comparison_value(metric: str, field: str) -> float | None:
            item = comparison.get(metric)
            if not isinstance(item, dict) or item.get(field) is None:
                return None
            try:
                return float(item[field])
            except (TypeError, ValueError):
                return None

        current_gmv = comparison_value("paid_amount", "current")
        previous_gmv = comparison_value("paid_amount", "previous")
        current_visitors = comparison_value("visitors", "current")
        previous_visitors = comparison_value("visitors", "previous")
        current_buyers = comparison_value("buyers", "current")
        previous_buyers = comparison_value("buyers", "previous")
        current_unit_price = comparison_value("customer_unit_price", "current")
        previous_unit_price = comparison_value("customer_unit_price", "previous")
        gmv_driver_bridge: dict[str, Any] | None = None
        if all(value is not None for value in (
            current_gmv, previous_gmv, current_visitors, previous_visitors,
            current_buyers, previous_buyers, current_unit_price, previous_unit_price,
        )) and previous_visitors and previous_buyers:
            exact_previous_unit_price = previous_gmv / previous_buyers
            previous_buyer_rate = previous_buyers / previous_visitors
            buyers_after_traffic = current_visitors * previous_buyer_rate
            traffic_impact = (buyers_after_traffic - previous_buyers) * exact_previous_unit_price
            conversion_impact = (current_buyers - buyers_after_traffic) * exact_previous_unit_price
            unit_price_impact = current_gmv - current_buyers * exact_previous_unit_price
            drivers = [
                {
                    "key": "traffic",
                    "label": "访客规模",
                    "metric": "visitors",
                    "current": current_visitors,
                    "previous": previous_visitors,
                    "change_percent": comparison_value("visitors", "change_percent"),
                    "impact_amount": round(traffic_impact, 2),
                },
                {
                    "key": "conversion",
                    "label": "支付转化",
                    "metric": "conversion_rate",
                    "current": comparison_value("conversion_rate", "current"),
                    "previous": comparison_value("conversion_rate", "previous"),
                    "change_percent": comparison_value("conversion_rate", "change_percent"),
                    "impact_amount": round(conversion_impact, 2),
                },
                {
                    "key": "customer_unit_price",
                    "label": "客单价",
                    "metric": "customer_unit_price",
                    "current": current_unit_price,
                    "previous": previous_unit_price,
                    "change_percent": comparison_value("customer_unit_price", "change_percent"),
                    "impact_amount": round(unit_price_impact, 2),
                },
            ]
            dominant = max(drivers, key=lambda item: abs(float(item["impact_amount"])))
            gmv_driver_bridge = {
                "formula": "GMV = visitors * payment_conversion_rate * customer_unit_price",
                "method": "sequential_bridge",
                "previous_gmv": previous_gmv,
                "current_gmv": current_gmv,
                "delta_amount": round(current_gmv - previous_gmv, 2),
                "drivers": drivers,
                "dominant_driver": dominant,
                "reconciliation_error": round(
                    current_gmv - previous_gmv - sum(float(item["impact_amount"]) for item in drivers),
                    2,
                ),
                "note": "按上一周期客单价顺序桥接访客、转化和客单价影响；影响金额用于解释变化，不代表因果增量。",
            }
        # When the customer-analysis endpoint has an empty value, the daily
        # overview still gives us an auditable new/returning buyer split.
        # Prefer the endpoint value, otherwise derive it from paid buyers and
        # older paid buyers; never manufacture a zero for an absent field.
        derived_new_buyers = None
        if operations.get("older_paid_buyers") is not None:
            derived_new_buyers = max(int(summary.buyers) - int(operations["older_paid_buyers"] or 0), 0)
            operations["new_paid_buyers"] = derived_new_buyers
            if summary.buyers and not new_paid_buyers:
                operations["new_customer_buyer_share"] = round(derived_new_buyers / summary.buyers * 100, 2)
        customer = {
            "status": "available" if customer and available("客户分析") else dataset_status("客户分析"),
            "new_paid_buyers": (customer.new_customer_paid_buyers or derived_new_buyers) if customer and available("客户分析") else derived_new_buyers,
            "new_paid_amount": float(customer.new_customer_paid_amount) if customer and available("客户分析") and customer.new_customer_paid_amount else None,
            "new_buyer_share": operations.get("new_customer_buyer_share"),
            "repeat_buyers": customer.repeat_customers if customer and available("客户分析") else None,
            "repeat_paid_amount": float(customer.repeat_customer_paid_amount) if customer and available("客户分析") else None,
            "repeat_rate": float(customer.repeat_rate) if customer and available("客户分析") else None,
        }
        channels = {
            "member": self._report_channel(member.paid_amount, share(member.paid_amount), {"new_members": member.new_members, "new_paid_members": member.new_paid_members}) if member and available("会员分析") else self._missing_channel(dataset_status("会员分析")),
            "shop_live": self._report_channel(live.shop_paid_amount, share(live.shop_paid_amount)) if live and available("直播概览") else self._missing_channel(dataset_status("直播概览")),
            "bybt": self._report_channel(bybt.paid_amount, share(bybt.paid_amount)) if bybt and available("百亿补贴") else self._missing_channel(dataset_status("百亿补贴")),
            "cps_payment": self._report_channel(cps.paid_amount, share(cps.paid_amount), {"expense": float(cps.payment_expense), "commission_expense": float(cps.payment_commission_expense), "service_expense": float(cps.payment_service_expense), "click_visitors": cps.click_visitors}) if cps and available("CPS") else self._missing_channel(dataset_status("CPS")),
            "cps_settlement": self._report_channel(cps.settlement_amount, share(cps.settlement_amount), {"expense": float(cps.settlement_expense), "commission_expense": float(cps.settlement_commission_expense), "service_expense": float(cps.settlement_service_expense)}) if cps and available("CPS") else self._missing_channel(dataset_status("CPS")),
        }
        channel_scope = {
            "scope_type": "overlapping_attribution_labels",
            "denominator": "store_paid_gmv",
            "can_sum": False,
            "note": "会员是客户身份，自播间和 CPS 是归因/结算标签，同一订单可能重复出现；各行占比均以店铺支付 GMV 为分母，但不能相加到 100%。",
            "rules": [
                "会员成交不能与直播或 CPS 成交相加后作为渠道总成交。",
                "CPS 支付与 CPS 出库是同一业务的不同阶段，不能相加。",
                "推广归因成交与店铺支付 GMV 不是同一结算口径。",
            ],
        }
        promotion_summary = promotion.data.get("summary", {})
        brand_spend = self._brand_zone_spend(source, dashboard.range_start, dashboard.range_end)
        rtb_spend = float(promotion_summary.get("spend") or 0)
        rtb_paid = float(promotion_summary.get("paid_amount") or 0)
        brand_paid = float(brand.paid_amount) if brand and available("品销宝") else None
        brand_clicks = int(brand.click_visitors) if brand and available("品销宝") else None
        paid_clicks = sum(int(item.get("clicks") or 0) for item in promotion.data.get("scenes", [])) + (brand_clicks or 0)
        total_spend = rtb_spend + (brand_spend or 0)
        attributed_paid = rtb_paid + (brand_paid or 0)
        promotions = {
            "attribution_window_days": 15,
            "paid_clicks": paid_clicks,
            "paid_click_share_of_store_uv": round(paid_clicks / summary.visitors * 100, 2) if summary.visitors else None,
            "paid_visitors": paid_clicks,
            "paid_traffic_share": round(paid_clicks / summary.visitors * 100, 2) if summary.visitors else None,
            "spend": total_spend,
            "attributed_paid_amount": attributed_paid if promotion.status != "no_data" or brand_paid is not None else None,
            "roi": round(attributed_paid / total_spend, 2) if total_spend else None,
            "scenes": promotion.data.get("scenes", []),
            "brand_zone": {
                "status": "available" if available("品销宝") else dataset_status("品销宝"),
                "spend": brand_spend,
                "paid_amount": brand_paid,
                "roi": round(brand_paid / brand_spend, 2) if brand_paid is not None and brand_spend else None,
            },
        }
        talents = []
        if live and available("直播概览"):
            talents = [{"name": item.talent_name, "gmv": float(item.paid_amount), "sessions": item.sessions, "buyers": item.buyers} for item in live.talents[:3]]

        missing_sections = []
        section_datasets = {
            "新客支付人数占比": "客户分析", "会员成交": "会员分析", "自播间成交": "直播概览",
            "百亿补贴成交": "百亿补贴", "CPS": "CPS", "品销宝": "品销宝",
        }
        no_data_sections = []
        for section, dataset in section_datasets.items():
            state = dataset_status(dataset)
            if state == "missing":
                missing_sections.append(section)
            elif state == "no_data":
                no_data_sections.append(section)

        core_status = dataset_status("店铺日概览")
        if core_status == "missing":
            core_status = dataset_status("店铺总览")
        core_complete = core_status == "complete" and not coverage.missing_dates
        available_channels = sum(1 for item in channels.values() if item.get("status") == "available")
        decision_quality = {
            "overall": {
                "confidence": "high" if core_complete else "low",
                "status": "complete" if core_complete else core_status,
                "reason": "经营总盘与上一周期数据完整，可审计拆解 GMV 变化。" if core_complete else "经营总盘覆盖不完整，环比和驱动拆解仅供参考。",
            },
            "modules": [
                {
                    "key": "operations",
                    "label": "经营总盘",
                    "confidence": "high" if core_complete else "low",
                    "status": "complete" if core_complete else core_status,
                    "reason": "支付、访客、买家、转化和客单价来自店铺日概览。",
                },
                {
                    "key": "channels",
                    "label": "渠道标签",
                    "confidence": "medium" if available_channels else "low",
                    "status": "available" if available_channels else "missing",
                    "reason": "可用于看归因贡献，但标签相互重叠，不能加总或解释为增量。" if available_channels else "当前没有可用渠道标签。",
                },
                {
                    "key": "promotions",
                    "label": "推广归因",
                    "confidence": "medium" if promotions.get("roi") is not None else "low",
                    "status": promotion.status,
                    "reason": "15 天平台归因可用于比较投放效率，不等同利润或因果增量。" if promotions.get("roi") is not None else "推广归因数据不可用。",
                },
                {
                    "key": "customers",
                    "label": "客户结构",
                    "confidence": "medium" if customer.get("status") == "available" else "low",
                    "status": customer.get("status"),
                    "reason": "新老客字段可辅助解释结构，但复购数据缺失时不外推留存。" if customer.get("status") == "available" else "客户分析模块未完整采集。",
                },
                {
                    "key": "talents",
                    "label": "直播达人",
                    "confidence": "medium" if talents else "low",
                    "status": "available" if talents else dataset_status("直播概览"),
                    "reason": "当前可比较成交、场次和买家；缺少完整佣金与退款成本时不能判断盈利。" if talents else "直播达人数据不可用。",
                },
            ],
        }

        data = {
            "report_type": report_type,
            "range_start": dashboard.range_start.isoformat(),
            "range_end": dashboard.range_end.isoformat(),
            "operations": operations,
            "comparison": comparison,
            "gmv_driver_bridge": gmv_driver_bridge,
            "previous_period": {
                "range_start": dashboard.period.previous_start.isoformat(),
                "range_end": dashboard.period.previous_end.isoformat(),
            },
            "channels": channels,
            "channel_scope": channel_scope,
            "promotions": promotions,
            "top_talents": talents,
            "customer": customer,
            "missing_sections": missing_sections,
            "no_data_sections": no_data_sections,
            "coverage_by_dataset": [item.model_dump(mode="json") for item in coverage_items],
            "data_quality": {
                "status": "complete" if not coverage.missing_dates and not coverage.missing_datasets and not coverage.partial_datasets else "partial",
                "missing_sections": missing_sections,
                "no_data_sections": no_data_sections,
                "missing_dates": [item.isoformat() for item in coverage.missing_dates],
                "missing_datasets": list(coverage.missing_datasets),
                "partial_datasets": list(coverage.partial_datasets),
                "failed_datasets": list(coverage.failed_datasets),
                "no_data_datasets": list(coverage.no_data_datasets),
                "no_data_dates": list(coverage.no_data_dates),
                "latest_data_date": coverage.latest_data_date,
            },
            "decision_quality": decision_quality,
        }
        if report_type == "daily_series":
            daily_series = []
            for item in dashboard.daily_metrics:
                row = item.model_dump(mode="json")
                # Warehouse daily overview stores payment conversion as a
                # fraction in some historical imports and as a percentage in
                # newer ones. Normalize the displayed series to percent.
                conversion = row.get("conversion_rate")
                if conversion is not None and 0 < float(conversion) <= 1:
                    row["conversion_rate"] = round(float(conversion) * 100, 2)
                daily_series.append(row)
            data["daily_series"] = daily_series
        # The report can still calculate its core GMV metrics when a companion
        # dataset is empty, but the overall result must expose that limitation.
        # Keep platform no-data separate from collections that have not landed.
        warnings = self._coverage_warnings(coverage)
        if missing_sections:
            warnings.append("以下报告模块未采集完整：" + "、".join(missing_sections))
        if no_data_sections:
            warnings.append("平台确认无数据的报告模块：" + "、".join(no_data_sections))
        return self._envelope(
            tool="reports.build_period_report",
            context=self._context(store_id, dashboard.range_start, dashboard.range_end),
            status="partial" if warnings else "ok",
            data=data,
            metrics=[
                MetricValue(id="gmv", label="GMV", value=paid_amount, unit="CNY", formula="sum(paid_amount)", source="store_daily_overviews"),
                MetricValue(id="net_gmv", label="去退 GMV", value=float(summary.net_paid_amount), unit="CNY", formula="paid_amount - refund_amount", source="store_daily_overviews"),
                MetricValue(id="visitors", label="UV", value=summary.visitors, unit="person", formula="sum(visitors)", source="store_daily_overviews"),
                MetricValue(id="conversion_rate", label="支付转化率", value=float(summary.conversion_rate), unit="percent", formula="buyers / visitors * 100", source="store_daily_overviews"),
                MetricValue(id="buyers", label="支付买家数", value=summary.buyers, unit="person", formula="sum(buyers)", source="store_daily_overviews"),
                MetricValue(id="refund_rate", label="退款金额占比", value=operations["refund_rate"], unit="percent", formula="refund_amount / paid_amount * 100", source="store_daily_overviews"),
            ],
            coverage=coverage,
            evidence=[
                EvidenceRecord(dataset="店铺经营总览", table="store_daily_overviews", date_range=[str(dashboard.range_start), str(dashboard.range_end)], row_count=len(dashboard.daily_metrics)),
                *promotion.evidence,
            ],
            warnings=warnings,
        )

    @staticmethod
    def _report_channel(value: Any, sales_share: float | None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"status": "available", "paid_amount": float(value), "sales_share": sales_share, **(extra or {})}

    @staticmethod
    def _missing_channel(status: str | None) -> dict[str, Any]:
        return {"status": status or "missing", "paid_amount": None, "sales_share": None}

    @staticmethod
    def _brand_zone_spend(source: Any, start_date: date, end_date: date) -> float | None:
        rows = source._rows("pragma table_info('store_daily_brand_zone_overviews')")
        columns = {str(row.get("name")) for row in rows}
        spend_column = next((name for name in ("品销宝花费", "花费", "消耗") if name in columns), None)
        if not spend_column:
            return None
        values = source._rows(
            f'''select sum(cast(coalesce("{spend_column}", '0') as real)) as spend
                from store_daily_brand_zone_overviews
                where "店铺ID" = ? and "业务日期" between ? and ?''',
            source._store_id, start_date.isoformat(), end_date.isoformat(),
        )
        return float(values[0].get("spend") or 0) if values else 0

    @staticmethod
    def _overview_behavior_metrics(source: Any, start_date: date, end_date: date) -> dict[str, Any]:
        """Expose the high-value dailyshopdata fields when the local warehouse has them."""
        if not hasattr(source, "_rows") or not hasattr(source, "_store_id"):
            return {}
        table = "store_daily_overviews"
        try:
            columns = {str(row.get("name")) for row in source._rows(f"pragma table_info('{table}')")}
            candidates = {
                "add_cart_buyers": "加购人数",
                "add_cart_items": "加购件数",
                "favorite_buyers": "商品收藏人数",
                "page_views": "浏览量",
                "paid_items": "支付件数",
                "older_paid_amount": "老客复购金额",
                "older_paid_buyers": "老客复购人数",
                "older_repurchase_rate": "老客复购率",
                "refund_paid_time_amount": "退款金额（支付时间）",
                "refund_finished_amount": "退款金额（完结时间）",
            }
            selected = {key: column for key, column in candidates.items() if column in columns}
            if not selected:
                return {}
            expressions = ", ".join(
                f'sum(cast(coalesce("{column}", \'0\') as real)) as "{key}"'
                for key, column in selected.items()
                if key != "older_repurchase_rate"
            )
            if "older_repurchase_rate" in selected:
                expressions += (", " if expressions else "") + 'avg(cast(coalesce("老客复购率", \'0\') as real)) as "older_repurchase_rate"'
            rows = source._rows(
                f'''select count(*) as __row_count, {expressions} from {table}
                    where "店铺ID" = ? and "业务日期" between ? and ?''',
                source._store_id, start_date.isoformat(), end_date.isoformat(),
            )
            row = rows[0] if rows else {}
            if not int(row.get("__row_count") or 0):
                return {}
            result: dict[str, Any] = {}
            for key in selected:
                value = _number(row.get(key))
                if key == "older_repurchase_rate" and value is not None and abs(float(value)) <= 1:
                    value = float(value) * 100
                result[key] = value
            return result
        except Exception:
            # A legacy adapter may expose the same concepts under a different
            # table/SQL dialect. It is better to omit these optional metrics
            # than to make the complete report fail.
            return {}

    @staticmethod
    def _traffic_scene_rows(source: Any, start_date: date, end_date: date) -> list[dict[str, Any]]:
        getter = getattr(source, "get_traffic_tree", None)
        if getter is None:
            return []
        try:
            nodes = getter(start_date, end_date)
        except Exception:
            return []
        mapping = {
            "智能场景": "万象台", "人群推广": "万象台", "全站推广": "万象台",
            "货品运营": "万象台", "短直联动": "万象台", "关键词推广": "直通车",
            "品销宝- 品牌专区": "品销宝", "品销宝-品牌专区": "品销宝",
        }
        result: list[dict[str, Any]] = []
        def walk(items: list[Any]):
            for item in items:
                yield item
                yield from walk(list(getattr(item, "children", []) or []))

        for node in walk(nodes):
            level = int(getattr(node, "level", 0) or 0)
            path = list(getattr(node, "path", []) or [])
            raw_name = str(getattr(node, "name", "未分类") or "未分类")
            if level < 2 or not path:
                continue
            parent = path[1] if len(path) > 1 else path[0]
            normalized = mapping.get(raw_name, mapping.get(parent, raw_name))
            result.append({
                "scene_name": normalized,
                "raw_scene_name": raw_name,
                "source_path": path,
                "source_level": level,
                "visitors": int(getattr(node, "visitors", 0) or 0),
                "buyers": int(getattr(node, "buyers", 0) or 0),
                "paid_amount": _number(getattr(node, "paid_amount", 0)),
                "conversion_rate": _number(getattr(node, "conversion_rate", 0)),
                "uv_value": _number(getattr(node, "uv_value", 0)),
            })
        return result

    def _source_and_range(
        self,
        store_id: int | None,
        start_date: date | None,
        end_date: date | None,
        history_scope: str = "selected",
    ):
        source = self.analytics._source_for_store(store_id)
        minimum, maximum = source.get_date_bounds()
        if history_scope == "all" and start_date is None and end_date is None:
            selected_start, selected_end = minimum, maximum
        else:
            default_start, default_end = source.default_range(maximum)
            selected_start = start_date or default_start
            selected_end = end_date or default_end
        if selected_start < minimum or selected_end > maximum or selected_start > selected_end:
            raise ValueError(f"Available date range is {minimum.isoformat()} to {maximum.isoformat()}")
        return source, selected_start, selected_end

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        if value is None or isinstance(value, date):
            return value
        return date.fromisoformat(str(value))

    @staticmethod
    def _context(store_id: int | None, start_date: date, end_date: date) -> AnalysisContext:
        return AnalysisContext(store_id=store_id, range_start=start_date, range_end=end_date)

    @staticmethod
    def _coverage(items: list, start_date: date, end_date: date, primary_label: str, include_all: bool = False) -> CoverageSummary:
        expected = (end_date - start_date).days + 1
        primary = next((item for item in items if item.dataset == primary_label), None)
        relevant = list(items) if include_all else [item for item in items if item.dataset == primary_label]
        missing_dates = [value.isoformat() for value in (primary.missing_dates if primary else [])]
        return CoverageSummary(
            expected_days=expected,
            covered_days=primary.covered_days if primary else 0,
            missing_dates=missing_dates,
            missing_datasets=[item.dataset for item in relevant if item.status == "empty"],
            partial_datasets=[item.dataset for item in relevant if item.status == "partial"],
            latest_data_date=primary.latest_date.isoformat() if primary and primary.latest_date else None,
            no_data_dates=[item.isoformat() for item in (primary.no_data_dates if primary else [])],
            no_data_datasets=[item.dataset for item in relevant if item.no_data_dates and not item.missing_dates and item.covered_days == item.expected_days],
        )

    @staticmethod
    def _status(coverage: CoverageSummary, has_data: bool) -> str:
        if not has_data:
            return "no_data"
        if coverage.missing_dates or coverage.missing_datasets or coverage.partial_datasets or coverage.failed_datasets:
            return "partial"
        return "ok"

    @staticmethod
    def _coverage_warnings(coverage: CoverageSummary) -> list[str]:
        warnings = []
        if coverage.missing_dates:
            warnings.append("所选区间存在未采集日期：" + "、".join(coverage.missing_dates))
        if coverage.missing_datasets:
            warnings.append("缺少数据集：" + "、".join(coverage.missing_datasets))
        if coverage.partial_datasets:
            warnings.append("数据集覆盖不完整：" + "、".join(coverage.partial_datasets))
        if coverage.no_data_datasets:
            warnings.append("平台确认无数据：" + "、".join(coverage.no_data_datasets))
        return warnings

    @staticmethod
    def _metric(metric_id: str, label: str, value: Any, unit: str, formula: str, comparison: Any, source: str) -> MetricValue:
        compare = comparison.model_dump(mode="json") if comparison is not None else {}
        return MetricValue(id=metric_id, label=label, value=_number(value), unit=unit, formula=formula, comparison=compare, source=source)

    @staticmethod
    def _promotion_row(item: Any) -> dict[str, Any]:
        data = item.model_dump(mode="json")
        # Promotion imports may preserve CSV numeric fields as strings.  Keep
        # the MCP contract numeric so aggregate checks, filters and sorting do
        # not fail on a single untyped row.
        spend = float(item.spend or 0)
        paid_amount = float(item.paid_amount or 0)
        buyers = float(item.buyers or 0)
        clicks = float(item.clicks or 0)
        data["spend"] = spend
        data["paid_amount"] = paid_amount
        data["buyers"] = buyers
        data["clicks"] = clicks
        data["roi"] = paid_amount / spend if spend else 0
        data["conversion_rate"] = buyers / clicks * 100 if clicks else 0
        return data

    @staticmethod
    def _envelope(**kwargs: Any) -> MCPEnvelope:
        return MCPEnvelope(
            request_id=str(uuid4()),
            generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            next_actions=[],
            **kwargs,
        )
