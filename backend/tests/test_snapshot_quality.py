from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app.modules.collection.coverage import resolve_dataset_day
from app.modules.collection.registry import COLLECTION_DATASET_BY_KEY
from app.modules.collection.schemas import DatasetTableCoverage
from app.modules.collection.service import CollectionService
from app.modules.collection.snapshot_quality import current_price_snapshot_error


DAY = date(2026, 9, 6)


def _write_snapshot(database_path: Path, *, second_page: dict | None) -> None:
    source = database_path.parent / "raw_responses" / "taobao_operational_snapshots" / DAY.isoformat()
    source.mkdir(parents=True, exist_ok=True)
    pages = [{"ret": ["SUCCESS::调用成功"], "data": {"model": {"items": [{"itemId": "1"}], "totalCount": 2}}}]
    if second_page is not None:
        pages.append(second_page)
    (source / "current_prices.json").write_text(json.dumps({"pages": pages}), encoding="utf-8")


def test_current_price_quality_requires_all_advertised_pages(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.sqlite3"
    _write_snapshot(database_path, second_page=None)
    assert "1/2" in (current_price_snapshot_error(database_path, DAY) or "")
    _write_snapshot(database_path, second_page={"ret": ["BUSINESS_EXCEPTION::ic服务异常"], "data": {}})
    assert "平台返回异常" in (current_price_snapshot_error(database_path, DAY) or "")
    _write_snapshot(database_path, second_page={"ret": ["SUCCESS::调用成功"], "data": {"model": {"items": [{"itemId": "2"}]}}})
    assert current_price_snapshot_error(database_path, DAY) is None


def test_snapshot_coverage_does_not_claim_truncated_page_is_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "warehouse.sqlite3"
    service = CollectionService(database_path)
    dataset = COLLECTION_DATASET_BY_KEY["taobao_operational_snapshots"]
    _write_snapshot(database_path, second_page=None)
    monkeypatch.setattr(service, "_table_coverage_for_dataset", lambda _conn, _dataset, table, _day: DatasetTableCoverage(
        table=table, present=True, row_count=1, raw_row_count=1, latest_date=DAY.isoformat(),
    ))
    monkeypatch.setattr(service, "_latest_task_attempts", lambda *_args: [{
        "task_type": "taobao_operational_snapshots", "day_status": "ingested",
        "run_status": "completed", "started_at": "2026-09-06T09:00:00", "error_message": None,
    }])
    with service.database.connect() as conn:
        visible = service._dataset_coverage(conn, dataset, DAY)
        shared = resolve_dataset_day(conn, dataset, business_day=DAY)
    assert visible.status == "partial"
    assert "1/2" in (visible.error_message or "")
    assert shared.status == "failed"  # No fact rows were inserted into the fixture.
