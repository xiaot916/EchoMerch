from typing import Literal

from pydantic import BaseModel


class SystemCapabilities(BaseModel):
    mode: Literal["read_only"]
    legacy_source: Literal["configured", "not_configured"]
    enabled_modules: list[str]
    disabled_modules: list[str]
    safety_rules: list[str]
