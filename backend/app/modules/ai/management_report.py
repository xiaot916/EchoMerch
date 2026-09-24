from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Any

from app.modules.ai.schemas import ArtifactSpec, PeriodReportRequest


_CORE_METRICS: tuple[tuple[str, str, str, bool], ...] = (
    ("paid_amount", "支付金额", "gmv", False),
    ("net_paid_amount", "净支付金额", "net_gmv", False),
    ("visitors", "访客数", "visitors", False),
    ("buyers", "支付买家数", "buyers", False),
    ("conversion_rate", "支付转化率", "conversion_rate", True),
    ("customer_unit_price", "客单价", "customer_unit_price", False),
    ("refund_amount", "退款金额", "refund_amount", False),
    ("refund_rate", "退款金额占比", "refund_rate", True),
)


def resolve_review_ranges(
    request: PeriodReportRequest,
    *,
    minimum: date,
    maximum: date,
) -> tuple[date, date, date, date]:
    """Resolve a bounded review range and an explicit comparison range."""
    current_end = min(request.end_date or request.anchor_date or maximum, maximum)
    current_start = request.start_date or current_end.replace(month=1, day=1)
    if current_start < minimum or current_start > current_end:
        raise ValueError(f"经营复盘区间必须在 {minimum.isoformat()} 至 {maximum.isoformat()} 之间")

    if request.comparison_mode == "custom":
        comparison_start = request.comparison_start_date
        comparison_end = request.comparison_end_date
        if comparison_start is None or comparison_end is None:
            raise ValueError("自定义对比必须同时提供对比开始和结束日期")
    elif request.comparison_mode == "previous_period":
        days = (current_end - current_start).days + 1
        comparison_end = current_start - timedelta(days=1)
        comparison_start = comparison_end - timedelta(days=days - 1)
    else:
        comparison_start = _shift_year(current_start, -1)
        comparison_end = _shift_year(current_end, -1)

    if comparison_start < minimum or comparison_end > maximum or comparison_start > comparison_end:
        raise ValueError(f"对比区间必须在 {minimum.isoformat()} 至 {maximum.isoformat()} 之间")
    return current_start, current_end, comparison_start, comparison_end


