from app.modules.reviews.analyzer import ReviewAnalyzer


def test_positive_negated_quality_phrases_are_not_issues() -> None:
    analyzer = ReviewAnalyzer()

    for text in (
        "宝宝用了没有红屁股，整晚干爽",
        "这款不漏尿，透气性很好",
        "之前穿别的会红屁股，这款用了几天没有红屁股",
        "没有异味，宝宝很舒服",
        "不容易闷红屁股，透气性很好",
        "透气性在线不闷红屁屁",
        "怕宝宝夏天闷出红屁股，这款用着就不错",
        "告别红屁屁，宝宝整晚干爽",
        "没有侧漏红屁股现象，薄厚度刚好",
    ):
        result = analyzer.classify(text)
        assert result.categories == [], text
        assert result.is_negative is False, text


def test_real_issue_after_positive_phrase_is_kept() -> None:
    analyzer = ReviewAnalyzer()

    result = analyzer.classify("不漏尿，但是晚上还是红屁股，勒腿")

    assert "红屁股" in result.categories
    assert "尺码问题" in result.categories
    assert "漏尿" not in result.categories
    assert result.is_negative is True

    quick_onset = analyzer.classify("没用两天就红屁股了")
    assert "红屁股" in quick_onset.categories


def test_competitor_only_mention_is_not_negative() -> None:
    result = ReviewAnalyzer().classify("之前用好奇，这款更透气")

    assert result.competitors == ["好奇"]
    assert result.categories == []
    assert result.is_negative is False
