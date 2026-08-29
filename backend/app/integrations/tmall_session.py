"""Runtime-only Tmall browser session access.

This module deliberately never persists cookies.  A worker can attach to a
locally logged-in Chrome instance, use the cookie header for one process, and
discard it when the process exits.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.error import URLError
from urllib.parse import parse_qs, unquote, urlparse
from urllib.request import urlopen


DEFAULT_DEBUG_PORT = 9222
DEFAULT_SYCM_HOME_URL = "https://sycm.taobao.com/portal/home.htm"
DEFAULT_BYBT_HOME_URL = "https://sycm.taobao.com/xsite/frame/bybt?from=bybtzd"
BYBT_OVERVIEW_URL = (
    "https://sycm.taobao.com/mc/bybt/sellerData/businessOverview/statistics.json"
)
DEFAULT_NEW_CUSTOMER_DISCOUNT_HOME_URL = (
    "https://sycm.taobao.com/xsite/promotion/promotion/sales?activeKey=promotionMethod"
)
NEW_CUSTOMER_DISCOUNT_OVERVIEW_URL = (
    "https://sycm.taobao.com/s_content/brandnewdiscount/overview.json"
)
DEFAULT_DATABANK_HOME_URL = "https://databank.tmall.com/"
DEFAULT_ALIMAMA_REPORT_HOME_URL = (
    "https://one.alimama.com/index.html#!/report/campaign?rptType=campaign"
)
DEFAULT_BRANDSEARCH_REPORT_HOME_URL = (
    "https://branding.taobao.com/#!/report/index?productid=101005201"
)
BRANDSEARCH_REPORT_URL = (
    "https://brandsearch.taobao.com/report/query/rptAdvertiserSubListNew.json"
)
DEFAULT_CPS_REPORT_HOME_URL = (
    "https://ad.alimama.com/portal/v2/report/promotionDataPage.htm"
)
CPS_OVERVIEW_URL = (
    "https://ad.alimama.com/openapi/param2/1/gateway.unionadv/data.home.overview.json"
)
DEFAULT_UTRY_REPORT_HOME_URL = (
    "https://tmesh.tmall.com/utry/samplePlatform/common_data_board?id=1904810"
)
UTRY_REPORT_URLS = {
    1904974: "https://tmesh.tmall.com/utry/samplePlatform/common_data_board?id=1904974",
    1906730: "https://tmesh.tmall.com/utry/samplePlatform/common_data_board?id=1906730",
}
UTRY_WIDGET_URL = "https://quark.taobao.com/fbi/.json"
UTRY_DASHBOARD_LIST_API = (
    "mtop.tmall.tmesh.apps.utry.sampleplatform.getDataDashboardList"
)
UTRY_DASHBOARD_RESULT_GLOBAL = "__echoMerchUtryDashboardResult"
ALIMAMA_RUNTIME_GLOBAL = "__echoMerchAlimamaRuntime"
DEFAULT_BROWSER_LOGIN_TIMEOUT = 180


class RuntimeSessionUnavailable(RuntimeError):
    """Raised when a runtime browser session cannot be used safely."""


@dataclass(frozen=True)
class BrowserPlatformSession:
    """A secret-free snapshot of one platform inside the collection browser."""

    code: str
    name: str
    status: str
    detail: str
    page_detected: bool = False
    authenticated: bool = False
    cookie_detected: bool = False
    cookie_count: int = 0


@dataclass(frozen=True)
class _BrowserPlatformSpec:
    code: str
    name: str
    home_url: str
    hosts: tuple[str, ...]


_BROWSER_PLATFORM_SPECS = {
    "sycm": _BrowserPlatformSpec(
        code="sycm",
        name="生意参谋",
        home_url=DEFAULT_SYCM_HOME_URL,
        hosts=("sycm.taobao.com",),
    ),
    "cps": _BrowserPlatformSpec(
        code="cps",
        name="淘宝客 CPS",
        home_url=DEFAULT_CPS_REPORT_HOME_URL,
        hosts=("ad.alimama.com",),
    ),
}


@dataclass(frozen=True)
class RuntimeSession:
    cookie_header: str = field(repr=False)
    source: str = "env"
    cookie_count: int = 0


@dataclass(frozen=True)
class AlimamaRuntimeContext:
    """Runtime-only values needed by the Alimama report endpoint."""

    session: RuntimeSession
    csrf_id: str = field(repr=False)
    login_point_id: str = field(repr=False)


@dataclass(frozen=True)
class BrandSearchRuntimeContext:
    """Runtime-only values needed by the PZ brand-search report endpoint."""

    session: RuntimeSession
    csrf_id: str = field(repr=False)
    query_params: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True)
class CpsRuntimeContext:
    """Runtime-only values needed by the CPS overview endpoint."""

    session: RuntimeSession
    tb_token: str = field(repr=False)


@dataclass(frozen=True)
class SycmRuntimeContext:
    """Runtime-only values needed by SYCM endpoints with a request token."""

    session: RuntimeSession
    token: str = field(repr=False)


@dataclass(frozen=True)
class DatabankRuntimeContext:
    """Runtime-only values needed by the Tmall Brand Data Bank APIs."""

    session: RuntimeSession
    csrf_token: str = field(repr=False)


@dataclass(frozen=True)
class UtryReportTemplate:
    report_id: int
    request_url: str
    referer: str
    params: Mapping[str, Any] = field(repr=False)


@dataclass(frozen=True)
class UtryRuntimeContext:
    session: RuntimeSession
    templates: Mapping[int, UtryReportTemplate] = field(repr=False)


def add_session_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--session-source",
        choices=("env", "drissionpage"),
        default=os.getenv("ECHO_TMALL_SESSION_SOURCE", "drissionpage"),
        help="env reads the configured cookie variable; drissionpage attaches to a logged-in local browser.",
    )
    parser.add_argument(
        "--cookie-env",
        default="SYCM_COOKIE",
        help="Cookie environment variable used only when --session-source=env.",
    )
    parser.add_argument(
        "--browser-port",
        type=int,
        default=int(os.getenv("ECHO_TMALL_BROWSER_PORT", str(DEFAULT_DEBUG_PORT))),
        help="Chrome remote-debugging port used only when --session-source=drissionpage.",
    )


def resolve_runtime_session(
    *,
    source: str,
    cookie_env: str,
    browser_port: int = DEFAULT_DEBUG_PORT,
    home_url: str = DEFAULT_SYCM_HOME_URL,
    platform_name: str = "生意参谋",
    expected_hosts: tuple[str, ...] = ("sycm.taobao.com",),
) -> RuntimeSession:
    if source == "env":
        cookie_header = os.getenv(cookie_env, "").strip()
        if not cookie_header:
            raise RuntimeSessionUnavailable(f"{cookie_env} is required for --session-source=env.")
        return RuntimeSession(
            cookie_header=_validate_cookie_header(cookie_header),
            source="env",
            cookie_count=_cookie_count(cookie_header),
        )
    if source == "drissionpage":
        return DrissionPageSessionProvider(
            browser_port,
            home_url=home_url,
            platform_name=platform_name,
            expected_hosts=expected_hosts,
        ).read_session()
    raise ValueError(f"Unsupported session source: {source}")


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
        session = resolve_runtime_session(
            source=source,
            cookie_env=cookie_env,
            browser_port=browser_port,
        )
        if not csrf_id or not login_point_id:
            raise RuntimeSessionUnavailable(
                "--csrf-id/RTB_CSRF_ID and --login-point-id/RTB_LOGIN_POINT_ID are required "
                "when --session-source=env."
            )
        return AlimamaRuntimeContext(
            session=session,
            csrf_id=csrf_id,
            login_point_id=login_point_id,
        )

    if source == "drissionpage":
        return DrissionPageAlimamaSessionProvider(
            browser_port,
            report_home_url=report_home_url,
            timeout=timeout,
        ).read_context(csrf_id=csrf_id, login_point_id=login_point_id)

    raise ValueError(f"Unsupported session source: {source}")


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
            source=source,
            cookie_env=cookie_env,
            browser_port=browser_port,
        )
        if not csrf_id:
            raise RuntimeSessionUnavailable(
                "--csrf-id/PZ_CSRF_ID is required when --session-source=env."
            )
        return BrandSearchRuntimeContext(
            session=session,
            csrf_id=csrf_id,
            query_params={
                "r": "mx_548",
                "attribution": "impression",
                "effectConversionCycle": "30",
                "trafficType": "[1,2,4,5]",
                "csrfID": csrf_id,
            },
        )

    if source == "drissionpage":
        return DrissionPageBrandSearchSessionProvider(
            browser_port,
            report_home_url=report_home_url,
            timeout=timeout,
        ).read_context(csrf_id=csrf_id)

    raise ValueError(f"Unsupported session source: {source}")


def resolve_cps_runtime_context(
    *,
    source: str,
    cookie_env: str,
    tb_token: str = "",
    browser_port: int = DEFAULT_DEBUG_PORT,
    report_home_url: str = DEFAULT_CPS_REPORT_HOME_URL,
    timeout: float = 20,
) -> CpsRuntimeContext:
    """Resolve CPS cookies and the transient _tb_token_ without persisting either."""

    if source == "env":
        tb_token = tb_token or os.getenv("CPS_TB_TOKEN", "").strip()
        session = resolve_runtime_session(
            source=source,
            cookie_env=cookie_env,
            browser_port=browser_port,
        )
        if not tb_token:
            raise RuntimeSessionUnavailable(
                "--tb-token/CPS_TB_TOKEN is required when --session-source=env."
            )
        return CpsRuntimeContext(session=session, tb_token=tb_token)

    if source == "drissionpage":
        return DrissionPageCpsSessionProvider(
            browser_port,
            report_home_url=report_home_url,
            timeout=timeout,
        ).read_context(tb_token=tb_token)

    raise ValueError(f"Unsupported session source: {source}")


def resolve_bybt_runtime_context(
    *,
    source: str,
    cookie_env: str,
    token: str = "",
    browser_port: int = DEFAULT_DEBUG_PORT,
    home_url: str = DEFAULT_BYBT_HOME_URL,
    timeout: float = 20,
) -> SycmRuntimeContext:
    """Resolve a live 百亿补贴 request token and browser cookies."""

    return resolve_sycm_runtime_context(
        source=source,
        cookie_env=cookie_env,
        token=token,
        browser_port=browser_port,
        home_url=home_url,
        request_target=(
            r"sycm\.taobao\.com/mc/bybt/sellerData/businessOverview/statistics\.json"
        ),
        platform_name="百亿补贴",
        timeout=timeout,
    )


def resolve_new_customer_discount_runtime_context(
    *,
    source: str,
    cookie_env: str,
    token: str = "",
    browser_port: int = DEFAULT_DEBUG_PORT,
    home_url: str = DEFAULT_NEW_CUSTOMER_DISCOUNT_HOME_URL,
    timeout: float = 20,
) -> SycmRuntimeContext:
    """Resolve 新客折扣 with the logged-in SYCM page session.

    The endpoint accepts the browser Cookie session directly. Token capture
    used to make this otherwise simple report depend on a second page load and
    could fail when the SPA served the data from an already-warm page.
    """

    if source == "drissionpage":
        session = DrissionPageSessionProvider(
            browser_port,
            home_url=home_url,
            platform_name="新客折扣",
            expected_hosts=("sycm.taobao.com",),
        ).read_session()
        return SycmRuntimeContext(session=session, token=token.strip())

    return resolve_sycm_runtime_context(
        source=source,
        cookie_env=cookie_env,
        token=token,
        browser_port=browser_port,
        home_url=home_url,
        request_target=(
            r"sycm\.taobao\.com/s_content/brandnewdiscount/overview\.json"
        ),
        platform_name="新客折扣",
        timeout=timeout,
    )


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
            source=source,
            cookie_env=cookie_env,
            browser_port=browser_port,
            home_url=home_url,
        )
        if not token:
            raise RuntimeSessionUnavailable(
                "--token/SYCM_TOKEN is required when --session-source=env."
            )
        return SycmRuntimeContext(session=session, token=token)

    if source == "drissionpage":
        return DrissionPageSycmTokenSessionProvider(
            browser_port,
            home_url=home_url,
            request_target=request_target,
            platform_name=platform_name,
            timeout=timeout,
        ).read_context(token=token)

    raise ValueError(f"Unsupported session source: {source}")


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
            browser_port,
            home_url=home_url,
            timeout=DEFAULT_BROWSER_LOGIN_TIMEOUT,
        ).read_context(csrf_token=csrf_token)

    session = resolve_runtime_session(
        source=source,
        cookie_env=cookie_env,
        browser_port=browser_port,
        home_url=home_url,
    )
    csrf_token = csrf_token or os.getenv(csrf_env, "").strip() or _cookie_value(
        session.cookie_header, "_tb_token_"
    )
    if not csrf_token:
        raise RuntimeSessionUnavailable(
            f"--csrf-token/{csrf_env} or _tb_token_ cookie is required for the Brand Data Bank."
        )
    return DatabankRuntimeContext(session=session, csrf_token=csrf_token)


def resolve_utry_runtime_context(
    *,
    source: str,
    cookie_env: str,
    browser_port: int = DEFAULT_DEBUG_PORT,
    report_home_url: str = DEFAULT_UTRY_REPORT_HOME_URL,
    timeout: float = 30,
) -> UtryRuntimeContext:
    """Capture U先 FBI report templates and cookies without persisting them."""

    if source != "drissionpage":
        raise RuntimeSessionUnavailable(
            "U先 requires --session-source=drissionpage because reportIdToken and secureParams "
            "must be captured from the live report page."
        )
    return DrissionPageUtrySessionProvider(
        browser_port,
        report_home_url=report_home_url,
        timeout=timeout,
    ).read_context()


def cookie_header_from_mapping(cookies: Mapping[str, object]) -> str:
    pairs: list[str] = []
    for name, value in cookies.items():
        cookie_name = str(name).strip()
        cookie_value = str(value).strip()
        if not cookie_name or not cookie_value:
            continue
        if any(character in cookie_name or character in cookie_value for character in "\r\n;"):
            raise RuntimeSessionUnavailable("Browser returned an invalid cookie value.")
        pairs.append(f"{cookie_name}={cookie_value}")
    if not pairs:
        raise RuntimeSessionUnavailable("No usable cookies were found in the logged-in browser session.")
    return "; ".join(pairs)


class DrissionPageBrowser:
    """Connect to the configured browser without owning the browser process.

    Providers reuse an already-open matching page whenever its session is
    sufficient; a worker-owned tab is created only for a first-time capture or
    a platform that still needs a live request listener.
    """

    def __init__(self, browser_port: int) -> None:
        if not 1 <= browser_port <= 65535:
            raise ValueError("--browser-port must be between 1 and 65535.")
        _require_debug_browser(browser_port)
        try:
            from DrissionPage import Chromium
        except ImportError as exc:
            raise RuntimeSessionUnavailable(
                "DrissionPage is not installed. Install backend requirements before using this source."
            ) from exc
        try:
            # Use an explicit address string. Passing an integer can make
            # DrissionPage try to launch a new browser when the port is busy.
            self.browser = Chromium(f"127.0.0.1:{browser_port}")
        except Exception as exc:
            raise RuntimeSessionUnavailable(
                f"无法接管 Chrome 调试端口 {browser_port}，请确认采集浏览器已启动。"
            ) from exc

    def new_tab(self) -> Any:
        try:
            tab = self.browser.new_tab(background=False)
        except Exception as exc:
            raise RuntimeSessionUnavailable(
                "已连接采集浏览器，但无法创建独立采集标签页。"
            ) from exc
        if tab is None:
            raise RuntimeSessionUnavailable("已连接采集浏览器，但没有可用采集标签页。")
        return tab

    def close_tab(self, tab: Any) -> None:
        try:
            self.browser.close_tabs(tab)
        except Exception:
            # Closing a worker-owned tab is cleanup only. Never turn a
            # successful collection into a failure because cleanup failed.
            pass


def _wait_for_authenticated_tab(
    tab: Any,
    *,
    platform_name: str,
    timeout: float = DEFAULT_BROWSER_LOGIN_TIMEOUT,
    expected_hosts: tuple[str, ...] = (),
) -> None:
    """Allow a user to finish login and verify the intended business page."""

    deadline = time.monotonic() + max(1.0, timeout)
    while True:
        url = str(getattr(tab, "url", "") or "")
        on_expected_page = not expected_hosts or _url_matches_hosts(url, expected_hosts)
        if not _is_login_url(url) and on_expected_page:
            return
        if time.monotonic() >= deadline:
            if not _is_login_url(url) and expected_hosts:
                raise RuntimeSessionUnavailable(
                    f"{platform_name}未进入对应业务页面，当前页面为 {url or '空白页'}。"
                    "请在已打开的采集标签页确认账号权限和页面跳转后重试。"
                )
            raise RuntimeSessionUnavailable(
                f"{platform_name}采集页面仍处于登录状态，请在已打开的采集标签页完成登录后重试。"
            )
        try:
            tab.wait(0.5)
        except Exception:
            time.sleep(0.5)


def _open_flow_tab(browser_port: int) -> tuple[DrissionPageBrowser, Any]:
    browser = DrissionPageBrowser(browser_port)
    return browser, browser.new_tab()


def _browser_tabs(
    browser: DrissionPageBrowser,
    expected_hosts: tuple[str, ...] = (),
) -> list[Any]:
    """List live page targets through the bounded Chrome JSON endpoint."""

    native_browser = getattr(browser, "browser", None)
    if native_browser is None:
        return []
    address = getattr(native_browser, "address", "")
    if not address:
        return []
    try:
        with urlopen(f"http://{address}/json", timeout=2.0) as response:
            records = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    tabs: list[Any] = []
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, Mapping) or record.get("type") != "page":
            continue
        record_url = _as_nonempty_text(record.get("url"))
        if expected_hosts and not _url_matches_hosts(record_url, expected_hosts):
            continue
        tab_id = _as_nonempty_text(record.get("id"))
        if not tab_id:
            continue
        try:
            tabs.append(native_browser.get_tab(tab_id))
        except Exception:
            continue
    return tabs


def _open_reusable_flow_tab(
    browser_port: int,
    expected_hosts: tuple[str, ...],
) -> tuple[DrissionPageBrowser, Any, bool]:
    """Attach to an existing platform page before creating a blank tab."""

    browser = DrissionPageBrowser(browser_port)
    existing = _find_existing_tab(browser, None, expected_hosts)
    if existing is not None:
        return browser, existing, False
    return browser, browser.new_tab(), True


def _find_existing_platform_session(
    browser: Any,
    current_tab: Any,
    spec: _BrowserPlatformSpec,
) -> BrowserPlatformSession | None:
    """Reuse an already-open business tab during lightweight preflight.

    The collection entrypoint only needs to prove that the browser session is
    usable. Reusing a matching tab avoids opening another tab and, more
    importantly, avoids navigating through a slow or temporarily unavailable
    homepage when the user is already logged in.
    """

    tabs = _browser_tabs(browser, spec.hosts)

    probes = [
        (tab, _platform_tab_session(tab, spec))
        for tab in tabs
        if tab is not current_tab
    ]
    return next(
        (item for _tab, item in probes if item.authenticated),
        next((item for _tab, item in probes if item.page_detected), None),
    )


def _navigate_tab(tab: Any, url: str, *, timeout: float) -> None:
    """Navigate with DrissionPage's bounded page-load timeout.

    A small compatibility fallback keeps lightweight fake tabs used by tests
    working when they do not accept DrissionPage's keyword arguments.
    """

    navigation_timeout = max(1.0, float(timeout))
    # Page.navigate returns as soon as Chrome schedules navigation, unlike
    # tab.get(), which can block indefinitely while a SPA waits on a stalled
    # subresource. The bounded authenticated-page poll handles readiness.
    if hasattr(tab, "run_cdp"):
        try:
            tab.run_cdp("Page.navigate", url=url)
            return
        except Exception as exc:
            raise RuntimeSessionUnavailable(
                "采集页面导航请求失败，请检查浏览器网络后重试。"
            ) from exc
    try:
        tab.get(url, timeout=navigation_timeout)
    except TypeError as exc:
        if "timeout" not in str(exc).lower():
            raise
        tab.get(url)


def _runtime_session_from_tab(tab: Any) -> RuntimeSession:
    """Build a process-local session from one already authenticated tab."""

    cookies = tab.cookies(all_domains=True).as_dict()
    cookie_header = cookie_header_from_mapping(cookies)
    return RuntimeSession(
        cookie_header=cookie_header,
        source="drissionpage",
        cookie_count=_cookie_count(cookie_header),
    )


def _runtime_cookie_value_from_tab(tab: Any, name: str) -> str:
    """Read a cookie from the current host before falling back to all domains."""

    try:
        current = tab.cookies().as_dict()
        value = _as_nonempty_text(current.get(name))
        if value:
            return value
    except Exception:
        pass
    try:
        return _cookie_value(
            cookie_header_from_mapping(tab.cookies(all_domains=True).as_dict()),
            name,
        )
    except RuntimeSessionUnavailable:
        return ""


def _find_existing_runtime_session(
    browser: Any,
    current_tab: Any,
    expected_hosts: tuple[str, ...],
) -> RuntimeSession | None:
    """Reuse a matching authenticated tab without another page navigation."""

    tabs = _browser_tabs(browser, expected_hosts)
    for candidate in tabs:
        if candidate is current_tab:
            continue
        url = str(getattr(candidate, "url", "") or "")
        if _is_login_url(url) or not _url_matches_hosts(url, expected_hosts):
            continue
        try:
            return _runtime_session_from_tab(candidate)
        except RuntimeSessionUnavailable:
            continue
    return None


def _find_existing_tab(
    browser: Any,
    current_tab: Any,
    expected_hosts: tuple[str, ...],
) -> Any | None:
    """Return the first already-open, non-login tab for a platform."""

    tabs = _browser_tabs(browser, expected_hosts)
    for candidate in tabs:
        if candidate is current_tab:
            continue
        url = str(getattr(candidate, "url", "") or "")
        if _is_login_url(url) or not _url_matches_hosts(url, expected_hosts):
            continue
        return candidate
    return None


def _tab_local_storage_value(tab: Any, key: str) -> str:
    """Read one non-secret runtime value from an existing page when exposed."""

    try:
        value = tab.run_js(
            f"return localStorage.getItem({json.dumps(key, ensure_ascii=False)})"
        )
    except Exception:
        return ""
    return _as_nonempty_text(value)


def _tab_window_value(tab: Any, global_name: str, key: str) -> str:
    """Read one in-page runtime value without persisting it to disk."""

    try:
        value = tab.run_js(
            "return (window[%s] && window[%s][%s]) || ''"
            % (
                json.dumps(global_name, ensure_ascii=False),
                json.dumps(global_name, ensure_ascii=False),
                json.dumps(key, ensure_ascii=False),
            )
        )
    except Exception:
        return ""
    return _as_nonempty_text(value)


def _set_tab_window_values(tab: Any, global_name: str, values: Mapping[str, str]) -> None:
    """Keep transient context on a retained page for sibling workers."""

    try:
        encoded = json.dumps(dict(values), ensure_ascii=False, separators=(",", ":"))
        tab.run_js(
            "window[%s] = Object.assign(window[%s] || {}, %s); return true"
            % (
                json.dumps(global_name, ensure_ascii=False),
                json.dumps(global_name, ensure_ascii=False),
                encoded,
            )
        )
    except Exception:
        # Caching is an optimization; a failed injection must not fail a
        # successful report capture.
        pass


class DrissionPageSessionProvider:
    """Attach to an already-running, manually logged-in Chrome session."""

    def __init__(
        self,
        browser_port: int,
        home_url: str = DEFAULT_SYCM_HOME_URL,
        *,
        platform_name: str = "生意参谋",
        expected_hosts: tuple[str, ...] = ("sycm.taobao.com",),
    ) -> None:
        if not 1 <= browser_port <= 65535:
            raise ValueError("--browser-port must be between 1 and 65535.")
        self.browser_port = browser_port
        self.home_url = home_url
        self.platform_name = platform_name
        self.expected_hosts = expected_hosts

    def read_session(self) -> RuntimeSession:
        browser, tab = _open_flow_tab(self.browser_port)
        existing = _find_existing_runtime_session(
            browser,
            tab,
            self.expected_hosts,
        )
        if existing is not None:
            browser.close_tab(tab)
            return existing
        try:
            _navigate_tab(tab, self.home_url, timeout=30)
            _wait_for_authenticated_tab(
                tab,
                platform_name=self.platform_name,
                timeout=30,
                expected_hosts=self.expected_hosts,
            )
            # MTop signing cookies can be scoped to a sibling Taobao domain.
            session = _runtime_session_from_tab(tab)
        except Exception:
            # Keep the tab open on failure so a user can finish login or inspect
            # the page before retrying. The next attempt creates a fresh tab.
            raise
        else:
            browser.close_tab(tab)
            return session


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
        browser, tab = _open_flow_tab(self.browser_port)
        captured_token = token
        should_capture = not captured_token
        capture_started = False

        # BYBT keeps its short-lived token in the already-loaded SYCM SPA.
        # Reuse that tab first so a second collector does not navigate or
        # attach another listener to the same business page.
        existing_tab = _find_existing_tab(
            browser,
            tab,
            ("sycm.taobao.com",),
        )
        if existing_tab is not None and should_capture:
            captured_token = _tab_local_storage_value(existing_tab, "jycmToken")
            should_capture = not captured_token
        if existing_tab is not None and captured_token:
            try:
                session = _runtime_session_from_tab(existing_tab)
            finally:
                browser.close_tab(tab)
            return SycmRuntimeContext(session=session, token=captured_token)

        if should_capture:
            tab.listen.start(
                targets=self.request_target,
                is_regex=True,
                method="GET",
            )
            capture_started = True
        try:
            _navigate_tab(tab, self.home_url, timeout=max(self.timeout, 1.0))
            _wait_for_authenticated_tab(
                tab,
                platform_name=self.platform_name,
                timeout=max(self.timeout, 1.0),
                expected_hosts=("sycm.taobao.com",),
            )
            if should_capture:
                for packet in tab.listen.steps(timeout=self.timeout):
                    captured_token = _extract_sycm_request_token(packet)
                    if captured_token:
                        break
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
                cookie_header=cookie_header,
                source="drissionpage",
                cookie_count=_cookie_count(cookie_header),
            ),
            token=captured_token,
        )
        browser.close_tab(tab)
        return context


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
        browser, tab, owns_tab = _open_reusable_flow_tab(
            self.browser_port, ("databank.tmall.com",)
        )
        if not owns_tab:
            try:
                session = _runtime_session_from_tab(tab)
                existing_csrf = csrf_token or _runtime_cookie_value_from_tab(
                    tab, "_tb_token_"
                )
            except RuntimeSessionUnavailable:
                existing_csrf = ""
                session = None
            if session is not None and existing_csrf:
                return DatabankRuntimeContext(session=session, csrf_token=existing_csrf)
        try:
            _navigate_tab(tab, self.home_url, timeout=max(self.timeout, 1.0))
            _wait_for_authenticated_tab(
                tab,
                platform_name="品牌数据银行",
                timeout=self.timeout,
            )
            cookies = tab.cookies(all_domains=True).as_dict()
            cookie_header = cookie_header_from_mapping(cookies)
            csrf_token = csrf_token or _runtime_cookie_value_from_tab(tab, "_tb_token_")
            if not csrf_token:
                raise RuntimeSessionUnavailable(
                    "品牌数据银行页面未提供 _tb_token_，请在采集标签页完成登录后重试。"
                )
            session = RuntimeSession(
                cookie_header=cookie_header,
                source="drissionpage",
                cookie_count=_cookie_count(cookie_header),
            )
            return_context = DatabankRuntimeContext(session=session, csrf_token=csrf_token)
        except Exception:
            raise
        else:
            return return_context


def _require_debug_browser(port: int) -> None:
    try:
        with urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.5) as response:
            if response.status != 200:
                raise RuntimeSessionUnavailable(
                    f"Chrome debugging endpoint returned HTTP {response.status} on port {port}."
                )
    except (OSError, URLError, socket.timeout) as exc:
        raise RuntimeSessionUnavailable(
            f"No Chrome remote-debugging session is listening on 127.0.0.1:{port}. "
            "Start the dedicated session browser, log in manually, then retry."
        ) from exc


def _validate_cookie_header(value: str) -> str:
    if "\r" in value or "\n" in value:
        raise RuntimeSessionUnavailable("Cookie headers cannot contain line breaks.")
    return value


def _cookie_count(value: str) -> int:
    return len([part for part in value.split(";") if part.strip()])


def _cookie_value(header: str, name: str) -> str:
    for part in header.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key == name:
            return value.strip()
    return ""


def _is_login_url(value: str) -> bool:
    lowered = value.lower()
    return "login" in lowered or "passport" in lowered


def _url_matches_hosts(value: str, hosts: tuple[str, ...]) -> bool:
    try:
        hostname = (urlparse(value).hostname or "").lower()
    except ValueError:
        return False
    return any(hostname == host or hostname.endswith(f".{host}") for host in hosts)


def _login_targets_platform(value: str, spec: _BrowserPlatformSpec) -> bool:
    decoded = unquote(value).lower()
    return _is_login_url(value) and any(host in decoded for host in spec.hosts)


def _platform_tab_session(
    tab: Any,
    spec: _BrowserPlatformSpec,
    *,
    assume_login_targets_platform: bool = False,
) -> BrowserPlatformSession:
    url = str(getattr(tab, "url", "") or "")
    if _is_login_url(url):
        targeted = assume_login_targets_platform or _login_targets_platform(url, spec)
        return BrowserPlatformSession(
            code=spec.code,
            name=spec.name,
            status="attention" if targeted else "offline",
            detail=(
                f"{spec.name}登录页已打开，请完成登录后再开始采集。"
                if targeted
                else f"尚未打开{spec.name}业务页面。"
            ),
            page_detected=targeted,
        )
    if not _url_matches_hosts(url, spec.hosts):
        return BrowserPlatformSession(
            code=spec.code,
            name=spec.name,
            status="offline",
            detail=f"尚未打开{spec.name}业务页面。",
        )
    if spec.code == "cps" and _cps_requires_primary_account(tab):
        return BrowserPlatformSession(
            code=spec.code,
            name=spec.name,
            status="attention",
            detail="CPS 已打开，但当前是子账号；请切换为主账号后重试。",
            page_detected=True,
        )
    try:
        cookies = tab.cookies(all_domains=True).as_dict()
        cookie_header = cookie_header_from_mapping(cookies)
        cookie_count = _cookie_count(cookie_header)
    except Exception:
        return BrowserPlatformSession(
            code=spec.code,
            name=spec.name,
            status="attention",
            detail=f"已进入{spec.name}页面，但未检测到可用登录会话，请重新登录。",
            page_detected=True,
        )
    return BrowserPlatformSession(
        code=spec.code,
        name=spec.name,
        status="healthy",
        detail=f"已进入{spec.name}业务页面并检测到登录会话。",
        page_detected=True,
        authenticated=True,
        cookie_detected=True,
        cookie_count=cookie_count,
    )


def inspect_browser_platform_sessions(browser_port: int) -> list[BrowserPlatformSession]:
    """Inspect existing tabs without navigating or exposing session material."""

    browser = DrissionPageBrowser(browser_port)
    results: list[BrowserPlatformSession] = []
    for spec in _BROWSER_PLATFORM_SPECS.values():
        tabs = _browser_tabs(browser, spec.hosts)
        probes = [_platform_tab_session(tab, spec) for tab in tabs]
        selected = next((item for item in probes if item.authenticated), None)
        if selected is None:
            selected = next((item for item in probes if item.page_detected), None)
        results.append(selected or BrowserPlatformSession(
            code=spec.code,
            name=spec.name,
            status="offline",
            detail=f"尚未打开{spec.name}业务页面。",
        ))
    return results


def open_browser_platform_session(
    browser_port: int,
    platform_code: str,
    *,
    timeout: float = 8.0,
    keep_open_on_success: bool = False,
) -> BrowserPlatformSession:
    """Open a fresh platform tab and quickly verify page arrival and login.

    Failed probes intentionally remain open so the user can finish login or
    inspect an account/permission page. Successful worker-owned tabs are
    closed unless the caller explicitly wants to leave the business page open.
    """

    try:
        spec = _BROWSER_PLATFORM_SPECS[platform_code]
    except KeyError as exc:
        raise ValueError(f"Unsupported collection platform: {platform_code}") from exc

    browser, tab = _open_flow_tab(browser_port)
    existing = _find_existing_platform_session(browser, tab, spec)
    if existing is not None:
        browser.close_tab(tab)
        return existing

    try:
        _navigate_tab(tab, spec.home_url, timeout=timeout)
        deadline = time.monotonic() + max(1.0, timeout)
        probe = _platform_tab_session(
            tab,
            spec,
            assume_login_targets_platform=True,
        )
        while (
            not probe.authenticated
            and probe.status == "offline"
            and time.monotonic() < deadline
        ):
            try:
                tab.wait(0.25)
            except Exception:
                time.sleep(0.25)
            probe = _platform_tab_session(
                tab,
                spec,
                assume_login_targets_platform=True,
            )
    except RuntimeSessionUnavailable:
        # A failed navigation is actionable in the visible tab. Keep it open.
        raise
    except Exception as exc:
        raise RuntimeSessionUnavailable(
            f"{spec.name}页面打开失败，请检查网络或在已打开的标签页中确认页面状态后重试。"
        ) from exc
    if probe.authenticated and not keep_open_on_success:
        browser.close_tab(tab)
    return probe


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
        browser, tab, owns_tab = _open_reusable_flow_tab(
            self.browser_port, ("one.alimama.com",)
        )
        captured_csrf = csrf_id
        captured_login_point = login_point_id
        should_capture = not captured_csrf or not captured_login_point
        capture_started = False

        # When the caller already has the one-time report parameters, an
        # existing Alimama tab only needs to provide its authenticated Cookie.
        # This is the common path for the second and later promotion workers.
        if not owns_tab:
            if should_capture:
                captured_csrf = captured_csrf or _tab_window_value(
                    tab, ALIMAMA_RUNTIME_GLOBAL, "csrfId"
                )
                captured_login_point = captured_login_point or _tab_window_value(
                    tab, ALIMAMA_RUNTIME_GLOBAL, "loginPointId"
                )
                should_capture = not captured_csrf or not captured_login_point
            if not should_capture:
                session = _runtime_session_from_tab(tab)
                return AlimamaRuntimeContext(
                    session=session,
                    csrf_id=captured_csrf,
                    login_point_id=captured_login_point,
                )

        if should_capture:
            tab.listen.start(
                targets=r"one\.alimama\.com/report/query",
                is_regex=True,
                method="POST",
            )
            capture_started = True
        try:
            if owns_tab:
                _navigate_tab(tab, self.report_home_url, timeout=max(self.timeout, 1.0))
            _wait_for_authenticated_tab(
                tab,
                platform_name="阿里妈妈",
                timeout=max(self.timeout, 1.0),
                expected_hosts=("one.alimama.com",),
            )

            if should_capture:
                for packet in tab.listen.steps(timeout=self.timeout):
                    request_csrf, request_login_point = _extract_alimama_request_context(packet)
                    captured_csrf = captured_csrf or request_csrf
                    captured_login_point = captured_login_point or request_login_point
                    if captured_csrf and captured_login_point:
                        break
        finally:
            if capture_started:
                tab.listen.stop()

        if not captured_csrf or not captured_login_point:
            raise RuntimeSessionUnavailable(
                "Alimama report parameters were not observed. Open the report page in the attached browser, "
                "confirm the account is logged in, and retry."
            )

        cookie_header = cookie_header_from_mapping(tab.cookies(all_domains=True).as_dict())
        session = RuntimeSession(
            cookie_header=cookie_header,
            source="drissionpage",
            cookie_count=_cookie_count(cookie_header),
        )
        context = AlimamaRuntimeContext(
            session=session,
            csrf_id=captured_csrf,
            login_point_id=captured_login_point,
        )
        # Keep the first report tab open so item/content sibling workers can
        # reuse this page and its transient request parameters.
        _set_tab_window_values(
            tab,
            ALIMAMA_RUNTIME_GLOBAL,
            {"csrfId": captured_csrf, "loginPointId": captured_login_point},
        )
        return context


def _extract_alimama_request_context(packet: Any) -> tuple[str, str]:
    """Read the values already emitted by Alimama's own report request."""

    request = getattr(packet, "request", None)
    if request is None:
        return "", ""
    params = getattr(request, "params", {}) or {}
    post_data = getattr(request, "postData", {}) or {}
    if not isinstance(params, Mapping):
        params = {}
    if not isinstance(post_data, Mapping):
        post_data = {}
    csrf_id = _as_nonempty_text(params.get("csrfId") or post_data.get("csrfId"))
    login_point_id = _as_nonempty_text(
        params.get("loginPointId") or post_data.get("loginPointId")
    )
    return csrf_id, login_point_id


