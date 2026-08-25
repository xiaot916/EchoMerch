from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.modules.ai.catalog import DATASET_CATALOG, DatasetDefinition, get_dataset
from app.modules.ai.schemas import (
    CoverageSummary,
    DatasetDescriptor,
    DatasetField,
    EvidenceRecord,
    MCPQueryRequest,
    MCPQueryResult,
)
from app.modules.analytics.service import AnalyticsService


_AGGREGATIONS = {"sum": "sum", "avg": "avg", "min": "min", "max": "max", "count": "count"}
_FORMULA_TOKEN = __import__("re").compile(r"[A-Za-z_][A-Za-z0-9_]*|/|\+|-|\*|\(|\)")


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date,)):
        return value.isoformat()
    return value


class AnalyticsQueryService:
    """Compile structured catalog requests into parameterized read-only SQL."""

    def __init__(self, analytics: AnalyticsService | None = None) -> None:
        self.analytics = analytics or AnalyticsService()

    def list_datasets(self) -> list[DatasetDescriptor]:
        return [self.describe_dataset(key) for key in DATASET_CATALOG]

    def describe_dataset(self, key: str) -> DatasetDescriptor:
        dataset = get_dataset(key)
        return DatasetDescriptor(
            key=dataset.key,
            label=dataset.label,
            table=dataset.table,
            grain=dataset.grain,
            date_column=dataset.date_column,
            dimensions=[self._field_descriptor(item) for item in dataset.dimensions.values()],
            measures=[self._field_descriptor(item) for item in [*dataset.measures.values(), *dataset.calculated_measures.values()]],
        )

    def query(self, request: MCPQueryRequest) -> MCPQueryResult:
        dataset = get_dataset(request.dataset)
        source, start_date, end_date = self._source_and_range(request)
        if not request.dimensions and not request.measures:
            raise ValueError("data.query requires at least one dimension or measure")
        dimensions = self._resolve_fields(dataset, request.dimensions, kind="dimension")
        measures = self._resolve_fields(dataset, request.measures, kind="measure")
        physical_measures = [item for item in measures if item.aggregation != "calculated"]
        calculated_measures = [item for item in measures if item.aggregation == "calculated"]
        dependencies = self._formula_dependencies(dataset, calculated_measures)
        selected_physical = list(dict.fromkeys([*physical_measures, *dependencies]))
        self._validate_physical_columns(source, dataset, [*dimensions, *selected_physical])

        select_parts = [f'{_quote(item.column)} as {_quote(item.id)}' for item in dimensions]
        formulas: dict[str, str] = {}
        for item in selected_physical:
            aggregation = _AGGREGATIONS.get(item.aggregation)
            if aggregation is None:
                raise ValueError(f"Unsupported aggregation for {item.id}: {item.aggregation}")
            numeric = f"cast(nullif({_quote(item.column)}, '') as real)"
            select_parts.append(f'{aggregation}({numeric}) as {_quote(item.id)}')
            formulas[item.id] = f'{item.aggregation}({item.column})'
        for item in calculated_measures:
            formulas[item.id] = item.formula

        # Static master data (for example the product catalog) has no business
        # date. Keep it queryable through the same whitelist while avoiding a
        # fabricated daily predicate.
        where = [f'{_quote(dataset.store_column)} = ?']
        where_params: list[Any] = [source._store_id]
        if dataset.date_column:
            where.append(f'{_quote(dataset.date_column)} between ? and ?')
            where_params.extend([start_date.isoformat(), end_date.isoformat()])
        merged_filters = {**dataset.default_filters, **request.filters}
        having: list[str] = []
        having_params: list[Any] = []
        for field_id, value in merged_filters.items():
            field = dataset.dimensions.get(field_id)
            if field is not None:
                self._append_filter(where, where_params, field.column, value)
                continue
            measure = dataset.measures.get(field_id)
            if measure is None or measure.aggregation == "calculated":
                raise ValueError(f"Filter field is not an allowed dimension or physical measure for {dataset.key}: {field_id}")
            self._append_measure_filter(having, having_params, measure, value)

        group_by = ", ".join(_quote(item.column) for item in dimensions)
        sql = f"select {', '.join(select_parts)} from {_quote(dataset.table)} where {' and '.join(where)}"
        if group_by:
            sql += f" group by {group_by}"
        if having:
            sql += f" having {' and '.join(having)}"
        calculated_ids = {item.id for item in calculated_measures}
        sql_order = [item for item in request.order_by if item.lstrip("-") not in calculated_ids]
        sql += self._order_clause(sql_order, dataset, dimensions, selected_physical)
        sql += " limit ?"
        rows = source._rows(sql, *where_params, *having_params, request.limit)

        if group_by:
            count_sql = f"select count(*) as row_count from (select 1 from {_quote(dataset.table)} where {' and '.join(where)}"
            count_sql += f" group by {group_by}"
            if having:
                count_sql += f" having {' and '.join(having)}"
            count_sql += ")"
        elif having:
            # SQLite does not allow HAVING on a non-aggregate SELECT.  Keep
            # the no-dimension count as one aggregate group and count the
            # group only when its measure predicate passes.
            count_sql = (
                f"select count(*) as row_count from (select "
                f"{_AGGREGATIONS[physical_measures[0].aggregation]}(cast(nullif({_quote(physical_measures[0].column)}, '') as real)) "
                f"as {_quote(physical_measures[0].id)} from {_quote(dataset.table)} where {' and '.join(where)} "
                f"having {' and '.join(having)})"
            )
        else:
            count_sql = f"select count(*) as row_count from {_quote(dataset.table)} where {' and '.join(where)}"
        physical_rows = source._rows(count_sql, *where_params, *having_params)
        row_count = int(physical_rows[0].get("row_count") or 0) if physical_rows else 0
        if row_count == 0:
            rows = []
        serialized = []
        for row in rows:
            values = {key: _json_value(value) for key, value in row.items()}
            self._calculate_measures(dataset, values, calculated_measures)
            serialized.append({key: values.get(key) for key in [*(item.id for item in dimensions), *(item.id for item in measures)]})
        for raw in reversed(request.order_by):
            field_id = raw[1:] if raw.startswith("-") else raw
            if field_id in calculated_ids:
                serialized.sort(key=lambda row: (row.get(field_id) is None, row.get(field_id) if isinstance(row.get(field_id), (int, float)) else 0), reverse=raw.startswith("-"))
        # With dimensions, return period totals as well so a Skill can compare
        # the selected slice without issuing a second unconstrained query.
        # Keep period totals on the same filtered population as the returned
        # grouped rows.  Measure filters are HAVING predicates (not WHERE
        # predicates), so omitting them here would report a total for rows
        # that the query intentionally excluded.
        aggregate_expressions = ", ".join(
            f"{_AGGREGATIONS[item.aggregation]}(cast(nullif({_quote(item.column)}, '') as real)) as {_quote(item.id)}"
            for item in selected_physical
        )
        aggregate_sql = ""
        aggregate_params: list[Any] = []
        if selected_physical:
            if group_by and having:
                # For grouped queries, first retain only groups satisfying
                # the measure predicates, then aggregate those groups.  A
                # plain HAVING on the ungrouped table would test the grand
                # total and incorrectly discard valid zero-stock groups.
                grouped_sql = (
                    f"select {aggregate_expressions} from {_quote(dataset.table)} "
                    f"where {' and '.join(where)} group by {group_by} having {' and '.join(having)}"
                )
                aggregate_sql = "select " + ", ".join(
                    f"{'sum' if item.aggregation == 'count' else _AGGREGATIONS[item.aggregation]}({_quote(item.id)}) as {_quote(item.id)}"
                    for item in selected_physical
                ) + f" from ({grouped_sql}) as filtered_groups"
                aggregate_params = [*where_params, *having_params]
            else:
                aggregate_sql = (
                    f"select {aggregate_expressions} from {_quote(dataset.table)} where {' and '.join(where)}"
                )
                if having:
                    aggregate_sql += f" having {' and '.join(having)}"
                aggregate_params = [*where_params, *having_params]
        aggregate_rows = source._rows(
            aggregate_sql,
            *aggregate_params,
        ) if aggregate_sql else []
        aggregate_row = aggregate_rows[0] if aggregate_rows else {}
        aggregate_values = {item.id: _json_value(aggregate_row.get(item.id)) for item in selected_physical}
        self._calculate_measures(dataset, aggregate_values, calculated_measures)
        aggregates = {item.id: aggregate_values.get(item.id) for item in measures}
        coverage = self.coverage(request.dataset, source._store_id, start_date, end_date)
        evidence_range = [] if not dataset.date_column else [start_date.isoformat(), end_date.isoformat()]
        evidence_note = (
            f"静态主档；无业务日期；dimensions={request.dimensions}; measures={request.measures}; filters={merged_filters}"
            if not dataset.date_column
            else f"dimensions={request.dimensions}; measures={request.measures}; filters={merged_filters}"
        )
        return MCPQueryResult(
            dataset=dataset.key,
            columns=[item.id for item in [*dimensions, *measures]],
            rows=serialized,
            aggregates={item.id: aggregates.get(item.id) for item in measures},
            formula=formulas,
            coverage=coverage,
            evidence=[EvidenceRecord(
                dataset=dataset.label,
                table=dataset.table,
                date_range=evidence_range,
                row_count=row_count,
                note=evidence_note,
            )],
        )

    def compare_periods(self, request: MCPQueryRequest) -> dict[str, Any]:
        dataset = get_dataset(request.dataset)
        if not dataset.date_column:
            raise ValueError(f"data.compare_periods does not support static dataset: {request.dataset}")
        source, start_date, end_date = self._source_and_range(request)
        days = (end_date - start_date).days + 1
        previous_end = start_date - timedelta(days=1)
        previous_start = previous_end - timedelta(days=days - 1)
        current = self.query(request.model_copy(update={"start_date": start_date, "end_date": end_date}))
        previous = self.query(request.model_copy(update={"start_date": previous_start, "end_date": previous_end}))
        comparable = self._coverage_complete(current.coverage) and self._coverage_complete(previous.coverage)
        comparisons: dict[str, dict[str, float | int | None]] = {}
        for measure in request.measures:
            current_value = current.aggregates.get(measure)
            previous_value = previous.aggregates.get(measure)
            delta = None
            change_percent = None
            if comparable and isinstance(current_value, (int, float)) and isinstance(previous_value, (int, float)):
                delta = current_value - previous_value
                if previous_value != 0:
                    change_percent = delta / abs(previous_value) * 100
            comparisons[measure] = {
                "current": current_value,
                "previous": previous_value,
                "delta": delta,
                "change_percent": change_percent,
            }
        return {
            "dataset": request.dataset,
            "comparable": comparable,
            "current_range": [start_date.isoformat(), end_date.isoformat()],
            "previous_range": [previous_start.isoformat(), previous_end.isoformat()],
            "comparisons": comparisons,
            "current": current.model_dump(mode="json"),
            "previous": previous.model_dump(mode="json"),
        }

    def coverage(self, dataset_key: str, store_id: int | None, start_date: date, end_date: date) -> CoverageSummary:
        dataset = get_dataset(dataset_key)
        if not dataset.date_column:
            source = self.analytics._source_for_store(store_id)
            try:
                rows = source._rows(
                    f'select count(*) as row_count from {_quote(dataset.table)} where {_quote(dataset.store_column)} = ?',
                    source._store_id,
                )
                count = int(rows[0].get("row_count") or 0) if rows else 0
            except Exception:
                count = 0
            return CoverageSummary(
                expected_days=0,
                covered_days=0 if count == 0 else 1,
                missing_datasets=[dataset.label] if count == 0 else [],
                latest_data_date=None,
            )
        source = self.analytics._source_for_store(store_id)
        getter = getattr(source, "get_data_coverage", None)
        if getter is None:
            return CoverageSummary(expected_days=(end_date - start_date).days + 1)
        item = next((entry for entry in getter(start_date, end_date) if entry.dataset == dataset.label), None)
        if item is None:
            return CoverageSummary(
                expected_days=(end_date - start_date).days + 1,
                missing_datasets=[dataset.label],
            )
        no_data = bool(item.no_data_dates and not item.missing_dates and item.covered_days == item.expected_days)
        return CoverageSummary(
            expected_days=item.expected_days,
            covered_days=item.covered_days,
            missing_dates=[value.isoformat() for value in item.missing_dates],
            partial_datasets=[dataset.label] if item.status == "partial" else [],
            missing_datasets=[dataset.label] if item.status == "empty" and not no_data else [],
            no_data_datasets=[dataset.label] if no_data else [],
            no_data_dates=[value.isoformat() for value in item.no_data_dates],
            latest_data_date=item.latest_date.isoformat() if item.latest_date else None,
        )

    def _source_and_range(self, request: MCPQueryRequest):
        dataset = get_dataset(request.dataset)
        source = self.analytics._source_for_store(request.store_id)
        if not hasattr(source, "_rows") or not hasattr(source, "_store_id"):
            raise RuntimeError("Generic data MCP requires the normalized local warehouse source")
        # Static master/snapshot tables do not use the normalized daily-fact
        # date column. They remain queryable even when the analytics overview
        # has a different latest business date (or has not been ingested yet).
        if not dataset.date_column:
            anchor = request.start_date or request.end_date or date.today()
            return source, anchor, anchor
        minimum, maximum = source.get_date_bounds()
        if request.history_scope == "all" and request.start_date is None and request.end_date is None:
            start_date, end_date = minimum, maximum
        else:
            start_date = request.start_date or maximum
            end_date = request.end_date or maximum
        if start_date > end_date:
            raise ValueError("start_date must be earlier than or equal to end_date")
        if end_date > maximum:
            raise ValueError(f"end_date cannot be later than the latest available date ({maximum.isoformat()})")
        return source, start_date, end_date

    @staticmethod
    def _resolve_fields(dataset: DatasetDefinition, ids: list[str], *, kind: str):
        catalog = dataset.dimensions if kind == "dimension" else {**dataset.measures, **dataset.calculated_measures}
        unknown = [field_id for field_id in ids if field_id not in catalog]
        if unknown:
            raise ValueError(f"Unknown {kind} fields for {dataset.key}: {', '.join(unknown)}")
        if len(set(ids)) != len(ids):
            raise ValueError(f"Duplicate {kind} fields are not allowed")
        return [catalog[field_id] for field_id in ids]

    @staticmethod
    def _validate_physical_columns(source: Any, dataset: DatasetDefinition, fields: list[Any]) -> None:
        rows = source._rows(f"pragma table_info({_quote(dataset.table)})")
        columns = {str(row.get("name")) for row in rows}
        required = {dataset.store_column, *(item.column for item in fields)}
        if dataset.date_column:
            required.add(dataset.date_column)
        missing = sorted(required - columns)
        if missing:
            raise ValueError(f"Dataset {dataset.key} is missing registered columns: {', '.join(missing)}")

    @staticmethod
    def _append_filter(where: list[str], params: list[Any], column: str, value: Any) -> None:
        quoted = _quote(column)
        if value is None:
            where.append(f"{quoted} is null")
        elif isinstance(value, list):
            if not value:
                where.append("1 = 0")
            else:
                where.append(f"{quoted} in ({', '.join('?' for _ in value)})")
                params.extend(value)
        elif isinstance(value, dict):
            allowed = {"eq", "ne", "gte", "lte", "contains"}
            unknown = set(value) - allowed
            if unknown:
                raise ValueError(f"Unsupported filter operators: {', '.join(sorted(unknown))}")
            for operator, operand in value.items():
                sql_operator = {"eq": "=", "ne": "!=", "gte": ">=", "lte": "<="}.get(operator)
                if operator == "contains":
                    where.append(f"{quoted} like ?")
                    params.append(f"%{operand}%")
                else:
                    where.append(f"{quoted} {sql_operator} ?")
                    params.append(operand)
        else:
            where.append(f"{quoted} = ?")
            params.append(value)

    @staticmethod
    def _append_measure_filter(having: list[str], params: list[Any], field: Any, value: Any) -> None:
        """Apply safe numeric filters to aggregated physical measures."""
        aggregation = _AGGREGATIONS.get(field.aggregation)
        if aggregation is None:
            raise ValueError(f"Unsupported measure filter: {field.id}")
        expression = f"{aggregation}(cast(nullif({_quote(field.column)}, '') as real))"
        if isinstance(value, dict):
            allowed = {"eq": "=", "ne": "!=", "gte": ">=", "lte": "<="}
            unknown = set(value) - set(allowed)
            if unknown:
                raise ValueError(f"Unsupported measure filter operators: {', '.join(sorted(unknown))}")
            for operator, operand in value.items():
                having.append(f"{expression} {allowed[operator]} ?")
                params.append(operand)
            return
        if isinstance(value, (int, float, str)):
            having.append(f"{expression} = ?")
            params.append(value)
            return
        raise ValueError(f"Unsupported measure filter value for {field.id}")

    @staticmethod
    def _order_clause(order_by: list[str], dataset: DatasetDefinition, dimensions: list[Any], measures: list[Any]) -> str:
        available = {item.id for item in [*dimensions, *measures]}
        parts = []
        for raw in order_by:
            descending = raw.startswith("-")
            field_id = raw[1:] if descending else raw
            if field_id not in available:
                raise ValueError(f"order_by field must be selected: {field_id}")
            if field_id not in dataset.fields:
                raise ValueError(f"Unknown order_by field: {field_id}")
            parts.append(f'{_quote(field_id)} {"desc" if descending else "asc"}')
        return f" order by {', '.join(parts)}" if parts else ""

    @staticmethod
    def _field_descriptor(item: Any) -> DatasetField:
        return DatasetField(
            id=item.id, label=item.label, column=item.column, kind=item.kind,
            unit=item.unit, aggregation=item.aggregation, description=item.description, formula=item.formula,
        )

    @staticmethod
    def _formula_dependencies(dataset: DatasetDefinition, fields: list[Any]) -> list[Any]:
        dependencies: list[Any] = []
        for field in fields:
            tokens = [token for token in _FORMULA_TOKEN.findall(field.formula) if token not in {"/", "+", "-", "*", "(", ")"}]
            for token in tokens:
                dependency = dataset.measures.get(token)
                if dependency is None:
                    raise ValueError(f"Calculated measure {field.id} references unknown measure: {token}")
                if dependency not in dependencies:
                    dependencies.append(dependency)
        return dependencies

    @staticmethod
    def _calculate_measures(dataset: DatasetDefinition, values: dict[str, Any], fields: list[Any]) -> None:
        for field in fields:
            tokens = _FORMULA_TOKEN.findall(field.formula)
            if len(tokens) != 3 or tokens[1] != "/":
                raise ValueError(f"Unsupported calculated formula for {field.id}: {field.formula}")
            numerator = values.get(tokens[0])
            denominator = values.get(tokens[2])
            value = None
            if isinstance(numerator, (int, float)) and isinstance(denominator, (int, float)) and denominator != 0:
                value = numerator / denominator
                if field.unit == "percent":
                    value *= 100
            values[field.id] = value

    @staticmethod
    def _coverage_complete(coverage: CoverageSummary) -> bool:
        return not (
            coverage.missing_dates or coverage.missing_datasets or coverage.partial_datasets or coverage.failed_datasets
        )
