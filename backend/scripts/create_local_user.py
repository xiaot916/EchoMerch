"""Create the first local EchoMerch account or add a delegated account."""

from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings  # noqa: E402
from app.core.local_database import LocalDatabase  # noqa: E402
from app.modules.access.service import AccessControlStore  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a local EchoMerch access account.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--role", action="append", default=[], dest="roles")
    parser.add_argument("--store-id", action="append", default=[], type=int, dest="store_ids")
    parser.add_argument("--password-env", default="ECHO_BOOTSTRAP_ADMIN_PASSWORD")
    parser.add_argument("--database-path", type=Path, default=Path(settings.local_database_path))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    password = os.getenv(args.password_env)
    if not password:
        password = getpass.getpass("Password (minimum 12 characters): ")
    if len(password) < 12:
        raise SystemExit("Password must be at least 12 characters.")
    database_path = args.database_path.expanduser().resolve()
    LocalDatabase(database_path).initialize_schema()
    user = AccessControlStore(database_path).create_user(
        username=args.username,
        display_name=args.display_name,
        password=password,
        role_codes=args.roles or ["super_admin"],
        store_ids=args.store_ids,
        actor_user_id=None,
    )
    print(f"Created {user.username} with roles: {', '.join(user.roles)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
