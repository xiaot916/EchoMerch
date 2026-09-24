from __future__ import annotations

from datetime import date
from typing import Iterable

from app.core.business_days import today_in_shanghai


CURRENT_DAY_ONLY_DATASETS = frozenset({"taobao_operational_snapshots"})


def validate_collection_day(dataset_names: Iterable[str], day: date) -> None:
    if CURRENT_DAY_ONLY_DATASETS.intersection(dataset_names) and day != today_in_shanghai():
        raise ValueError(
            f"淘宝运营商品快照只能采集上海时区当天（{today_in_shanghai()}）；"
            f"{day} 的实时状态无法追溯，请勿用今天的数据补写历史。"
        )
