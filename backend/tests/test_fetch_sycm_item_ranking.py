import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scripts import fetch_sycm_item_ranking


class _Response:
    status = 200

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps({"code": 0, "message": "操作成功"}).encode("utf-8")


def test_item_ranking_request_uses_runtime_cookie_and_expected_query(
    monkeypatch, tmp_path: Path
) -> None:
    captured = {}

    def fake_urlopen(request, timeout: int) -> _Response:
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(fetch_sycm_item_ranking, "urlopen", fake_urlopen)
    output = tmp_path / "item-ranking.json"

    status, code, message, size = fetch_sycm_item_ranking.fetch_item_ranking(
        day=date(2026, 8, 16),
        output=output,
        cookie="t=runtime-session",
        page=2,
        page_size=50,
        timeout=12,
    )

    query = parse_qs(urlparse(captured["url"]).query)
    assert status == 200
    assert code == 0
    assert message == "操作成功"
    assert size == output.stat().st_size
    assert query["dateRange"] == ["2026-08-16|2026-08-16"]
    assert query["page"] == ["2"]
    assert query["pageSize"] == ["50"]
    assert "itmBounceRate" in query["indexCode"][0]
    assert captured["headers"]["Cookie"] == "t=runtime-session"
    assert captured["timeout"] == 12
