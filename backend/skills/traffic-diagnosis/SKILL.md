---
name: traffic-diagnosis
description: Diagnose traffic-source scale, conversion, new-visitor mix, and UV value when users ask which sources are weak, valuable, or suitable for expansion.
---

# Traffic Diagnosis

Call the generic `data.query` MCP on `traffic_sources` and preserve the platform's source hierarchy and attribution semantics. Use `data.coverage` before making expansion recommendations. The old `analytics.get_traffic_sources` name is compatibility-only.

Compare sources across visitor scale, conversion rate, paid amount, new-visitor share, and UV value. Identify:

- high-volume, low-conversion sources needing landing-page or audience repair;
- high-UV-value sources suitable for controlled expansion;
- concentrated sources that create dependency risk.

Never add parent and child attribution rows together. Mark incomplete coverage before giving expansion advice.

For paid-traffic scene diagnosis, use `paid_traffic_scenes` when returned by MCP. The normalized alias is for cross-source comparison; retain `raw_scene_name`, `source_path`, and `source_level` as evidence.
