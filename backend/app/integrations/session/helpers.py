"""Generic navigation/cookie helpers shared by platform providers.

This module centralises the DrissionPage-specific helpers so that
`session/alimama.py`, `session/sycm.py`, `session/databank.py`,
`session/cps.py`, `session/brandsearch.py` and `session/utry.py` can
import them without dragging in the full `tmall_session` god-file.
"""

from __future__ import annotations

import json
import time
from typing import Any, Mapping
from urllib.request import urlopen

from app.integrations.session.core import (
    BrowserPlatformSession,
    DrissionPageBrowser,
    PlatformSpec,
    RuntimeSession,
    RuntimeSessionUnavailable,
    _cookie_count,
    _cookie_value,
    _is_login_url,
    _url_matches_hosts,
    cookie_header_from_mapping,
)


def _open_flow_tab(
    browser_port: int,
    initial_url: str | None = None,
) -> tuple[DrissionPageBrowser, Any]:
    browser = DrissionPageBrowser(browser_port)
    return browser, browser.new_tab(initial_url)


def _browser_tabs(browser: DrissionPageBrowser, expected_hosts: tuple[str, ...] = ()) -> list[Any]:
    """Resolve live tabs, avoiding a fragile ``get_tab`` call per candidate.

    ``Chromium.get_tab`` opens a websocket per tab and can hang forever on the
    second call (DrissionPage 4.1.1.4) while the browser is busy, which used to
    stall every ``drissionpage`` session resolve.  Callers here only need one
    usable tab, so resolve it through ``DrissionPageBrowser.find_tab`` and wrap
    the result in a list to keep the existing contract.
    """

    tab = browser.find_tab(expected_hosts)
    return [tab] if tab is not None else []


def _open_reusable_flow_tab(
    browser_port: int,
    expected_hosts: tuple[str, ...],
) -> tuple[DrissionPageBrowser, Any, bool]:
    initial_url = _initial_url_for_hosts(expected_hosts)
    try:
        browser = DrissionPageBrowser(browser_port)
    except RuntimeSessionUnavailable as original_error:
        try:
            browser, tab = _open_flow_tab(browser_port, initial_url)
        except Exception:
            raise original_error
        return browser, tab, True
    existing = _find_existing_tab(browser, None, expected_hosts)
    if existing is not None:
        return browser, existing, False
    return browser, browser.new_tab(initial_url), True


def _initial_url_for_hosts(expected_hosts: tuple[str, ...]) -> str | None:
    """Return a direct first navigation for a known business domain.

    The page-specific providers still perform their own navigation/reload
    after listeners are ready.  This initial URL only prevents Chrome from
    presenting a visible blank tab while the provider is attaching.
    """
    hosts = set(expected_hosts)
    if "sycm.taobao.com" in hosts:
        return "https://sycm.taobao.com/portal/home.htm"
    if "ad.alimama.com" in hosts:
        return "https://ad.alimama.com/portal/v2/report/promotionDataPage.htm"
    if "one.alimama.com" in hosts:
        return "https://one.alimama.com/index.html#!/report/campaign?rptType=campaign"
    if "databank.tmall.com" in hosts:
        return "https://databank.tmall.com/"
    if {"branding.taobao.com", "brandsearch.taobao.com"} & hosts:
        return "https://branding.taobao.com/#!/report/index?productid=101005201"
    if "tmesh.tmall.com" in hosts:
        return "https://tmesh.tmall.com/utry/samplePlatform/common_data_board?id=1904810"
    return None


def _find_existing_tab(browser: Any, current_tab: Any, expected_hosts: tuple[str, ...]) -> Any | None:
    tabs = _browser_tabs(browser, expected_hosts)
    for candidate in tabs:
        if candidate is current_tab:
            continue
        url = str(getattr(candidate, "url", "") or "")
        if _is_login_url(url) or not _url_matches_hosts(url, expected_hosts):
            continue
        return candidate
    return None


def _tab_cookie_count(target: Any) -> int:
    """Best-effort cookie count for a tab; never raises."""
    try:
        cookies = target.cookies(all_domains=True).as_dict()
    except Exception:
        try:
            cookies = target.cookies().as_dict()
        except Exception:
            return 0
    try:
        return len([value for value in cookies.values() if str(value).strip()])
    except Exception:
        return 0


def _platform_tab_session(
    target: Any,
    spec: PlatformSpec,
    *,
    assume_login_targets_platform: bool = False,
) -> BrowserPlatformSession:
    """Secret-free probe of one tab against one platform spec.

    ``target`` is a DrissionPage tab (a ``DrissionPageBrowser`` may be passed by
    callers that only have the wrapper; it simply reports ``offline``).
    """
    # ChromiumTab itself has a ``browser`` attribute; the wrapper has no URL.
    url = _as_nonempty_text(getattr(target, "url", ""))
    on_platform = bool(url) and _url_matches_hosts(url, spec.hosts)
    login_page = bool(url) and _is_login_url(url)

    if login_page and assume_login_targets_platform:
        # A login redirect still proves the platform tab is the right one.
        page_detected = True
    else:
        page_detected = on_platform

    authenticated = page_detected and not login_page
    cookie_count = _tab_cookie_count(target) if url else 0

    if authenticated:
        status = "authenticated"
        detail = f"{spec.name}页面已登录，可直接采集。"
    elif page_detected:
        status = "login_required"
        detail = f"{spec.name}页面已打开，但会话未登录，请在该标签页完成登录后重试。"
    else:
        status = "offline"
        detail = f"尚未打开{spec.name}业务页面。"

    return BrowserPlatformSession(
        code=spec.code,
        name=spec.name,
        status=status,
        detail=detail,
        page_detected=page_detected,
        authenticated=authenticated,
        cookie_detected=cookie_count > 0,
        cookie_count=cookie_count,
    )


