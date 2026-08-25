from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from collections import Counter, defaultdict
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.config import settings
from app.core.local_database import LocalDatabase
from app.integrations.tmall_session import RuntimeSession, RuntimeSessionUnavailable, resolve_runtime_session
from app.warehouse.mtop_sign import sign_mtop_data
from app.modules.reviews.analyzer import ReviewAnalyzer
from app.modules.collection.locks import active_daily_batch, active_feedback_run
from app.modules.reviews.schemas import (
    AskListResponse,
    AskRecord,
    AskSummary,
    ReviewAnalysis,
    ReviewCategoryCount,
    ReviewCollectionRun,
    ReviewCollectionSummary,
    ReviewListResponse,
    ReviewRecord,
    ReviewTrendPoint,
)


REVIEWS_TABLE = "review_records"
RUNS_TABLE = "review_collection_runs"
ASKS_TABLE = "ask_records"
ASK_RUNS_TABLE = "ask_collection_runs"
APP_KEY = "12574478"
API_NAME = "mtop.rm.sellercenter.list.data.pc"
API_URL = "https://h5api.m.taobao.com/h5/mtop.rm.sellercenter.list.data.pc/1.0/"
ASK_API_NAME = "mtop.rm.sellercenter.ask.list"
ASK_API_URL = "https://h5api.m.taobao.com/h5/mtop.rm.sellercenter.ask.list/1.0/"
PAGE_TYPE = "rateWait4PC"
PAGE_SIZE = 20
ASK_PAGE_SIZE = 10
DEFAULT_START_DATE = "2025-01-01"
CLASSIFIER_VERSION = "context-v4"


class ReviewCollectionError(RuntimeError):
    pass


