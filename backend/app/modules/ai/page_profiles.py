from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PageAIProfile:
    key: str
    title: str
    section: str
    domain: str
    primary_skill: str
    goal: str
    diagnostic_question: str
    data_domains: tuple[str, ...]
    datasets: tuple[str, ...]
    recommended_questions: tuple[str, ...]
    focus_dimensions: tuple[str, ...] = ()

    @property
    def decision_lens(self) -> dict[str, str]:
        return dict(PAGE_DECISION_LENSES.get(self.key, DEFAULT_DECISION_LENS))

    @property
    def quality_checks(self) -> tuple[str, ...]:
        return PAGE_QUALITY_CHECKS.get(self.key, DEFAULT_QUALITY_CHECKS)

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "section": self.section,
            "domain": self.domain,
            "primary_skill": self.primary_skill,
            "goal": self.goal,
            "diagnostic_question": self.diagnostic_question,
            "data_domains": list(self.data_domains),
            "datasets": list(self.datasets),
            "recommended_questions": list(self.recommended_questions),
            "focus_dimensions": list(self.focus_dimensions),
            "decision_lens": self.decision_lens,
            "quality_checks": list(self.quality_checks),
        }


def _profile(
    key: str,
    title: str,
    section: str,
    domain: str,
    primary_skill: str,
    goal: str,
    diagnostic_question: str,
    data_domains: tuple[str, ...],
    datasets: tuple[str, ...],
    recommended_questions: tuple[str, ...],
    focus_dimensions: tuple[str, ...] = (),
) -> PageAIProfile:
    return PageAIProfile(
        key=key,
        title=title,
        section=section,
        domain=domain,
        primary_skill=primary_skill,
        goal=goal,
        diagnostic_question=diagnostic_question,
        data_domains=data_domains,
        datasets=datasets,
        recommended_questions=recommended_questions,
        focus_dimensions=focus_dimensions,
    )


DEFAULT_DECISION_LENS = {
    "result": "当前值、对比变化与目标差距",
    "cause": "规模、效率与结构变化",
    "affected": "具体渠道、商品或人群",
    "action": "优先处理影响最大的对象",
    "validation": "观察核心指标并设置停止条件",
}

DEFAULT_QUALITY_CHECKS = ("数据截止日与覆盖天数", "关键指标分母与统计口径", "缺失字段不能按 0 解释")


def _lens(result: str, cause: str, affected: str, action: str, validation: str) -> dict[str, str]:
    return {
        "result": result,
        "cause": cause,
        "affected": affected,
        "action": action,
        "validation": validation,
    }


