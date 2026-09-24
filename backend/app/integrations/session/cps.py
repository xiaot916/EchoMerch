"""CPS (ad.alimama.com) session context with short-lived `_tb_token_`."""

from __future__ import annotations

import os
import json
import threading
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urlparse

from app.integrations.session.core import (
    DEFAULT_DEBUG_PORT,
    RuntimeSession,
    RuntimeSessionUnavailable,
    _cookie_count,
    cookie_header_from_mapping,
    resolve_runtime_session,
)

DEFAULT_CPS_REPORT_HOME_URL = (
    "https://ad.alimama.com/portal/v2/report/promotionDataPage.htm"
)
# CPS 总览（data.home.overview.json）与商品明细（analysis.data.itemAnalysisTopList.json）
# 都挂在 unionadv 网关下；商品明细 referer 必须是商品分析列表页。
CPS_OVERVIEW_URL = (
    "https://ad.alimama.com/openapi/param2/1/gateway.unionadv/data.home.overview.json"
)
CPS_ITEM_ANALYSIS_URL = (
    "https://ad.alimama.com/openapi/param2/1/gateway.unionadv/"
    "analysis.data.itemAnalysisTopList.json"
)
CPS_ITEM_LIST_REFERER = (
    "https://ad.alimama.com/portal/v2/report/item/list.htm"
)


def browser_fallback_port(source: str, port: int) -> int | None:
    """Only the managed browser source (or its batch snapshot) may fall back."""
    value = str(port) if source == "drissionpage" else os.getenv("ECHO_BATCH_CPS_BROWSER_PORT", "")
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if 1 <= parsed <= 65535 else None


def fetch_cps_browser_json(
    browser_port: int, endpoint_url: str, params: Mapping[str, str], *, timeout: int = 30,
) -> tuple[int, bytes]:
    """Read a CPS report in its existing same-origin tab when direct HTTP is rejected."""
    from app.integrations.session.core import DrissionPageBrowser

    endpoint = urlparse(endpoint_url)
    allowed_paths = {urlparse(url).path for url in (CPS_OVERVIEW_URL, CPS_ITEM_ANALYSIS_URL)}
    if endpoint.scheme != "https" or endpoint.hostname != "ad.alimama.com" or endpoint.path not in allowed_paths:
        raise ValueError("CPS 浏览器回退只支持已登记的只读报表接口")
    tab = DrissionPageBrowser(browser_port).find_tab(("ad.alimama.com",))
    if tab is None:
        raise RuntimeSessionUnavailable("CPS 浏览器回退需要已打开的淘宝客报表标签页。")

    # The token is read inside the first-party page; it is never returned to
    # Python, inserted into a command line, or persisted by the fallback.
    safe_params = {key: value for key, value in params.items() if key != "_tb_token_"}
    script = """(async () => {
      const token = document.cookie.split('; ').find(part => part.startsWith('_tb_token_='))?.slice(11);
      if (!token) return {error: 'missing_token'};
      const query = new URLSearchParams(%s);
      query.set('_tb_token_', decodeURIComponent(token));
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), %d);
      try {
        const response = await fetch(%s + '?' + query, {
          credentials: 'include', signal: controller.signal,
        });
        return {status: response.status, body: await response.text()};
      } catch (_) { return {error: 'request_failed'}; }
      finally { clearTimeout(timer); }
    })()""" % (json.dumps(safe_params), max(1000, timeout * 1000), json.dumps(endpoint.path))
    result: list[Any] = []

    def evaluate() -> None:
        try:
            result.append(tab.run_cdp("Runtime.evaluate", expression=script, awaitPromise=True, returnByValue=True))
        except Exception:
            result.append(None)

    worker = threading.Thread(target=evaluate, daemon=True, name="cps-browser-fetch")
    worker.start()
    worker.join(timeout=max(1, timeout) + 5)
    if worker.is_alive() or not result or not isinstance(result[0], dict):
        raise RuntimeSessionUnavailable("CPS 浏览器内报表请求超时或失败，请检查页面与网络状态。")
    value = result[0].get("result", {}).get("value")
    if not isinstance(value, dict) or value.get("error") or not isinstance(value.get("body"), str):
        raise RuntimeSessionUnavailable("CPS 页面没有可用报表会话，请确认主账号已登录。")
    return int(value["status"]), value["body"].encode("utf-8")


