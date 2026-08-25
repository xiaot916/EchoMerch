---
name: promotion-roi
description: Diagnose promotion spend, attributed sales, ROI, and budget allocation when users ask which scenes or plans should scale, reduce, stop, or be reviewed.
---

# Promotion ROI Diagnosis

Call `data.query` over the registered Tmall promotion datasets. Use the complete denominator returned by MCP, not a UI-truncated list. For a forward-looking request such as "预算怎么拆/怎么分/怎么规划", route to `promotion-budget-planning`, which reuses the same generic MCP and returns an auditable allocation table.

Evaluate overall efficiency first, then scenes and plans. Separate high-spend low-ROI risks from high-ROI expansion candidates. All budget actions must state a validation threshold and account for the configured attribution window.

ROI alone is not profit. When margin or target ROI is unavailable, frame thresholds as diagnostic defaults and ask operations to compare them with the product margin line.

## Cross-platform formulas

The JD reference workbook is useful for the formula chain, not for copying platform names or attribution. Preserve these platform-neutral formulas where the Tmall dataset has the required fields:

- CTR = clicks / impressions
- CPC = spend / clicks
- click conversion = buyers / clicks
- cart rate = carts / clicks
- cart cost = spend / carts
- buyer cost = spend / buyers
- direct ROI = direct attributed GMV / spend
- total ROI = total attributed GMV / spend
- promoted customer unit price = attributed GMV / buyers
- new buyer share = new buyers / buyers

Keep direct and indirect attributed GMV separate. Do not compare different attribution windows as if they were the same metric. Budget progress is optional and must remain `null` unless an explicit budget field is collected; never infer budget from spend.
