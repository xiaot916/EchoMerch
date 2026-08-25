from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.core.local_database import LocalDatabase
from app.modules.notifications.providers.dingtalk import DingTalkError, DingTalkProvider
from app.modules.notifications.schemas import (
    NotificationChannel,
    NotificationChannelCreate,
    NotificationChannelUpdate,
    NotificationDelivery,
    NotificationDeliveryList,
    NotificationSendRequest,
)


CHANNELS_TABLE = "notification_channels"
DELIVERIES_TABLE = "notification_deliveries"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class NotificationService:
    def __init__(self, database_path: Path) -> None:
        self.database = LocalDatabase(Path(database_path))
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self.database.initialize_schema()
        with closing(self.database.connect(read_only=False)) as conn:
            conn.executescript(
                f"""
                create table if not exists {CHANNELS_TABLE} (
                    channel_id integer primary key autoincrement,
                    name text not null unique,
                    provider text not null default 'dingtalk',
                    webhook_env text not null,
                    secret_env text,
                    enabled integer not null default 1 check (enabled in (0, 1)),
                    created_at text not null,
                    updated_at text not null
                );
                create table if not exists {DELIVERIES_TABLE} (
                    delivery_id integer primary key autoincrement,
                    channel_id integer not null references {CHANNELS_TABLE}(channel_id) on delete restrict,
                    message_type text not null,
                    title text not null,
                    content text not null,
                    status text not null,
                    provider_code text,
                    provider_message text,
                    idempotency_key text unique,
                    requested_by text,
                    created_at text not null,
                    sent_at text
                );
                create index if not exists idx_notification_deliveries_created
                    on {DELIVERIES_TABLE}(created_at desc);
                """
            )
            conn.commit()

    @staticmethod
    def _channel(row: sqlite3.Row) -> NotificationChannel:
        webhook_env = str(row["webhook_env"])
        secret_env = str(row["secret_env"]) if row["secret_env"] else None
        return NotificationChannel(
            channel_id=int(row["channel_id"]), name=str(row["name"]), provider=str(row["provider"]),
            webhook_env=webhook_env, secret_env=secret_env, enabled=bool(row["enabled"]),
            created_at=str(row["created_at"]), updated_at=str(row["updated_at"]),
            webhook_configured=bool(os.getenv(webhook_env)),
            secret_configured=bool(secret_env and os.getenv(secret_env)),
        )

    @staticmethod
    def _delivery(row: sqlite3.Row) -> NotificationDelivery:
        return NotificationDelivery(**dict(row))

    def list_channels(self) -> list[NotificationChannel]:
        with closing(self.database.connect()) as conn:
            rows = conn.execute(f"select * from {CHANNELS_TABLE} order by name").fetchall()
        return [self._channel(row) for row in rows]

    def create_channel(self, request: NotificationChannelCreate) -> NotificationChannel:
        now = _now()
        try:
            with closing(self.database.connect(read_only=False)) as conn:
                cursor = conn.execute(
                    f"insert into {CHANNELS_TABLE} (name, provider, webhook_env, secret_env, enabled, created_at, updated_at) values (?, ?, ?, ?, ?, ?, ?)",
                    (request.name.strip(), request.provider, request.webhook_env.strip(), request.secret_env.strip() if request.secret_env else None, int(request.enabled), now, now),
                )
                channel_id = int(cursor.lastrowid)
                conn.commit()
                row = conn.execute(f"select * from {CHANNELS_TABLE} where channel_id = ?", (channel_id,)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise ValueError("通知渠道名称已存在。") from exc
        assert row is not None
        return self._channel(row)

    def update_channel(self, channel_id: int, request: NotificationChannelUpdate) -> NotificationChannel:
        now = _now()
        with closing(self.database.connect(read_only=False)) as conn:
            current = conn.execute(f"select channel_id from {CHANNELS_TABLE} where channel_id = ?", (channel_id,)).fetchone()
            if current is None:
                raise LookupError("通知渠道不存在。")
            try:
                conn.execute(
                    f"update {CHANNELS_TABLE} set name = ?, provider = ?, webhook_env = ?, secret_env = ?, enabled = ?, updated_at = ? where channel_id = ?",
                    (request.name.strip(), request.provider, request.webhook_env.strip(), request.secret_env.strip() if request.secret_env else None, int(request.enabled), now, channel_id),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                raise ValueError("通知渠道名称已存在。") from exc
            row = conn.execute(f"select * from {CHANNELS_TABLE} where channel_id = ?", (channel_id,)).fetchone()
        assert row is not None
        return self._channel(row)

    def list_deliveries(self, *, page: int = 1, page_size: int = 20) -> NotificationDeliveryList:
        offset = (page - 1) * page_size
        with closing(self.database.connect()) as conn:
            total = int(conn.execute(f"select count(*) from {DELIVERIES_TABLE}").fetchone()[0])
            rows = conn.execute(
                f"select d.*, c.name as channel_name from {DELIVERIES_TABLE} d left join {CHANNELS_TABLE} c on c.channel_id = d.channel_id order by d.created_at desc limit ? offset ?",
                (page_size, offset),
            ).fetchall()
        return NotificationDeliveryList(items=[self._delivery(row) for row in rows], total=total, page=page, page_size=page_size)

    def send(self, request: NotificationSendRequest, *, requested_by: str | None = None) -> NotificationDelivery:
        with closing(self.database.connect(read_only=False)) as conn:
            channel = conn.execute(f"select * from {CHANNELS_TABLE} where channel_id = ?", (request.channel_id,)).fetchone()
            if channel is None:
                raise LookupError("通知渠道不存在。")
            if not bool(channel["enabled"]):
                raise ValueError("通知渠道已停用。")
            if request.idempotency_key:
                existing = conn.execute(f"select d.*, c.name as channel_name from {DELIVERIES_TABLE} d left join {CHANNELS_TABLE} c on c.channel_id=d.channel_id where d.idempotency_key = ?", (request.idempotency_key,)).fetchone()
                if existing is not None:
                    return self._delivery(existing)
            now = _now()
            cursor = conn.execute(
                f"insert into {DELIVERIES_TABLE} (channel_id, message_type, title, content, status, idempotency_key, requested_by, created_at) values (?, ?, ?, ?, 'sending', ?, ?, ?)",
                (request.channel_id, request.message_type, request.title, request.content, request.idempotency_key, requested_by, now),
            )
            delivery_id = int(cursor.lastrowid)
            conn.commit()
        webhook_env = str(channel["webhook_env"])
        secret_env = str(channel["secret_env"]) if channel["secret_env"] else None
        webhook = os.getenv(webhook_env, "").strip()
        secret = os.getenv(secret_env, "").strip() if secret_env else None
        try:
            if not webhook:
                raise DingTalkError(f"通知渠道的环境变量 {webhook_env} 未配置。")
            result = DingTalkProvider(webhook, secret).send(
                message_type=request.message_type, title=request.title, content=request.content,
                at_all=request.at_all, msg_uuid=request.idempotency_key or str(uuid.uuid4()),
            )
            status, provider_code, provider_message, sent_at = "sent", result.code, result.message, _now()
        except DingTalkError as exc:
            status, provider_code, provider_message, sent_at = "failed", None, str(exc), None
        with closing(self.database.connect(read_only=False)) as conn:
            conn.execute(
                f"update {DELIVERIES_TABLE} set status = ?, provider_code = ?, provider_message = ?, sent_at = ? where delivery_id = ?",
                (status, provider_code, provider_message, sent_at, delivery_id),
            )
            conn.commit()
            row = conn.execute(f"select d.*, c.name as channel_name from {DELIVERIES_TABLE} d left join {CHANNELS_TABLE} c on c.channel_id=d.channel_id where d.delivery_id = ?", (delivery_id,)).fetchone()
        assert row is not None
        return self._delivery(row)

