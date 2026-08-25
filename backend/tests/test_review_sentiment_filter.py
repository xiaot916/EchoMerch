from datetime import datetime, timezone

from app.modules.reviews.service import ReviewService


def _insert_review(service: ReviewService, review_key: str, emotion_type: str, content: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with service.database.connect(read_only=False) as conn:
        conn.execute(
            """
            insert into review_records(
                review_key, emotion_type, series, review_date, merged_content,
                first_seen_at, fetched_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (review_key, emotion_type, "测试系列", "2026-08-21", content, now, now, now),
        )
        conn.commit()


def test_platform_sentiment_filter_does_not_infer_from_text_issue(tmp_path) -> None:
    service = ReviewService(tmp_path / "reviews.sqlite3")
    _insert_review(service, "positive", "11", "穿着舒服，没有红屁股")
    _insert_review(service, "neutral", "12", "一般，暂时可以")
    _insert_review(service, "negative", "13", "晚上漏尿，体验不好")
    _insert_review(service, "unknown", "", "文本提到漏尿，但没有平台等级")

    assert service.list_reviews(series="测试系列", sentiment="positive", page=1, page_size=20).total == 1
    assert service.list_reviews(series="测试系列", sentiment="neutral", page=1, page_size=20).total == 1
    negative = service.list_reviews(series="测试系列", sentiment="negative", page=1, page_size=20)
    assert negative.total == 1
    assert negative.items[0].review_key == "negative"

    missing_level = service.list_reviews(series="测试系列", sentiment="unknown", page=1, page_size=20)
    assert missing_level.total == 1
    assert missing_level.items[0].review_key == "unknown"

    unknown = service.list_reviews(series="测试系列", page=1, page_size=20)
    assert next(item for item in unknown.items if item.review_key == "unknown").sentiment == "unknown"


def test_platform_sentiment_analysis_and_list_have_same_scope(tmp_path) -> None:
    service = ReviewService(tmp_path / "reviews.sqlite3")
    for key, emotion_type in (("n1", "13"), ("n2", "13"), ("p1", "11")):
        _insert_review(service, key, emotion_type, "漏尿" if key.startswith("n") else "体验不错")

    analysis = service.analysis(series="测试系列", sentiment="negative")
    reviews = service.list_reviews(series="测试系列", sentiment="negative", page=1, page_size=20)

    assert analysis.total_reviews == reviews.total == 2
    assert {item.review_key for item in reviews.items} == {"n1", "n2"}
