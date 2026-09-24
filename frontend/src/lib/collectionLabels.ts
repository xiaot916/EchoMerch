import type { CrawlRunDay } from "@/types"

/**
 * 采集任务相关的展示标签与错误归一化。
 *
 * 这些映射把后端返回的枚举值（status / mode / dataset_key / 原始 error 文本）
 * 转成面向运营的中文文案，集中在一个地方维护：
 * - 新增数据集或任务类型时，只需要扩展这里的字典；
 * - 错误信息的"人话"归一化也集中于此，避免散落在各页面里。
 */

/** 把 ISO 时间字符串转成 `M/D HH:mm` 形式的短文案，空值返回占位符。 */
export function collectionTimeLabel(value: string | null | undefined, placeholder = "--"): string {
  if (!value) return placeholder
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return placeholder
  const month = date.getMonth() + 1
  const day = date.getDate()
  const hours = String(date.getHours()).padStart(2, "0")
  const minutes = String(date.getMinutes()).padStart(2, "0")
  return `${month}/${day} ${hours}:${minutes}`
}

/** 采集批次 / 子任务的运行状态文案。 */
export function crawlStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    running: "采集中",
    completed: "已完成",
    completed_with_errors: "部分失败",
    stopped: "已停止",
    queued: "排队中",
  }
  return labels[status] || status
}

/** 采集批次的状态文案（与 crawlStatusLabel 略有差异：批次有明确的 failed 终态）。 */
export function batchStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    running: "采集中",
    completed: "已完成",
    completed_with_errors: "部分失败",
    failed: "失败",
  }
  return labels[status] || status
}

/** 评价 / 问答增量采集任务的状态文案。 */
export function collectionStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    queued: "排队中",
    running: "采集中",
    completed: "已完成",
    failed: "失败",
  }
  return labels[status] || status
}

/** 单个业务日期的入库状态文案。 */
export function dayStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    ingested: "已入库",
    skipped_existing: "已跳过",
    fetch_failed: "请求失败",
    ingest_failed: "解析失败",
  }
  return labels[status] || status
}

/** 日期行的视觉状态分类：failed / ready / muted。 */
export function dayStatusClass(day: CrawlRunDay): "failed" | "ready" | "muted" {
  if (day.status.includes("failed")) return "failed"
  if (day.status === "ingested") return "ready"
  return "muted"
}

/** 任务类型 → 中文名称。未知类型原样返回。 */
export function taskTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    sycm_overview: "店铺经营总览",
    sycm_bybt: "百亿补贴",
    sycm_bybt_items: "百亿补贴商品明细（按日）",
    sycm_customer_overview: "客户概览",
    sycm_item_rankings: "商品排行",
    sycm_live: "直播经营",
    sycm_member_analysis: "会员分析",
    sycm_new_customer_discount: "新客折扣",
    sycm_shopping_gold: "购物金",
    sycm_traffic_source: "流量来源",
    mtop_content_overview: "内容效果",
    mtop_taojinbi: "淘金币",
    customer_service: "客服数据",
    cps_overview: "淘宝客 CPS",
    brandsearch_report: "品销宝品牌专区",
    taobao_flash_sale: "淘宝秒杀",
  }
  return labels[type] || type
}

/** 数据集 key → 中文名称。未知 key 原样返回。 */
export function datasetLabel(key: string): string {
  const labels: Record<string, string> = {
    sycm_overviews: "店铺经营总览",
    sycm_bybt: "百亿补贴",
    sycm_customer_overviews: "客户概览",
    sycm_item_rankings: "商品排行",
    sycm_live: "直播经营",
    sycm_member_analysis: "会员分析",
    sycm_new_customer_discount: "新客折扣",
    sycm_shopping_gold: "购物金",
    sycm_traffic_sources: "流量来源",
    mtop_content_overviews: "内容效果",
    mtop_taojinbi: "淘金币",
    customer_service: "客服数据",
    cps_overviews: "淘宝客 CPS",
    brandsearch_reports: "品销宝品牌专区",
    taobao_flash_sales: "淘宝秒杀",
    taobao_flash_sale_items: "淘宝秒杀商品明细（按日）",
    taobao_operational_snapshots: "淘宝运营商品快照",
    alimama_campaigns: "推广计划",
    alimama_crowds: "推广人群",
    alimama_promotion_details: "推广商品与内容",
    alimama_adgroup_bidwords: "推广单元与关键词",
  }
  return labels[key] || key
}

/** 评价 / 问答采集模式文案。 */
export function collectionModeLabel(mode: string, target: "review" | "ask"): string {
  if (mode === "incremental") return target === "review" ? "增量采集新评价" : "增量采集新问答"
  return target === "review" ? "历史评价补录" : "历史问答补录"
}

/**
 * 把采集链路抛出的原始错误归一化为面向运营的"人话"。
 * 未命中已知特征时原样返回，避免吞掉未知错误。
 */
export function collectionErrorLabel(value: string): string {
  const text = value.toLowerCase()
  if (text.includes("未配置，且已登录采集浏览器不可用") || text.includes("sycm_cookie is required")) {
    return "环境会话未配置，且采集浏览器不可用。请启动 9222 浏览器并登录天猫商家后台后重试。"
  }
  if (text.includes("no chrome remote-debugging") || text.includes("无法连接 chrome") || text.includes("调试端口")) {
    return "采集浏览器未连接，请启动 9222 采集浏览器后重试。"
  }
  if (text.includes("not logged in") || text.includes("未登录") || text.includes("login")) {
    return "采集浏览器尚未登录，请先登录天猫商家后台后重试。"
  }
  if (text.includes("登录状态") || text.includes("完成登录后重试")) {
    return "对应采集页面仍未完成登录，请在新打开的采集标签页登录后再重试。"
  }
  if (text.includes("品牌数据银行页面未提供")) {
    return "品牌数据银行页面未拿到有效登录令牌，请在新打开的品牌数据银行页完成登录后重试。"
  }
  if (text.includes("utry report templates") || text.includes("missing reportid") || text.includes("u先")) {
    return "U先页面请求参数未捕获，请确认派样和复购页面都能正常打开并完成登录后重试。"
  }
  if (text.includes("m_h5_tk")) {
    return "当前浏览器会话缺少淘宝签名 Cookie，请打开评价管理页后再重试。"
  }
  if (text.includes("drissionpage is not installed")) {
    return "采集组件未安装 DrissionPage，请补齐后端依赖后重试。"
  }
  return value
}
