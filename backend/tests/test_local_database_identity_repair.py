import sqlite3

from app.core.local_database import LocalDatabase


def test_repairs_legacy_identity_foreign_key_targets(tmp_path) -> None:
    path = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("pragma foreign_keys = off")
        conn.execute('create table platforms ("平台ID" integer primary key)')
        conn.execute('create table "platforms__legacy_identity" ("平台ID" integer primary key)')
        conn.execute('insert into platforms values (1)')
        conn.execute('insert into "platforms__legacy_identity" values (1)')
        conn.execute(
            'create table stores ('
            '"店铺ID" integer primary key, '
            '"平台ID" integer references "platforms__legacy_identity"("平台ID"), '
            '"平台主体ID" text, "店铺名称" text, "状态" text, '
            '"首次发现时间" text, "更新时间" text)'
        )
        conn.execute(
            'insert into stores values (1, 1, "subject", "store", "active", "now", "now")'
        )
        conn.execute('create table "stores__legacy_identity" ("店铺ID" integer primary key)')
        conn.execute(
            'create table store_daily_member_analysis_overviews ('
            '"店铺ID" integer references "stores__legacy_identity"("店铺ID"), '
            '"业务日期" text primary key, "会员总数" text)'
        )
        conn.execute(
            'insert into store_daily_member_analysis_overviews values (1, "2026-08-01", "5")'
        )

        LocalDatabase._repair_identity_foreign_keys(conn)

        assert conn.execute('pragma foreign_key_list("stores")').fetchone()[2] == "platforms"
        assert (
            conn.execute(
                'pragma foreign_key_list("store_daily_member_analysis_overviews")'
            ).fetchone()[2]
            == "stores"
        )
        assert conn.execute(
            'select "会员总数" from store_daily_member_analysis_overviews'
        ).fetchone()[0] == "5"
        assert conn.execute(
            "select name from sqlite_master where type = 'table' and name = 'platforms__legacy_identity'"
        ).fetchone() is None
    finally:
        conn.close()


def test_repairs_identity_foreign_keys_for_access_and_brand_scope_tables(tmp_path) -> None:
    path = tmp_path / "scope-legacy.sqlite3"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("pragma foreign_keys = off")
        conn.execute('create table platforms ("平台ID" integer primary key)')
        conn.execute('insert into platforms values (1)')
        conn.execute(
            'create table stores ('
            '"店铺ID" integer primary key, "平台ID" integer references platforms("平台ID"), '
            '"平台主体ID" text, "店铺名称" text, "状态" text, "首次发现时间" text, "更新时间" text)'
        )
        conn.execute('insert into stores values (7, 1, "subject", "store", "active", "now", "now")')
        conn.execute(
            'create table access_user_store_scopes ('
            'user_id integer, store_id integer references "stores__foreign_key_repair"("店铺ID"), '
            'primary key (user_id, store_id))'
        )
        conn.execute('insert into access_user_store_scopes values (1, 7)')
        conn.execute(
            'create table brand_store_scopes ('
            '"品牌ID" text, "店铺ID" integer references "stores__foreign_key_repair"("店铺ID"), '
            'primary key ("品牌ID", "店铺ID"))'
        )
        conn.execute('insert into brand_store_scopes values ("brand", 7)')

        LocalDatabase._repair_identity_foreign_keys(conn)

        for table in ("access_user_store_scopes", "brand_store_scopes"):
            assert conn.execute(f'pragma foreign_key_list("{table}")').fetchone()[2] == "stores"
        assert conn.execute("select store_id from access_user_store_scopes").fetchone()[0] == 7
        assert conn.execute('select "店铺ID" from brand_store_scopes').fetchone()[0] == 7
    finally:
        conn.close()
