"""PZ 品牌专区 (brandsearch) session context with csrfID + query params."""

from __future__ import annotations

import os
import json
import time
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.integrations.session.core import (
    DEFAULT_DEBUG_PORT,
    DrissionPageBrowser,
    RuntimeSession,
    RuntimeSessionUnavailable,
    _cookie_count,
    cookie_header_from_mapping,
    resolve_runtime_session,
)

DEFAULT_BRANDSEARCH_REPORT_HOME_URL = (
    "https://branding.taobao.com/#!/report/index?productid=101005201"
)
BRANDSEARCH_USER_INFO_URL = "https://branding.taobao.com/login/userInfo.json"
BRANDSEARCH_RUNTIME_GLOBAL = "__echoMerchBrandSearchRuntime"


@dataclass(frozen=True)
class BrandSearchRuntimeContext:
    """Runtime-only values needed by the PZ brand-search report endpoint."""

    session: RuntimeSession
    csrf_id: str = field(repr=False)
    query_params: Mapping[str, str] = field(repr=False)


def resolve_brandsearch_runtime_context(
    *,
    source: str,
    cookie_env: str,
    csrf_id: str = "",
    browser_port: int = DEFAULT_DEBUG_PORT,
    report_home_url: str = DEFAULT_BRANDSEARCH_REPORT_HOME_URL,
    timeout: float = 20,
) -> BrandSearchRuntimeContext:
    """Resolve PZ cookies and the current report query contract at runtime."""
    if source == "env":
        csrf_id = csrf_id or os.getenv("PZ_CSRF_ID", "").strip()
        session = resolve_runtime_session(
            source=source, cookie_env=cookie_env, browser_port=browser_port,
        )
        return _brandsearch_context_from_session(
            session,
            csrf_id=csrf_id,
            timeout=timeout,
        )

    if source == "drissionpage":
        return DrissionPageBrandSearchSessionProvider(
            browser_port, report_home_url=report_home_url, timeout=timeout,
        ).read_context(csrf_id=csrf_id)

    raise ValueError(f"Unsupported session source: {source}")


