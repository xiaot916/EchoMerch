import asyncio
import json
from queue import Empty, Queue
from threading import Thread
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
    PageAIProfileDescriptor,
    SkillDescriptor,
)
from app.modules.ai.page_profiles import list_page_ai_profiles
from app.modules.ai.service import AIAnalysisService
from app.modules.ai.run_registry import AIRunCancelled, get_ai_run_registry


router = APIRouter()


def get_ai_service() -> AIAnalysisService:
    return AIAnalysisService()


def get_mcp_service() -> CommerceMCPService:
    return CommerceMCPService()


def _stream_run(
    *,
    http_request: Request,
    kind: str,
    conversation_id: str | None,
    user_id: int | None,
    store_id: int | None,
    runner: Callable[[Callable[[dict], None], Callable[[], bool]], None],
) -> StreamingResponse:
    """Run one AI workflow with a shared, observable SSE lifecycle."""
    registry = get_ai_run_registry()
    record = registry.start(kind=kind, conversation_id=conversation_id, user_id=user_id, store_id=store_id)
    events: Queue[dict | None] = Queue()
    initial = record.snapshot()
    events.put({"event": "run", "status": "preparing", **initial})
    last_phase = "preparing"
    error_event_sent = False

    def publish(event: dict) -> None:
        nonlocal last_phase, error_event_sent
        if registry.is_cancelled(record.run_id):
            raise AIRunCancelled("AI 流式任务已取消")
        event_name = str(event.get("event") or "message")
        snapshot = registry.update(
            record.run_id,
            event=event_name,
            status=str(event.get("status")) if event.get("status") is not None else None,
            detail=str(event.get("detail")) if event.get("detail") is not None else None,
        ) or record.snapshot()
        phase = str(snapshot.get("phase") or last_phase)
        if phase != last_phase:
            last_phase = phase
            events.put({"event": "run", "status": phase, **snapshot})
        payload = {**event, "run_id": record.run_id, "revision": snapshot.get("revision", 0)}
        events.put(payload)
        if event_name == "error":
            error_event_sent = True

    def run() -> None:
        nonlocal last_phase
        try:
            runner(publish, lambda: registry.is_cancelled(record.run_id))
            snapshot = registry.finish(record.run_id, phase="complete") or record.snapshot()
            if last_phase != "complete":
                last_phase = "complete"
                events.put({"event": "run", "status": "complete", **snapshot})
        except AIRunCancelled as exc:
            snapshot = registry.finish(record.run_id, phase="cancelled", error=str(exc)) or record.snapshot()
            events.put({"event": "run", "status": "cancelled", **snapshot})
        except Exception as exc:  # The stream has already started; report the failure as an event.
            snapshot = registry.finish(record.run_id, phase="error", error=str(exc)) or record.snapshot()
            if not error_event_sent:
                events.put({"event": "error", "status": "failed", "detail": str(exc), "run_id": record.run_id, "revision": snapshot.get("revision", 0)})
            if last_phase != "error":
                last_phase = "error"
                events.put({"event": "run", "status": "error", **snapshot})
        finally:
            events.put(None)

    Thread(target=run, name=f"ai-{kind}-stream", daemon=True).start()

    async def generate():
        try:
            while True:
                if await http_request.is_disconnected():
                    registry.request_cancel(record.run_id, user_id=user_id, store_id=store_id)
                    break
                try:
                    event = await asyncio.to_thread(events.get, True, 0.5)
                except Empty:
                    continue
                if event is None:
                    break
                event_name = str(event.get("event") or "message")
                yield f"event: {event_name}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        finally:
            snapshot = registry.get(record.run_id, user_id=user_id, store_id=store_id)
            if snapshot and snapshot.get("phase") not in {"complete", "error", "cancelled"}:
                registry.request_cancel(record.run_id, user_id=user_id, store_id=store_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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


@router.get("/page-profiles", response_model=list[PageAIProfileDescriptor])
def list_ai_page_profiles(
    _: Principal = Depends(require_permission("analytics.read")),
) -> list[PageAIProfileDescriptor]:
    return [PageAIProfileDescriptor.model_validate(item.as_dict()) for item in list_page_ai_profiles()]


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
    http_request: Request,
    request: AnalysisRequest,
    service: AIAnalysisService = Depends(get_ai_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> StreamingResponse:
    store_id = resolve_store_scope(principal, request.store_id)
    return _stream_run(
        http_request=http_request,
        kind="analysis",
        conversation_id=request.conversation_id,
        user_id=principal.user_id,
        store_id=store_id,
        runner=lambda on_event, should_stop: service.analyze(
            request,
            store_id=store_id,
            user_id=principal.user_id,
            on_event=on_event,
            stream_model=True,
            should_stop=should_stop,
        ),
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
    http_request: Request,
    request: PeriodReportRequest,
    service: AIAnalysisService = Depends(get_ai_service),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> StreamingResponse:
    store_id = resolve_store_scope(principal, request.store_id)
    return _stream_run(
        http_request=http_request,
        kind="period-report",
        conversation_id=request.conversation_id,
        user_id=principal.user_id,
        store_id=store_id,
        runner=lambda on_event, should_stop: service.build_period_report(
            request,
            store_id=store_id,
            user_id=principal.user_id,
            on_event=on_event,
            stream_model=True,
            should_stop=should_stop,
        ),
    )


@router.get("/runs/{run_id}")
def get_ai_run(
    run_id: str,
    store_id: int | None = Query(default=None),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> dict[str, object]:
    registry = get_ai_run_registry()
    run = registry.get(run_id, user_id=principal.user_id, store_id=resolve_store_scope(principal, store_id))
    if run is None:
        raise HTTPException(status_code=404, detail="AI 运行任务不存在或不属于当前账号/店铺")
    return run


@router.post("/runs/{run_id}/cancel")
def cancel_ai_run(
    run_id: str,
    store_id: int | None = Query(default=None),
    principal: Principal = Depends(require_permission("analytics.read")),
) -> dict[str, object]:
    registry = get_ai_run_registry()
    resolved_store_id = resolve_store_scope(principal, store_id)
    if not registry.request_cancel(run_id, user_id=principal.user_id, store_id=resolved_store_id):
        raise HTTPException(status_code=404, detail="AI 运行任务不存在、已结束或不属于当前账号/店铺")
    return registry.get(run_id, user_id=principal.user_id, store_id=resolved_store_id) or {"run_id": run_id, "phase": "stopping"}


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
    try:
        return service.get_conversation(conversation_id, user_id=principal.user_id, store_id=resolve_store_scope(principal, store_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    service: AIAnalysisService = Depends(get_ai_service),
    principal: Principal = Depends(require_permission("analytics.read")),
):
    if not service.delete_conversation(conversation_id, user_id=principal.user_id):
        raise HTTPException(status_code=404, detail="会话不存在或无权删除")
    return {"ok": True}
