from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.modules.captures.analyzer import parse_capture_filename  # noqa: E402

FILE_RE = re.compile(
    r"^(?P<timestamp>\d+)-(?P<session>\d+)-(?P<sequence>\d+)-(?P<kind>.+)\.reqable$",
    re.IGNORECASE,
)
API_FIELD_ORDER = [
    "url",
    "method",
    "success",
    "msg",
    "status",
    "code",
    "duration",
    "trace_id",
    "params",
    "headers",
    "rtype",
    "ts",
    "type",
]
NEXT_FIELD_RE = {
    key: re.compile(
        r"&(" + "|".join(re.escape(item) for item in API_FIELD_ORDER[index + 1 :]) + r")="
    )
    for index, key in enumerate(API_FIELD_ORDER[:-1])
}
SENSITIVE_KEY_RE = re.compile(
    r"(?i)(cookie|authorization|token|sign|csrf|session|password|passwd|secret|"
    r"account|seller.?id|shop.?id|user.?id|uid|buyer.?id|order.?id|"
    r"device.?id|umid|cna|bx-|trace_id|username|nick)"
)
SAFE_HEADER_VALUES = {"bx-v", "sycm-referer", "onetrace-card-id", "sycm-query"}
PLATFORM_HOST_RE = re.compile(r"(?i)(taobao|tmall|alibaba|alimama|alicdn|sycm|qn\.)")


@dataclass(frozen=True)
class ApiRequestObservation:
    source_name: str
    capture_at: str
    host: str
    path: str
    url: str
    method: str
    status: str
    code: str
    success: str
    message: str
    duration_ms: str
    rtype: str
    ts: str
    trace_id_present: bool
    params: dict[str, str]
    headers: dict[str, str]


def _full_unquote(value: str, rounds: int = 8) -> str:
    previous = value if isinstance(value, str) else ""
    for _ in range(rounds):
        current = unquote(previous)
        if current == previous:
            return current
        previous = current
    return previous


def _segment_starts(value: str) -> list[int]:
    starts = []
    for match in re.finditer(r"(?:^|[|&])url=", value):
        starts.append(match.start() + (1 if value[match.start()] in "|&" else 0))
    if value.startswith("msg=url="):
        starts.append(4)
    return sorted(set(starts))


def _split_api_segments(value: str) -> list[str]:
    starts = _segment_starts(value)
    segments = []
    for index, start in enumerate(starts):
        end = len(value)
        for next_start in starts[index + 1 :]:
            if next_start > start:
                end = next_start - 1 if value[next_start - 1] == "|" else next_start
                break
        segment = value[start:end]
        if segment.startswith("url=") and "&method=" in segment:
            segments.append(segment)
    return segments


def _field_value(segment: str, key: str) -> str:
    marker = f"{key}="
    position = segment.find(marker)
    if position < 0:
        return ""
    start = position + len(marker)
    if key == "type":
        return segment[start:]
    match = NEXT_FIELD_RE.get(key).search(segment, start) if key in NEXT_FIELD_RE else None
    end = match.start() if match else len(segment)
    return segment[start:end]


def _safe_value(value: str) -> str:
    if value == "":
        return ""
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"<present len={len(value)} sha10={digest}>"


def _sanitize_mapping(values: dict[str, str], *, headers: bool = False) -> dict[str, str]:
    sanitized = {}
    for key, value in values.items():
        if headers and key.lower() in SAFE_HEADER_VALUES:
            sanitized[key] = value
        elif SENSITIVE_KEY_RE.search(key):
            sanitized[key] = _safe_value(value)
        else:
            sanitized[key] = value
    return sanitized


def _sensitive_count(values: dict[str, str]) -> int:
    return sum(1 for key in values if SENSITIVE_KEY_RE.search(key))


