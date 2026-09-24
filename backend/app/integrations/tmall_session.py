"""Legacy compatibility shim for the old god-module ``tmall_session``.

All real logic now lives under :mod:`app.integrations.session` (one file per
platform, plus a shared ``helpers`` module and a platform registry). This
module exists only so that the ~30 existing ``from app.integrations.tmall_session
import ...`` call sites keep working without modification. New code should
import from the ``session`` package directly.
"""

from __future__ import annotations

from app.integrations.session.core import (
    DEFAULT_DEBUG_PORT,
    DEFAULT_BROWSER_LOGIN_TIMEOUT,
    BrowserPlatformSession,
    PlatformSpec,
    RuntimeSession,
    RuntimeSessionUnavailable,
    _cookie_count,
    _validate_cookie_header,
    add_session_source_arguments,
    cookie_header_from_mapping,
    inspect_browser_platform_sessions,
    open_browser_platform_session,
    resolve_runtime_session,
)
from app.integrations.session.helpers import DrissionPageBrowser
from app.integrations.session.alimama import (
    AlimamaRuntimeContext,
    mint_login_point_id,
    resolve_alimama_runtime_context,
)
from app.integrations.session.sycm import (
    SycmRuntimeContext,
    resolve_bybt_runtime_context,
    resolve_new_customer_discount_runtime_context,
    resolve_sycm_runtime_context,
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

# --- Platform URL / global constants re-exported for legacy callers ---

DEFAULT_SYCM_HOME_URL = "https://sycm.taobao.com/portal/home.htm"
DEFAULT_BYBT_HOME_URL = "https://sycm.taobao.com/xsite/frame/bybt?from=bybtzd"
DEFAULT_NEW_CUSTOMER_DISCOUNT_HOME_URL = (
    "https://sycm.taobao.com/xsite/promotion/promotion/sales?activeKey=promotionMethod"
)
DEFAULT_DATABANK_HOME_URL = "https://databank.tmall.com/"
DEFAULT_ALIMAMA_REPORT_HOME_URL = (
    "https://one.alimama.com/index.html#!/report/campaign?rptType=campaign"
)
DEFAULT_BRANDSEARCH_REPORT_HOME_URL = (
    "https://branding.taobao.com/#!/report/index?productid=101005201"
)
DEFAULT_CPS_REPORT_HOME_URL = (
    "https://ad.alimama.com/portal/v2/report/promotionDataPage.htm"
)
DEFAULT_UTRY_REPORT_HOME_URL = (
    "https://tmesh.tmall.com/utry/samplePlatform/common_data_board?id=1904810"
)

ALIMAMA_RUNTIME_GLOBAL = "__echoMerchAlimamaRuntime"
BRANDSEARCH_RUNTIME_GLOBAL = "__echoMerchBrandSearchRuntime"

__all__ = [
    # constants
    "DEFAULT_DEBUG_PORT",
    "DEFAULT_BROWSER_LOGIN_TIMEOUT",
    "DEFAULT_SYCM_HOME_URL",
    "DEFAULT_BYBT_HOME_URL",
    "DEFAULT_NEW_CUSTOMER_DISCOUNT_HOME_URL",
    "DEFAULT_DATABANK_HOME_URL",
    "DEFAULT_ALIMAMA_REPORT_HOME_URL",
    "DEFAULT_BRANDSEARCH_REPORT_HOME_URL",
    "DEFAULT_CPS_REPORT_HOME_URL",
    "CPS_OVERVIEW_URL",
    "CPS_ITEM_ANALYSIS_URL",
    "CPS_ITEM_LIST_REFERER",
    "DEFAULT_UTRY_REPORT_HOME_URL",
    "ALIMAMA_RUNTIME_GLOBAL",
    "BRANDSEARCH_RUNTIME_GLOBAL",
    # types
    "BrowserPlatformSession",
    "PlatformSpec",
    "RuntimeSession",
    "RuntimeSessionUnavailable",
    "DrissionPageBrowser",
    "AlimamaRuntimeContext",
    "SycmRuntimeContext",
    "DatabankRuntimeContext",
    "CpsRuntimeContext",
    "BrandSearchRuntimeContext",
    "UtryReportTemplate",
    "UtryRuntimeContext",
    # functions
    "_cookie_count",
    "_validate_cookie_header",
    "add_session_source_arguments",
    "cookie_header_from_mapping",
    "inspect_browser_platform_sessions",
    "mint_login_point_id",
    "open_browser_platform_session",
    "resolve_runtime_session",
    "resolve_alimama_runtime_context",
    "resolve_sycm_runtime_context",
    "resolve_bybt_runtime_context",
    "resolve_new_customer_discount_runtime_context",
    "resolve_databank_runtime_context",
    "resolve_cps_runtime_context",
    "resolve_brandsearch_runtime_context",
    "resolve_utry_runtime_context",
]
