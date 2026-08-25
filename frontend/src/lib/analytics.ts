import type { DailyMetric, PromotionMetric } from "@/types"

export interface LinearTrend {
  slope: number
  intercept: number
  r2: number
  average: number
  forecast: number
  direction: "up" | "down" | "flat"
  label: string
}

export interface TrendPoint {
  date: string
  value: number
}

export interface ParetoPlan extends PromotionMetric {
  paid: number
  roi: number | null
  cpa: number | null
  spendShare: number
  paidShare: number
  cumulativePaidShare: number
  rank: number
  inCore80: boolean
  action: "放量" | "稳投" | "降本" | "观察"
}

export interface PromotionCluster {
  id: number
  label: "效率放量" | "核心贡献" | "降本观察"
  description: string
  color: "green" | "blue" | "amber"
  count: number
  spend: number
  paid: number
  roi: number
  avgCpa: number | null
  plans: ParetoPlan[]
}

export function regression(values: number[], forecastDays = 3): LinearTrend {
  const clean = values.map((value) => Number(value) || 0)
  if (!clean.length) return { slope: 0, intercept: 0, r2: 0, average: 0, forecast: 0, direction: "flat", label: "暂无趋势" }
  if (clean.length === 1) return { slope: 0, intercept: clean[0], r2: 1, average: clean[0], forecast: clean[0], direction: "flat", label: "样本不足" }
  const average = clean.reduce((sum, value) => sum + value, 0) / clean.length
  const meanX = (clean.length - 1) / 2
  const numerator = clean.reduce((sum, value, index) => sum + (index - meanX) * (value - average), 0)
  const denominator = clean.reduce((sum, _value, index) => sum + (index - meanX) ** 2, 0)
  const slope = denominator ? numerator / denominator : 0
  const intercept = average - slope * meanX
  const ssTot = clean.reduce((sum, value) => sum + (value - average) ** 2, 0)
  const ssRes = clean.reduce((sum, value, index) => sum + (value - (intercept + slope * index)) ** 2, 0)
  const r2 = ssTot ? Math.max(0, Math.min(1, 1 - ssRes / ssTot)) : 1
  const forecast = intercept + slope * (clean.length - 1 + forecastDays)
  const relativeSlope = average ? (slope / average) * 100 : 0
  const direction = relativeSlope > 1.5 ? "up" : relativeSlope < -1.5 ? "down" : "flat"
  const label = direction === "up" ? "线性上行" : direction === "down" ? "线性走弱" : "基本平稳"
  return { slope, intercept, r2, average, forecast: Math.max(0, forecast), direction, label }
}

export function dailyTrend(metrics: DailyMetric[]): { points: TrendPoint[]; trend: LinearTrend; residuals: Array<TrendPoint & { score: number }> } {
  const points = metrics.map((item) => ({ date: item.stat_date, value: item.paid_amount }))
  const trend = regression(points.map((point) => point.value))
  const residualValues = points.map((point, index) => point.value - (trend.intercept + trend.slope * index))
  const residualMean = residualValues.length ? residualValues.reduce((sum, value) => sum + value, 0) / residualValues.length : 0
  const residualStd = Math.sqrt(residualValues.reduce((sum, value) => sum + (value - residualMean) ** 2, 0) / Math.max(residualValues.length, 1))
  const residuals = points.map((point, index) => ({ ...point, score: residualStd ? Math.abs(residualValues[index] - residualMean) / residualStd : 0 }))
  return { points, trend, residuals }
}

