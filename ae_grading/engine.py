"""规则引擎公开入口。"""

from __future__ import annotations

from .parser import parse_json_input
from .possibilities import classify_possible


def classify(payload: str) -> dict[str, object]:
    """接收LLM输出的JSON字符串，返回最终等级和是否带R。"""

    facts = parse_json_input(payload)
    return classify_possible(facts).to_dict()
