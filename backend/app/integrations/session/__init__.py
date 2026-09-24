from app.integrations.session.core import (
    BrowserPlatformSession,
    DrissionPageBrowser,
    RuntimeSession,
    RuntimeSessionUnavailable,
    add_session_source_arguments,
    cookie_header_from_mapping,
    inspect_browser_platform_sessions,
    open_browser_platform_session,
    resolve_runtime_session,
)
from app.integrations.session.registry import (
    default_registry,
    PlatformContext,
    SessionProviderRegistry,
)
from app.integrations.session.csrf_refresh import (
    refresh_alimama_csrf,
    refresh_cps_token,
    refresh_databank_csrf,
    refresh_sycm_token,
)
from app.integrations.session.resolver import (
    resolve_dataset_context,
)
from app.integrations.session.alimama import (
    AlimamaRuntimeContext,
    resolve_alimama_runtime_context,
)
from app.integrations.session.sycm import (
    SycmRuntimeContext,
    resolve_sycm_runtime_context,
    resolve_bybt_runtime_context,
    resolve_new_customer_discount_runtime_context,
)
from app.integrations.session.databank import (
    DatabankRuntimeContext,
    resolve_databank_runtime_context,
)
from app.integrations.session.cps import (
    CpsRuntimeContext,
    CPS_OVERVIEW_URL,
    CPS_ITEM_ANALYSIS_URL,
    CPS_ITEM_LIST_REFERER,
    resolve_cps_runtime_context,
)
from app.integrations.session.brandsearch import (
    BrandSearchRuntimeContext,
    resolve_brandsearch_runtime_context,
)
from app.integrations.session.utry import (
    UtryReportTemplate,
    UtryRuntimeContext,
    resolve_utry_runtime_context,
)

__all__ = [
    # core
    "BrowserPlatformSession",
    "DrissionPageBrowser",
    "RuntimeSession",
    "RuntimeSessionUnavailable",
    "add_session_source_arguments",
    "cookie_header_from_mapping",
    "inspect_browser_platform_sessions",
    "open_browser_platform_session",
    "resolve_runtime_session",
    # registry
    "default_registry",
    "PlatformContext",
    "SessionProviderRegistry",
    # csrf refreshers
    "refresh_alimama_csrf",
    "refresh_cps_token",
    "refresh_databank_csrf",
    "refresh_sycm_token",
    # dataset resolver (decoupling layer for the 24 collection workers)
    "resolve_dataset_context",
    # alimama
    "AlimamaRuntimeContext",
    "resolve_alimama_runtime_context",
    # sycm
    "SycmRuntimeContext",
    "resolve_sycm_runtime_context",
    "resolve_bybt_runtime_context",
    "resolve_new_customer_discount_runtime_context",
    # databank
    "DatabankRuntimeContext",
    "resolve_databank_runtime_context",
    # cps
    "CpsRuntimeContext",
    "CPS_OVERVIEW_URL",
    "CPS_ITEM_ANALYSIS_URL",
    "CPS_ITEM_LIST_REFERER",
    "resolve_cps_runtime_context",
    # brandsearch
    "BrandSearchRuntimeContext",
    "resolve_brandsearch_runtime_context",
    # utry
    "UtryReportTemplate",
    "UtryRuntimeContext",
    "resolve_utry_runtime_context",
]
