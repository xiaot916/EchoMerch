from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, unquote, urlsplit

from app.modules.captures.storage import CaptureStore

FILE_RE = re.compile(
    r"^(?P<timestamp>\d+)-(?P<session>\d+)-(?P<sequence>\d+)-(?P<kind>.+)\.reqable$",
    re.IGNORECASE,
)
URL_RE = re.compile(r"""(?i)(?:https?://|//)[a-z0-9.-]+(?::\d+)?/[^\s"'<>\\\]}]+""")
PATH_RE = re.compile(
    r"""(?<![a-z0-9])/(?:[a-z0-9_.-]+/){1,}[a-z0-9_.-]+(?:\?[^"'<>\\\s]*)?""",
    re.IGNORECASE,
)
SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_./~%+-]+$")
FORM_KEY_RE = re.compile(r"^[a-zA-Z0-9_.:%+\-\[\]]{1,120}$")
SENSITIVE_KEY_RE = re.compile(
    r"(?i)(cookie|authorization|token|sign|session|password|passwd|secret|"
    r"account|seller.?id|shop.?id|user.?id|uid|buyer.?id|order.?id|"
    r"device.?id|umid|bx-)",
)
STATIC_PATH_RE = re.compile(
    r"(?i)\.(?:js|css|map|png|jpg|jpeg|gif|webp|svg|ico|woff2?|ttf|eot)$"
)
PLATFORM_HOST_RE = re.compile(
    r"(?i)(?:taobao|tmall|alibaba|alimama|alicdn|qn\.|sycm\.)"
)
MAX_ANALYSIS_BYTES = 1 * 1024 * 1024
MAX_SHAPE_NODES = 2000


@dataclass(frozen=True)
class ParsedCapture:
    source_name: str
    capture_at: datetime
    session_id: str
    sequence: int
    kind: str
    size_bytes: int
    sha256: str
    is_binary: bool
    is_json_like: bool
    sensitive_field_count: int
    endpoints: tuple[dict[str, str], ...]
    fields: tuple[dict[str, str], ...]
    shape: tuple[dict[str, str], ...]
    daily_candidate: dict[str, str] | None


