from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scripts import fetch_taobao_flash_sale


class _Response:
    status = 200

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"success":true,"data":{"data":[]}}'


def test_flash_sale_overview_uses_the_platform_request_parameter_name(
    monkeypatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout: int) -> _Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(fetch_taobao_flash_sale, "urlopen", fake_urlopen)
    result = fetch_taobao_flash_sale.fetch_taobao_flash_sale(
        day=date(2026, 8, 26),
        output=tmp_path / "flash-sale.json",
        cookie="t=session; _tb_token_=not-needed",
        timeout=17,
    )

    request = captured["request"]
    query = parse_qs(urlparse(request.full_url).query)

    assert result.ok
    assert captured["timeout"] == 17
    assert query["startTime"] == ["1787673600000"]
    assert query["endTime"] == ["1787673600000"]
    assert query["__sm_request__"] == ["true"]
    assert "sm_request" not in query
    assert "tb_token" not in query


def test_non_json_direct_response_retries_in_existing_browser(monkeypatch, tmp_path: Path) -> None:
    class HtmlResponse(_Response):
        def read(self) -> bytes:
            return b"<html>login</html>"

    captured: dict[str, object] = {}
    monkeypatch.setattr(fetch_taobao_flash_sale, "urlopen", lambda *_args, **_kwargs: HtmlResponse())

    def browser_fetch(port: int, url: str, *, timeout: int) -> tuple[int, bytes]:
        captured.update(port=port, url=url, timeout=timeout)
        return 200, b'{"success":true,"data":{"data":[]}}'

    monkeypatch.setattr(fetch_taobao_flash_sale, "_fetch_in_existing_browser", browser_fetch)
    output = tmp_path / "flash-sale.json"
    result = fetch_taobao_flash_sale.fetch_taobao_flash_sale(
        day=date(2026, 9, 22), output=output, cookie="t=session", browser_port=9222, timeout=11,
    )

    assert result.ok
    assert captured["port"] == 9222
    assert captured["timeout"] == 11
    assert urlparse(str(captured["url"])).hostname == "sale.taobao.com"
    assert output.read_bytes().startswith(b'{"success":true')


def test_non_json_without_managed_browser_remains_a_failure(monkeypatch, tmp_path: Path) -> None:
    class HtmlResponse(_Response):
        def read(self) -> bytes:
            return b"<html>login</html>"

    monkeypatch.setattr(fetch_taobao_flash_sale, "urlopen", lambda *_args, **_kwargs: HtmlResponse())
    result = fetch_taobao_flash_sale.fetch_taobao_flash_sale(
        day=date(2026, 9, 22), output=tmp_path / "flash-sale.json", cookie="t=session",
    )
    assert not result.ok
    assert result.message == "non-json response"
