from __future__ import annotations

import argparse
import ast
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from analyze_daily_endpoints import (  # noqa: E402
    SECRET_PARAM_KEYS,
    LegacyDailyEndpoint,
    _daily_params_for,
    _priority,
    _query_capture_matches,
    extract_legacy_endpoints,
)

RUNTIME_ONLY_KEYS = SECRET_PARAM_KEYS | {"csrfId", "csrfID"}
DEFAULT_PRIORITIES = ("A", "A-")


@dataclass(frozen=True)
class HttpContract:
    method: str
    line: int


def _sqlite_readonly_connection(database_path: Path) -> sqlite3.Connection | None:
    if not database_path.exists():
        return None
    connection = sqlite3.connect(database_path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _infer_http_contracts(source_path: Path) -> dict[str, HttpContract]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    contracts: dict[str, HttpContract] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue

        methods: list[HttpContract] = []
        for child in ast.walk(node):
            if not isinstance(child, ast.Call) or not isinstance(child.func, ast.Attribute):
                continue
            attr = child.func.attr.lower()
            if attr in {"get", "post", "put", "delete", "patch"}:
                methods.append(HttpContract(method=attr.upper(), line=child.lineno))
            elif attr == "request":
                method = _request_method_from_call(child)
                if method:
                    methods.append(HttpContract(method=method, line=child.lineno))

        if methods:
            contracts[node.name] = sorted(methods, key=lambda item: (item.method != "POST", item.line))[0]
    return contracts


def _request_method_from_call(node: ast.Call) -> str | None:
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return node.args[0].value.upper()
    for keyword in node.keywords:
        if (
            keyword.arg == "method"
            and isinstance(keyword.value, ast.Constant)
            and isinstance(keyword.value.value, str)
        ):
            return keyword.value.value.upper()
    return None


def _day_start_ms(day: str, timezone: str) -> str:
    day_value = date.fromisoformat(day)
    tzinfo = ZoneInfo(timezone)
    start = datetime.combine(day_value, time.min, tzinfo=tzinfo)
    return str(int(start.timestamp() * 1000))


def _normalized_date_params(endpoint: LegacyDailyEndpoint, day: str, timezone: str) -> dict[str, str]:
    params = dict(_daily_params_for(endpoint, day))
    if endpoint.date_mode == "epoch_ms_range":
        start_ms = _day_start_ms(day, timezone)
        params["startTime"] = start_ms
        params["endTime"] = start_ms
    return params


def _runtime_keys_for(endpoint: LegacyDailyEndpoint) -> list[str]:
    keys = {key for key in endpoint.params if key in RUNTIME_ONLY_KEYS}
    if endpoint.function == "get_rtb_plan_data":
        keys.add("csrfId")
    return sorted(keys)


def _request_contract(
    endpoint: LegacyDailyEndpoint,
    *,
    method: str,
    day: str,
    timezone: str,
) -> dict[str, Any]:
    date_params = _normalized_date_params(endpoint, day, timezone)
    runtime_keys = _runtime_keys_for(endpoint)

    if endpoint.function == "get_rtb_plan_data":
        return {
            "method": "POST",
            "url": endpoint.url,
            "query_params": {"bizCode": "universalBP"},
            "body_template": {
                "bizCode": "universalBP",
                "source": "baseReport",
                "rptType": "campaign",
                "splitType": "day",
                "startTime": day,
                "endTime": day,
                "pageSize": 100,
                "page": 1,
                "queryFieldIn": _metric_terms(endpoint.metric_keys)[:40],
            },
            "runtime_credentials": runtime_keys,
            "target_table": endpoint.table,
            "execute": False,
            "write_database": False,
        }

    if method == "POST":
        query_params: dict[str, str] = {}
        body_template: dict[str, Any] | None = date_params
    else:
        query_params = date_params
        body_template = None

    return {
        "method": method,
        "url": endpoint.url,
        "query_params": query_params,
        "body_template": body_template,
        "runtime_credentials": runtime_keys,
        "target_table": endpoint.table,
        "execute": False,
        "write_database": False,
    }


def _capture_samples(connection: sqlite3.Connection | None, path: str, limit: int = 8) -> list[dict[str, Any]]:
    if connection is None:
        return []
    rows = connection.execute(
        """
        SELECT c.source_name, c.kind, c.is_json_like, c.size_bytes, c.capture_at,
               e.host, e.confidence
        FROM endpoint_observations e
        JOIN capture_files c ON c.id = e.capture_file_id
        WHERE e.path = ?
        ORDER BY c.is_json_like DESC, c.capture_at, c.source_name
        LIMIT ?
        """,
        (path, limit),
    ).fetchall()
    return [
        {
            "source_name": row["source_name"],
            "kind": row["kind"],
            "is_json_like": bool(row["is_json_like"]),
            "size_bytes": int(row["size_bytes"]),
            "capture_at": row["capture_at"],
            "host": row["host"],
            "confidence": row["confidence"],
        }
        for row in rows
    ]


def _json_like_count(connection: sqlite3.Connection | None, path: str) -> int:
    if connection is None:
        return 0
    row = connection.execute(
        """
        SELECT COUNT(DISTINCT e.capture_file_id) AS files
        FROM endpoint_observations e
        JOIN capture_files c ON c.id = e.capture_file_id
        WHERE e.path = ? AND c.is_json_like = 1
        """,
        (path,),
    ).fetchone()
    return int(row["files"] or 0)


def _shape_preview(
    connection: sqlite3.Connection | None,
    path: str,
    *,
    limit: int = 24,
) -> list[dict[str, Any]]:
    if connection is None:
        return []
    rows = connection.execute(
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
        LIMIT ?
        """,
        (path, limit),
    ).fetchall()
    return [
        {
            "path": row["field_path"],
            "kind": row["value_kind"],
            "files": int(row["files"] or 0),
        }
        for row in rows
    ]


def _metric_terms(metric_keys: tuple[str, ...]) -> list[str]:
    terms: list[str] = []
    for key in metric_keys:
        for part in key.split(","):
            normalized = part.strip().replace(".value", "")
            if not normalized or normalized.startswith(("/", "{")):
                continue
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{1,80}", normalized):
                terms.append(normalized)
    return list(dict.fromkeys(terms))


def _metric_shape_hits(
    connection: sqlite3.Connection | None,
    endpoint: LegacyDailyEndpoint,
    path: str,
    *,
    limit: int = 16,
) -> list[dict[str, Any]]:
    if connection is None:
        return []
    hits: list[dict[str, Any]] = []
    for term in _metric_terms(endpoint.metric_keys)[:60]:
        rows = connection.execute(
            """
            SELECT s.field_path, s.value_kind, COUNT(DISTINCT s.capture_file_id) AS files
            FROM shape_observations s
            WHERE s.capture_file_id IN (
                SELECT e.capture_file_id
                FROM endpoint_observations e
                JOIN capture_files c ON c.id = e.capture_file_id
                WHERE e.path = ? AND c.is_json_like = 1
            )
            AND s.field_path LIKE ?
            GROUP BY s.field_path, s.value_kind
            ORDER BY files DESC, LENGTH(s.field_path), s.field_path
            LIMIT 3
            """,
            (path, f"%{term}%"),
        ).fetchall()
        if rows:
            hits.append(
                {
                    "metric": term,
                    "fields": [
                        {
                            "path": row["field_path"],
                            "kind": row["value_kind"],
                            "files": int(row["files"] or 0),
                        }
                        for row in rows
                    ],
                }
            )
        if len(hits) >= limit:
            break
    return hits


def _selected_observed_paths(matches: dict[str, Any]) -> list[dict[str, Any]]:
    exact = list(matches.get("exact", []))
    if exact:
        return [{"evidence": "exact", **row} for row in exact[:3]]
    return [{"evidence": "related", **row} for row in list(matches.get("same_area", []))[:3]]


def _shape_status(paths: list[dict[str, Any]]) -> str:
    if not paths:
        return "no_capture_evidence"
    if not any(path.get("json_like_files", 0) for path in paths):
        return "path_seen_without_json_metric_body"
    if not any(path.get("metric_shape_hits") for path in paths):
        return "json_shape_seen_but_metric_mapping_unconfirmed"
    if not any(path.get("evidence") == "exact" and path.get("metric_shape_hits") for path in paths):
        return "related_json_metric_candidate"
    return "metric_shape_candidate"


def _daily_request_rows(connection: sqlite3.Connection | None) -> list[dict[str, Any]]:
    if connection is None:
        return []
    rows = connection.execute(
        """
        SELECT business_date, date_mode, COUNT(*) AS files
        FROM daily_request_candidates
        GROUP BY business_date, date_mode
        ORDER BY files DESC, business_date
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _build_result(args: argparse.Namespace) -> dict[str, Any]:
    endpoints = extract_legacy_endpoints(args.source)
    http_contracts = _infer_http_contracts(args.source)
    selected_priorities = set(args.priorities)

    connection = _sqlite_readonly_connection(args.capture_db)
    try:
        matches = {
            endpoint.function: _query_capture_matches(args.capture_db, endpoint)
            for endpoint in endpoints
        }
        daily_requests = _daily_request_rows(connection)

        selected: list[dict[str, Any]] = []
        deferred: list[dict[str, Any]] = []
        for endpoint in endpoints:
            priority = _priority(endpoint, matches[endpoint.function])
            http = http_contracts.get(endpoint.function, HttpContract(method="GET", line=endpoint.line))
            contract = _request_contract(
                endpoint,
                method=http.method,
                day=args.day,
                timezone=args.timezone,
            )

            observed_paths = _selected_observed_paths(matches[endpoint.function])
            enriched_paths = []
            for observed in observed_paths:
                path = observed["path"]
                enriched_paths.append(
                    {
                        **observed,
                        "json_like_files": _json_like_count(connection, path),
                        "samples": _capture_samples(connection, path),
                        "shape_preview": _shape_preview(connection, path),
                        "metric_shape_hits": _metric_shape_hits(connection, endpoint, path),
                    }
                )
            item = {
                "function": endpoint.function,
                "line": endpoint.line,
                "priority": priority,
                "legacy_path": endpoint.path,
                "date_mode": endpoint.date_mode,
                "metric_keys": list(endpoint.metric_keys[:40]),
                "capture": {
                    "field_hits": matches[endpoint.function].get("field_hits", 0),
                    "observed_paths": enriched_paths,
                },
                "shape_status": _shape_status(enriched_paths),
                "request_contract": contract,
            }
            if priority in selected_priorities:
                selected.append(item)
            else:
                deferred.append(
                    {
                        "function": endpoint.function,
                        "priority": priority,
                        "legacy_path": endpoint.path,
                        "reason": "not in dry-run priority set",
                    }
                )

        return {
            "generated_at": datetime.now().astimezone().isoformat(),
            "mode": "offline_readonly_dry_run",
            "day": args.day,
            "timezone": args.timezone,
            "source": str(args.source),
            "capture_db": str(args.capture_db),
            "guardrails": {
                "platform_requests_executed": 0,
                "mysql_writes": 0,
                "sqlite_connection": "read_only_uri",
                "raw_cookies_or_tokens_persisted": False,
            },
            "daily_request_evidence": daily_requests,
            "selected_priorities": list(args.priorities),
            "selected": selected,
            "deferred": deferred,
        }
    finally:
        if connection is not None:
            connection.close()


def build_markdown_report(result: dict[str, Any]) -> str:
    selected = result["selected"]
    deferred = result["deferred"]
    lines = [
        "# Daily Import Dry Run",
        "",
        "> Offline dry run only. No Tmall/Qianniu request was replayed, no MySQL table was changed, and no raw Cookie/Token/signature value is written here.",
        "",
        f"- Business day: `{result['day']}`",
        f"- Timezone: `{result['timezone']}`",
        f"- Source script: `{result['source']}`",
        f"- Capture DB: `{result['capture_db']}`",
        f"- Generated at: `{result['generated_at']}`",
        "",
        "## Guardrails",
        "",
        "| Check | Value |",
        "| --- | ---: |",
        f"| Platform requests executed | `{result['guardrails']['platform_requests_executed']}` |",
        f"| MySQL writes | `{result['guardrails']['mysql_writes']}` |",
        f"| SQLite access mode | `{result['guardrails']['sqlite_connection']}` |",
        f"| Raw cookie/token persisted | `{result['guardrails']['raw_cookies_or_tokens_persisted']}` |",
        "",
        "## Captured Day Params",
        "",
    ]
    daily_requests = result.get("daily_request_evidence", [])
    if daily_requests:
        lines.extend(["| Business date | Date mode | Files |", "| --- | --- | ---: |"])
        for row in daily_requests:
            lines.append(
                f"| `{row.get('business_date') or 'unknown'}` | `{row.get('date_mode')}` | {row.get('files', 0)} |"
            )
    else:
        lines.append("No day-level request-body evidence was found in the local capture DB.")

    lines.extend(
        [
            "",
            "## Dry-Run Batch",
            "",
            f"Selected priorities: `{', '.join(result['selected_priorities'])}`",
            "",
            "| Priority | Function | Method | Table | Date mode | Capture fit | Shape status |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in selected:
        capture_fit = _capture_fit_label(item)
        lines.append(
            f"| `{item['priority']}` | `{item['function']}` | `{item['request_contract']['method']}` | "
            f"`{item['request_contract']['target_table']}` | `{item['date_mode']}` | {capture_fit} | `{item['shape_status']}` |"
        )

    lines.extend(["", "## Request Contracts", ""])
    for item in selected:
        lines.extend(_contract_section(item, result["day"]))

    lines.extend(
        [
            "",
            "## Deferred",
            "",
            "| Priority | Function | Legacy path | Reason |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in deferred:
        lines.append(
            f"| `{item['priority']}` | `{item['function']}` | `{item['legacy_path']}` | {item['reason']} |"
        )

    lines.extend(
        [
            "",
            "## Next Adapter Step",
            "",
            "- First live-capable worker should keep the same contract shape: build request -> parse response -> validate row count -> preview rows -> write only after explicit enablement.",
            "- `path_seen_without_json_metric_body` means the endpoint path was observed in local response text, but the current body sample is not a metric JSON response.",
            "- `json_shape_seen_but_metric_mapping_unconfirmed` means JSON exists, but legacy metric keys were not found in the captured shape; it needs a closer paired request/response sample from Reqable.",
            "- `related_json_metric_candidate` means a newer or neighboring endpoint has JSON plus metric-like fields, so it is useful for adapter design but still needs exact request/response pairing.",
            "- Runtime credential keys are listed only as names. Values must come from a local secret provider at execution time.",
        ]
    )
    return "\n".join(lines) + "\n"


def _capture_fit_label(item: dict[str, Any]) -> str:
    paths = item["capture"]["observed_paths"]
    if not paths:
        return "none"
    first = paths[0]
    files = first.get("files", 0)
    if "files" not in first:
        files = len(first.get("samples", []))
    return f"`{first['evidence']}` `{first['path']}` ({files} files)"


def _contract_section(item: dict[str, Any], day: str) -> list[str]:
    contract = item["request_contract"]
    lines = [
        f"### `{item['function']}`",
        "",
        f"- Priority: `{item['priority']}`",
        f"- Legacy path: `{item['legacy_path']}`",
        f"- Method: `{contract['method']}`",
        f"- URL: `{contract['url']}`",
        f"- Target table: `{contract['target_table']}`",
        f"- Query params for `{day}`: `{json.dumps(contract['query_params'], ensure_ascii=False)}`",
        f"- Runtime-only keys: `{', '.join(contract['runtime_credentials']) or 'none'}`",
        f"- Execute request: `{contract['execute']}`",
        f"- Write database: `{contract['write_database']}`",
    ]
    if contract.get("body_template") is not None:
        lines.append(f"- Body template: `{json.dumps(contract['body_template'], ensure_ascii=False)}`")

    paths = item["capture"]["observed_paths"]
    if paths:
        lines.append("- Capture evidence:")
        for observed in paths[:3]:
            lines.append(
                f"  - `{observed['evidence']}` `{observed['path']}`: json-like `{observed['json_like_files']}` files"
            )
            if observed.get("metric_shape_hits"):
                hit_preview = ", ".join(
                    f"`{hit['metric']}`" for hit in observed["metric_shape_hits"][:8]
                )
                lines.append(f"    Metric-like fields: {hit_preview}")
            elif observed.get("shape_preview"):
                shape_preview = ", ".join(
                    f"`{row['path']}:{row['kind']}`" for row in observed["shape_preview"][:8]
                )
                lines.append(f"    Shape preview: {shape_preview}")
    else:
        lines.append("- Capture evidence: no path candidate found in the current local body analysis")

    if item.get("metric_keys"):
        metric_preview = ", ".join(f"`{key}`" for key in item["metric_keys"][:14])
        lines.append(f"- Legacy metric mapping preview: {metric_preview}")
    lines.append("")
    return lines


def _write_outputs(result: dict[str, Any], report_path: Path, json_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(build_markdown_report(result), encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an offline daily-import dry run.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(r"D:\PyPrograms\Ador_tmall\_core\Tmall_Data.py"),
    )
    parser.add_argument(
        "--capture-db",
        type=Path,
        default=Path("artifacts/local/reqable_capture.sqlite3"),
    )
    parser.add_argument("--day", default="2026-07-29")
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument(
        "--priorities",
        nargs="+",
        default=list(DEFAULT_PRIORITIES),
        choices=["A", "A-", "B", "C"],
    )
    parser.add_argument("--report", type=Path, default=Path("docs/DAILY_DRY_RUN.md"))
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()

    if args.json_output is None:
        safe_day = args.day.replace("-", "")
        args.json_output = Path(f"artifacts/local/daily_dry_run_{safe_day}.json")

    result = _build_result(args)
    _write_outputs(result, args.report, args.json_output)
    print(
        json.dumps(
            {
                "mode": result["mode"],
                "day": result["day"],
                "selected": len(result["selected"]),
                "deferred": len(result["deferred"]),
                "platform_requests_executed": result["guardrails"]["platform_requests_executed"],
                "mysql_writes": result["guardrails"]["mysql_writes"],
                "report": str(args.report),
                "json_output": str(args.json_output),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
