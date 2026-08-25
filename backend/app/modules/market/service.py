from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.local_database import LocalDatabase
from app.modules.market.schemas import (
    MarketCoverage,
    MarketCompetitiveSignal,
    MarketDecision,
    MarketDailyMetric,
    MarketDemandSignal,
    MarketInsightResponse,
    MarketKeyword,
    MarketKeywordSegment,
    MarketOpportunity,
    MarketRanking,
    MarketSummary,
)


_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

# The current SYCM category is mother-and-baby diapers.  The platform's trend
# endpoint occasionally leaks adjacent-category words; keep those rows for
# audit, but prevent them from becoming business actions.
_CATEGORY_ANCHORS = ("纸尿裤", "尿不湿", "拉拉裤", "婴儿", "宝宝", "尿片", "隔尿垫", "湿巾")
_UNRELATED_CATEGORY_TERMS = ("猫砂", "洗发水", "包包", "床垫", "内裤", "裤子")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _midpoint(value: str | None, *, percent: bool = False) -> float | None:
    if not value:
        return None
    numbers = [float(item) for item in _NUMBER_RE.findall(value)]
    if not numbers:
        return None
    result = sum(numbers) / len(numbers)
    if percent and result <= 1:
        result *= 100
    return result


def _category_relevance(keyword: str | None) -> str:
    text = str(keyword or "").strip()
    if not text:
        return "unclassified"
    if any(term in text for term in _UNRELATED_CATEGORY_TERMS):
        return "unrelated"
    if any(term in text for term in _CATEGORY_ANCHORS):
        return "relevant"
    return "generic"


