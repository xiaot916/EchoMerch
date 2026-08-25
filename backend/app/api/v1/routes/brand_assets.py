from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.dependencies import require_permission, resolve_brand_scope
from app.core.config import settings
from app.modules.access.service import AccessDenied, Principal
from app.modules.brand_assets.schemas import BrandAssetSummary, BrandProductAnalysis, BrandProductRecord, BrandRecord
from app.modules.brand_assets.service import BrandAssetService, BrandNotFound


router = APIRouter()


def get_brand_asset_service() -> BrandAssetService:
    return BrandAssetService(Path(settings.local_database_path))


@router.get("/brands", response_model=list[BrandRecord])
def list_brand_assets_brands(
    principal: Principal = Depends(require_permission("brand_assets.read")),
) -> list[BrandRecord]:
    return get_brand_asset_service().list_brands(principal)


@router.get("/summary", response_model=BrandAssetSummary)
def get_brand_asset_summary(
    brand_id: str | None = Query(default=None, max_length=120),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    principal: Principal = Depends(require_permission("brand_assets.read")),
) -> BrandAssetSummary:
    try:
        resolved_id = resolve_brand_scope(principal, brand_id)
        return get_brand_asset_service().get_summary(
            principal,
            brand_id=resolved_id,
            start_date=start_date,
            end_date=end_date,
        )
    except BrandNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/products", response_model=list[BrandProductRecord])
def list_brand_products(
    brand_id: str | None = Query(default=None, max_length=120),
    principal: Principal = Depends(require_permission("brand_assets.read")),
) -> list[BrandProductRecord]:
    try:
        return get_brand_asset_service().list_products(
            principal,
            brand_id=brand_id,
        )
    except BrandNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/products/{product_id}/analysis", response_model=BrandProductAnalysis)
def get_brand_product_analysis(
    product_id: str,
    brand_id: str | None = Query(default=None, max_length=120),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    principal: Principal = Depends(require_permission("brand_assets.read")),
) -> BrandProductAnalysis:
    try:
        return get_brand_asset_service().get_product_analysis(
            principal,
            brand_id=brand_id,
            product_id=product_id,
            start_date=start_date,
            end_date=end_date,
        )
    except BrandNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
