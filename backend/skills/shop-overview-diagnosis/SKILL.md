---
name: shop-overview-diagnosis
description: Diagnose store-level GMV, traffic, conversion, buyer, refund, and promotion changes when users ask why overall business performance moved or what should be addressed first.
---

# Store Overview Diagnosis

Call the generic `data.compare_periods` MCP for the selected store and period.

Use `data.coverage` or the supporting data-quality Skill before comparing periods. The old `analytics.get_overview` name is compatibility-only.

Use MCP metrics and comparisons as the only numerical source. Do not recompute from prose and do not treat missing dates as zero.

Prioritize the diagnosis in this order:

1. Verify coverage. If incomplete, make data repair the first action and qualify period comparisons.
2. Determine whether GMV movement is driven primarily by visitors, conversion, buyers, customer unit price, or refunds.
3. When visitors are stable but buyers and conversion fall, diagnose an on-page or offer conversion problem before recommending more traffic.
4. Return evidence-linked findings and actions with a validation metric.

Do not claim causality below the available dimensions. Recommend the next drill-down instead.
