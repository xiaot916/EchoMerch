from decimal import Decimal

from app.modules.analytics.derived_metrics import CUSTOMER_DERIVED_METRICS, derive_metrics


def _by_id(source: dict[str, Decimal | int | None]):
    return {item.id: item for item in derive_metrics(source, CUSTOMER_DERIVED_METRICS)}


def test_customer_derived_metrics_reconcile_first_purchase_and_repeat_structure() -> None:
    metrics = _by_id({
        "total_paid_buyers": 100,
        "total_paid_amount": Decimal("1000"),
        "new_visit_paid_buyers": 30,
        "new_visit_paid_amount": Decimal("300"),
        "no_purchase_paid_buyers": 30,
        "no_purchase_paid_amount": Decimal("200"),
        "repeat_paid_buyers": 40,
        "repeat_paid_amount": Decimal("500"),
    })

    assert metrics["first_purchase_paid_buyers"].value == Decimal("60.00")
    assert metrics["first_purchase_paid_amount"].value == Decimal("500.00")
    assert metrics["first_purchase_buyer_share"].value == Decimal("60.00")
    assert metrics["repeat_amount_share"].value == Decimal("50.00")
    assert metrics["first_purchase_unit_price"].value == Decimal("8.33")
    assert metrics["repeat_unit_price"].value == Decimal("12.50")
    assert metrics["classified_buyer_gap"].value == Decimal("0.00")
    assert metrics["classified_amount_gap"].value == Decimal("0.00")


def test_customer_derived_metrics_stop_when_dependencies_are_missing() -> None:
    metrics = _by_id({
        "total_paid_buyers": 100,
        "total_paid_amount": Decimal("1000"),
        "repeat_paid_buyers": 40,
        "repeat_paid_amount": None,
    })

    assert metrics["first_purchase_paid_buyers"].status == "available"
    assert metrics["first_purchase_paid_amount"].status == "unavailable"
    assert metrics["first_purchase_amount_share"].status == "unavailable"
    assert "repeat_paid_amount" in metrics["first_purchase_paid_amount"].note


def test_customer_derived_metrics_flag_negative_difference_as_inconsistent() -> None:
    metrics = _by_id({
        "total_paid_buyers": 10,
        "total_paid_amount": Decimal("100"),
        "repeat_paid_buyers": 12,
        "repeat_paid_amount": Decimal("120"),
    })

    assert metrics["first_purchase_paid_buyers"].status == "inconsistent"
    assert metrics["first_purchase_paid_buyers"].value is None
    assert metrics["first_purchase_paid_amount"].status == "inconsistent"
    assert metrics["first_purchase_paid_amount"].value is None
