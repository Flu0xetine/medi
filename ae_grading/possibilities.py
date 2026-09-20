"""缺失事实的符号求值与可能分级聚合。

本模块不枚举所有原始字段排列。它先把每组规则压缩为规则真正关心的
布尔状态，再按分类优先级组合这些状态。这样六个 D2 指标全部缺失时，
D2 只产生 ``{False, True}``，而不是 64 个底层排列。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .models import ClassificationResult, ClassificationResults, ExtractedFacts


BoolSet = frozenset[bool]
FALSE_ONLY: BoolSet = frozenset((False,))
TRUE_ONLY: BoolSet = frozenset((True,))
EITHER: BoolSet = frozenset((False, True))

# 公开结果遵循 A 门控后 E → D → C → B；同一等级先显示不带 R，再显示带 R。
GRADE_ORDER = ("A", "E2", "E1", "D2", "D1", "C1", "C2", "C3", "B1", "B2")


def _predicate(
    facts: ExtractedFacts,
    name: str,
    test: Callable[[Any], bool],
) -> BoolSet:
    """返回一个原子条件的全部可能真值。"""

    value = facts.get(name)
    if value is None:
        return EITHER
    return TRUE_ONLY if test(value) else FALSE_ONLY


def _boolean(facts: ExtractedFacts, name: str) -> BoolSet:
    return _predicate(facts, name, lambda value: value is True)


def _or(conditions: Iterable[BoolSet]) -> BoolSet:
    """精确压缩彼此独立的 OR 条件，不生成各条件的排列。"""

    items = tuple(conditions)
    if any(item == TRUE_ONLY for item in items):
        return TRUE_ONLY
    if all(item == FALSE_ONLY for item in items):
        return FALSE_ONLY
    return EITHER


def _and(conditions: Iterable[BoolSet]) -> BoolSet:
    """精确压缩彼此独立的 AND 条件，不生成各条件的排列。"""

    items = tuple(conditions)
    if any(item == FALSE_ONLY for item in items):
        return FALSE_ONLY
    if all(item == TRUE_ONLY for item in items):
        return TRUE_ONLY
    return EITHER


def _not(condition: BoolSet) -> BoolSet:
    return frozenset(not value for value in condition)


def possible_d2(facts: ExtractedFacts) -> BoolSet:
    """计算 D2 的可能真值。

    完整伪代码：
        把六项指标分别转换为“条件真值集合”
        如果任意一项被明确判定为真：返回 {真}
        否则如果六项都被明确判定为假：返回 {假}
        否则：返回 {假, 真}
    """

    return _or(
        (
            _predicate(facts, "lactate_mmol_l", lambda value: value > 2),
            _boolean(facts, "acute_kidney_dysfunction"),
            _predicate(facts, "urine_output_ml_kg_h", lambda value: value < 0.5),
            _boolean(facts, "altered_mental_status"),
            _predicate(facts, "cardiac_index_l_min_m2", lambda value: value < 2.2),
            _predicate(facts, "mean_arterial_pressure_mmhg", lambda value: value < 60),
        )
    )


def possible_d1(facts: ExtractedFacts) -> BoolSet:
    """计算 D1 的可能真值，并保留同一血压条件在公式中的相关性。

    完整伪代码：
        求出六个原子条件各自可能的真值
        只枚举这六个规则原子，而不是枚举原始数值
        对每组原子值计算：
            绝对短暂低血压 = SBP低 AND 持续时间短
            相对短暂低血压 = 下降大 AND 持续时间短
            补液恢复路径 = (SBP低 OR 下降大) AND 补液恢复
            D1 = (三条路径任一成立) AND 明确无低灌注
        收集并返回不同的 D1 真值
    """

    sbp_low = _predicate(facts, "hypotension_systolic_bp_mmhg", lambda v: v < 90)
    sbp_short = _predicate(facts, "sbp_below_90_duration_minutes", lambda v: v < 15)
    drop_large = _predicate(facts, "systolic_bp_drop_mmhg", lambda v: v > 40)
    drop_short = _predicate(facts, "sbp_drop_gt_40_duration_minutes", lambda v: v < 15)
    fluid_recovery = _boolean(facts, "hypotension_resolved_after_fluid")
    no_hypoperfusion = _not(_boolean(facts, "hypoperfusion_or_end_organ_damage"))

    outcomes: set[bool] = set()
    for low in sbp_low:
        for low_short in sbp_short:
            for large in drop_large:
                for large_short in drop_short:
                    for recovered in fluid_recovery:
                        for no_damage in no_hypoperfusion:
                            absolute = low and low_short
                            relative = large and large_short
                            fluid_path = (low or large) and recovered
                            outcomes.add((absolute or relative or fluid_path) and no_damage)
    return frozenset(outcomes)


def possible_e2(facts: ExtractedFacts) -> BoolSet:
    refractory = _boolean(facts, "refractory_cardiogenic_shock")
    arrest_path = _and(
        (_boolean(facts, "cardiac_arrest"), _boolean(facts, "no_rosc_after_30_minutes"))
    )
    return _or((refractory, arrest_path))


def possible_e1(facts: ExtractedFacts) -> BoolSet:
    return _and(
        (
            _boolean(facts, "recurrent_or_persistent_hypotension"),
            _boolean(facts, "cardiogenic_shock"),
        )
    )


def possible_a(facts: ExtractedFacts) -> BoolSet:
    return _and((_boolean(facts, "incidental_finding"), _boolean(facts, "asymptomatic")))


def _other_spesi_positive(facts: ExtractedFacts) -> BoolSet:
    """计算除 SpO2 外五项 sPESI 是否至少一项阳性。"""

    return _or(
        (
            _predicate(facts, "age_years", lambda value: value > 80),
            _boolean(facts, "cancer_history"),
            _boolean(facts, "chronic_cardiopulmonary_disease"),
            _predicate(facts, "spesi_systolic_bp_mmhg", lambda value: value < 100),
            _predicate(facts, "heart_rate_bpm", lambda value: value >= 110),
        )
    )


def possible_spesi_and_c_r(facts: ExtractedFacts) -> frozenset[tuple[bool, bool]]:
    """联合计算 sPESI 阳性和 C 级 R，保留共享 SpO2 的相关性。

    完整伪代码：
        压缩 SpO2 以外的五项 sPESI 为“是否至少一项阳性”
        压缩呼吸频率和吸氧为“其他 C-R 条件是否阳性”
        枚举上述两个状态和 SpO2<90 状态（最多 2×2×2）
        对每组状态同时计算 sPESI是否阳性、C-R是否阳性
        去重后返回联合结果
    """

    other_spesi = _other_spesi_positive(facts)
    spo2_low = _predicate(facts, "spo2_percent", lambda value: value < 90)
    other_r = _or(
        (
            _predicate(facts, "respiratory_rate_bpm", lambda value: value >= 30),
            _boolean(facts, "oxygen_required"),
        )
    )
    return frozenset(
        (other_score or low, low or respiratory)
        for other_score in other_spesi
        for low in spo2_low
        for respiratory in other_r
    )


def possible_c_grades(facts: ExtractedFacts) -> frozenset[str]:
    rv = _boolean(facts, "rv_abnormal")
    biomarker = _boolean(facts, "cardiac_biomarker_abnormal")
    grades: set[str] = set()
    for rv_value in rv:
        for biomarker_value in biomarker:
            grades.add("C3" if rv_value and biomarker_value else "C2" if rv_value or biomarker_value else "C1")
    return frozenset(grades)


def possible_b_grades(facts: ExtractedFacts) -> frozenset[str]:
    location = facts.get("highest_thrombus_location")
    if location == "subsegmental_only":
        return frozenset(("B1",))
    if location == "non_subsegmental":
        return frozenset(("B2",))
    return frozenset(("B1", "B2"))


def _possible_r(facts: ExtractedFacts, grade_family: str) -> BoolSet:
    if grade_family == "D":
        return _or(
            (
                _predicate(facts, "nasal_cannula_flow_l_min", lambda value: value > 6),
                _boolean(facts, "face_mask_oxygen"),
            )
        )
    if grade_family == "E":
        return _or(
            (
                _boolean(facts, "noninvasive_ventilation"),
                _boolean(facts, "invasive_mechanical_ventilation"),
            )
        )
    return FALSE_ONLY


def classify_possible(facts: ExtractedFacts) -> ClassificationResults:
    """按优先级返回所有可区分的最终输出。

    完整伪代码：
        results = 空集合
        先计算A：
            如果A可能成立：加入A
            只有A可能不成立时，BCDE才可达
        如果EDCB可达，依次处理 E2、E1、D2、D1：
            如果低优先级仍可能到达且当前条件可能为真：加入当前等级的R可能结果
            只有当前条件可能为假时，低优先级才继续可达
        如果 B/C 层仍可达：
            联合求值 sPESI阳性与C-R，避免拆散共享的SpO2
            sPESI阴性时加入所有可能B子级
            sPESI阳性时加入所有可能C子级及对应R状态
        按固定等级顺序和has_r排序，返回去重结果
    """

    results: set[ClassificationResult] = set()
    a_condition = possible_a(facts)
    if True in a_condition:
        results.add(ClassificationResult("A", False))

    # A 与 EDCB 互斥：只有 A 存在“不成立”路径时才继续后续分级。
    lower_reachable = False in a_condition
    priority_conditions = (
        ("E2", possible_e2(facts)),
        ("E1", possible_e1(facts)),
        ("D2", possible_d2(facts)),
        ("D1", possible_d1(facts)),
    )
    for grade, condition in priority_conditions:
        if not lower_reachable:
            break
        if True in condition:
            for has_r in _possible_r(facts, grade[0]):
                results.add(ClassificationResult(grade, has_r))
        lower_reachable = False in condition

    if lower_reachable:
        joint_states = possible_spesi_and_c_r(facts)
        if any(not spesi_positive for spesi_positive, _ in joint_states):
            for grade in possible_b_grades(facts):
                results.add(ClassificationResult(grade, False))
        c_r_values = {has_r for spesi_positive, has_r in joint_states if spesi_positive}
        for grade in possible_c_grades(facts):
            for has_r in c_r_values:
                results.add(ClassificationResult(grade, has_r))

    order = {grade: index for index, grade in enumerate(GRADE_ORDER)}
    sorted_results = tuple(sorted(results, key=lambda item: (order[item.grade], item.has_r)))
    return ClassificationResults(sorted_results)
