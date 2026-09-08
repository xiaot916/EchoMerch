import json

from app.modules.ai.context_budget import build_model_messages


def test_context_budget_preserves_small_payload_without_exclusions():
    result = build_model_messages(
        system_prompt="system",
        question="为什么成交下降？",
        diagnosis={"headline": "成交下降"},
        evidence=[{"dataset": "store_overview"}],
        mcp_results=[{"data": {"gmv": 100}}],
        context={"recent_messages": [{"role": "user", "text": "上一轮问题"}]},
        max_input_chars=10_000,
    )

    assert result.exclusion_reason is None
    assert result.excluded_count == 0
    assert result.overflow is False
    assert [item["role"] for item in result.messages] == ["system", "user", "user"]


def test_context_budget_drops_old_history_and_samples_large_evidence():
    history = [{"role": "user" if index % 2 == 0 else "assistant", "text": f"历史{index}-" + "x" * 500} for index in range(8)]
    rows = [{"item_id": index, "name": "商品" + "长描述" * 80} for index in range(100)]
    result = build_model_messages(
        system_prompt="system",
        question="分析全部商品，但缺失日期不要当作 0",
        diagnosis={"headline": "商品分析", "coverage": {"missing_dates": ["2026-08-27"]}, "artifacts": [{"rows": rows}]},
        evidence=rows,
        mcp_results=[{"data": {"rows": rows, "total": 100}}],
        context={"recent_messages": history, "memory_rules": "缺失日期不能按 0"},
        max_input_chars=8_000,
    )

    assert result.raw_chars > result.sent_chars
    assert result.sent_chars <= 8_000
    assert result.exclusion_reason == "input_budget"
    assert result.excluded_count > 0
    assert result.overflow is False
    payload = json.loads(result.messages[-1]["content"])
    assert payload["diagnosis"]["coverage"]["missing_dates"] == ["2026-08-27"]
    assert payload["analysis_context"]["memory_rules"] == "缺失日期不能按 0"