def _as_nonempty_text(value: object) -> str:
    return str(value).strip() if value is not None else ""


class DrissionPageBrandSearchSessionProvider:
    """Capture the PZ report query and session from a logged-in browser."""

    def __init__(self, browser_port: int, report_home_url: str, timeout: float) -> None:
        if not 1 <= browser_port <= 65535:
            raise ValueError("--browser-port must be between 1 and 65535.")
        if timeout <= 0:
            raise ValueError("Brand-search request capture timeout must be positive.")
        self.browser_port = browser_port
        self.report_home_url = report_home_url
        self.timeout = timeout

    def read_context(self, *, csrf_id: str = "") -> BrandSearchRuntimeContext:
        browser, tab = _open_flow_tab(self.browser_port)
        captured_csrf = csrf_id
        captured_params: dict[str, str] = {}
        existing_tab = _find_existing_tab(
            browser,
            tab,
            ("branding.taobao.com", "brandsearch.taobao.com"),
        )
        if existing_tab is not None and captured_csrf:
            session = _runtime_session_from_tab(existing_tab)
            browser.close_tab(tab)
            return BrandSearchRuntimeContext(
                session=session,
                csrf_id=captured_csrf,
                query_params={
                    "r": "mx_548",
                    "attribution": "impression",
                    "effectConversionCycle": "30",
                    "trafficType": "[1,2,4,5]",
                    "csrfID": captured_csrf,
                },
            )
        tab.listen.start(
            targets=r"brandsearch\.taobao\.com/report/query/rptAdvertiserSubListNew\.json",
            is_regex=True,
            method="GET",
        )
        try:
            _navigate_tab(tab, self.report_home_url, timeout=max(self.timeout, 1.0))
            _wait_for_authenticated_tab(
                tab,
                platform_name="品销宝品牌专区",
                timeout=max(self.timeout, 1.0),
                expected_hosts=("branding.taobao.com", "brandsearch.taobao.com"),
            )

            for packet in tab.listen.steps(timeout=self.timeout):
                request_csrf, request_params = _extract_brandsearch_request_context(packet)
                if request_csrf:
                    captured_csrf = captured_csrf or request_csrf
                    captured_params = request_params
                    break
        finally:
            tab.listen.stop()

        if not captured_csrf:
            raise RuntimeSessionUnavailable(
                "PZ csrfID was not observed. Open the 品销宝品牌专区报表 in the attached browser and retry."
            )

        captured_params["csrfID"] = captured_csrf
        cookie_header = cookie_header_from_mapping(tab.cookies(all_domains=True).as_dict())
        session = RuntimeSession(
            cookie_header=cookie_header,
            source="drissionpage",
            cookie_count=_cookie_count(cookie_header),
        )
        context = BrandSearchRuntimeContext(
            session=session,
            csrf_id=captured_csrf,
            query_params=captured_params,
        )
        browser.close_tab(tab)
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
    return _as_nonempty_text(normalized.get("csrfID")), normalized