class DrissionPageBrandSearchSessionProvider:
    """Resolve PZ context from browser cookies, with page capture as fallback."""

    def __init__(self, browser_port: int, report_home_url: str, timeout: float) -> None:
        if not 1 <= browser_port <= 65535:
            raise ValueError("--browser-port must be between 1 and 65535.")
        if timeout <= 0:
            raise ValueError("Brand-search request capture timeout must be positive.")
        self.browser_port = browser_port
        self.report_home_url = report_home_url
        self.timeout = timeout

    def read_context(self, *, csrf_id: str = "") -> BrandSearchRuntimeContext:
        from app.integrations.session.helpers import (
            _browser_tabs,
            _navigate_tab,
            _open_reusable_flow_tab,
            _reload_tab,
            _runtime_session_from_tab,
            _set_tab_window_values,
            _tab_window_value,
            _wait_for_authenticated_tab,
        )

        # The PZ frontend obtains csrfID from /login/userInfo.json.  That
        # endpoint accepts the shared Taobao login cookies, so any existing
        # tab can supply the browser cookie jar; the PZ report page does not
        # need to be opened, refreshed, or listened to during normal runs.
        try:
            browser = DrissionPageBrowser(self.browser_port)
            cookie_tabs = _browser_tabs(browser)
            if not cookie_tabs:
                raise RuntimeSessionUnavailable(
                    "采集浏览器没有可复用的已登录业务标签页。"
                )
            session = _runtime_session_from_tab(cookie_tabs[0])
            return _brandsearch_context_from_session(
                session,
                csrf_id=csrf_id,
                timeout=self.timeout,
            )
        except RuntimeSessionUnavailable:
            # Login expiry, incomplete cookie jars, and upstream contract
            # changes still have a recoverable path: open/reuse the PZ page
            # and capture one real request using the legacy implementation.
            pass

        browser, tab, owns_tab = _open_reusable_flow_tab(
            self.browser_port, ("branding.taobao.com", "brandsearch.taobao.com")
        )
        captured_csrf = csrf_id
        captured_params: dict[str, str] = {}
        if not owns_tab:
            captured_csrf = captured_csrf or _tab_window_value(
                tab, BRANDSEARCH_RUNTIME_GLOBAL, "csrfId"
            )
            cached_params = _tab_window_value(
                tab, BRANDSEARCH_RUNTIME_GLOBAL, "queryParams"
            )
            if cached_params:
                try:
                    parsed_cached_params = json.loads(cached_params)
                except (TypeError, ValueError, json.JSONDecodeError):
                    parsed_cached_params = None
                if isinstance(parsed_cached_params, Mapping):
                    captured_params = {
                        str(key): str(value)
                        for key, value in parsed_cached_params.items()
                        if value is not None and str(value).strip()
                    }
        if captured_csrf and not owns_tab:
            session = _runtime_session_from_tab(tab)
            captured_params["csrfID"] = captured_csrf
            return BrandSearchRuntimeContext(
                session=session,
                csrf_id=captured_csrf,
                query_params={
                    **_default_query_params(),
                    **captured_params,
                },
            )
        tab.listen.start(
            # The report page first boots on branding.taobao.com and may
            # redirect its API request to brandsearch.taobao.com.  Listening
            # only to the final endpoint made cold starts depend on timing.
            targets=r"(?:branding|brandsearch)\.taobao\.com",
            is_regex=True,
            method="GET",
        )
        try:
            if owns_tab:
                _navigate_tab(tab, self.report_home_url, timeout=max(self.timeout, 1.0))
            else:
                # Same-hash navigation is a no-op for the PZ SPA.  Reload the
                # existing tab after the listener is attached so the request
                # carrying csrfID is emitted again without opening a blank tab.
                _reload_tab(tab, timeout=max(self.timeout, 1.0))
            _wait_for_authenticated_tab(
                tab,
                platform_name="品销宝品牌专区",
                timeout=max(self.timeout, 1.0),
                expected_hosts=("branding.taobao.com", "brandsearch.taobao.com"),
            )
            for attempt in range(3):
                if attempt:
                    _reload_tab(tab, timeout=max(self.timeout, 1.0))
                deadline = time.monotonic() + max(self.timeout, 5.0)
                while time.monotonic() < deadline and not captured_csrf:
                    for packet in tab.listen.steps(timeout=min(3.0, max(self.timeout, 5.0))):
                        request_csrf, request_params = _extract_brandsearch_request_context(packet)
                        if request_csrf:
                            captured_csrf = captured_csrf or request_csrf
                            captured_params = request_params
                            # A captured request whose response is the login HTML
                            # page means the brand-search session itself is stale;
                            # fail with an actionable message instead of letting
                            # the fetch worker crash on a JSON decode error.
                            response_body = getattr(
                                getattr(packet, "response", None), "body", None
                            )
                            if isinstance(response_body, str) and _looks_like_html(response_body):
                                raise RuntimeSessionUnavailable(
                                    "品销宝报表接口返回了登录页 HTML，品销宝会话已失效。"
                                    "请在采集浏览器中重新打开品销宝品牌专区并完成登录后重试。"
                                )
                            break
                if captured_csrf and captured_params:
                    break
        finally:
            tab.listen.stop()

        if not captured_csrf:
            if owns_tab:
                browser.close_tab(tab)
            raise RuntimeSessionUnavailable(
                "PZ csrfID was not observed. Open the 品销宝品牌专区报表 in the attached browser and retry."
            )

        captured_params = {**_default_query_params(), **captured_params, "csrfID": captured_csrf}
        cookie_header = cookie_header_from_mapping(tab.cookies(all_domains=True).as_dict())
        session = RuntimeSession(
            cookie_header=cookie_header, source="drissionpage",
            cookie_count=_cookie_count(cookie_header),
        )
        context = BrandSearchRuntimeContext(
            session=session,
            csrf_id=captured_csrf,
            query_params=captured_params,
        )
        _set_tab_window_values(
            tab,
            BRANDSEARCH_RUNTIME_GLOBAL,
            {
                "csrfId": captured_csrf,
                "queryParams": json.dumps(captured_params, ensure_ascii=False, separators=(",", ":")),
            },
        )
        return context


