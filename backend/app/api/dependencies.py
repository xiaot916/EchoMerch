from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings
from app.modules.access.service import AccessControlStore, Principal, development_principal


bearer_scheme = HTTPBearer(auto_error=False)


def get_access_store() -> AccessControlStore:
    return AccessControlStore(Path(settings.local_database_path))


def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    store: AccessControlStore = Depends(get_access_store),
) -> Principal:
    if not settings.auth_enabled:
        return development_principal()
    token = credentials.credentials if credentials else request.cookies.get("echomerch_session")
    principal = store.principal_for_token(token) if token else None
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请先登录后再访问此资源。",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


def require_permission(permission: str) -> Callable[[Principal], Principal]:
    def dependency(principal: Principal = Depends(get_current_principal)) -> Principal:
        if not principal.can(permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前账号没有此功能权限。")
        return principal

    return dependency


def resolve_store_scope(principal: Principal, requested_store_id: int | None) -> int | None:
    try:
        return principal.resolve_store_id(requested_store_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc


def resolve_brand_scope(principal: Principal, requested_brand_id: str | None) -> str | None:
    try:
        return principal.resolve_brand_id(requested_brand_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
