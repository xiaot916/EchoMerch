"""U先派样 (tmesh.tmall.com) session context — Quark FBI report templates."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import parse_qs

from app.integrations.session.core import (
    DEFAULT_DEBUG_PORT,
    RuntimeSession,
    RuntimeSessionUnavailable,
    _cookie_count,
    cookie_header_from_mapping,
)

DEFAULT_UTRY_REPORT_HOME_URL = (
    "https://tmesh.tmall.com/utry/samplePlatform/common_data_board?id=1904810"
)
UTRY_REPORT_URLS = {
    1904974: "https://tmesh.tmall.com/utry/samplePlatform/common_data_board?id=1904974",
    1906730: "https://tmesh.tmall.com/utry/samplePlatform/common_data_board?id=1906730",
}
UTRY_WIDGET_URL = "https://quark.taobao.com/fbi/.json"
UTRY_DASHBOARD_LIST_API = "mtop.tmall.tmesh.apps.utry.sampleplatform.getDataDashboardList"
UTRY_DASHBOARD_RESULT_GLOBAL = "__echoMerchUtryDashboardResult"


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
        browser_port, report_home_url=report_home_url, timeout=timeout,
    ).read_context()


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
        from app.integrations.session.helpers import (
            _navigate_tab,
            _open_reusable_flow_tab,
            _wait_for_authenticated_tab,
        )

        browser, tab, owns_tab = _open_reusable_flow_tab(self.browser_port, ("tmesh.tmall.com",))
        templates: dict[int, UtryReportTemplate] = {}
        try:
            if owns_tab:
                _navigate_tab(tab, self.report_home_url, timeout=max(self.timeout, 1.0))
            _wait_for_authenticated_tab(
                tab, platform_name="U先", timeout=max(self.timeout, 1.0),
            )
            report_urls = _resolve_utry_dashboard_urls(
                tab, report_ids=self.REQUIRED_REPORT_IDS, timeout=self.timeout,
            )
        except RuntimeSessionUnavailable:
            report_urls = {}

        templates.update(_capture_utry_templates_concurrently(
            browser, report_urls=report_urls, timeout=self.timeout,
        ))

        for report_id in sorted(self.REQUIRED_REPORT_IDS - templates.keys()):
            template = _capture_utry_template_from_parent_page(
                tab, report_id=report_id, timeout=self.timeout,
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
        return UtryRuntimeContext(
            session=RuntimeSession(
                cookie_header=cookie_header, source="drissionpage",
                cookie_count=_cookie_count(cookie_header),
            ),
            templates=templates,
        )


def _resolve_utry_dashboard_urls(
    tab: Any, *, report_ids: set[int], timeout: float,
) -> dict[int, str]:
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
    response: Any, *, report_ids: set[int],
) -> dict[int, str]:
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
        report_url = _text(entry.get("data"))
        if report_url.startswith("https://quark.taobao.com/") and \
                f"id={report_id}" in report_url and "QUARK_PARAMS=" in report_url:
            urls[report_id] = report_url
    if not urls:
        raise RuntimeSessionUnavailable("U先批量报表初始化未返回 Quark 地址。")
    return urls


def _capture_utry_template_from_direct_url(
    tab: Any, *, report_id: int, report_url: str, timeout: float,
) -> UtryReportTemplate | None:
    tab.listen.start(targets="fbi", is_regex=True, method="POST")
    try:
        from app.integrations.session.helpers import _navigate_tab, _wait_for_authenticated_tab
        _navigate_tab(tab, report_url, timeout=max(timeout, 1.0))
        _wait_for_authenticated_tab(
            tab, platform_name="U先", timeout=max(timeout, 1.0),
        )
        for packet in tab.listen.steps(timeout=timeout):
            template = _extract_utry_request_template(packet)
            if template is not None and template.report_id == report_id:
                return template
    finally:
        tab.listen.stop()
    return None


def _capture_utry_templates_concurrently(
    browser: Any, *, report_urls: Mapping[int, str], timeout: float,
) -> dict[int, UtryReportTemplate]:
    if not report_urls:
        return {}

    def capture(item: tuple[int, str]) -> UtryReportTemplate | None:
        report_id, report_url = item
        tab = browser.new_tab()
        try:
            return _capture_utry_template_from_direct_url(
                tab, report_id=report_id, report_url=report_url, timeout=timeout,
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
    tab: Any, *, report_id: int, timeout: float,
) -> UtryReportTemplate | None:
    from app.integrations.session.helpers import _navigate_tab, _wait_for_authenticated_tab
    _navigate_tab(tab, UTRY_REPORT_URLS[report_id], timeout=max(timeout, 1.0))
    _wait_for_authenticated_tab(tab, platform_name="U先", timeout=max(timeout, 1.0))
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
        referer = _text(headers.get("referer") or headers.get("Referer"))
    return UtryReportTemplate(
        report_id=report_id,
        request_url=_text(getattr(request, "url", "")) or UTRY_WIDGET_URL,
        referer=referer,
        params=params,
    )


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""