def _parse_api_log_file(path: Path) -> list[ApiRequestObservation]:
    text = path.read_text(encoding="utf-8", errors="replace").replace("\x00", "").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []

    metadata = parse_capture_filename(path)
    capture_at = metadata[0].isoformat() if metadata else ""
    payloads = payload if isinstance(payload, list) else [payload]
    observations = []

    for item in payloads:
        if not isinstance(item, dict):
            continue
        raw = item.get("gokey") or item.get("data") or ""
        decoded = _full_unquote(raw)
        for segment in _split_api_segments(decoded):
            url = _field_value(segment, "url")
            if url.startswith("//"):
                url = "https:" + url
            if not url.startswith(("http://", "https://")):
                continue

            parsed_url = urlsplit(url)
            host = (parsed_url.hostname or "").lower()
            if not host or not PLATFORM_HOST_RE.search(host):
                continue

            params_raw = _field_value(segment, "params")
            params = {
                key: values[-1] if values else ""
                for key, values in parse_qs(params_raw, keep_blank_values=True).items()
            }
            headers_raw = _field_value(segment, "headers")
            try:
                raw_headers = json.loads(headers_raw) if headers_raw else {}
            except json.JSONDecodeError:
                raw_headers = {"<parse_error>": headers_raw[:200]}
            headers = {str(key): str(value) for key, value in raw_headers.items()}

            observations.append(
                ApiRequestObservation(
                    source_name=path.name,
                    capture_at=capture_at,
                    host=host,
                    path=parsed_url.path,
                    url=url,
                    method=_field_value(segment, "method"),
                    status=_field_value(segment, "status"),
                    code=_field_value(segment, "code"),
                    success=_field_value(segment, "success"),
                    message=_field_value(segment, "msg"),
                    duration_ms=_field_value(segment, "duration"),
                    rtype=_field_value(segment, "rtype"),
                    ts=_field_value(segment, "ts"),
                    trace_id_present=bool(_field_value(segment, "trace_id")),
                    params=_sanitize_mapping(params),
                    headers=_sanitize_mapping(headers, headers=True),
                )
            )
    return observations


