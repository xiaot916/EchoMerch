"""SYCM (sycm.taobao.com) session contexts: generic token + BYBT + 新客折扣.

The generic SYCM request token is read from the authenticated HTML bootstrap
when possible and falls back to a live request/localStorage only when the
bootstrap contract is unavailable. BYBT and 新客折扣 are special cases of the
same generic provider with a home URL / request-target pre-filled.
"""

from __future__ import annotations

import html
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from app.integrations.session.core import (
    DEFAULT_DEBUG_PORT,
    RuntimeSession,
    RuntimeSessionUnavailable,
    _cookie_count,
    cookie_header_from_mapping,
    resolve_runtime_session,
)


DEFAULT_BYBT_HOME_URL = "https://sycm.taobao.com/xsite/frame/bybt?from=bybtzd"
DEFAULT_NEW_CUSTOMER_DISCOUNT_HOME_URL = (
    "https://sycm.taobao.com/xsite/promotion/promotion/sales?activeKey=promotionMethod"
)
# The dedicated overview.json request is NOT fired on page load anymore (the
# SPA now renders the report lazily), so capture the generic jycm ``token``
# from any sycm JSON request — the same strategy the healthy SYCM datasets
# (overviews, traffic sources, ...) already rely on.
NEW_CUSTOMER_DISCOUNT_REQUEST_TARGET = r"sycm\.taobao\.com/.+\.json"
SYCM_TOKEN_META_PATTERN = re.compile(
    r'<meta[^>]+name=["\']microdata["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
SYCM_TOKEN_VALUE_PATTERN = re.compile(
    r'["\'](?:legalityToken|jycmToken|token)["\']\s*:\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

SYCM_BROWSER_REPORT_PATHS = frozenset({
    "/domain/oneQuery.json",
    "/s_content/brandnewdiscount/overview.json",
    "/datawar/v4/activity/actList/getActivityCalendar.json",
})


def sycm_browser_fallback_port(source: str, port: int) -> int | None:
    value = str(port) if source == "drissionpage" else os.getenv("ECHO_BATCH_SYCM_BROWSER_PORT", "")
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if 1 <= parsed <= 65535 else None


def fetch_sycm_browser_json(
    browser_port: int, url: str, *, timeout: int, card_id: str = "",
) -> tuple[int, bytes]:
    from app.integrations.session.core import DrissionPageBrowser

    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "sycm.taobao.com" or parsed.path not in SYCM_BROWSER_REPORT_PATHS:
        raise ValueError("生意参谋浏览器回退只支持已登记的只读报表接口。")
    tab = DrissionPageBrowser(browser_port).find_tab(("sycm.taobao.com",))
    if tab is None:
        raise RuntimeSessionUnavailable("生意参谋直连失败，且没有已打开的生意参谋页面。")
    script = """(async () => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), %d);
      try {
        const headers = %s ? {'onetrace-card-id': %s} : {};
        const response = await fetch(%s, {credentials: 'include', headers, signal: controller.signal});
        return {status: response.status, body: await response.text()};
      } catch (_) { return {error: 'request_failed'}; }
      finally { clearTimeout(timer); }
    })()""" % (
        max(1000, timeout * 1000), json.dumps(card_id), json.dumps(card_id), json.dumps(url),
    )
    result: list[object] = []

    def evaluate() -> None:
        try:
            result.append(tab.run_cdp("Runtime.evaluate", expression=script, awaitPromise=True, returnByValue=True))
        except Exception:
            result.append(None)

    worker = threading.Thread(target=evaluate, daemon=True, name="sycm-browser-fetch")
    worker.start()
    worker.join(timeout=max(1, timeout) + 5)
    value = result[0].get("result", {}).get("value") if result and isinstance(result[0], dict) else None
    if worker.is_alive() or not isinstance(value, dict) or not isinstance(value.get("body"), str):
        raise RuntimeSessionUnavailable("生意参谋页面内报表请求失败，请检查登录和网络状态。")
    return int(value["status"]), value["body"].encode("utf-8")


@dataclass(frozen=True)
class SycmRuntimeContext:
    """Runtime-only values needed by SYCM endpoints with a request token."""

    session: RuntimeSession
    token: str = field(repr=False)


def resolve_sycm_runtime_context(
    *,
    source: str,
    cookie_env: str,
    token: str = "",
    browser_port: int = DEFAULT_DEBUG_PORT,
    home_url: str,
    request_target: str,
    platform_name: str,
    timeout: float = 20,
) -> SycmRuntimeContext:
    """Resolve cookies and a transient token from one authenticated SYCM page."""
    if source == "env":
        token = token or os.getenv("SYCM_TOKEN", "").strip()
        session = resolve_runtime_session(
            source=source, cookie_env=cookie_env, browser_port=browser_port, home_url=home_url,
        )
        if not token:
            raise RuntimeSessionUnavailable("--token/SYCM_TOKEN is required when --session-source=env.")
        return SycmRuntimeContext(session=session, token=token)

    if source == "drissionpage":
        return DrissionPageSycmTokenSessionProvider(
            browser_port, home_url=home_url, request_target=request_target,
            platform_name=platform_name, timeout=timeout,
        ).read_context(token=token)

    raise ValueError(f"Unsupported session source: {source}")


def resolve_bybt_runtime_context(
    *,
    source: str,
    cookie_env: str,
    token: str = "",
    browser_port: int = DEFAULT_DEBUG_PORT,
    timeout: float = 20,
) -> SycmRuntimeContext:
    """Resolve a live 百亿补贴 request token and browser cookies."""
    return resolve_sycm_runtime_context(
        source=source,
        cookie_env=cookie_env,
        token=token,
        browser_port=browser_port,
        home_url=DEFAULT_BYBT_HOME_URL,
        request_target=r"sycm\.taobao\.com/mc/bybt/sellerData/businessOverview/statistics\.json",
        platform_name="百亿补贴",
        timeout=timeout,
    )


def resolve_new_customer_discount_runtime_context(
    *,
    source: str,
    cookie_env: str,
    token: str = "",
    browser_port: int = DEFAULT_DEBUG_PORT,
    timeout: float = 20,
) -> SycmRuntimeContext:
    """Resolve 新客折扣 with the logged-in SYCM page session."""
    if source == "drissionpage":
        context = DrissionPageSycmTokenSessionProvider(
            browser_port,
            home_url=DEFAULT_NEW_CUSTOMER_DISCOUNT_HOME_URL,
            request_target=NEW_CUSTOMER_DISCOUNT_REQUEST_TARGET,
            platform_name="新客折扣",
            timeout=timeout,
        ).read_context(token=token)
        # The captured token IS the request token the fetch worker needs.
        # Historically only ``.session`` was propagated here and the token was
        # silently dropped, so the fetch ran without ``token`` until the
        # platform started enforcing it.
        return SycmRuntimeContext(session=context.session, token=token.strip() or context.token)

    return resolve_sycm_runtime_context(
        source=source,
        cookie_env=cookie_env,
        token=token,
        browser_port=browser_port,
        home_url=DEFAULT_NEW_CUSTOMER_DISCOUNT_HOME_URL,
        request_target=NEW_CUSTOMER_DISCOUNT_REQUEST_TARGET,
        platform_name="新客折扣",
        timeout=timeout,
    )


class DrissionPageSycmTokenSessionProvider:
    """Capture a short-lived SYCM token emitted by one business page."""

    def __init__(
        self,
        browser_port: int,
        *,
        home_url: str,
        request_target: str,
        platform_name: str,
        timeout: float,
    ) -> None:
        if not 1 <= browser_port <= 65535:
            raise ValueError("--browser-port must be between 1 and 65535.")
        if timeout <= 0:
            raise ValueError("SYCM request capture timeout must be positive.")
        self.browser_port = browser_port
        self.home_url = home_url
        self.request_target = request_target
        self.platform_name = platform_name
        self.timeout = timeout

    def read_context(self, *, token: str = "") -> SycmRuntimeContext:
        from app.integrations.session.helpers import (
            _navigate_tab,
            _open_reusable_flow_tab,
            _reload_tab,
            _runtime_session_from_tab,
            _tab_local_storage_value,
            _wait_for_authenticated_tab,
        )

        browser, tab, owns_tab = _open_reusable_flow_tab(self.browser_port, ("sycm.taobao.com",))
        captured_token = token
        should_capture = not captured_token
        capture_started = False

        if not owns_tab and should_capture:
            # A parked authenticated tab is enough to build the protocol
            # session. Read the bootstrap token over HTTP so every dataset can
            # reuse this page without navigation or request-listener races.
            try:
                session = _runtime_session_from_tab(tab)
            except RuntimeSessionUnavailable:
                session = None
            if session is not None:
                captured_token = _fetch_sycm_html_token(
                    session.cookie_header,
                    home_url=self.home_url,
                    timeout=min(max(self.timeout, 3.0), 15.0),
                )
                if captured_token:
                    return SycmRuntimeContext(session=session, token=captured_token)
            captured_token = _tab_local_storage_value(tab, "jycmToken")
            should_capture = not captured_token
        if not owns_tab and captured_token:
            session = _runtime_session_from_tab(tab)
            return SycmRuntimeContext(session=session, token=captured_token)

        try:
            _navigate_tab(tab, self.home_url, timeout=max(self.timeout, 1.0))
            _wait_for_authenticated_tab(
                tab, platform_name=self.platform_name,
                timeout=max(self.timeout, 1.0),
                expected_hosts=("sycm.taobao.com",),
            )
            if should_capture:
                # Prefer the authenticated HTML shell even on a cold start.
                # Only use the listener when the protocol bootstrap endpoint
                # is unavailable or has changed its response contract.
                try:
                    session = _runtime_session_from_tab(tab)
                except RuntimeSessionUnavailable:
                    session = None
                if session is not None:
                    captured_token = _fetch_sycm_html_token(
                        session.cookie_header,
                        home_url=self.home_url,
                        timeout=min(max(self.timeout, 3.0), 15.0),
                    )
                if not captured_token:
                    tab.listen.start(targets=self.request_target, is_regex=True, method="GET")
                    capture_started = True
                    # Lazy SPA pages may not fire the target request on the
                    # first load; reload and listen again before localStorage.
                    for attempt in range(3):
                        if attempt:
                            _reload_tab(tab, timeout=max(self.timeout, 1.0))
                        deadline = time.monotonic() + max(self.timeout, 5.0)
                        while time.monotonic() < deadline:
                            for packet in tab.listen.steps(timeout=3):
                                captured_token = captured_token or _extract_sycm_request_token(packet)
                                if captured_token:
                                    break
                            if captured_token:
                                break
                        if captured_token:
                            break
                if not captured_token:
                    captured_token = _tab_local_storage_value(tab, "jycmToken")
        finally:
            if capture_started:
                tab.listen.stop()

        if not captured_token:
            raise RuntimeSessionUnavailable(
                f"{self.platform_name}页面已打开，但没有捕获到有效会话 token。"
                "请确认账号拥有对应页面权限、报表可以正常显示后重试。"
            )

        cookie_header = cookie_header_from_mapping(tab.cookies(all_domains=True).as_dict())
        context = SycmRuntimeContext(
            session=RuntimeSession(
                cookie_header=cookie_header, source="drissionpage",
                cookie_count=_cookie_count(cookie_header),
            ),
            token=captured_token,
        )
        browser.close_tab(tab)
        return context


def _fetch_sycm_html_token(cookie_header: str, *, home_url: str, timeout: float) -> str:
    """Read the SYCM bootstrap token from authenticated HTML, in memory only."""
    request = Request(
        home_url,
        method="GET",
        headers={
            "accept": "text/html,application/xhtml+xml",
            "cache-control": "no-cache",
            "cookie": cookie_header,
            "pragma": "no-cache",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/153.0.0.0 Safari/537.36"
            ),
        },
    )
    try:
        with urlopen(request, timeout=max(float(timeout), 1.0)) as response:
            raw = response.read(2_000_000)
    except (HTTPError, OSError, URLError, TimeoutError):
        return ""
    source = raw.decode("utf-8", errors="replace")
    meta_match = SYCM_TOKEN_META_PATTERN.search(source)
    candidates = [meta_match.group(1)] if meta_match else []
    candidates.append(source)
    for candidate in candidates:
        decoded = html.unescape(candidate)
        try:
            payload = json.loads(decoded)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict):
            for key in ("legalityToken", "jycmToken", "token"):
                value = str(payload.get(key) or "").strip()
                if value:
                    return value
        match = SYCM_TOKEN_VALUE_PATTERN.search(decoded)
        if match:
            return match.group(1).strip()
    return ""


def _extract_sycm_request_token(packet: Any) -> str:
    request = getattr(packet, "request", None)
    if request is None:
        return ""
    params = getattr(request, "params", {}) or {}
    if not isinstance(params, dict):
        return ""
    value = params.get("token")
    return str(value).strip() if value is not None else ""