class DrissionPageCpsSessionProvider:
    """Capture CPS request parameters from a logged-in primary Alimama account."""

    def __init__(self, browser_port: int, report_home_url: str, timeout: float) -> None:
        if not 1 <= browser_port <= 65535:
            raise ValueError("--browser-port must be between 1 and 65535.")
        if timeout <= 0:
            raise ValueError("CPS request capture timeout must be positive.")
        self.browser_port = browser_port
        self.report_home_url = report_home_url
        self.timeout = timeout

    def read_context(self, *, tb_token: str = "") -> CpsRuntimeContext:
        browser, tab, owns_tab = _open_reusable_flow_tab(
            self.browser_port, ("ad.alimama.com",)
        )
        captured_token = tb_token
        should_capture = not captured_token
        capture_started = False

        # The CPS page exposes the same short-lived token as a cookie.  A
        # previously opened report tab is therefore enough for all CPS child
        # jobs; request listening remains a fallback for fresh sessions.
        if not owns_tab:
            if _cps_requires_primary_account(tab):
                browser.close_tab(tab)
                raise RuntimeSessionUnavailable(
                    "CPS 暂不支持当前子账号，请在采集浏览器中切换为主账号后重试。"
                )
            try:
                session = _runtime_session_from_tab(tab)
                captured_token = captured_token or _runtime_cookie_value_from_tab(tab, "_tb_token_")
            except RuntimeSessionUnavailable:
                session = None
            if session is not None and captured_token:
                return CpsRuntimeContext(session=session, tb_token=captured_token)

        if should_capture:
            tab.listen.start(
                targets=r"ad\.alimama\.com/openapi/param2/1/gateway\.unionadv/data\.home\.overview\.json",
                is_regex=True,
                method="GET",
            )
            capture_started = True
        try:
            _navigate_tab(tab, self.report_home_url, timeout=max(self.timeout, 1.0))
            _wait_for_authenticated_tab(
                tab,
                platform_name="淘宝客 CPS",
                timeout=max(self.timeout, 1.0),
                expected_hosts=("ad.alimama.com",),
            )
            if _cps_requires_primary_account(tab):
                raise RuntimeSessionUnavailable(
                    "CPS 暂不支持当前子账号，请在采集浏览器中切换为商家主账号后重试。"
                )

            if should_capture:
                for packet in tab.listen.steps(timeout=self.timeout):
                    captured_token = _extract_cps_request_token(packet)
                    if captured_token:
                        break
        finally:
            if capture_started:
                tab.listen.stop()

        if not captured_token:
            raise RuntimeSessionUnavailable(
                "CPS 页面已打开，但没有捕获到有效报表会话。请确认主账号已登录、"
                "页面可以正常显示报表，然后重试。"
            )

        cookie_header = cookie_header_from_mapping(tab.cookies(all_domains=True).as_dict())
        session = RuntimeSession(
            cookie_header=cookie_header,
            source="drissionpage",
            cookie_count=_cookie_count(cookie_header),
        )
        context = CpsRuntimeContext(session=session, tb_token=captured_token)
        # Retain the first CPS report tab so later CPS retries reuse its
        # session without another navigation. The browser is user-owned and
        # will clean up the tab when the user closes it.
        return context


