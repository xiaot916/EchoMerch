from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Iterable


PLATFORM_ID = "\u5e73\u53f0ID"
PLATFORM_CODE = "\u5e73\u53f0\u7f16\u7801"
PLATFORM_NAME = "\u5e73\u53f0\u540d\u79f0"
STORE_ID = "\u5e97\u94faID"
STORE_SUBJECT_ID = "\u5e73\u53f0\u4e3b\u4f53ID"
PLATFORM_STORE_ID = "\u5e73\u53f0\u5e97\u94faID"
LEGACY_STORE_SUBJECT_ID = "\u5e73\u53f0\u5e97\u94faID"
STORE_NAME = "\u5e97\u94fa\u540d\u79f0"
STATUS = "\u72b6\u6001"
CREATED_AT = "\u521b\u5efa\u65f6\u95f4"
UPDATED_AT = "\u66f4\u65b0\u65f6\u95f4"
FIRST_SEEN_AT = "\u9996\u6b21\u53d1\u73b0\u65f6\u95f4"
ARTIFACT_ID = "\u8bc1\u636eID"
ENDPOINT_KEY = "\u63a5\u53e3\u6807\u8bc6"
BUSINESS_DAY = "\u4e1a\u52a1\u65e5\u671f"
FETCHED_AT = "\u6293\u53d6\u65f6\u95f4"
HTTP_STATUS = "HTTP\u72b6\u6001\u7801"
RESPONSE_CODE = "\u54cd\u5e94\u7801"
SOURCE_FILE = "\u6765\u6e90\u6587\u4ef6"
CONTENT_SHA256 = "\u5185\u5bb9SHA256"
FILE_SIZE = "\u6587\u4ef6\u5927\u5c0f"
PARSER_VERSION = "\u89e3\u6790\u5668\u7248\u672c"
PAID_AMOUNT = "\u652f\u4ed8\u91d1\u989d"
NET_PAID_AMOUNT = "\u51c0\u652f\u4ed8\u91d1\u989d"
VISITORS = "\u8bbf\u5ba2\u6570"
BUYERS = "\u4e70\u5bb6\u6570"
PAID_BUYERS = "\u652f\u4ed8\u4e70\u5bb6\u6570"
CONVERSION_RATE = "\u652f\u4ed8\u8f6c\u5316\u7387"
SIGN_REFUND_RATE = "\u7b7e\u6536\u9000\u6b3e\u7387"
PROMOTION_COST = "\u63a8\u5e7f\u6210\u672c"
ALL_SITE_PROMOTION_SPEND = "\u5168\u7ad9\u63a8\u5e7f\u82b1\u8d39"
PRECISION_AUDIENCE_PROMOTION_SPEND = "\u7cbe\u51c6\u4eba\u7fa4\u63a8\u5e7f\u82b1\u8d39"
SMART_SCENE_SPEND = "\u667a\u80fd\u573a\u666f\u82b1\u8d39"
TOTAL_PAID_AMOUNT = "\u603b\u652f\u4ed8\u91d1\u989d"
REFUND_PAID_TIME_AMOUNT = "\u9000\u6b3e\u91d1\u989d\uff08\u652f\u4ed8\u65f6\u95f4\uff09"
AMOUNT_REFUND_RATE = "\u91d1\u989d\u9000\u6b3e\u7387"
PAID_ORDERS = "\u652f\u4ed8\u8ba2\u5355\u6570"
PAID_ITEMS = "\u652f\u4ed8\u4ef6\u6570"
PAGE_VIEWS = "\u6d4f\u89c8\u91cf"
CART_COUNT = "\u52a0\u8d2d\u6b21\u6570"
CART_BUYERS = "\u52a0\u8d2d\u4e70\u5bb6\u6570"
ADD_CART_BUYERS = "\u52a0\u8d2d\u4eba\u6570"
PRODUCT_FAVORITE_BUYERS = "\u5546\u54c1\u6536\u85cf\u4eba\u6570"
AVERAGE_STAY_TIME = "\u5e73\u5747\u505c\u7559\u65f6\u957f"
FLOW_PRODUCT_VISITORS = "\u5546\u54c1\u8bbf\u5ba2\u6570"
FLOW_BOUNCE_RATE = "\u8df3\u5931\u7387"
FLOW_AVERAGE_PAGE_VIEWS = "\u4eba\u5747\u6d4f\u89c8\u91cf"
FLOW_OLD_VISITORS = "\u8001\u8bbf\u5ba2\u6570"
FLOW_NEW_VISITORS = "\u65b0\u8bbf\u5ba2\u6570"
FLOW_FOLLOW_STORE_BUYERS = "\u5173\u6ce8\u5e97\u94fa\u4eba\u6570"
FLOW_LIVE_ROOM_VISITORS = "\u76f4\u64ad\u95f4\u8bbf\u5ba2\u6570"
FLOW_SHORT_VIDEO_VISITORS = "\u77ed\u89c6\u9891\u8bbf\u5ba2\u6570"
FLOW_IMAGE_TEXT_VISITORS = "\u56fe\u6587\u8bbf\u5ba2\u6570"
FLOW_SHOP_PAGE_VISITORS = "\u5e97\u94fa\u9875\u8bbf\u5ba2\u6570"
ADD_CART_ITEMS = "\u52a0\u8d2d\u4ef6\u6570"
PAID_SUB_ORDER_COUNT = "\u652f\u4ed8\u5b50\u8ba2\u5355\u6570"
TOTAL_PAID_SUB_ORDER_COUNT = "\u603b\u652f\u4ed8\u5b50\u8ba2\u5355\u6570"
ORDER_REFUND_RATE = "\u8ba2\u5355\u9000\u6b3e\u7387"
CUSTOMER_UNIT_PRICE = "\u5ba2\u5355\u4ef7"
P4P_SPEND = "\u76f4\u901a\u8f66\u82b1\u8d39"
KEYWORD_PROMOTION_SPEND = "\u5173\u952e\u8bcd\u63a8\u5e7f\u82b1\u8d39"
TAOKE_SPEND = "\u6dd8\u5b9d\u5ba2\u82b1\u8d39"
TAOKE_COMMISSION = "\u6dd8\u5b9d\u5ba2\u4f63\u91d1"
ZHIZUAN_SPEND = "\u94bb\u5c55\u82b1\u8d39"
REFUND_FINISHED_AMOUNT = "\u9000\u6b3e\u91d1\u989d\uff08\u5b8c\u7ed3\u65f6\u95f4\uff09"
OLDER_PAID_AMOUNT = "\u8001\u5ba2\u590d\u8d2d\u91d1\u989d"
OLDER_PAID_BUYERS = "\u8001\u5ba2\u590d\u8d2d\u4eba\u6570"
OLDER_REPURCHASE_RATE = "\u8001\u5ba2\u590d\u8d2d\u7387"
REFUND_PROCESS_DAYS = "\u9000\u6b3e\u5904\u7406\u65f6\u957f(\u5929)"
WANGWANG_MANUAL_RESPONSE_SECONDS = "\u65fa\u65fa\u4eba\u5de5\u54cd\u5e94\u65f6\u957f(\u79d2)"
CONSULTATION_RATE = "\u54a8\u8be2\u7387"
PLATFORM_DUTY_RATE = "\u5e73\u53f0\u5224\u8d23\u7387"
PICKUP_24H_RATE = "24\u5c0f\u65f6\u63fd\u6536\u53ca\u65f6\u7387"
LOGISTICS_ARRIVAL_HOURS = "\u7269\u6d41\u5230\u8d27\u65f6\u957f"
NEW_CUSTOMER_DISCOUNT_SHOP_VISITORS = "\u5e97\u94fa\u8bbf\u5ba2\u6570"
NEW_CUSTOMER_DISCOUNT_PRODUCT_NEW_VISITORS = "\u5546\u54c1\u65b0\u8bbf\u5ba2\u6570"
NEW_CUSTOMER_DISCOUNT_PAID_BUYERS = "\u65b0\u5ba2\u652f\u4ed8\u4eba\u6570"
NEW_CUSTOMER_DISCOUNT_PAID_BUYER_RATIO = "\u65b0\u5ba2\u652f\u4ed8\u4eba\u6570\u5360\u6bd4"
NEW_CUSTOMER_DISCOUNT_PAID_AMOUNT = "\u65b0\u5ba2\u652f\u4ed8\u91d1\u989d"
NEW_CUSTOMER_DISCOUNT_PAID_AMOUNT_RATIO = "\u65b0\u5ba2\u652f\u4ed8\u91d1\u989d\u5360\u6bd4"
NEW_CUSTOMER_DISCOUNT_PAY_RATE = "\u65b0\u5ba2\u652f\u4ed8\u8f6c\u5316\u7387"
NEW_CUSTOMER_DISCOUNT_SHOP_PAID_BUYERS = "\u5e97\u94fa\u65b0\u5ba2\u652f\u4ed8\u4eba\u6570"
NEW_CUSTOMER_DISCOUNT_SHOP_PAID_AMOUNT = "\u5e97\u94fa\u65b0\u5ba2\u652f\u4ed8\u91d1\u989d"
NEW_CUSTOMER_DISCOUNT_SHOP_PAY_RATE = "\u5e97\u94fa\u65b0\u5ba2\u652f\u4ed8\u8f6c\u5316\u7387"
NEW_CUSTOMER_DISCOUNT_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    NEW_CUSTOMER_DISCOUNT_SHOP_VISITORS,
    NEW_CUSTOMER_DISCOUNT_PRODUCT_NEW_VISITORS,
    NEW_CUSTOMER_DISCOUNT_PAID_BUYERS,
    NEW_CUSTOMER_DISCOUNT_PAID_BUYER_RATIO,
    NEW_CUSTOMER_DISCOUNT_PAID_AMOUNT,
    NEW_CUSTOMER_DISCOUNT_PAID_AMOUNT_RATIO,
    NEW_CUSTOMER_DISCOUNT_PAY_RATE,
    NEW_CUSTOMER_DISCOUNT_SHOP_PAID_BUYERS,
    NEW_CUSTOMER_DISCOUNT_SHOP_PAID_AMOUNT,
    NEW_CUSTOMER_DISCOUNT_SHOP_PAY_RATE,
)
SHOPPING_GOLD_AVERAGE_RECHARGE_AMOUNT = "人均充值金额"
SHOPPING_GOLD_RECHARGE_AMOUNT = "充值总金额"
SHOPPING_GOLD_RECHARGE_ITEMS = "充值件数"
SHOPPING_GOLD_RECHARGE_REFUND_AMOUNT = "充值成功退款金额"
SHOPPING_GOLD_RECHARGE_CAPITAL_AMOUNT = "充值本金金额"
SHOPPING_GOLD_RECHARGE_BUYERS = "充值买家数"
SHOPPING_GOLD_RECHARGE_RATE = "充值转化率"
SHOPPING_GOLD_RECHARGE_SUB_ORDER_COUNT = "充值子订单数"
SHOPPING_GOLD_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    SHOPPING_GOLD_AVERAGE_RECHARGE_AMOUNT,
    SHOPPING_GOLD_RECHARGE_AMOUNT,
    PAID_BUYERS,
    SHOPPING_GOLD_RECHARGE_ITEMS,
    SHOPPING_GOLD_RECHARGE_REFUND_AMOUNT,
    PAID_AMOUNT,
    CUSTOMER_UNIT_PRICE,
    SHOPPING_GOLD_RECHARGE_CAPITAL_AMOUNT,
    SHOPPING_GOLD_RECHARGE_BUYERS,
    SHOPPING_GOLD_RECHARGE_RATE,
    FLOW_PRODUCT_VISITORS,
    SHOPPING_GOLD_RECHARGE_SUB_ORDER_COUNT,
)
BYBT_VISITORS = "百补访客数"
BYBT_PAID_BUYERS = "百补支付买家数"
BYBT_ONLINE_ITEMS = "百补在线商品数量"
BYBT_PAID_AMOUNT = "百补支付金额"
BYBT_PAID_SUB_ORDER_COUNT = "百补子订单数"
BYBT_PAID_ITEMS = "百补支付成交件数"
BYBT_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    BYBT_VISITORS,
    BYBT_PAID_BUYERS,
    BYBT_ONLINE_ITEMS,
    BYBT_PAID_AMOUNT,
    BYBT_PAID_SUB_ORDER_COUNT,
    BYBT_PAID_ITEMS,
)
BRAND_ZONE_IMPRESSIONS = "品销宝展现量"
BRAND_ZONE_SEARCH_REQUESTS = "品销宝搜索量"
BRAND_ZONE_CLICKS = "品销宝点击量"
BRAND_ZONE_CLICK_RATE = "品销宝点击率"
BRAND_ZONE_CLICK_VISITORS = "品销宝点击访客数"
BRAND_ZONE_ITEM_CART_COUNT = "品销宝宝贝加购数"
BRAND_ZONE_PAID_AMOUNT = "品销宝成交金额"
BRAND_ZONE_PAID_ORDER_COUNT = "品销宝成交笔数"
BRAND_ZONE_CONVERSION_RATE = "品销宝转化率"
BRAND_ZONE_DESTINATION_CLICKS = "品销宝跳转点击量"
BRAND_ZONE_INTERACTION_CLICKS = "品销宝互动点击量"
BRAND_ZONE_DESTINATION_CLICK_RATE = "品销宝跳转点击率"
BRAND_ZONE_SHOP_FAVORITES = "品销宝店铺收藏数"
BRAND_ZONE_ITEM_FAVORITES = "品销宝宝贝收藏数"
BRAND_ZONE_ITEM_PAGE_VIEWS = "品销宝宝贝浏览数"
BRAND_ZONE_RESEARCH_IMPRESSIONS = "品销宝回搜展现量"
BRAND_ZONE_SHOP_PAGE_VIEWS = "品销宝店铺浏览数"
BRAND_ZONE_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    BRAND_ZONE_IMPRESSIONS,
    BRAND_ZONE_SEARCH_REQUESTS,
    BRAND_ZONE_CLICKS,
    BRAND_ZONE_CLICK_RATE,
    BRAND_ZONE_CLICK_VISITORS,
    BRAND_ZONE_ITEM_CART_COUNT,
    BRAND_ZONE_PAID_AMOUNT,
    BRAND_ZONE_PAID_ORDER_COUNT,
    BRAND_ZONE_CONVERSION_RATE,
    BRAND_ZONE_DESTINATION_CLICKS,
    BRAND_ZONE_INTERACTION_CLICKS,
    BRAND_ZONE_DESTINATION_CLICK_RATE,
    BRAND_ZONE_SHOP_FAVORITES,
    BRAND_ZONE_ITEM_FAVORITES,
    BRAND_ZONE_ITEM_PAGE_VIEWS,
    BRAND_ZONE_RESEARCH_IMPRESSIONS,
    BRAND_ZONE_SHOP_PAGE_VIEWS,
)
CPS_PAYMENT_COMMISSION_EXPENSE = "CPS付款佣金支出"
CPS_PAYMENT_SERVICE_FEE_EXPENSE = "CPS付款服务费支出"
CPS_PAYMENT_COMMISSION_RATE = "CPS付款佣金率"
CPS_PAYMENT_SERVICE_FEE_RATE = "CPS付款服务费率"
CPS_PAYMENT_ORDER_COUNT = "CPS付款笔数"
CPS_PAYMENT_AMOUNT = "CPS付款金额"
CPS_CLICK_VISITORS = "CPS点击人数"
CPS_SETTLEMENT_TOTAL_EXPENSE = "CPS结算支出费用"
CPS_SETTLEMENT_ORDER_COUNT = "CPS结算笔数"
CPS_SETTLEMENT_AMOUNT = "CPS结算金额"
CPS_PREORDER_DEPOSIT_ORDER_COUNT = "CPS预售定金笔数"
CPS_PREORDER_DEPOSIT_AMOUNT = "CPS预售定金金额"
CPS_PREORDER_REMAINING_AMOUNT = "CPS预估预售尾款金额"
CPS_PREORDER_TOTAL_AMOUNT = "CPS预估预售整单金额"
CPS_PAYMENT_MARKETING_SERVICE_FEE_EXPENSE = "CPS付款营销服务费支出"
CPS_SETTLEMENT_MARKETING_SERVICE_FEE_EXPENSE = "CPS结算营销服务费支出"
CPS_FIELDS = (
    (CPS_PAYMENT_COMMISSION_EXPENSE, "pay_ord_cfee_8"),
    (CPS_PAYMENT_SERVICE_FEE_EXPENSE, "pay_ord_sfee_8"),
    (CPS_PAYMENT_COMMISSION_RATE, "pay_ord_cfee_rt_8"),
    (CPS_PAYMENT_SERVICE_FEE_RATE, "pay_ser_ord_sfee_rt_8"),
    (CPS_PAYMENT_ORDER_COUNT, "pay_ord_num_8"),
    (CPS_PAYMENT_AMOUNT, "pay_ord_amt_8"),
    (CPS_CLICK_VISITORS, "uclk_uv_8"),
    (CPS_SETTLEMENT_TOTAL_EXPENSE, "sett_ord_total_fee_8"),
    (CPS_SETTLEMENT_ORDER_COUNT, "sett_ord_num_8"),
    (CPS_SETTLEMENT_AMOUNT, "sett_ord_amt_8"),
    (CPS_PREORDER_DEPOSIT_ORDER_COUNT, "dep_ord_num_8"),
    (CPS_PREORDER_DEPOSIT_AMOUNT, "dep_ord_dep_amt_8"),
    (CPS_PREORDER_REMAINING_AMOUNT, "dep_ord_rest_amt_8"),
    (CPS_PREORDER_TOTAL_AMOUNT, "dep_ord_total_amt_8"),
    (CPS_PAYMENT_MARKETING_SERVICE_FEE_EXPENSE, "pay_bmkt_fee_8"),
    (CPS_SETTLEMENT_MARKETING_SERVICE_FEE_EXPENSE, "sett_bmkt_fee_8"),
)
CPS_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    *[column for column, _ in CPS_FIELDS],
)
TAOBAO_FLASH_SALE_ITEM_COUNT_LEVEL = "活动中商品量级"
TAOBAO_FLASH_SALE_PRODUCT_IPV = "活动商品IPV"
TAOBAO_FLASH_SALE_PRODUCT_IPVUV = "活动商品IPVUV"
TAOBAO_FLASH_SALE_PAID_ORDER_COUNT = "活动商品成交笔数"
TAOBAO_FLASH_SALE_PAID_ORDER_AMOUNT = "活动商品成交金额"
TAOBAO_FLASH_SALE_NEW_CUSTOMERS = "活动商品引导店铺新客"
TAOBAO_FLASH_SALE_BURST_COEFFICIENT = "活动商品最高爆发系数"
TAOBAO_FLASH_SALE_FIELDS = (
    (TAOBAO_FLASH_SALE_ITEM_COUNT_LEVEL, "itemCnt"),
    (TAOBAO_FLASH_SALE_PRODUCT_IPV, "ipv"),
    (TAOBAO_FLASH_SALE_PRODUCT_IPVUV, "ipvUv"),
    (TAOBAO_FLASH_SALE_PAID_ORDER_COUNT, "payOrderCnt"),
    (TAOBAO_FLASH_SALE_PAID_ORDER_AMOUNT, "payOrderAmt"),
    (TAOBAO_FLASH_SALE_NEW_CUSTOMERS, "newDac"),
    (TAOBAO_FLASH_SALE_BURST_COEFFICIENT, "payOrderCntCoef"),
)
TAOBAO_FLASH_SALE_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    *[column for column, _ in TAOBAO_FLASH_SALE_FIELDS],
)

# Product-level snapshots are kept separate from the daily overview totals.
BYBT_ITEM_TABLE = "store_daily_bybt_items"
BYBT_ITEM_DIMENSIONS = (
    "商品ID", "营销ID", "商品名称", "百补类目", "经营场景", "销售方式", "赛道类型", "玩法类型",
)
BYBT_ITEM_METRICS = (
    "百补支付金额", "百补支付成交件数", "百补支付子订单数", "百补商品访客数", "百补转化率",
)
BYBT_ITEM_COLUMNS = (STORE_ID, BUSINESS_DAY, *BYBT_ITEM_DIMENSIONS, *BYBT_ITEM_METRICS)

TAOBAO_FLASH_SALE_ITEM_TABLE = "store_daily_taobao_flash_sale_items"
TAOBAO_FLASH_SALE_ITEM_DIMENSIONS = (
    "商品ID", "活动ID", "商品名称", "活动名称", "活动状态", "活动开始时间", "活动结束时间",
)
TAOBAO_FLASH_SALE_ITEM_METRICS = (
    "活动商品IPV", "活动商品IPVUV", "活动商品成交笔数", "活动商品成交金额", "活动商品引导店铺新客", "活动商品转化率",
)
TAOBAO_FLASH_SALE_ITEM_COLUMNS = (
    STORE_ID, BUSINESS_DAY, *TAOBAO_FLASH_SALE_ITEM_DIMENSIONS, *TAOBAO_FLASH_SALE_ITEM_METRICS,
)

# Taobao operational snapshots are deliberately separate from promotion
# performance facts.  They describe the current item/risk/activity state and
# are replaced for the same store/day on each successful collection.
TAOBAO_RISK_PRICE_ITEM_TABLE = "store_daily_taobao_risk_price_items"
TAOBAO_RISK_PRICE_ITEM_DIMENSIONS = (
    "商品ID", "商品名称", "风险更新时间", "风险类型", "风险描述", "促销详情", "风险子描述",
)
TAOBAO_RISK_PRICE_ITEM_METRICS = (
    "最低风险价", "原价", "低价SKU数量",
)
TAOBAO_RISK_PRICE_ITEM_COLUMNS = (
    STORE_ID, BUSINESS_DAY, *TAOBAO_RISK_PRICE_ITEM_DIMENSIONS, *TAOBAO_RISK_PRICE_ITEM_METRICS,
)

TAOBAO_CURRENT_PRICE_ITEM_TABLE = "store_daily_taobao_current_price_items"
TAOBAO_CURRENT_PRICE_ITEM_DIMENSIONS = (
    "商品ID", "商品标题", "是否需关注", "风险标签", "正常促销详情", "预测促销详情",
    "风险促销详情", "商品详情链接", "主图链接",
)
TAOBAO_CURRENT_PRICE_ITEM_METRICS = (
    "最低价", "最低价下限", "最低价上限", "原价下限", "原价上限",
    "正常预测价下限", "正常预测价上限", "预测价格下限", "预测价格上限", "SKU数量",
)
TAOBAO_CURRENT_PRICE_ITEM_COLUMNS = (
    STORE_ID, BUSINESS_DAY, *TAOBAO_CURRENT_PRICE_ITEM_DIMENSIONS, *TAOBAO_CURRENT_PRICE_ITEM_METRICS,
)

