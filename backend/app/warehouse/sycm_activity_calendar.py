from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CHINA_TIMEZONE = timezone(timedelta(hours=8))

ACTIVITY_ENDPOINT_KEY = "sycm.datawar.v4.activity.act_list.get_activity_calendar"
DEFAULT_PLATFORM_STORE_ID = "2200573698992"
PARSER_VERSION = "sycm-activity-calendar-v2"

ACTIVITY_ID_KEYS = (
    "activityId",
    "actId",
    "id",
    "activityNo",
    "actNo",
    "bizId",
    "calendarId",
    "schemeId",
)
ACTIVITY_NAME_KEYS = ("activityName", "actName", "name", "title")
ACTIVITY_TYPE_KEYS = ("activityType", "actType", "type", "activityTypeName")
ACTIVITY_STATUS_KEYS = ("activityStatus", "actStatus", "status", "state")
ACTIVITY_START_KEYS = (
    "activityStart",
    "activityStartTime",
    "startTime",
    "beginTime",
    "startDate",
    "beginDate",
    "activityStartDate",
)
ACTIVITY_END_KEYS = (
    "activityEnd",
    "activityEndTime",
    "endTime",
    "finishTime",
    "endDate",
    "finishDate",
    "activityEndDate",
)
SIGNUP_START_KEYS = (
    "signupStartTime",
    "signStartTime",
    "registrationStartTime",
    "applyStartTime",
    "signupBeginTime",
    "regStartTime",
)
SIGNUP_END_KEYS = (
    "signupEndTime",
    "signEndTime",
    "registrationEndTime",
    "applyEndTime",
    "signupFinishTime",
    "regEndTime",
)
ACTIVITY_TAG_KEYS = ("activityTag", "tag", "tags", "label")
ACTIVITY_LEVEL_KEYS = ("activityLevel", "level")
ACTIVITY_STAGE_KEYS = ("activityStage", "stage")
PARTICIPATION_STATUS_KEYS = (
    "shopParticipationStatus",
    "participationStatus",
    "shopStatus",
    "joinStatus",
    "storeJoinStatus",
)
DATE_KEYS = (
    "date",
    "day",
    "bizDate",
    "statDate",
    "calendarDate",
    "activityDate",
    "actDate",
    "activityStart",
    "activityStartTime",
    "startTime",
    "beginTime",
    "startDate",
    "beginDate",
    "activityStartDate",
)


class SycmActivityCalendarPayloadError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedActivityCalendarEvent:
    business_day: date
    activity_id: str
    activity_name: str
    activity_type: str
    activity_status: str
    activity_start_time: str
    activity_end_time: str
    signup_start_time: str
    signup_end_time: str
    activity_tag: str
    activity_level: str
    activity_stage: str
    shop_participation_status: str


@dataclass(frozen=True)
class ParsedSycmActivityCalendar:
    platform_store_id: str
    query_date: date
    covered_days: tuple[date, ...]
    events: list[ParsedActivityCalendarEvent]
    response_code: int
    source_sha256: str
    source_bytes: int
    endpoint_key: str
    parser_version: str


def load_and_parse(
    path: Path,
    query_date: date,
    fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID,
) -> ParsedSycmActivityCalendar:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    return parse_payload(
        payload,
        query_date=query_date,
        raw=raw,
        fallback_platform_store_id=fallback_platform_store_id,
    )


