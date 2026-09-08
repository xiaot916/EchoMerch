from __future__ import annotations

from argparse import Namespace
from datetime import date
from pathlib import Path

from scripts import backfill_sycm_item_rankings


def test_item_ranking_retries_qps_limit_before_failing(monkeypatch, tmp_path: Path) -> None:
    attempts: list[int] = []
    pauses: list[float] = []

    def fake_fetch(**_kwargs):
        attempts.append(1)
        return (200, 1800, "QPS exceeded", 10) if len(attempts) == 1 else (200, 0, "ok", 20)

    monkeypatch.setattr(backfill_sycm_item_rankings, "fetch_item_ranking", fake_fetch)
    monkeypatch.setattr(backfill_sycm_item_rankings.time, "sleep", pauses.append)
    monkeypatch.setattr(backfill_sycm_item_rankings.random, "uniform", lambda *_args: 0.0)
    args = Namespace(token="", page_size=20, timeout=30, qps_retries=3, qps_backoff_seconds=3.0)

    result = backfill_sycm_item_rankings._fetch_page_with_qps_retry(
        day=date(2026, 9, 7),
        args=args,
        cookie="session",
        page=7,
        output=tmp_path / "page.json",
    )

    assert result[1] == 0
    assert len(attempts) == 2
    assert pauses == [3.0]
