from __future__ import annotations

from pydantic import BaseModel, Field


class NotificationChannelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    provider: str = Field(default="dingtalk", pattern="^dingtalk$")
    webhook_env: str = Field(min_length=1, max_length=120, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    secret_env: str | None = Field(default=None, max_length=120, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    enabled: bool = True


class NotificationChannelUpdate(NotificationChannelCreate):
    pass


class NotificationChannel(NotificationChannelCreate):
    channel_id: int
    created_at: str
    updated_at: str
    webhook_configured: bool = False
    secret_configured: bool = False


class NotificationSendRequest(BaseModel):
    channel_id: int = Field(gt=0)
    message_type: str = Field(default="markdown", pattern="^(text|markdown)$")
    title: str = Field(default="EchoMerch 通知", max_length=120)
    content: str = Field(min_length=1, max_length=20000)
    at_all: bool = False
    idempotency_key: str | None = Field(default=None, max_length=120)


class NotificationDelivery(BaseModel):
    delivery_id: int
    channel_id: int
    channel_name: str | None = None
    message_type: str
    title: str
    content: str
    status: str
    provider_code: str | None = None
    provider_message: str | None = None
    idempotency_key: str | None = None
    requested_by: str | None = None
    created_at: str
    sent_at: str | None = None


class NotificationDeliveryList(BaseModel):
    items: list[NotificationDelivery] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20

