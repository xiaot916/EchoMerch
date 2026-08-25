from datetime import date

from app.modules.ai.mcp import CommerceMCPService
from app.modules.ai.provider import AgnesProvider
from app.modules.ai.schemas import AnalysisContext, AnalysisRequest, MCPEnvelope
from app.modules.ai.service import AIAnalysisService
from app.modules.ai.skills import select_skills


def test_data_freshness_is_a_generic_mcp_contract() -> None:
    result = CommerceMCPService().execute(
        "data.freshness",
        {"store_id": 1, "datasets": ["store_overview", "promotion_campaigns"]},
    )
    assert result.tool == "data.freshness"
    assert result.data["datasets"]
    assert {"dataset", "label", "status", "latest_date", "business_lag_days"}.issubset(result.data["datasets"][0])


def test_market_insights_is_exposed_as_structured_mcp() -> None:
    result = CommerceMCPService().execute("market.get_insights", {"limit": 8})
    assert result.tool == "market.get_insights"
    assert result.status in {"ok", "partial", "no_data"}
    assert result.coverage.expected_days >= result.coverage.covered_days
    assert result.evidence
    assert "summary" in result.data
    assert "competitive_signals" in result.data
    assert "keyword_segments" in result.data
    assert "demand_signals" in result.data
    assert "decisions" in result.data
    assert result.data["summary"]["coverage_rate"] >= 0
    assert all({"finding", "evidence", "action", "validation", "confidence"}.issubset(item) for item in result.data["decisions"])
    assert all(item["category_relevance"] == "relevant" for item in result.data["keywords"] if item["keyword"] in {signal["keyword"] for signal in result.data["demand_signals"]})
    assert {item.id for item in result.metrics} >= {"market_content_count", "market_competitor_movers", "market_keyword_segments"}


def test_market_specialized_tools_preserve_platform_boundaries() -> None:
    service = CommerceMCPService()
    descriptors = {item.name for item in service.list_tools()}
    assert {
        "market.get_keyword_opportunities",
        "market.get_competitor_movements",
        "market.match_store_products",
    }.issubset(descriptors)

    opportunities = service.execute(
        "market.get_keyword_opportunities",
        {"start_date": "2026-08-18", "end_date": "2026-08-22", "limit": 5},
    )
    assert opportunities.tool == "market.get_keyword_opportunities"
    assert opportunities.status in {"ok", "partial", "no_data"}
    assert "boundary" in opportunities.data
    assert opportunities.evidence[0].dataset == "市场搜索词"

    movements = service.execute(
        "market.get_competitor_movements",
        {"start_date": "2026-08-18", "end_date": "2026-08-22", "rank_type": "item", "direction": "rising", "limit": 5},
    )
    assert movements.tool == "market.get_competitor_movements"
    assert all(item["direction"] == "rising" for item in movements.data["movements"])
    assert "boundary" in movements.data

    unmatched = service.execute(
        "market.match_store_products",
        {"store_id": 1, "start_date": "2026-08-18", "end_date": "2026-08-22", "query": "__definitely_no_market_product_match__", "limit": 5},
    )
    assert unmatched.status == "no_data"
    assert unmatched.data["signals"] == []
    assert "no_match" in unmatched.data["boundary"]


def test_mini_diagnosis_tool_and_router_are_exposed() -> None:
    service = CommerceMCPService()
    assert "mini.get_diagnosis" in {item.name for item in service.list_tools()}
    primary, supporting = select_skills(
        "帮我分析 mini 装商品并看应该补齐哪些动作",
        "auto",
        {"page_key": "ai"},
    )
    assert primary.descriptor.name == "mini-product-diagnosis"
    assert {item.descriptor.name for item in supporting} >= {
        "product-diagnosis", "review-diagnosis", "utry-repurchase-diagnosis", "data-quality-audit",
    }


def test_mini_diagnosis_joins_catalog_and_cross_domain_evidence() -> None:
    result = CommerceMCPService().execute(
        "mini.get_diagnosis",
        {"store_id": 1, "query": "mini,尝鲜", "start_date": "2026-08-16", "end_date": "2026-08-22", "limit": 100},
    )
    assert result.status in {"ok", "partial"}
    assert result.data["matched_count"] > 0
    assert result.data["products"]
    assert {"sales", "promotion", "reviews", "asks", "utry_sample", "utry_repurchase"}.issubset(result.data["products"][0])
    assert result.data["products"][0]["product_id"]
    assert result.data["domain_status"]["catalog"]["status"] == "ok"
    assert result.data["rate_available"] is False


