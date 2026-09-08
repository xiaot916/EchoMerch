"""Model-context budgeting independent from business and provider logic."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextBudgetResult:
    messages: list[dict[str, str]]
    raw_chars: int
    sent_chars: int
    excluded_count: int
    exclusion_reason: str | None
    overflow: bool


def build_model_messages(
    *,
    system_prompt: str,
    question: str,
    diagnosis: dict[str, Any],
    evidence: list[dict],
    mcp_results: list[dict],
    context: dict[str, Any] | None,
    max_input_chars: int = 100_000,
    recent_message_limit: int = 6,
    recent_message_chars: int = 4_000,
) -> ContextBudgetResult:
    """Build bounded chat messages and report why context was excluded.

    Character budgeting is intentionally provider-neutral. It is predictable,
    cheap, and leaves the provider free to replace it with a tokenizer later.
    """
    analysis_context = dict(context or {})
    recent_messages = analysis_context.pop("recent_messages", [])
    history: list[dict[str, str]] = []
    if isinstance(recent_messages, list):
        for item in recent_messages[-recent_message_limit:]:
            if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
                continue
            content = str(item.get("text") or "").strip()
            if content:
                history.append({"role": str(item["role"]), "content": content[:recent_message_chars]})

    raw_payload = {
        "question": question,
        "diagnosis": diagnosis,
        "evidence": evidence,
        "mcp_results": mcp_results,
        "analysis_context": analysis_context,
    }
    raw_user_content = _dumps(raw_payload)
    messages = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": raw_user_content}]
    raw_chars = _message_chars(messages)
    if raw_chars <= max_input_chars:
        return ContextBudgetResult(messages, raw_chars, raw_chars, 0, None, False)

    excluded_count = 0
    while history and _message_chars([{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": raw_user_content}]) > max_input_chars:
        history.pop(0)
        excluded_count += 1

    compact_payload = raw_payload
    for list_limit, string_limit in ((20, 1_000), (10, 600), (5, 400), (2, 240), (1, 160)):
        compact_payload, omitted = _compact(raw_payload, list_limit=list_limit, string_limit=string_limit)
        if isinstance(compact_payload, dict) and omitted:
            compact_context = compact_payload.setdefault("analysis_context", {})
            if isinstance(compact_context, dict):
                compact_context["_context_budget"] = {"excluded_count": omitted, "reason": "input_budget"}
        user_content = _dumps(compact_payload)
        candidate = [{"role": "system", "content": system_prompt}, *history, {"role": "user", "content": user_content}]
        if _message_chars(candidate) <= max_input_chars:
            excluded_count += omitted
            sent_chars = _message_chars(candidate)
            return ContextBudgetResult(candidate, raw_chars, sent_chars, excluded_count, "input_budget", False)

    fallback_payload = {
        "question": question[:4_000],
        "diagnosis": compact_payload.get("diagnosis", {}),
        "analysis_context": compact_payload.get("analysis_context", {}),
        "context_notice": "明细证据超过输入预算，已保留诊断、范围与口径；不得将被排除数据推断为 0。",
        "context_budget": {"reason": "input_budget_exceeded", "excluded_count": excluded_count + 1},
    }
    user_content = _dumps(fallback_payload)
    candidate = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}]
    sent_chars = _message_chars(candidate)
    overflow = sent_chars > max_input_chars
    if overflow:
        allowed = max(1_000, max_input_chars - len(system_prompt) - 200)
        fallback_payload["diagnosis"] = {"headline": str(diagnosis.get("headline") or "")[:500]}
        fallback_payload["analysis_context"] = {
            key: value for key, value in analysis_context.items()
            if isinstance(value, (str, int, float, bool, type(None)))
        }
        fallback_payload["question"] = question[:allowed]
        user_content = _dumps(fallback_payload)
        candidate = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}]
        sent_chars = _message_chars(candidate)
        overflow = sent_chars > max_input_chars
    return ContextBudgetResult(candidate, raw_chars, sent_chars, excluded_count + 1, "input_budget_exceeded" if overflow else "input_budget", overflow)


def _compact(value: Any, *, list_limit: int, string_limit: int, depth: int = 0) -> tuple[Any, int]:
    if isinstance(value, list):
        compacted = []
        omitted = max(0, len(value) - list_limit)
        for item in value[:list_limit]:
            next_value, next_omitted = _compact(item, list_limit=list_limit, string_limit=string_limit, depth=depth + 1)
            compacted.append(next_value)
            omitted += next_omitted
        return compacted, omitted
    if isinstance(value, dict):
        if depth >= 7:
            scalars = {
                str(key): item for key, item in value.items()
                if isinstance(item, (str, int, float, bool, type(None))) and len(str(item)) <= string_limit
            }
            return scalars, max(0, len(value) - len(scalars))
        compacted: dict[str, Any] = {}
        omitted = 0
        for key, item in value.items():
            next_value, next_omitted = _compact(item, list_limit=list_limit, string_limit=string_limit, depth=depth + 1)
            compacted[str(key)] = next_value
            omitted += next_omitted
        return compacted, omitted
    if isinstance(value, str) and len(value) > string_limit:
        return f"{value[:string_limit]}...", 1
    return value, 0


def _dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _message_chars(messages: list[dict[str, str]]) -> int:
    return sum(len(item.get("role", "")) + len(item.get("content", "")) for item in messages)
