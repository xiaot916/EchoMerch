from __future__ import annotations

from pydantic import BaseModel, Field


class AuthConfiguration(BaseModel):
    enabled: bool
    session_days: int


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=6, max_length=256)


class RoleRecord(BaseModel):
    code: str
    name: str
    description: str
    permissions: list[str] = Field(default_factory=list)
    menus: list[str] = Field(default_factory=list)


class PermissionRecord(BaseModel):
    code: str
    name: str
    description: str


class MenuRecord(BaseModel):
    code: str
    parent_code: str | None
    name: str
    menu_type: str
    path: str
    component: str
    permission: str | None = None
    order: int
    hidden: bool = False


class AccessUser(BaseModel):
    user_id: int | None
    username: str
    display_name: str
    roles: list[str]
    permissions: list[str]
    menus: list[str] = Field(default_factory=list)
    store_ids: list[int] | None
    brand_ids: list[str] | None
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None
    last_login_at: str | None = None


class LoginResponse(BaseModel):
    user: AccessUser


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=6, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class ChangePasswordResponse(BaseModel):
    detail: str
    relogin_required: bool = True


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=2, max_length=80)
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=6, max_length=256)
    role_codes: list[str] = Field(min_length=1)
    store_ids: list[int] = Field(default_factory=list)
    brand_ids: list[str] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    role_codes: list[str] = Field(min_length=1)
    store_ids: list[int] = Field(default_factory=list)
    brand_ids: list[str] = Field(default_factory=list)


class UpdateUserStatusRequest(BaseModel):
    is_active: bool


class ResetUserPasswordRequest(BaseModel):
    password: str = Field(min_length=12, max_length=256)


class AccessDirectory(BaseModel):
    users: list[AccessUser]
    roles: list[RoleRecord]
    permissions: list[PermissionRecord]
    menus: list[MenuRecord]


class UpdateRoleAccessRequest(BaseModel):
    permission_codes: list[str] = Field(default_factory=list)
    menu_codes: list[str] = Field(default_factory=list)


class ApiPermissionRecord(BaseModel):
    path: str
    method: str
    name: str
    module: str
    permission: str | None = None
    protected: bool = True