def test_mini_analysis_does_not_claim_no_products_when_utry_is_empty() -> None:
    result = AIAnalysisService().analyze(
        AnalysisRequest(
            question="帮我分析 mini 装商品并看应该补齐哪些动作",
            start_date=date(2026, 8, 16),
            end_date=date(2026, 8, 22),
            use_model=False,
            page_context={"page_key": "ai"},
        ),
        store_id=1,
    )
    assert result.skill.name == "mini-product-diagnosis"
    assert result.mcp_results[0].tool == "mini.get_diagnosis"
    assert "未匹配到 MINI/尝鲜商品" not in result.diagnosis.headline
    assert any(action.title for action in result.diagnosis.actions)


def test_market_skill_runs_specialized_market_workflow() -> None:
    result = AIAnalysisService().analyze(
        AnalysisRequest(
            question="请分析市场竞品和搜索词机会",
            start_date=date(2026, 8, 18),
            end_date=date(2026, 8, 22),
            use_model=False,
        ),
        store_id=1,
    )
    assert result.skill.name == "market-insight"
    assert {item.tool for item in result.mcp_results} >= {
        "market.get_insights",
        "market.get_keyword_opportunities",
        "market.get_competitor_movements",
        "market.match_store_products",
    }


def test_market_questions_route_to_market_skill() -> None:
    primary, supporting = select_skills("请做市场竞品和搜索词趋势分析", "auto")
    assert primary.descriptor.name == "market-insight"
    assert "data-quality-audit" in {item.descriptor.name for item in supporting}


def test_router_exposes_supporting_skills_for_compound_question() -> None:
    primary, supporting = select_skills("618预算怎么分，哪些商品适合主推，预算50万，目标ROI 3.5", "auto")
    assert primary.descriptor.name == "campaign-planning"
    assert {item.descriptor.name for item in supporting} >= {"promotion-budget-planning", "product-diagnosis", "data-quality-audit"}


def test_analysis_response_contains_coverage_and_boundary_contract() -> None:
    result = AIAnalysisService().analyze(
        AnalysisRequest(
            question="为什么昨天成交下降？",
            start_date=date(2026, 8, 20),
            end_date=date(2026, 8, 20),
            use_model=False,
        ),
        store_id=1,
    )
    assert result.diagnosis.coverage.expected_days == 1
    assert result.diagnosis.confidence in {"high", "medium", "low"}
    assert result.diagnosis.causal_boundary
    assert result.diagnosis.evidence_refs
    assert all(action.observation_window and action.expected_impact for action in result.diagnosis.actions)


def test_page_context_routes_reviews_and_content_to_page_capabilities() -> None:
    review, _ = select_skills("分析当前页面最重要的问题", "auto", {"page_key": "reviews"})
    content, _ = select_skills("分析当前页面最重要的问题", "auto", {"page_key": "content"})
    greeting, _ = select_skills("你好", "auto", {"page_key": "reviews"})

    assert review.descriptor.name == "review-diagnosis"
    assert content.descriptor.name == "data-exploration"
    assert greeting.descriptor.name == "general-chat"


def test_utry_repurchase_routes_to_specialized_skill() -> None:
    primary, supporting = select_skills("帮我分析一下U先的回购情况", "auto", {"page_key": "ai"})
    assert primary.descriptor.name == "utry-repurchase-diagnosis"
    assert "data-quality-audit" in {item.descriptor.name for item in supporting}
    assert primary.descriptor.workflow[0].tool == "utry.get_repurchase_diagnosis"


def test_utry_repurchase_returns_real_snapshot_without_fake_rate() -> None:
    result = AIAnalysisService().analyze(
        AnalysisRequest(
            question="帮我分析一下U先的回购情况",
            start_date=date(2026, 8, 16),
            end_date=date(2026, 8, 22),
            use_model=False,
            page_context={"page_key": "ai"},
        ),
        store_id=1,
    )

    assert result.skill.name == "utry-repurchase-diagnosis"
    assert result.mcp_results[0].tool == "utry.get_repurchase_diagnosis"
    assert result.mcp_results[0].status == "ok"
    payload = result.mcp_results[0].data
    assert payload["latest_business_day"] == "2026-08-22"
    assert payload["current"]["product_count"] > 0
    assert payload["current"]["store_365d_repurchase_amount"] > 0
    assert len(payload["top_products"]) > 0
    assert len(payload["daily_trend"]) == 7
    assert payload["rate_available"] is False
    assert "不能计算回购率" in result.diagnosis.summary
    assert "U先数据集不存在" not in result.answer


def test_utry_repurchase_does_not_sum_rolling_snapshots_across_days() -> None:
    result = CommerceMCPService().execute(
        "utry.get_repurchase_diagnosis",
        {"store_id": 1, "start_date": "2026-08-16", "end_date": "2026-08-22"},
    )
    current = result.data["current"]
    trend_sum = sum(float(row.get("store_365d_repurchase_amount") or 0) for row in result.data["daily_trend"])
    assert current["store_365d_repurchase_amount"] != trend_sum
    assert "30/90/365" in result.data["snapshot_semantics"]
    assert any("30/90/365" in warning for warning in result.warnings)