class DrissionPageUtrySessionProvider:
    """Capture U先 Quark widget requests emitted by the logged-in report page."""

    REQUIRED_REPORT_IDS = {1904974, 1906730}

    def __init__(self, browser_port: int, report_home_url: str, timeout: float) -> None:
        if not 1 <= browser_port <= 65535:
            raise ValueError("--browser-port must be between 1 and 65535.")
        if timeout <= 0:
            raise ValueError("U先 request capture timeout must be positive.")
        self.browser_port = browser_port
        self.report_home_url = report_home_url
        self.timeout = timeout

    def read_context(self) -> UtryRuntimeContext:
        browser, tab, owns_tab = _open_reusable_flow_tab(
            self.browser_port, ("tmesh.tmall.com",)
        )
        templates: dict[int, UtryReportTemplate] = {}
        # The U先 parent app can resolve several Quark report URLs in one
        # MTop request. Each URL contains the server-issued QUARK_PARAMS for the
        # current login session. Going directly to those URLs avoids opening
        # two parent pages and refreshing two already-loaded iframes.
        try:
            if owns_tab:
                _navigate_tab(tab, self.report_home_url, timeout=max(self.timeout, 1.0))
            _wait_for_authenticated_tab(
                tab,
                platform_name="U先",
                timeout=max(self.timeout, 1.0),
            )
            report_urls = _resolve_utry_dashboard_urls(
                tab,
                report_ids=self.REQUIRED_REPORT_IDS,
                timeout=self.timeout,
            )
        except RuntimeSessionUnavailable:
            report_urls = {}

        templates.update(
            _capture_utry_templates_concurrently(
                browser,
                report_urls=report_urls,
                timeout=self.timeout,
            )
        )

        # Keep the former parent-page capture as a compatibility fallback if
        # Alibaba changes the MTop response shape or blocks the batched call.
        for report_id in sorted(self.REQUIRED_REPORT_IDS - templates.keys()):
            template = _capture_utry_template_from_parent_page(
                tab,
                report_id=report_id,
                timeout=self.timeout,
            )
            if template is not None:
                templates[report_id] = template

        missing = sorted(self.REQUIRED_REPORT_IDS - templates.keys())
        if missing:
            raise RuntimeSessionUnavailable(
                "U先 report templates were not observed. Missing reportId: "
                + ", ".join(str(value) for value in missing)
                + ". Open the corresponding 派样/复购 report page and retry."
            )
        cookie_header = cookie_header_from_mapping(tab.cookies(all_domains=True).as_dict())
        context = UtryRuntimeContext(
            session=RuntimeSession(
                cookie_header=cookie_header,
                source="drissionpage",
                cookie_count=_cookie_count(cookie_header),
            ),
            templates=templates,
        )
        # Keep the parent report tab available for subsequent retries. The
        # two short-lived Quark capture tabs are still closed by their worker.
        return context


