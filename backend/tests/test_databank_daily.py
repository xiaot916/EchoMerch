import json
from datetime import date
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.local_database import LocalDatabase
from app.warehouse.databank import ingest_snapshot, parse_payload
from scripts import fetch_databank_daily
from scripts.fetch_databank_daily import _homepage_query


def _payload() -> dict[str, object]:
    return {
        "core": {"customerVolume": {"value": 100}, "deepenRatio": {"value": 0.1}, "aiPlRate": {"value": 2}, "brandPayAmt": {"value": 300}, "mbrPayAmt": {"value": 20}, "customerPropertyPred": {"value": 1000}},
        "volume": {"awarenessVolumePer": {"value": 0.6}, "purchaseVolumePer": {"value": 0.4}},
        "pay": {"brandPayUv": {"value": 5}},
        "crowd": {
            "self": [
                {"aiplStatus": "a", "customerVolume": {"value": 60}, "viewUv": {"value": 12}},
                {"aiplStatus": "p", "customerVolume": {"value": 40}},
            ],
            "compare": [{"aiplStatus": "a", "customerVolume": {"value": 600}}],
        },
        "category": [{"cateName": "cat", "brandPayAmt": {"value": 300}, "brandPayUv": {"value": 5}, "brandCustomerValue": {"value": 60}}],
    }


def test_databank_parser_maps_daily_core_stages_and_dimensions() -> None:
    parsed = parse_payload(_payload(), brand_id="b", business_day=date(2026, 8, 20))
    assert parsed["overview"][0][3:8] == ("100", "0.1", "2", "300", "5")
    assert [row[2] for row in parsed["stages"]] == ["a", "p"]
    assert parsed["dimensions"][0][4] == "cat"
    assert {row[4] for row in parsed["metrics"]} >= {"认知人群占比", "购买人群占比", "浏览人数"}
    assert any(row[2:6] == ("crowd_compare", "a", "消费者数", "600") for row in parsed["metrics"])


def test_databank_parser_drops_zero_only_days() -> None:
    empty = {
        "core": {"customerVolume": {"value": 0}, "brandPayAmt": {"value": 0}, "purchaseVolume": {"value": 0}, "interestVolume": {"value": 0}, "loyalVolume": {"value": 0}},
        "pay": {"brandPayUv": {"value": 0}},
        "crowd": {"self": [], "compare": []},
    }
    assert parse_payload(empty, brand_id="b", business_day=date(2025, 1, 1)) == {
        "overview": [],
        "stages": [],
        "dimensions": [],
        "metrics": [],
    }


def test_databank_parser_maps_new_homepage_metrics_for_snapshot_day_only() -> None:
    payload = _payload()
    payload.update(
        {
            "homepage_panel": {
                "activeCnt": 100,
                "aiplCnt": 80,
                "list": [
                    {"ds": "20260819", "activeCnt": 90},
                    {"ds": "20260820", "activeCnt": 100},
                ],
            },
            "homepage_growth_strategy": {"touchUV": 200, "touchUVMedian": 150},
            "homepage_panel_detail_aipl": {
                "aiplTaoRateIndex": 1.2,
                "list": [{"ds": "20260820", "add": 8, "deep": 3}],
            },
            "homepage_growth_map_ctr": [
                {"ds": "20260819", "brandValue": 0.08, "medianValue": 0.05},
                {"ds": "20260820", "brandValue": 0.09, "medianValue": 0.06},
            ],
        }
    )
    parsed = parse_payload(payload, brand_id="b", business_day=date(2026, 8, 20))
    metrics = parsed["metrics"]
    assert any(row[2:6] == ("homepage_panel", "activeCnt", "活跃人数", "100") for row in metrics)
    assert any(row[2:6] == ("homepage_growth_strategy", "touchUV", "触达人数", "200") for row in metrics)
    assert any(row[2:6] == ("homepage_detail_trend", "aipl.add", "经营面板-AIPL.add", "8") for row in metrics)
    assert any(row[2:6] == ("homepage_growth_map", "ctr.brandValue", "ctr.品牌值", "0.09") for row in metrics)
    assert not any(row[5] in {"90", "0.08", "0.05"} and row[2].startswith("homepage_") for row in metrics)


def test_new_homepage_query_uses_daily_contract() -> None:
    query = parse_qs(urlparse(_homepage_query("/homepage/queryPanel", date(2026, 8, 20), brand_id="b")).query)
    assert query["path"] == ["/homepage/queryPanel"]
    assert query["brandId"] == ["b"]
    assert query["dateType"] == ["d"]
    assert query["ds"] == ["20260820"]
    assert query["xcatId"] == ["-999"]


def test_databank_persists_platform_error_responses_before_failing(
    monkeypatch, tmp_path: Path
) -> None:
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {"data": None, "errCode": 477012030108, "errMsg": "param illegal", "codeClass": "CLIENT_ERROR"}
            ).encode("utf-8")

    monkeypatch.setattr(fetch_databank_daily, "urlopen", lambda request, timeout: Response())
    output = tmp_path / "databank-error.json"

    with pytest.raises(RuntimeError, match="param illegal"):
        fetch_databank_daily.fetch_databank_daily(
            business_day=date(2026, 9, 1),
            output=output,
            cookie="t=runtime-session",
            csrf_token="csrf",
        )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["core"]["errCode"] == 477012030108
    assert saved["homepage_panel"]["errMsg"] == "param illegal"


def test_databank_ingest_is_idempotent(tmp_path: Path) -> None:
    database_path = tmp_path / "databank.sqlite3"
    LocalDatabase(database_path).initialize_schema()
    with sqlite3.connect(database_path) as conn:
        conn.execute('insert into brands ("品牌ID", "品牌主体ID", "品牌名称", "品牌状态", "创建时间", "更新时间") values (?, ?, ?, ?, ?, ?)', ("b", "b", "品牌", "active", "now", "now"))
    first = ingest_snapshot(database_path, brand_id="b", business_day=date(2026, 8, 20), payload=_payload())
    second = ingest_snapshot(database_path, brand_id="b", business_day=date(2026, 8, 20), payload=_payload())
    assert first == second == {"overview": 1, "stages": 2, "dimensions": 1, "metrics": 6}
    with sqlite3.connect(database_path) as conn:
        assert conn.execute('select count(*) from brand_asset_daily_overviews').fetchone()[0] == 1
        assert conn.execute('select count(*) from brand_asset_daily_stages').fetchone()[0] == 2
        assert conn.execute('select count(*) from brand_asset_daily_metrics').fetchone()[0] == 6
