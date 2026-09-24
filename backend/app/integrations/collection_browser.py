"""Launch and reuse the dedicated browser used by collection workers."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from app.core.config import PROJECT_ROOT
from app.integrations.tmall_session import DEFAULT_SYCM_HOME_URL


DEFAULT_PROFILE_DIR = PROJECT_ROOT / "artifacts" / "runtime" / "tmall-browser-profile"
SELLER_LOGIN_URL = (
    "https://loginmyseller.taobao.com/?from=taobaoindex&f=top&style=&sub=true&"
    "redirect_url=https%3A%2F%2Fmyseller.taobao.com%2Fhome.htm%2FQnworkbenchHome%2F"
)
SELLER_PAGE_HOSTS = ("myseller.taobao.com", "loginmyseller.taobao.com", "havanalogin.taobao.com")


class CollectionBrowserLaunchError(RuntimeError):
    """Raised when the managed collection browser cannot be started."""


@dataclass(frozen=True)
class CollectionBrowserLaunch:
    started: bool
    reused: bool
    process_id: int | None = None


@dataclass(frozen=True)
class SellerLoginStatus:
    """Secret-free status of the store login flow in the managed browser."""

    status: str
    detail: str
    browser_connected: bool
    debug_port: int
    login_url: str = SELLER_LOGIN_URL
    page_url: str | None = None


def _browser_page_records(port: int) -> list[dict[str, object]]:
    try:
        with urlopen(f"http://127.0.0.1:{port}/json", timeout=2.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, socket.timeout, TimeoutError, ValueError):
        return []
    return [
        item for item in payload
        if isinstance(item, dict) and item.get("type") == "page"
    ] if isinstance(payload, list) else []


def inspect_seller_login(port: int) -> SellerLoginStatus:
    """Inspect the seller login redirect without attaching to page WebSockets."""
    if not browser_debug_connected(port):
        return SellerLoginStatus(
            status="offline",
            detail="采集浏览器未连接。",
            browser_connected=False,
            debug_port=port,
        )
    records = _browser_page_records(port)
    seller_pages: list[tuple[str, str]] = []
    for record in records:
        value = str(record.get("url") or "")
        try:
            host = (urlparse(value).hostname or "").lower()
        except ValueError:
            continue
        if host in SELLER_PAGE_HOSTS:
            seller_pages.append((value, host))
    authenticated = next(
        (
            (url, host)
            for url, host in seller_pages
            if host == "myseller.taobao.com" and not _looks_like_seller_login_url(url)
        ),
        None,
    )
    if authenticated:
        return SellerLoginStatus(
            status="authenticated",
            detail="千牛业务页已打开；生意参谋、CPS 等报表会话需分别验证，不能仅凭此页判断采集可用。",
            browser_connected=True,
            debug_port=port,
            page_url=authenticated[0],
        )
    if seller_pages:
        return SellerLoginStatus(
            status="login_required",
            detail="千牛登录页已打开，请在采集浏览器中使用扫码或账号登录。",
            browser_connected=True,
            debug_port=port,
            page_url=seller_pages[0][0],
        )
    return SellerLoginStatus(
        status="ready",
        detail="采集浏览器已连接，尚未打开店铺登录页。",
        browser_connected=True,
        debug_port=port,
    )


def _looks_like_seller_login_url(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in ("/login", "passport", "signin", "mini_login"))


def open_seller_login(port: int) -> SellerLoginStatus:
    """Open the official seller login page once, reusing an existing tab."""
    current = inspect_seller_login(port)
    if current.status in {"authenticated", "login_required"}:
        return current
    if not current.browser_connected:
        launch_collection_browser(port, url=SELLER_LOGIN_URL)
        current = inspect_seller_login(port)
    if current.status == "ready":
        try:
            # /json/new is an HTTP-only CDP endpoint and therefore works even
            # before the browser is restarted with remote-allow-origins. It
            # also creates the tab with the destination already set, avoiding
            # a visible about:blank page.
            request_url = f"http://127.0.0.1:{port}/json/new?{quote(SELLER_LOGIN_URL, safe='')}"
            request = Request(request_url, method="PUT")
            with urlopen(request, timeout=5.0):
                pass
        except Exception as exc:
            raise CollectionBrowserLaunchError(
                "无法打开千牛登录页，请确认采集浏览器已启动且调试端口可用。"
            ) from exc
    return inspect_seller_login(port)


def browser_debug_connected(port: int, *, timeout: float = 1.5) -> bool:
    if not 1 <= port <= 65535:
        return False
    try:
        with urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout) as response:
            return response.status == 200
    except (OSError, URLError, socket.timeout, TimeoutError):
        return False


def find_browser_executable() -> Path | None:
    program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
    candidates = (
        program_files / "Google" / "Chrome" / "Application" / "chrome.exe",
        program_files_x86 / "Google" / "Chrome" / "Application" / "chrome.exe",
        local_app_data / "Google" / "Chrome" / "Application" / "chrome.exe",
        program_files / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        program_files_x86 / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        local_app_data / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    )
    return next((path for path in candidates if path.is_file()), None)


def launch_collection_browser(
    port: int,
    *,
    profile_dir: Path | None = None,
    url: str = DEFAULT_SYCM_HOME_URL,
    browser_path: Path | None = None,
    wait_timeout: float = 10.0,
) -> CollectionBrowserLaunch:
    """Start the isolated visible browser and wait for its debug port.

    The operation is idempotent: an existing listener is reused instead of
    starting a second process against the same profile.
    """

    if not 1 <= port <= 65535:
        raise CollectionBrowserLaunchError("浏览器端口必须在 1 到 65535 之间。")
    if browser_debug_connected(port):
        return CollectionBrowserLaunch(started=False, reused=True)

    executable = Path(browser_path).resolve() if browser_path else find_browser_executable()
    if executable is None or not executable.is_file():
        raise CollectionBrowserLaunchError("未找到 Chrome 或 Edge，请先安装浏览器后重试。")

    resolved_profile = Path(profile_dir or DEFAULT_PROFILE_DIR).expanduser().resolve()
    resolved_profile.mkdir(parents=True, exist_ok=True)
    command = [
        str(executable),
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        # Chrome 94+ rejects WebSocket clients that send an Origin header
        # unless the origin is explicitly allowed.  DrissionPage is such a
        # client; without this flag the HTTP /json endpoint still works, but
        # every tab attach blocks until the session provider falls back to a
        # new blank tab.
        "--remote-allow-origins=*",
        f"--user-data-dir={resolved_profile}",
        "--no-first-run",
        "--no-default-browser-check",
        url,
    ]
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    try:
        process = subprocess.Popen(
            command,
            cwd=str(PROJECT_ROOT),
            creationflags=creationflags,
            close_fds=True,
        )
    except OSError as exc:
        raise CollectionBrowserLaunchError(f"采集浏览器启动失败：{exc}") from exc

    deadline = time.monotonic() + max(1.0, wait_timeout)
    while time.monotonic() < deadline:
        if browser_debug_connected(port, timeout=0.5):
            return CollectionBrowserLaunch(started=True, reused=False, process_id=process.pid)
        return_code = process.poll()
        if return_code is not None:
            raise CollectionBrowserLaunchError(f"采集浏览器启动后立即退出，退出码 {return_code}。")
        time.sleep(0.2)

    raise CollectionBrowserLaunchError(
        f"采集浏览器已启动，但调试端口 {port} 在 {wait_timeout:g} 秒内没有就绪。"
    )
