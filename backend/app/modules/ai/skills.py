from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Callable

from app.modules.ai.schemas import (
    ArtifactSpec,
    Diagnosis,
    DiagnosisFinding,
    MCPEnvelope,
    RecommendedAction,
    SkillDescriptor,
    SkillToolStep,
)


@dataclass(frozen=True)
class RuntimeSkill:
    descriptor: SkillDescriptor
    keywords: tuple[str, ...]
    diagnose: Callable[..., Diagnosis]


SKILL_ROOT = Path(__file__).resolve().parents[3] / "skills"


def _runtime_skill(
    name: str,
    diagnose: Callable[..., Diagnosis],
    *,
    accepts_inputs: bool = False,
) -> RuntimeSkill:
    manifest_path = SKILL_ROOT / name / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw_workflow = manifest.get("workflow") or [{"tool": tool} for tool in manifest.get("tools", [])]
    workflow = [SkillToolStep.model_validate(item) for item in raw_workflow]
    return RuntimeSkill(
        descriptor=SkillDescriptor(
            name=manifest["name"],
            display_name=manifest["display_name"],
            description=manifest["description"],
            version=manifest["version"],
            domains=manifest.get("domains", []),
            tools=[step.tool for step in workflow],
            workflow=workflow,
            enabled=manifest.get("enabled", True),
        ),
        keywords=tuple(manifest.get("keywords", [])),
        diagnose=(
            (lambda results, inputs=None: diagnose(results, inputs or {}))
            if accepts_inputs
            else (lambda results, _inputs=None: diagnose(results))
        ),
    )


def _general_chat_diagnosis(results: list[MCPEnvelope], inputs: dict[str, Any]) -> Diagnosis:
    """Return a safe no-tool reply for greetings and meta questions."""
    _ = results
    _ = inputs
    summary = "你可以直接问我库存、成交、商品、流量或推广问题。"
    return Diagnosis(
        headline="你好，我在",
        summary=summary,
        findings=[],
        actions=[],
        analysis_scope={"kind": "chat"},
        confidence="high",
        assumptions=[],
        next_questions=[
            "查一下大鱼 M 码库存",
            "为什么最近成交下降？",
            "哪些推广场景值得加预算？",
        ],
    )


def _metric(result: MCPEnvelope, metric_id: str):
    return next((item for item in result.metrics if item.id == metric_id), None)


def _change(result: MCPEnvelope, metric_id: str) -> float | None:
    item = _metric(result, metric_id)
    value = item.comparison.get("change_percent") if item else None
    return float(value) if value is not None else None


def _overview_diagnosis(results: list[MCPEnvelope]) -> Diagnosis:
    result = next((item for item in results if item.tool == "data.compare_periods"), results[0])
    summary_result = next((item for item in results if item.tool == "overview.get_store_summary"), None)
    paid_change = _change(result, "gmv")
    if paid_change is None:
        paid_change = _change(result, "paid_amount")
    visitor_change = _change(result, "visitors")
    buyer_change = _change(result, "buyers")
    conversion_change = _change(result, "conversion_rate")
    comparisons = result.data.get("comparisons", {})
    current_aggregates = (result.data.get("current") or {}).get("aggregates", {})
    previous_aggregates = (result.data.get("previous") or {}).get("aggregates", {})

    def derived_rate(values: dict[str, Any], numerator: str, denominator: str) -> float | None:
        denominator_value = float(values.get(denominator) or 0)
        return float(values.get(numerator) or 0) / denominator_value if denominator_value else None

    current_conversion = derived_rate(current_aggregates, "buyers", "visitors")
    previous_conversion = derived_rate(previous_aggregates, "buyers", "visitors")
    if conversion_change is None and current_conversion is not None and previous_conversion:
        conversion_change = (current_conversion - previous_conversion) / abs(previous_conversion) * 100
    current_unit_price = derived_rate(current_aggregates, "gmv", "buyers")
    previous_unit_price = derived_rate(previous_aggregates, "gmv", "buyers")
    unit_price_change = (
        (current_unit_price - previous_unit_price) / abs(previous_unit_price) * 100
        if current_unit_price is not None and previous_unit_price else None
    )
    findings: list[DiagnosisFinding] = []
    actions: list[RecommendedAction] = []

    if result.status == "partial":
        findings.append(DiagnosisFinding(level="warning", title="数据覆盖不完整", detail="当前诊断只能作为方向判断，缺失日期不能按 0 参与经营结论。"))
        actions.append(RecommendedAction(priority="P0", title="先补齐缺失数据", detail="在数据完整性页面补采未覆盖日期，再重新执行经营诊断。", owner="数据运营", validation="缺失日期清零后重新比较"))

    if paid_change is not None and paid_change <= -10:
        if visitor_change is not None and abs(visitor_change) < 5 and conversion_change is not None and conversion_change < -5:
            current_conversion_text = f"{current_conversion * 100:.2f}%" if current_conversion is not None else "--"
            previous_conversion_text = f"{previous_conversion * 100:.2f}%" if previous_conversion is not None else "--"
            findings.append(DiagnosisFinding(level="critical", title="成交下降主要由支付转化变差导致", detail=f"支付金额环比 {paid_change:.1f}%，访客仅变化 {visitor_change:.1f}%；支付转化率由 {previous_conversion_text} 降至 {current_conversion_text}，环比 {conversion_change:.1f}%。", metric_ids=["paid_amount", "visitors", "conversion_rate"]))
            if unit_price_change is not None:
                findings.append(DiagnosisFinding(
                    level="positive" if unit_price_change >= 0 else "warning",
                    title="客单价不是本次主要拖累" if unit_price_change >= 0 else "客单价同步形成拖累",
                    detail=f"客单价由 {float(previous_unit_price or 0):.2f} 元变为 {float(current_unit_price or 0):.2f} 元，环比 {unit_price_change:+.1f}%；当前应先解决转化掉点。",
                    metric_ids=["customer_unit_price", "paid_amount"],
                ))
            actions.extend([
                RecommendedAction(priority="P0", title="按商品结构定位转化掉点", detail="按系列 → 类型 → 商品对比支付转化、访客、价格带和退款，先找出下降贡献最大的商品组。", owner="商品运营", validation="定位前三个转化下降贡献项，并确认其访客规模足够"),
                RecommendedAction(priority="P1", title="核对渠道与人群承接", detail="比较自然、推广、直播和会员标签下的转化变化；推广花费下降只能作为待验证信号，不能直接推出恢复预算。", owner="流量运营", validation="找到转化下降集中的来源或确认各来源同步下降"),
                RecommendedAction(priority="P2", title="复核库存、优惠与详情变化", detail="针对 P0 锁定的商品检查库存、价格、优惠门槛、详情首屏、评价和客服响应。", owner="商品运营", validation="修正后连续 3 天支付转化率和支付买家回升"),
            ])
        elif visitor_change is not None and visitor_change <= -10:
            findings.append(DiagnosisFinding(level="critical", title="成交下降伴随流量规模收缩", detail=f"支付金额环比 {paid_change:.1f}%，访客环比 {visitor_change:.1f}%。", metric_ids=["paid_amount", "visitors"]))
            actions.append(RecommendedAction(priority="P0", title="定位流量缺口", detail="下钻流量来源，区分自然流量、付费流量和回访流量的减少来源。", validation="找出贡献下降最大的前三个来源"))
        else:
            findings.append(DiagnosisFinding(level="warning", title="支付金额明显下降", detail=f"支付金额环比 {paid_change:.1f}%，需要继续结合流量和商品结构定位。", metric_ids=["paid_amount"]))
            actions.append(RecommendedAction(priority="P0", title="下钻流量与商品结构", detail="先比较流量来源、主销商品和转化承接，区分流量问题与成交效率问题。", validation="定位前三个下降贡献来源"))
    elif paid_change is not None and paid_change >= 10:
        findings.append(DiagnosisFinding(level="positive", title="成交增长明显", detail=f"支付金额环比增长 {paid_change:.1f}%，应识别增长来源并判断是否可持续。", metric_ids=["paid_amount"]))
        actions.append(RecommendedAction(priority="P1", title="复盘增量来源", detail="拆解商品、流量和推广贡献，保留可复制动作，避免将活动脉冲误判为长期增长。", validation="确认前三个增量来源及其转化效率"))
    else:
        findings.append(DiagnosisFinding(level="info", title="成交未触发显著波动预警", detail="当前周期核心成交变化未超过默认 10% 预警阈值。", metric_ids=["paid_amount"]))
        actions.append(RecommendedAction(priority="P1", title="保持日常监控", detail="继续观察支付金额、访客、支付转化率和库存变化；若任一核心指标连续两日恶化，再下钻商品与流量。", owner="运营", validation="核心指标不连续恶化"))

    if buyer_change is not None and buyer_change <= -10 and not any("支付买家" in item.title for item in findings):
        findings.append(DiagnosisFinding(level="warning", title="支付买家减少", detail=f"支付买家环比 {buyer_change:.1f}%，需关注转化和新老客结构。", metric_ids=["buyers"]))

    headline = findings[0].title
    summary = findings[0].detail
    if summary_result:
        summary_data = summary_result.data.get("summary", {})
        total_cost = summary_data.get("total_cost")
        fee_ratio = summary_data.get("fee_ratio")
        findings.append(DiagnosisFinding(level="info", title="已知营销费用与费比已纳入判断", detail=f"支付金额 {float(summary_data.get('paid_amount') or 0):,.0f}，退款 {float(summary_data.get('refund_amount') or 0):,.0f}，已知营销费用 {float(total_cost):,.0f}，占支付金额 {float(fee_ratio) * 100:.2f}%；该字段不等于经营总成本。" if total_cost is not None and fee_ratio is not None else "营销费用字段未完整返回，费比保持为空，不用 0 代替未知。", metric_ids=["total_cost", "fee_ratio"]))
        if summary_data.get("net_paid_amount") is not None:
            findings.append(DiagnosisFinding(level="info", title="退款后口径已拆开", detail=f"支付金额 {float(summary_data.get('paid_amount') or 0):,.0f}，退款 {float(summary_data.get('refund_amount') or 0):,.0f}，净支付 {float(summary_data.get('net_paid_amount') or 0):,.0f}。", metric_ids=["net_paid_amount"]))
    metrics = [{"指标": item.label, "当前值": item.value, "单位": item.unit, "环比%": item.comparison.get("change_percent")} for item in result.metrics]
    if summary_result:
        summary_data = summary_result.data.get("summary", {})
        metrics.extend([{"指标": "已知营销费用", "当前值": summary_data.get("total_cost"), "单位": "CNY", "环比%": None}, {"指标": "营销费比", "当前值": summary_data.get("fee_ratio"), "单位": "ratio", "环比%": None}])
    if current_conversion is not None:
        metrics.append({"指标": "支付转化率", "当前值": current_conversion * 100, "单位": "%", "环比%": conversion_change})
    if current_unit_price is not None:
        metrics.append({"指标": "客单价", "当前值": current_unit_price, "单位": "CNY", "环比%": unit_price_change})
    return Diagnosis(headline=headline, summary=summary, findings=findings, actions=actions, artifacts=[ArtifactSpec(type="metric_table", title="经营核心指标", rows=metrics)])


def _traffic_diagnosis(results: list[MCPEnvelope]) -> Diagnosis:
    result = results[0]
    sources = result.data.get("sources", [])
    if not sources:
        sources = result.data.get("rows", [])
        for item in sources:
            item["source_name"] = item.get("source")
            item["paid_amount"] = item.get("gmv")
            visitors = float(item.get("visitors") or 0)
            buyers = float(item.get("buyers") or 0)
            paid_amount = float(item.get("gmv") or 0)
            item["conversion_rate"] = buyers / visitors * 100 if visitors else 0
            item["uv_value"] = paid_amount / visitors if visitors else 0
    findings: list[DiagnosisFinding] = []
    actions: list[RecommendedAction] = []
    if not sources:
        return Diagnosis(headline="所选区间没有流量来源数据", summary="需要先确认平台是否返回数据或完成补采。", findings=[DiagnosisFinding(level="warning", title="流量数据不可用", detail="当前没有可用于来源分析的记录。")], actions=[RecommendedAction(priority="P0", title="检查流量来源采集", detail="查看数据完整性与最近采集错误。", owner="数据运营")])

    visitors = sum(float(item.get("visitors", 0)) for item in sources)
    buyers = sum(float(item.get("buyers", 0)) for item in sources)
    weighted_conversion = buyers / visitors * 100 if visitors else 0
    top = max(sources, key=lambda item: float(item.get("paid_amount", 0)))
    weak = sorted(
        [item for item in sources if float(item.get("visitors", 0)) >= visitors * 0.08 and float(item.get("conversion_rate", 0)) < weighted_conversion * 0.75],
        key=lambda item: float(item.get("visitors", 0)), reverse=True,
    )
    efficient = sorted(sources, key=lambda item: float(item.get("uv_value", 0)), reverse=True)[:3]
    findings.append(DiagnosisFinding(level="info", title=f"{top.get('source_name')} 是当前成交贡献最高的来源", detail=f"支付金额 {float(top.get('paid_amount', 0)):,.0f}，转化率 {float(top.get('conversion_rate', 0)):.2f}%，UV 价值 {float(top.get('uv_value', 0)):.2f}。"))
    if weak:
        item = weak[0]
        findings.append(DiagnosisFinding(level="warning", title=f"{item.get('source_name')} 流量规模较大但转化偏低", detail=f"访客 {float(item.get('visitors', 0)):,.0f}，转化率 {float(item.get('conversion_rate', 0)):.2f}%，整体加权转化率 {weighted_conversion:.2f}%。"))
        actions.append(RecommendedAction(priority="P0", title="优化低效来源的落地承接", detail=f"针对 {item.get('source_name')} 检查进入商品、首屏卖点、价格优惠和人群匹配，不直接扩大该来源流量。", validation="该来源转化率接近整体水平"))
    if efficient:
        names = "、".join(str(item.get("source_name")) for item in efficient)
        actions.append(RecommendedAction(priority="P1", title="验证高价值来源扩量空间", detail=f"优先对 {names} 做小幅流量增量测试，同时监控 UV 价值是否衰减。", validation="扩量后 UV 价值下降不超过 10%"))
    rows = [{"来源": item.get("source_name"), "访客": item.get("visitors"), "支付金额": item.get("paid_amount"), "转化率%": item.get("conversion_rate"), "UV价值": item.get("uv_value")} for item in sources]
    return Diagnosis(headline=findings[0].title, summary=findings[0].detail, findings=findings, actions=actions, artifacts=[ArtifactSpec(type="matrix", title="流量来源质量矩阵", rows=rows)])


def _market_keyword_is_relevant(keyword: Any, summary: dict[str, Any]) -> bool:
    """Reject obvious cross-category words before turning platform samples into actions.

    SYCM can occasionally return noisy adjacent-category samples. The guard is
    deliberately conservative: it only suppresses a recommendation when the
    current top item clearly identifies the diaper category and the candidate
    is an unmistakably unrelated category. Raw platform rows remain available
    in the MCP response for audit.
    """
    text = str(keyword or "").strip()
    top_item = str(summary.get("top_item") or "")
    diaper_anchors = ("纸尿裤", "尿不湿", "拉拉裤", "婴儿", "宝宝", "尿片")
    unrelated = ("猫砂", "洗发水", "包包", "床垫", "内裤", "裤子")
    if not text or not top_item or not any(token in top_item for token in diaper_anchors):
        return True
    return not any(token in text for token in unrelated)


