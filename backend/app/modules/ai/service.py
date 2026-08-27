from __future__ import annotations

import json
import re
import time
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from collections.abc import Callable

from app.core.config import settings
from app.core.local_database import LocalDatabase
from app.modules.ai.mcp import CommerceMCPService
from app.modules.ai.provider import AIProviderError, AgnesProvider
from app.modules.ai.schemas import (
    AIConversationState,
    AIConversationMessage,
    AIConversationListItem,
    AIConversationDetail,
    AnalysisRequest,
    AnalysisResponse,
    CoverageSummary,
    ExecutionStep,
    MCPEnvelope,
    PeriodReportRequest,
    PeriodReportResponse,
    ArtifactSpec,
    Diagnosis,
    DiagnosisFinding,
    RecommendedAction,
)
from app.modules.ai.skills import SKILLS, select_skills


class AIAnalysisService:
    def __init__(
        self,
        *,
        mcp: CommerceMCPService | None = None,
        provider: AgnesProvider | None = None,
        database_path: Path | None = None,
    ) -> None:
        self.mcp = mcp or CommerceMCPService()
        self.provider = provider or AgnesProvider()
        self.database = LocalDatabase(Path(database_path or settings.local_database_path))

    def _conversation_state(
        self,
        conversation_id: str | None,
        *,
        user_id: int | None,
        store_id: int | None,
        create: bool = True,
    ) -> AIConversationState:
        """Load a bounded conversation context scoped to the current user and store."""
        conversation_id = conversation_id or str(uuid4())
        self.database.initialize_schema()
        with self.database.connect(initialize=True) as conn:
            row = conn.execute(
                """
                select conversation_id, summary, memory_json, updated_at
                from ai_conversations
                where conversation_id = ?
                  and ((user_id is null and ? is null) or user_id = ?)
                  and ((store_id is null and ? is null) or store_id = ?)
                """,
                (conversation_id, user_id, user_id, store_id, store_id),
            ).fetchone()
            if row is None:
                existing = conn.execute(
                    "select 1 from ai_conversations where conversation_id = ?",
                    (conversation_id,),
                ).fetchone()
                if existing is not None or not create:
                    raise ValueError("会话不存在或不属于当前账号/店铺")
                now = datetime.now().astimezone().isoformat(timespec="seconds")
                conn.execute(
                    """
                    insert into ai_conversations
                        (conversation_id, user_id, store_id, created_at, updated_at)
                    values (?, ?, ?, ?, ?)
                    """,
                    (conversation_id, user_id, store_id, now, now),
                )
                conn.commit()
                return AIConversationState(conversation_id=conversation_id, updated_at=now)
            try:
                memory = json.loads(row["memory_json"] or "{}")
            except (TypeError, ValueError):
                memory = {}
            messages = conn.execute(
                """
                select role, text, analysis_json, created_at
                from ai_conversation_messages
                where conversation_id = ?
                order by created_at desc, rowid desc
                limit 8
                """,
                (conversation_id,),
            ).fetchall()
        return AIConversationState(
            conversation_id=str(row["conversation_id"]),
            summary=str(row["summary"] or ""),
            memory=memory if isinstance(memory, dict) else {},
            recent_messages=[
                AIConversationMessage(
                    role=str(item["role"]),
                    text=str(item["text"]),
                    created_at=str(item["created_at"]),
                    payload=self._message_payload(item["analysis_json"]),
                )
                for item in reversed(messages)
            ],
            updated_at=str(row["updated_at"] or ""),
        )

    def _remember(
        self,
        state: AIConversationState,
        *,
        user_id: int | None,
        store_id: int | None,
        question: str,
        answer: str,
        memory: dict,
        response: AnalysisResponse | PeriodReportResponse | None = None,
        request_context: dict | None = None,
    ) -> None:
        now = datetime.now().astimezone().isoformat(timespec="microseconds")
        summary = str(memory.get("summary") or question[:160])[:500]
        payload = self._conversation_message_payload(response, request_context=request_context) if response is not None else None
        self.database.initialize_schema()
        with self.database.connect(initialize=True) as conn:
            conn.execute(
                """
                insert or ignore into ai_conversations
                    (conversation_id, user_id, store_id, created_at, updated_at)
                values (?, ?, ?, ?, ?)
                """,
                (state.conversation_id, user_id, store_id, now, now),
            )
            conn.execute(
                """
                update ai_conversations
                set store_id = coalesce(store_id, ?),
                    title = case when title = '新对话' then ? else title end,
                    summary = ?, memory_json = ?, updated_at = ?
                where conversation_id = ?
                """,
                (
                    store_id,
                    question[:24],
                    summary,
                    json.dumps(memory, ensure_ascii=False, default=self._json_default),
                    now,
                    state.conversation_id,
                ),
            )
            conn.execute(
                """
                insert into ai_conversation_messages
                    (message_id, conversation_id, role, text, analysis_json, created_at)
                values (?, ?, 'user', ?, null, ?), (?, ?, 'assistant', ?, ?, ?)
                """,
                (
                    str(uuid4()), state.conversation_id, question[:4000], now,
                    str(uuid4()), state.conversation_id, answer[:12000],
                    json.dumps(payload, ensure_ascii=False, default=self._json_default) if payload else None,
                    now,
                ),
            )
            conn.execute(
                """
                delete from ai_conversation_messages
                where conversation_id = ?
                  and message_id not in (
                    select message_id from ai_conversation_messages
                    where conversation_id = ? order by created_at desc, rowid desc limit 200
                  )
                """,
                (state.conversation_id, state.conversation_id),
            )
            conn.commit()

    @staticmethod
    def _json_default(value: object):
        """Keep persisted AI context JSON-safe for typed query values."""
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return str(value)

    @classmethod
    def _conversation_message_payload(
        cls,
        response: AnalysisResponse | PeriodReportResponse | None,
        *,
        request_context: dict | None = None,
    ) -> dict | None:
        """Persist the renderable response, while bounding raw MCP rows."""
        if response is None:
            return None
        if isinstance(response, AnalysisResponse):
            data = response.model_dump(mode="json")
            data["mcp_results"] = cls._bounded_mcp_results(response.mcp_results)
            return {"kind": "analysis", "data": data, "request": request_context or {}}
        data = response.model_dump(mode="json")
        data["mcp_result"] = cls._bounded_mcp_result(response.mcp_result)
        return {"kind": "report", "data": data, "request": request_context or {}}

    @staticmethod
    def _message_payload(value: object) -> dict | None:
        if not value:
            return None
        try:
            payload = json.loads(str(value))
        except (TypeError, ValueError):
            return None
        return payload if isinstance(payload, dict) and payload.get("kind") in {"analysis", "report"} else None

    @staticmethod
    def _bounded_mcp_result(result: MCPEnvelope | dict) -> dict:
        item = result.model_dump(mode="json") if isinstance(result, MCPEnvelope) else dict(result)
        data = item.get("data") or {}
        for key in ("rows", "sources", "campaigns", "datasets", "items"):
            value = data.get(key)
            if isinstance(value, list) and len(value) > 240:
                data[key] = value[:240]
                data.setdefault("_truncated", []).append({"key": key, "total": len(value), "returned": 240})
        item["data"] = data
        return item

    @classmethod
    def _bounded_mcp_results(cls, results: list[MCPEnvelope]) -> list[dict]:
        return [cls._bounded_mcp_result(result) for result in results]

    @staticmethod
    def _analysis_memory(response: AnalysisResponse, state: AIConversationState) -> dict:
        diagnosis = response.diagnosis
        findings = [{"title": item.title, "detail": item.detail} for item in diagnosis.findings[:3]]
        actions = [{"priority": item.priority, "title": item.title, "validation": item.validation} for item in diagnosis.actions[:3]]
        focus: list[dict] = []
        for artifact in diagnosis.artifacts[:2]:
            focus.extend(artifact.rows[:5])
        return {
            "summary": diagnosis.headline,
            "last_question": "",
            "skill": response.skill.name,
            "range_start": diagnosis.analysis_scope.get("range_start"),
            "range_end": diagnosis.analysis_scope.get("range_end"),
            "headline": diagnosis.headline,
            "findings": findings,
            "actions": actions,
            "focus": focus[:8],
            "metric_definitions": dict(list(diagnosis.metric_definitions.items())[:12]),
            "evidence_refs": diagnosis.evidence_refs[:12],
            "confidence": diagnosis.confidence,
            "causal_boundary": diagnosis.causal_boundary,
            "previous": state.memory.get("headline"),
        }

    @staticmethod
    def _memory_timeline(state: AIConversationState, *, question: str, headline: str, skill: str, range_start=None, range_end=None) -> list[dict]:
        existing = state.memory.get("timeline")
        timeline = list(existing[-5:]) if isinstance(existing, list) else []
        timeline.append({
            "question": question[:300],
            "headline": headline[:500],
            "skill": skill,
            "range_start": range_start,
            "range_end": range_end,
        })
        return timeline

    @staticmethod
    def _analysis_turn_memory(
        response: AnalysisResponse,
        state: AIConversationState,
        *,
        question: str,
        planning_inputs: dict[str, object],
        page_context: dict,
    ) -> dict:
        memory = AIAnalysisService._analysis_memory(response, state)
        previous_inputs = state.memory.get("planning_inputs")
        merged_inputs = dict(previous_inputs) if isinstance(previous_inputs, dict) else {}
        merged_inputs.update(planning_inputs)
        return {
            **memory,
            "last_question": question,
            "planning_inputs": merged_inputs,
            "page_context": page_context,
            "timeline": AIAnalysisService._memory_timeline(
                state,
                question=question,
                headline=response.diagnosis.headline,
                skill=response.skill.name,
                range_start=response.diagnosis.analysis_scope.get("range_start"),
                range_end=response.diagnosis.analysis_scope.get("range_end"),
            ),
        }

    @staticmethod
    def _conversation_prompt_context(state: AIConversationState) -> dict:
        recent_messages = []
        for item in state.recent_messages:
            entry = {"role": item.role, "text": item.text, "created_at": item.created_at}
            payload = item.payload or {}
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, dict):
                diagnosis = data.get("diagnosis") or {}
                entry["context"] = {
                    "kind": payload.get("kind"),
                    "request": payload.get("request") or {},
                    "headline": diagnosis.get("headline"),
                    "analysis_scope": diagnosis.get("analysis_scope"),
                    "coverage": diagnosis.get("coverage"),
                }
            recent_messages.append(entry)
        return {
            "conversation_id": state.conversation_id,
            "conversation_summary": state.summary,
            "conversation_memory": state.memory,
            "recent_messages": recent_messages,
            "memory_rules": "仅把历史内容用于指代消解和延续分析；当前查询数据与当前日期范围优先，不能把历史缺失数据当作当前事实。",
        }

    @staticmethod
    def _contextual_request(request: AnalysisRequest, state: AIConversationState) -> AnalysisRequest:
        question = request.question.strip()
        if not state.memory:
            return request
        follow_up = bool(re.search(
            r"(^|[，,。\s])(那|那么|这个|这些|上述|上面|刚才|之前|前面|继续|再|展开|细说|它|他们|其中|前者|后者|分别|按(?:这个|上面|上述|剩余|该|此|以上|前述)|换成|改成|第[一二三四五六七八九十\d]+个)",
            question,
        )) or bool(len(question) <= 12 and re.match(r"^(哪个|哪一个|为什么|怎么|如何)", question))
        if not follow_up:
            return request
        memory = state.memory
        context_text = json.dumps(
            {
                "上一轮问题": memory.get("last_question"),
                "上一轮结论": memory.get("headline"),
                "重点对象": memory.get("focus") or memory.get("findings"),
                "上一轮分析能力": memory.get("skill"),
                "上一轮范围": [memory.get("range_start"), memory.get("range_end")],
                "已确认规划输入": memory.get("planning_inputs"),
                "近期结论": memory.get("timeline"),
            },
            ensure_ascii=False,
        )
        return request.model_copy(update={"question": f"基于以下上一轮上下文回答追问。{context_text}\n当前追问：{question}"})

    def list_skills(self):
        return [skill.descriptor for skill in SKILLS]

    def list_conversations(self, *, user_id: int | None, store_id: int | None, limit: int = 30) -> list[AIConversationListItem]:
        self.database.initialize_schema()
        with self.database.connect(initialize=True) as conn:
            rows = conn.execute(
                """
                select c.conversation_id, c.title, c.updated_at, count(m.message_id) message_count
                from ai_conversations c
                left join ai_conversation_messages m on m.conversation_id = c.conversation_id
                where ((c.user_id is null and ? is null) or c.user_id = ?)
                  and ((c.store_id is null and ? is null) or c.store_id = ?)
                group by c.conversation_id, c.title, c.updated_at
                order by c.updated_at desc
                limit ?
                """,
                (user_id, user_id, store_id, store_id, limit),
            ).fetchall()
        return [AIConversationListItem(**dict(row)) for row in rows]

    def get_conversation(self, conversation_id: str, *, user_id: int | None, store_id: int | None) -> AIConversationDetail:
        state = self._conversation_state(conversation_id, user_id=user_id, store_id=store_id, create=False)
        self.database.initialize_schema()
        with self.database.connect(initialize=True) as conn:
            row = conn.execute("select title from ai_conversations where conversation_id = ?", (state.conversation_id,)).fetchone()
            messages = conn.execute(
                """
                select role, text, analysis_json, created_at from ai_conversation_messages
                where conversation_id = ? order by created_at desc, rowid desc limit 200
                """,
                (state.conversation_id,),
            ).fetchall()
        return AIConversationDetail(
            **state.model_dump(exclude={"recent_messages"}),
            title=str(row["title"] if row else "新对话"),
            recent_messages=[
                AIConversationMessage(
                    role=str(item["role"]),
                    text=str(item["text"]),
                    created_at=str(item["created_at"]),
                    payload=self._message_payload(item["analysis_json"]),
                )
                for item in reversed(messages)
            ],
        )

    def delete_conversation(self, conversation_id: str, *, user_id: int | None) -> bool:
        self.database.initialize_schema()
        with self.database.connect(initialize=True) as conn:
            cursor = conn.execute(
                """
                delete from ai_conversations
                where conversation_id = ? and ((user_id is null and ? is null) or user_id = ?)
                """,
                (conversation_id, user_id, user_id),
            )
            conn.commit()
        return cursor.rowcount > 0

    @staticmethod
    def _emit(callback: Callable[[dict], None] | None, event: str, **payload: object) -> None:
        if callback is not None:
            callback({"event": event, **payload})

    @staticmethod
    def _tool_call_key(tool: str, arguments: dict[str, object]) -> str:
        """Stable signature for reusing an identical read-only MCP call."""
        ignored = {"request_id"}
        # A larger/smaller display limit does not change the analytical
        # population or aggregates. Reuse the first query instead of showing
        # duplicate data-tool steps for the same page evidence.
        if tool == "data.query":
            ignored.add("limit")
        payload = {key: arguments[key] for key in sorted(arguments) if key not in ignored}
        return f"{tool}:{json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)}"

    def analyze(
        self,
        request: AnalysisRequest,
        *,
        store_id: int | None,
        user_id: int | None = None,
        on_event: Callable[[dict], None] | None = None,
        stream_model: bool = False,
    ) -> AnalysisResponse:
        started = time.perf_counter()
        request_id = str(uuid4())
        conversation = self._conversation_state(request.conversation_id, user_id=user_id, store_id=store_id)
        contextual_request = self._contextual_request(request, conversation)
        skill, supporting_skills = select_skills(contextual_request.question, request.domain, request.page_context)
        skill_inputs = self._planning_inputs(contextual_request)
        self._emit(on_event, "planner", status="completed", name="ecommerce-analysis-router", detail=f"已选择主能力：{skill.descriptor.display_name}")
        self._emit(on_event, "skill", status="completed", name=skill.descriptor.name, detail=f"主能力 {skill.descriptor.display_name} · 辅助能力 {len(supporting_skills)} 个", skill=skill.descriptor.model_dump(mode="json"), supporting_skills=[item.descriptor.model_dump(mode="json") for item in supporting_skills])
        steps = [
            ExecutionStep(kind="planner", name="ecommerce-analysis-router", status="completed", detail=f"主 Skill：{skill.descriptor.display_name}；候选辅助 Skill：{len(supporting_skills)} 个", elapsed_ms=0),
            ExecutionStep(kind="skill", name=skill.descriptor.name, status="completed", detail=f"版本 {skill.descriptor.version}", elapsed_ms=0),
        ]
        results: list[MCPEnvelope] = []
        warnings: list[str] = []
        executed_calls: set[str] = set()
        status = "ok"
        error_message: str | None = None

        try:
            # Inventory is a dedicated point-in-time workflow. Do not let a
            # single word such as “库存” hijack a store-wide diagnosis that
            # intentionally includes product, channel and service evidence.
            if skill.descriptor.name == "inventory-query":
                self._emit(on_event, "mcp", status="running", name="inventory.query", detail="查询最新库存快照")
                tool_started = time.perf_counter()
                inventory_result = self.mcp.execute("inventory.query", {
                    "store_id": store_id,
                    "query": contextual_request.question,
                    # Inventory is a point-in-time snapshot. Unless the user
                    # explicitly asks for a historical day, use the latest
                    # successful snapshot rather than the business date filter.
                    "business_day": self._inventory_business_day(contextual_request.question),
                })
                results.append(inventory_result)
                warnings.extend(inventory_result.warnings)
                tool_elapsed = round((time.perf_counter() - tool_started) * 1000, 1)
                steps.append(ExecutionStep(kind="mcp", name="inventory.query", status="completed", detail="查询最新库存快照；组合货品仅返回主档和组成关系", elapsed_ms=tool_elapsed))
                self._emit(on_event, "mcp", status="completed", name="inventory.query", detail="库存快照已返回", result_status=inventory_result.status, elapsed_ms=tool_elapsed)
                diagnosis = self._enrich_diagnosis(
                    self._inventory_diagnosis(inventory_result),
                    request=request,
                    results=results,
                    skill_inputs=skill_inputs,
                    skill=skill,
                )
                answer = self._deterministic_answer(diagnosis)
                response = AnalysisResponse(
                    request_id=request_id,
                    conversation_id=conversation.conversation_id,
                    status=inventory_result.status,
                    skill=skill.descriptor,
                    supporting_skills=[item.descriptor for item in supporting_skills],
                    provider="rules",
                    model=None,
                    elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
                    answer=answer,
                    diagnosis=diagnosis,
                    mcp_results=results,
                    execution_steps=steps,
                    warnings=list(dict.fromkeys(warnings)),
                )
                turn_memory = self._analysis_turn_memory(
                    response,
                    conversation,
                    question=request.question,
                    planning_inputs=skill_inputs,
                    page_context=request.page_context,
                )
                response = response.model_copy(update={"conversation_memory": turn_memory})
                self._remember(
                    conversation,
                    user_id=user_id,
                    store_id=store_id,
                    question=request.question,
                    answer=answer,
                    memory=turn_memory,
                    response=response,
                    request_context=self._analysis_request_context(request, store_id=store_id),
                )
                self._log(request_id, request, store_id, response, started, None)
                self._emit(on_event, "final", status="completed", response=response.model_dump(mode="json"))
                return response
            workflow_start, workflow_end = self._workflow_dates(request, skill.descriptor.name, store_id)
            arguments = {
                "store_id": store_id,
                "start_date": workflow_start,
                "end_date": workflow_end,
            }
            custom_diagnosis: Diagnosis | None = None
            # The legacy catalog lookup is only for a concrete product
            # identity.  Structure questions must use the period comparison
            # workflow so a phrase such as “下钻客单价下降的系列、类型和商品”
            # is not reduced to a literal catalog search for “下降”.
            if (
                skill.descriptor.name == "product-diagnosis"
                and self._is_product_question(contextual_request.question)
                and self._has_specific_product_identity(contextual_request.question)
            ):
                lookup = self._product_lookup_query(contextual_request.question)
                search_arguments = {"store_id": store_id, **lookup, "limit": 100}
                executed_calls.add(self._tool_call_key("products.search", search_arguments))
                self._emit(on_event, "mcp", status="running", name="products.search", detail=f"按商品 ID/名称搜索商品主档：{lookup}")
                tool_started = time.perf_counter()
                search_result = self.mcp.execute("products.search", search_arguments)
                tool_elapsed = round((time.perf_counter() - tool_started) * 1000, 1)
                results.append(search_result)
                warnings.extend(search_result.warnings)
                steps.append(ExecutionStep(kind="mcp", name="products.search", status="completed", detail=f"商品主档搜索返回 {search_result.data.get('total', 0)} 条；{search_result.status}", elapsed_ms=tool_elapsed))
                self._emit(on_event, "mcp", status="completed", name="products.search", detail=f"商品主档搜索完成 · {search_result.status}", result_status=search_result.status, elapsed_ms=tool_elapsed)
                search_rows = search_result.data.get("rows") or []
                if len(search_rows) == 1:
                    product_id = str(search_rows[0].get("product_id") or "")
                    profile_arguments = {"store_id": store_id, "product_id": product_id, "start_date": workflow_start, "end_date": workflow_end}
                    executed_calls.add(self._tool_call_key("products.get_profile", profile_arguments))
                    self._emit(on_event, "mcp", status="running", name="products.get_profile", detail=f"唯一命中商品 {product_id}，读取经营画像")
                    tool_started = time.perf_counter()
                    profile_result = self.mcp.execute("products.get_profile", profile_arguments)
                    tool_elapsed = round((time.perf_counter() - tool_started) * 1000, 1)
                    results.append(profile_result)
                    warnings.extend(profile_result.warnings)
                    steps.append(ExecutionStep(kind="mcp", name="products.get_profile", status="completed", detail=f"读取商品画像；{profile_result.status}", elapsed_ms=tool_elapsed))
                    self._emit(on_event, "mcp", status="completed", name="products.get_profile", detail="商品画像已返回", result_status=profile_result.status, elapsed_ms=tool_elapsed)
                else:
                    series_names = {str(item.get("series") or "").strip() for item in search_rows if str(item.get("series") or "").strip()}
                    positioning = lookup.get("positioning")
                    product_type = lookup.get("product_type")
                    asks_series = any(token in contextual_request.question.casefold() for token in ("系列", "正装", "mini", "试用装", "类型"))
                    if len(series_names) == 1 and (asks_series or positioning or product_type):
                        series_name = next(iter(series_names))
                        profile_arguments = {"store_id": store_id, "series": series_name, "positioning": positioning, "product_type": product_type, "start_date": workflow_start, "end_date": workflow_end}
                        executed_calls.add(self._tool_call_key("products.get_series_profile", profile_arguments))
                        self._emit(on_event, "mcp", status="running", name="products.get_series_profile", detail=f"按系列聚合商品画像：{series_name}")
                        tool_started = time.perf_counter()
                        profile_result = self.mcp.execute("products.get_series_profile", profile_arguments)
                        tool_elapsed = round((time.perf_counter() - tool_started) * 1000, 1)
                        results.append(profile_result)
                        warnings.extend(profile_result.warnings)
                        steps.append(ExecutionStep(kind="mcp", name="products.get_series_profile", status="completed", detail=f"读取系列画像；{profile_result.status}", elapsed_ms=tool_elapsed))
                        self._emit(on_event, "mcp", status="completed", name="products.get_series_profile", detail="系列画像已返回", result_status=profile_result.status, elapsed_ms=tool_elapsed)
                custom_diagnosis = self._product_profile_diagnosis(results)
            else:
                workflow = skill.descriptor.workflow or []
                for step in workflow:
                    step_arguments = {**arguments, **step.arguments}
                    if skill.descriptor.name == "mini-product-diagnosis" and step.tool == "mini.get_diagnosis":
                        # The MINI tool owns catalog identity. Pass through an
                        # explicit product ID when the user supplied one;
                        # otherwise its default matcher covers mini/MINI,
                        # 尝鲜 and 试用装 in title, attributes, positioning or
                        # type. Do not turn the whole natural-language
                        # question into a noisy LIKE query.
                        mini_match = re.search(
                            r"(?:商品\s*id|item\s*id|货品(?:编码|id)|商品编码|sku(?:编码|id)?)\s*[:：]?\s*([A-Za-z0-9_-]+)",
                            contextual_request.question,
                            re.IGNORECASE,
                        )
                        if mini_match:
                            step_arguments["product_id"] = mini_match.group(1)
                        else:
                            lowered_question = contextual_request.question.casefold()
                            mini_terms: list[str] = []
                            if "mini" in lowered_question:
                                mini_terms.append("mini")
                            if "尝鲜" in contextual_request.question:
                                mini_terms.append("尝鲜")
                            if "试用装" in contextual_request.question and not mini_terms:
                                mini_terms.append("试用装")
                            if "小规格" in contextual_request.question and not mini_terms:
                                mini_terms.extend(("mini", "尝鲜", "试用装"))
                            if mini_terms:
                                step_arguments["query"] = ",".join(mini_terms)
                    executed_calls.add(self._tool_call_key(step.tool, step_arguments))
                    self._emit(on_event, "mcp", status="running", name=step.tool, detail=step.description or "执行数据工具")
                    tool_started = time.perf_counter()
                    result = self.mcp.execute(step.tool, step_arguments)
                    tool_elapsed = round((time.perf_counter() - tool_started) * 1000, 1)
                    results.append(result)
                    warnings.extend(result.warnings)
                    detail = f"{step.description}；返回 {result.status}" if step.description else f"返回 {result.status}"
                    steps.append(ExecutionStep(kind="mcp", name=step.tool, status="completed", detail=detail, elapsed_ms=tool_elapsed))
                    self._emit(on_event, "mcp", status="completed", name=step.tool, detail=detail, result_status=result.status, elapsed_ms=tool_elapsed)
                    if skill.descriptor.name == "data-exploration" and step.tool == "data.catalog" and not request.page_context.get("page_key"):
                        query_arguments = self._exploration_query_arguments(contextual_request.question, arguments, request.page_context)
                        executed_calls.add(self._tool_call_key("data.query", query_arguments))
                        self._emit(on_event, "mcp", status="running", name="data.query", detail="根据问题继续下钻数据集")
                        query_started = time.perf_counter()
                        query_result = self.mcp.execute("data.query", query_arguments)
                        query_elapsed = round((time.perf_counter() - query_started) * 1000, 1)
                        results.append(query_result)
                        warnings.extend(query_result.warnings)
                        steps.append(ExecutionStep(kind="mcp", name="data.query", status="completed", detail="根据问题关键词选择数据集并下钻", elapsed_ms=query_elapsed))
                        self._emit(on_event, "mcp", status="completed", name="data.query", detail="数据下钻已返回", result_status=query_result.status, elapsed_ms=query_elapsed)

                # A primary Skill owns the calculations, while this evidence
                # plan loads the neighbouring store facts that let Agnes rank
                # competing explanations.  All calls are read-only and are
                # deduplicated against the primary workflow.
                for tool, extra_arguments in self._compound_evidence_plan(
                    skill.descriptor.name,
                    contextual_request.question,
                    request.page_context,
                ):
                    evidence_arguments = {**arguments, **extra_arguments}
                    call_key = self._tool_call_key(tool, evidence_arguments)
                    if call_key in executed_calls:
                        detail = "与主能力已执行的数据调用重复，已复用现有结果"
                        steps.append(ExecutionStep(kind="mcp", name=tool, status="skipped", detail=detail, elapsed_ms=0))
                        self._emit(on_event, "mcp", status="skipped", name=tool, detail=detail)
                        continue
                    executed_calls.add(call_key)
                    self._emit(on_event, "mcp", status="running", name=tool, detail="补充跨域经营证据")
                    evidence_started = time.perf_counter()
                    try:
                        evidence_result = self.mcp.execute(tool, evidence_arguments)
                    except Exception as exc:
                        warnings.append(f"辅助数据工具 {tool} 未返回：{exc}")
                        evidence_elapsed = round((time.perf_counter() - evidence_started) * 1000, 1)
                        steps.append(ExecutionStep(kind="mcp", name=tool, status="failed", detail="辅助证据不可用，已继续使用已有数据", elapsed_ms=evidence_elapsed))
                        self._emit(on_event, "mcp", status="failed", name=tool, detail="辅助证据不可用，已继续使用已有数据", elapsed_ms=evidence_elapsed)
                        continue
                    evidence_elapsed = round((time.perf_counter() - evidence_started) * 1000, 1)
                    results.append(evidence_result)
                    warnings.extend(evidence_result.warnings)
                    steps.append(ExecutionStep(kind="mcp", name=tool, status="completed", detail=f"跨域证据已返回；{evidence_result.status}", elapsed_ms=evidence_elapsed))
                    self._emit(on_event, "mcp", status="completed", name=tool, detail="跨域证据已返回", result_status=evidence_result.status, elapsed_ms=evidence_elapsed)

                if skill.descriptor.name == "promotion-roi":
                    efficiency = next((item for item in results if item.tool == "promotions.get_efficiency"), None)
                    scenes = (efficiency.data.get("scenes") if efficiency else None) or []
                    low_scenes = sorted([item for item in scenes if float(item.get("spend") or 0) > 0 and float(item.get("roi") or 0) < 1.5], key=lambda item: float(item.get("spend") or 0), reverse=True)[:2]
                    for scene in low_scenes:
                        scene_name = scene.get("scene_name") or scene.get("dimension_name") or ""
                        self._emit(on_event, "mcp", status="running", name="promotions.get_drilldown", detail=f"下钻低效场景：{scene_name} → 计划")
                        drill_started = time.perf_counter()
                        drill_result = self.mcp.execute("promotions.get_drilldown", {"store_id": store_id, "start_date": workflow_start, "end_date": workflow_end, "level": "campaign", "scene": scene_name, "max_roi": 1.5, "order_by": "-spend", "page": 1, "page_size": 50})
                        drill_elapsed = round((time.perf_counter() - drill_started) * 1000, 1)
                        results.append(drill_result)
                        warnings.extend(drill_result.warnings)
                        steps.append(ExecutionStep(kind="mcp", name="promotions.get_drilldown", status="completed", detail=f"{scene_name} 低效计划已分页返回 {drill_result.data.get('total', 0)} 条", elapsed_ms=drill_elapsed))
                        self._emit(on_event, "mcp", status="completed", name="promotions.get_drilldown", detail=f"低效场景 {scene_name} 已下钻", result_status=drill_result.status, elapsed_ms=drill_elapsed)
            base_diagnosis = custom_diagnosis or skill.diagnose(results, skill_inputs)
            if skill.descriptor.name == "data-exploration" and request.page_context.get("page_key"):
                page_name = str(request.page_context.get("page") or request.page_context.get("section") or "当前页面")
                business_results = [item for item in results if item.tool != "data.catalog"]
                datasets = list(dict.fromkeys(evidence.dataset for item in business_results for evidence in item.evidence if evidence.dataset))
                base_diagnosis = base_diagnosis.model_copy(update={
                    "headline": f"{page_name}多域经营证据已汇总",
                    "summary": f"已读取 {len(business_results)} 个数据工具、{len(datasets)} 个数据集，覆盖：{'、'.join(datasets[:8]) or '当前页面数据'}。",
                })
            diagnosis = self._enrich_diagnosis(
                base_diagnosis,
                request=request,
                results=results,
                skill_inputs=skill_inputs,
                skill=skill,
            )
            coverage = diagnosis.coverage
            fact_sheet = self._analysis_fact_sheet(results, coverage)
            all_no_data = bool(results) and all(result.status == "no_data" for result in results)
            status = "no_data" if all_no_data else "partial" if (
                any(result.status == "partial" for result in results)
                or coverage.missing_dates
                or coverage.missing_datasets
                or coverage.partial_datasets
                or coverage.failed_datasets
                or coverage.no_data_datasets
                or any(step.status == "failed" for step in steps)
            ) else "ok"
            answer = self._deterministic_answer(diagnosis)
            provider_name = "rules"
            model_name = None
            should_use_model = request.use_model and self.provider.configured and skill.descriptor.name != "general-chat"
            if should_use_model:
                self._emit(on_event, "model", status="running", name=self.provider.model, detail="基于结构化诊断生成回答")
                model_started = time.perf_counter()
                try:
                    provider_kwargs = {
                        "question": request.question,
                        "diagnosis": diagnosis,
                        "evidence": [item.model_dump(mode="json") for result in results for item in result.evidence],
                        "mcp_results": self._model_mcp_results(results),
                        "context": {
                            "store_id": store_id,
                            "page_context": request.page_context,
                            "analysis_mode": True,
                            "supporting_skills": [item.descriptor.name for item in supporting_skills],
                            "store_fact_sheet": fact_sheet,
                            **self._conversation_prompt_context(conversation),
                        },
                    }
                    if stream_model and on_event is not None:
                        answer = ""
                        for chunk in self.provider.stream_answer(**provider_kwargs):
                            answer += chunk
                            self._emit(on_event, "token", text=chunk)
                        if not answer.strip():
                            raise AIProviderError("Agnes returned an empty streaming answer")
                    else:
                        answer = self.provider.generate_answer(**provider_kwargs)
                    provider_name = self.provider.name
                    model_name = self.provider.model
                    model_elapsed = round((time.perf_counter() - model_started) * 1000, 1)
                    steps.append(ExecutionStep(kind="model", name=self.provider.model, status="completed", detail="AI 已基于结构化诊断生成回答", elapsed_ms=model_elapsed))
                    self._emit(on_event, "model", status="completed", name=self.provider.model, detail="回答生成完成", elapsed_ms=model_elapsed)
                except AIProviderError as exc:
                    warnings.append("AI 模型调用失败，已回退到确定性业务规则结果。")
                    error_message = str(exc)
                    model_elapsed = round((time.perf_counter() - model_started) * 1000, 1)
                    steps.append(ExecutionStep(kind="model", name=self.provider.model, status="failed", detail="已使用规则结果回退", elapsed_ms=model_elapsed))
                    self._emit(on_event, "model", status="failed", name=self.provider.model, detail="模型不可用，已回退规则结果", elapsed_ms=model_elapsed)
            else:
                if skill.descriptor.name == "general-chat":
                    reason = "通用对话使用快速回复"
                else:
                    reason = "本次请求未启用模型" if not request.use_model else "后端未配置 Agnes API Key"
                steps.append(ExecutionStep(kind="model", name=self.provider.model, status="skipped", detail=reason, elapsed_ms=0))
                self._emit(on_event, "model", status="skipped", name=self.provider.model, detail=reason, elapsed_ms=0)
            response = AnalysisResponse(
                request_id=request_id,
                conversation_id=conversation.conversation_id,
                status=status,
                skill=skill.descriptor,
                supporting_skills=[item.descriptor for item in supporting_skills],
                provider=provider_name,
                model=model_name,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
                answer=answer,
                diagnosis=diagnosis,
                mcp_results=results,
                execution_steps=steps,
                warnings=list(dict.fromkeys(warnings)),
            )
            turn_memory = self._analysis_turn_memory(
                response,
                conversation,
                question=request.question,
                planning_inputs=skill_inputs,
                page_context=request.page_context,
            )
            response = response.model_copy(update={"conversation_memory": turn_memory})
            self._remember(
                conversation,
                user_id=user_id,
                store_id=store_id,
                question=request.question,
                answer=answer,
                memory=turn_memory,
                response=response,
                request_context=self._analysis_request_context(request, store_id=store_id),
            )
            self._log(request_id, request, store_id, response, started, error_message)
            self._emit(on_event, "final", status="completed", response=response.model_dump(mode="json"))
            return response
        except Exception as exc:
            self._emit(on_event, "error", status="failed", detail=str(exc))
            self._log_failure(request_id, request, store_id, skill.descriptor.name, skill.descriptor.version, started, str(exc))
            raise

    @staticmethod
    def _is_inventory_question(question: str) -> bool:
        lowered = question.casefold()
        return any(token in lowered for token in ("库存", "组合品", "组多少", "缺货", "断货", "可用量", "现货"))

    @staticmethod
    def _is_product_question(question: str) -> bool:
        lowered = question.casefold()
        if AIAnalysisService._is_inventory_question(question):
            return False
        if any(token in lowered for token in ("推广", "投放", "广告", "roi", "投产")) and not any(token in lowered for token in ("单品分析", "商品分析", "商品id", "商品 id", "商品名称", "商品表现", "主销商品", "爆款商品")):
            return False
        return any(token in lowered for token in ("商品", "货品", "单品", "sku", "系列", "主销", "爆款", "商品id", "商品 ID"))

    @staticmethod
    def _has_specific_product_identity(question: str) -> bool:
        """Return true only when a question names a product to look up.

        Generic requests such as “商品明细”“商品结构” must stay on the
        aggregate product workflow.  Searching the catalog with those words
        is both noisy and the source of the old zero-result diagnosis.
        """
        lowered = question.casefold()
        if re.search(r"(?:商品\s*id|item\s*id|货品(?:编码|id)|商品编码|sku(?:编码|id)?)\s*[:：]?\s*[a-z0-9_-]+", lowered, re.IGNORECASE):
            return True
        # Structure questions are not product identities. Without this guard,
        # “下钻客单价下降的系列、类型和商品” was reduced to a catalog search.
        if any(token in lowered for token in ("客单价", "客单", "客价")) and any(
            token in lowered for token in ("系列", "类型", "结构", "下钻", "商品层")
        ):
            return False
        generic_terms = (
            "商品明细", "商品结构", "商品排行", "商品表现", "商品分析", "主销商品",
            "爆款商品", "商品数据", "商品情况", "商品列表", "商品清单", "商品变化",
            "商品贡献", "商品层", "系列", "类型", "客单价", "客单", "客价",
        )
        if any(term in lowered for term in generic_terms):
            # A product name can still be present alongside a generic word.
            # The lookup helper will only be used when the remaining phrase
            # has meaningful identity text.
            cleaned = AIAnalysisService._product_lookup_query(question).get("query", "").strip()
            identity_tokens = tuple(token for token in cleaned.split() if token not in {"下降", "变化", "明细", "数据", "情况", "最近", "当前"})
            return len(identity_tokens) == 1 and len(identity_tokens[0]) >= 3
        cleaned = AIAnalysisService._product_lookup_query(question).get("query", "").strip()
        return len(cleaned) >= 3 and not any(token in cleaned for token in ("下降", "变化", "明细", "数据", "结构", "下钻"))

    @staticmethod
    def _compound_evidence_plan(skill_name: str, question: str, page_context: dict[str, object] | None = None) -> list[tuple[str, dict[str, object]]]:
        """Choose neighbouring evidence domains for model synthesis.

        This is a bounded planner, not a keyword-to-answer template: the
        primary Skill still computes its own diagnosis, while these read-only
        facts expose the store's product, traffic, customer and cost context
        to the model.  The plan deliberately keeps raw data behind MCP.
        """
        _ = question
        page_context = page_context or {}
        page_evidence: dict[str, list[tuple[str, dict[str, object]]]] = {
            "overview": [
                ("products.get_structure_profile", {}),
                ("customer_service.get_diagnosis", {}),
                ("data.query", {"dataset": "traffic_sources", "dimensions": ["source"], "measures": ["visitors", "buyers", "gmv"], "order_by": ["-gmv"], "limit": 100}),
                ("promotions.get_efficiency", {}),
            ],
            "analytics": [
                ("products.get_structure_profile", {}),
                ("data.query", {"dataset": "traffic_sources", "dimensions": ["source"], "measures": ["visitors", "buyers", "gmv"], "order_by": ["-gmv"], "limit": 100}),
                ("data.query", {"dataset": "customers", "dimensions": ["date"], "measures": ["new_paid_buyers", "repeat_buyers"], "order_by": ["date"], "limit": 100}),
            ],
            "traffic": [
                ("data.query", {"dataset": "store_overview", "dimensions": ["date"], "measures": ["gmv", "visitors", "buyers", "payment_conversion_rate"], "order_by": ["date"], "limit": 100}),
                ("products.get_structure_profile", {}),
            ],
            "products": [
                ("products.get_structure_profile", {}),
                ("data.query", {"dataset": "promotion_products", "dimensions": ["product_id", "product_name"], "measures": ["spend", "gmv", "clicks"], "order_by": ["-spend"], "limit": 200}),
                ("pricing.get_current_prices", {"limit": 200}),
                ("pricing.get_risk_items", {"limit": 200}),
                ("activities.get_snapshots", {"limit": 200}),
            ],
            "product-analysis": [
                ("products.get_structure_profile", {}),
                ("data.query", {"dataset": "promotion_products", "dimensions": ["product_id", "product_name"], "measures": ["spend", "gmv", "clicks"], "order_by": ["-spend"], "limit": 200}),
                ("pricing.get_current_prices", {"limit": 200}),
            ],
            "service": [
                ("customer_service.get_diagnosis", {}),
                ("overview.get_store_summary", {}),
                ("products.get_structure_profile", {}),
            ],
            "reviews": [
                ("reviews.get_diagnosis", {}),
                ("products.get_structure_profile", {}),
                ("overview.get_store_summary", {}),
            ],
            "promotions": [
                ("promotions.get_efficiency", {}),
                ("data.compare_periods", {"dataset": "promotion_campaigns", "dimensions": ["scene"], "measures": ["spend", "gmv", "buyers", "clicks", "roi", "direct_roi", "click_conversion_rate"], "order_by": ["-spend"], "limit": 100}),
                ("data.query", {"dataset": "promotion_products", "dimensions": ["product_id", "product_name"], "measures": ["spend", "gmv", "clicks"], "order_by": ["-spend"], "limit": 200}),
            ],
            "customers": [("data.query", {"dataset": "customers", "dimensions": ["date"], "measures": ["new_visitors", "new_paid_buyers", "repeat_buyers"], "order_by": ["date"], "limit": 100}), ("products.get_structure_profile", {})],
            "customer-members": [("data.query", {"dataset": "members", "dimensions": ["date"], "measures": ["gmv", "member_buyers", "new_members"], "order_by": ["date"], "limit": 100}), ("data.query", {"dataset": "member_channels", "dimensions": ["channel"], "measures": ["gmv", "member_buyers", "new_members"], "order_by": ["-gmv"], "limit": 100})],
            "promotions-cps": [
                ("data.query", {"dataset": "cps", "dimensions": ["date"], "measures": ["payment_gmv", "settlement_gmv", "payment_commission", "payment_service_fee", "settlement_expense"], "order_by": ["date"], "limit": 100}),
                ("data.query", {"dataset": "live_talent_reports", "dimensions": ["talent_id", "talent_name"], "measures": ["sessions", "gmv", "buyers", "orders"], "order_by": ["-gmv"], "limit": 200}),
            ],
            "content": [
                ("data.query", {"dataset": "content", "dimensions": ["date"], "measures": ["gmv", "visitors", "buyers", "interactions"], "order_by": ["date"], "limit": 100}),
                ("data.query", {"dataset": "promotion_contents", "dimensions": ["content_id", "content_name", "content_type"], "measures": ["impressions", "clicks", "spend", "gmv", "orders"], "order_by": ["-gmv"], "limit": 200}),
                ("products.get_structure_profile", {}),
            ],
            "live": [
                ("data.query", {"dataset": "live_store_performance", "dimensions": ["date"], "measures": ["viewers", "item_click_users", "buyers", "gmv", "view_click_rate", "click_conversion_rate"], "order_by": ["date"], "limit": 100}),
                ("data.query", {"dataset": "live_talent_reports", "dimensions": ["talent_id", "talent_name"], "measures": ["sessions", "item_click_users", "add_cart_users", "buyers", "gmv", "orders"], "order_by": ["-gmv"], "limit": 200}),
                ("products.get_structure_profile", {}),
            ],
            "market": [("market.get_insights", {"limit": 50}), ("products.get_structure_profile", {})],
            "marketing-activities": [
                ("data.query", {"dataset": "store_activity_calendar_events", "dimensions": ["activity_id", "activity_name", "activity_type", "activity_start", "activity_end", "activity_stage"], "measures": ["event_count"], "limit": 300}),
                ("data.query", {"dataset": "store_overview", "dimensions": ["date"], "measures": ["gmv", "visitors", "buyers", "payment_conversion_rate", "customer_unit_price", "refund_amount"], "order_by": ["date"], "limit": 100}),
                ("products.get_structure_profile", {}),
            ],
            "marketing-flash-sale": [
                ("data.query", {"dataset": "taobao_flash_sale_overviews", "dimensions": ["date"], "measures": ["active_item_level", "item_views", "item_visitors", "orders", "gmv", "new_customers", "conversion_rate"], "order_by": ["date"], "limit": 100}),
                ("data.query", {"dataset": "taobao_flash_sale_items", "dimensions": ["product_id", "product_name", "activity_name", "activity_status"], "measures": ["item_views", "item_visitors", "orders", "gmv", "new_customers", "conversion_rate"], "order_by": ["-gmv"], "limit": 300}),
                ("products.get_structure_profile", {}),
            ],
            "marketing-new-customer": [
                ("data.query", {"dataset": "new_customer_discount", "dimensions": ["date"], "measures": ["shop_visitors", "product_new_visitors", "buyers", "gmv", "buyer_share", "gmv_share", "conversion_rate", "store_new_buyers", "store_new_gmv"], "order_by": ["date"], "limit": 100}),
                ("data.query", {"dataset": "customers", "dimensions": ["date"], "measures": ["new_paid_buyers", "repeat_buyers", "no_purchase_buyers"], "order_by": ["date"], "limit": 100}),
                ("products.get_structure_profile", {}),
            ],
            "marketing-shopping-gold": [
                ("data.query", {"dataset": "shopping_gold", "dimensions": ["date"], "measures": ["recharge_amount", "recharge_buyers", "recharge_refund_amount", "paid_amount", "paid_buyers", "customer_unit_price", "recharge_rate"], "order_by": ["date"], "limit": 100}),
                ("data.query", {"dataset": "store_overview", "dimensions": ["date"], "measures": ["gmv", "buyers", "refund_amount"], "order_by": ["date"], "limit": 100}),
            ],
            "marketing-bybt": [
                ("data.query", {"dataset": "bybt", "dimensions": ["date"], "measures": ["gmv", "buyers"], "order_by": ["date"], "limit": 100}),
                ("data.query", {"dataset": "bybt_items", "dimensions": ["product_id", "product_name", "category", "business_scene", "sales_mode"], "measures": ["gmv", "paid_items", "orders", "visitors", "conversion_rate"], "order_by": ["-gmv"], "limit": 300}),
                ("products.get_structure_profile", {}),
            ],
            "inventory": [
                ("data.query", {"dataset": "inventory_catalog", "dimensions": ["series", "specification", "size", "goods_no", "display_name"], "measures": ["sku_count", "pieces"], "limit": 500}),
                ("data.query", {"dataset": "inventory_snapshots", "dimensions": ["business_day", "warehouse_name", "goods_no", "sku_no", "goods_name", "sku_name"], "measures": ["available_quantity", "stock_quantity"], "limit": 500}),
                ("products.get_structure_profile", {}),
            ],
            "brand-assets": [
                ("overview.get_store_summary", {}),
                ("products.get_structure_profile", {}),
                ("brand_assets.get_diagnosis", {}),
            ],
        }
        page_key = str(page_context.get("page_key") or page_context.get("page") or "")
        selected = page_evidence.get(page_key, [])
        if selected:
            return selected
        common_product = {
            "tool": "products.get_structure_profile",
            "args": {},
        }
        if skill_name == "shop-overview-diagnosis":
            return [
                (common_product["tool"], common_product["args"]),
                ("data.query", {"dataset": "traffic_sources", "dimensions": ["source"], "measures": ["visitors", "new_visitors", "buyers", "gmv", "add_cart_users", "favorite_users"], "order_by": ["-gmv"], "limit": 100}),
                ("data.compare_periods", {"dataset": "traffic_sources", "dimensions": ["source"], "measures": ["visitors", "buyers", "gmv", "add_cart_users", "favorite_users"], "order_by": ["-gmv"], "limit": 100}),
                ("promotions.get_efficiency", {}),
                ("data.compare_periods", {"dataset": "promotion_campaigns", "dimensions": ["scene"], "measures": ["spend", "gmv", "buyers", "clicks", "roi", "direct_roi", "click_conversion_rate"], "order_by": ["-spend"], "limit": 100}),
                ("customer_service.get_diagnosis", {}),
                ("data.query", {"dataset": "customers", "dimensions": ["date"], "measures": ["new_visitors", "new_paid_buyers", "no_purchase_buyers", "repeat_buyers"], "order_by": ["date"], "limit": 100}),
                ("data.query", {"dataset": "members", "dimensions": ["date"], "measures": ["gmv", "member_buyers", "new_members"], "order_by": ["date"], "limit": 100}),
                ("data.query", {"dataset": "live", "dimensions": ["date"], "measures": ["gmv", "shop_gmv", "visitors"], "order_by": ["date"], "limit": 100}),
                ("data.query", {"dataset": "cps", "dimensions": ["date"], "measures": ["payment_gmv", "settlement_gmv", "payment_commission", "payment_service_fee", "settlement_expense"], "order_by": ["date"], "limit": 100}),
                ("data.query", {"dataset": "promotion_products", "dimensions": ["product_id", "product_name"], "measures": ["spend", "gmv", "clicks"], "order_by": ["-spend"], "limit": 100}),
                ("reviews.get_diagnosis", {}),
                ("data.query", {"dataset": "store_activity_calendar_events", "dimensions": ["activity_id", "activity_name", "activity_type", "activity_start", "activity_end", "activity_stage"], "measures": ["event_count"], "limit": 300}),
                ("data.query", {"dataset": "taobao_flash_sale_overviews", "dimensions": ["date"], "measures": ["active_item_level", "item_views", "item_visitors", "orders", "gmv", "new_customers", "conversion_rate"], "order_by": ["date"], "limit": 100}),
                ("data.query", {"dataset": "new_customer_discount", "dimensions": ["date"], "measures": ["shop_visitors", "product_new_visitors", "buyers", "gmv", "buyer_share", "gmv_share", "conversion_rate", "store_new_buyers", "store_new_gmv"], "order_by": ["date"], "limit": 100}),
                ("data.query", {"dataset": "promotion_contents", "dimensions": ["content_id", "content_name", "content_type"], "measures": ["impressions", "clicks", "spend", "gmv", "orders"], "order_by": ["-gmv"], "limit": 200}),
                ("data.query", {"dataset": "inventory_snapshots", "dimensions": ["business_day", "warehouse_name", "goods_no", "sku_no", "goods_name", "sku_name"], "measures": ["available_quantity", "stock_quantity"], "limit": 500}),
                ("brand_assets.get_diagnosis", {}),
            ]
        if skill_name == "customer-service-diagnosis":
            return [
                ("overview.get_store_summary", {}),
                ("overview.get_metric_trend", {}),
                ("data.compare_periods", {"dataset": "store_overview", "measures": ["gmv", "visitors", "buyers", "payment_conversion_rate", "customer_unit_price", "refund_amount"]}),
                (common_product["tool"], common_product["args"]),
                ("data.query", {"dataset": "products", "dimensions": ["product_id", "product_name"], "measures": ["gmv", "buyers", "visitors", "refund_amount"], "order_by": ["-gmv"], "limit": 100}),
            ]
        if skill_name == "promotion-roi":
            return [
                ("data.compare_periods", {"dataset": "promotion_campaigns", "dimensions": ["scene"], "measures": ["spend", "gmv", "buyers", "clicks", "roi", "direct_roi", "click_conversion_rate"], "order_by": ["-spend"], "limit": 100}),
                ("data.query", {"dataset": "promotion_products", "dimensions": ["product_id", "product_name"], "measures": ["spend", "gmv", "clicks"], "order_by": ["-spend"], "limit": 200}),
            ]
        if skill_name == "product-structure-diagnosis":
            return [
                ("data.query", {"dataset": "product_catalog", "dimensions": ["product_id", "product_name", "product_type", "series", "positioning", "channel"], "limit": 1000}),
                ("data.query", {"dataset": "promotion_products", "dimensions": ["product_id", "product_name"], "measures": ["spend", "gmv", "clicks"], "order_by": ["-spend"], "limit": 200}),
                ("pricing.get_current_prices", {"limit": 200}),
                ("pricing.get_risk_items", {"limit": 200}),
                ("activities.get_snapshots", {"limit": 200}),
            ]
        if skill_name == "product-diagnosis":
            return [
                ("data.query", {"dataset": "product_catalog", "dimensions": ["product_id", "product_name", "product_type", "series", "positioning", "channel"], "limit": 1000}),
                ("data.query", {"dataset": "promotion_products", "dimensions": ["product_id", "product_name"], "measures": ["spend", "gmv", "clicks"], "order_by": ["-spend"], "limit": 200}),
            ]
        return []

    @staticmethod
    def _product_lookup_query(question: str) -> dict[str, str]:
        import re
        text = question.strip()
        id_match = re.search(r"(?:商品\s*id|item\s*id|货品编码|商品编码)\s*[:：]?\s*([A-Za-z0-9_-]+)", text, re.IGNORECASE)
        if id_match:
            return {"product_id": id_match.group(1)}
        # Keep the complete phrase for name search; the catalog endpoint does
        # a parameterized LIKE and returns candidates when the phrase is not
        # unique, so the agent never invents a product identity.
        positioning = next((token for token in ("正装", "mini装", "MINI装", "试用装") if token.casefold() in text.casefold()), None)
        product_type = next((token for token in ("纸尿裤", "拉拉裤", "湿巾", "湿纸巾") if token in text), None)
        cleaned = re.sub(r"(分析|诊断|表现|怎么样|如何|的|这个|这款|该商品|商品|单品|货品|sku|sku编码|商品id|商品 ID|主销|爆款|最近|当前|正装|mini装|MINI装|试用装|纸尿裤|拉拉裤|湿巾|湿纸巾|系列|类型)", " ", text, flags=re.IGNORECASE)
        cleaned = re.sub(r"[：:，,。！？?]+", " ", cleaned).strip()
        result: dict[str, str] = {"query": cleaned or text}
        # In phrases such as “大鱼海棠正装系列”，the cleaned brand/series
        # phrase is a dimension value, not an arbitrary full-text query.
        # Passing it as series prevents unrelated products whose title merely
        # contains the phrase from being mixed into the series diagnosis.
        if "系列" in text and cleaned:
            result["series"] = cleaned
        if positioning:
            result["positioning"] = "正装" if positioning.casefold() == "正装" else "试用装" if positioning.casefold() == "试用装" else "MINI装"
        if product_type:
            result["product_type"] = product_type
        return result

    @staticmethod
    def _product_profile_diagnosis(results: list[MCPEnvelope]) -> Diagnosis:
        search = next((item for item in results if item.tool == "products.search"), None)
        profile_result = next((item for item in results if item.tool in {"products.get_profile", "products.get_series_profile"}), None)
        candidates = (search.data.get("rows") if search else None) or []
        if not profile_result:
            names = "、".join(str(item.get("product_name") or item.get("product_id")) for item in candidates[:5])
            detail = f"找到 {len(candidates)} 个商品候选：{names}。请补充商品 ID 或更完整名称后再读取画像。" if candidates else "没有匹配到商品主档，请使用商品名称或商品 ID 重新查询。"
            return Diagnosis(
                headline="商品候选需要确认",
                summary=detail,
                findings=[DiagnosisFinding(level="warning", title="商品身份未唯一确认", detail=detail)],
                actions=[RecommendedAction(priority="P0", title="确认商品身份", detail="优先提供商品 ID；若按名称命中多个候选，请选择具体商品后再分析。", owner="商品运营", validation="商品搜索返回唯一商品 ID")],
                artifacts=[ArtifactSpec(type="matrix", title="商品候选", rows=candidates[:20])],
            )
        data = profile_result.data or {}
        if profile_result.tool == "products.get_series_profile":
            sales = data.get("sales") or {}
            series = data.get("series") or "指定系列"
            positioning = data.get("positioning")
            scope = f"系列 {series}" + (f" · {positioning}" if positioning else "")
            detail_rows = data.get("products") or []
            findings = [DiagnosisFinding(level="info", title=f"已读取{scope}画像", detail=f"覆盖 {int(data.get('product_count') or 0)} 个商品，近 30 天支付金额 {float(sales.get('paid_amount') or 0):,.0f}，支付买家 {int(sales.get('buyers') or 0):,}。", metric_ids=["paid_amount", "buyers"])]
            conversion = sales.get("conversion_rate")
            if conversion is not None:
                findings.append(DiagnosisFinding(level="info", title="系列承接指标已计算", detail=f"系列访客 {int(sales.get('visitors') or 0):,}，支付转化率 {float(conversion):.2f}%，推广花费 {float(sales.get('promotion_spend') or 0):,.0f}。", metric_ids=["visitors", "conversion_rate", "promotion_spend"]))
            weakest = sorted([item for item in detail_rows if item.get("conversion_rate") is not None], key=lambda item: float(item.get("conversion_rate") or 0))[:3]
            actions = [RecommendedAction(priority="P1", title="按商品明细复盘系列结构", detail="优先检查系列内低转化商品的价格、库存、详情和评价，再决定系列层面的投放或活动动作。", owner="商品运营", validation="系列支付转化率提升且低转化商品占比下降")]
            if weakest:
                sample = "、".join(str(item.get("product_name") or item.get("product_id")) for item in weakest)
                findings.append(DiagnosisFinding(level="warning", title="系列内存在低转化商品", detail=f"低转化商品：{sample}。先做商品级承接排查，不把系列均值直接归因给所有 SKU。", metric_ids=["conversion_rate"]))
                actions.insert(0, RecommendedAction(priority="P0", title="下钻系列内低转化商品", detail="按商品 ID 逐个核对库存、价格、评价和推广依赖度。", owner="商品运营", validation="低转化商品支付转化率提升"))
            table = [{"商品ID": item.get("product_id"), "商品": item.get("product_name"), "类型": item.get("product_type"), "定位": item.get("positioning"), "支付金额": item.get("paid_amount"), "访客": item.get("visitors"), "支付买家": item.get("buyers"), "转化率%": item.get("conversion_rate"), "推广花费": item.get("promotion_spend"), "推广ROI": item.get("promotion_roi")} for item in detail_rows]
            return Diagnosis(headline=findings[0].title, summary=findings[0].detail, findings=findings, actions=actions, artifacts=[ArtifactSpec(type="matrix", title="系列商品明细", rows=table)], assumptions=["系列口径：商品主档中的系列字段；类型/定位按商品主档筛选。"], denominator_notes=["系列转化率 = 系列支付买家 ÷ 系列商品访客；推广 ROI = 商品归因成交 ÷ 商品推广花费。"], causal_boundary="推广成交为平台归因贡献，不代表因果增量。")
        product = data.get("product") or {}
        sales = data.get("sales") or {}
        last_7 = sales.get("last_7_days") or {}
        last_30 = sales.get("last_30_days") or {}
        promo = data.get("promotion") or {}
        name = product.get("product_name") or product.get("product_id") or "指定商品"
        findings = [DiagnosisFinding(level="info", title=f"已读取{name}商品画像", detail=f"系列 {product.get('series') or '未归类'}，类型 {product.get('product_type') or '未归类'}；近 30 天支付金额 {float(last_30.get('paid_amount') or 0):,.0f}，支付买家 {int(last_30.get('buyers') or 0):,}。", metric_ids=["paid_amount", "buyers"])]
        actions: list[RecommendedAction] = []
        visitors = float(last_30.get("visitors") or 0)
        buyers = float(last_30.get("buyers") or 0)
        conversion = buyers / visitors * 100 if visitors else None
        if conversion is not None:
            findings.append(DiagnosisFinding(level="info", title="商品承接指标已计算", detail=f"近 30 天访客 {int(visitors):,}，支付转化率 {conversion:.2f}%；近 7 天支付金额 {float(last_7.get('paid_amount') or 0):,.0f}。", metric_ids=["visitors", "conversion_rate"]))
            if conversion < 3:
                actions.append(RecommendedAction(priority="P0", title="优先复查商品承接", detail="结合价格、库存、详情首屏、评价和退款原因判断低转化来源，不先扩大投放。", owner="商品运营", validation="商品转化率提升且退款率不恶化"))
        if promo.get("roi") is not None:
            roi = float(promo.get("roi") or 0)
            findings.append(DiagnosisFinding(level="warning" if roi < 1.5 else "positive", title="商品推广归因已纳入", detail=f"近 30 天商品推广花费 {float(promo.get('spend') or 0):,.0f}，归因成交 {float(promo.get('attributed_gmv') or 0):,.0f}，ROI {roi:.2f}。", metric_ids=["promotion_roi"]))
            if roi < 1.5:
                actions.append(RecommendedAction(priority="P0", title="下钻商品推广计划", detail="按计划、单元、关键词和人群拆解商品推广花费，确认归因窗口后再降预算。", owner="投放运营", validation="商品推广 ROI 达到目标线"))
        price = data.get("current_price")
        risk = data.get("price_risk")
        if risk:
            findings.append(DiagnosisFinding(level="warning", title="商品存在价格风险记录", detail=f"当前价格风险信息已命中，风险标签：{risk.get('风险标签') or risk.get('risk_tag') or '请查看明细'}。"))
            actions.append(RecommendedAction(priority="P0", title="复核商品价格风险", detail="对照当前价、风险下限和活动促销详情，确认活动价不会触发平台红线。", owner="商品运营", validation="价格风险状态解除或已确认可接受"))
        rows = [{"周期": key, **value} for key, value in sales.items() if isinstance(value, dict)]
        return Diagnosis(headline=f"{name}商品画像已完成", summary=f"已按商品 ID {product.get('product_id') or '--'} 汇总主档、销售、推广和价格风险证据。", findings=findings, actions=actions, artifacts=[ArtifactSpec(type="matrix", title="商品周期经营", rows=rows), ArtifactSpec(type="matrix", title="商品主档", rows=[product])], assumptions=["商品推广成交为平台归因，不等于因果增量。"])

    def _workflow_dates(self, request: AnalysisRequest, skill_name: str, store_id: int | None):
        if skill_name not in {"promotion-budget-planning", "campaign-planning"}:
            return request.start_date, request.end_date
        _minimum, maximum = self.mcp.analytics._source_for_store(store_id).get_date_bounds()
        if request.start_date is None and request.end_date is None:
            # Forward-looking planning should use a recent operating baseline,
            # not the entire warehouse history.  The latter often contains
            # long periods before a dataset was onboarded and makes coverage
            # warnings look like business risk.  Thirty business days is a
            # stable default while explicit dates still win.
            from datetime import timedelta

            return max(_minimum, maximum - timedelta(days=29)), maximum
        if (request.start_date and request.start_date > maximum) or (request.end_date and request.end_date > maximum):
            return None, None
        return request.start_date, request.end_date

    @staticmethod
    def _inventory_business_day(question: str):
        import re
        from datetime import date

        match = re.search(r"(?<!\d)(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})日?", question)
        if not match:
            return None
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))

    @classmethod
    def _planning_inputs(cls, request: AnalysisRequest) -> dict[str, object]:
        question = request.question
        values: dict[str, object] = {}

        total_budget = cls._extract_amount(question, r"总预算|投放预算|推广预算|活动预算|预算")
        target_gmv = cls._extract_amount(question, r"目标\s*GMV|GMV\s*目标|销售目标|成交目标|目标销售额")
        target_uv = cls._extract_amount(question, r"目标\s*UV|UV\s*目标|访客目标|目标访客")
        target_atv = cls._extract_amount(question, r"目标\s*ATV|ATV\s*目标|客单价目标|目标客单价")
        target_roi = cls._extract_number(question, r"目标\s*ROI|ROI\s*目标|目标投产|投产目标")
        target_cvr = cls._extract_percent(question, r"目标\s*CVR|CVR\s*目标|转化率目标|目标转化率")
        margin_rate = cls._extract_percent(question, r"毛利率|目标毛利率")

        if total_budget is not None: values["total_budget"] = total_budget
        if target_gmv is not None: values["target_gmv"] = target_gmv
        if target_uv is not None: values["target_uv"] = target_uv
        if target_atv is not None: values["target_atv"] = target_atv
        if target_roi is not None: values["target_roi"] = target_roi
        if target_cvr is not None: values["target_cvr"] = target_cvr
        if margin_rate is not None: values["margin_rate"] = margin_rate
        if request.start_date is not None: values["period_start"] = request.start_date.isoformat()
        if request.end_date is not None: values["period_end"] = request.end_date.isoformat()
        for token in ("618", "双11", "双十一", "会员日", "上新", "年货节"):
            if token in question:
                values["event"] = token
                break
        return values

    @staticmethod
    def _extract_number(text: str, label_pattern: str) -> float | None:
        match = re.search(rf"(?:{label_pattern})\s*(?:为|是|[:：=])?\s*([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
        return float(match.group(1)) if match else None

    @classmethod
    def _extract_percent(cls, text: str, label_pattern: str) -> float | None:
        value = cls._extract_number(text, label_pattern)
        return value / 100 if value is not None else None

    @staticmethod
    def _extract_amount(text: str, label_pattern: str) -> float | None:
        match = re.search(rf"(?:{label_pattern})\s*(?:为|是|[:：=])?\s*([0-9]+(?:\.[0-9]+)?)\s*(亿|万|千|元|w|k)?", text, re.IGNORECASE)
        if not match:
            return None
        value = float(match.group(1))
        unit = (match.group(2) or "元").lower()
        multiplier = {"亿": 100_000_000, "万": 10_000, "w": 10_000, "千": 1_000, "k": 1_000, "元": 1}[unit]
        return value * multiplier

    @staticmethod
    def _inventory_item_group(item: dict) -> str:
        name = " ".join(str(item.get(key) or "") for key in ("goods_name", "sku_name", "display_name", "goods_no")).lower()
        if any(token in name for token in ("纸箱", "包袋", "半成品")) or name.strip().endswith("纸箱"):
            return "packaging"
        if any(token in name for token in ("试用", "白片", "单片", "便携", "旅行", "尝鲜", "卷膜")):
            return "sample"
        pieces = item.get("pieces")
        if pieces is not None:
            try:
                if float(pieces) <= 10:
                    return "sample"
            except (TypeError, ValueError):
                pass
        if any(token in name for token in ("礼盒", "专供", "量贩", "加量", "优享", "加赠", "彩箱", "*")):
            return "bundle"
        return "regular"

    @classmethod
    def _inventory_summary_diagnosis(cls, result: MCPEnvelope, items: list[dict]) -> Diagnosis:
        labels = {
            "regular": "常规销售装",
            "sample": "试用/便携装",
            "bundle": "组合/渠道装",
            "packaging": "包装/半成品",
        }
        grouped: dict[str, dict[str, float]] = {
            key: {"item_count": 0, "available_count": 0, "zero_stock_count": 0, "available_quantity": 0}
            for key in labels
        }
        all_rows: list[dict] = []
        for item in items:
            group = cls._inventory_item_group(item)
            is_package = item.get("item_type") == "package"
            quantity = item.get("assemblable_quantity") if is_package else item.get("available_quantity")
            quantity_value = float(quantity or 0)
            status = "组合关系" if is_package else "零库存" if quantity_value <= 0 else "少量（≤100）" if quantity_value <= 100 else "有库存"
            bucket = grouped[group]
            bucket["item_count"] += 1
            if quantity_value <= 0:
                bucket["zero_stock_count"] += 1
            else:
                bucket["available_count"] += 1
                bucket["available_quantity"] += quantity_value
            all_rows.append({
                "货品分组": labels[group],
                "库存状态": status,
                "商品": item.get("goods_name") or item.get("display_name") or item.get("goods_no") or "未命名商品",
                "规格": item.get("specification") or "--",
                "尺码": item.get("size") or "--",
                "货品编码": item.get("goods_no") or "--",
                "SKU编码": item.get("sku_no") or item.get("sku_id") or "--",
                "可用库存": "查看组成 SKU" if is_package else quantity,
            })
        order = {"regular": 0, "bundle": 1, "sample": 2, "packaging": 3}
        status_order = {"零库存": 0, "少量（≤100）": 1, "组合关系": 2, "有库存": 3}
        all_rows.sort(key=lambda row: (order.get(next((key for key, label in labels.items() if label == row["货品分组"]), "regular"), 9), status_order.get(row["库存状态"], 9), str(row["商品"])))
        risk_rows = [row for row in all_rows if row["货品分组"] != labels["packaging"] and row["库存状态"] in {"零库存", "少量（≤100）"}][:30]
        result.data["decision_summary"] = {
            "matched_count": len(items),
            "available_sku_count": sum(1 for item in items if float((item.get("assemblable_quantity") if item.get("item_type") == "package" else item.get("available_quantity")) or 0) > 0),
            "zero_stock_sku_count": sum(1 for item in items if float((item.get("assemblable_quantity") if item.get("item_type") == "package" else item.get("available_quantity")) or 0) <= 0),
            "low_stock_sku_count": sum(1 for item in items if 0 < float((item.get("assemblable_quantity") if item.get("item_type") == "package" else item.get("available_quantity")) or 0) <= 100),
            "available_quantity_total": sum(float((item.get("assemblable_quantity") if item.get("item_type") == "package" else item.get("available_quantity")) or 0) for item in items),
            "groups": [{"key": key, "label": labels[key], **{name: int(value) if name != "available_quantity" else value for name, value in bucket.items()}} for key, bucket in grouped.items() if bucket["item_count"]],
            "snapshot_age_minutes": result.data.get("snapshot_age_minutes"),
            "freshness_status": result.data.get("freshness_status", "unknown"),
        }
        summary = result.data["decision_summary"]
        regular = grouped["regular"]
        headline = f"已匹配 {len(items)} 个库存条目：常规销售装 {int(regular['item_count'])} 个，其中 {int(regular['zero_stock_count'])} 个零库存"
        if result.data.get("freshness_status") == "stale":
            headline += "；快照已过期"
        findings = [
            DiagnosisFinding(level="warning" if regular["zero_stock_count"] else "positive", title="常规销售装可售情况", detail=f"常规销售装 {int(regular['item_count'])} 个：{int(regular['available_count'])} 个有库存、{int(regular['zero_stock_count'])} 个零库存；另有 {int(regular['item_count'] - regular['available_count'] - regular['zero_stock_count'])} 个组合关系或未直接计量。"),
            DiagnosisFinding(level="info", title="库存结构已分组", detail="；".join(f"{labels[key]} {int(bucket['item_count'])} 个，零库存 {int(bucket['zero_stock_count'])} 个" for key, bucket in grouped.items() if bucket["item_count"] and key != "regular") or "未发现试用、组合或包装条目。"),
        ]
        if result.data.get("freshness_status") == "stale":
            findings.append(DiagnosisFinding(level="warning", title="库存快照已过期", detail=f"快照约 {result.data.get('snapshot_age_minutes') or '--'} 分钟前采集，补货或缺货判断前应先同步。"))
        actions = []
        if result.data.get("freshness_status") == "stale":
            actions.append(RecommendedAction(priority="P0", title="先同步库存快照", detail="当前快照超过 1 小时，先完成同步，再确认零库存条目是否真实缺货。", owner="数据运营", validation="快照时效不超过 60 分钟"))
        if regular["zero_stock_count"]:
            actions.append(RecommendedAction(priority="P1", title="核对常规销售装零库存", detail=f"优先核对 {int(regular['zero_stock_count'])} 个常规销售装的在途、上下架和近 7 天销量；包装/半成品零库存不直接算销售缺货。", owner="商品运营", validation="常规销售装零库存数量下降且可售状态恢复"))
        if summary["low_stock_sku_count"]:
            actions.append(RecommendedAction(priority="P2", title="复核少量库存", detail=f"有 {summary['low_stock_sku_count']} 个条目可用库存不超过 100，仅作少量筛查，未计算库存覆盖天数。", owner="商品运营", validation="结合销量和在途确认补货量"))
        if not actions:
            actions.append(RecommendedAction(priority="P1", title="继续监控库存变化", detail="当前匹配条目未发现常规销售装零库存，结合销量速度和在途安排补货。", owner="商品运营", validation="常规销售装零库存保持为 0"))
        freshness = result.data.get("freshness_status")
        assumptions = ["本次只判断快照中的可用库存；未提供销量速度和在途，不计算库存覆盖天数或补货量。"]
        if freshness == "stale":
            assumptions.append("库存快照已过期，当前结论仅供排查，不作为最终补货依据。")
        return Diagnosis(
            headline=headline,
            summary=f"可用库存合计 {summary['available_quantity_total']:,.0f}；有库存 {summary['available_sku_count']} 个，零库存 {summary['zero_stock_sku_count']} 个，少量筛查 {summary['low_stock_sku_count']} 个。包装/半成品和试用装已单独分组。",
            findings=findings[:3],
            actions=actions[:3],
            artifacts=[ArtifactSpec(type="metric_table", title="库存风险清单", rows=risk_rows), ArtifactSpec(type="metric_table", title="全部匹配库存", rows=all_rows)],
            assumptions=assumptions,
            next_questions=["只看大鱼 M 码常规销售装", "只看零库存的可售 SKU", "同步库存后重新查询"],
        )

    @staticmethod
    def _inventory_diagnosis(result: MCPEnvelope) -> Diagnosis:
        items = result.data.get("items", [])
        if not items:
            reason = result.data.get("reason")
            if reason in {"no_stockouts", "stockout_scope_partial"}:
                scope = result.data.get("scope") or {}
                label = scope.get("label") or "所选商品范围"
                checked_count = int(scope.get("checked_sku_count") or 0)
                unmatched_count = int(scope.get("unmatched_sku_count") or 0)
                snapshot_day = result.data.get("business_day") or "--"
                checked_items = result.data.get("checked_items") or []
                rows = [{
                    "系列": item.get("series") or "未归类",
                    "类型": item.get("specification") or "--",
                    "尺码": item.get("size") or "--",
                    "货品编码": item.get("goods_no") or "--",
                    "可用库存": item.get("available_quantity"),
                    "库存业务日": item.get("business_day") or snapshot_day,
                } for item in checked_items]
                if reason == "stockout_scope_partial":
                    headline = f"{label}库存范围未完全匹配"
                    summary = f"已核对 {checked_count} 个 SKU，暂未发现真实 0 库存；另有 {unmatched_count} 个目录 SKU 未匹配快照，不能判定为缺货。"
                    finding_level = "warning"
                    action = RecommendedAction(
                        priority="P0",
                        title="补齐未匹配 SKU",
                        detail="先核对目录货品编码与吉客云返回编码，再重新判断缺货尺码。",
                        owner="数据运营",
                        validation="所选范围未匹配 SKU 数量为 0",
                    )
                else:
                    headline = f"{label}当前没有缺货尺码"
                    summary = f"库存业务日 {snapshot_day}，共核对 {checked_count} 个 SKU，未发现可用库存为 0 的尺码。"
                    finding_level = "positive"
                    action = RecommendedAction(
                        priority="P1",
                        title="继续关注低库存尺码",
                        detail="按最新库存快照监控可用库存接近安全线的尺码，并结合近 7 天销量安排补货。",
                        owner="商品运营",
                        validation="缺货尺码数保持为 0",
                    )
                return Diagnosis(
                    headline=headline,
                    summary=summary,
                    findings=[DiagnosisFinding(level=finding_level, title="缺货尺码核对结果", detail=summary)],
                    actions=[action],
                    artifacts=[ArtifactSpec(type="metric_table", title="已核对尺码", rows=rows)],
                    assumptions=["缺货定义：最新快照各仓可用库存合计为 0。", "目录未匹配快照的 SKU 不按 0 库存处理。"],
                )
            messages = {
                "not_configured": ("吉客云库存尚未配置", "请先配置吉客云库存接口和 Token，当前不能判断库存是否为 0。", "配置吉客云接口与 Token 后执行一次库存同步。"),
                "not_collected": ("尚未采集库存快照", "吉客云配置已存在，但没有成功写入库存快照，当前不能判断库存是否为 0。", "检查同步状态并手动执行一次库存同步。"),
                "date_not_available": ("指定日期没有库存快照", "该日期没有库存时点数据，不能用经营区间数据替代。", "改查最新库存快照，或补采指定日期库存。"),
                "sku_not_matched": ("商品已匹配但尺码未匹配", "已找到同商品记录，但没有找到问题中的尺码或 SKU。", "核对尺码名称、SKU 编码或条码。"),
                "code_known_no_snapshot": ("货品编码已识别但快照未命中", "编码在货品映射中存在，但当前库存快照没有对应记录；不能把未返回当成库存为 0。", "先确认该货品是否应出现在吉客云库存接口，再补采当前库存快照。"),
                "product_not_matched": ("没有匹配到库存商品", "当前快照没有找到对应商品，请确认商品编码、名称或条码。", "优先使用商品编码、SKU 编码或条码重新查询。"),
            }
            headline, summary, action_detail = messages.get(reason, messages["product_not_matched"])
            freshness = result.data.get("freshness_status")
            if freshness == "stale":
                summary += "当前快照已超过 1 小时，建议先同步后再判断。"
            return Diagnosis(
                headline=headline,
                summary=summary,
                findings=[DiagnosisFinding(level="warning", title="库存数据状态", detail=summary)],
                actions=[RecommendedAction(priority="P0", title="处理库存数据状态", detail=action_detail, owner="数据运营", validation="库存同步状态为 success 且快照时效不超过 60 分钟")],
                assumptions=[f"查询词：{'、'.join(result.data.get('query_terms') or [result.data.get('query') or ''])}"],
            )
        if len(items) > 1 and result.data.get("reason") not in {"stockouts_found", "stockout_scope_partial"} and not result.data.get("ambiguous"):
            return AIAnalysisService._inventory_summary_diagnosis(result, items)
        stockout_scope = result.data.get("reason") == "stockouts_found"
        partial_scope = result.data.get("reason") == "stockout_scope_partial"
        rows = []
        findings = []
        series_groups: dict[str, dict[str, list[dict]]] = {}
        for item in items:
            name = item.get("goods_name") or item.get("goods_no") or item.get("sku_barcode") or "未命名商品"
            is_package = item.get("item_type") == "package"
            quantity = item.get("assemblable_quantity") if is_package else item.get("available_quantity")
            label = "组合关系" if is_package else "可用库存"
            rows.append({
                "系列": item.get("series") or "未归类",
                "类型": item.get("specification") or "--",
                "尺码": item.get("size") or "--",
                "货品编码": item.get("goods_no") or "--",
                "片数": item.get("pieces") if item.get("pieces") is not None else "--",
                "可用库存": "不计算（查看组成 SKU）" if is_package else quantity,
                "商品": name,
                "SKU编码": item.get("sku_no") or item.get("sku_id") or "--",
                "库存业务日": item.get("business_day"),
                "匹配依据": "、".join(item.get("matched_by") or []) or "--",
            })
            if stockout_scope or partial_scope:
                series = str(item.get("series") or "未归类")
                series_groups.setdefault(series, {}).setdefault(str(item.get("specification") or "其他"), []).append(item)
            if is_package:
                level = "info"
                detail = f"已找到组合货品关系，包含 {len(item.get('components') or [])} 个组成 SKU；库存需查看组成 SKU。"
            else:
                level = "critical" if float(quantity or 0) <= 0 else "warning" if float(quantity or 0) <= 10 else "info"
                detail = f"{label} {float(quantity or 0):g}。"
            if item.get("match_type") == "exact_code":
                detail += f"按货品编码精确命中（{'、'.join(item.get('matched_by') or [])}）。"
            # Broad stockout scopes are summarized by series below; ordinary
            # SKU lookups retain the item-level finding.
            if not (stockout_scope or partial_scope):
                findings.append(DiagnosisFinding(level=level, title=f"{name}库存结果", detail=detail))
        first = items[0]
        first_name = first.get("goods_name") or first.get("goods_no") or "库存商品"
        snapshot_at = result.data.get("latest_snapshot_at")
        snapshot_display = str(snapshot_at or "").replace("T", " ").split("+")[0].split("Z")[0] or "--"
        ambiguous = bool(result.data.get("ambiguous"))
        scope = result.data.get("scope") or {}
        if stockout_scope or partial_scope:
            for series, specifications in series_groups.items():
                details = []
                for specification, specification_items in specifications.items():
                    sku_details = []
                    for item in specification_items:
                        size = item.get("size") or "--"
                        pieces = f"/{item.get('pieces')}片" if item.get("pieces") is not None else ""
                        sku_details.append(f"{size}{pieces}（{item.get('goods_no') or '--'}）")
                    details.append(f"{specification}：" + "、".join(sku_details))
                findings.append(DiagnosisFinding(
                    level="critical",
                    title=f"{series}系列缺货 {sum(len(values) for values in specifications.values())} 个 SKU",
                    detail="；".join(details),
                ))
        headline = (
            f"{scope.get('label') or '所选商品范围'}有 {len(items)} 个缺货 SKU，涉及 {len(series_groups)} 个系列"
            + (f"，另有 {int(scope.get('unmatched_sku_count') or 0)} 个 SKU 未匹配" if partial_scope else "")
            if stockout_scope else
            f"{scope.get('label') or '所选商品范围'}有 {len(items)} 个缺货 SKU（范围部分未匹配）"
            if partial_scope else
            f"编码对应 {len(items)} 个库存候选，请确认货品"
            if ambiguous else
            f"已查询到 {len(items)} 个库存商品"
        )
        summary = f"{first_name}：" + (f"已同步组合关系，共 {len(first.get('components') or [])} 个组成 SKU；不计算组合库存。" if first.get("item_type") == "package" else f"可用库存 {first.get('available_quantity')}。")
        if stockout_scope:
            series_counts = "、".join(f"{series} {sum(len(values) for values in specifications.values())}个" for series, specifications in series_groups.items())
            summary = f"共 {len(items)} 个缺货 SKU，涉及 {len(series_groups)} 个系列：{series_counts}。详情按系列列出尺码和货品编码。"
        if partial_scope:
            series_counts = "、".join(f"{series} {sum(len(values) for values in specifications.values())}个" for series, specifications in series_groups.items())
            summary = f"已发现 {len(items)} 个真实缺货 SKU，涉及 {len(series_groups)} 个系列：{series_counts}。"
            summary += f"另有 {int(scope.get('unmatched_sku_count') or 0)} 个目录 SKU 未匹配最新库存快照，不能据此判定库存。"
        if snapshot_at:
            summary += f"库存业务日 {first.get('business_day') or result.data.get('business_day')}，快照采集于 {snapshot_display}。"
        if ambiguous:
            summary += "同一编码返回多个货品候选，已保留规格、尺码和 SKU 字段供确认。"
        actions = [RecommendedAction(
            priority="P0" if (stockout_scope or partial_scope) else "P1",
            title="优先补齐缺货规格" if (stockout_scope or partial_scope) else "关注低库存商品",
            detail="按缺货尺码核对在途和补货计划，恢复可售后复查库存快照。" if (stockout_scope or partial_scope) else "对普通 SKU 可用库存接近零的商品设置预警，并结合近 7 天销量决定补货量；组合货品请回看组成 SKU。",
            owner="商品运营" if (stockout_scope or partial_scope) else "运营",
            validation="缺货规格可用库存恢复到安全线" if stockout_scope else "",
        )]
        if partial_scope:
            actions.insert(0, RecommendedAction(
                priority="P0",
                title="补齐未匹配 SKU",
                detail="先核对目录货品编码与吉客云返回编码，再重新判断未匹配 SKU 是否缺货。",
                owner="数据运营",
                validation="所选范围未匹配 SKU 数量为 0",
            ))
        if ambiguous:
            actions.insert(0, RecommendedAction(priority="P0", title="确认编码对应货品", detail="同一编码命中多个库存候选，先按系列、规格、尺码或 SKU 编码确认目标货品，再做补货判断。", owner="商品运营", validation="目标货品唯一匹配"))
        return Diagnosis(
            headline=headline,
            summary=summary,
            findings=findings,
            actions=actions,
            artifacts=[ArtifactSpec(type="metric_table", title="库存查询结果", rows=rows)],
            assumptions=[f"库存业务日：{result.data.get('business_day') or '--'}", f"库存快照时间：{snapshot_display}"],
        )

    @staticmethod
    def _exploration_query_arguments(
        question: str,
        base: dict[str, object],
        page_context: dict[str, object] | None = None,
    ) -> dict[str, object]:
        lowered = question.lower()
        page_key = str((page_context or {}).get("page_key") or "")
        page_queries: dict[str, tuple[str, list[str], list[str], list[str]]] = {
            "promotions-cps": ("cps", ["date"], ["payment_gmv", "settlement_gmv", "payment_commission", "payment_service_fee", "settlement_expense"], ["date"]),
            "content": ("promotion_contents", ["content_id", "content_name", "content_type"], ["impressions", "clicks", "spend", "gmv", "orders"], ["-gmv"]),
            "live": ("live_store_performance", ["date"], ["viewers", "item_click_users", "buyers", "gmv", "view_click_rate", "click_conversion_rate"], ["date"]),
            "marketing-activities": ("store_activity_calendar_events", ["activity_id", "activity_name", "activity_type", "activity_start", "activity_end", "activity_stage"], ["event_count"], []),
            "marketing-flash-sale": ("taobao_flash_sale_overviews", ["date"], ["item_views", "item_visitors", "orders", "gmv", "new_customers", "conversion_rate"], ["date"]),
            "marketing-new-customer": ("new_customer_discount", ["date"], ["buyers", "gmv", "buyer_share", "gmv_share", "conversion_rate", "store_new_buyers", "store_new_gmv"], ["date"]),
            "marketing-shopping-gold": ("shopping_gold", ["date"], ["recharge_amount", "recharge_buyers", "recharge_refund_amount", "paid_amount", "paid_buyers", "recharge_rate"], ["date"]),
            "marketing-bybt": ("bybt", ["date"], ["gmv", "buyers"], ["date"]),
            "inventory": ("inventory_snapshots", ["business_day", "warehouse_name", "goods_no", "sku_no", "goods_name", "sku_name"], ["available_quantity", "stock_quantity"], ["-available_quantity"]),
        }
        if page_key in page_queries:
            dataset, dimensions, measures, order_by = page_queries[page_key]
            return {**base, "dataset": dataset, "dimensions": dimensions, "measures": measures, "order_by": order_by, "limit": 200}
        if any(word in lowered for word in ("商品", "货品", "sku", "排行")):
            dataset, dimensions, measures = "products", ["product_id", "product_name"], ["gmv", "buyers", "visitors", "add_cart_users"]
        elif any(word in lowered for word in ("流量", "来源", "uv", "访客")):
            dataset, dimensions, measures = "traffic_sources", ["source"], ["gmv", "buyers", "visitors", "new_visitors"]
        elif any(word in lowered for word in ("推广", "投放", "广告", "roi")):
            dataset, dimensions, measures = "promotion_campaigns", ["scene"], ["spend", "gmv", "buyers", "clicks"]
        elif any(word in lowered for word in ("客户", "新客", "复购", "老客")):
            dataset, dimensions, measures = "customers", [], ["new_paid_buyers", "repeat_buyers", "no_purchase_buyers"]
        elif any(word in lowered for word in ("会员", "入会")):
            dataset, dimensions, measures = "members", [], ["gmv", "member_buyers", "new_members"]
        else:
            dataset, dimensions, measures = "store_overview", [], ["gmv", "visitors", "buyers", "refund_amount"]
        return {**base, "dataset": dataset, "dimensions": dimensions, "measures": measures, "order_by": ["-gmv"] if "gmv" in measures else [], "limit": 100}

    def build_period_report(
        self,
        request: PeriodReportRequest,
        *,
        store_id: int | None,
        user_id: int | None = None,
        on_event: Callable[[dict], None] | None = None,
        stream_model: bool = False,
    ) -> PeriodReportResponse:
        started = time.perf_counter()
        conversation = self._conversation_state(request.conversation_id, user_id=user_id, store_id=store_id)
        from datetime import date, timedelta

        source = self.mcp.analytics._source_for_store(store_id)
        _minimum, maximum = source.get_date_bounds()
        anchor = request.anchor_date or maximum
        if anchor > maximum:
            anchor = maximum
        if request.report_type == "daily":
            start_date = end_date = anchor
        elif request.report_type == "weekly":
            start_date = anchor - timedelta(days=6)
            end_date = anchor
        elif request.report_type in {"monthly", "daily_series"}:
            start_date = anchor.replace(day=1)
            end_date = anchor
        else:
            start_date = anchor.replace(day=1)
            end_date = anchor
        skill = next(skill for skill in SKILLS if skill.descriptor.name == "period-report-generation")
        execution_steps = [
            ExecutionStep(kind="planner", name="period-report-router", status="completed", detail=f"已按 {request.report_type} 解析报告区间：{start_date} 至 {end_date}", elapsed_ms=0),
            ExecutionStep(kind="skill", name=skill.descriptor.name, status="completed", detail=f"已加载周期报告能力：{skill.descriptor.display_name}", elapsed_ms=0),
        ]
        self._emit(on_event, "planner", status="completed", name="period-report-router", detail=f"已选择报告能力：{skill.descriptor.display_name}")
        self._emit(on_event, "skill", status="completed", name=skill.descriptor.name, detail="周期报告 Agent 已就绪", skill=skill.descriptor.model_dump(mode="json"), supporting_skills=[])
        self._emit(on_event, "mcp", status="running", name="reports.build_period_report", detail="汇总周期经营数据")
        data_started = time.perf_counter()
        result = self.mcp.execute("reports.build_period_report", {
            "store_id": store_id,
            "start_date": start_date,
            "end_date": end_date,
            "report_type": request.report_type,
        })
        data_elapsed = round((time.perf_counter() - data_started) * 1000, 1)
        execution_steps.append(ExecutionStep(kind="mcp", name="reports.build_period_report", status="completed", detail=f"汇总经营数据并校验覆盖 · {result.status}", elapsed_ms=data_elapsed))
        self._emit(on_event, "mcp", status="completed", name="reports.build_period_report", detail=f"报告数据已返回 · {result.status}", result_status=result.status, elapsed_ms=data_elapsed)
        if request.target_gmv is not None:
            import calendar
            current_gmv = float(result.data.get("operations", {}).get("gmv") or 0)
            if request.report_type in {"monthly", "mtd"}:
                total_days = calendar.monthrange(end_date.year, end_date.month)[1]
                time_progress = end_date.day / total_days * 100
                remaining_days = max(total_days - end_date.day, 0)
            elif request.report_type == "daily_series":
                total_days = max((end_date - start_date).days + 1, 1)
                time_progress = 100
                remaining_days = 0
            else:
                total_days = max((end_date - start_date).days + 1, 1)
                time_progress = min(total_days / ({"weekly": 7, "daily": 1}.get(request.report_type, total_days)) * 100, 100)
                remaining_days = 0
            completion_rate = round(current_gmv / request.target_gmv * 100, 2) if request.target_gmv else None
            remaining_gmv = round(max(request.target_gmv - current_gmv, 0), 2)
            report_data = dict(result.data)
            report_data["target"] = {
                "target_gmv": request.target_gmv,
                "completion_rate": completion_rate,
                "gap": round(request.target_gmv - current_gmv, 2),
                "remaining_gmv": remaining_gmv,
                "remaining_days": remaining_days,
                "required_daily_gmv": round(remaining_gmv / remaining_days, 2) if remaining_days else None,
                "time_progress": round(time_progress, 2),
                "pace_gap": round(completion_rate - time_progress, 2) if completion_rate is not None else None,
                "source": "用户输入",
            }
            result = result.model_copy(update={"data": report_data})
        title_map = {"daily": "经营日报", "weekly": "经营周报", "monthly": "经营月报", "mtd": "经营 MTD 报告", "daily_series": "逐日经营日报"}
        diagnosis = self._enrich_diagnosis(
            skill.diagnose([result], {}),
            request=AnalysisRequest(
                question=title_map.get(request.report_type, "经营报告"),
                store_id=store_id,
                start_date=start_date,
                end_date=end_date,
                use_model=request.use_model,
            ),
            results=[result],
            skill_inputs={},
            skill=skill,
        )
        provider_name = "rules"
        model_name = None
        warnings = list(result.warnings)
        text = self._period_report_text(request.report_type, result.data, diagnosis)
        if request.use_model and self.provider.configured:
            self._emit(on_event, "model", status="running", name=self.provider.model, detail="正在生成报告解读")
            model_started = time.perf_counter()
            try:
                provider_kwargs = {
                    "question": title_map[request.report_type],
                    "diagnosis": diagnosis,
                    "evidence": [item.model_dump(mode="json") for item in result.evidence],
                    "mcp_results": self._model_mcp_results([result]),
                    "context": {"store_id": store_id, "report_type": request.report_type, **self._conversation_prompt_context(conversation)},
                }
                if stream_model and on_event is not None:
                    text = ""
                    for chunk in self.provider.stream_answer(**provider_kwargs):
                        text += chunk
                        self._emit(on_event, "token", text=chunk)
                    if not text.strip():
                        raise AIProviderError("Agnes returned an empty streaming answer")
                else:
                    text = self.provider.generate_answer(**provider_kwargs)
                provider_name = self.provider.name
                model_name = self.provider.model
                model_elapsed = round((time.perf_counter() - model_started) * 1000, 1)
                execution_steps.append(ExecutionStep(kind="model", name=self.provider.model, status="completed", detail="基于结构化证据生成报告解读", elapsed_ms=model_elapsed))
                self._emit(on_event, "model", status="completed", name=self.provider.model, detail="报告解读生成完成", elapsed_ms=model_elapsed)
            except AIProviderError:
                warnings.append("AI 模型调用失败，已使用固定口径报告结果。")
                model_elapsed = round((time.perf_counter() - model_started) * 1000, 1)
                execution_steps.append(ExecutionStep(kind="model", name=self.provider.model, status="failed", detail="模型不可用，已回退固定口径报告", elapsed_ms=model_elapsed))
                self._emit(on_event, "model", status="failed", name=self.provider.model, detail="模型不可用，已回退固定口径报告", elapsed_ms=model_elapsed)
        else:
            self._emit(on_event, "model", status="skipped", name=self.provider.model, detail="未配置模型或本次未启用模型")
            execution_steps.append(ExecutionStep(kind="model", name=self.provider.model, status="skipped", detail="未配置模型或本次未启用模型", elapsed_ms=0))
        response = PeriodReportResponse(
            request_id=result.request_id,
            conversation_id=conversation.conversation_id,
            status=result.status,
            report_type=request.report_type,
            range_start=start_date,
            range_end=end_date,
            title=title_map[request.report_type],
            text=text,
            report=result.data,
            diagnosis=diagnosis,
            mcp_result=result,
            skill=skill.descriptor,
            provider=provider_name,
            model=model_name,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 1),
            execution_steps=execution_steps,
            warnings=list(dict.fromkeys(warnings)),
        )
        self._remember(
            conversation,
            user_id=user_id,
            store_id=store_id,
            question=title_map[request.report_type],
            answer=text,
            memory={
                "summary": diagnosis.headline,
                "last_question": title_map[request.report_type],
                "report_type": request.report_type,
                "target_gmv": request.target_gmv,
                "planning_inputs": {
                    **(conversation.memory.get("planning_inputs") if isinstance(conversation.memory.get("planning_inputs"), dict) else {}),
                    **({"target_gmv": request.target_gmv} if request.target_gmv is not None else {}),
                },
                "range_start": start_date.isoformat(),
                "range_end": end_date.isoformat(),
                "headline": diagnosis.headline,
                "findings": [{"title": item.title, "detail": item.detail} for item in diagnosis.findings[:3]],
                "actions": [{"priority": item.priority, "title": item.title, "validation": item.validation} for item in diagnosis.actions[:3]],
                "confidence": diagnosis.confidence,
                "causal_boundary": diagnosis.causal_boundary,
                "timeline": self._memory_timeline(
                    conversation,
                    question=title_map[request.report_type],
                    headline=diagnosis.headline,
                    skill=skill.descriptor.name,
                    range_start=start_date.isoformat(),
                    range_end=end_date.isoformat(),
                ),
            },
            response=response,
            request_context={
                "kind": "period_report_request",
                "store_id": store_id,
                "report_type": request.report_type,
                "anchor_date": request.anchor_date.isoformat() if request.anchor_date else None,
                "target_gmv": request.target_gmv,
            },
        )
        self._emit(on_event, "final", status="completed", response=response.model_dump(mode="json"))
        return response

    @staticmethod
    def _analysis_request_context(request: AnalysisRequest, *, store_id: int | None) -> dict:
        return {
            "kind": "analysis_request",
            "question": request.question,
            "store_id": store_id,
            "start_date": request.start_date.isoformat() if request.start_date else None,
            "end_date": request.end_date.isoformat() if request.end_date else None,
            "domain": request.domain,
            "page_context": request.page_context,
        }

    @staticmethod
    def _deterministic_answer(diagnosis) -> str:
        lines = [diagnosis.headline]
        if diagnosis.summary and diagnosis.summary != diagnosis.headline:
            lines.append(diagnosis.summary)
        if diagnosis.findings:
            lines.append("问题定位：")
            seen: set[str] = set()
            for item in diagnosis.findings:
                line = f"- {item.title}：{item.detail}"
                if line not in seen and item.detail != diagnosis.summary:
                    lines.append(line)
                    seen.add(line)
        if diagnosis.actions:
            lines.append("建议动作：")
            lines.extend(f"- {item.priority} {item.title}：{item.detail}" for item in diagnosis.actions)
        return "\n".join(lines)

    @classmethod
    def _period_report_text(cls, report_type: str, report: dict, diagnosis: Diagnosis) -> str:
        """Render a compact, copyable report while the UI uses the same data as tables."""
        operations = report.get("operations", {})
        comparison = report.get("comparison", {})
        channels = report.get("channels", {})
        promotions = report.get("promotions", {})
        target = report.get("target") or {}
        talents = report.get("top_talents", [])
        start = str(report.get("range_start") or "")
        end = str(report.get("range_end") or start)
        title_map = {"daily": "日报", "weekly": "周报", "monthly": "月报", "mtd": "MTD"}

        def amount(value) -> str:
            return "--" if value is None else f"{float(value) / 10000:.2f}万"

        def number(value) -> str:
            return "--" if value is None else f"{float(value):,.0f}"

        def percent(value) -> str:
            return "--" if value is None else f"{float(value):.2f}%"

        def change(key: str) -> str:
            item = comparison.get(key, {}) if isinstance(comparison.get(key), dict) else {}
            value = item.get("change_percent")
            return "--" if value is None else f"{float(value):+.2f}%"

        if start:
            try:
                start_date = date.fromisoformat(start)
                if report_type == "mtd":
                    report_title = f"{start_date.year % 100:02d}年-{start_date.month}月MTD"
                elif report_type == "monthly":
                    report_title = f"{start_date.year % 100:02d}年-{start_date.month}月月报"
                elif report_type == "daily_series":
                    report_title = f"{start_date.year % 100:02d}年-{start_date.month}月逐日经营日报"
                elif report_type == "daily":
                    report_title = f"{start_date.year % 100:02d}年-{start_date.month}月{start_date.day}日日报"
                else:
                    report_title = f"{start} {title_map.get(report_type, '经营报告')}"
            except ValueError:
                report_title = f"{start} {title_map.get(report_type, '经营报告')}"
        else:
            report_title = title_map.get(report_type, "经营报告")
        lines = [report_title, f"统计区间：{start} 至 {end}"]
        if target.get("target_gmv") is not None:
            target_line = f"销售目标：{amount(target['target_gmv'])}；完成率：{percent(target.get('completion_rate'))}；时间进度：{percent(target.get('time_progress'))}；进度差：{percent(target.get('pace_gap'))}"
            if target.get("remaining_days") and target.get("required_daily_gmv") is not None:
                target_line += f"；剩余{amount(target.get('remaining_gmv'))}，剩余{int(target['remaining_days'])}天日均需完成{amount(target.get('required_daily_gmv'))}"
            lines.append(target_line)
        lines.append(f"GMV：{amount(operations.get('gmv'))}（环比 {change('paid_amount')}）；去退 GMV：{amount(operations.get('net_gmv'))}；退款金额占比：{percent(operations.get('refund_rate'))}")
        lines.append("1.运营数据")
        lines.append(
            f"UV：{number(operations.get('visitors'))}（环比 {change('visitors')}）；支付买家：{number(operations.get('buyers'))}（环比 {change('buyers')}）；"
            f"转化率：{percent(operations.get('conversion_rate'))}（环比 {change('conversion_rate')}）；客单价：¥{float(operations.get('customer_unit_price') or 0):.2f}；"
            f"新客支付人数占比：{percent(operations.get('new_customer_buyer_share'))}"
        )
        if operations.get("add_cart_buyers") is not None or operations.get("paid_items") is not None:
            lines.append(
                f"加购人数：{number(operations.get('add_cart_buyers'))}；收藏人数：{number(operations.get('favorite_buyers'))}；"
                f"支付件数：{number(operations.get('paid_items'))}；浏览量：{number(operations.get('page_views'))}"
            )
        if operations.get("visitors") and operations.get("gmv") is not None:
            lines.append(f"UV价值：¥{float(operations.get('gmv') or 0) / float(operations.get('visitors') or 1):.2f}；推广费比：{percent(float(promotions.get('spend') or 0) / float(operations.get('gmv') or 1) * 100)}")
        customer = report.get("customer") or {}
        if customer.get("status") in {"available", "complete"}:
            lines.append(
                f"客户结构：新客支付买家 {number(customer.get('new_paid_buyers'))}（成交 {amount(customer.get('new_paid_amount'))}）；"
                f"老客支付买家 {number(customer.get('repeat_buyers'))}（成交 {amount(customer.get('repeat_paid_amount'))}）"
            )
        lines.append("2.渠道数据")
        channel_labels = {"member": "会员成交", "shop_live": "自播间成交", "bybt": "百亿补贴成交", "cps_payment": "CPS-GMV", "cps_settlement": "CPS出库成交"}
        for key, label in channel_labels.items():
            item = channels.get(key, {})
            if item.get("status") not in {"available", "complete"}:
                continue
            line = f"{label}：{amount(item.get('paid_amount'))}，销售占比：{percent(item.get('sales_share'))}"
            if item.get("expense") is not None:
                line += f"，已知费用：{amount(item.get('expense'))}"
            if key == "member" and item.get("new_members") is not None:
                line += f"，新增会员：{number(item.get('new_members'))}"
            if key == "cps_payment":
                line += f"，佣金：{amount(item.get('commission_expense'))}，服务费：{amount(item.get('service_expense'))}"
            if key == "cps_settlement":
                line += f"，佣金服务费：{amount(item.get('expense'))}"
            lines.append(line)
        lines.append("3.推广数据")
        lines.append(
            f"阿里妈妈（15天归因）：推广点击 {number(promotions.get('paid_clicks'))}，占店铺 UV：{percent(promotions.get('paid_click_share_of_store_uv'))}；"
            f"花费：{amount(promotions.get('spend'))}，归因成交：{amount(promotions.get('attributed_paid_amount'))}，整体 ROI：{promotions.get('roi') if promotions.get('roi') is not None else '--'}"
        )
        for scene in sorted(promotions.get("scenes", []), key=lambda row: float(row.get("spend") or 0), reverse=True):
            name = scene.get("scene_name") or scene.get("dimension_name") or "未分类"
            spend = float(scene.get("spend") or 0)
            spend_share = spend / float(promotions.get("spend") or 1) * 100 if promotions.get("spend") else None
            detail = f"{name}（花费 {amount(spend)}，费用占比：{percent(spend_share)}，ROI：{float(scene.get('roi') or 0):.2f}，归因成交：{amount(scene.get('paid_amount'))}"
            if scene.get("direct_paid_amount") is not None or scene.get("indirect_paid_amount") is not None:
                detail += f"，直接/间接：{amount(scene.get('direct_paid_amount'))}/{amount(scene.get('indirect_paid_amount'))}"
            if scene.get("buyers") is not None:
                detail += f"，支付买家：{number(scene.get('buyers'))}"
            lines.append(detail + "）")
        if promotions.get("brand_zone", {}).get("status") == "available":
            brand = promotions["brand_zone"]
            lines.append(f"品销宝（花费 {amount(brand.get('spend'))}，成交：{amount(brand.get('paid_amount'))}，ROI：{brand.get('roi') if brand.get('roi') is not None else '--'}）")
        if talents:
            lines.append("4.前三达人数据")
            for item in talents[:3]:
                talent_share = float(item.get('gmv') or 0) / float(operations.get('gmv') or 1) * 100 if operations.get('gmv') else None
                avg_session = float(item.get('gmv') or 0) / float(item.get('sessions') or 1) if item.get('sessions') else None
                lines.append(
                    f"{item.get('name') or '未命名达人'}（GMV：{amount(item.get('gmv'))}，销售占比：{percent(talent_share)}，"
                    f"场次：{number(item.get('sessions'))}，单场 GMV：{amount(avg_session)}，支付买家：{number(item.get('buyers'))}）"
                )
        if diagnosis.actions:
            lines.append("5.今日动作")
            lines.extend(f"- {item.priority} {item.title}：{item.detail}" for item in diagnosis.actions[:5])
        quality = report.get("data_quality") or {}
        coverage = diagnosis.coverage
        missing_datasets = quality.get("missing_datasets") or coverage.missing_datasets
        partial_datasets = quality.get("partial_datasets") or coverage.partial_datasets
        failed_datasets = quality.get("failed_datasets") or coverage.failed_datasets
        no_data_datasets = quality.get("no_data_datasets") or coverage.no_data_datasets
        missing_dates = quality.get("missing_dates") or coverage.missing_dates
        if quality.get("missing_sections") or quality.get("no_data_sections") or missing_datasets or partial_datasets or failed_datasets or no_data_datasets or missing_dates:
            lines.append("数据状态")
            if quality.get("missing_sections"):
                lines.append("- 待补采：" + "、".join(quality["missing_sections"]))
            if missing_datasets:
                lines.append("- 待补采数据集：" + "、".join(missing_datasets))
            if partial_datasets:
                lines.append("- 部分覆盖：" + "、".join(partial_datasets))
            if failed_datasets:
                lines.append("- 采集失败：" + "、".join(failed_datasets))
            if quality.get("no_data_sections"):
                lines.append("- 平台无数据：" + "、".join(quality["no_data_sections"]))
            if no_data_datasets:
                lines.append("- 平台无数据集：" + "、".join(no_data_datasets))
            if missing_dates:
                lines.append("- 缺失日期：" + "、".join(missing_dates))
        return "\n".join(lines)

    @staticmethod
    def _coverage_summary(results: list[MCPEnvelope]) -> CoverageSummary:
        """Merge MCP coverage without turning platform no-data into missing data."""
        coverages = [item.coverage for item in results if item.coverage.expected_days or item.coverage.covered_days or item.coverage.missing_dates or item.coverage.no_data_datasets]
        if not coverages:
            # Static datasets (catalogs, reviews and snapshots) legitimately
            # have no business-day coverage. Their no-data state still needs
            # to be visible to the user and to the model.
            no_data = sorted({
                evidence.dataset or evidence.table or item.tool
                for item in results if item.status == "no_data"
                for evidence in item.evidence
            })
            return CoverageSummary(no_data_datasets=no_data)
        dated = [item for item in coverages if item.expected_days]
        expected = max((item.expected_days for item in dated), default=0)
        covered = min((item.covered_days for item in dated), default=0)
        def unique(values: list[str]) -> list[str]:
            return sorted({str(value) for value in values if value})
        latest_dates = [item.latest_data_date for item in coverages if item.latest_data_date]
        no_data_datasets = unique([
            value for item in coverages for value in item.no_data_datasets
        ])
        no_data_datasets.extend(sorted({
            evidence.dataset or evidence.table or item.tool
            for item in results if item.status == "no_data"
            for evidence in item.evidence
        }))
        return CoverageSummary(
            expected_days=expected,
            covered_days=covered,
            missing_dates=unique([value for item in coverages for value in item.missing_dates]),
            missing_datasets=unique([value for item in coverages for value in item.missing_datasets]),
            partial_datasets=unique([value for item in coverages for value in item.partial_datasets]),
            failed_datasets=unique([value for item in coverages for value in item.failed_datasets]),
            no_data_datasets=unique(no_data_datasets),
            no_data_dates=unique([value for item in coverages for value in item.no_data_dates]),
            latest_data_date=max(latest_dates) if latest_dates else None,
        )

    @classmethod
    def _enrich_diagnosis(
        cls,
        diagnosis: Diagnosis,
        *,
        request: AnalysisRequest,
        results: list[MCPEnvelope],
        skill_inputs: dict[str, object],
        skill,
    ) -> Diagnosis:
        if skill.descriptor.name == "general-chat":
            return diagnosis.model_copy(update={
                "analysis_scope": {"kind": "chat"},
                "coverage": CoverageSummary(),
                "confidence": "high",
                "assumptions": [],
                "missing_inputs": [],
                "evidence_refs": [],
                "metric_definitions": {},
                "denominator_notes": [],
                "causal_boundary": "",
                "next_questions": list(dict.fromkeys(diagnosis.next_questions)),
            })
        coverage = cls._coverage_summary(results)
        report_quality = None
        if skill.descriptor.name == "period-report-generation":
            report_quality = (results[0].data.get("decision_quality") or {}).get("overall") if results else None
        if skill.descriptor.name == "inventory-query":
            inventory_data = results[0].data if results else {}
            if inventory_data.get("freshness_status") == "stale":
                confidence = "low"
            elif inventory_data.get("ambiguous") or any(item.status == "partial" for item in results):
                confidence = "medium"
            elif inventory_data.get("freshness_status") == "fresh" and inventory_data.get("reason") not in {"not_configured", "not_collected", "date_not_available"}:
                confidence = "high"
            else:
                confidence = "low"
        elif report_quality and report_quality.get("confidence") in {"high", "medium", "low"}:
            confidence = str(report_quality["confidence"])
        else:
            # Confidence belongs to the question's primary evidence chain,
            # not to every optional domain loaded for context. A missing
            # reviews or campaign dataset should not downgrade a complete
            # total-store conversion diagnosis to "low" confidence.
            primary_names = {step.tool for step in (skill.descriptor.workflow or [])}
            primary_results = [item for item in results if item.tool in primary_names]
            if not primary_results:
                primary_results = results[:1]
            primary_no_data = any(item.status == "no_data" or not item.evidence for item in primary_results)
            primary_partial = any(item.status == "partial" for item in primary_results)
            if primary_no_data:
                confidence = "low"
            elif primary_partial or coverage.missing_dates or coverage.missing_datasets or coverage.partial_datasets or coverage.failed_datasets:
                confidence = "medium"
            else:
                confidence = "high"

        contexts = [item.context for item in results if item.context]
        context = contexts[0] if contexts else None
        scope_start = context.range_start.isoformat() if context else request.start_date.isoformat() if request.start_date else None
        scope_end = context.range_end.isoformat() if context else request.end_date.isoformat() if request.end_date else None
        metric_definitions: dict[str, str] = {}
        denominator_notes = {"占比、ROI 和排名使用本次查询的全量结果作为分母；展示 Top N 不改变总计。"}
        evidence_refs: list[str] = []
        for result in results:
            for metric in result.metrics:
                metric_definitions[metric.id] = f"{metric.label}：{metric.formula or metric.source or '数据源原始字段'}"
                if metric.formula and ("/" in metric.formula or "占" in metric.label or "ROI" in metric.label.upper()):
                    denominator_notes.add(f"{metric.label} 口径：{metric.formula}")
            for evidence in result.evidence:
                ref = f"{result.tool}:{evidence.dataset or evidence.table}"
                if ref not in evidence_refs:
                    evidence_refs.append(ref)

        missing_inputs: list[str] = []
        if skill.descriptor.name == "promotion-budget-planning":
            if skill_inputs.get("total_budget") is None: missing_inputs.append("总预算")
            if skill_inputs.get("target_roi") is None: missing_inputs.append("目标 ROI")
        if skill.descriptor.name == "campaign-planning":
            if skill_inputs.get("target_gmv") is None: missing_inputs.append("GMV 目标")
            if skill_inputs.get("total_budget") is None: missing_inputs.append("总预算")
            if skill_inputs.get("target_roi") is None: missing_inputs.append("目标 ROI")
            if skill_inputs.get("period_start") is None or skill_inputs.get("period_end") is None:
                missing_inputs.append("规划周期")
        assumptions = list(diagnosis.assumptions)
        if skill.descriptor.name != "inventory-query" and "未提供完整成本字段，不能计算毛利率或净利润。" not in assumptions:
            assumptions.append("未提供完整成本字段，不能计算毛利率或净利润。")
        next_questions = list(diagnosis.next_questions)
        if coverage.missing_dates and "是否生成缺失日期补采任务？" not in next_questions:
            next_questions.append("是否生成缺失日期补采任务？")
        if missing_inputs:
            next_questions.append("是否补充规划输入后重新计算情景？")
        causal_boundary = "" if skill.descriptor.name == "inventory-query" else diagnosis.causal_boundary or "当前结论是描述性分析或平台归因贡献；没有实验、对照或平台增量报告时，不代表因果增量。"
        actions = []
        for action in diagnosis.actions:
            actions.append(action.model_copy(update={
                "observation_window": action.observation_window or ("3-7天" if action.priority == "P0" else "7-14天"),
                "expected_impact": action.expected_impact or "改善对应验证指标，同时不恶化支付转化率、退款率或已知费用效率。",
            }))
        fact_sheet = cls._analysis_fact_sheet(results, coverage)
        artifacts = list(diagnosis.artifacts)
        if skill.descriptor.name != "inventory-query":
            domain_rows = [
                {
                    "经营域": item.get("domain"),
                    "状态": {"ok": "可用", "partial": "部分覆盖", "no_data": "平台无数据"}.get(str(item.get("status")), str(item.get("status") or "未知")),
                    "证据记录": item.get("records"),
                    "数据集": "、".join(item.get("datasets") or []) or "--",
                    "数据时效": item.get("time_scope") or "--",
                    "最新业务日": item.get("latest_data_date") or "--",
                }
                for item in fact_sheet.get("domains", [])
                if item.get("domain") != "other"
            ]
            if domain_rows and not any(item.title == "跨域数据状态" for item in artifacts):
                artifacts.append(ArtifactSpec(type="matrix", title="跨域数据状态", rows=domain_rows[:16]))
            core_rows = [
                {
                    "指标": item.get("metric"),
                    "本期": item.get("current"),
                    "上期": item.get("previous"),
                    "环比%": item.get("change_percent"),
                    "来源": item.get("source"),
                }
                for item in fact_sheet.get("core_metrics", [])
                if item.get("current") is not None or item.get("previous") is not None
            ]
            if core_rows and not any(item.title == "总盘口径校验" for item in artifacts):
                artifacts.append(ArtifactSpec(type="matrix", title="总盘口径校验", rows=core_rows[:12]))
        return diagnosis.model_copy(update={
            "analysis_scope": {
                "store_id": request.store_id,
                "range_start": scope_start,
                "range_end": scope_end,
                "timezone": "Asia/Shanghai",
                "filters": request.page_context,
            },
            "coverage": coverage,
            "confidence": confidence,
            "assumptions": assumptions,
            "missing_inputs": list(dict.fromkeys(missing_inputs + diagnosis.missing_inputs)),
            "evidence_refs": list(dict.fromkeys([*diagnosis.evidence_refs, *evidence_refs])),
            "metric_definitions": {**metric_definitions, **diagnosis.metric_definitions},
            "denominator_notes": list(dict.fromkeys([*diagnosis.denominator_notes, *sorted(denominator_notes)])),
            "causal_boundary": causal_boundary,
            "actions": actions,
            "artifacts": artifacts,
            "next_questions": list(dict.fromkeys(next_questions)),
        })

    @staticmethod
    def _analysis_fact_sheet(results: list[MCPEnvelope], coverage: CoverageSummary) -> dict[str, object]:
        """Build one bounded, cross-domain fact layer for model synthesis.

        MCP envelopes remain the auditable source of truth. This view only
        normalizes the facts that are safe to compare across tools so Agnes
        does not have to infer the store's primary KPIs from unrelated rows.
        """
        domain_labels = {
            "overview": "店铺总盘", "traffic": "流量", "product": "商品",
            "promotion": "推广", "customer": "客户/会员", "service": "客服",
            "review": "评价", "campaign": "活动", "live": "直播",
            "cps": "CPS/达人", "inventory": "库存", "brand": "品牌资产",
        }

        def domain_for(item: MCPEnvelope) -> str:
            tool = item.tool
            if tool.startswith("utry."):
                return "customer"
            if tool.startswith("overview."):
                return "overview"
            if tool == "data.compare_periods":
                dataset = str(item.data.get("dataset") or "").casefold()
                return {
                    "store_overview": "overview",
                    "traffic_sources": "traffic",
                    "products": "product",
                    "promotion_campaigns": "promotion",
                    "customers": "customer",
                }.get(dataset, "other")
            if tool.startswith("products."):
                return "product"
            if tool.startswith("promotions.") or "promotion" in tool:
                return "promotion"
            if tool.startswith("customer_service."):
                return "service"
            if tool.startswith("reviews."):
                return "review"
            if tool.startswith("inventory.") or "inventory" in tool:
                return "inventory"
            if "live" in tool or "talent" in tool:
                return "live"
            if tool.startswith("brand_assets.") or "brand_asset" in tool:
                return "brand"
            if tool.startswith("cps.") or tool == "data.query" and any(
                "cps" in (e.dataset or "").casefold() for e in item.evidence
            ):
                return "cps"
            if tool.startswith("data.query"):
                datasets = " ".join((e.dataset or "") for e in item.evidence).casefold()
                if "traffic" in datasets or "流量" in datasets:
                    return "traffic"
                if "customer" in datasets or "member" in datasets or "客户" in datasets or "会员" in datasets:
                    return "customer"
                if "review" in datasets or "评价" in datasets or "问大家" in datasets:
                    return "review"
                if "activity" in datasets or "flash" in datasets or "customer discount" in datasets or "活动" in datasets or "秒杀" in datasets or "新客折扣" in datasets or "新客礼金" in datasets:
                    return "campaign"
                if "content" in datasets or "内容" in datasets:
                    return "campaign"
                if "直播" in datasets or "live" in datasets:
                    return "live"
                if "推广" in datasets:
                    return "promotion"
                if "库存" in datasets:
                    return "inventory"
            return "other"

        def row_count(item: MCPEnvelope) -> int:
            evidence_count = sum(max(0, int(evidence.row_count or 0)) for evidence in item.evidence)
            if evidence_count:
                return evidence_count
            for key in ("rows", "sources", "campaigns", "items", "products", "series", "types"):
                value = item.data.get(key)
                if isinstance(value, list):
                    return len(value)
            return 0

        def time_scope(item: MCPEnvelope) -> str:
            item_coverage = item.coverage
            if item_coverage.expected_days:
                return f"周期 {item_coverage.covered_days}/{item_coverage.expected_days} 天"
            if item.status == "no_data":
                return "无可用记录"
            if item.tool.startswith("reviews."):
                return "事件明细"
            return "静态/快照数据"

        domains: dict[str, dict[str, object]] = {}
        for item in results:
            key = domain_for(item)
            current = domains.setdefault(key, {
                "domain": domain_labels.get(key, key),
                "status": "unknown",
                "tools": [],
                "datasets": [],
                "records": 0,
                "latest_data_date": item.coverage.latest_data_date,
                "warnings": [],
                "time_scopes": [],
            })
            had_tools = bool(current["tools"])
            if item.tool not in current["tools"]:
                current["tools"].append(item.tool)
            if not had_tools:
                current["status"] = item.status
            else:
                current_status = str(current["status"])
                if item.status == "partial" or current_status == "partial":
                    current["status"] = "partial"
                elif item.status == "failed" or current_status == "failed":
                    current["status"] = "partial"
                elif item.status == "no_data" or current_status == "no_data":
                    current["status"] = "partial"
                else:
                    current["status"] = "ok"
            current["records"] = int(current["records"]) + row_count(item)
            scope = time_scope(item)
            if scope not in current["time_scopes"]:
                current["time_scopes"].append(scope)
            if item.coverage.latest_data_date:
                current["latest_data_date"] = max(str(current.get("latest_data_date") or ""), item.coverage.latest_data_date)
            for evidence in item.evidence:
                dataset = evidence.dataset or evidence.table
                if dataset and dataset not in current["datasets"]:
                    current["datasets"].append(dataset)
            current["warnings"].extend(item.warnings[:2])
        for item in domains.values():
            item["tools"] = item["tools"][:8]
            item["datasets"] = item["datasets"][:8]
            item["warnings"] = list(dict.fromkeys(item["warnings"]))[:3]
            scopes = list(item.pop("time_scopes"))
            period_scope = next((value for value in scopes if value.startswith("周期 ")), None)
            static_scope = next((value for value in scopes if value in {"静态/快照数据", "事件明细"}), None)
            item["time_scope"] = f"{period_scope} + {static_scope}" if period_scope and static_scope else period_scope or static_scope or "范围未确认"

        core_metrics: list[dict[str, object]] = []
        for item in results:
            if item.tool == "data.compare_periods" and item.data.get("dataset") == "store_overview":
                comparisons = item.data.get("comparisons") or {}
                for metric_id, values in comparisons.items():
                    if not isinstance(values, dict):
                        continue
                    core_metrics.append({
                        "metric": metric_id,
                        "current": values.get("current"),
                        "previous": values.get("previous"),
                        "delta": values.get("delta"),
                        "change_percent": values.get("change_percent"),
                        "source": item.tool,
                    })
                break
        consistency_checks: list[dict[str, object]] = []
        by_metric = {str(item["metric"]): item for item in core_metrics}
        buyers = by_metric.get("buyers")
        visitors = by_metric.get("visitors")
        paid = by_metric.get("gmv") or by_metric.get("paid_amount")
        if buyers and visitors:
            current_visitors = float(visitors.get("current") or 0)
            previous_visitors = float(visitors.get("previous") or 0)
            current_buyers = float(buyers.get("current") or 0)
            previous_buyers = float(buyers.get("previous") or 0)
            current_rate = current_buyers / current_visitors * 100 if current_visitors else None
            previous_rate = previous_buyers / previous_visitors * 100 if previous_visitors else None
            consistency_checks.append({
                "check": "支付转化率",
                "formula": "支付买家 ÷ 访客",
                "current": round(current_rate, 4) if current_rate is not None else None,
                "previous": round(previous_rate, 4) if previous_rate is not None else None,
                "status": "calculated" if current_rate is not None and previous_rate is not None else "insufficient_data",
            })
        if paid and buyers:
            current_buyers = float(buyers.get("current") or 0)
            previous_buyers = float(buyers.get("previous") or 0)
            current_paid = float(paid.get("current") or 0)
            previous_paid = float(paid.get("previous") or 0)
            consistency_checks.append({
                "check": "客单价",
                "formula": "支付金额 ÷ 支付买家",
                "current": round(current_paid / current_buyers, 4) if current_buyers else None,
                "previous": round(previous_paid / previous_buyers, 4) if previous_buyers else None,
                "status": "calculated" if current_buyers and previous_buyers else "insufficient_data",
            })
        return {
            "scope": {
                "expected_days": coverage.expected_days,
                "covered_days": coverage.covered_days,
                "latest_data_date": coverage.latest_data_date,
            },
            "coverage": coverage.model_dump(mode="json"),
            "core_metrics": core_metrics[:20],
            "consistency_checks": consistency_checks,
            "domains": sorted(domains.values(), key=lambda item: str(item["domain"])),
            "rules": [
                "总盘核心指标优先采用 data.compare_periods/overview 工具。",
                "推广成交是平台归因贡献，不等于因果增量；CPS/直播/会员可能与总盘重叠。",
                "缺失或平台无数据不按 0；完整成本不足时不计算利润率或净利润。",
            ],
        }

    @staticmethod
    def _model_mcp_results(results: list[MCPEnvelope]) -> list[dict]:
        """Keep model context structured and bounded while retaining calculations.

        Aggregates, metrics, coverage and provenance are always retained. Row
        lists are evidence samples, not the population used for calculations;
        sending thousands of nearly identical rows only increases latency and
        makes cross-domain reasoning less reliable.
        """
        list_limits = {
            "products": 20,
            "rows": 20,
            "campaigns": 12,
            "items": 20,
            "top_reviews": 4,
            "representative_unanswered_questions": 5,
            "risk_products": 10,
            "risk_series": 8,
            "accounts": 20,
        }

        def sample(value: object, *, key: str = "", depth: int = 0) -> object:
            if isinstance(value, list):
                limit = list_limits.get(key, 40)
                return [sample(item, depth=depth + 1) for item in value[:limit]]
            if isinstance(value, dict):
                # Deep, repeated payloads are normally raw event records.
                # Preserve their identifier and numeric/business fields but
                # do not recursively carry media, content or long metadata.
                if depth >= 4:
                    return {
                        str(item_key): item_value
                        for item_key, item_value in value.items()
                        if isinstance(item_value, (str, int, float, bool, type(None)))
                        and len(str(item_value)) <= 300
                    }
                return {str(item_key): sample(item_value, key=str(item_key), depth=depth + 1) for item_key, item_value in value.items()}
            if isinstance(value, str) and len(value) > 600:
                return f"{value[:600]}…"
            return value

        payload: list[dict] = []
        for result in results:
            item = result.model_dump(mode="json")
            original_data = item.get("data") or {}
            data = sample(original_data)
            if isinstance(data, dict):
                truncated = [
                    {"key": key, "total": len(value), "returned": len(data.get(key) or []), "note": "仅为证据样本；汇总值使用全量记录"}
                    for key, value in original_data.items()
                    if isinstance(value, list) and len(value) > len(data.get(key) or [])
                ]
                if truncated:
                    data["_truncated"] = truncated
            item["data"] = data
            payload.append(item)
        return payload

    def _log(self, execution_id, request, store_id, response, started, error_message) -> None:
        self._write_log(
            execution_id=execution_id,
            store_id=store_id,
            question=request.question,
            skill_name=response.skill.name,
            skill_version=response.skill.version,
            provider_name=response.provider,
            model_name=response.model,
            status=response.status,
            mcp_tools=[item.tool for item in response.mcp_results],
            warnings=response.warnings,
            duration_ms=round((time.perf_counter() - started) * 1000),
            error_message=error_message,
        )

    def _log_failure(self, execution_id, request, store_id, skill_name, skill_version, started, error_message) -> None:
        self._write_log(
            execution_id=execution_id,
            store_id=store_id,
            question=request.question,
            skill_name=skill_name,
            skill_version=skill_version,
            provider_name=self.provider.name if self.provider.configured else "rules",
            model_name=self.provider.model if self.provider.configured else None,
            status="error",
            mcp_tools=[],
            warnings=[],
            duration_ms=round((time.perf_counter() - started) * 1000),
            error_message=error_message,
        )

    def _write_log(self, **values) -> None:
        self.database.initialize_schema()
        with self.database.connect(initialize=True) as conn:
            conn.execute(
                """
                insert into ai_execution_logs (
                    execution_id, store_id, question, skill_name, skill_version,
                    provider_name, model_name, status, mcp_tools_json,
                    warnings_json, duration_ms, error_message, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    values["execution_id"], values["store_id"], values["question"],
                    values["skill_name"], values["skill_version"], values["provider_name"],
                    values["model_name"], values["status"],
                    json.dumps(values["mcp_tools"], ensure_ascii=False),
                    json.dumps(values["warnings"], ensure_ascii=False), values["duration_ms"],
                    values["error_message"], datetime.now().astimezone().isoformat(timespec="seconds"),
                ),
            )
            conn.commit()
