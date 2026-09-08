from datetime import date

from app.modules.ai.agent_planner import build_agent_plan
from app.modules.ai.schemas import AIConversationState, AnalysisRequest
from app.modules.ai.service import AIAnalysisService


def test_channel_growth_question_builds_a_comparison_plan() -> None:
    plan = build_agent_plan(
        question="最近两天和前两天比较哪个渠道增长较多？",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 7),
    )

    assert plan is not None
    assert plan.primary_skill == "traffic-diagnosis"
    assert plan.intent.current_start == date(2026, 9, 6)
    assert plan.intent.previous_start == date(2026, 9, 4)
    tools = [step.tool for step in plan.calls]
    assert tools == ["data.coverage", "data.compare_periods", "data.compare_periods", "data.compare_periods"]
    traffic_call = next(step for step in plan.calls if step.arguments.get("dataset") == "traffic_sources")
    assert traffic_call.arguments["dimensions"] == ["source"]
    assert traffic_call.arguments["start_date"] == date(2026, 9, 6)


def test_channel_growth_analysis_uses_complete_daily_evidence_not_generic_exploration() -> None:
    result = AIAnalysisService().analyze(
        AnalysisRequest(
            question="最近两天和前两天比较哪个渠道增长较多？",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 7),
            page_context={"page_key": "ai"},
            use_model=False,
        ),
        store_id=1,
    )

    assert result.skill.name == "traffic-diagnosis"
    assert result.diagnosis.analysis_plan["name"] == "channel-growth-comparison"
    assert result.diagnosis.coverage.covered_days == 2
    assert result.diagnosis.coverage.expected_days == 2
    assert not result.diagnosis.coverage.missing_dates
    tools = [item.tool for item in result.mcp_results]
    assert "data.catalog" not in tools
    assert any(item.tool == "data.compare_periods" and item.data.get("dataset") == "traffic_sources" for item in result.mcp_results)
    matrix = next(item for item in result.diagnosis.artifacts if item.title == "一级流量来源两窗口对比")
    assert matrix.rows
    assert matrix.rows[0]["支付金额增量"] > 0
    assert matrix.rows[0]["支付金额增量"] == max(row["支付金额增量"] for row in matrix.rows)
    assert "待补采" not in result.answer
    assert any(step.name == "evidence-quality-gate" for step in result.execution_steps)


def test_channel_growth_follow_up_inherits_the_previous_analysis_end_date() -> None:
    service = AIAnalysisService()
    plan = service._agent_plan(
        AnalysisRequest(question="最近两天和前两天比较哪个渠道增长较多？", use_model=False),
        AIConversationState(
            conversation_id="agent-plan-follow-up",
            memory={"range_start": "2026-09-01", "range_end": "2026-09-07"},
        ),
        store_id=1,
    )

    assert plan is not None
    assert plan.intent.current_start == date(2026, 9, 6)
    assert plan.intent.current_end == date(2026, 9, 7)


def test_recent_sales_growth_uses_a_focused_evidence_plan() -> None:
    result = AIAnalysisService().analyze(
        AnalysisRequest(
            question="最近2天的销售为什么增长？",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 7),
            page_context={"page_key": "ai"},
            use_model=False,
        ),
        store_id=1,
    )

    assert result.skill.name == "shop-overview-diagnosis"
    assert result.diagnosis.analysis_plan["name"] == "recent-sales-growth-diagnosis"
    assert result.diagnosis.coverage.covered_days == result.diagnosis.coverage.expected_days == 2
    assert "成交下降" not in result.diagnosis.headline
    assert "支付金额增长" in result.diagnosis.headline
    tools = [item.tool for item in result.mcp_results]
    assert tools.count("data.compare_periods") == 4
    assert "overview.get_store_summary" not in tools
    assert "data.catalog" not in tools
    assert any(item.data.get("dataset") == "products" for item in result.mcp_results)
