from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from app.core.local_database import LocalDatabase


TABLES = (
    "brands",
    "brand_asset_daily_overviews",
    "brand_asset_daily_stages",
    "brand_asset_daily_dimensions",
    "brand_asset_daily_metrics",
)


def merge(source: Path, target: Path) -> dict[str, int]:
    LocalDatabase(target).initialize_schema()
    with sqlite3.connect(target) as conn:
        conn.execute("pragma foreign_keys=on")
        conn.execute("attach database ? as source_db", (str(source),))
        try:
            conn.execute("begin immediate")
            counts: dict[str, int] = {}
            conn.execute(
                'insert into "brands" select * from source_db."brands" '
                'where "品牌ID" not in (select "品牌ID" from "brands")'
            )
            conn.execute(
                'insert into "brands" select s.* from source_db."brands" s '
                'where "品牌ID" in (select "品牌ID" from "brands") '
                'and not exists (select 1 from "brands" t where t."品牌ID"=s."品牌ID" and t."品牌主体ID"=s."品牌主体ID" and t."品牌名称"=s."品牌名称")'
            )
            for table in TABLES[1:]:
                source_exists = conn.execute(
                    "select 1 from source_db.sqlite_master where type='table' and name=?",
                    (table,),
                ).fetchone()
                target_exists = conn.execute(
                    "select 1 from main.sqlite_master where type='table' and name=?",
                    (table,),
                ).fetchone()
                if not source_exists or not target_exists:
                    counts[table] = 0
                    continue
                conn.execute(f'delete from "{table}" where "品牌ID" in (select "品牌ID" from source_db."{table}")')
                conn.execute(f'insert into "{table}" select * from source_db."{table}"')
                counts[table] = int(conn.execute(f'select count(*) from "{table}"').fetchone()[0])
            counts["brands"] = int(conn.execute('select count(*) from "brands"').fetchone()[0])
            conn.commit()
            return counts
        finally:
            conn.execute("detach database source_db")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    print(merge(args.source.resolve(), args.target.resolve()))
