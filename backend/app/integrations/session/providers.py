"""Generic DrissionPage helpers shared by all platform providers.

These functions live in their own module so that platform-specific providers
in `session/alimama.py`, `session/sycm.py`, etc. can import them without
creating a circular dependency on `tmall_session`.
"""

from __future__ import annotations

import json
import time
from typing import Any, Mapping
from urllib.parse import unquote
from urllib.request import urlopen

from app.integrations.session.core import (
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


def _open_flow_tab(browser_port: int) -> tuple[DrissionPageBrowser, Any]:
    browser = DrissionPageBrowser(browser_port)
    return browser, browser.new_tab()


def _browser_tabs(browser: DrissionPageBrowser, expected_hosts: tuple[str, ...] = ()) -> list[Any]:
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
    try:
        browser = DrissionPageBrowser(browser_port)
    except RuntimeSessionUnavailable as original_error:
        try:
            browser, tab = _open_flow_tab(browser_port)
        except Exception:
            raise original_error
        return browser, tab, True
    existing = _find_existing_tab(browser, None, expected_hosts)
    if existing is not None:
        return browser, existing, False
    return browser, browser.new_tab(), True


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


def _login_targets_platform(value: str, spec: PlatformSpec) -> bool:
    decoded = unquote(value).lower()
    return _is_login_url(value) and any(host in decoded for host in spec.hosts)


def _platform_tab_session(
    tab: Any,
    spec: PlatformSpec,
    *,
    assume_login_targets_platform: bool = False,
) -> Any:
    from app.integrations.session.core import BrowserPlatformSession

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
        from app.integrations.session.helpers import (
            _navigate_tab,
            _open_reusable_flow_tab,
            _runtime_session_from_tab,
            _wait_for_authenticated_tab,
        )
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
