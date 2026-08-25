from __future__ import annotations

import re
from dataclasses import dataclass


# These are evidence phrases, not simple word matches. A keyword is only
# treated as an issue when it is used as a complaint in its local sentence.
RULES: dict[str, tuple[str, ...]] = {
    "漏尿": ("漏尿", "侧漏", "渗尿", "湿床单", "滴答", "透湿", "滴水", "漏出来", "漏一屁股", "漏湿"),
    "漏屎": ("漏屎", "漏💩", "便便漏", "渗屎", "粑粑漏", "漏粑粑"),
    "红屁股": ("红屁股", "红屁屁", "红臀", "过敏", "红肿", "疹子", "红痘痘", "红破皮", "红疹"),
    "材质问题": ("粗糙", "硬", "扎人", "磨腿", "毛刺", "颗粒感", "硌得慌", "渣渣", "白毛毛", "掉絮"),
    "异味": ("异味", "臭味", "刺鼻", "香精", "甲醛", "工业香精", "臭的", "一股味道"),
    "尺码问题": ("尺码不准", "码数不对", "勒肚子", "勒痕", "尺码偏小", "码偏小", "尺码小", "偏小", "勒腿", "太紧", "过紧", "偏紧", "有点紧"),
    "设计缺陷": ("胶条粘不住", "粘不住", "设计不合理", "没胶条", "胶条掉", "收纳贴", "丢弃贴", "漏斗"),
    "客服问题": ("客服态度差", "客服不理人", "客服推脱", "阴阳怪气", "敷衍", "售后差", "不解决", "态度差", "不理人"),
    "包装问题": ("包装差", "包装破损", "包装脏", "包装烂", "破损", "简陋", "运输损坏"),
    "反渗问题": ("反渗", "返渗", "潮湿", "湿透", "潮潮的", "透湿", "不干爽"),
    "起坨/结块": ("起坨", "结块", "沙沙的", "一坨", "坨着", "挤在一坨"),
    "价格问题": ("太贵", "贵了", "越来越贵", "涨价", "不值", "性价比低", "价格高", "价格越来越高", "小贵", "不便宜"),
    "物流问题": ("物流慢", "快递差", "不送货", "自提柜", "丢件", "运输慢"),
    "赠品问题": ("没赠品", "赠品少", "赠品差", "不送赠品", "赠品破损"),
    "产品破损": ("破的", "坏的", "裂开", "撕烂", "质量差"),
    "厚度问题": ("太厚", "偏厚", "过厚", "厚重", "厚了", "有点厚", "不够薄", "太薄"),
    "吸水性问题": ("不吸尿", "吸水差", "吸收差", "兜不住", "尿不干"),
    "尺寸偏差": ("偏大", "码数偏差", "尺码差异"),
    "真假问题": ("假货", "仿品", "非正品", "品质不一", "和之前不一样"),
    "使用体验": ("不舒服", "难受", "难用", "不顺手", "体验差"),
}

COMPETITORS = ("好奇", "babycare", "bbc", "帮宝适", "大王", "尤妮佳", "露安适", "bebebus", "奇莫", "黑金帮")
NEGATION_BEFORE_RE = re.compile(
    r"(?:没有|没|无|未|不曾|不会|不易|不容易|未见|没见|没出现|没有出现|未出现|没发生|没有发生|未发生|避免|防止|从未|告别|远离|不)"
    r"(?:再|会|容易|出现|发生|造成|导致|引起|有)?"
    r"(?:闷汗|闷出|闷|任何|一点|一点点|什么)?$"
)
NEGATION_SPAN_RE = re.compile(r"(?:没有|没|无|未|不易|不容易|不会|不)(?!到|如)[^，,。！？!?；;]{0,8}$")
RAPID_ONSET_RE = re.compile(r"(?:没|没有|未)(?:用|穿|戴)[^，,。！？!?；;]{0,6}(?:就|便|开始)$")
HISTORICAL_RE = re.compile(r"(?:之前|以前|原来|别的|其他|上一款|上一个|以前用)")
CONCERN_RE = re.compile(r"(?:怕|担心|害怕|最怕|预防|防止|避免|针对|告别|远离)")
CLAUSE_BOUNDARY_RE = re.compile(r"[，,。！？!?；;\n]|但是|不过|然而|反而|后来|现在|却|但")


@dataclass(frozen=True)
class Classification:
    categories: list[str]
    competitors: list[str]
    is_negative: bool


class ReviewAnalyzer:
    def __init__(self) -> None:
        self._patterns = {
            name: tuple(re.compile(re.escape(keyword), re.IGNORECASE) for keyword in sorted(keywords, key=len, reverse=True))
            for name, keywords in RULES.items()
        }
        self._competitor_patterns = tuple((name, re.compile(re.escape(name), re.IGNORECASE)) for name in COMPETITORS)

    @staticmethod
    def _local_clause(text: str, start: int, end: int) -> tuple[str, str, str]:
        left_boundary = max((match.end() for match in CLAUSE_BOUNDARY_RE.finditer(text, 0, start)), default=0)
        right_match = CLAUSE_BOUNDARY_RE.search(text, end)
        right_boundary = right_match.start() if right_match else len(text)
        clause = text[left_boundary:right_boundary]
        return clause, clause[: start - left_boundary], clause[end - left_boundary :]

    @classmethod
    def _is_negated(cls, text: str, start: int, end: int) -> bool:
        _, before, after = cls._local_clause(text, start, end)
        if NEGATION_BEFORE_RE.search(before[-12:]):
            return True
        if NEGATION_SPAN_RE.search(before[-14:]) and not RAPID_ONSET_RE.search(before[-14:]):
            return True
        # “之前穿别的会红屁股，这款没有” describes the old product, not
        # the current review target. A later clause is still evaluated on its
        # own, so “之前会红，这款现在也红” remains a real issue.
        if HISTORICAL_RE.search(before) and not re.search(r"(?:这款|现在|本款|这一款)", before):
            return True
        if CONCERN_RE.search(before):
            return True
        if re.match(r"^(?:都|也|一直|完全)?(?:没有|没|无|未|不)", after[:10]):
            return True
        return False

    def _issue_match(self, text: str, pattern: re.Pattern[str]) -> bool:
        return any(not self._is_negated(text, match.start(), match.end()) for match in pattern.finditer(text))

    def classify(self, text: str) -> Classification:
        normalized = re.sub(r"\s+", "", str(text or "").strip())
        categories = [name for name, patterns in self._patterns.items() if any(self._issue_match(normalized, pattern) for pattern in patterns)]
        competitors = [name for name, pattern in self._competitor_patterns if pattern.search(normalized)]
        issue_categories = [category for category in categories if category != "竞品提及"]
        return Classification(categories=categories, competitors=competitors, is_negative=bool(issue_categories))
