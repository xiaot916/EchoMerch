"""Launch and reuse the dedicated browser used by collection workers."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from app.core.config import PROJECT_ROOT
from app.integrations.tmall_session import DEFAULT_SYCM_HOME_URL


DEFAULT_PROFILE_DIR = PROJECT_ROOT / "artifacts" / "runtime" / "tmall-browser-profile"


class CollectionBrowserLaunchError(RuntimeError):
    """Raised when the managed collection browser cannot be started."""


@dataclass(frozen=True)
class CollectionBrowserLaunch:
    started: bool
    reused: bool
    process_id: int | None = None


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
