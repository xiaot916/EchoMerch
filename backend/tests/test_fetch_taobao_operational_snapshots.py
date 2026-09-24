from pathlib import Path

import pytest

from scripts import fetch_taobao_operational_snapshots as snapshots
from scripts.backfill_taobao_operational_snapshots import _page_metadata


class _HtmlResponse:
    status = 200

    def __enter__(self) -> "_HtmlResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return b"<html>login</html>"


def test_mtop_html_response_is_not_a_success(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(snapshots, "urlopen", lambda *_args, **_kwargs: _HtmlResponse())
    result = snapshots.fetch_risk_price(
        output=tmp_path / "risk.json", cookie="_m_h5_tk=token_123",
    )

    assert not result.ok
    assert result.message == "non-json response"


@pytest.mark.parametrize("ret", ["BUSINESS_EXCEPTION::ic服务异常", "FAIL_SYS_TOKEN_EXPIRED::令牌失效"])
def test_mtop_platform_error_cannot_be_treated_as_a_success(monkeypatch, tmp_path: Path, ret: str) -> None:
    class ErrorResponse(_HtmlResponse):
        def read(self) -> bytes:
            import json
            return json.dumps({"ret": [ret], "data": {"showErrorMessage": {}}}).encode("utf-8")

    monkeypatch.setattr(snapshots, "urlopen", lambda *_args, **_kwargs: ErrorResponse())
    result = snapshots.fetch_current_prices(
        output=tmp_path / "current.json", cookie="_m_h5_tk=token_123", page=5,
    )
    assert not result.ok
    assert result.message == ret


def test_snapshot_pagination_distinguishes_explicit_empty_from_missing_list() -> None:
    assert _page_metadata({"data": {"model": {"items": [], "totalCount": 0}}}) == ([], 0)
    assert _page_metadata({"data": {"data": [], "total": 0}}) == ([], 0)
    with pytest.raises(ValueError, match="未返回明细列表"):
        _page_metadata({"data": {"showErrorMessage": {}}})
