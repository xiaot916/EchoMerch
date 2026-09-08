from datetime import date

import pytest

from app.modules.ai.schemas import AnalysisRequest, AIConversationState
from app.modules.ai.service import AIAnalysisService


def test_conversation_keeps_structured_responses_and_more_than_eight_turns(tmp_path) -> None:
    service = AIAnalysisService(database_path=tmp_path / "ai-context.sqlite3")
    response = service.analyze(
        AnalysisRequest(
            question="为什么昨天成交下降？",
            start_date=date(2026, 8, 20),
            end_date=date(2026, 8, 20),
            use_model=False,
        ),
        store_id=1,
        user_id=7,
    )
    state = service._conversation_state(response.conversation_id, user_id=7, store_id=1)

    for index in range(9):
        service._remember(
            state,
            user_id=7,
            store_id=1,
            question=f"继续追问 {index}",
            answer=response.answer,
            memory={**state.memory, "summary": response.diagnosis.headline, "last_question": f"继续追问 {index}"},
            response=response,
        )

    detail = service.get_conversation(response.conversation_id, user_id=7, store_id=1)
    assert len(detail.recent_messages) == 20
    assert [item.role for item in detail.recent_messages[:4]] == ["user", "assistant", "user", "assistant"]
    assistant = next(item for item in detail.recent_messages if item.role == "assistant" and item.payload)
    assert assistant.payload["kind"] == "analysis"
    assert assistant.payload["data"]["diagnosis"]["headline"] == response.diagnosis.headline

    bounded = service._conversation_state(response.conversation_id, user_id=7, store_id=1)
    assert len(bounded.recent_messages) == 8


def test_inventory_analysis_persists_date_values_in_memory(tmp_path) -> None:
    service = AIAnalysisService(database_path=tmp_path / "ai-inventory-context.sqlite3")
    result = service.analyze(
        AnalysisRequest(question="查一下大鱼 M 码库存", use_model=False),
        store_id=1,
        user_id=7,
    )

    assert result.status in {"ok", "partial", "no_data"}
    state = service._conversation_state(result.conversation_id, user_id=7, store_id=1)
    assert state.memory.get("last_question") == "查一下大鱼 M 码库存"


def test_conversation_is_strictly_scoped_to_store(tmp_path) -> None:
    service = AIAnalysisService(database_path=tmp_path / "ai-store-scope.sqlite3")
    state = service._conversation_state(None, user_id=7, store_id=1)

    with pytest.raises(ValueError, match="会话不存在"):
        service._conversation_state(state.conversation_id, user_id=7, store_id=2, create=False)

    assert service.list_conversations(user_id=7, store_id=2) == []


def test_only_explicit_follow_up_references_expand_previous_context() -> None:
    state = AIConversationState(
        conversation_id="conversation-123",
        summary="上一轮结论",
        memory={
            "last_question": "推广预算怎么分",
            "headline": "全站推广优先",
            "skill": "promotion-budget-planning",
            "planning_inputs": {"total_budget": 500000, "target_roi": 3.5},
            "timeline": [{"headline": "全站推广优先"}],
        },
    )

    standalone = AnalysisRequest(question="查库存", use_model=False)
    assert AIAnalysisService._contextual_request(standalone, state).question == "查库存"

    follow_up = AnalysisRequest(question="按上面的方案把预算改成 60 万", use_model=False)
    expanded = AIAnalysisService._contextual_request(follow_up, state).question
    assert expanded == "按上面的方案把预算改成 60 万"
    context = AIAnalysisService._contextual_request(follow_up, state).page_context["conversation_context"]
    assert context["planning_inputs"]["total_budget"] == 500000

    short_follow_up = AnalysisRequest(question="哪个最严重？", use_model=False)
    assert AIAnalysisService._contextual_request(short_follow_up, state).page_context["conversation_context"]["headline"] == "全站推广优先"
