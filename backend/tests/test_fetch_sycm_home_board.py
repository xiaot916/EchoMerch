"""Request-contract tests for the SYCM home-board endpoint group.

The interesting behaviour here is `portal/month/trend.json`: it returns a
rolling 30-day series that always ends on the *previous* closed day, so the
request must not use the requested business day as its own end date.  Asking
for today produced, on the scheduled 07:30 run:

    month_trend: HTTP 200, code 1009, validate end date error,
    Params: statDate=2026-09-18, endDate=2026-09-19

See `scripts/fetch_sycm_home_board.fetch_sycm_home_board` for the full note.
"""

import json
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from scripts import fetch_sycm_home_board


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


@pytest.fixture()
def captured_urls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every endpoint URL the fetcher builds, without touching the network."""
    urls: list[str] = []

    def fake_urlopen(request, timeout=None):  # noqa: ANN001, ARG001
        urls.append(request.full_url if hasattr(request, "full_url") else str(request))
        return _Response({"content": {"code": 0, "data": {}}})

    monkeypatch.setattr(fetch_sycm_home_board, "urlopen", fake_urlopen)
    monkeypatch.setattr(fetch_sycm_home_board.time, "sleep", lambda _s: None)
    return urls


def _date_range_of(url: str) -> str:
    return parse_qs(urlparse(url).query)["dateRange"][0]


def test_month_trend_asks_for_the_previous_closed_day(
    tmp_path: Path,
    captured_urls: list[str],
) -> None:
    """month_trend must end on day-1; every other dated endpoint uses `day`."""
    day = date(2026, 9, 19)
    today = day.isoformat()
    yesterday = (day - timedelta(days=1)).isoformat()

    fetch_sycm_home_board.fetch_sycm_home_board(
        day=day, output_dir=tmp_path, cookie="t=session",
    )

    def url_for(fragment: str) -> str:
        return next(u for u in captured_urls if fragment in u)

    # Lagged: the 30-day rolling series ends on the previous closed day.
    assert _date_range_of(url_for("/portal/month/trend.json")) == f"{yesterday}|{yesterday}"

    # Not lagged: these all accept the requested business day.
    for fragment in (
        "/portal/board/grow/factor/overview.json",
        "/portal/board/grow/factor/trend.json",
        "/portal/month/overview.json",
        "/portal/level/info/v3.json",
    ):
        assert _date_range_of(url_for(fragment)) == f"{today}|{today}", fragment

    assert len(captured_urls) == 7
    assert not any("/domain/oneQuery.json" in url for url in captured_urls)


def test_repeated_days_always_produce_a_past_end_date(
    tmp_path: Path,
    captured_urls: list[str],
) -> None:
    """The requested day is never used as month_trend's own end date."""
    for offset in range(3):
        day = date(2026, 9, 15) + timedelta(days=offset)
        fetch_sycm_home_board.fetch_sycm_home_board(
            day=day, output_dir=tmp_path, cookie="t=session",
        )

    month_trend_urls = [u for u in captured_urls if "/portal/month/trend.json" in u]
    assert len(month_trend_urls) == 3
    for url, offset in zip(month_trend_urls, range(3)):
        requested = date(2026, 9, 15) + timedelta(days=offset)
        assert _date_range_of(url).split("|")[0] < requested.isoformat()
