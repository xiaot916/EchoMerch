from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl
from urllib.request import Request, urlopen


class DingTalkError(RuntimeError):
    """Safe provider error that never includes webhook or signing credentials."""


@dataclass(frozen=True)
class DingTalkResult:
    code: str
    message: str


class DingTalkProvider:
    def __init__(self, webhook: str, secret: str | None = None, timeout: float = 10.0) -> None:
        if not webhook.startswith(("http://", "https://")):
            raise DingTalkError("钉钉 Webhook 必须是 http/https 地址。")
        self.webhook = webhook
        self.secret = secret or None
        self.timeout = timeout

    def _url(self) -> str:
        if not self.secret:
            return self.webhook
        timestamp = str(int(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}".encode("utf-8")
        digest = hmac.new(self.secret.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
        # Keep the raw base64 value here; urlencode performs the single
        # required URL encoding when rebuilding the query string.
        sign = base64.b64encode(digest).decode("ascii")
        parts = urlsplit(self.webhook)
        query = parse_qsl(parts.query, keep_blank_values=True)
        query.extend((("timestamp", timestamp), ("sign", sign)))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))

    def send(self, *, message_type: str, title: str, content: str, at_all: bool, msg_uuid: str | None) -> DingTalkResult:
        if message_type == "text":
            payload: dict[str, object] = {
                "msgtype": "text",
                "text": {"content": content},
                "at": {"isAtAll": at_all},
            }
        else:
            payload = {
                "msgtype": "markdown",
                "markdown": {"title": title, "text": content},
                "at": {"isAtAll": at_all},
            }
        if msg_uuid:
            payload["msgUuid"] = msg_uuid
        request = Request(
            self._url(),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except Exception as exc:  # pragma: no cover - exercised through the service error path
            raise DingTalkError("钉钉消息请求失败，请检查网络和机器人配置。") from exc
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DingTalkError("钉钉返回了无法解析的响应。") from exc
        code = str(result.get("errcode", "unknown"))
        message = str(result.get("errmsg", ""))[:500]
        if code not in {"0", "None"}:
            raise DingTalkError(f"钉钉拒绝了消息（错误码 {code}）：{message or '未知错误'}")
        return DingTalkResult(code=code, message=message or "ok")
