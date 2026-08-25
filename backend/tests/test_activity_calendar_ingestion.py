from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.local_database import ACTIVITY_CALENDAR_COLUMNS  # noqa: E402
from app.warehouse.store import WarehouseStore  # noqa: E402
from app.warehouse.sycm_activity_calendar import parse_payload  # noqa: E402
from app.modules.collection.registry import COLLECTION_DATASET_BY_KEY  # noqa: E402


QUERY_DAY = date(2026, 1, 1)


def activity_payload() -> dict[str, object]:
    return {
        "traceId": "215045a617853983552801397e0c5d",
        "code": 0,
        "message": "操作成功",
        "data": [
            {
                "activityId": 139127570,
                "actName": "年货开门红预售",
                "actStatus": "3",
                "activityType": 1,
                "activityStart": 1767628800000,
                "activityEnd": 1767887999000,
            },
            {
                "activityId": 140093464,
                "actName": "2026年天猫38开门红&amp;38焕新周",
                "actStatus": "3",
                "activityType": 1,
                "activityStart": 1771862400000,
                "activityEnd": 1773071999000,
            },
        ],
    }


class ActivityCalendarParserTests(unittest.TestCase):
    def test_parser_uses_real_activity_time_fields(self) -> None:
        parsed = parse_payload(activity_payload(), query_date=QUERY_DAY)

        self.assertEqual(len(parsed.events), 2)
        self.assertEqual(
            parsed.covered_days,
            (date(2026, 1, 6), date(2026, 2, 24)),
        )

        first = parsed.events[0]
        self.assertEqual(first.business_day, date(2026, 1, 6))
        self.assertEqual(first.activity_start_time, "2026-01-06 00:00:00")
        self.assertEqual(first.activity_end_time, "2026-01-08 23:59:59")

        second = parsed.events[1]
        self.assertEqual(second.activity_name, "2026年天猫38开门红&38焕新周")
        self.assertEqual(second.business_day, date(2026, 2, 24))

    def test_activity_calendar_is_registered_as_a_coverage_snapshot(self) -> None:
        dataset = COLLECTION_DATASET_BY_KEY["sycm_activity_calendar"]
        self.assertEqual(dataset.tables, ("store_activity_calendar_events",))
        self.assertEqual(dataset.task_types, ("sycm_activity_calendar",))
        self.assertTrue(dataset.allow_no_data)
        self.assertEqual(dataset.collection_mode, "coverage_snapshot")


class ActivityCalendarIngestionTests(unittest.TestCase):
    def test_ingestion_keeps_clean_business_table_columns(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "warehouse.sqlite3"
            response_path = root / "activity-calendar.json"
            response_path.write_text(
                json.dumps(activity_payload(), ensure_ascii=False),
                encoding="utf-8",
            )

            store = WarehouseStore(database_path)
            result = store.ingest_sycm_activity_calendar(
                source_path=response_path,
                business_day=QUERY_DAY,
                store_name="碧芭宝贝旗舰店",
            )

            self.assertEqual(result.metric_count, 2)
            self.assertEqual(result.store.store_id, 1)

            with closing(sqlite3.connect(database_path)) as conn:
                columns = {
                    row[1]
                    for row in conn.execute(
                        'pragma table_info("store_activity_calendar_events")'
                    )
                }
                self.assertEqual(columns, set(ACTIVITY_CALENDAR_COLUMNS))

                rows = conn.execute(
                    """
                    select "业务日期", "活动名称", "活动开始时间", "活动结束时间"
                    from store_activity_calendar_events
                    order by "活动开始时间"
                    """
                ).fetchall()
                self.assertEqual(
                    rows,
                    [
                        (
                            "2026-01-06",
                            "年货开门红预售",
                            "2026-01-06 00:00:00",
                            "2026-01-08 23:59:59",
                        ),
                        (
                            "2026-02-24",
                            "2026年天猫38开门红&38焕新周",
                            "2026-02-24 00:00:00",
                            "2026-03-09 23:59:59",
                        ),
                    ],
                )

                raw_table = conn.execute(
                    """
                    select 1
                    from sqlite_master
                    where type = 'table' and name = 'raw_response_artifacts'
                    """
                ).fetchone()
                self.assertIsNone(raw_table)

    def test_ingestion_replaces_the_entire_store_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "warehouse.sqlite3"
            first_path = root / "first.json"
            second_path = root / "second.json"
            first_path.write_text(
                json.dumps(activity_payload(), ensure_ascii=False),
                encoding="utf-8",
            )
            second_payload = activity_payload()
            second_payload["data"] = [activity_payload()["data"][1]]
            second_path.write_text(
                json.dumps(second_payload, ensure_ascii=False),
                encoding="utf-8",
            )

            store = WarehouseStore(database_path)
            store.ingest_sycm_activity_calendar(
                source_path=first_path,
                business_day=QUERY_DAY,
                store_name="碧芭宝贝旗舰店",
            )
            store.ingest_sycm_activity_calendar(
                source_path=second_path,
                business_day=QUERY_DAY,
                store_name="碧芭宝贝旗舰店",
            )

            with closing(sqlite3.connect(database_path)) as conn:
                rows = conn.execute(
                    'select "活动名称" from store_activity_calendar_events order by "活动名称"'
                ).fetchall()
                self.assertEqual(rows, [("2026年天猫38开门红&38焕新周",)])

    def test_successful_empty_response_clears_the_store_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "warehouse.sqlite3"
            first_path = root / "first.json"
            empty_path = root / "empty.json"
            first_path.write_text(
                json.dumps(activity_payload(), ensure_ascii=False),
                encoding="utf-8",
            )
            empty_path.write_text(
                json.dumps({"code": 0, "message": "操作成功", "data": []}),
                encoding="utf-8",
            )

            store = WarehouseStore(database_path)
            store.ingest_sycm_activity_calendar(
                source_path=first_path,
                business_day=QUERY_DAY,
                store_name="碧芭宝贝旗舰店",
            )
            result = store.ingest_sycm_activity_calendar(
                source_path=empty_path,
                business_day=QUERY_DAY,
                store_name="碧芭宝贝旗舰店",
            )

            self.assertEqual(result.metric_count, 0)
            with closing(sqlite3.connect(database_path)) as conn:
                self.assertEqual(
                    conn.execute("select count(*) from store_activity_calendar_events").fetchone()[0],
                    0,
                )

    def test_failed_response_keeps_the_previous_store_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "warehouse.sqlite3"
            first_path = root / "first.json"
            failed_path = root / "failed.json"
            first_path.write_text(
                json.dumps(activity_payload(), ensure_ascii=False),
                encoding="utf-8",
            )
            failed_path.write_text(
                json.dumps({"code": 500, "message": "request failed", "data": []}),
                encoding="utf-8",
            )

            store = WarehouseStore(database_path)
            store.ingest_sycm_activity_calendar(
                source_path=first_path,
                business_day=QUERY_DAY,
                store_name="碧芭宝贝旗舰店",
            )
            with self.assertRaises(ValueError):
                store.ingest_sycm_activity_calendar(
                    source_path=failed_path,
                    business_day=QUERY_DAY,
                    store_name="碧芭宝贝旗舰店",
                )

            with closing(sqlite3.connect(database_path)) as conn:
                self.assertEqual(
                    conn.execute("select count(*) from store_activity_calendar_events").fetchone()[0],
                    2,
                )


if __name__ == "__main__":
    unittest.main()
