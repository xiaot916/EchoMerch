import type { RouteLocationRaw } from "vue-router"

export interface SalesBridgeInput {
  paidAmount: number
  visitors: number
  buyers: number
  conversionRate: number
}

export interface SalesBridgeDriver {
  key: "traffic" | "conversion" | "unitPrice"
  label: string
  contribution: number
  currentValue: number
  previousValue: number
  explanation: string
}

export interface SalesGrowthBridge {
  previousPaidAmount: number
  currentPaidAmount: number
  delta: number
  drivers: SalesBridgeDriver[]
}

export interface BusinessActionRow {
  id: string
  priority: "P0" | "P1" | "P2"
  object: string
  issue: string
  evidence: string
  impact: string
  action: string
  validation: string
  window: string
  tone?: "risk" | "warning" | "opportunity" | "stable"
  to?: RouteLocationRaw
}

function normalizedRate(value: number): number {
  return Math.max(0, value) / 100
}

function effectiveConversionRate(input: SalesBridgeInput): number {
  if (input.visitors > 0 && input.buyers >= 0) return input.buyers / input.visitors
  return normalizedRate(input.conversionRate)
}

export function buildSalesGrowthBridge(current: SalesBridgeInput, previous: SalesBridgeInput): SalesGrowthBridge {
  const previousUnitPrice = previous.buyers ? previous.paidAmount / previous.buyers : 0
  const currentUnitPrice = current.buyers ? current.paidAmount / current.buyers : 0
  // Recompute from the raw buyer and visitor counts when available. The
  // displayed percentage is rounded and would otherwise create a false
  // residual in the unit-price/structure contribution.
  const previousRate = effectiveConversionRate(previous)
  const currentRate = effectiveConversionRate(current)
  const delta = current.paidAmount - previous.paidAmount

  const trafficContribution = (current.visitors - previous.visitors) * previousRate * previousUnitPrice
  const conversionContribution = current.visitors * (currentRate - previousRate) * previousUnitPrice
  // Keep the bridge exactly reconcilable with the reported paid amount. This
  // residual includes unit-price mix and small rounding differences in rates.
  const unitPriceContribution = delta - trafficContribution - conversionContribution

  return {
    previousPaidAmount: previous.paidAmount,
    currentPaidAmount: current.paidAmount,
    delta,
    drivers: [
      {
        key: "traffic",
        label: "访客规模",
        contribution: trafficContribution,
        currentValue: current.visitors,
        previousValue: previous.visitors,
        explanation: "访客变化按上期转化率与上期客单价折算",
      },
      {
        key: "conversion",
        label: "支付转化",
        contribution: conversionContribution,
        currentValue: currentRate * 100,
        previousValue: previousRate * 100,
        explanation: "转化率变化按本期访客与上期客单价折算",
      },
      {
        key: "unitPrice",
        label: "客单与结构",
        contribution: unitPriceContribution,
        currentValue: currentUnitPrice,
        previousValue: previousUnitPrice,
        explanation: "剩余金额变化归入客单价、商品结构与四舍五入影响",
      },
    ],
  }
}

export function percentageDelta(current: number, previous: number): number | null {
  if (!previous) return null
  return (current - previous) / Math.abs(previous) * 100
}