def parse_payload(
    payload: dict[str, Any],
    query_date: date,
    raw: bytes | None = None,
    fallback_platform_store_id: str = DEFAULT_PLATFORM_STORE_ID,
) -> ParsedSycmActivityCalendar:
    root = payload.get("content") if isinstance(payload.get("content"), dict) else payload
    response_code = _as_int(root.get("code"))
    if response_code not in (0, 200):
        message = _first_text(root, ("message", "msg", "errorMsg")) or "unknown response error"
        raise SycmActivityCalendarPayloadError(
            f"SYCM activity calendar response failed: {message}"
        )
    if root.get("success") is False:
        message = _first_text(root, ("message", "msg", "errorMsg")) or "unknown response error"
        raise SycmActivityCalendarPayloadError(
            f"SYCM activity calendar response failed: {message}"
        )

    data_root = _select_data_root(root)
    platform_store_id = (
        _recursive_find_text((root, data_root), ("sellerId", "shopId", "mainUserId", "userId"))
        or fallback_platform_store_id
    )

    events: list[ParsedActivityCalendarEvent] = []
    covered_days: set[date] = set()
    seen_signatures: set[tuple[str, ...]] = set()

    def walk(node: object, inherited_day: date | None = None) -> None:
        if isinstance(node, list):
            for item in node:
                walk(item, inherited_day)
            return
        if not isinstance(node, dict):
            return

        node_day = _extract_day(node) or inherited_day

        if _looks_like_activity_event(node):
            event_day = node_day or query_date
            event = _build_event(node, event_day)
            signature = (
                event.business_day.isoformat(),
                event.activity_id,
                event.activity_name,
                event.activity_type,
                event.activity_status,
                event.activity_start_time,
                event.activity_end_time,
                event.signup_start_time,
                event.signup_end_time,
            )
            if signature not in seen_signatures:
                seen_signatures.add(signature)
                events.append(event)
                covered_days.add(event.business_day)
            return

        for value in node.values():
            if isinstance(value, (dict, list)):
                walk(value, node_day)

    walk(data_root)

    source_bytes = len(raw) if raw is not None else 0
    source_sha256 = hashlib.sha256(raw or b"").hexdigest()
    return ParsedSycmActivityCalendar(
        platform_store_id=platform_store_id,
        query_date=query_date,
        covered_days=tuple(sorted(covered_days or {query_date})),
        events=events,
        response_code=response_code,
        source_sha256=source_sha256,
        source_bytes=source_bytes,
        endpoint_key=ACTIVITY_ENDPOINT_KEY,
        parser_version=PARSER_VERSION,
    )


def _select_data_root(root: dict[str, Any]) -> object:
    for key in ("data", "result", "list", "items", "rows"):
        value = root.get(key)
        if isinstance(value, (dict, list)):
            return value
    return root


def _looks_like_activity_event(node: dict[str, Any]) -> bool:
    score = 0
    if _first_text(node, ACTIVITY_ID_KEYS):
        score += 1
    if _first_text(node, ACTIVITY_NAME_KEYS):
        score += 1
    if _first_text(node, ACTIVITY_TYPE_KEYS):
        score += 1
    if _first_text(node, ACTIVITY_STATUS_KEYS):
        score += 1
    if _extract_day(node) is not None:
        score += 1
    if _first_text(node, ACTIVITY_START_KEYS) or _first_text(node, ACTIVITY_END_KEYS):
        score += 1
    if _first_text(node, SIGNUP_START_KEYS) or _first_text(node, SIGNUP_END_KEYS):
        score += 1
    return score >= 2


def _build_event(node: dict[str, Any], business_day: date) -> ParsedActivityCalendarEvent:
    event_day = _extract_day(node) or business_day
    activity_name = html.unescape(_first_text(node, ACTIVITY_NAME_KEYS))
    activity_id = _first_text(node, ACTIVITY_ID_KEYS)
    activity_type = html.unescape(_first_text(node, ACTIVITY_TYPE_KEYS))
    activity_status = html.unescape(_first_text(node, ACTIVITY_STATUS_KEYS))
    activity_start_time = _first_time_text(node, ACTIVITY_START_KEYS)
    activity_end_time = _first_time_text(node, ACTIVITY_END_KEYS)
    signup_start_time = _first_time_text(node, SIGNUP_START_KEYS)
    signup_end_time = _first_time_text(node, SIGNUP_END_KEYS)
    activity_tag = html.unescape(_first_text(node, ACTIVITY_TAG_KEYS))
    activity_level = html.unescape(_first_text(node, ACTIVITY_LEVEL_KEYS))
    activity_stage = html.unescape(_first_text(node, ACTIVITY_STAGE_KEYS))
    shop_participation_status = html.unescape(_first_text(node, PARTICIPATION_STATUS_KEYS))

    if not activity_id:
        activity_id = _stable_activity_id(
            event_day,
            activity_name,
            activity_type,
            activity_status,
            activity_start_time,
            activity_end_time,
            signup_start_time,
            signup_end_time,
            activity_tag,
            activity_level,
            activity_stage,
            shop_participation_status,
        )

    return ParsedActivityCalendarEvent(
        business_day=event_day,
        activity_id=activity_id,
        activity_name=activity_name,
        activity_type=activity_type,
        activity_status=activity_status,
        activity_start_time=activity_start_time,
        activity_end_time=activity_end_time,
        signup_start_time=signup_start_time,
        signup_end_time=signup_end_time,
        activity_tag=activity_tag,
        activity_level=activity_level,
        activity_stage=activity_stage,
        shop_participation_status=shop_participation_status,
    )


