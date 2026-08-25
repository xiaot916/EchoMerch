import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scripts import fetch_mtop_content_overview


class _Response:
    status = 200

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return (
            b'mtopjsonp35({"ret":["SUCCESS::ok"],"data":{"model":{"result":['
            b'{"ds":"20260818","consumeUv":{"absolute":15062}}]}}})'
        )


def test_content_overview_uses_trailing_window_ending_on_target_day(
    monkeypatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(request, timeout: int) -> _Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(fetch_mtop_content_overview, "urlopen", fake_urlopen)
    output = tmp_path / "content.json"

    result = fetch_mtop_content_overview.fetch_mtop_content_overview(
        day=date(2026, 8, 18),
        output=output,
        cookie="_m_h5_tk=runtime_token_123; t=session",
        timeout=17,
    )

    request = captured["request"]
    query = parse_qs(urlparse(request.full_url).query)
    data = json.loads(query["data"][0])
    conditions = json.loads(data["conditions"])

    assert result.ok
    assert captured["timeout"] == 17
    assert data["timeRangeType"] == "7"
    assert conditions["stat_date"] == "20260812"
    assert conditions["end_date"] == "20260818"
    assert conditions["retainLatestDs"] is True
    assert request.get_header("Cookie") == "_m_h5_tk=runtime_token_123; t=session"
    assert json.loads(output.read_text(encoding="utf-8"))["data"]["model"]["result"][0]["ds"] == "20260818"
