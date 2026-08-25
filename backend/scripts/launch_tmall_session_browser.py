"""Launch an isolated Chrome profile for manual Tmall/SYCM login.

The profile is local runtime state. It is intentionally excluded from SQLite,
worker logs, and application configuration.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.collection_browser import (  # noqa: E402
    CollectionBrowserLaunchError,
    DEFAULT_PROFILE_DIR,
    launch_collection_browser,
)
from app.integrations.tmall_session import DEFAULT_DEBUG_PORT, DEFAULT_SYCM_HOME_URL  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Launch an isolated Chrome session for manual SYCM login."
    )
    parser.add_argument("--browser-port", type=int, default=DEFAULT_DEBUG_PORT)
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
    )
    parser.add_argument("--url", default=DEFAULT_SYCM_HOME_URL)
    parser.add_argument("--chrome-path", type=Path)
    args = parser.parse_args()

    if not 1 <= args.browser_port <= 65535:
        raise ValueError("--browser-port must be between 1 and 65535.")
    outcome = launch_collection_browser(
        args.browser_port,
        profile_dir=args.profile_dir,
        url=args.url,
        browser_path=args.chrome_path,
    )
    action = "reused" if outcome.reused else "started"
    print(f"Session browser {action} on port {args.browser_port}. Log in manually if prompted.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CollectionBrowserLaunchError, OSError, ValueError) as exc:
        print(f"Could not start session browser: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