def _market_diagnosis(results: list[MCPEnvelope]) -> Diagnosis:
    """Turn platform market observations into bounded business hypotheses."""
    result = next((item for item in reversed(results) if item.tool == "market.get_insights"), results[-1])
    keyword_result = next((item for item in results if item.tool == "market.get_keyword_opportunities"), None)
    movement_result = next((item for item in results if item.tool == "market.get_competitor_movements"), None)
    match_result = next((item for item in results if item.tool == "market.match_store_products"), None)
    data = result.data or {}
    summary = data.get("summary") or {}
    rankings = data.get("rankings") or []
    keywords = data.get("keywords") or []
    raw_opportunities = ((keyword_result.data or {}).get("opportunities") if keyword_result else None) or data.get("opportunities") or []
    opportunities = [item for item in raw_opportunities if _market_keyword_is_relevant(item.get("keyword"), summary)]
    competitive_signals = ((movement_result.data or {}).get("movements") if movement_result else None) or data.get("competitive_signals") or []
    store_signals = ((match_result.data or {}).get("signals") if match_result else None) or []
    keyword_segments = data.get("keyword_segments") or []
    findings: list[DiagnosisFinding] = []
    actions: list[RecommendedAction] = []

    if result.status == "no_data" or (not rankings and not keywords):
        detail = "当前区间没有市场排行或搜索词快照，先区分平台无数据与市场采集缺失。"
        return Diagnosis(
            headline="没有可用的市场观察数据",
            summary=detail,
            findings=[DiagnosisFinding(level="warning", title="市场数据不可用", detail=detail)],
            actions=[RecommendedAction(priority="P0", title="检查市场快照采集", detail="调用数据覆盖审计，补采实际缺失日期；平台确认无数据无需重复采集。", owner="数据运营", validation="市场排行或搜索词覆盖恢复")],
            artifacts=[],
            causal_boundary="市场排行和搜索词是平台相对观察，不代表本店铺成交或因果增量。",
        )

    rank_coverage = next((item for item in result.coverage.missing_dates), None)
    if result.coverage.missing_dates or result.coverage.partial_datasets:
        missing = "、".join(result.coverage.missing_dates[:8]) or "部分数据集"
        findings.append(DiagnosisFinding(level="warning", title="市场观察存在覆盖缺口", detail=f"缺失 {missing}；缺失日期没有按 0 补齐，当前结论仅作方向判断。"))
        actions.append(RecommendedAction(priority="P0", title="补采市场缺失日期", detail="只对未采集日期重跑市场排行/搜索词采集，平台确认无数据日期不重复采集。", owner="数据运营", validation="市场数据覆盖完整或明确为平台无数据"))

    top_shop = summary.get("top_shop")
    top_item = summary.get("top_item")
    top_keyword = summary.get("top_keyword")
    top_content = summary.get("top_content")
    if top_shop or top_item or top_content:
        anchor = "；".join(item for item in [f"头部店铺：{top_shop}" if top_shop else "", f"头部商品：{top_item}" if top_item else "", f"头部内容：{top_content}" if top_content else ""] if item)
        findings.append(DiagnosisFinding(level="info", title="已识别当前市场头部锚点", detail=f"{anchor}。这些是平台排行样本，不等于本店铺的支付金额。"))
        actions.append(RecommendedAction(priority="P1", title="建立头部竞品监控清单", detail="将头部店铺、商品及其价格/内容卖点与本店主销商品并列跟踪，先做小范围选品或素材验证。", owner="市场运营", validation="竞品监控覆盖稳定且验证商品点击率/转化率改善"))

    rising = [item for item in competitive_signals if item.get("direction") == "rising"]
    falling = [item for item in competitive_signals if item.get("direction") == "falling"]
    if rising:
        sample = "、".join(str(item.get("name")) for item in rising[:3])
        findings.append(DiagnosisFinding(level="positive", title="市场出现上升中的竞品或内容样本", detail=f"重点样本：{sample}。排名变化只能说明相对位置变化，不等于成交增量。"))
        actions.append(RecommendedAction(priority="P1", title="拆解上升样本的可复制因素", detail="按商品卖点、价格/规格、内容主题和投放承接拆解上升样本，选择一个变量做小范围对照测试。", owner="市场与商品运营", validation="测试样本点击率、加购率和支付转化率优于当前基线"))
    if falling:
        sample = "、".join(str(item.get("name")) for item in falling[:3])
        findings.append(DiagnosisFinding(level="warning", title="部分竞品或内容样本排名下滑", detail=f"重点样本：{sample}。下滑不是本店机会的直接证明，需要结合本店对应品类流量和库存验证。"))

    filtered_keyword_count = sum(1 for item in keywords if not _market_keyword_is_relevant(item.get("keyword"), summary))
    if filtered_keyword_count:
        findings.append(DiagnosisFinding(level="warning", title="已过滤明显跨类目机会词", detail=f"原始搜索词中有 {filtered_keyword_count} 个词与当前头部商品类目不一致，已保留在原始 MCP 数据中但不生成投放或标题建议。"))
    if keywords:
        ranked_keywords = sorted(keywords, key=lambda item: float(item.get("opportunity_score") or -1), reverse=True)
        candidate = next((item for item in ranked_keywords if item.get("keyword") and _market_keyword_is_relevant(item.get("keyword"), summary)), None)
        if candidate:
            findings.append(DiagnosisFinding(level="positive", title=f"搜索需求出现可验证机会词：{candidate.get('keyword')}", detail=f"点击率 {candidate.get('click_rate') if candidate.get('click_rate') is not None else '暂无'}%；支付转化区间 {candidate.get('pay_conversion_rate') or '暂无'}。机会分仅用于排序，不代表精确成交。"))
            actions.append(RecommendedAction(priority="P1", title="小预算验证机会词", detail=f"把“{candidate.get('keyword')}”加入标题/详情卖点和投放词包，先控制预算观察点击到支付转化，不直接全量扩量。", owner="商品与投放运营", validation="机会词点击率、支付转化率和加购率连续 3～7 天改善"))
    elif top_keyword:
        findings.append(DiagnosisFinding(level="info", title="已识别头部搜索需求", detail=f"当前头部搜索词为“{top_keyword}”，但缺少足够字段计算机会分。"))

    if keyword_segments:
        strongest_segment = max(keyword_segments, key=lambda item: float(item.get("average_opportunity_score") or -1))
        findings.append(DiagnosisFinding(level="info", title=f"{strongest_segment.get('keyword_type')} 词层的平均机会分最高", detail=f"该层平均点击率 {strongest_segment.get('average_click_rate') or '暂无'}%，平均支付转化 {strongest_segment.get('average_pay_conversion_rate') or '暂无'}%，高机会词 {strongest_segment.get('high_opportunity_count') or 0} 个；仅作词层筛选，不替代本店实测。"))
        actions.append(RecommendedAction(priority="P2", title="按词层配置不同运营动作", detail="核心词优先守住标题和自然搜索，趋势词先做内容/小预算测试，修饰词用于卖点组合；每层都回填本店点击、加购、支付和库存覆盖。", owner="搜索与内容运营", validation="词层动作执行后 3～7 天观察搜索流量和支付转化变化"))

    matched_store_signals = [item for item in store_signals if item.get("relationship") != "no_match"]
    unmatched_store_signals = [item for item in store_signals if item.get("relationship") == "no_match"]
    weak_store_signals = [item for item in matched_store_signals if item.get("relationship") == "market_signal_store_weak"]
    if matched_store_signals:
        sample = "、".join(str(item.get("keyword")) for item in matched_store_signals[:3])
        findings.append(DiagnosisFinding(level="info", title="市场信号已与本店商品经营数据对照", detail=f"已找到本店商品承接的市场词：{sample}。这只是平台需求与本店现状的同向/弱承接观察，不证明新增成交。"))
    if weak_store_signals:
        sample = "、".join(str(item.get("keyword")) for item in weak_store_signals[:3])
        findings.append(DiagnosisFinding(level="warning", title="部分市场需求在本店承接偏弱", detail=f"{sample} 已匹配到本店商品，但所选区间访客或支付承接偏弱；不建议直接扩预算。"))
        actions.append(RecommendedAction(priority="P0", title="先修复市场词对应商品承接", detail="依次核对标题/详情相关性、价格、评价、库存和支付转化，再做单变量小预算测试。", owner="商品与投放运营", validation="对应商品搜索访客、点击率、加购率、支付转化率连续 3～7 天改善"))
    if unmatched_store_signals:
        sample = "、".join(str(item.get("keyword")) for item in unmatched_store_signals[:3])
        findings.append(DiagnosisFinding(level="info", title="部分市场词未匹配到本店商品", detail=f"未匹配样本：{sample}。系统保持 no_match，不据此虚构选品或投放结论。"))

    rank_rows = [
        {"类型": item.get("rank_type"), "排名": item.get("rank_no"), "名称": item.get("shop_name") or item.get("entity_name") or item.get("keyword"), "支付买家区间": item.get("paid_buyers_range"), "访客区间": item.get("visitors_range"), "排名变化": item.get("rank_change")}
        for item in rankings[:30]
    ]
    keyword_rows = [
        {"搜索词": item.get("keyword"), "类型": item.get("keyword_type"), "热度区间": item.get("popularity_range"), "点击率%": item.get("click_rate"), "支付转化区间": item.get("pay_conversion_rate"), "机会分": item.get("opportunity_score")}
        for item in keywords[:30]
    ]
    artifacts = []
    if rank_rows:
        artifacts.append(ArtifactSpec(type="matrix", title="平台头部竞争样本", rows=rank_rows))
    if keyword_rows:
        artifacts.append(ArtifactSpec(type="matrix", title="搜索需求与机会词", rows=keyword_rows))
    if opportunities:
        artifacts.append(ArtifactSpec(type="matrix", title="可验证市场机会", rows=opportunities[:12]))
    if competitive_signals:
        artifacts.append(ArtifactSpec(type="matrix", title="竞品与内容异动", rows=[{
            "类型": item.get("rank_type"), "对象": item.get("name"), "方向": item.get("direction"),
            "当前排名": item.get("current_rank"), "排名变化": item.get("rank_change"), "证据": item.get("evidence"),
        } for item in competitive_signals[:16]]))
    if keyword_segments:
        artifacts.append(ArtifactSpec(type="matrix", title="搜索词分层效率", rows=[{
            "词层": item.get("keyword_type"), "词数": item.get("keyword_count"), "头部词": item.get("top_keyword"),
            "平均点击率%": item.get("average_click_rate"), "平均支付转化率%": item.get("average_pay_conversion_rate"),
            "平均机会分": item.get("average_opportunity_score"), "高机会词数": item.get("high_opportunity_count"),
        } for item in keyword_segments]))
    if store_signals:
        artifacts.append(ArtifactSpec(type="matrix", title="市场信号与本店商品匹配", rows=[{
            "市场词": item.get("keyword"), "词类": item.get("keyword_type"), "机会分": item.get("opportunity_score"),
            "匹配状态": item.get("relationship"), "匹配商品数": len(item.get("matched_products") or []),
            "本店商品": "、".join(str(product.get("product_name") or product.get("product_id")) for product in (item.get("matched_products") or [])[:3]),
        } for item in store_signals[:20]]))
    if not findings:
        findings.append(DiagnosisFinding(level="info", title="市场观察已完成", detail=f"返回 {len(rankings)} 条排行和 {len(keywords)} 条搜索词样本。"))
    return Diagnosis(
        headline=findings[0].title,
        summary=findings[0].detail,
        findings=findings,
        actions=actions,
        artifacts=artifacts,
        causal_boundary="市场排行、热度和平台转化区间属于平台观察或归因信号，不等于本店铺支付金额、利润或因果增量；需用本店商品/流量数据做验证。",
    )


def _promotion_scene_periods(results: list[MCPEnvelope]) -> tuple[bool, list[dict[str, Any]]]:
    """Align promotion scenes across two complete periods for budget tests."""
    comparison = next(
        (
            item for item in results
            if item.tool == "data.compare_periods"
            and str(item.data.get("dataset") or "") == "promotion_campaigns"
        ),
        None,
    )
    if comparison is None or not comparison.data.get("comparable"):
        return False, []

    current_rows = (comparison.data.get("current") or {}).get("rows") or []
    previous_rows = (comparison.data.get("previous") or {}).get("rows") or []
    current_by_scene = {str(item.get("scene") or "").strip(): item for item in current_rows if str(item.get("scene") or "").strip()}
    previous_by_scene = {str(item.get("scene") or "").strip(): item for item in previous_rows if str(item.get("scene") or "").strip()}

    def number(row: dict[str, Any], key: str) -> float | None:
        value = row.get(key)
        try:
            return float(value) if value is not None and value != "" else None
        except (TypeError, ValueError):
            return None

    def roi(row: dict[str, Any]) -> float | None:
        reported = number(row, "roi")
        if reported is not None:
            return reported
        spend = number(row, "spend")
        gmv = number(row, "gmv")
        return gmv / spend if spend and gmv is not None else None

    def change(current: float | None, previous: float | None) -> float | None:
        if current is None or previous in (None, 0):
            return None
        return (current - previous) / abs(previous) * 100

    rows: list[dict[str, Any]] = []
    for scene in sorted(set(current_by_scene) | set(previous_by_scene), key=lambda name: number(current_by_scene.get(name, {}), "spend") or 0, reverse=True):
        current = current_by_scene.get(scene, {})
        previous = previous_by_scene.get(scene, {})
        current_spend, previous_spend = number(current, "spend"), number(previous, "spend")
        current_gmv, previous_gmv = number(current, "gmv"), number(previous, "gmv")
        current_roi, previous_roi = roi(current), roi(previous)
        roi_delta = current_roi - previous_roi if current_roi is not None and previous_roi is not None else None
        can_test_scale = bool(
            current_spend and previous_spend
            and current_roi is not None and previous_roi is not None
            and current_roi >= 2
            and current_roi >= previous_roi * 0.9
        )
        decision = (
            "可小额扩量验证" if can_test_scale
            else "先控量复查" if current_roi is not None and (current_roi < 2 or (roi_delta is not None and roi_delta < 0))
            else "待补同口径趋势"
        )
        rows.append({
            "scene": scene,
            "current_spend": current_spend,
            "previous_spend": previous_spend,
            "spend_change_percent": change(current_spend, previous_spend),
            "current_gmv": current_gmv,
            "previous_gmv": previous_gmv,
            "gmv_change_percent": change(current_gmv, previous_gmv),
            "current_roi": current_roi,
            "previous_roi": previous_roi,
            "roi_delta": roi_delta,
            "scale_test_candidate": can_test_scale,
            "decision": decision,
        })
    return bool(rows), rows


