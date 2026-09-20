"""LangGraph 工作流共享状态的数据结构。

这里使用 TypedDict 描述 State，不引入 Pydantic。TypedDict 帮助编辑器和开发者
理解字段含义；规则引擎已有的 parser.py 仍负责运行时输入校验。
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict


class ReviewIssue(TypedDict):
    """审核 Agent 发现的一个提取问题。"""

    field: str
    issue_type: str
    reason: str
    suggestion: str


class ReviewResult(TypedDict):
    """审核 Agent 的结构化输出。"""

    approved: bool
    issues: list[ReviewIssue]


class PossibleResult(TypedDict):
    """规则引擎产生的一个可能结果。"""

    grade: str
    has_r: bool


class ClassificationResult(TypedDict):
    """规则引擎 2.0 的完整公开结果。"""

    results: list[PossibleResult]


class CompletedOutput(ClassificationResult):
    """整个工作流成功时的最终输出。"""

    status: Literal["completed"]


class ErrorOutput(TypedDict):
    """规则引擎报错时的最终输出。"""

    status: Literal["error"]
    error: str


class WorkflowState(TypedDict, total=False):
    """整张图中由所有节点共享的数据。

    total=False 表示创建初始 State 时不必提供所有字段。中间字段会在节点运行后
    逐步出现。没有声明 Reducer 的字段使用 LangGraph 的默认覆盖行为。
    """

    medical_record: str
    extracted_facts: dict[str, Any]
    review_result: ReviewResult
    revision_count: int

    # 审核节点计算这个临时路由标记。把计数和是否重试放在同一个节点中，
    # 可以避免再创建一个单独的“计次节点”。
    retry_extraction: bool

    engine_result: ClassificationResult
    engine_error: str | None
    final_output: CompletedOutput | ErrorOutput
