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
