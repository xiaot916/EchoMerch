export function currency(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "暂无"
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 2,
  }).format(value)
}

export function number(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "暂无"
  return new Intl.NumberFormat("zh-CN").format(value)
}

export function shortDate(value: string): string {
  return value.slice(5)
}

export function compactRange(start: string, end: string): string {
  return `${shortDate(start)} 至 ${shortDate(end)}`
}

export function ratio(value: number): string {
  return `${value.toFixed(2)}%`
}
