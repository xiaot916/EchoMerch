import json
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scripts import fetch_alimama_rtb_report


class _Response:
    status = 200

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"code":0,"data":{"list":[],"count":0}}'


def test_alimama_report_builds_post_body_and_query(monkeypatch, tmp_path: Path) -> None:
    captured = {}

    def fake_urlopen(request, timeout: int) -> _Response:
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(fetch_alimama_rtb_report, "urlopen", fake_urlopen)
    output = tmp_path / "rtb.json"
    status, code, message, size = fetch_alimama_rtb_report.fetch_alimama_report(
        start_day=date(2026, 8, 11),
        end_day=date(2026, 8, 17),
        output=output,
        cookie="t=runtime-session",
        csrf_id="csrf-value",
        login_point_id="login-point",
        offset=60,
        page_size=20,
        timeout=17,
    )

    request = captured["request"]
    body = json.loads(request.data.decode("utf-8"))
    query = parse_qs(urlparse(request.full_url).query)
    assert status == 200
    assert code == 0
    assert message is None
    assert size == output.stat().st_size
    assert request.method == "POST"
    assert query == {"csrfId": ["csrf-value"], "bizCode": ["universalBP"]}
    assert body["startTime"] == "2026-08-11"
    assert body["endTime"] == "2026-08-17"
    assert body["offset"] == 60
    assert body["bizCodeIn"] == ["onebpSearch"]
    assert body["queryFieldIn"] == list(fetch_alimama_rtb_report.ADGROUP_REPORT_FIELDS)
    assert body["csrfId"] == "csrf-value"
    assert request.get_header("Cookie") == "t=runtime-session"
    assert captured["timeout"] == 17


def test_bidword_report_home_matches_the_keyword_report_route() -> None:
    report_home = fetch_alimama_rtb_report.alimama_report_home("bidword")

    assert "#!/report/bidword" in report_home
    assert "rptType=bidword" in report_home


def test_adgroup_and_bidword_configs_match_the_daily_reports(
    monkeypatch, tmp_path: Path
) -> None:
    bodies = []

    def fake_urlopen(request, timeout: int) -> _Response:
        bodies.append(json.loads(request.data.decode("utf-8")))
        return _Response()

    monkeypatch.setattr(fetch_alimama_rtb_report, "urlopen", fake_urlopen)
    for report_type in ("adgroup", "bidword"):
        config = fetch_alimama_rtb_report.REPORT_CONFIG[report_type]
        fetch_alimama_rtb_report.fetch_alimama_report(
            start_day=date(2026, 8, 19),
            end_day=date(2026, 8, 19),
            output=tmp_path / f"{report_type}.json",
            cookie="t=runtime-session",
            csrf_id="csrf-value",
            login_point_id="login-point",
            rpt_type=report_type,
            query_fields=config["fields"],
            query_domains=config["domains"],
            biz_codes=config["biz_codes"],
            by_page_without_count=config["by_page_without_count"],
            extra_body=config.get("extra_body"),
            offset=100 if report_type == "bidword" else 0,
            page_size=100,
        )

    adgroup_body, bidword_body = bodies
    assert adgroup_body["byPageWithoutCount"] is False
    assert adgroup_body["queryDomains"] == ["adgroup", "date", "campaign"]
    assert bidword_body["byPageWithoutCount"] is True
    assert bidword_body["isKeyWordNotContainChase"] == "true"
    assert bidword_body["offset"] == 100


def test_campaign_report_does_not_limit_results_to_search_promotion(
    monkeypatch, tmp_path: Path
) -> None:
    captured = {}

    def fake_urlopen(request, timeout: int) -> _Response:
        captured["request"] = request
        return _Response()

    monkeypatch.setattr(fetch_alimama_rtb_report, "urlopen", fake_urlopen)
    config = fetch_alimama_rtb_report.REPORT_CONFIG["campaign"]
    fetch_alimama_rtb_report.fetch_alimama_report(
        start_day=date(2026, 8, 19),
        end_day=date(2026, 8, 19),
        output=tmp_path / "campaign.json",
        cookie="t=runtime-session",
        csrf_id="csrf-value",
        login_point_id="login-point",
        rpt_type="campaign",
        query_fields=config["fields"],
        query_domains=config["domains"],
        biz_codes=config["biz_codes"],
        page_size=100,
    )

    body = json.loads(captured["request"].data.decode("utf-8"))
    assert body["queryDomains"] == ["campaign"]
    assert body["pageSize"] == 100
    assert "bizCodeIn" not in body


def test_item_and_content_reports_send_their_subject_filters(
    monkeypatch, tmp_path: Path
) -> None:
    bodies = []

    def fake_urlopen(request, timeout: int) -> _Response:
        bodies.append(json.loads(request.data.decode("utf-8")))
        return _Response()

    monkeypatch.setattr(fetch_alimama_rtb_report, "urlopen", fake_urlopen)
    for report_type in ("item_promotion", "other_promotion"):
        config = fetch_alimama_rtb_report.REPORT_CONFIG[report_type]
        fetch_alimama_rtb_report.fetch_alimama_report(
            start_day=date(2026, 8, 19),
            end_day=date(2026, 8, 19),
            output=tmp_path / f"{report_type}.json",
            cookie="t=runtime-session",
            csrf_id="csrf-value",
            login_point_id="login-point",
            rpt_type=report_type,
            query_fields=config["fields"],
            query_domains=config["domains"],
            biz_codes=config["biz_codes"],
            extra_body=config["extra_body"],
            offset=100,
            page_size=100,
        )

    item_body, content_body = bodies
    assert item_body["subPromotionTypes"] == ["ITEM"]
    assert item_body["offset"] == 100
    assert content_body["strategySubPromotionTypeNotIn"] == ["11"]
    assert content_body["needCountAccelerate"] is False
    assert content_body["offset"] == 100
