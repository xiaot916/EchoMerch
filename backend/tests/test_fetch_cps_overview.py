import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from app.integrations.session import cps
from app.integrations.session.core import RuntimeSessionUnavailable
from scripts import fetch_cps_items, fetch_cps_overview


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


def test_cps_overview_retries_taobao_error_page_in_existing_tab(monkeypatch, tmp_path: Path) -> None:
    class HtmlResponse(_Response):
        def read(self) -> bytes:
            return b"<html>taobao-error</html>"

    calls = []
    monkeypatch.setattr(fetch_cps_overview, "urlopen", lambda *_args, **_kwargs: HtmlResponse())

    def browser_fetch(port, url, params, *, timeout):
        calls.append((port, url, params, timeout))
        return 200, _Response().read()

    monkeypatch.setattr(fetch_cps_overview, "fetch_cps_browser_json", browser_fetch)
    output = tmp_path / "cps.json"
    status, code, _, _ = fetch_cps_overview.fetch_cps_overview(
        business_day=date(2026, 9, 22), output=output,
        cookie="t=session", tb_token="transient", browser_port=9222,
    )
    assert (status, code) == (200, 200)
    assert len(calls) == 1
    assert calls[0][0] == 9222
    assert output.read_bytes() == _Response().read()


def test_cps_item_page_retries_non_json_in_existing_tab(monkeypatch, tmp_path: Path) -> None:
    class HtmlResponse(_Response):
        def read(self) -> bytes:
            return b"<html>taobao-error</html>"

    monkeypatch.setattr(fetch_cps_items, "urlopen", lambda *_args, **_kwargs: HtmlResponse())
    monkeypatch.setattr(
        fetch_cps_items, "fetch_cps_browser_json",
        lambda *_args, **_kwargs: (200, b'{"data":{"list":[{"itemId":"1"}]}}'),
    )
    output = tmp_path / "item.json"
    status, payload, _ = fetch_cps_items.fetch_cps_items_page(
        business_day=date(2026, 9, 22), page_num=1, page_size=20,
        output=output, cookie="t=session", tb_token="transient", browser_port=9222,
    )
    assert status == 200
    assert payload["data"]["list"][0]["itemId"] == "1"
    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_cps_browser_fallback_is_limited_to_known_read_only_endpoints(monkeypatch) -> None:
    class Tab:
        def run_cdp(self, _method, **kwargs):
            assert "transient-secret" not in kwargs["expression"]
            assert "document.cookie" in kwargs["expression"]
            return {"result": {"value": {"status": 200, "body": '{"resultCode":200}'}}}

    class Browser:
        def __init__(self, port):
            assert port == 9222

        def find_tab(self, hosts):
            assert hosts == ("ad.alimama.com",)
            return Tab()

    monkeypatch.setattr("app.integrations.session.core.DrissionPageBrowser", Browser)
    status, body = cps.fetch_cps_browser_json(
        9222, cps.CPS_OVERVIEW_URL, {"_tb_token_": "transient-secret", "startDate": "2026-09-22"},
    )
    assert status == 200
    assert json.loads(body)["resultCode"] == 200
    with pytest.raises(ValueError, match="只读报表"):
        cps.fetch_cps_browser_json(9222, "https://ad.alimama.com/openapi/write.json", {})
    with pytest.raises(ValueError, match="只读报表"):
        cps.fetch_cps_browser_json(9222, "https://evil.example/openapi/param2/1/gateway.unionadv/data.home.overview.json", {})


def test_cps_browser_fallback_does_not_open_a_new_tab(monkeypatch) -> None:
    class Browser:
        def __init__(self, _port):
            pass

        def find_tab(self, _hosts):
            return None

        def new_tab(self, _url):
            pytest.fail("fallback must not open a new page")

    monkeypatch.setattr("app.integrations.session.core.DrissionPageBrowser", Browser)
    with pytest.raises(RuntimeSessionUnavailable, match="已打开"):
        cps.fetch_cps_browser_json(9222, cps.CPS_ITEM_ANALYSIS_URL, {})
