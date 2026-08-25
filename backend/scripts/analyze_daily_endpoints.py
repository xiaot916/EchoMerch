from __future__ import annotations

import argparse
import ast
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


DATE_PARAM_KEYS = {
    "dateRange",
    "dateType",
    "startDate",
    "endDate",
    "startTime",
    "endTime",
    "page",
    "pageSize",
    "_",
    "t",
}
SECRET_PARAM_KEYS = {"token", "_tb_token_", "csrfID"}
GENERIC_ENDPOINT_TERMS = {
    "overview",
    "statistics",
    "list",
    "query",
    "transform",
    "data",
    "index",
    "detail",
    "home",
}


@dataclass(frozen=True)
class LegacyDailyEndpoint:
    function: str
    line: int
    url: str
    table: str
    host: str
    path: str
    date_mode: str
    params: tuple[str, ...]
    metric_keys: tuple[str, ...]


def _constant_strings(node: ast.AST) -> list[str]:
    return [
        str(child.value)
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]


def _infer_date_mode(params: set[str], strings: list[str]) -> str:
    if {"startTime", "endTime"}.issubset(params):
        if any(re.fullmatch(r"\d{13}", value) for value in strings):
            return "epoch_ms_range"
        if any(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) for value in strings):
            return "date_string_range"
        return "epoch_ms_range"
    if {"startDate", "endDate"}.issubset(params):
        return "date_pair"
    if "dateRange" in params:
        return "dateRange_day"
    return "unknown"


def _extract_metric_keys(strings: list[str]) -> tuple[str, ...]:
    markers = (
        ".value",
        "pay",
        "Pay",
        "Amt",
        "Cnt",
        "Rate",
        "statDate",
        "uv",
        "Uv",
        "Pv",
        "item",
        "source",
        "flow",
        "live",
        "rc",
        "bybt",
        "click",
        "impression",
    )
    values = {
        value
        for value in strings
        if any(marker in value for marker in markers)
        and not value.startswith(("http://", "https://"))
        and len(value) <= 180
    }
    return tuple(sorted(values)[:60])


def extract_legacy_endpoints(source_path: Path) -> list[LegacyDailyEndpoint]:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    endpoints: list[LegacyDailyEndpoint] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.startswith("get_") or node.name in {
            "get_tmall_session",
            "get_yesterday_str",
            "get_dbmaxdaynext_str",
        }:
            continue

        url = ""
        table = ""
        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if (
                        isinstance(target, ast.Name)
                        and target.id == "url"
                        and isinstance(child.value, ast.Constant)
                    ):
                        url = str(child.value.value)
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "to_sql"
                and child.args
                and isinstance(child.args[0], ast.Constant)
            ):
                table = str(child.args[0].value)

        if not url:
            continue

        strings = _constant_strings(node)
        params = {value for value in strings if value in DATE_PARAM_KEYS | SECRET_PARAM_KEYS}
        parsed = urlsplit(url)
        endpoints.append(
            LegacyDailyEndpoint(
                function=node.name,
                line=node.lineno,
                url=url,
                table=table,
                host=parsed.hostname or "",
                path=parsed.path,
                date_mode=_infer_date_mode(params, strings),
                params=tuple(sorted(params)),
                metric_keys=_extract_metric_keys(strings),
            )
        )
    return endpoints


