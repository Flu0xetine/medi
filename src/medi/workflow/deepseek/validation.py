"""审核 Agent JSON 的独立运行时校验。"""

from __future__ import annotations

from typing import Any, cast

from ..state import ReviewIssue, ReviewResult


def validate_review_result(raw: dict[str, Any]) -> ReviewResult:
    """不用 Pydantic，对审核 Agent 的关键输出做最小运行时检查。"""

    if set(raw) != {"approved", "issues"}:
        raise ValueError("审核结果必须且只能包含approved和issues")
    if not isinstance(raw["approved"], bool):
        raise ValueError("审核结果approved必须是boolean")
    if not isinstance(raw["issues"], list):
        raise ValueError("审核结果issues必须是数组")

    required_issue_fields = {"field", "issue_type", "reason", "suggestion"}
    issues: list[ReviewIssue] = []
    for index, issue in enumerate(raw["issues"]):
        if not isinstance(issue, dict) or set(issue) != required_issue_fields:
            raise ValueError(f"审核问题第{index + 1}项结构不正确")
        if not all(isinstance(issue[name], str) for name in required_issue_fields):
            raise ValueError(f"审核问题第{index + 1}项的所有字段必须是字符串")
        issues.append(cast(ReviewIssue, issue))

    if raw["approved"] and issues:
        raise ValueError("审核通过时issues必须为空")
    if not raw["approved"] and not issues:
        raise ValueError("审核不通过时issues不能为空")
    return {"approved": raw["approved"], "issues": issues}
