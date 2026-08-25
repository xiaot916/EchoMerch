import json
from queue import Queue
from threading import Thread

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.api.dependencies import require_permission, resolve_store_scope
from app.modules.access.service import Principal
from app.modules.ai.mcp import CommerceMCPService
from app.modules.ai.provider import AgnesProvider, AIProviderError
from app.modules.ai.configuration import get_ai_config, save_ai_config
from app.integrations.jackyun_credentials import CredentialVaultError
from app.modules.ai.schemas import (
    AIHealthResponse,
    AIConfigurationResponse,
    AIConfigurationUpdate,
    AIConnectionTestResponse,
    AnalysisRequest,
    AnalysisResponse,
    MCPEnvelope,
    MCPExecuteRequest,
    MCPToolDescriptor,
    AIConversationDetail,
    AIConversationListItem,
    PeriodReportRequest,
    PeriodReportResponse,
    SkillDescriptor,
)
from app.modules.ai.service import AIAnalysisService


router = APIRouter()


def get_ai_service() -> AIAnalysisService:
    return AIAnalysisService()


def get_mcp_service() -> CommerceMCPService:
    return CommerceMCPService()


@router.get("/health", response_model=AIHealthResponse)
def get_ai_health(
    principal: Principal = Depends(require_permission("analytics.read")),
) -> AIHealthResponse:
    provider = AgnesProvider()
    return AIHealthResponse(
        status="configured" if provider.configured else "not_configured",
        provider=provider.name,
        model=provider.model,
        endpoint=provider.endpoint,
        api_key_configured=provider.configured,
    )


def _configuration_response() -> AIConfigurationResponse:
    config = get_ai_config()
    return AIConfigurationResponse(
        base_url=config.base_url,
        api_path=config.api_path,
        endpoint=config.endpoint,
        model=config.model,
        timeout_seconds=config.timeout_seconds,
        api_key_configured=config.configured,
        api_key_masked=config.api_key_masked,
    )


@router.get("/configuration", response_model=AIConfigurationResponse)
def get_ai_configuration(
    _: Principal = Depends(require_permission("system.manage")),
) -> AIConfigurationResponse:
    return _configuration_response()


@router.put("/configuration", response_model=AIConfigurationResponse)
def update_ai_configuration(
    request: AIConfigurationUpdate,
    _: Principal = Depends(require_permission("system.manage")),
) -> AIConfigurationResponse:
    try:
        save_ai_config(
            base_url=request.base_url,
            api_path=request.api_path,
            model=request.model,
            timeout_seconds=request.timeout_seconds,
            api_key=request.api_key,
        )
    except CredentialVaultError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return _configuration_response()


@router.post("/configuration/test", response_model=AIConnectionTestResponse)
def test_ai_configuration(
    _: Principal = Depends(require_permission("system.manage")),
) -> AIConnectionTestResponse:
    provider = AgnesProvider()
    try:
        return AIConnectionTestResponse(**provider.test_connection())
    except AIProviderError as exc:
        return AIConnectionTestResponse(ok=False, model=provider.model, error=str(exc))


@router.get("/skills", response_model=list[SkillDescriptor])
def list_ai_skills(
    service: AIAnalysisService = Depends(get_ai_service),
    principal: Principal = Depends(require_permission("analytics.read")),
):
    return service.list_skills()


@router.get("/mcp/tools", response_model=list[MCPToolDescriptor])
def list_mcp_tools(
    service: CommerceMCPService = Depends(get_mcp_service),
    principal: Principal = Depends(require_permission("analytics.read")),
):
    return service.list_tools()


@router.post("/mcp/execute", response_model=MCPEnvelope)
def execute_mcp_tool(
    request: MCPExecuteRequest,
    service: CommerceMCPService = Depends(get_mcp_service),
    principal: Principal = Depends(require_permission("analytics.read")),
):
    arguments = dict(request.arguments)
    requested_store_id = arguments.get("store_id")
    arguments["store_id"] = resolve_store_scope(principal, requested_store_id)
    try:
        return service.execute(request.tool, arguments)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/analyze", response_model=AnalysisResponse)
def analyze_business(
    request: AnalysisRequest,
    service: AIAnalysisService = Depends(get_ai_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> AnalysisResponse:
    try:
        store_id = resolve_store_scope(principal, request.store_id)
        return service.analyze(request, store_id=store_id, user_id=principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/analyze/stream")
def stream_business_analysis(
    request: AnalysisRequest,
    service: AIAnalysisService = Depends(get_ai_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> StreamingResponse:
    store_id = resolve_store_scope(principal, request.store_id)
    events: Queue[dict | None] = Queue()

    def run() -> None:
        try:
            service.analyze(
                request,
                store_id=store_id,
                user_id=principal.user_id,
                on_event=events.put,
                stream_model=True,
            )
        except Exception as exc:  # The stream has already started; report the failure as an event.
            events.put({"event": "error", "status": "failed", "detail": str(exc)})
        finally:
            events.put(None)

    Thread(target=run, name="ai-analysis-stream", daemon=True).start()

    def generate():
        while True:
            event = events.get()
            if event is None:
                break
            event_name = str(event.get("event") or "message")
            yield f"event: {event_name}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/reports/period", response_model=PeriodReportResponse)
def build_period_report(
    request: PeriodReportRequest,
    service: AIAnalysisService = Depends(get_ai_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> PeriodReportResponse:
    try:
        store_id = resolve_store_scope(principal, request.store_id)
        return service.build_period_report(request, store_id=store_id, user_id=principal.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/reports/period/stream")
def stream_period_report(
    request: PeriodReportRequest,
    service: AIAnalysisService = Depends(get_ai_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> StreamingResponse:
    store_id = resolve_store_scope(principal, request.store_id)
    events: Queue[dict | None] = Queue()

    def run() -> None:
        try:
            service.build_period_report(
                request,
                store_id=store_id,
                user_id=principal.user_id,
                on_event=events.put,
                stream_model=True,
            )
        except Exception as exc:
            events.put({"event": "error", "status": "failed", "detail": str(exc)})
        finally:
            events.put(None)

    Thread(target=run, name="ai-period-report-stream", daemon=True).start()

    def generate():
        while True:
            event = events.get()
            if event is None:
                break
            event_name = str(event.get("event") or "message")
            yield f"event: {event_name}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/conversations", response_model=list[AIConversationListItem])
def list_conversations(
    store_id: int | None = Query(default=None),
    service: AIAnalysisService = Depends(get_ai_service),
    principal: Principal = Depends(require_permission("analytics.read")),
):
    return service.list_conversations(user_id=principal.user_id, store_id=resolve_store_scope(principal, store_id))


@router.get("/conversations/{conversation_id}", response_model=AIConversationDetail)
def get_conversation(
    conversation_id: str,
    store_id: int | None = Query(default=None),
    service: AIAnalysisService = Depends(get_ai_service),
    principal: Principal = Depends(require_permission("analytics.read")),
):
    return service.get_conversation(conversation_id, user_id=principal.user_id, store_id=resolve_store_scope(principal, store_id))


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    service: AIAnalysisService = Depends(get_ai_service),
    principal: Principal = Depends(require_permission("analytics.read")),
):
    if not service.delete_conversation(conversation_id, user_id=principal.user_id):
        raise HTTPException(status_code=404, detail="会话不存在或无权删除")
    return {"ok": True}
