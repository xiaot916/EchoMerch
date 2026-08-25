from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.dependencies import get_access_store, get_current_principal
from app.core.config import settings
from app.modules.access.schemas import (
    AuthConfiguration,
    ChangePasswordRequest,
    ChangePasswordResponse,
    LoginRequest,
    LoginResponse,
)
from app.modules.access.service import (
    SESSION_COOKIE_NAME,
    AccessControlStore,
    InvalidCredentials,
    Principal,
)


router = APIRouter()


@router.get("/configuration", response_model=AuthConfiguration)
def get_auth_configuration() -> AuthConfiguration:
    return AuthConfiguration(enabled=settings.auth_enabled, session_days=settings.auth_session_days)


@router.post("/login", response_model=LoginResponse)
def login(
    request: LoginRequest,
    response: Response,
    store: AccessControlStore = Depends(get_access_store),
) -> LoginResponse:
    if not settings.auth_enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="本地开发模式未启用登录。")
    try:
        principal = store.authenticate(request.username, request.password)
    except InvalidCredentials as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    assert principal.user_id is not None
    token, expires_at = store.create_session(principal.user_id, session_days=settings.auth_session_days)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        max_age=max(1, int(expires_at.timestamp() - time.time())),
        path="/",
    )
    return LoginResponse(user=principal.as_schema())


@router.get("/me", response_model=LoginResponse)
def get_me(principal: Principal = Depends(get_current_principal)) -> LoginResponse:
    return LoginResponse(user=principal.as_schema())


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    principal: Principal = Depends(get_current_principal),
    store: AccessControlStore = Depends(get_access_store),
) -> ChangePasswordResponse:
    if principal.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="当前运行模式没有可修改密码的用户账号。",
        )
    try:
        store.change_own_password(
            user_id=principal.user_id,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except InvalidCredentials as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return ChangePasswordResponse(detail="密码修改成功，请使用新密码重新登录。")


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    principal: Principal = Depends(get_current_principal),
    store: AccessControlStore = Depends(get_access_store),
) -> Response:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token and settings.auth_enabled:
        store.revoke_session(token, actor_user_id=principal.user_id)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