def _promotion_diagnosis(results: list[MCPEnvelope]) -> Diagnosis:
    result = next((item for item in results if item.tool in {"promotions.get_efficiency", "data.query"}), results[0])
    summary = result.data.get("summary", {})
    scenes = result.data.get("scenes", [])
    if not scenes:
        summary = result.data.get("aggregates", {})
        scenes = result.data.get("rows", [])
        for item in scenes:
            item["dimension_name"] = item.get("scene")
            item["paid_amount"] = item.get("gmv")
            spend = float(item.get("spend") or 0)
            item["roi"] = item.get("roi") if item.get("roi") is not None else float(item.get("gmv") or 0) / spend if spend else 0
    if "roi" not in summary:
        spend = float(summary.get("spend") or 0)
        summary["roi"] = float(summary.get("gmv") or 0) / spend if spend else 0
    roi = float(summary.get("roi") or 0)
    findings: list[DiagnosisFinding] = []
    actions: list[RecommendedAction] = []
    if not scenes and not result.data.get("campaigns"):
        return Diagnosis(headline="所选区间没有推广数据", summary="无法形成预算与 ROI 判断。", findings=[DiagnosisFinding(level="warning", title="推广数据不可用", detail="需要先检查推广计划采集状态。")], actions=[RecommendedAction(priority="P0", title="检查推广数据采集", detail="确认推广计划是否平台无数据或采集失败。", owner="数据运营")])
    if roi < 1:
        findings.append(DiagnosisFinding(level="critical", title="整体归因成交未覆盖推广花费", detail=f"当前推广 ROI 为 {roi:.2f}；这表示归因成交低于广告花费，不等于利润判断。", metric_ids=["promotion_roi"]))
        actions.append(RecommendedAction(priority="P0", title="暂停低效计划扩量", detail="先按场景和计划筛选 ROI 低于 1 的高花费对象，核对归因窗口、商品承接和完整成本字段后再调整。", validation="低效计划花费下降且整体归因效率不下降"))
    elif roi < 2:
        findings.append(DiagnosisFinding(level="warning", title="整体推广归因效率需要复查", detail=f"当前推广 ROI 为 {roi:.2f}；完整成本未接入，不能据此判断盈利或设置毛利线。", metric_ids=["promotion_roi"]))
    else:
        findings.append(DiagnosisFinding(level="positive", title="整体推广归因效率已汇总", detail=f"当前推广 ROI 为 {roi:.2f}，仍需识别内部低效场景并对比同场景趋势。", metric_ids=["promotion_roi"]))
    low = sorted([item for item in scenes if float(item.get("spend", 0)) > 0 and float(item.get("roi", 0)) < 1.5], key=lambda item: float(item.get("spend", 0)), reverse=True)
    if low:
        item = low[0]
        findings.append(DiagnosisFinding(level="warning", title=f"{item.get('dimension_name')} 是优先复查的低效场景", detail=f"花费 {float(item.get('spend', 0)):,.0f}，ROI {float(item.get('roi', 0)):.2f}。"))
        actions.append(RecommendedAction(priority="P0", title="下钻低效场景", detail=f"拆解 {item.get('dimension_name')} 的计划、商品、人群和关键词，先处理高花费低 ROI 对象。", validation="场景归因效率回升，且整体归因效率不下降"))
        findings.append(DiagnosisFinding(level="info", title="低效来源已具备下钻条件", detail=f"全量低效场景 {len(low)} 个；下一步应按场景→计划→商品→单元→关键词/人群分页定位，不能只看场景汇总。", metric_ids=["promotion_roi"]))
    comparable_scenes, period_rows = _promotion_scene_periods(results)
    if comparable_scenes:
        candidates = [item for item in period_rows if item["scale_test_candidate"]]
        if candidates:
            item = candidates[0]
            findings.append(DiagnosisFinding(level="positive", title="存在可小额扩量验证的场景", detail=f"{item['scene']} 本期 ROI {float(item['current_roi']):.2f}，上期 {float(item['previous_roi']):.2f}；同口径未明显恶化，可进入限额测试。", metric_ids=["promotion_roi"]))
            actions.append(RecommendedAction(priority="P1", title="对稳定场景做小额阶梯测试", detail=f"先将 {item['scene']} 日预算提高 5%-10%，同时保留其余场景预算；ROI 是归因效率，不等于利润或因果增量。", owner="投放运营", validation="连续 3-7 天边际 ROI 不低于上期的 90%，且支付转化率不下降", observation_window="3-7天", expected_impact="验证该场景是否存在可持续的归因效率扩量空间。"))
        else:
            findings.append(DiagnosisFinding(level="info", title="暂无可直接扩量的同口径场景", detail="当前场景 ROI 未同时满足相对稳定和效率门槛；先控量复查或继续观察，不直接增加预算。", metric_ids=["promotion_roi"]))
    else:
        findings.append(DiagnosisFinding(level="warning", title="推广场景趋势待补", detail="缺少本期与上期同场景的完整比较，只能按当前归因效率排序，不能直接下加预算结论。", metric_ids=["promotion_roi"]))
    if summary.get("direct_roi") is not None and summary.get("roi") is not None:
        indirect_lift = float(summary["roi"]) - float(summary["direct_roi"])
        findings.append(DiagnosisFinding(level="info", title="直接与整体归因已分开", detail=f"直接 ROI {float(summary['direct_roi']):.2f}，整体 ROI {float(summary['roi']):.2f}，间接归因贡献差 {indirect_lift:.2f}。不同归因窗口不得混算。"))
    if summary.get("ctr") is not None and summary.get("click_conversion_rate") is not None:
        findings.append(DiagnosisFinding(level="info", title="推广漏斗效率已纳入判断", detail=f"CTR {float(summary['ctr']):.2f}%，点击转化率 {float(summary['click_conversion_rate']):.2f}%，CPC {float(summary.get('cpc') or 0):.2f}，成交获客成本 {float(summary.get('buyer_cost') or 0):.2f}。"))
    rows = [{
        "场景": item.get("dimension_name"), "花费": item.get("spend"), "归因成交": item.get("paid_amount"),
        "整体ROI": item.get("roi"), "直接ROI": item.get("direct_roi"), "CTR%": item.get("ctr"),
        "CPC": item.get("cpc"), "点击转化率%": item.get("click_conversion_rate"), "加购率%": item.get("cart_rate"),
        "加购成本": item.get("cart_cost"), "获客成本": item.get("buyer_cost"), "新客占比%": item.get("new_buyer_share"),
    } for item in scenes]
    artifacts = [ArtifactSpec(type="bar_chart", title="推广场景投入产出", rows=rows)]
    if period_rows:
        artifacts.append(ArtifactSpec(type="matrix", title="推广场景同口径对比", rows=[{
            "场景": item["scene"], "本期花费": item["current_spend"], "上期花费": item["previous_spend"], "花费环比%": item["spend_change_percent"],
            "本期归因成交": item["current_gmv"], "上期归因成交": item["previous_gmv"], "归因成交环比%": item["gmv_change_percent"],
            "本期ROI": item["current_roi"], "上期ROI": item["previous_roi"], "ROI变化": item["roi_delta"], "预算动作": item["decision"],
        } for item in period_rows]))
    return Diagnosis(
        headline=findings[0].title,
        summary=findings[0].detail,
        findings=findings,
        actions=actions,
        artifacts=artifacts,
        causal_boundary="推广 ROI 为平台归因成交 ÷ 花费；缺少完整商品、履约、平台、佣金和售后成本时，不判断利润。扩量建议是限额测试，不代表已证明因果增量。",
    )


def _promotion_budget_diagnosis(results: list[MCPEnvelope], inputs: dict[str, Any]) -> Diagnosis:
    result = results[0]
    rows = result.data.get("rows", [])
    usable = []
    for item in rows:
        spend = float(item.get("spend") or 0)
        gmv = float(item.get("gmv") or 0)
        roi = item.get("roi")
        if spend <= 0 or roi is None:
            continue
        usable.append({**item, "spend": spend, "gmv": gmv, "roi": float(roi)})
    if not usable:
        return Diagnosis(
            headline="没有可用于预算拆解的历史推广数据",
            summary="无法形成可靠的场景基线，先区分平台无数据与采集缺失。",
            findings=[DiagnosisFinding(level="warning", title="预算基线不可用", detail="至少需要包含花费和归因成交的历史场景数据。")],
            actions=[RecommendedAction(priority="P0", title="补齐推广历史数据", detail="先补采 missing_dates；平台确认无数据不需要重复采集。", owner="数据运营")],
        )

    total_spend = sum(item["spend"] for item in usable)
    total_gmv = sum(item["gmv"] for item in usable)
    weighted_roi = total_gmv / total_spend if total_spend else None
    target_roi = inputs.get("target_roi")
    total_budget = inputs.get("total_budget")
    coverage_incomplete = any(
        item.coverage.missing_dates
        or item.coverage.missing_datasets
        or item.coverage.partial_datasets
        or item.coverage.failed_datasets
        for item in results
    )
    weighted_rows = []
    for item in usable:
        history_share = item["spend"] / total_spend if total_spend else 0
        efficiency_factor = 1.0
        if target_roi and target_roi > 0:
            efficiency_factor = max(0.5, min(1.5, item["roi"] / target_roi))
        raw_weight = history_share * efficiency_factor
        weighted_rows.append({**item, "history_share": history_share, "efficiency_factor": efficiency_factor, "raw_weight": raw_weight})
    weight_total = sum(item["raw_weight"] for item in weighted_rows)
    matrix = []
    allocated_budget = 0.0
    for index, item in enumerate(weighted_rows):
        recommended_share = item["raw_weight"] / weight_total if weight_total else item["history_share"]
        recommended_budget = None
        if total_budget is not None:
            if index == len(weighted_rows) - 1:
                recommended_budget = round(total_budget - allocated_budget, 2)
            else:
                recommended_budget = round(total_budget * recommended_share, 2)
                allocated_budget += recommended_budget
        estimated_gmv = round(recommended_budget * item["roi"], 2) if recommended_budget is not None and not coverage_incomplete else None
        if target_roi:
            action = "阶梯扩量" if item["roi"] >= target_roi * 1.1 else "控量复查" if item["roi"] < target_roi * 0.9 else "保持验证"
        else:
            action = "待输入目标 ROI"
        matrix.append({
            "场景": item.get("scene") or item.get("dimension_name") or "未分类",
            "历史花费占比%": round(item["history_share"] * 100, 2),
            "历史ROI": round(item["roi"], 2),
            "效率系数": round(item["efficiency_factor"], 2),
            "建议预算占比%": round(recommended_share * 100, 2),
            "建议预算": recommended_budget,
            "情景成交估算": estimated_gmv,
            "动作": action,
        })

    findings = [DiagnosisFinding(
        level="info",
        title="已形成可勾稽的场景预算基线",
        detail=f"历史总花费 {total_spend:,.0f}，加权 ROI {weighted_roi:.2f}。历史花费只用于计算结构，不会被当作新预算。",
    )]
    actions = []
    if total_budget is None:
        findings.append(DiagnosisFinding(level="warning", title="尚未提供规划总预算", detail="当前只输出建议占比，绝对预算保持为空。"))
        actions.append(RecommendedAction(priority="P0", title="补充总预算", detail="明确规划周期和总预算后，系统才能把占比换算为场景及分日金额。", owner="业务负责人"))
    if target_roi is None:
        findings.append(DiagnosisFinding(level="warning", title="尚未提供目标 ROI", detail="当前不根据效率调权，也不能判断扩量或控量边界。"))
        actions.append(RecommendedAction(priority="P0", title="补充目标 ROI 或投产线", detail="同时确认毛利、退款、佣金和服务费，避免把 ROI 当作利润。", owner="业务负责人"))
    else:
        best = max(weighted_rows, key=lambda item: item["roi"])
        weak = min(weighted_rows, key=lambda item: item["roi"])
        actions.append(RecommendedAction(priority="P1", title="对高效场景做阶梯扩量", detail=f"{best.get('scene') or '高效场景'} 历史 ROI {best['roi']:.2f}，每次小幅扩量并观察边际 ROI。", validation="扩量后 ROI 不低于目标线"))
        if weak["roi"] < target_roi * 0.9:
            actions.append(RecommendedAction(priority="P0", title="控量复查低效场景", detail=f"{weak.get('scene') or '低效场景'} 历史 ROI {weak['roi']:.2f}，先下钻计划、商品和人群再恢复预算。", validation="低效场景达到目标 ROI 的 90% 以上"))
    if coverage_incomplete:
        findings.append(DiagnosisFinding(level="warning", title="历史周期存在采集缺口", detail="缺失日期没有按 0 参与计算；情景成交估算保持为空。"))
        actions.insert(0, RecommendedAction(priority="P0", title="先补采历史缺失日期", detail="只补 missing_dates，平台 no_data 日期不重复采集。", owner="数据运营"))
    daily_result = results[1] if len(results) > 1 else None
    artifacts = [ArtifactSpec(type="matrix", title="推广预算拆解", rows=matrix)]
    if daily_result and daily_result.data.get("rows"):
        artifacts.append(ArtifactSpec(
            type="line_chart",
            title="历史投放节奏参考",
            rows=[{"日期": item.get("date"), "花费": item.get("spend"), "ROI": item.get("roi")} for item in daily_result.data["rows"]],
        ))
    headline = "推广预算已拆到场景占比" if total_budget is None else f"推广预算已按 {total_budget:,.0f} 元拆解"
    return Diagnosis(headline=headline, summary=findings[0].detail, findings=findings, actions=actions, artifacts=artifacts)