PAGE_DECISION_LENSES: dict[str, dict[str, str]] = {
    "overview": _lens("支付、净成交与目标差距", "流量 × 转化 × 客单与退款", "渠道、系列、类型与客户结构", "锁定金额影响最大的三项", "3-7 天复核贡献金额与核心效率"),
    "analytics": _lens("支付、退款、净成交和客单", "买家、件数、件单价与退款拆解", "系列、商品及新老客", "修复主要掉点并保护净成交", "共同覆盖周期复核金额贡献"),
    "traffic": _lens("访客、转化率与 UV 价值", "来源规模、点击质量和页面承接", "来源层级、入口与承接商品", "扩优质来源、修低效入口", "7 天观察转化率、UV 价值和费用"),
    "customers": _lens("首购与老客人数、金额和客单", "新访、未购回访、已购回访迁移", "首购商品、沉默人群与 MINI 客群", "拉新、承接、复购、召回分层执行", "7/30/60/90 天观察迁移与复购"),
    "customer-members": _lens("新增、活跃、成交与会员贡献", "入会来源、激活和复购质量", "U先来源、会员层级与权益人群", "降低来源集中度并补入会后承接", "30/60/90 天复核成交与复购"),
    "products": _lens("系列、类型、商品的成交结构", "流量、转化、价格、退款与库存", "潜力款、风险款和结构拖累项", "按增长、利润信号、库存风险分策略", "7-14 天复核转化、退款与库存覆盖"),
    "product-analysis": _lens("单品全链路成交质量", "流量、详情、加购、支付、退款、复购", "商品 ID、SKU、计划和评价主题", "联动页面、投放、口碑与库存动作", "3-7 天观察漏斗和风险指标"),
    "promotions": _lens("花费、归因成交、ROI 与费用率", "场景、计划、单元、词和人群效率", "应停、应降、应扩的具体计划", "按边际 ROI 做限额测试", "3-7 天复核边际 ROI 与转化"),
    "promotions-cps": _lens("付款、结算、佣金与退款后贡献", "达人、商品、佣金率和退款扣除", "高贡献达人、低效合作方与集中风险", "调整合作、佣金或选品", "结算周期复核有效订单与净贡献"),
    "marketing-activities": _lens("活动前中后成交与交易质量", "流量、转化、客单、退款和结构", "活动、商品、渠道与客户群", "补救活动后回落和风险项", "活动后 3-7 天复核留存与退款"),
    "marketing-flash-sale": _lens("曝光、成交、售罄与退款", "流量、转化、价格和库存准备", "秒杀商品、时段和库存编码", "调库存、价格或活动承接", "活动后 3-7 天观察退款和日销挤压"),
    "marketing-new-customer": _lens("真实新客、首购金额与获客信号", "折扣、商品、流量和首购转化", "新客商品、渠道和未二购人群", "优化首购门槛与二购承接", "30/60 天复核二购和回本信号"),
    "marketing-shopping-gold": _lens("充值、核销、余额与带动成交", "充值到使用的漏斗和退款风险", "沉淀余额人群、权益和商品", "促进核销并控制资金沉淀", "7/30 天复核核销率和带动金额"),
    "marketing-bybt": _lens("补贴归因成交、转化与价格力", "商品、价格带、流量和自然成交变化", "补贴商品、类目和库存编码", "调商品、价格与库存承接", "7 天复核转化、退款和自然成交"),
    "marketing-utry": _lens("派样、入会、正装首购与回购证据", "MINI 识别、正装绑定和权益承接", "MINI 商品 ID、系列和正装商品", "补映射、权益、推广和内容承接", "30/60/90 天复核正装购买"),
    "service": _lens("响应、接待、询单成交与退款", "账号效率、问题类型和商品承接", "客服账号、问题主题与具体 SKU", "优化排班、话术和商品信息", "3-7 天复核响应时长与询单转化"),
    "content": _lens("曝光、观看、点击、进店与成交", "内容吸引力和承接商品匹配", "内容 ID、素材、账号与商品", "调整选题、素材或商品承接", "7 天复核点击、进店和成交漏斗"),
    "live": _lens("店播与达播的观看、点击和成交", "场次、时段、坑位、停留和退款", "直播场次、达人和主推商品", "优化排期、讲解、选品和投流", "逐场复核 GPM、转化和退款后产出"),
    "market": _lens("类目、份额、价格带和需求变化", "竞品、搜索词与价格结构", "类目、竞品、关键词和机会价格带", "用小预算或商品测试验证机会", "7-14 天复核搜索、点击和成交信号"),
    "brand-assets": _lens("访客、粉丝、会员、首购与复购资产", "人群关系迁移和商品承接", "高潜人群、来源和承接商品", "推动关注到入会到购买迁移", "30 天复核迁移率与成交质量"),
    "reviews": _lens("评分、差评率、问题率和问答缺口", "问题主题、商品集中度和服务关联", "商品、系列、评价主题和未回答问题", "修详情、品控、客服话术和问答", "7-14 天复核问题率、退款和转化"),
    "inventory": _lens("可售库存、覆盖天数与资金占用信号", "销量速度、缺货、滞销和组合关系", "货品编码、SKU、尺码和系列", "补货、调拨、清理或修正映射", "按补货周期复核可售天数和断货"),
}