def _query_capture_matches(database_path: Path, endpoint: LegacyDailyEndpoint) -> dict[str, object]:
    if not database_path.exists():
        return {"exact": [], "same_area": [], "field_hits": 0}

    with sqlite3.connect(database_path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        exact_rows = connection.execute(
            """
            SELECT family, host, path, COUNT(DISTINCT capture_file_id) AS files
            FROM endpoint_observations
            WHERE path = ? OR (host = ? AND path = ?)
            GROUP BY family, host, path
            ORDER BY files DESC
            """,
            (endpoint.path, endpoint.host, endpoint.path),
        ).fetchall()

        segments = [segment for segment in endpoint.path.split("/") if segment]
        fuzzy_terms = []
        if len(segments) >= 2:
            fuzzy_terms.append("/" + "/".join(segments[:2]) + "/")
        if segments:
            final_term = segments[-1].replace(".json", "")
            if final_term not in GENERIC_ENDPOINT_TERMS:
                fuzzy_terms.append(final_term)
        if endpoint.function == "get_tmall_dailyshopdata":
            fuzzy_terms.extend(
                [
                    "/portal/coreIndex/new/overview/",
                    "/portal/coreIndex/new/trend/",
                    "/portal/coreIndex/new/getTableData/",
                ]
            )

        same_area: dict[tuple[str, str, str], dict[str, object]] = {}
        for term in fuzzy_terms:
            if not term:
                continue
            rows = connection.execute(
                """
                SELECT family, host, path, COUNT(DISTINCT capture_file_id) AS files
                FROM endpoint_observations
                WHERE path LIKE ?
                GROUP BY family, host, path
                ORDER BY files DESC
                LIMIT 12
                """,
                (f"%{term}%",),
            ).fetchall()
            for row in rows:
                key = (row["family"], row["host"], row["path"])
                same_area[key] = dict(row)

        field_hits = 0
        for key in endpoint.metric_keys[:20]:
            row = connection.execute(
                """
                SELECT COUNT(DISTINCT capture_file_id) AS files
                FROM field_observations
                WHERE field_path LIKE ?
                """,
                (f"%{key.replace('.value', '')}%",),
            ).fetchone()
            field_hits += int(row["files"] or 0)

    return {
        "exact": [dict(row) for row in exact_rows],
        "same_area": sorted(same_area.values(), key=lambda item: int(item["files"]), reverse=True)[
            :10
        ],
        "field_hits": field_hits,
    }


def _priority(endpoint: LegacyDailyEndpoint, matches: dict[str, object]) -> str:
    exact = matches["exact"]
    same_area = matches["same_area"]
    if exact:
        return "A"
    if endpoint.function in {"get_tmall_dailyshopdata", "get_member_overview"} and same_area:
        return "A-"
    if same_area:
        return "B"
    return "C"


def _daily_params_for(endpoint: LegacyDailyEndpoint, day: str) -> dict[str, str]:
    if endpoint.date_mode == "dateRange_day":
        params = {"dateType": "day", "dateRange": f"{day}|{day}"}
    elif endpoint.date_mode == "date_pair":
        params = {"startDate": day, "endDate": day}
    elif endpoint.date_mode == "epoch_ms_range":
        params = {"startTime": "<day_start_ms>", "endTime": "<day_start_ms>"}
    elif endpoint.date_mode == "date_string_range":
        params = {"startTime": day, "endTime": day}
    else:
        params = {"date": day}

    if "page" in endpoint.params:
        params["page"] = "1"
    if "pageSize" in endpoint.params:
        params["pageSize"] = "100" if endpoint.function == "get_rtb_plan_data" else "10"
    return params


def build_report(
    endpoints: list[LegacyDailyEndpoint],
    matches: dict[str, dict[str, object]],
    *,
    day: str,
    source_path: Path,
    daily_requests: list[dict[str, object]],
) -> str:
    rows = []
    for endpoint in endpoints:
        endpoint_matches = matches[endpoint.function]
        rows.append((endpoint, endpoint_matches, _priority(endpoint, endpoint_matches)))

    lines = [
        "# Daily Endpoint Candidates",
        "",
        f"- Source script: `{source_path}`",
        f"- Test day: `{day}`",
        "- Note: captures made on 2026-07-30 may request business date `2026-07-29` because daily reports usually pull yesterday.",
        "- Mode: offline contract analysis. No platform request replay was executed.",
        "",
        "## Captured Daily-Shaped Requests",
        "",
    ]
    if daily_requests:
        lines.extend(
            [
                "| Business date | Date mode | Files | Note |",
                "| --- | --- | ---: | --- |",
            ]
        )
        for row in daily_requests:
            lines.append(
                f"| `{row.get('business_date') or 'unknown'}` | `{row['date_mode']}` | {row['files']} | request body has day params; paired response is not necessarily metric data |"
            )
    else:
        lines.append("No request body with clear day-level params was found in the current local capture set.")

    lines.extend(
        [
            "",
            "## Summary",
            "",
            "| Priority | Function | Table | Date mode | Legacy path | Capture evidence |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for endpoint, endpoint_matches, priority in rows:
        exact = endpoint_matches["exact"]
        same_area = endpoint_matches["same_area"]
        if exact:
            evidence = f"exact {exact[0]['files']} files"
        elif same_area:
            evidence = f"related {same_area[0]['path']} ({same_area[0]['files']} files)"
        else:
            evidence = "not observed in local body analysis"
        lines.append(
            f"| `{priority}` | `{endpoint.function}` | `{endpoint.table}` | `{endpoint.date_mode}` | `{endpoint.path}` | {evidence} |"
        )

    lines.extend(
        [
            "",
            "## Priority A: Good First Daily Tests",
            "",
            f"These are the safest first candidates for the `{day}` business-date importer contract because they either have exact local evidence or strong same-module evidence.",
            "",
        ]
    )
    for endpoint, endpoint_matches, priority in rows:
        if priority not in {"A", "A-"}:
            continue
        lines.extend(_endpoint_section(endpoint, endpoint_matches, priority, day))

    lines.extend(
        [
            "",
            "## Remaining Candidates",
            "",
        ]
    )
    for endpoint, endpoint_matches, priority in rows:
        if priority in {"A", "A-"}:
            continue
        lines.extend(_endpoint_section(endpoint, endpoint_matches, priority, day))

    lines.extend(
        [
            "",
            "## Implementation Notes",
            "",
            "- Build the first worker as a dry-run importer: generate URL, normalized params, target table, and expected response shape, but do not write to MySQL until the parsed row count and field mapping are validated.",
            "- Keep legacy cookies/tokens outside code and Markdown. Runtime credential loading should be a separate adapter concern.",
            "- For `dateRange_day`, use `YYYY-MM-DD|YYYY-MM-DD`; for `date_pair`, use `startDate=endDate=YYYY-MM-DD`; for `epoch_ms_range`, convert the local day start to milliseconds.",
            "- `token`, `_tb_token_`, and `csrfID` are contract placeholders only. They must be resolved at runtime and never persisted in reports.",
        "- The 2026-07-30 capture suggests some SYCM old endpoints have moved to `/portal/coreIndex/new/*/v3.json`; keep a versioned adapter instead of hard-coding one URL in the page layer.",
        ]
    )
    return "\n".join(lines) + "\n"


def _endpoint_section(
    endpoint: LegacyDailyEndpoint,
    matches: dict[str, object],
    priority: str,
    day: str,
) -> list[str]:
    lines = [
        f"### `{endpoint.function}`",
        "",
        f"- Priority: `{priority}`",
        f"- URL: `{endpoint.url}`",
        f"- Table: `{endpoint.table}`",
        f"- Date params for `{day}`: `{json.dumps(_daily_params_for(endpoint, day), ensure_ascii=False)}`",
        f"- Runtime-only params: `{', '.join(key for key in endpoint.params if key in SECRET_PARAM_KEYS) or 'none'}`",
    ]
    exact = matches["exact"]
    same_area = matches["same_area"]
    if exact:
        lines.append(f"- Capture exact match: `{exact[0]['host']}{exact[0]['path']}` seen in `{exact[0]['files']}` files")
    elif same_area:
        lines.append("- Capture related candidates:")
        for row in same_area[:5]:
            lines.append(f"  - `{row['host']}{row['path']}` seen in `{row['files']}` files")
    else:
        lines.append("- Capture evidence: no URL/path candidate found in the current offline body analysis")

    if endpoint.metric_keys:
        preview = ", ".join(f"`{key}`" for key in endpoint.metric_keys[:18])
        lines.append(f"- Metric keys from legacy mapping: {preview}")
    lines.append("")
    return lines


def _daily_request_rows(database_path: Path) -> list[dict[str, object]]:
    if not database_path.exists():
        return []
    with sqlite3.connect(database_path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        return [
            dict(row)
            for row in connection.execute(
                """
                SELECT business_date, date_mode, COUNT(*) AS files
                FROM daily_request_candidates
                GROUP BY business_date, date_mode
                ORDER BY files DESC, business_date
                """
            )
        ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze daily endpoint candidates.")
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
    parser.add_argument("--day", default="2026-07-30")
    parser.add_argument("--report", type=Path, default=Path("docs/DAILY_ENDPOINTS.md"))
    args = parser.parse_args()

    endpoints = extract_legacy_endpoints(args.source)
    matches = {
        endpoint.function: _query_capture_matches(args.capture_db, endpoint)
        for endpoint in endpoints
    }
    daily_requests = _daily_request_rows(args.capture_db)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        build_report(
            endpoints,
            matches,
            day=args.day,
            source_path=args.source,
            daily_requests=daily_requests,
        ),
        encoding="utf-8",
    )

    priorities = {key: 0 for key in ("A", "A-", "B", "C")}
    for endpoint in endpoints:
        priorities[_priority(endpoint, matches[endpoint.function])] += 1
    print(
        json.dumps(
            {
                "source": str(args.source),
                "day": args.day,
                "endpoints": len(endpoints),
                "priorities": priorities,
                "report": str(args.report),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