def _campaign_planning_diagnosis(results: list[MCPEnvelope], inputs: dict[str, Any]) -> Diagnosis:
    coverage_result = results[0]
    dataset_results = {item.data.get("dataset"): item for item in results[1:] if item.tool == "data.query"}
    overview = dataset_results.get("store_overview")
    traffic = dataset_results.get("traffic_sources")
    promotions = dataset_results.get("promotion_campaigns")
    products = dataset_results.get("products")
    overview_totals = overview.data.get("aggregates", {}) if overview else {}
    history_gmv = float(overview_totals.get("gmv") or 0)
    history_visitors = float(overview_totals.get("visitors") or 0)
    history_buyers = float(overview_totals.get("buyers") or 0)
    history_cvr = history_buyers / history_visitors if history_visitors else None
    history_atv = history_gmv / history_buyers if history_buyers else None
    target_gmv = inputs.get("target_gmv")
    target_uv = inputs.get("target_uv")
    target_cvr = inputs.get("target_cvr")
    target_atv = inputs.get("target_atv")
    total_budget = inputs.get("total_budget")
    target_roi = inputs.get("target_roi")

    # If the user only gives a GMV target, preserve the recent baseline CVR
    # and ATV as the first planning scenario instead of leaving the target
    # tree unusable.  The assumptions are surfaced below so this is not
    # mistaken for a guaranteed forecast.
    if target_gmv is not None:
        target_cvr = target_cvr if target_cvr is not None else history_cvr
        target_atv = target_atv if target_atv is not None else history_atv
        if target_uv is None and target_cvr and target_atv:
            target_uv = target_gmv / (target_cvr * target_atv)
        if target_cvr is None and target_uv and target_atv:
            target_cvr = target_gmv / (target_uv * target_atv)
        if target_atv is None and target_uv and target_cvr:
            target_atv = target_gmv / (target_uv * target_cvr)

    attributed_gmv_target = total_budget * target_roi if total_budget is not None and target_roi is not None else None
    non_paid_gmv_target = max(float(target_gmv) - attributed_gmv_target, 0.0) if target_gmv is not None and attributed_gmv_target is not None else None

    target_rows = [
        {"指标": "GMV", "历史基线": round(history_gmv, 2), "规划目标": target_gmv, "公式": "UV x CVR x ATV"},
        {"指标": "UV", "历史基线": round(history_visitors, 2), "规划目标": round(target_uv, 2) if target_uv is not None else None, "公式": "GMV / (CVR x ATV)"},
        {"指标": "CVR", "历史基线": round(history_cvr * 100, 2) if history_cvr is not None else None, "规划目标": round(target_cvr * 100, 2) if target_cvr is not None else None, "公式": "GMV / (UV x ATV)"},
        {"指标": "ATV", "历史基线": round(history_atv, 2) if history_atv is not None else None, "规划目标": round(target_atv, 2) if target_atv is not None else None, "公式": "GMV / (UV x CVR)"},
        {"指标": "预算", "历史基线": None, "规划目标": total_budget, "公式": "用户明确输入"},
        {"指标": "目标ROI", "历史基线": promotions.data.get("aggregates", {}).get("roi") if promotions else None, "规划目标": target_roi, "公式": "用户明确输入"},
        {"指标": "预算可承载归因GMV", "历史基线": promotions.data.get("aggregates", {}).get("gmv") if promotions else None, "规划目标": round(attributed_gmv_target, 2) if attributed_gmv_target is not None else None, "公式": "预算 x 目标 ROI；仅为推广归因情景"},
        {"指标": "非付费/重叠渠道承接GMV", "历史基线": None, "规划目标": round(non_paid_gmv_target, 2) if non_paid_gmv_target is not None else None, "公式": "总GMV - 预算可承载归因GMV；不与重叠渠道直接相加"},
    ]

    channel_rows = []
    traffic_rows = traffic.data.get("rows", []) if traffic else []
    traffic_gmv = sum(float(item.get("gmv") or 0) for item in traffic_rows)
    for item in traffic_rows:
        share = float(item.get("gmv") or 0) / traffic_gmv if traffic_gmv else None
        planned = round(target_gmv * share, 2) if target_gmv is not None and share is not None else None
        channel_rows.append({"渠道": item.get("source"), "类型": "互斥一级来源", "历史GMV": item.get("gmv"), "历史占比%": round(share * 100, 2) if share is not None else None, "规划GMV": planned, "规划预算": None})
    for key, label, measure in (("members", "会员", "gmv"), ("live", "直播", "gmv"), ("cps", "CPS", "payment_gmv"), ("bybt", "百亿补贴", "gmv"), ("content", "内容种草", "gmv")):
        result = dataset_results.get(key)
        if not result or result.status == "no_data":
            continue
        value = result.data.get("aggregates", {}).get(measure)
        channel_rows.append({"渠道": label, "类型": "重叠贡献标签", "历史GMV": value, "历史占比%": round(float(value or 0) / history_gmv * 100, 2) if history_gmv else None, "规划GMV": None, "规划预算": None})

    product_rows = []
    product_data = products.data.get("rows", []) if products else []
    product_total = sum(float(item.get("gmv") or 0) for item in product_data)
    for index, item in enumerate(product_data[:20]):
        gmv = float(item.get("gmv") or 0)
        share = gmv / product_total if product_total else None
        refund_rate = float(item.get("refund_amount") or 0) / gmv * 100 if gmv else None
        role = "主销款" if index < 3 else "增长/承接款" if index < 10 else "长尾观察款"
        risk = "先修承接，不直接扩量" if refund_rate is not None and refund_rate >= 30 else "限额测试" if refund_rate is not None and refund_rate >= 20 else "可进入扩量候选"
        product_rows.append({"商品": item.get("product_name") or item.get("product_id"), "角色建议": role, "历史GMV": gmv, "历史占比%": round(share * 100, 2) if share is not None else None, "规划GMV": round(float(target_gmv) * share, 2) if target_gmv is not None and share is not None else None, "退款率%": round(refund_rate, 2) if refund_rate is not None else None, "扩量闸门": risk})

    missing_inputs = []
    if target_gmv is None: missing_inputs.append("GMV 目标")
    if total_budget is None: missing_inputs.append("总预算")
    if target_roi is None: missing_inputs.append("目标 ROI")
    if inputs.get("margin_rate") is None: missing_inputs.append("毛利率")
    findings = [DiagnosisFinding(level="info", title="618目标树与承接情景已建立", detail="已按 GMV = UV x CVR x ATV，以最近完整业务基线填充可计算的 UV/CVR/ATV，并将预算 ROI 约束与总 GMV 分开。")]
    actions = []
    if missing_inputs:
        required = [item for item in missing_inputs if item != "毛利率"]
        optional = [item for item in missing_inputs if item == "毛利率"]
        detail = "缺少：" + "、".join(required or optional) + "；相关绝对金额保持为空。"
        if optional and required:
            detail += " 毛利率只影响利润/费用承受能力，不阻塞 GMV 和预算节奏情景。"
        findings.append(DiagnosisFinding(level="warning", title="部分规划输入尚未明确", detail=detail))
        if required:
            actions.append(RecommendedAction(priority="P0", title="补齐规划约束", detail="先确认活动周期、GMV、预算和目标 ROI，再锁定阶段与渠道金额；毛利率用于后续利润闸门。", owner="业务负责人"))
        elif optional:
            actions.append(RecommendedAction(priority="P1", title="补充毛利与费用口径", detail="补充商品成本、平台费、佣金、优惠和履约费用后，再判断目标 ROI 是否可承受。", owner="财务与业务"))
    if target_gmv is not None and attributed_gmv_target is not None and total_budget:
        required_roi = float(target_gmv) / float(total_budget)
        if required_roi > float(target_roi or 0):
            findings.append(DiagnosisFinding(level="warning", title="GMV目标与预算ROI需要拆分承接", detail=f"预算 {total_budget:,.0f} 元按目标 ROI {float(target_roi):.2f} 仅对应约 {attributed_gmv_target:,.0f} 元推广归因成交；若总 GMV 目标为 {float(target_gmv):,.0f} 元，整体费用效率需达到 {required_roi:.2f}，其余约 {non_paid_gmv_target:,.0f} 元必须由自然、会员、直播或 CPS 等承接，且这些渠道存在归因重叠，不能直接相加。"))
            actions.append(RecommendedAction(priority="P0", title="先拆清付费与总盘目标", detail=f"把 {float(target_gmv):,.0f} 元拆成付费归因目标 {attributed_gmv_target:,.0f} 元和非付费/重叠渠道承接目标 {non_paid_gmv_target:,.0f} 元，按互斥一级来源验收总盘。", owner="经营负责人", validation="每日同时核对总支付 GMV、推广归因 GMV、预算消耗和重叠渠道标签"))
    missing_datasets = [item for item in coverage_result.data.get("datasets", []) if item.get("missing_dates") or item.get("missing_datasets") or item.get("partial_datasets")]
    if missing_datasets:
        findings.append(DiagnosisFinding(level="warning", title="规划基线存在采集缺口", detail="缺失数据没有按 0 参与目标和占比计算。"))
        actions.insert(0, RecommendedAction(priority="P0", title="补齐规划基线", detail="优先补采覆盖缺口，再锁定阶段、渠道和商品目标。", owner="数据运营"))
    if channel_rows:
        actions.append(RecommendedAction(priority="P1", title="先锁定互斥渠道目标", detail="一级来源可合计到 100%；会员、直播、CPS 等作为重叠贡献标签单独管理，避免重复加总。", validation="渠道目标合计与总 GMV 勾稽"))
    if product_rows:
        actions.append(RecommendedAction(priority="P1", title="明确商品角色和承接责任", detail="主销款保护库存与转化，增长款配置流量测试，退款高的商品不直接扩量。", validation="商品目标合计、转化率和退款率按日复盘"))
    if any((row.get("退款率%") or 0) >= 30 for row in product_rows):
        actions.insert(0, RecommendedAction(priority="P0", title="先处理高退款主销款", detail="至少一个高贡献商品退款率达到 30% 以上，618 前先核对尺码/规格、详情预期、发货和售后原因，再决定是否放量。", owner="商品与履约", validation="退款率下降且支付转化不恶化"))
    artifacts = [ArtifactSpec(type="metric_table", title="规划目标树", rows=target_rows)]
    if channel_rows: artifacts.append(ArtifactSpec(type="matrix", title="渠道目标基线", rows=channel_rows))
    if product_rows: artifacts.append(ArtifactSpec(type="matrix", title="商品角色与目标基线", rows=product_rows))
    if inputs.get("event"):
        phase_weights = [("蓄水", 0.05, "UV、新客、加购、收藏", "目标人群和货品池准备完成"), ("启动/预售", 0.20, "预售/支付、CVR、ATV", "首轮承接达到目标线"), ("日销承接", 0.30, "稳定成交、预算消耗、退款", "预算和成交节奏不脱节"), ("高潮", 0.40, "峰值 UV、CVR、库存", "核心商品不断货且转化稳定"), ("返场/复盘", 0.05, "净GMV、费用率、退款、复购", "结论可回写下一次规划")]
        artifacts.append(ArtifactSpec(type="matrix", title="活动阶段计划模板", rows=[
            {"阶段": phase, "GMV占比%": round(weight * 100, 2), "GMV目标": round(float(target_gmv) * weight, 2) if target_gmv is not None else None, "预算占比%": round(weight * 100, 2), "预算": round(float(total_budget) * weight, 2) if total_budget is not None else None, "核心指标": metrics, "验证": validation}
            for phase, weight, metrics, validation in phase_weights
        ]))
    assumptions = list(findings[0].detail and ["未明确活动起止日期；阶段金额使用 5%/20%/30%/40%/5% 的可调整情景，不代表平台固定节奏。"] or [])
    if history_cvr is not None and inputs.get("target_cvr") is None:
        assumptions.append(f"未提供目标 CVR，暂用最近规划基线 {history_cvr * 100:.2f}% 计算目标 UV。")
    if history_atv is not None and inputs.get("target_atv") is None:
        assumptions.append(f"未提供目标 ATV，暂用最近规划基线 {history_atv:.2f} 元计算目标 UV。")
    return Diagnosis(headline="618目标树与阶段计划已生成", summary=findings[0].detail, findings=findings, actions=actions, artifacts=artifacts, assumptions=assumptions)


def _period_report_diagnosis(results: list[MCPEnvelope]) -> Diagnosis:
    result = next((item for item in results if item.tool == "reports.build_period_report"), results[-1])
    report = result.data
    operations = report.get("operations", {})
    channels = report.get("channels", {})
    promotions = report.get("promotions", {})
    missing = report.get("missing_sections", [])
    gmv = float(operations.get("gmv") or 0)
    net_gmv = float(operations.get("net_gmv") or 0)
    refund_rate = float(operations.get("refund_rate")) if operations.get("refund_rate") is not None else ((gmv - net_gmv) / gmv * 100 if gmv else 0)
    comparison = report.get("comparison", {})
    report_type = str(report.get("report_type") or "daily")
    range_start = str(report.get("range_start") or "")
    range_end = str(report.get("range_end") or "")
    period_label = "昨日" if report_type == "daily" else "本周" if report_type == "weekly" else "本月" if report_type in {"monthly", "daily_series"} else "本月至今"

    def change(metric: str) -> float | None:
        value = comparison.get(metric, {}).get("change_percent") if isinstance(comparison.get(metric), dict) else None
        return float(value) if value is not None else None

    gmv_change = change("paid_amount")
    visitors_change = change("visitors")
    buyers_change = change("buyers")
    conversion_change = change("conversion_rate")
    customer_unit_price_change = change("customer_unit_price")
    driver_bridge = report.get("gmv_driver_bridge") or {}
    dominant_driver = driver_bridge.get("dominant_driver") or {}
    dominant_label = dominant_driver.get("label")
    dominant_impact = float(dominant_driver.get("impact_amount") or 0)
    if gmv_change is None:
        headline = f"{period_label} GMV {gmv / 10000:.2f} 万，去退后 {net_gmv / 10000:.2f} 万"
        summary = f"统计区间 {range_start} 至 {range_end}，当前没有可用的上一周期对比，先看本期结构和数据覆盖。"
    elif gmv_change <= -5:
        driver = dominant_label or ("流量收缩" if visitors_change is not None and visitors_change <= -5 else "转化承接变弱" if conversion_change is not None and conversion_change <= -5 else "需要结合渠道与商品继续定位")
        headline = f"{period_label} GMV 环比下降 {abs(gmv_change):.1f}%，优先排查{driver}"
        summary = f"统计区间 {range_start} 至 {range_end}；GMV {gmv / 10000:.2f} 万，去退 GMV {net_gmv / 10000:.2f} 万。顺序桥接显示{driver}影响约 {abs(dominant_impact) / 10000:.2f} 万，是本次变化的最大解释项；这不是因果增量结论。"
    elif gmv_change >= 5:
        headline = f"{period_label} GMV 环比增长 {gmv_change:.1f}%，需要确认增长是否可复制"
        summary = f"统计区间 {range_start} 至 {range_end}；GMV {gmv / 10000:.2f} 万，去退 GMV {net_gmv / 10000:.2f} 万；重点复核流量、商品和推广结构是否同步改善。"
    else:
        headline = f"{period_label}经营基本平稳，GMV {gmv / 10000:.2f} 万"
        summary = f"统计区间 {range_start} 至 {range_end}；去退 GMV {net_gmv / 10000:.2f} 万，退款金额占 GMV {refund_rate:.2f}%；未触发显著波动预警。"

    findings = [DiagnosisFinding(level="info", title="经营结果", detail=summary, metric_ids=["gmv", "net_gmv", "refund_rate"])]
    actions: list[RecommendedAction] = []
    target = report.get("target") or {}
    if target.get("target_gmv") is not None:
        completion = target.get("completion_rate")
        pace_gap = target.get("pace_gap")
        progress_detail = f"目标 {float(target['target_gmv']) / 10000:.2f} 万，当前完成 {float(completion or 0):.2f}%"
        if pace_gap is not None:
            progress_detail += f"，与时间进度相差 {float(pace_gap):+.2f} 个百分点"
        level = "warning" if pace_gap is not None and float(pace_gap) < -3 else "positive" if pace_gap is not None and float(pace_gap) >= 0 else "info"
        findings.insert(1, DiagnosisFinding(level=level, title="销售目标进度", detail=progress_detail, metric_ids=["gmv"]))
        if pace_gap is not None and float(pace_gap) < -3:
            actions.append(RecommendedAction(priority="P0", title="补齐目标进度缺口", detail="先按剩余天数反推日均 GMV 缺口，再拆到渠道与主销商品；不要直接按历史花费同比例加预算。", owner="经营负责人", validation="未来 3 天日均 GMV 达到追赶目标且退款率不恶化"))
    if gmv_change is not None and gmv_change <= -5:
        if driver_bridge.get("drivers"):
            for item in sorted(driver_bridge["drivers"], key=lambda row: abs(float(row.get("impact_amount") or 0)), reverse=True)[:3]:
                impact = float(item.get("impact_amount") or 0)
                change_percent = item.get("change_percent")
                detail = f"{item.get('label')}环比 {float(change_percent):+.1f}%" if change_percent is not None else f"{item.get('label')}缺少环比"
                detail += f"，顺序桥接影响 {impact / 10000:+.2f} 万。"
                findings.append(DiagnosisFinding(
                    level="warning" if impact < 0 else "positive",
                    title=f"{item.get('label')}驱动",
                    detail=detail,
                    metric_ids=[str(item.get("metric") or "gmv"), "gmv"],
                ))
        if dominant_label == "客单价":
            actions.append(RecommendedAction(
                priority="P0",
                title="下钻客单价下降来源",
                detail="按系列 → 类型 → 商品拆分正装、MINI 装和试用装的成交结构，复核价格带、优惠门槛、件单价和低价商品占比；先定位结构变化，再调整流量。",
                owner="商品运营",
                validation="客单价恢复、正装/主销系列占比回升，且支付转化率与退款率不恶化",
            ))
        if visitors_change is not None and visitors_change <= -5:
            findings.append(DiagnosisFinding(level="warning", title="流量规模是首要排查方向", detail=f"访客环比 {visitors_change:.1f}%，需要下钻自然、推广和直播来源的下降贡献。", metric_ids=["visitors", "gmv"]))
            actions.append(RecommendedAction(priority="P0", title="定位流量缺口", detail="先找出下降贡献最大的流量来源，再决定是否恢复预算；不要直接全量加投。", owner="流量运营", validation="下降来源恢复且支付转化率不恶化"))
        elif conversion_change is not None and conversion_change <= -5:
            findings.append(DiagnosisFinding(level="warning", title="流量仍在但成交承接变弱", detail=f"支付转化率环比 {conversion_change:.1f}%，优先检查主销商品价格、库存、详情和优惠。", metric_ids=["conversion_rate", "gmv"]))
            actions.append(RecommendedAction(priority="P0", title="修复成交承接", detail="先检查高流量商品的详情首屏、价格力、库存和评价，不先扩大推广。", owner="商品运营", validation="支付转化率和加购率恢复"))
        elif buyers_change is not None and buyers_change <= -5:
            findings.append(DiagnosisFinding(level="warning", title="支付买家减少", detail=f"支付买家环比 {buyers_change:.1f}%，需要结合新老客和渠道结构判断。", metric_ids=["buyers", "gmv"]))
    elif gmv_change is not None and gmv_change >= 5:
        findings.append(DiagnosisFinding(level="positive", title="成交增长需要验证可持续性", detail=f"GMV 环比增长 {gmv_change:.1f}%，不能直接等同于活动或渠道产生了因果增量。", metric_ids=["gmv"]))

    if refund_rate >= 20:
        findings.append(DiagnosisFinding(level="warning", title="退款压力偏高", detail=f"退款金额占 GMV {refund_rate:.2f}%，建议按商品、原因和渠道拆解退款结构。", metric_ids=["net_gmv"]))
        actions.append(RecommendedAction(priority="P0", title="复盘退款结构", detail="先定位退款金额最高的商品和退款原因，避免只看 GMV 增长。", validation="退款率连续两个周期下降"))
    elif refund_rate >= 10:
        findings.append(DiagnosisFinding(level="warning", title="退款占比需要关注", detail=f"退款金额占 GMV {refund_rate:.2f}%，建议按商品和渠道追踪，不将去退 GMV 与支付 GMV 混用。", metric_ids=["refund_rate", "net_gmv"]))
        actions.append(RecommendedAction(priority="P1", title="追踪高退款商品", detail="按商品、活动和渠道拆解退款金额，确认是商品预期、优惠承诺还是履约问题。", owner="商品运营", validation="退款金额占比连续下降"))
    member = channels.get("member", {})
    if member.get("status") == "available":
        findings.append(DiagnosisFinding(level="positive", title="会员是重要成交渠道", detail=f"会员成交 {float(member.get('paid_amount') or 0) / 10000:.2f} 万，占 GMV {float(member.get('sales_share') or 0):.2f}%。"))
    if promotions.get("roi") is not None:
        roi = float(promotions["roi"])
        level = "positive" if roi >= 3 else "warning" if roi < 2 else "info"
        findings.append(DiagnosisFinding(level=level, title="推广投入产出已纳入报告", detail=f"15 天归因口径整体 ROI {roi:.2f}，花费 {float(promotions.get('spend') or 0) / 10000:.2f} 万。", metric_ids=["promotion_roi"]))
        low_scene = next((item for item in sorted(promotions.get("scenes", []), key=lambda row: float(row.get("spend") or 0), reverse=True) if float(item.get("spend") or 0) > 0 and float(item.get("roi") or 0) < 1), None)
        if low_scene:
            scene_name = low_scene.get("scene_name") or low_scene.get("dimension_name") or "低效推广场景"
            findings.append(DiagnosisFinding(level="warning", title=f"{scene_name} 需要降级复查", detail=f"花费 {float(low_scene.get('spend') or 0) / 10000:.2f} 万，ROI {float(low_scene.get('roi') or 0):.2f}；归因成交未覆盖广告花费，但这不等同亏损或利润结论。", metric_ids=["promotion_roi"]))
            actions.append(RecommendedAction(priority="P0", title="下钻高花费低 ROI 场景", detail=f"先拆到计划、商品和人群，确认归因窗口后再决定降预算或暂停。", owner="投放运营", validation="低效花费下降且整体 ROI 不下降"))
    if missing:
        actions.append(RecommendedAction(priority="P0", title="补齐报告缺失模块", detail="以下模块暂不能作为完整经营结论：" + "、".join(missing), owner="数据运营", validation="模块状态变为 complete 或 no_data"))
    talents = report.get("top_talents", [])
    if talents:
        actions.append(RecommendedAction(priority="P1", title="补齐头部达人效率口径", detail=f"头部达人 {talents[0].get('name')} GMV {float(talents[0].get('gmv') or 0) / 10000:.2f} 万；先补齐佣金、退款扣除和新客数据，再判断是否复投，不直接按 GMV 扩合作。", validation="同时得到退款后成交、已知佣金、单买家产出和新客占比"))
    channel_rows = []
    for key, channel in channels.items():
        if not isinstance(channel, dict) or channel.get("status") not in {"available", "complete"}:
            continue
        channel_rows.append({
            "渠道": {"member": "会员", "shop_live": "自播间", "bybt": "百亿补贴", "cps_payment": "CPS支付", "cps_settlement": "CPS出库"}.get(key, key),
            "成交金额": channel.get("paid_amount"),
            "销售占比%": channel.get("sales_share"),
            "已知费用": channel.get("expense"),
            "状态": "可用",
        })
    promotion_rows = []
    for item in promotions.get("scenes", []):
        def numeric(value):
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None
        promotion_rows.append({
            "推广场景": item.get("scene_name") or item.get("dimension_name") or "未分类",
            "花费": numeric(item.get("spend")),
            "归因成交": numeric(item.get("paid_amount")),
            "ROI": numeric(item.get("roi")),
            "点击": numeric(item.get("clicks")),
            "支付买家": numeric(item.get("buyers")),
            "直接成交": numeric(item.get("direct_paid_amount")),
            "间接成交": numeric(item.get("indirect_paid_amount")),
        })
    talent_rows = [{"达人": item.get("name"), "成交金额": item.get("gmv"), "合作场次": item.get("sessions"), "支付买家": item.get("buyers")} for item in talents]
    artifacts = [ArtifactSpec(type="metric_table", title="周期经营指标", rows=[
        {"指标": "GMV", "当前值": gmv, "单位": "CNY", "环比%": gmv_change},
        {"指标": "去退 GMV", "当前值": net_gmv, "单位": "CNY"},
        {"指标": "访客", "当前值": operations.get("visitors"), "单位": "人", "环比%": visitors_change},
        {"指标": "支付买家", "当前值": operations.get("buyers"), "单位": "人", "环比%": buyers_change},
        {"指标": "支付转化率", "当前值": operations.get("conversion_rate"), "单位": "%", "环比%": conversion_change},
        {"指标": "客单价", "当前值": operations.get("customer_unit_price"), "单位": "CNY", "环比%": customer_unit_price_change},
        {"指标": "退款金额占比", "当前值": round(refund_rate, 2), "单位": "%"},
        {"指标": "推广 ROI", "当前值": promotions.get("roi"), "单位": "ratio"},
    ])]
    if channel_rows:
        artifacts.append(ArtifactSpec(type="matrix", title="渠道成交结构", rows=channel_rows))
    if driver_bridge.get("drivers"):
        artifacts.append(ArtifactSpec(type="matrix", title="GMV 变化驱动桥接", rows=[
            {"驱动": item.get("label"), "影响金额": item.get("impact_amount"), "环比%": item.get("change_percent")}
            for item in driver_bridge["drivers"]
        ]))
    if promotion_rows:
        artifacts.append(ArtifactSpec(type="bar_chart", title="推广场景投入产出", rows=promotion_rows))
    if talent_rows:
        artifacts.append(ArtifactSpec(type="matrix", title="前三达人贡献", rows=talent_rows))
    return Diagnosis(
        headline=headline,
        summary=summary,
        findings=findings[:6],
        actions=actions[:6],
        artifacts=artifacts,
        next_questions=list(dict.fromkeys([
            "下钻客单价下降的系列、类型和商品" if dominant_label == "客单价" else "下钻 GMV 变化最大的驱动项",
            "拆解会员、直播和 CPS 的重叠口径" if report.get("channel_scope") else "查看渠道归因明细",
        ])),
    )