PAGE_QUALITY_CHECKS: dict[str, tuple[str, ...]] = {
    "overview": ("支付与退款必须分口径", "各结构占比使用全量分母", "日报截止日与缺失日期"),
    "analytics": ("支付金额不等于 GMV", "新老客金额必须可对账", "比较周期覆盖天数一致"),
    "traffic": ("父子来源不可重复求和", "访客与成交使用同一来源口径", "缺失来源不按 0"),
    "customers": ("人数为每日累计还是跨日去重", "repeat_rate 与复购人数一致性", "首购定义依赖完整历史订单"),
    "customer-members": ("入会来源字段完整", "会员与非会员分母一致", "U先新增占比与后续成交窗口"),
    "products": ("系列与类型映射覆盖", "Top N 不替代全量分母", "退款和库存业务日一致"),
    "product-analysis": ("商品 ID 与 SKU 映射", "推广归因窗口明确", "评价、问答和库存均有最新日期"),
    "promotions": ("直接与间接成交分开", "ROI 不等于利润率", "计划总计基于全量记录"),
    "promotions-cps": ("付款与结算分开", "佣金与广告费不混算", "退款扣除和结算周期明确"),
    "marketing-activities": ("活动前中后窗口等长", "活动变化不直接宣称增量", "优惠成本缺失时不算利润"),
    "marketing-flash-sale": ("活动商品与库存编码匹配", "售罄率分母为到货量", "活动后退款日期完整"),
    "marketing-new-customer": ("新客基于完整历史首购", "折扣成本字段是否可用", "二购观察窗口足够"),
    "marketing-shopping-gold": ("充值与核销口径分开", "余额时点与成交周期匹配", "退款冲销逻辑明确"),
    "marketing-bybt": ("补贴归因与店铺支付分开", "价格快照业务日一致", "自然成交不可重复归因"),
    "marketing-utry": ("派样客户分母是否存在", "MINI 到正装映射完整", "滚动回购 UV 不冒充 cohort 复购率"),
    "service": ("询单人数与成交人数同口径", "响应时长异常值处理", "账号与商品映射覆盖"),
    "content": ("曝光到成交漏斗分母明确", "内容归因窗口明确", "内容 ID 与商品 ID 可联动"),
    "live": ("店播与达播分开", "观看人数与场观口径明确", "退款后成交和投流费用可用"),
    "market": ("市场日期与店铺日期对齐", "排名样本和类目范围明确", "机会判断不冒充因果"),
    "brand-assets": ("人群资产是否跨日去重", "迁移链路字段完整", "资产变化与成交仅做相关解释"),
    "reviews": ("评价等级与文本主题分开", "筛选同步影响图表和明细", "问题率不用词频代替"),
    "inventory": ("大鱼鎏金完整编码覆盖", "快照采集时间与业务日分开", "可售、占用、在途不可混算"),
}