def parse_capture_filename(path: Path) -> tuple[datetime, str, int, str] | None:
    match = FILE_RE.match(path.name)
    if not match:
        return None

    raw_timestamp = int(match.group("timestamp"))
    if len(match.group("timestamp")) >= 16:
        timestamp_seconds = raw_timestamp / 1_000_000
    elif len(match.group("timestamp")) >= 13:
        timestamp_seconds = raw_timestamp / 1_000
    else:
        timestamp_seconds = float(raw_timestamp)

    capture_at = datetime.fromtimestamp(timestamp_seconds, tz=timezone.utc).astimezone()
    return (
        capture_at,
        match.group("session"),
        int(match.group("sequence")),
        match.group("kind").lower(),
    )


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decode_text(data: bytes) -> str | None:
    if not data:
        return ""
    if data.startswith((b"RIFF", b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"PK\x03\x04")):
        return None

    text = data.decode("utf-8", errors="replace")
    if text.count("\ufffd") > max(4, len(text) // 100):
        return None
    return text.replace("\x00", "")


def _safe_segment(value: object) -> str:
    text = str(value)
    return "<sensitive>" if SENSITIVE_KEY_RE.search(text) else text


def _safe_field_path(parts: Iterable[object]) -> str:
    return ".".join(_safe_segment(part) for part in parts)


def _value_kind(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return type(value).__name__


def _walk_shape(
    value: object,
    path: tuple[object, ...] = (),
    *,
    nodes: list[int] | None = None,
) -> list[dict[str, str]]:
    counter = nodes or [0]
    counter[0] += 1
    if counter[0] > MAX_SHAPE_NODES:
        return []

    current_path = _safe_field_path(path) or "$"
    kind = _value_kind(value)
    rows = [{"path": current_path, "kind": kind}]
    if isinstance(value, dict):
        for key, child in list(value.items())[:500]:
            rows.extend(_walk_shape(child, path + (key,), nodes=counter))
    elif isinstance(value, list) and value:
        rows.extend(_walk_shape(value[0], path + ("[]",), nodes=counter))
    return rows


def _parse_payload(text: str) -> tuple[object | None, bool]:
    stripped = text.strip()
    if not stripped:
        return None, False

    try:
        return json.loads(stripped), True
    except json.JSONDecodeError:
        pass

    if (
        "=" in stripped
        and "&" in stripped
        and "\n" not in stripped[:5000]
        and len(stripped) < 256_000
    ):
        parsed = parse_qs(stripped, keep_blank_values=True)
        if parsed and all(FORM_KEY_RE.match(unquote(key)) for key in parsed):
            normalized: dict[str, object] = {}
            for key, values in parsed.items():
                value = values[-1] if values else ""
                decoded = unquote(value)
                try:
                    normalized[key] = json.loads(decoded)
                except json.JSONDecodeError:
                    normalized[key] = decoded
            return normalized, True
    return None, False


def _daily_candidate(payload: object | None, kind: str) -> dict[str, str] | None:
    if "req" not in kind or not isinstance(payload, dict):
        return None

    candidate_keys = {
        "dateRange",
        "dateType",
        "startDate",
        "endDate",
        "startTime",
        "endTime",
        "page",
        "pageSize",
        "indexCode",
        "pathInfo",
        "indexCodes",
    }
    observed = {key: payload.get(key) for key in candidate_keys if key in payload}
    if not observed:
        return None

    business_date = None
    date_mode = "unknown"
    date_range = str(payload.get("dateRange") or "")
    if re.match(r"^\d{4}-\d{2}-\d{2}\|\d{4}-\d{2}-\d{2}$", date_range):
        start, end = date_range.split("|", 1)
        if start == end:
            business_date = start
            date_mode = "dateRange_day"
    elif payload.get("startDate") and payload.get("endDate"):
        start = str(payload.get("startDate"))
        end = str(payload.get("endDate"))
        if re.match(r"^\d{4}-\d{2}-\d{2}$", start) and start == end:
            business_date = start
            date_mode = "date_pair"
    elif payload.get("startTime") and payload.get("endTime"):
        date_mode = "epoch_ms_range"

    if date_mode == "unknown":
        return None
    safe_params = {
        key: "<sensitive>" if SENSITIVE_KEY_RE.search(key) else str(value)
        for key, value in sorted(observed.items())
    }
    return {
        "business_date": business_date or "",
        "date_mode": date_mode,
        "params_json": json.dumps(safe_params, ensure_ascii=False, sort_keys=True),
    }


def _is_llm_payload(payload: object | None, text: str) -> bool:
    if isinstance(payload, dict):
        keys = set(payload)
        if "model" in keys and keys.intersection({"instructions", "messages", "input", "tools"}):
            return True
        if "customInstructions" in keys or "conversation_history" in keys:
            return True
    prefix = text[:4000]
    return '"model"' in prefix and "You are Codex" in prefix


def _normalize_endpoint(value: str) -> tuple[str, str] | None:
    candidate = value.strip().strip("`'\";,)")
    if candidate.startswith("//"):
        candidate = "https:" + candidate
    if not candidate.startswith(("http://", "https://")):
        return None

    parsed = urlsplit(candidate)
    host = (parsed.hostname or "").lower()
    path = unquote(parsed.path or "/").split("#", 1)[0].rstrip("/")
    if not host or not path or not PLATFORM_HOST_RE.search(host):
        return None
    if STATIC_PATH_RE.search(path):
        return None
    if not SAFE_PATH_RE.match(path):
        return None
    if len(path) > 300:
        return None
    return host, path


def _extract_endpoints(text: str, kind: str) -> tuple[dict[str, str], ...]:
    found: dict[tuple[str, str], str] = {}
    source_text = text[:MAX_ANALYSIS_BYTES]
    decoded_text = unquote(source_text) if "%" in source_text else ""
    for match in URL_RE.finditer(source_text):
        normalized = _normalize_endpoint(match.group(0))
        if normalized:
            found[normalized] = "url"
    if decoded_text:
        for match in URL_RE.finditer(decoded_text):
            normalized = _normalize_endpoint(match.group(0))
            if normalized:
                found[normalized] = "decoded_url"

    path_source = decoded_text or source_text
    for match in PATH_RE.finditer(path_source):
        path = unquote(match.group(0)).split("?", 1)[0].rstrip("/")
        if STATIC_PATH_RE.search(path) or len(path) > 240 or not SAFE_PATH_RE.match(path):
            continue
        first_segment = path.strip("/").split("/", 1)[0]
        if "." in first_segment:
            continue
        if path.startswith("/api/v1/"):
            continue
        if not any(
            marker in path.lower()
            for marker in (
                ".json",
                "/api/",
                "/portal/",
                "/oneauth/",
                "/datawar/",
                "/domain/",
                "/coupon/",
                "/cc/",
                "/bda/",
                "/ai/",
                "/mtop",
            )
        ):
            continue
        found[("unknown", path)] = "path"

    rows = []
    for (host, path), confidence in sorted(found.items()):
        rows.append(
            {
                "host": host,
                "path": path,
                "family": classify_endpoint(host, path, kind),
                "confidence": confidence,
            }
        )
    return tuple(rows)


def classify_endpoint(host: str, path: str, kind: str) -> str:
    haystack = f"{host} {path} {kind}".lower()
    if "websocket" in kind:
        return "websocket"
    if "coupon" in haystack or "benefit" in haystack:
        return "qianniu_coupon"
    if "mtop" in haystack or "h5api.m.taobao" in haystack:
        return "mtop"
    if "sycm" in haystack or any(
        marker in path.lower()
        for marker in ("/portal/", "/oneauth/", "/datawar/", "/domain/")
    ):
        return "sycm_analytics"
    if "qn." in host or "myseller" in host:
        return "qianniu_platform"
    return "platform_api"


def parse_capture_file(path: Path) -> ParsedCapture | None:
    metadata = parse_capture_filename(path)
    if metadata is None:
        return None
    capture_at, session_id, sequence, kind = metadata
    data = path.read_bytes()
    text = _decode_text(data[:MAX_ANALYSIS_BYTES])
    is_binary = text is None
    is_json_like = False
    endpoints: tuple[dict[str, str], ...] = ()
    fields: tuple[dict[str, str], ...] = ()
    shape: tuple[dict[str, str], ...] = ()
    sensitive_field_count = 0

    if text is not None:
        payload, is_json_like = _parse_payload(text)
        if _is_llm_payload(payload, text):
            return ParsedCapture(
                source_name=path.name,
                capture_at=capture_at,
                session_id=session_id,
                sequence=sequence,
                kind=kind,
                size_bytes=path.stat().st_size,
                sha256=_sha256(data),
                is_binary=is_binary,
                is_json_like=is_json_like,
                sensitive_field_count=0,
                endpoints=(),
                fields=(),
                shape=(),
                daily_candidate=None,
            )
        daily_candidate = _daily_candidate(payload, kind)
        if payload is not None:
            shape_rows = _walk_shape(payload)
            shape = tuple(shape_rows[:2000])
            field_rows: dict[tuple[str, str], dict[str, str]] = {}
            for row in shape_rows:
                if row["path"] == "$":
                    continue
                field_rows[(row["path"], row["kind"])] = row
                if "<sensitive>" in row["path"]:
                    sensitive_field_count += 1
            fields = tuple(field_rows.values())
        endpoints = _extract_endpoints(text, kind)

    return ParsedCapture(
        source_name=path.name,
        capture_at=capture_at,
        session_id=session_id,
        sequence=sequence,
        kind=kind,
        size_bytes=path.stat().st_size,
        sha256=_sha256(data),
        is_binary=is_binary,
        is_json_like=is_json_like,
        sensitive_field_count=sensitive_field_count,
        endpoints=endpoints,
        fields=fields,
        shape=shape,
        daily_candidate=daily_candidate if text is not None else None,
    )


def iter_capture_files(
    capture_dir: Path,
    *,
    since: date | None = None,
    until: date | None = None,
) -> Iterable[Path]:
    for path in sorted(capture_dir.glob("*.reqable")):
        metadata = parse_capture_filename(path)
        if metadata is None:
            continue
        capture_date = metadata[0].date()
        if since and capture_date < since:
            continue
        if until and capture_date > until:
            continue
        yield path


def analyze_capture_directory(
    capture_dir: Path,
    database_path: Path,
    *,
    since: date | None = None,
    until: date | None = None,
) -> dict[str, Any]:
    store = CaptureStore(database_path)
    store.initialize()
    started_at = datetime.now().astimezone()
    file_count = 0
    analyzed_count = 0

    with store._connect() as connection:
        for path in iter_capture_files(capture_dir, since=since, until=until):
            file_count += 1
            parsed = parse_capture_file(path)
            if parsed is None:
                continue
            store.upsert_capture(parsed, connection=connection)
            analyzed_count += 1

    finished_at = datetime.now().astimezone()
    run_id = store.record_run(
        capture_dir=str(capture_dir),
        since=since,
        until=until,
        started_at=started_at,
        finished_at=finished_at,
        file_count=file_count,
        analyzed_count=analyzed_count,
    )
    summary = store.summary(since=since, until=until)
    summary.update({"run_id": run_id, "file_count": file_count, "analyzed_count": analyzed_count})
    return summary


def build_markdown_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Reqable Capture Analysis",
        "",
        "> Offline analysis only. This report intentionally excludes raw request bodies, cookies, tokens, signatures, authorization headers, and personal identifiers.",
        "",
        f"- Window: `{summary.get('window_start') or 'all'} .. {summary.get('window_end') or 'all'}`",
        f"- Files selected: `{summary.get('file_count', 0)}`",
        f"- Files analyzed: `{summary.get('analyzed_count', 0)}`",
        f"- Generated at: `{summary.get('generated_at', '')}`",
        "",
        "## Daily Volume",
        "",
        "| Date | Files | Bytes |",
        "| --- | ---: | ---: |",
    ]
    for row in summary.get("daily", []):
        lines.append(f"| {row['capture_date']} | {row['file_count']} | {row['bytes']} |")
    if len(summary.get("daily", [])) < 2:
        lines.extend(
            [
                "",
                "Selected window contains fewer than two capture dates. Current local Reqable samples only validate a single-day import; keep the 2-3 day contract but compare again after more daily captures are available.",
            ]
        )

    lines.extend(
        [
            "",
            "## Daily-Shaped Request Bodies",
            "",
        ]
    )
    if summary.get("daily_requests"):
        lines.extend(
            [
                "| Business date | Date mode | Files |",
                "| --- | --- | ---: |",
            ]
        )
        for row in summary.get("daily_requests", []):
            lines.append(f"| {row.get('business_date') or 'unknown'} | `{row['date_mode']}` | {row['files']} |")
    else:
        lines.append("No request body with clear day-level params was found in this window.")

    lines.extend(
        [
            "",
            "## Families",
            "",
            "| Family | Observations |",
            "| --- | ---: |",
        ]
    )
    for row in summary.get("families", []):
        lines.append(f"| `{row['family']}` | {row['observations']} |")

    lines.extend(
        [
            "",
            "## Endpoint Candidates",
            "",
            "| Family | Host | Path | Files |",
            "| --- | --- | --- | ---: |",
        ]
    )
    for row in summary.get("endpoints", [])[:80]:
        lines.append(
            f"| `{row['family']}` | `{row['host']}` | `{row['path']}` | {row['files']} |"
        )

    lines.extend(
        [
            "",
            "## Field Paths",
            "",
            "Only field names and inferred value kinds are retained. Sensitive segments are replaced with `<sensitive>`.",
            "",
            "| Direction | Field path | Kind | Files |",
            "| --- | --- | --- | ---: |",
        ]
    )
    for row in summary.get("fields", [])[:120]:
        lines.append(
            f"| `{row['direction']}` | `{row['field_path']}` | `{row['value_kind']}` | {row['files']} |"
        )

    lines.extend(
        [
            "",
            "## Initial Adapter Decision",
            "",
            "- `sycm_analytics`: candidate read-only analytics adapter for overview, trend, traffic, product, and promotion reporting.",
            "- `qianniu_coupon`: candidate task adapter, currently discovery-only and disabled for replay or mutation.",
            "- `mtop`: transport-envelope family; requires a separate contract for request signing and expiry, so it is not replayed by this phase.",
            "- `websocket`: retained as a stream candidate; binary messages require a schema contract before decoding.",
            "",
            "The next validation step is to compare two or three capture dates and confirm stable response shapes. Only after that should a daily importer be enabled.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_markdown_report(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_markdown_report(summary), encoding="utf-8")
