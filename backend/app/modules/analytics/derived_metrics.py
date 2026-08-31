from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Callable, Mapping

from app.modules.analytics.schemas import DecisionMetric


Number = Decimal | int
Calculator = Callable[[dict[str, Decimal]], Decimal]


@dataclass(frozen=True, slots=True)
class DerivedMetricDefinition:
    id: str
    label: str
    unit: str
    formula: str
    dependencies: tuple[str, ...]
    calculator: Calculator
    note: str = ""
    require_non_negative: bool = False


def _difference(left: str, right: str) -> Calculator:
    return lambda values: values[left] - values[right]


def _ratio(numerator: str, denominator: str, *, percent: bool = False) -> Calculator:
    multiplier = Decimal("100") if percent else Decimal("1")

    def calculate(values: dict[str, Decimal]) -> Decimal:
        denominator_value = values[denominator]
        if denominator_value == 0:
            raise ZeroDivisionError(denominator)
        return values[numerator] / denominator_value * multiplier

    return calculate


CUSTOMER_DERIVED_METRICS: tuple[DerivedMetricDefinition, ...] = (
    DerivedMetricDefinition(
        id="first_purchase_paid_buyers",
        label="首次购买人数",
        unit="count",
        formula="总支付买家数 - 老客复购人数",
        dependencies=("total_paid_buyers", "repeat_paid_buyers"),
        calculator=_difference("total_paid_buyers", "repeat_paid_buyers"),
        note="总支付与老客复购必须使用同一店铺、日期和支付口径；区间人数为每日人数累计，不是跨日去重买家。",
        require_non_negative=True,
    ),
    DerivedMetricDefinition(
        id="first_purchase_paid_amount",
        label="首次购买金额",
        unit="currency",
        formula="总支付金额 - 老客复购金额",
        dependencies=("total_paid_amount", "repeat_paid_amount"),
        calculator=_difference("total_paid_amount", "repeat_paid_amount"),
        note="首次购买包括新访成交和未购回访后的首次成交，不等同于仅新访成交金额。",
        require_non_negative=True,
    ),
    DerivedMetricDefinition(
        id="first_purchase_buyer_share",
        label="首次购买人数占比",
        unit="percent",
        formula="首次购买人数 / 总支付买家数",
        dependencies=("first_purchase_paid_buyers", "total_paid_buyers"),
        calculator=_ratio("first_purchase_paid_buyers", "total_paid_buyers", percent=True),
    ),
    DerivedMetricDefinition(
        id="repeat_buyer_share",
        label="老客支付人数占比",
        unit="percent",
        formula="老客复购人数 / 总支付买家数",
        dependencies=("repeat_paid_buyers", "total_paid_buyers"),
        calculator=_ratio("repeat_paid_buyers", "total_paid_buyers", percent=True),
    ),
    DerivedMetricDefinition(
        id="first_purchase_amount_share",
        label="首次购买金额占比",
        unit="percent",
        formula="首次购买金额 / 总支付金额",
        dependencies=("first_purchase_paid_amount", "total_paid_amount"),
        calculator=_ratio("first_purchase_paid_amount", "total_paid_amount", percent=True),
    ),
    DerivedMetricDefinition(
        id="repeat_amount_share",
        label="老客支付金额占比",
        unit="percent",
        formula="老客复购金额 / 总支付金额",
        dependencies=("repeat_paid_amount", "total_paid_amount"),
        calculator=_ratio("repeat_paid_amount", "total_paid_amount", percent=True),
    ),
    DerivedMetricDefinition(
        id="first_purchase_unit_price",
        label="首次购买客单价",
        unit="currency",
        formula="首次购买金额 / 首次购买人数",
        dependencies=("first_purchase_paid_amount", "first_purchase_paid_buyers"),
        calculator=_ratio("first_purchase_paid_amount", "first_purchase_paid_buyers"),
    ),
    DerivedMetricDefinition(
        id="repeat_unit_price",
        label="老客支付客单价",
        unit="currency",
        formula="老客复购金额 / 老客复购人数",
        dependencies=("repeat_paid_amount", "repeat_paid_buyers"),
        calculator=_ratio("repeat_paid_amount", "repeat_paid_buyers"),
    ),
    DerivedMetricDefinition(
        id="repeat_unit_price_index",
        label="老客客单指数",
        unit="percent",
        formula="老客支付客单价 / 首次购买客单价",
        dependencies=("repeat_unit_price", "first_purchase_unit_price"),
        calculator=_ratio("repeat_unit_price", "first_purchase_unit_price", percent=True),
        note="100%表示老客与首次购买客单相同，高于100%表示老客客单更高。",
    ),
    DerivedMetricDefinition(
        id="classified_buyer_gap",
        label="客户人数分类差额",
        unit="count",
        formula="总支付买家数 - 新访成交 - 未购回访成交 - 老客复购",
        dependencies=("total_paid_buyers", "new_visit_paid_buyers", "no_purchase_paid_buyers", "repeat_paid_buyers"),
        calculator=lambda values: values["total_paid_buyers"] - values["new_visit_paid_buyers"] - values["no_purchase_paid_buyers"] - values["repeat_paid_buyers"],
        note="差额不为0时优先核对平台人群定义、字段有效日期和日累计口径。",
    ),
    DerivedMetricDefinition(
        id="classified_amount_gap",
        label="客户金额分类差额",
        unit="currency",
        formula="总支付金额 - 新访成交金额 - 未购回访成交金额 - 老客复购金额",
        dependencies=("total_paid_amount", "new_visit_paid_amount", "no_purchase_paid_amount", "repeat_paid_amount"),
        calculator=lambda values: values["total_paid_amount"] - values["new_visit_paid_amount"] - values["no_purchase_paid_amount"] - values["repeat_paid_amount"],
        note="金额占比来自客户报表时可能存在四舍五入差额，较大差额应视为口径或数据质量问题。",
    ),
)


def derive_metrics(
    source_values: Mapping[str, Number | None],
    definitions: tuple[DerivedMetricDefinition, ...],
) -> list[DecisionMetric]:
    values: dict[str, Decimal] = {
        key: Decimal(str(value))
        for key, value in source_values.items()
        if value is not None
    }
    results: list[DecisionMetric] = []
    for definition in definitions:
        missing = [key for key in definition.dependencies if key not in values]
        if missing:
            results.append(DecisionMetric(
                id=definition.id,
                label=definition.label,
                unit=definition.unit,
                formula=definition.formula,
                source_metric_ids=list(definition.dependencies),
                status="unavailable",
                note=f"缺少依赖指标：{'、'.join(missing)}。{definition.note}".strip(),
            ))
            continue
        try:
            value = definition.calculator(values)
        except ZeroDivisionError:
            results.append(DecisionMetric(
                id=definition.id,
                label=definition.label,
                unit=definition.unit,
                formula=definition.formula,
                source_metric_ids=list(definition.dependencies),
                status="unavailable",
                note=f"分母为0，暂不计算。{definition.note}".strip(),
            ))
            continue
        status = "available"
        note = definition.note
        if definition.require_non_negative and value < 0:
            status = "inconsistent"
            note = f"推导结果为负，说明依赖字段口径不一致或数据异常。{definition.note}".strip()
            output_value = None
        else:
            output_value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            values[definition.id] = output_value
        results.append(DecisionMetric(
            id=definition.id,
            label=definition.label,
            value=output_value,
            unit=definition.unit,
            formula=definition.formula,
            source_metric_ids=list(definition.dependencies),
            status=status,
            note=note,
        ))
    return results
