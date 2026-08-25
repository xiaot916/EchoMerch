from __future__ import annotations

from app.modules.operations.schemas import OperationCapability, OperationCenterSummary


class OperationService:
    def get_summary(self) -> OperationCenterSummary:
        return OperationCenterSummary(
            mode="read_only",
            required_flow=[
                "draft",
                "preview",
                "validate",
                "confirm",
                "execute",
                "audit",
            ],
            capabilities=[
                OperationCapability(
                    key="coupon.batch_create",
                    title="Batch coupon creation",
                    status="planned",
                    risk_level="high",
                    mode="preview_required_before_execute",
                    guardrails=[
                        "Template parameters must be validated before execution.",
                        "Every item must produce an audit row.",
                        "Execution must support idempotency keys.",
                    ],
                ),
                OperationCapability(
                    key="product.batch_update",
                    title="Batch product operations",
                    status="planned",
                    risk_level="high",
                    mode="disabled_until_adapter_exists",
                    guardrails=[
                        "No browser automation endpoint is exposed.",
                        "Adapter must separate request building from execution.",
                    ],
                ),
                OperationCapability(
                    key="daily_import.preview",
                    title="Daily import preview",
                    status="dry_run_only",
                    risk_level="medium",
                    mode="local_contract_preview",
                    guardrails=[
                        "Platform replay is disabled.",
                        "MySQL writes are disabled.",
                        "Response parsing must be approved before enabling writes.",
                    ],
                ),
            ],
        )

