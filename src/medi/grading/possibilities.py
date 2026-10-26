"""按新流程求所有可达分级；OR 指标按条件状态压缩，而非枚举原始排列。"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from math import inf
from typing import Any

from .decision_tree import DecisionPath, DecisionStep, GRADE_ORDER
from .models import ClassificationResult, ClassificationResults, ExtractedFacts
from .pesi import possible_pesi_and_c_r


BoolSet = frozenset[bool]
FALSE_ONLY: BoolSet = frozenset((False,))
TRUE_ONLY: BoolSet = frozenset((True,))
EITHER: BoolSet = frozenset((False, True))
Steps = tuple[DecisionStep, ...]


@dataclass(frozen=True)
class _SystolicCase:
    """同一收缩压在低血压、MAP 和 PESI 中的一致状态。"""

    below_90: bool
    below_100: bool
    lower: float
    upper: float
    exact: bool = False


def _systolic_cases(facts: ExtractedFacts) -> tuple[_SystolicCase, ...]:
    """按 90、100 mmHg 两个规则边界压缩缺失收缩压。

    完整伪代码：
        若收缩压已知，只保留它所在的一个状态
        若收缩压缺失，分成 <90、[90,100)、>=100 三段
        每段同时固定低血压条件和 PESI 加分条件
        不在不同规则中重新独立假设同一个收缩压
    """

    value = facts.get("systolic_bp_mmhg")
    if value is not None:
        return (_SystolicCase(value < 90, value < 100, value, value, True),)
    return (
        _SystolicCase(True, True, -inf, 90),
        _SystolicCase(False, True, 90, 100),
        _SystolicCase(False, False, 100, inf),
    )


def _map_below_60_states(facts: ExtractedFacts, systolic: _SystolicCase) -> BoolSet:
    """按同次 SBP/DBP 计算 MAP<60 的可达状态。

    完整伪代码：
        MAP = (SBP + 2*DBP)/3；与60比较等价于SBP+2*DBP<180
        DBP缺失时保留真假两种可能
        SBP已知时直接计算单一真值
        SBP缺失时，比较该SBP区间与阈值(180-2*DBP)
        整段低于阈值则只可能为真；整段不低于则只可能为假
        阈值落在区间内部则保留真假，不枚举每个血压数值
    """

    diastolic = facts.get("diastolic_bp_mmhg")
    if diastolic is None:
        return EITHER
    if systolic.exact:
        return TRUE_ONLY if systolic.lower + 2 * diastolic < 180 else FALSE_ONLY
    cutoff = 180 - 2 * diastolic
    if cutoff <= systolic.lower:
        return FALSE_ONLY
    if cutoff >= systolic.upper:
        return TRUE_ONLY
    return EITHER


def _predicate(facts: ExtractedFacts, name: str, test: Callable[[Any], bool]) -> BoolSet:
    """已知事实给出单一真值；缺失事实保留真、假两个可能。"""

    value = facts.get(name)
    return EITHER if value is None else TRUE_ONLY if test(value) else FALSE_ONLY


def _boolean(facts: ExtractedFacts, name: str) -> BoolSet:
    return _predicate(facts, name, lambda value: value is True)


def _or(conditions: Iterable[BoolSet]) -> BoolSet:
    """把独立 OR 指标压缩成至多两个条件状态。"""

    items = tuple(conditions)
    if any(item == TRUE_ONLY for item in items):
        return TRUE_ONLY
    return FALSE_ONLY if all(item == FALSE_ONLY for item in items) else EITHER


def _and(conditions: Iterable[BoolSet]) -> BoolSet:
    items = tuple(conditions)
    if any(item == FALSE_ONLY for item in items):
        return FALSE_ONLY
    return TRUE_ONLY if all(item == TRUE_ONLY for item in items) else EITHER


def _r_states(facts: ExtractedFacts, family: str) -> BoolSet:
    """A、B、D0 固定无 R；其余家族按各自条件计算。"""

    if family == "D":
        return _or((
            _boolean(facts, "nasal_cannula_over_6_l_min"),
            _boolean(facts, "face_mask_oxygen"),
        ))
    if family == "E":
        return _or((
            _boolean(facts, "noninvasive_ventilation"),
            _boolean(facts, "invasive_mechanical_ventilation"),
        ))
    return FALSE_ONLY


def _step(steps: Steps, node: str, outcome: str) -> Steps:
    return (*steps, DecisionStep(node, outcome))


def _add(
    results: set[ClassificationResult], grade: str, r_states: BoolSet,
    *, paths: set[DecisionPath] | None = None, steps: Steps = (), r_node: str | None = None,
) -> None:
    """同一次求值同时加入结果与可选路径；R 的真假作为末端判断。"""

    for has_r in r_states:
        results.add(ClassificationResult(grade=grade, has_r=has_r))
        if paths is not None:
            route = _step(steps, r_node, "yes" if has_r else "no") if r_node else steps
            paths.add(DecisionPath(grade=grade, has_r=has_r, steps=route))


def _c_grades(facts: ExtractedFacts) -> frozenset[str]:
    grades = set()
    for rv in _boolean(facts, "rv_abnormal"):
        for biomarker in _boolean(facts, "cardiac_biomarker_abnormal"):
            grades.add("C3" if rv and biomarker else "C2" if rv or biomarker else "C1")
    return frozenset(grades)


def _b_grades(facts: ExtractedFacts) -> frozenset[str]:
    location = facts.get("highest_thrombus_location")
    if location == "subsegmental_only":
        return frozenset(("B1",))
    if location == "non_subsegmental":
        return frozenset(("B2",))
    return frozenset(("B1", "B2"))


def _transient_states(
    facts: ExtractedFacts, *, sbp_low: bool, drop_large: bool
) -> BoolSet:
    """求已命中血压数值阈值时的“低血压短暂”。

    完整伪代码：
        至少一个血压数值阈值须成立，否则无法据现有时间字段证明短暂
        对每个已成立阈值读取对应持续时间是否小于15分钟
        暂按两个阈值均成立时两段时间都小于15分钟解释“短暂”
        必要事实缺失时保留真、假，不把缺失当作正常
    """

    if not (sbp_low or drop_large):
        return FALSE_ONLY
    durations = []
    if sbp_low:
        durations.append(_predicate(facts, "sbp_below_90_duration_minutes", lambda v: v < 15))
    if drop_large:
        durations.append(_predicate(facts, "sbp_drop_gt_40_duration_minutes", lambda v: v < 15))
    return _and(durations)


def _add_d1_or_d0(
    results: set[ClassificationResult],
    facts: ExtractedFacts,
    candidate_states: BoolSet,
    relapse_states: BoolSet,
    *, paths: set[DecisionPath] | None = None, steps: Steps = (),
) -> None:
    """在既有短暂／可恢复条件之后，排除恢复后复发的 D1 候选。

    完整伪代码：
        若短暂或可恢复条件可能为假，加入 D0，R 固定为假
        若该条件可能为真，再查看恢复后复发事实
        若复发可能为真，加入 D0，R 固定为假
        若复发可能为假，加入 D1，并按 D-R 计算 R
        任一事实缺失时保留对应可达结果，最终由结果集合去重
    """

    if False in candidate_states:
        _add(results, "D0", FALSE_ONLY, paths=paths,
             steps=_step(steps, "transient_or_recovered", "no"))
    if True in candidate_states:
        candidate_route = _step(steps, "transient_or_recovered", "yes")
        if True in relapse_states:
            _add(results, "D0", FALSE_ONLY, paths=paths,
                 steps=_step(candidate_route, "relapse", "yes"))
        if False in relapse_states:
            _add(results, "D1", _r_states(facts, "D"), paths=paths,
                 steps=_step(candidate_route, "relapse", "no"), r_node="d_r")


def _add_pesi_branch(
    results: set[ClassificationResult], facts: ExtractedFacts, *, systolic_below_100: bool,
    paths: set[DecisionPath] | None = None, steps: Steps = (),
) -> None:
    """低灌注为假时，联合求 PESI 与共享字段所决定的 C-R。"""

    for high, has_r in possible_pesi_and_c_r(
        facts, systolic_below_100=systolic_below_100
    ):
        grades = _c_grades(facts) if high else _b_grades(facts)
        for grade in grades:
            route = _step(_step(steps, "pesi", "yes" if high else "no"),
                          "c_status" if high else "b_location", grade)
            _add(results, grade, frozenset((has_r,)) if high else FALSE_ONLY,
                 paths=paths, steps=route, r_node="c_r" if high else None)


def _sorted(results: set[ClassificationResult]) -> ClassificationResults:
    order = {grade: index for index, grade in enumerate(GRADE_ORDER)}
    return ClassificationResults(results=tuple(sorted(
        results, key=lambda item: (order[item.grade], item.has_r)
    )))


def _classify(
    facts: ExtractedFacts, *, collect_paths: bool,
) -> tuple[ClassificationResults, tuple[DecisionPath, ...]]:
    """按 A → E2 → 低血压 → 低灌注 → D/E/PESI 求去重结果。

    完整伪代码：
        若A可能成立则加入A；仅A可能不成立时进入其余分级
        若E2可能成立则加入E2；仅E2可能不成立时继续
        按90、100两个边界枚举同一收缩压的至多三个区间
        对每个区间与舒张压计算MAP<60，并固定PESI血压加分
        再枚举“SBP下降大”的真假；与升压药、补液合成低血压OR
        将乳酸、MAP、急性肾功能不全、四肢湿冷压缩成一个OR状态
        单独枚举精神状态，以保持它与PESI的同一取值
        低血压真、低灌注真：低血压反复/持续则E1，否则D2
        低血压真、低灌注假：先判断短暂或已恢复，候选D1再以恢复后复发排除
        候选D1若复发则D0；未复发则D1；复发缺失则保留两种结果
        低血压假、低灌注真：D2
        低血压假、低灌注假：PESI>=85进C，否则进B
        各级求对应R；D0的R恒假；最后去重排序

    五个低灌注指标全缺失时，不展开32种原始排列。
    """

    results: set[ClassificationResult] = set()
    paths: set[DecisionPath] | None = set() if collect_paths else None
    a = _and((_boolean(facts, "incidental_finding"), _boolean(facts, "asymptomatic")))
    if True in a:
        _add(results, "A", FALSE_ONLY, paths=paths, steps=(DecisionStep("a", "yes"),))
    if False not in a:
        return _sorted(results), tuple(paths or ())

    e2 = _or((
        _boolean(facts, "refractory_cardiogenic_shock"),
        _boolean(facts, "no_rosc_after_30_minutes"),
    ))
    if True in e2:
        _add(results, "E2", _r_states(facts, "E"), paths=paths,
             steps=(DecisionStep("a", "no"), DecisionStep("e2", "yes")), r_node="e_r")
    if False not in e2:
        return _sorted(results), tuple(paths or ())

    drop_states = _predicate(facts, "systolic_bp_drop_mmhg", lambda v: v > 40)
    treatment = _or((_boolean(facts, "vasopressor_used"), _boolean(facts, "fluid_treatment_given")))
    other_perfusion = _or((
        _predicate(facts, "lactate_mmol_l", lambda v: v > 2),
        _boolean(facts, "acute_kidney_dysfunction"),
        _boolean(facts, "cold_clammy_extremities"),
    ))
    recurrence = _boolean(facts, "recurrent_or_persistent_hypotension")
    relapse_after_recovery = _boolean(facts, "hypotension_recurred_after_recovery")
    mental_states = _boolean(facts, "altered_mental_status")
    start: Steps = (DecisionStep("a", "no"), DecisionStep("e2", "no"))

    for systolic in _systolic_cases(facts):
        sbp_low = systolic.below_90
        perfusion_without_mental = _or((other_perfusion, _map_below_60_states(facts, systolic)))
        for drop_large in drop_states:
            hypotension = TRUE_ONLY if sbp_low or drop_large else treatment
            for mental in mental_states:
                perfusion = _or((perfusion_without_mental, TRUE_ONLY if mental else FALSE_ONLY))
                for branch_is_true in hypotension:
                    for low_perfusion in perfusion:
                        route = _step(start, "h", "yes" if branch_is_true else "no")
                        route = _step(route, "l_h" if branch_is_true else "l_no_h",
                                      "yes" if low_perfusion else "no")
                        if branch_is_true and low_perfusion:
                            if True in recurrence:
                                _add(results, "E1", _r_states(facts, "E"), paths=paths,
                                     steps=_step(route, "recurrent", "yes"), r_node="e_r")
                            if False in recurrence:
                                _add(results, "D2", _r_states(facts, "D"), paths=paths,
                                     steps=_step(route, "recurrent", "no"), r_node="d_r")
                        elif branch_is_true:
                            d1_candidate = _or((
                                _transient_states(facts, sbp_low=sbp_low, drop_large=drop_large),
                                _boolean(facts, "hypotension_recovered"),
                            ))
                            _add_d1_or_d0(results, facts, d1_candidate, relapse_after_recovery,
                                          paths=paths, steps=route)
                        elif low_perfusion:
                            _add(results, "D2", _r_states(facts, "D"), paths=paths,
                                 steps=route, r_node="d_r")
                        else:
                            # 低灌注为假时精神状态必为假，PESI据此固定该项0分。
                            _add_pesi_branch(
                                results, facts, systolic_below_100=systolic.below_100,
                                paths=paths, steps=route,
                            )
    return _sorted(results), tuple(paths or ())


def classify_possible(facts: ExtractedFacts) -> ClassificationResults:
    """保持旧公开契约：仅返回去重后的分级集合。"""

    return _classify(facts, collect_paths=False)[0]


def classify_possible_with_paths(
    facts: ExtractedFacts,
) -> tuple[ClassificationResults, tuple[DecisionPath, ...]]:
    """与等级在同一次求值中收集路径，不从结果倒推判断过程。"""

    return _classify(facts, collect_paths=True)
