import json
from datetime import date
from pathlib import Path

from scripts import fetch_sycm_member_analysis as member
from scripts import fetch_sycm_new_customer_discount as discount
from scripts import fetch_sycm_activity_calendar as calendar


class _HtmlResponse:
    status = 400

    def __enter__(self) -> "_HtmlResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return b"<html>error</html>"


def test_member_report_retries_non_json_in_existing_sycm_tab(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(member, "urlopen", lambda *_args, **_kwargs: _HtmlResponse())
    calls: list[tuple[int, str, str]] = []

    def browser_fetch(port: int, url: str, *, timeout: int, card_id: str) -> tuple[int, bytes]:
        calls.append((port, url, card_id))
        return 200, b'{"content":{"code":0,"data":{"totalMbrCnt":{"value":10}}}}'

    monkeypatch.setattr(member, "fetch_sycm_browser_json", browser_fetch)
    output = tmp_path / "member.json"
    result = member.fetch_sycm_member_analysis(
        day=date(2026, 9, 22), section="core", output=output,
        cookie="t=session", timeout=11, browser_port=9222,
    )

    assert result.ok
    assert calls[0][0] == 9222
    assert "/domain/oneQuery.json?" in calls[0][1]
    assert calls[0][2]
    assert json.loads(output.read_text(encoding="utf-8"))["content"]["code"] == 0


def test_new_customer_report_retries_non_json_in_existing_sycm_tab(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(discount, "urlopen", lambda *_args, **_kwargs: _HtmlResponse())
    calls: list[str] = []

    def browser_fetch(port: int, url: str, *, timeout: int) -> tuple[int, bytes]:
        assert port == 9222 and timeout == 11
        calls.append(url)
        return 200, b'{"code":0,"data":{"payAmt":{"value":10}}}'

    monkeypatch.setattr(discount, "fetch_sycm_browser_json", browser_fetch)
    output = tmp_path / "discount.json"
    result = discount.fetch_sycm_new_customer_discount(
        day=date(2026, 9, 22), output=output,
        cookie="t=session", timeout=11, browser_port=9222,
    )

    assert result.ok
    assert "/s_content/brandnewdiscount/overview.json?" in calls[0]
    assert json.loads(output.read_text(encoding="utf-8"))["code"] == 0


def test_activity_calendar_retries_html_in_existing_sycm_tab(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(calendar, "urlopen", lambda *_args, **_kwargs: _HtmlResponse())
    calls: list[tuple[int, str, str]] = []

    def browser_fetch(port: int, url: str, *, timeout: int, card_id: str) -> tuple[int, bytes]:
        calls.append((port, url, card_id))
        return 200, b'{"code":0,"data":[{"activityId":1,"actName":"Sale"}]}'

    monkeypatch.setattr(calendar, "fetch_sycm_browser_json", browser_fetch)
    output = tmp_path / "calendar.json"
    result = calendar.fetch_sycm_activity_calendar(
        day=date(2026, 1, 1), output=output, cookie="session=1",
        timeout=11, browser_port=9222,
    )

    assert result.ok
    assert calls[0][0] == 9222 and calls[0][2] == "am-activity-calendar"
    assert "/datawar/v4/activity/actList/getActivityCalendar.json?" in calls[0][1]
    assert len(json.loads(output.read_text(encoding="utf-8"))["data"]) == 1


def test_activity_calendar_invalid_response_does_not_replace_existing_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(calendar, "urlopen", lambda *_args, **_kwargs: _HtmlResponse())
    monkeypatch.setattr(calendar, "fetch_sycm_browser_json", lambda *_args, **_kwargs: (200, b"<html>login</html>"))
    output = tmp_path / "calendar.json"
    output.write_text('{"code":0,"data":[{"activityId":1}]}', encoding="utf-8")

    result = calendar.fetch_sycm_activity_calendar(
        day=date(2026, 1, 1), output=output, cookie="session=1", browser_port=9222,
    )

    assert not result.ok
    assert json.loads(output.read_text(encoding="utf-8"))["data"][0]["activityId"] == 1
