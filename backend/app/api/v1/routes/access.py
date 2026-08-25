from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.routing import APIRoute

from app.api.dependencies import get_access_store, require_permission
from app.modules.access.schemas import (
    AccessDirectory,
    ApiPermissionRecord,
    AccessUser,
    CreateUserRequest,
    ResetUserPasswordRequest,
    RoleRecord,
    UpdateUserRequest,
    UpdateUserStatusRequest,
    UpdateRoleAccessRequest,
)
from app.modules.access.service import AccessControlStore, DuplicateUsername, Principal


router = APIRouter()


def _route_permission(route: APIRoute) -> str | None:
    for dependant in route.dependant.dependencies:
        call = dependant.call
        closure = getattr(call, "__closure__", None)
        freevars = getattr(getattr(call, "__code__", None), "co_freevars", ())
        if closure and "permission" in freevars:
            values = dict(zip(freevars, (cell.cell_contents for cell in closure)))
            permission = values.get("permission")
            if isinstance(permission, str):
                return permission
    return None


@router.get("/api-permissions", response_model=list[ApiPermissionRecord])
def list_api_permissions(
    request: Request,
    _: Principal = Depends(require_permission("system.manage")),
) -> list[ApiPermissionRecord]:
    records: list[ApiPermissionRecord] = []
    for route in request.app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/v1"):
            continue
        permission = _route_permission(route)
        module = route.path.removeprefix("/api/v1/").split("/", 1)[0]
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            records.append(ApiPermissionRecord(
                path=route.path,
                method=method,
                name=route.name,
                module=module,
                permission=permission,
                protected=permission is not None,
            ))
    return sorted(records, key=lambda item: (item.module, item.path, item.method))


@router.get("/directory", response_model=AccessDirectory)
def get_access_directory(
    _: Principal = Depends(require_permission("system.manage")),
    store: AccessControlStore = Depends(get_access_store),
) -> AccessDirectory:
    users, roles, permissions, menus = store.list_directory()
    return AccessDirectory(users=users, roles=roles, permissions=permissions, menus=menus)


@router.put("/roles/{role_code}/access", response_model=RoleRecord)
def update_role_access(
    role_code: str,
    request: UpdateRoleAccessRequest,
    principal: Principal = Depends(require_permission("system.manage")),
    store: AccessControlStore = Depends(get_access_store),
) -> RoleRecord:
    try:
        return store.update_role_access(
            role_code=role_code,
            permission_codes=request.permission_codes,
            menu_codes=request.menu_codes,
            actor_user_id=principal.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/users", response_model=AccessUser, status_code=status.HTTP_201_CREATED)
def create_access_user(
    request: CreateUserRequest,
    principal: Principal = Depends(require_permission("system.manage")),
    store: AccessControlStore = Depends(get_access_store),
) -> AccessUser:
    try:
        return store.create_user(
            username=request.username,
            display_name=request.display_name,
            password=request.password,
            role_codes=request.role_codes,
            store_ids=request.store_ids,
            brand_ids=request.brand_ids,
            actor_user_id=principal.user_id,
        )
    except DuplicateUsername as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/users/{user_id}", response_model=AccessUser)
def update_access_user(
    user_id: int,
    request: UpdateUserRequest,
    principal: Principal = Depends(require_permission("system.manage")),
    store: AccessControlStore = Depends(get_access_store),
) -> AccessUser:
    try:
        return store.update_user(
            user_id=user_id,
            display_name=request.display_name,
            role_codes=request.role_codes,
            store_ids=request.store_ids,
            brand_ids=request.brand_ids,
            actor_user_id=principal.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/users/{user_id}/status", response_model=AccessUser)
def update_access_user_status(
    user_id: int,
    request: UpdateUserStatusRequest,
    principal: Principal = Depends(require_permission("system.manage")),
    store: AccessControlStore = Depends(get_access_store),
) -> AccessUser:
    try:
        return store.set_user_active(
            user_id=user_id,
            is_active=request.is_active,
            actor_user_id=principal.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/users/{user_id}/reset-password", response_model=AccessUser)
def reset_access_user_password(
    user_id: int,
    request: ResetUserPasswordRequest,
    principal: Principal = Depends(require_permission("system.manage")),
    store: AccessControlStore = Depends(get_access_store),
) -> AccessUser:
    try:
        return store.reset_user_password(
            user_id=user_id,
            password=request.password,
            actor_user_id=principal.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
