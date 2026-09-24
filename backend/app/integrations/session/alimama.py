"""Alimama (one.alimama.com) report context: cookies + csrfId + loginPointId.

Two request parameters are sent on every Alimama report call, but they have
very different lifetimes:

``csrfId``
    Issued by ``member/checkAccess.json`` and tied to the logged-in session.
    It is **long-lived** (despite the name): repeated harvests of the same
    session return a byte-identical value, so the provider caches it on the
    page via ``window.__echoMerchAlimamaRuntime`` and re-reads it on
    subsequent calls.  It is issued by a normal same-origin bootstrap
    request and can be resolved directly with the browser's logged-in Cookie
    jar.  Capturing a report XHR remains only a compatibility fallback.

``loginPointId``
    Wire format is ``[0:8] 8 hex`` (login prefix) + ``[8:21] 13 digits``
    (millisecond unix timestamp) + ``[21:] 9 hex`` (per-call random).
    **The server does not validate it.**  A controlled four-way experiment
    against ``/campaign/horizontal/findPage.json`` (real captured value,
    self-minted with the real prefix, self-minted with an all-zero prefix,
    and pure garbage) all returned ``info.ok=True`` with the same rows, so
    it is a pass-through field.  It is therefore *minted locally* instead of
    being harvested — the browser is only navigated when the direct bootstrap
    request cannot establish the Alimama SSO session.

See ``Tm_ecpm/references/cookie-notes.md`` for the raw experiment log.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.integrations.session.core import (
    DEFAULT_DEBUG_PORT,
    RuntimeSession,
    RuntimeSessionUnavailable,
    _cookie_count,
    cookie_header_from_mapping,
    resolve_runtime_session,
)
from app.integrations.session.core import DrissionPageBrowser

DEFAULT_ALIMAMA_REPORT_HOME_URL = (
    "https://one.alimama.com/index.html#!/report/campaign?rptType=campaign"
)
ALIMAMA_RUNTIME_GLOBAL = "__echoMerchAlimamaRuntime"


@dataclass(frozen=True)
class AlimamaRuntimeContext:
    """Runtime-only values needed by the Alimama report endpoint."""

    session: RuntimeSession
    csrf_id: str = field(repr=False)
    login_point_id: str = field(repr=False)


def mint_login_point_id() -> str:
    """Build a well-formed ``loginPointId`` without touching the browser.

    Mirrors the observed wire format — 8 hex login prefix, 13-digit
    millisecond timestamp, 9 hex per-call suffix — so the value looks
    native in access logs.  The server ignores the contents (see the module
    docstring), so any non-empty string would work; keeping the shape is
    purely for diagnostics.
    """
    return f"{secrets.token_hex(4)}{int(time.time() * 1000):013d}{secrets.token_hex(5)[:9]}"


def resolve_alimama_runtime_context(
    *,
    source: str,
    cookie_env: str,
    csrf_id: str = "",
    login_point_id: str = "",
    browser_port: int = DEFAULT_DEBUG_PORT,
    report_home_url: str = DEFAULT_ALIMAMA_REPORT_HOME_URL,
    timeout: float = 20,
) -> AlimamaRuntimeContext:
    """Resolve Alimama cookies and transient request parameters without persisting either."""
    if source == "env":
        csrf_id = csrf_id or os.getenv("RTB_CSRF_ID", "").strip()
        login_point_id = login_point_id or os.getenv("RTB_LOGIN_POINT_ID", "").strip()
        session = resolve_runtime_session(source=source, cookie_env=cookie_env, browser_port=browser_port)
        if not csrf_id:
            raise RuntimeSessionUnavailable(
                "--csrf-id/RTB_CSRF_ID is required when --session-source=env. "
                "loginPointId is optional — it is minted locally when absent."
            )
        return AlimamaRuntimeContext(
            session=session,
            csrf_id=csrf_id,
            login_point_id=login_point_id or mint_login_point_id(),
        )

    if source == "drissionpage":
        return DrissionPageAlimamaSessionProvider(
            browser_port, report_home_url=report_home_url, timeout=timeout,
        ).read_context(csrf_id=csrf_id, login_point_id=login_point_id)

    raise ValueError(f"Unsupported session source: {source}")


class DrissionPageAlimamaSessionProvider:
    """Capture report request parameters from a manually logged-in Alimama page."""

    def __init__(self, browser_port: int, report_home_url: str, timeout: float) -> None:
        if not 1 <= browser_port <= 65535:
            raise ValueError("--browser-port must be between 1 and 65535.")
        if timeout <= 0:
            raise ValueError("Alimama request capture timeout must be positive.")
        self.browser_port = browser_port
        self.report_home_url = report_home_url
        self.timeout = timeout

    def read_context(self, *, csrf_id: str = "", login_point_id: str = "") -> AlimamaRuntimeContext:
        from app.integrations.session.helpers import (
            _navigate_tab,
            _open_reusable_flow_tab,
            _reload_tab,
            _runtime_session_from_tab,
            _set_tab_window_values,
            _tab_window_value,
            _wait_for_authenticated_tab,
        )

        browser, tab, owns_tab = _open_reusable_flow_tab(self.browser_port, ("one.alimama.com",))
        captured_csrf = csrf_id
        # loginPointId is never captured: the server does not validate it
        # (four-way experiment, see module docstring), so a self-minted value
        # is always sufficient.  This removes the single most fragile part of
        # the flow — previously a missing loginPointId raised, even when the
        # session was perfectly healthy.
        captured_login_point = login_point_id or mint_login_point_id()
        should_capture = not captured_csrf
        capture_started = False

        if not owns_tab:
            if should_capture:
                captured_csrf = captured_csrf or _tab_window_value(tab, ALIMAMA_RUNTIME_GLOBAL, "csrfId")
                should_capture = not captured_csrf
            if not should_capture:
                session = _runtime_session_from_tab(tab)
                return AlimamaRuntimeContext(
                    session=session, csrf_id=captured_csrf, login_point_id=captured_login_point,
                )

        # ``csrfId`` is issued by a normal same-origin bootstrap API, not
        # computed by the report bundle.  Reuse the browser cookie jar and
        # call that API directly before starting a request listener.  This is
        # both faster and less sensitive to the SPA being idle on a parked
        # tab; the listener remains a fallback for fresh SSO hand-offs where
        # the Alimama domain cookies have not been established yet.
        if should_capture:
            try:
                session = _runtime_session_from_tab(tab)
            except RuntimeSessionUnavailable:
                session = None
            if session is not None:
                captured_csrf = _fetch_alimama_csrf_id(
                    session.cookie_header,
                    timeout=min(max(self.timeout, 3.0), 15.0),
                )
                if captured_csrf:
                    _set_tab_window_values(
                        tab,
                        ALIMAMA_RUNTIME_GLOBAL,
                        {"csrfId": captured_csrf, "loginPointId": captured_login_point},
                    )
                    return AlimamaRuntimeContext(
                        session=session,
                        csrf_id=captured_csrf,
                        login_point_id=captured_login_point,
                    )

        if should_capture:
            # Broad target: report/query is the primary carrier, but on cold
            # starts the SPA can take a long time before the first query XHR,
            # while boot-time calls (e.g. member/isSignProtocol.json) already
            # carry csrfId.  Extraction only accepts packets that contain
            # csrfId, so the extra traffic is harmless.
            tab.listen.start(targets=r"one\.alimama\.com", is_regex=True)
            capture_started = True
        try:
            if owns_tab:
                _navigate_tab(tab, self.report_home_url, timeout=max(self.timeout, 1.0))
            elif should_capture:
                _reload_tab(tab, timeout=max(self.timeout, 1.0))
            _wait_for_authenticated_tab(
                tab, platform_name="阿里妈妈",
                timeout=max(self.timeout, 1.0),
                expected_hosts=("one.alimama.com",),
            )
            if should_capture:
                # The first page load regularly renders only the SPA shell
                # (no report XHR within the timeout).  Reload and listen again
                # before giving up — this covers the "parameters not observed"
                # failures seen on scheduled morning runs.
                for attempt in range(3):
                    if attempt:
                        _reload_tab(tab, timeout=max(self.timeout, 1.0))
                    deadline = time.monotonic() + max(self.timeout, 5.0)
                    while time.monotonic() < deadline:
                        for packet in tab.listen.steps(timeout=3):
                            request_csrf, _ = _extract_alimama_request_context(packet)
                            captured_csrf = captured_csrf or request_csrf
                            if captured_csrf:
                                break
                        if captured_csrf:
                            break
                    if captured_csrf:
                        break
        finally:
            if capture_started:
                tab.listen.stop()

        if not captured_csrf:
            raise RuntimeSessionUnavailable(
                "Alimama csrfId was not observed. Open the report page in the attached browser, "
                "confirm the account is logged in, and retry."
            )

        cookie_header = cookie_header_from_mapping(tab.cookies(all_domains=True).as_dict())
        session = RuntimeSession(
            cookie_header=cookie_header, source="drissionpage", cookie_count=_cookie_count(cookie_header),
        )
        context = AlimamaRuntimeContext(session=session, csrf_id=captured_csrf, login_point_id=captured_login_point)
        _set_tab_window_values(tab, ALIMAMA_RUNTIME_GLOBAL, {"csrfId": captured_csrf, "loginPointId": captured_login_point})
        return context


def _fetch_alimama_csrf_id(cookie_header: str, *, timeout: float) -> str:
    """Resolve ``csrfId`` through Alimama's bootstrap contract.

    The value is returned by ``member/checkAccess.json`` at
    ``data.accessInfo.csrfId``.  Keep this helper secret-free: callers only
    receive the value in memory and failures intentionally collapse to an
    empty result so the browser-listener fallback can establish a fresh SSO
    session when needed.
    """

    request = Request(
        "https://one.alimama.com/member/checkAccess.json",
        data=b'{"bizCode":"universalBP"}',
        method="POST",
        headers={
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
            "cookie": cookie_header,
            "origin": "https://one.alimama.com",
            "referer": DEFAULT_ALIMAMA_REPORT_HOME_URL,
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/153.0.0.0 Safari/537.36"
            ),
            "x-requested-with": "XMLHttpRequest",
        },
    )
    try:
        with urlopen(request, timeout=max(float(timeout), 1.0)) as response:
            payload = json.loads(response.read(1_000_000).decode("utf-8", errors="replace"))
    except (HTTPError, URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, Mapping):
        return ""
    data = payload.get("data")
    if not isinstance(data, Mapping):
        return ""
    access_info = data.get("accessInfo")
    if not isinstance(access_info, Mapping):
        return ""
    return _text(access_info.get("csrfId") or access_info.get("csrfID"))


def _extract_alimama_request_context(packet: Any) -> tuple[str, str]:
    request = getattr(packet, "request", None)
    if request is None:
        return "", ""
    params = getattr(request, "params", {}) or {}
    post_data = getattr(request, "postData", {}) or {}
    if not isinstance(params, Mapping):
        params = {}
    if not isinstance(post_data, Mapping):
        post_data = {}
    csrf_id = _text(params.get("csrfId") or post_data.get("csrfId"))
    login_point_id = _text(params.get("loginPointId") or post_data.get("loginPointId"))
    return csrf_id, login_point_id


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
