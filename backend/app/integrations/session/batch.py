"""One-shot browser session bootstrap for a collection batch.

The daily collector launches independent worker processes.  This module keeps
the browser-facing work in the parent process, so a platform is attached (and
its runtime parameters are harvested) at most once per batch.  Secrets stay in
the child process environment only; the snapshot is never written to disk or
included in command lines/logs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

@dataclass(frozen=True)
class BatchSessionSnapshot:
    """Environment-only credentials and source choice for one platform."""

    platform: str
    cookie_env: str
    environment: Mapping[str, str] = field(repr=False)
    session_source: str = "env"


def bootstrap_collection_sessions(
    *,
    source: str,
    browser_port: int,
    platforms: set[str] | None = None,
) -> dict[str, BatchSessionSnapshot]:
    """Harvest each reusable platform context once.

    A failed optional bootstrap is deliberately ignored.  The worker will use
    the original ``drissionpage`` path and produce its normal dataset-level
    diagnostic, so one unavailable platform does not hide failures elsewhere.
    """
    if source != "drissionpage":
        return {}

    requested = platforms or {"sycm", "alimama", "cps", "brandsearch", "databank"}

    snapshots: dict[str, BatchSessionSnapshot] = {}

    def add(
        platform: str,
        cookie_env: str,
        cookie_header: str,
        **values: str,
    ) -> None:
        if not cookie_header.strip():
            return
        environment = {cookie_env: cookie_header}
        environment.update({key: value for key, value in values.items() if value.strip()})
        snapshots[platform] = BatchSessionSnapshot(
            platform=platform,
            cookie_env=cookie_env,
            environment=environment,
        )

    # SYCM read-only reports can use the browser Cookie directly.  The generic
    # context additionally attempts the HTML bootstrap token, without opening
    # a new report page when the authenticated tab already exists.
    if "sycm" in requested:
        try:
            from app.integrations.session.sycm import DrissionPageSycmTokenSessionProvider

            context = DrissionPageSycmTokenSessionProvider(
                browser_port,
                home_url="https://sycm.taobao.com/portal/home.htm",
                request_target=r"sycm\.taobao\.com/.+\.json",
                platform_name="生意参谋",
                timeout=20,
            ).read_context()
            add(
                "sycm", "ECHO_BATCH_SYCM_COOKIE", context.session.cookie_header,
                SYCM_TOKEN=context.token, ECHO_BATCH_SYCM_BROWSER_PORT=str(browser_port),
            )
        except Exception:
            pass

    if "alimama" in requested:
        try:
            from app.integrations.session.alimama import resolve_alimama_runtime_context

            context = resolve_alimama_runtime_context(
                source="drissionpage",
                cookie_env="ECHO_BATCH_ALIMAMA_COOKIE",
                browser_port=browser_port,
            )
            add(
                "alimama",
                "ECHO_BATCH_ALIMAMA_COOKIE",
                context.session.cookie_header,
                RTB_CSRF_ID=context.csrf_id,
                RTB_LOGIN_POINT_ID=context.login_point_id,
                ECHO_BATCH_ALIMAMA_BROWSER_PORT=str(browser_port),
            )
        except Exception:
            pass

    if "cps" in requested:
        try:
            from app.integrations.session.cps import resolve_cps_runtime_context

            context = resolve_cps_runtime_context(
                source="drissionpage",
                cookie_env="ECHO_BATCH_CPS_COOKIE",
                browser_port=browser_port,
            )
            add(
                "cps", "ECHO_BATCH_CPS_COOKIE", context.session.cookie_header,
                CPS_TB_TOKEN=context.tb_token,
                ECHO_BATCH_CPS_BROWSER_PORT=str(browser_port),
            )
        except Exception:
            pass

    if "brandsearch" in requested:
        try:
            from app.integrations.session.brandsearch import resolve_brandsearch_runtime_context

            context = resolve_brandsearch_runtime_context(
                source="drissionpage",
                cookie_env="ECHO_BATCH_BRANDSEARCH_COOKIE",
                browser_port=browser_port,
            )
            add(
                "brandsearch",
                "ECHO_BATCH_BRANDSEARCH_COOKIE",
                context.session.cookie_header,
                PZ_CSRF_ID=context.csrf_id,
                ECHO_BATCH_BRANDSEARCH_BROWSER_PORT=str(browser_port),
            )
        except Exception:
            pass

    if "databank" in requested:
        try:
            from app.integrations.session.databank import resolve_databank_runtime_context

            context = resolve_databank_runtime_context(
                source="drissionpage",
                cookie_env="ECHO_BATCH_DATABANK_COOKIE",
                browser_port=browser_port,
            )
            add(
                "databank",
                "ECHO_BATCH_DATABANK_COOKIE",
                context.session.cookie_header,
                DATABANK_CSRF_TOKEN=context.csrf_token,
                ECHO_BATCH_DATABANK_BROWSER_PORT=str(browser_port),
            )
        except Exception:
            pass

    return snapshots
