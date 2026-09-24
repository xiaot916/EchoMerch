from __future__ import annotations

from typing import Any, Iterator

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.routing import APIRoute
from starlette.routing import Mount

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


def _route_permission(route: APIRoute | Any) -> str | None:
    for dependant in getattr(route, "dependant", None).dependencies if getattr(route, "dependant", None) else []:
        call = dependant.call
        closure = getattr(call, "__closure__", None)
        freevars = getattr(getattr(call, "__code__", None), "co_freevars", ())
        if closure and "permission" in freevars:
            values = dict(zip(freevars, (cell.cell_contents for cell in closure)))
            permission = values.get("permission")
            if isinstance(permission, str):
                return permission
    return None


def _iter_api_routes(app: FastAPI) -> Iterator[Any]:
    """Yield every registered API route, including lazily included routers.

    FastAPI 0.141 no longer flattens ``include_router`` into ``APIRoute``
    objects; it stores a single ``_IncludedRouter`` placeholder and resolves the
    real routes on demand. Reading ``app.routes`` alone therefore finds zero
    endpoints, so the permission audit must expand the placeholder explicitly.
    """

    pending: list[Any] = list(app.routes)
    seen: set[int] = set()
    while pending:
        route = pending.pop(0)
        if id(route) in seen:
            continue
        seen.add(id(route))
        if isinstance(route, APIRoute):
            yield route
            continue
        expand = getattr(route, "effective_route_contexts", None)
        if callable(expand):
            for context in expand():
                original = getattr(context, "original_route", None)
                if isinstance(original, APIRoute):
                    yield APIRouteView(original, context)
                elif original is not None:
                    pending.append(original)
        elif isinstance(route, Mount):
            pending.extend(getattr(route, "routes", ()) or ())


class APIRouteView:
    """Adapts a lazily resolved route context to the ``APIRoute`` surface."""

    __slots__ = ("_context", "_route")

    def __init__(self, route: APIRoute, context: Any) -> None:
        self._route = route
        self._context = context

    @property
    def path(self) -> str:
        return getattr(self._context, "path", None) or self._route.path

    @property
    def name(self) -> str:
        return getattr(self._context, "name", None) or self._route.name

    @property
    def methods(self) -> set[str]:
        return getattr(self._context, "methods", None) or self._route.methods

    @property
    def dependant(self) -> Any:
        return getattr(self._context, "dependant", None) or self._route.dependant


@router.get("/api-permissions", response_model=list[ApiPermissionRecord])
def list_api_permissions(
    request: Request,
    _: Principal = Depends(require_permission("system.manage")),
) -> list[ApiPermissionRecord]:
    records: list[ApiPermissionRecord] = []
    for route in _iter_api_routes(request.app):
        if not route.path.startswith("/api/v1"):
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
