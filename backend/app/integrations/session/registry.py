"""Platform context registry — single place to know "how to get a session for platform X".

High cohesion: one module, one concern (platform → provider factory + spec).
Low coupling: callers depend on this registry, not on 6 separate resolve_*
functions.  New platforms are added by calling `registry.register(...)`
rather than editing a god-file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.integrations.session.core import PlatformSpec, RuntimeSession


@dataclass(frozen=True)
class PlatformContext:
    """One platform's spec + session factory + (optional) CSRF refresher."""

    spec: PlatformSpec
    session_factory: Callable[..., RuntimeSession]
    csrf_refresher: Callable[..., Any] | None = None
    hosts: tuple[str, ...] = ()


class SessionProviderRegistry:
    """Maps platform code → (spec, session_factory, csrf_refresher)."""

    def __init__(self) -> None:
        self._entries: dict[str, PlatformContext] = {}

    def register(
        self,
        spec: PlatformSpec,
        session_factory: Callable[..., RuntimeSession],
        csrf_refresher: Callable[..., Any] | None = None,
    ) -> None:
        self._entries[spec.code] = PlatformContext(
            spec=spec,
            session_factory=session_factory,
            csrf_refresher=csrf_refresher,
            hosts=spec.hosts,
        )

    def get(self, code: str) -> PlatformContext:
        if code not in self._entries:
            raise KeyError(f"Unknown platform: {code}")
        return self._entries[code]

    def list_codes(self) -> list[str]:
        return list(self._entries)

    def specs(self) -> dict[str, PlatformSpec]:
        return {code: entry.spec for code, entry in self._entries.items()}


# ---- module-level default registry (pre-populated with known platforms) ----

def _sycm_spec() -> PlatformSpec:
    return PlatformSpec(
        code="sycm",
        name="生意参谋",
        home_url="https://sycm.taobao.com/portal/home.htm",
        hosts=("sycm.taobao.com",),
    )


def _cps_spec() -> PlatformSpec:
    return PlatformSpec(
        code="cps",
        name="淘宝客 CPS",
        home_url="https://ad.alimama.com/portal/v2/report/promotionDataPage.htm",
        hosts=("ad.alimama.com",),
    )


def _alimama_spec() -> PlatformSpec:
    return PlatformSpec(
        code="alimama",
        name="阿里妈妈",
        home_url="https://one.alimama.com/index.html#!/report/campaign?rptType=campaign",
        hosts=("one.alimama.com",),
    )


def _databank_spec() -> PlatformSpec:
    return PlatformSpec(
        code="databank",
        name="品牌数据银行",
        home_url="https://databank.tmall.com/",
        hosts=("databank.tmall.com",),
    )


def _brandsearch_spec() -> PlatformSpec:
    return PlatformSpec(
        code="brandsearch",
        name="品销宝品牌专区",
        home_url="https://branding.taobao.com/#!/report/index?productid=101005201",
        hosts=("branding.taobao.com", "brandsearch.taobao.com"),
    )


def _utry_spec() -> PlatformSpec:
    return PlatformSpec(
        code="utry",
        name="U先派样",
        home_url="https://tmesh.tmall.com/utry/samplePlatform/common_data_board?id=1904810",
        hosts=("tmesh.tmall.com",),
    )


def build_default_registry() -> SessionProviderRegistry:
    """Return a registry pre-populated with the 6 known platforms.

    Session factories are wired lazily to avoid importing all provider
    modules at registry-construction time (each provider module pulls in
    DrissionPage-specific helpers that are only needed on the
    `drissionpage` source path).
    """
    registry = SessionProviderRegistry()

    def _sycm_factory(**kwargs: Any) -> RuntimeSession:
        from app.integrations.session.sycm import resolve_sycm_runtime_context
        context = resolve_sycm_runtime_context(**kwargs)
        return context.session

    def _alimama_factory(**kwargs: Any) -> RuntimeSession:
        from app.integrations.session.alimama import resolve_alimama_runtime_context
        context = resolve_alimama_runtime_context(**kwargs)
        return context.session

    def _databank_factory(**kwargs: Any) -> RuntimeSession:
        from app.integrations.session.databank import resolve_databank_runtime_context
        context = resolve_databank_runtime_context(**kwargs)
        return context.session

    def _cps_factory(**kwargs: Any) -> RuntimeSession:
        from app.integrations.session.cps import resolve_cps_runtime_context
        context = resolve_cps_runtime_context(**kwargs)
        return context.session

    def _brandsearch_factory(**kwargs: Any) -> RuntimeSession:
        from app.integrations.session.brandsearch import resolve_brandsearch_runtime_context
        context = resolve_brandsearch_runtime_context(**kwargs)
        return context.session

    def _utry_factory(**kwargs: Any) -> RuntimeSession:
        from app.integrations.session.utry import resolve_utry_runtime_context
        context = resolve_utry_runtime_context(**kwargs)
        return context.session

    # Lazy csrf refreshers: each refreshes a short-lived token in-memory.
    def _alimama_refresh(browser_port: int, **_: Any) -> str:
        from app.integrations.session.csrf_refresh import refresh_alimama_csrf
        return refresh_alimama_csrf(browser_port)

    registry.register(_sycm_spec(), _sycm_factory)
    registry.register(_cps_spec(), _cps_factory)
    registry.register(_alimama_spec(), _alimama_factory, csrf_refresher=_alimama_refresh)
    registry.register(_databank_spec(), _databank_factory)
    registry.register(_brandsearch_spec(), _brandsearch_factory)
    registry.register(_utry_spec(), _utry_factory)
    return registry


# Module-level default instance (callers can use it directly or build their own).
default_registry = build_default_registry()