export function paretoPlans(plans: PromotionMetric[]): ParetoPlan[] {
  const rows = plans
    .filter((item) => item.spend > 0)
    .map((item) => ({ ...item, paid: Math.max(0, item.paid_amount ?? 0) }))
    .sort((left, right) => right.paid - left.paid || right.spend - left.spend)
  const totalSpend = rows.reduce((sum, item) => sum + item.spend, 0)
  const totalPaid = rows.reduce((sum, item) => sum + item.paid, 0)
  let cumulative = 0
  return rows.map((item, index) => {
    const paidShare = totalPaid ? item.paid / totalPaid : 0
    cumulative += paidShare
    const roi = item.paid_amount === null ? null : item.spend ? item.paid / item.spend : null
    const cpa = item.buyers && item.buyers > 0 ? item.spend / item.buyers : null
    const action = roi === null ? "观察" : roi >= 4 ? "放量" : roi >= 2 ? "稳投" : roi < 1 ? "降本" : "观察"
    return {
      ...item,
      paid: item.paid,
      roi,
      cpa,
      spendShare: totalSpend ? item.spend / totalSpend : 0,
      paidShare,
      cumulativePaidShare: cumulative,
      rank: index + 1,
      inCore80: cumulative - paidShare < 0.8,
      action,
    }
  })
}

function distance(left: number[], right: number[]): number {
  return Math.sqrt(left.reduce((sum, value, index) => sum + (value - right[index]) ** 2, 0))
}

export function clusterPromotionPlans(rows: ParetoPlan[]): PromotionCluster[] {
  if (!rows.length) return []
  const values = rows.map((item) => [Math.log1p(item.spend), Math.log1p(item.paid), Math.log1p(Math.max(item.roi ?? 0, 0))])
  const means = values[0].map((_value, index) => values.reduce((sum, row) => sum + row[index], 0) / values.length)
  const stds = means.map((mean, index) => Math.sqrt(values.reduce((sum, row) => sum + (row[index] - mean) ** 2, 0) / values.length) || 1)
  const normalized = values.map((row) => row.map((value, index) => (value - means[index]) / stds[index]))
  const k = Math.min(3, normalized.length)
  const centers = Array.from({ length: k }, (_value, index) => normalized[Math.floor((index * normalized.length) / k)].slice())
  const assignments = new Array(normalized.length).fill(0)
  for (let iteration = 0; iteration < 18; iteration += 1) {
    normalized.forEach((row, index) => {
      assignments[index] = centers.reduce((best, center, centerIndex) => distance(row, center) < distance(row, centers[best]) ? centerIndex : best, 0)
    })
    centers.forEach((center, centerIndex) => {
      const members = normalized.filter((_row, index) => assignments[index] === centerIndex)
      if (members.length) center.forEach((_value, dimension) => { center[dimension] = members.reduce((sum, row) => sum + row[dimension], 0) / members.length })
    })
  }
  const clusterRows = centers.map((_center, id) => rows.filter((_row, index) => assignments[index] === id))
  const ranked = clusterRows.map((plans, id) => ({ id, plans, roi: plans.reduce((sum, item) => sum + (item.roi ?? 0), 0) / Math.max(plans.length, 1), paid: plans.reduce((sum, item) => sum + item.paid, 0) })).sort((left, right) => right.roi - left.roi)
  const labels: PromotionCluster["label"][] = ["效率放量", "核心贡献", "降本观察"]
  const descriptions = ["ROI 高但预算仍轻，优先验证增量空间", "成交贡献和预算都在主航道，保持稳定投放", "效率偏低或成本偏高，先收缩无效消耗"]
  const colors: PromotionCluster["color"][] = ["green", "blue", "amber"]
  return ranked.map((group, rank) => {
    const spend = group.plans.reduce((sum, item) => sum + item.spend, 0)
    const paid = group.plans.reduce((sum, item) => sum + item.paid, 0)
    const buyers = group.plans.reduce((sum, item) => sum + (item.buyers ?? 0), 0)
    return { id: group.id, label: labels[rank] ?? "核心贡献", description: descriptions[rank] ?? descriptions[1], color: colors[rank] ?? "blue", count: group.plans.length, spend, paid, roi: spend ? paid / spend : 0, avgCpa: buyers ? spend / buyers : null, plans: group.plans }
  })
}
