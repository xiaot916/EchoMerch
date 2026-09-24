"""Core browser session primitives shared by all platform providers.

Everything in this module is platform-agnostic.  Platform-specific context
types and capture logic live in sibling modules (`alimama.py`, `sycm.py`,
`databank.py`, `cps.py`, `brandsearch.py`, `utry.py`).
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen


DEFAULT_DEBUG_PORT = 9222
DEFAULT_BROWSER_LOGIN_TIMEOUT = 180

# ``Chromium.get_tab`` has been observed to hang indefinitely on some calls
# (DrissionPage 4.1.1.4) when the attached browser is busy.  Every tab lookup
# therefore runs behind this watchdog so a stuck websocket degrades into "no
# reusable tab" instead of stalling the whole collection batch.
DP_TAB_RESOLVE_TIMEOUT = 8.0

# Opening a brand new tab legitimately takes longer than attaching to an
# existing one (a fresh renderer has to spin up), so it gets its own budget.
DP_NEW_TAB_TIMEOUT = 20.0

# Platforms reported by the collection-health surface.  Kept as codes so the
# legacy ``inspect_browser_platform_sessions(port)`` call style keeps working.
DEFAULT_INSPECT_CODES: tuple[str, ...] = ("sycm", "cps")


class RuntimeSessionUnavailable(RuntimeError):
    """Raised when a runtime browser session cannot be used safely."""


@dataclass(frozen=True)
class BrowserPlatformSession:
    """A secret-free snapshot of one platform inside the collection browser."""

    code: str
    name: str
    status: str
    detail: str
    page_detected: bool = False
    authenticated: bool = False
    cookie_detected: bool = False
    cookie_count: int = 0


@dataclass(frozen=True)
class PlatformSpec:
    code: str
    name: str
    home_url: str
    hosts: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeSession:
    cookie_header: str = field(repr=False)
    source: str = "env"
    cookie_count: int = 0


def add_session_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--session-source",
        choices=("env", "drissionpage"),
        default=os.getenv("ECHO_TMALL_SESSION_SOURCE", "drissionpage"),
        help="env reads the configured cookie variable; drissionpage attaches to a logged-in local browser.",
    )
    parser.add_argument(
        "--cookie-env",
        default="SYCM_COOKIE",
        help="Cookie environment variable used only when --session-source=env.",
    )
    parser.add_argument(
        "--browser-port",
        type=int,
        default=int(os.getenv("ECHO_TMALL_BROWSER_PORT", str(DEFAULT_DEBUG_PORT))),
        help="Chrome remote-debugging port used only when --session-source=drissionpage.",
    )


def cookie_header_from_mapping(cookies: Mapping[str, object]) -> str:
    pairs: list[str] = []
    for name, value in cookies.items():
        cookie_name = str(name).strip()
        cookie_value = str(value).strip()
        if not cookie_name or not cookie_value:
            continue
        if any(character in cookie_name or character in cookie_value for character in "\r\n;"):
            raise RuntimeSessionUnavailable("Browser returned an invalid cookie value.")
        pairs.append(f"{cookie_name}={cookie_value}")
    if not pairs:
        raise RuntimeSessionUnavailable("No usable cookies were found in the logged-in browser session.")
    return "; ".join(pairs)


def resolve_runtime_session(
    *,
    source: str,
    cookie_env: str,
    browser_port: int = DEFAULT_DEBUG_PORT,
    home_url: str = "https://sycm.taobao.com/portal/home.htm",
    platform_name: str = "生意参谋",
    expected_hosts: tuple[str, ...] = ("sycm.taobao.com",),
) -> RuntimeSession:
    if source == "env":
        cookie_header = os.getenv(cookie_env, "").strip()
        if not cookie_header:
            raise RuntimeSessionUnavailable(f"{cookie_env} is required for --session-source=env.")
        return RuntimeSession(
            cookie_header=_validate_cookie_header(cookie_header),
            source="env",
            cookie_count=_cookie_count(cookie_header),
        )
    if source == "drissionpage":
        from app.integrations.session.helpers import DrissionPageSessionProvider
        return DrissionPageSessionProvider(
            browser_port,
            home_url=home_url,
            platform_name=platform_name,
            expected_hosts=expected_hosts,
        ).read_session()
    raise ValueError(f"Unsupported session source: {source}")


def inspect_browser_platform_sessions(
    browser_port: int,
    specs: Mapping[str, PlatformSpec] | Iterable[str] | str | None = None,
) -> list[BrowserPlatformSession]:
    """Inspect existing tabs without navigating or exposing session material.

    ``specs`` accepts either a ``{code: PlatformSpec}`` mapping (preferred) or
    one or more platform *codes*, which are resolved through the registry —
    the HTTP layer passes codes, so both call styles must work.  When omitted
    it falls back to :data:`DEFAULT_INSPECT_CODES` (sycm + cps), which is what
    the collection-health endpoint reports.
    """
    from app.integrations.session.helpers import _browser_tabs, _platform_tab_session

    if specs is None:
        specs = DEFAULT_INSPECT_CODES
    if isinstance(specs, str):
        specs = (specs,)
    if not isinstance(specs, Mapping):
        specs = {code: _platform_spec_for_code(code) for code in specs}

    browser = DrissionPageBrowser(browser_port)
    results: list[BrowserPlatformSession] = []
    for spec in specs.values():
        tabs = _browser_tabs(browser, spec.hosts)
        probes = [_platform_tab_session(tab, spec) for tab in tabs]
        selected = next((item for item in probes if item.authenticated), None)
        if selected is None:
            selected = next((item for item in probes if item.page_detected), None)
        results.append(selected or BrowserPlatformSession(
            code=spec.code,
            name=spec.name,
            status="offline",
            detail=f"尚未打开{spec.name}业务页面。",
        ))
    return results


def _platform_spec_for_code(code: str) -> PlatformSpec:
    """Resolve a platform code (``"sycm"``) to its :class:`PlatformSpec`.

    Imported lazily because ``registry`` imports this module — a top-level
    import would be circular.  Called only on the legacy string-argument
    path, so the cost is irrelevant.
    """
    from app.integrations.session.registry import default_registry

    try:
        return default_registry.get(code).spec
    except KeyError as exc:
        known = ", ".join(sorted(default_registry.list_codes()))
        raise RuntimeSessionUnavailable(
            f"未知的采集平台代号 {code!r}，可选：{known}。"
        ) from exc


def open_browser_platform_session(
    browser_port: int,
    spec: PlatformSpec | str,
    *,
    timeout: float = 8.0,
    keep_open_on_success: bool = False,
) -> BrowserPlatformSession:
    """Open a fresh platform tab and quickly verify page arrival and login.

    ``spec`` accepts either a :class:`PlatformSpec` or a platform *code*
    string (``"sycm"``, ``"cps"``, ...).  The HTTP layer passes codes, and
    the registry already knows how to turn a code into a spec — resolving
    here keeps both call styles working.
    """
    from app.integrations.session.helpers import (
        _navigate_tab,
        _open_reusable_flow_tab,
        _platform_tab_session,
    )

    if isinstance(spec, str):
        spec = _platform_spec_for_code(spec)

    browser, tab, owns_tab = _open_reusable_flow_tab(browser_port, spec.hosts)
    if not owns_tab:
        existing = _platform_tab_session(tab, spec, assume_login_targets_platform=False)
        if existing.authenticated or existing.page_detected:
            return existing
    try:
        _navigate_tab(tab, spec.home_url, timeout=timeout)
        deadline = time.monotonic() + max(1.0, timeout)
        probe = _platform_tab_session(tab, spec, assume_login_targets_platform=True)
        while (
            not probe.authenticated
            and probe.status == "offline"
            and time.monotonic() < deadline
        ):
            try:
                tab.wait(0.25)
            except Exception:
                time.sleep(0.25)
            probe = _platform_tab_session(tab, spec, assume_login_targets_platform=True)
    except RuntimeSessionUnavailable:
        raise
    except Exception as exc:
        raise RuntimeSessionUnavailable(
            f"{spec.name}页面打开失败，请检查网络或在已打开的标签页中确认页面状态后重试。"
        ) from exc
    if probe.authenticated and not keep_open_on_success and owns_tab:
        browser.close_tab(tab)
    return probe


# ---- generic browser helpers (moved from tmall_session.py) ----

class DrissionPageBrowser:
    """Connect to the configured browser without owning the browser process."""

    def __init__(self, browser_port: int) -> None:
        if not 1 <= browser_port <= 65535:
            raise ValueError("--browser-port must be between 1 and 65535.")
        _require_debug_browser(browser_port)
        try:
            from DrissionPage import Chromium
        except ImportError as exc:
            raise RuntimeSessionUnavailable(
                "DrissionPage is not installed. Install backend requirements before using this source."
            ) from exc
        try:
            self.browser = Chromium(f"127.0.0.1:{browser_port}")
        except Exception as exc:
            raise RuntimeSessionUnavailable(
                f"无法接管 Chrome 调试端口 {browser_port}，请确认采集浏览器已启动。"
            ) from exc

    def list_tabs(self) -> list[dict[str, Any]]:
        """Return raw ``/json`` page records for this browser.

        This deliberately talks to the CDP HTTP endpoint directly instead of
        going through DrissionPage.  ``Chromium.get_tab`` opens a fresh
        websocket per tab and has been observed (DrissionPage 4.1.1.4) to hang
        forever on the second call when the browser is busy — which silently
        stalls every ``drissionpage`` session resolve.  The HTTP listing cannot
        hang: it has its own socket timeout and returns plain JSON.
        """

        address = str(getattr(self.browser, "address", "") or "")
        if not address:
            return []
        try:
            with urlopen(f"http://{address}/json", timeout=3.0) as response:
                records = json.loads(response.read().decode("utf-8"))
        except Exception:
            return []
        if not isinstance(records, list):
            return []
        return [r for r in records if isinstance(r, Mapping)]

    def find_tab(self, expected_hosts: tuple[str, ...]) -> Any | None:
        """Return a live tab whose URL matches ``expected_hosts``.

        Deliberately avoids ``Chromium.get_tab``: that helper acquires the
        browser-wide lock and constructs a ``MixTab``, and in DrissionPage
        4.1.1.4 the second such call blocks forever once another tab object is
        alive.  That single behaviour was stalling every ``drissionpage``
        session resolve.  ``ChromiumTab(browser, tab_id)`` performs no locking
        and was measured at ~0.01s per tab, so tab reuse stays cheap.
        """

        for record in self.list_tabs():
            if record.get("type") != "page":
                continue
            url = str(record.get("url") or "").strip()
            try:
                is_web_page = urlparse(url).scheme.lower() in {"http", "https"}
            except ValueError:
                is_web_page = False
            if (
                not url
                or not is_web_page
                or _is_login_url(url)
                or (expected_hosts and not _url_matches_hosts(url, expected_hosts))
            ):
                continue
            tab_id = str(record.get("id") or "").strip()
            if not tab_id:
                continue
            tab = self._open_tab_safely(tab_id)
            if tab is not None:
                return tab
        return None

    def _open_tab_safely(self, tab_id: str) -> Any | None:
        """Attach to ``tab_id`` without the locking ``get_tab`` code path.

        ``ChromiumTab`` avoids the browser-wide lock that makes ``get_tab``
        deadlock, but DrissionPage can still block intermittently while it
        primes a freshly attached target.  A watchdog converts any such stall
        into "no reusable tab" — the caller then opens its own tab — instead of
        freezing the whole collection batch.
        """

        try:
            from DrissionPage._pages.chromium_tab import ChromiumTab
        except ImportError:
            return None

        result: list[Any] = []

        def _attach() -> None:
            try:
                result.append(ChromiumTab(self.browser, tab_id))
            except BaseException:  # noqa: BLE001 - best-effort attachment
                pass

        worker = threading.Thread(target=_attach, daemon=True, name="dptab-attach")
        worker.start()
        worker.join(timeout=DP_TAB_RESOLVE_TIMEOUT)
        if worker.is_alive() or not result:
            return None
        return result[0]

    def new_tab(self, url: str | None = None) -> Any:
        """Open a fresh tab, bounded by a watchdog like every other lookup."""

        result: list[Any] = []
        failure: list[BaseException] = []

        def _open() -> None:
            try:
                # Supplying the destination to Chrome avoids exposing a
                # transient about:blank tab.  Providers still reload after
                # attaching their listener, so no bootstrap request is lost.
                result.append(self.browser.new_tab(url=url, background=False))
            except BaseException as exc:  # noqa: BLE001 - re-raised below
                failure.append(exc)

        worker = threading.Thread(target=_open, daemon=True, name="dptab-new")
        worker.start()
        worker.join(timeout=DP_NEW_TAB_TIMEOUT)
        if worker.is_alive():
            raise RuntimeSessionUnavailable(
                "采集浏览器在 20 秒内没有创建新标签页，请确认浏览器未卡死或弹窗阻塞后重试。"
            )
        if failure:
            raise RuntimeSessionUnavailable(
                "已连接采集浏览器，但无法创建独立采集标签页。"
            ) from failure[0]
        if not result or result[0] is None:
            raise RuntimeSessionUnavailable("已连接采集浏览器，但没有可用采集标签页。")
        return result[0]

    def close_tab(self, tab: Any) -> None:
        try:
            self.browser.close_tabs(tab)
        except Exception:
            pass


def _require_debug_browser(port: int) -> None:
    try:
        with urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.5) as response:
            if response.status != 200:
                raise RuntimeSessionUnavailable(
                    f"Chrome debugging endpoint returned HTTP {response.status} on port {port}."
                )
    except (OSError, URLError, socket.timeout) as exc:
        raise RuntimeSessionUnavailable(
            f"No Chrome remote-debugging session is listening on 127.0.0.1:{port}. "
            "Start the dedicated session browser, log in manually, then retry."
        ) from exc


def _validate_cookie_header(value: str) -> str:
    if "\r" in value or "\n" in value:
        raise RuntimeSessionUnavailable("Cookie headers cannot contain line breaks.")
    return value


def _cookie_count(value: str) -> int:
    return len([part for part in value.split(";") if part.strip()])


def _cookie_value(header: str, name: str) -> str:
    for part in header.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key == name:
            return value.strip()
    return ""


def _is_login_url(value: str) -> bool:
    lowered = value.lower()
    return "login" in lowered or "passport" in lowered


def _url_matches_hosts(value: str, hosts: tuple[str, ...]) -> bool:
    try:
        hostname = (urlparse(value).hostname or "").lower()
    except ValueError:
        return False
    return any(hostname == host or hostname.endswith(f".{host}") for host in hosts)