def _generic_data_diagnosis(results: list[MCPEnvelope]) -> Diagnosis:
    """Safe fallback for exploratory questions over a generic MCP result."""
    result = results[-1] if results else None
    if result is None or result.status == "no_data":
        return Diagnosis(
            headline="没有可用数据",
            summary="先确认数据集是否已采集，平台确认无数据不等同于采集失败。",
            findings=[DiagnosisFinding(level="warning", title="数据不可用", detail="当前查询没有返回可分析记录。")],
            actions=[RecommendedAction(priority="P0", title="检查数据覆盖", detail="调用 data.coverage 区分未采集日期和平台无数据。", owner="数据运营")],
        )
    rows = result.data.get("rows", [])
    findings = [DiagnosisFinding(level="info", title="结构化数据已返回", detail=f"查询返回 {len(rows)} 行，证据来自 {len(result.evidence)} 个数据集记录。")]
    if result.coverage.missing_dates:
        findings.append(DiagnosisFinding(level="warning", title="结果存在缺失日期", detail="缺失日期不会按 0 参与业务计算。"))
    columns = result.data.get("columns", [])
    return Diagnosis(
        headline=findings[0].title,
        summary=findings[0].detail,
        findings=findings,
        actions=[RecommendedAction(priority="P1", title="继续下钻业务维度", detail="根据问题选择商品、来源、推广或客户维度，再交给对应业务 Skill 判断。", validation="得到可解释的业务结论")],
        artifacts=[ArtifactSpec(type="metric_table", title="查询结果", columns=[{"key": key, "label": key} for key in columns], rows=rows)],
    )


def _data_quality_diagnosis(results: list[MCPEnvelope]) -> Diagnosis:
    result = results[0]
    datasets = result.data.get("datasets", [])
    missing = [item for item in datasets if item.get("missing_dates") or item.get("missing_datasets")]
    partial = [item for item in datasets if item.get("partial_datasets")]
    no_data = [item for item in datasets if item.get("no_data_datasets")]
    findings: list[DiagnosisFinding] = []
    actions: list[RecommendedAction] = []
    if missing or partial:
        labels = "、".join(str(item.get("label")) for item in [*missing, *partial][:8])
        findings.append(DiagnosisFinding(level="warning", title="存在需要补采的数据缺口", detail=f"涉及：{labels}。平台确认无数据未计入缺口。"))
        actions.append(RecommendedAction(priority="P0", title="按缺失日期补采", detail="只补 missing_dates 对应日期，完成后重新执行覆盖审计。", owner="数据运营", validation="缺失日期清零"))
    else:
        findings.append(DiagnosisFinding(level="positive", title="所选数据集覆盖完整", detail="没有发现未采集日期。"))
    if no_data:
        findings.append(DiagnosisFinding(level="info", title="存在平台确认无数据", detail="以下数据不需要反复补采：" + "、".join(str(item.get("label")) for item in no_data[:8])))
    rows = [{"数据集": item.get("label"), "应有天数": item.get("expected_days"), "覆盖天数": item.get("covered_days"), "缺失日期": "、".join(item.get("missing_dates") or []), "平台无数据日期": "、".join(item.get("no_data_dates") or [])} for item in datasets]
    freshness = next((item for item in results if item.tool == "data.freshness"), None)
    if freshness:
        stale = [item for item in freshness.data.get("datasets", []) if item.get("status") == "stale"]
        unobserved = [item for item in freshness.data.get("datasets", []) if item.get("status") == "no_observed_data"]
        if stale:
            findings.append(DiagnosisFinding(level="warning", title="部分数据集业务日滞后", detail="最新业务日已落后当前日期：" + "、".join(f"{item.get('label')}（{item.get('business_lag_days')}天）" for item in stale[:8])))
            actions.insert(0, RecommendedAction(priority="P0", title="优先补采滞后数据", detail="先检查采集任务和接口返回，再只补实际缺失日期；业务日滞后不等同平台无数据。", owner="数据运营", validation="最新业务日追平且采集批次成功"))
        if unobserved:
            findings.append(DiagnosisFinding(level="info", title="部分数据集没有观测到业务日期", detail="这些数据集可能是平台无数据或尚未配置，不能直接判断为缺失：" + "、".join(item.get("label") for item in unobserved[:8])))
    return Diagnosis(headline=findings[0].title, summary=findings[0].detail, findings=findings, actions=actions, artifacts=[ArtifactSpec(type="metric_table", title="数据覆盖审计", rows=rows)])


def _inventory_diagnosis(results: list[MCPEnvelope]) -> Diagnosis:
    result = results[-1]
    items = result.data.get("items", [])
    if not items:
        reason = result.data.get("reason")
        labels = {
            "not_configured": ("吉客云库存尚未配置", "先配置吉客云库存接口和 Token。"),
            "not_collected": ("尚未采集库存快照", "检查同步状态并手动执行库存同步。"),
            "date_not_available": ("指定日期没有库存快照", "改查最新库存快照，或补采指定日期库存。"),
            "sku_not_matched": ("商品已匹配但尺码未匹配", "核对尺码名称、SKU 编码或条码。"),
            "code_known_no_snapshot": ("货品编码已识别但快照未命中", "先确认该货品是否应出现在吉客云库存接口，再补采当前库存快照。"),
            "product_not_matched": ("没有匹配到库存商品", "使用商品编码、SKU 编码、条码或完整商品名称查询。"),
        }
        headline, action_detail = labels.get(reason, labels["product_not_matched"])
        return Diagnosis(
            headline=headline,
            summary=action_detail,
            findings=[DiagnosisFinding(level="warning", title="库存数据状态", detail=action_detail)],
            actions=[RecommendedAction(priority="P0", title="处理库存数据状态", detail=action_detail, owner="数据运营")],
        )
    rows = []
    for item in items:
        name = item.get("goods_name") or item.get("goods_no") or item.get("sku_barcode") or "未命名商品"
        is_package = item.get("item_type") == "package"
        quantity = item.get("assemblable_quantity") if is_package else item.get("available_quantity")
        rows.append({
            "商品": name,
            "货品编码": item.get("goods_no") or "--",
            "SKU编码": item.get("sku_no") or item.get("sku_id") or "--",
            "规格": item.get("specification") or "--",
            "尺码": item.get("size") or "--",
            "片数": item.get("pieces") if item.get("pieces") is not None else "--",
            "类型": "组合品" if item.get("item_type") == "package" else "普通 SKU",
            "库存": "不计算（查看组成 SKU）" if is_package else quantity,
            "库存业务日": item.get("business_day"),
            "匹配依据": "、".join(item.get("matched_by") or []) or "--",
        })
    return Diagnosis(
        headline=f"已查询到 {len(items)} 个库存商品",
        summary="普通 SKU 返回各仓可用库存；组合货品仅展示组成关系，不计算组合库存。",
        findings=[DiagnosisFinding(level="info", title="库存查询完成", detail=f"返回 {len(items)} 个匹配商品。")],
        actions=[RecommendedAction(priority="P1", title="关注低库存商品", detail="对库存接近零的商品设置预警。", owner="运营")],
        artifacts=[ArtifactSpec(type="metric_table", title="库存查询结果", rows=rows)],
    )


def _product_diagnosis(results: list[MCPEnvelope]) -> Diagnosis:
    result = results[0]
    rows = result.data.get("rows", [])
    if not rows:
        return _generic_data_diagnosis(results)
    ranked = []
    for item in rows:
        visitors = float(item.get("visitors") or 0)
        buyers = float(item.get("buyers") or 0)
        gmv = float(item.get("gmv") or 0)
        ranked.append({**item, "conversion_rate": buyers / visitors * 100 if visitors else None, "uv_value": gmv / visitors if visitors else None})
    top = max(ranked, key=lambda item: float(item.get("gmv") or 0))
    weak = sorted([item for item in ranked if item.get("conversion_rate") is not None], key=lambda item: float(item.get("conversion_rate") or 0))[:3]
    findings = [DiagnosisFinding(level="positive", title="主销商品已识别", detail=f"{top.get('product_name') or top.get('product_id')} 支付金额最高，GMV {float(top.get('gmv') or 0):,.0}。", metric_ids=["gmv"])]
    actions = [RecommendedAction(priority="P1", title="保护主销商品承接", detail="检查主销商品库存、价格、优惠和评价，避免高流量商品掉转化。", validation="主销商品转化率稳定")]
    if weak:
        item = weak[0]
        findings.append(DiagnosisFinding(level="warning", title="存在低转化商品", detail=f"{item.get('product_name') or item.get('product_id')} 访客 {float(item.get('visitors') or 0):,.0}，转化率 {float(item.get('conversion_rate') or 0):.2f}%。", metric_ids=["visitors", "buyers"]))
        actions.append(RecommendedAction(priority="P0", title="优先优化低转化商品", detail="按商品检查详情首屏、价格力、库存和评价，再决定是否继续加大流量。", validation="商品转化率提升且退款率不恶化"))
    table = [{"商品": item.get("product_name") or item.get("product_id"), "GMV": item.get("gmv"), "访客": item.get("visitors"), "买家": item.get("buyers"), "转化率%": item.get("conversion_rate"), "UV价值": item.get("uv_value")} for item in ranked]
    return Diagnosis(headline=findings[0].title, summary=findings[0].detail, findings=findings, actions=actions, artifacts=[ArtifactSpec(type="matrix", title="商品经营质量矩阵", rows=table)])


def _customer_diagnosis(results: list[MCPEnvelope]) -> Diagnosis:
    result = results[0]
    values = result.data.get("aggregates", {})
    new_buyers = float(values.get("new_paid_buyers") or 0)
    repeat_buyers = float(values.get("repeat_buyers") or 0)
    no_purchase_buyers = float(values.get("no_purchase_buyers") or 0)
    findings = [DiagnosisFinding(level="info", title="客户结构已汇总", detail=f"新客成交 {new_buyers:,.0f}，老客复购 {repeat_buyers:,.0f}，未购回访成交 {no_purchase_buyers:,.0f}。")]
    actions = [RecommendedAction(priority="P1", title="分层运营客户", detail="新客重点优化首单承接，未购回访做召回，老客复购做周期和会员权益运营。", validation="复购人数和回访转化率连续提升")]
    if repeat_buyers == 0 and new_buyers > 0:
        findings.append(DiagnosisFinding(level="warning", title="当前区间没有识别到老客复购", detail="需要确认客户分析是否完成采集，或本期确实没有复购成交。"))
        actions.insert(0, RecommendedAction(priority="P0", title="核查复购数据和召回动作", detail="先用 data.coverage 区分未采集与平台无数据，再检查老客触达和复购权益。", owner="CRM运营", validation="复购数据可解释且复购人数回升"))
    return Diagnosis(headline=findings[0].title, summary=findings[0].detail, findings=findings, actions=actions, artifacts=[ArtifactSpec(type="metric_table", title="客户结构", rows=[{"指标": "新客成交人数", "值": new_buyers}, {"指标": "老客复购人数", "值": repeat_buyers}, {"指标": "未购回访成交人数", "值": no_purchase_buyers}])])


