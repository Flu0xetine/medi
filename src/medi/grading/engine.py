"""规则引擎公开入口。"""

from __future__ import annotations

from .decision_tree import serialize_paths
from .parser import parse_json_input
from .possibilities import classify_possible, classify_possible_with_paths


def classify(payload: str) -> dict[str, object]:
    """接收 LLM 输出的 JSON 字符串，返回全部可能分级结果。"""

    facts = parse_json_input(payload)
    return classify_possible(facts).to_dict()


def classify_with_trace(payload: str) -> dict[str, object]:
    """工作台专用：在原分类过程中记录可达路径与分支确定性。

    完整伪代码：
        按旧接口的同一 Schema 解析事实
        同一轮规则计算生成分类结果及原始路径
        根据完整路径集合标记每步确定/可能
        仅为本接口附加 paths，旧 classify 输出不改变
    """

    facts = parse_json_input(payload)
    results, paths = classify_possible_with_paths(facts)
    return {**results.to_dict(), "paths": serialize_paths(paths)}
