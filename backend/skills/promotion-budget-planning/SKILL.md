---
name: promotion-budget-planning
description: Plan and decompose promotion budgets by scene, campaign, product, and day when users ask how much to allocate, how to phase spend, or how to adjust a target budget.
---

# Promotion Budget Planning

Use the generic `data.query` MCP over the Tmall promotion datasets. This Skill is for forward-looking allocation; use `promotion-roi` for retrospective efficiency diagnosis unless the question explicitly asks for both.

Collect or parse these inputs when available:

- total budget and planning period;
- target ROI or margin/commission constraint;
- business nodes or dates that require a deliberate budget ramp;
- optional product, campaign, scene, or audience priorities.

Query historical promotion performance by scene and, when a period is available, by day. Build a recommendation that preserves the requested total and makes every allocation traceable to observed spend and ROI. Keep the hierarchy visible: total budget -> scene/campaign -> product or audience -> day.

Rules:

- Never use historical spend as if it were the user's new budget. If total budget is missing, return shares and request the amount; absolute recommendations remain `null`.
- Use historical ROI as an efficiency signal, not as a promise. Expected GMV must be labeled as a scenario estimate and should be `null` when the denominator or attribution coverage is incomplete.
- A target ROI is not profit. If margin, commission, refund, or service fee is missing, state that the target line still needs confirmation.
- Preserve platform-specific scene names as data values. Do not hard-code JD channel names into the generic catalog.
- Keep uncollected dates and platform-confirmed no-data dates separate. Do not spread a missing date's budget as though its performance were zero.

Read [references/jd-budget-decomposition.md](references/jd-budget-decomposition.md) when translating a planning workbook or extending the budgeting logic.
