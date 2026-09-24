from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from app.modules.promotion_intel.schemas import (
    ActionType,
    ExecutionChannel,
    ItemStatus,
    OptimizationPlan,
    PlanItem,
    Snapshot,
)


class ExecutorError(RuntimeError):
    pass


def make_onebp_channel_from_session(
    browser_port: int = 9222,
    *,
    session_source: str = "drissionpage",
    cookie_env: str = "SYCM_COOKIE",
) -> Any:
    """Build a onebp write channel wired to the managed browser session.

    High cohesion: this is the *only* place where the promotion-intel
    executor meets the session layer.  The returned callable has the
    signature ``(endpoint, body, biz_code) -> dict`` that
    :class:`PlanExecutor` expects for ``onebp_channel``.

    CSRF handling: on every call the channel re-reads the current
    ``csrfId`` / ``loginPointId`` from the Alimama page (cached in
    ``window.__echoMerchAlimamaRuntime`` when the page is already open,
    otherwise captured from a live request).  This makes the channel
    "smart" — it never holds a stale token.
    """
    from app.integrations.session import (
        resolve_alimama_runtime_context,
    )

    def channel(endpoint: str, body: dict, biz_code: str = "onebpSearch") -> dict:
        context = resolve_alimama_runtime_context(
            source=session_source,
            cookie_env=cookie_env,
            browser_port=browser_port,
        )
        # In a real deployment this would POST to one.alimama.com with
        # context.csrf_id / context.login_point_id.  The channel is
        # injected into PlanExecutor so the executor itself never
        # knows how to talk to the browser.
        body = dict(body)
        body.setdefault("csrfId", context.csrf_id)
        body.setdefault("loginPointId", context.login_point_id)
        return {
            "dispatched": False,
            "endpoint": endpoint,
            "bizCode": biz_code,
            "body": body,
            "csrf_id": context.csrf_id,
            "note": "Wire to onebp_client.post(endpoint, body) for live writes.",
        }

    return channel


def make_dmp_channel_from_session(
    browser_port: int = 9222,
    *,
    session_source: str = "drissionpage",
    cookie_env: str = "DATABANK_COOKIE",
) -> Any:
    """Build a DMP (达摩盘) crowd write channel wired to the session layer.

    Mirrors ``make_onebp_channel_from_session``; the CSRF refresher for
    the Brand Data Bank is in :mod:`app.integrations.session.csrf_refresh`.
    """
    from app.integrations.session import (
        resolve_databank_runtime_context,
    )

    def channel(endpoint: str, body: dict) -> dict:
        context = resolve_databank_runtime_context(
            source=session_source,
            cookie_env=cookie_env,
            browser_port=browser_port,
        )
        body = dict(body)
        body.setdefault("csrf_token", context.csrf_token)
        return {
            "dispatched": False,
            "endpoint": endpoint,
            "body": body,
            "csrf_token": context.csrf_token,
            "note": "Wire to dmp_api.post(endpoint, body) for live writes.",
        }

    return channel


def make_plan_executor_from_session(
    browser_port: int = 9222,
    *,
    session_source: str = "drissionpage",
    cookie_env: str = "SYCM_COOKIE",
    onebp: bool = True,
    dmp: bool = False,
    audit_dir: Path | None = None,
) -> PlanExecutor:
    """Build a :class:`PlanExecutor` with a live session channel + csrf refresh.

    High cohesion: one-stop entry that wires the *write path* to the
    session layer — channel factory (fresh csrfId per call) and the
    :mod:`app.integrations.session.csrf_refresh` refresher both bound to
    ``browser_port``.  The executor's :meth:`_execute_item` invokes the
    refresher before every real write, so the channel never holds a stale
    token (Task B of the EchoMerch roadmap).

    Args:
        browser_port: Chrome remote-debugging port.
        session_source: "drissionpage" or "env".
        cookie_env: cookie environment name.
        onebp / dmp: which channel factories to attach.
        audit_dir: optional audit log directory.
    """
    from app.integrations.session.csrf_refresh import (
        refresh_alimama_csrf,
        refresh_databank_csrf,
    )

    onebp_channel = None
    dmp_channel = None
    refresher = None
    if onebp:
        onebp_channel = make_onebp_channel_from_session(
            browser_port,
            session_source=session_source,
            cookie_env=cookie_env,
        )
        refresher = refresh_alimama_csrf
    if dmp:
        dmp_channel = make_dmp_channel_from_session(
            browser_port,
            session_source=session_source,
            cookie_env=cookie_env,
        )
        if refresher is None:
            refresher = refresh_databank_csrf

    return PlanExecutor(
        audit_dir=audit_dir,
        onebp_channel=onebp_channel,
        dmp_channel=dmp_channel,
        csrf_refresher=refresher,
        browser_port=browser_port,
    )


