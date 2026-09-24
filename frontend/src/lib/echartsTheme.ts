import type { EChartsCoreOption } from "echarts/core"

/*
 * Shared ECharts theme for EchoMerch.
 *
 * All chart options in views should be built through `withChartTheme` (or
 * rendered via BusinessChart, which applies these defaults automatically).
 * Views then only declare chart-specific pieces (series, data, custom axis
 * formatters) instead of repeating tooltip/legend/axis styling.
 *
 * Colors align with the CSS design tokens in styles/admin-theme.css.
 */

export const chartPalette = [
  "#16845b", // accent green
  "#4f7fd1", // blue
  "#d0933b", // amber
  "#c76d59", // clay red
  "#886bb4", // violet
  "#4b9a9c", // teal
  "#78945e", // olive
  "#a78662", // sand
]

export const chartColors = {
  axisLabel: "#849188",
  axisLine: "#dfe8e3",
  splitLine: "#edf1ef",
  legendText: "#718179",
  seriesLabel: "#506158",
  tooltipBg: "#ffffff",
  tooltipBorder: "#dfe8e3",
  tooltipText: "#17231e",
  emphasis: "#116f4b",
} as const

export const chartFontSize = 12

/** Default tooltip styled to match the light admin theme. */
export function baseTooltip(): Record<string, unknown> {
  return {
    trigger: "axis",
    axisPointer: { type: "shadow" },
    backgroundColor: chartColors.tooltipBg,
    borderColor: chartColors.tooltipBorder,
    borderWidth: 1,
    padding: [8, 12],
    textStyle: { color: chartColors.tooltipText, fontSize: chartFontSize },
    extraCssText: "box-shadow: 0 2px 8px rgba(23, 35, 30, .08); border-radius: 6px;",
  }
}

/** Default legend pinned to the bottom of the chart. */
export function baseLegend(): Record<string, unknown> {
  return {
    bottom: 0,
    itemWidth: 14,
    itemHeight: 8,
    icon: "roundRect",
    textStyle: { color: chartColors.legendText, fontSize: chartFontSize },
  }
}

/** Default grid leaving room for the bottom legend. */
export function baseGrid(): Record<string, unknown> {
  return { left: 52, right: 20, top: 32, bottom: 44 }
}

/** Styling shared by category and value axes. */
function axisTextStyle(): Record<string, unknown> {
  return { color: chartColors.axisLabel, fontSize: chartFontSize }
}

export function baseCategoryAxis(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    type: "category",
    axisLabel: axisTextStyle(),
    axisLine: { lineStyle: { color: chartColors.axisLine } },
    axisTick: { show: false },
    splitLine: { show: false },
    ...overrides,
  }
}

export function baseValueAxis(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    type: "value",
    axisLabel: axisTextStyle(),
    nameTextStyle: axisTextStyle(),
    axisLine: { show: false },
    axisTick: { show: false },
    splitLine: { lineStyle: { color: chartColors.splitLine } },
    ...overrides,
  }
}

/**
 * Fill a view-provided option with the shared theme defaults.
 *
 * Merging is intentionally shallow per top-level key: if the view already
 * declares `tooltip`, `textStyle` or `color`, the view's value wins as-is;
 * otherwise the theme default is injected. Series arrays are never merged,
 * so per-series overrides keep working.
 *
 * Charts whose series are item-based (pie/funnel) get an item tooltip
 * instead of the axis tooltip.
 *
 * `legend` and `grid` are deliberately NOT auto-injected: injecting them
 * silently changes the layout of charts that were authored without them
 * (e.g. an unexpected bottom legend on single-series charts). Views that
 * want the shared values must opt in with `baseLegend()` / `baseGrid()`.
 */
export function withChartTheme(option: EChartsCoreOption): EChartsCoreOption {
  const merged: Record<string, unknown> = { ...option }
  const series = Array.isArray(merged.series) ? (merged.series as Array<Record<string, unknown>>) : []
  const isItemBased = series.some(
    (entry) => entry.type === "pie" || entry.type === "funnel" || entry.type === "sunburst" || entry.type === "graph",
  )
  const tooltipDefault = isItemBased
    ? {
        trigger: "item",
        backgroundColor: chartColors.tooltipBg,
        borderColor: chartColors.tooltipBorder,
        borderWidth: 1,
        padding: [8, 12],
        textStyle: { color: chartColors.tooltipText, fontSize: chartFontSize },
        extraCssText: "box-shadow: 0 2px 8px rgba(23, 35, 30, .08); border-radius: 6px;",
      }
    : baseTooltip()
  const defaults: Record<string, unknown> = {
    color: chartPalette,
    textStyle: { color: chartColors.legendText, fontSize: chartFontSize },
    tooltip: tooltipDefault,
  }
  for (const key of Object.keys(defaults)) {
    if (merged[key] === undefined || merged[key] === null) {
      merged[key] = defaults[key]
    }
  }
  return merged as EChartsCoreOption
}