def _extract_brandsearch_request_context(packet: Any) -> tuple[str, dict[str, str]]:
    request = getattr(packet, "request", None)
    if request is None:
        return "", {}
    params = getattr(request, "params", {}) or {}
    if not isinstance(params, Mapping):
        return "", {}
    normalized = {
        str(key): str(value)
        for key, value in params.items()
        if value is not None and str(value).strip()
    }
    csrf = next(
        (
            normalized.get(key, "")
            for key in ("csrfID", "csrfId", "csrf_id")
            if normalized.get(key, "")
        ),
        "",
    )
    return csrf.strip(), normalized


def _default_query_params() -> dict[str, str]:
    return {
        "r": "mx_548",
        "attribution": "impression",
        "effectConversionCycle": "30",
        "trafficType": "[1,2,4,5]",
    }


def _brandsearch_context_from_session(
    session: RuntimeSession,
    *,
    csrf_id: str = "",
    timeout: float = 20,
) -> BrandSearchRuntimeContext:
    resolved_csrf = csrf_id.strip() or _fetch_brandsearch_csrf_id(
        session.cookie_header,
        timeout=timeout,
    )
    return BrandSearchRuntimeContext(
        session=session,
        csrf_id=resolved_csrf,
        query_params={**_default_query_params(), "csrfID": resolved_csrf},
    )


def _fetch_brandsearch_csrf_id(cookie_header: str, *, timeout: float) -> str:
    request = Request(
        f"{BRANDSEARCH_USER_INFO_URL}?r=echomerch_session",
        method="GET",
        headers={
            "accept": "application/json, text/javascript, */*; q=0.01",
            "cache-control": "no-cache",
            "cookie": cookie_header,
            "pragma": "no-cache",
            "referer": "https://branding.taobao.com/",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/138.0.0.0 Safari/537.36"
            ),
            "x-requested-with": "XMLHttpRequest",
        },
    )
    try:
        with urlopen(request, timeout=max(float(timeout), 1.0)) as response:
            raw = response.read()
            status = int(getattr(response, "status", 200))
    except HTTPError as exc:
        raise RuntimeSessionUnavailable(
            f"品销宝会话初始化接口返回 HTTP {exc.code}。"
        ) from exc
    except (OSError, URLError, TimeoutError) as exc:
        raise RuntimeSessionUnavailable(
            "品销宝会话初始化接口暂时不可用。"
        ) from exc

    if not 200 <= status < 300:
        raise RuntimeSessionUnavailable(
            f"品销宝会话初始化接口返回 HTTP {status}。"
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeSessionUnavailable(
            "品销宝会话初始化返回了非 JSON 内容，登录会话可能已失效。"
        ) from exc
    if not isinstance(payload, Mapping):
        raise RuntimeSessionUnavailable("品销宝会话初始化返回格式异常。")

    data = payload.get("data")
    csrf_id = str(data.get("csrfID") or "").strip() if isinstance(data, Mapping) else ""
    if csrf_id:
        return csrf_id

    info = payload.get("info")
    message = ""
    if isinstance(info, Mapping):
        message = str(info.get("message") or info.get("msg") or "").strip()
    detail = f"：{message}" if message else ""
    raise RuntimeSessionUnavailable(
        f"品销宝登录会话未返回 csrfID{detail}，请重新登录采集浏览器。"
    )


def _looks_like_html(value: str) -> bool:
    head = value.lstrip()[:200].lower()
    return head.startswith("<!doctype") or "<html" in head
