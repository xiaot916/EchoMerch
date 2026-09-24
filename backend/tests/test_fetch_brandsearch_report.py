import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scripts import fetch_brandsearch_report


class _Response:
    status = 200

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"data":{"rptQueryResp":{"rptDataSum":[]}}}'


def test_brandsearch_report_builds_daily_query(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_urlopen(request, timeout: int) -> _Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(fetch_brandsearch_report, "urlopen", fake_urlopen)
    output = tmp_path / "brandsearch.json"
    status, code, message, size = fetch_brandsearch_report.fetch_brandsearch_report(
        business_day=date(2026, 8, 17),
        output=output,
        cookie="t=runtime-session",
        csrf_id="csrf-value",
        product_id="101005201",
        query_params={"r": "mx-548"},
        timeout=17,
    )

    request = captured["request"]
    query = parse_qs(urlparse(request.full_url).query)
    assert status == 200
    assert code is None
    assert message is None
    assert size == output.stat().st_size
    assert query["r"] == ["mx-548"]
    assert query["productId"] == ["101005201"]
    assert query["csrfID"] == ["csrf-value"]
    assert query["startDate"] == ["2026-08-17"]
    assert query["endDate"] == ["2026-08-17"]
    assert request.get_header("Cookie") == "t=runtime-session"
    assert captured["timeout"] == 17
    assert json.loads(output.read_text(encoding="utf-8"))["data"]


def test_brandsearch_html_retries_in_existing_branding_tab(monkeypatch, tmp_path: Path) -> None:
    class HtmlResponse(_Response):
        def read(self) -> bytes:
            return b"<html>login</html>"

    monkeypatch.setattr(fetch_brandsearch_report, "urlopen", lambda *_args, **_kwargs: HtmlResponse())
    captured: dict[str, object] = {}

    def browser_fetch(port: int, url: str, *, timeout: int) -> tuple[int, bytes]:
        captured.update(port=port, url=url, timeout=timeout)
        return 200, b'{"data":{"rptQueryResp":{"rptDataSum":[]}},"info":{"ok":true}}'

    monkeypatch.setattr(fetch_brandsearch_report, "_fetch_in_brandsearch_tab", browser_fetch)
    output = tmp_path / "brandsearch.json"
    status, _code, _message, size = fetch_brandsearch_report.fetch_brandsearch_report(
        business_day=date(2026, 9, 22), output=output,
        cookie="t=session", csrf_id="csrf", browser_port=9222, timeout=11,
    )

    assert (status, size) == (200, output.stat().st_size)
    assert captured["port"] == 9222
    assert captured["timeout"] == 11
    assert urlparse(str(captured["url"])).hostname == "brandsearch.taobao.com"
    assert json.loads(output.read_text(encoding="utf-8"))["info"]["ok"] is True