class ReviewService:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database = LocalDatabase(self.database_path)
        self.analyzer = ReviewAnalyzer()
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self.database.initialize_schema()
        with closing(self.database.connect(read_only=False)) as conn:
            conn.executescript(
                f"""
                create table if not exists {REVIEWS_TABLE} (
                    review_key text primary key,
                    platform_review_id text,
                    user_name text,
                    security_id text,
                    emotion_type text,
                    order_id text,
                    item_id text,
                    item_name text,
                    item_link text,
                    series text,
                    review_date text,
                    main_content text not null default '',
                    append_content text not null default '',
                    merged_content text not null default '',
                    main_media_json text not null default '[]',
                    append_media_json text not null default '[]',
                    overview_json text not null default '[]',
                    categories_json text not null default '[]',
                    competitors_json text not null default '[]',
                    is_negative integer not null default 1,
                    source_json text not null default '{{}}',
                    first_seen_at text not null,
                    fetched_at text not null,
                    updated_at text not null
                );
                create index if not exists idx_review_item_date on {REVIEWS_TABLE}(item_id, review_date);
                create index if not exists idx_review_series_date on {REVIEWS_TABLE}(series, review_date);
                create index if not exists idx_review_date on {REVIEWS_TABLE}(review_date);
                create table if not exists {RUNS_TABLE} (
                    run_id text primary key,
                    mode text not null,
                    status text not null,
                    started_at text not null,
                    finished_at text,
                    pages integer not null default 0,
                    fetched_count integer not null default 0,
                    inserted_count integer not null default 0,
                    updated_count integer not null default 0,
                    skipped_count integer not null default 0,
                    stopped_reason text,
                    error text
                );
                create index if not exists idx_review_runs_started on {RUNS_TABLE}(started_at desc);
                create table if not exists {ASKS_TABLE} (
                    ask_id text primary key,
                    item_id text,
                    item_name text,
                    item_link text,
                    series text,
                    user_name text,
                    question text not null default '',
                    question_date text,
                    answer_count integer not null default 0,
                    has_answer integer not null default 0,
                    categories_json text not null default '[]',
                    competitors_json text not null default '[]',
                    source_json text not null default '{{}}',
                    first_seen_at text not null,
                    fetched_at text not null,
                    updated_at text not null
                );
                create index if not exists idx_ask_item_date on {ASKS_TABLE}(item_id, question_date);
                create index if not exists idx_ask_date on {ASKS_TABLE}(question_date);
                create table if not exists {ASK_RUNS_TABLE} (
                    run_id text primary key,
                    mode text not null,
                    status text not null,
                    started_at text not null,
                    finished_at text,
                    pages integer not null default 0,
                    fetched_count integer not null default 0,
                    inserted_count integer not null default 0,
                    updated_count integer not null default 0,
                    skipped_count integer not null default 0,
                    stopped_reason text,
                    error text
                );
                create index if not exists idx_ask_runs_started on {ASK_RUNS_TABLE}(started_at desc);
                create table if not exists review_analysis_metadata (
                    key text primary key,
                    value text not null
                );
                """
            )
            classifier_row = conn.execute(
                "select value from review_analysis_metadata where key = 'classifier_version'"
            ).fetchone()
            if not classifier_row or classifier_row["value"] != CLASSIFIER_VERSION:
                conn.execute("begin immediate")
                classifier_row = conn.execute(
                    "select value from review_analysis_metadata where key = 'classifier_version'"
                ).fetchone()
            if not classifier_row or classifier_row["value"] != CLASSIFIER_VERSION:
                self._reclassify_existing_reviews(conn)
                conn.execute(
                    "insert into review_analysis_metadata(key, value) values('classifier_version', ?) "
                    "on conflict(key) do update set value = excluded.value",
                    (CLASSIFIER_VERSION,),
                )
            conn.commit()

    def _reclassify_existing_reviews(self, conn: sqlite3.Connection) -> None:
        """Repair classifications written by older, keyword-only rules.

        This is intentionally idempotent. It lets existing reviews immediately
        benefit from the context-aware classifier without requiring another
        Taobao collection run.
        """
        rows = conn.execute(f"select review_key, merged_content from {REVIEWS_TABLE}").fetchall()
        for row in rows:
            classification = self.analyzer.classify(row["merged_content"] or "")
            conn.execute(
                f"update {REVIEWS_TABLE} set categories_json = ?, competitors_json = ?, is_negative = ?, updated_at = ? where review_key = ?",
                (
                    json.dumps(classification.categories, ensure_ascii=False),
                    json.dumps(classification.competitors, ensure_ascii=False),
                    int(classification.is_negative),
                    self._now(),
                    row["review_key"],
                ),
            )

    def summary(self) -> ReviewCollectionSummary:
        with closing(self.database.connect()) as conn:
            row = conn.execute(
                f"select count(*) as total, min(review_date) as first_day, max(review_date) as latest_day, "
                f"count(distinct item_id) as products, count(distinct nullif(series, '')) as series from {REVIEWS_TABLE}"
            ).fetchone()
            run = conn.execute(f"select * from {RUNS_TABLE} order by started_at desc limit 1").fetchone()
        return ReviewCollectionSummary(
            total_reviews=int(row["total"]),
            first_review_date=str(row["first_day"]) if row["first_day"] else None,
            latest_review_date=str(row["latest_day"]) if row["latest_day"] else None,
            last_collected_at=str(run["finished_at"] or run["started_at"]) if run else None,
            last_run=self._run_model(run) if run else None,
            product_count=int(row["products"]),
            series_count=int(row["series"]),
        )

    def list_products(self) -> list[dict[str, str | int | None]]:
        with closing(self.database.connect()) as conn:
            rows = conn.execute(
                f"select item_id, max(item_name) as item_name, max(series) as series, count(*) as review_count "
                f"from {REVIEWS_TABLE} where item_id is not null and item_id <> '' group by item_id order by item_name collate nocase"
            ).fetchall()
        return [{"item_id": str(row["item_id"]), "item_name": row["item_name"], "series": row["series"], "review_count": int(row["review_count"])} for row in rows]

    def list_series(self) -> list[dict[str, str | int | None]]:
        with closing(self.database.connect()) as conn:
            rows = conn.execute(
                f"select series, count(*) as review_count, count(distinct item_id) as product_count from {REVIEWS_TABLE} "
                f"where series is not null and series <> '' group by series order by review_count desc, series collate nocase"
            ).fetchall()
        return [{"series": str(row["series"]), "review_count": int(row["review_count"]), "product_count": int(row["product_count"])} for row in rows]

    def ask_summary(self) -> AskSummary:
        with closing(self.database.connect()) as conn:
            row = conn.execute(
                f"select count(*) total, sum(has_answer) answered, count(distinct item_id) products, "
                f"min(question_date) first_day, max(question_date) latest_day from {ASKS_TABLE}"
            ).fetchone()
            category_rows = conn.execute(f"select categories_json from {ASKS_TABLE}").fetchall()
            run = conn.execute(f"select * from {ASK_RUNS_TABLE} order by started_at desc limit 1").fetchone()
        total = int(row["total"] or 0)
        answered = int(row["answered"] or 0)
        categories: Counter[str] = Counter()
        for category_row in category_rows:
            try:
                categories.update(json.loads(category_row[0] or "[]"))
            except (TypeError, json.JSONDecodeError):
                continue
        return AskSummary(
            total_questions=total,
            answered_questions=answered,
            unanswered_questions=total - answered,
            answer_rate=round(answered / total * 100, 2) if total else 0,
            product_count=int(row["products"] or 0),
            first_question_date=row["first_day"],
            latest_question_date=row["latest_day"],
            category_counts=self._counts(categories, total),
            last_run=self._run_model(run) if run else None,
        )

    def list_asks(
        self,
        *,
        product_id: str | None = None,
        series: str | None = None,
        category: str | None = None,
        search: str | None = None,
        has_answer: bool | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AskListResponse:
        conditions = ["1 = 1"]
        params: list[Any] = []
        if product_id:
            conditions.append("item_id = ?"); params.append(product_id)
        if series:
            conditions.append("series = ?"); params.append(series)
        if search:
            conditions.append("(question like ? or item_name like ? or item_id like ?)")
            value = f"%{search}%"; params.extend((value, value, value))
        if category:
            conditions.append("instr(categories_json, ?) > 0")
            params.append(json.dumps(category, ensure_ascii=False)[1:-1])
        if has_answer is not None:
            conditions.append("has_answer = ?"); params.append(int(has_answer))
        if start_date:
            conditions.append("question_date >= ?"); params.append(start_date)
        if end_date:
            conditions.append("question_date < date(?, '+1 day')"); params.append(end_date)
        where = " and ".join(conditions)
        offset = (page - 1) * page_size
        with closing(self.database.connect()) as conn:
            total = int(conn.execute(f"select count(*) from {ASKS_TABLE} where {where}", params).fetchone()[0])
            rows = conn.execute(
                f"select * from {ASKS_TABLE} where {where} order by question_date desc limit ? offset ?",
                [*params, page_size, offset],
            ).fetchall()
        return AskListResponse(items=[self._ask_record(row) for row in rows], total=total, page=page, page_size=page_size)

    def list_reviews(
        self,
        *,
        product_id: str | None = None,
        series: str | None = None,
        category: str | None = None,
        sentiment: str | None = None,
        search: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ReviewListResponse:
        where, params = self._where(product_id, series, start_date, end_date, search)
        category_sql = ""
        if category:
            category_sql = " and instr(categories_json, ?) > 0"
            params.append(json.dumps(category, ensure_ascii=False)[1:-1])
        sentiment_sql, sentiment_params = self._sentiment_where(sentiment)
        category_sql += sentiment_sql
        params.extend(sentiment_params)
        offset = (page - 1) * page_size
        with closing(self.database.connect()) as conn:
            total = int(conn.execute(f"select count(*) from {REVIEWS_TABLE} where {where}{category_sql}", params).fetchone()[0])
            rows = conn.execute(
                f"select * from {REVIEWS_TABLE} where {where}{category_sql} order by coalesce(review_date, fetched_at) desc limit ? offset ?",
                [*params, page_size, offset],
            ).fetchall()
        return ReviewListResponse(items=[self._record(row) for row in rows], total=total, page=page, page_size=page_size)

    def analysis(
        self,
        *,
        product_id: str | None = None,
        series: str | None = None,
        sentiment: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        top_limit: int = 10,
    ) -> ReviewAnalysis:
        where, params = self._where(product_id, series, start_date, end_date, None)
        sentiment_sql, sentiment_params = self._sentiment_where(sentiment)
        where += sentiment_sql
        params.extend(sentiment_params)
        with closing(self.database.connect()) as conn:
            rows = conn.execute(f"select * from {REVIEWS_TABLE} where {where} order by review_date", params).fetchall()
        records = [self._record(row) for row in rows]
        categories = Counter(category for record in records for category in record.categories if category != "竞品提及")
        competitors = Counter(name for record in records for name in record.competitors)
        trend: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for record in records:
            day = (record.review_date or "未知")[:10]
            trend[day][0] += 1
            trend[day][1] += int(record.is_negative)
        total = len(records)
        negative_reviews = sum(record.is_negative for record in records)
        return ReviewAnalysis(
            scope="product" if product_id else "series" if series else "all",
            product_id=product_id,
            series=series,
            start_date=start_date,
            end_date=end_date,
            total_reviews=total,
            negative_reviews=negative_reviews,
            normal_reviews=total - negative_reviews,
            negative_rate=round(negative_reviews / total * 100, 2) if total else 0,
            append_reviews=sum(bool(record.append_content) for record in records),
            media_reviews=sum(bool(record.main_media or record.append_media) for record in records),
            product_count=len({record.item_id for record in records if record.item_id}),
            category_counts=self._counts(categories, total),
            competitor_counts=self._counts(competitors, total),
            trend=[ReviewTrendPoint(day=day, total=values[0], negative=values[1]) for day, values in sorted(trend.items()) if day != "未知"],
            risk_products=self._risk_metrics(records, "product"),
            risk_series=self._risk_metrics(records, "series"),
            top_reviews=sorted(records, key=lambda record: (len(record.categories), record.review_date or ""), reverse=True)[:top_limit],
        )

    def collect(
        self,
        *,
        mode: str,
        max_pages: int,
        start_date: str = DEFAULT_START_DATE,
        end_date: str | None = None,
    ) -> ReviewCollectionRun:
        run = self.start_collection(mode=mode)
        self.execute_collection(
            run.run_id,
            mode=mode,
            max_pages=max_pages,
            start_date=start_date,
            end_date=end_date or datetime.now(timezone.utc).date().isoformat(),
        )
        return self._run_by_id(run.run_id)

    def start_collection(self, *, mode: str) -> ReviewCollectionRun:
        batch_id = active_daily_batch(self.database_path)
        if batch_id is not None:
            raise ReviewCollectionError(
                f"日常经营采集正在运行（{batch_id}），请等待完成后再启动评价采集。"
            )
        active_feedback = active_feedback_run(self.database_path)
        if active_feedback is not None:
            label, run_id = active_feedback
            raise ReviewCollectionError(
                f"{label}采集任务正在运行（{run_id}），请等待完成后再启动评价采集。"
            )
        run_id = str(uuid.uuid4())
        started = self._now()
        with closing(self.database.connect(read_only=False)) as conn:
            active = conn.execute(
                f"select run_id from {RUNS_TABLE} where status in ('queued', 'running') order by started_at desc limit 1"
            ).fetchone()
            if active:
                raise ReviewCollectionError("已有评价采集任务正在运行，请等待完成后再发起。")
            conn.execute(f"insert into {RUNS_TABLE}(run_id, mode, status, started_at) values (?, ?, 'queued', ?)", (run_id, mode, started))
            conn.commit()
        return self._run_by_id(run_id)

    def execute_collection(
        self,
        run_id: str,
        *,
        mode: str,
        max_pages: int,
        start_date: str = DEFAULT_START_DATE,
        end_date: str | None = None,
    ) -> None:
        with closing(self.database.connect(read_only=False)) as conn:
            conn.execute(f"update {RUNS_TABLE} set status='running' where run_id=?", (run_id,))
            conn.commit()
        try:
            result = self._collect_pages(
                mode=mode,
                max_pages=max_pages,
                start_date=start_date,
                end_date=end_date or datetime.now(timezone.utc).date().isoformat(),
            )
            finished = self._now()
            with closing(self.database.connect(read_only=False)) as conn:
                conn.execute(
                    f"update {RUNS_TABLE} set status='completed', finished_at=?, pages=?, fetched_count=?, inserted_count=?, updated_count=?, skipped_count=?, stopped_reason=? where run_id=?",
                    (finished, result["pages"], result["fetched"], result["inserted"], result["updated"], result["skipped"], result["reason"], run_id),
                )
                conn.commit()
        except Exception as exc:
            finished = self._now()
            with closing(self.database.connect(read_only=False)) as conn:
                conn.execute(f"update {RUNS_TABLE} set status='failed', finished_at=?, error=? where run_id=?", (finished, str(exc), run_id))
                conn.commit()
            return

    def collect_asks(self, *, mode: str = "incremental", max_pages: int = 500) -> ReviewCollectionRun:
        run = self.start_ask_collection(mode=mode)
        self.execute_ask_collection(run.run_id, mode=mode, max_pages=max_pages)
        with closing(self.database.connect()) as conn:
            row = conn.execute(f"select * from {ASK_RUNS_TABLE} where run_id = ?", (run.run_id,)).fetchone()
        return self._run_model(row)

    def start_ask_collection(self, *, mode: str = "incremental") -> ReviewCollectionRun:
        batch_id = active_daily_batch(self.database_path)
        if batch_id is not None:
            raise ReviewCollectionError(
                f"日常经营采集正在运行（{batch_id}），请等待完成后再启动问答采集。"
            )
        active_feedback = active_feedback_run(self.database_path)
        if active_feedback is not None:
            label, run_id = active_feedback
            raise ReviewCollectionError(
                f"{label}采集任务正在运行（{run_id}），请等待完成后再启动问答采集。"
            )
        run_id = str(uuid.uuid4())
        started = self._now()
        with closing(self.database.connect(read_only=False)) as conn:
            active = conn.execute(
                f"select run_id from {ASK_RUNS_TABLE} where status in ('queued', 'running') order by started_at desc limit 1"
            ).fetchone()
            if active:
                raise ReviewCollectionError("已有问大家采集任务正在运行，请等待完成后再发起。")
            conn.execute(
                f"insert into {ASK_RUNS_TABLE}(run_id, mode, status, started_at) values (?, ?, 'queued', ?)",
                (run_id, mode, started),
            )
            conn.commit()
        return self._ask_run_by_id(run_id)

    def execute_ask_collection(self, run_id: str, *, mode: str, max_pages: int) -> None:
        with closing(self.database.connect(read_only=False)) as conn:
            conn.execute(f"update {ASK_RUNS_TABLE} set status='running' where run_id=?", (run_id,))
            conn.commit()
        try:
            result = self._collect_ask_pages(mode=mode, max_pages=max_pages)
            finished = self._now()
            with closing(self.database.connect(read_only=False)) as conn:
                conn.execute(
                    f"update {ASK_RUNS_TABLE} set status='completed', finished_at=?, pages=?, fetched_count=?, inserted_count=?, updated_count=?, skipped_count=?, stopped_reason=? where run_id=?",
                    (finished, result["pages"], result["fetched"], result["inserted"], result["updated"], result["skipped"], result["reason"], run_id),
                )
                conn.commit()
        except Exception as exc:
            finished = self._now()
            with closing(self.database.connect(read_only=False)) as conn:
                conn.execute(
                    f"update {ASK_RUNS_TABLE} set status='failed', finished_at=?, error=? where run_id=?",
                    (finished, str(exc), run_id),
                )
                conn.commit()

    def _ask_run_by_id(self, run_id: str) -> ReviewCollectionRun:
        with closing(self.database.connect()) as conn:
            row = conn.execute(f"select * from {ASK_RUNS_TABLE} where run_id = ?", (run_id,)).fetchone()
        return self._run_model(row)

    def ask_runs(self, limit: int = 20) -> list[ReviewCollectionRun]:
        with closing(self.database.connect()) as conn:
            rows = conn.execute(
                f"select * from {ASK_RUNS_TABLE} order by started_at desc limit ?", (limit,)
            ).fetchall()
        return [self._run_model(row) for row in rows]

    def _collect_ask_pages(self, *, mode: str, max_pages: int) -> dict[str, int | str]:
        session = self._resolve_collection_session(
            home_url="https://myseller.taobao.com/home.htm/comment-manage/ask-all?current=1&pageSize=10",
        )
        cookie_map = self._cookie_map(session.cookie_header)
        m_h5_tk = cookie_map.get("_m_h5_tk") or cookie_map.get("*m_h5_tk*") or cookie_map.get("m_h5_tk")
        if not m_h5_tk:
            raise ReviewCollectionError("当前会话缺少 _m_h5_tk，无法生成淘宝接口签名。")
        known = self._known_ask_keys() if mode == "incremental" else set()
        inserted = updated = skipped = fetched = 0
        reason = "达到接口末页"
        for page in range(1, max_pages + 1):
            items = self._request_ask_page(cookie_map, m_h5_tk, page)
            if not items:
                reason = "接口返回空页"
                return {"pages": page, "fetched": fetched, "inserted": inserted, "updated": updated, "skipped": skipped, "reason": reason}
            fetched += len(items)
            page_known = 0
            for item in items:
                parsed = self._parse_ask_item(item)
                if parsed is None:
                    skipped += 1
                    continue
                if parsed["ask_id"] in known:
                    page_known += 1
                action = self._upsert_ask(parsed)
                inserted += action == "inserted"
                updated += action == "updated"
                known.add(parsed["ask_id"])
            if mode == "incremental" and page_known == len(items):
                reason = "整页问题已存在，增量采集停止"
                return {"pages": page, "fetched": fetched, "inserted": inserted, "updated": updated, "skipped": skipped, "reason": reason}
            if len(items) < ASK_PAGE_SIZE:
                reason = "返回数量少于分页大小"
                return {"pages": page, "fetched": fetched, "inserted": inserted, "updated": updated, "skipped": skipped, "reason": reason}
        return {"pages": max_pages, "fetched": fetched, "inserted": inserted, "updated": updated, "skipped": skipped, "reason": "达到采集页数上限"}

    def _request_ask_page(self, cookies: dict[str, str], m_h5_tk: str, page: int) -> list[dict[str, Any]]:
        body = {
            "pagination": {"current": page, "pageSize": ASK_PAGE_SIZE},
            "hasAnswer": 1,
            "sellerConfigTag": 0,
            "bizType": 200,
        }
        inner = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        data_json = json.dumps({"jsonBody": inner}, ensure_ascii=False, separators=(",", ":"))
        timestamp, sign = sign_mtop_data(data_json, m_h5_tk, APP_KEY)
        params = {
            "jsv": "2.6.1", "appKey": APP_KEY, "t": timestamp, "sign": sign,
            "api": ASK_API_NAME, "v": "1.0", "ttid": "11320@taobao_WEB_9.9.99",
            "syncCookieMode": "true", "type": "originaljson", "dataType": "json",
        }
        request = Request(
            ASK_API_URL + "?" + urlencode(params),
            data=urlencode({"data": data_json}).encode("utf-8"),
            headers={
                "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded",
                "Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items()),
                "Origin": "https://myseller.taobao.com",
                "Referer": "https://myseller.taobao.com/home.htm/comment-manage/ask-all?current=1&pageSize=10",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ReviewCollectionError(f"淘宝问大家接口请求失败（第 {page} 页）：{exc}") from exc
        if payload.get("ret") and any("成功" not in str(value) and "调用成功" not in str(value) for value in payload.get("ret", [])):
            raise ReviewCollectionError("淘宝问大家接口返回错误：" + "；".join(map(str, payload.get("ret", []))))
        data = payload.get("data", {}).get("data", {})
        return data.get("dataSource", []) if isinstance(data.get("dataSource"), list) else []

    def _parse_ask_item(self, item: dict[str, Any]) -> dict[str, Any] | None:
        module = item.get("askAndAnswerModule") if isinstance(item.get("askAndAnswerModule"), dict) else {}
        product = item.get("itemInfo") if isinstance(item.get("itemInfo"), dict) else {}
        user = item.get("userInfoModule") if isinstance(item.get("userInfoModule"), dict) else {}
        ask_id = self._first(item, "id") or self._first(module, "id")
        question = self._text(module.get("content"))
        if not ask_id or not question:
            return None
        classification = self.analyzer.classify(question)
        return {
            "ask_id": self._text(ask_id),
            "item_id": self._text(self._first(product, "itemId")),
            "item_name": self._text(self._first(product, "title")),
            "item_link": self._text(self._first(product, "link")),
            "series": self._series_for(self._text(self._first(product, "itemId"))),
            "user_name": self._text(self._first(user, "userAnnoyNick")),
            "question": question,
            "question_date": self._date(self._first(module, "gmtCreate")),
            "answer_count": int(item.get("answerNumber") or 0),
            "has_answer": int(bool(item.get("hasAnswer") or int(item.get("answerNumber") or 0) > 0)),
            "categories": classification.categories,
            "competitors": classification.competitors,
            "source_json": json.dumps(item, ensure_ascii=False, separators=(",", ":")),
        }

    def _upsert_ask(self, data: dict[str, Any]) -> str:
        now = self._now()
        fields = dict(data)
        fields["categories_json"] = json.dumps(fields.pop("categories"), ensure_ascii=False)
        fields["competitors_json"] = json.dumps(fields.pop("competitors"), ensure_ascii=False)
        fields.update({"first_seen_at": now, "fetched_at": now, "updated_at": now})
        with closing(self.database.connect(read_only=False)) as conn:
            exists = conn.execute(f"select ask_id from {ASKS_TABLE} where ask_id = ?", (fields["ask_id"],)).fetchone()
            if exists:
                assignments = ", ".join(f"{key} = ?" for key in fields if key not in {"ask_id", "first_seen_at"})
                conn.execute(
                    f"update {ASKS_TABLE} set {assignments} where ask_id = ?",
                    [value for key, value in fields.items() if key not in {"ask_id", "first_seen_at"}] + [fields["ask_id"]],
                )
                conn.commit()
                return "updated"
            columns = ", ".join(fields)
            placeholders = ", ".join("?" for _ in fields)
            conn.execute(f"insert into {ASKS_TABLE} ({columns}) values ({placeholders})", list(fields.values()))
            conn.commit()
            return "inserted"

    def _known_ask_keys(self) -> set[str]:
        with closing(self.database.connect()) as conn:
            return {str(row[0]) for row in conn.execute(f"select ask_id from {ASKS_TABLE}").fetchall()}

    def _collect_pages(
        self,
        *,
        mode: str,
        max_pages: int,
        start_date: str = DEFAULT_START_DATE,
        end_date: str | None = None,
    ) -> dict[str, int | str]:
        session = self._resolve_collection_session(
            home_url="https://myseller.taobao.com/home.htm/comment-manage/list/rateWait4PC?current=1&pageSize=20",
        )
        cookie_map = self._cookie_map(session.cookie_header)
        m_h5_tk = cookie_map.get("_m_h5_tk") or cookie_map.get("*m_h5_tk*") or cookie_map.get("m_h5_tk")
        if not m_h5_tk:
            raise ReviewCollectionError("当前会话缺少 _m_h5_tk，无法生成淘宝接口签名。")
        known = self._known_keys() if mode == "incremental" else set()
        inserted = updated = skipped = fetched = pages = 0
        reason = "达到接口末页"
        # 淘宝页面按 20 条分页，串行请求 714 页会非常慢；小批量并行只
        # 加速网络等待，解析和 SQLite 写入仍按页顺序执行，增量停止规则稳定。
        worker_count = 6
        ranges = self._collection_ranges(mode=mode, start_date=start_date, end_date=end_date)
        for range_start, range_end in ranges:
            if pages >= max_pages:
                reason = "达到采集页数上限"
                break
            range_pages = 0
            with ThreadPoolExecutor(max_workers=worker_count) as executor:
                for batch_start in range(1, max_pages - pages + 1, worker_count):
                    batch_pages = range(batch_start, min(batch_start + worker_count, max_pages - pages + 1))
                    futures = {
                        executor.submit(
                            self._request_page,
                            cookie_map,
                            m_h5_tk,
                            page,
                            start_date=range_start,
                            end_date=range_end,
                        ): page
                        for page in batch_pages
                    }
                    page_results: dict[int, list[dict[str, Any]]] = {}
                    for future in as_completed(futures):
                        page_results[futures[future]] = future.result()
                    should_stop = False
                    for page in sorted(page_results):
                        items = page_results[page]
                        pages += 1
                        range_pages = page
                        if not items:
                            reason = "接口返回空页"
                            should_stop = True
                            break
                        fetched += len(items)
                        page_known = 0
                        for item in items:
                            parsed = self._parse_item(item)
                            if parsed is None:
                                skipped += 1
                                continue
                            if parsed["review_key"] in known:
                                page_known += 1
                            action = self._upsert(parsed)
                            inserted += action == "inserted"
                            updated += action == "updated"
                            known.add(parsed["review_key"])
                        if mode == "incremental" and page_known == len(items):
                            reason = "整页评价已存在，增量采集停止"
                            should_stop = True
                            break
                        if len(items) < PAGE_SIZE:
                            reason = "返回数量少于分页大小"
                            should_stop = True
                            break
                    if should_stop:
                        break
            if mode == "incremental" and reason == "整页评价已存在，增量采集停止":
                break
        return {"pages": pages, "fetched": fetched, "inserted": inserted, "updated": updated, "skipped": skipped, "reason": reason}

    def _resolve_collection_session(self, *, home_url: str) -> RuntimeSession:
        """Resolve the review session, falling back to the local logged-in browser.

        Older deployments default to an environment cookie.  On this machine the
        supported session is the attached Chrome profile, so a missing env value
        should not make review and ask collection fail when that browser is ready.
        """
        if settings.tmall_session_source != "env":
            return resolve_runtime_session(
                source=settings.tmall_session_source,
                cookie_env=settings.tmall_cookie_env,
                browser_port=settings.tmall_browser_port,
                home_url=home_url,
            )

        if os.getenv(settings.tmall_cookie_env, "").strip():
            return resolve_runtime_session(
                source="env",
                cookie_env=settings.tmall_cookie_env,
                browser_port=settings.tmall_browser_port,
                home_url=home_url,
            )

        try:
            return resolve_runtime_session(
                source="drissionpage",
                cookie_env=settings.tmall_cookie_env,
                browser_port=settings.tmall_browser_port,
                home_url=home_url,
            )
        except RuntimeSessionUnavailable as browser_exc:
            raise ReviewCollectionError(
                f"{settings.tmall_cookie_env} 未配置，且已登录采集浏览器不可用：{browser_exc}"
            ) from browser_exc

    def _request_page(
        self,
        cookies: dict[str, str],
        m_h5_tk: str,
        page: int,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        # 浏览器的“来自买家的评价”默认不带情感筛选；旧脚本的 emotion=13
        # 只会返回部分情感类型，无法完成全量历史采集。
        body: dict[str, Any] = {
            "pageType": PAGE_TYPE,
            "pagination": {"current": page, "pageSize": PAGE_SIZE},
        }
        if start_date and end_date:
            # 评价管理前端使用 YYYYMMDD 数字字符串，同时发送 dateRange/timeTag。
            date_range = [start_date.replace("-", ""), end_date.replace("-", "")]
            body["dateRange"] = date_range
            body["timeTag"] = date_range
        inner = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        data_json = json.dumps({"jsonBody": inner}, ensure_ascii=False, separators=(",", ":"))
        timestamp, sign = sign_mtop_data(data_json, m_h5_tk, APP_KEY)
        params = {"jsv": "2.6.1", "appKey": APP_KEY, "t": timestamp, "sign": sign, "api": API_NAME, "v": "1.0", "ttid": "11320@taobao_WEB_9.9.99", "syncCookieMode": "true", "type": "originaljson", "dataType": "json"}
        request = Request(
            API_URL + "?" + urlencode(params),
            data=urlencode({"data": data_json}).encode("utf-8"),
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded", "Cookie": "; ".join(f"{key}={value}" for key, value in cookies.items()), "Origin": "https://myseller.taobao.com", "Referer": "https://myseller.taobao.com/home.htm/comment-manage/list/rateWait4PC?current=1&pageSize=20", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0.0.0 Safari/537.36"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ReviewCollectionError(f"淘宝评价接口请求失败（第 {page} 页）：{exc}") from exc
        if not isinstance(payload, dict):
            raise ReviewCollectionError("淘宝评价接口返回格式不是 JSON 对象。")
        if payload.get("ret") and any("成功" not in str(value) for value in payload.get("ret", [])):
            raise ReviewCollectionError("淘宝评价接口返回错误：" + "；".join(map(str, payload.get("ret", []))))
        return self._extract_items(payload)

    @staticmethod
    def _collection_ranges(
        *, mode: str, start_date: str, end_date: str | None
    ) -> list[tuple[str | None, str | None]]:
        """Split initial history into monthly windows to avoid Taobao's 5k cap."""
        if mode != "initial":
            return [(start_date, end_date)]
        start = date.fromisoformat(start_date or DEFAULT_START_DATE)
        finish = date.fromisoformat(end_date or datetime.now(timezone.utc).date().isoformat())
        ranges: list[tuple[str, str]] = []
        cursor = start.replace(day=1)
        while cursor <= finish:
            if cursor.month == 12:
                next_month = cursor.replace(year=cursor.year + 1, month=1, day=1)
            else:
                next_month = cursor.replace(month=cursor.month + 1, day=1)
            month_end = min(finish, next_month - timedelta(days=1))
            ranges.append((max(start, cursor).isoformat(), month_end.isoformat()))
            cursor = next_month
        return ranges

    def _parse_item(self, item: dict[str, Any]) -> dict[str, Any] | None:
        rate = item.get("rateContent") if isinstance(item.get("rateContent"), dict) else {}
        main = rate.get("mainRate") if isinstance(rate.get("mainRate"), dict) else {}
        append = rate.get("appendRate") if isinstance(rate.get("appendRate"), dict) else {}
        user = item.get("userInfo") if isinstance(item.get("userInfo"), dict) else {}
        order = item.get("orderInfo") if isinstance(item.get("orderInfo"), dict) else {}
        product = item.get("itemInfo") if isinstance(item.get("itemInfo"), dict) else {}
        main_content = self._text(main.get("content") or main.get("rateContent"))
        append_content = self._text(append.get("content") or append.get("rateContent"))
        merged = "\n".join(part for part in (main_content, append_content) if part)
        platform_id = self._first(main, "id", "rateId", "reviewId") or self._first(rate, "id", "rateId") or self._first(item, "id", "rateId")
        order_id = self._first(order, "mainOrderId", "orderId")
        item_id = self._first(product, "itemId", "id")
        if not item_id:
            item_id = self._first(item, "itemId")
        review_key = str(platform_id or self._fingerprint(order_id, item_id, self._first(main, "date", "createTime"), merged))
        classification = self.analyzer.classify(merged)
        series = self._series_for(item_id)
        return {"review_key": review_key, "platform_review_id": self._text(platform_id), "user_name": self._text(self._first(user, "userName", "nick")), "security_id": self._text(self._first(user, "securityuid", "securityUid")), "emotion_type": self._text((item.get("emotionType") or {}).get("status") if isinstance(item.get("emotionType"), dict) else item.get("emotionType")), "order_id": self._text(order_id), "item_id": self._text(item_id), "item_name": self._text(self._first(product, "title", "itemTitle", "name")), "item_link": self._text(self._first(product, "link", "url")), "series": series, "review_date": self._date(self._first(main, "date", "createTime", "gmtCreate")), "main_content": main_content, "append_content": append_content, "merged_content": merged, "main_media": self._media(main.get("mediaList")), "append_media": self._media(append.get("mediaList")), "overview": self._overview(main.get("expression")), "categories": classification.categories, "competitors": classification.competitors, "is_negative": int(classification.is_negative), "source_json": json.dumps(item, ensure_ascii=False, separators=(",", ":"))}

    def _upsert(self, data: dict[str, Any]) -> str:
        now = self._now()
        fields = dict(data)
        fields["main_media_json"] = json.dumps(fields.pop("main_media"), ensure_ascii=False)
        fields["append_media_json"] = json.dumps(fields.pop("append_media"), ensure_ascii=False)
        fields["overview_json"] = json.dumps(fields.pop("overview"), ensure_ascii=False)
        fields["categories_json"] = json.dumps(fields.pop("categories"), ensure_ascii=False)
        fields["competitors_json"] = json.dumps(fields.pop("competitors"), ensure_ascii=False)
        fields["is_negative"] = int(fields["is_negative"])
        fields.update({"first_seen_at": now, "fetched_at": now, "updated_at": now})
        with closing(self.database.connect(read_only=False)) as conn:
            exists = conn.execute(f"select review_key from {REVIEWS_TABLE} where review_key = ?", (fields["review_key"],)).fetchone()
            if exists:
                assignments = ", ".join(f"{key} = ?" for key in fields if key not in {"review_key", "first_seen_at"})
                conn.execute(f"update {REVIEWS_TABLE} set {assignments} where review_key = ?", [value for key, value in fields.items() if key not in {"review_key", "first_seen_at"}] + [fields["review_key"]])
                conn.commit()
                return "updated"
            columns = ", ".join(fields)
            placeholders = ", ".join("?" for _ in fields)
            conn.execute(f"insert into {REVIEWS_TABLE} ({columns}) values ({placeholders})", list(fields.values()))
            conn.commit()
            return "inserted"

    def _known_keys(self) -> set[str]:
        with closing(self.database.connect()) as conn:
            return {str(row[0]) for row in conn.execute(f"select review_key from {REVIEWS_TABLE}").fetchall()}

    def _where(self, product_id: str | None, series: str | None, start_date: str | None, end_date: str | None, search: str | None) -> tuple[str, list[Any]]:
        conditions = ["1 = 1"]
        params: list[Any] = []
        if product_id:
            conditions.append("item_id = ?"); params.append(product_id)
        if series:
            conditions.append("series = ?"); params.append(series)
        if start_date:
            conditions.append("review_date >= ?"); params.append(start_date)
        if end_date:
            conditions.append("review_date < date(?, '+1 day')"); params.append(end_date)
        if search:
            conditions.append("(merged_content like ? or item_name like ? or item_id like ?)"); value = f"%{search}%"; params.extend((value, value, value))
        return " and ".join(conditions), params

    def _run_by_id(self, run_id: str) -> ReviewCollectionRun:
        with closing(self.database.connect()) as conn:
            row = conn.execute(f"select * from {RUNS_TABLE} where run_id = ?", (run_id,)).fetchone()
        return self._run_model(row)

    @staticmethod
    def _run_model(row: sqlite3.Row) -> ReviewCollectionRun:
        return ReviewCollectionRun(**dict(row))

    def _record(self, row: sqlite3.Row, *, reclassify: bool = False) -> ReviewRecord:
        value = dict(row)
        for target, source in (("main_media", "main_media_json"), ("append_media", "append_media_json"), ("overview", "overview_json"), ("categories", "categories_json"), ("competitors", "competitors_json")):
            try: value[target] = json.loads(value.pop(source) or "[]")
            except (TypeError, json.JSONDecodeError): value[target] = []
        value.pop("source_json", None); value.pop("first_seen_at", None); value.pop("updated_at", None)
        # The classifier runs once during ingestion/reclassification. Reusing
        # the persisted result avoids scanning and classifying every review on
        # each dashboard request. Callers handling legacy rows can opt in to a
        # read-time refresh explicitly.
        if reclassify:
            classification = self.analyzer.classify(value.get("merged_content", ""))
            value["categories"] = classification.categories
            value["competitors"] = classification.competitors
            value["is_negative"] = classification.is_negative
        value["sentiment"] = self._sentiment_label(value.get("emotion_type"), bool(value.get("is_negative")))
        return ReviewRecord(**value)

    @staticmethod
    def _sentiment_label(emotion_type: Any, has_issue: bool) -> str:
        value = str(emotion_type or "").strip()
        if value == "11":
            return "positive"
        if value == "12":
            return "neutral"
        if value == "13":
            return "negative"
        # Platform sentiment and text-issue classification are different
        # dimensions. Missing platform status must remain unknown instead of
        # being inferred from keyword-based issue detection.
        return "unknown"

    @staticmethod
    def _sentiment_where(sentiment: str | None) -> tuple[str, list[Any]]:
        if sentiment == "positive":
            return " and emotion_type = '11'", []
        if sentiment == "neutral":
            return " and emotion_type = '12'", []
        if sentiment == "negative":
            return " and emotion_type = '13'", []
        if sentiment == "unknown":
            return " and coalesce(trim(emotion_type), '') = ''", []
        return "", []

    @staticmethod
    def _ask_record(row: sqlite3.Row) -> AskRecord:
        value = dict(row)
        for target, source in (("categories", "categories_json"), ("competitors", "competitors_json")):
            try:
                value[target] = json.loads(value.pop(source) or "[]")
            except (TypeError, json.JSONDecodeError):
                value[target] = []
        value.pop("source_json", None)
        value.pop("first_seen_at", None)
        value.pop("updated_at", None)
        value["has_answer"] = bool(value.get("has_answer"))
        return AskRecord(**value)

    @staticmethod
    def _counts(counter: Counter[str], total: int) -> list[ReviewCategoryCount]:
        return [ReviewCategoryCount(name=name, count=count, share=round(count / total * 100, 2) if total else 0) for name, count in counter.most_common()]

    @staticmethod
    def _risk_metrics(records: list[ReviewRecord], dimension: str) -> list[dict[str, Any]]:
        groups: dict[str, list[ReviewRecord]] = defaultdict(list)
        for record in records:
            key = record.item_id if dimension == "product" else record.series
            if key:
                groups[str(key)].append(record)
        metrics: list[dict[str, Any]] = []
        for key, rows in groups.items():
            total = len(rows)
            issues = [record for record in rows if record.is_negative]
            if not issues:
                continue
            issue_counts = Counter(
                category
                for record in issues
                for category in record.categories
                if category != "竞品提及"
            )
            first = rows[0]
            metrics.append({
                "key": key,
                "label": (first.item_name or key) if dimension == "product" else key,
                "series": first.series if dimension == "product" else key,
                "total_reviews": total,
                "issue_reviews": len(issues),
                "issue_rate": round(len(issues) / total * 100, 2),
                "top_issue": issue_counts.most_common(1)[0][0] if issue_counts else None,
            })
        return sorted(
            metrics,
            key=lambda item: (item["issue_reviews"], item["issue_rate"], item["total_reviews"]),
            reverse=True,
        )[:10]

    def _series_for(self, item_id: str | None) -> str | None:
        if not item_id:
            return None
        try:
            with closing(self.database.connect()) as conn:
                for table in ("brand_products", "store_product_catalog"):
                    if not self._table_exists(conn, table): continue
                    columns = {str(row[1]) for row in conn.execute(f"pragma table_info(\"{table}\")")}
                    if "商品ID" not in columns or "系列" not in columns: continue
                    row = conn.execute(f"select \"系列\" from \"{table}\" where \"商品ID\" = ? limit 1", (item_id,)).fetchone()
                    if row and row[0]: return str(row[0])
        except sqlite3.Error:
            pass
        return None

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
        return conn.execute("select 1 from sqlite_master where type='table' and name=?", (name,)).fetchone() is not None

    @staticmethod
    def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        def walk(value: Any) -> list[dict[str, Any]]:
            if isinstance(value, dict):
                for key in ("dataSource", "list", "items", "results"):
                    if isinstance(value.get(key), list) and all(isinstance(item, dict) for item in value[key]): return value[key]
                for child in value.values():
                    found = walk(child)
                    if found: return found
            elif isinstance(value, list):
                for child in value:
                    found = walk(child)
                    if found: return found
            return []
        return walk(payload)

    @staticmethod
    def _cookie_map(header: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for part in header.split(";"):
            if "=" not in part: continue
            key, value = part.strip().split("=", 1)
            result[key.strip()] = value.strip()
        return result

    @staticmethod
    def _first(value: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if value.get(key) not in (None, ""): return value.get(key)
        return None

    @staticmethod
    def _text(value: Any) -> str:
        if value is None: return ""
        if isinstance(value, list): return "".join(ReviewService._text(item) for item in value)
        return str(value).strip()

    @staticmethod
    def _date(value: Any) -> str | None:
        if value in (None, ""): return None
        if isinstance(value, (int, float)):
            try: return datetime.fromtimestamp(float(value) / (1000 if float(value) > 10_000_000_000 else 1), tz=timezone.utc).isoformat()
            except (ValueError, OSError, OverflowError): return None
        text = str(value).strip()
        return text[:19].replace("/", "-") or None

    @staticmethod
    def _media(value: Any) -> list[str]:
        if not isinstance(value, list): return []
        result: list[str] = []
        for media in value:
            if not isinstance(media, dict): continue
            link = media.get("thumbnail") or media.get("url") or media.get("mp4Url")
            if link: result.append(str(link))
        return result

    @staticmethod
    def _overview(value: Any) -> list[str]:
        if not isinstance(value, list): return []
        return [str(item.get("content")) for item in value if isinstance(item, dict) and item.get("content")]

    @staticmethod
    def _fingerprint(*values: Any) -> str:
        raw = "|".join(str(value or "").strip() for value in values)
        return "fp_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
