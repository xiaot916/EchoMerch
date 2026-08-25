import pytest

from app.integrations.tmall_session import (
    BrowserPlatformSession,
    DatabankRuntimeContext,
    RuntimeSessionUnavailable,
    _extract_utry_dashboard_urls,
    _extract_brandsearch_request_context,
    _extract_cps_request_token,
    _extract_alimama_request_context,
    cookie_header_from_mapping,
    open_browser_platform_session,
    resolve_alimama_runtime_context,
    resolve_cps_runtime_context,
    resolve_runtime_session,
    resolve_databank_runtime_context,
)


class _FakeCookies:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values

    def as_dict(self) -> dict[str, str]:
        return self.values


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


def test_browser_cookie_mapping_becomes_a_request_header() -> None:
    header = cookie_header_from_mapping({"t": "session", "cookie2": "device"})

    assert header == "t=session; cookie2=device"


def test_cookie_mapping_rejects_header_injection() -> None:
    with pytest.raises(RuntimeSessionUnavailable, match="invalid cookie"):
        cookie_header_from_mapping({"t": "session\r\nX-Injected: value"})


def test_platform_probe_requires_the_expected_business_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser = _FakePlatformBrowser()
    tab = _FakePlatformTab(
        "https://sycm.taobao.com/portal/home.htm",
        cookies={"t": "session", "cookie2": "device"},
    )
    monkeypatch.setattr(
        "app.integrations.tmall_session._open_flow_tab",
        lambda _port: (browser, tab),
    )

    result = open_browser_platform_session(9222, "sycm", timeout=1)

    assert result.authenticated is True
    assert result.page_detected is True
    assert result.cookie_count == 2
    assert browser.closed == [tab]


def test_platform_probe_keeps_login_page_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser = _FakePlatformBrowser()
    tab = _FakePlatformTab("https://login.taobao.com/member/login.jhtml")
    monkeypatch.setattr(
        "app.integrations.tmall_session._open_flow_tab",
        lambda _port: (browser, tab),
    )

    result = open_browser_platform_session(9222, "cps", timeout=1)

    assert result.authenticated is False
    assert result.page_detected is True
    assert "登录页已打开" in result.detail
    assert browser.closed == []


def test_cps_platform_probe_rejects_subaccount(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser = _FakePlatformBrowser()
    tab = _FakePlatformTab(
        "https://ad.alimama.com/portal/v2/report/promotionDataPage.htm",
        cookies={"t": "session"},
        html="暂不支持子账号访问",
    )
    monkeypatch.setattr(
        "app.integrations.tmall_session._open_flow_tab",
        lambda _port: (browser, tab),
    )

    result = open_browser_platform_session(9222, "cps", timeout=1)

    assert result.authenticated is False
    assert result.page_detected is True
    assert "主账号" in result.detail
    assert browser.closed == []


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


def test_env_alimama_context_requires_transient_request_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_RTB_COOKIE", "t=session")

    with pytest.raises(RuntimeSessionUnavailable, match="RTB_CSRF_ID"):
        resolve_alimama_runtime_context(source="env", cookie_env="TEST_RTB_COOKIE")


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


def test_cps_context_reads_token_from_the_observed_get_request() -> None:
    token = _extract_cps_request_token(
        _Packet({"_tb_token_": "cps-runtime-token", "startDate": "2026-08-17"}, {})
    )

    assert token == "cps-runtime-token"


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
        "app.integrations.tmall_session.DrissionPageDatabankSessionProvider",
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