def _stable_activity_id(business_day: date, *parts: str) -> str:
    digest = hashlib.sha1(
        "|".join([business_day.isoformat(), *parts]).encode("utf-8")
    ).hexdigest()
    return f"auto-{digest[:24]}"


def _extract_day(node: dict[str, Any]) -> date | None:
    for key in DATE_KEYS:
        values = _date_values(node.get(key))
        if values:
            return values[0]
    return None


def _date_values(value: object) -> list[date]:
    if isinstance(value, list):
        values: list[date] = []
        for item in value:
            parsed = _parse_date(item)
            if parsed is not None:
                values.append(parsed)
        return values
    parsed = _parse_date(value)
    return [parsed] if parsed is not None else []


def _recursive_find_text(node: object, keys: tuple[str, ...]) -> str:
    if isinstance(node, dict):
        text = _first_text(node, keys)
        if text:
            return text
        for value in node.values():
            found = _recursive_find_text(value, keys)
            if found:
                return found
        return ""
    if isinstance(node, (list, tuple)):
        for item in node:
            found = _recursive_find_text(item, keys)
            if found:
                return found
    return ""


def _first_text(node: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        if key not in node:
            continue
        text = _to_text(node.get(key))
        if text:
            return text
    return ""


def _first_time_text(node: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        if key not in node:
            continue
        text = _format_datetime_text(node.get(key))
        if text:
            return text
    return ""


def _format_datetime_text(value: object) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, list):
        texts = [_format_datetime_text(item) for item in value]
        return "、".join(text for text in texts if text)
    if isinstance(value, dict):
        for key in ("value", "time", "date", "text", "name", "label"):
            if key in value:
                text = _format_datetime_text(value.get(key))
                if text:
                    return text
        return ""
    if isinstance(value, datetime):
        parsed = value.astimezone(CHINA_TIMEZONE) if value.tzinfo else value
        return parsed.replace(tzinfo=None).isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        parsed = _timestamp_to_datetime(int(value))
        return parsed.isoformat(sep=" ", timespec="seconds") if parsed else ""

    text = html.unescape(str(value).strip())
    if not text:
        return ""
    if re.fullmatch(r"\d{10,13}", text):
        parsed = _timestamp_to_datetime(int(text))
        return parsed.isoformat(sep=" ", timespec="seconds") if parsed else ""

    normalized = text.replace("/", "-").replace("T", " ")
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return text
    if parsed.tzinfo:
        parsed = parsed.astimezone(CHINA_TIMEZONE).replace(tzinfo=None)
    return parsed.isoformat(sep=" ", timespec="seconds")


def _to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        texts = [_to_text(item) for item in value]
        return "、".join(text for text in texts if text)
    if isinstance(value, dict):
        for key in ("value", "text", "name", "label", "title", "desc", "code"):
            nested = value.get(key)
            text = _to_text(nested)
            if text:
                return text
        return ""
    return str(value).strip()


def _parse_date(value: object) -> date | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, (int, float)):
        return _timestamp_to_date(int(value))

    text = str(value).strip()
    if not text:
        return None

    if re.fullmatch(r"\d{10,13}", text):
        return _timestamp_to_date(int(text))

    normalized = text.replace("/", "-").replace("T", " ")
    if len(normalized) >= 10:
        candidate = normalized[:10]
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(normalized.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _timestamp_to_date(value: int) -> date | None:
    parsed = _timestamp_to_datetime(value)
    return parsed.date() if parsed else None


def _timestamp_to_datetime(value: int) -> datetime | None:
    if value <= 0:
        return None
    timestamp_ms = value if value >= 10**11 else value * 1000
    try:
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=CHINA_TIMEZONE).replace(
            tzinfo=None
        )
    except (OverflowError, OSError, ValueError):
        return None


def _as_int(value: object) -> int:
    if value is None or isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