def _resolve_utry_dashboard_urls(
    tab: Any,
    *,
    report_ids: set[int],
    timeout: float,
) -> dict[int, str]:
    """Resolve all Quark iframe URLs with one session-scoped MTop request."""

    requested = {str(report_id): "" for report_id in sorted(report_ids)}
    requested_json = json.dumps(requested, ensure_ascii=False, separators=(",", ":"))
    api_json = json.dumps(UTRY_DASHBOARD_LIST_API)
    result_name_json = json.dumps(UTRY_DASHBOARD_RESULT_GLOBAL)
    script = f"""
const resultName = {result_name_json};
window[resultName] = null;
const mtop = window.lib && window.lib.mtop;
if (!mtop || typeof mtop.request !== 'function') {{
  window[resultName] = {{ok: false, error: 'lib.mtop unavailable'}};
  return false;
}}
mtop.request({{
  api: {api_json},
  v: '1.0',
  data: {{fbiReportInfos: {json.dumps(requested_json)}}}
}}).then(function(response) {{
  window[resultName] = {{ok: true, response: response}};
}}).catch(function(error) {{
  window[resultName] = {{ok: false, error: String(error)}};
}});
return true;
"""
    try:
        tab.run_js(script, timeout=min(timeout, 10))
    except Exception as exc:
        raise RuntimeSessionUnavailable("U先批量报表初始化调用失败。") from exc

    deadline = time.monotonic() + timeout
    result: Any = None
    try:
        while time.monotonic() < deadline:
            try:
                result = tab.run_js(f"return window[{result_name_json}]")
            except Exception as exc:
                raise RuntimeSessionUnavailable("U先批量报表初始化结果不可读。") from exc
            if result:
                break
            try:
                tab.wait(0.1)
            except Exception:
                time.sleep(0.1)
    finally:
        try:
            tab.run_js(f"delete window[{result_name_json}]")
        except Exception:
            pass

    if not isinstance(result, Mapping) or not result.get("ok"):
        raise RuntimeSessionUnavailable("U先批量报表初始化未返回可用结果。")
    return _extract_utry_dashboard_urls(result.get("response"), report_ids=report_ids)


