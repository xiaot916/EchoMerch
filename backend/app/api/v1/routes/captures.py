from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import require_permission
from app.core.config import settings
from app.modules.captures.schemas import CaptureSummary
from app.modules.captures.storage import CaptureStore
from app.modules.access.service import Principal

router = APIRouter()


@router.get("/summary", response_model=CaptureSummary)
def get_capture_summary(_: Principal = Depends(require_permission("system.manage"))) -> CaptureSummary:
    database_path = Path(settings.capture_database_path)
    if not database_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Offline capture analysis has not been initialized.",
        )
    payload = CaptureStore(database_path).api_summary()
    if payload["imported_at"]:
        payload["imported_at"] = datetime.fromisoformat(payload["imported_at"])
    return CaptureSummary.model_validate(payload)
