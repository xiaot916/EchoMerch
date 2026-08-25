from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

import pytest

import app.modules.reviews.service as review_service_module
from app.integrations.tmall_session import RuntimeSession, RuntimeSessionUnavailable
from app.modules.reviews.service import ReviewCollectionError, ReviewService


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
    calls: list[str] = []

    def fake_resolve_runtime_session(**kwargs: object) -> RuntimeSession:
        calls.append(str(kwargs["source"]))
        return RuntimeSession(cookie_header="_m_h5_tk=token; t=session", source=str(kwargs["source"]))

    monkeypatch.setattr(review_service_module, "resolve_runtime_session", fake_resolve_runtime_session)

    session = ReviewService(tmp_path / "reviews.sqlite3")._resolve_collection_session(home_url="https://example.test")

    assert session.source == "drissionpage"
    assert calls == ["drissionpage"]


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


def test_review_collection_reports_both_missing_session_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_SYCM_COOKIE", raising=False)
    monkeypatch.setattr(review_service_module, "settings", _settings())

    def unavailable(**kwargs: object) -> RuntimeSession:
        raise RuntimeSessionUnavailable("No Chrome remote-debugging session is listening")

    monkeypatch.setattr(review_service_module, "resolve_runtime_session", unavailable)

    with pytest.raises(ReviewCollectionError, match="TEST_SYCM_COOKIE.*浏览器不可用"):
        ReviewService(tmp_path / "reviews.sqlite3")._resolve_collection_session(home_url="https://example.test")
