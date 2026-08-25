from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CollectionDataset:
    key: str
    label: str
    group: str
    tables: tuple[str, ...]
    task_types: tuple[str, ...]
    description: str
    allow_no_data: bool = False
    scope: str = "store"
    collection_mode: str = "daily_fact"


COLLECTION_DATASETS: tuple[CollectionDataset, ...] = (
    CollectionDataset(
        "sycm_overviews", "店铺经营总览", "经营", ("store_daily_overviews",),
        ("sycm_overview",), "交易、流量、退款和履约核心指标。",
    ),
    CollectionDataset(
        "sycm_bybt", "百亿补贴", "营销", ("store_daily_bybt_overviews",),
        ("sycm_bybt",), "百补流量、成交和在售商品指标。",
    ),
    CollectionDataset(
        "sycm_bybt_items", "百亿补贴商品明细（按日）", "营销", ("store_daily_bybt_items",),
        ("sycm_bybt_items",), "百亿补贴单品成交明细，按业务日期每天批量采集并逐日留存历史。", allow_no_data=True,
    ),
    CollectionDataset(
        "sycm_customer_overviews", "客户概览", "客户", ("store_daily_customer_overviews",),
        ("sycm_customer_overview",), "新客、老客和复购客户分层指标。",
    ),
    CollectionDataset(
        "sycm_item_rankings", "商品排行", "商品", ("store_daily_product_rankings",),
        ("sycm_item_rankings",), "按商品维度的支付、退款与流量排行。",
    ),
    CollectionDataset(
        "sycm_live", "直播经营", "内容", (
            "store_daily_live_overviews",
            "store_daily_live_store_performance",
            "store_daily_live_talent_reports",
        ), ("sycm_live",), "直播总览、店铺表现和达人明细必须同时到达。",
    ),
    CollectionDataset(
        "sycm_member_analysis", "会员分析", "客户", (
            "store_daily_member_analysis_overviews", "store_daily_member_channels",
        ), ("sycm_member_analysis",), "会员资产、复购与入会渠道。",
    ),
    CollectionDataset(
        "sycm_new_customer_discount", "新客礼金", "营销",
        ("store_daily_new_customer_discount_overviews",),
        ("sycm_new_customer_discount",), "新客礼金触达与成交表现。",
    ),
    CollectionDataset(
        "sycm_shopping_gold", "购物金", "营销", ("store_daily_shopping_gold_overviews",),
        ("sycm_shopping_gold",), "购物金充值和核销指标。",
    ),
    CollectionDataset(
        "sycm_traffic_sources", "流量来源", "流量", ("store_daily_traffic_sources",),
        ("sycm_traffic_source",), "多层级来源流量与成交贡献。",
    ),
    CollectionDataset(
        "mtop_content_overviews", "内容效果", "内容", ("store_daily_content_overviews",),
        ("mtop_content_overview",), "内容曝光、互动和种草成交；平台可能明确返回无数据。",
        allow_no_data=True,
    ),
    CollectionDataset(
        "mtop_taojinbi", "淘金币", "营销", ("store_daily_taojinbi_overviews",),
        ("mtop_taojinbi",), "淘金币频道、补贴和访问指标。",
    ),
    CollectionDataset(
        "customer_service", "客服数据", "服务", (
            "store_daily_customer_service_overviews",
            "store_daily_customer_service_accounts",
        ), ("customer_service",), "客服经营总览与客服账号明细必须同时到达。",
    ),
    CollectionDataset(
        "cps_overviews", "淘宝客 CPS", "推广", ("store_daily_cps_overviews",),
        ("cps_overview",), "淘宝客付款、结算和佣金数据。",
    ),
    CollectionDataset(
        "brandsearch_reports", "品销宝品牌专区", "推广",
        ("store_daily_brand_zone_overviews",), ("brandsearch_report",),
        "品牌专区曝光、点击与成交。",
    ),
    CollectionDataset(
        "taobao_flash_sales", "淘宝秒杀", "营销",
        ("store_daily_taobao_flash_sale_overviews",), ("taobao_flash_sale",),
        "秒杀活动商品与成交表现。平台明确返回空列表时标记为无数据。", allow_no_data=True,
    ),
    CollectionDataset(
        "taobao_flash_sale_items", "淘宝秒杀商品明细（按日）", "营销",
        ("store_daily_taobao_flash_sale_items",), ("taobao_flash_sale_items",),
        "淘宝秒杀单品成交明细，按业务日期每天批量采集并逐日留存历史。", allow_no_data=True,
    ),
    CollectionDataset(
        "taobao_operational_snapshots", "淘宝运营商品快照", "商品",
        (
            "store_daily_taobao_current_price_items",
            "store_daily_taobao_risk_price_items",
            "store_daily_taobao_activity_item_snapshots",
        ), ("taobao_operational_snapshots",),
        "百补在线商品、秒杀在线商品、商品当前价与商品红线价的每日全量覆盖快照。", allow_no_data=True,
        collection_mode="coverage_snapshot",
    ),
    CollectionDataset(
        "sycm_activity_calendar", "活动日历", "营销",
        ("store_activity_calendar_events",), ("sycm_activity_calendar",),
        "SYCM 当前活动日历的每日全量覆盖快照；成功空响应表示当前没有活动。",
        allow_no_data=True, collection_mode="coverage_snapshot",
    ),
    CollectionDataset(
        "utry_overviews", "U先商品数据", "营销",
        ("store_daily_utry_sample_overviews", "store_daily_utry_repurchase_overviews"),
        ("utry_overviews",),
        "U先派样和复购商品明细必须同时到达；平台可能明确返回无数据。",
        allow_no_data=True,
    ),
    CollectionDataset(
        "databank_daily", "品牌数据银行", "品牌",
        (
            "brand_asset_daily_overviews",
            "brand_asset_daily_stages",
            "brand_asset_daily_dimensions",
            "brand_asset_daily_metrics",
        ), ("databank_daily",),
        "品牌主体的消费者资产、阶段、维度和指标日报。",
        allow_no_data=True, scope="brand",
    ),
    CollectionDataset(
        "sycm_market", "SYCM 市场排行与搜索词", "市场",
        ("sycm_market_rankings", "sycm_market_keywords"), ("sycm_market",),
        "类目市场排行和搜索词，不属于店铺经营事实。",
        allow_no_data=True, scope="market",
    ),
    CollectionDataset(
        "alimama_campaigns", "推广计划", "推广", ("store_daily_promotion_campaigns",),
        ("alimama_campaigns",), "阿里妈妈计划层级日报。",
    ),
    CollectionDataset(
        "alimama_crowds", "推广人群", "推广", ("store_daily_promotion_crowds",),
        ("alimama_crowds",), "阿里妈妈人群层级日报。",
    ),
    CollectionDataset(
        "alimama_promotion_details", "推广商品与内容", "推广", (
            "store_daily_promotion_items", "store_daily_promotion_contents",
        ), ("alimama_item_promotion", "alimama_content_promotion"),
        "推广商品和内容明细必须同时到达。",
    ),
    CollectionDataset(
        "alimama_adgroup_bidwords", "推广单元与关键词", "推广", (
            "store_daily_promotion_adgroups", "store_daily_promotion_bidwords",
        ), ("alimama_adgroups", "alimama_bidwords"),
        "推广单元和关键词明细必须同时到达。",
    ),
)

COLLECTION_DATASET_BY_KEY = {dataset.key: dataset for dataset in COLLECTION_DATASETS}
COLLECTION_DATASET_KEYS = tuple(dataset.key for dataset in COLLECTION_DATASETS)
COVERAGE_SNAPSHOT_DATASET_NAMES = frozenset(
    dataset.key for dataset in COLLECTION_DATASETS if dataset.collection_mode == "coverage_snapshot"
)
