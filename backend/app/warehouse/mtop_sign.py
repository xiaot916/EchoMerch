from __future__ import annotations

import hashlib
import json
import time
from typing import Any


DEFAULT_MTOP_APP_KEY = "12574478"


def token_from_m_h5_tk(cookie_value: str) -> str:
    return cookie_value.split("_", 1)[0]


def stable_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def sign_mtop_data(
    data_json: str,
    m_h5_tk: str,
    app_key: str = DEFAULT_MTOP_APP_KEY,
    timestamp_ms: str | None = None,
) -> tuple[str, str]:
    timestamp = timestamp_ms or str(int(time.time() * 1000))
    token = token_from_m_h5_tk(m_h5_tk)
    raw = f"{token}&{timestamp}&{app_key}&{data_json}"
    return timestamp, hashlib.md5(raw.encode("utf-8")).hexdigest()