class MarketInsightService:
    """Read-only adapter for SYCM market snapshots.

    Market tables are platform-level observations, not store revenue facts.
    The service therefore keeps platform ranges verbatim and exposes derived
    scores only as ranking helpers with an explicit diagnostic boundary.
    """

    def __init__(self, database_path: Path) -> None:
        self.database = LocalDatabase(database_path)
        self.database.initialize_schema()

    def _rows(self, conn: sqlite3.Connection, statement: str, *params: Any) -> list[dict[str, Any]]:
        return [dict(row) for row in conn.execute(statement, params).fetchall()]

    def _bounds(self, conn: sqlite3.Connection, table: str) -> tuple[date | None, date | None]:
        row = conn.execute(f"select min(stat_start) as first_date, max(stat_end) as latest_date from {table}").fetchone()
        if not row or not row["latest_date"]:
            return None, None
        return date.fromisoformat(str(row["first_date"])), date.fromisoformat(str(row["latest_date"]))

    def _available_dates(self, conn: sqlite3.Connection, table: str, start: date, end: date) -> set[date]:
        return {
            date.fromisoformat(str(row["stat_end"]))
            for row in conn.execute(
                f"select distinct stat_end from {table} where stat_end between ? and ?",
                (start.isoformat(), end.isoformat()),
            ).fetchall()
            if row["stat_end"]
        }

    def _latest_date(self, conn: sqlite3.Connection, table: str, end: date) -> date | None:
        row = conn.execute(f"select max(stat_end) as latest_date from {table} where stat_end <= ?", (end.isoformat(),)).fetchone()
        return date.fromisoformat(str(row["latest_date"])) if row and row["latest_date"] else None

    def _coverage(self, conn: sqlite3.Connection, table: str, label: str, start: date, end: date) -> MarketCoverage:
        first_date, latest_date = self._bounds(conn, table)
        available = self._available_dates(conn, table, start, end)
        expected_days = (end - start).days + 1
        missing_dates = [start + timedelta(days=offset) for offset in range(expected_days) if start + timedelta(days=offset) not in available]
        # Use the selected window for freshness. A later snapshot outside the
        # requested range must not make an old market window look fresh.
        fetched = conn.execute(
            f"select max(fetched_at) as fetched_at from {table} where stat_end between ? and ?",
            (start.isoformat(), end.isoformat()),
        ).fetchone()
        fetched_at = None
        if fetched and fetched["fetched_at"]:
            try:
                fetched_at = datetime.fromisoformat(str(fetched["fetched_at"]).replace("Z", "+00:00"))
            except ValueError:
                fetched_at = None
        return MarketCoverage(
            dataset=label,
            range_start=start,
            range_end=end,
            expected_days=expected_days,
            covered_days=len(available),
            missing_dates=missing_dates,
            first_date=first_date,
            latest_date=latest_date,
            latest_fetched_at=fetched_at,
            status="empty" if not available else "complete" if not missing_dates else "partial",
        )

    def _latest_fetched_at(self, conn: sqlite3.Connection, table: str, stat_date: date | None) -> datetime | None:
        if not stat_date:
            return None
        row = conn.execute(f"select max(fetched_at) as fetched_at from {table} where stat_end = ?", (stat_date.isoformat(),)).fetchone()
        if not row or not row["fetched_at"]:
            return None
        try:
            return datetime.fromisoformat(str(row["fetched_at"]).replace("Z", "+00:00"))
        except ValueError:
            return None

    def get_insights(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        rank_type: str = "all",
        keyword_type: str = "all",
        query: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        with self.database.connect() as conn:
            rank_first, rank_latest = self._bounds(conn, "sycm_market_rankings")
            kw_first, kw_latest = self._bounds(conn, "sycm_market_keywords")
            latest_available = max((item for item in (rank_latest, kw_latest) if item), default=None)
            if latest_available is None:
                today = date.today()
                start = start_date or today
                end = end_date or today
            else:
                end = end_date or latest_available
                start = start_date or max(rank_first or kw_first or end, end - timedelta(days=6))
            if start > end:
                raise ValueError("市场洞察开始日期不能晚于结束日期")
            rank_coverage = self._coverage(conn, "sycm_market_rankings", "市场排行", start, end)
            keyword_coverage = self._coverage(conn, "sycm_market_keywords", "搜索词", start, end)
            rank_day = self._latest_date(conn, "sycm_market_rankings", end)
            keyword_day = self._latest_date(conn, "sycm_market_keywords", end)
            selected_rank_day = rank_day or end
            selected_keyword_day = keyword_day or end
            limit = min(100, max(5, limit))
            params: list[Any] = [selected_rank_day.isoformat()]
            rank_where = ["stat_end = ?"]
            if rank_type != "all":
                rank_where.append("rank_type = ?")
                params.append(rank_type)
            if query:
                rank_where.append("(coalesce(entity_name, '') like ? or coalesce(shop_name, '') like ? or coalesce(keyword, '') like ?)")
                needle = f"%{query.strip()}%"
                params.extend([needle, needle, needle])
            rank_rows = self._rows(
                conn,
                f"""select rank_no, rank_change, rank_type, entity_type, entity_id, entity_name,
                    shop_name, keyword, paid_buyers_range, visitors_range, sale_item_count,
                    content_title, content_start_time, fan_count_range, grass_paid_amount_range,
                    goods_clicks_range, live_views_range, raw_json from sycm_market_rankings
                    where {' and '.join(rank_where)} order by rank_no asc limit {limit}""",
                *params,
            )
            kw_params: list[Any] = [selected_keyword_day.isoformat()]
            kw_where = ["stat_end = ?"]
            if keyword_type != "all":
                kw_where.append("keyword_type = ?")
                kw_params.append(keyword_type)
            if query:
                kw_where.append("coalesce(keyword, '') like ?")
                kw_params.append(f"%{query.strip()}%")
            kw_rows = self._rows(
                conn,
                f"""select rank_no, keyword_type, keyword, search_popularity_range,
                    click_rate, pay_conversion_rate from sycm_market_keywords
                    where {' and '.join(kw_where)} order by rank_no asc limit {limit}""",
                *kw_params,
            )
            rankings = [
                MarketRanking(
                    rank_no=int(row["rank_no"] or 0),
                    rank_change=int(row["rank_change"]) if row["rank_change"] is not None else None,
                    rank_type=str(row["rank_type"] or ""),
                    entity_type=str(row["entity_type"] or ""),
                    entity_id=_text(row["entity_id"]),
                    entity_name=str(row["entity_name"] or ""),
                    shop_name=_text(row["shop_name"]),
                    keyword=_text(row["keyword"]),
                    paid_buyers_range=_text(row["paid_buyers_range"]),
                    visitors_range=_text(row["visitors_range"]),
                    sale_item_count=int(row["sale_item_count"]) if row["sale_item_count"] is not None else None,
                    content_title=_text(row["content_title"]),
                    content_start_time=_text(row["content_start_time"]),
                    fan_count_range=_text(row["fan_count_range"]),
                    grass_paid_amount_range=_text(row["grass_paid_amount_range"]),
                    goods_clicks_range=_text(row["goods_clicks_range"]),
                    live_views_range=_text(row["live_views_range"]),
                    is_monitored='"isMonitor": true' in str(row["raw_json"] or ""),
                )
                for row in rank_rows
            ]
            keywords = []
            for row in kw_rows:
                midpoint = _midpoint(row["pay_conversion_rate"], percent=True)
                click_rate = _midpoint(str(row["click_rate"]) if row["click_rate"] is not None else None, percent=True)
                score = round(midpoint * click_rate / 100, 2) if midpoint is not None and click_rate is not None else None
                keywords.append(MarketKeyword(
                    rank_no=int(row["rank_no"] or 0),
                    keyword_type=str(row["keyword_type"] or ""),
                    keyword=str(row["keyword"] or ""),
                    popularity_range=_text(row["search_popularity_range"]),
                    click_rate=click_rate,
                    pay_conversion_rate=_text(row["pay_conversion_rate"]),
                    pay_conversion_midpoint=midpoint,
                    opportunity_score=score,
                    category_relevance=_category_relevance(_text(row["keyword"])),
                ))
            daily_rows = self._rows(
                conn,
                """select stat_end, count(*) as ranking_rows,
                    count(distinct case when rank_type = 'shop' then shop_id end) as shops,
                    count(distinct case when rank_type = 'item' then entity_id end) as items,
                    0 as keywords from sycm_market_rankings
                    where stat_end between ? and ? group by stat_end
                    union all
                    select stat_end, 0, 0, 0, count(*) from sycm_market_keywords
                    where stat_end between ? and ? group by stat_end""",
                start.isoformat(), end.isoformat(), start.isoformat(), end.isoformat(),
            )
            by_day: dict[str, dict[str, int]] = {}
            for row in daily_rows:
                key = str(row["stat_end"])
                item = by_day.setdefault(key, {"ranking_rows": 0, "shops": 0, "items": 0, "keywords": 0})
                for field in item:
                    item[field] += int(row[field] or 0)
            daily_keyword_rows = self._rows(
                conn,
                """select stat_end, keyword, click_rate, pay_conversion_rate
                   from sycm_market_keywords where stat_end between ? and ?""",
                start.isoformat(), end.isoformat(),
            )
            keyword_daily: dict[str, list[tuple[float | None, float | None, float | None]]] = {}
            for row in daily_keyword_rows:
                if _category_relevance(_text(row["keyword"])) != "relevant":
                    continue
                click = _midpoint(str(row["click_rate"]) if row["click_rate"] is not None else None, percent=True)
                conversion = _midpoint(row["pay_conversion_rate"], percent=True)
                score = round(click * conversion / 100, 2) if click is not None and conversion is not None else None
                keyword_daily.setdefault(str(row["stat_end"]), []).append((click, conversion, score))
            movement_rows = self._rows(
                conn,
                """select stat_end,
                          sum(case when rank_change > 0 then 1 else 0 end) as risers,
                          sum(case when rank_change < 0 then 1 else 0 end) as fallers
                   from sycm_market_rankings where stat_end between ? and ? group by stat_end""",
                start.isoformat(), end.isoformat(),
            )
            movement_by_day = {str(row["stat_end"]): row for row in movement_rows}
            daily_metrics = []
            for day, values in sorted(by_day.items()):
                parsed = keyword_daily.get(day, [])
                clicks = [item[0] for item in parsed if item[0] is not None]
                conversions = [item[1] for item in parsed if item[1] is not None]
                scores = [item[2] for item in parsed if item[2] is not None]
                movements = movement_by_day.get(day, {})
                daily_metrics.append(MarketDailyMetric(
                    stat_date=date.fromisoformat(day),
                    **values,
                    average_click_rate=round(sum(clicks) / len(clicks), 2) if clicks else None,
                    average_pay_conversion_rate=round(sum(conversions) / len(conversions), 2) if conversions else None,
                    high_opportunity_keywords=sum(1 for score in scores if score >= 20),
                    ranking_risers=int(movements.get("risers") or 0),
                    ranking_fallers=int(movements.get("fallers") or 0),
                ))
            full_rank_rows = self._rows(conn, """select rank_no, rank_change, rank_type, entity_id, entity_name, shop_name,
                content_title, content_start_time, fan_count_range, grass_paid_amount_range, goods_clicks_range,
                live_views_range, paid_buyers_range, visitors_range, raw_json
                from sycm_market_rankings where stat_end = ? order by rank_no""", selected_rank_day.isoformat())
            full_kw_rows = self._rows(conn, """select rank_no, keyword_type, keyword, search_popularity_range, click_rate, pay_conversion_rate
                from sycm_market_keywords where stat_end = ? order by rank_no""", selected_keyword_day.isoformat())
            previous_keyword_day_row = conn.execute(
                "select max(stat_end) as stat_end from sycm_market_keywords where stat_end >= ? and stat_end < ?",
                (start.isoformat(), selected_keyword_day.isoformat()),
            ).fetchone()
            previous_keyword_day = _text(previous_keyword_day_row["stat_end"]) if previous_keyword_day_row else None
            previous_keyword_rows = self._rows(
                conn,
                """select rank_no, keyword_type, keyword from sycm_market_keywords where stat_end = ?""",
                previous_keyword_day,
            ) if previous_keyword_day else []
            previous_keyword_ranks = {
                (str(row["keyword_type"] or ""), str(row["keyword"] or "")): int(row["rank_no"] or 0)
                for row in previous_keyword_rows if row["keyword"]
            }
            keyword_history_rows = self._rows(
                conn,
                """select keyword_type, keyword, count(distinct stat_end) as days_seen
                   from sycm_market_keywords where stat_end between ? and ?
                   group by keyword_type, keyword""",
                start.isoformat(), end.isoformat(),
            )
            keyword_days_seen = {
                (str(row["keyword_type"] or ""), str(row["keyword"] or "")): int(row["days_seen"] or 0)
                for row in keyword_history_rows if row["keyword"]
            }
            top_shop = next((str(row["shop_name"]) for row in full_rank_rows if row["rank_type"] == "shop" and row["shop_name"]), None)
            top_item = next((str(row["entity_name"]) for row in full_rank_rows if row["rank_type"] == "item" and row["entity_name"]), None)
            top_content = next((str(row["content_title"] or row["entity_name"]) for row in full_rank_rows if row["rank_type"] == "content" and (row["content_title"] or row["entity_name"])), None)
            top_keyword = next((str(row["keyword"]) for row in full_kw_rows if row["keyword"]), None)
            rank_groups = {kind: [row for row in full_rank_rows if row["rank_type"] == kind] for kind in ("shop", "item", "content")}
            monitored_count = sum('"isMonitor": true' in str(row["raw_json"] or "") for row in full_rank_rows)
            rising_counts = {kind: sum(1 for row in rows if (row["rank_change"] or 0) > 0) for kind, rows in rank_groups.items()}
            falling_counts = {kind: sum(1 for row in rows if (row["rank_change"] or 0) < 0) for kind, rows in rank_groups.items()}
            parsed_full_keywords = []
            for row in full_kw_rows:
                relevance = _category_relevance(_text(row["keyword"]))
                click = _midpoint(str(row["click_rate"]) if row["click_rate"] is not None else None, percent=True)
                conversion = _midpoint(row["pay_conversion_rate"], percent=True)
                score = round(click * conversion / 100, 2) if click is not None and conversion is not None else None
                parsed_full_keywords.append((row, relevance, click, conversion, score))
            # Only explicit category terms may become actions. Generic modifiers
            # remain auditable in the raw keyword list, but can otherwise lift
            # adjacent-category words into misleading recommendations.
            relevant_full_keywords = [item for item in parsed_full_keywords if item[1] == "relevant" and item[0]["keyword"]]
            high_opportunity_count = sum(1 for item in relevant_full_keywords if item[4] is not None and item[4] >= 20)
            covered_total = rank_coverage.covered_days + keyword_coverage.covered_days
            expected_total = rank_coverage.expected_days + keyword_coverage.expected_days
            summary = MarketSummary(
                ranking_rows=len(full_rank_rows),
                keyword_rows=len(full_kw_rows),
                shop_count=len({row["shop_name"] for row in full_rank_rows if row["rank_type"] == "shop" and row["shop_name"]}),
                item_count=len({row["entity_id"] for row in full_rank_rows if row["rank_type"] == "item" and row["entity_id"]}),
                content_count=sum(1 for row in full_rank_rows if row["rank_type"] == "content"),
                keyword_count=len({row["keyword"] for row in full_kw_rows if row["keyword"]}),
                latest_rank_date=rank_day,
                latest_keyword_date=keyword_day,
                top_shop=top_shop,
                top_item=top_item,
                top_content=top_content,
                top_keyword=top_keyword,
                monitored_count=monitored_count,
                relevant_keyword_count=len(relevant_full_keywords),
                high_opportunity_count=high_opportunity_count,
                rank_mover_count=sum(rising_counts.values()) + sum(falling_counts.values()),
                coverage_rate=round(covered_total / expected_total * 100, 1) if expected_total else 0,
                rising_counts=rising_counts,
                falling_counts=falling_counts,
            )
            opportunities = []
            for row, _, click, conversion, score in sorted(relevant_full_keywords, key=lambda value: value[4] or -1, reverse=True)[:6]:
                keyword = str(row["keyword"] or "")
                opportunities.append(MarketOpportunity(
                    keyword=keyword,
                    keyword_type=str(row["keyword_type"] or ""),
                    evidence=f"点击率 {click:.2f}% · 支付转化区间 {row['pay_conversion_rate'] or '暂无'}" if click is not None else f"支付转化区间 {row['pay_conversion_rate'] or '暂无'}",
                    action="先核对本店商品、标题和库存是否承接该需求，再以小流量验证点击、加购和支付。",
                    score=score,
                ))
            demand_signals = []
            for row, _, click, conversion, score in relevant_full_keywords:
                keyword = str(row["keyword"] or "")
                kind = str(row["keyword_type"] or "")
                current_rank = int(row["rank_no"] or 0)
                previous_rank = previous_keyword_ranks.get((kind, keyword))
                rank_change = previous_rank - current_rank if previous_rank is not None else None
                direction = "new" if previous_rank is None else "rising" if rank_change and rank_change > 0 else "falling" if rank_change and rank_change < 0 else "stable"
                days_seen = keyword_days_seen.get((kind, keyword), 1)
                trend_text = "本期新进入样本" if direction == "new" else f"较前快照上升 {rank_change} 位" if direction == "rising" else f"较前快照下降 {abs(rank_change or 0)} 位" if direction == "falling" else "较前快照排名稳定"
                confidence = "high" if days_seen >= 5 and previous_rank is not None else "medium" if days_seen >= 2 else "low"
                demand_signals.append(MarketDemandSignal(
                    keyword=keyword,
                    keyword_type=kind,
                    current_rank=current_rank,
                    previous_rank=previous_rank,
                    rank_change=rank_change,
                    direction=direction,
                    days_seen=days_seen,
                    popularity_range=_text(row["search_popularity_range"]),
                    click_rate=click,
                    pay_conversion_midpoint=conversion,
                    opportunity_score=score,
                    evidence=f"当前第 {current_rank} 名，{trend_text}；点击率 {click:.2f}%" if click is not None else f"当前第 {current_rank} 名，{trend_text}",
                    action="核对本店是否有对应商品与库存；有承接能力时再测试标题、内容和搜索投放。",
                    confidence=confidence,
                ))
            demand_signals.sort(key=lambda item: (
                0 if item.direction == "rising" else 1 if item.direction == "new" else 2,
                -(item.rank_change or 0),
                -(item.opportunity_score or -1),
                item.current_rank,
            ))
            demand_signals = demand_signals[:12]
            keyword_segments = []
            for kind in ("core", "search", "trend", "modify"):
                rows = [row for row in full_kw_rows if row["keyword_type"] == kind and row["keyword"] and _category_relevance(_text(row["keyword"])) == "relevant"]
                if not rows:
                    continue
                parsed = []
                for row in rows:
                    click = _midpoint(str(row["click_rate"]) if row["click_rate"] is not None else None, percent=True)
                    conversion = _midpoint(row["pay_conversion_rate"], percent=True)
                    score = round(click * conversion / 100, 2) if click is not None and conversion is not None else None
                    parsed.append((row, click, conversion, score))
                valid_click = [item[1] for item in parsed if item[1] is not None]
                valid_conversion = [item[2] for item in parsed if item[2] is not None]
                valid_scores = [item[3] for item in parsed if item[3] is not None]
                top = next((item[0]["keyword"] for item in sorted(parsed, key=lambda item: item[3] or -1, reverse=True)), None)
                keyword_segments.append(MarketKeywordSegment(
                    keyword_type=kind,
                    keyword_count=len(rows),
                    top_keyword=str(top) if top else None,
                    average_click_rate=round(sum(valid_click) / len(valid_click), 2) if valid_click else None,
                    average_pay_conversion_rate=round(sum(valid_conversion) / len(valid_conversion), 2) if valid_conversion else None,
                    average_opportunity_score=round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else None,
                    high_opportunity_count=sum(1 for score in valid_scores if score >= 20),
                ))
            competitive_signals = []
            for kind, rows in rank_groups.items():
                name_key = "content_title" if kind == "content" else "shop_name" if kind == "shop" else "entity_name"
                rising_rows = sorted([item for item in rows if (item["rank_change"] or 0) > 0], key=lambda item: int(item["rank_change"]), reverse=True)
                falling_rows = sorted([item for item in rows if (item["rank_change"] or 0) < 0], key=lambda item: int(item["rank_change"]))
                for row in rising_rows[:3]:
                    name = _text(row[name_key] or row["entity_name"]) or "未命名样本"
                    competitive_signals.append(MarketCompetitiveSignal(
                        rank_type=kind,
                        entity_id=_text(row["entity_id"]),
                        name=name,
                        current_rank=int(row["rank_no"] or 0),
                        rank_change=int(row["rank_change"]),
                        direction="rising",
                        evidence=f"当前第 {int(row['rank_no'] or 0)} 名，较前期上升 {abs(int(row['rank_change']))} 位。",
                        action="加入竞品监控清单，核对其商品卖点、内容主题和投放承接，再决定是否做同类测试。",
                    ))
                for row in falling_rows[:2]:
                    name = _text(row[name_key] or row["entity_name"]) or "未命名样本"
                    competitive_signals.append(MarketCompetitiveSignal(
                        rank_type=kind,
                        entity_id=_text(row["entity_id"]),
                        name=name,
                        current_rank=int(row["rank_no"] or 0),
                        rank_change=int(row["rank_change"]),
                        direction="falling",
                        evidence=f"当前第 {int(row['rank_no'] or 0)} 名，较前期下降 {abs(int(row['rank_change']))} 位。",
                        action="作为防守样本，检查本店对应商品/内容的流量、价格和库存是否出现承接问题。",
                    ))
            competitive_signals = competitive_signals[:16]
            filtered_keywords = sum(1 for row in full_kw_rows if _category_relevance(_text(row["keyword"])) == "unrelated")
            generic_keywords = sum(1 for row in full_kw_rows if _category_relevance(_text(row["keyword"])) == "generic")
            diagnostics: list[str] = ["市场排行是平台相对排名，不等于店铺支付金额或财务结算金额。", "搜索热度和支付转化部分为平台区间值，页面保留原始区间，不用于精确 GMV 计算。"]
            if filtered_keywords:
                diagnostics.append(f"搜索词样本中有 {filtered_keywords} 条明显跨类目词，仅保留原始证据，不生成投放或标题建议。")
            if generic_keywords:
                diagnostics.append(f"另有 {generic_keywords} 条未包含明确类目锚点的泛词，仅保留在原始样本，不进入需求机会与行动建议。")
            flags: list[str] = []
            for coverage in (rank_coverage, keyword_coverage):
                if coverage.status == "partial":
                    flags.append(f"{coverage.dataset}缺少 {len(coverage.missing_dates)} 个自然日，不能按 0 补齐。")
            encoding_hits = sum("�" in str(row.get("entity_name") or "") or "�" in str(row.get("shop_name") or "") for row in full_rank_rows)
            encoding_hits += sum("�" in str(row.get("keyword") or "") for row in full_kw_rows)
            if encoding_hits:
                flags.append(f"有 {encoding_hits} 条市场文本疑似编码异常，需修复采集解码后再做品牌/竞品结论。")
            coverage_confidence = "high" if not flags and min(rank_coverage.covered_days, keyword_coverage.covered_days) >= 5 else "medium" if covered_total else "low"
            decisions: list[MarketDecision] = []
            if opportunities:
                top = opportunities[0]
                decisions.append(MarketDecision(
                    priority="P0",
                    theme="需求机会",
                    title=f"先验证 {top.keyword}",
                    finding="该词在最新全量搜索词样本中同时具备点击和支付转化信号，但仍属于平台样本机会。",
                    evidence=top.evidence,
                    action="先检查本店对应商品、卖点表达和可售库存，再做标题/内容/搜索词的小流量测试。",
                    validation="观察 3-7 天：本店搜索点击率、加购率、支付转化率及对应 SKU 库存覆盖。",
                    confidence=coverage_confidence,
                ))
            top_riser = next((item for item in competitive_signals if item.direction == "rising"), None)
            if top_riser:
                decisions.append(MarketDecision(
                    priority="P1",
                    theme="竞争变化",
                    title=f"拆解上升{ {'shop': '店铺', 'item': '商品', 'content': '内容'}.get(top_riser.rank_type, '样本') }：{top_riser.name}",
                    finding="该对象在最新市场快照中排名上升，适合作为竞品变化线索，不代表其成交增量。",
                    evidence=top_riser.evidence,
                    action="记录其价格带、规格、核心卖点、内容主题和承接页面，与本店同类商品逐项比较。",
                    validation="下一次快照复核排名是否持续，同时对照本店同类商品访客、转化与退款变化。",
                    confidence=coverage_confidence,
                ))
            if top_content:
                decisions.append(MarketDecision(
                    priority="P2",
                    theme="内容方向",
                    title=f"拆解头部内容：{top_content}",
                    finding="这是当前内容/直播排行的头部样本，只能用来观察表达和货品组织方式。",
                    evidence=f"最新内容样本 {summary.content_count} 条，头部样本当前排名第 1。",
                    action="拆解开场、核心利益点、货品组合和促单节点，选一个变量在本店内容中测试。",
                    validation="观察本店内容的观看、商品点击、加购和支付，不用平台内容排名代替成交。",
                    confidence=coverage_confidence,
                ))
            return MarketInsightResponse(
                range_start=start,
                range_end=end,
                latest_available_date=latest_available,
                summary=summary,
                coverage=[rank_coverage, keyword_coverage],
                daily_metrics=daily_metrics,
                rankings=rankings,
                keywords=keywords,
                opportunities=opportunities,
                demand_signals=demand_signals,
                decisions=decisions,
                competitive_signals=competitive_signals,
                keyword_segments=keyword_segments,
                diagnostics=diagnostics,
                data_quality_flags=flags,
            ).model_dump()

    def get_keyword_opportunities(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        keyword_type: str = "all",
        query: str | None = None,
        min_click_rate: float | None = None,
        min_pay_conversion: float | None = None,
        include_unrelated: bool = False,
        limit: int = 20,
    ) -> dict[str, Any]:
        """Return a bounded, auditable list of platform keyword signals."""
        response = MarketInsightResponse.model_validate(self.get_insights(
            start_date=start_date,
            end_date=end_date,
            keyword_type=keyword_type,
            query=query,
            limit=100,
        ))
        demand_by_key = {
            (item.keyword_type, item.keyword): item
            for item in response.demand_signals
        }
        rows: list[dict[str, Any]] = []
        for item in response.keywords:
            if not item.keyword or (not include_unrelated and item.category_relevance == "unrelated"):
                continue
            if min_click_rate is not None and (item.click_rate is None or item.click_rate < min_click_rate):
                continue
            if min_pay_conversion is not None and (
                item.pay_conversion_midpoint is None or item.pay_conversion_midpoint < min_pay_conversion
            ):
                continue
            demand = demand_by_key.get((item.keyword_type, item.keyword))
            rows.append({
                **item.model_dump(mode="json"),
                "rank_change": demand.rank_change if demand else None,
                "direction": demand.direction if demand else "stable",
                "days_seen": demand.days_seen if demand else 1,
                "confidence": demand.confidence if demand else "low",
                "evidence": demand.evidence if demand else "平台搜索词快照样本",
                "action": "先检查本店商品、卖点和库存，再做小流量标题/内容/搜索测试。",
            })
        rows.sort(key=lambda row: (
            0 if row.get("direction") == "rising" else 1 if row.get("direction") == "new" else 2,
            -(row.get("opportunity_score") or -1),
            row.get("rank_no") or 0,
        ))
        return {
            "range_start": response.range_start.isoformat(),
            "range_end": response.range_end.isoformat(),
            "coverage": [item.model_dump(mode="json") for item in response.coverage],
            "opportunities": rows[:min(100, max(1, limit))],
            "diagnostics": response.diagnostics,
            "data_quality_flags": response.data_quality_flags,
            "boundary": "平台搜索词是需求方向信号，不等于本店成交、增量或精确 GMV。",
        }

    def get_competitor_movements(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        rank_type: str = "all",
        query: str | None = None,
        direction: str = "all",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Return rising/falling platform ranking samples without inventing causality."""
        response = MarketInsightResponse.model_validate(self.get_insights(
            start_date=start_date,
            end_date=end_date,
            rank_type=rank_type,
            query=query,
            limit=100,
        ))
        rows: list[dict[str, Any]] = []
        for item in response.rankings:
            change = item.rank_change
            item_direction = "rising" if change is not None and change > 0 else "falling" if change is not None and change < 0 else "stable"
            if direction != "all" and item_direction != direction:
                continue
            name = item.content_title if item.rank_type == "content" else item.shop_name if item.rank_type == "shop" else item.entity_name
            rows.append({
                **item.model_dump(mode="json"),
                "name": name or item.entity_name or item.shop_name or item.keyword or "未命名样本",
                "direction": item_direction,
                "evidence": f"当前第 {item.rank_no} 名；排名变化 {change:+d} 位。" if change is not None else "当前快照没有返回排名变化。",
                "action": "与本店同类商品的访客、支付转化、价格、内容和库存并列核验。",
            })
        rows.sort(key=lambda row: (0 if row["direction"] == "rising" else 1 if row["direction"] == "falling" else 2, -(abs(row.get("rank_change") or 0)), row.get("rank_no") or 0))
        return {
            "range_start": response.range_start.isoformat(),
            "range_end": response.range_end.isoformat(),
            "coverage": [item.model_dump(mode="json") for item in response.coverage],
            "movements": rows[:min(100, max(1, limit))],
            "diagnostics": response.diagnostics,
            "data_quality_flags": response.data_quality_flags,
            "boundary": "市场排名变化是平台相对位置变化，不等于竞品成交增量或本店损失。",
        }