def _extract_utry_dashboard_urls(
    response: Any,
    *,
    report_ids: set[int],
) -> dict[int, str]:
    """Extract Quark URLs without exposing their session-scoped parameters."""

    if not isinstance(response, Mapping):
        raise RuntimeSessionUnavailable("U先批量报表初始化响应格式无效。")
    outer_data = response.get("data")
    if not isinstance(outer_data, Mapping):
        raise RuntimeSessionUnavailable("U先批量报表初始化响应缺少 data。")
    entries = outer_data.get("data")
    if not isinstance(entries, Mapping):
        raise RuntimeSessionUnavailable("U先批量报表初始化响应缺少报表映射。")

    urls: dict[int, str] = {}
    for report_id in sorted(report_ids):
        entry = entries.get(str(report_id))
        if not isinstance(entry, Mapping):
            continue
        report_url = _as_nonempty_text(entry.get("data"))
        if not report_url.startswith("https://quark.taobao.com/"):
            continue
        if f"id={report_id}" not in report_url or "QUARK_PARAMS=" not in report_url:
            continue
        urls[report_id] = report_url
    if not urls:
        raise RuntimeSessionUnavailable("U先批量报表初始化未返回 Quark 地址。")
    return urls


def _capture_utry_template_from_direct_url(
    tab: Any,
    *,
    report_id: int,
    report_url: str,
    timeout: float,
) -> UtryReportTemplate | None:
    """Capture one report request while loading its Quark URL only once."""

    tab.listen.start(targets="fbi", is_regex=True, method="POST")
    try:
        _navigate_tab(tab, report_url, timeout=max(timeout, 1.0))
        _wait_for_authenticated_tab(
            tab,
            platform_name="U先",
            timeout=max(timeout, 1.0),
        )
        for packet in tab.listen.steps(timeout=timeout):
            template = _extract_utry_request_template(packet)
            if template is not None and template.report_id == report_id:
                return template
    finally:
        tab.listen.stop()
    return None


