"""提取 Agent 与审核 Agent 的接口约定。

本模块不绑定某一家大模型。任何模型适配器只要实现这里的两个 Protocol，
就可以接入同一张 LangGraph 图；单元测试也可以使用简单的假 Agent。
"""

from __future__ import annotations

from typing import Any, Protocol, TypedDict

from .state import ReviewResult


class ExtractionRequest(TypedDict, total=False):
    """工作流传给提取 Agent 的信息。"""

    medical_record: str
    previous_facts: dict[str, Any]
    review_feedback: ReviewResult
    revision_count: int


class ReviewRequest(TypedDict):
    """工作流传给审核 Agent 的信息。"""

    medical_record: str
    extracted_facts: dict[str, Any]
    revision_count: int


class Extractor(Protocol):
    """提取 Agent 必须满足的调用接口。"""

    def __call__(self, request: ExtractionRequest) -> dict[str, Any]: ...


class Reviewer(Protocol):
    """审核 Agent 必须满足的调用接口。"""

    def __call__(self, request: ReviewRequest) -> ReviewResult: ...
