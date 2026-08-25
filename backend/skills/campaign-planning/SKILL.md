---
name: campaign-planning
description: Build reusable annual, monthly, launch, 618, 11.11, membership-day, or custom campaign plans from actual store, traffic, product, promotion, customer, and channel data.
---

# Campaign Planning

Use this Skill for forward-looking planning and post-event planning review when the user asks to set a sales target, split a target by stage/channel/product, design a promotion rhythm, or turn a plan into measurable operating actions. The event name is a parameter, not a separate MCP or a hard-coded rule.

Use generic `data.coverage` and `data.query` MCP tools. Build the target tree in this order:

`GMV target -> UV/CVR/ATV drivers -> stage -> channel -> product role -> spend and validation metric`.

Rules:

- Preserve the distinction between user-entered targets and historical baselines. Never infer a new target or budget from last period alone.
- If the user provides only GMV, budget and ROI, use the recent 30-day CVR and ATV baseline to derive a scenario UV target. Mark those values as assumptions, not commitments.
- Separate total store GMV from paid-attribution GMV. `budget x target ROI` is the paid scenario only; the remaining GMV needs an explicit non-paid or overlapping-channel acceptance target.
- Margin is optional for GMV/traffic arithmetic but required before claiming profit, contribution margin, or an economically safe ROI.
- Use actual data to rank channels and products, but do not promise that historical ROI or conversion will repeat. Mark forecast GMV as a scenario estimate.
- When the user supplies a total target and budget, return stage GMV and stage budget rather than an empty phase template. Include stop/scale gates for each stage.
- Product roles must include a refund-risk gate. High-refund products are not automatically eligible for scale even when their GMV rank is high.
- Do not fill uncollected dates with zero. Platform-confirmed no-data dates must remain separate from collection gaps.
- Every recommendation needs an owner and a validation metric that can be checked in a later report.

Read [references/planning-frameworks.md](references/planning-frameworks.md) when building a target tree, phase rhythm, product roles, or activity review.