def _utry_repurchase_diagnosis(results: list[MCPEnvelope]) -> Diagnosis:
    result = next((item for item in results if item.tool == "utry.get_repurchase_diagnosis"), results[0] if results else None)
    if result is None or result.status == "no_data":
        detail = "所选区间没有 U先回购快照记录，不能把缺失数据当作没有回购。"
        return Diagnosis(
            headline="U先回购数据不可用",
            summary=detail,
            findings=[DiagnosisFinding(level="warning", title="U先回购快照未返回", detail=detail)],
            actions=[RecommendedAction(priority="P0", title="核对 U先回购采集覆盖", detail="检查 U先复购表的业务日期和采集任务，区分平台无数据与尚未采集后再分析。", owner="数据运营", validation="U先复购快照覆盖目标业务日")],
            artifacts=[ArtifactSpec(type="metric_table", title="U先回购数据状态", rows=[{"指标": "状态", "值": "所选区间无快照"}])],
            causal_boundary="当前没有 U先回购事实数据，不对回购规模、回购率或新客质量做推断。",
        )
    data = result.data or {}
    current = data.get("current") or {}
    previous = data.get("previous") or {}
    comparisons = data.get("comparisons") or {}
    latest_day = data.get("latest_business_day") or "--"
    previous_day = data.get("previous_business_day") or "--"
    def num(key: str) -> float:
        return float(current.get(key) or 0)
    def change(key: str) -> float | None:
        value = (comparisons.get(key) or {}).get("change_percent")
        return float(value) if value is not None else None
    def money(value: Any) -> str:
        return f"¥{float(value or 0):,.0f}"
    def count(value: Any) -> str:
        return f"{float(value or 0):,.0f}"
    def pct(value: Any) -> str:
        return "--" if value is None else f"{float(value):.1f}%"

    store_30_amount = num("store_30d_repurchase_amount")
    store_90_amount = num("store_90d_repurchase_amount")
    store_365_amount = num("store_365d_repurchase_amount")
    brand_365_amount = num("brand_365d_repurchase_amount")
    findings: list[DiagnosisFinding] = [
        DiagnosisFinding(
            level="positive" if store_365_amount > 0 else "info",
            title="U先回购快照已接入",
            detail=(
                f"最新业务日 {latest_day} 共 {count(current.get('product_count'))} 个 U先商品；同店回购金额 30/90/365 日分别为 "
                f"{money(store_30_amount)}、{money(store_90_amount)}、{money(store_365_amount)}，同品牌365日为 {money(brand_365_amount)}。"
            ),
            metric_ids=["store_30d_repurchase_amount", "store_90d_repurchase_amount", "store_365d_repurchase_amount", "brand_365d_repurchase_amount"],
        )
    ]
    latest_change = change("store_365d_repurchase_amount")
    if latest_change is not None:
        findings.append(DiagnosisFinding(
            level="warning" if latest_change < -10 else "positive" if latest_change > 10 else "info",
            title="最新快照相对上一业务日的变化",
            detail=f"同店365日回购金额较 {previous_day} {latest_change:+.1f}%；这是两个业务日滚动快照的描述性变化，不等于新增回购金额变化。",
            metric_ids=["store_365d_repurchase_amount"],
        ))
    bound_count = float(current.get("bound_regular_product_count") or 0)
    product_count = float(current.get("product_count") or 0)
    coupon_count = float(current.get("configured_coupon_count") or 0)
    gift_count = float(current.get("configured_gift_count") or 0)
    findings.append(DiagnosisFinding(
        level="warning" if coupon_count == 0 and gift_count == 0 else "info",
        title="正装绑定与回购权益配置",
        detail=(
            f"{count(bound_count)}/{count(product_count)} 个商品已绑定正装（{pct(current.get('bound_regular_product_share'))}）；"
            f"已配置回购券 {count(coupon_count)} 个、回购礼金 {count(gift_count)} 个。配置状态只能作为运营检查项，不能据此证明回购因果。"
        ),
        metric_ids=["bound_regular_product_count", "configured_coupon_count", "configured_gift_count"],
    ))
    top_products = data.get("top_products") or []
    if top_products:
        top = top_products[0]
        findings.append(DiagnosisFinding(
            level="positive",
            title="高贡献 U先商品已识别",
            detail=f"{top.get('product_name') or top.get('product_id')} 同店365日回购金额 {money(top.get('store_365d_repurchase_amount'))}，占最新日商品回购金额 {pct(top.get('store_365d_amount_share'))}。",
            metric_ids=["store_365d_repurchase_amount"],
        ))

    actions: list[RecommendedAction] = []
    if top_products:
        top_names = "、".join(str(item.get("product_name") or item.get("product_id"))[:24] for item in top_products[:3])
        actions.append(RecommendedAction(
            priority="P0", title="优先复盘高贡献 U先商品的正装承接", detail=f"针对 {top_names} 核对试用装→正装链接、尺码覆盖、首购后触达和商品页回购入口；先保护已有回购贡献，不直接把同品牌回购当作同店增量。", owner="U先/商品运营", validation="30日同店回购金额与回购UV价值连续 2 个业务周稳定或提升", observation_window="7-14天", expected_impact="提升试用后正装承接，同时不恶化退款率和商品转化率",
        ))
    unbound_count = float(current.get("unbound_regular_product_count") or max(product_count - bound_count, 0))
    if unbound_count > 0:
        actions.append(RecommendedAction(
            priority="P1", title="补齐未绑定正装商品清单", detail=f"当前 {count(unbound_count)} 个商品未绑定正装；按同店365日回购金额排序，先确认是否有可承接的正装 SKU。没有正装或规则不适用的商品要标记原因，不能按缺失当作低回购。", owner="商品运营", validation="高贡献商品的绑定状态和不适用原因可解释", observation_window="7天", expected_impact="减少试用成交后无法承接正装的商品断点",
        ))
    if coupon_count == 0 and gift_count == 0:
        actions.append(RecommendedAction(
            priority="P1", title="核对回购券/礼金是否有意关闭", detail="确认平台配置为空是策略选择还是数据未采集；如要测试权益，先选高贡献商品做小范围 A/B 或限量测试，不把配置与回购变化直接写成因果。", owner="CRM运营", validation="配置状态可核对，测试组30/90日回购指标相对对照组改善", observation_window="30-90天", expected_impact="验证回购权益对试用后承接的实际贡献",
        ))
    sample = data.get("sample_snapshot") or {}
    if sample:
        actions.append(RecommendedAction(
            priority="P2", title="建立派样 cohort 回购口径", detail="将派样商品、人次和首批派样日期与后续支付用户做 cohort 关联，补齐回购率分母；当前只展示回购 UV/金额，不虚构回购率。", owner="数据运营", validation="每个派样批次具备首批人数、30/90/365日回购人数和回购金额", observation_window="30-365天", expected_impact="从快照规模分析升级为可比较的 cohort 回购率与回购周期",
        ))

    metric_rows = [
        {"指标": "同店30日", "回购UV合计": current.get("store_30d_repurchase_uv"), "回购金额": current.get("store_30d_repurchase_amount"), "回购UV价值": current.get("store_30d_repurchase_uv_value"), "较上一业务日%": change("store_30d_repurchase_amount")},
        {"指标": "同店90日", "回购UV合计": current.get("store_90d_repurchase_uv"), "回购金额": current.get("store_90d_repurchase_amount"), "回购UV价值": current.get("store_90d_repurchase_uv_value"), "较上一业务日%": change("store_90d_repurchase_amount")},
        {"指标": "同店365日", "回购UV合计": current.get("store_365d_repurchase_uv"), "回购金额": current.get("store_365d_repurchase_amount"), "回购UV价值": current.get("store_365d_repurchase_uv_value"), "较上一业务日%": change("store_365d_repurchase_amount")},
        {"指标": "同品牌365日", "回购UV合计": current.get("brand_365d_repurchase_uv"), "回购金额": current.get("brand_365d_repurchase_amount"), "回购UV价值": current.get("brand_365d_repurchase_uv_value"), "较上一业务日%": change("brand_365d_repurchase_amount")},
    ]
    product_rows = [
        {"商品": item.get("product_name") or item.get("product_id"), "商品ID": item.get("product_id"), "同店365日回购金额": item.get("store_365d_repurchase_amount"), "同店365日回购UV": item.get("store_365d_repurchase_uv"), "金额占比%": item.get("store_365d_amount_share"), "绑定正装": item.get("bind_regular_product"), "回购券": item.get("configured_repurchase_coupon"), "回购礼金": item.get("configured_repurchase_gift")} for item in top_products
    ]
    return Diagnosis(
        headline="U先回购诊断已完成",
        summary=f"最新业务日 {latest_day} 已读取 U先回购真实快照：同店365日回购金额 {money(store_365_amount)}，其中同店30/90日金额为 {money(store_30_amount)}/{money(store_90_amount)}；当前可定位高贡献商品和权益配置，但没有 cohort 分母，不能计算回购率。",
        findings=findings,
        actions=actions[:6],
        artifacts=[
            ArtifactSpec(type="metric_table", title="U先回购窗口对比", rows=metric_rows),
            ArtifactSpec(type="line_chart", title="U先回购日快照趋势", rows=data.get("daily_trend") or []),
            ArtifactSpec(type="matrix", title="U先商品回购贡献明细", rows=product_rows),
        ],
        assumptions=["总盘使用最新业务日全量 U先商品快照；趋势逐日比较，不跨日累加 30/90/365 日滚动指标。", "同品牌回购金额不等于同店成交金额。"],
        denominator_notes=["回购UV为商品行汇总，跨商品可能重复；回购UV价值 = 回购金额 ÷ 商品回购UV合计。", "当前没有严格匹配首批派样 cohort 的分母，因此不计算回购率。", "Top N 仅用于展示，最新业务日总盘使用全量商品。"],
        causal_boundary="U先回购指标是平台快照的描述性结果；正装绑定、回购券或礼金配置与回购表现之间没有实验或 cohort 对照时，不宣称因果增量。",
        next_questions=["查看 U先高贡献商品的派样规模与正装承接", "按派样批次建立30/90/365日 cohort 回购率", "比较配置回购权益与未配置商品的同口径回购表现"],
    )


