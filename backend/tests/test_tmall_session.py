import re

import pytest

from app.integrations.session.helpers import (
    DrissionPageSessionProvider, _platform_tab_session, _reload_tab,
    browser_cookie_headers_for_urls, request_cookie_headers_for_urls,
)
from app.integrations.session.alimama import (
    DrissionPageAlimamaSessionProvider,
    _fetch_alimama_csrf_id,
    _extract_alimama_request_context,
    mint_login_point_id,
    resolve_alimama_runtime_context,
)
from app.integrations.session.brandsearch import (
    DrissionPageBrandSearchSessionProvider,
    _brandsearch_context_from_session,
    _extract_brandsearch_request_context,
)
from app.integrations.session.core import DrissionPageBrowser, PlatformSpec
from app.integrations.session.cps import _cps_requires_primary_account, _extract_cps_request_token
from app.integrations.session.sycm import (
    SycmRuntimeContext,
    _extract_sycm_request_token,
    resolve_bybt_runtime_context,
)
from app.integrations.session.utry import _extract_utry_dashboard_urls
from app.integrations.tmall_session import (
    BrowserPlatformSession,
    DatabankRuntimeContext,
    RuntimeSessionUnavailable,
    RuntimeSession,
    cookie_header_from_mapping,
    open_browser_platform_session,
    resolve_cps_runtime_context,
    resolve_runtime_session,
    resolve_databank_runtime_context,
)


class _FakeCookies:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def as_dict(self) -> dict[str, str]:
        return self.values


class _FakeJsonResponse:
    def __init__(self, payload: dict[str, object], status: int = 200) -> None:
        import json

        self.payload = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self) -> "_FakeJsonResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class _FakePlatformTab:
    def __init__(self, destination: str, *, cookies: dict[str, str] | None = None, html: str = "") -> None:
        self.destination = destination
        self.url = "about:blank"
        self.cookie_values = cookies or {}
        self.html = html

    def get(self, _url: str) -> None:
        self.url = self.destination

    def wait(self, _seconds: float) -> None:
        return None

    def cookies(self, *, all_domains: bool = False) -> _FakeCookies:
        assert all_domains is True
        return _FakeCookies(self.cookie_values)


class _FakePlatformBrowser:
    def __init__(self) -> None:
        self.closed: list[object] = []

    def close_tab(self, tab: object) -> None:
        self.closed.append(tab)


class _FakeReloadTab:
    def __init__(self) -> None:
        self.url = "https://one.alimama.com/index.html#!/report/campaign"
        self.cdp_calls: list[tuple[str, dict[str, object]]] = []
        self.refresh_calls: list[dict[str, object]] = []

    def run_cdp(self, method: str, **kwargs: object) -> None:
        self.cdp_calls.append((method, kwargs))

    def refresh(self, **kwargs: object) -> None:
        self.refresh_calls.append(kwargs)

    def wait(self, _seconds: float) -> None:
        return None

    def cookies(self, *, all_domains: bool = False) -> _FakeCookies:
        assert all_domains is True
        return _FakeCookies({"t": "session"})

    def run_js(self, _script: str) -> None:
        return None


class _FakeAlimamaListener:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self, **_kwargs: object) -> None:
        self.started = True

    def steps(self, *, timeout: float):
        assert timeout > 0
        return iter([_Packet({}, {"csrfId": "csrf-runtime", "loginPointId": "login-runtime"})])

    def stop(self) -> None:
        self.stopped = True


class _FakeBrandSearchListener:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def start(self, **_kwargs: object) -> None:
        self.started = True

    def steps(self, *, timeout: float):
        assert timeout > 0
        return iter([_Packet({"csrfId": "pz-csrf", "productId": "101005201"}, {})])

    def stop(self) -> None:
        self.stopped = True


def test_browser_cookie_mapping_becomes_a_request_header() -> None:
    header = cookie_header_from_mapping({"t": "session", "cookie2": "device"})

    assert header == "t=session; cookie2=device"


def test_cookie_mapping_rejects_header_injection() -> None:
    with pytest.raises(RuntimeSessionUnavailable, match="invalid cookie"):
        cookie_header_from_mapping({"t": "session\r\nX-Injected: value"})


