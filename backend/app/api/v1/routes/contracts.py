from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import require_permission
from app.core.config import settings
from app.modules.contracts.schemas import ContractCatalog, ContractSummary
from app.modules.contracts.service import ContractCatalogMissing, ContractService
from app.modules.access.service import Principal

router = APIRouter()


def get_contract_service() -> ContractService:
    return ContractService(Path(settings.contract_report_path))


@router.get("/summary", response_model=ContractSummary)
def get_contract_summary(_: Principal = Depends(require_permission("system.manage"))) -> ContractSummary:
    try:
        return get_contract_service().get_summary()
    except ContractCatalogMissing as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/endpoints", response_model=ContractCatalog)
def list_contracts(
    daily_only: bool = Query(default=False),
    limit: int = Query(default=80, ge=1, le=200),
    query: str | None = Query(default=None),
    _: Principal = Depends(require_permission("system.manage")),
) -> ContractCatalog:
    try:
        return get_contract_service().list_contracts(
            daily_only=daily_only,
            limit=limit,
            query=query,
        )
    except ContractCatalogMissing as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