def _mini_product_diagnosis(results: list[MCPEnvelope]) -> Diagnosis:
    result = next((item for item in results if item.tool == "mini.get_diagnosis"), results[0] if results else None)
    if result is None:
        return Diagnosis(headline="MINI/尝鲜商品数据未返回", summary="没有拿到专项商品联动结果。", confidence="low")
    data = result.data or {}
    products = data.get("products") or []
    domains = data.get("domain_status") or {}
    if not products:
        return Diagnosis(
            headline="未匹配到 MINI/尝鲜商品",
            summary="当前商品主档按标题、属性、定位和类型未匹配到 MINI/尝鲜商品；这不是 U先或复购数据为空的结论。",
            findings=[DiagnosisFinding(level="warning", title="商品身份未建立", detail="先确认店铺商品主档是否已采集，以及标题/属性是否包含 mini、尝鲜或试用装标识。")],
            actions=[RecommendedAction(priority="P0", title="补齐商品主档或商品标识", detail="采集店铺商品主档并规范 MINI/尝鲜商品的标题、属性、定位；验证后再按商品 ID 联动经营数据。", owner="商品/数据运营", validation="商品主档命中至少 1 个商品 ID", observation_window="即时", expected_impact="建立销售、推广、问大家和 U先关联主键")],
            artifacts=[ArtifactSpec(type="matrix", title="MINI/尝鲜商品匹配结果", rows=[])], coverage=result.coverage, confidence="low", missing_inputs=["可匹配的商品主档或商品标识"], evidence_refs=[item.dataset for item in result.evidence], causal_boundary="没有商品身份时不能判断销售、推广或反馈动作。",
        )
    def num(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0
    total_paid = sum(num((item.get("sales") or {}).get("paid_amount")) for item in products)
    total_spend = sum(num((item.get("promotion") or {}).get("spend")) for item in products)
    unanswered = sum(int((item.get("asks") or {}).get("unanswered_count") or 0) for item in products)
    findings: list[DiagnosisFinding] = []
    actions: list[RecommendedAction] = []
    if total_paid <= 0:
        findings.append(DiagnosisFinding(level="warning", title="MINI/尝鲜商品当前区间暂无支付成交", detail="商品身份已匹配，但所选区间支付金额为 0 或没有商品排行记录；应先区分未成交、未采集和缺失日期。"))
        actions.append(RecommendedAction(priority="P0", title="先核对商品承接和数据覆盖", detail="对照商品访客、加购、推广点击、库存/价格和商品排行覆盖日期；不要直接通过增加预算解决未确认的详情承接问题。", owner="商品运营", validation="确认每个商品的访客、转化和商品排行覆盖状态", observation_window="1～3 天", expected_impact="识别没有需求、页面承接弱或数据未到达"))
    else:
        findings.append(DiagnosisFinding(level="info", title="已按商品 ID 建立 MINI/尝鲜经营画像", detail=f"匹配 {len(products)} 个商品，所选区间支付金额合计 {total_paid:,.2f} 元；商品主档是跨域关联主键。"))
    if total_spend > 0:
        low_efficiency = [item for item in products if num((item.get("promotion") or {}).get("spend")) > 0 and (item.get("promotion") or {}).get("roi") is not None and num((item.get("promotion") or {}).get("roi")) < 1.5]
        if low_efficiency:
            findings.append(DiagnosisFinding(level="warning", title="部分 MINI/尝鲜商品推广效率偏低", detail=f"有 {len(low_efficiency)} 个商品存在花费且 ROI 低于 1.5；这是归因效率信号，不等于利润亏损。"))
            actions.append(RecommendedAction(priority="P1", title="下钻低效商品的推广计划与承接", detail="按商品 ID 继续拆计划、点击、加购和支付转化；先检查详情首屏、价格和评价/问大家，再决定降预算或暂停。", owner="推广/商品运营", validation="低效商品点击转化率、加购率和 ROI 同时改善", observation_window="3～7 天", expected_impact="减少无效花费并提升有效商品承接"))
    if unanswered:
        findings.append(DiagnosisFinding(level="warning", title="MINI/尝鲜商品存在未回答购买疑虑", detail=f"匹配商品有 {unanswered:,} 条未回答问大家；未回答是承接缺口信号，不直接证明成交损失。"))
        actions.append(RecommendedAction(priority="P0", title="补齐 MINI/尝鲜商品问大家 FAQ", detail="按商品 ID 和疑虑类型整理尺码、适用月龄、厚度、漏尿、材质和正装差异，补到详情 FAQ、客服和直播话术。", owner="客服/商品运营", validation="未回答问题数下降、回答率提升且商品支付转化率不恶化", observation_window="3～7 天", expected_impact="减少售前疑虑和重复咨询"))
    missing_domains = [name for name, info in domains.items() if info.get("status") in {"no_data", "unavailable"}]
    if any(name in missing_domains for name in ("utry_sample", "utry_repurchase")):
        actions.append(RecommendedAction(priority="P1", title="补采 U先派样/复购商品快照", detail="按已匹配商品 ID 检查 U先派样与复购表是未采集还是平台无该商品记录；有复购数据后再核对正装绑定、回购券/礼金配置。", owner="数据运营/会员运营", validation="每个商品的 U先状态明确；有 cohort 分母后再计算回购率", observation_window="7 天", expected_impact="补齐派样到正装回购的证据链"))
    if any(name in missing_domains for name in ("reviews", "asks")):
        actions.append(RecommendedAction(priority="P1", title="补采评价与问大家", detail="对匹配商品 ID 执行评价和问大家增量采集，区分没有记录与尚未采集；反馈缺失时不对商品质量下结论。", owner="数据运营", validation="评价/问大家最新采集时间和商品 ID 覆盖可核对", observation_window="即时", expected_impact="建立商品问题和售前疑虑证据"))
    rows = []
    for item in products[:50]:
        sales, promo, asks, sample, repurchase = (item.get(key) or {} for key in ("sales", "promotion", "asks", "utry_sample", "utry_repurchase"))
        rows.append({"商品": item.get("product_name") or item.get("product_id"), "商品ID": item.get("product_id"), "系列": item.get("series"), "定位": item.get("positioning"), "支付金额": sales.get("paid_amount"), "支付转化率%": sales.get("conversion_rate"), "推广花费": promo.get("spend"), "推广ROI": promo.get("roi"), "评价数": (item.get("reviews") or {}).get("review_count"), "未回答问大家": asks.get("unanswered_count"), "派样人次": sample.get("sample_people"), "同店30日回购UV": repurchase.get("store_30d_repurchase_uv"), "正装绑定": repurchase.get("bind_regular_product")})
    return Diagnosis(
        headline="MINI/尝鲜商品联动诊断已完成", summary=f"已按商品标题/属性/定位匹配 {len(products)} 个 MINI/尝鲜商品，并用商品 ID 联动销售、推广、评价、问大家和 U先证据；当前优先补齐 {len(actions)} 项动作。", findings=findings[:6], actions=actions[:6], artifacts=[ArtifactSpec(type="matrix", title="MINI/尝鲜商品跨域证据", rows=rows)], analysis_scope={"kind": "mini_product", "matched_count": len(products), "range": data.get("selected_range")}, coverage=result.coverage, confidence="medium", assumptions=["商品标题/属性/定位/类型用于识别候选，商品 ID 用于跨域关联。", "U先复购 30/90/365 日字段为最新业务日滚动快照。"], missing_inputs=[f"{name} 域数据" for name in missing_domains], evidence_refs=[f"{item.dataset}:{item.table}" for item in result.evidence], metric_definitions={"mini_product_count": "商品主档匹配后的商品 ID 数", "mini_unanswered_question_count": "匹配商品已采集且未回答的问大家数"}, denominator_notes=["未回答问题不等于成交损失；推广 ROI 是归因成交/花费，不是利润率。", "缺失日期不按 0 计入；U先无 cohort 分母时不计算回购率。"], causal_boundary="销售、推广、反馈和 U先数据按商品 ID 做描述性联动；没有商品级对照或实验时，不把某个域直接表述为成交因果。", next_questions=["下钻未回答问大家最多的 MINI 商品", "查看 MINI 商品推广低效计划", "核对 MINI 商品与正装绑定及回购权益"],
    )


def _customer_service_diagnosis(results: list[MCPEnvelope]) -> Diagnosis:
    result = next((item for item in results if item.tool == "customer_service.get_diagnosis"), results[0] if results else None)
    if result is None or result.status == "no_data":
        detail = "所选区间没有客服概览记录，不能判断咨询、接待、响应或客服成交表现。"
        return Diagnosis(
            headline="客服数据不可用",
            summary=detail,
            findings=[DiagnosisFinding(level="warning", title="客服数据不可用", detail=detail)],
            actions=[RecommendedAction(priority="P0", title="检查客服数据采集", detail="区分客服平台无数据、尚未采集和日期覆盖不足，再重新分析。", owner="数据运营", validation="客服概览和账号明细覆盖所选日期")],
            causal_boundary="当前没有客服事实数据，不对成交或服务质量做业务推断。",
        )
    data = result.data or {}
    current = data.get("current") or {}
    comparison = data.get("comparison") or {}
    accounts = data.get("accounts") or []
    sales_change = (comparison.get("sales_amount") or {}).get("change_percent")
    conversion_change = (comparison.get("sales_conversion_rate") or {}).get("change_percent")
    response_change = (comparison.get("avg_reply_seconds") or {}).get("change_percent")
    satisfaction_change = (comparison.get("satisfaction_rate") or {}).get("change_percent")
    findings: list[DiagnosisFinding] = []
    actions: list[RecommendedAction] = []
    sales_detail = f"客服销售额 {float(current.get('sales_amount') or 0):,.0f}，净销售额 {float(current.get('net_sales_amount') or 0):,.0f}"
    if sales_change is not None:
        sales_detail += f"，环比 {float(sales_change):+.1f}%"
    findings.append(DiagnosisFinding(level="warning" if sales_change is not None and sales_change < -10 else "positive" if sales_change is not None and sales_change > 10 else "info", title="客服成交结果", detail=sales_detail, metric_ids=["customer_service_sales", "customer_service_net_sales"]))
    consult = float(current.get("consult_users") or 0); reception = float(current.get("reception_users") or 0); buyers = float(current.get("sale_users") or 0)
    funnel_detail = f"咨询 {consult:,.0f} 人，接待 {reception:,.0f} 人，客服成交 {buyers:,.0f} 人；接待率 {float(current.get('reception_rate') or 0):.2f}%，询单转化率 {float(current.get('sales_conversion_rate') or 0):.2f}%"
    if conversion_change is not None:
        funnel_detail += f"，转化环比 {float(conversion_change):+.1f}%"
    findings.append(DiagnosisFinding(level="warning" if conversion_change is not None and conversion_change < -10 else "info", title="客服咨询漏斗", detail=funnel_detail, metric_ids=["customer_service_conversion", "customer_service_reception_rate"]))
    if response_change is not None or satisfaction_change is not None:
        detail = f"平均响应 {float(current.get('avg_reply_seconds') or 0):.1f} 秒，满意率 {float(current.get('satisfaction_rate') or 0):.2f}%"
        if response_change is not None:
            detail += f"；响应时长环比 {float(response_change):+.1f}%"
        if satisfaction_change is not None:
            detail += f"；满意率环比 {float(satisfaction_change):+.1f}%"
        level = "warning" if (response_change is not None and response_change > 10) or (satisfaction_change is not None and satisfaction_change < -5) else "info"
        findings.append(DiagnosisFinding(level=level, title="服务质量信号", detail=detail, metric_ids=["avg_reply_seconds", "satisfaction_rate"]))
    active_accounts = [item for item in accounts if float(item.get("consult_users") or 0) > 0]
    weak_account = min(active_accounts, key=lambda item: float(item.get("sales_conversion_rate") or 0), default=None)
    top_account = max(accounts, key=lambda item: float(item.get("sales_amount") or 0), default=None)
    if weak_account:
        weak_name = weak_account.get("account_name") or "未命名客服"
        findings.append(DiagnosisFinding(level="warning", title="客服账号承接存在差异", detail=f"{weak_name} 咨询 {float(weak_account.get('consult_users') or 0):,.0} 人，接待率 {float(weak_account.get('reception_rate') or 0):.2f}%，询单转化率 {float(weak_account.get('sales_conversion_rate') or 0):.2f}%；账号样本用于定位，不等同绩效定责。", metric_ids=["customer_service_conversion"]))
        actions.append(RecommendedAction(priority="P0", title="复盘低承接客服账号", detail=f"先复盘 {weak_name} 的接待、响应和咨询转化明细，区分排班、流量分配和话术问题，不直接按销售额奖惩。", owner="客服主管", validation="该账号接待率和询单转化率回到团队中位数"))
    if conversion_change is not None and conversion_change < -10:
        actions.append(RecommendedAction(priority="P0", title="修复咨询到成交漏斗", detail="按日拆解咨询→接待→下单→销售人数，重点检查低转化日期的响应时长、优惠解释和库存承接。", owner="客服主管", validation="询单转化率连续 3 天回升且退款率不恶化"))
    if response_change is not None and response_change > 10:
        actions.append(RecommendedAction(priority="P1", title="压降客服响应时长", detail="按小时段和账号检查排班缺口，优先覆盖咨询高峰；响应时长只作为服务信号，不直接证明因果。", owner="客服主管", validation="平均响应时长下降且接待率不下降"))
    actions.append(RecommendedAction(priority="P2", title="追踪客服净成交质量", detail="并列查看销售额、成功退款和净销售额，避免只按客服销售额判断服务价值。", owner="经营负责人", validation="净销售额占比稳定且退款金额不异常上升"))
    daily_rows = [{"业务日": row.get("business_day"), "客服销售额": row.get("sales_amount"), "净销售额": row.get("net_sales_amount"), "咨询人数": row.get("consult_users"), "接待人数": row.get("reception_users"), "销售人数": row.get("sale_users"), "询单转化率%": (float(row.get("sale_users") or 0) / float(row.get("consult_users") or 0) * 100 if float(row.get("consult_users") or 0) else None), "平均响应秒": row.get("avg_reply_seconds"), "满意率%": (float(row.get("satisfaction_rate") or 0) * 100 if float(row.get("satisfaction_rate") or 0) <= 1 else row.get("satisfaction_rate"))} for row in data.get("daily") or []]
    account_rows = [{"客服": item.get("account_name"), "咨询人数": item.get("consult_users"), "接待率%": item.get("reception_rate"), "销售人数": item.get("sale_users"), "销售额": item.get("sales_amount"), "询单转化率%": item.get("sales_conversion_rate"), "客服客单价": item.get("sales_unit_price"), "退款率%": item.get("refund_rate")} for item in accounts[:30]]
    return Diagnosis(
        headline=findings[0].title,
        summary=findings[0].detail,
        findings=findings[:6],
        actions=actions[:6],
        artifacts=[ArtifactSpec(type="line_chart", title="客服日趋势", rows=daily_rows), ArtifactSpec(type="matrix", title="客服账号表现", rows=account_rows)],
        assumptions=["客服询单转化率统一按客服销售人数 ÷ 咨询人数重算；客服销售额为客服报表归因口径。"],
        denominator_notes=["接待率 = 有效接待人数 ÷ 咨询人数；询单转化率 = 客服销售人数 ÷ 咨询人数；账号排行不将零咨询账号当作低转化。"],
        causal_boundary="客服销售额、询单转化和响应指标是客服报表归因/描述性信号；没有咨询会话级对照时，不把响应变化直接说成成交因果。",
        next_questions=["下钻低转化客服账号和日期", "查看客服退款较高的商品", "比较客服成交与店铺整体转化"],
    )


def _review_diagnosis(results: list[MCPEnvelope]) -> Diagnosis:
    result = next((item for item in results if item.tool == "reviews.get_diagnosis"), results[0] if results else None)
    if result is None or result.status == "no_data":
        detail = "当前没有可用的评价或问大家记录，不能判断商品口碑、问题分类和售前疑虑。"
        return Diagnosis(
            headline="用户反馈数据不可用",
            summary=detail,
            findings=[DiagnosisFinding(level="warning", title="用户反馈数据不可用", detail=detail)],
            actions=[RecommendedAction(priority="P0", title="检查评价与问大家采集", detail="确认评价和问大家任务是否完成，并区分没有记录与尚未采集。", owner="数据运营", validation="评价和问大家均出现最新采集时间")],
            causal_boundary="没有用户反馈事实数据时，不对商品质量或成交影响做推断。",
        )
    reviews = result.data.get("reviews") or {}
    asks = result.data.get("asks") or {}
    categories = reviews.get("category_counts") or []
    risk_products = reviews.get("risk_products") or []
    risk_series = reviews.get("risk_series") or []
    total = int(reviews.get("total_reviews") or 0)
    issue_count = int(reviews.get("negative_reviews") or 0)
    issue_rate = float(reviews.get("negative_rate") or 0)
    findings = [DiagnosisFinding(
        level="warning" if issue_rate >= 10 else "info",
        title="评价问题信号已汇总",
        detail=f"所选区间评价 {total:,} 条，其中问题评价 {issue_count:,} 条，问题评价率 {issue_rate:.2f}%；该比例与星级评价分开，不把词频当作差评率。",
        metric_ids=["review_count", "negative_review_rate"],
    )]
    if categories:
        top = "、".join(f"{item.get('name')} {int(item.get('count') or 0)} 条" for item in categories[:3])
        findings.append(DiagnosisFinding(level="warning", title="主要用户问题", detail=f"高频问题为：{top}。需要回看代表文本并关联具体系列、商品和批次后再定责。"))
    if risk_products:
        item = risk_products[0]
        findings.append(DiagnosisFinding(level="warning", title="高风险商品需要优先复核", detail=f"{item.get('label') or item.get('key')} 共 {int(item.get('total_reviews') or 0)} 条评价，问题率 {float(item.get('issue_rate') or 0):.2f}%，主要问题为 {item.get('top_issue') or '待归类'}。"))
    unanswered = int(asks.get("unanswered_questions") or 0)
    if unanswered:
        findings.append(DiagnosisFinding(level="warning", title="问大家存在未承接需求", detail=f"当前已采集问大家中有 {unanswered:,} 条未回答，回答率 {float(asks.get('answer_rate') or 0):.2f}%；这是售前疑虑承接信号。", metric_ids=["unanswered_question_count"]))
    actions = [
        RecommendedAction(priority="P0", title="处理高频问题商品", detail="按问题分类→系列→商品查看代表评价，先确认是否集中于具体商品、规格或批次，再安排详情页说明、客服口径或品质复核。", owner="商品运营/品控", validation="目标商品问题评价率在后续 14 天下降，且退款率不恶化"),
        RecommendedAction(priority="P1", title="补齐问大家高频未回答问题", detail="将未回答问题按商品和问题分类分派给客服，沉淀尺码、使用、成分和售后标准答案。", owner="客服主管", validation="问大家回答率提升，重复咨询占比下降"),
        RecommendedAction(priority="P2", title="联动成交与售后验证", detail="把高风险商品与支付金额、转化和退款并列观察；评价问题只作为解释信号，不直接宣称造成成交变化。", owner="经营负责人", validation="问题信号改善同时净支付金额和商品转化不下降"),
    ]
    artifacts = [
        ArtifactSpec(type="matrix", title="评价问题分类", rows=[{"问题": item.get("name"), "评价数": item.get("count"), "占评价比%": item.get("share")} for item in categories[:20]]),
        ArtifactSpec(type="matrix", title="评价风险商品", rows=[{"商品": item.get("label"), "系列": item.get("series"), "评价数": item.get("total_reviews"), "问题评价数": item.get("issue_reviews"), "问题率%": item.get("issue_rate"), "主要问题": item.get("top_issue")} for item in risk_products[:20]]),
        ArtifactSpec(type="matrix", title="评价风险系列", rows=[{"系列": item.get("label"), "评价数": item.get("total_reviews"), "问题评价数": item.get("issue_reviews"), "问题率%": item.get("issue_rate"), "主要问题": item.get("top_issue")} for item in risk_series[:20]]),
    ]
    return Diagnosis(
        headline=findings[0].title,
        summary=findings[0].detail,
        findings=findings,
        actions=actions,
        artifacts=artifacts,
        assumptions=["问题评价率来自评价文本分类；问大家汇总为当前已采集全量。"],
        denominator_notes=["问题评价率 = 问题评价数 ÷ 所选范围评价数；问题词频不能替代星级或差评率。"],
        causal_boundary="评价、问大家和成交之间是描述性关联；没有商品级时间对照或实验时，不把用户反馈直接表述为成交下降因果。",
        next_questions=["下钻问题率最高的商品评价", "查看问大家未回答问题", "把评价风险与商品退款和成交关联"],
    )


def _product_structure_diagnosis(results: list[MCPEnvelope]) -> Diagnosis:
    result = next((item for item in results if item.tool == "products.get_structure_profile"), results[0] if results else None)
    if result is None or result.status == "no_data":
        detail = "所选区间没有商品排行数据，不能按系列、类型和商品拆解客单价。"
        return Diagnosis(headline="商品结构数据不可用", summary=detail, findings=[DiagnosisFinding(level="warning", title="商品排行数据不可用", detail=detail)], actions=[RecommendedAction(priority="P0", title="检查商品排行采集", detail="区分未采集日期与平台无数据，再重新执行客单价结构分析。", owner="数据运营", validation="商品排行覆盖当前和上一周期")])
    data = result.data or {}; summary = data.get("summary") or {}; atv_delta = summary.get("unit_price_delta"); atv_change = summary.get("unit_price_change_percent")
    direction = "下降" if atv_delta is not None and float(atv_delta) < 0 else "上升" if atv_delta is not None and float(atv_delta) > 0 else "基本稳定"
    findings = [DiagnosisFinding(level="warning" if direction == "下降" else "positive" if direction == "上升" else "info", title=f"整体客单价{direction}", detail=f"当前客单价 {float(summary.get('current_unit_price') or 0):.2f} 元，上期 {float(summary.get('previous_unit_price') or 0):.2f} 元，变化 {float(atv_delta or 0):+.2f} 元（{float(atv_change or 0):+.1f}%）。", metric_ids=["customer_unit_price"])]
    series = data.get("series") or []; types = data.get("types") or []; products = data.get("products") or []
    negative_series = [item for item in series if float(item.get("aov_contribution") or 0) < 0]
    negative_types = [item for item in types if float(item.get("aov_contribution") or 0) < 0]
    negative_products = [item for item in products if float(item.get("aov_contribution") or 0) < 0]
    if negative_series:
        sample = "、".join(f"{item.get('name')}（{float(item.get('aov_contribution') or 0):+.2f}元）" for item in negative_series[:3])
        findings.append(DiagnosisFinding(level="warning", title="系列层存在客单价拖累项", detail=f"按 GMV/支付买家桥接，主要拖累：{sample}；这是结构描述，不代表该系列单独造成全部下降。", metric_ids=["customer_unit_price"]))
    if negative_types:
        sample = "、".join(f"{item.get('name')}（买家占比 {float(item.get('buyer_share_delta_pp') or 0):+.2f} 个百分点）" for item in negative_types[:3])
        findings.append(DiagnosisFinding(level="warning", title="类型结构发生不利变化", detail=f"主要关注：{sample}。同时核对正装/MINI装/试用装的买家占比和类型客单价。", metric_ids=["customer_unit_price"]))
    actions = [RecommendedAction(priority="P0", title="优先复核客单价拖累系列", detail="按系列 → 类型 → 商品查看当前/上期客单价、买家占比和支付金额，先核对低价结构是否放大，再检查价格和优惠门槛。", owner="商品运营", validation="拖累系列/类型的买家占比或客单价恢复，整体客单价回升"), RecommendedAction(priority="P1", title="检查主销商品结构变化", detail="对负向贡献最大的商品核对正装、MINI装、试用装、组合装和活动价；没有商品主档映射的条目标记待归类，不凭名称猜测。", owner="商品运营", validation="主销商品结构可解释且低价商品占比不再上升"), RecommendedAction(priority="P2", title="联动验证转化与退款", detail="客单价优化不能牺牲支付转化和售后质量，连续观察商品转化率、退款率和净支付金额。", owner="经营负责人", validation="客单价回升同时支付转化率不下降、退款率不恶化")]
    artifacts = [ArtifactSpec(type="matrix", title="客单价下降·系列", rows=[{"系列": item.get("name"), "商品数": item.get("product_count"), "当前客单价": item.get("current_unit_price"), "上期客单价": item.get("previous_unit_price"), "客单价变化": item.get("unit_price_delta"), "买家占比变化": item.get("buyer_share_delta_pp"), "客单价桥接贡献": item.get("aov_contribution"), "当前支付金额": item.get("current_paid_amount"), "上期支付金额": item.get("previous_paid_amount")} for item in series]), ArtifactSpec(type="matrix", title="客单价下降·类型", rows=[{"类型": item.get("name"), "商品数": item.get("product_count"), "当前客单价": item.get("current_unit_price"), "上期客单价": item.get("previous_unit_price"), "客单价变化": item.get("unit_price_delta"), "买家占比变化": item.get("buyer_share_delta_pp"), "客单价桥接贡献": item.get("aov_contribution")} for item in types]), ArtifactSpec(type="matrix", title="客单价下降·商品", rows=[{"商品": item.get("product_name"), "商品ID": item.get("product_id"), "系列": item.get("series"), "类型": item.get("product_type"), "当前客单价": item.get("current_unit_price"), "上期客单价": item.get("previous_unit_price"), "客单价变化": item.get("unit_price_delta"), "买家占比变化": item.get("buyer_share_delta_pp"), "客单价桥接贡献": item.get("aov_contribution"), "当前支付金额": item.get("current_paid_amount"), "上期支付金额": item.get("previous_paid_amount")} for item in products[:30]])]
    return Diagnosis(headline=findings[0].title, summary=findings[0].detail, findings=findings[:6], actions=actions, artifacts=artifacts, assumptions=["客单价 = 商品支付金额合计 ÷ 商品支付买家合计；系列/类型来自商品主档，缺失映射归入待归类。"], denominator_notes=["客单价桥接贡献按‘当前组支付金额/当前总买家 − 上期组支付金额/上期总买家’分摊，合计可还原总客单价变化；属于描述性桥接，不是因果增量。"], causal_boundary="商品结构、价格和活动数据只能描述客单价变化及其相关贡献；没有商品级对照实验时，不把某个系列直接表述为唯一因果。", next_questions=["下钻客单价拖累最大的商品", "只看正装与试用装结构变化", "比较客单价下降商品的活动价和库存"])


SKILLS = (
    _runtime_skill("inventory-query", _inventory_diagnosis),
    _runtime_skill("data-exploration", _generic_data_diagnosis),
    _runtime_skill("data-quality-audit", _data_quality_diagnosis),
    _runtime_skill("customer-service-diagnosis", _customer_service_diagnosis),
    _runtime_skill("review-diagnosis", _review_diagnosis),
    _runtime_skill("product-structure-diagnosis", _product_structure_diagnosis),
    _runtime_skill("product-diagnosis", _product_diagnosis),
    _runtime_skill("customer-retention", _customer_diagnosis),
    _runtime_skill("utry-repurchase-diagnosis", _utry_repurchase_diagnosis),
    _runtime_skill("mini-product-diagnosis", _mini_product_diagnosis),
    _runtime_skill("shop-overview-diagnosis", _overview_diagnosis),
    _runtime_skill("traffic-diagnosis", _traffic_diagnosis),
    _runtime_skill("market-insight", _market_diagnosis),
    _runtime_skill("promotion-roi", _promotion_diagnosis),
    _runtime_skill("promotion-budget-planning", _promotion_budget_diagnosis, accepts_inputs=True),
    _runtime_skill("campaign-planning", _campaign_planning_diagnosis, accepts_inputs=True),
    _runtime_skill("period-report-generation", _period_report_diagnosis),
    _runtime_skill("general-chat", _general_chat_diagnosis, accepts_inputs=True),
)


def _is_general_chat_question(question: str) -> bool:
    lowered = question.casefold().strip()
    if not lowered:
        return True
    chat_tokens = ("你好", "您好", "在吗", "hello", "hi", "hey", "帮我", "能做什么", "可以做什么", "怎么用", "怎么问", "上下文", "能力", "介绍一下", "聊聊")
    if not any(token in lowered for token in chat_tokens):
        return False
    business_tokens = tuple({
        keyword.casefold()
        for skill in SKILLS
        if skill.descriptor.name != "general-chat"
        for keyword in skill.keywords
        if keyword
    })
    return not any(token in lowered for token in business_tokens)


def _is_mini_product_question(question: str) -> bool:
    """Identify MINI/trial-product requests before broad page routing.

    MINI questions are deliberately treated as a product identity workflow:
    the catalog establishes the product IDs, then the dedicated MCP tool joins
    sales, promotion, VOC and U先 evidence. This prevents a generic
    ``data-exploration`` response from claiming that U先 is empty before it is
    queried.
    """
    lowered = question.casefold()
    return any(token in lowered for token in (
        "mini", "mini装", "尝鲜装", "尝鲜", "小规格", "试用装商品",
    ))


def _generic_chat_skill() -> RuntimeSkill:
    return next(skill for skill in SKILLS if skill.descriptor.name == "general-chat")


def _is_cross_domain_question(question: str) -> bool:
    """Keep broad business questions on the overview orchestrator.

    A request such as “成交下降，请结合商品、推广和客服数据” mentions
    several domains, but it is still a store-level diagnosis. Routing it to
    the last keyword (客服) makes the visible Agent and headline misleading.
    Explicit page/domain prompts such as “分析客服账号” remain specialized.
    """
    lowered = question.casefold().strip()
    broad_tokens = (
        "为什么", "成交下降", "成交增长", "经营诊断", "经营问题", "最重要的", "原因和动作",
        "全店", "全盘", "全域", "整体", "整个店铺", "店铺整体", "全面分析", "综合分析", "所有数据",
    )
    return any(token in lowered for token in broad_tokens)


def _is_explicit_service_question(question: str) -> bool:
    lowered = question.casefold().strip()
    service_tokens = ("客服", "咨询", "接待", "询单", "响应", "满意率", "旺旺", "客服账号", "客服成交")
    if not any(token in lowered for token in service_tokens):
        return False
    return bool(re.search(r"(?:分析|诊断|查看|下钻|复盘|排查|比较).{0,10}(客服|咨询|接待|询单|响应|满意率|旺旺)", lowered)) or lowered.startswith(("客服", "咨询", "接待", "询单"))


def _is_promotion_efficiency_question(question: str) -> bool:
    lowered = question.casefold().strip()
    channel_tokens = ("渠道", "来源", "场景", "计划", "推广", "投放", "广告", "roi", "投产", "投入产出", "花费")
    budget_tokens = ("加预算", "增预算", "降预算", "预算调整", "值得投", "值得加", "扩量", "效率", "产出")
    return any(token in lowered for token in channel_tokens) and any(token in lowered for token in budget_tokens)


def _is_budget_planning_question(question: str) -> bool:
    lowered = question.casefold().strip()
    return any(token in lowered for token in ("预算怎么分", "预算怎么拆", "预算分配", "预算规划", "预算节奏", "目标roi", "目标投产", "总预算"))


def select_skill(question: str, domain: str, page_context: dict[str, Any] | None = None) -> RuntimeSkill:
    _ = page_context
    if _is_general_chat_question(question):
        return _generic_chat_skill()
    lowered = question.casefold()
    mini = next((skill for skill in SKILLS if skill.descriptor.name == "mini-product-diagnosis"), None)
    if mini and _is_mini_product_question(question):
        return mini
    if any(token in lowered for token in ("u先", "u 先", "u先回购", "u先复购", "试用回购", "派样回购")):
        utry = next((skill for skill in SKILLS if skill.descriptor.name == "utry-repurchase-diagnosis"), None)
        if utry:
            return utry
    if domain != "auto":
        match = next((skill for skill in SKILLS if domain in skill.descriptor.domains), None)
        if match:
            return match
    if _is_promotion_efficiency_question(question) and not _is_budget_planning_question(question):
        promotion = next((skill for skill in SKILLS if skill.descriptor.name == "promotion-roi"), None)
        if promotion:
            return promotion
    service_tokens = ("客服", "咨询", "接待", "询单", "响应", "满意率", "旺旺", "客服账号", "客服成交")
    if any(token in lowered for token in service_tokens) and not (_is_cross_domain_question(question) and not _is_explicit_service_question(question)):
        service = next((skill for skill in SKILLS if skill.descriptor.name == "customer-service-diagnosis"), None)
        if service:
            return service
    structure_tokens = ("客单价", "客单", "客价")
    structure_dimensions = ("系列", "类型", "商品", "货品", "sku", "结构", "下钻")
    if any(token in lowered for token in structure_tokens) and any(token in lowered for token in structure_dimensions):
        structure = next((skill for skill in SKILLS if skill.descriptor.name == "product-structure-diagnosis"), None)
        if structure:
            return structure
    # Product questions must win over the generic "分析/查询/数据" keywords.
    # The service has a product-specific lookup workflow (catalog search ->
    # unique product profile), so showing data-exploration here would make the
    # audit trail and the visible capability label disagree with the work that
    # is actually executed.
    inventory_tokens = ("库存", "缺货", "断货", "尺码", "sku库存", "现货", "可用量")
    promotion_tokens = ("推广", "投放", "广告", "roi", "投产", "花费", "计划")
    product_tokens = ("商品", "货品", "单品", "sku", "主销", "爆款", "商品id", "商品 id", "系列")
    if (
        any(token in lowered for token in product_tokens)
        and not any(token in lowered for token in inventory_tokens)
        and not (any(token in lowered for token in promotion_tokens) and not any(token in lowered for token in ("单品分析", "商品分析", "商品表现", "商品id", "商品 id")))
    ):
        product = next((skill for skill in SKILLS if skill.descriptor.name == "product-diagnosis"), None)
        if product:
            return product
    quality = next((skill for skill in SKILLS if skill.descriptor.name == "data-quality-audit"), None)
    if quality and any(keyword.lower() in lowered for keyword in quality.keywords):
        return quality
    planning = next((skill for skill in SKILLS if skill.descriptor.name == "campaign-planning"), None)
    if planning and any(keyword.lower() in lowered for keyword in planning.keywords):
        return planning
    budget = next((skill for skill in SKILLS if skill.descriptor.name == "promotion-budget-planning"), None)
    if budget and any(keyword.lower() in lowered for keyword in budget.keywords):
        return budget
    ranked = sorted(SKILLS, key=lambda skill: sum(keyword.lower() in lowered for keyword in skill.keywords), reverse=True)
    return ranked[0] if ranked and any(keyword in lowered for keyword in ranked[0].keywords) else _generic_chat_skill()


def select_skills(question: str, domain: str, page_context: dict[str, Any] | None = None) -> tuple[RuntimeSkill, list[RuntimeSkill]]:
    """Return a primary business skill and safe supporting skills.

    The primary skill owns calculations and the response headline. Supporting
    skills describe the next evidence domains to load or drill into; keeping
    this explicit lets the API/UI show the plan without pretending that a
    keyword router performed a full autonomous workflow.
    """
    page_context = page_context or {}
    page_key = str(page_context.get("page_key") or page_context.get("page") or "")
    page_skill_names = {
        "overview": "shop-overview-diagnosis",
        "analytics": "shop-overview-diagnosis",
        "products": "product-structure-diagnosis",
        "product-analysis": "product-diagnosis",
        "service": "customer-service-diagnosis",
        "traffic": "traffic-diagnosis",
        "promotions": "promotion-roi",
        "promotions-cps": "data-exploration",
        "market": "market-insight",
        "customers": "customer-retention",
        "customer-members": "customer-retention",
        "reviews": "review-diagnosis",
        "content": "data-exploration",
        "live": "data-exploration",
        "marketing-activities": "data-exploration",
        "marketing-flash-sale": "data-exploration",
        "marketing-new-customer": "data-exploration",
        "marketing-shopping-gold": "data-exploration",
        "marketing-bybt": "data-exploration",
        "inventory": "data-exploration",
        "brand-assets": "data-exploration",
    }
    primary = None
    # A greeting remains a lightweight chat even inside a business page.
    # Generic page prompts (“分析一下当前页面”) use the page's real domain.
    if page_key and page_key != "ai" and not _is_general_chat_question(question):
        page_name = page_skill_names.get(page_key)
        primary = next((skill for skill in SKILLS if skill.descriptor.name == page_name), None) if page_name else None
    # The AI workbench is a cross-domain page. Let explicit specialist prompts
    # win, while broad store questions use the overview orchestrator.
    if page_key == "ai" and not _is_general_chat_question(question) and _is_cross_domain_question(question) and not _is_explicit_service_question(question):
        primary = next((skill for skill in SKILLS if skill.descriptor.name == "shop-overview-diagnosis"), None)
    primary = primary or select_skill(question, domain, page_context)
    # Explicit MINI/尝鲜 wording owns the workflow even when the request came
    # from a generic products or AI workbench page. The dedicated tool starts
    # from catalog identity and joins all requested evidence by product ID.
    if _is_mini_product_question(question):
        primary = next((skill for skill in SKILLS if skill.descriptor.name == "mini-product-diagnosis"), primary)
    if any(token in question.casefold() for token in ("u先", "u 先", "u先回购", "u先复购", "试用回购", "派样回购")):
        # A combined MINI + U先 request needs the product-ID join first. A
        # U先-only request remains on the existing U先 snapshot workflow.
        if not _is_mini_product_question(question):
            primary = next((skill for skill in SKILLS if skill.descriptor.name == "utry-repurchase-diagnosis"), primary)
    support_names: list[str] = []
    plans = {
        "campaign-planning": ["promotion-budget-planning", "product-diagnosis", "data-quality-audit"],
        "promotion-budget-planning": ["promotion-roi", "product-diagnosis", "data-quality-audit"],
        "promotion-roi": ["data-quality-audit"],
        "shop-overview-diagnosis": [
            "traffic-diagnosis", "product-diagnosis", "promotion-roi", "customer-retention",
            "customer-service-diagnosis", "review-diagnosis", "data-exploration", "data-quality-audit",
        ],
        "traffic-diagnosis": ["data-quality-audit"],
        "market-insight": ["data-quality-audit", "product-diagnosis", "traffic-diagnosis"],
        "product-diagnosis": ["data-quality-audit"],
        "product-structure-diagnosis": ["product-diagnosis", "data-quality-audit"],
        "customer-service-diagnosis": ["data-quality-audit", "shop-overview-diagnosis"],
        "review-diagnosis": ["product-diagnosis", "data-quality-audit"],
        "customer-retention": ["data-quality-audit"],
        "utry-repurchase-diagnosis": ["data-quality-audit", "product-diagnosis"],
        "mini-product-diagnosis": ["product-diagnosis", "review-diagnosis", "utry-repurchase-diagnosis", "data-quality-audit"],
        "period-report-generation": ["data-quality-audit"],
    }
    support_names.extend(plans.get(primary.descriptor.name, []))
    lowered = question.casefold()
    if any(token in lowered for token in ("缺失", "覆盖", "补采", "完整")) and primary.descriptor.name != "data-quality-audit":
        support_names.insert(0, "data-quality-audit")
    by_name = {skill.descriptor.name: skill for skill in SKILLS if skill.descriptor.enabled}
    supporting: list[RuntimeSkill] = []
    for name in support_names:
        skill = by_name.get(name)
        if skill and skill.descriptor.name != primary.descriptor.name and skill not in supporting:
            supporting.append(skill)
    return primary, supporting