def _capture_utry_templates_concurrently(
    browser: DrissionPageBrowser,
    *,
    report_urls: Mapping[int, str],
    timeout: float,
) -> dict[int, UtryReportTemplate]:
    """Load independent Quark reports in parallel to reduce wall-clock time."""

    if not report_urls:
        return {}

    def capture(item: tuple[int, str]) -> UtryReportTemplate | None:
        report_id, report_url = item
        tab = browser.new_tab()
        try:
            return _capture_utry_template_from_direct_url(
                tab,
                report_id=report_id,
                report_url=report_url,
                timeout=timeout,
            )
        finally:
            browser.close_tab(tab)

    templates: dict[int, UtryReportTemplate] = {}
    worker_count = min(len(report_urls), 2)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(capture, item): item[0]
            for item in sorted(report_urls.items())
        }
        for future in as_completed(futures):
            try:
                template = future.result()
            except Exception:
                continue
            if template is not None:
                templates[template.report_id] = template
    return templates


def _capture_utry_template_from_parent_page(
    tab: Any,
    *,
    report_id: int,
    timeout: float,
) -> UtryReportTemplate | None:
    """Compatibility path used when batched Quark URL resolution fails."""

    _navigate_tab(tab, UTRY_REPORT_URLS[report_id], timeout=max(timeout, 1.0))
    _wait_for_authenticated_tab(
        tab,
        platform_name="U先",
        timeout=max(timeout, 1.0),
    )
    frame = _find_utry_frame(tab, timeout=timeout)
    if frame is None:
        return None
    frame.listen.start(targets="fbi", is_regex=True, method="POST")
    try:
        frame.refresh()
        for packet in frame.listen.steps(timeout=timeout):
            template = _extract_utry_request_template(packet)
            if template is not None and template.report_id == report_id:
                return template
    finally:
        frame.listen.stop()
    return None