def build_management_review(
    *,
    current: dict[str, Any],
    comparison: dict[str, Any],
    request: PeriodReportRequest,
    current_range: tuple[date, date],
    comparison_range: tuple[date, date],
    support: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[ArtifactSpec], list[str]]:
    """Build deterministic report sections before any model writes narrative."""
    current_start, current_end = current_range
    comparison_start, comparison_end = comparison_range
    current_ops = dict(current.get("operations") or {})
    comparison_ops = dict(comparison.get("operations") or {})
    comparison_label = {
        "same_period_last_year": "同比",
        "previous_period": "环比",
        "custom": "自定义对比",
    }[request.comparison_mode]

    metric_rows, comparison_payload = _core_metric_comparison(current_ops, comparison_ops, comparison_label)
    monthly_trend = _monthly_comparison(
        list(current.get("daily_series") or []),
        list(comparison.get("daily_series") or []),
    )
    traffic_rows = _dimension_comparison(
        support.get("traffic_current", {}).get("rows") or [],
        support.get("traffic_comparison", {}).get("rows") or [],
        key="source",
        label="流量来源",
        metrics=(("gmv", "支付金额"), ("visitors", "访客"), ("buyers", "支付买家")),
    )
    product_structure = support.get("product_structure") or {}
    product_series = _product_structure_rows(product_structure.get("series") or [])
    product_types = _product_structure_rows(product_structure.get("types") or [])
    customer_rows = _aggregate_comparison_rows(
        support.get("customers_current", {}).get("aggregates") or {},
        support.get("customers_comparison", {}).get("aggregates") or {},
        (
            ("new_visitors", "新访客"),
            ("new_paid_buyers", "新访成交"),
            ("no_purchase_returners", "未购回访"),
            ("no_purchase_buyers", "未购回访成交"),
            ("repeat_returners", "已购回访"),
            ("repeat_buyers", "老客复购"),
        ),
    )
    member_rows = _aggregate_comparison_rows(
        support.get("members_current", {}).get("aggregates") or {},
        support.get("members_comparison", {}).get("aggregates") or {},
        (("gmv", "会员成交金额"), ("member_buyers", "会员成交人数"), ("new_members", "新增会员")),
    )
    service_rows = _aggregate_comparison_rows(
        support.get("service_current", {}).get("aggregates") or {},
        support.get("service_comparison", {}).get("aggregates") or {},
        (
            ("consultations", "咨询人数"),
            ("buyers", "客服成交人数"),
            ("gmv", "客服成交金额"),
            ("avg_response_seconds", "平均响应时长"),
            ("consult_conversion_rate", "询单转化率"),
        ),
    )
    promotion_rows = _promotion_comparison(
        list((current.get("promotions") or {}).get("scenes") or []),
        list((comparison.get("promotions") or {}).get("scenes") or []),
    )
    integrity_checks = _integrity_checks(current_ops, comparison_ops)
    driver_bridge = _gmv_driver_bridge(current_ops, comparison_ops, comparison_label)
    planning = _planning_block(request, current_ops)
    source_ledger = _source_ledger(request, support)

    data = {
        **current,
        "report_type": "business_review",
        "report_title": request.report_title or f"{current_start.year}年经营复盘",
        "range_start": current_start.isoformat(),
        "range_end": current_end.isoformat(),
        "comparison_label": comparison_label,
        "comparison_mode": request.comparison_mode,
        "previous_period": {
            "range_start": comparison_start.isoformat(),
            "range_end": comparison_end.isoformat(),
        },
        "comparison_data_quality": comparison.get("data_quality") or {},
        "comparison_coverage_by_dataset": comparison.get("coverage_by_dataset") or [],
        "comparison": comparison_payload,
        "gmv_driver_bridge": driver_bridge,
        "review_kpis": metric_rows,
        "monthly_trend": monthly_trend,
        "review_sections": {
            "traffic": traffic_rows,
            "product_series": product_series,
            "product_types": product_types,
            "customers": customer_rows,
            "members": member_rows,
            "customer_service": service_rows,
            "promotions": promotion_rows,
        },
        "integrity_checks": integrity_checks,
        "source_ledger": source_ledger,
        "business_events": [item.strip() for item in request.business_events if item.strip()],
        "strategy_notes": request.strategy_notes.strip(),
        "planning": planning,
    }

    artifacts = [ArtifactSpec(type="metric_table", title="经营核心指标对比", rows=metric_rows)]
    if monthly_trend:
        artifacts.append(ArtifactSpec(type="line_chart", title="月度支付与净支付趋势", rows=monthly_trend))
    if traffic_rows:
        artifacts.append(ArtifactSpec(type="matrix", title="流量来源对比", rows=traffic_rows[:15]))
    if product_series:
        artifacts.append(ArtifactSpec(type="bar_chart", title="系列销售结构对比", rows=product_series[:15]))
    if product_types:
        artifacts.append(ArtifactSpec(type="matrix", title="商品类型结构对比", rows=product_types))
    if customer_rows:
        artifacts.append(ArtifactSpec(type="matrix", title="客户生命周期对比", rows=customer_rows))
    if member_rows:
        artifacts.append(ArtifactSpec(type="matrix", title="会员经营对比", rows=member_rows))
    if service_rows:
        artifacts.append(ArtifactSpec(type="matrix", title="客服经营对比", rows=service_rows))
    if promotion_rows:
        artifacts.append(ArtifactSpec(type="matrix", title="推广场景对比", rows=promotion_rows[:15]))
    if planning.get("validation"):
        artifacts.append(ArtifactSpec(type="matrix", title="规划目标一致性校验", rows=planning["validation"]))

    warnings = [item["detail"] for item in integrity_checks if item["status"] == "warning"]
    warnings.extend(item["detail"] for item in planning.get("validation", []) if item.get("status") == "warning")
    return data, artifacts, list(dict.fromkeys(warnings))


def _shift_year(value: date, years: int) -> date:
    target_year = value.year + years
    return value.replace(year=target_year, day=min(value.day, monthrange(target_year, value.month)[1]))


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((current - previous) / abs(previous) * 100, 2)


