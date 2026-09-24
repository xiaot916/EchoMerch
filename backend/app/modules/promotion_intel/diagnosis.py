from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Sequence


@dataclass(frozen=True)
class DiagnosisInput:
    """诊断输入：由调用方从 store_daily_promotion_* 表聚合而来。"""

    campaigns: Sequence[Any]  # 每行: campaign_id, campaign_name, scene, charge, alipay_inshop_amt, alipay_inshop_num, ecpc, roi, cvr
    crowds: Sequence[Any]  # 每行: campaign_id, crowd_id, crowd_name, crowd_type, charge, roi
    words: Sequence[Any]  # 每行: campaign_id, word, bid_price, match_scope, charge, click, roi, cvr
    word_packages: Sequence[Any]  # 每行: campaign_id, package_name, package_type, charge, roi
    daily_overview: Any  # 单行: paid_amount, visitors, paid_buyers, conversion_rate, customer_unit_price
    baseline: dict[str, float]  # break_even_roi, actual_cpc, actual_roi, customer_unit_price, gross_margin


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # critical / warning / info
    title: str
    detail: str
    targets: tuple[dict, ...] = ()


class PromotionDiagnoser:
    """6 条硬规则诊断器。阈值来自 30 日实测基线，可由 baseline 覆盖。"""

    def __init__(self, baseline: dict[str, float]) -> None:
        self.baseline = baseline

    def run(self, input_data: DiagnosisInput) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(self._word_price_bounds(input_data))
        findings.extend(self._premium_backfire(input_data))
        findings.extend(self._bare_traffic_share(input_data))
        findings.extend(self._smart_targeting_leak(input_data))
        findings.extend(self._word_package_squeeze(input_data))
        findings.extend(self._channel_threshold_mismatch(input_data))
        return findings

    # ---- 规则 1：词价越界 ----
    def _word_price_bounds(self, d: DiagnosisInput) -> list[Finding]:
        """custom_bid 场景词价偏离保本 CPC 过多 → 上调/下调。"""
        break_even_cpc = self._break_even_cpc()
        if break_even_cpc <= 0:
            return []
        lo, hi = break_even_cpc * 0.7, break_even_cpc * 1.3
        bad: list[dict] = []
        for w in d.words:
            price = float(w.get("bid_price") or 0)
            if price <= 0:
                continue
            if price > hi:
                bad.append({**w, "reason": f"词价 {price:.2f} > 保本CPC×1.3={hi:.2f}", "suggested": min(price * 0.9, hi)})
            elif price < lo:
                bad.append({**w, "reason": f"词价 {price:.2f} < 保本CPC×0.7={lo:.2f}", "suggested": max(price * 1.1, lo)})
        if not bad:
            return []
        return [Finding("word_price_bounds", "warning" if len(bad) <= 5 else "critical",
                        f"{len(bad)} 个词价偏离保本区间", f"保本CPC={break_even_cpc:.3f}，建议区间 [{lo:.2f}, {hi:.2f}]",
                        tuple(bad[:30]))]

    # ---- 规则 2：溢价反噬 ----
    def _premium_backfire(self, d: DiagnosisInput) -> list[Finding]:
        """人群溢价 > 100% 且该人群 ROI < 保本线 → 降溢价。"""
        break_even = float(self.baseline.get("break_even_roi") or 2.5)
        bad: list[dict] = []
        for c in d.crowds:
            premium = float(c.get("premium") or 0)  # 百分数
            roi = float(c.get("roi") or 0)
            if premium > 100 and roi < break_even:
                bad.append({**c, "reason": f"溢价 {premium:.0f}% 但 ROI {roi:.2f} < 保本 {break_even}", "suggested": 50.0})
        if not bad:
            return []
        return [Finding("premium_backfire", "critical",
                        f"{len(bad)} 个人群溢价反噬", "溢价 >100% 且 ROI 低于保本线，建议降到 50% 或 0",
                        tuple(bad[:30]))]

    # ---- 规则 3：裸投高消耗 ----
    def _bare_traffic_share(self, d: DiagnosisInput) -> list[Finding]:
        """crowdType=-999（无定向）占账户花费 > 50% → 拉新计划加人群包。"""
        total = sum(float(c.get("charge") or 0) for c in d.crowds)
        if total <= 0:
            return []
        bare = sum(float(c.get("charge") or 0) for c in d.crowds if str(c.get("crowd_type")) in ("-999", "None"))
        share = bare / total * 100
        if share <= 50:
            return []
        return [Finding("bare_traffic_share", "warning",
                        f"裸投流量占 {share:.1f}%", f"未做人群定向的花费 {bare:,.0f} 元，建议拉新计划绑定达摩盘包",
                        tuple([{"bare_charge": bare, "share_pct": round(share, 1), "total_charge": total}]))]

    # ---- 规则 4：智能定向漏点 ----
    def _smart_targeting_leak(self, d: DiagnosisInput) -> list[Finding]:
        """crowdType=100（智能定向）花费 > 1 万且 ROI < 1 → 降预算。"""
        bad: list[dict] = []
        for c in d.crowds:
            if str(c.get("crowd_type")) != "100":
                continue
            charge = float(c.get("charge") or 0)
            roi = float(c.get("roi") or 0)
            if charge > 10000 and roi < 1:
                bad.append({**c, "reason": f"智能定向花费 {charge:,.0f} ROI {roi:.2f} < 1", "suggested": "降预算 30%"})
        if not bad:
            return []
        return [Finding("smart_targeting_leak", "critical",
                        f"{len(bad)} 个智能定向漏点", "智能定向无法关闭，只能降预算抑制",
                        tuple(bad[:20]))]

    # ---- 规则 5：词包挤压 ----
    def _word_package_squeeze(self, d: DiagnosisInput) -> list[Finding]:
        """流量智选词包花费 > 60% 且手动词 ROI 领先 → 压词包出价。"""
        pkg_total = sum(float(p.get("charge") or 0) for p in d.word_packages)
        word_total = sum(float(w.get("charge") or 0) for w in d.words)
        if pkg_total + word_total <= 0:
            return []
        share = pkg_total / (pkg_total + word_total) * 100
        if share <= 60:
            return []
        pkg_roi = self._weighted_roi(d.word_packages)
        word_roi = self._weighted_roi(d.words)
        if word_roi > pkg_roi:
            return [Finding("word_package_squeeze", "warning",
                            f"词包花费占 {share:.1f}%", f"流量智选 ROI {pkg_roi:.2f} 低于手动词 {word_roi:.2f}，压词包出价 20~30%",
                            tuple([{"pkg_charge": pkg_total, "word_charge": word_total, "pkg_roi": pkg_roi, "word_roi": word_roi, "share_pct": round(share, 1)}]))]
        return []

    # ---- 规则 6：渠道门槛失配 ----
    def _channel_threshold_mismatch(self, d: DiagnosisInput) -> list[Finding]:
        """达摩盘包规模与渠道门槛不匹配。
        门槛：直通车49 >10万且≤2000万 ｜ 无界74 无门槛 ｜ 品牌专区33 1万~2亿 ｜ CRM113 1万~1000万
        """
        mismatches: list[dict] = []
        for c in d.crowds:
            coverage = float(c.get("coverage") or 0)
            if coverage <= 0:
                continue
            issues: list[str] = []
            if c.get("dmp") and 100000 > coverage > 20000000:
                pass  # 直通车 49 门槛正常
            if c.get("dmp") and coverage < 100000:
                issues.append("规模 < 10万 推不进直通车(49)")
            if c.get("dmp") and coverage > 20000000:
                issues.append("规模 > 2000万 超直通车(49) 上限")
            if c.get("dmp") and 10000 > coverage > 10000000:
                pass  # 品牌专区 33 正常
            if c.get("dmp") and coverage < 10000:
                issues.append("规模 < 1万 推不进品牌专区(33)/CRM(113)")
            if c.get("dmp") and coverage > 10000000:
                issues.append("规模 > 1000万 超 CRM(113) 上限")
            if issues:
                mismatches.append({**c, "reason": "；".join(issues)})
        if not mismatches:
            return []
        return [Finding("channel_threshold_mismatch", "info",
                        f"{len(mismatches)} 个人群包渠道门槛失配", "按 49/74/33/113 门槛核对同步",
                        tuple(mismatches[:30]))]

    # ---- 内部工具 ----
    def _break_even_cpc(self) -> float:
        """保本CPC = 客单 × 毛利率 × CVR。"""
        cu = float(self.baseline.get("customer_unit_price") or 0)
        gm = float(self.baseline.get("gross_margin") or 0)
        cvr = float(self.baseline.get("baseline_cvr") or 0)
        return cu * gm * cvr

    @staticmethod
    def _weighted_roi(rows: Sequence[Any]) -> float:
        total_charge = sum(float(r.get("charge") or 0) for r in rows)
        total_gmv = sum(float(r.get("alipay_inshop_amt") or 0) for r in rows)
        if total_charge <= 0:
            return 0.0
        return total_gmv / total_charge
