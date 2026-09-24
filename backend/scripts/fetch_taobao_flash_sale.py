from __future__ import annotations

import argparse
import json
import sys
import threading
from dataclasses import asdict, dataclass
from datetime import date, datetime, time as day_time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.integrations.tmall_session import (  # noqa: E402
    add_session_source_arguments,
    resolve_runtime_session,
)


FLASH_SALE_HOME_URL = "https://myseller.taobao.com/home.htm/ltao-home/"
FLASH_SALE_API_URL = "https://sale.taobao.com/extend/api/tbhjActivityDataQuery.json"
FLASH_SALE_ITEMS_API_URL = "https://sale.taobao.com/extend/api/tbhjItemDataQuery.json"


@dataclass(frozen=True)
class FetchResult:
    status: int
    code: int | None
    message: str | None
    output: str
    bytes: int

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and self.code == 0


def fetch_taobao_flash_sale(
    *,
    day: date,
    output: Path,
    cookie: str,
    timeout: int = 30,
    browser_port: int | None = None,
) -> FetchResult:
    timestamp = int(
        datetime.combine(day, day_time.min, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()
        * 1000
    )
    params = {
        "startTime": str(timestamp),
        "endTime": str(timestamp),
        "__sm_request__": "true",
    }
    url = f"{FLASH_SALE_API_URL}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "cookie": cookie,
            "origin": "https://myseller.taobao.com",
            "priority": "u=1, i",
            "referer": "https://myseller.taobao.com/home.htm/ltao-home/",
            "sec-ch-ua": '"Not;A=Brand";v="8", "Chromium";v="150", "Google Chrome";v="150"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-site",
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/150.0.0.0 Safari/537.36"
            ),
        },
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
    except HTTPError as exc:
        body = exc.read()
        status = exc.code

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        if browser_port is not None:
            try:
                status, body = _fetch_in_existing_browser(browser_port, url, timeout=timeout)
            except RuntimeError:
                output.write_bytes(body)
                raise
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
    code, message = _response_code_and_message(payload) if payload is not None else (None, "non-json response")
    output.write_bytes(body)

    return FetchResult(status, code, message, str(output), len(body))


def _fetch_in_existing_browser(
    browser_port: int, url: str, *, timeout: int, include_tb_token: bool = False,
) -> tuple[int, bytes]:
    from app.integrations.session.core import DrissionPageBrowser, RuntimeSessionUnavailable

    parsed = urlparse(url)
    if parsed.scheme != "https" or f"{parsed.scheme}://{parsed.netloc}{parsed.path}" not in (
        FLASH_SALE_API_URL, FLASH_SALE_ITEMS_API_URL,
    ):
        raise ValueError("千牛页面回退只支持已登记的秒杀只读报表接口。")
    tab = DrissionPageBrowser(browser_port).find_tab(("myseller.taobao.com",))
    if tab is None:
        raise RuntimeSessionUnavailable("秒杀接口直连失败，且没有可复用的千牛页面。")
    script = """(async () => {
      const endpoint = new URL(%s);
      if (%s) {
        const token = document.cookie.split('; ').find(part => part.startsWith('_tb_token_='));
        if (!token) return {error: 'missing_token'};
        endpoint.searchParams.set('_tb_token_', decodeURIComponent(token.slice(11)));
      }
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), %d);
      try {
        const response = await fetch(endpoint, {credentials: 'include', signal: controller.signal});
        return {status: response.status, body: await response.text()};
      } catch (_) { return {error: 'request_failed'}; }
      finally { clearTimeout(timer); }
    })()""" % (json.dumps(url), json.dumps(include_tb_token), max(1000, timeout * 1000))
    result: list[object] = []

    def evaluate() -> None:
        try:
            result.append(tab.run_cdp("Runtime.evaluate", expression=script, awaitPromise=True, returnByValue=True))
        except Exception:
            result.append(None)

    worker = threading.Thread(target=evaluate, daemon=True, name="flash-sale-browser-fetch")
    worker.start()
    worker.join(timeout=max(1, timeout) + 5)
    value = result[0].get("result", {}).get("value") if result and isinstance(result[0], dict) else None
    if worker.is_alive() or not isinstance(value, dict) or not isinstance(value.get("body"), str):
        raise RuntimeSessionUnavailable("千牛页面内的秒杀报表请求失败，请确认页面登录和网络状态。")
    return int(value["status"]), value["body"].encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Taobao flash-sale metrics for one day.")
    parser.add_argument("--day", type=date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    add_session_source_arguments(parser)
    args = parser.parse_args()
    session = resolve_runtime_session(
        source=args.session_source,
        cookie_env=args.cookie_env,
        browser_port=args.browser_port,
        home_url=FLASH_SALE_HOME_URL,
        platform_name="淘宝秒杀",
        expected_hosts=("myseller.taobao.com",),
    )
    result = fetch_taobao_flash_sale(
        day=args.day,
        output=args.output,
        cookie=session.cookie_header,
        browser_port=args.browser_port if args.session_source == "drissionpage" else None,
    )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def _response_code_and_message(payload: object) -> tuple[int | None, str | None]:
    if not isinstance(payload, dict):
        return None, "unexpected response payload"
    if payload.get("success") is False:
        return 1, str(payload.get("message") or payload.get("msg") or "request failed")
    code = payload.get("code")
    try:
        normalized_code = int(code) if code is not None else 0
    except (TypeError, ValueError):
        normalized_code = None
    return normalized_code, str(payload.get("message") or payload.get("msg") or "") or None


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"Fetch failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
