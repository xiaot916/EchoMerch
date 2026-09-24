from datetime import date

import pytest

from scripts.alimama_report_quality import (
    AlimamaReportIncomplete,
    validate_campaign_buyer_metrics,
)


def test_campaign_snapshot_accepts_settled_buyer_metrics() -> None:
    pages = [{
        "data": {
            "totalData": [{"alipayInshopNum": 12, "alipayInshopUv": 9}],
            "list": [
                {"alipayInshopNum": 7, "alipayInshopUv": 5},
                {"alipayInshopNum": 5, "alipayInshopUv": 4},
            ],
        }
    }]

    validate_campaign_buyer_metrics(pages, date(2026, 9, 20))


def test_campaign_snapshot_rejects_orders_with_zero_buyers() -> None:
    pages = [{
        "data": {
            "totalData": [{"alipayInshopNum": 958, "alipayInshopUv": 0}],
            "list": [
                {"alipayInshopNum": 7, "alipayInshopUv": 0},
                {"alipayInshopNum": 1, "alipayInshopUv": 0},
            ],
        }
    }]

    with pytest.raises(AlimamaReportIncomplete, match="still settling"):
        validate_campaign_buyer_metrics(pages, date(2026, 9, 20))


def test_campaign_snapshot_accepts_true_zero_order_day() -> None:
    pages = [{
        "data": {
            "totalData": {"alipayInshopNum": 0, "alipayInshopUv": 0},
            "list": [{"alipayInshopNum": 0, "alipayInshopUv": 0}],
        }
    }]

    validate_campaign_buyer_metrics(pages, date(2026, 9, 20))
