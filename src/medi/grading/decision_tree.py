"""规则判断树及与分级求值同源的路径表示。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import dataclass


GRADE_ORDER = ("A", "E2", "E1", "D2", "D1", "D0", "C1", "C2", "C3", "B1", "B2")


@dataclass(frozen=True)
class DecisionStep:
    node: str
    outcome: str


@dataclass(frozen=True)
class DecisionPath:
    grade: str
    has_r: bool
    steps: tuple[DecisionStep, ...]


def _leaf(grade: str, has_r: bool = False) -> dict:
    return {
        "label": f"{grade}{'-R' if has_r else ''}",
        "result": {"grade": grade, "has_r": has_r},
    }


def _decision(node_id: str, label: str, *branches: tuple[str, str, dict]) -> dict:
    return {
        "id": node_id,
        "label": label,
        "branches": [
            {"outcome": outcome, "label": branch_label, "child": child}
            for outcome, branch_label, child in branches
        ],
    }


def _r_decision(grade: str, family: str) -> dict:
    conditions = {
        "e": "E-R｜有创或无创机械通气",
        "d": "D-R｜鼻导管流量 >6 L/min 或面罩吸氧",
        "c": "C-R｜SpO₂ <90%、呼吸频率 ≥30 次/分或需要吸氧",
    }
    return _decision(
        f"{family}_r", conditions[family],
        ("yes", "是", _leaf(grade, True)),
        ("no", "否", _leaf(grade)),
    )


def _build_tree() -> dict:
    """自叶向根构造现行判断树，重复叶子保留不同的真实入口。

    完整伪代码：
        先建立 C、B 子级和各等级的 R 判断叶子
        PESI>=85 指向 C 状态，否则指向血栓位置
        H=false 时按低灌注分流至 D2 或 PESI
        H=true 时按低灌注分流至 E1/D2 或 D1候选/D0
        D1候选先检查恢复后复发，复发则 D0，否则进入 D1 的 R 判断
        在根部按 A、E2 优先判断，任一成立便不再进入下级
    """

    c_status = _decision(
        "c_status", "RV 与心脏生物标志物状态",
        ("C1", "均正常", _r_decision("C1", "c")),
        ("C2", "仅一类异常", _r_decision("C2", "c")),
        ("C3", "均异常", _r_decision("C3", "c")),
    )
    b_location = _decision(
        "b_location", "最高血栓位置",
        ("B1", "仅亚段", _leaf("B1")),
        ("B2", "存在非亚段", _leaf("B2")),
    )
    pesi = _decision(
        "pesi", "PESI ≥85",
        ("yes", "是", c_status),
        ("no", "否", b_location),
    )
    perfusion_without_h = _decision(
        "l_no_h", "低灌注",
        ("yes", "是", _r_decision("D2", "d")),
        ("no", "否", pesi),
    )
    relapse = _decision(
        "relapse", "低血压恢复后复发",
        ("yes", "是", _leaf("D0")),
        ("no", "否", _r_decision("D1", "d")),
    )
    transient = _decision(
        "transient_or_recovered", "低血压短暂（<15 分钟）或已恢复",
        ("yes", "是", relapse),
        ("no", "否", _leaf("D0")),
    )
    recurrent = _decision(
        "recurrent", "低血压反复或持续",
        ("yes", "是", _r_decision("E1", "e")),
        ("no", "否", _r_decision("D2", "d")),
    )
    perfusion_with_h = _decision(
        "l_h", "低灌注",
        ("yes", "是", recurrent),
        ("no", "否", transient),
    )
    hypotension = _decision(
        "h", "低血压：收缩压 <90 mmHg、下降 >40 mmHg、使用升压药或补液",
        ("yes", "是", perfusion_with_h),
        ("no", "否", perfusion_without_h),
    )
    e2 = _decision(
        "e2", "难治性心源性休克或心脏骤停经 30 分钟复苏仍无自主循环",
        ("yes", "是", _r_decision("E2", "e")),
        ("no", "否", hypotension),
    )
    return _decision(
        "a", "偶然发现且无症状",
        ("yes", "是", _leaf("A")),
        ("no", "否", e2),
    )


_TREE = _build_tree()


def rule_tree() -> dict[str, object]:
    """返回独立副本，避免外部修改全局树定义。"""

    return deepcopy(_TREE)


def resolve_path(path: DecisionPath) -> tuple[str, bool]:
    """逐步验证路径确实抵达与声明等级相同的叶子。

    完整伪代码：
        从根节点开始遍历步骤
        每一步须匹配当前判断节点 ID 和它的一个出口
        跳到该出口的子节点；遇到叶子后不可再有步骤
        步骤结束时必须已到叶子，且等级和 R 与路径声明完全一致
    """

    node = _TREE
    for step in path.steps:
        if node.get("id") != step.node:
            raise ValueError(f"路径节点不匹配：{step.node}")
        branch = next((item for item in node["branches"] if item["outcome"] == step.outcome), None)
        if branch is None:
            raise ValueError(f"路径分支不存在：{step.node}/{step.outcome}")
        node = branch["child"]
    result = node.get("result")
    if result is None or (result["grade"], result["has_r"]) != (path.grade, path.has_r):
        raise ValueError("路径终点与分级结果不一致")
    return path.grade, path.has_r


def serialize_paths(paths: Iterable[DecisionPath]) -> list[dict[str, object]]:
    """按完整路径集合标注条件确定性，不受页面当前筛选影响。

    完整伪代码：
        去重并验证每条路径在静态树上确实存在
        按等级、R、判断序列稳定排序
        对每条路径的每一步，以“此前所有步骤 + 当前节点”为键
        统计这一前缀下全部可达出口
        出口只有一个则该步确定，否则该步可能
        全部步骤确定时整条路径才确定；序列化供页面直接着色
    """

    unique = set(paths)
    for path in unique:
        resolve_path(path)
    ordered = sorted(unique, key=lambda path: (
        GRADE_ORDER.index(path.grade), path.has_r,
        tuple((step.node, step.outcome) for step in path.steps),
    ))
    outcomes: dict[tuple[tuple[DecisionStep, ...], str], set[str]] = defaultdict(set)
    for path in ordered:
        for index, step in enumerate(path.steps):
            outcomes[(path.steps[:index], step.node)].add(step.outcome)

    serialized = []
    for path in ordered:
        steps = []
        for index, step in enumerate(path.steps):
            certainty = "certain" if len(outcomes[(path.steps[:index], step.node)]) == 1 else "possible"
            steps.append({"node": step.node, "outcome": step.outcome, "certainty": certainty})
        serialized.append({
            "grade": path.grade,
            "has_r": path.has_r,
            "certainty": "certain" if all(step["certainty"] == "certain" for step in steps) else "possible",
            "steps": steps,
        })
    return serialized
