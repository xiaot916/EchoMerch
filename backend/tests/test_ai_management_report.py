from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.ai.schemas import PeriodReportRequest
from app.modules.ai.management_report import _monthly_comparison
from app.modules.ai.mcp import CommerceMCPService
from app.modules.ai.service import AIAnalysisService


def test_business_review_builds_yoy_evidence_and_report_artifacts() -> None:
    result = AIAnalysisService().build_period_report(
        PeriodReportRequest(
            report_type="business_review",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 8, 18),
            comparison_mode="same_period_last_year",
            business_events=["6月舆情事件"],
            use_model=False,
        ),
        store_id=1,
    )

    report = result.report
    assert result.report_type == "business_review"
    assert report["comparison_label"] == "同比"
    assert report["previous_period"] == {"range_start": "2025-01-01", "range_end": "2025-08-18"}
    assert report["review_kpis"]
    assert report["monthly_trend"]
    assert report["comparison_data_quality"]
    assert report["data_quality"]["latest_data_date"] == "2026-08-18"
    assert result.diagnosis.coverage.covered_days == result.diagnosis.coverage.expected_days == 230
    assert result.diagnosis.coverage.missing_dates == []
    assert report["business_events"] == ["6月舆情事件"]
    assert any(item["source_type"] == "系统事实" for item in report["source_ledger"])
    assert any(item["source_type"] == "计算推导" for item in report["source_ledger"])
    bridge = report["gmv_driver_bridge"]
    assert bridge is not None
    assert bridge["reconciliation_error"] == pytest.approx(0, abs=0.01)
    artifact_titles = {item.title for item in result.diagnosis.artifacts}
    assert "经营核心指标对比" in artifact_titles
    assert "月度支付与净支付趋势" in artifact_titles


def test_business_review_validates_planning_targets_without_treating_them_as_facts() -> None:
    result = AIAnalysisService().build_period_report(
        PeriodReportRequest(
            report_type="business_review",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 8, 18),
            target_gmv=50_000_000,
            planning_targets={
                "net_gmv": 60_000_000,
                "visitors": 1_000_000,
                "buyers": 100_000,
                "conversion_rate": 5,
                "customer_unit_price": 100,
            },
            strategy_notes="双11重点发展高客单系列",
            use_model=False,
        ),
        store_id=1,
    )

    planning = result.report["planning"]
    assert planning["source_type"] == "人工输入"
    assert planning["targets"]["gmv"] == 50_000_000
    assert any(item["status"] == "warning" for item in planning["validation"])
    assert any("净销售目标高于支付目标" in warning for warning in result.warnings)


def test_business_review_rejects_incomplete_custom_comparison() -> None:
    with pytest.raises(ValidationError):
        PeriodReportRequest(
            report_type="business_review",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 8, 18),
            comparison_mode="custom",
            comparison_start_date=date(2025, 1, 1),
        )


def test_monthly_comparison_keeps_year_months_separate_and_aligns_period_order() -> None:
    rows = _monthly_comparison(
        [
            {"stat_date": "2025-12-31", "paid_amount": 10, "refund_amount": 1},
            {"stat_date": "2026-01-01", "paid_amount": 20, "refund_amount": 2},
        ],
        [
            {"stat_date": "2024-10-31", "paid_amount": 5, "refund_amount": 0},
            {"stat_date": "2024-11-01", "paid_amount": 8, "refund_amount": 1},
        ],
    )

    assert [row["月份"] for row in rows] == ["2025-12", "2026-01"]
    assert [row["对比月份"] for row in rows] == ["2024-10", "2024-11"]
    assert rows[1]["本期支付金额"] == 20
    assert rows[1]["对比期净支付金额"] == 7


def test_report_coverage_latest_date_is_bounded_to_selected_period() -> None:
    coverage = CommerceMCPService._coverage(
        [
            SimpleNamespace(
                dataset="店铺日概览",
                status="complete",
                covered_days=31,
                expected_days=31,
                missing_dates=[],
                no_data_dates=[],
                latest_date=date(2026, 9, 20),
            ),
        ],
        date(2026, 8, 1),
        date(2026, 8, 31),
        "店铺日概览",
        include_all=True,
    )

    assert coverage.latest_data_date == "2026-08-31"