def test_browser_cookie_headers_are_scoped_to_each_request_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTab:
        def run_cdp(self, method: str, *, urls: list[str]) -> dict[str, object]:
            assert method == "Network.getCookies"
            suffix = "mtop" if "h5api" in urls[0] else "activity"
            return {"cookies": [{"name": "session", "value": suffix}]}

    class FakeBrowser:
        def __init__(self, port: int) -> None:
            assert port == 9222

        def find_tab(self, hosts: tuple[str, ...]) -> FakeTab:
            assert hosts == ("myseller.taobao.com",)
            return FakeTab()

    monkeypatch.setattr("app.integrations.session.helpers.DrissionPageBrowser", FakeBrowser)
    urls = ("https://h5api.m.taobao.com/h5/api", "https://sale.taobao.com/domain/item/query.json")
    headers = browser_cookie_headers_for_urls(9222, urls, expected_hosts=("myseller.taobao.com",))

    assert headers == {urls[0]: "session=mtop", urls[1]: "session=activity"}


def test_request_cookie_headers_preserve_explicit_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_REQUEST_COOKIE", "t=explicit")
    urls = ("https://h5api.m.taobao.com/h5/api", "https://sale.taobao.com/domain/item/query.json")
    assert request_cookie_headers_for_urls(
        source="env", cookie_env="TEST_REQUEST_COOKIE", browser_port=9222,
        urls=urls, expected_hosts=("myseller.taobao.com",),
    ) == {url: "t=explicit" for url in urls}


