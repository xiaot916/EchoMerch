from app.modules.ai.mcp import CommerceMCPService
from app.modules.ai.schemas import AnalysisRequest
from app.modules.ai.service import AIAnalysisService


def test_budget_planning_without_total_budget_returns_shares_only() -> None:
    result = AIAnalysisService().analyze(
        AnalysisRequest(question="推广预算拆解，目标 ROI 3.5", use_model=False),
        store_id=1,
    )
    assert result.skill.name == "promotion-budget-planning"
    rows = result.diagnosis.artifacts[0].rows
    assert rows
    assert all(row["建议预算"] is None for row in rows)
    assert any(action.title == "补充总预算" for action in result.diagnosis.actions)


def test_budget_planning_allocates_exact_total_budget() -> None:
    result = AIAnalysisService().analyze(
        AnalysisRequest(question="推广预算拆解，预算 50 万，目标 ROI 3.5", use_model=False),
        store_id=1,
    )
    assert result.skill.name == "promotion-budget-planning"
    rows = result.diagnosis.artifacts[0].rows
    assert round(sum(row["建议预算"] or 0 for row in rows), 2) == 500000.0
    assert any(action.title == "对高效场景做阶梯扩量" for action in result.diagnosis.actions)


def test_campaign_planning_builds_target_tree_and_event_stages() -> None:
    result = AIAnalysisService().analyze(
        AnalysisRequest(question="做 618 活动规划，GMV 目标 500 万，预算 50 万，目标 ROI 3.5", use_model=False),
        store_id=1,
    )
    assert result.skill.name == "campaign-planning"
    titles = {artifact.title for artifact in result.diagnosis.artifacts}
    assert "规划目标树" in titles
    assert "活动阶段计划模板" in titles


def test_all_history_scope_uses_available_date_bounds() -> None:
    result = CommerceMCPService().execute(
        "data.query",
        {
            "store_id": 1,
            "dataset": "promotion_campaigns",
            "dimensions": ["date"],
            "measures": ["spend"],
            "history_scope": "all",
            "limit": 1000,
        },
    )
    assert result.context.range_start < result.context.range_end
    assert result.evidence[0].date_range[0] == result.context.range_start.isoformat()
    assert result.evidence[0].date_range[1] == result.context.range_end.isoformat()
