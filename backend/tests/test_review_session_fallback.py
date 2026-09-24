from __future__ import annotations

import json
from io import BytesIO
from types import SimpleNamespace
from pathlib import Path

import pytest

import app.modules.reviews.service as review_service_module
from app.integrations.tmall_session import RuntimeSession, RuntimeSessionUnavailable
from app.modules.reviews.service import API_URL, ASK_API_URL, ReviewCollectionError, ReviewService


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        tmall_session_source="env",
        tmall_cookie_env="TEST_SYCM_COOKIE",
        tmall_browser_port=9222,
    )


def test_review_collection_falls_back_to_logged_in_browser_when_env_cookie_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_SYCM_COOKIE", raising=False)
    monkeypatch.setattr(review_service_module, "settings", _settings())
    calls: list[tuple[int, tuple[str, ...]]] = []

    def scoped_cookies(port: int, urls: tuple[str, ...], *, expected_hosts: tuple[str, ...]) -> dict[str, str]:
        calls.append((port, expected_hosts))
        assert urls == (API_URL,)
        return {API_URL: "_m_h5_tk=token; t=session"}

    monkeypatch.setattr(review_service_module, "browser_cookie_headers_for_urls", scoped_cookies)
    monkeypatch.setattr(review_service_module, "resolve_runtime_session", lambda **_kwargs: pytest.fail("must not read all-domain cookies"))

    session = ReviewService(tmp_path / "reviews.sqlite3")._resolve_collection_session(home_url="https://example.test")

    assert session.source == "drissionpage"
    assert session.cookie_header == "_m_h5_tk=token; t=session"
    assert calls == [(9222, ("myseller.taobao.com",))]


def test_review_collection_prefers_configured_env_cookie(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_SYCM_COOKIE", "_m_h5_tk=token; t=session")
    monkeypatch.setattr(review_service_module, "settings", _settings())
    calls: list[str] = []

    def fake_resolve_runtime_session(**kwargs: object) -> RuntimeSession:
        calls.append(str(kwargs["source"]))
        return RuntimeSession(cookie_header="_m_h5_tk=token; t=session", source=str(kwargs["source"]))

    monkeypatch.setattr(review_service_module, "resolve_runtime_session", fake_resolve_runtime_session)

    session = ReviewService(tmp_path / "reviews.sqlite3")._resolve_collection_session(home_url="https://example.test")

    assert session.source == "env"
    assert calls == ["env"]


def test_ask_collection_scopes_cookies_to_its_own_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_SYCM_COOKIE", raising=False)
    monkeypatch.setattr(review_service_module, "settings", _settings())

    def scoped_cookies(_port: int, urls: tuple[str, ...], *, expected_hosts: tuple[str, ...]) -> dict[str, str]:
        assert urls == (ASK_API_URL,)
        assert expected_hosts == ("myseller.taobao.com",)
        return {ASK_API_URL: "_m_h5_tk=token; t=session"}

    monkeypatch.setattr(review_service_module, "browser_cookie_headers_for_urls", scoped_cookies)
    session = ReviewService(tmp_path / "reviews.sqlite3")._resolve_collection_session(
        home_url="https://myseller.taobao.com/home.htm/comment-manage/ask-all",
        request_url=ASK_API_URL,
    )
    assert session.cookie_header == "_m_h5_tk=token; t=session"


def test_review_collection_reports_both_missing_session_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_SYCM_COOKIE", raising=False)
    monkeypatch.setattr(review_service_module, "settings", _settings())

    def unavailable(*_args: object, **_kwargs: object) -> RuntimeSession:
        raise RuntimeSessionUnavailable("No Chrome remote-debugging session is listening")

    monkeypatch.setattr(review_service_module, "browser_cookie_headers_for_urls", unavailable)

    with pytest.raises(ReviewCollectionError, match="TEST_SYCM_COOKIE.*浏览器不可用"):
        ReviewService(tmp_path / "reviews.sqlite3")._resolve_collection_session(home_url="https://example.test")


@pytest.mark.parametrize("method", ["_request_ask_page", "_request_page"])
def test_mtop_431_reports_cookie_recovery_without_leaking_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, method: str,
) -> None:
    from urllib.error import HTTPError

    def reject(_request: object, *, timeout: int) -> None:
        assert timeout == 30
        raise HTTPError("https://h5api.m.taobao.com/", 431, "Request Header Fields Too Large", None, None)

    monkeypatch.setattr(review_service_module, "urlopen", reject)
    service = ReviewService(tmp_path / "reviews.sqlite3")
    with pytest.raises(ReviewCollectionError, match="Cookie 请求头.*采集浏览器") as error:
        getattr(service, method)({"_m_h5_tk": "private-token", "t": "private-session"}, "private-token", 1)
    assert "private-token" not in str(error.value)


@pytest.mark.parametrize("method", ["_request_ask_page", "_request_page"])
def test_mtop_empty_page_requires_an_explicit_items_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, method: str,
) -> None:
    payload: dict[str, object] = {"ret": ["SUCCESS::调用成功"], "data": {"data": {"dataSource": []}}}

    def respond(*_args: object, **_kwargs: object) -> BytesIO:
        return BytesIO(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(review_service_module, "urlopen", respond)
    service = ReviewService(tmp_path / "reviews.sqlite3")
    request_page = getattr(service, method)
    assert request_page({"_m_h5_tk": "token", "t": "session"}, "token", 1) == []

    payload["data"] = {"data": {"unexpected": []}}
    with pytest.raises(ReviewCollectionError, match="未返回.*列表"):
        request_page({"_m_h5_tk": "token", "t": "session"}, "token", 1)
