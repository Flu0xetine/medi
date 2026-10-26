"""PESI 加权评分及其与 C-R 的联合求值。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import inf

from .models import ExtractedFacts


@dataclass(frozen=True)
class ScoreItem:
    """一个 PESI 加分项；年龄按原始岁数单独累加。"""

    field: str
    points: int
    positive: Callable[[object], bool]


SCORE_ITEMS = (
    ScoreItem("male_sex", 10, lambda v: v is True),
    ScoreItem("cancer_history", 30, lambda v: v is True),
    ScoreItem("heart_failure_history", 10, lambda v: v is True),
    ScoreItem("chronic_lung_disease", 10, lambda v: v is True),
    ScoreItem("heart_rate_bpm", 20, lambda v: v >= 110),
    ScoreItem("systolic_bp_mmhg", 30, lambda v: v < 100),
    ScoreItem("respiratory_rate_bpm", 20, lambda v: v >= 30),
    ScoreItem("body_temperature_c", 20, lambda v: v < 36),
    ScoreItem("altered_mental_status", 60, lambda v: v is True),
    ScoreItem("spo2_percent", 20, lambda v: v < 90),
)
SHARED_R_FIELDS = frozenset(("spo2_percent", "respiratory_rate_bpm"))


def score_bounds(
    facts: ExtractedFacts,
    *,
    conditions: dict[str, bool] | None = None,
) -> tuple[float, float]:
    """返回 PESI 可达的最小、最大分数；完整输入时两者相同。

    完整伪代码：
        年龄已知：上下界均从实际年龄开始
        年龄缺失：下界从0开始，上界为无穷（未规定年龄上限）
        对每个加分项：
            若调用方固定了该条件：按固定真值加分
            否则已知事实按阈值确定；缺失事实保留假、真
            下界累加最小贡献，上界累加最大贡献
        返回上下界
    调用方只能传入与已知事实一致的条件，用于共享字段分支约束。
    """

    conditions = conditions or {}
    age = facts.get("age_years")
    minimum, maximum = (0, inf) if age is None else (age, age)
    for item in SCORE_ITEMS:
        value = facts.get(item.field)
        states = (
            (conditions[item.field],)
            if item.field in conditions
            else (False, True) if value is None else (item.positive(value),)
        )
        minimum += item.points * min(states)
        maximum += item.points * max(states)
    return minimum, maximum


def possible_pesi_and_c_r(
    facts: ExtractedFacts, *, systolic_below_100: bool
) -> frozenset[tuple[bool, bool]]:
    """返回 (PESI>=85, C-R成立) 的可达组合；仅在低灌注=false路径调用。

    完整伪代码：
        低灌注未命中意味着精神状态改变为假，在本路径固定该项为0分
        同一收缩压还用于低血压和MAP；使用调用方已选定的SBP区间
        分别取得SpO2<90、RR>=30、需要吸氧的可能真值
        枚举这三个共享条件的小规模组合（最多8组）
        每组使用相同SpO2/RR状态计算PESI上下界和C-R
        最小分数<85：B可达；最大分数>=85：C可达
        收集联合状态并去重

    其余加分项均为非负独立贡献，上下界可达，足以精确判断85分两侧；
    不需要枚举所有评分项排列。精神状态为真已由低灌注截获。
    """

    if facts.get("altered_mental_status") is True:
        raise ValueError("PESI分类分支要求低灌注不成立")
    shared_items = [item for item in SCORE_ITEMS if item.field in SHARED_R_FIELDS]
    domains = {}
    for item in shared_items:
        value = facts.get(item.field)
        domains[item.field] = (False, True) if value is None else (item.positive(value),)
    oxygen = facts.get("oxygen_required")
    oxygen_states = (False, True) if oxygen is None else (oxygen,)
    results = set()
    for low in domains["spo2_percent"]:
        for rapid in domains["respiratory_rate_bpm"]:
            minimum, maximum = score_bounds(facts, conditions={
                "spo2_percent": low,
                "respiratory_rate_bpm": rapid,
                "altered_mental_status": False,
                "systolic_bp_mmhg": systolic_below_100,
            })
            for required in oxygen_states:
                has_r = low or rapid or required
                if minimum < 85:
                    results.add((False, has_r))
                if maximum >= 85:
                    results.add((True, has_r))
    return frozenset(results)
