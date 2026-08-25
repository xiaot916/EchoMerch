"""Per-user encrypted storage for the long-lived Jackyun credentials.

Windows DPAPI binds the vault to the current Windows user and machine. The
vault is intentionally not a database record and is never returned by an API.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

try:
    import win32crypt
except ImportError:  # pragma: no cover - only used on non-Windows dev hosts
    win32crypt = None


MAGIC = b"ECHOMERCH-JACKYUN-DPAPI\0"


class CredentialVaultError(RuntimeError):
    pass


def load_vault(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if win32crypt is None:
        raise CredentialVaultError("当前环境没有 Windows DPAPI，无法读取吉客云凭证库")
    try:
        raw = path.read_bytes()
        if not raw.startswith(MAGIC):
            raise CredentialVaultError("吉客云凭证库格式无效")
        result = win32crypt.CryptUnprotectData(raw[len(MAGIC):], None, None, None, 0)
        decrypted = result[-1]
        payload = json.loads(decrypted.decode("utf-8"))
        return payload if isinstance(payload, dict) else {}
    except CredentialVaultError:
        raise
    except Exception as exc:
        raise CredentialVaultError("吉客云凭证库无法解密或内容无效") from exc


def save_vault(path: Path, values: dict[str, Any]) -> None:
    if win32crypt is None:
        raise CredentialVaultError("当前环境没有 Windows DPAPI，拒绝以明文保存吉客云凭证")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        encrypted = win32crypt.CryptProtectData(payload, "EchoMerch Jackyun credentials", None, None, None, 0)
        temporary.write_bytes(MAGIC + encrypted)
        os.replace(temporary, path)
    except Exception as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise CredentialVaultError("吉客云凭证库保存失败") from exc


def vault_contains_plaintext(path: Path, needles: list[str]) -> bool:
    """Diagnostic helper used by tests; never exposed through an API."""
    if not path.exists():
        return False
    raw = path.read_bytes()
    return any(needle.encode("utf-8") in raw for needle in needles)
