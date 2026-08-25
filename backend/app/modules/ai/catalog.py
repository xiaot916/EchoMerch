"""Canonical, read-only analytics catalog used by the generic data MCP.

The catalog is deliberately independent from UI labels and report templates.
Skills select these stable ids; the executor is the only component that knows
the physical SQLite columns.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldDefinition:
    id: str
    label: str
    column: str
    kind: str
    unit: str = ""
    aggregation: str = "sum"
    description: str = ""
    formula: str = ""


@dataclass(frozen=True)
class DatasetDefinition:
    key: str
    label: str
    table: str
    grain: str
    date_column: str = "业务日期"
    store_column: str = "店铺ID"
    dimensions: dict[str, FieldDefinition] = field(default_factory=dict)
    measures: dict[str, FieldDefinition] = field(default_factory=dict)
    default_filters: dict[str, object] = field(default_factory=dict)
    calculated_measures: dict[str, FieldDefinition] = field(default_factory=dict)

    @property
    def fields(self) -> dict[str, FieldDefinition]:
        return {**self.dimensions, **self.measures, **self.calculated_measures}


def _dims(*items: tuple[str, str, str]) -> dict[str, FieldDefinition]:
    return {key: FieldDefinition(key, label, column, "dimension") for key, label, column in items}


def _measures(*items: tuple[str, str, str, str, str]) -> dict[str, FieldDefinition]:
    return {
        key: FieldDefinition(key, label, column, "measure", unit, aggregation)
        for key, label, column, unit, aggregation in items
    }


def _calculated(*items: tuple[str, str, str, str, str]) -> dict[str, FieldDefinition]:
    return {
        key: FieldDefinition(key, label, "", "measure", unit, "calculated", description=formula, formula=formula)
        for key, label, formula, unit, _aggregation in items
    }


_overview_measures = _measures(
    ("gmv", "支付金额", "支付金额", "CNY", "sum"),
    ("refund_amount", "退款金额", "退款金额（支付时间）", "CNY", "sum"),
    ("visitors", "访客数", "访客数", "person", "sum"),
    ("buyers", "支付买家数", "支付买家数", "person", "sum"),
    ("add_cart_users", "加购人数", "加购人数", "person", "sum"),
    ("favorite_users", "收藏人数", "商品收藏人数", "person", "sum"),
    ("page_views", "浏览量", "浏览量", "count", "sum"),
    ("payment_items", "支付件数", "支付件数", "item", "sum"),
    ("promotion_spend", "全站推广花费", "全站推广花费", "CNY", "sum"),
    ("keyword_spend", "关键词推广花费", "关键词推广花费", "CNY", "sum"),
    ("crowd_spend", "精准人群推广花费", "精准人群推广花费", "CNY", "sum"),
    ("smart_scene_spend", "智能场景花费", "智能场景花费", "CNY", "sum"),
    ("cps_commission", "淘宝客佣金", "淘宝客佣金", "CNY", "sum"),
    ("net_gmv", "净支付金额", "净支付金额", "CNY", "sum"),
    ("payment_conversion_rate", "支付转化率", "支付转化率", "percent", "avg"),
    ("customer_unit_price", "客单价", "客单价", "CNY", "avg"),
)


DATASET_CATALOG: dict[str, DatasetDefinition] = {
    "store_overview": DatasetDefinition(
        "store_overview", "店铺日概览", "store_daily_overviews", "店铺-日",
        dimensions=_dims(("date", "业务日期", "业务日期")), measures=_overview_measures,
    ),
    "traffic_sources": DatasetDefinition(
        "traffic_sources", "流量来源", "store_daily_traffic_sources", "来源层级-日",
        dimensions=_dims(("date", "业务日期", "业务日期"), ("source", "一级来源", "一级来源"), ("source_level", "来源层级", "来源层级")),
        measures=_measures(
            ("visitors", "访客数", "访客数", "person", "sum"), ("new_visitors", "新访客数", "新访客数", "person", "sum"),
            ("buyers", "支付买家数", "支付买家数", "person", "sum"), ("gmv", "支付金额", "支付金额", "CNY", "sum"),
            ("add_cart_users", "加购人数", "加购人数", "person", "sum"), ("favorite_users", "收藏人数", "商品收藏人数", "person", "sum"),
        ), default_filters={"source_level": 1},
    ),
    "products": DatasetDefinition(
        "products", "商品排行", "store_daily_product_rankings", "商品-日",
        dimensions=_dims(("date", "业务日期", "业务日期"), ("product_id", "商品ID", "商品ID"), ("product_name", "商品名称", "商品名称")),
        measures=_measures(
            ("gmv", "支付金额", "支付金额", "CNY", "sum"), ("refund_amount", "退款金额", "退款金额（完结时间）", "CNY", "sum"),
            ("buyers", "支付买家数", "支付买家数", "person", "sum"), ("visitors", "商品访客数", "商品访客数", "person", "sum"),
            ("add_cart_users", "加购人数", "商品加购人数", "person", "sum"), ("favorite_users", "收藏人数", "商品收藏人数", "person", "sum"),
            ("page_views", "浏览量", "商品浏览量", "count", "sum"), ("promotion_spend", "推广消耗", "推广消耗", "CNY", "sum"),
        ),
    ),
    "customers": DatasetDefinition(
        "customers", "客户分析", "store_daily_customer_overviews", "客户类型-日",
        dimensions=_dims(("date", "业务日期", "业务日期")),
        measures=_measures(
            ("new_visitors", "客户新访", "客户新访", "person", "sum"), ("new_paid_buyers", "新访成交", "新访成交", "person", "sum"),
            ("no_purchase_returners", "未购客户回访", "未购客户回访", "person", "sum"), ("no_purchase_buyers", "回访成交", "回访成交", "person", "sum"),
            ("repeat_returners", "已购客户回访", "已购客户回访", "person", "sum"), ("repeat_buyers", "老客复购", "老客复购", "person", "sum"),
        ),
    ),
    "utry_sample": DatasetDefinition(
        "utry_sample", "U先派样", "store_daily_utry_sample_overviews", "U先商品-日",
        dimensions=_dims(
            ("date", "业务日期", "业务日期"), ("product_id", "商品ID", "商品ID"),
            ("product_name", "商品标题", "商品标题"), ("leaf_category", "叶子类目名称", "叶子类目名称"),
            ("industry_group", "行业大组名称", "行业大组名称"), ("first_category", "一级大类名称", "一级大类名称"),
            ("second_category", "二级大类名称", "二级大类名称"),
        ),
        measures=_measures(
            ("sample_orders", "派样单量", "派样单量", "order", "sum"),
            ("sample_people", "派样人次", "派样人次", "person", "sum"),
            ("sample_gmv", "派样GMV", "派样GMV", "CNY", "sum"),
            ("merchant_new_customers_365d", "派样365天商家新客数", "派样365天商家新客数", "person", "sum"),
            ("merchant_new_customers_180d", "派样180天商家新客数", "派样180天商家新客数", "person", "sum"),
            ("new_members", "新会员数", "新会员数", "person", "sum"),
            ("new_followers", "新粉丝数", "新粉丝数", "person", "sum"),
        ),
    ),
    "utry_repurchase": DatasetDefinition(
        "utry_repurchase", "U先复购", "store_daily_utry_repurchase_overviews", "U先商品回购快照-日",
        dimensions=_dims(
            ("date", "业务日期", "业务日期"), ("product_id", "商品ID", "商品ID"),
            ("product_name", "商品名称", "商品名称"), ("ju_id", "聚划算ID", "ju_id"),
            ("leaf_category", "叶子类目", "叶子类目"), ("industry_group", "行业大组", "行业大组"),
            ("first_category", "一级大类", "一级大类"), ("second_category", "二级大类", "二级大类"),
            ("bind_regular_product", "是否绑定正装", "是否绑定正装"),
            ("configured_repurchase_coupon", "是否配置回购券", "是否配置回购券"),
            ("configured_repurchase_gift", "是否配置回购礼金", "是否配置回购礼金"),
        ),
        measures=_measures(
            ("store_30d_repurchase_uv", "同店30日回购UV", "同店30日回购UV", "person", "sum"),
            ("store_30d_repurchase_amount", "同店30日回购金额", "同店30日回购金额", "CNY", "sum"),
            ("store_90d_repurchase_uv", "同店90日回购UV", "同店90日回购UV", "person", "sum"),
            ("store_90d_repurchase_amount", "同店90日回购金额", "同店90日回购金额", "CNY", "sum"),
            ("store_365d_repurchase_uv", "同店365日回购UV", "同店365日回购UV", "person", "sum"),
            ("store_365d_repurchase_amount", "同店365日回购金额", "同店365日回购金额", "CNY", "sum"),
            ("brand_30d_repurchase_uv", "同品牌30日回购UV", "同品牌30日回购UV", "person", "sum"),
            ("brand_30d_repurchase_amount", "同品牌30日回购金额", "同品牌30日回购金额", "CNY", "sum"),
            ("brand_90d_repurchase_uv", "同品牌90日回购UV", "同品牌90日回购UV", "person", "sum"),
            ("brand_90d_repurchase_amount", "同品牌90日回购金额", "同品牌90日回购金额", "CNY", "sum"),
            ("brand_365d_repurchase_uv", "同品牌365日回购UV", "同品牌365日回购UV", "person", "sum"),
            ("brand_365d_repurchase_amount", "同品牌365日回购金额", "同品牌365日回购金额", "CNY", "sum"),
        ),
    ),
    "members": DatasetDefinition(
        "members", "会员分析", "store_daily_member_analysis_overviews", "会员-日",
        dimensions=_dims(("date", "业务日期", "业务日期")),
        measures=_measures(("gmv", "会员成交金额", "会员成交金额", "CNY", "sum"), ("member_buyers", "会员成交人数", "会员成交人数", "person", "sum"), ("new_members", "新增会员", "新增会员数", "person", "sum")),
    ),
    "member_channels": DatasetDefinition(
        "member_channels", "会员渠道", "store_daily_member_channels", "会员渠道-日",
        dimensions=_dims(("date", "业务日期", "业务日期"), ("channel", "入会渠道", "入会渠道")),
        measures=_measures(("new_members", "新增会员", "新增会员数", "person", "sum"), ("gmv", "新会员成交金额", "新会员成交金额", "CNY", "sum"), ("member_buyers", "新会员成交人数", "新会员成交人数", "person", "sum")),
    ),
    "customer_service": DatasetDefinition(
        "customer_service", "客服概览", "store_daily_customer_service_overviews", "客服-日",
        dimensions=_dims(("date", "业务日期", "业务日期")),
        measures=_measures(("consultations", "咨询人数", "咨询人数", "person", "sum"), ("buyers", "客服销售人数", "客服销售人数", "person", "sum"), ("gmv", "客服销售额", "客服销售额", "CNY", "sum"), ("avg_response_seconds", "平均响应时长", "平均响应时长（秒）", "second", "avg"), ("consult_conversion_rate", "询单转化率", "询单转化率", "percent", "avg")),
    ),
    "live": DatasetDefinition(
        "live", "直播概览", "store_daily_live_overviews", "直播-日",
        dimensions=_dims(("date", "业务日期", "业务日期")),
        measures=_measures(("gmv", "直播成交金额", "直播成交金额", "CNY", "sum"), ("shop_gmv", "店播成交金额", "店播成交金额", "CNY", "sum"), ("visitors", "直播观看独立访客数", "直播观看独立访客数", "person", "sum")),
    ),
    "promotion_campaigns": DatasetDefinition(
        "promotion_campaigns", "推广计划", "store_daily_promotion_campaigns", "推广计划-日",
        dimensions=_dims(("date", "业务日期", "业务日期"), ("scene", "推广场景", "推广场景"), ("campaign_id", "推广计划ID", "推广计划ID"), ("campaign_name", "推广计划名称", "推广计划名称")),
        measures=_measures(
            ("impressions", "展现量", "展现量", "count", "sum"), ("clicks", "点击量", "点击量", "count", "sum"),
            ("spend", "花费", "花费", "CNY", "sum"), ("gmv", "总成交金额", "总成交金额", "CNY", "sum"),
            ("direct_gmv", "直接成交金额", "直接成交金额", "CNY", "sum"), ("indirect_gmv", "间接成交金额", "间接成交金额", "CNY", "sum"),
            ("buyers", "成交人数", "成交人数", "person", "sum"), ("orders", "总成交笔数", "总成交笔数", "order", "sum"),
            ("carts", "总购物车数", "总购物车数", "count", "sum"), ("new_buyers", "成交新客数", "成交新客数", "person", "sum"),
            ("member_gmv", "会员成交金额", "会员成交金额", "CNY", "sum"),
        ),
        calculated_measures=_calculated(
            ("roi", "整体 ROI", "gmv / spend", "ratio", "calculated"), ("direct_roi", "直接 ROI", "direct_gmv / spend", "ratio", "calculated"),
            ("ctr", "点击率", "clicks / impressions", "percent", "calculated"), ("cpc", "平均点击成本", "spend / clicks", "CNY", "calculated"),
            ("click_conversion_rate", "点击转化率", "buyers / clicks", "percent", "calculated"), ("cart_rate", "加购率", "carts / clicks", "percent", "calculated"),
            ("cart_cost", "加购成本", "spend / carts", "CNY", "calculated"), ("buyer_cost", "成交获客成本", "spend / buyers", "CNY", "calculated"),
            ("customer_unit_price", "推广客单价", "gmv / buyers", "CNY", "calculated"), ("new_buyer_share", "新客成交占比", "new_buyers / buyers", "percent", "calculated"),
        ),
    ),
    "promotion_crowds": DatasetDefinition("promotion_crowds", "推广人群", "store_daily_promotion_crowds", "推广人群-日", dimensions=_dims(("date", "业务日期", "业务日期"), ("scene", "推广场景", "推广场景"), ("campaign_name", "推广计划名称", "推广计划名称")), measures=_measures(("spend", "花费", "花费", "CNY", "sum"), ("gmv", "总成交金额", "总成交金额", "CNY", "sum"), ("clicks", "点击量", "点击量", "count", "sum"))),
    "promotion_adgroups": DatasetDefinition("promotion_adgroups", "推广单元", "store_daily_promotion_adgroups", "推广单元-日", dimensions=_dims(("date", "业务日期", "业务日期"), ("product_id", "商品ID", "商品ID"), ("campaign_name", "推广计划名称", "推广计划名称")), measures=_measures(("spend", "花费", "花费", "CNY", "sum"), ("gmv", "总成交金额", "总成交金额", "CNY", "sum"), ("clicks", "点击量", "点击量", "count", "sum"))),
    "promotion_keywords": DatasetDefinition("promotion_keywords", "推广关键词", "store_daily_promotion_bidwords", "关键词-日", dimensions=_dims(("date", "业务日期", "业务日期"), ("keyword", "关键词名称", "关键词名称"), ("campaign_name", "推广计划名称", "推广计划名称")), measures=_measures(("spend", "花费", "花费", "CNY", "sum"), ("gmv", "总成交金额", "总成交金额", "CNY", "sum"), ("clicks", "点击量", "点击量", "count", "sum"))),
    "promotion_products": DatasetDefinition("promotion_products", "推广商品", "store_daily_promotion_items", "推广商品-日", dimensions=_dims(("date", "业务日期", "业务日期"), ("product_id", "商品ID", "商品ID"), ("product_name", "商品名称", "商品名称")), measures=_measures(("spend", "花费", "花费", "CNY", "sum"), ("gmv", "总成交金额", "总成交金额", "CNY", "sum"), ("clicks", "点击量", "点击量", "count", "sum"))),
    "content": DatasetDefinition("content", "内容分析", "store_daily_content_overviews", "内容-日", dimensions=_dims(("date", "业务日期", "业务日期")), measures=_measures(("gmv", "种草成交金额", "种草成交金额", "CNY", "sum"), ("visitors", "内容查看人数", "内容查看人数", "person", "sum"), ("buyers", "种草成交人数", "种草成交人数", "person", "sum"), ("interactions", "内容互动次数", "内容互动次数", "count", "sum"))),
    "brand_zone": DatasetDefinition("brand_zone", "品销宝", "store_daily_brand_zone_overviews", "品销宝-日", dimensions=_dims(("date", "业务日期", "业务日期")), measures=_measures(("gmv", "成交金额", "品销宝成交金额", "CNY", "sum"), ("clicks", "点击访客数", "品销宝点击访客数", "person", "sum"), ("impressions", "展现量", "品销宝展现量", "count", "sum"))),
    "cps": DatasetDefinition("cps", "CPS", "store_daily_cps_overviews", "CPS-日", dimensions=_dims(("date", "业务日期", "业务日期")), measures=_measures(("payment_gmv", "付款金额", "CPS付款金额", "CNY", "sum"), ("settlement_gmv", "结算金额", "CPS结算金额", "CNY", "sum"), ("payment_commission", "付款佣金支出", "CPS付款佣金支出", "CNY", "sum"), ("payment_service_fee", "付款服务费支出", "CPS付款服务费支出", "CNY", "sum"), ("settlement_expense", "结算支出", "CPS结算支出费用", "CNY", "sum"))),
    "bybt": DatasetDefinition("bybt", "百亿补贴", "store_daily_bybt_overviews", "百亿补贴-日", dimensions=_dims(("date", "业务日期", "业务日期")), measures=_measures(("gmv", "支付金额", "百补支付金额", "CNY", "sum"), ("buyers", "支付买家数", "百补支付买家数", "person", "sum"))),
    "promotion_contents": DatasetDefinition(
        "promotion_contents", "推广内容", "store_daily_promotion_contents", "推广内容-日",
        dimensions=_dims(
            ("date", "业务日期", "业务日期"), ("scene", "推广场景", "推广场景"),
            ("campaign_id", "推广计划ID", "推广计划ID"), ("campaign_name", "推广计划名称", "推广计划名称"),
            ("content_id", "内容ID", "内容ID"), ("content_name", "内容名称", "内容名称"),
            ("content_type", "内容类型", "内容类型"),
        ),
        measures=_measures(
            ("impressions", "展现量", "展现量", "count", "sum"), ("clicks", "点击量", "点击量", "count", "sum"),
            ("spend", "花费", "花费", "CNY", "sum"), ("gmv", "归因成交金额", "总成交金额", "CNY", "sum"),
            ("orders", "归因成交笔数", "总成交笔数", "order", "sum"), ("carts", "购物车数", "总购物车数", "count", "sum"),
            ("favorites", "收藏数", "总收藏数", "count", "sum"),
        ),
        calculated_measures=_calculated(
            ("roi", "内容推广 ROI", "gmv / spend", "ratio", "calculated"),
            ("ctr", "内容点击率", "clicks / impressions", "percent", "calculated"),
            ("cpc", "平均点击成本", "spend / clicks", "CNY", "calculated"),
        ),
    ),
    "new_customer_discount": DatasetDefinition(
        "new_customer_discount", "新客礼金", "store_daily_new_customer_discount_overviews", "新客礼金-日",
        dimensions=_dims(("date", "业务日期", "业务日期")),
        measures=_measures(
            ("shop_visitors", "店铺访客数", "店铺访客数", "person", "sum"),
            ("product_new_visitors", "商品新访客数", "商品新访客数", "person", "sum"),
            ("buyers", "礼金新客支付人数", "新客支付人数", "person", "sum"),
            ("buyer_share", "礼金新客支付人数占比", "新客支付人数占比", "percent", "avg"),
            ("gmv", "礼金新客支付金额", "新客支付金额", "CNY", "sum"),
            ("gmv_share", "礼金新客支付金额占比", "新客支付金额占比", "percent", "avg"),
            ("conversion_rate", "礼金新客支付转化率", "新客支付转化率", "percent", "avg"),
            ("store_new_buyers", "店铺新客支付人数", "店铺新客支付人数", "person", "sum"),
            ("store_new_gmv", "店铺新客支付金额", "店铺新客支付金额", "CNY", "sum"),
            ("store_new_conversion_rate", "店铺新客支付转化率", "店铺新客支付转化率", "percent", "avg"),
        ),
    ),
    "shopping_gold": DatasetDefinition(
        "shopping_gold", "购物金", "store_daily_shopping_gold_overviews", "购物金-日",
        dimensions=_dims(("date", "业务日期", "业务日期")),
        measures=_measures(
            ("recharge_amount", "充值总金额", "充值总金额", "CNY", "sum"),
            ("recharge_buyers", "充值买家数", "充值买家数", "person", "sum"),
            ("average_recharge_amount", "人均充值金额", "人均充值金额", "CNY", "avg"),
            ("recharge_rate", "充值转化率", "充值转化率", "percent", "avg"),
            ("recharge_refund_amount", "充值成功退款金额", "充值成功退款金额", "CNY", "sum"),
            ("paid_amount", "购物金支付金额", "支付金额", "CNY", "sum"),
            ("paid_buyers", "购物金支付买家数", "支付买家数", "person", "sum"),
            ("customer_unit_price", "购物金客单价", "客单价", "CNY", "avg"),
            ("product_visitors", "商品访客数", "商品访客数", "person", "sum"),
        ),
    ),
    "taojinbi": DatasetDefinition(
        "taojinbi", "淘金币", "store_daily_taojinbi_overviews", "淘金币-日",
        dimensions=_dims(("date", "业务日期", "业务日期")),
        measures=_measures(
            ("supported_order_amount", "支持抵扣订单金额", "支持抵扣订单金额", "CNY", "sum"),
            ("discount_spend", "金币抵扣及其他支出", "实际抵扣及其他支出（元）", "CNY", "sum"),
            ("channel_order_amount", "频道成交订单金额", "频道成交订单金额", "CNY", "sum"),
            ("channel_order_count", "频道成交订单量", "频道成交订单量", "order", "sum"),
            ("channel_visitors", "频道进店访客数", "频道进店访客数", "person", "sum"),
            ("channel_product_visitors", "频道商品访客数", "频道商品访客数", "person", "sum"),
            ("platform_subsidy_amount", "全店补贴订单金额", "全店补贴订单金额", "CNY", "sum"),
            ("new_subscriptions", "新增订阅数", "新增订阅数", "person", "sum"),
        ),
    ),
    "taobao_flash_sale_overviews": DatasetDefinition(
        "taobao_flash_sale_overviews", "淘宝秒杀", "store_daily_taobao_flash_sale_overviews", "秒杀-日",
        dimensions=_dims(("date", "业务日期", "业务日期")),
        measures=_measures(
            ("active_item_level", "活动中商品量级", "活动中商品量级", "item", "sum"),
            ("item_views", "活动商品 IPV", "活动商品IPV", "count", "sum"),
            ("item_visitors", "活动商品 IPVUV", "活动商品IPVUV", "person", "sum"),
            ("orders", "活动商品成交笔数", "活动商品成交笔数", "order", "sum"),
            ("gmv", "活动商品成交金额", "活动商品成交金额", "CNY", "sum"),
            ("new_customers", "活动引导店铺新客", "活动商品引导店铺新客", "person", "sum"),
            ("burst_coefficient", "最高爆发系数", "活动商品最高爆发系数", "ratio", "max"),
        ),
        calculated_measures=_calculated(("conversion_rate", "活动访客成交率", "orders / item_visitors", "percent", "calculated")),
    ),
    "taobao_flash_sale_items": DatasetDefinition(
        "taobao_flash_sale_items", "淘宝秒杀商品明细", "store_daily_taobao_flash_sale_items", "秒杀活动-商品-日",
        dimensions=_dims(
            ("date", "业务日期", "业务日期"), ("product_id", "商品ID", "商品ID"), ("product_name", "商品名称", "商品名称"),
            ("activity_id", "活动ID", "活动ID"), ("activity_name", "活动名称", "活动名称"), ("activity_status", "活动状态", "活动状态"),
        ),
        measures=_measures(
            ("item_views", "活动商品 IPV", "活动商品IPV", "count", "sum"),
            ("item_visitors", "活动商品 IPVUV", "活动商品IPVUV", "person", "sum"),
            ("orders", "活动商品成交笔数", "活动商品成交笔数", "order", "sum"),
            ("gmv", "活动商品成交金额", "活动商品成交金额", "CNY", "sum"),
            ("new_customers", "活动引导店铺新客", "活动商品引导店铺新客", "person", "sum"),
            ("conversion_rate", "活动商品转化率", "活动商品转化率", "percent", "avg"),
        ),
    ),
    "store_activity_calendar_events": DatasetDefinition(
        "store_activity_calendar_events", "活动日历", "store_activity_calendar_events", "活动事件",
        date_column="",
        dimensions=_dims(
            ("date", "采集业务日", "业务日期"), ("activity_id", "活动ID", "活动ID"), ("activity_name", "活动名称", "活动名称"),
            ("activity_type", "活动类型", "活动类型"), ("activity_status", "活动状态", "活动状态"),
            ("activity_start", "活动开始时间", "活动开始时间"), ("activity_end", "活动结束时间", "活动结束时间"),
            ("activity_tag", "活动标签", "活动标签"), ("activity_level", "活动层级", "活动层级"), ("activity_stage", "活动阶段", "活动阶段"),
        ),
        measures=_measures(("event_count", "活动记录数", "活动ID", "event", "count")),
    ),
    "live_store_performance": DatasetDefinition(
        "live_store_performance", "店播表现", "store_daily_live_store_performance", "店播-日",
        dimensions=_dims(("date", "业务日期", "业务日期")),
        measures=_measures(
            ("viewers", "观看人数", "观看人数", "person", "sum"), ("item_click_users", "商品点击人数", "商品点击人数", "person", "sum"),
            ("view_click_rate", "观看-商品点击率", "观看-商品点击率", "percent", "avg"), ("buyers", "成交人数", "成交人数", "person", "sum"),
            ("click_conversion_rate", "点击-成交转化率", "点击-成交转化率", "percent", "avg"), ("gmv", "成交金额", "成交金额", "CNY", "sum"),
            ("customer_unit_price", "客单价", "客单价", "CNY", "avg"), ("paid_items", "成交件数", "成交件数", "item", "sum"),
            ("orders", "成交笔数", "成交笔数", "order", "sum"),
        ),
    ),
    "live_talent_reports": DatasetDefinition(
        "live_talent_reports", "达人直播", "store_daily_live_talent_reports", "达人-日",
        dimensions=_dims(("date", "业务日期", "业务日期"), ("talent_id", "合作主播ID", "合作主播ID"), ("talent_name", "合作主播名称", "合作主播名称")),
        measures=_measures(
            ("sessions", "合作场次数", "合作场次数", "session", "sum"), ("item_click_users", "商品点击人数", "商品点击人数", "person", "sum"),
            ("add_cart_users", "商品加购人数", "商品加购人数", "person", "sum"), ("buyers", "成交人数", "成交人数", "person", "sum"),
            ("gmv", "成交金额", "成交金额", "CNY", "sum"), ("paid_products", "成交商品数", "成交商品数", "item", "sum"),
            ("paid_items", "成交件数", "成交件数", "item", "sum"), ("orders", "成交笔数", "成交笔数", "order", "sum"),
        ),
        calculated_measures=_calculated(
            ("single_session_gmv", "单场成交金额", "gmv / sessions", "CNY", "calculated"),
            ("click_conversion_rate", "点击成交率", "buyers / item_click_users", "percent", "calculated"),
        ),
    ),
    "bybt_items": DatasetDefinition(
        "bybt_items", "百亿补贴商品明细", "store_daily_bybt_items", "百补商品-日",
        dimensions=_dims(
            ("date", "业务日期", "业务日期"), ("product_id", "商品ID", "商品ID"), ("product_name", "商品名称", "商品名称"),
            ("marketing_id", "营销ID", "营销ID"), ("category", "百补类目", "百补类目"), ("business_scene", "经营场景", "经营场景"),
            ("sales_mode", "销售方式", "销售方式"), ("play_type", "玩法类型", "玩法类型"),
        ),
        measures=_measures(
            ("gmv", "百补支付金额", "百补支付金额", "CNY", "sum"), ("paid_items", "百补支付件数", "百补支付成交件数", "item", "sum"),
            ("orders", "百补支付子订单数", "百补支付子订单数", "order", "sum"), ("visitors", "百补商品访客数", "百补商品访客数", "person", "sum"),
            ("conversion_rate", "百补转化率", "百补转化率", "percent", "avg"),
        ),
    ),
    "product_catalog": DatasetDefinition(
        "product_catalog", "商品主档", "store_product_catalog", "商品",
        date_column="", dimensions=_dims(
            ("product_id", "商品ID", "商品ID"), ("product_name", "商品名称", "商品名称"),
            ("product_type", "商品类型", "类型"), ("series", "产品系列", "系列"),
            ("positioning", "商品定位", "定位"), ("channel", "渠道", "渠道"),
        ),
    ),
    "taobao_price_risks": DatasetDefinition(
        "taobao_price_risks", "淘宝红线价风险", "store_daily_taobao_risk_price_items", "商品-日",
        dimensions=_dims(
            ("date", "业务日期", "业务日期"), ("product_id", "商品ID", "商品ID"),
            ("product_name", "商品名称", "商品名称"), ("risk_type", "风险类型", "风险类型"),
            ("risk_description", "风险描述", "风险描述"), ("risk_sub_description", "风险子描述", "风险子描述"),
        ),
        measures=_measures(
            ("risk_price", "最低风险价", "最低风险价", "CNY", "min"),
            ("original_price", "原价", "原价", "CNY", "max"),
            ("low_price_sku_count", "低价 SKU 数量", "低价SKU数量", "sku", "sum"),
        ),
    ),
    "taobao_current_prices": DatasetDefinition(
        "taobao_current_prices", "淘宝当前价格", "store_daily_taobao_current_price_items", "商品-日",
        dimensions=_dims(
            ("date", "业务日期", "业务日期"), ("product_id", "商品ID", "商品ID"),
            ("product_name", "商品标题", "商品标题"), ("attention", "是否需关注", "是否需关注"),
            ("risk_tag", "风险标签", "风险标签"),
        ),
        measures=_measures(
            ("low_price", "最低价", "最低价", "CNY", "min"),
            ("sku_count", "SKU 数量", "SKU数量", "sku", "sum"),
        ),
    ),
    "taobao_activity_snapshots": DatasetDefinition(
        "taobao_activity_snapshots", "淘宝活动商品快照", "store_daily_taobao_activity_item_snapshots", "活动商品-日",
        dimensions=_dims(
            ("date", "业务日期", "业务日期"), ("snapshot_type", "快照类型", "快照类型"),
            ("product_id", "商品ID", "商品ID"), ("product_name", "商品名称", "商品名称"),
            ("status", "状态", "状态"), ("status_name", "状态名称", "状态名称"),
            ("activity_name", "活动名称", "活动名称"),
        ),
        measures=_measures(
            ("activity_price", "活动价", "活动价", "CNY", "min"),
            ("original_price", "原价", "原价", "CNY", "max"),
            ("inventory", "库存", "库存", "item", "sum"),
            ("sold_count", "已售数量", "已售数量", "item", "sum"),
        ),
    ),
    # Inventory is kept in the same local warehouse but uses its own stable
    # English column contract. These read-only datasets make the inventory
    # catalog and point-in-time snapshot available to the generic data MCP
    # when a question is broader than the inventory Skill's natural-language
    # shortcuts. They intentionally expose no raw JSON or credentials.
    "inventory_catalog": DatasetDefinition(
        "inventory_catalog", "库存商品目录", "inventory_product_catalog", "商品 SKU",
        date_column="", store_column="store_id",
        dimensions=_dims(
            ("id", "目录行ID", "id"), ("series", "产品系列", "series"),
            ("specification", "规格类型", "specification"), ("size", "尺码", "size"),
            ("goods_no", "货品编码", "goods_no"), ("display_name", "商品名称", "display_name"),
            ("source", "目录来源", "source"), ("is_active", "是否有效", "is_active"),
        ),
        measures=_measures(("sku_count", "SKU 数量", "id", "sku", "count"), ("pieces", "包装片数", "pieces", "item", "sum")),
    ),
    "inventory_snapshots": DatasetDefinition(
        "inventory_snapshots", "库存快照", "jackyun_inventory_snapshots", "仓库-SKU-业务日",
        date_column="", store_column="store_id",
        dimensions=_dims(
            ("business_day", "库存业务日", "business_day"), ("warehouse_id", "仓库ID", "warehouse_id"),
            ("warehouse_name", "仓库名称", "warehouse_name"), ("goods_no", "货品编码", "goods_no"),
            ("sku_id", "SKU ID", "sku_id"), ("sku_no", "SKU 编码", "sku_no"),
            ("goods_name", "商品名称", "goods_name"), ("sku_name", "SKU 名称", "sku_name"),
            ("sku_barcode", "SKU 条码", "sku_barcode"), ("fetched_at", "采集时间", "fetched_at"),
        ),
        measures=_measures(
            ("sku_count", "库存行数", "sku_id", "row", "count"),
            ("available_quantity", "可用库存", "available_quantity", "item", "sum"),
            ("stock_quantity", "实物库存", "stock_quantity", "item", "sum"),
        ),
    ),
}


def get_dataset(key: str) -> DatasetDefinition:
    try:
        return DATASET_CATALOG[key]
    except KeyError as exc:
        raise ValueError(f"Unknown dataset: {key}") from exc
