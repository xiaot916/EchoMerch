import sqlite3
from pathlib import Path

import pytest

from app.core.local_database import LocalDatabase
from app.modules.imports.crawl_run_store import CrawlRunStore


def test_initialize_schema_uses_version_gate_after_process_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = (tmp_path / "schema-version.sqlite3").resolve()
    calls = 0
    original = LocalDatabase._ensure_schema

    def counted(self: LocalDatabase, conn: sqlite3.Connection) -> None:
        nonlocal calls
        calls += 1
        original(self, conn)

    monkeypatch.setattr(LocalDatabase, "_ensure_schema", counted)
    LocalDatabase(database_path).initialize_schema()
    assert calls == 1

    # Simulate a fresh process: the on-disk schema version is authoritative,
    # while the in-process path cache is deliberately cleared.
    LocalDatabase._initialized_paths.discard(database_path)
    LocalDatabase(database_path).initialize_schema()
    assert calls == 1

    LocalDatabase(database_path).initialize_schema(force=True)
    assert calls == 2


def test_recluster_daily_fact_table_restores_chronological_row_order(tmp_path: Path) -> None:
    database_path = tmp_path / "warehouse.sqlite3"
    database = LocalDatabase(database_path)
    database.initialize_schema()
    CrawlRunStore(database_path).ensure_store_reference(
        store_id=1,
        store_name="Store 1",
        platform_store_id="store-1",
    )

    with sqlite3.connect(database_path) as conn:
        conn.execute(
            'insert into store_daily_overviews ("店铺ID", "业务日期", "支付金额") '
            "values (?, ?, ?)",
            (1, "2026-08-03", "300"),
        )
        conn.execute(
            'insert into store_daily_overviews ("店铺ID", "业务日期", "支付金额") '
            "values (?, ?, ?)",
            (1, "2026-08-01", "100"),
        )

    assert database.recluster_daily_fact_tables(["store_daily_overviews"]) == {
        "store_daily_overviews": 2
    }

    with sqlite3.connect(database_path) as conn:
        rows = conn.execute(
            'select "业务日期", "支付金额" from store_daily_overviews order by rowid'
        ).fetchall()
        index = conn.execute(
            "select 1 from sqlite_master where type = 'index' "
            "and name = 'idx_store_daily_overviews_store_day'"
        ).fetchone()

    assert rows == [("2026-08-01", "100"), ("2026-08-03", "300")]
    assert index is not None