TAOBAO_ACTIVITY_ITEM_SNAPSHOT_TABLE = "store_daily_taobao_activity_item_snapshots"
TAOBAO_ACTIVITY_ITEM_SNAPSHOT_DIMENSIONS = (
    "快照类型", "营销ID", "商品ID", "商品名称", "状态", "状态名称", "活动名称",
    "活动开始时间", "活动结束时间", "签署时间", "商品链接", "活动链接", "商品图片",
    "活动价格名称", "供货价名称", "通用活动标签", "素材状态名称", "IC状态名称",
)
TAOBAO_ACTIVITY_ITEM_SNAPSHOT_METRICS = (
    "原价", "活动价", "供货价", "库存", "已售数量", "限购数量", "营销玩法已报名数量",
    "营销玩法未报名数量",
)
TAOBAO_ACTIVITY_ITEM_SNAPSHOT_COLUMNS = (
    STORE_ID, BUSINESS_DAY, *TAOBAO_ACTIVITY_ITEM_SNAPSHOT_DIMENSIONS,
    *TAOBAO_ACTIVITY_ITEM_SNAPSHOT_METRICS,
)
CONTENT_CLICK_USERS = "点击人数"
CONTENT_VIEW_COUNT = "内容查看次数"
CONTENT_EXPOSURE_PV_CLICK_RATE = "曝光PV点击率"
CONTENT_FREE_VIEW_COUNT = "免费内容查看次数"
CONTENT_PRODUCT_CLICK_USERS = "商品点击人数"
CONTENT_GUIDE_CLICK_CONTENTS = "商品引导点击内容数"
CONTENT_TOTAL_PUBLISHED_CONTENTS = "累计发布内容数"
CONTENT_GRASS_GMV_SHARE = "种草成交金额占比全店"
CONTENT_GUIDE_CLICK_USERS = "商品引导点击人数"
CONTENT_NON_FREE_VIEW_COUNT = "非免费内容查看次数"
CONTENT_PRODUCT_CLICK_CONTENTS = "商品点击内容数"
CONTENT_PRODUCT_CLICK_COUNT = "商品点击次数"
CONTENT_PUBLIC_CONTENTS = "公开内容数"
CONTENT_GRASS_PAID_ORDERS = "种草成交订单数"
CONTENT_INTERACTION_COUNT = "内容互动次数"
CONTENT_PUBLISHED_CONTENTS = "发布内容数"
CONTENT_EXPOSURE_USERS = "曝光人数"
CONTENT_VIEWERS = "内容查看人数"
CONTENT_CART_USERS = "商品加购人数"
CONTENT_GUIDE_CLICK_RATE = "商品引导点击率"
CONTENT_VIEWED_CONTENTS = "查看内容数"
CONTENT_GRASS_PAID_BUYERS = "种草成交人数"
CONTENT_GUIDE_CLICK_COUNT = "商品引导点击次数"
CONTENT_GRASS_PAID_AMOUNT = "种草成交金额"
CONTENT_INTERACTION_USERS = "内容互动人数"
CONTENT_INTERACTION_RATE = "内容互动率"
CONTENT_AVERAGE_VIEW_TIME = "次均内容查看时长"
CONTENT_EXPOSURE_UV_CLICK_RATE = "曝光UV点击率"
CONTENT_CART_COUNT = "商品加购次数"
CONTENT_OVERVIEW_FIELDS = (
    (CONTENT_CLICK_USERS, "clickUv"),
    (CONTENT_VIEW_COUNT, "consumePv"),
    (CONTENT_EXPOSURE_PV_CLICK_RATE, "pctr"),
    (CONTENT_FREE_VIEW_COUNT, "freeConsumePv"),
    (CONTENT_PRODUCT_CLICK_USERS, "detailIpvUv"),
    (CONTENT_GUIDE_CLICK_CONTENTS, "ipvContentCnt"),
    (CONTENT_TOTAL_PUBLISHED_CONTENTS, "publishContentCnt"),
    (CONTENT_GRASS_GMV_SHARE, "gmvPct"),
    (CONTENT_GUIDE_CLICK_USERS, "ipvUv"),
    (CONTENT_NON_FREE_VIEW_COUNT, "notFreeConsumePv"),
    (CONTENT_PRODUCT_CLICK_CONTENTS, "detailIpvContentCnt"),
    (CONTENT_PRODUCT_CLICK_COUNT, "detailIpvPv"),
    (CONTENT_PUBLIC_CONTENTS, "publicContentCnt"),
    (CONTENT_GRASS_PAID_ORDERS, "payOrderCntZcLast"),
    (CONTENT_INTERACTION_COUNT, "itrtPv"),
    (CONTENT_PUBLISHED_CONTENTS, "publishAllContentCnt"),
    (CONTENT_EXPOSURE_USERS, "expoUv"),
    (CONTENT_VIEWERS, "consumeUv"),
    (CONTENT_CART_USERS, "cartUv"),
    (CONTENT_GUIDE_CLICK_RATE, "ipvRate"),
    (CONTENT_VIEWED_CONTENTS, "consumeContentCnt"),
    (CONTENT_GRASS_PAID_BUYERS, "payBuyerCntZc"),
    (CONTENT_GUIDE_CLICK_COUNT, "ipvPv"),
    (CONTENT_GRASS_PAID_AMOUNT, "payAmtZcLast"),
    (CONTENT_INTERACTION_USERS, "itrtUv"),
    (CONTENT_INTERACTION_RATE, "itrtRate"),
    (CONTENT_AVERAGE_VIEW_TIME, "consumeTimeAvgPv"),
    (CONTENT_EXPOSURE_UV_CLICK_RATE, "uctr"),
    (CONTENT_CART_COUNT, "cartPv"),
)
CONTENT_OVERVIEW_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    *[column for column, _ in CONTENT_OVERVIEW_FIELDS],
)
TAOJINBI_COIN_BALANCE = "实时金币余额"
TAOJINBI_SUPPORTED_ORDER_COUNT = "支持抵扣订单量"
TAOJINBI_ACTIVE_USER_ORDER_COUNT = "金币活跃用户订单量"
TAOJINBI_SUPPORTED_ORDER_AMOUNT = "支持抵扣订单金额"
TAOJINBI_DISCOUNT_SPEND = "实际抵扣及其他支出（元）"
TAOJINBI_CHANNEL_ORDER_COUNT = "频道成交订单量"
TAOJINBI_CHANNEL_LARGE_DISCOUNT_ORDER_COUNT = "频道大额抵成交订单量"
TAOJINBI_CHANNEL_ORDER_AMOUNT = "频道成交订单金额"
TAOJINBI_CHANNEL_LARGE_DISCOUNT_ORDER_AMOUNT = "频道大额抵成交金额"
TAOJINBI_CHANNEL_VISITORS = "频道进店访客数"
TAOJINBI_CHANNEL_PRODUCT_VISITORS = "频道商品访客数"
TAOJINBI_CHANNEL_PRODUCT_VIEWS = "频道商品访问次数"
TAOJINBI_PLATFORM_SUBSIDY_ORDERS = "全店平台补贴订单"
TAOJINBI_PLATFORM_SUBSIDY_ORDER_AMOUNT = "全店补贴订单金额"
TAOJINBI_SELLER_COIN_INCOME = "卖家金币收入"
TAOJINBI_SELLER_COIN_EXPENSE = "卖家金币支出"
TAOJINBI_TOTAL_VISITS = "总访问次数"
TAOJINBI_FEATURED_PRODUCT_VIEWS = "首推商品访问次数"
TAOJINBI_LIVE_ROOM_VIEWS = "直播间访问次数"
TAOJINBI_NEW_SUBSCRIPTIONS = "新增订阅数"
TAOJINBI_TRAFFIC_GUARANTEE_SHOP_VISITS = "流量保障进店铺数"
TAOJINBI_TRAFFIC_GUARANTEE_LIVE_VISITS = "流量保障进直播间数"
TAOJINBI_TRAFFIC_SUPPORT_SHOP_JUMPS = "流量扶持跳转店铺数"
TAOJINBI_PLATFORM_SUBSIDY_REDEMPTION = "全店平台补贴核销"
TAOJINBI_TAB3_PRODUCT_EXPOSURES = "Tab3商品卡曝光次数"
TAOJINBI_BRAND_GRID_EXPOSURES = "品牌格子曝光次数"
TAOJINBI_FIELDS = (
    (TAOJINBI_COIN_BALANCE, "coinAmount"),
    (TAOJINBI_SUPPORTED_ORDER_COUNT, "tt_ord_cnt"),
    (TAOJINBI_ACTIVE_USER_ORDER_COUNT, "active_user_odr_cnt"),
    (TAOJINBI_SUPPORTED_ORDER_AMOUNT, "tt_ord_amt"),
    (TAOJINBI_DISCOUNT_SPEND, "coin_tt_disc_amt"),
    (TAOJINBI_CHANNEL_ORDER_COUNT, "coin_odr_cnt"),
    (TAOJINBI_CHANNEL_LARGE_DISCOUNT_ORDER_COUNT, "coin_disc_ord_cnt"),
    (TAOJINBI_CHANNEL_ORDER_AMOUNT, "coin_ord_amt"),
    (TAOJINBI_CHANNEL_LARGE_DISCOUNT_ORDER_AMOUNT, "coin_disc_ord_amt"),
    (TAOJINBI_CHANNEL_VISITORS, "coin_visit_uv"),
    (TAOJINBI_CHANNEL_PRODUCT_VISITORS, "coin_item_visit_uv"),
    (TAOJINBI_CHANNEL_PRODUCT_VIEWS, "coin_item_visit_pv"),
    (TAOJINBI_PLATFORM_SUBSIDY_ORDERS, "coin_sub_ord_cnt"),
    (TAOJINBI_PLATFORM_SUBSIDY_ORDER_AMOUNT, "coin_sub_ord_amt"),
    (TAOJINBI_SELLER_COIN_INCOME, "coin_seller_inc"),
    (TAOJINBI_SELLER_COIN_EXPENSE, "coin_seller_exp"),
    (TAOJINBI_TOTAL_VISITS, "fans_shop_vst_cnt"),
    (TAOJINBI_FEATURED_PRODUCT_VIEWS, "fans_item_view_cnt"),
    (TAOJINBI_LIVE_ROOM_VIEWS, "fans_live_view_cnt"),
    (TAOJINBI_NEW_SUBSCRIPTIONS, "fans_inc_cnt_cnt"),
    (TAOJINBI_TRAFFIC_GUARANTEE_SHOP_VISITS, "tgt_shop_vst_cnt"),
    (TAOJINBI_TRAFFIC_GUARANTEE_LIVE_VISITS, "tgt_live_vst_cnt"),
    (TAOJINBI_TRAFFIC_SUPPORT_SHOP_JUMPS, "spt_shop_jump"),
    (TAOJINBI_PLATFORM_SUBSIDY_REDEMPTION, "coin_sub_benefit_amt"),
    (TAOJINBI_TAB3_PRODUCT_EXPOSURES, "tab3_expose_pv"),
    (TAOJINBI_BRAND_GRID_EXPOSURES, "brand_box_expose_pv"),
)
TAOJINBI_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    *[column for column, _ in TAOJINBI_FIELDS],
)
CUSTOMER_SERVICE_GMV = "客服销售额"
CUSTOMER_SERVICE_SALE_COUNT = "客服销售人数"
CUSTOMER_SERVICE_SALE_RATIO = "客服销售占比"
CUSTOMER_SERVICE_SALE_PRICE = "客服销售客单价"
CUSTOMER_SERVICE_REFUND_AMOUNT = "成功退款金额"
CUSTOMER_SERVICE_NET_SALES_AMOUNT = "净销售额"
CUSTOMER_SERVICE_CONSULT_USERS = "咨询人数"
CUSTOMER_SERVICE_RECEPTION_USERS = "接待人数"
CUSTOMER_SERVICE_CONSULT_PAY_RATE = "询单转化率"
CUSTOMER_SERVICE_AVG_REPLY_SECONDS = "平均响应时长（秒）"
CUSTOMER_SERVICE_SATISFACTION_RATE = "客户满意率"
CUSTOMER_SERVICE_WW_REPLY_RATE = "旺旺回复率"
CUSTOMER_SERVICE_REFUND_ONLY_FINISH_HOURS = "仅退款自主完结时长（小时）"
CUSTOMER_SERVICE_RETURN_REFUND_FINISH_HOURS = "退货退款完结时长（小时）"
CUSTOMER_SERVICE_PLATFORM_HELP_RATE = "平台求助率"
CUSTOMER_SERVICE_PLATFORM_RESP_RATE = "平台判责率"
CUSTOMER_SERVICE_OVERVIEW_FIELDS = (
    (CUSTOMER_SERVICE_GMV, "customerServiceGmv"),
    (CUSTOMER_SERVICE_SALE_COUNT, "customerServiceSaleCnt"),
    (CUSTOMER_SERVICE_SALE_RATIO, "customerServiceSaleRatio"),
    (CUSTOMER_SERVICE_SALE_PRICE, "customerServiceSalePrice"),
    (CUSTOMER_SERVICE_REFUND_AMOUNT, "sucRefundAmount"),
    (CUSTOMER_SERVICE_NET_SALES_AMOUNT, "netPayAmt"),
    (CUSTOMER_SERVICE_CONSULT_USERS, "consultUserCnt"),
    (CUSTOMER_SERVICE_RECEPTION_USERS, "customerServiceRecUserCnt"),
    (CUSTOMER_SERVICE_CONSULT_PAY_RATE, "wwConsultPayRate"),
    (CUSTOMER_SERVICE_AVG_REPLY_SECONDS, "avgReplyInterval"),
    (CUSTOMER_SERVICE_SATISFACTION_RATE, "customerAllSateRate"),
    (CUSTOMER_SERVICE_WW_REPLY_RATE, "wwUserReplayRate"),
    (CUSTOMER_SERVICE_REFUND_ONLY_FINISH_HOURS, "jtkCaseEndAvgDur"),
    (CUSTOMER_SERVICE_RETURN_REFUND_FINISH_HOURS, "thtkCaseEndAvgDur"),
    (CUSTOMER_SERVICE_PLATFORM_HELP_RATE, "pltfHelpRate"),
    (CUSTOMER_SERVICE_PLATFORM_RESP_RATE, "pltfRespRate"),
)
CUSTOMER_SERVICE_OVERVIEW_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    *[column for column, _ in CUSTOMER_SERVICE_OVERVIEW_FIELDS],
)
CUSTOMER_SERVICE_ACCOUNT_NICK = "旺旺昵称"
CUSTOMER_SERVICE_ACCOUNT_VALID_RECEPTION_USERS = "有效接待人数"
CUSTOMER_SERVICE_ACCOUNT_CONSULT_ORDER_USERS = "询单人数"
CUSTOMER_SERVICE_ACCOUNT_ORDER_USERS = "下单人数"
CUSTOMER_SERVICE_ACCOUNT_ORDER_AMOUNT = "下单金额"
CUSTOMER_SERVICE_ACCOUNT_SALE_USERS = "销售人数"
CUSTOMER_SERVICE_ACCOUNT_SALE_AMOUNT = "销售额"
CUSTOMER_SERVICE_ACCOUNT_SALE_QUANTITY = "销售量"
CUSTOMER_SERVICE_ACCOUNT_ORDER_COUNT = "订单量"
CUSTOMER_SERVICE_ACCOUNT_SALE_AMOUNT_RATIO = "个人销售额占比"
CUSTOMER_SERVICE_ACCOUNT_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    CUSTOMER_SERVICE_ACCOUNT_NICK,
    CUSTOMER_SERVICE_CONSULT_USERS,
    CUSTOMER_SERVICE_ACCOUNT_VALID_RECEPTION_USERS,
    CUSTOMER_SERVICE_ACCOUNT_CONSULT_ORDER_USERS,
    CUSTOMER_SERVICE_ACCOUNT_ORDER_USERS,
    CUSTOMER_SERVICE_ACCOUNT_ORDER_AMOUNT,
    CUSTOMER_SERVICE_ACCOUNT_SALE_USERS,
    CUSTOMER_SERVICE_ACCOUNT_SALE_AMOUNT,
    CUSTOMER_SERVICE_ACCOUNT_SALE_QUANTITY,
    CUSTOMER_SERVICE_ACCOUNT_ORDER_COUNT,
    CUSTOMER_SERVICE_ACCOUNT_SALE_AMOUNT_RATIO,
    CUSTOMER_SERVICE_REFUND_AMOUNT,
    CUSTOMER_SERVICE_NET_SALES_AMOUNT,
)

PRODUCT_RANKING_TABLE = "store_daily_product_rankings"
PRODUCT_RANKING_ITEM_ID = "\u5546\u54c1ID"
PRODUCT_RANKING_ITEM_NAME = "\u5546\u54c1\u540d\u79f0"
PRODUCT_RANKING_ITEM_STATUS = "\u5546\u54c1\u72b6\u6001"
PRODUCT_RANKING_FIELDS = (
    (PAID_AMOUNT, "payAmt"),
    (TOTAL_PAID_AMOUNT, "subPayOrdAmt"),
    (REFUND_FINISHED_AMOUNT, "sucRefundAmt"),
    (PAID_ITEMS, "payItmCnt"),
    ("\u603b\u652f\u4ed8\u5546\u54c1\u4ef6\u6570", "subPayOrdItmQty"),
    (PAID_BUYERS, "payByrCnt"),
    (CONVERSION_RATE, "payRate"),
    ("\u652f\u4ed8\u65b0\u4e70\u5bb6\u6570", "newPayByrCnt"),
    ("\u652f\u4ed8\u8001\u4e70\u5bb6\u6570", "payOldByrCnt"),
    (OLDER_PAID_AMOUNT, "olderPayAmt"),
    ("\u805a\u5212\u7b97\u652f\u4ed8\u91d1\u989d", "juPayAmt"),
    ("\u6708\u7d2f\u8ba1\u652f\u4ed8\u91d1\u989d", "mtdPayAmt"),
    ("\u6708\u7d2f\u8ba1\u652f\u4ed8\u4ef6\u6570", "mtdPayItmCnt"),
    ("\u5e74\u7d2f\u8ba1\u652f\u4ed8\u91d1\u989d", "ytdPayAmt"),
    (PRODUCT_RANKING_ITEM_STATUS, "itemStatus"),
    ("\u5546\u54c1\u52a0\u8d2d\u4ef6\u6570", "itemCartCnt"),
    ("\u5546\u54c1\u52a0\u8d2d\u4eba\u6570", "itemCartByrCnt"),
    (PRODUCT_FAVORITE_BUYERS, "itemCltByrCnt"),
    ("\u8bbf\u95ee\u52a0\u8d2d\u8f6c\u5316\u7387", "visitCartRate"),
    ("\u8bbf\u95ee\u6536\u85cf\u8f6c\u5316\u7387", "visitCltRate"),
    (FLOW_PRODUCT_VISITORS, "itmUv"),
    ("\u5546\u54c1\u6d4f\u89c8\u91cf", "itmPv"),
    (AVERAGE_STAY_TIME, "itmStayTime"),
    ("\u5546\u54c1\u8be6\u60c5\u9875\u8df3\u51fa\u7387", "itmBounceRate"),
    ("\u641c\u7d22\u5f15\u5bfc\u8bbf\u5ba2\u6570", "seGuideUv"),
    ("\u641c\u7d22\u5f15\u5bfc\u652f\u4ed8\u4e70\u5bb6\u6570", "seGuidePayByrCnt"),
    ("\u641c\u7d22\u5f15\u5bfc\u652f\u4ed8\u8f6c\u5316\u7387", "seGuidePayRate"),
    ("\u8bbf\u5ba2\u5e73\u5747\u4ef7\u503c", "uvAvgValue"),
    ("\u4ef7\u683c\u529b\u661f\u7ea7", "starLevel001"),
    ("\u4ef6\u5355\u4ef7", "itemUnitPrice1"),
    ("\u63a8\u5e7f\u6d88\u8017", "fCharge"),
    ("\u63a8\u5e7f\u76f4\u63a5ROI", "pDROI"),
)
PRODUCT_RANKING_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    PRODUCT_RANKING_ITEM_ID,
    PRODUCT_RANKING_ITEM_NAME,
    *[column for column, _ in PRODUCT_RANKING_FIELDS],
)
PRODUCT_CATALOG_TABLE = "store_product_catalog"
PRODUCT_CATALOG_COLUMNS = (
    STORE_ID,
    "商品ID",
    "商品名称",
    "类型",
    "属性",
    "系列",
    "定位",
    "渠道",
)

# The shop's operational SKU/code dictionary is intentionally separate from
# the platform product master.  A code may legitimately map to more than one
# physical product (for example the same sample code used by diaper and
# pull-up variants), so this table does not make goods_no unique.
INVENTORY_PRODUCT_CATALOG_TABLE = "inventory_product_catalog"

# Brand Data Bank is a separate analytical subject from store operations.
# Brand facts intentionally do not carry a store id; store links are kept in
# brand_store_scopes only for authorization and drill-through context.
BRAND_TABLE = "brands"
BRAND_STORE_SCOPE_TABLE = "brand_store_scopes"
BRAND_ASSET_OVERVIEW_TABLE = "brand_asset_daily_overviews"
BRAND_ASSET_STAGE_TABLE = "brand_asset_daily_stages"
BRAND_ASSET_DIMENSION_TABLE = "brand_asset_daily_dimensions"
BRAND_ASSET_METRICS_TABLE = "brand_asset_daily_metrics"
BRAND_ASSET_FLOW_TABLE = "brand_asset_daily_flows"
BRAND_BENCHMARK_TABLE = "brand_asset_benchmarks"
BRAND_ACTIVITY_TABLE = "brand_activity_performance"
BRAND_PRODUCT_TABLE = "brand_products"
BRAND_PRODUCT_STORE_LINK_TABLE = "brand_product_store_links"
BRAND_PRODUCT_DAILY_TABLE = "brand_asset_daily_products"
BRAND_PRODUCT_DIMENSION_TABLE = "brand_asset_daily_product_dimensions"

BRAND_ID = "品牌ID"
BRAND_SUBJECT_ID = "品牌主体ID"
BRAND_NAME = "品牌名称"
BRAND_STATUS = "品牌状态"
BRAND_STATISTIC_SCOPE = "统计范围"
BRAND_DIMENSION_TYPE = "维度类型"
BRAND_DIMENSION_CODE = "维度编码"
BRAND_DIMENSION_NAME = "维度名称"
BRAND_STAGE_CODE = "资产阶段编码"
BRAND_STAGE_NAME = "资产阶段名称"
BRAND_CONSUMER_COUNT = "消费者数"
BRAND_CONSUMER_SHARE = "消费者占比"
BRAND_RELATIONSHIP_DEEPENING_RATE = "关系加深率"
BRAND_REPURCHASE_PURCHASE_RATIO = "蓄水购买比"
BRAND_TRANSACTION_AMOUNT = "成交金额"
BRAND_TRANSACTION_BUYER_COUNT = "成交人数"
BRAND_CONSUMER_UNIT_PRICE = "客单价"
BRAND_CONVERSION_RATE = "成交转化率"
BRAND_PREDICTED_CONSUMER_VALUE = "消费者价值预测"
BRAND_MEMBER_TRANSACTION_AMOUNT = "会员成交金额"
BRAND_FLOW_TYPE = "流转类型"
BRAND_FROM_STAGE = "来源阶段"
BRAND_TO_STAGE = "目标阶段"
BRAND_FLOW_COUNT = "流转人数"
BRAND_FLOW_SHARE = "流转占比"
BRAND_PERIOD_START = "统计开始日期"
BRAND_PERIOD_END = "统计结束日期"
BRAND_METRIC_NAME = "指标名称"
BRAND_VALUE = "品牌值"
INDUSTRY_MEDIAN = "行业中位值"
INDUSTRY_TOP = "行业优秀值"
INDUSTRY_RANK = "行业排名"
SAMPLE_SIZE = "样本量"
BRAND_ACTIVITY_ID = "活动ID"
BRAND_ACTIVITY_NAME = "活动名称"
BRAND_ACTIVITY_TYPE = "活动类型"
BRAND_ACTIVITY_START_TIME = "活动开始时间"
BRAND_ACTIVITY_END_TIME = "活动结束时间"
BRAND_BASELINE_START_DATE = "基准开始日期"
BRAND_BASELINE_END_DATE = "基准结束日期"
BRAND_ASSET_BEFORE = "活动前资产量"
BRAND_ASSET_AFTER = "活动后资产量"
BRAND_ASSET_GROWTH = "资产增量"
BRAND_NEW_CONSUMER_COUNT = "新增消费者数"
BRAND_RETURN_ON_INVESTMENT = "投入产出比"
BRAND_PRODUCT_ID = "商品ID"
BRAND_PRODUCT_SPU_ID = "SPU ID"
BRAND_PRODUCT_NAME = "商品名称"
BRAND_PRODUCT_SERIES = "系列"
BRAND_PRODUCT_CATEGORY = "类目"
BRAND_PRODUCT_LINE = "产品线"
BRAND_PRODUCT_POSITIONING = "定位"
BRAND_PRODUCT_STATUS = "商品状态"
BRAND_PRODUCT_LAUNCH_DATE = "上市日期"
BRAND_STORE_PRODUCT_ID = "店铺商品ID"
BRAND_PRODUCT_CHANNEL = "渠道"
BRAND_PRODUCT_EXPOSURE_CONSUMERS = "曝光消费者数"
BRAND_PRODUCT_INTEREST_CONSUMERS = "兴趣消费者数"
BRAND_PRODUCT_ASSET_CONSUMERS = "资产消费者数"
BRAND_PRODUCT_NEW_ASSET_CONSUMERS = "新增资产消费者数"
BRAND_PRODUCT_PURCHASE_CONSUMERS = "购买消费者数"
BRAND_PRODUCT_NEW_CUSTOMER_BUYERS = "新客购买人数"
BRAND_PRODUCT_OLD_CUSTOMER_BUYERS = "老客购买人数"
BRAND_PRODUCT_MEMBER_BUYERS = "会员购买人数"
BRAND_PRODUCT_REPURCHASE_BUYERS = "复购人数"
BRAND_PRODUCT_REPURCHASE_RATE = "复购率"
BRAND_PRODUCT_CONTRIBUTION_RATE = "品牌成交贡献占比"

BRAND_ASSET_TABLES = (
    BRAND_ASSET_OVERVIEW_TABLE,
    BRAND_ASSET_STAGE_TABLE,
    BRAND_ASSET_DIMENSION_TABLE,
    BRAND_ASSET_METRICS_TABLE,
    BRAND_ASSET_FLOW_TABLE,
    BRAND_BENCHMARK_TABLE,
    BRAND_ACTIVITY_TABLE,
    BRAND_PRODUCT_DAILY_TABLE,
    BRAND_PRODUCT_DIMENSION_TABLE,
)
UTRY_SAMPLE_TABLE = "store_daily_utry_sample_overviews"
UTRY_REPURCHASE_TABLE = "store_daily_utry_repurchase_overviews"
UTRY_PRODUCT_ID = "商品ID"
UTRY_PRODUCT_NAME = "商品标题"
UTRY_SAMPLE_DIMENSIONS = (
    UTRY_PRODUCT_ID,
    UTRY_PRODUCT_NAME,
    "叶子类目名称",
    "行业大组名称",
    "一级大类名称",
    "二级大类名称",
)
UTRY_SAMPLE_METRICS = (
    "派样单量",
    "派样人次",
    "派样GMV",
    "入仓单量",
    "入仓派样人次",
    "派样365天商家新客数",
    "派样180天商家新客数",
    "新会员数",
    "新粉丝数",
    "365叶子类目新客数",
    "180叶子类目新客数",
    "日均IPV",
    "日均IPVUV",
)
UTRY_SAMPLE_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    *UTRY_SAMPLE_DIMENSIONS,
    *UTRY_SAMPLE_METRICS,
)
UTRY_REPURCHASE_DIMENSIONS = (
    UTRY_PRODUCT_ID,
    "商品名称",
    "ju_id",
    "叶子类目",
    "行业大组",
    "一级大类",
    "二级大类",
    "是否绑定正装",
    "是否配置回购券",
    "是否配置回购礼金",
)
UTRY_REPURCHASE_METRICS = (
    "同店30日回购UV",
    "同店30日回购金额",
    "同店90日回购UV",
    "同店90日回购金额",
    "同店365日回购UV",
    "同店365日回购金额",
    "同品牌30日回购UV",
    "同品牌30日回购金额",
    "同品牌90日回购UV",
    "同品牌90日回购金额",
    "同品牌365日回购UV",
    "同品牌365日回购金额",
)
UTRY_REPURCHASE_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    *UTRY_REPURCHASE_DIMENSIONS,
    *UTRY_REPURCHASE_METRICS,
)
PROMOTION_CAMPAIGN_TABLE = "store_daily_promotion_campaigns"
PROMOTION_SCENE_NAME = "推广场景"
PROMOTION_CAMPAIGN_ID = "推广计划ID"
PROMOTION_CAMPAIGN_NAME = "推广计划名称"
PROMOTION_CAMPAIGN_METRICS = (
    "展现量",
    "点击量",
    "花费",
    "点击率",
    "平均点击花费",
    "千次展现花费",
    "总预售成交金额",
    "总预售成交笔数",
    "直接预售成交金额",
    "直接预售成交笔数",
    "间接预售成交金额",
    "间接预售成交笔数",
    "直接成交金额",
    "间接成交金额",
    "总成交金额",
    "总成交笔数",
    "直接成交笔数",
    "间接成交笔数",
    "点击转化率",
    "投入产出比",
    "总成交成本",
    "总购物车数",
    "直接购物车数",
    "间接购物车数",
    "加购率",
    "宝贝收藏数",
    "店铺收藏数",
    "店铺收藏成本",
    "总收藏加购数",
    "总收藏加购成本",
    "宝贝收藏加购数",
    "宝贝收藏加购成本",
    "总收藏数",
    "宝贝收藏成本",
    "宝贝收藏率",
    "加购成本",
    "拍下订单笔数",
    "拍下订单金额",
    "直接收藏宝贝数",
    "间接收藏宝贝数",
    "优惠券领取量",
    "购物金充值笔数",
    "购物金充值金额",
    "旺旺咨询量",
    "引导访问量",
    "引导访问人数",
    "引导访问潜客数",
    "引导访问潜客占比",
    "入会率",
    "入会量",
    "引导访问率",
    "深度访问量",
    "平均访问页面数",
    "成交新客数",
    "成交新客占比",
    "会员首购人数",
    "会员成交金额",
    "会员成交笔数",
    "成交人数",
    "人均成交笔数",
    "人均成交金额",
    "自然流量转化金额",
    "自然流量曝光量",
)
PROMOTION_CAMPAIGN_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    PROMOTION_SCENE_NAME,
    PROMOTION_CAMPAIGN_ID,
    PROMOTION_CAMPAIGN_NAME,
    *PROMOTION_CAMPAIGN_METRICS,
)
PROMOTION_CROWD_TABLE = "store_daily_promotion_crowds"
PROMOTION_ADGROUP_ID = "推广单元ID"
PROMOTION_ADGROUP_NAME = "推广单元名称"
PROMOTION_CROWD_ID = "人群ID"
PROMOTION_CROWD_NAME = "人群名称"
PROMOTION_SUBJECT_ID = "主体ID"
PROMOTION_SUBJECT_NAME = "主体名称"
PROMOTION_SUBJECT_TYPE = "主体类型"
PROMOTION_CROWD_METRICS = (
    "展现量",
    "点击量",
    "点击率",
    "花费",
    "平均点击花费",
    "旺旺咨询量",
    "直接购物车数",
    "总购物车数",
    "总收藏数",
    "加购率",
    "加购成本",
    "直接成交笔数",
    "总成交笔数",
    "直接成交金额",
    "总成交金额",
    "投入产出比",
    "总成交成本",
    "点击转化率",
    "人均成交金额",
    "入会量",
    "入会率",
    "会员首购人数",
    "会员成交金额",
    "成交新客数",
    "成交新客占比",
    "成交人数",
)
PROMOTION_CROWD_DIMENSIONS = (
    PROMOTION_SCENE_NAME,
    PROMOTION_CAMPAIGN_ID,
    PROMOTION_CAMPAIGN_NAME,
    PROMOTION_ADGROUP_ID,
    PROMOTION_ADGROUP_NAME,
    PROMOTION_CROWD_ID,
    PROMOTION_CROWD_NAME,
    PROMOTION_SUBJECT_ID,
    PROMOTION_SUBJECT_NAME,
    PROMOTION_SUBJECT_TYPE,
)
PROMOTION_CROWD_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    *PROMOTION_CROWD_DIMENSIONS,
    *PROMOTION_CROWD_METRICS,
)
PROMOTION_ADGROUP_TABLE = "store_daily_promotion_adgroups"
PROMOTION_ADGROUP_METRICS = (
    "展现量",
    "点击量",
    "花费",
    "点击率",
    "平均点击花费",
    "总成交金额",
    "总成交笔数",
    "点击转化率",
    "总购物车数",
    "宝贝收藏数",
    "店铺收藏数",
    "总收藏数",
    "宝贝收藏成本",
)
PROMOTION_ADGROUP_DIMENSIONS = (
    PROMOTION_SCENE_NAME,
    PROMOTION_CAMPAIGN_ID,
    PROMOTION_CAMPAIGN_NAME,
    PROMOTION_ADGROUP_ID,
    PROMOTION_ADGROUP_NAME,
    "商品ID",
    "商品名称",
)
PROMOTION_ADGROUP_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    *PROMOTION_ADGROUP_DIMENSIONS,
    *PROMOTION_ADGROUP_METRICS,
)
PROMOTION_BIDWORD_TABLE = "store_daily_promotion_bidwords"
PROMOTION_BIDWORD_ID = "关键词ID"
PROMOTION_BIDWORD_NAME = "关键词名称"
PROMOTION_BIDWORD_PACKAGE_ID = "关键词包ID"
PROMOTION_BIDWORD_PACKAGE_NAME = "关键词包名称"
PROMOTION_BIDWORD_TYPE = "关键词类型"
PROMOTION_AUTOMATCH_TYPE = "智能匹配类型"
PROMOTION_BIDWORD_METRICS = (
    "展现量",
    "点击量",
    "点击率",
    "花费",
    "平均点击花费",
    "旺旺咨询量",
    "直接购物车数",
    "总购物车数",
    "总收藏数",
    "加购率",
    "加购成本",
    "直接成交笔数",
    "总成交笔数",
    "直接成交金额",
    "总成交金额",
    "成交人数",
    "人均成交金额",
    "投入产出比",
    "总成交成本",
    "入会量",
    "入会率",
    "会员首购人数",
    "会员成交金额",
    "成交新客数",
    "成交新客占比",
)
PROMOTION_BIDWORD_DIMENSIONS = (
    PROMOTION_SCENE_NAME,
    PROMOTION_CAMPAIGN_ID,
    PROMOTION_CAMPAIGN_NAME,
    PROMOTION_ADGROUP_ID,
    PROMOTION_ADGROUP_NAME,
    PROMOTION_BIDWORD_ID,
    PROMOTION_BIDWORD_NAME,
    PROMOTION_BIDWORD_PACKAGE_ID,
    PROMOTION_BIDWORD_PACKAGE_NAME,
    PROMOTION_BIDWORD_TYPE,
    PROMOTION_AUTOMATCH_TYPE,
    "商品ID",
    "商品名称",
)
PROMOTION_BIDWORD_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    *PROMOTION_BIDWORD_DIMENSIONS,
    *PROMOTION_BIDWORD_METRICS,
)
PROMOTION_ITEM_TABLE = "store_daily_promotion_items"
PROMOTION_ITEM_ID = "商品ID"
PROMOTION_ITEM_NAME = "商品名称"
PROMOTION_ITEM_TYPE = "商品类型"
PROMOTION_ITEM_METRICS = (
    "展现量",
    "点击量",
    "点击率",
    "花费",
    "平均点击花费",
    "旺旺咨询量",
    "直接购物车数",
    "总购物车数",
    "总收藏数",
    "加购率",
    "加购成本",
    "直接成交笔数",
    "总成交笔数",
    "直接成交金额",
    "总成交金额",
    "点击转化率",
    "投入产出比",
    "总成交成本",
    "成交人数",
    "人均成交笔数",
    "人均成交金额",
    "入会量",
    "入会率",
    "会员首购人数",
    "会员成交笔数",
    "会员成交金额",
    "成交新客数",
    "成交新客占比",
    "自然流量转化金额",
    "自然流量曝光量",
)
PROMOTION_ITEM_DIMENSIONS = (
    PROMOTION_SCENE_NAME,
    PROMOTION_CAMPAIGN_ID,
    PROMOTION_CAMPAIGN_NAME,
    PROMOTION_ITEM_ID,
    PROMOTION_ITEM_NAME,
    PROMOTION_ITEM_TYPE,
)
PROMOTION_ITEM_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    *PROMOTION_ITEM_DIMENSIONS,
    *PROMOTION_ITEM_METRICS,
)
PROMOTION_CONTENT_TABLE = "store_daily_promotion_contents"
PROMOTION_CONTENT_ID = "内容ID"
PROMOTION_CONTENT_NAME = "内容名称"
PROMOTION_CONTENT_TYPE = "内容类型"
PROMOTION_CONTENT_METRICS = (
    "展现量",
    "点击量",
    "花费",
    "点击率",
    "平均点击花费",
    "总成交金额",
    "总成交笔数",
    "点击转化率",
    "总购物车数",
    "宝贝收藏数",
    "店铺收藏数",
    "总收藏数",
    "宝贝收藏成本",
)
PROMOTION_CONTENT_DIMENSIONS = (
    PROMOTION_SCENE_NAME,
    PROMOTION_CAMPAIGN_ID,
    PROMOTION_CAMPAIGN_NAME,
    PROMOTION_CONTENT_ID,
    PROMOTION_CONTENT_NAME,
    PROMOTION_CONTENT_TYPE,
)
PROMOTION_CONTENT_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    *PROMOTION_CONTENT_DIMENSIONS,
    *PROMOTION_CONTENT_METRICS,
)
LIVE_OVERVIEW_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    "直播成交金额",
    "千次观看成交金额",
    "店播成交金额",
    "直播观看独立访客数",
    "单小时访客数",
    "播后成交金额",
    "直播中成交金额",
    "平均每次直播的播放时长",
)
LIVE_STORE_PERFORMANCE_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    "观看人数",
    "商品点击人数",
    "观看-商品点击率",
    "成交人数",
    "点击-成交转化率",
    "成交金额",
    "客单价",
    "成交件数",
    "成交笔数",
)
LIVE_TALENT_TABLE = "store_daily_live_talent_reports"
LIVE_TALENT_ID = "合作主播ID"
LIVE_TALENT_NAME = "合作主播名称"
LIVE_TALENT_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    LIVE_TALENT_ID,
    LIVE_TALENT_NAME,
    "合作场次数",
    "商品点击人数",
    "商品点击次数",
    "商品加购人数",
    "商品加购件数",
    "成交人数",
    "成交金额",
    "成交商品数",
    "单产",
    "成交件数",
    "成交笔数",
)
CUSTOMER_SERVICE_ACCOUNT_LEGACY_ALIASES: dict[str, tuple[str, ...]] = {
    STORE_ID: (STORE_ID, "store_id"),
    BUSINESS_DAY: (BUSINESS_DAY, "business_day"),
    CUSTOMER_SERVICE_ACCOUNT_NICK: (
        CUSTOMER_SERVICE_ACCOUNT_NICK,
        "nick",
        "nickName",
        "userNick",
        "accountNick",
        "accountName",
        "psnNickName",
        "wwNick",
        "serviceNick",
        "userName",
    ),
    CUSTOMER_SERVICE_CONSULT_USERS: (
        CUSTOMER_SERVICE_CONSULT_USERS,
        "cstUv1d",
        "cstUv",
        "consultUv1d",
        "consultCnt",
        "consultUserCnt",
    ),
    CUSTOMER_SERVICE_ACCOUNT_VALID_RECEPTION_USERS: (
        CUSTOMER_SERVICE_ACCOUNT_VALID_RECEPTION_USERS,
        "validReplyUv1d",
        "validReplyUv",
        "validReplyCnt",
    ),
    CUSTOMER_SERVICE_ACCOUNT_CONSULT_ORDER_USERS: (
        CUSTOMER_SERVICE_ACCOUNT_CONSULT_ORDER_USERS,
        "cstOrdUv1d",
        "wwConsultOrdByrCnt",
        "consultOrdByrCnt",
        "finalCstUv",
    ),
    CUSTOMER_SERVICE_ACCOUNT_ORDER_USERS: (
        CUSTOMER_SERVICE_ACCOUNT_ORDER_USERS,
        "ordCrtUv1d",
        "ordUsrCnt1d",
        "ordCrtUv",
        "orderUv",
        "crtOrdByrCnt",
    ),
    CUSTOMER_SERVICE_ACCOUNT_ORDER_AMOUNT: (
        CUSTOMER_SERVICE_ACCOUNT_ORDER_AMOUNT,
        "crtAmt1d",
        "ordAmt1d",
        "crtVldAmt1d",
        "crtOrdAmt",
        "orderAmt",
        "csCrtOrdAmt",
    ),
    CUSTOMER_SERVICE_ACCOUNT_SALE_USERS: (
        CUSTOMER_SERVICE_ACCOUNT_SALE_USERS,
        "payUsrCnt1d",
        "customerServiceSaleCnt",
        "payByrCnt1d",
    ),
    CUSTOMER_SERVICE_ACCOUNT_SALE_AMOUNT: (
        CUSTOMER_SERVICE_ACCOUNT_SALE_AMOUNT,
        "payAmt1d",
        "customerServiceGmv",
    ),
    CUSTOMER_SERVICE_ACCOUNT_SALE_QUANTITY: (
        CUSTOMER_SERVICE_ACCOUNT_SALE_QUANTITY,
        "payItmCnt1d",
        "payQty1d",
        "payOrdItmQty1d",
        "saleQty1d",
    ),
    CUSTOMER_SERVICE_ACCOUNT_ORDER_COUNT: (
        CUSTOMER_SERVICE_ACCOUNT_ORDER_COUNT,
        "payOrdCnt1d",
        "payMordCnt1d",
        "payCnt1d",
        "orderCnt1d",
        "saleOrdCnt1d",
    ),
    CUSTOMER_SERVICE_ACCOUNT_SALE_AMOUNT_RATIO: (
        CUSTOMER_SERVICE_ACCOUNT_SALE_AMOUNT_RATIO,
        "proportionCss",
    ),
    CUSTOMER_SERVICE_REFUND_AMOUNT: (
        CUSTOMER_SERVICE_REFUND_AMOUNT,
        "sucRefundAmt",
        "sucRefundAmount",
        "rfdAmt1d",
        "csRfdSucAmt",
    ),
    CUSTOMER_SERVICE_NET_SALES_AMOUNT: (
        CUSTOMER_SERVICE_NET_SALES_AMOUNT,
        "netPayAmt",
        "realPayAmt1d",
        "csNetPayAmt",
    ),
}
FLOW_OVERVIEW_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    VISITORS,
    FLOW_PRODUCT_VISITORS,
    PAID_BUYERS,
    PAGE_VIEWS,
    FLOW_BOUNCE_RATE,
    FLOW_AVERAGE_PAGE_VIEWS,
    AVERAGE_STAY_TIME,
    FLOW_OLD_VISITORS,
    FLOW_NEW_VISITORS,
    FLOW_FOLLOW_STORE_BUYERS,
    FLOW_LIVE_ROOM_VISITORS,
    FLOW_SHORT_VIDEO_VISITORS,
    FLOW_IMAGE_TEXT_VISITORS,
    FLOW_SHOP_PAGE_VISITORS,
)

