"""Tmall Brand Data Bank session context (databank.tmall.com)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.integrations.session.core import (
    DEFAULT_DEBUG_PORT,
    DEFAULT_BROWSER_LOGIN_TIMEOUT,
    RuntimeSession,
    RuntimeSessionUnavailable,
    _cookie_count,
    _cookie_value,
    cookie_header_from_mapping,
    resolve_runtime_session,
)

DEFAULT_DATABANK_HOME_URL = "https://databank.tmall.com/"


@dataclass(frozen=True)
class DatabankRuntimeContext:
    """Runtime-only values needed by the Tmall Brand Data Bank APIs."""

    session: RuntimeSession
    csrf_token: str = field(repr=False)


def resolve_databank_runtime_context(
    *,
    source: str,
    cookie_env: str = "DATABANK_COOKIE",
    csrf_token: str = "",
    csrf_env: str = "DATABANK_CSRF_TOKEN",
    browser_port: int = DEFAULT_DEBUG_PORT,
    home_url: str = DEFAULT_DATABANK_HOME_URL,
) -> DatabankRuntimeContext:
    """Resolve Brand Data Bank cookies and its short-lived CSRF token."""
    if source == "drissionpage":
        return DrissionPageDatabankSessionProvider(
            browser_port, home_url=home_url, timeout=DEFAULT_BROWSER_LOGIN_TIMEOUT,
        ).read_context(csrf_token=csrf_token)

    session = resolve_runtime_session(
        source=source, cookie_env=cookie_env, browser_port=browser_port, home_url=home_url,
    )
    csrf_token = csrf_token or os.getenv(csrf_env, "").strip() or _cookie_value(
        session.cookie_header, "_tb_token_"
    )
    if not csrf_token:
        raise RuntimeSessionUnavailable(
            f"--csrf-token/{csrf_env} or _tb_token_ cookie is required for the Brand Data Bank."
        )
    return DatabankRuntimeContext(session=session, csrf_token=csrf_token)


class DrissionPageDatabankSessionProvider:
    """Open Brand Data Bank and resolve its runtime CSRF material."""

    def __init__(self, browser_port: int, home_url: str, timeout: float) -> None:
        if not 1 <= browser_port <= 65535:
            raise ValueError("--browser-port must be between 1 and 65535.")
        if timeout <= 0:
            raise ValueError("Brand Data Bank login timeout must be positive.")
        self.browser_port = browser_port
        self.home_url = home_url
        self.timeout = timeout

    def read_context(self, *, csrf_token: str = "") -> DatabankRuntimeContext:
        from app.integrations.session.helpers import (
            _navigate_tab,
            _open_reusable_flow_tab,
            _runtime_cookie_value_from_tab,
            _wait_for_authenticated_tab,
        )

        browser, tab, owns_tab = _open_reusable_flow_tab(self.browser_port, ("databank.tmall.com",))
        # Always (re)load the business page before harvesting cookies.
        #
        # Reusing a parked tab's cookies without navigating looks like a cheap
        # optimisation, but the Brand Data Bank validates the session against a
        # freshly loaded page: a tab that has been idle since a previous run
        # answers every endpoint with ``errCode=477012030108 param illegal`` even
        # though its cookies and ``_tb_token_`` are byte-identical to a working
        # session.  Measured 2026-09-20: parked tab -> all 17 endpoints reject;
        # same tab after ``Page.navigate`` -> all 17 endpoints return 200.
        try:
            _navigate_tab(tab, self.home_url, timeout=max(self.timeout, 1.0))
            _wait_for_authenticated_tab(
                tab, platform_name="品牌数据银行", timeout=self.timeout,
            )
            cookies = tab.cookies(all_domains=True).as_dict()
            cookie_header = cookie_header_from_mapping(cookies)
            csrf_token = csrf_token or _runtime_cookie_value_from_tab(tab, "_tb_token_")
            if not csrf_token:
                raise RuntimeSessionUnavailable(
                    "品牌数据银行页面未提供 _tb_token_，请在采集标签页完成登录后重试。"
                )
            session = RuntimeSession(
                cookie_header=cookie_header, source="drissionpage",
                cookie_count=_cookie_count(cookie_header),
            )
            return DatabankRuntimeContext(session=session, csrf_token=csrf_token)
        except RuntimeSessionUnavailable:
            raise
