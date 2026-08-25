import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs

import pytest

from app.integrations.tmall_session import UtryReportTemplate
from scripts import fetch_utry_report


class _Response:
    status = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


def _template() -> UtryReportTemplate:
    return UtryReportTemplate(
        report_id=1904974,
        request_url="https://quark.taobao.com/fbi/.json",
        referer="https://quark.taobao.com/dashboard/view/uic.htm?id=1904974",
        params={
            "reportId": 1904974,
            "configs": [
                {"datasetGuid": 74161110, "type": "datasetId"},
                {
                    "datasetGuid": 74161110,
                    "type": "condition",
                    "config": {
                        "valueType": "dateTimePicker",
                        "value": "2026-07-01",
                    },
                },
            ],
        },
    )


def _payload(*, count: int, limit: int, offset: int, rows: list[int]) -> dict[str, object]:
    return {
        "code": 0,
        "data": {
            "value": {
                "columns": [],
                "values": [[{"v": row}] for row in rows],
                "page": {"count": count, "limit": limit, "offset": offset},
            }
        },
    }


def _request_params(request: object) -> dict[str, object]:
    form = parse_qs(request.data.decode("utf-8"), keep_blank_values=True)
    return json.loads(form["params"][0])


def test_utry_does_not_paginate_when_count_does_not_exceed_limit(
    monkeypatch, tmp_path: Path
) -> None:
    requests = []
    payload = _payload(count=2, limit=1000, offset=0, rows=[1, 2])

    def fake_urlopen(request, timeout: int) -> _Response:
        requests.append(request)
        return _Response(payload)

    monkeypatch.setattr(fetch_utry_report, "urlopen", fake_urlopen)
    output = tmp_path / "utry.json"
    result = fetch_utry_report.fetch_utry_report(
        template=_template(),
        business_day=date(2026, 8, 19),
        output=output,
        cookie="t=runtime-session",
    )

    assert result[4:] == (2, 1000)
    assert len(requests) == 1
    assert not any(
        config.get("type") == "pagination"
        for config in _request_params(requests[0])["configs"]
    )
    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_utry_paginates_only_after_first_response_exceeds_limit(
    monkeypatch, tmp_path: Path
) -> None:
    requests = []
    responses = iter(
        [
            _payload(count=5, limit=2, offset=0, rows=[1, 2]),
            _payload(count=5, limit=2, offset=2, rows=[2, 3]),
            _payload(count=5, limit=2, offset=4, rows=[4, 5]),
        ]
    )

    def fake_urlopen(request, timeout: int) -> _Response:
        requests.append(request)
        return _Response(next(responses))

    monkeypatch.setattr(fetch_utry_report, "urlopen", fake_urlopen)
    output = tmp_path / "utry-paginated.json"
    result = fetch_utry_report.fetch_utry_report(
        template=_template(),
        business_day=date(2026, 8, 19),
        output=output,
        cookie="t=runtime-session",
    )

    assert result[4:] == (5, 2)
    assert len(requests) == 3
    first_configs = _request_params(requests[0])["configs"]
    assert not any(config.get("type") == "pagination" for config in first_configs)
    page_configs = [
        next(
            config
            for config in _request_params(request)["configs"]
            if config.get("type") == "pagination"
        )
        for request in requests[1:]
    ]
    assert [config["config"] for config in page_configs] == [
        {"offset": 2, "limit": 2},
        {"offset": 4, "limit": 2},
    ]
    merged = json.loads(output.read_text(encoding="utf-8"))
    assert [row[0]["v"] for row in merged["data"]["value"]["values"]] == [1, 2, 3, 4, 5]
    assert merged["data"]["value"]["page"] == {"count": 5, "limit": 5, "offset": 0}
    assert merged["_echoMerchPagination"] == {
        "pages": 3,
        "receivedRows": 6,
        "uniqueRows": 5,
    }


def test_utry_rejects_a_page_when_server_ignores_requested_offset(
    monkeypatch, tmp_path: Path
) -> None:
    responses = iter(
        [
            _payload(count=3, limit=2, offset=0, rows=[1, 2]),
            _payload(count=3, limit=2, offset=0, rows=[1, 2]),
        ]
    )

    monkeypatch.setattr(
        fetch_utry_report,
        "urlopen",
        lambda request, timeout: _Response(next(responses)),
    )

    with pytest.raises(RuntimeError, match="ignored pagination offset=2"):
        fetch_utry_report.fetch_utry_report(
            template=_template(),
            business_day=date(2026, 8, 19),
            output=tmp_path / "ignored-offset.json",
            cookie="t=runtime-session",
        )