SIMPLE_DAILY_FACT_TABLES: dict[str, tuple[str, ...]] = {
    "store_daily_shopping_gold_overviews": SHOPPING_GOLD_COLUMNS,
    "store_daily_bybt_overviews": BYBT_COLUMNS,
    "store_daily_brand_zone_overviews": BRAND_ZONE_COLUMNS,
    "store_daily_cps_overviews": CPS_COLUMNS,
    "store_daily_taobao_flash_sale_overviews": TAOBAO_FLASH_SALE_COLUMNS,
    "store_daily_content_overviews": CONTENT_OVERVIEW_COLUMNS,
    "store_daily_taojinbi_overviews": TAOJINBI_COLUMNS,
    "store_daily_customer_service_overviews": CUSTOMER_SERVICE_OVERVIEW_COLUMNS,
    "store_daily_live_overviews": LIVE_OVERVIEW_COLUMNS,
    "store_daily_live_store_performance": LIVE_STORE_PERFORMANCE_COLUMNS,
    "store_daily_flow_overviews": FLOW_OVERVIEW_COLUMNS,
}
DIMENSION_DAILY_FACT_TABLES: dict[
    str,
    tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]],
] = {
    BYBT_ITEM_TABLE: (BYBT_ITEM_COLUMNS, BYBT_ITEM_DIMENSIONS, ("商品ID", "营销ID")),
    TAOBAO_FLASH_SALE_ITEM_TABLE: (
        TAOBAO_FLASH_SALE_ITEM_COLUMNS,
        TAOBAO_FLASH_SALE_ITEM_DIMENSIONS,
        ("商品ID", "活动ID"),
    ),
    TAOBAO_RISK_PRICE_ITEM_TABLE: (
        TAOBAO_RISK_PRICE_ITEM_COLUMNS,
        TAOBAO_RISK_PRICE_ITEM_DIMENSIONS,
        ("商品ID",),
    ),
    TAOBAO_CURRENT_PRICE_ITEM_TABLE: (
        TAOBAO_CURRENT_PRICE_ITEM_COLUMNS,
        TAOBAO_CURRENT_PRICE_ITEM_DIMENSIONS,
        ("商品ID",),
    ),
    TAOBAO_ACTIVITY_ITEM_SNAPSHOT_TABLE: (
        TAOBAO_ACTIVITY_ITEM_SNAPSHOT_COLUMNS,
        TAOBAO_ACTIVITY_ITEM_SNAPSHOT_DIMENSIONS,
        ("快照类型", "商品ID", "营销ID"),
    ),
    UTRY_SAMPLE_TABLE: (
        UTRY_SAMPLE_COLUMNS,
        UTRY_SAMPLE_DIMENSIONS,
        (UTRY_PRODUCT_ID,),
    ),
    UTRY_REPURCHASE_TABLE: (
        UTRY_REPURCHASE_COLUMNS,
        UTRY_REPURCHASE_DIMENSIONS,
        (UTRY_PRODUCT_ID,),
    ),
    PROMOTION_CAMPAIGN_TABLE: (
        PROMOTION_CAMPAIGN_COLUMNS,
        (PROMOTION_SCENE_NAME, PROMOTION_CAMPAIGN_ID, PROMOTION_CAMPAIGN_NAME),
        (PROMOTION_CAMPAIGN_ID,),
    ),
    PROMOTION_CROWD_TABLE: (
        PROMOTION_CROWD_COLUMNS,
        PROMOTION_CROWD_DIMENSIONS,
        (
            PROMOTION_CAMPAIGN_ID,
            PROMOTION_ADGROUP_ID,
            PROMOTION_CROWD_ID,
            PROMOTION_SUBJECT_ID,
        ),
    ),
    PROMOTION_ADGROUP_TABLE: (
        PROMOTION_ADGROUP_COLUMNS,
        PROMOTION_ADGROUP_DIMENSIONS,
        (PROMOTION_CAMPAIGN_ID, PROMOTION_ADGROUP_ID),
    ),
    PROMOTION_BIDWORD_TABLE: (
        PROMOTION_BIDWORD_COLUMNS,
        PROMOTION_BIDWORD_DIMENSIONS,
        (
            PROMOTION_CAMPAIGN_ID,
            PROMOTION_ADGROUP_ID,
            PROMOTION_BIDWORD_ID,
            PROMOTION_BIDWORD_PACKAGE_ID,
            PROMOTION_BIDWORD_TYPE,
            PROMOTION_AUTOMATCH_TYPE,
            "商品ID",
        ),
    ),
    PROMOTION_ITEM_TABLE: (
        PROMOTION_ITEM_COLUMNS,
        PROMOTION_ITEM_DIMENSIONS,
        (PROMOTION_CAMPAIGN_ID, PROMOTION_ITEM_ID),
    ),
    PROMOTION_CONTENT_TABLE: (
        PROMOTION_CONTENT_COLUMNS,
        PROMOTION_CONTENT_DIMENSIONS,
        (PROMOTION_CAMPAIGN_ID, PROMOTION_CONTENT_ID),
    ),
    LIVE_TALENT_TABLE: (
        LIVE_TALENT_COLUMNS,
        (LIVE_TALENT_ID, LIVE_TALENT_NAME),
        (LIVE_TALENT_ID,),
    ),
}
SIMPLE_DAILY_FACT_LEGACY_ALIASES: dict[
    str,
    dict[str, tuple[str, ...]],
] = {
    "store_daily_shopping_gold_overviews": {
        STORE_ID: (STORE_ID, "store_id"),
        BUSINESS_DAY: (BUSINESS_DAY, "business_day"),
        SHOPPING_GOLD_AVERAGE_RECHARGE_AMOUNT: (
            SHOPPING_GOLD_AVERAGE_RECHARGE_AMOUNT,
            "average_recharge_amount",
            "avgRcAmt",
        ),
        SHOPPING_GOLD_RECHARGE_AMOUNT: (
            SHOPPING_GOLD_RECHARGE_AMOUNT,
            "recharge_amount",
            "rcAmt",
        ),
        PAID_BUYERS: (PAID_BUYERS, "paid_buyers", "rcPayByrCnt"),
        SHOPPING_GOLD_RECHARGE_ITEMS: (
            SHOPPING_GOLD_RECHARGE_ITEMS,
            "recharge_items",
            "rechargeItemCnt",
        ),
        SHOPPING_GOLD_RECHARGE_REFUND_AMOUNT: (
            SHOPPING_GOLD_RECHARGE_REFUND_AMOUNT,
            "recharge_refund_amount",
            "rechargeSucRfdAmt",
        ),
        PAID_AMOUNT: (PAID_AMOUNT, "paid_amount", "rcPayAmt"),
        CUSTOMER_UNIT_PRICE: (
            CUSTOMER_UNIT_PRICE,
            "customer_unit_price",
            "rcPayOrdPbt",
        ),
        SHOPPING_GOLD_RECHARGE_CAPITAL_AMOUNT: (
            SHOPPING_GOLD_RECHARGE_CAPITAL_AMOUNT,
            "recharge_capital_amount",
            "rcCapitalAmt",
        ),
        SHOPPING_GOLD_RECHARGE_BUYERS: (
            SHOPPING_GOLD_RECHARGE_BUYERS,
            "recharge_buyers",
            "rcByrCnt",
        ),
        SHOPPING_GOLD_RECHARGE_RATE: (
            SHOPPING_GOLD_RECHARGE_RATE,
            "recharge_rate",
            "rcRate",
        ),
        FLOW_PRODUCT_VISITORS: (
            FLOW_PRODUCT_VISITORS,
            "product_visitors",
            "itmUv",
        ),
        SHOPPING_GOLD_RECHARGE_SUB_ORDER_COUNT: (
            SHOPPING_GOLD_RECHARGE_SUB_ORDER_COUNT,
            "recharge_sub_order_count",
            "rechargeOrdCnt",
        ),
    },
    "store_daily_bybt_overviews": {
        STORE_ID: (STORE_ID, "store_id"),
        BUSINESS_DAY: (BUSINESS_DAY, "business_day"),
        BYBT_VISITORS: (BYBT_VISITORS, "visitors", "bybtItemUv"),
        BYBT_PAID_BUYERS: (
            BYBT_PAID_BUYERS,
            "paid_buyers",
            "bybtPayByrCntNew",
        ),
        BYBT_ONLINE_ITEMS: (
            BYBT_ONLINE_ITEMS,
            "online_items",
            "bybtOnlineItemCnt",
        ),
        BYBT_PAID_AMOUNT: (
            BYBT_PAID_AMOUNT,
            "paid_amount",
            "bybtPayAmt",
        ),
        BYBT_PAID_SUB_ORDER_COUNT: (
            BYBT_PAID_SUB_ORDER_COUNT,
            "paid_sub_order_count",
            "bybtPayOrdCntNew",
        ),
        BYBT_PAID_ITEMS: (
            BYBT_PAID_ITEMS,
            "paid_items",
            "bybtPayOrdQty",
        ),
    },
    "store_daily_cps_overviews": {
        STORE_ID: (STORE_ID, "store_id"),
        BUSINESS_DAY: (BUSINESS_DAY, "business_day"),
        **{
            column: (column, code)
            for column, code in CPS_FIELDS
        },
    },
    "store_daily_taobao_flash_sale_overviews": {
        STORE_ID: (STORE_ID, "store_id"),
        BUSINESS_DAY: (BUSINESS_DAY, "business_day", "ds"),
        **{
            column: (column, code)
            for column, code in TAOBAO_FLASH_SALE_FIELDS
        },
    },
    "store_daily_content_overviews": {
        STORE_ID: (STORE_ID, "store_id"),
        BUSINESS_DAY: (BUSINESS_DAY, "business_day"),
        **{
            column: (column, code)
            for column, code in CONTENT_OVERVIEW_FIELDS
        },
    },
    "store_daily_taojinbi_overviews": {
        STORE_ID: (STORE_ID, "store_id"),
        BUSINESS_DAY: (BUSINESS_DAY, "business_day"),
        **{
            column: (column, code)
            for column, code in TAOJINBI_FIELDS
        },
    },
    "store_daily_customer_service_overviews": {
        STORE_ID: (STORE_ID, "store_id"),
        BUSINESS_DAY: (BUSINESS_DAY, "business_day"),
        **{
            column: (column, code)
            for column, code in CUSTOMER_SERVICE_OVERVIEW_FIELDS
        },
    },
}
CUSTOMER_SHOP_CUSTOMERS = "\u5e97\u94fa\u5ba2\u6237\u6570"
CUSTOMER_NEW_VISITOR_COUNT = "\u5ba2\u6237\u65b0\u8bbf"
CUSTOMER_NEW_VISITOR_BUYERS = "\u65b0\u8bbf\u6210\u4ea4"
CUSTOMER_NEW_VISITOR_IN_SHOP = "\u65b0\u8bbf\u672a\u6210\u4ea4"
CUSTOMER_NEW_VISITOR_PAY_RATE = "\u65b0\u8bbf\u652f\u4ed8\u8f6c\u5316\u7387"
CUSTOMER_NEW_VISITOR_PAY_AMOUNT_RATIO = "\u65b0\u8bbf\u652f\u4ed8\u91d1\u989d\u5360\u6bd4"
CUSTOMER_NEW_VISITOR_UNIT_PRICE = "\u65b0\u8bbf\u5ba2\u5355\u4ef7"
CUSTOMER_NEW_VISITOR_FANS_RATE = "\u65b0\u8bbf\u7c89\u4e1d\u5360\u6bd4"
CUSTOMER_NEW_VISITOR_VIP_RATE = "\u65b0\u8bbf\u4f1a\u5458\u5360\u6bd4"
CUSTOMER_NEW_VISITOR_RECALL_RATE = "\u65b0\u8bbf\u6f5c\u5ba2\u53ec\u56de\u7387"
CUSTOMER_NO_PURCHASE_COUNT = "\u672a\u8d2d\u5ba2\u6237\u56de\u8bbf"
CUSTOMER_NO_PURCHASE_BUYERS = "\u56de\u8bbf\u6210\u4ea4"
CUSTOMER_NO_BUY_IN_SHOP = "\u56de\u8bbf\u672a\u6210\u4ea4"
CUSTOMER_NO_PURCHASE_PAY_RATE = "\u672a\u8d2d\u56de\u8bbf\u652f\u4ed8\u8f6c\u5316\u7387"
CUSTOMER_NO_PURCHASE_PAY_AMOUNT_RATIO = "\u672a\u8d2d\u56de\u8bbf\u652f\u4ed8\u91d1\u989d\u5360\u6bd4"
CUSTOMER_NO_PURCHASE_UNIT_PRICE = "\u672a\u8d2d\u56de\u8bbf\u5ba2\u5355\u4ef7"
CUSTOMER_NO_PURCHASE_FANS_RATE = "\u672a\u8d2d\u56de\u8bbf\u7c89\u4e1d\u5360\u6bd4"
CUSTOMER_NO_PURCHASE_VIP_RATE = "\u672a\u8d2d\u56de\u8bbf\u4f1a\u5458\u5360\u6bd4"
CUSTOMER_NO_PURCHASE_RECALL_RATE = "\u672a\u8d2d\u5ba2\u6237\u53ec\u56de\u7387"
CUSTOMER_NO_PURCHASE_BUY_RATE = "\u672a\u8d2d\u56de\u8bbf\u6210\u4ea4\u7387"
CUSTOMER_HAS_PURCHASE_COUNT = "\u5df2\u8d2d\u5ba2\u6237\u56de\u8bbf"
CUSTOMER_HAS_PURCHASE_REPEAT_BUYERS = "\u8001\u5ba2\u590d\u8d2d"
CUSTOMER_HAS_PURCHASE_NO_REPEAT = "\u8001\u5ba2\u672a\u590d\u8d2d"
CUSTOMER_HAS_PURCHASE_PAY_RATE = "\u5df2\u8d2d\u56de\u8bbf\u652f\u4ed8\u8f6c\u5316\u7387"
CUSTOMER_HAS_PURCHASE_PAY_AMOUNT_RATIO = "\u5df2\u8d2d\u56de\u8bbf\u652f\u4ed8\u91d1\u989d\u5360\u6bd4"
CUSTOMER_HAS_PURCHASE_UNIT_PRICE = "\u8001\u5ba2\u590d\u8d2d\u5ba2\u5355\u4ef7"
CUSTOMER_HAS_PURCHASE_FANS_RATE = "\u5df2\u8d2d\u56de\u8bbf\u7c89\u4e1d\u5360\u6bd4"
CUSTOMER_HAS_PURCHASE_VIP_RATE = "\u5df2\u8d2d\u56de\u8bbf\u4f1a\u5458\u5360\u6bd4"
CUSTOMER_HAS_PURCHASE_RECALL_RATE = "\u5df2\u8d2d\u5ba2\u6237\u53ec\u56de\u7387"
CUSTOMER_HAS_PURCHASE_REPEAT_RATE = "\u8001\u5ba2\u590d\u8d2d\u7387"
CUSTOMER_OVERVIEW_ARTIFACT_ID = "\u5ba2\u6237\u6982\u51b5\u8bc1\u636eID"
CUSTOMER_OVERVIEW_FIELDS = (
    (CUSTOMER_SHOP_CUSTOMERS, "customer.shopCustomer"),
    (CUSTOMER_NEW_VISITOR_COUNT, "customer.newVisitorCnt"),
    (CUSTOMER_NEW_VISITOR_BUYERS, "customer.newVisitorBuyCnt"),
    (CUSTOMER_NEW_VISITOR_IN_SHOP, "customer.newVisitorInShopCnt"),
    (CUSTOMER_NEW_VISITOR_PAY_RATE, "customer.newVisitorPayRate"),
    (CUSTOMER_NEW_VISITOR_PAY_AMOUNT_RATIO, "customer.newVisitorPayAmtRatio"),
    (CUSTOMER_NEW_VISITOR_UNIT_PRICE, "customer.newVisitorPct"),
    (CUSTOMER_NEW_VISITOR_FANS_RATE, "customer.newVisitorFansRate"),
    (CUSTOMER_NEW_VISITOR_VIP_RATE, "customer.newVisitorVipRate"),
    (CUSTOMER_NEW_VISITOR_RECALL_RATE, "customer.newVisitorReCall"),
    (CUSTOMER_NO_PURCHASE_COUNT, "customer.noPurchaseCnt"),
    (CUSTOMER_NO_PURCHASE_BUYERS, "customer.noPurchaseBuyCnt"),
    (CUSTOMER_NO_BUY_IN_SHOP, "customer.noBuyInShopCnt"),
    (CUSTOMER_NO_PURCHASE_PAY_RATE, "customer.noPurchasePayRate"),
    (CUSTOMER_NO_PURCHASE_PAY_AMOUNT_RATIO, "customer.noPurchasePayAmtRatio"),
    (CUSTOMER_NO_PURCHASE_UNIT_PRICE, "customer.noPurchasePct"),
    (CUSTOMER_NO_PURCHASE_FANS_RATE, "customer.noPurchaseFansRate"),
    (CUSTOMER_NO_PURCHASE_VIP_RATE, "customer.noPurchaseVipRate"),
    (CUSTOMER_NO_PURCHASE_RECALL_RATE, "customer.noPurchaseReCall"),
    (CUSTOMER_NO_PURCHASE_BUY_RATE, "customer.noPurchaseBuyCntRate"),
    (CUSTOMER_HAS_PURCHASE_COUNT, "customer.hasPurchaseCnt"),
    (CUSTOMER_HAS_PURCHASE_REPEAT_BUYERS, "customer.hasPurchaseUbyCnt"),
    (CUSTOMER_HAS_PURCHASE_NO_REPEAT, "customer.hasBuyInShopCnt"),
    (CUSTOMER_HAS_PURCHASE_PAY_RATE, "customer.hasPurchasePayRate"),
    (CUSTOMER_HAS_PURCHASE_PAY_AMOUNT_RATIO, "customer.hasPurchasePayAmtRatio"),
    (CUSTOMER_HAS_PURCHASE_UNIT_PRICE, "customer.hasPurchasePct"),
    (CUSTOMER_HAS_PURCHASE_FANS_RATE, "customer.hasPurchaseFansRate"),
    (CUSTOMER_HAS_PURCHASE_VIP_RATE, "customer.hasPurchaseVipRate"),
    (CUSTOMER_HAS_PURCHASE_RECALL_RATE, "customer.hasPurchaseReCall"),
    (CUSTOMER_HAS_PURCHASE_REPEAT_RATE, "customer.hasPurchaseUbyCntRate"),
)
MEMBER_TOTAL_COUNT = "\u4f1a\u5458\u603b\u6570"
MEMBER_PAID_COUNT = "\u4f1a\u5458\u6210\u4ea4\u4eba\u6570"
MEMBER_PAID_AMOUNT = "\u4f1a\u5458\u6210\u4ea4\u91d1\u989d"
MEMBER_UNIT_PRICE = "\u4f1a\u5458\u5ba2\u5355\u4ef7"
MEMBER_REPURCHASE_RATE = "\u4f1a\u5458\u590d\u8d2d\u7387"
MEMBER_CORE_REPURCHASE_RATE = "\u4f1a\u5458\u590d\u8d2d\u7387"
LEGACY_MEMBER_CORE_REPURCHASE_RATE = "\u6838\u5fc3\u4f1a\u5458\u590d\u8d2d\u7387"
MEMBER_HIGH_FREQ_COUNT = "\u9ad8\u9891\u590d\u8d2d\u4f1a\u5458"
MEMBER_HIGH_FREQ_AMOUNT_RATE = "\u9ad8\u9891\u590d\u8d2d\u6210\u4ea4\u91d1\u989d\u5360\u6bd4"
MEMBER_HIGH_FREQ_OWN_RATIO = "\u9ad8\u9891\u590d\u8d2d\u672c\u5e97\u5360\u6bd4"
MEMBER_HIGH_FREQ_BENCHMARK_RATIO = "\u9ad8\u9891\u590d\u8d2d\u540c\u884c\u5360\u6bd4"
MEMBER_TWO_ORDER_COUNT = "2\u5355\u590d\u8d2d\u4f1a\u5458"
MEMBER_TWO_ORDER_AMOUNT_RATE = "2\u5355\u590d\u8d2d\u6210\u4ea4\u91d1\u989d\u5360\u6bd4"
MEMBER_TWO_ORDER_OWN_RATIO = "2\u5355\u590d\u8d2d\u672c\u5e97\u5360\u6bd4"
MEMBER_TWO_ORDER_BENCHMARK_RATIO = "2\u5355\u590d\u8d2d\u540c\u884c\u5360\u6bd4"
MEMBER_FIRST_TIME_COUNT = "\u9996\u8d2d\u4f1a\u5458"
MEMBER_FIRST_TIME_AMOUNT_RATE = "\u9996\u8d2d\u6210\u4ea4\u91d1\u989d\u5360\u6bd4"
MEMBER_FIRST_TIME_OWN_RATIO = "\u9996\u8d2d\u672c\u5e97\u5360\u6bd4"
MEMBER_FIRST_TIME_BENCHMARK_RATIO = "\u9996\u8d2d\u540c\u884c\u5360\u6bd4"
MEMBER_ACTIVE_NON_BUYER_COUNT = "\u6d3b\u8dc3\u672a\u8d2d\u4f1a\u5458"
MEMBER_ACTIVE_NON_BUYER_OWN_RATIO = "\u6d3b\u8dc3\u672a\u8d2d\u672c\u5e97\u5360\u6bd4"
MEMBER_ACTIVE_NON_BUYER_BENCHMARK_RATIO = "\u6d3b\u8dc3\u672a\u8d2d\u540c\u884c\u5360\u6bd4"
MEMBER_INACTIVE_COUNT = "\u6c89\u9ed8\u4f1a\u5458"
MEMBER_INACTIVE_OWN_RATIO = "\u6c89\u9ed8\u4f1a\u5458\u672c\u5e97\u5360\u6bd4"
MEMBER_INACTIVE_BENCHMARK_RATIO = "\u6c89\u9ed8\u4f1a\u5458\u540c\u884c\u5360\u6bd4"
MEMBER_REPURCHASE_COUNT = "\u590d\u8d2d\u4f1a\u5458\u6570"
MEMBER_REPURCHASE_AMOUNT = "\u4f1a\u5458\u590d\u8d2d\u91d1\u989d"
MEMBER_REPURCHASE_ORDER_COUNT = "\u590d\u8d2d\u8ba2\u5355\u6570"
MEMBER_REPURCHASE_UNIT_PRICE = "\u590d\u8d2d\u4f1a\u5458\u5ba2\u5355\u4ef7"
MEMBER_REPURCHASE_CYCLE = "\u590d\u8d2d\u5468\u671f"
MEMBER_REPURCHASE_PAGE_RATE = "\u590d\u8d2d\u9875\u4f1a\u5458\u590d\u8d2d\u7387"
MEMBER_REPURCHASE_FREQUENCY = "\u4eba\u5747\u590d\u8d2d\u7b14\u6570"
MEMBER_NEW_COUNT = "\u65b0\u589e\u4f1a\u5458\u6570"
MEMBER_NEW_PAID_COUNT = "\u65b0\u4f1a\u5458\u6210\u4ea4\u4eba\u6570"
MEMBER_RECRUIT_CONVERSION_RATE = "\u62db\u52df\u8f6c\u5316\u7387"
MEMBER_NEW_PAID_AMOUNT = "\u65b0\u4f1a\u5458\u6210\u4ea4\u91d1\u989d"
MEMBER_NEW_UNIT_PRICE = "\u65b0\u4f1a\u5458\u5ba2\u5355\u4ef7"
MEMBER_OLD_NEW_COUNT = "\u8001\u5ba2\u5165\u4f1a\u4eba\u6570"
MEMBER_CORE_ARTIFACT_ID = "\u6838\u5fc3\u6307\u6807\u8bc1\u636eID"
MEMBER_ASSET_ARTIFACT_ID = "\u8d44\u4ea7\u5206\u5e03\u8bc1\u636eID"
MEMBER_REPURCHASE_ARTIFACT_ID = "\u4f1a\u5458\u590d\u8d2d\u8bc1\u636eID"
MEMBER_ACQUISITION_ARTIFACT_ID = "\u4f1a\u5458\u62c9\u65b0\u8bc1\u636eID"
MEMBER_ANALYSIS_ARTIFACT_COLUMNS = (
    (MEMBER_CORE_ARTIFACT_ID, "member.core."),
    (MEMBER_ASSET_ARTIFACT_ID, "member.asset."),
    (MEMBER_REPURCHASE_ARTIFACT_ID, "member.repurchase."),
    (MEMBER_ACQUISITION_ARTIFACT_ID, "member.acquisition."),
)
MEMBER_ANALYSIS_OVERVIEW_FIELDS = (
    (MEMBER_TOTAL_COUNT, "member.core.totalMbrCnt"),
    (MEMBER_PAID_COUNT, "member.core.paidMbrCnt"),
    (MEMBER_PAID_AMOUNT, "member.core.mbrPayAmt"),
    (MEMBER_UNIT_PRICE, "member.core.mbrUnitPrice"),
    (MEMBER_CORE_REPURCHASE_RATE, "member.core.repurMbrRate"),
    (MEMBER_HIGH_FREQ_COUNT, "member.asset.highFreqBuyerMemberAssets"),
    (MEMBER_HIGH_FREQ_AMOUNT_RATE, "member.asset.highFreqBuyerMemberPayAmtRate"),
    (MEMBER_HIGH_FREQ_OWN_RATIO, "member.asset.highFreqBuyerMemberAssetsPortion"),
    (MEMBER_HIGH_FREQ_BENCHMARK_RATIO, "member.asset.highFreqBuyerMemberAssetsRatio"),
    (MEMBER_TWO_ORDER_COUNT, "member.asset.twoOrderBuyerMemberAssets"),
    (MEMBER_TWO_ORDER_AMOUNT_RATE, "member.asset.twoOrderBuyerMemberPayAmtRate"),
    (MEMBER_TWO_ORDER_OWN_RATIO, "member.asset.twoOrderBuyerMemberAssetsPortion"),
    (MEMBER_TWO_ORDER_BENCHMARK_RATIO, "member.asset.twoOrderBuyerMemberAssetsRatio"),
    (MEMBER_FIRST_TIME_COUNT, "member.asset.firstTimeBuyerMemberAssets"),
    (MEMBER_FIRST_TIME_AMOUNT_RATE, "member.asset.firstTimeBuyerMemberPayAmtRate"),
    (MEMBER_FIRST_TIME_OWN_RATIO, "member.asset.firstTimeBuyerMemberAssetsPortion"),
    (MEMBER_FIRST_TIME_BENCHMARK_RATIO, "member.asset.firstTimeBuyerMemberLyrAssetsRatio"),
    (MEMBER_ACTIVE_NON_BUYER_COUNT, "member.asset.activeNonBuyerMemberAssets"),
    (MEMBER_ACTIVE_NON_BUYER_OWN_RATIO, "member.asset.activeNonBuyerMemberAssetsPortion"),
    (MEMBER_ACTIVE_NON_BUYER_BENCHMARK_RATIO, "member.asset.activeNonBuyerMemberLyrAssetsRatio"),
    (MEMBER_INACTIVE_COUNT, "member.asset.inactiveMemberAssets"),
    (MEMBER_INACTIVE_OWN_RATIO, "member.asset.inactiveMemberAssetsPortion"),
    (MEMBER_INACTIVE_BENCHMARK_RATIO, "member.asset.inactiveMemberLyrAssetsRatio"),
    (MEMBER_REPURCHASE_COUNT, "member.repurchase.repurMbrCnt"),
    (MEMBER_REPURCHASE_AMOUNT, "member.repurchase.repurPayAmt"),
    (MEMBER_REPURCHASE_ORDER_COUNT, "member.repurchase.repurOrdCnt"),
    (MEMBER_REPURCHASE_UNIT_PRICE, "member.repurchase.repurUnitPrice"),
    (MEMBER_REPURCHASE_CYCLE, "member.repurchase.repurCycle"),
    (MEMBER_REPURCHASE_PAGE_RATE, "member.repurchase.repurMbrRate"),
    (MEMBER_REPURCHASE_FREQUENCY, "member.repurchase.repurFrequency"),
    (MEMBER_NEW_COUNT, "member.acquisition.incrMbrCnt"),
    (MEMBER_NEW_PAID_COUNT, "member.acquisition.incrPaidMbrCnt"),
    (MEMBER_RECRUIT_CONVERSION_RATE, "member.acquisition.recConvertRate"),
    (MEMBER_NEW_PAID_AMOUNT, "member.acquisition.incrPayOrdAmt"),
    (MEMBER_NEW_UNIT_PRICE, "member.acquisition.incrUnitPrice"),
    (MEMBER_OLD_NEW_COUNT, "member.acquisition.oldNewMemberCount"),
)
DAILY_OVERVIEW_FIELDS = (
    (PAID_AMOUNT, "payAmt"),
    (NET_PAID_AMOUNT, "netPaymentAmount"),
    (VISITORS, "uv"),
    (PAID_BUYERS, "payByrCnt"),
    (CONVERSION_RATE, "payRate"),
    (SIGN_REFUND_RATE, "realPayrealRfdRate"),
    (REFUND_FINISHED_AMOUNT, "rfdSucAmt"),
    (KEYWORD_PROMOTION_SPEND, "p4pExpendAmt"),
    (PRECISION_AUDIENCE_PROMOTION_SPEND, "cubeAmt"),
    (SMART_SCENE_SPEND, "feedCharge"),
    (ALL_SITE_PROMOTION_SPEND, "admCostFamtQzt"),
    (TAOKE_COMMISSION, "tkExpendAmt"),
    (TOTAL_PAID_AMOUNT, "subPayOrdAmt"),
    (REFUND_PAID_TIME_AMOUNT, "payShopRfdAmt"),
    (AMOUNT_REFUND_RATE, "payAmtRfdRate"),
    (ADD_CART_BUYERS, "cartByrCnt"),
    (PRODUCT_FAVORITE_BUYERS, "cltItmCnt"),
    (PAGE_VIEWS, "pv"),
    (AVERAGE_STAY_TIME, "stayTime"),
    (ADD_CART_ITEMS, "cartItemCnt"),
    (PAID_SUB_ORDER_COUNT, "payOrdCnt"),
    (TOTAL_PAID_SUB_ORDER_COUNT, "subPayOrdSubCnt"),
    (ORDER_REFUND_RATE, "ordRfdRate"),
    (PAID_ITEMS, "payItmCnt"),
    (CUSTOMER_UNIT_PRICE, "payPct"),
    (OLDER_PAID_AMOUNT, "olderPayAmt"),
    (OLDER_PAID_BUYERS, "payOldByrCnt"),
    (OLDER_REPURCHASE_RATE, "hasPurchaseUbyCntRate"),
    (REFUND_PROCESS_DAYS, "rfdFinshDur"),
    (WANGWANG_MANUAL_RESPONSE_SECONDS, "wwReplyManualAvgTimeLen"),
    (CONSULTATION_RATE, "consultRate"),
    (PLATFORM_DUTY_RATE, "disputeDutyRatio"),
    (PICKUP_24H_RATE, "gotInTime24hRate"),
    (LOGISTICS_ARRIVAL_HOURS, "avgSignTimeHh"),
)
DAILY_OVERVIEW_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    *[column for column, _ in DAILY_OVERVIEW_FIELDS],
)
CHANNEL_ORDER = "\u6e20\u9053\u987a\u5e8f"
MEMBER_CHANNEL_NAME = "\u5165\u4f1a\u6e20\u9053"
MEMBER_CHANNEL_LINK = "\u6e20\u9053\u94fe\u63a5"
METRIC_SCOPE = "\u6307\u6807\u8303\u56f4"
METRIC_CODE = "\u6307\u6807\u7f16\u7801"
METRIC_VALUE = "\u6307\u6807\u6570\u503c"
STORE_DAILY_METRIC_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    METRIC_SCOPE,
    METRIC_CODE,
    METRIC_VALUE,
)
RAW_VALUE_JSON = "\u539f\u59cb\u503cJSON"
METRIC_NAME = "\u6307\u6807\u540d\u79f0"
METRIC_GROUP = "\u6307\u6807\u5206\u7c7b"
UNIT = "\u5355\u4f4d"
DESCRIPTION = "\u8bf4\u660e"
CONFIRMATION_STATUS = "\u786e\u8ba4\u72b6\u6001"
RUN_ID = "\u8fd0\u884cID"
IDEMPOTENCY_KEY = "\u5e42\u7b49\u952e"
RUN_MODE = "\u8fd0\u884c\u6a21\u5f0f"
RUN_STATUS = "\u8fd0\u884c\u72b6\u6001"
SOURCE_SCRIPT = "\u6765\u6e90\u811a\u672c"
SOURCE_ORDER = "\u6765\u6e90\u987a\u5e8f"
SOURCE_LEVEL = "\u6765\u6e90\u5c42\u7ea7"
SOURCE_PATH = "\u6765\u6e90\u8def\u5f84"
TRAFFIC_SOURCE_LEVEL_1 = "\u4e00\u7ea7\u6765\u6e90"
TRAFFIC_SOURCE_LEVEL_2 = "\u4e8c\u7ea7\u6765\u6e90"
TRAFFIC_SOURCE_LEVEL_3 = "\u4e09\u7ea7\u6765\u6e90"
NEW_VISITORS = "\u65b0\u8bbf\u5ba2\u6570"
PAID_AMOUNT_SHARE = "\u652f\u4ed8\u91d1\u989d\u5360\u6bd4"
UV_VALUE = "UV\u4ef7\u503c"
ORDER_BUYERS = "\u4e0b\u5355\u4e70\u5bb6\u6570"
ORDER_AMOUNT = "\u4e0b\u5355\u91d1\u989d"
ORDER_CONVERSION_RATE = "\u4e0b\u5355\u8f6c\u5316\u7387"
ACTIVITY_ID = "\u6d3b\u52a8ID"
ACTIVITY_NAME = "\u6d3b\u52a8\u540d\u79f0"
ACTIVITY_TYPE = "\u6d3b\u52a8\u7c7b\u578b"
ACTIVITY_STATUS = "\u6d3b\u52a8\u72b6\u6001"
ACTIVITY_START_TIME = "\u6d3b\u52a8\u5f00\u59cb\u65f6\u95f4"
ACTIVITY_END_TIME = "\u6d3b\u52a8\u7ed3\u675f\u65f6\u95f4"
SIGNUP_START_TIME = "\u62a5\u540d\u5f00\u59cb\u65f6\u95f4"
SIGNUP_END_TIME = "\u62a5\u540d\u7ed3\u675f\u65f6\u95f4"
ACTIVITY_TAG = "\u6d3b\u52a8\u6807\u7b7e"
ACTIVITY_LEVEL = "\u6d3b\u52a8\u5c42\u7ea7"
ACTIVITY_STAGE = "\u6d3b\u52a8\u9636\u6bb5"
SHOP_PARTICIPATION_STATUS = "\u5e97\u94fa\u53c2\u4e0e\u72b6\u6001"
ACTIVITY_CALENDAR_COLUMNS = (
    STORE_ID,
    BUSINESS_DAY,
    ACTIVITY_ID,
    ACTIVITY_NAME,
    ACTIVITY_TYPE,
    ACTIVITY_STATUS,
    ACTIVITY_START_TIME,
    ACTIVITY_END_TIME,
    SIGNUP_START_TIME,
    SIGNUP_END_TIME,
    ACTIVITY_TAG,
    ACTIVITY_LEVEL,
    ACTIVITY_STAGE,
    SHOP_PARTICIPATION_STATUS,
)

