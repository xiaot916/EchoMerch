from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.tmall_session import (  # noqa: E402
    DEFAULT_UTRY_REPORT_HOME_URL,
    UtryReportTemplate,
    add_session_source_arguments,
    resolve_utry_runtime_context,
)


UTRY_WIDGET_URL = "https://quark.taobao.com/fbi/.json"
UTRY_REPORT_CONFIG = {
    "sample": {
        "report_id": 1904974,
        "endpoint_key": "quark.utry.sample_platform.sample_overview",
    },
    "repurchase": {
        "report_id": 1906730,
        "endpoint_key": "quark.utry.sample_platform.repurchase_overview",
    },
}


def fetch_utry_report(
    *,
    template: UtryReportTemplate,
    business_day: date,
    output: Path,
    cookie: str,
    timeout: int = 60,
) -> tuple[int, int | None, str | None, int, int, int]:
    if template.report_id not in {item["report_id"] for item in UTRY_REPORT_CONFIG.values()}:
        raise ValueError(f"Unsupported U先 report id: {template.report_id}")
    params = _dated_params(template.params, business_day)
    output.parent.mkdir(parents=True, exist_ok=True)
    status, response_body = _request_report_page_with_retry(
        template=template,
        params=params,
        cookie=cookie,
        timeout=timeout,
    )
    code, message = _response_status(response_body)
    if not 200 <= status < 300 or code != 0:
        output.write_bytes(response_body)
        row_count, row_limit, _ = _response_page(response_body)
        return status, code, message, len(response_body), row_count, row_limit

    payload = _decode_payload(response_body)
    row_count, row_limit, row_offset = _payload_page(payload)
    if row_count <= row_limit:
        output.write_bytes(response_body)
        return status, code, message, len(response_body), row_count, row_limit
    if row_limit <= 0:
        raise RuntimeError(
            f"U先 report {template.report_id} returned count={row_count} with an invalid limit={row_limit}."
        )

    dataset_guid = _dataset_guid(params)
    first_values = _payload_values(payload)
    if not first_values:
        raise RuntimeError(
            f"U先 report {template.report_id} returned count={row_count} but its first page was empty."
        )

    page_payloads = [payload]
    received_rows = len(first_values)
    next_offset = row_offset + len(first_values)
    while next_offset < row_count:
        page_params = _paginated_params(
            params,
            dataset_guid=dataset_guid,
            offset=next_offset,
            limit=row_limit,
        )
        page_status, page_body = _request_report_page_with_retry(
            template=template,
            params=page_params,
            cookie=cookie,
            timeout=timeout,
        )
        page_code, page_message = _response_status(page_body)
        if not 200 <= page_status < 300 or page_code != 0:
            raise RuntimeError(
                f"U先 report {template.report_id} page offset={next_offset} failed: "
                f"HTTP {page_status}, code={page_code}, message={page_message or 'unknown error'}."
            )
        page_payload = _decode_payload(page_body)
        page_count, _, page_offset = _payload_page(page_payload)
        if page_offset != next_offset:
            raise RuntimeError(
                f"U先 report {template.report_id} ignored pagination offset={next_offset}; "
                f"the response returned offset={page_offset}."
            )
        page_values = _payload_values(page_payload)
        if not page_values:
            raise RuntimeError(
                f"U先 report {template.report_id} returned an empty page at offset={next_offset} "
                f"before all {row_count} rows were fetched."
            )
        page_payloads.append(page_payload)
        received_rows += len(page_values)
        row_count = max(row_count, page_count)
        next_offset = page_offset + len(page_values)

    if received_rows < row_count:
        raise RuntimeError(
            f"U先 report {template.report_id} fetched {received_rows} rows but expected {row_count}."
        )
    merged_body = _merge_page_payloads(page_payloads, row_count=row_count)
    output.write_bytes(merged_body)
    return status, code, message, len(merged_body), row_count, row_limit


def _request_report_page_with_retry(
    *,
    template: UtryReportTemplate,
    params: dict[str, Any],
    cookie: str,
    timeout: int,
    attempts: int = 3,
) -> tuple[int, bytes]:
    """Retry transient success responses that have no usable report payload."""

    last: tuple[int, bytes] | None = None
    for attempt in range(attempts):
        result = _request_report_page(
            template=template,
            params=params,
            cookie=cookie,
            timeout=timeout,
        )
        last = result
        status, body = result
        try:
            payload = json.loads(body.decode("utf-8"))
            value = payload.get("data", {}).get("value", {})
            if isinstance(value, dict) and isinstance(value.get("page"), dict):
                return result
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            pass
        if attempt + 1 < attempts:
            time.sleep(0.5 * (attempt + 1))
    assert last is not None
    return last


def _request_report_page(
    *,
    template: UtryReportTemplate,
    params: dict[str, Any],
    cookie: str,
    timeout: int,
) -> tuple[int, bytes]:
    body = urlencode({"params": json.dumps(params, ensure_ascii=False, separators=(",", ":"))})
    request = Request(
        template.request_url or UTRY_WIDGET_URL,
        data=body.encode("utf-8"),
        method="POST",
        headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9",
            "bx-v": "2.5.37",
            "content-type": "application/x-www-form-urlencoded",
            "cookie": cookie,
            "origin": "https://quark.taobao.com",
            "referer": template.referer or DEFAULT_UTRY_REPORT_HOME_URL,
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/151.0.0.0 Safari/537.36"
            ),
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