@dataclass(frozen=True)
class CpsRuntimeContext:
    """Runtime-only values needed by the CPS overview endpoint."""

    session: RuntimeSession
    tb_token: str = field(repr=False)


def resolve_cps_runtime_context(
    *,
    source: str,
    cookie_env: str,
    tb_token: str = "",
    browser_port: int = DEFAULT_DEBUG_PORT,
    report_home_url: str = DEFAULT_CPS_REPORT_HOME_URL,
    timeout: float = 20,
) -> CpsRuntimeContext:
    """Resolve CPS cookies and the transient `_tb_token_` without persisting either."""
    if source == "env":
        tb_token = tb_token or os.getenv("CPS_TB_TOKEN", "").strip()
        session = resolve_runtime_session(
            source=source, cookie_env=cookie_env, browser_port=browser_port,
        )
        if not tb_token:
            raise RuntimeSessionUnavailable(
                "--tb-token/CPS_TB_TOKEN is required when --session-source=env."
            )
        return CpsRuntimeContext(session=session, tb_token=tb_token)

    if source == "drissionpage":
        return DrissionPageCpsSessionProvider(
            browser_port, report_home_url=report_home_url, timeout=timeout,
        ).read_context(tb_token=tb_token)

    raise ValueError(f"Unsupported session source: {source}")


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
        from app.integrations.session.helpers import (
            _navigate_tab,
            _open_reusable_flow_tab,
            _reload_tab,
            _runtime_cookie_value_from_tab,
            _runtime_session_from_tab,
            _wait_for_authenticated_tab,
        )

        browser, tab, owns_tab = _open_reusable_flow_tab(self.browser_port, ("ad.alimama.com",))
        captured_token = tb_token
        should_capture = not captured_token

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
        try:
            _navigate_tab(tab, self.report_home_url, timeout=max(self.timeout, 1.0))
            _wait_for_authenticated_tab(
                tab, platform_name="淘宝客 CPS",
                timeout=max(self.timeout, 1.0),
                expected_hosts=("ad.alimama.com",),
            )
            if _cps_requires_primary_account(tab):
                raise RuntimeSessionUnavailable(
                    "CPS 暂不支持当前子账号，请在采集浏览器中切换为商家主账号后重试。"
                )
            # SPA 首次进入可能只渲染了壳页面（路由未触发报表 XHR）；
            # 没等到 overview.json 就重载一次再听，覆盖「没点进主页」的场景。
            for attempt in range(2):
                if attempt == 1 and should_capture:
                    _reload_tab(tab, timeout=max(self.timeout, 1.0))
                if should_capture:
                    for packet in tab.listen.steps(timeout=self.timeout):
                        captured_token = _extract_cps_request_token(packet)
                        if captured_token:
                            break
                if captured_token or not should_capture:
                    break
        finally:
            if should_capture:
                tab.listen.stop()

        if not captured_token:
            raise RuntimeSessionUnavailable(
                "CPS 页面已打开，但没有捕获到有效报表会话。请确认主账号已登录、"
                "页面可以正常显示报表，然后重试。"
            )

        cookie_header = cookie_header_from_mapping(tab.cookies(all_domains=True).as_dict())
        session = RuntimeSession(
            cookie_header=cookie_header, source="drissionpage",
            cookie_count=_cookie_count(cookie_header),
        )
        return CpsRuntimeContext(session=session, tb_token=captured_token)


def _cps_requires_primary_account(tab: Any) -> bool:
    try:
        page_html = str(tab.html or "")
    except Exception:
        return False
    return "暂不支持子账号访问" in page_html


def _extract_cps_request_token(packet: Any) -> str:
    request = getattr(packet, "request", None)
    if request is None:
        return ""
    params = getattr(request, "params", {}) or {}
    post_data = getattr(request, "postData", {}) or {}
    if not isinstance(params, Mapping):
        params = {}
    if not isinstance(post_data, Mapping):
        post_data = {}
    value = params.get("_tb_token_") or post_data.get("_tb_token_")
    return str(value).strip() if value is not None else ""
