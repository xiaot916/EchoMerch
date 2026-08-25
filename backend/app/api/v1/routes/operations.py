from fastapi import APIRouter, Depends

from app.api.dependencies import require_permission
from app.modules.access.service import Principal
from app.modules.operations.schemas import OperationCenterSummary
from app.modules.operations.service import OperationService

router = APIRouter()


@router.get("/summary", response_model=OperationCenterSummary)
def get_operation_summary(_: Principal = Depends(require_permission("system.manage"))) -> OperationCenterSummary:
    return OperationService().get_summary()
