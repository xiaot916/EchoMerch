from __future__ import annotations

import json
from pathlib import Path

from app.modules.notifications.providers import dingtalk
from app.modules.notifications.providers.dingtalk import DingTalkProvider
from app.modules.notifications.schemas import NotificationChannelCreate, NotificationSendRequest
from app.modules.notifications.service import NotificationService


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self) -> bytes:
        return b'{"errcode": 0, "errmsg": "ok"}'


def test_dingtalk_signing_and_payload_are_built_without_network(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(dingtalk, "urlopen", fake_urlopen)
    result = DingTalkProvider("https://example.test/robot?access_token=masked", "secret-value").send(
        message_type="markdown", title="标题", content="## 内容", at_all=True, msg_uuid="id-1"
    )

    assert result.code == "0"
    assert "timestamp=" in str(captured["url"])
    assert "sign=" in str(captured["url"])
    assert captured["body"] == {
        "msgtype": "markdown",
        "markdown": {"title": "标题", "text": "## 内容"},
        "at": {"isAtAll": True},
        "msgUuid": "id-1",
    }


def test_service_records_failed_delivery_without_exposing_secret(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_DINGTALK_WEBHOOK", "")
    service = NotificationService(tmp_path / "notifications.sqlite3")
    channel = service.create_channel(
        NotificationChannelCreate(
            name="测试群", webhook_env="TEST_DINGTALK_WEBHOOK", secret_env=None,
        )
    )

    delivery = service.send(
        NotificationSendRequest(
            channel_id=channel.channel_id, message_type="text", title="测试", content="不会真实发送",
            idempotency_key="delivery-1",
        ),
        requested_by="tester",
    )

    assert delivery.status == "failed"
    assert delivery.provider_message is not None
    assert "TEST_DINGTALK_WEBHOOK" in delivery.provider_message
    assert "secret-value" not in delivery.provider_message
    assert service.list_deliveries().total == 1
    assert service.send(
        NotificationSendRequest(
            channel_id=channel.channel_id, message_type="text", title="重复", content="重复请求",
            idempotency_key="delivery-1",
        )
    ).delivery_id == delivery.delivery_id
