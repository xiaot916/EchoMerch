from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path
from collections.abc import Iterator

import httpx

from app.core.config import settings
from app.modules.ai.configuration import AIConfig, get_ai_config
from app.modules.ai.schemas import Diagnosis


class AIProviderError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _ecommerce_methodology() -> str:
    # Keep the provider prompt aligned with the installed analytics skill.
    # The old singular directory name silently returned an empty methodology.
    skill_path = Path(__file__).resolve().parents[3] / "skills" / "ecommerce-analytics-methodology" / "SKILL.md"
    try:
        return skill_path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


class AgnesProvider:
    name = "agnes"

    @staticmethod
    def _system_prompt(*, report_mode: bool = False, analysis_mode: bool = False) -> str:
        base = (
            "你是 EchoMerch 电商经营分析助手。只依据给定的结构化诊断和证据回答。"
            "先给结论，再解释原因和优先级，最后给可验证的运营动作。"
            "必须区分平台无数据与未采集数据；缺失数据不得当作 0。"
            "历史对话只用于理解追问，当前结构化查询结果始终优先。"
            "不要编造指标、商品、渠道或因果关系。"
            "当用户要求多个原因但证据不足时，明确区分已确认原因与待验证方向，不要凑数；退款下降或成本下降不能直接解释成交下降。"
        )
        if report_mode:
            base += (
                "当前是周期报告的 AI 补充判断，页面已经展示 KPI、渠道、推广和达人表格，不要复述整张表。"
                "只输出纯文本，禁止 Markdown 标题、表格、加粗符号和分隔线。"
                "控制在 600 个汉字以内，固定为：核心矛盾；最多 3 个原因；今日动作；风险边界。"
                "必须优先引用 gmv_driver_bridge 的最大驱动，不得用‘前日基数高’替代已有驱动证据。"
                "会员是客户身份，自播和 CPS 是重叠归因标签；CPS 支付与 CPS 出库不可相加。"
                "缺少完整成本时，禁止使用盈亏线、亏损、利润或值得扩量等结论；ROI 小于 1 只能说归因成交未覆盖广告花费。"
                "当用户要求‘三个原因’但证据不足时，明确写‘已确认原因’和‘待验证方向’，不要凑数；退款下降、成本下降或前期基数变化不能直接解释成交下降。"
            )
        elif analysis_mode:
            base += (
                "当前页面会同时展示结构化证据和动作卡片。你必须综合所有 mcp_results，而不是只看主 Skill 的第一条结果；"
                "analysis_context.store_fact_sheet 是跨域事实摘要：优先用其中的 core_metrics、consistency_checks 和 domains 排序判断，再用 mcp_results 的明细解释原因；"
                "domains 中的 records 是证据记录数，不是金额或用户数；domains.time_scope 明确区分周期、静态快照和事件明细：静态/事件数据已返回不等于它有完整历史趋势，不能写成全周期覆盖或用来单独证明变化原因；带有‘仅为证据样本’的截断列表不能当作全量；"
                "先排序最重要的 1-3 个原因，再说明每个原因对应的跨域证据、证据强度和待验证项。"
                "使用简洁 Markdown 输出，允许标题、列表和短表格；不要输出代码围栏。最多给 3 个已证实原因，证据不足的方向标为待验证。"
                "当主能力是店铺经营诊断时，按‘总盘结果→流量/转化漏斗→商品结构→渠道与投放→客户/会员→客服/评价/活动/库存’串联证据；不要把单个域的异常直接写成全店唯一原因。"
                "全店问题的结论必须明确哪些域已返回数据、哪些域部分覆盖或无数据，并优先给能解释支付金额/支付买家变化的证据。"
                "总盘问题的金额、买家、访客、客单价和环比必须优先采用 overview.get_store_summary 或 data.compare_periods 的字段；不同数据集的聚合结果不一致时，以总盘工具为准并标注口径，不自行平均或重算。"
                "不得把推广花费下降直接写成应恢复预算，也不得把退款下降、成本下降或前期基数变化当作成交下降原因。"
                "商品问题必须优先使用商品明细、商品主档、系列/类型结构、价格/活动/推广依赖数据；客服问题必须结合客服总盘、日趋势、账号表现和店铺成交，不要只复述客服销售额。"
                "已确认原因必须能在 mcp_results 的字段中直接核对，不得创造‘GMV转化率’等结果中不存在的复合指标。"
                "要把某域写成‘本期变化的已确认原因’，必须有该域当前/上期对比、同口径桥接或明确事件时间对照；只有当前期横向高低（例如某渠道当前转化率较低）时，只能写为‘待验证方向/当前优先排查项’，不能作为成交下降的已确认原因。"
                "推广预算建议必须优先使用 promotion_campaigns 的同场景本期/上期比较：没有同口径趋势时，只能建议补充趋势或做限额测试；即便 ROI 提升，也只能称为‘可进入小额阶梯测试’，不能直接称为值得加预算、盈利或高产出。本期 ROI 上升且花费下降只是一项描述性变化，不能据此推断边际效率、可扩量空间、价格弹性或因果增量；这些只能在限额测试后依据结果判断。"
                "明细数量少于汇总数量时，先写口径/覆盖待核对，不能直接建议扩大活动覆盖；只有 coverage.no_data_datasets 明确标记时才能写平台无数据，否则写本轮未查询或待补采。"
                "每个动作写清对象、优先级、负责人或执行角色、验证指标、观察窗口和预期影响；缺失数据要明确写待补采或平台无数据。"
                "当事实摘要已经能计算支付转化率或客单价时，直接采用摘要的 current/previous，不要从不同数据集自行拼接另一个总盘口径。"
                "遇到 U先、U 先、试用回购或派样回购问题，必须优先使用 utry.get_repurchase_diagnosis 和 U先复购/派样明细；不得声称 U先数据集不存在。"
                "U先回购表的 30/90/365 日指标是按业务日保存的滚动快照：总盘只读最新业务日，趋势按日比较，禁止跨日求和。"
                "U先回购UV是商品行口径，跨商品可能重复；没有首批派样 cohort 分母时禁止计算或虚构回购率，只能报告回购UV、金额、UV价值、商品贡献和待补的分母。"
                "U先商品数、绑定正装数、未绑定数、券/礼金配置数和 Top 商品贡献必须逐字采用结构化字段或做可复核算术；例如未绑定数只能用 product_count-bound_regular_product_count，禁止凭 Top 列表猜测或改写数量。"
                "模型回答中的 U先商品数量、金额、比例和变化必须优先引用 utry.get_repurchase_diagnosis 的 current/comparisons 字段；若结构化字段与文字推导冲突，以字段为准并明确待核对，不要自行改写。"
            )
        return base + "\n\n" + _ecommerce_methodology()

    @staticmethod
    def _config() -> AIConfig:
        # Keep the provider testable when callers monkeypatch its legacy settings object.
        if settings.__class__.__module__ != "app.core.config":
            return AIConfig(
                base_url=settings.ai_base_url,
                api_path=settings.ai_api_path,
                api_key=settings.ai_api_key,
                model=settings.ai_model,
                timeout_seconds=settings.ai_timeout_seconds,
            )
        return get_ai_config()

    @property
    def configured(self) -> bool:
        return self._config().configured

    @property
    def endpoint(self) -> str:
        return self._config().endpoint

    @property
    def model(self) -> str:
        return self._config().model

    def test_connection(self) -> dict[str, object]:
        config = self._config()
        if not config.configured:
            raise AIProviderError("AI API Key 尚未配置")
        started = time.perf_counter()
        payload = {
            "model": config.model,
            "temperature": 0,
            # Agnes may spend a few tokens in reasoning_content before the
            # visible answer. Keep enough budget for a short visible reply.
            "max_tokens": 32,
            "messages": [
                {"role": "system", "content": "你是连通性测试助手。不要解释，只输出 OK。"},
                {"role": "user", "content": "仅输出 OK。"},
            ],
        }
        try:
            response = httpx.post(
                config.endpoint,
                headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=config.timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            content = body.get("choices", [{}])[0].get("message", {}).get("content")
            reply = str(content).strip() if content else ""
            return {
                "ok": True,
                "model": config.model,
                "status_code": response.status_code,
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                "reply": reply or "连接已成功，模型未返回可展示文本",
            }
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300] if exc.response is not None else str(exc)
            raise AIProviderError(f"AI 服务返回 HTTP {exc.response.status_code}: {detail}") from exc
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise AIProviderError(f"AI 连通性测试失败: {exc}") from exc

    def generate_answer(
        self,
        *,
        question: str,
        diagnosis: Diagnosis,
        evidence: list[dict],
        mcp_results: list[dict] | None = None,
        context: dict | None = None,
    ) -> str:
        if not self.configured:
            raise AIProviderError("Agnes API key is not configured")

        analysis_context = dict(context or {})
        recent_messages = analysis_context.pop("recent_messages", [])
        messages = [
            {
                "role": "system",
                "content": self._system_prompt(report_mode=bool(analysis_context.get("report_type")), analysis_mode=bool(analysis_context.get("analysis_mode"))),
            }
        ]
        if isinstance(recent_messages, list):
            for item in recent_messages[-6:]:
                if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
                    continue
                content = str(item.get("text") or "").strip()
                if content:
                    messages.append({"role": item["role"], "content": content[:4000]})
        messages.append(
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": question,
                        "diagnosis": diagnosis.model_dump(mode="json"),
                        "evidence": evidence,
                        # The model narrates a deterministic calculation;
                        # it receives the structured result and its limits
                        # so it cannot fill gaps from prose alone.
                        "mcp_results": mcp_results or [],
                        "analysis_context": analysis_context,
                    },
                    ensure_ascii=False,
                ),
            }
        )
        payload = {
            "model": self._config().model,
            "temperature": 0.2,
            "max_tokens": 3500,
            "messages": messages,
        }
        try:
            response = httpx.post(
                self.endpoint,
                headers={"Authorization": f"Bearer {self._config().api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=self._config().timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            content = body.get("choices", [{}])[0].get("message", {}).get("content")
            if not content:
                raise AIProviderError("Agnes returned an empty answer")
            return str(content).strip()
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise AIProviderError(f"Agnes request failed: {exc}") from exc

    def stream_answer(
        self,
        *,
        question: str,
        diagnosis: Diagnosis,
        evidence: list[dict],
        mcp_results: list[dict] | None = None,
        context: dict | None = None,
    ) -> Iterator[str]:
        """Yield model text deltas from an OpenAI-compatible SSE response."""
        if not self.configured:
            raise AIProviderError("Agnes API key is not configured")

        analysis_context = dict(context or {})
        recent_messages = analysis_context.pop("recent_messages", [])
        messages = [
            {
                "role": "system",
                "content": self._system_prompt(report_mode=bool(analysis_context.get("report_type")), analysis_mode=bool(analysis_context.get("analysis_mode"))),
            }
        ]
        if isinstance(recent_messages, list):
            for item in recent_messages[-6:]:
                if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
                    continue
                content = str(item.get("text") or "").strip()
                if content:
                    messages.append({"role": item["role"], "content": content[:4000]})
        messages.append({
            "role": "user",
            "content": json.dumps(
                {
                    "question": question,
                    "diagnosis": diagnosis.model_dump(mode="json"),
                    "evidence": evidence,
                    "mcp_results": mcp_results or [],
                    "analysis_context": analysis_context,
                },
                ensure_ascii=False,
            ),
        })
        config = self._config()
        payload = {"model": config.model, "temperature": 0.2, "max_tokens": 3500, "stream": True, "messages": messages}
        try:
            with httpx.stream(
                "POST",
                self.endpoint,
                headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=config.timeout_seconds,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    data = line[5:].strip() if line.startswith("data:") else line.strip()
                    if data == "[DONE]":
                        break
                    try:
                        body = json.loads(data)
                    except (TypeError, ValueError):
                        continue
                    choices = body.get("choices") or []
                    if not choices:
                        continue
                    delta = (choices[0].get("delta") or {}).get("content") or (choices[0].get("message") or {}).get("content")
                    if delta:
                        yield str(delta)
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise AIProviderError(f"Agnes streaming request failed: {exc}") from exc