def _date_evidence(params: dict[str, str]) -> tuple[str, str]:
    date_range = params.get("dateRange", "")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}\|\d{4}-\d{2}-\d{2}", date_range):
        start, end = date_range.split("|", 1)
        if start == end:
            return start, "dateRange_day"
        return f"{start}..{end}", "dateRange_span"
    start_date = params.get("startDate", "")
    end_date = params.get("endDate", "")
    if start_date and start_date == end_date:
        return start_date, "date_pair"
    date_value = params.get("date", "")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
        return date_value, "date"
    start_time = params.get("startTime", "")
    end_time = params.get("endTime", "")
    if start_time and start_time == end_time:
        if re.fullmatch(r"\d{13}", start_time):
            return "", "epoch_ms_range"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_time):
            return start_time, "date_string_range"
    return "", ""


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _connect_output_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS api_request_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_name TEXT NOT NULL,
            capture_at TEXT,
            host TEXT NOT NULL,
            path TEXT NOT NULL,
            url TEXT NOT NULL,
            method TEXT,
            status TEXT,
            code TEXT,
            success TEXT,
            message TEXT,
            duration_ms TEXT,
            rtype TEXT,
            ts TEXT,
            trace_id_present INTEGER NOT NULL,
            date_mode TEXT,
            business_date TEXT,
            params_json TEXT NOT NULL,
            headers_json TEXT NOT NULL,
            sensitive_field_count INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS endpoint_contracts (
            host TEXT NOT NULL,
            path TEXT NOT NULL,
            method TEXT NOT NULL,
            calls INTEGER NOT NULL,
            daily_calls INTEGER NOT NULL,
            success_calls INTEGER NOT NULL,
            statuses_json TEXT NOT NULL,
            business_dates_json TEXT NOT NULL,
            sample_params_json TEXT NOT NULL,
            sample_headers_json TEXT NOT NULL,
            response_files INTEGER NOT NULL,
            response_json_like_files INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (host, path, method)
        );

        DELETE FROM api_request_observations;
        DELETE FROM endpoint_contracts;
        """
    )
    return connection


def _capture_db_connection(path: Path) -> sqlite3.Connection | None:
    if not path.exists():
        return None
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _response_stats(connection: sqlite3.Connection | None, path: str) -> dict[str, Any]:
    if connection is None:
        return {"files": 0, "json_like_files": 0, "samples": [], "shape": []}
    row = connection.execute(
        """
        SELECT COUNT(DISTINCT e.capture_file_id) AS files,
               COUNT(DISTINCT CASE WHEN c.is_json_like = 1 THEN e.capture_file_id END) AS json_like_files
        FROM endpoint_observations e
        JOIN capture_files c ON c.id = e.capture_file_id
        WHERE e.path = ?
        """,
        (path,),
    ).fetchone()
    samples = connection.execute(
        """
        SELECT c.source_name, c.kind, c.is_json_like, c.size_bytes, c.capture_at
        FROM endpoint_observations e
        JOIN capture_files c ON c.id = e.capture_file_id
        WHERE e.path = ?
        ORDER BY c.is_json_like DESC, c.capture_at DESC
        LIMIT 6
        """,
        (path,),
    ).fetchall()
    shape = connection.execute(
        """
        SELECT s.field_path, s.value_kind, COUNT(DISTINCT s.capture_file_id) AS files
        FROM shape_observations s
        WHERE s.capture_file_id IN (
            SELECT e.capture_file_id
            FROM endpoint_observations e
            JOIN capture_files c ON c.id = e.capture_file_id
            WHERE e.path = ? AND c.is_json_like = 1
        )
        GROUP BY s.field_path, s.value_kind
        ORDER BY files DESC, LENGTH(s.field_path), s.field_path
        LIMIT 16
        """,
        (path,),
    ).fetchall()
    return {
        "files": int(row["files"] or 0),
        "json_like_files": int(row["json_like_files"] or 0),
        "samples": [dict(item) for item in samples],
        "shape": [
            {
                "path": item["field_path"],
                "kind": item["value_kind"],
                "files": int(item["files"] or 0),
            }
            for item in shape
        ],
    }


def _iter_api_observations(capture_dir: Path) -> list[ApiRequestObservation]:
    observations = []
    for path in sorted(capture_dir.glob("*req_raw-body.reqable")):
        observations.extend(_parse_api_log_file(path))
    return observations


def _store_observations(
    output_db: Path,
    observations: list[ApiRequestObservation],
    response_by_path: dict[str, dict[str, Any]],
) -> None:
    with _connect_output_db(output_db) as connection:
        connection.executemany(
            """
            INSERT INTO api_request_observations (
                source_name, capture_at, host, path, url, method, status, code,
                success, message, duration_ms, rtype, ts, trace_id_present,
                date_mode, business_date, params_json, headers_json,
                sensitive_field_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    item.source_name,
                    item.capture_at,
                    item.host,
                    item.path,
                    item.url,
                    item.method,
                    item.status,
                    item.code,
                    item.success,
                    item.message,
                    item.duration_ms,
                    item.rtype,
                    item.ts,
                    int(item.trace_id_present),
                    _date_evidence(item.params)[1],
                    _date_evidence(item.params)[0],
                    _json_dumps(item.params),
                    _json_dumps(item.headers),
                    _sensitive_count(item.params) + _sensitive_count(item.headers),
                )
                for item in observations
            ],
        )

        for contract in _build_contracts(observations, response_by_path):
            connection.execute(
                """
                INSERT INTO endpoint_contracts (
                    host, path, method, calls, daily_calls, success_calls,
                    statuses_json, business_dates_json, sample_params_json,
                    sample_headers_json, response_files, response_json_like_files,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contract["host"],
                    contract["path"],
                    contract["method"],
                    contract["calls"],
                    contract["daily_calls"],
                    contract["success_calls"],
                    _json_dumps(contract["statuses"]),
                    _json_dumps(contract["business_dates"]),
                    _json_dumps(contract["sample_params"]),
                    _json_dumps(contract["sample_headers"]),
                    contract["response"]["files"],
                    contract["response"]["json_like_files"],
                    datetime.now(tz=timezone.utc).astimezone().isoformat(),
                ),
            )


def _build_contracts(
    observations: list[ApiRequestObservation],
    response_by_path: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[ApiRequestObservation]] = defaultdict(list)
    for item in observations:
        grouped[(item.host, item.path, item.method or "GET")].append(item)

    contracts = []
    for (host, path, method), rows in grouped.items():
        business_dates = Counter()
        date_modes = Counter()
        daily_calls = 0
        for row in rows:
            business_date, date_mode = _date_evidence(row.params)
            if business_date:
                business_dates[business_date] += 1
            if date_mode:
                date_modes[date_mode] += 1
                if date_mode in {"dateRange_day", "date_pair", "date", "date_string_range"}:
                    daily_calls += 1

        sample = max(rows, key=lambda row: len(_json_dumps(row.params)))
        contracts.append(
            {
                "host": host,
                "path": path,
                "method": method,
                "calls": len(rows),
                "daily_calls": daily_calls,
                "success_calls": sum(1 for row in rows if row.success == "true" or row.status == "200"),
                "statuses": dict(Counter(row.status or "unknown" for row in rows)),
                "date_modes": dict(date_modes),
                "business_dates": dict(business_dates),
                "sample_params": sample.params,
                "sample_headers": sample.headers,
                "response": response_by_path.get(path, {"files": 0, "json_like_files": 0, "samples": [], "shape": []}),
            }
        )
    return sorted(
        contracts,
        key=lambda item: (item["daily_calls"], item["calls"], item["path"]),
        reverse=True,
    )


def _target_paths() -> list[str]:
    return [
        "/portal/coreIndex/new/overview/v3.json",
        "/portal/coreIndex/new/trend/v3.json",
        "/portal/coreIndex/new/getTableData/v3.json",
        "/portal/coreIndex/getShopMainIndexes.json",
        "/cc/item/view/top.json",
        "/flow/v5/shop/source/tree/v4.json",
        "/domain/oneQuery.json",
        "/extend/api/tbhjActivityDataQuery.json",
        "/report/query.json",
        "/portal/month/overview.json",
        "/portal/month/trend.json",
        "/portal/level/info/v3.json",
        "/portal/board/grow/factor/overview.json",
        "/portal/board/grow/factor/trend.json",
        "/portal/board/grow/factor/promo/top.json",
    ]


def _build_result(
    observations: list[ApiRequestObservation],
    response_by_path: dict[str, dict[str, Any]],
    *,
    capture_dir: Path,
    capture_db: Path,
    output_db: Path,
) -> dict[str, Any]:
    contracts = _build_contracts(observations, response_by_path)
    daily_counter = Counter()
    mode_counter = Counter()
    for item in observations:
        business_date, date_mode = _date_evidence(item.params)
        if business_date:
            daily_counter[business_date] += 1
        if date_mode:
            mode_counter[date_mode] += 1

    by_path = {contract["path"]: contract for contract in contracts}
    target_contracts = []
    for path in _target_paths():
        if path in by_path:
            target_contracts.append(by_path[path])
        else:
            target_contracts.append(
                {
                    "host": "",
                    "path": path,
                    "method": "",
                    "calls": 0,
                    "daily_calls": 0,
                    "success_calls": 0,
                    "statuses": {},
                    "date_modes": {},
                    "business_dates": {},
                    "sample_params": {},
                    "sample_headers": {},
                    "response": response_by_path.get(path, {"files": 0, "json_like_files": 0, "samples": [], "shape": []}),
                }
            )

    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "source": "reqable_mcp_live_empty_plus_local_capture_logs",
        "capture_dir": str(capture_dir),
        "capture_db": str(capture_db),
        "output_db": str(output_db),
        "mcp": {
            "server": "reqable-mcp 1.0.1",
            "live_records": 0,
            "note": "MCP was reachable, but Reqable live capture retained no records at query time.",
        },
        "summary": {
            "api_observations": len(observations),
            "endpoint_contracts": len(contracts),
            "daily_observations": sum(daily_counter.values()),
            "business_dates": dict(daily_counter),
            "date_modes": dict(mode_counter),
        },
        "target_contracts": target_contracts,
        "top_daily_contracts": [
            contract
            for contract in contracts
            if contract["daily_calls"] > 0 and "punish:" not in contract["path"]
        ][:40],
        "top_contracts": contracts[:60],
    }


def build_markdown_report(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        "# Reqable Request/Response Pair Analysis",
        "",
        "> Reqable MCP was probed first. It is reachable, but live capture returned zero retained records, so this report derives request contracts from local Reqable raw-body logs and response candidates from the local capture analysis DB.",
        "",
        f"- Generated at: `{result['generated_at']}`",
        f"- Capture dir: `{result['capture_dir']}`",
        f"- Capture DB: `{result['capture_db']}`",
        f"- Local request DB: `{result['output_db']}`",
        f"- API observations extracted from request logs: `{summary['api_observations']}`",
        f"- Endpoint contracts: `{summary['endpoint_contracts']}`",
        f"- Daily observations: `{summary['daily_observations']}`",
        "",
        "## Important Boundary",
        "",
        "- The same Reqable record for these request logs usually responds with a 1x1 GIF, because it is the frontend telemetry request that reports API calls.",
        "- The real API request details are inside that telemetry payload: URL, method, status, params, selected headers, duration, and trace presence.",
        "- Response candidates below are matched by endpoint path from local response bodies. They are useful schema evidence, but not guaranteed to be the exact response pair unless marked by future live MCP records.",
        "- Credential values are not written to project artifacts. Sensitive fields are retained as presence markers with length/hash metadata.",
        "",
        "## Business Dates",
        "",
    ]
    if summary["business_dates"]:
        lines.extend(["| Business date | Observations |", "| --- | ---: |"])
        for day, count in sorted(summary["business_dates"].items()):
            lines.append(f"| `{day}` | {count} |")
    else:
        lines.append("No date-like request params were found.")

    lines.extend(
        [
            "",
            "## Priority Paths",
            "",
            "| Path | Method | Calls | Daily | Dates | Response files | JSON-like | Sample params |",
            "| --- | --- | ---: | ---: | --- | ---: | ---: | --- |",
        ]
    )
    for contract in result["target_contracts"]:
        sample_params = _compact_params(contract.get("sample_params", {}))
        dates = ", ".join(f"`{key}`:{value}" for key, value in contract["business_dates"].items()) or "-"
        lines.append(
            f"| `{contract['path']}` | `{contract['method'] or '-'}` | {contract['calls']} | "
            f"{contract['daily_calls']} | {dates} | {contract['response']['files']} | "
            f"{contract['response']['json_like_files']} | {sample_params} |"
        )

    lines.extend(
        [
            "",
            "## Top Daily Contracts",
            "",
            "| Host | Path | Method | Calls | Dates | Status |",
            "| --- | --- | --- | ---: | --- | --- |",
        ]
    )
    for contract in result["top_daily_contracts"]:
        dates = ", ".join(f"`{key}`:{value}" for key, value in contract["business_dates"].items()) or "-"
        statuses = ", ".join(f"`{key}`:{value}" for key, value in contract["statuses"].items()) or "-"
        lines.append(
            f"| `{contract['host']}` | `{contract['path']}` | `{contract['method']}` | "
            f"{contract['calls']} | {dates} | {statuses} |"
        )

    lines.extend(["", "## Contract Details", ""])
    for contract in result["target_contracts"]:
        if not contract["calls"] and not contract["response"]["files"]:
            continue
        lines.extend(_contract_section(contract))

    lines.extend(
        [
            "",
            "## Worker Implications",
            "",
            "- Good first live-contract candidates now include `/portal/coreIndex/new/overview/v3.json`, `/portal/coreIndex/new/trend/v3.json`, `/cc/item/view/top.json`, and member `/domain/oneQuery.json` variants for `2026-07-29`.",
            "- `/report/query.json`, `/extend/api/tbhjActivityDataQuery.json`, and `/flow/v5/shop/source/tree/v4.json` still need live MCP records or explicit exported API pairs; the current local files only show path/body evidence.",
            "- The importer should treat telemetry-derived params as request contracts, then require one exact live response sample before enabling writes.",
        ]
    )
    return "\n".join(lines) + "\n"


def _compact_params(params: dict[str, str], *, max_items: int = 8) -> str:
    if not params:
        return "-"
    keys = ["dateType", "dateRange", "date", "domainCode", "showType", "indexCode", "indexCodes", "page", "pageSize"]
    selected = [(key, params[key]) for key in keys if key in params]
    for key, value in params.items():
        if len(selected) >= max_items:
            break
        if key not in {item[0] for item in selected} and not SENSITIVE_KEY_RE.search(key):
            selected.append((key, value))
    text = ", ".join(f"`{key}={value}`" for key, value in selected[:max_items])
    return text or "-"


def _contract_section(contract: dict[str, Any]) -> list[str]:
    lines = [
        f"### `{contract['path']}`",
        "",
        f"- Host: `{contract['host'] or 'unknown'}`",
        f"- Method: `{contract['method'] or 'unknown'}`",
        f"- Observed calls: `{contract['calls']}`",
        f"- Daily calls: `{contract['daily_calls']}`",
        f"- Statuses: `{_json_dumps(contract['statuses'])}`",
        f"- Business dates: `{_json_dumps(contract['business_dates'])}`",
        f"- Sample params: `{_json_dumps(contract['sample_params'])}`",
        f"- Sample headers: `{_json_dumps(contract['sample_headers'])}`",
        f"- Response candidate files: `{contract['response']['files']}`",
        f"- JSON-like response candidate files: `{contract['response']['json_like_files']}`",
    ]
    if contract["response"].get("shape"):
        shape = ", ".join(
            f"`{item['path']}:{item['kind']}`" for item in contract["response"]["shape"][:10]
        )
        lines.append(f"- Response shape preview: {shape}")
    if contract["response"].get("samples"):
        sample_names = ", ".join(f"`{item['source_name']}`" for item in contract["response"]["samples"][:4])
        lines.append(f"- Response candidate samples: {sample_names}")
    lines.append("")
    return lines


def write_outputs(result: dict[str, Any], report: Path, json_output: Path) -> None:
    report.parent.mkdir(parents=True, exist_ok=True)
    json_output.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(build_markdown_report(result), encoding="utf-8")
    json_output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Reqable request/response pairing evidence.")
    parser.add_argument(
        "--capture-dir",
        type=Path,
        default=Path(r"C:\Users\Moli\AppData\Roaming\Reqable\capture"),
    )
    parser.add_argument(
        "--capture-db",
        type=Path,
        default=Path("artifacts/local/reqable_capture.sqlite3"),
    )
    parser.add_argument(
        "--output-db",
        type=Path,
        default=Path("artifacts/local/reqable_api_requests.sqlite3"),
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=Path("artifacts/local/reqable_api_request_pairs.json"),
    )
    parser.add_argument("--report", type=Path, default=Path("docs/REQABLE_REQUEST_RESPONSE_PAIRS.md"))
    args = parser.parse_args()

    observations = _iter_api_observations(args.capture_dir)
    capture_connection = _capture_db_connection(args.capture_db)
    try:
        observed_paths = {item.path for item in observations} | set(_target_paths())
        response_by_path = {
            path: _response_stats(capture_connection, path)
            for path in sorted(observed_paths)
        }
    finally:
        if capture_connection is not None:
            capture_connection.close()

    _store_observations(args.output_db, observations, response_by_path)
    result = _build_result(
        observations,
        response_by_path,
        capture_dir=args.capture_dir,
        capture_db=args.capture_db,
        output_db=args.output_db,
    )
    write_outputs(result, args.report, args.json_output)

    print(
        json.dumps(
            {
                "api_observations": result["summary"]["api_observations"],
                "endpoint_contracts": result["summary"]["endpoint_contracts"],
                "daily_observations": result["summary"]["daily_observations"],
                "business_dates": result["summary"]["business_dates"],
                "report": str(args.report),
                "json_output": str(args.json_output),
                "output_db": str(args.output_db),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
