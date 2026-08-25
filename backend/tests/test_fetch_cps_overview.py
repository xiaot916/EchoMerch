import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scripts import fetch_cps_overview


class _Response:
    status = 200

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"success":true,"resultCode":200,"data":{"result":[{"pay_ord_amt_8":"1329.84"}]}}'


def test_cps_overview_builds_a_single_day_query(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_urlopen(request, timeout: int) -> _Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(fetch_cps_overview, "urlopen", fake_urlopen)
    output = tmp_path / "cps.json"
    status, code, message, size = fetch_cps_overview.fetch_cps_overview(
        business_day=date(2026, 8, 17),
        output=output,
        cookie="t=runtime-session",
        tb_token="runtime-token",
        timeout=17,
    )

    request = captured["request"]
    query = parse_qs(urlparse(request.full_url).query)
    assert status == 200
    assert code == 200
    assert message is None
    assert size == output.stat().st_size
    assert query["split"] == ["0"]
    assert query["startDate"] == ["2026-08-17"]
    assert query["endDate"] == ["2026-08-17"]
    assert query["_tb_token_"] == ["runtime-token"]
    assert "t" in query
    assert request.get_header("Cookie") == "t=runtime-session"
    assert captured["timeout"] == 17
    assert json.loads(output.read_text(encoding="utf-8"))["data"]
