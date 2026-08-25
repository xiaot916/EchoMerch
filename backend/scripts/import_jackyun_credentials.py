"""Import a locally refreshed Jackyun token cache into the DPAPI vault.

The script deliberately prints only metadata. The cache and vault stay local;
tokens, cookies, and signing secrets are never echoed to the terminal.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.integrations.jackyun_credentials import CredentialVaultError, load_vault, save_vault


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Jackyun token cache into the encrypted EchoMerch vault")
    parser.add_argument("--cache", type=Path, default=None, help="local Jackyun token_cache.json")
    parser.add_argument("--vault", type=Path, default=Path(settings.jackyun_credentials_path))
    parser.add_argument("--interactive", action="store_true", help="read the new token pair and optional cookie without echoing secrets")
    args = parser.parse_args()

    if args.interactive:
        try:
            access_token = getpass.getpass("Access Token (hidden): ").strip()
            refresh_token = getpass.getpass("Refresh Token (hidden): ").strip()
            cookie = getpass.getpass("Cookie (hidden, optional): ").strip()
            if not access_token or not refresh_token:
                print("status=invalid_input")
                return 2
            current = load_vault(args.vault)
            updates = {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_at": time.time() + settings.jackyun_token_ttl_seconds,
                "updated_at": time.time(),
            }
            if cookie:
                updates["cookie"] = cookie
            save_vault(args.vault, {**current, **updates})
            print(f"status=imported vault={args.vault} has_access_token=True has_refresh_token=True cookie_saved={bool(cookie)} refresh_window_seconds={settings.jackyun_token_ttl_seconds}")
            return 0
        except (KeyboardInterrupt, EOFError):
            print("status=cancelled")
            return 2
        except (OSError, CredentialVaultError) as exc:
            print(f"status=failed reason={exc.__class__.__name__}")
            return 1

    cache_path = args.cache or (Path(__file__).resolve().parents[3] / "Arachne" / "JackyunV5" / "token_cache.json")
    if not cache_path.exists():
        print("status=missing_cache")
        return 2
    try:
        raw = json.loads(cache_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not raw.get("refresh_token"):
            print("status=invalid_cache")
            return 2
        current = load_vault(args.vault)
        imported = {
            key: raw[key]
            for key in ("access_token", "refresh_token", "expires_at", "updated_at", "user_id", "member_name")
            if raw.get(key) not in (None, "", [])
        }
        save_vault(args.vault, {**current, **imported})
    except (OSError, UnicodeError, json.JSONDecodeError, CredentialVaultError) as exc:
        print(f"status=failed reason={exc.__class__.__name__}")
        return 1
    print(f"status=imported cache={cache_path} vault={args.vault} has_access_token={bool(imported.get('access_token'))} has_refresh_token={bool(imported.get('refresh_token'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