def test_request_cookie_headers_delegate_browser_scoping(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.integrations.session import helpers

    urls = ("https://h5api.m.taobao.com/h5/api",)
    monkeypatch.setattr(
        helpers, "browser_cookie_headers_for_urls",
        lambda port, targets, *, expected_hosts: (
            {targets[0]: "t=scoped"}
            if (port, targets, expected_hosts) == (9222, urls, ("myseller.taobao.com",))
            else pytest.fail("unexpected cookie target")
        ),
    )
    assert request_cookie_headers_for_urls(
        source="drissionpage", cookie_env="UNUSED", browser_port=9222,
        urls=urls, expected_hosts=("myseller.taobao.com",),
    ) == {urls[0]: "t=scoped"}


def test_domain_cookies_can_be_read_from_an_existing_non_seller_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeTab:
        def run_cdp(self, _method: str, *, urls: list[str]) -> dict[str, object]:
            assert urls == ["https://h5api.m.taobao.com/h5/api"]
            return {"cookies": [{"name": "_m_h5_tk", "value": "browser-session"}]}

    class FakeBrowser:
        def __init__(self, _port: int) -> None:
            self.lookups: list[tuple[str, ...]] = []

        def find_tab(self, hosts: tuple[str, ...]) -> FakeTab | None:
            self.lookups.append(hosts)
            return None if hosts else FakeTab()

    monkeypatch.setattr("app.integrations.session.helpers.DrissionPageBrowser", FakeBrowser)
    url = "https://h5api.m.taobao.com/h5/api"
    assert browser_cookie_headers_for_urls(9222, (url,), expected_hosts=("myseller.taobao.com",)) == {
        url: "_m_h5_tk=browser-session",
    }


def test_browser_can_reuse_any_non_login_tab_for_shared_cookie_access() -> None:
    browser = object.__new__(DrissionPageBrowser)
    browser.list_tabs = lambda: [
        {"type": "page", "url": "about:blank", "id": "blank-tab"},
        {"type": "page", "url": "https://sycm.taobao.com/portal/home.htm", "id": "tab-1"}
    ]
    browser._open_tab_safely = lambda tab_id: {"id": tab_id}

    assert browser.find_tab(()) == {"id": "tab-1"}


def test_platform_probe_requires_the_expected_business_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser = _FakePlatformBrowser()
    tab = _FakePlatformTab(
        "https://sycm.taobao.com/portal/home.htm",
        cookies={"t": "session", "cookie2": "device"},
    )
    monkeypatch.setattr(
        "app.integrations.session.helpers._open_reusable_flow_tab",
        lambda _port, _hosts: (browser, tab, True),
    )

    result = open_browser_platform_session(9222, "sycm", timeout=1)

    assert result.authenticated is True
    assert result.page_detected is True
    assert result.cookie_count == 2
    assert browser.closed == [tab]


def test_live_drission_tab_browser_attribute_does_not_hide_its_url() -> None:
    tab = _FakePlatformTab(
        "https://sycm.taobao.com/portal/home.htm", cookies={"t": "session"}
    )
    tab.browser = object()  # ChromiumTab also exposes this attribute.
    tab.url = tab.destination

    result = _platform_tab_session(
        tab, PlatformSpec("sycm", "生意参谋", tab.destination, ("sycm.taobao.com",))
    )

    assert result.status == "authenticated"
    assert result.page_detected is True
    assert result.cookie_count == 1


def test_platform_probe_keeps_login_page_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A login redirect still proves the platform tab is ours, and is not closed."""
    browser = _FakePlatformBrowser()
    tab = _FakePlatformTab("https://login.taobao.com/member/login.jhtml")
    monkeypatch.setattr(
        "app.integrations.session.helpers._open_reusable_flow_tab",
        lambda _port, _hosts: (browser, tab, True),
    )

    result = open_browser_platform_session(9222, "cps", timeout=1)

    # Note: open_browser_platform_session navigates to the platform home_url
    # before probing, so the fake tab's URL is unchanged by design here — the
    # probe still classifies it from the login URL it reports.
    assert result.authenticated is False
    assert result.page_detected is True
    assert result.status == "login_required"
    assert "未登录" in result.detail
    assert browser.closed == []


def test_cps_platform_probe_accepts_a_probed_platform_tab(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After navigation, an authenticated CPS tab reports authenticated."""
    browser = _FakePlatformBrowser()
    tab = _FakePlatformTab(
        "https://ad.alimama.com/portal/v2/report/promotionDataPage.htm",
        cookies={"t": "session"},
    )
    monkeypatch.setattr(
        "app.integrations.session.helpers._open_reusable_flow_tab",
        lambda _port, _hosts: (browser, tab, True),
    )

    result = open_browser_platform_session(9222, "cps", timeout=1)

    assert result.authenticated is True
    assert result.page_detected is True
    assert result.cookie_count == 1
    assert browser.closed == [tab]


def test_cps_provider_rejects_subaccount_page() -> None:
    """Subaccount detection is a CPS-provider concern, not a generic probe one."""
    tab = _FakePlatformTab(
        "https://ad.alimama.com/portal/v2/report/promotionDataPage.htm",
        cookies={"t": "session"},
        html="暂不支持子账号访问",
    )

    assert _cps_requires_primary_account(tab) is True

    tab_ok = _FakePlatformTab(
        "https://ad.alimama.com/portal/v2/report/promotionDataPage.htm",
        cookies={"t": "session"},
        html="<html><body>报表</body></html>",
    )
    assert _cps_requires_primary_account(tab_ok) is False


def test_env_session_reads_only_the_named_environment_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_SYCM_COOKIE", "t=session; cookie2=device")

    session = resolve_runtime_session(
        source="env",
        cookie_env="TEST_SYCM_COOKIE",
    )

    assert session.source == "env"
    assert session.cookie_count == 2
    assert session.cookie_header == "t=session; cookie2=device"


def test_env_session_requires_a_nonempty_cookie(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_SYCM_COOKIE", raising=False)

    with pytest.raises(RuntimeSessionUnavailable, match="TEST_SYCM_COOKIE"):
        resolve_runtime_session(source="env", cookie_env="TEST_SYCM_COOKIE")


def test_content_session_accepts_the_web_taobao_business_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser = _FakePlatformBrowser()
    tab = _FakePlatformTab(
        "https://web.taobao.com/s-guanghe-creator/asset-overview",
        cookies={"t": "session", "_m_h5_tk": "runtime_123"},
    )
    monkeypatch.setattr(
        "app.integrations.session.helpers._open_reusable_flow_tab",
        lambda _port, _hosts: (browser, tab, True),
    )

    session = DrissionPageSessionProvider(
        9222,
        home_url="https://web.taobao.com/s-guanghe-creator/asset-overview",
        platform_name="内容效果",
        expected_hosts=("web.taobao.com",),
    ).read_session()

    assert session.cookie_count == 2
    assert browser.closed == [tab]


class _Request:
    def __init__(self, params: object, post_data: object) -> None:
        self.params = params
        self.postData = post_data


class _Packet:
    def __init__(self, params: object, post_data: object) -> None:
        self.request = _Request(params, post_data)


def test_alimama_context_reads_csrf_from_url_and_login_point_from_post_body() -> None:
    csrf_id, login_point_id = _extract_alimama_request_context(
        _Packet(
            {"csrfId": "csrf-runtime"},
            {"loginPointId": "login-point-runtime"},
        )
    )

    assert csrf_id == "csrf-runtime"
    assert login_point_id == "login-point-runtime"


def test_alimama_context_accepts_both_values_from_post_body() -> None:
    csrf_id, login_point_id = _extract_alimama_request_context(
        _Packet({}, {"csrfId": "csrf-runtime", "loginPointId": "login-point-runtime"})
    )

    assert csrf_id == "csrf-runtime"
    assert login_point_id == "login-point-runtime"


def test_alimama_csrf_can_be_resolved_from_bootstrap_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _limit: int) -> bytes:
            return b'{"data":{"accessInfo":{"csrfId":"csrf-from-bootstrap"}}}'

    def fake_urlopen(request: object, timeout: float) -> _Response:
        assert getattr(request, "full_url") == (
            "https://one.alimama.com/member/checkAccess.json"
        )
        assert getattr(request, "method") == "POST"
        assert getattr(request, "data") == b'{"bizCode":"universalBP"}'
        assert getattr(request, "get_header")("Cookie") == "t=session"
        assert timeout == 4.0
        return _Response()

    monkeypatch.setattr("app.integrations.session.alimama.urlopen", fake_urlopen)

    assert _fetch_alimama_csrf_id("t=session", timeout=4) == "csrf-from-bootstrap"


def test_existing_alimama_tab_is_reloaded_before_capturing_report_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser = _FakePlatformBrowser()
    tab = _FakeReloadTab()
    tab.listen = _FakeAlimamaListener()
    monkeypatch.setattr(
        "app.integrations.session.helpers._open_reusable_flow_tab",
        lambda _port, _hosts: (browser, tab, False),
    )

    context = DrissionPageAlimamaSessionProvider(
        9222,
        report_home_url=tab.url,
        timeout=1,
    ).read_context()

    assert context.session.cookie_count == 1
    assert context.csrf_id == "csrf-runtime"
    # loginPointId is never harvested — the server does not validate it, so
    # the provider always supplies its own value.  Assert the wire shape
    # (8 hex + 13-digit ms timestamp + 9 hex) rather than a fixed string.
    assert re.fullmatch(r"[0-9a-f]{8}\d{13}[0-9a-f]{9}", context.login_point_id)
    assert tab.cdp_calls == [("Page.reload", {"ignoreCache": True})]
    assert tab.refresh_calls == []
    assert tab.listen.started is True
    assert tab.listen.stopped is True


def test_env_alimama_context_requires_csrf_but_mints_login_point(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_RTB_COOKIE", "t=session")

    with pytest.raises(RuntimeSessionUnavailable, match="RTB_CSRF_ID"):
        resolve_alimama_runtime_context(source="env", cookie_env="TEST_RTB_COOKIE")


def test_env_alimama_context_mints_login_point_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_RTB_COOKIE", "t=session")
    monkeypatch.setenv("RTB_CSRF_ID", "csrf-from-env")
    monkeypatch.delenv("RTB_LOGIN_POINT_ID", raising=False)

    context = resolve_alimama_runtime_context(source="env", cookie_env="TEST_RTB_COOKIE")

    assert context.csrf_id == "csrf-from-env"
    assert re.fullmatch(r"[0-9a-f]{8}\d{13}[0-9a-f]{9}", context.login_point_id)


def test_env_alimama_context_reads_transient_parameters_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_RTB_COOKIE", "t=session")
    monkeypatch.setenv("RTB_CSRF_ID", "csrf-from-env")
    monkeypatch.setenv("RTB_LOGIN_POINT_ID", "login-from-env")

    context = resolve_alimama_runtime_context(source="env", cookie_env="TEST_RTB_COOKIE")

    assert context.csrf_id == "csrf-from-env"
    assert context.login_point_id == "login-from-env"


def test_brandsearch_context_reads_csrf_and_preserves_frontend_query_contract() -> None:
    csrf_id, params = _extract_brandsearch_request_context(
        _Packet(
            {
                "r": "mx-548",
                "attribution": "impression",
                "effectConversionCycle": "30",
                "trafficType": "[1,2,4,5]",
                "productId": "101005201",
                "csrfID": "csrf-runtime",
            },
            {},
        )
    )

    assert csrf_id == "csrf-runtime"
    assert params["r"] == "mx-548"
    assert params["productId"] == "101005201"


def test_brandsearch_context_resolves_csrf_directly_from_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.integrations.session.brandsearch.urlopen",
        lambda _request, timeout: _FakeJsonResponse(
            {"info": {"ok": True}, "data": {"csrfID": "csrf-from-user-info"}}
        ),
    )

    context = _brandsearch_context_from_session(
        RuntimeSession(cookie_header="t=session", source="drissionpage", cookie_count=1),
        timeout=1,
    )

    assert context.csrf_id == "csrf-from-user-info"
    assert context.query_params["csrfID"] == "csrf-from-user-info"


def test_brandsearch_provider_uses_any_existing_tab_without_opening_report_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tab = _FakeReloadTab()
    tab.url = "https://sycm.taobao.com/portal/home.htm"
    monkeypatch.setattr(
        "app.integrations.session.brandsearch.DrissionPageBrowser",
        lambda _port: object(),
    )
    monkeypatch.setattr(
        "app.integrations.session.helpers._browser_tabs",
        lambda _browser: [tab],
    )
    monkeypatch.setattr(
        "app.integrations.session.brandsearch._fetch_brandsearch_csrf_id",
        lambda _cookie, timeout: "csrf-from-cookie",
    )
    monkeypatch.setattr(
        "app.integrations.session.helpers._open_reusable_flow_tab",
        lambda *_args, **_kwargs: pytest.fail("report page fallback must not run"),
    )

    context = DrissionPageBrandSearchSessionProvider(
        9222,
        report_home_url="https://branding.taobao.com/#!/report/index",
        timeout=1,
    ).read_context()

    assert context.csrf_id == "csrf-from-cookie"
    assert context.session.cookie_count == 1
    assert tab.cdp_calls == []


def test_existing_brandsearch_tab_reloads_and_captures_csrf_without_new_blank_tab(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser = _FakePlatformBrowser()
    tab = _FakeReloadTab()
    tab.url = "https://brandsearch.taobao.com/#!/report/index?productid=101005201"
    tab.listen = _FakeBrandSearchListener()
    monkeypatch.setattr(
        "app.integrations.session.helpers._open_reusable_flow_tab",
        lambda _port, _hosts: (browser, tab, False),
    )
    monkeypatch.setattr(
        "app.integrations.session.brandsearch.DrissionPageBrowser",
        lambda _port: (_ for _ in ()).throw(RuntimeSessionUnavailable("protocol unavailable")),
    )

    context = DrissionPageBrandSearchSessionProvider(
        9222,
        report_home_url=tab.url,
        timeout=1,
    ).read_context()

    assert context.csrf_id == "pz-csrf"
    assert context.query_params["csrfID"] == "pz-csrf"
    assert context.query_params["productId"] == "101005201"
    assert tab.cdp_calls == [("Page.reload", {"ignoreCache": True})]
    assert tab.refresh_calls == []
    assert tab.listen.started is True
    assert tab.listen.stopped is True


def test_cps_context_reads_token_from_the_observed_get_request() -> None:
    token = _extract_cps_request_token(
        _Packet({"_tb_token_": "cps-runtime-token", "startDate": "2026-08-17"}, {})
    )

    assert token == "cps-runtime-token"


def test_sycm_context_reads_token_from_the_observed_get_request() -> None:
    token = _extract_sycm_request_token(
        _Packet({"token": "sycm-runtime-token", "dateType": "day"}, {})
    )

    assert token == "sycm-runtime-token"


def test_env_bybt_context_requires_a_transient_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_BYBT_COOKIE", "t=session")
    monkeypatch.delenv("SYCM_TOKEN", raising=False)

    with pytest.raises(RuntimeSessionUnavailable, match="SYCM_TOKEN"):
        resolve_bybt_runtime_context(source="env", cookie_env="TEST_BYBT_COOKIE")


def test_env_bybt_context_reads_an_explicit_transient_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_BYBT_COOKIE", "t=session")

    context = resolve_bybt_runtime_context(
        source="env",
        cookie_env="TEST_BYBT_COOKIE",
        token="bybt-from-argument",
    )

    assert context.token == "bybt-from-argument"


def test_bybt_drissionpage_context_uses_the_business_page_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeProvider:
        def __init__(
            self,
            browser_port: int,
            *,
            home_url: str,
            request_target: str,
            platform_name: str,
            timeout: float,
        ) -> None:
            captured.update(
                browser_port=browser_port,
                home_url=home_url,
                request_target=request_target,
                platform_name=platform_name,
                timeout=timeout,
            )

        def read_context(self, *, token: str = "") -> SycmRuntimeContext:
            captured["token"] = token
            return SycmRuntimeContext(
                session=RuntimeSession(cookie_header="t=session"),
                token=token or "bybt-runtime-token",
            )

    monkeypatch.setattr(
        "app.integrations.session.sycm.DrissionPageSycmTokenSessionProvider",
        FakeProvider,
    )

    context = resolve_bybt_runtime_context(
        source="drissionpage",
        cookie_env="TEST_BYBT_COOKIE",
        token="bybt-explicit",
        browser_port=9333,
        timeout=17,
    )

    assert context.token == "bybt-explicit"
    assert captured["browser_port"] == 9333
    assert captured["platform_name"] == "百亿补贴"
    assert captured["token"] == "bybt-explicit"


def test_env_cps_context_requires_a_transient_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_CPS_COOKIE", "t=session")

    with pytest.raises(RuntimeSessionUnavailable, match="CPS_TB_TOKEN"):
        resolve_cps_runtime_context(
            source="env",
            cookie_env="TEST_CPS_COOKIE",
        )


def test_env_cps_context_reads_transient_token_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_CPS_COOKIE", "t=session")
    monkeypatch.setenv("CPS_TB_TOKEN", "cps-from-env")

    context = resolve_cps_runtime_context(
        source="env",
        cookie_env="TEST_CPS_COOKIE",
    )

    assert context.tb_token == "cps-from-env"


def test_utry_batch_dashboard_response_returns_both_quark_urls() -> None:
    urls = _extract_utry_dashboard_urls(
        {
            "data": {
                "data": {
                    "1904974": {
                        "data": (
                            "https://quark.taobao.com/dashboard/view/uic.htm?id=1904974"
                            "&QUARK_PARAMS=sample-runtime"
                        )
                    },
                    "1906730": {
                        "data": (
                            "https://quark.taobao.com/dashboard/view/uic.htm?id=1906730"
                            "&QUARK_PARAMS=repurchase-runtime"
                        )
                    },
                }
            }
        },
        report_ids={1904974, 1906730},
    )

    assert set(urls) == {1904974, 1906730}
    assert "sample-runtime" in urls[1904974]
    assert "repurchase-runtime" in urls[1906730]


def test_utry_batch_dashboard_response_rejects_non_quark_urls() -> None:
    with pytest.raises(RuntimeSessionUnavailable, match="Quark"):
        _extract_utry_dashboard_urls(
            {
                "data": {
                    "data": {
                        "1904974": {
                            "data": (
                                "https://example.com/dashboard/view/uic.htm?id=1904974"
                                "&QUARK_PARAMS=not-trusted"
                            )
                        }
                    }
                }
            },
            report_ids={1904974},
        )


def test_databank_drissionpage_context_uses_the_business_page_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeProvider:
        def __init__(self, browser_port: int, home_url: str, timeout: float) -> None:
            captured.update(browser_port=browser_port, home_url=home_url, timeout=timeout)

        def read_context(self, *, csrf_token: str = "") -> DatabankRuntimeContext:
            captured["csrf_token"] = csrf_token
            return DatabankRuntimeContext(
                session=resolve_runtime_session(
                    source="env",
                    cookie_env="TEST_DATABANK_COOKIE",
                ),
                csrf_token=csrf_token or "csrf-runtime",
            )

    monkeypatch.setenv("TEST_DATABANK_COOKIE", "t=session")
    monkeypatch.setattr(
        "app.integrations.session.databank.DrissionPageDatabankSessionProvider",
        FakeProvider,
    )

    context = resolve_databank_runtime_context(
        source="drissionpage",
        cookie_env="TEST_DATABANK_COOKIE",
        csrf_token="csrf-explicit",
        browser_port=9333,
    )

    assert context.csrf_token == "csrf-explicit"
    assert captured["browser_port"] == 9333
    assert captured["csrf_token"] == "csrf-explicit"