def _dated_params(params: dict[str, Any], business_day: date) -> dict[str, Any]:
    result = copy.deepcopy(params)
    day = business_day.isoformat()
    for config in result.get("configs", []):
        if not isinstance(config, dict) or config.get("type") != "condition":
            continue
        condition = config.get("config")
        if not isinstance(condition, dict):
            continue
        value_type = condition.get("valueType")
        if value_type == "dateTimeRange":
            condition["value"] = {"start": day, "end": day}
        elif value_type == "dateTimePicker":
            condition["value"] = day
    return result


def _response_status(response_body: bytes) -> tuple[int | None, str | None]:
    try:
        payload = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "non-json response"
    if not isinstance(payload, dict):
        return None, "unexpected response payload"
    try:
        code = int(payload.get("code"))
    except (TypeError, ValueError):
        code = None
    return code, payload.get("message") or payload.get("finalMessage")


def _decode_payload(response_body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(response_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("U先 returned a non-JSON success response.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("U先 returned an unexpected success response.")
    return payload


def _response_page(response_body: bytes) -> tuple[int, int, int]:
    try:
        return _payload_page(_decode_payload(response_body))
    except RuntimeError:
        return 0, 0, 0


def _payload_page(payload: dict[str, Any]) -> tuple[int, int, int]:
    try:
        page = payload["data"]["value"]["page"]
        return (
            int(page.get("count", 0)),
            int(page.get("limit", 0)),
            int(page.get("offset", 0)),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("U先 response is missing data.value.page pagination metadata.") from exc


def _payload_values(payload: dict[str, Any]) -> list[Any]:
    try:
        values = payload["data"]["value"]["values"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("U先 response is missing data.value.values.") from exc
    if not isinstance(values, list):
        raise RuntimeError("U先 response data.value.values is not a list.")
    return values


def _dataset_guid(params: dict[str, Any]) -> Any:
    for config in params.get("configs", []):
        if isinstance(config, dict) and config.get("type") == "datasetId":
            dataset_guid = config.get("datasetGuid")
            if dataset_guid is not None:
                return dataset_guid
    raise RuntimeError("U先 request template is missing its datasetGuid.")


def _paginated_params(
    params: dict[str, Any],
    *,
    dataset_guid: Any,
    offset: int,
    limit: int,
) -> dict[str, Any]:
    result = copy.deepcopy(params)
    configs = result.setdefault("configs", [])
    pagination = {
        "datasetGuid": dataset_guid,
        "type": "pagination",
        "config": {"offset": offset, "limit": limit},
    }
    for index, config in enumerate(configs):
        if (
            isinstance(config, dict)
            and config.get("type") == "pagination"
            and config.get("datasetGuid") == dataset_guid
        ):
            configs[index] = pagination
            break
    else:
        configs.append(pagination)
    return result


def _merge_page_payloads(
    payloads: list[dict[str, Any]],
    *,
    row_count: int,
) -> bytes:
    merged = copy.deepcopy(payloads[0])
    merged_values: list[Any] = []
    seen: set[str] = set()
    for payload in payloads:
        for row in _payload_values(payload):
            identity = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if identity in seen:
                continue
            seen.add(identity)
            merged_values.append(row)
    value = merged["data"]["value"]
    value["values"] = merged_values
    value["page"] = {
        "count": row_count,
        "limit": len(merged_values),
        "offset": 0,
    }
    merged["_echoMerchPagination"] = {
        "pages": len(payloads),
        "receivedRows": sum(len(_payload_values(payload)) for payload in payloads),
        "uniqueRows": len(merged_values),
    }
    return json.dumps(merged, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch one U先 daily report from live page templates.")
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--report-type", choices=sorted(UTRY_REPORT_CONFIG), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--report-home-url", default=DEFAULT_UTRY_REPORT_HOME_URL)
    add_session_source_arguments(parser)
    args = parser.parse_args()
    if args.session_source != "drissionpage":
        raise ValueError("U先 requires --session-source drissionpage.")
    runtime = resolve_utry_runtime_context(
        source=args.session_source,
        cookie_env=args.cookie_env,
        browser_port=args.browser_port,
        report_home_url=args.report_home_url,
        timeout=args.timeout,
    )
    report_id = UTRY_REPORT_CONFIG[args.report_type]["report_id"]
    template = runtime.templates[report_id]
    status, code, message, size, rows, limit = fetch_utry_report(
        template=template,
        business_day=args.day,
        output=args.output,
        cookie=runtime.session.cookie_header,
        timeout=args.timeout,
    )
    print(json.dumps({
        "status": status,
        "code": code,
        "message": message,
        "report_type": args.report_type,
        "report_id": report_id,
        "rows": rows,
        "limit": limit,
        "output": str(args.output),
        "bytes": size,
    }, ensure_ascii=False, indent=2))
    return 0 if 200 <= status < 300 and code == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"U先 report fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
