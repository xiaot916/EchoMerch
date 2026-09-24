"""Map SYCM home-board endpoint metric codes onto canonical Chinese columns."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

# grow_factor: /portal/board/grow/factor/overview.json
# NOTE: this endpoint does NOT return the five 增长因子 scores (交易/流量/商品/
# 营销/服务分). It returns a GMV composition under data.self / data.rivalGood
# (mbrPayAmt, totalPromoSpend, clicks, portalAdPayAmt, portalLivePayAmt,
# newItmPayAmt, superItemPayAmt, tROI), each wrapped as {value, cycleCrc}.
# Those are nested one level deep, so the flat parser emits nothing and the
# 增长因子_* columns stay NULL until the real score endpoint is identified.
GROW_FACTOR_MAP: dict[str, str] = {}

# level_info: /portal/level/info/v3.json
# NOTE: for this shop the response only carries {bcSeller, sellerType} - no
# level / score / rankPercent fields, so 层级_* columns stay NULL.
LEVEL_INFO_MAP: dict[str, str] = {}

# experience_scorecard: /portal/new/experience/scorecard.json
# Real keys (verified against a live 2026-09-18 response):
#   goodsValue      商品体验 5.00
#   logisticsValue  物流体验 4.92
#   serviceExpValue 服务体验 5.00
#   refundValue     退款体验 4.80
#   dsptValue       纠纷体验 4.75
# There is no total-score field (only industryRank / rankValue), so 体验总分
# is intentionally left unmapped.
EXPERIENCE_MAP: dict[str, str] = {
    "home_board.experience_scorecard.goodsValue": "商品体验分",
    "home_board.experience_scorecard.logisticsValue": "物流体验分",
    "home_board.experience_scorecard.serviceExpValue": "服务体验分",
    "home_board.experience_scorecard.refundValue": "退款体验分",
    "home_board.experience_scorecard.dsptValue": "纠纷体验分",
}

# main_cate_info: /portal/shop/getMainCateInfo.json
# Real keys: cateLevel1Id (numeric), cateLevel1Name (text, carried through
# ParsedHomeBoard.text_values because the parser only emits numeric metrics).
MAIN_CATE_MAP: dict[str, str] = {
    "home_board.main_cate_info.cateLevel1Id": "主营类目ID",
}

ENDPOINT_MAPS: dict[str, dict[str, str]] = {
    "grow_factor": GROW_FACTOR_MAP,
    "level_info": LEVEL_INFO_MAP,
    "experience_scorecard": EXPERIENCE_MAP,
    "main_cate_info": MAIN_CATE_MAP,
}


def map_home_board_metrics(
    metric_values: dict[str, Any],
    endpoint_name: str,
) -> dict[str, Any]:
    """Return {chinese_column: value} for the given endpoint."""
    mapping = ENDPOINT_MAPS.get(endpoint_name, {})
    result: dict[str, Any] = {}
    for code, column in mapping.items():
        value = metric_values.get(code)
        if value is not None:
            result[column] = value
    return result