def _find_utry_frame(tab: Any, *, timeout: float) -> Any | None:
    """Return the Quark report iframe after the parent page has navigated."""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for frame in tab.get_frames():
            if str(getattr(frame, "url", "") or "").startswith("https://quark.taobao.com/"):
                return frame
        try:
            tab.wait(0.25)
        except Exception:
            pass
    return None


def _extract_utry_request_template(packet: Any) -> UtryReportTemplate | None:
    request = getattr(packet, "request", None)
    if request is None:
        return None
    post_data = getattr(request, "postData", "") or ""
    if isinstance(post_data, Mapping):
        encoded_params = post_data.get("params")
    else:
        form = parse_qs(str(post_data), keep_blank_values=True)
        encoded_params = form.get("params", [None])[0]
    if not encoded_params:
        return None
    try:
        params = json.loads(str(encoded_params))
        report_id = int(params.get("reportId"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    headers = getattr(request, "headers", {}) or {}
    referer = ""
    if isinstance(headers, Mapping):
        referer = _as_nonempty_text(headers.get("referer") or headers.get("Referer"))
    return UtryReportTemplate(
        report_id=report_id,
        request_url=_as_nonempty_text(getattr(request, "url", "")) or UTRY_WIDGET_URL,
        referer=referer,
        params=params,
    )


def _extract_cps_request_token(packet: Any) -> str:
    """Read the short-lived token already emitted by the CPS overview request."""

    request = getattr(packet, "request", None)
    if request is None:
        return ""
    params = getattr(request, "params", {}) or {}
    post_data = getattr(request, "postData", {}) or {}
    if not isinstance(params, Mapping):
        params = {}
    if not isinstance(post_data, Mapping):
        post_data = {}
    return _as_nonempty_text(params.get("_tb_token_") or post_data.get("_tb_token_"))


def _extract_sycm_request_token(packet: Any) -> str:
    """Read the transient token emitted by an authenticated SYCM request."""

    request = getattr(packet, "request", None)
    if request is None:
        return ""
    params = getattr(request, "params", {}) or {}
    if not isinstance(params, Mapping):
        return ""
    return _as_nonempty_text(params.get("token"))


def _cps_requires_primary_account(tab: Any) -> bool:
    """CPS renders this server-side when the current login is a subaccount."""

    try:
        page_html = str(tab.html or "")
    except Exception:
        return False
    return "暂不支持子账号访问" in page_html