def _core_metric_comparison(
    current: dict[str, Any],
    previous: dict[str, Any],
    comparison_label: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    payload: dict[str, dict[str, Any]] = {}
    for output_key, label, source_key, percentage_metric in _CORE_METRICS:
        current_value = _number(current.get(source_key))
        previous_value = _number(previous.get(source_key))
        delta = round(current_value - previous_value, 2) if current_value is not None and previous_value is not None else None
        change_percent = _change(current_value, previous_value)
        delta_pp = delta if percentage_metric else None
        payload[output_key] = {
            "current": current_value,
            "previous": previous_value,
            "delta": delta,
            "change_percent": change_percent,
            "delta_pp": delta_pp,
        }
        rows.append({
            "指标": label,
            "本期": current_value,
            "对比期": previous_value,
            f"{comparison_label}%": change_percent,
            "变化百分点": delta_pp,
            "来源类型": "计算推导" if source_key in {"net_gmv", "conversion_rate", "customer_unit_price", "refund_rate"} else "系统事实",
        })
    return rows, payload


def _monthly_comparison(current: list[dict[str, Any]], previous: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        buckets: dict[tuple[int, int], dict[str, float]] = {}
        for row in rows:
            raw_day = str(row.get("stat_date") or row.get("date") or "")
            try:
                parsed = date.fromisoformat(raw_day[:10])
            except ValueError:
                continue
            bucket = buckets.setdefault((parsed.year, parsed.month), {"gmv": 0.0, "refund": 0.0, "visitors": 0.0, "buyers": 0.0})
            bucket["gmv"] += _number(row.get("paid_amount")) or 0
            bucket["refund"] += _number(row.get("refund_amount")) or 0
            bucket["visitors"] += _number(row.get("visitors")) or 0
            bucket["buyers"] += _number(row.get("buyers")) or 0
        return [
            {"period": f"{year}-{month:02d}", **buckets[(year, month)]}
            for year, month in sorted(buckets)
        ]

    current_months, previous_months = aggregate(current), aggregate(previous)
    rows: list[dict[str, Any]] = []
    for index in range(max(len(current_months), len(previous_months))):
        current_row = current_months[index] if index < len(current_months) else {}
        previous_row = previous_months[index] if index < len(previous_months) else {}
        rows.append({
            "月份": current_row.get("period") or f"第 {index + 1} 期",
            "对比月份": previous_row.get("period"),
            "本期支付金额": round(current_row.get("gmv", 0), 2) if current_row else None,
            "对比期支付金额": round(previous_row.get("gmv", 0), 2) if previous_row else None,
            "本期净支付金额": round(current_row.get("gmv", 0) - current_row.get("refund", 0), 2) if current_row else None,
            "对比期净支付金额": round(previous_row.get("gmv", 0) - previous_row.get("refund", 0), 2) if previous_row else None,
        })
    return rows


def _dimension_comparison(
    current: list[dict[str, Any]],
    previous: list[dict[str, Any]],
    *,
    key: str,
    label: str,
    metrics: tuple[tuple[str, str], ...],
) -> list[dict[str, Any]]:
    current_map = {str(item.get(key) or "未分类"): item for item in current}
    previous_map = {str(item.get(key) or "未分类"): item for item in previous}
    rows = []
    for name in set(current_map) | set(previous_map):
        row: dict[str, Any] = {label: name}
        for metric, metric_label in metrics:
            current_value = _number(current_map.get(name, {}).get(metric))
            previous_value = _number(previous_map.get(name, {}).get(metric))
            row[f"本期{metric_label}"] = current_value
            row[f"对比期{metric_label}"] = previous_value
            row[f"{metric_label}变化%"] = _change(current_value, previous_value)
        rows.append(row)
    primary = f"本期{metrics[0][1]}"
    return sorted(rows, key=lambda item: float(item.get(primary) or 0), reverse=True)


def _product_structure_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for item in rows:
        current = _number(item.get("current_paid_amount"))
        previous = _number(item.get("previous_paid_amount"))
        output.append({
            "结构": item.get("name") or "待归类",
            "本期支付金额": current,
            "对比期支付金额": previous,
            "支付金额变化%": _change(current, previous),
            "本期客单价": _number(item.get("current_unit_price")),
            "对比期客单价": _number(item.get("previous_unit_price")),
            "买家占比变化pt": _number(item.get("buyer_share_delta_pp")),
            "商品数": item.get("product_count"),
        })
    return sorted(output, key=lambda item: float(item.get("本期支付金额") or 0), reverse=True)


def _aggregate_comparison_rows(
    current: dict[str, Any],
    previous: dict[str, Any],
    metrics: tuple[tuple[str, str], ...],
) -> list[dict[str, Any]]:
    rows = []
    for key, label in metrics:
        current_value, previous_value = _number(current.get(key)), _number(previous.get(key))
        rows.append({"指标": label, "本期": current_value, "对比期": previous_value, "变化%": _change(current_value, previous_value)})
    return rows if any(row["本期"] is not None or row["对比期"] is not None for row in rows) else []


def _promotion_comparison(current: list[dict[str, Any]], previous: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def name(item: dict[str, Any]) -> str:
        return str(item.get("scene_name") or item.get("dimension_name") or item.get("scene") or "未分类")

    current_map, previous_map = {name(item): item for item in current}, {name(item): item for item in previous}
    rows = []
    for scene in set(current_map) | set(previous_map):
        current_item, previous_item = current_map.get(scene, {}), previous_map.get(scene, {})
        current_spend, previous_spend = _number(current_item.get("spend")), _number(previous_item.get("spend"))
        current_gmv = _number(current_item.get("paid_amount") or current_item.get("gmv"))
        previous_gmv = _number(previous_item.get("paid_amount") or previous_item.get("gmv"))
        rows.append({
            "推广场景": scene,
            "本期花费": current_spend,
            "对比期花费": previous_spend,
            "花费变化%": _change(current_spend, previous_spend),
            "本期归因成交": current_gmv,
            "对比期归因成交": previous_gmv,
            "成交变化%": _change(current_gmv, previous_gmv),
            "本期ROI": _number(current_item.get("roi")),
            "对比期ROI": _number(previous_item.get("roi")),
        })
    return sorted(rows, key=lambda item: float(item.get("本期花费") or 0), reverse=True)


def _integrity_checks(current: dict[str, Any], previous: dict[str, Any]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []
    for label, values in (("本期", current), ("对比期", previous)):
        gmv, net_gmv = _number(values.get("gmv")), _number(values.get("net_gmv"))
        visitors, buyers = _number(values.get("visitors")), _number(values.get("buyers"))
        conversion = _number(values.get("conversion_rate"))
        unit_price = _number(values.get("customer_unit_price"))
        if gmv is not None and net_gmv is not None:
            ok = net_gmv <= gmv + 0.01
            checks.append({"check": f"{label}净支付不高于支付金额", "status": "passed" if ok else "warning", "detail": "口径一致" if ok else f"{label}净支付金额高于支付金额，请检查退款和净支付口径。"})
        if visitors and buyers is not None and conversion is not None:
            expected = buyers / visitors * 100
            ok = abs(expected - conversion) <= 0.2
            checks.append({"check": f"{label}转化率回勾", "status": "passed" if ok else "warning", "detail": f"支付买家÷访客={expected:.2f}%，报表={conversion:.2f}%。"})
        if buyers and gmv is not None and unit_price is not None:
            expected = gmv / buyers
            ok = abs(expected - unit_price) <= max(0.5, expected * 0.01)
            checks.append({"check": f"{label}客单价回勾", "status": "passed" if ok else "warning", "detail": f"支付金额÷支付买家={expected:.2f}，报表={unit_price:.2f}。"})
    return checks


def _gmv_driver_bridge(current: dict[str, Any], previous: dict[str, Any], comparison_label: str) -> dict[str, Any] | None:
    current_gmv, previous_gmv = _number(current.get("gmv")), _number(previous.get("gmv"))
    current_visitors, previous_visitors = _number(current.get("visitors")), _number(previous.get("visitors"))
    current_buyers, previous_buyers = _number(current.get("buyers")), _number(previous.get("buyers"))
    if None in {current_gmv, previous_gmv, current_visitors, previous_visitors, current_buyers, previous_buyers}:
        return None
    if not previous_visitors or not previous_buyers:
        return None
    previous_unit_price = previous_gmv / previous_buyers
    previous_conversion = previous_buyers / previous_visitors
    buyers_after_traffic = current_visitors * previous_conversion
    traffic_impact = (buyers_after_traffic - previous_buyers) * previous_unit_price
    conversion_impact = (current_buyers - buyers_after_traffic) * previous_unit_price
    unit_price_impact = current_gmv - current_buyers * previous_unit_price
    drivers = [
        {"key": "traffic", "label": "访客规模", "metric": "visitors", "current": current_visitors, "previous": previous_visitors, "change_percent": _change(current_visitors, previous_visitors), "impact_amount": round(traffic_impact, 2)},
        {"key": "conversion", "label": "支付转化", "metric": "conversion_rate", "current": current_buyers / current_visitors * 100 if current_visitors else None, "previous": previous_conversion * 100, "change_percent": _change(current_buyers / current_visitors if current_visitors else None, previous_conversion), "impact_amount": round(conversion_impact, 2)},
        {"key": "customer_unit_price", "label": "客单价", "metric": "customer_unit_price", "current": current_gmv / current_buyers if current_buyers else None, "previous": previous_unit_price, "change_percent": _change(current_gmv / current_buyers if current_buyers else None, previous_unit_price), "impact_amount": round(unit_price_impact, 2)},
    ]
    return {
        "formula": "paid_amount = visitors * payment_conversion_rate * customer_unit_price",
        "method": "sequential_bridge",
        "previous_gmv": previous_gmv,
        "current_gmv": current_gmv,
        "delta_amount": round(current_gmv - previous_gmv, 2),
        "drivers": drivers,
        "dominant_driver": max(drivers, key=lambda item: abs(float(item["impact_amount"]))),
        "reconciliation_error": round(current_gmv - previous_gmv - sum(float(item["impact_amount"]) for item in drivers), 2),
        "note": f"按对比期客单价顺序桥接访客、支付转化和客单价对支付金额的{comparison_label}影响；影响金额用于解释变化，不代表因果增量。",
    }


def _planning_block(request: PeriodReportRequest, current: dict[str, Any]) -> dict[str, Any]:
    targets = {key: _number(value) for key, value in request.planning_targets.items() if _number(value) is not None}
    if request.target_gmv is not None:
        targets.setdefault("gmv", float(request.target_gmv))
    validation: list[dict[str, Any]] = []
    target_gmv = targets.get("gmv")
    target_net_gmv = targets.get("net_gmv")
    target_visitors = targets.get("visitors")
    target_buyers = targets.get("buyers")
    target_conversion = targets.get("conversion_rate")
    target_unit_price = targets.get("customer_unit_price")
    if target_gmv is not None and target_net_gmv is not None:
        ok = target_net_gmv <= target_gmv
        validation.append({"校验": "净销售目标不高于支付目标", "status": "passed" if ok else "warning", "detail": "目标口径一致" if ok else "净销售目标高于支付目标，请检查两者口径或录入值。"})
    if target_gmv is not None and target_buyers and target_unit_price:
        modeled = target_buyers * target_unit_price
        deviation = abs(modeled - target_gmv) / target_gmv * 100 if target_gmv else 0
        validation.append({"校验": "支付目标=支付买家×客单价", "status": "passed" if deviation <= 2 else "warning", "detail": f"模型值 {modeled:,.2f}，目标 {target_gmv:,.2f}，偏差 {deviation:.2f}%。"})
    if target_gmv is not None and target_visitors and target_conversion is not None and target_unit_price:
        modeled = target_visitors * target_conversion / 100 * target_unit_price
        deviation = abs(modeled - target_gmv) / target_gmv * 100 if target_gmv else 0
        validation.append({"校验": "支付目标=访客×支付转化率×客单价", "status": "passed" if deviation <= 2 else "warning", "detail": f"模型值 {modeled:,.2f}，目标 {target_gmv:,.2f}，偏差 {deviation:.2f}%。"})
    return {
        "targets": targets,
        "baseline": {key: current.get(key) for key in ("gmv", "net_gmv", "visitors", "buyers", "conversion_rate", "customer_unit_price")},
        "validation": validation,
        "source_type": "人工输入",
    }


def _source_ledger(request: PeriodReportRequest, support: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    rows = [
        {"section": "经营总盘", "source_type": "系统事实", "source": "store_daily_overviews", "rule": "支付、访客、买家和退款按所选区间聚合"},
        {"section": "核心派生指标", "source_type": "计算推导", "source": "确定性指标引擎", "rule": "转化率、客单价、净支付和同比按固定公式计算"},
        {"section": "流量来源", "source_type": "系统事实", "source": "store_daily_traffic_sources", "rule": "只使用一级来源，全量分母后展示Top项"},
        {"section": "商品结构", "source_type": "计算推导", "source": "商品排行 + 商品主档", "rule": "系列→类型→商品，未映射商品归入待归类"},
        {"section": "推广", "source_type": "系统事实", "source": "store_daily_promotion_campaigns", "rule": "平台归因成交与店铺支付不直接相加"},
    ]
    if request.business_events:
        rows.append({"section": "经营事件", "source_type": "人工输入", "source": "报告生成参数", "rule": "用于辅助解释，不自动证明因果"})
    if request.planning_targets or request.target_gmv is not None or request.strategy_notes:
        rows.append({"section": "经营规划", "source_type": "人工输入", "source": "报告生成参数", "rule": "目标由人工维护，系统只做一致性校验"})
    if not support.get("product_structure"):
        rows.append({"section": "商品结构", "source_type": "数据缺口", "source": "--", "rule": "当前没有可用商品结构证据"})
    return rows
