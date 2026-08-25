from fastapi import APIRouter, Depends

from app.api.dependencies import require_permission
from app.core.config import settings
from app.modules.system.schemas import SystemCapabilities
from app.modules.access.service import Principal

router = APIRouter()


@router.get("/capabilities", response_model=SystemCapabilities)
def get_capabilities(_: Principal = Depends(require_permission("data.manage"))) -> SystemCapabilities:
    return SystemCapabilities(
        mode="read_only",
        legacy_source="configured" if settings.legacy_database_url else "not_configured",
        enabled_modules=[
            "analytics.dashboard",
            "analytics.products",
            "analytics.traffic",
            "analytics.promotions",
            "captures.offline_analysis",
            "contracts.catalog",
            "imports.daily_dry_run",
            "imports.run_registry",
            "warehouse.platform_store",
            "operations.control_center",
        ],
        disabled_modules=[
            "crawler.execution",
            "coupon.batch_create",
            "tmall.browser_automation",
            "scheduled_jobs",
            "captures.request_replay",
        ],
        safety_rules=[
            "Legacy database adapters execute read-only SELECT queries.",
            "HTTP APIs expose contracts, dry-run plans, and summaries only.",
            "Crawler execution and platform mutation are disabled until an audited worker is added.",
            "Batch operations must follow draft -> preview -> validate -> confirm -> execute -> audit.",
        ],
    )
