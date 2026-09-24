"""In-memory CSRF refreshers for platform request tokens.

These values are **runtime credentials**: they are derived from the logged-in
managed browser and are never written to the database or to disk.  That is a
security boundary, not a freshness claim — some of them (notably Alimama's
``csrfId``) are actually long-lived, but they still must not be persisted
because they are tied to the live browser session.

Each refresh function below opens the matching platform tab in the managed
browser, performs a single page reload (or navigation), reads the token from
the page's request or cookie, and returns it.  The caller is expected to
discard the value at process exit.

High cohesion: this module is the *only* place that knows how to refresh
a platform token.  Callers (e.g. `executor.py` for onebp writes, `dmp_api`
for crowd writes) call `refresh_<platform>_token()` and use the result
directly — they never have to know whether the token came from a cookie, a
request parameter, or an in-page global.

Low coupling: the refreshers are pure functions of `browser_port` (plus
an optional pre-seeded value).  No global state, no DB writes, no file
writes.  The browser is owned by the user (managed session browser); the
refreshers only read from it.
"""

from __future__ import annotations

from typing import Any


def refresh_alimama_csrf(browser_port: int, preseed_csrf: str = "", preseed_login_point: str = "") -> str:
    """Return the Alimama ``csrfId`` for the attached browser session.

    Returns only the csrfId string.  Contrary to its name the value is
    long-lived (issued by ``member/checkAccess.json``); it still must not be
    persisted because it is bound to the live browser session.

    ``preseed_login_point`` is a legacy pass-through — ``loginPointId`` is
    no longer harvested (the server does not validate it), so it is minted
    locally by the provider when absent.

    Raises `RuntimeSessionUnavailable` when the page could not be
    reached or the token could not be captured within the timeout.
    """
    from app.integrations.session.alimama import DrissionPageAlimamaSessionProvider

    provider = DrissionPageAlimamaSessionProvider(
        browser_port,
        report_home_url=(
            "https://one.alimama.com/index.html#!/report/campaign?rptType=campaign"
        ),
        timeout=20,
    )
    context = provider.read_context(
        csrf_id=preseed_csrf, login_point_id=preseed_login_point,
    )
    return context.csrf_id


def refresh_databank_csrf(browser_port: int, preseed_csrf: str = "") -> str:
    """Return a fresh Brand Data Bank `_tb_token_`-style CSRF value."""
    from app.integrations.session.databank import DrissionPageDatabankSessionProvider

    provider = DrissionPageDatabankSessionProvider(
        browser_port,
        home_url="https://databank.tmall.com/",
        timeout=180,
    )
    context = provider.read_context(csrf_token=preseed_csrf)
    return context.csrf_token


def refresh_cps_token(browser_port: int, preseed_token: str = "") -> str:
    """Return a fresh CPS `_tb_token_` (short-lived, primary account only)."""
    from app.integrations.session.cps import DrissionPageCpsSessionProvider

    provider = DrissionPageCpsSessionProvider(
        browser_port,
        report_home_url=(
            "https://ad.alimama.com/portal/v2/report/promotionDataPage.htm"
        ),
        timeout=20,
    )
    context = provider.read_context(tb_token=preseed_token)
    return context.tb_token


def refresh_sycm_token(browser_port: int, home_url: str, preseed_token: str = "") -> str:
    """Return a fresh SYCM `jycmToken` for a given home page."""
    from app.integrations.session.sycm import DrissionPageSycmTokenSessionProvider

    provider = DrissionPageSycmTokenSessionProvider(
        browser_port,
        home_url=home_url,
        request_target=r"sycm\.taobao\.com/.+\.json",
        platform_name="生意参谋",
        timeout=30,
    )
    context = provider.read_context(token=preseed_token)
    return context.token
