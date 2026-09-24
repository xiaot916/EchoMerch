from datetime import date
from pathlib import Path

from scripts import fetch_taobao_flash_sale_items as items


class _HtmlResponse:
    status = 200

    def __enter__(self) -> "_HtmlResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return b"<html>login</html>"


def test_item_fetch_uses_existing_browser_when_direct_request_is_html(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(items, "urlopen", lambda *_args, **_kwargs: _HtmlResponse())
    captured: dict[str, object] = {}

    def browser_fetch(port: int, url: str, *, timeout: int, include_tb_token: bool) -> tuple[int, bytes]:
        captured.update(port=port, url=url, timeout=timeout, token=include_tb_token)
        return 200, b'{"success":true,"data":{"data":[]}}'

    monkeypatch.setattr(items, "_fetch_in_existing_browser", browser_fetch)
    output = tmp_path / "items.json"
    result = items.fetch_taobao_flash_sale_items(
        day=date(2026, 9, 22), output=output, cookie="t=session", browser_port=9222,
    )

    assert result.ok
    assert captured["port"] == 9222
    assert captured["token"] is True
    assert "tbhjItemDataQuery.json" in str(captured["url"])
    assert output.read_bytes().startswith(b'{"success":true')


def test_html_response_is_not_success_without_browser(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(items, "urlopen", lambda *_args, **_kwargs: _HtmlResponse())
    result = items.fetch_taobao_flash_sale_items(
        day=date(2026, 9, 22), output=tmp_path / "items.json", cookie="t=session",
    )

    assert not result.ok
    assert result.message == "non-json response"