def _wait_for_authenticated_tab(
    tab: Any,
    *,
    platform_name: str,
    timeout: float,
    expected_hosts: tuple[str, ...] = (),
) -> None:
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


def _navigate_tab(tab: Any, url: str, *, timeout: float) -> None:
    navigation_timeout = max(1.0, float(timeout))
    if hasattr(tab, "run_cdp"):
        try:
            tab.run_cdp("Page.navigate", url=url)
            return
        except Exception as exc:
            raise RuntimeSessionUnavailable("采集页面导航请求失败，请检查浏览器网络后重试。") from exc
    try:
        tab.get(url, timeout=navigation_timeout)
    except TypeError as exc:
        if "timeout" not in str(exc).lower():
            raise
        tab.get(url)


def _reload_tab(tab: Any, *, timeout: float) -> None:
    navigation_timeout = max(1.0, float(timeout))
    if hasattr(tab, "run_cdp"):
        try:
            tab.run_cdp("Page.reload", ignoreCache=True)
            return
        except Exception:
            pass
    try:
        tab.refresh(timeout=navigation_timeout)
    except TypeError as exc:
        if "timeout" not in str(exc).lower():
            raise
        tab.refresh()
    except Exception as exc:
        raise RuntimeSessionUnavailable("采集页面刷新失败，请检查浏览器网络后重试。") from exc


def _runtime_session_from_tab(tab: Any) -> RuntimeSession:
    cookies = tab.cookies(all_domains=True).as_dict()
    cookie_header = cookie_header_from_mapping(cookies)
    return RuntimeSession(
        cookie_header=cookie_header,
        source="drissionpage",
        cookie_count=_cookie_count(cookie_header),
    )


def browser_cookie_headers_for_urls(
    browser_port: int,
    urls: tuple[str, ...],
    *,
    expected_hosts: tuple[str, ...],
) -> dict[str, str]:
    """Read Chrome's domain-scoped cookies without opening or navigating tabs."""
    browser = DrissionPageBrowser(browser_port)
    tab = browser.find_tab(expected_hosts) or browser.find_tab(())
    if tab is None:
        raise RuntimeSessionUnavailable("没有可复用的采集浏览器标签页，请先登录淘宝。")
    headers: dict[str, str] = {}
    for url in urls:
        try:
            records = tab.run_cdp("Network.getCookies", urls=[url]).get("cookies", [])
            cookies = {record["name"]: record["value"] for record in records}
            headers[url] = cookie_header_from_mapping(cookies)
        except Exception as exc:
            raise RuntimeSessionUnavailable("无法读取目标域的千牛会话 Cookie，请确认登录状态。") from exc
    return headers


def request_cookie_headers_for_urls(
    *,
    source: str,
    cookie_env: str,
    browser_port: int,
    urls: tuple[str, ...],
    expected_hosts: tuple[str, ...],
) -> dict[str, str]:
    """Resolve an explicit env override or Chrome's cookies for each request URL."""
    if source == "env":
        from app.integrations.session.core import resolve_runtime_session

        header = resolve_runtime_session(source="env", cookie_env=cookie_env).cookie_header
        return {url: header for url in urls}
    if source == "drissionpage":
        return browser_cookie_headers_for_urls(browser_port, urls, expected_hosts=expected_hosts)
    raise ValueError(f"Unsupported session source: {source}")


def _runtime_cookie_value_from_tab(tab: Any, name: str) -> str:
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


def _tab_local_storage_value(tab: Any, key: str) -> str:
    try:
        value = tab.run_js(f"return localStorage.getItem({json.dumps(key, ensure_ascii=False)})")
    except Exception:
        return ""
    return _as_nonempty_text(value)


def _tab_window_value(tab: Any, global_name: str, key: str) -> str:
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
        pass


def _as_nonempty_text(value: object) -> str:
    return str(value).strip() if value is not None else ""


# ---- generic provider ----

class DrissionPageSessionProvider:
    """Attach to an already-running, manually logged-in Chrome session."""

    def __init__(
        self,
        browser_port: int,
        home_url: str = "https://sycm.taobao.com/portal/home.htm",
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
        browser, tab, owns_tab = _open_reusable_flow_tab(
            self.browser_port, self.expected_hosts
        )
        if not owns_tab:
            try:
                return _runtime_session_from_tab(tab)
            except RuntimeSessionUnavailable:
                pass
        try:
            _navigate_tab(tab, self.home_url, timeout=30)
            _wait_for_authenticated_tab(
                tab,
                platform_name=self.platform_name,
                timeout=30,
                expected_hosts=self.expected_hosts,
            )
            session = _runtime_session_from_tab(tab)
        except Exception:
            raise
        else:
            browser.close_tab(tab)
            return session
