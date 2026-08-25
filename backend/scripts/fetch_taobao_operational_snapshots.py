from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MTOP_URL = "https://h5api.m.taobao.com/h5/mtop.taobao.argus.mtopapirouterservice.process/1.0/"
MTOP_APP_KEY = "12574478"
ACTIVITY_URL = "https://sale.taobao.com/domain/item/query.json"


@dataclass(frozen=True)
class FetchResult:
    status: int
    code: int | None
    message: str | None
    output: str
    bytes: int

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300 and self.code in (0, None)


def fetch_risk_price(*, output: Path, cookie: str, timeout: int = 30, size: int = 100) -> FetchResult:
    return _mtop_post(
        api_name="GetRiskDetectListInfo",
        params={"size": size, "riskCode": "ITEM_PREDICT_RISK_DETECT"},
        output=output, cookie=cookie, timeout=timeout,
    )


def fetch_current_prices(*, output: Path, cookie: str, page: int, size: int = 500, timeout: int = 30) -> FetchResult:
    return _mtop_post(
        api_name="getAllItemCurrentPriceList",
        params={"page": page, "size": size, "queryAttention": "false"},
        output=output, cookie=cookie, timeout=timeout,
    )


def fetch_activity_items(*, output: Path, cookie: str, snapshot_type: str, page: int, page_size: int = 100, timeout: int = 30) -> FetchResult:
    configurations = {
        "bybt_online": {"frontActivityTypeId": "11", "siteIds": "127", "status": "1"},
        "bybt_pending": {"frontActivityTypeId": "11", "siteIds": "127", "status": "8"},
        "flash_sale_online": {"frontActivityTypeId": "105", "siteIds": "180", "signObject": "1", "status": "8"},
    }
    try:
        configuration = configurations[snapshot_type]
    except KeyError as exc:
        raise ValueError(f"unknown snapshot type: {snapshot_type}") from exc
    token = _cookie_value(cookie, "_tb_token_")
    if not token:
        raise RuntimeError("The managed Taobao session has no _tb_token_ cookie.")
    params = {
        "_tb_token_": token,
        "excludeButtonIds": "1207",
        "keySet": (
            "themisInfo,itemLink,itemName,activityPrice,originalPrice,supplyPrice,inventory,soldCount,itemPic,statusName,"
            "activityPriceName,onlineEndTime,supplyPriceName,limitNum,commonActivityTags,materialStatusName,signTime,"
            "onlineStartTime,activityName,buttonList,itemId,icStatusName,activityUrl,juId,icStatus,status,playSignInfo"
        ),
        "querier": "juItemCompositeQuerier",
        "pageSizeCode": "itemList-juItemPageSize",
        "currentPage": str(page),
        "sortType": "2",
        "page": str(page),
        "pageSize": str(page_size),
        **configuration,
    }
    body, status = _request(ACTIVITY_URL + "?" + urlencode(params), headers={
        "accept": "application/json, text/plain, */*", "cookie": cookie,
        "referer": "https://myseller.taobao.com/home.htm/qianniu-service-market/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
    }, timeout=timeout)
    return _write_result(body=body, status=status, output=output, extra={"snapshotType": snapshot_type})


def _mtop_post(*, api_name: str, params: dict[str, Any], output: Path, cookie: str, timeout: int) -> FetchResult:
    token = _cookie_value(cookie, "_m_h5_tk").split("_", 1)[0]
    if not token:
        raise RuntimeError("The managed Taobao session has no usable _m_h5_tk cookie.")
    payload = {
        "api": api_name,
        "params": json.dumps(params, ensure_ascii=False, separators=(",", ":")),
        "pageVersion": "2.1.0",
        "source": "mkt_home",
    }
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    timestamp = str(int(time.time() * 1000))
    signature = hashlib.md5(f"{token}&{timestamp}&{MTOP_APP_KEY}&{data}".encode("utf-8")).hexdigest()
    query = urlencode({
        "jsv": "2.6.1", "appKey": MTOP_APP_KEY, "t": timestamp, "sign": signature,
        "api": "mtop.taobao.argus.MTopApiRouterService.process", "v": "1.0",
        "ttid": "11320@taobao_WEB_9.9.99", "dataType": "json", "type": "originaljson", "timeout": "8000",
    })
    encoded = urlencode({"data": data}).encode("utf-8")
    request = Request(MTOP_URL + "?" + query, data=encoded, method="POST", headers={
        "accept": "application/json", "content-type": "application/x-www-form-urlencoded",
        "cookie": cookie, "origin": "https://qn.taobao.com", "referer": "https://qn.taobao.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36",
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            body, status = response.read(), response.status
    except HTTPError as exc:
        body, status = exc.read(), exc.code
    return _write_result(body=body, status=status, output=output)


def _request(url: str, *, headers: dict[str, str], timeout: int) -> tuple[bytes, int]:
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read(), response.status
    except HTTPError as exc:
        return exc.read(), exc.code


def _write_result(*, body: bytes, status: int, output: Path, extra: dict[str, Any] | None = None) -> FetchResult:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    normalized: bytes
    if isinstance(payload, dict):
        if extra:
            payload = {**payload, **extra}
        normalized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        code, message = _response_status(payload)
    else:
        normalized, code, message = body, None, "non-json response"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(normalized)
    if code == 200:
        code = 0
    return FetchResult(status=status, code=code, message=message, output=str(output), bytes=len(normalized))


def _response_status(payload: dict[str, Any]) -> tuple[int | None, str | None]:
    if payload.get("success") is False:
        return 1, str(payload.get("message") or payload.get("msg") or "request failed")
    ret = payload.get("ret")
    if isinstance(ret, list) and any("FAIL" in str(value).upper() for value in ret):
        return 1, str(ret[0])
    value = payload.get("code", payload.get("retCode"))
    try:
        code = int(value) if value is not None else 0
    except (TypeError, ValueError):
        code = None
    return code, str(payload.get("message") or payload.get("msg") or "") or None


def _cookie_value(header: str, name: str) -> str:
    for part in header.split(";"):
        if "=" not in part:
            continue
        key, value = part.strip().split("=", 1)
        if key == name:
            return value.strip()
    return ""