def test_channel_budget_question_uses_promotion_roi_and_not_catalog_exploration() -> None:
    primary, supporting = select_skills("哪些渠道值得加预算？请结合投入产出分析", "auto", {"page_key": "ai"})
    assert primary.descriptor.name == "promotion-roi"
    assert "data-quality-audit" in {item.descriptor.name for item in supporting}


def test_promotion_budget_advice_uses_same_scene_period_comparison() -> None:
    result = AIAnalysisService().analyze(
        AnalysisRequest(
            question="哪些渠道值得加预算？请结合投入产出分析",
            start_date=date(2026, 8, 16),
            end_date=date(2026, 8, 22),
            use_model=False,
            page_context={"page_key": "ai"},
        ),
        store_id=1,
    )

    assert result.skill.name == "promotion-roi"
    assert any(
        item.tool == "data.compare_periods" and item.data.get("dataset") == "promotion_campaigns"
        for item in result.mcp_results
    )
    comparison = next(item for item in result.diagnosis.artifacts if item.title == "推广场景同口径对比")
    assert comparison.rows
    assert {"本期ROI", "上期ROI", "预算动作"}.issubset(comparison.rows[0])
    deterministic_answer = "\n".join([result.diagnosis.headline, result.diagnosis.summary, *(item.detail for item in result.diagnosis.findings)])
    assert "盈亏" not in deterministic_answer
    assert "毛利线" not in deterministic_answer


def test_model_prompt_does_not_treat_roi_trend_as_marginal_efficiency() -> None:
    prompt = AgnesProvider._system_prompt(analysis_mode=True)
    assert "不能据此推断边际效率" in prompt
    assert "限额测试后依据结果判断" in prompt


def test_store_wide_question_keeps_overview_primary_and_loads_cross_domain_evidence() -> None:
    primary, supporting = select_skills(
        "请结合整个店铺所有数据，分析成交下降最重要的原因和动作",
        "auto",
        {"page_key": "ai"},
    )
    assert primary.descriptor.name == "shop-overview-diagnosis"
    assert {item.descriptor.name for item in supporting} >= {
        "traffic-diagnosis", "product-diagnosis", "promotion-roi", "review-diagnosis", "data-quality-audit",
    }


def test_store_wide_diagnosis_exposes_fact_artifacts_and_primary_confidence() -> None:
    result = AIAnalysisService().analyze(
        AnalysisRequest(
            question="请结合整个店铺所有数据，分析成交下降最重要的原因和动作",
            start_date=date(2026, 8, 16),
            end_date=date(2026, 8, 22),
            use_model=False,
            page_context={"page_key": "ai"},
        ),
        store_id=1,
    )

    titles = {item.title for item in result.diagnosis.artifacts}
    assert {"跨域数据状态", "总盘口径校验"}.issubset(titles)
    domain_rows = next(item.rows for item in result.diagnosis.artifacts if item.title == "跨域数据状态")
    inventory = next(item for item in domain_rows if item["经营域"] == "库存")
    assert inventory["数据时效"] == "静态/快照数据"
    assert result.diagnosis.confidence == "high"
    assert result.diagnosis.coverage.expected_days == 7


def test_store_wide_plan_compares_source_changes_not_only_current_source_levels() -> None:
    plan = AIAnalysisService._compound_evidence_plan("shop-overview-diagnosis", "全店成交下降", {"page_key": "ai"})
    assert any(
        tool == "data.compare_periods" and arguments.get("dataset") == "traffic_sources"
        for tool, arguments in plan
    )


def test_store_wide_question_with_inventory_keeps_cross_domain_workflow() -> None:
    result = AIAnalysisService().analyze(
        AnalysisRequest(
            question="为什么最近成交下降？请结合整个店铺、商品、推广、客服和库存数据",
            start_date=date(2026, 8, 16),
            end_date=date(2026, 8, 22),
            use_model=False,
            page_context={"page_key": "ai"},
        ),
        store_id=1,
    )

    assert result.skill.name == "shop-overview-diagnosis"
    assert result.mcp_results[0].tool == "overview.get_store_summary"
    assert any(item.data.get("dataset") == "inventory_snapshots" for item in result.mcp_results)


def test_model_mcp_payload_bounds_all_large_top_level_lists() -> None:
    envelope = MCPEnvelope(
        request_id="test",
        tool="data.query",
        generated_at="2026-08-23T00:00:00+08:00",
        context=AnalysisContext(range_start=date(2026, 8, 23), range_end=date(2026, 8, 23)),
        status="ok",
        data={"rows": [{"id": index} for index in range(500)], "summary": {"total": 500}},
    )
    bounded = AIAnalysisService._model_mcp_results([envelope])[0]["data"]
    assert len(bounded["rows"]) == 20
    assert bounded["summary"]["total"] == 500
    assert bounded["_truncated"][0]["total"] == 500