# A daily fact table always starts with store and business day. The remaining
# columns make maintenance rebuilds deterministic for tables with several rows
# per day. Application queries must still use an explicit ORDER BY.
DAILY_FACT_TABLE_SORT_COLUMNS: dict[str, tuple[str, ...]] = {
    "store_daily_overviews": (),
    "store_daily_customer_overviews": (),
    "store_daily_traffic_sources": (
        SOURCE_LEVEL,
        TRAFFIC_SOURCE_LEVEL_1,
        TRAFFIC_SOURCE_LEVEL_2,
        TRAFFIC_SOURCE_LEVEL_3,
    ),
    "store_daily_member_channels": (MEMBER_CHANNEL_NAME,),
    "store_daily_member_analysis_overviews": (),
    "store_activity_calendar_events": (ACTIVITY_ID,),
    "store_daily_new_customer_discount_overviews": (),
    "store_daily_customer_service_accounts": (CUSTOMER_SERVICE_ACCOUNT_NICK,),
    PRODUCT_RANKING_TABLE: (PRODUCT_RANKING_ITEM_ID,),
    UTRY_SAMPLE_TABLE: (UTRY_PRODUCT_ID,),
    UTRY_REPURCHASE_TABLE: (UTRY_PRODUCT_ID,),
    PROMOTION_CAMPAIGN_TABLE: (PROMOTION_CAMPAIGN_ID,),
    PROMOTION_CROWD_TABLE: (
        PROMOTION_CAMPAIGN_ID,
        PROMOTION_ADGROUP_ID,
        PROMOTION_CROWD_ID,
        PROMOTION_SUBJECT_ID,
    ),
    PROMOTION_ADGROUP_TABLE: (PROMOTION_CAMPAIGN_ID, PROMOTION_ADGROUP_ID),
    PROMOTION_BIDWORD_TABLE: (
        PROMOTION_CAMPAIGN_ID,
        PROMOTION_ADGROUP_ID,
        PROMOTION_BIDWORD_ID,
        PROMOTION_BIDWORD_PACKAGE_ID,
        PROMOTION_BIDWORD_TYPE,
        PROMOTION_AUTOMATCH_TYPE,
        "商品ID",
    ),
    PROMOTION_ITEM_TABLE: (PROMOTION_CAMPAIGN_ID, PROMOTION_ITEM_ID),
    PROMOTION_CONTENT_TABLE: (PROMOTION_CAMPAIGN_ID, PROMOTION_CONTENT_ID),
    LIVE_TALENT_TABLE: (LIVE_TALENT_ID,),
    **{table: () for table in SIMPLE_DAILY_FACT_TABLES},
}
GENERATED_AT = "\u751f\u6210\u65f6\u95f4"
SELECTED_COUNT = "\u9009\u4e2d\u6570\u91cf"
DEFERRED_COUNT = "\u5ef6\u540e\u6570\u91cf"
GUARDRAILS_JSON = "\u5b89\u5168\u89c4\u5219JSON"
ITEM_ID = "\u6761\u76eeID"
ITEM_ORDER = "\u6761\u76ee\u987a\u5e8f"
FUNCTION_NAME = "\u51fd\u6570\u540d\u79f0"
PRIORITY = "\u4f18\u5148\u7ea7"
LEGACY_PATH = "\u65e7\u63a5\u53e3\u8def\u5f84"
REQUEST_METHOD = "\u8bf7\u6c42\u65b9\u6cd5"
REQUEST_URL = "\u8bf7\u6c42\u5730\u5740"
TARGET_TABLE = "\u76ee\u6807\u8868"
DATE_MODE = "\u65e5\u671f\u6a21\u5f0f"
SHAPE_STATUS = "\u54cd\u5e94\u5f62\u72b6\u72b6\u6001"
RUNTIME_CREDENTIALS_JSON = "\u8fd0\u884c\u65f6\u51ed\u8bc1JSON"
QUERY_PARAMS_JSON = "\u67e5\u8be2\u53c2\u6570JSON"
BODY_TEMPLATE_JSON = "\u8bf7\u6c42\u4f53JSON"
ITEM_STATUS = "\u6761\u76ee\u72b6\u6001"
RISK_NOTES_JSON = "\u98ce\u9669\u63d0\u793aJSON"
CRAWL_RUN_ID = "\u91c7\u96c6\u4efb\u52a1ID"
CRAWL_TASK_TYPE = "\u4efb\u52a1\u7c7b\u578b"
START_DAY = "\u5f00\u59cb\u65e5\u671f"
END_DAY = "\u7ed3\u675f\u65e5\u671f"
PLANNED_DAYS = "\u8ba1\u5212\u5929\u6570"
SUCCESS_DAYS = "\u6210\u529f\u5929\u6570"
SKIPPED_DAYS = "\u8df3\u8fc7\u5929\u6570"
FAILED_DAYS = "\u5931\u8d25\u5929\u6570"
STARTED_AT = "\u5f00\u59cb\u65f6\u95f4"
FINISHED_AT = "\u7ed3\u675f\u65f6\u95f4"
LOG_FILE = "\u65e5\u5fd7\u6587\u4ef6"
ITEM_DAY_ID = "\u65e5\u671f\u6761\u76eeID"
DAY_STATUS = "\u65e5\u671f\u72b6\u6001"
ERROR_MESSAGE = "\u9519\u8bef\u4fe1\u606f"
METRIC_COUNT = "\u6307\u6807\u6570\u91cf"


def q(name: str) -> str:
    return f'"{name}"'


def _daily_overview_create_sql(if_not_exists: bool) -> str:
    existence_clause = "if not exists " if if_not_exists else ""
    metric_columns = ",\n                ".join(
        f"{q(column)} text" for column, _ in DAILY_OVERVIEW_FIELDS
    )
    return f"""
            create table {existence_clause}store_daily_overviews (
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
                {q(BUSINESS_DAY)} text not null,
                {metric_columns},
                primary key({q(STORE_ID)}, {q(BUSINESS_DAY)})
            )
            """


def _activity_calendar_create_sql(if_not_exists: bool) -> str:
    existence_clause = "if not exists " if if_not_exists else ""
    metric_columns = ",\n                ".join(
        f"{q(column)} text not null" for column in ACTIVITY_CALENDAR_COLUMNS[2:]
    )
    return f"""
            create table {existence_clause}store_activity_calendar_events (
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
                {q(BUSINESS_DAY)} text not null,
                {metric_columns},
                primary key({q(STORE_ID)}, {q(BUSINESS_DAY)}, {q(ACTIVITY_ID)})
            )
            """


def _new_customer_discount_create_sql(if_not_exists: bool) -> str:
    existence_clause = "if not exists " if if_not_exists else ""
    metric_columns = ",\n                ".join(
        f"{q(column)} text" for column in NEW_CUSTOMER_DISCOUNT_COLUMNS[2:]
    )
    return f"""
            create table {existence_clause}store_daily_new_customer_discount_overviews (
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
                {q(BUSINESS_DAY)} text not null,
                {metric_columns},
                primary key({q(STORE_ID)}, {q(BUSINESS_DAY)})
            )
            """


def _simple_daily_fact_create_sql(
    table: str,
    columns: tuple[str, ...],
    if_not_exists: bool,
) -> str:
    existence_clause = "if not exists " if if_not_exists else ""
    metric_columns = ",\n                ".join(
        f"{q(column)} text" for column in columns[2:]
    )
    return f"""
            create table {existence_clause}{table} (
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
                {q(BUSINESS_DAY)} text not null,
                {metric_columns},
                primary key({q(STORE_ID)}, {q(BUSINESS_DAY)})
            )
    """


def _dimension_daily_fact_create_sql(
    table: str,
    columns: tuple[str, ...],
    dimensions: tuple[str, ...],
    key_dimensions: tuple[str, ...],
    if_not_exists: bool,
) -> str:
    existence_clause = "if not exists " if if_not_exists else ""
    dimension_columns = ",\n                ".join(
        f"{q(column)} text not null" for column in dimensions
    )
    metric_columns = ",\n                ".join(
        f"{q(column)} text" for column in columns[2 + len(dimensions) :]
    )
    primary_key_columns = ", ".join(
        q(column) for column in (STORE_ID, BUSINESS_DAY, *key_dimensions)
    )
    return f"""
            create table {existence_clause}{table} (
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
                {q(BUSINESS_DAY)} text not null,
                {dimension_columns},
                {metric_columns},
                primary key({primary_key_columns})
            )
            """


def _product_ranking_create_sql(if_not_exists: bool) -> str:
    existence_clause = "if not exists " if if_not_exists else ""
    metric_columns = ",\n                ".join(
        f"{q(column)} text" for column in PRODUCT_RANKING_COLUMNS[2:]
    )
    return f"""
            create table {existence_clause}{PRODUCT_RANKING_TABLE} (
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
                {q(BUSINESS_DAY)} text not null,
                {metric_columns},
                primary key(
                    {q(STORE_ID)}, {q(BUSINESS_DAY)}, {q(PRODUCT_RANKING_ITEM_ID)}
                )
            )
            """


def _product_catalog_create_sql(if_not_exists: bool) -> str:
    existence_clause = "if not exists " if if_not_exists else ""
    return f"""
            create table {existence_clause}{PRODUCT_CATALOG_TABLE} (
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
                {q("商品ID")} text not null,
                {q("商品名称")} text,
                {q("类型")} text,
                {q("属性")} text,
                {q("系列")} text,
                {q("定位")} text,
                {q("渠道")} text,
                primary key({q(STORE_ID)}, {q("商品ID")})
            )
            """


def _customer_service_accounts_create_sql(if_not_exists: bool) -> str:
    existence_clause = "if not exists " if if_not_exists else ""
    metric_columns = ",\n                ".join(
        f"{q(column)} text" for column in CUSTOMER_SERVICE_ACCOUNT_COLUMNS[3:]
    )
    return f"""
            create table {existence_clause}store_daily_customer_service_accounts (
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
                {q(BUSINESS_DAY)} text not null,
                {q(CUSTOMER_SERVICE_ACCOUNT_NICK)} text not null,
                {metric_columns},
                primary key(
                    {q(STORE_ID)},
                    {q(BUSINESS_DAY)},
                    {q(CUSTOMER_SERVICE_ACCOUNT_NICK)}
                )
            )
            """


DAILY_OVERVIEW_LEGACY_ALIASES: dict[str, tuple[str, ...]] = {
    STORE_ID: (STORE_ID, "store_id"),
    BUSINESS_DAY: (BUSINESS_DAY, "business_day"),
    PAID_AMOUNT: (PAID_AMOUNT, "paid_amount"),
    NET_PAID_AMOUNT: (NET_PAID_AMOUNT, "net_paid_amount"),
    VISITORS: (VISITORS, "visitors"),
    PAID_BUYERS: (PAID_BUYERS, BUYERS, "paid_buyers", "buyers"),
    CONVERSION_RATE: (CONVERSION_RATE, "conversion_rate"),
    SIGN_REFUND_RATE: (SIGN_REFUND_RATE, "sign_refund_rate"),
    REFUND_FINISHED_AMOUNT: (REFUND_FINISHED_AMOUNT, "refund_finished_amount"),
    KEYWORD_PROMOTION_SPEND: (
        KEYWORD_PROMOTION_SPEND,
        P4P_SPEND,
        "keyword_promotion_spend",
        "p4p_spend",
    ),
    PRECISION_AUDIENCE_PROMOTION_SPEND: (
        PRECISION_AUDIENCE_PROMOTION_SPEND,
        "precision_audience_promotion_spend",
        "cube_amt",
    ),
    SMART_SCENE_SPEND: (
        SMART_SCENE_SPEND,
        "smart_scene_spend",
        "feed_charge",
    ),
    ALL_SITE_PROMOTION_SPEND: (
        ALL_SITE_PROMOTION_SPEND,
        PROMOTION_COST,
        "all_site_promotion_spend",
        "promotion_cost",
    ),
    TAOKE_COMMISSION: (
        TAOKE_COMMISSION,
        TAOKE_SPEND,
        "taoke_commission",
        "taoke_spend",
    ),
    TOTAL_PAID_AMOUNT: (TOTAL_PAID_AMOUNT, "total_paid_amount"),
    REFUND_PAID_TIME_AMOUNT: (
        REFUND_PAID_TIME_AMOUNT,
        "refund_paid_time_amount",
    ),
    AMOUNT_REFUND_RATE: (AMOUNT_REFUND_RATE, "amount_refund_rate"),
    ADD_CART_BUYERS: (
        ADD_CART_BUYERS,
        CART_BUYERS,
        "add_cart_buyers",
        "cart_buyers",
    ),
    PRODUCT_FAVORITE_BUYERS: (
        PRODUCT_FAVORITE_BUYERS,
        "product_favorite_buyers",
    ),
    PAGE_VIEWS: (PAGE_VIEWS, "page_views"),
    AVERAGE_STAY_TIME: (AVERAGE_STAY_TIME, "average_stay_time"),
    ADD_CART_ITEMS: (
        ADD_CART_ITEMS,
        CART_COUNT,
        "add_cart_items",
        "cart_count",
    ),
    PAID_SUB_ORDER_COUNT: (
        PAID_SUB_ORDER_COUNT,
        PAID_ORDERS,
        "paid_sub_order_count",
        "paid_orders",
    ),
    TOTAL_PAID_SUB_ORDER_COUNT: (
        TOTAL_PAID_SUB_ORDER_COUNT,
        "total_paid_sub_order_count",
    ),
    ORDER_REFUND_RATE: (ORDER_REFUND_RATE, "order_refund_rate"),
    PAID_ITEMS: (PAID_ITEMS, "paid_items"),
    CUSTOMER_UNIT_PRICE: (CUSTOMER_UNIT_PRICE, "customer_unit_price"),
    OLDER_PAID_AMOUNT: (OLDER_PAID_AMOUNT, "older_paid_amount"),
    OLDER_PAID_BUYERS: (OLDER_PAID_BUYERS, "older_paid_buyers"),
    OLDER_REPURCHASE_RATE: (OLDER_REPURCHASE_RATE, "older_repurchase_rate"),
    REFUND_PROCESS_DAYS: (REFUND_PROCESS_DAYS, "refund_process_days"),
    WANGWANG_MANUAL_RESPONSE_SECONDS: (
        WANGWANG_MANUAL_RESPONSE_SECONDS,
        "wangwang_manual_response_seconds",
    ),
    CONSULTATION_RATE: (CONSULTATION_RATE, "consultation_rate"),
    PLATFORM_DUTY_RATE: (PLATFORM_DUTY_RATE, "platform_duty_rate"),
    PICKUP_24H_RATE: (PICKUP_24H_RATE, "pickup_24h_rate"),
    LOGISTICS_ARRIVAL_HOURS: (
        LOGISTICS_ARRIVAL_HOURS,
        "logistics_arrival_hours",
    ),
}


