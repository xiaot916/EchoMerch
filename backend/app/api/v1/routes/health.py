from fastapi import APIRouter

from app.core.config import settings

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "legacy_source": "configured" if settings.legacy_database_url else "not_configured",
    }

