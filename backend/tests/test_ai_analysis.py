from datetime import date
from decimal import Decimal
import pytest

from app.modules.ai.mcp import CommerceMCPService
from app.modules.ai.schemas import AnalysisRequest, PeriodReportRequest
from app.modules.ai.service import AIAnalysisService


def test_mcp_tools_include_period_report() -> None:
    names = {item.name for item in CommerceMCPService().list_tools()}
    assert "reports.build_period_report" in names


def test_period_report_keeps_structured_sections() -> None:
    service = AIAnalysisService()
    result = service.build_period_report(
        PeriodReportRequest(report_type="daily", anchor_date=date(2026, 8, 20), use_model=False),
        store_id=1,
    )
    assert result.report_type == "daily"
    assert result.report["operations"]["gmv"] is not None
    assert "channels" in result.report
    assert "promotions" in result.report
    assert "missing_sections" in result.report


def test_daily_report_explains_gmv_decline_with_reconciled_driver_bridge() -> None:
    service = AIAnalysisService()
    result = service.build_period_report(
        PeriodReportRequest(report_type="daily", anchor_date=date(2026, 8, 22), use_model=False),
        store_id=1,
    )

    bridge = result.report["gmv_driver_bridge"]
    assert bridge["dominant_driver"]["key"] == "customer_unit_price"
    assert bridge["reconciliation_error"] == pytest.approx(0, abs=0.01)
    assert result.report["channel_scope"]["can_sum"] is False
    assert result.report["decision_quality"]["overall"]["confidence"] == "high"
    assert result.diagnosis.confidence == "high"
    assert "客单价" in result.diagnosis.headline


def test_overview_decline_derives_conversion_and_does_not_restore_budget_by_assumption() -> None:
    service = AIAnalysisService()
    result = service.analyze(
        AnalysisRequest(
            question="为什么最近成交下降？给我最重要的三个原因和动作",
            start_date=date(2026, 8, 16),
            end_date=date(2026, 8, 22),
            use_model=False,
        ),
        store_id=1,
    )

    assert "支付转化" in result.diagnosis.headline
    assert any("客单价不是本次主要拖累" == item.title for item in result.diagnosis.findings)
    assert not any("恢复推广" in item.title or "恢复预算" in item.title for item in result.diagnosis.actions)
    assert not any("建议恢复" in item.detail or "恢复至" in item.detail for item in result.diagnosis.actions)


def test_mtd_report_calculates_target_pace_and_copyable_title() -> None:
    service = AIAnalysisService()
    result = service.build_period_report(
        PeriodReportRequest(
            report_type="mtd",
            anchor_date=date(2026, 8, 21),
            target_gmv=13_000_000,
            use_model=False,
        ),
        store_id=1,
    )
    target = result.report["target"]
    assert result.text.startswith("26年-8月MTD")
    assert target["target_gmv"] == 13_000_000
    assert target["completion_rate"] is not None
    assert target["time_progress"] == 67.74
    assert target["pace_gap"] < 0
    assert target["remaining_days"] == 10
    assert target["required_daily_gmv"] == pytest.approx(target["remaining_gmv"] / 10, abs=0.01)


def test_rule_analysis_returns_evidence_and_actions_without_model() -> None:
    service = AIAnalysisService()
    result = service.analyze(
        AnalysisRequest(
            question="为什么昨天成交下降？",
            start_date=date(2026, 8, 20),
            end_date=date(2026, 8, 20),
            use_model=False,
        ),
        store_id=1,
    )
    assert result.provider == "rules"
    assert result.mcp_results
    assert result.mcp_results[0].evidence
    assert result.diagnosis.findings
    assert result.diagnosis.actions
    assert result.conversation_memory["last_question"] == "为什么昨天成交下降？"
    assert result.conversation_memory["skill"] == result.skill.name


def test_analysis_emits_auditable_agent_progress_events() -> None:
    events: list[dict] = []
    service = AIAnalysisService()
    result = service.analyze(
        AnalysisRequest(
            question="为什么昨天成交下降？",
            start_date=date(2026, 8, 20),
            end_date=date(2026, 8, 20),
            use_model=False,
        ),
        store_id=1,
        on_event=events.append,
        stream_model=True,
    )

    assert result.status in {"ok", "partial", "no_data"}
    assert events[0]["event"] == "planner"
    assert any(item["event"] == "skill" for item in events)
    assert any(item["event"] == "mcp" and item["status"] == "completed" for item in events)
    assert events[-1]["event"] == "final"
    assert events[-1]["response"]["request_id"] == result.request_id
