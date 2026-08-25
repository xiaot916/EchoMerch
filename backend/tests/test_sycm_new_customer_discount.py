from datetime import date
from decimal import Decimal

from app.warehouse.sycm_new_customer_discount import parse_payload


def test_parser_keeps_a_complete_zero_activity_day() -> None:
    parsed = parse_payload(
        {
            "code": 0,
            "data": {
                "statDate": {"value": 1787155200000},
                "guideNewUv": {"value": 0},
                "guideNewPayByrCnt": {"value": 0, "ratio": 0},
                "guideNewPayByrCntRatio": {"value": 0},
                "guideNewPayAmt": {"value": 0, "ratio": 0},
                "guideNewPayAmtRatio": {"value": 0},
                "guideNewPayRate": {"value": 0},
                "newbuyerPayByrCnt": {"value": 10},
                "newbuyerPayAmt": {"value": 100},
            },
        },
        business_day=date(2026, 8, 20),
    )

    assert parsed.product_new_visitors == Decimal("0")
    assert parsed.new_customer_paid_buyers == Decimal("0")
    assert parsed.new_customer_paid_amount == Decimal("0.00")
    assert parsed.new_customer_paid_conversion_rate == Decimal("0")


def test_parser_nulls_platform_placeholder_zeroes_when_activity_bundle_is_partial() -> None:
    parsed = parse_payload(
        {
            "code": 0,
            "data": {
                "statDate": {"value": 1787155200000},
                "guideNewUv": {"value": None},
                "guideNewPayByrCnt": {"value": 0, "ratio": 0},
                "guideNewPayByrCntRatio": {"value": 0},
                "guideNewPayAmt": {"value": 0, "ratio": 0},
                "guideNewPayAmtRatio": {"value": 0},
                "guideNewPayRate": {"value": None},
                "newbuyerPayByrCnt": {"value": 1251},
                "newbuyerPayAmt": {"value": 26684.36},
            },
        },
        business_day=date(2026, 8, 20),
    )

    assert parsed.product_new_visitors is None
    assert parsed.new_customer_paid_buyers is None
    assert parsed.new_customer_paid_buyer_ratio is None
    assert parsed.new_customer_paid_amount is None
    assert parsed.new_customer_paid_amount_ratio is None
    assert parsed.new_customer_paid_conversion_rate is None
    assert parsed.shop_new_customer_paid_buyers == Decimal("1251")
    assert parsed.shop_new_customer_paid_amount == Decimal("26684.36")
