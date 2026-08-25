from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.integrations.jackyun_credentials import CredentialVaultError, load_vault, save_vault


@dataclass(frozen=True)
class AIConfig:
    base_url: str
    api_path: str
    api_key: str | None
    model: str
    timeout_seconds: float

    @property
    def endpoint(self) -> str:
        path = self.api_path if self.api_path.startswith("/") else f"/{self.api_path}"
        return f"{self.base_url.rstrip('/')}{path}"

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def api_key_masked(self) -> str | None:
        if not self.api_key:
            return None
        if len(self.api_key) <= 8:
            return "*" * len(self.api_key)
        return f"{self.api_key[:4]}{'*' * max(4, len(self.api_key) - 8)}{self.api_key[-4:]}"


def _path() -> Path:
    return Path(settings.ai_credentials_path).expanduser().resolve()


def _environment_config() -> AIConfig:
    return AIConfig(
        base_url=settings.ai_base_url,
        api_path=settings.ai_api_path,
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        timeout_seconds=settings.ai_timeout_seconds,
    )


def get_ai_config() -> AIConfig:
    """Read the encrypted runtime configuration, falling back to environment values."""
    values: dict[str, Any] = {
        "base_url": _environment_config().base_url,
        "api_path": _environment_config().api_path,
        "api_key": _environment_config().api_key,
        "model": _environment_config().model,
        "timeout_seconds": _environment_config().timeout_seconds,
    }
    vault_path = _path()
    if vault_path.exists():
        try:
            stored = load_vault(vault_path)
        except CredentialVaultError:
            stored = {}
        for key in values:
            if key in stored and stored[key] is not None:
                values[key] = stored[key]
    return AIConfig(
        base_url=str(values["base_url"]).strip().rstrip("/"),
        api_path=str(values["api_path"]).strip() or "/v1/chat/completions",
        api_key=str(values["api_key"]).strip() if values.get("api_key") else None,
        model=str(values["model"]).strip() or "agnes-2.0-flash",
        timeout_seconds=max(1.0, float(values["timeout_seconds"])),
    )


def save_ai_config(
    *,
    base_url: str,
    api_path: str,
    model: str,
    timeout_seconds: float,
    api_key: str | None = None,
) -> AIConfig:
    current = get_ai_config()
    next_config = AIConfig(
        base_url=base_url.strip().rstrip("/"),
        api_path=api_path.strip() or "/v1/chat/completions",
        api_key=current.api_key if api_key is None else (api_key.strip() or None),
        model=model.strip(),
        timeout_seconds=max(1.0, float(timeout_seconds)),
    )
    save_vault(
        _path(),
        {
            "base_url": next_config.base_url,
            "api_path": next_config.api_path,
            "api_key": next_config.api_key,
            "model": next_config.model,
            "timeout_seconds": next_config.timeout_seconds,
        },
    )
    return next_config