class LocalDatabase:
    """Shared local SQLite schema with readable Chinese business columns."""

    SCHEMA_VERSION: ClassVar[int] = 1
    _schema_lock: ClassVar[threading.RLock] = threading.RLock()
    _initialized_paths: ClassVar[set[Path]] = set()

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()

    def connect(
        self,
        *,
        initialize: bool = False,
        read_only: bool | None = None,
    ) -> sqlite3.Connection:
        if read_only is None:
            read_only = not initialize
        if read_only:
            if not self.database_path.exists():
                raise sqlite3.OperationalError(
                    f"Local database does not exist: {self.database_path}"
                )
            conn = sqlite3.connect(
                f"{self.database_path.as_uri()}?mode=ro",
                uri=True,
                timeout=30,
            )
        else:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.database_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("pragma busy_timeout = 30000")
        if initialize:
            self.initialize_schema(conn=conn)
        conn.execute("pragma foreign_keys = on")
        return conn

    def initialize_schema(
        self,
        conn: sqlite3.Connection | None = None,
        *,
        force: bool = False,
    ) -> None:
        with self._schema_lock:
            if not force and self.database_path in self._initialized_paths:
                return

            should_close = conn is None
            if conn is None:
                self.database_path.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(self.database_path, timeout=30)
                conn.row_factory = sqlite3.Row
                conn.execute("pragma busy_timeout = 30000")

            try:
                conn.execute("pragma foreign_keys = off")
                conn.execute("pragma journal_mode = wal")
                conn.execute(
                    """
                    create table if not exists schema_version (
                        version integer primary key,
                        applied_at text not null
                    )
                    """
                )
                current = conn.execute("select max(version) from schema_version").fetchone()[0]
                if force or current != self.SCHEMA_VERSION:
                    self._ensure_schema(conn)
                    conn.execute("delete from schema_version")
                    conn.execute(
                        "insert into schema_version(version, applied_at) values (?, ?)",
                        (self.SCHEMA_VERSION, datetime.now().astimezone().isoformat(timespec="seconds")),
                    )
                conn.execute("pragma foreign_keys = on")
                conn.commit()
                self._initialized_paths.add(self.database_path)
            except Exception:
                conn.rollback()
                raise
            finally:
                if should_close:
                    conn.close()

    def recluster_daily_fact_tables(
        self,
        tables: Iterable[str] | None = None,
    ) -> dict[str, int]:
        """Rewrite known daily fact tables in chronological physical order.

        SQLite does not promise any order unless a query uses ``ORDER BY``. This
        maintenance operation is deliberately for database-browser ergonomics
        after historical backfills; normal application queries retain their own
        explicit ordering contract.
        """
        selected_tables = tuple(tables or DAILY_FACT_TABLE_SORT_COLUMNS)
        unknown_tables = sorted(set(selected_tables) - DAILY_FACT_TABLE_SORT_COLUMNS.keys())
        if unknown_tables:
            raise ValueError(
                "Unsupported daily fact tables: " + ", ".join(unknown_tables)
            )

        self.initialize_schema()
        with self.connect(read_only=False) as conn:
            try:
                conn.execute("begin immediate")
                row_counts: dict[str, int] = {}
                for index, table in enumerate(selected_tables):
                    if not self._table_exists(conn, table):
                        continue

                    columns = [
                        str(row["name"])
                        for row in conn.execute(f"pragma table_info({q(table)})")
                    ]
                    required_columns = {
                        STORE_ID,
                        BUSINESS_DAY,
                        *DAILY_FACT_TABLE_SORT_COLUMNS[table],
                    }
                    missing_columns = sorted(required_columns - set(columns))
                    if missing_columns:
                        raise sqlite3.OperationalError(
                            f"Cannot recluster {table}; missing columns: "
                            + ", ".join(missing_columns)
                        )

                    quoted_columns = ", ".join(q(column) for column in columns)
                    ordering = ", ".join(
                        q(column)
                        for column in (
                            STORE_ID,
                            BUSINESS_DAY,
                            *DAILY_FACT_TABLE_SORT_COLUMNS[table],
                        )
                    )
                    temporary_table = f"__recluster_daily_fact_{index}"
                    conn.execute(f"drop table if exists temp.{q(temporary_table)}")
                    conn.execute(
                        f"create temp table {q(temporary_table)} as "
                        f"select {quoted_columns} from {q(table)}"
                    )
                    row_counts[table] = int(
                        conn.execute(
                            f"select count(*) from {q(temporary_table)}"
                        ).fetchone()[0]
                    )
                    conn.execute(f"delete from {q(table)}")
                    conn.execute(
                        f"insert into {q(table)} ({quoted_columns}) "
                        f"select {quoted_columns} from {q(temporary_table)} "
                        f"order by {ordering}"
                    )
                    conn.execute(f"drop table {q(temporary_table)}")
                conn.commit()
                return row_counts
            except Exception:
                conn.rollback()
                raise

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        self._rename_legacy_store_subject_column(conn)
        self._migrate_table(
            conn,
            "platforms",
            f"""
            create table if not exists platforms (
                {q(PLATFORM_ID)} text primary key,
                {q(PLATFORM_CODE)} text not null unique,
                {q(PLATFORM_NAME)} text not null,
                {q(STATUS)} text not null,
                {q(CREATED_AT)} text not null,
                {q(UPDATED_AT)} text not null
            )
            """,
            {PLATFORM_ID, PLATFORM_CODE, PLATFORM_NAME, STATUS, CREATED_AT, UPDATED_AT},
            f"""
            insert into platforms (
                {q(PLATFORM_ID)}, {q(PLATFORM_CODE)}, {q(PLATFORM_NAME)},
                {q(STATUS)}, {q(CREATED_AT)}, {q(UPDATED_AT)}
            )
            select platform_id, code, name, status, created_at, updated_at
            from "{{legacy}}"
            """,
        )
        self._migrate_table(
            conn,
            "stores",
            f"""
            create table if not exists stores (
                {q(STORE_ID)} text primary key,
                {q(PLATFORM_ID)} text not null references platforms({q(PLATFORM_ID)}),
                {q(STORE_SUBJECT_ID)} text not null,
                {q(STORE_NAME)} text not null,
                {q(STATUS)} text not null,
                {q(FIRST_SEEN_AT)} text not null,
                {q(UPDATED_AT)} text not null,
                unique({q(PLATFORM_ID)}, {q(STORE_SUBJECT_ID)})
            )
            """,
            {
                STORE_ID,
                PLATFORM_ID,
                STORE_SUBJECT_ID,
                STORE_NAME,
                STATUS,
                FIRST_SEEN_AT,
                UPDATED_AT,
            },
            f"""
            insert into stores (
                {q(STORE_ID)}, {q(PLATFORM_ID)}, {q(STORE_SUBJECT_ID)},
                {q(STORE_NAME)}, {q(STATUS)}, {q(FIRST_SEEN_AT)}, {q(UPDATED_AT)}
            )
            select store_id, platform_id, platform_store_id, store_name, status,
                   first_seen_at, updated_at
            from "{{legacy}}"
            """,
        )
        self._ensure_brand_schema(conn)
        conn.execute(_product_catalog_create_sql(if_not_exists=True))
        self._migrate_table(
            conn,
            "raw_response_artifacts",
            f"""
            create table if not exists raw_response_artifacts (
                {q(ARTIFACT_ID)} text primary key,
                {q(PLATFORM_ID)} integer not null references platforms({q(PLATFORM_ID)}),
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
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
            """,
            {
                ARTIFACT_ID,
                PLATFORM_ID,
                STORE_ID,
                ENDPOINT_KEY,
                BUSINESS_DAY,
                FETCHED_AT,
                HTTP_STATUS,
                RESPONSE_CODE,
                SOURCE_FILE,
                CONTENT_SHA256,
                FILE_SIZE,
                PARSER_VERSION,
                CREATED_AT,
            },
            f"""
            insert into raw_response_artifacts (
                {q(ARTIFACT_ID)}, {q(PLATFORM_ID)}, {q(STORE_ID)}, {q(ENDPOINT_KEY)},
                {q(BUSINESS_DAY)}, {q(FETCHED_AT)}, {q(HTTP_STATUS)}, {q(RESPONSE_CODE)},
                {q(SOURCE_FILE)}, {q(CONTENT_SHA256)}, {q(FILE_SIZE)},
                {q(PARSER_VERSION)}, {q(CREATED_AT)}
            )
            select artifact_id, platform_id, store_id, endpoint_key, business_day,
                   fetched_at, http_status, response_code, source_path, sha256,
                   size_bytes, parser_version, created_at
            from "{{legacy}}"
            """,
        )
        self._migrate_table(
            conn,
            "store_daily_overviews",
            _daily_overview_create_sql(if_not_exists=True),
            set(DAILY_OVERVIEW_COLUMNS),
            "",
        )
        customer_overview_metric_columns_sql = ",\n                ".join(
            f"{q(column)} text" for column, _ in CUSTOMER_OVERVIEW_FIELDS
        )
        customer_overview_columns = (
            [STORE_ID, BUSINESS_DAY]
            + [column for column, _ in CUSTOMER_OVERVIEW_FIELDS]
        )
        self._migrate_table(
            conn,
            "store_daily_customer_overviews",
            f"""
            create table if not exists store_daily_customer_overviews (
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
                {q(BUSINESS_DAY)} text not null,
                {customer_overview_metric_columns_sql},
                primary key({q(STORE_ID)}, {q(BUSINESS_DAY)})
            )
            """,
            set(customer_overview_columns),
            f"""
            insert into store_daily_customer_overviews (
                {", ".join(q(column) for column in customer_overview_columns)}
            )
            select store_id, business_day, shop_customer, new_visitor_cnt, new_visitor_buy_cnt,
                   new_visitor_in_shop_cnt, new_visitor_pay_rate,
                   new_visitor_pay_amt_ratio, new_visitor_pct,
                   new_visitor_fans_rate, new_visitor_vip_rate,
                   new_visitor_re_call, no_purchase_cnt, no_purchase_buy_cnt,
                   no_buy_in_shop_cnt, no_purchase_pay_rate,
                   no_purchase_pay_amt_ratio, no_purchase_pct,
                   no_purchase_fans_rate, no_purchase_vip_rate,
                   no_purchase_re_call, no_purchase_buy_cnt_rate,
                   has_purchase_cnt, has_purchase_uby_cnt, has_buy_in_shop_cnt,
                   has_purchase_pay_rate, has_purchase_pay_amt_ratio,
                   has_purchase_pct, has_purchase_fans_rate,
                   has_purchase_vip_rate, has_purchase_re_call,
                   has_purchase_uby_cnt_rate
            from "{{legacy}}"
            """,
        )
        self._migrate_table(
            conn,
            "store_daily_traffic_sources",
            f"""
            create table if not exists store_daily_traffic_sources (
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
                {q(BUSINESS_DAY)} text not null,
                {q(TRAFFIC_SOURCE_LEVEL_1)} text not null,
                {q(TRAFFIC_SOURCE_LEVEL_2)} text not null,
                {q(TRAFFIC_SOURCE_LEVEL_3)} text not null,
                {q(SOURCE_LEVEL)} integer not null,
                {q(VISITORS)} text not null,
                {q(NEW_VISITORS)} text not null,
                {q(ADD_CART_BUYERS)} text not null,
                {q(PRODUCT_FAVORITE_BUYERS)} text not null,
                {q(PAID_BUYERS)} text not null,
                {q(CONVERSION_RATE)} text not null,
                {q(PAID_AMOUNT)} text not null,
                {q(PAID_AMOUNT_SHARE)} text not null,
                {q(UV_VALUE)} text not null,
                {q(ORDER_BUYERS)} text not null,
                {q(ORDER_AMOUNT)} text not null,
                {q(ORDER_CONVERSION_RATE)} text not null,
                primary key(
                    {q(STORE_ID)}, {q(BUSINESS_DAY)},
                    {q(SOURCE_LEVEL)}, {q(TRAFFIC_SOURCE_LEVEL_1)},
                    {q(TRAFFIC_SOURCE_LEVEL_2)}, {q(TRAFFIC_SOURCE_LEVEL_3)}
                )
            )
            """,
            {
                STORE_ID,
                BUSINESS_DAY,
                TRAFFIC_SOURCE_LEVEL_1,
                TRAFFIC_SOURCE_LEVEL_2,
                TRAFFIC_SOURCE_LEVEL_3,
                SOURCE_LEVEL,
                VISITORS,
                NEW_VISITORS,
                ADD_CART_BUYERS,
                PRODUCT_FAVORITE_BUYERS,
                PAID_BUYERS,
                CONVERSION_RATE,
                PAID_AMOUNT,
                PAID_AMOUNT_SHARE,
                UV_VALUE,
                ORDER_BUYERS,
                ORDER_AMOUNT,
                ORDER_CONVERSION_RATE,
            },
            f"""
            insert into store_daily_traffic_sources (
                {q(STORE_ID)}, {q(BUSINESS_DAY)},
                {q(TRAFFIC_SOURCE_LEVEL_1)}, {q(TRAFFIC_SOURCE_LEVEL_2)},
                {q(TRAFFIC_SOURCE_LEVEL_3)}, {q(SOURCE_LEVEL)},
                {q(VISITORS)}, {q(NEW_VISITORS)}, {q(ADD_CART_BUYERS)},
                {q(PRODUCT_FAVORITE_BUYERS)}, {q(PAID_BUYERS)}, {q(CONVERSION_RATE)},
                {q(PAID_AMOUNT)}, {q(PAID_AMOUNT_SHARE)}, {q(UV_VALUE)},
                {q(ORDER_BUYERS)}, {q(ORDER_AMOUNT)}, {q(ORDER_CONVERSION_RATE)}
            )
            select store_id, business_day, level1, level2, level3,
                   source_level, visitors, new_visitors, cart_buyers,
                   product_favorite_buyers, paid_buyers, conversion_rate,
                   paid_amount, paid_amount_share, uv_value, order_buyers,
                   order_amount, order_conversion_rate
            from "{{legacy}}"
            """,
        )
        self._migrate_table(
            conn,
            "store_daily_member_channels",
            f"""
            create table if not exists store_daily_member_channels (
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
                {q(BUSINESS_DAY)} text not null,
                {q(MEMBER_CHANNEL_NAME)} text not null,
                {q(MEMBER_NEW_COUNT)} text not null,
                {q(MEMBER_NEW_PAID_COUNT)} text not null,
                {q(MEMBER_RECRUIT_CONVERSION_RATE)} text not null,
                {q(MEMBER_NEW_PAID_AMOUNT)} text not null,
                {q(MEMBER_NEW_UNIT_PRICE)} text not null,
                primary key({q(STORE_ID)}, {q(BUSINESS_DAY)}, {q(MEMBER_CHANNEL_NAME)})
            )
            """,
            {
                STORE_ID,
                BUSINESS_DAY,
                MEMBER_CHANNEL_NAME,
                MEMBER_NEW_COUNT,
                MEMBER_NEW_PAID_COUNT,
                MEMBER_RECRUIT_CONVERSION_RATE,
                MEMBER_NEW_PAID_AMOUNT,
                MEMBER_NEW_UNIT_PRICE,
            },
            f"""
            insert into store_daily_member_channels (
                {q(STORE_ID)}, {q(BUSINESS_DAY)}, {q(MEMBER_CHANNEL_NAME)},
                {q(MEMBER_NEW_COUNT)}, {q(MEMBER_NEW_PAID_COUNT)},
                {q(MEMBER_RECRUIT_CONVERSION_RATE)}, {q(MEMBER_NEW_PAID_AMOUNT)},
                {q(MEMBER_NEW_UNIT_PRICE)}
            )
            select store_id, business_day, channel_name, new_members,
                   paid_new_members, recruit_conversion_rate,
                   new_member_paid_amount, new_member_unit_price
            from "{{legacy}}"
            """,
        )
        member_analysis_metric_columns_sql = ",\n                ".join(
            f"{q(column)} text" for column, _ in MEMBER_ANALYSIS_OVERVIEW_FIELDS
        )
        member_analysis_columns = (
            [STORE_ID, BUSINESS_DAY]
            + [column for column, _ in MEMBER_ANALYSIS_OVERVIEW_FIELDS]
        )
        self._migrate_table(
            conn,
            "store_daily_member_analysis_overviews",
            f"""
            create table if not exists store_daily_member_analysis_overviews (
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
                {q(BUSINESS_DAY)} text not null,
                {member_analysis_metric_columns_sql},
                primary key({q(STORE_ID)}, {q(BUSINESS_DAY)})
            )
            """,
            set(member_analysis_columns),
            f"""
            insert into store_daily_member_analysis_overviews (
                {", ".join(q(column) for column in member_analysis_columns)}
            )
            select store_id, business_day, total_mbr_cnt, paid_mbr_cnt, mbr_pay_amt, mbr_unit_price,
                   repur_mbr_rate, high_freq_buyer_member_assets,
                   high_freq_buyer_member_pay_amt_rate,
                   high_freq_buyer_member_assets_portion,
                   high_freq_buyer_member_assets_ratio,
                   two_order_buyer_member_assets,
                   two_order_buyer_member_pay_amt_rate,
                   two_order_buyer_member_assets_portion,
                   two_order_buyer_member_assets_ratio,
                   first_time_buyer_member_assets,
                   first_time_buyer_member_pay_amt_rate,
                   first_time_buyer_member_assets_portion,
                   first_time_buyer_member_lyr_assets_ratio,
                   active_non_buyer_member_assets,
                   active_non_buyer_member_assets_portion,
                   active_non_buyer_member_lyr_assets_ratio,
                   inactive_member_assets, inactive_member_assets_portion,
                   inactive_member_lyr_assets_ratio, repur_mbr_cnt, repur_pay_amt,
                   repur_ord_cnt, repur_unit_price, repur_cycle, repur_mbr_rate,
                   repur_frequency, incr_mbr_cnt, incr_paid_mbr_cnt,
                   rec_convert_rate, incr_pay_ord_amt, incr_unit_price,
                   old_new_member_count
            from "{{legacy}}"
            """,
        )
        self._migrate_table(
            conn,
            "store_activity_calendar_events",
            _activity_calendar_create_sql(if_not_exists=True),
            set(ACTIVITY_CALENDAR_COLUMNS),
            f"""
            insert into store_activity_calendar_events (
                {", ".join(q(column) for column in ACTIVITY_CALENDAR_COLUMNS)}
            )
            select store_id, business_day, activity_id, activity_name, activity_type,
                   activity_status, activity_start_time, activity_end_time,
                   signup_start_time, signup_end_time, activity_tag, activity_level,
                   activity_stage, shop_participation_status
            from "{{legacy}}"
            """,
        )
        self._migrate_table(
            conn,
            "store_daily_new_customer_discount_overviews",
            _new_customer_discount_create_sql(if_not_exists=True),
            set(NEW_CUSTOMER_DISCOUNT_COLUMNS),
            f"""
            insert into store_daily_new_customer_discount_overviews (
                {", ".join(q(column) for column in NEW_CUSTOMER_DISCOUNT_COLUMNS)}
            )
            select store_id, business_day, shop_visitors, product_new_visitors,
                   new_customer_paid_buyers, new_customer_paid_buyer_ratio,
                   new_customer_paid_amount, new_customer_paid_amount_ratio,
                   new_customer_paid_conversion_rate, shop_new_customer_paid_buyers,
                   shop_new_customer_paid_amount,
                   shop_new_customer_paid_conversion_rate
            from "{{legacy}}"
            """,
        )
        for table, columns in SIMPLE_DAILY_FACT_TABLES.items():
            self._migrate_table(
                conn,
                table,
                _simple_daily_fact_create_sql(
                    table,
                    columns,
                    if_not_exists=True,
                ),
                set(columns),
                "",
            )
        self._migrate_table(
            conn,
            "store_daily_customer_service_accounts",
            _customer_service_accounts_create_sql(if_not_exists=True),
            set(CUSTOMER_SERVICE_ACCOUNT_COLUMNS),
            "",
        )
        self._migrate_table(
            conn,
            PRODUCT_RANKING_TABLE,
            _product_ranking_create_sql(if_not_exists=True),
            set(PRODUCT_RANKING_COLUMNS),
            "",
        )
        for table, (columns, dimensions, key_dimensions) in DIMENSION_DAILY_FACT_TABLES.items():
            self._migrate_table(
                conn,
                table,
                _dimension_daily_fact_create_sql(
                    table,
                    columns,
                    dimensions,
                    key_dimensions,
                    if_not_exists=True,
                ),
                set(columns),
                "",
            )
        self._migrate_table(
            conn,
            "metric_definitions",
            f"""
            create table if not exists metric_definitions (
                {q(METRIC_CODE)} text primary key,
                {q(METRIC_NAME)} text not null,
                {q(METRIC_GROUP)} text not null,
                {q(UNIT)} text not null,
                {q(DESCRIPTION)} text not null,
                {q(CONFIRMATION_STATUS)} text not null,
                {q(UPDATED_AT)} text not null
            )
            """,
            {
                METRIC_CODE,
                METRIC_NAME,
                METRIC_GROUP,
                UNIT,
                DESCRIPTION,
                CONFIRMATION_STATUS,
                UPDATED_AT,
            },
            f"""
            insert into metric_definitions (
                {q(METRIC_CODE)}, {q(METRIC_NAME)}, {q(METRIC_GROUP)}, {q(UNIT)},
                {q(DESCRIPTION)}, {q(CONFIRMATION_STATUS)}, {q(UPDATED_AT)}
            )
            select metric_code, metric_name, metric_group, unit, description,
                   confirmation_status, updated_at
            from "{{legacy}}"
            """,
        )
        self._migrate_table(
            conn,
            "import_runs",
            f"""
            create table if not exists import_runs (
                {q(RUN_ID)} text primary key,
                {q(IDEMPOTENCY_KEY)} text not null unique,
                {q(BUSINESS_DAY)} text not null,
                {q(RUN_MODE)} text not null,
                {q(RUN_STATUS)} text not null,
                {q(SOURCE_SCRIPT)} text not null,
                {q(GENERATED_AT)} text,
                {q(CREATED_AT)} text not null,
                {q(UPDATED_AT)} text not null,
                {q(SELECTED_COUNT)} integer not null,
                {q(DEFERRED_COUNT)} integer not null,
                {q(GUARDRAILS_JSON)} text not null
            )
            """,
            {
                RUN_ID,
                IDEMPOTENCY_KEY,
                BUSINESS_DAY,
                RUN_MODE,
                RUN_STATUS,
                SOURCE_SCRIPT,
                GENERATED_AT,
                CREATED_AT,
                UPDATED_AT,
                SELECTED_COUNT,
                DEFERRED_COUNT,
                GUARDRAILS_JSON,
            },
            f"""
            insert into import_runs (
                {q(RUN_ID)}, {q(IDEMPOTENCY_KEY)}, {q(BUSINESS_DAY)}, {q(RUN_MODE)},
                {q(RUN_STATUS)}, {q(SOURCE_SCRIPT)}, {q(GENERATED_AT)}, {q(CREATED_AT)},
                {q(UPDATED_AT)}, {q(SELECTED_COUNT)}, {q(DEFERRED_COUNT)}, {q(GUARDRAILS_JSON)}
            )
            select run_id, idempotency_key, day, mode, status, source, generated_at,
                   created_at, updated_at, selected_count, deferred_count, guardrails_json
            from "{{legacy}}"
            """,
        )
        self._migrate_table(
            conn,
            "import_run_items",
            f"""
            create table if not exists import_run_items (
                {q(ITEM_ID)} integer primary key autoincrement,
                {q(RUN_ID)} text not null references import_runs({q(RUN_ID)}) on delete cascade,
                {q(ITEM_ORDER)} integer not null,
                {q(FUNCTION_NAME)} text not null,
                {q(PRIORITY)} text not null,
                {q(LEGACY_PATH)} text not null,
                {q(REQUEST_METHOD)} text not null,
                {q(REQUEST_URL)} text not null,
                {q(TARGET_TABLE)} text not null,
                {q(DATE_MODE)} text not null,
                {q(SHAPE_STATUS)} text not null,
                {q(RUNTIME_CREDENTIALS_JSON)} text not null,
                {q(QUERY_PARAMS_JSON)} text not null,
                {q(BODY_TEMPLATE_JSON)} text,
                {q(ITEM_STATUS)} text not null,
                {q(RISK_NOTES_JSON)} text not null
            )
            """,
            {
                ITEM_ID,
                RUN_ID,
                ITEM_ORDER,
                FUNCTION_NAME,
                PRIORITY,
                LEGACY_PATH,
                REQUEST_METHOD,
                REQUEST_URL,
                TARGET_TABLE,
                DATE_MODE,
                SHAPE_STATUS,
                RUNTIME_CREDENTIALS_JSON,
                QUERY_PARAMS_JSON,
                BODY_TEMPLATE_JSON,
                ITEM_STATUS,
                RISK_NOTES_JSON,
            },
            f"""
            insert into import_run_items (
                {q(ITEM_ID)}, {q(RUN_ID)}, {q(ITEM_ORDER)}, {q(FUNCTION_NAME)},
                {q(PRIORITY)}, {q(LEGACY_PATH)}, {q(REQUEST_METHOD)}, {q(REQUEST_URL)},
                {q(TARGET_TABLE)}, {q(DATE_MODE)}, {q(SHAPE_STATUS)},
                {q(RUNTIME_CREDENTIALS_JSON)}, {q(QUERY_PARAMS_JSON)}, {q(BODY_TEMPLATE_JSON)},
                {q(ITEM_STATUS)}, {q(RISK_NOTES_JSON)}
            )
            select item_id, run_id, item_order, function_name, priority, legacy_path,
                   method, url, target_table, date_mode, shape_status,
                   runtime_credentials_json, query_params_json, body_template_json,
                   status, risk_notes_json
            from "{{legacy}}"
            """,
        )
        self._migrate_table(
            conn,
            "crawl_runs",
            f"""
            create table if not exists crawl_runs (
                {q(CRAWL_RUN_ID)} text primary key,
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
                {q(CRAWL_TASK_TYPE)} text not null,
                {q(START_DAY)} text not null,
                {q(END_DAY)} text not null,
                {q(RUN_MODE)} text not null,
                {q(RUN_STATUS)} text not null,
                {q(PLANNED_DAYS)} integer not null,
                {q(SUCCESS_DAYS)} integer not null,
                {q(SKIPPED_DAYS)} integer not null,
                {q(FAILED_DAYS)} integer not null,
                {q(STARTED_AT)} text not null,
                {q(FINISHED_AT)} text,
                {q(LOG_FILE)} text not null
            )
            """,
            {
                CRAWL_RUN_ID,
                STORE_ID,
                CRAWL_TASK_TYPE,
                START_DAY,
                END_DAY,
                RUN_MODE,
                RUN_STATUS,
                PLANNED_DAYS,
                SUCCESS_DAYS,
                SKIPPED_DAYS,
                FAILED_DAYS,
                STARTED_AT,
                FINISHED_AT,
                LOG_FILE,
            },
            "",
        )
        self._migrate_table(
            conn,
            "crawl_run_days",
            f"""
            create table if not exists crawl_run_days (
                {q(ITEM_DAY_ID)} integer primary key autoincrement,
                {q(CRAWL_RUN_ID)} text not null references crawl_runs({q(CRAWL_RUN_ID)}) on delete cascade,
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
                {q(BUSINESS_DAY)} text not null,
                {q(DAY_STATUS)} text not null,
                {q(METRIC_COUNT)} integer,
                {q(ERROR_MESSAGE)} text,
                unique({q(CRAWL_RUN_ID)}, {q(BUSINESS_DAY)})
            )
            """,
            {
                ITEM_DAY_ID,
                CRAWL_RUN_ID,
                STORE_ID,
                BUSINESS_DAY,
                DAY_STATUS,
                METRIC_COUNT,
                ERROR_MESSAGE,
            },
            "",
        )
        conn.execute(
            """
            create table if not exists collection_batches (
                batch_id text primary key,
                business_day text not null,
                dataset_names_json text not null,
                trigger_type text not null,
                session_source text not null,
                refresh_existing integer not null default 0,
                status text not null,
                process_id integer,
                completed_count integer not null default 0,
                failed_count integer not null default 0,
                started_at text not null,
                finished_at text,
                log_file text not null,
                error_message text
            )
            """
        )
        conn.execute(
            """
            create table if not exists collection_schedule (
                schedule_id integer primary key check(schedule_id = 1),
                enabled integer not null default 0,
                run_time text not null,
                timezone text not null,
                dataset_names_json text not null,
                session_source text not null,
                last_triggered_day text,
                last_triggered_at text,
                updated_at text not null
            )
            """
        )
        conn.execute(
            """
            create index if not exists idx_collection_batches_started
            on collection_batches(started_at desc)
            """
        )
        conn.execute(
            """
            create table if not exists ai_execution_logs (
                execution_id text primary key,
                store_id integer,
                question text not null,
                skill_name text not null,
                skill_version text not null,
                provider_name text not null,
                model_name text,
                status text not null,
                mcp_tools_json text not null,
                warnings_json text not null,
                duration_ms integer not null default 0,
                error_message text,
                created_at text not null
            )
            """
        )
        conn.execute(
            """
            create index if not exists idx_ai_execution_logs_created
            on ai_execution_logs(created_at desc)
            """
        )
        conn.executescript(
            """
            create table if not exists ai_conversations (
                conversation_id text primary key,
                user_id integer,
                store_id integer,
                title text not null default '新对话',
                summary text not null default '',
                memory_json text not null default '{}',
                created_at text not null,
                updated_at text not null
            );
            create index if not exists idx_ai_conversations_user_updated
            on ai_conversations(user_id, updated_at desc);
            create table if not exists ai_conversation_messages (
                message_id text primary key,
                conversation_id text not null,
                role text not null check(role in ('user', 'assistant')),
                text text not null,
                analysis_json text,
                created_at text not null,
                foreign key(conversation_id) references ai_conversations(conversation_id) on delete cascade
            );
            create index if not exists idx_ai_conversation_messages_conversation
            on ai_conversation_messages(conversation_id, created_at desc);
            """
        )
        conn.executescript(
            """
            create table if not exists jackyun_inventory_snapshots (
                store_id integer not null default 0,
                business_day text not null,
                warehouse_id text not null,
                warehouse_name text,
                goods_id text not null default '',
                sku_id text not null default '',
                goods_no text not null default '',
                sku_no text not null default '',
                goods_name text,
                sku_name text,
                sku_barcode text not null default '',
                available_quantity real not null default 0,
                stock_quantity real not null default 0,
                raw_json text not null default '{}',
                fetched_at text not null,
                primary key (business_day, store_id, warehouse_id, sku_id, goods_no, sku_barcode)
            );

            create index if not exists idx_jackyun_inventory_lookup
            on jackyun_inventory_snapshots(store_id, business_day, goods_no, sku_barcode, sku_id);

            create table if not exists jackyun_inventory_sync_status (
                store_id integer primary key,
                status text not null default 'never_run',
                latest_business_day text,
                latest_snapshot_at text,
                last_attempt_at text,
                row_count integer not null default 0,
                error_message text
            );

            create table if not exists jackyun_package_products (
                store_id integer not null default 0,
                goods_id text not null default '',
                sku_id text not null default '',
                goods_no text not null default '',
                sku_no text not null default '',
                goods_name text,
                sku_name text,
                sku_barcode text not null default '',
                updated_at text not null,
                primary key (store_id, goods_id, sku_id)
            );

            create index if not exists idx_jackyun_packages_lookup
            on jackyun_package_products(store_id, goods_no, sku_barcode, sku_id);

            create table if not exists jackyun_package_components (
                component_id integer primary key autoincrement,
                store_id integer not null default 0,
                package_goods_id text not null default '',
                package_sku_id text not null default '',
                component_goods_id text not null default '',
                component_sku_id text not null default '',
                component_goods_no text not null default '',
                component_sku_barcode text not null default '',
                component_goods_name text,
                required_quantity real not null check(required_quantity > 0),
                updated_at text not null
            );

            create index if not exists idx_jackyun_package_components_package
            on jackyun_package_components(store_id, package_goods_id, package_sku_id);

            create table if not exists jackyun_goods_master (
                store_id integer not null default 0,
                goods_id text not null default '',
                goods_no text not null default '',
                goods_name text,
                cate_name text,
                brand_name text,
                unit_name text,
                assist_unit text,
                owner_name text,
                package_good integer not null default 0,
                audit_status text,
                is_blockup integer,
                is_stop_selling integer,
                is_stop_purchasing integer,
                raw_json text not null default '{}',
                fetched_at text not null,
                primary key (store_id, goods_id, goods_no)
            );

            create index if not exists idx_jackyun_goods_master_lookup
            on jackyun_goods_master(store_id, goods_no, goods_name, package_good);

            create table if not exists jackyun_inventory_master_sync_status (
                store_id integer not null,
                business_day text not null,
                goods_status text not null default 'never_run',
                package_status text not null default 'never_run',
                goods_count integer not null default 0,
                package_count integer not null default 0,
                component_count integer not null default 0,
                last_attempt_at text,
                finished_at text,
                error_message text,
                primary key (store_id, business_day)
            );

            create index if not exists idx_jackyun_master_sync_latest
            on jackyun_inventory_master_sync_status(store_id, business_day desc);

            create table if not exists inventory_product_catalog (
                id integer primary key autoincrement,
                store_id integer not null default 0,
                series text not null default '',
                specification text not null default '',
                size text not null default '',
                goods_no text not null,
                pieces integer,
                display_name text,
                source text not null default '',
                source_line integer,
                is_active integer not null default 1,
                updated_at text not null,
                unique (store_id, series, specification, size, goods_no, pieces)
            );

            create index if not exists idx_inventory_catalog_code
            on inventory_product_catalog(store_id, goods_no);
            create index if not exists idx_inventory_catalog_dimensions
            on inventory_product_catalog(store_id, series, specification, size);
            """
        )
        self._drop_business_views(conn)
        self._rebuild_business_fact_tables_if_needed(conn)
        self._repair_promotion_bidword_primary_key(conn)
        self._migrate_identity_ids(conn)
        self._rebuild_identity_tables_if_needed(conn)
        self._repair_identity_foreign_keys(conn)
        self._repair_crawl_ledger_foreign_keys(conn)
        self._repair_orphaned_platforms(conn)
        self._normalize_live_overview_business_days(conn)
        self._ensure_access_control_schema(conn)
        for table in DAILY_FACT_TABLE_SORT_COLUMNS:
            conn.execute(
                f'create index if not exists "idx_{table}_store_day" '
                f'on {q(table)}({q(STORE_ID)}, {q(BUSINESS_DAY)})'
            )
        conn.execute(
            f'create index if not exists "idx_store_daily_overviews_day" '
            f'on store_daily_overviews({q(BUSINESS_DAY)})'
        )
        conn.execute(
            f'create index if not exists "idx_store_daily_customer_overviews_day" '
            f'on store_daily_customer_overviews({q(BUSINESS_DAY)})'
        )
        conn.execute(
            f'create index if not exists "idx_store_daily_traffic_sources_day" '
            f'on store_daily_traffic_sources({q(BUSINESS_DAY)})'
        )
        conn.execute(
            f'create index if not exists "idx_store_daily_member_channels_day" '
            f'on store_daily_member_channels({q(BUSINESS_DAY)})'
        )
        conn.execute(
            f'create index if not exists "idx_store_daily_member_analysis_overviews_day" '
            f'on store_daily_member_analysis_overviews({q(BUSINESS_DAY)})'
        )
        conn.execute(
            f'create index if not exists "idx_store_activity_calendar_events_day" '
            f'on store_activity_calendar_events({q(BUSINESS_DAY)})'
        )
        conn.execute(
            f'create index if not exists "idx_store_daily_new_customer_discount_day" '
            f'on store_daily_new_customer_discount_overviews({q(BUSINESS_DAY)})'
        )
        for table in SIMPLE_DAILY_FACT_TABLES:
            conn.execute(
                f'create index if not exists "idx_{table}_day" '
                f'on {table}({q(BUSINESS_DAY)})'
            )
        conn.execute(
            'create index if not exists "idx_store_daily_customer_service_accounts_day" '
            f'on store_daily_customer_service_accounts({q(BUSINESS_DAY)})'
        )
        conn.execute(
            f'create index if not exists "idx_{PRODUCT_RANKING_TABLE}_day" '
            f'on {PRODUCT_RANKING_TABLE}({q(BUSINESS_DAY)})'
        )
        conn.execute(
            f'create index if not exists "idx_{PRODUCT_CATALOG_TABLE}_name" '
            f'on {PRODUCT_CATALOG_TABLE}({q(STORE_ID)}, {q("商品名称")})'
        )
        for table in DIMENSION_DAILY_FACT_TABLES:
            conn.execute(
                f'create index if not exists "idx_{table}_day" '
                f'on {table}({q(BUSINESS_DAY)})'
            )
        conn.execute(
            'create index if not exists "idx_crawl_runs_started" '
            f'on crawl_runs({q(STARTED_AT)})'
        )
        conn.execute(
            'create index if not exists "idx_crawl_run_days_day" '
            f'on crawl_run_days({q(STORE_ID)}, {q(BUSINESS_DAY)})'
        )
        self._migrate_legacy_flow_metrics(conn)
        conn.execute('drop table if exists "store_daily_metrics"')
        self._drop_business_views(conn)
        conn.execute('drop table if exists "raw_response_artifacts"')
        conn.commit()

    @staticmethod
    def _ensure_brand_schema(conn: sqlite3.Connection) -> None:
        """Create the data-bank subject separately from store operations."""
        # The daily collector currently populates only the overview, stage,
        # and dimension facts.  Keep optional/unused brand tables out of an
        # already-established database when they have no rows.  A brand
        # schema created for a brand-new database still gets the complete
        # table set so tests and future imports can opt into those datasets.
        established_brand_db = LocalDatabase._table_exists(conn, BRAND_TABLE)
        conn.executescript(
            f"""
            create table if not exists {BRAND_TABLE} (
                {q(BRAND_ID)} text primary key,
                {q(BRAND_SUBJECT_ID)} text not null unique,
                {q(BRAND_NAME)} text not null,
                {q(BRAND_STATUS)} text not null default 'active',
                {q(CREATED_AT)} text not null,
                {q(UPDATED_AT)} text not null
            );
            create table if not exists {BRAND_STORE_SCOPE_TABLE} (
                {q(BRAND_ID)} text not null references {BRAND_TABLE}({q(BRAND_ID)}) on delete cascade,
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}) on delete cascade,
                is_primary integer not null default 0 check (is_primary in (0, 1)),
                {q(CREATED_AT)} text not null,
                primary key ({q(BRAND_ID)}, {q(STORE_ID)})
            );
            create table if not exists {BRAND_ASSET_OVERVIEW_TABLE} (
                {q(BRAND_ID)} text not null references {BRAND_TABLE}({q(BRAND_ID)}) on delete cascade,
                {q(BUSINESS_DAY)} text not null,
                {q(BRAND_STATISTIC_SCOPE)} text not null,
                {q(BRAND_CONSUMER_COUNT)} text,
                {q(BRAND_RELATIONSHIP_DEEPENING_RATE)} text,
                {q(BRAND_REPURCHASE_PURCHASE_RATIO)} text,
                {q(BRAND_TRANSACTION_AMOUNT)} text,
                {q(BRAND_TRANSACTION_BUYER_COUNT)} text,
                {q(BRAND_CONSUMER_UNIT_PRICE)} text,
                {q(BRAND_MEMBER_TRANSACTION_AMOUNT)} text,
                {q(BRAND_PREDICTED_CONSUMER_VALUE)} text,
                primary key ({q(BRAND_ID)}, {q(BUSINESS_DAY)}, {q(BRAND_STATISTIC_SCOPE)})
            );
            create table if not exists {BRAND_ASSET_STAGE_TABLE} (
                {q(BRAND_ID)} text not null references {BRAND_TABLE}({q(BRAND_ID)}) on delete cascade,
                {q(BUSINESS_DAY)} text not null,
                {q(BRAND_STAGE_CODE)} text not null,
                {q(BRAND_STAGE_NAME)} text not null,
                {q(BRAND_CONSUMER_COUNT)} text,
                {q(BRAND_CONSUMER_SHARE)} text,
                {q(BRAND_TRANSACTION_AMOUNT)} text,
                {q(BRAND_TRANSACTION_BUYER_COUNT)} text,
                {q(BRAND_CONVERSION_RATE)} text,
                {q(BRAND_CONSUMER_UNIT_PRICE)} text,
                primary key ({q(BRAND_ID)}, {q(BUSINESS_DAY)}, {q(BRAND_STAGE_CODE)})
            );
            create table if not exists {BRAND_ASSET_DIMENSION_TABLE} (
                {q(BRAND_ID)} text not null references {BRAND_TABLE}({q(BRAND_ID)}) on delete cascade,
                {q(BUSINESS_DAY)} text not null,
                {q(BRAND_DIMENSION_TYPE)} text not null,
                {q(BRAND_DIMENSION_CODE)} text not null,
                {q(BRAND_DIMENSION_NAME)} text not null,
                {q(BRAND_CONSUMER_COUNT)} text,
                {q(BRAND_CONSUMER_SHARE)} text,
                {q(BRAND_TRANSACTION_AMOUNT)} text,
                {q(BRAND_TRANSACTION_BUYER_COUNT)} text,
                {q(BRAND_CONVERSION_RATE)} text,
                {q(BRAND_CONSUMER_UNIT_PRICE)} text,
                primary key ({q(BRAND_ID)}, {q(BUSINESS_DAY)}, {q(BRAND_DIMENSION_TYPE)}, {q(BRAND_DIMENSION_CODE)})
            );
            create table if not exists {BRAND_ASSET_METRICS_TABLE} (
                {q(BRAND_ID)} text not null references {BRAND_TABLE}({q(BRAND_ID)}) on delete cascade,
                {q(BUSINESS_DAY)} text not null,
                {q(BRAND_DIMENSION_TYPE)} text not null,
                {q(BRAND_DIMENSION_CODE)} text not null,
                {q(BRAND_METRIC_NAME)} text not null,
                {q(BRAND_VALUE)} text,
                {q(BRAND_PERIOD_START)} text,
                {q(BRAND_PERIOD_END)} text,
                primary key ({q(BRAND_ID)}, {q(BUSINESS_DAY)}, {q(BRAND_DIMENSION_TYPE)}, {q(BRAND_DIMENSION_CODE)}, {q(BRAND_METRIC_NAME)})
            );
            create table if not exists {BRAND_ASSET_FLOW_TABLE} (
                {q(BRAND_ID)} text not null references {BRAND_TABLE}({q(BRAND_ID)}) on delete cascade,
                {q(BUSINESS_DAY)} text not null,
                {q(BRAND_FLOW_TYPE)} text not null,
                {q(BRAND_FROM_STAGE)} text not null,
                {q(BRAND_TO_STAGE)} text not null,
                {q(BRAND_FLOW_COUNT)} text,
                {q(BRAND_FLOW_SHARE)} text,
                primary key ({q(BRAND_ID)}, {q(BUSINESS_DAY)}, {q(BRAND_FLOW_TYPE)}, {q(BRAND_FROM_STAGE)}, {q(BRAND_TO_STAGE)})
            );
            create table if not exists {BRAND_BENCHMARK_TABLE} (
                {q(BRAND_ID)} text not null references {BRAND_TABLE}({q(BRAND_ID)}) on delete cascade,
                {q(BRAND_PERIOD_START)} text not null,
                {q(BRAND_PERIOD_END)} text not null,
                {q(BRAND_DIMENSION_TYPE)} text not null,
                {q(BRAND_DIMENSION_NAME)} text not null,
                {q(BRAND_METRIC_NAME)} text not null,
                {q(BRAND_VALUE)} text,
                {q(INDUSTRY_MEDIAN)} text,
                {q(INDUSTRY_TOP)} text,
                {q(INDUSTRY_RANK)} text,
                {q(SAMPLE_SIZE)} text,
                primary key ({q(BRAND_ID)}, {q(BRAND_PERIOD_START)}, {q(BRAND_PERIOD_END)}, {q(BRAND_DIMENSION_TYPE)}, {q(BRAND_DIMENSION_NAME)}, {q(BRAND_METRIC_NAME)})
            );
            create table if not exists {BRAND_ACTIVITY_TABLE} (
                {q(BRAND_ID)} text not null references {BRAND_TABLE}({q(BRAND_ID)}) on delete cascade,
                {q(BRAND_ACTIVITY_ID)} text not null,
                {q(BRAND_ACTIVITY_NAME)} text not null,
                {q(BRAND_ACTIVITY_TYPE)} text not null,
                {q(BRAND_ACTIVITY_START_TIME)} text,
                {q(BRAND_ACTIVITY_END_TIME)} text,
                {q(BRAND_BASELINE_START_DATE)} text,
                {q(BRAND_BASELINE_END_DATE)} text,
                {q(BRAND_ASSET_BEFORE)} text,
                {q(BRAND_ASSET_AFTER)} text,
                {q(BRAND_ASSET_GROWTH)} text,
                {q(BRAND_NEW_CONSUMER_COUNT)} text,
                {q(BRAND_TRANSACTION_AMOUNT)} text,
                {q(BRAND_RETURN_ON_INVESTMENT)} text,
                primary key ({q(BRAND_ID)}, {q(BRAND_ACTIVITY_ID)})
            );
            create table if not exists {BRAND_PRODUCT_TABLE} (
                {q(BRAND_ID)} text not null references {BRAND_TABLE}({q(BRAND_ID)}) on delete cascade,
                {q(BRAND_PRODUCT_ID)} text not null,
                {q(BRAND_PRODUCT_SPU_ID)} text,
                {q(BRAND_PRODUCT_NAME)} text not null,
                {q(BRAND_PRODUCT_SERIES)} text,
                {q(BRAND_PRODUCT_CATEGORY)} text,
                {q(BRAND_PRODUCT_LINE)} text,
                {q(BRAND_PRODUCT_POSITIONING)} text,
                {q(BRAND_PRODUCT_STATUS)} text not null default 'active',
                {q(BRAND_PRODUCT_LAUNCH_DATE)} text,
                {q(CREATED_AT)} text not null,
                {q(UPDATED_AT)} text not null,
                primary key ({q(BRAND_ID)}, {q(BRAND_PRODUCT_ID)})
            );
            create table if not exists {BRAND_PRODUCT_STORE_LINK_TABLE} (
                {q(BRAND_ID)} text not null,
                {q(BRAND_PRODUCT_ID)} text not null,
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}) on delete cascade,
                {q(BRAND_STORE_PRODUCT_ID)} text not null,
                {q(BRAND_PRODUCT_CHANNEL)} text,
                {q(CREATED_AT)} text not null,
                primary key ({q(BRAND_ID)}, {q(BRAND_PRODUCT_ID)}, {q(STORE_ID)}, {q(BRAND_STORE_PRODUCT_ID)}),
                foreign key ({q(BRAND_ID)}, {q(BRAND_PRODUCT_ID)})
                    references {BRAND_PRODUCT_TABLE}({q(BRAND_ID)}, {q(BRAND_PRODUCT_ID)}) on delete cascade
            );
            create table if not exists {BRAND_PRODUCT_DAILY_TABLE} (
                {q(BRAND_ID)} text not null,
                {q(BUSINESS_DAY)} text not null,
                {q(BRAND_PRODUCT_ID)} text not null,
                {q(BRAND_PRODUCT_EXPOSURE_CONSUMERS)} text,
                {q(BRAND_PRODUCT_INTEREST_CONSUMERS)} text,
                {q(BRAND_PRODUCT_ASSET_CONSUMERS)} text,
                {q(BRAND_PRODUCT_NEW_ASSET_CONSUMERS)} text,
                {q(BRAND_PRODUCT_PURCHASE_CONSUMERS)} text,
                {q(BRAND_PRODUCT_NEW_CUSTOMER_BUYERS)} text,
                {q(BRAND_PRODUCT_OLD_CUSTOMER_BUYERS)} text,
                {q(BRAND_PRODUCT_MEMBER_BUYERS)} text,
                {q(BRAND_TRANSACTION_BUYER_COUNT)} text,
                {q(BRAND_TRANSACTION_AMOUNT)} text,
                {q(BRAND_CONVERSION_RATE)} text,
                {q(BRAND_CONSUMER_UNIT_PRICE)} text,
                {q(BRAND_PRODUCT_REPURCHASE_BUYERS)} text,
                {q(BRAND_PRODUCT_REPURCHASE_RATE)} text,
                {q(BRAND_PRODUCT_CONTRIBUTION_RATE)} text,
                primary key ({q(BRAND_ID)}, {q(BUSINESS_DAY)}, {q(BRAND_PRODUCT_ID)}),
                foreign key ({q(BRAND_ID)}, {q(BRAND_PRODUCT_ID)})
                    references {BRAND_PRODUCT_TABLE}({q(BRAND_ID)}, {q(BRAND_PRODUCT_ID)}) on delete cascade
            );
            create table if not exists {BRAND_PRODUCT_DIMENSION_TABLE} (
                {q(BRAND_ID)} text not null,
                {q(BUSINESS_DAY)} text not null,
                {q(BRAND_PRODUCT_ID)} text not null,
                {q(BRAND_DIMENSION_TYPE)} text not null,
                {q(BRAND_DIMENSION_CODE)} text not null,
                {q(BRAND_DIMENSION_NAME)} text not null,
                {q(BRAND_CONSUMER_COUNT)} text,
                {q(BRAND_CONSUMER_SHARE)} text,
                {q(BRAND_PRODUCT_NEW_ASSET_CONSUMERS)} text,
                {q(BRAND_TRANSACTION_BUYER_COUNT)} text,
                {q(BRAND_TRANSACTION_AMOUNT)} text,
                {q(BRAND_CONVERSION_RATE)} text,
                primary key ({q(BRAND_ID)}, {q(BUSINESS_DAY)}, {q(BRAND_PRODUCT_ID)}, {q(BRAND_DIMENSION_TYPE)}, {q(BRAND_DIMENSION_CODE)}),
                foreign key ({q(BRAND_ID)}, {q(BRAND_PRODUCT_ID)})
                    references {BRAND_PRODUCT_TABLE}({q(BRAND_ID)}, {q(BRAND_PRODUCT_ID)}) on delete cascade
            );
            create index if not exists idx_brand_store_scopes_store
                on {BRAND_STORE_SCOPE_TABLE}({q(STORE_ID)});
            create index if not exists idx_brand_asset_overview_day
                on {BRAND_ASSET_OVERVIEW_TABLE}({q(BRAND_ID)}, {q(BUSINESS_DAY)});
            create index if not exists idx_brand_asset_stage_day
                on {BRAND_ASSET_STAGE_TABLE}({q(BRAND_ID)}, {q(BUSINESS_DAY)});
            create index if not exists idx_brand_asset_dimension_day
                on {BRAND_ASSET_DIMENSION_TABLE}({q(BRAND_ID)}, {q(BUSINESS_DAY)});
            create index if not exists idx_brand_asset_metrics_day
                on {BRAND_ASSET_METRICS_TABLE}({q(BRAND_ID)}, {q(BUSINESS_DAY)}, {q(BRAND_DIMENSION_TYPE)});
            create index if not exists idx_brand_products_series
                on {BRAND_PRODUCT_TABLE}({q(BRAND_ID)}, {q(BRAND_PRODUCT_SERIES)});
            create index if not exists idx_brand_product_store_link
                on {BRAND_PRODUCT_STORE_LINK_TABLE}({q(STORE_ID)}, {q(BRAND_STORE_PRODUCT_ID)});
            create index if not exists idx_brand_product_daily_day
                on {BRAND_PRODUCT_DAILY_TABLE}({q(BRAND_ID)}, {q(BRAND_PRODUCT_ID)}, {q(BUSINESS_DAY)});
            create index if not exists idx_brand_product_dimension_day
                on {BRAND_PRODUCT_DIMENSION_TABLE}({q(BRAND_ID)}, {q(BRAND_PRODUCT_ID)}, {q(BUSINESS_DAY)});
            """
        )
        if established_brand_db:
            # Drop only empty optional tables.  Children must be removed
            # before brand_products because they carry composite FKs.
            optional_tables = (
                BRAND_ASSET_FLOW_TABLE,
                BRAND_BENCHMARK_TABLE,
                BRAND_ACTIVITY_TABLE,
                BRAND_PRODUCT_DIMENSION_TABLE,
                BRAND_PRODUCT_DAILY_TABLE,
                BRAND_PRODUCT_STORE_LINK_TABLE,
                BRAND_PRODUCT_TABLE,
            )
            for table in optional_tables:
                if LocalDatabase._table_exists(conn, table):
                    row_count = conn.execute(
                        f"select count(*) from {q(table)}"
                    ).fetchone()[0]
                    if int(row_count) == 0:
                        conn.execute(f"drop table {q(table)}")

    @staticmethod
    def _ensure_access_control_schema(conn: sqlite3.Connection) -> None:
        """Create the system-owned access-control tables outside the business mart."""
        conn.executescript(
            f"""
            create table if not exists access_users (
                user_id integer primary key autoincrement,
                username text not null collate nocase unique,
                display_name text not null,
                password_hash text not null,
                is_active integer not null default 1 check (is_active in (0, 1)),
                created_at text not null,
                updated_at text not null,
                last_login_at text
            );

            create table if not exists access_roles (
                role_code text primary key,
                role_name text not null,
                description text not null,
                is_system integer not null default 1 check (is_system in (0, 1))
            );

            create table if not exists access_permissions (
                permission_code text primary key,
                permission_name text not null,
                description text not null
            );

            create table if not exists access_user_roles (
                user_id integer not null references access_users(user_id) on delete cascade,
                role_code text not null references access_roles(role_code) on delete cascade,
                primary key (user_id, role_code)
            );

            create table if not exists access_role_permissions (
                role_code text not null references access_roles(role_code) on delete cascade,
                permission_code text not null references access_permissions(permission_code) on delete cascade,
                primary key (role_code, permission_code)
            );

            create table if not exists access_menus (
                menu_code text primary key,
                parent_code text references access_menus(menu_code) on delete cascade,
                menu_name text not null,
                menu_type text not null check (menu_type in ('catalog', 'menu')),
                path text not null,
                component text not null,
                permission_code text references access_permissions(permission_code) on delete set null,
                sort_order integer not null default 0,
                is_hidden integer not null default 0 check (is_hidden in (0, 1))
            );

            create table if not exists access_role_menus (
                role_code text not null references access_roles(role_code) on delete cascade,
                menu_code text not null references access_menus(menu_code) on delete cascade,
                primary key (role_code, menu_code)
            );

            create table if not exists access_schema_migrations (
                migration_code text primary key,
                applied_at text not null
            );

            create table if not exists access_user_store_scopes (
                user_id integer not null references access_users(user_id) on delete cascade,
                store_id integer not null references stores("店铺ID") on delete cascade,
                primary key (user_id, store_id)
            );

            create table if not exists access_user_brand_scopes (
                user_id integer not null references access_users(user_id) on delete cascade,
                {q(BRAND_ID)} text not null references {BRAND_TABLE}({q(BRAND_ID)}) on delete cascade,
                primary key (user_id, {q(BRAND_ID)})
            );

            create table if not exists access_sessions (
                session_id text primary key,
                user_id integer not null references access_users(user_id) on delete cascade,
                token_hash text not null unique,
                created_at text not null,
                expires_at text not null,
                revoked_at text,
                last_seen_at text not null
            );

            create table if not exists access_audit_logs (
                audit_id integer primary key autoincrement,
                actor_user_id integer references access_users(user_id) on delete set null,
                action_code text not null,
                target_type text not null,
                target_id text,
                outcome text not null,
                detail text,
                created_at text not null
            );

            create index if not exists idx_access_sessions_token on access_sessions(token_hash);
            create index if not exists idx_access_sessions_user on access_sessions(user_id, expires_at);
            create index if not exists idx_access_audit_actor on access_audit_logs(actor_user_id, created_at);
            create index if not exists idx_access_menus_parent on access_menus(parent_code, sort_order);
            create index if not exists idx_access_user_store_scopes_store on access_user_store_scopes(store_id);
            create index if not exists idx_access_user_brand_scopes_brand on access_user_brand_scopes({q(BRAND_ID)});
            """
        )
        conn.executemany(
            """
            insert into access_permissions (permission_code, permission_name, description)
            values (?, ?, ?)
            on conflict(permission_code) do update set
                permission_name = excluded.permission_name,
                description = excluded.description
            """,
            (
                ("analytics.read", "查看经营数据", "查看店铺经营、商品、流量、客户和营销指标。"),
                ("warehouse.read", "查看数据仓库", "查看店铺、日概览、指标和活动数据。"),
                ("imports.read", "查看采集记录", "查看采集计划、运行记录和进度。"),
                ("imports.manage", "管理采集计划", "创建本地采集预览和后续受控任务。"),
                ("captures.read", "查看采集实验室", "查看脱敏的抓包摘要。"),
                ("contracts.read", "查看接口契约", "查看脱敏的接口契约与字段结构。"),
                ("operations.read", "查看操作中心", "查看受控操作能力和安全状态。"),
                ("system.read", "查看系统状态", "查看系统能力和运行状态。"),
                ("access.manage", "管理用户权限", "管理用户、角色和店铺数据授权。"),
                ("brand_assets.read", "查看品牌资产", "查看品牌数据银行资产、分层、维度和对标数据。"),
                ("data.manage", "数据管理", "访问数据完整性、采集记录、店铺数据和采集设置。"),
                ("system.manage", "系统设置", "访问用户、角色、菜单和接口权限配置。"),
            ),
        )
        from app.modules.access.catalog import MENU_DEFINITIONS

        existing_menu_codes = {
            str(row["menu_code"])
            for row in conn.execute("select menu_code from access_menus").fetchall()
        }
        conn.executemany(
            """
            insert into access_menus (
                menu_code, parent_code, menu_name, menu_type, path, component,
                permission_code, sort_order, is_hidden
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(menu_code) do update set
                parent_code = excluded.parent_code,
                menu_name = excluded.menu_name,
                menu_type = excluded.menu_type,
                path = excluded.path,
                component = excluded.component,
                permission_code = excluded.permission_code,
                sort_order = excluded.sort_order,
                is_hidden = excluded.is_hidden
            """,
            (
                (
                    menu["code"], menu["parent_code"], menu["name"], menu["menu_type"],
                    menu["path"], menu["component"], menu["permission"], menu["order"], int(menu["hidden"]),
                )
                for menu in MENU_DEFINITIONS
            ),
        )
        conn.executemany(
            """
            insert into access_roles (role_code, role_name, description, is_system)
            values (?, ?, ?, 1)
            on conflict(role_code) do update set
                role_name = excluded.role_name,
                description = excluded.description,
                is_system = 1
            """,
            (
                ("super_admin", "超级管理员", "管理全部业务、数据管理和系统设置。"),
                ("admin", "管理员", "访问全部业务功能，负责日常账号和运营协作。"),
                ("operations_supervisor", "运营主管", "查看并跟进全部业务经营数据。"),
                ("store_manager", "运营店长", "负责授权店铺的日常经营分析。"),
                ("operator", "运营", "负责授权店铺的日常运营工作。"),
            ),
        )
        business_permissions = ["analytics.read", "warehouse.read", "brand_assets.read"]
        role_permissions = {
            "super_admin": [
                *business_permissions, "imports.read", "imports.manage", "captures.read", "contracts.read",
                "operations.read", "system.read", "access.manage", "data.manage", "system.manage",
            ],
            "admin": business_permissions,
            "operations_supervisor": business_permissions,
            "store_manager": business_permissions,
            "operator": business_permissions,
        }
        for role_code, permissions in role_permissions.items():
            existing_permissions = conn.execute(
                "select 1 from access_role_permissions where role_code = ? limit 1",
                (role_code,),
            ).fetchone()
            if existing_permissions is None:
                conn.executemany(
                    "insert into access_role_permissions (role_code, permission_code) values (?, ?)",
                    ((role_code, permission_code) for permission_code in permissions),
                )
        # Bootstrap grants for a new role, and grant newly introduced catalog
        # entries once during upgrades. Existing explicit removals stay
        # untouched on subsequent application starts.
        new_menu_codes = {menu["code"] for menu in MENU_DEFINITIONS} - existing_menu_codes
        for role_code in role_permissions:
            existing = conn.execute(
                "select 1 from access_role_menus where role_code = ? limit 1",
                (role_code,),
            ).fetchone()
            if existing is not None and not new_menu_codes:
                continue
            permission_set = {
                str(row["permission_code"])
                for row in conn.execute(
                    "select permission_code from access_role_permissions where role_code = ?",
                    (role_code,),
                ).fetchall()
            }
            candidates = MENU_DEFINITIONS if existing is None else (
                menu for menu in MENU_DEFINITIONS if menu["code"] in new_menu_codes
            )
            menu_codes = {
                menu["code"]
                for menu in candidates
                if menu["permission"] in permission_set or role_code == "super_admin"
            }
            parent_codes = {
                menu["parent_code"]
                for menu in MENU_DEFINITIONS
                if menu["code"] in menu_codes and menu["parent_code"] is not None
            }
            conn.executemany(
                "insert or ignore into access_role_menus (role_code, menu_code) values (?, ?)",
                ((role_code, menu_code) for menu_code in sorted(menu_codes | parent_codes)),
            )
        split_data_menu_migration = "20260822_split_data_management_menus"
        if conn.execute(
            "select 1 from access_schema_migrations where migration_code = ?",
            (split_data_menu_migration,),
        ).fetchone() is None:
            split_data_menu_codes = (
                "route:imports-tasks",
                "route:imports-overview",
                "route:imports-settings",
            )
            roles_with_data_access = [
                str(row["role_code"])
                for row in conn.execute(
                    """
                    select role_code from access_role_permissions
                    where permission_code = 'data.manage'
                    union select 'super_admin'
                    """
                ).fetchall()
            ]
            conn.executemany(
                "insert or ignore into access_role_menus (role_code, menu_code) values (?, ?)",
                (
                    (role_code, menu_code)
                    for role_code in roles_with_data_access
                    for menu_code in ("domain:data", *split_data_menu_codes)
                ),
            )
            conn.execute(
                "insert into access_schema_migrations (migration_code, applied_at) values (?, datetime('now'))",
                (split_data_menu_migration,),
            )
        # Older local databases used these role codes. Migrate existing users
        # while still accepting them as input aliases in the access service.
        conn.execute(
            "insert or ignore into access_user_roles (user_id, role_code) select user_id, 'operations_supervisor' from access_user_roles where role_code = 'business_manager'"
        )
        conn.execute(
            "insert or ignore into access_user_roles (user_id, role_code) select user_id, 'operator' from access_user_roles where role_code = 'viewer'"
        )
        conn.execute("delete from access_user_roles where role_code in ('business_manager', 'viewer')")
        conn.execute("delete from access_role_permissions where role_code in ('business_manager', 'viewer')")
        conn.execute("delete from access_roles where role_code in ('business_manager', 'viewer')")

    @staticmethod
    def _repair_orphaned_platforms(conn: sqlite3.Connection) -> None:
        """Restore platform rows left behind by the earlier identity migration."""
        rows = conn.execute(
            f"""
            select distinct s.{q(PLATFORM_ID)} as platform_id
            from stores s
            left join platforms p on p.{q(PLATFORM_ID)} = s.{q(PLATFORM_ID)}
            where p.{q(PLATFORM_ID)} is null
            """
        ).fetchall()
        if not rows:
            return

        now = datetime.now().astimezone().isoformat(timespec="seconds")
        for row in rows:
            platform_id = int(row["platform_id"])
            code = "tmall" if platform_id == 1 else f"platform_{platform_id}"
            name = "天猫" if platform_id == 1 else f"平台 {platform_id}"
            conn.execute(
                f"""
                insert into platforms (
                    {q(PLATFORM_ID)}, {q(PLATFORM_CODE)}, {q(PLATFORM_NAME)},
                    {q(STATUS)}, {q(CREATED_AT)}, {q(UPDATED_AT)}
                ) values (?, ?, ?, ?, ?, ?)
                """,
                (platform_id, code, name, "active", now, now),
            )

    @staticmethod
    def _repair_crawl_ledger_foreign_keys(conn: sqlite3.Connection) -> None:
        """Repoint ledger foreign keys after identity tables are rebuilt."""
        if not LocalDatabase._table_exists(conn, "crawl_runs"):
            return
        references = {
            str(row["table"])
            for row in conn.execute('pragma foreign_key_list("crawl_runs")').fetchall()
        }
        if "stores__legacy_identity" not in references:
            return

        legacy_days = "crawl_run_days__legacy_fk"
        legacy_runs = "crawl_runs__legacy_fk"
        conn.execute(f'alter table "crawl_run_days" rename to "{legacy_days}"')
        conn.execute(f'alter table "crawl_runs" rename to "{legacy_runs}"')
        conn.execute(
            f"""
            create table crawl_runs (
                {q(CRAWL_RUN_ID)} text primary key,
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
                {q(CRAWL_TASK_TYPE)} text not null,
                {q(START_DAY)} text not null,
                {q(END_DAY)} text not null,
                {q(RUN_MODE)} text not null,
                {q(RUN_STATUS)} text not null,
                {q(PLANNED_DAYS)} integer not null,
                {q(SUCCESS_DAYS)} integer not null,
                {q(SKIPPED_DAYS)} integer not null,
                {q(FAILED_DAYS)} integer not null,
                {q(STARTED_AT)} text not null,
                {q(FINISHED_AT)} text,
                {q(LOG_FILE)} text not null
            )
            """
        )
        conn.execute(
            f"""
            create table crawl_run_days (
                {q(ITEM_DAY_ID)} integer primary key autoincrement,
                {q(CRAWL_RUN_ID)} text not null references crawl_runs({q(CRAWL_RUN_ID)}) on delete cascade,
                {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
                {q(BUSINESS_DAY)} text not null,
                {q(DAY_STATUS)} text not null,
                {q(METRIC_COUNT)} integer,
                {q(ERROR_MESSAGE)} text,
                unique({q(CRAWL_RUN_ID)}, {q(BUSINESS_DAY)})
            )
            """
        )
        run_columns = [
            CRAWL_RUN_ID,
            STORE_ID,
            CRAWL_TASK_TYPE,
            START_DAY,
            END_DAY,
            RUN_MODE,
            RUN_STATUS,
            PLANNED_DAYS,
            SUCCESS_DAYS,
            SKIPPED_DAYS,
            FAILED_DAYS,
            STARTED_AT,
            FINISHED_AT,
            LOG_FILE,
        ]
        conn.execute(
            f"insert into crawl_runs ({', '.join(q(column) for column in run_columns)}) "
            f"select {', '.join(q(column) for column in run_columns)} from \"{legacy_runs}\""
        )
        day_columns = [
            ITEM_DAY_ID,
            CRAWL_RUN_ID,
            STORE_ID,
            BUSINESS_DAY,
            DAY_STATUS,
            METRIC_COUNT,
            ERROR_MESSAGE,
        ]
        conn.execute(
            f"insert into crawl_run_days ({', '.join(q(column) for column in day_columns)}) "
            f"select {', '.join(q(column) for column in day_columns)} from \"{legacy_days}\""
        )
        conn.execute(f'drop table "{legacy_days}"')
        conn.execute(f'drop table "{legacy_runs}"')

    @staticmethod
    def _repair_identity_foreign_keys(conn: sqlite3.Connection) -> None:
        """Repair child foreign keys left behind by an interrupted identity rebuild."""
        legacy_store_targets = {
            "stores__legacy_identity",
            "stores__foreign_key_repair",
        }
        legacy_platform_targets = {
            "platforms__legacy_identity",
            "platforms__foreign_key_repair",
        }

        def foreign_targets(table: str) -> set[str]:
            return {
                str(row["table"])
                for row in conn.execute(f'pragma foreign_key_list("{table}")').fetchall()
            }

        tables = [
            str(row["name"])
            for row in conn.execute(
                "select name from sqlite_master where type = 'table' and name not like 'sqlite_%'"
            ).fetchall()
        ]
        has_invalid_reference = any(
            foreign_targets(table) & (legacy_store_targets | legacy_platform_targets)
            for table in tables
        )
        if not has_invalid_reference:
            return

        store_sql = conn.execute(
            "select sql from sqlite_master where type = 'table' and name = 'stores'"
        ).fetchone()
        if store_sql is None:
            raise sqlite3.OperationalError("Cannot repair identity foreign keys without stores.")

        replacements = {
            "platforms__legacy_identity": "platforms",
            "platforms__foreign_key_repair": "platforms",
            "stores__legacy_identity": "stores",
            "stores__foreign_key_repair": "stores",
            "crawl_runs__foreign_key_repair": "crawl_runs",
        }

        def repaired_sql(sql: str) -> str:
            for legacy, current in replacements.items():
                sql = sql.replace(f'"{legacy}"', f'"{current}"')
                sql = sql.replace(legacy, current)
            return sql

        def rebuild(table: str) -> None:
            table_sql_row = conn.execute(
                "select sql from sqlite_master where type = 'table' and name = ?",
                (table,),
            ).fetchone()
            if table_sql_row is None:
                return
            columns = LocalDatabase._columns(conn, table)
            legacy = f"{table}__foreign_key_repair"
            if LocalDatabase._table_exists(conn, legacy):
                raise sqlite3.OperationalError(
                    f"Cannot repair identity foreign keys; temporary table already exists: {legacy}"
                )
            conn.execute(f'alter table "{table}" rename to "{legacy}"')
            conn.execute(repaired_sql(str(table_sql_row["sql"])))
            conn.execute(
                f"""
                insert into "{table}" ({", ".join(q(column) for column in columns)})
                select {", ".join(q(column) for column in columns)}
                from "{legacy}"
                """
            )
            conn.execute(f'drop table "{legacy}"')

        rebuild("stores")
        LocalDatabase._repair_orphaned_platforms(conn)

        # Parent tables must be rebuilt before their dependent ledger tables.
        ordered_tables = [
            "raw_response_artifacts",
            PRODUCT_CATALOG_TABLE,
            "store_daily_overviews",
            "store_daily_customer_overviews",
            "store_daily_traffic_sources",
            "store_daily_member_channels",
            "store_daily_member_analysis_overviews",
            "store_activity_calendar_events",
            "store_daily_new_customer_discount_overviews",
            "store_daily_customer_service_accounts",
            PRODUCT_RANKING_TABLE,
            *DIMENSION_DAILY_FACT_TABLES,
            *SIMPLE_DAILY_FACT_TABLES,
            "crawl_runs",
            "crawl_run_days",
        ]
        # Keep the known parent-before-child order, then include tables added
        # by later modules (for example access and brand scope tables). Older
        # interrupted migrations can leave any child table pointing at the
        # temporary identity table, so the repair must not depend on a fixed
        # hand-maintained list.
        known_tables = set(ordered_tables)
        all_tables = [
            str(row["name"])
            for row in conn.execute(
                "select name from sqlite_master where type = 'table' and name not like 'sqlite_%'"
            ).fetchall()
        ]
        ordered_tables.extend(table for table in all_tables if table not in known_tables and table != "stores")
        for table in ordered_tables:
            if not LocalDatabase._table_exists(conn, table):
                continue
            if foreign_targets(table) & legacy_store_targets or (
                table == "crawl_run_days"
                and "crawl_runs__foreign_key_repair" in foreign_targets(table)
            ):
                rebuild(table)

        for legacy_table in ("platforms__legacy_identity", "platforms__foreign_key_repair"):
            if not LocalDatabase._table_exists(conn, legacy_table):
                continue
            still_referenced = any(
                legacy_table in foreign_targets(table)
                for table in [
                    str(row["name"])
                    for row in conn.execute(
                        "select name from sqlite_master where type = 'table' and name not like 'sqlite_%'"
                    ).fetchall()
                ]
            )
            if not still_referenced:
                conn.execute(f'drop table "{legacy_table}"')

    @staticmethod
    def _normalize_live_overview_business_days(conn: sqlite3.Connection) -> None:
        """Keep the live overview's daily key in the same YYYY-MM-DD format as other facts."""
        table = "store_daily_live_overviews"
        if not LocalDatabase._table_exists(conn, table):
            return
        rows = conn.execute(
            f"""
            select {q(STORE_ID)} as store_id, {q(BUSINESS_DAY)} as business_day
            from {table}
            where {q(BUSINESS_DAY)} glob '????-??-??T*'
            """
        ).fetchall()
        for row in rows:
            store_id = row[0]
            business_day = row[1]
            normalized_day = str(business_day)[:10]
            exists = conn.execute(
                f"""
                select 1 from {table}
                where {q(STORE_ID)} = ? and {q(BUSINESS_DAY)} = ?
                """,
                (store_id, normalized_day),
            ).fetchone()
            if exists is not None:
                conn.execute(
                    f"delete from {table} where {q(STORE_ID)} = ? and {q(BUSINESS_DAY)} = ?",
                    (store_id, business_day),
                )
                continue
            conn.execute(
                f"update {table} set {q(BUSINESS_DAY)} = ? "
                f"where {q(STORE_ID)} = ? and {q(BUSINESS_DAY)} = ?",
                (normalized_day, store_id, business_day),
            )

    @staticmethod
    def _migrate_table(
        conn: sqlite3.Connection,
        table: str,
        create_sql: str,
        chinese_columns: set[str],
        copy_sql: str,
    ) -> None:
        columns = LocalDatabase._columns(conn, table)
        if not columns:
            conn.execute(create_sql)
            return
        legacy = f"{table}__legacy_en"
        if LocalDatabase._table_exists(conn, legacy):
            current_count = int(conn.execute(f'select count(*) from "{table}"').fetchone()[0])
            legacy_count = int(conn.execute(f'select count(*) from "{legacy}"').fetchone()[0])
            if current_count == 0 and legacy_count > 0:
                if table == "store_daily_overviews":
                    LocalDatabase._copy_daily_overview_from_legacy(conn, legacy)
                elif table == "store_daily_traffic_sources":
                    LocalDatabase._copy_traffic_sources_from_partial_legacy(conn, legacy)
                else:
                    LocalDatabase._copy_matching_columns_from_partial_legacy(conn, table, legacy)
                conn.execute(f'drop table "{legacy}"')
                columns = LocalDatabase._columns(conn, table)
        renamed_columns = {
            "store_daily_member_analysis_overviews": {
                MEMBER_CORE_REPURCHASE_RATE: LEGACY_MEMBER_CORE_REPURCHASE_RATE,
            },
        }
        for current_column, legacy_column in renamed_columns.get(table, {}).items():
            if current_column not in columns and legacy_column in columns:
                conn.execute(
                    f'alter table "{table}" rename column {q(legacy_column)} to {q(current_column)}'
                )
                columns = LocalDatabase._columns(conn, table)
        if chinese_columns.issubset(columns):
            return

        if LocalDatabase._table_exists(conn, legacy):
            conn.execute(f'drop table "{legacy}"')
        conn.execute(f'alter table "{table}" rename to "{legacy}"')
        conn.execute(create_sql)
        if table == "store_daily_overviews":
            LocalDatabase._copy_daily_overview_from_legacy(conn, legacy)
        elif table == "store_daily_traffic_sources":
            # Traffic-source tables existed in two Chinese schemas during the
            # migration from the English warehouse names.  The historical
            # schema used ``成交转化率`` while the current public name is
            # ``支付转化率``; copy by the known aliases instead of executing
            # the old English-column INSERT template.
            LocalDatabase._copy_traffic_sources_from_partial_legacy(conn, legacy)
        elif table in SIMPLE_DAILY_FACT_TABLES:
            LocalDatabase._copy_simple_daily_fact_from_legacy(
                conn,
                table,
                legacy,
                SIMPLE_DAILY_FACT_TABLES[table],
            )
        elif table == "store_daily_customer_service_accounts":
            LocalDatabase._copy_customer_service_accounts_from_legacy(
                conn,
                legacy,
            )
        else:
            conn.execute(copy_sql.format(legacy=legacy))
        conn.execute(f'drop table "{legacy}"')

    @staticmethod
    def _copy_matching_columns_from_partial_legacy(
        conn: sqlite3.Connection,
        table: str,
        legacy: str,
    ) -> None:
        target_columns = LocalDatabase._columns(conn, table)
        legacy_columns = LocalDatabase._columns(conn, legacy)
        matching_columns = [column for column in target_columns if column in legacy_columns]
        if STORE_ID not in matching_columns or BUSINESS_DAY not in matching_columns:
            return
        joined = ", ".join(q(column) for column in matching_columns)
        conn.execute(
            f'insert or ignore into "{table}" ({joined}) select {joined} from "{legacy}"'
        )

    @staticmethod
    def _copy_traffic_sources_from_partial_legacy(
        conn: sqlite3.Connection,
        legacy: str,
    ) -> None:
        target_columns = LocalDatabase._columns(conn, "store_daily_traffic_sources")
        legacy_columns = LocalDatabase._columns(conn, legacy)
        aliases = {
            CONVERSION_RATE: (CONVERSION_RATE, "支付转化率", "成交转化率"),
        }
        select_columns: list[str] = []
        for target_column in target_columns:
            source_column = next(
                (
                    candidate
                    for candidate in aliases.get(target_column, (target_column,))
                    if candidate in legacy_columns
                ),
                None,
            )
            if source_column is None:
                return
            select_columns.append(q(source_column))
        conn.execute(
            f'''
            insert or ignore into store_daily_traffic_sources (
                {", ".join(q(column) for column in target_columns)}
            )
            select {", ".join(select_columns)}
            from "{legacy}"
            '''
        )

    @staticmethod
    def _copy_daily_overview_from_legacy(
        conn: sqlite3.Connection,
        legacy: str,
    ) -> None:
        legacy_columns = LocalDatabase._columns(conn, legacy)
        if not legacy_columns:
            return

        target_columns = list(DAILY_OVERVIEW_COLUMNS)
        select_columns: list[str] = []
        for target_column in target_columns:
            source_column = next(
                (
                    candidate
                    for candidate in DAILY_OVERVIEW_LEGACY_ALIASES.get(
                        target_column,
                        (target_column,),
                    )
                    if candidate in legacy_columns
                ),
                None,
            )
            if source_column is None and target_column in {STORE_ID, BUSINESS_DAY}:
                return
            if source_column is None:
                select_columns.append(f"'0' as {q(target_column)}")
            elif target_column == STORE_ID:
                select_columns.append(
                    f"cast({q(source_column)} as integer) as {q(target_column)}"
                )
            else:
                select_columns.append(
                    f"coalesce({q(source_column)}, '0') as {q(target_column)}"
                )

        conn.execute(
            f"""
            insert or replace into store_daily_overviews (
                {", ".join(q(column) for column in target_columns)}
            )
            select {", ".join(select_columns)}
            from "{legacy}"
            """
        )

    @staticmethod
    def _copy_simple_daily_fact_from_legacy(
        conn: sqlite3.Connection,
        table: str,
        legacy: str,
        target_columns: tuple[str, ...],
    ) -> None:
        legacy_columns = LocalDatabase._columns(conn, legacy)
        aliases = SIMPLE_DAILY_FACT_LEGACY_ALIASES.get(table, {})
        select_columns: list[str] = []
        for target_column in target_columns:
            source_column = next(
                (
                    candidate
                    for candidate in aliases.get(
                        target_column,
                        (target_column,),
                    )
                    if candidate in legacy_columns
                ),
                None,
            )
            if source_column is None and target_column in {STORE_ID, BUSINESS_DAY}:
                return
            if source_column is None:
                select_columns.append(f"null as {q(target_column)}")
            elif target_column == STORE_ID:
                select_columns.append(
                    f"cast({q(source_column)} as integer) as {q(target_column)}"
                )
            else:
                select_columns.append(f"{q(source_column)} as {q(target_column)}")

        conn.execute(
            f"""
            insert or replace into {table} (
                {", ".join(q(column) for column in target_columns)}
            )
            select {", ".join(select_columns)}
            from "{legacy}"
            """
        )

    @staticmethod
    def _copy_customer_service_accounts_from_legacy(
        conn: sqlite3.Connection,
        legacy: str,
    ) -> None:
        legacy_columns = LocalDatabase._columns(conn, legacy)
        select_columns: list[str] = []
        for target_column in CUSTOMER_SERVICE_ACCOUNT_COLUMNS:
            source_column = next(
                (
                    candidate
                    for candidate in CUSTOMER_SERVICE_ACCOUNT_LEGACY_ALIASES.get(
                        target_column,
                        (target_column,),
                    )
                    if candidate in legacy_columns
                ),
                None,
            )
            if source_column is None and target_column in {
                STORE_ID,
                BUSINESS_DAY,
                CUSTOMER_SERVICE_ACCOUNT_NICK,
            }:
                return
            if source_column is None:
                select_columns.append(f"null as {q(target_column)}")
            elif target_column == STORE_ID:
                select_columns.append(
                    f"cast({q(source_column)} as integer) as {q(target_column)}"
                )
            else:
                select_columns.append(f"{q(source_column)} as {q(target_column)}")

        conn.execute(
            f"""
            insert or replace into store_daily_customer_service_accounts (
                {", ".join(q(column) for column in CUSTOMER_SERVICE_ACCOUNT_COLUMNS)}
            )
            select {", ".join(select_columns)}
            from "{legacy}"
            """
        )

    @staticmethod
    def _rebuild_business_fact_tables_if_needed(conn: sqlite3.Connection) -> None:
        definitions = [
            (
                "store_daily_overviews",
                list(DAILY_OVERVIEW_COLUMNS),
            ),
            (
                "store_daily_customer_overviews",
                [STORE_ID, BUSINESS_DAY] + [column for column, _ in CUSTOMER_OVERVIEW_FIELDS],
            ),
            (
                "store_daily_traffic_sources",
                [
                    STORE_ID,
                    BUSINESS_DAY,
                    TRAFFIC_SOURCE_LEVEL_1,
                    TRAFFIC_SOURCE_LEVEL_2,
                    TRAFFIC_SOURCE_LEVEL_3,
                    SOURCE_LEVEL,
                    VISITORS,
                    NEW_VISITORS,
                    ADD_CART_BUYERS,
                    PRODUCT_FAVORITE_BUYERS,
                    PAID_BUYERS,
                    CONVERSION_RATE,
                    PAID_AMOUNT,
                    PAID_AMOUNT_SHARE,
                    UV_VALUE,
                    ORDER_BUYERS,
                    ORDER_AMOUNT,
                    ORDER_CONVERSION_RATE,
                ],
            ),
            (
                "store_daily_member_channels",
                [
                    STORE_ID,
                    BUSINESS_DAY,
                    MEMBER_CHANNEL_NAME,
                    MEMBER_NEW_COUNT,
                    MEMBER_NEW_PAID_COUNT,
                    MEMBER_RECRUIT_CONVERSION_RATE,
                    MEMBER_NEW_PAID_AMOUNT,
                    MEMBER_NEW_UNIT_PRICE,
                ],
            ),
            (
                "store_daily_member_analysis_overviews",
                [STORE_ID, BUSINESS_DAY] + [column for column, _ in MEMBER_ANALYSIS_OVERVIEW_FIELDS],
            ),
            (
                "store_activity_calendar_events",
                [STORE_ID, BUSINESS_DAY] + list(ACTIVITY_CALENDAR_COLUMNS[2:]),
            ),
            (
                "store_daily_new_customer_discount_overviews",
                list(NEW_CUSTOMER_DISCOUNT_COLUMNS),
            ),
            *[
                (table, list(columns))
                for table, columns in SIMPLE_DAILY_FACT_TABLES.items()
            ],
            (
                "store_daily_customer_service_accounts",
                list(CUSTOMER_SERVICE_ACCOUNT_COLUMNS),
            ),
            (PRODUCT_RANKING_TABLE, list(PRODUCT_RANKING_COLUMNS)),
        ]

        for table, columns in definitions:
            current = LocalDatabase._columns(conn, table)
            if not current or current == set(columns):
                continue
            legacy = f"{table}__legacy_trim"
            if LocalDatabase._table_exists(conn, legacy):
                conn.execute(f'drop table "{legacy}"')
            conn.execute(f'alter table "{table}" rename to "{legacy}"')
            if table == "store_daily_overviews":
                conn.execute(_daily_overview_create_sql(if_not_exists=False))
                LocalDatabase._copy_daily_overview_from_legacy(conn, legacy)
                conn.execute(f'drop table "{legacy}"')
                continue
            if table == "store_daily_customer_overviews":
                conn.execute(
                    """
                    create table store_daily_customer_overviews (
                        "店铺ID" integer not null references stores("店铺ID"),
                        "业务日期" text not null,
                        "店铺客户数" text,
                        "客户新访" text,
                        "新访成交" text,
                        "新访未成交" text,
                        "新访支付转化率" text,
                        "新访支付金额占比" text,
                        "新访客单价" text,
                        "新访粉丝占比" text,
                        "新访会员占比" text,
                        "新访潜客召回率" text,
                        "未购客户回访" text,
                        "回访成交" text,
                        "回访未成交" text,
                        "未购回访支付转化率" text,
                        "未购回访支付金额占比" text,
                        "未购回访客单价" text,
                        "未购回访粉丝占比" text,
                        "未购回访会员占比" text,
                        "未购客户召回率" text,
                        "未购回访成交率" text,
                        "已购客户回访" text,
                        "老客复购" text,
                        "老客未复购" text,
                        "已购回访支付转化率" text,
                        "已购回访支付金额占比" text,
                        "老客复购客单价" text,
                        "已购回访粉丝占比" text,
                        "已购回访会员占比" text,
                        "已购客户召回率" text,
                        "老客复购率" text,
                        primary key("店铺ID", "业务日期")
                    )
                    """
                )
            elif table == "store_daily_traffic_sources":
                conn.execute(
                    """
                    create table store_daily_traffic_sources (
                        "店铺ID" integer not null references stores("店铺ID"),
                        "业务日期" text not null,
                        "一级来源" text not null,
                        "二级来源" text not null,
                        "三级来源" text not null,
                        "来源层级" integer not null,
                        "访客数" text not null,
                        "新访客数" text not null,
                        "加购人数" text not null,
                        "商品收藏人数" text not null,
                        "支付买家数" text not null,
                        "支付转化率" text not null,
                        "支付金额" text not null,
                        "支付金额占比" text not null,
                        "UV价值" text not null,
                        "下单买家数" text not null,
                        "下单金额" text not null,
                        "下单转化率" text not null,
                        primary key("店铺ID", "业务日期", "来源层级", "一级来源", "二级来源", "三级来源")
                    )
                    """
                )
                LocalDatabase._copy_traffic_sources_from_legacy(conn, legacy)
                conn.execute(f'drop table "{legacy}"')
                continue
            elif table == "store_daily_member_channels":
                conn.execute(
                    """
                    create table store_daily_member_channels (
                        "店铺ID" integer not null references stores("店铺ID"),
                        "业务日期" text not null,
                        "入会渠道" text not null,
                        "新增会员数" text not null,
                        "新会员成交人数" text not null,
                        "招募转化率" text not null,
                        "新会员成交金额" text not null,
                        "新会员客单价" text not null,
                        primary key("店铺ID", "业务日期", "入会渠道")
                    )
                    """
                )
            elif table == "store_activity_calendar_events":
                conn.execute(
                    """
                    create table store_activity_calendar_events (
                        "店铺ID" integer not null references stores("店铺ID"),
                        "业务日期" text not null,
                        "活动ID" text not null,
                        "活动名称" text not null,
                        "活动类型" text not null,
                        "活动状态" text not null,
                        "活动开始时间" text not null,
                        "活动结束时间" text not null,
                        "报名开始时间" text not null,
                        "报名结束时间" text not null,
                        "活动标签" text not null,
                        "活动层级" text not null,
                        "活动阶段" text not null,
                        "店铺参与状态" text not null,
                        primary key("店铺ID", "业务日期", "活动ID")
                    )
                    """
                )
            elif table == "store_daily_new_customer_discount_overviews":
                conn.execute(_new_customer_discount_create_sql(if_not_exists=False))
            elif table in SIMPLE_DAILY_FACT_TABLES:
                conn.execute(
                    _simple_daily_fact_create_sql(
                        table,
                        SIMPLE_DAILY_FACT_TABLES[table],
                        if_not_exists=False,
                    )
                )
            elif table == "store_daily_customer_service_accounts":
                conn.execute(
                    _customer_service_accounts_create_sql(if_not_exists=False)
                )
            elif table == PRODUCT_RANKING_TABLE:
                conn.execute(_product_ranking_create_sql(if_not_exists=False))
            else:
                conn.execute(
                    """
                    create table store_daily_member_analysis_overviews (
                        "店铺ID" integer not null references stores("店铺ID"),
                        "业务日期" text not null,
                        "会员总数" text,
                        "会员成交人数" text,
                        "会员成交金额" text,
                        "会员客单价" text,
                        "会员复购率" text,
                        "高频复购会员" text,
                        "高频复购成交金额占比" text,
                        "高频复购本店占比" text,
                        "高频复购同行占比" text,
                        "2单复购会员" text,
                        "2单复购成交金额占比" text,
                        "2单复购本店占比" text,
                        "2单复购同行占比" text,
                        "首购会员" text,
                        "首购成交金额占比" text,
                        "首购本店占比" text,
                        "首购同行占比" text,
                        "活跃未购会员" text,
                        "活跃未购本店占比" text,
                        "活跃未购同行占比" text,
                        "沉默会员" text,
                        "沉默会员本店占比" text,
                        "沉默会员同行占比" text,
                        "复购会员数" text,
                        "会员复购金额" text,
                        "复购订单数" text,
                        "复购会员客单价" text,
                        "复购周期" text,
                        "复购页会员复购率" text,
                        "人均复购笔数" text,
                        "新增会员数" text,
                        "新会员成交人数" text,
                        "招募转化率" text,
                        "新会员成交金额" text,
                        "新会员客单价" text,
                        "老客入会人数" text,
                        primary key("店铺ID", "业务日期")
                    )
                    """
                )
            renamed_columns = {
                "store_daily_member_analysis_overviews": {
                    MEMBER_CORE_REPURCHASE_RATE: LEGACY_MEMBER_CORE_REPURCHASE_RATE,
                },
            }
            select_columns = []
            for column in columns:
                legacy_column = renamed_columns.get(table, {}).get(column)
                if column in current:
                    select_columns.append(q(column))
                elif legacy_column and legacy_column in current:
                    select_columns.append(f"{q(legacy_column)} as {q(column)}")
                else:
                    select_columns.append(f"null as {q(column)}")
            conn.execute(
                f"""
                insert into "{table}" ({", ".join(q(column) for column in columns)})
                select {", ".join(select_columns)}
                from "{legacy}"
                """
            )
            conn.execute(f'drop table "{legacy}"')

    @staticmethod
    def _repair_promotion_bidword_primary_key(conn: sqlite3.Connection) -> None:
        """Keep keyword-package and match-mode rows distinct.

        Older databases keyed a keyword only by its ID and type. The live
        report can return the same keyword ID for multiple packages or match
        modes, so that key silently discarded valid rows during ingestion.
        """
        table = PROMOTION_BIDWORD_TABLE
        if not LocalDatabase._table_exists(conn, table):
            return
        primary_key = {
            str(row[1])
            for row in conn.execute(f'pragma table_info({q(table)})').fetchall()
            if int(row[5] or 0) > 0
        }
        required = {
            PROMOTION_BIDWORD_PACKAGE_ID,
            PROMOTION_AUTOMATCH_TYPE,
        }
        if required.issubset(primary_key):
            return

        legacy = f"{table}__legacy_bidword_key"
        if LocalDatabase._table_exists(conn, legacy):
            conn.execute(f'drop table {q(legacy)}')
        conn.execute(f'alter table {q(table)} rename to {q(legacy)}')
        conn.execute(
            _dimension_daily_fact_create_sql(
                table,
                PROMOTION_BIDWORD_COLUMNS,
                PROMOTION_BIDWORD_DIMENSIONS,
                DIMENSION_DAILY_FACT_TABLES[table][2],
                if_not_exists=False,
            )
        )
        quoted_columns = ", ".join(q(column) for column in PROMOTION_BIDWORD_COLUMNS)
        conn.execute(
            f'insert into {q(table)} ({quoted_columns}) '
            f'select {quoted_columns} from {q(legacy)}'
        )
        conn.execute(f'drop table {q(legacy)}')

    @staticmethod
    def _copy_traffic_sources_from_legacy(conn: sqlite3.Connection, legacy: str) -> None:
        legacy_columns = LocalDatabase._columns(conn, legacy)
        required_columns = {
            STORE_ID,
            BUSINESS_DAY,
            TRAFFIC_SOURCE_LEVEL_1,
            TRAFFIC_SOURCE_LEVEL_2,
            TRAFFIC_SOURCE_LEVEL_3,
            SOURCE_LEVEL,
            VISITORS,
            NEW_VISITORS,
            ADD_CART_BUYERS,
            PRODUCT_FAVORITE_BUYERS,
            PAID_BUYERS,
            PAID_AMOUNT,
            PAID_AMOUNT_SHARE,
            ORDER_BUYERS,
            ORDER_AMOUNT,
        }
        if not required_columns.issubset(legacy_columns):
            return

        def total(column: str) -> str:
            return f"sum(cast(coalesce({q(column)}, '0') as real))"

        visitors = total(VISITORS)
        paid_buyers = total(PAID_BUYERS)
        paid_amount = total(PAID_AMOUNT)
        order_buyers = total(ORDER_BUYERS)
        conversion_rate = (
            f"case when {visitors} = 0 then '0' "
            f"else cast(({paid_buyers}) / ({visitors}) as text) end"
        )
        uv_value = (
            f"case when {visitors} = 0 then '0' "
            f"else cast(({paid_amount}) / ({visitors}) as text) end"
        )
        order_conversion_rate = (
            f"case when {visitors} = 0 then '0' "
            f"else cast(({order_buyers}) / ({visitors}) as text) end"
        )

        conn.execute(
            f"""
            insert or replace into store_daily_traffic_sources (
                {q(STORE_ID)}, {q(BUSINESS_DAY)},
                {q(TRAFFIC_SOURCE_LEVEL_1)}, {q(TRAFFIC_SOURCE_LEVEL_2)},
                {q(TRAFFIC_SOURCE_LEVEL_3)}, {q(SOURCE_LEVEL)},
                {q(VISITORS)}, {q(NEW_VISITORS)}, {q(ADD_CART_BUYERS)},
                {q(PRODUCT_FAVORITE_BUYERS)}, {q(PAID_BUYERS)}, {q(CONVERSION_RATE)},
                {q(PAID_AMOUNT)}, {q(PAID_AMOUNT_SHARE)}, {q(UV_VALUE)},
                {q(ORDER_BUYERS)}, {q(ORDER_AMOUNT)}, {q(ORDER_CONVERSION_RATE)}
            )
            select
                cast({q(STORE_ID)} as integer),
                {q(BUSINESS_DAY)},
                {q(TRAFFIC_SOURCE_LEVEL_1)},
                {q(TRAFFIC_SOURCE_LEVEL_2)},
                {q(TRAFFIC_SOURCE_LEVEL_3)},
                {q(SOURCE_LEVEL)},
                cast({total(VISITORS)} as text),
                cast({total(NEW_VISITORS)} as text),
                cast({total(ADD_CART_BUYERS)} as text),
                cast({total(PRODUCT_FAVORITE_BUYERS)} as text),
                cast({total(PAID_BUYERS)} as text),
                {conversion_rate},
                cast({paid_amount} as text),
                cast({total(PAID_AMOUNT_SHARE)} as text),
                {uv_value},
                cast({order_buyers} as text),
                cast({total(ORDER_AMOUNT)} as text),
                {order_conversion_rate}
            from "{legacy}"
            group by
                {q(STORE_ID)}, {q(BUSINESS_DAY)}, {q(SOURCE_LEVEL)},
                {q(TRAFFIC_SOURCE_LEVEL_1)}, {q(TRAFFIC_SOURCE_LEVEL_2)},
                {q(TRAFFIC_SOURCE_LEVEL_3)}
            """
        )

    @staticmethod
    def _rename_legacy_store_subject_column(conn: sqlite3.Connection) -> None:
        columns = LocalDatabase._columns(conn, "stores")
        if LEGACY_STORE_SUBJECT_ID in columns and STORE_SUBJECT_ID not in columns:
            conn.execute(
                f'alter table stores rename column {q(LEGACY_STORE_SUBJECT_ID)} '
                f'to {q(STORE_SUBJECT_ID)}'
            )

    @staticmethod
    def _migrate_identity_ids(conn: sqlite3.Connection) -> None:
        platform_rows = conn.execute(
            f"select {q(PLATFORM_ID)} as platform_id from platforms order by rowid"
        ).fetchall()
        platform_mapping: dict[str, int] = {}
        next_platform_id = 1
        for row in platform_rows:
            old_value = str(row["platform_id"])
            if old_value.isdigit():
                platform_mapping[old_value] = int(old_value)
                next_platform_id = max(next_platform_id, int(old_value) + 1)
            else:
                platform_mapping[old_value] = next_platform_id
                next_platform_id += 1

        for old_value, new_value in platform_mapping.items():
            if old_value == str(new_value):
                continue
            temporary = f"__platform_migrate_{new_value}"
            for table in ("platforms", "stores", "raw_response_artifacts"):
                conn.execute(
                    f'update "{table}" set {q(PLATFORM_ID)} = ? where {q(PLATFORM_ID)} = ?',
                    (temporary, old_value),
                )
            for table in ("platforms", "stores", "raw_response_artifacts"):
                conn.execute(
                    f'update "{table}" set {q(PLATFORM_ID)} = ? where {q(PLATFORM_ID)} = ?',
                    (new_value, temporary),
                )

        store_rows = conn.execute(
            f"select {q(STORE_ID)} as store_id from stores order by rowid"
        ).fetchall()
        store_mapping: dict[str, int] = {}
        next_store_id = 1
        for row in store_rows:
            old_value = str(row["store_id"])
            if old_value.isdigit():
                store_mapping[old_value] = int(old_value)
                next_store_id = max(next_store_id, int(old_value) + 1)
            else:
                store_mapping[old_value] = next_store_id
                next_store_id += 1

        for old_value, new_value in store_mapping.items():
            if old_value == str(new_value):
                continue
            temporary = f"__store_migrate_{new_value}"
            for table in (
                "stores",
                "raw_response_artifacts",
                PRODUCT_CATALOG_TABLE,
                "store_daily_overviews",
                "store_daily_customer_overviews",
                "store_daily_traffic_sources",
                "store_daily_member_channels",
                "store_daily_member_analysis_overviews",
                "store_activity_calendar_events",
                "store_daily_new_customer_discount_overviews",
                "store_daily_customer_service_accounts",
                PRODUCT_RANKING_TABLE,
                *DIMENSION_DAILY_FACT_TABLES,
                "crawl_runs",
                "crawl_run_days",
                *SIMPLE_DAILY_FACT_TABLES,
            ):
                conn.execute(
                    f'update "{table}" set {q(STORE_ID)} = ? where {q(STORE_ID)} = ?',
                    (temporary, old_value),
                )
            for table in (
                "stores",
                "raw_response_artifacts",
                PRODUCT_CATALOG_TABLE,
                "store_daily_overviews",
                "store_daily_customer_overviews",
                "store_daily_traffic_sources",
                "store_daily_member_channels",
                "store_daily_member_analysis_overviews",
                "store_activity_calendar_events",
                "store_daily_new_customer_discount_overviews",
                "store_daily_customer_service_accounts",
                PRODUCT_RANKING_TABLE,
                *DIMENSION_DAILY_FACT_TABLES,
                "crawl_runs",
                "crawl_run_days",
                *SIMPLE_DAILY_FACT_TABLES,
            ):
                conn.execute(
                    f'update "{table}" set {q(STORE_ID)} = ? where {q(STORE_ID)} = ?',
                    (new_value, temporary),
                )

    @staticmethod
    def _rebuild_identity_tables_if_needed(conn: sqlite3.Connection) -> None:
        """Make legacy text identity columns physically integer-backed."""
        tables = {
            "platforms": {PLATFORM_ID: "INTEGER"},
            "stores": {STORE_ID: "INTEGER", PLATFORM_ID: "INTEGER"},
            "raw_response_artifacts": {PLATFORM_ID: "INTEGER", STORE_ID: "INTEGER"},
            PRODUCT_CATALOG_TABLE: {STORE_ID: "INTEGER"},
            "store_daily_overviews": {STORE_ID: "INTEGER"},
            "store_activity_calendar_events": {STORE_ID: "INTEGER"},
            "store_daily_new_customer_discount_overviews": {STORE_ID: "INTEGER"},
            "store_daily_customer_service_accounts": {STORE_ID: "INTEGER"},
            PRODUCT_RANKING_TABLE: {STORE_ID: "INTEGER"},
            "crawl_runs": {STORE_ID: "INTEGER"},
            "crawl_run_days": {STORE_ID: "INTEGER"},
            **{
                table: {STORE_ID: "INTEGER"}
                for table in SIMPLE_DAILY_FACT_TABLES
            },
            **{
                table: {STORE_ID: "INTEGER"}
                for table in DIMENSION_DAILY_FACT_TABLES
            },
        }
        needs_rebuild = any(
            LocalDatabase._column_type(conn, table, column).upper() != expected
            for table, columns in tables.items()
            for column, expected in columns.items()
        )
        if not needs_rebuild:
            return

        definitions = [
            (
                "platforms",
                f"""
                create table platforms (
                    {q(PLATFORM_ID)} integer primary key,
                    {q(PLATFORM_CODE)} text not null unique,
                    {q(PLATFORM_NAME)} text not null,
                    {q(STATUS)} text not null,
                    {q(CREATED_AT)} text not null,
                    {q(UPDATED_AT)} text not null
                )
                """,
                f"""
                insert into platforms (
                    {q(PLATFORM_ID)}, {q(PLATFORM_CODE)}, {q(PLATFORM_NAME)},
                    {q(STATUS)}, {q(CREATED_AT)}, {q(UPDATED_AT)}
                )
                select cast({q(PLATFORM_ID)} as integer), {q(PLATFORM_CODE)},
                       {q(PLATFORM_NAME)}, {q(STATUS)}, {q(CREATED_AT)}, {q(UPDATED_AT)}
                from "{{legacy}}"
                """,
            ),
            (
                "stores",
                f"""
                create table stores (
                    {q(STORE_ID)} integer primary key,
                    {q(PLATFORM_ID)} integer not null references platforms({q(PLATFORM_ID)}),
                    {q(STORE_SUBJECT_ID)} text not null,
                    {q(STORE_NAME)} text not null,
                    {q(STATUS)} text not null,
                    {q(FIRST_SEEN_AT)} text not null,
                    {q(UPDATED_AT)} text not null,
                    unique({q(PLATFORM_ID)}, {q(STORE_SUBJECT_ID)})
                )
                """,
                f"""
                insert into stores (
                    {q(STORE_ID)}, {q(PLATFORM_ID)}, {q(STORE_SUBJECT_ID)},
                    {q(STORE_NAME)}, {q(STATUS)}, {q(FIRST_SEEN_AT)}, {q(UPDATED_AT)}
                )
                select cast({q(STORE_ID)} as integer), cast({q(PLATFORM_ID)} as integer),
                       {q(STORE_SUBJECT_ID)}, {q(STORE_NAME)}, {q(STATUS)},
                       {q(FIRST_SEEN_AT)}, {q(UPDATED_AT)}
                from "{{legacy}}"
                """,
            ),
            (
                "raw_response_artifacts",
                f"""
                create table raw_response_artifacts (
                    {q(ARTIFACT_ID)} text primary key,
                    {q(PLATFORM_ID)} integer not null references platforms({q(PLATFORM_ID)}),
                    {q(STORE_ID)} integer not null references stores({q(STORE_ID)}),
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
                """,
                f"""
                insert into raw_response_artifacts (
                    {q(ARTIFACT_ID)}, {q(PLATFORM_ID)}, {q(STORE_ID)}, {q(ENDPOINT_KEY)},
                    {q(BUSINESS_DAY)}, {q(FETCHED_AT)}, {q(HTTP_STATUS)}, {q(RESPONSE_CODE)},
                    {q(SOURCE_FILE)}, {q(CONTENT_SHA256)}, {q(FILE_SIZE)},
                    {q(PARSER_VERSION)}, {q(CREATED_AT)}
                )
                select {q(ARTIFACT_ID)}, cast({q(PLATFORM_ID)} as integer),
                       cast({q(STORE_ID)} as integer), {q(ENDPOINT_KEY)}, {q(BUSINESS_DAY)},
                       {q(FETCHED_AT)}, {q(HTTP_STATUS)}, {q(RESPONSE_CODE)}, {q(SOURCE_FILE)},
                       {q(CONTENT_SHA256)}, {q(FILE_SIZE)}, {q(PARSER_VERSION)}, {q(CREATED_AT)}
                from "{{legacy}}"
                """,
            ),
            (
                "store_daily_overviews",
                _daily_overview_create_sql(if_not_exists=False),
                "",
            ),
            (
                "store_activity_calendar_events",
                _activity_calendar_create_sql(if_not_exists=False),
                f"""
                insert into store_activity_calendar_events (
                    {", ".join(q(column) for column in ACTIVITY_CALENDAR_COLUMNS)}
                )
                select cast({q(STORE_ID)} as integer), {q(BUSINESS_DAY)}, {q(ACTIVITY_ID)},
                       {q(ACTIVITY_NAME)}, {q(ACTIVITY_TYPE)}, {q(ACTIVITY_STATUS)},
                       {q(ACTIVITY_START_TIME)}, {q(ACTIVITY_END_TIME)},
                       {q(SIGNUP_START_TIME)}, {q(SIGNUP_END_TIME)},
                       {q(ACTIVITY_TAG)}, {q(ACTIVITY_LEVEL)}, {q(ACTIVITY_STAGE)},
                       {q(SHOP_PARTICIPATION_STATUS)}
                from "{{legacy}}"
                """,
            ),
            (
                "store_daily_new_customer_discount_overviews",
                _new_customer_discount_create_sql(if_not_exists=False),
                f"""
                insert into store_daily_new_customer_discount_overviews (
                    {", ".join(q(column) for column in NEW_CUSTOMER_DISCOUNT_COLUMNS)}
                )
                select cast({q(STORE_ID)} as integer), {q(BUSINESS_DAY)},
                       {", ".join(q(column) for column in NEW_CUSTOMER_DISCOUNT_COLUMNS[2:])}
                from "{{legacy}}"
                """,
            ),
            (
                "store_daily_customer_service_accounts",
                _customer_service_accounts_create_sql(if_not_exists=False),
                f"""
                insert into store_daily_customer_service_accounts (
                    {", ".join(q(column) for column in CUSTOMER_SERVICE_ACCOUNT_COLUMNS)}
                )
                select cast({q(STORE_ID)} as integer), {q(BUSINESS_DAY)},
                       {", ".join(q(column) for column in CUSTOMER_SERVICE_ACCOUNT_COLUMNS[2:])}
                from "{{legacy}}"
                """,
            ),
            (
                PRODUCT_RANKING_TABLE,
                _product_ranking_create_sql(if_not_exists=False),
                f"""
                insert into {PRODUCT_RANKING_TABLE} (
                    {", ".join(q(column) for column in PRODUCT_RANKING_COLUMNS)}
                )
                select cast({q(STORE_ID)} as integer), {q(BUSINESS_DAY)},
                       {", ".join(q(column) for column in PRODUCT_RANKING_COLUMNS[2:])}
                from "{{legacy}}"
                """,
            ),
        ]
        definitions.extend(
            (
                table,
                _dimension_daily_fact_create_sql(
                    table,
                    columns,
                    dimensions,
                    key_dimensions,
                    if_not_exists=False,
                ),
                f"""
                insert into {table} (
                    {", ".join(q(column) for column in columns)}
                )
                select cast({q(STORE_ID)} as integer),
                       {", ".join(q(column) for column in columns[1:])}
                from "{{legacy}}"
                """,
            )
            for table, (columns, dimensions, key_dimensions) in DIMENSION_DAILY_FACT_TABLES.items()
        )
        definitions.extend(
            (
                table,
                _simple_daily_fact_create_sql(
                    table,
                    columns,
                    if_not_exists=False,
                ),
                f"""
                insert into {table} (
                    {", ".join(q(column) for column in columns)}
                )
                select cast({q(STORE_ID)} as integer), {q(BUSINESS_DAY)},
                       {", ".join(q(column) for column in columns[2:])}
                from "{{legacy}}"
                """,
            )
            for table, columns in SIMPLE_DAILY_FACT_TABLES.items()
        )

        conn.execute('drop index if exists "idx_store_daily_overviews_day"')
        conn.execute('drop index if exists "idx_store_activity_calendar_events_day"')
        conn.execute('drop index if exists "idx_store_daily_new_customer_discount_day"')
        conn.execute(
            'drop index if exists "idx_store_daily_customer_service_accounts_day"'
        )
        conn.execute(
            f'drop index if exists "idx_{PRODUCT_RANKING_TABLE}_day"'
        )
        for table in DIMENSION_DAILY_FACT_TABLES:
            conn.execute(f'drop index if exists "idx_{table}_day"')
        for table in SIMPLE_DAILY_FACT_TABLES:
            conn.execute(f'drop index if exists "idx_{table}_day"')
        for table, create_sql, copy_sql in definitions:
            legacy = f"{table}__legacy_identity"
            if LocalDatabase._table_exists(conn, legacy):
                conn.execute(f'drop table "{legacy}"')
            conn.execute(f'alter table "{table}" rename to "{legacy}"')
            conn.execute(create_sql)
            if table == "store_daily_overviews":
                LocalDatabase._copy_daily_overview_from_legacy(conn, legacy)
            else:
                conn.execute(copy_sql.format(legacy=legacy))
            conn.execute(f'drop table "{legacy}"')

    @staticmethod
    def _recreate_business_views(conn: sqlite3.Connection) -> None:
        # Business facts now live in dedicated wide tables. Keep this hook
        # inert for callers from older maintenance scripts.
        return

        def metric_value_expr(code: str) -> str:
            return (
                f"max(case when m.{q(METRIC_SCOPE)} = 'self' "
                f"and m.{q(METRIC_CODE)} = '{code}' "
                f"then cast(m.{q(METRIC_VALUE)} as real) end)"
            )

        def metric_value(code: str, alias: str) -> str:
            return f"{metric_value_expr(code)} as {q(alias)}"

        def coalesced_metric_value(codes: tuple[str, ...], alias: str) -> str:
            expressions = ", ".join(metric_value_expr(code) for code in codes)
            return f"coalesce({expressions}) as {q(alias)}"

        conn.execute('drop view if exists "store_daily_business_metrics"')
        conn.execute(
            f"""
            create view "store_daily_business_metrics" as
            select
                m.{q(STORE_ID)} as {q(STORE_ID)},
                m.{q(BUSINESS_DAY)} as {q(BUSINESS_DAY)},
                {metric_value("payAmt", PAID_AMOUNT)},
                {metric_value("netPaymentAmount", NET_PAID_AMOUNT)},
                {metric_value("uv", VISITORS)},
                {metric_value("payByrCnt", PAID_BUYERS)},
                {metric_value("payRate", CONVERSION_RATE)},
                {metric_value("realPayrealRfdRate", SIGN_REFUND_RATE)},
                {metric_value("rfdSucAmt", REFUND_FINISHED_AMOUNT)},
                {metric_value("p4pExpendAmt", KEYWORD_PROMOTION_SPEND)},
                {metric_value("cubeAmt", PRECISION_AUDIENCE_PROMOTION_SPEND)},
                {metric_value("feedCharge", SMART_SCENE_SPEND)},
                {metric_value("admCostFamtQzt", ALL_SITE_PROMOTION_SPEND)},
                {metric_value("tkExpendAmt", TAOKE_COMMISSION)},
                {metric_value("subPayOrdAmt", TOTAL_PAID_AMOUNT)},
                {metric_value("payShopRfdAmt", REFUND_PAID_TIME_AMOUNT)},
                {metric_value("payAmtRfdRate", AMOUNT_REFUND_RATE)},
                {metric_value("cartByrCnt", ADD_CART_BUYERS)},
                {metric_value("cltItmCnt", PRODUCT_FAVORITE_BUYERS)},
                {metric_value("pv", PAGE_VIEWS)},
                {metric_value("stayTime", AVERAGE_STAY_TIME)},
                {metric_value("cartItemCnt", ADD_CART_ITEMS)},
                {metric_value("payOrdCnt", PAID_SUB_ORDER_COUNT)},
                {metric_value("subPayOrdSubCnt", TOTAL_PAID_SUB_ORDER_COUNT)},
                {metric_value("ordRfdRate", ORDER_REFUND_RATE)},
                {metric_value("payItmCnt", PAID_ITEMS)},
                {metric_value("payPct", CUSTOMER_UNIT_PRICE)},
                {metric_value("olderPayAmt", OLDER_PAID_AMOUNT)},
                {metric_value("payOldByrCnt", OLDER_PAID_BUYERS)},
                {metric_value("hasPurchaseUbyCntRate", OLDER_REPURCHASE_RATE)},
                {metric_value("rfdFinshDur", REFUND_PROCESS_DAYS)},
                {metric_value("wwReplyManualAvgTimeLen", WANGWANG_MANUAL_RESPONSE_SECONDS)},
                {metric_value("consultRate", CONSULTATION_RATE)},
                {metric_value("disputeDutyRatio", PLATFORM_DUTY_RATE)},
                {metric_value("gotInTime24hRate", PICKUP_24H_RATE)},
                {metric_value("avgSignTimeHh", LOGISTICS_ARRIVAL_HOURS)}
            from store_daily_metrics m
            where m.{q(METRIC_SCOPE)} = 'self'
            group by
                m.{q(STORE_ID)},
                m.{q(BUSINESS_DAY)}
            """
        )

        conn.execute('drop view if exists "store_daily_flow_overview_metrics"')
        conn.execute(
            f"""
            create view "store_daily_flow_overview_metrics" as
            select
                m.{q(STORE_ID)} as {q(STORE_ID)},
                m.{q(BUSINESS_DAY)} as {q(BUSINESS_DAY)},
                {metric_value("flow.uv", VISITORS)},
                {metric_value("flow.itmUv", FLOW_PRODUCT_VISITORS)},
                {metric_value("flow.payByrCnt", PAID_BUYERS)},
                {metric_value("flow.pv", PAGE_VIEWS)},
                {coalesced_metric_value((
                    "flow.bounceRate",
                    "flow.bounceUvRate",
                    "flow.bounceRate1d",
                    "flow.bounceUvRate1d",
                    "flow.avgBounceUvRate",
                    "flow.bounce_uv_rate_1d_002",
                ), FLOW_BOUNCE_RATE)},
                {metric_value("flow.avgPv", FLOW_AVERAGE_PAGE_VIEWS)},
                {coalesced_metric_value((
                    "flow.stayTime",
                    "flow.stayTimeLen",
                    "flow.stay_time_len_1d_001",
                    "stayTime",
                ), AVERAGE_STAY_TIME)},
                {metric_value("flow.oldUv", FLOW_OLD_VISITORS)},
                {metric_value("flow.newUv", FLOW_NEW_VISITORS)},
                {metric_value("flow.shopCltByrCnt", FLOW_FOLLOW_STORE_BUYERS)},
                {metric_value("flow.liveRoomUv", FLOW_LIVE_ROOM_VISITORS)},
                {metric_value("flow.shortVideoUv", FLOW_SHORT_VIDEO_VISITORS)},
                {metric_value("flow.imageUv", FLOW_IMAGE_TEXT_VISITORS)},
                {metric_value("flow.shopVisitUv", FLOW_SHOP_PAGE_VISITORS)}
            from store_daily_metrics m
            where m.{q(METRIC_SCOPE)} = 'self'
              and (m.{q(METRIC_CODE)} like 'flow.%' or m.{q(METRIC_CODE)} = 'stayTime')
            group by
                m.{q(STORE_ID)},
                m.{q(BUSINESS_DAY)}
            having max(case when m.{q(METRIC_CODE)} like 'flow.%' then 1 else 0 end) = 1
            """
        )

        conn.execute('drop view if exists "store_daily_customer_overview_metrics"')
        conn.execute(
            f"""
            create view "store_daily_customer_overview_metrics" as
            select
                m.{q(STORE_ID)} as {q(STORE_ID)},
                m.{q(BUSINESS_DAY)} as {q(BUSINESS_DAY)},
                {metric_value("customer.shopCustomer", CUSTOMER_SHOP_CUSTOMERS)},
                {metric_value("customer.newVisitorCnt", CUSTOMER_NEW_VISITOR_COUNT)},
                {metric_value("customer.newVisitorBuyCnt", CUSTOMER_NEW_VISITOR_BUYERS)},
                {metric_value("customer.newVisitorInShopCnt", CUSTOMER_NEW_VISITOR_IN_SHOP)},
                {metric_value("customer.newVisitorPayRate", CUSTOMER_NEW_VISITOR_PAY_RATE)},
                {metric_value("customer.newVisitorPayAmtRatio", CUSTOMER_NEW_VISITOR_PAY_AMOUNT_RATIO)},
                {metric_value("customer.newVisitorPct", CUSTOMER_NEW_VISITOR_UNIT_PRICE)},
                {metric_value("customer.newVisitorFansRate", CUSTOMER_NEW_VISITOR_FANS_RATE)},
                {metric_value("customer.newVisitorVipRate", CUSTOMER_NEW_VISITOR_VIP_RATE)},
                {metric_value("customer.newVisitorReCall", CUSTOMER_NEW_VISITOR_RECALL_RATE)},
                {metric_value("customer.noPurchaseCnt", CUSTOMER_NO_PURCHASE_COUNT)},
                {metric_value("customer.noPurchaseBuyCnt", CUSTOMER_NO_PURCHASE_BUYERS)},
                {metric_value("customer.noBuyInShopCnt", CUSTOMER_NO_BUY_IN_SHOP)},
                {metric_value("customer.noPurchasePayRate", CUSTOMER_NO_PURCHASE_PAY_RATE)},
                {metric_value("customer.noPurchasePayAmtRatio", CUSTOMER_NO_PURCHASE_PAY_AMOUNT_RATIO)},
                {metric_value("customer.noPurchasePct", CUSTOMER_NO_PURCHASE_UNIT_PRICE)},
                {metric_value("customer.noPurchaseFansRate", CUSTOMER_NO_PURCHASE_FANS_RATE)},
                {metric_value("customer.noPurchaseVipRate", CUSTOMER_NO_PURCHASE_VIP_RATE)},
                {metric_value("customer.noPurchaseReCall", CUSTOMER_NO_PURCHASE_RECALL_RATE)},
                {metric_value("customer.noPurchaseBuyCntRate", CUSTOMER_NO_PURCHASE_BUY_RATE)},
                {metric_value("customer.hasPurchaseCnt", CUSTOMER_HAS_PURCHASE_COUNT)},
                {metric_value("customer.hasPurchaseUbyCnt", CUSTOMER_HAS_PURCHASE_REPEAT_BUYERS)},
                {metric_value("customer.hasBuyInShopCnt", CUSTOMER_HAS_PURCHASE_NO_REPEAT)},
                {metric_value("customer.hasPurchasePayRate", CUSTOMER_HAS_PURCHASE_PAY_RATE)},
                {metric_value("customer.hasPurchasePayAmtRatio", CUSTOMER_HAS_PURCHASE_PAY_AMOUNT_RATIO)},
                {metric_value("customer.hasPurchasePct", CUSTOMER_HAS_PURCHASE_UNIT_PRICE)},
                {metric_value("customer.hasPurchaseFansRate", CUSTOMER_HAS_PURCHASE_FANS_RATE)},
                {metric_value("customer.hasPurchaseVipRate", CUSTOMER_HAS_PURCHASE_VIP_RATE)},
                {metric_value("customer.hasPurchaseReCall", CUSTOMER_HAS_PURCHASE_RECALL_RATE)},
                {metric_value("customer.hasPurchaseUbyCntRate", CUSTOMER_HAS_PURCHASE_REPEAT_RATE)}
            from store_daily_metrics m
            where m.{q(METRIC_SCOPE)} = 'self'
              and m.{q(METRIC_CODE)} like 'customer.%'
            group by
                m.{q(STORE_ID)},
                m.{q(BUSINESS_DAY)}
            """
        )

        conn.execute('drop view if exists "store_daily_member_analysis_metrics"')
        conn.execute(
            f"""
            create view "store_daily_member_analysis_metrics" as
            select
                m.{q(STORE_ID)} as {q(STORE_ID)},
                m.{q(BUSINESS_DAY)} as {q(BUSINESS_DAY)},
                {metric_value("member.core.totalMbrCnt", MEMBER_TOTAL_COUNT)},
                {metric_value("member.core.paidMbrCnt", MEMBER_PAID_COUNT)},
                {metric_value("member.core.mbrPayAmt", MEMBER_PAID_AMOUNT)},
                {metric_value("member.core.mbrUnitPrice", MEMBER_UNIT_PRICE)},
                {metric_value("member.core.repurMbrRate", MEMBER_CORE_REPURCHASE_RATE)},
                {metric_value("member.asset.highFreqBuyerMemberAssets", MEMBER_HIGH_FREQ_COUNT)},
                {metric_value("member.asset.highFreqBuyerMemberPayAmtRate", MEMBER_HIGH_FREQ_AMOUNT_RATE)},
                {metric_value("member.asset.highFreqBuyerMemberAssetsPortion", MEMBER_HIGH_FREQ_OWN_RATIO)},
                {metric_value("member.asset.highFreqBuyerMemberAssetsRatio", MEMBER_HIGH_FREQ_BENCHMARK_RATIO)},
                {metric_value("member.asset.twoOrderBuyerMemberAssets", MEMBER_TWO_ORDER_COUNT)},
                {metric_value("member.asset.twoOrderBuyerMemberPayAmtRate", MEMBER_TWO_ORDER_AMOUNT_RATE)},
                {metric_value("member.asset.twoOrderBuyerMemberAssetsPortion", MEMBER_TWO_ORDER_OWN_RATIO)},
                {metric_value("member.asset.twoOrderBuyerMemberAssetsRatio", MEMBER_TWO_ORDER_BENCHMARK_RATIO)},
                {metric_value("member.asset.firstTimeBuyerMemberAssets", MEMBER_FIRST_TIME_COUNT)},
                {metric_value("member.asset.firstTimeBuyerMemberPayAmtRate", MEMBER_FIRST_TIME_AMOUNT_RATE)},
                {metric_value("member.asset.firstTimeBuyerMemberAssetsPortion", MEMBER_FIRST_TIME_OWN_RATIO)},
                {metric_value("member.asset.firstTimeBuyerMemberLyrAssetsRatio", MEMBER_FIRST_TIME_BENCHMARK_RATIO)},
                {metric_value("member.asset.activeNonBuyerMemberAssets", MEMBER_ACTIVE_NON_BUYER_COUNT)},
                {metric_value("member.asset.activeNonBuyerMemberAssetsPortion", MEMBER_ACTIVE_NON_BUYER_OWN_RATIO)},
                {metric_value("member.asset.activeNonBuyerMemberLyrAssetsRatio", MEMBER_ACTIVE_NON_BUYER_BENCHMARK_RATIO)},
                {metric_value("member.asset.inactiveMemberAssets", MEMBER_INACTIVE_COUNT)},
                {metric_value("member.asset.inactiveMemberAssetsPortion", MEMBER_INACTIVE_OWN_RATIO)},
                {metric_value("member.asset.inactiveMemberLyrAssetsRatio", MEMBER_INACTIVE_BENCHMARK_RATIO)},
                {metric_value("member.repurchase.repurMbrCnt", MEMBER_REPURCHASE_COUNT)},
                {metric_value("member.repurchase.repurPayAmt", MEMBER_REPURCHASE_AMOUNT)},
                {metric_value("member.repurchase.repurOrdCnt", MEMBER_REPURCHASE_ORDER_COUNT)},
                {metric_value("member.repurchase.repurUnitPrice", MEMBER_REPURCHASE_UNIT_PRICE)},
                {metric_value("member.repurchase.repurCycle", MEMBER_REPURCHASE_CYCLE)},
                {metric_value("member.repurchase.repurMbrRate", MEMBER_REPURCHASE_PAGE_RATE)},
                {metric_value("member.repurchase.repurFrequency", MEMBER_REPURCHASE_FREQUENCY)},
                {metric_value("member.acquisition.incrMbrCnt", MEMBER_NEW_COUNT)},
                {metric_value("member.acquisition.incrPaidMbrCnt", MEMBER_NEW_PAID_COUNT)},
                {metric_value("member.acquisition.recConvertRate", MEMBER_RECRUIT_CONVERSION_RATE)},
                {metric_value("member.acquisition.incrPayOrdAmt", MEMBER_NEW_PAID_AMOUNT)},
                {metric_value("member.acquisition.incrUnitPrice", MEMBER_NEW_UNIT_PRICE)},
                {metric_value("member.acquisition.oldNewMemberCount", MEMBER_OLD_NEW_COUNT)}
            from store_daily_metrics m
            where m.{q(METRIC_SCOPE)} = 'self'
              and m.{q(METRIC_CODE)} like 'member.%'
            group by
                m.{q(STORE_ID)},
                m.{q(BUSINESS_DAY)}
            """
        )

        conn.execute('drop view if exists "store_daily_metric_values_readable"')
        conn.execute(
            f"""
            create view "store_daily_metric_values_readable" as
            select
                m.{q(STORE_ID)} as {q(STORE_ID)},
                m.{q(BUSINESS_DAY)} as {q(BUSINESS_DAY)},
                m.{q(METRIC_SCOPE)} as {q(METRIC_SCOPE)},
                m.{q(METRIC_CODE)} as {q(METRIC_CODE)},
                coalesce(d.{q(METRIC_NAME)}, m.{q(METRIC_CODE)}) as {q(METRIC_NAME)},
                coalesce(d.{q(METRIC_GROUP)}, '') as {q(METRIC_GROUP)},
                coalesce(d.{q(UNIT)}, '') as {q(UNIT)},
                m.{q(METRIC_VALUE)} as {q(METRIC_VALUE)}
            from store_daily_metrics m
            left join metric_definitions d on d.{q(METRIC_CODE)} = m.{q(METRIC_CODE)}
            """
        )

    @staticmethod
    def _drop_business_views(conn: sqlite3.Connection) -> None:
        for view in (
            "store_daily_business_metrics",
            "store_daily_flow_overview_metrics",
            "store_daily_customer_overview_metrics",
            "store_daily_member_analysis_metrics",
            "store_daily_metric_values_readable",
        ):
            conn.execute(f'drop view if exists "{view}"')

    @staticmethod
    def _migrate_legacy_flow_metrics(conn: sqlite3.Connection) -> None:
        """Move the one historical EAV dependency into the flow fact table once."""
        return

        if not LocalDatabase._table_exists(conn, "store_daily_metrics"):
            return

        def value_for(codes: tuple[str, ...]) -> str:
            expressions = ", ".join(
                f"max(case when {q(METRIC_CODE)} = 'flow.{code}' "
                f"then cast({q(METRIC_VALUE)} as real) end)"
                for code in codes
            )
            return f"coalesce({expressions})"

        columns = FLOW_OVERVIEW_COLUMNS
        values = [value_for(codes) for _, codes in FLOW_STORAGE_FIELDS]
        assignments = ", ".join(
            f"{q(column)} = excluded.{q(column)}" for column in columns[2:]
        )
        conn.execute(
            f"""
            insert into store_daily_flow_overviews (
                {", ".join(q(column) for column in columns)}
            )
            select {q(STORE_ID)}, {q(BUSINESS_DAY)}, {", ".join(values)}
            from store_daily_metrics
            where {q(METRIC_SCOPE)} = 'self'
              and {q(METRIC_CODE)} like 'flow.%'
            group by {q(STORE_ID)}, {q(BUSINESS_DAY)}
            on conflict({q(STORE_ID)}, {q(BUSINESS_DAY)}) do update set
                {assignments}
            """
        )

    @staticmethod
    def _refresh_daily_overviews_from_metrics(conn: sqlite3.Connection) -> None:
        return

        metric_columns = [column for column, _ in DAILY_OVERVIEW_FIELDS]
        source_columns = [STORE_ID, BUSINESS_DAY, *metric_columns]
        select_columns = [q(STORE_ID), q(BUSINESS_DAY)]
        select_columns.extend(
            f"coalesce({q(column)}, '0') as {q(column)}" for column in metric_columns
        )
        conn.execute(
            f"""
            insert or replace into store_daily_overviews (
                {", ".join(q(column) for column in source_columns)}
            )
            select {", ".join(select_columns)}
            from store_daily_business_metrics
            where {q(PAID_AMOUNT)} is not null
               or {q(VISITORS)} is not null
               or {q(PAID_BUYERS)} is not null
            """
        )

    @staticmethod
    def _delete_non_self_metrics(conn: sqlite3.Connection) -> None:
        return

        if LocalDatabase._table_exists(conn, "store_daily_metrics"):
            conn.execute(
                f"delete from store_daily_metrics where {q(METRIC_SCOPE)} <> 'self'"
            )

    @staticmethod
    def _column_type(conn: sqlite3.Connection, table: str, column: str) -> str:
        row = conn.execute(
            f'pragma table_info("{table}")'
        ).fetchall()
        for item in row:
            if item["name"] == column:
                return str(item["type"] or "")
        return ""

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute(
            "select 1 from sqlite_master where type = 'table' and name = ?",
            (table,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
        if not LocalDatabase._table_exists(conn, table):
            return set()
        return {
            str(row["name"])
            for row in conn.execute(f'pragma table_info("{table}")').fetchall()
        }