PAGE_AI_PROFILES: dict[str, PageAIProfile] = {
    item.key: item
    for item in (
        _profile("overview", "经营概览", "经营总盘", "overview", "shop-overview-diagnosis", "定位成交变化的主要驱动并形成今日优先动作", "诊断当前经营总盘，给出三个最重要的结果、原因、风险和可验证动作", ("overview", "traffic", "product", "customer", "promotion", "customer-service"), ("store_overview", "traffic_sources", "products", "product_catalog", "customers", "members", "promotion_campaigns", "customer_service", "live", "cps"), ("为什么最近成交变化？给我最重要的三个原因和动作", "成交变化主要来自流量、转化还是客单？", "今天最应该先处理什么？"), ("日期", "渠道", "系列", "类型", "客户阶段")),
        _profile("analytics", "交易分析", "交易分析", "overview", "shop-overview-diagnosis", "拆解支付、退款、转化、客单价和成交结构", "诊断当前交易结果，拆解支付金额变化并列出优先处理对象", ("overview", "product", "customer"), ("store_overview", "products", "product_catalog", "customers"), ("支付金额变化具体掉在哪个环节？", "下钻客单价变化的系列、类型和商品", "退款变化是否影响净支付？"), ("日期", "系列", "类型", "客户阶段")),
        _profile("traffic", "流量归因", "流量", "traffic", "traffic-diagnosis", "判断流量来源质量、转化承接和UV价值", "诊断当前流量来源质量，识别高流量低转化入口和优先动作", ("traffic", "overview", "product"), ("traffic_sources", "store_overview", "products"), ("哪些流量来源值得进入限额测试？", "有没有高流量低转化的来源？", "流量变化是否与成交变化同步？"), ("来源层级", "来源", "商品")),
        _profile("customers", "客户概况", "客户", "customer", "customer-retention", "分析新访、首次购买、未购回访和老客复购贡献", "诊断当前客户生命周期，核对首购与复购口径并给出分层运营动作", ("customer", "overview", "product"), ("customers", "store_overview", "products"), ("最近成交变化是首购客户还是老客造成的？", "未购回访客户的承接问题在哪里？", "哪些客户人群值得优先召回？"), ("客户阶段", "日期", "系列", "商品")),
        _profile("customer-members", "会员分析", "会员", "customer", "customer-retention", "分析会员资产、招募、成交、复购及渠道集中度", "诊断当前会员增长和成交质量，重点核对入会来源与后续承接", ("customer", "overview"), ("members", "member_channels", "customers", "store_overview", "utry_sample", "utry_repurchase"), ("会员成交和非会员成交有什么差异？", "哪个入会渠道的后续质量更高？", "U先入会依赖是否过高？"), ("入会渠道", "会员阶段", "日期")),
        _profile("products", "商品表现", "商品", "product", "product-structure-diagnosis", "按系列到类型到商品定位成交、客单和风险", "诊断当前商品结构，识别潜力款、承接风险和库存价格问题", ("product", "promotion", "inventory"), ("products", "product_catalog", "promotion_products", "taobao_current_prices", "taobao_price_risks", "taobao_activity_snapshots", "inventory_snapshots"), ("哪些系列或类型拖累了客单价？", "哪些商品高流量低转化？", "主销商品有哪些价格或库存风险？"), ("系列", "类型", "商品")),
        _profile("product-analysis", "单品分析", "单品分析", "product", "product-diagnosis", "结合单品成交、推广、价格、评价和库存给出动作", "诊断当前单品的流量、成交、推广、评价和库存承接", ("product", "promotion", "inventory", "reviews"), ("products", "product_catalog", "promotion_products", "review_records", "ask_records", "taobao_current_prices", "taobao_price_risks", "inventory_snapshots"), ("这个单品为什么转化变化？", "这个商品的价格、评价和库存风险是什么？", "它适合继续做投放测试吗？"), ("商品", "日期", "推广计划", "评价主题")),
        _profile("promotions", "推广分析", "推广", "promotion", "promotion-roi", "从场景到计划到单元定位投放效率", "诊断当前推广效率，列出应停、应降和可进入限额测试的计划", ("promotion", "product"), ("promotion_campaigns", "promotion_adgroups", "promotion_keywords", "promotion_crowds", "promotion_products", "products"), ("哪些推广场景应该降预算？", "帮我找高花费低产出的计划", "哪些低花费计划可进入阶梯测试？"), ("场景", "计划", "单元", "关键词", "人群", "商品")),
        _profile("promotions-cps", "CPS分析", "CPS", "promotion", "data-exploration", "区分付款、结算、佣金和达人贡献", "诊断当前CPS付款、结算和已知费用效率，识别达人集中风险", ("promotion", "live", "product"), ("cps", "live", "products"), ("CPS付款和结算差异是什么？", "哪些达人或商品值得复盘？", "佣金和服务费占比是否异常？"), ("达人", "商品", "日期")),
        _profile("marketing-activities", "活动复盘", "活动", "campaign", "data-exploration", "比较活动前中后成交、流量、商品和推广变化", "按活动前中后诊断经营变化并给出后续补救动作", ("campaign", "overview", "product", "traffic"), ("store_activity_calendar_events", "store_overview", "products", "traffic_sources", "promotion_campaigns"), ("这次活动前中后发生了什么变化？", "活动商品承接是否达标？", "活动后哪些指标需要补救？"), ("活动", "阶段", "商品", "渠道")),
        _profile("marketing-flash-sale", "淘宝秒杀", "秒杀", "campaign", "data-exploration", "判断秒杀曝光、转化、成交和活动后风险", "诊断当前秒杀商品的曝光、转化、成交与库存承接", ("campaign", "product"), ("taobao_flash_sale_overviews", "taobao_flash_sale_items", "products", "store_overview", "inventory_snapshots"), ("秒杀商品哪个最值得复盘？", "秒杀成交低是曝光还是转化问题？", "秒杀商品库存是否匹配？"), ("活动", "商品", "日期")),
        _profile("marketing-new-customer", "新客折扣", "新客折扣", "campaign", "data-exploration", "评估新客折扣带来的首购成交和后续质量", "诊断新客折扣的首购规模、成本信号和后续承接", ("campaign", "customer"), ("new_customer_discount", "store_overview", "customers", "products"), ("新客折扣带来的成交质量怎么样？", "新客折扣转化下降原因是什么？", "后续应该验证哪些二购指标？"), ("日期", "商品", "客户阶段")),
        _profile("marketing-shopping-gold", "购物金", "购物金", "campaign", "data-exploration", "分析充值、使用、成交和退款风险", "诊断购物金充值到核销的承接效率和资金沉淀风险", ("campaign", "customer"), ("shopping_gold", "store_overview", "customers"), ("购物金对成交有什么归因贡献？", "充值和使用之间是否健康？", "购物金应该优先优化哪一步？"), ("日期", "客户阶段")),
        _profile("marketing-bybt", "百亿补贴", "百亿补贴", "campaign", "data-exploration", "评估补贴商品成交、转化和店铺承接", "诊断百亿补贴商品的成交、转化、价格和库存承接", ("campaign", "product"), ("bybt", "bybt_items", "products", "store_overview", "inventory_snapshots"), ("百补成交变化的主要原因是什么？", "百补商品的转化是否健康？", "百补商品有哪些价格和库存风险？"), ("商品", "日期", "类目")),
        _profile("marketing-utry", "U先试用", "U先/MINI", "customer", "utry-repurchase-diagnosis", "分析派样到入会到正装购买的承接", "分析U先和MINI/尝鲜商品，联动派样、入会、正装绑定、推广、评价与回购证据", ("customer", "product", "promotion", "reviews"), ("utry_sample", "utry_repurchase", "products", "product_catalog", "promotion_products", "review_records", "ask_records"), ("MINI/尝鲜商品当前应该补齐哪些动作？", "哪些U先商品的正装绑定和权益未补齐？", "派样后回购证据目前能说明什么？"), ("MINI商品", "正装商品", "派样批次", "回购窗口")),
        _profile("service", "客服概览", "客服", "customer-service", "customer-service-diagnosis", "定位咨询到接待到成交漏斗和服务风险", "诊断客服咨询、接待、响应、成交和退款质量", ("customer-service", "overview", "product"), ("customer_service", "products", "product_catalog", "store_overview"), ("客服最重要的问题和动作是什么？", "哪个客服账号承接最弱？", "客服成交和店铺整体成交是否同步？"), ("客服账号", "日期", "商品")),
        _profile("content", "内容概览", "内容", "content", "data-exploration", "评估内容曝光、互动、点击和种草成交", "诊断内容曝光到商品点击到成交的漏斗和商品匹配", ("content", "promotion", "product"), ("content", "promotion_contents", "products", "store_overview"), ("内容带来的成交质量怎么样？", "哪些内容值得继续验证？", "内容流量为什么没有转化？"), ("内容", "商品", "日期")),
        _profile("live", "直播分析", "直播", "live", "data-exploration", "拆分店播与达播并定位直播漏斗", "分别诊断店播和达播的观看、点击、成交和商品承接", ("live", "product", "promotion"), ("live", "live_store_performance", "live_talent_reports", "products", "store_overview"), ("店播和达播当前分别有什么问题？", "直播成交变化掉在哪个环节？", "直播间主推商品需要调整吗？"), ("店播/达播", "场次", "时段", "商品", "达人")),
        _profile("market", "市场洞察", "市场", "market", "market-insight", "将市场需求与店铺商品成交结合形成验证机会", "诊断当前市场需求、竞品变化和店铺商品匹配机会", ("market", "product"), ("market_rankings", "market_keywords", "products"), ("当前市场有哪些竞品机会？", "哪些搜索词值得小预算验证？", "市场信号和店铺成交是否匹配？"), ("类目", "价格带", "竞品", "搜索词")),
        _profile("brand-assets", "品牌资产", "品牌资产", "customer", "data-exploration", "解释品牌资产、人群关系和成交的联动变化", "诊断访客、粉丝、会员、首购和复购之间的关系迁移", ("brand", "customer", "product"), ("brand_asset_daily_overviews", "brand_asset_daily_metrics", "customers", "products"), ("品牌资产最近最重要的变化是什么？", "哪些人群关系值得重点经营？", "品牌资产变化和店铺成交是否同步？"), ("人群关系", "日期", "商品")),
        _profile("reviews", "评价分析", "评价/问大家", "reviews", "review-diagnosis", "从评价问题和问大家定位购买阻碍与商品风险", "诊断评价主题、风险商品和问大家未回答问题", ("reviews", "product", "customer-service"), ("review_records", "ask_records", "products", "product_catalog", "store_overview", "customer_service"), ("评价里最重要的商品问题是什么？", "哪些商品的问题率最高？", "问大家未回答问题会影响哪些商品承接？"), ("评价等级", "问题主题", "商品", "系列")),
        _profile("inventory", "库存管理", "库存", "inventory", "data-exploration", "把库存快照与销量结合识别断货和滞销风险", "诊断主销商品库存覆盖、零库存和滞销风险，完整核对大鱼鎏金编码", ("inventory", "product"), ("inventory_catalog", "inventory_snapshots", "products", "product_catalog"), ("哪些主销商品最有断货风险？", "大鱼鎏金完整编码是否都有库存快照？", "哪些库存条目需要优先补货或清理？"), ("系列", "货品编码", "SKU", "尺码")),
    )
}


