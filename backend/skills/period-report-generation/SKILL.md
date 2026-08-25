---
name: period-report-generation
description: Generate evidence-backed daily, weekly, monthly, or MTD e-commerce operating reports covering operations, channels, promotion, and top talents.
---

# Period Report Generation

Call `reports.build_period_report` with one of `daily`, `weekly`, `monthly`, or `mtd`.

The report must retain these sections when data is available:

1. Operations: GMV, net GMV after refunds, UV, conversion rate, customer unit price, new-customer buyer share, add-to-cart users/items, favorites, page views, paid items, and returning-customer amount/buyers when available.
2. Channels: member sales and acquisition, shop live sales, subsidy sales, CPS payment and settlement values and expenses.
3. Promotion: paid visitors, paid traffic share, spend, attributed sales, overall ROI, scene ROI, and brand-zone ROI.
4. Top talents: top three talent accounts by GMV.

The legacy `dailyshopdata` report contains useful supporting metrics. Keep the following normalized fields when they exist instead of rebuilding a second report path:

- `new_paid_buyers = paid_buyers - older_paid_buyers` only when both operands are present;
- `new_customer_buyer_share = new_paid_buyers / paid_buyers * 100`;
- `older_paid_amount`, `older_paid_buyers`, and `older_repurchase_rate` for customer structure;
- `add_cart_buyers`, `add_cart_items`, `favorite_buyers`, `page_views`, and `paid_items` for funnel diagnosis.

Promotion traffic-source aliases are presentation groupings, not raw attribution rewrites. Normalize `人群推广/全站推广/货品运营/智能场景/短直联动` to `万象台`, `关键词推广` to `直通车`, and `品销宝-品牌专区` to `品销宝`, while retaining the raw scene and source path in MCP evidence.

Read [references/report-contract.md](references/report-contract.md) when changing metric definitions or report layout.

Never print `0` for an uncollected module. Show `未采集`, `平台无数据`, or `部分覆盖` according to MCP status. Add an AI diagnosis after the fixed report: key conclusion, problem location, prioritized actions, and validation metrics.