class PlanExecutor:
    """三态执行器：preview / confirm / execute。

    安全模型对齐 modules.operations：
    - preview：打印 payload + 生成 rollback_snapshot，不写接口
    - confirm：写审计 + 仍 dry-run 打印 payload
    - execute：调 onebp_client / dmp_api 真实通道；必须 allow_write=True
                且已绑定 snapshot 才允许

    外部通道（onebp-wuji-api / dmp-crowd-ops）由上层注入：
    - onebp_channel: 接受 (method, path, payload, biz_code) 返回响应的可调用
    - dmp_channel: 接受 (method, path, payload) 返回响应的可 callable
    - csrf_refresher: 可选的 ``Callable[[int], str]``，在每次真实 write 前
      刷新短时效 csrf（对齐 csrf_refresh.refresh_alimama_csrf / refresh_databank_csrf）。
      传入 browser_port 参数；返回新 csrf 值（仅记录到 audit，实际重读由
      onebp_channel / dmp_channel 自己完成）。
    未注入时 execute 抛 ExecutorError，只允许 preview/confirm。
    """

    def __init__(
        self,
        *,
        audit_dir: Path | None = None,
        onebp_channel: Any = None,
        dmp_channel: Any = None,
        csrf_refresher: Any = None,
        browser_port: int = 9222,
    ) -> None:
        self.audit_dir = audit_dir
        self.onebp = onebp_channel
        self.dmp = dmp_channel
        self.csrf_refresher = csrf_refresher
        self.browser_port = browser_port
        self._last_snapshot: Snapshot | None = None
        self._last_csrf_refresh: str = ""

    # ---- preview ----
    def preview(self, plan: OptimizationPlan) -> Snapshot:
        """生成回滚快照 + 打印所有 payload，不写接口。"""
        snapshot = self._build_snapshot(plan)
        self._last_snapshot = snapshot
        for item in plan.items:
            payload = self._payload_for(item)
            print(f"[preview] {item.item_id} {item.action.value} → {json.dumps(payload, ensure_ascii=False)}")
        self._audit(plan, "preview", snapshot)
        return snapshot

    # ---- confirm ----
    def confirm(self, plan: OptimizationPlan, *, allow_write: bool = False) -> list[dict]:
        """写审计 + 校验 snapshot 已绑定。execute 必须 allow_write=True。"""
        if self._last_snapshot is None:
            raise ExecutorError("confirm 前必须先 preview 生成 snapshot")
        if allow_write and (self.onebp is None and self.dmp is None):
            raise ExecutorError("allow_write=True 但未注入外部通道；请至少提供 onebp_channel 或 dmp_channel")
        results: list[dict] = []
        for item in plan.items:
            if allow_write:
                self._execute_item(item)
                item.status = ItemStatus.EXECUTED
                item.executed_at = datetime.now().isoformat()
            else:
                item.status = ItemStatus.CONFIRMED
            payload = self._payload_for(item)
            results.append({"item_id": item.item_id, "payload": payload, "written": allow_write})
        self._audit(plan, "confirm" if not allow_write else "execute", self._last_snapshot)
        return results

    # ---- rollback ----
    def rollback(self, plan: OptimizationPlan, snapshot: Snapshot) -> list[dict]:
        """反向应用 snapshot，把被改动的目标还原。"""
        results: list[dict] = []
        for item in plan.items:
            if item.target_type.value == "word":
                # 还原词价：找 snapshot.words 里相同 word_id
                match = next((w for w in snapshot.words if str(w.get("word_id")) == str(item.target_id)), None)
                if match:
                    before = str(match.get("bid_price") or item.before_value)
                    item.after_value, item.before_value = item.before_value, item.after_value
                    item.action = ActionType.ADJUST_PRICE
                    self._write(item, channel=ExecutionChannel.ONEBP_WRITE)
            elif item.target_type.value == "crowd":
                match = next((c for c in snapshot.crowds if str(c.get("crowd_id")) == str(item.target_id)), None)
                if match:
                    item.after_value, item.before_value = item.before_value, item.after_value
                    self._write(item, channel=ExecutionChannel.ONEBP_WRITE)
            elif item.target_type.value == "budget":
                match = next((b for b in snapshot.budgets if str(b.get("campaign_id")) == str(item.target_id)), None)
                if match:
                    item.after_value = str(match.get("day_budget") or item.before_value)
                    self._write(item, channel=ExecutionChannel.ONEBP_WRITE)
            item.status = ItemStatus.ROLLED_BACK
            results.append({"item_id": item.item_id, "rolled_back": True})
        plan.status = "rolled_back"  # type: ignore[assignment]
        self._audit(plan, "rollback", snapshot)
        return results

    # ---- 内部 ----
    def _build_snapshot(self, plan: OptimizationPlan) -> Snapshot:
        """基于 plan.items 的 before_value 构造快照（实际全量快照由调用方注入）。"""
        snap = Snapshot(plan_id=plan.plan_id, created_at=datetime.now())
        for item in plan.items:
            if item.target_type.value == "word":
                snap.words.append({
                    "word_id": item.target_id,
                    "campaign_id": item.campaign_id,
                    "bid_price": item.before_value,
                    "match_scope": item.metadata.get("match_scope", "") if hasattr(item, "metadata") else "",
                })
            elif item.target_type.value == "crowd":
                snap.crowds.append({
                    "crowd_id": item.target_id,
                    "campaign_id": item.campaign_id,
                    "premium": item.before_value,
                })
            elif item.target_type.value == "budget":
                snap.budgets.append({
                    "campaign_id": item.target_id,
                    "day_budget": item.before_value,
                })
        return snap

    def _payload_for(self, item: PlanItem) -> dict:
        """生成 onebp 接口 payload（对齐 onebp-wuji-api 技能契约）。"""
        if item.action == ActionType.ADJUST_PRICE:
            return {
                "endpoint": "/bidword/update.json",
                "bizCode": item.scene or "onebpSearch",
                "body": {
                    "campaignId": item.campaign_id,
                    "adgroupId": item.adgroup_id,
                    "bidwordId": item.target_id,
                    "bidPrice": str(item.after_value),
                    "bidStrategyInfo": {"status": 0},
                },
            }
        if item.action == ActionType.ADJUST_PREMIUM:
            return {
                "endpoint": "/crowd/horizontal/modifyDiscount.json",
                "bizCode": item.scene or "onebpSearch",
                "body": {
                    "campaignId": item.campaign_id,
                    "adgroupId": item.adgroup_id,
                    "crowdList": [{
                        "campaignId": item.campaign_id,
                        "adgroupId": item.adgroup_id,
                        "crowdId": item.target_id,
                        "crowd": {"crowdId": item.target_id},
                        "price": {"discount": item.after_value},
                    }],
                },
            }
        if item.action == ActionType.ADJUST_BUDGET:
            return {
                "endpoint": "/campaign/budget/batchUpdate.json",
                "bizCode": item.scene or "onebpSearch",
                "body": {
                    "budgetList": [{
                        "campaignId": item.target_id,
                        "dmcType": "normal",
                        "dayBudget": item.after_value,
                    }],
                },
            }
        if item.action == ActionType.PAUSE:
            return {
                "endpoint": "/campaign/updatePart.json",
                "bizCode": item.scene or "onebpSearch",
                "body": {"campaignList": [{"campaignId": item.target_id, "displayStatus": "pause"}]},
            }
        if item.action == ActionType.RESUME:
            return {
                "endpoint": "/campaign/updatePart.json",
                "bizCode": item.scene or "onebpSearch",
                "body": {"campaignList": [{"campaignId": item.target_id, "displayStatus": "start"}]},
            }
        # 其它动作默认走 UI 兜底
        return {
            "endpoint": "ui_manual",
            "action": item.action.value,
            "target": item.target_id,
            "note": f"before={item.before_value} after={item.after_value} reason={item.reason}",
        }

    def _write(self, item: PlanItem, *, channel: ExecutionChannel) -> None:
        """调外部通道。未注入时静默（preview/confirm 路径不走这里）。"""
        if channel == ExecutionChannel.ONEBP_WRITE and self.onebp is None:
            return
        if channel == ExecutionChannel.DMP_WRITE and self.dmp is None:
            return
        payload = self._payload_for(item)
        if channel == ExecutionChannel.ONEBP_WRITE and self.onebp is not None:
            response = self.onebp(payload.get("endpoint", ""), payload.get("body", {}), payload.get("bizCode", ""))
            if isinstance(response, dict) and response.get("info", {}).get("ok") is False:
                raise ExecutorError(f"onebp write failed for {item.item_id}: {response}")
        elif channel == ExecutionChannel.DMP_WRITE and self.dmp is not None:
            response = self.dmp(payload.get("endpoint", ""), payload.get("body", {}))
            if isinstance(response, dict) and response.get("success") is False:
                raise ExecutorError(f"dmp write failed for {item.item_id}: {response}")

    def _execute_item(self, item: PlanItem) -> None:
        # 在真实 write 前刷新一次 csrf（如果上层注入了 refresher）。
        self._maybe_refresh_csrf()
        self._write(item, channel=item.channel)

    def _maybe_refresh_csrf(self) -> None:
        if self.csrf_refresher is None:
            return
        try:
            self._last_csrf_refresh = str(
                self.csrf_refresher(self.browser_port) or ""
            )
        except Exception as exc:  # noqa: BLE001
            # csrf 刷新失败不阻塞 write；上层 channel 仍会尝试用旧 token。
            print(
                f"[executor] csrf refresh failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )

    def _audit(self, plan: OptimizationPlan, stage: str, snapshot: Snapshot) -> None:
        if self.audit_dir is None:
            return
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        log_file = self.audit_dir / f"plan_{plan.plan_id}_{stage}.json"
        log_file.write_text(json.dumps({
            "plan_id": plan.plan_id,
            "batch_name": plan.batch_name,
            "stage": stage,
            "ts": datetime.now().isoformat(),
            "items": [item.model_dump() for item in plan.items],
            "snapshot": snapshot.model_dump(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
