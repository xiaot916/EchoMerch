"""In-memory lifecycle registry for AI streaming runs.

The registry deliberately owns orchestration state only. Conversation data and
analysis results remain in the existing AI service/database so this module can
be replaced by a shared store later without changing provider code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Literal
from uuid import uuid4


RunPhase = Literal["preparing", "streaming", "stopping", "complete", "error", "cancelled"]


class AIRunCancelled(RuntimeError):
    """Raised inside a worker when its client requested cancellation."""


@dataclass
class AIRunRecord:
    run_id: str
    kind: str
    conversation_id: str | None
    user_id: int | None
    store_id: int | None
    phase: RunPhase = "preparing"
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_event_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_count: int = 0
    revision: int = 0
    error: str | None = None
    cancel_requested: bool = False

    def snapshot(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "kind": self.kind,
            "conversation_id": self.conversation_id,
            "phase": self.phase,
            "started_at": self.started_at.isoformat(),
            "last_event_at": self.last_event_at.isoformat(),
            "event_count": self.event_count,
            "revision": self.revision,
            "error": self.error,
            "cancel_requested": self.cancel_requested,
        }


class AIRunRegistry:
    def __init__(self, *, max_records: int = 256, ttl_seconds: int = 3600) -> None:
        self.max_records = max(16, max_records)
        self.ttl = timedelta(seconds=max(60, ttl_seconds))
        self._records: dict[str, AIRunRecord] = {}
        self._lock = RLock()

    def start(
        self,
        *,
        kind: str,
        conversation_id: str | None,
        user_id: int | None,
        store_id: int | None,
    ) -> AIRunRecord:
        now = datetime.now(timezone.utc)
        record = AIRunRecord(
            run_id=str(uuid4()),
            kind=kind,
            conversation_id=conversation_id,
            user_id=user_id,
            store_id=store_id,
            started_at=now,
            last_event_at=now,
        )
        with self._lock:
            self._prune_locked(now)
            self._records[record.run_id] = record
            self._trim_locked()
        return record

    def update(self, run_id: str, *, event: str, status: str | None = None, detail: str | None = None) -> dict[str, object] | None:
        with self._lock:
            record = self._records.get(run_id)
            if record is None:
                return None
            record.last_event_at = datetime.now(timezone.utc)
            record.event_count += 1
            record.revision += 1
            if event == "run" and status in {"preparing", "streaming", "stopping", "complete", "error", "cancelled"}:
                record.phase = status  # type: ignore[assignment]
            elif event in {"planner", "skill", "mcp"}:
                record.phase = "preparing"
            elif event in {"model", "token"}:
                record.phase = "streaming"
            elif event == "final":
                record.phase = "complete"
            elif event == "error":
                record.phase = "error"
                record.error = detail or "AI 流式任务失败"
            elif event == "cancelled":
                record.phase = "cancelled"
            return record.snapshot()

    def finish(self, run_id: str, *, phase: RunPhase, error: str | None = None) -> dict[str, object] | None:
        with self._lock:
            record = self._records.get(run_id)
            if record is None:
                return None
            record.phase = phase
            record.error = error
            record.last_event_at = datetime.now(timezone.utc)
            record.revision += 1
            return record.snapshot()

    def request_cancel(self, run_id: str, *, user_id: int | None, store_id: int | None) -> bool:
        with self._lock:
            record = self._records.get(run_id)
            if not self._owned_by(record, user_id=user_id, store_id=store_id):
                return False
            if record.phase in {"complete", "error", "cancelled"}:
                return False
            record.cancel_requested = True
            record.phase = "stopping"
            record.revision += 1
            record.last_event_at = datetime.now(timezone.utc)
            return True

    def is_cancelled(self, run_id: str) -> bool:
        with self._lock:
            record = self._records.get(run_id)
            return bool(record and record.cancel_requested)

    def get(self, run_id: str, *, user_id: int | None, store_id: int | None) -> dict[str, object] | None:
        with self._lock:
            record = self._records.get(run_id)
            if not self._owned_by(record, user_id=user_id, store_id=store_id):
                return None
            return record.snapshot() if record else None

    @staticmethod
    def _owned_by(record: AIRunRecord | None, *, user_id: int | None, store_id: int | None) -> bool:
        return bool(
            record is not None
            and record.user_id == user_id
            and record.store_id == store_id
        )

    def _prune_locked(self, now: datetime) -> None:
        expired = [
            run_id for run_id, record in self._records.items()
            if record.phase in {"complete", "error", "cancelled"} and now - record.last_event_at > self.ttl
        ]
        for run_id in expired:
            self._records.pop(run_id, None)

    def _trim_locked(self) -> None:
        if len(self._records) <= self.max_records:
            return
        ordered = sorted(self._records.values(), key=lambda item: item.last_event_at)
        for record in ordered[: len(self._records) - self.max_records]:
            if record.phase in {"complete", "error", "cancelled"}:
                self._records.pop(record.run_id, None)


_registry = AIRunRegistry()


def get_ai_run_registry() -> AIRunRegistry:
    return _registry
