from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.modules.contracts.schemas import ContractCatalog, ContractSummary, EndpointContract


class ContractCatalogMissing(RuntimeError):
    pass


class ContractService:
    def __init__(self, report_path: Path) -> None:
        self.report_path = report_path

    def _load_report(self) -> dict[str, Any]:
        if not self.report_path.exists():
            raise ContractCatalogMissing(
                f"Contract report not found: {self.report_path}. Run analyze_reqable_pairs.py first."
            )
        return json.loads(self.report_path.read_text(encoding="utf-8"))

    def get_summary(self) -> ContractSummary:
        payload = self._load_report()
        summary = payload.get("summary", {})
        return ContractSummary(
            generated_at=payload.get("generated_at"),
            source=str(payload.get("source") or "unknown"),
            api_observations=int(summary.get("api_observations") or 0),
            endpoint_contracts=int(summary.get("endpoint_contracts") or 0),
            daily_observations=int(summary.get("daily_observations") or 0),
            business_dates={
                str(key): int(value)
                for key, value in dict(summary.get("business_dates") or {}).items()
            },
            date_modes={
                str(key): int(value)
                for key, value in dict(summary.get("date_modes") or {}).items()
            },
            priority_paths=[
                EndpointContract.model_validate(item)
                for item in payload.get("target_contracts", [])
            ],
        )

    def list_contracts(
        self,
        *,
        daily_only: bool = False,
        limit: int = 80,
        query: str | None = None,
    ) -> ContractCatalog:
        payload = self._load_report()
        rows = payload.get("top_contracts") or []
        if daily_only:
            rows = payload.get("top_daily_contracts") or []

        contracts = []
        normalized_query = query.lower() if query else ""
        for item in rows:
            if normalized_query:
                haystack = f"{item.get('host', '')} {item.get('path', '')}".lower()
                if normalized_query not in haystack:
                    continue
            contracts.append(EndpointContract.model_validate(item))
            if len(contracts) >= limit:
                break

        return ContractCatalog(generated_at=payload.get("generated_at"), contracts=contracts)