def get_page_ai_profile(page_key: str | None) -> PageAIProfile | None:
    return PAGE_AI_PROFILES.get(str(page_key or "").strip())


def list_page_ai_profiles() -> list[PageAIProfile]:
    return list(PAGE_AI_PROFILES.values())


def enrich_page_context(page_key: str | None, page_context: dict[str, Any] | None) -> tuple[PageAIProfile | None, dict[str, Any]]:
    context = dict(page_context or {})
    resolved_key = str(page_key or context.get("page_key") or "").strip()
    profile = get_page_ai_profile(resolved_key)
    if resolved_key and profile is None and resolved_key != "ai":
        raise ValueError(f"Unknown page_key: {resolved_key}")
    if profile is None:
        if resolved_key:
            context["page_key"] = resolved_key
        return None, context
    trusted = profile.as_dict()
    context.update({
        "page_key": profile.key,
        "page": profile.title,
        "section": profile.section,
        "domain": profile.domain,
        "primary_skill": profile.primary_skill,
        "page_goal": profile.goal,
        "diagnostic_question": profile.diagnostic_question,
        "data_domains": trusted["data_domains"],
        "datasets": trusted["datasets"],
        "recommended_questions": trusted["recommended_questions"],
        "focus_dimensions": trusted["focus_dimensions"],
        "decision_lens": trusted["decision_lens"],
        "quality_checks": trusted["quality_checks"],
    })
    return profile, context
