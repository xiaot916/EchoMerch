import json
from types import SimpleNamespace

from app.modules.ai import provider
from app.modules.ai.schemas import Diagnosis


def test_ecommerce_methodology_is_loaded_into_model_context() -> None:
    provider._ecommerce_methodology.cache_clear()
    content = provider._ecommerce_methodology()

    assert "全量分母" in content
    assert "直播拆店播和达播" in content
    assert "不生成利润率或净利润" in content


def test_provider_sends_bounded_recent_messages_as_native_chat_history(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "继续分析结果"}}]}

    monkeypatch.setattr(
        provider,
        "settings",
        SimpleNamespace(
            ai_api_key="test-key",
            ai_model="test-model",
            ai_api_path="/v1/chat/completions",
            ai_base_url="https://example.invalid",
            ai_timeout_seconds=5,
        ),
    )

    def fake_post(*args, **kwargs):
        captured.update(kwargs["json"])
        return FakeResponse()

    monkeypatch.setattr(provider.httpx, "post", fake_post)
    answer = provider.AgnesProvider().generate_answer(
        question="那哪个最严重？",
        diagnosis=Diagnosis(headline="当前结论", summary="当前摘要"),
        evidence=[],
        context={
            "conversation_summary": "历史摘要",
            "recent_messages": [
                {"role": "user", "text": "为什么成交下降？"},
                {"role": "assistant", "text": "主要是转化率下降。"},
            ],
        },
    )

    assert answer == "继续分析结果"
    assert [item["role"] for item in captured["messages"]] == ["system", "user", "assistant", "user"]
    current = json.loads(captured["messages"][-1]["content"])
    assert "recent_messages" not in current["analysis_context"]
    assert current["question"] == "那哪个最严重？"
