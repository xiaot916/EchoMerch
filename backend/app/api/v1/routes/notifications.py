from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import require_permission
from app.core.config import settings
from app.modules.access.service import Principal
from app.modules.notifications.schemas import NotificationChannel, NotificationChannelCreate, NotificationChannelUpdate, NotificationDelivery, NotificationDeliveryList, NotificationSendRequest
from app.modules.notifications.service import NotificationService


router = APIRouter()


def get_notification_service() -> NotificationService:
    return NotificationService(Path(settings.local_database_path))


@router.get("/channels", response_model=list[NotificationChannel])
def list_channels(_: Principal = Depends(require_permission("system.manage"))) -> list[NotificationChannel]:
    return get_notification_service().list_channels()


@router.post("/channels", response_model=NotificationChannel)
def create_channel(request: NotificationChannelCreate, _: Principal = Depends(require_permission("system.manage"))) -> NotificationChannel:
    try:
        return get_notification_service().create_channel(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/channels/{channel_id}", response_model=NotificationChannel)
def update_channel(channel_id: int, request: NotificationChannelUpdate, _: Principal = Depends(require_permission("system.manage"))) -> NotificationChannel:
    try:
        return get_notification_service().update_channel(channel_id, request)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/deliveries", response_model=NotificationDeliveryList)
def list_deliveries(page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=10, le=100), _: Principal = Depends(require_permission("system.manage"))) -> NotificationDeliveryList:
    return get_notification_service().list_deliveries(page=page, page_size=page_size)


@router.post("/send", response_model=NotificationDelivery)
def send_notification(request: NotificationSendRequest, principal: Principal = Depends(require_permission("system.manage"))) -> NotificationDelivery:
    try:
        return get_notification_service().send(request, requested_by=principal.username)
    except (LookupError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
