from fastapi import APIRouter

from app.api.v1.routes.access import router as access_router
from app.api.v1.routes.brand_assets import router as brand_assets_router
from app.api.v1.routes.analytics import router as analytics_router
from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.captures import router as captures_router
from app.api.v1.routes.contracts import router as contracts_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.imports import router as imports_router
from app.api.v1.routes.operations import router as operations_router
from app.api.v1.routes.system import router as system_router
from app.api.v1.routes.warehouse import router as warehouse_router
from app.api.v1.routes.collection import router as collection_router
from app.api.v1.routes.store_data import router as store_data_router
from app.api.v1.routes.reviews import router as reviews_router
from app.api.v1.routes.ai import router as ai_router
from app.api.v1.routes.notifications import router as notifications_router
from app.api.v1.routes.inventory import router as inventory_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(access_router, prefix="/access", tags=["access"])
api_router.include_router(brand_assets_router, prefix="/brand-assets", tags=["brand-assets"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["analytics"])
api_router.include_router(captures_router, prefix="/captures", tags=["captures"])
api_router.include_router(contracts_router, prefix="/contracts", tags=["contracts"])
api_router.include_router(imports_router, prefix="/imports", tags=["imports"])
api_router.include_router(operations_router, prefix="/operations", tags=["operations"])
api_router.include_router(system_router, prefix="/system", tags=["system"])
api_router.include_router(warehouse_router, prefix="/warehouse", tags=["warehouse"])
api_router.include_router(store_data_router, prefix="/warehouse/store-data", tags=["store-data"])
api_router.include_router(reviews_router, prefix="/reviews", tags=["reviews"])
api_router.include_router(collection_router, prefix="/imports", tags=["collection"])
api_router.include_router(ai_router, prefix="/ai", tags=["ai"])
api_router.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
api_router.include_router(inventory_router, prefix="/inventory", tags=["inventory"])
