"""病历提取、审核和确定性分级的 LangGraph 图。"""

from __future__ import annotations

import json
from typing import Literal, cast

from langgraph.graph import END, START, StateGraph

from medi.grading import classify

from .agents import ExtractionRequest, Extractor, ReviewRequest, Reviewer
from .state import (
    ClassificationResult,
    CompletedOutput,
    ErrorOutput,
    ReviewResult,
    WorkflowState,
)


# “首次提取”不计入修正次数。审核不通过后最多允许三次修正。
MAX_REVISIONS = 3


def build_grading_graph(extractor: Extractor, reviewer: Reviewer):
    """创建并编译分级工作流。

    extractor 和 reviewer 从外部传入，使图不依赖具体大模型供应商。
    """

    def extract_node(state: WorkflowState) -> dict:
        """调用提取 Agent，保存一份新的完整事实表。

        伪代码：
            如果是首次提取：
                传入原始病历
            否则：
                传入原始病历、上一版事实和审核意见
            调用提取 Agent
            用新完整事实表覆盖 extracted_facts
        """

        request: ExtractionRequest = {
            "medical_record": state["medical_record"],
            "revision_count": state.get("revision_count", 0),
        }
        if "extracted_facts" in state:
            request["previous_facts"] = state["extracted_facts"]
        if "review_result" in state:
            request["review_feedback"] = state["review_result"]

        return {"extracted_facts": extractor(request)}

    def review_node(state: WorkflowState) -> dict:
        """审核事实表，并在需要时直接增加修正次数。

        伪代码：
            审核 Agent 对照原始病历检查最新事实表
            如果审核不通过且修正次数小于3：
                修正次数加1
                标记需要返回提取 Agent
            否则：
                标记进入规则引擎
        """

        current_count = state.get("revision_count", 0)
        review = reviewer(
            ReviewRequest(
                medical_record=state["medical_record"],
                extracted_facts=state["extracted_facts"],
                revision_count=current_count,
            )
        )

        should_retry = not review["approved"] and current_count < MAX_REVISIONS
        next_count = current_count + 1 if should_retry else current_count

        return {
            "review_result": review,
            "revision_count": next_count,
            "retry_extraction": should_retry,
        }

    def route_after_review(
        state: WorkflowState,
    ) -> Literal["extract", "engine"]:
        """根据审核节点写入的标记选择修正或计算。

        伪代码：
            如果需要修正：返回提取 Agent
            否则：进入规则引擎
        """

        return "extract" if state["retry_extraction"] else "engine"

    def engine_node(state: WorkflowState) -> dict:
        """调用现有规则引擎；失败时直接保存错误原因。

        伪代码：
            把最新事实表转换为JSON字符串
            尝试调用规则引擎
            如果成功：保存全部可能结果，最终状态为completed
            如果报错：保存错误原因，最终状态为error

        无论最后一次审核是否通过，只要规则引擎成功，就直接输出计算结果。
        """

        try:
            payload = json.dumps(state["extracted_facts"], ensure_ascii=False)
            result = cast(ClassificationResult, classify(payload))
            final_output: CompletedOutput = {
                "status": "completed",
                "results": result["results"],
            }
            return {
                "engine_result": result,
                "engine_error": None,
                "final_output": final_output,
            }
        except (TypeError, ValueError) as exc:
            error_message = str(exc)
            error_output: ErrorOutput = {
                "status": "error",
                "error": error_message,
            }
            return {
                "engine_error": error_message,
                "final_output": error_output,
            }

    builder = StateGraph(WorkflowState)
    builder.add_node("extract", extract_node)
    builder.add_node("review", review_node)
    builder.add_node("engine", engine_node)

    builder.add_edge(START, "extract")
    builder.add_edge("extract", "review")
    builder.add_conditional_edges("review", route_after_review)
    builder.add_edge("engine", END)

    return builder.compile()


def grade_medical_record(
    medical_record: str,
    extractor: Extractor,
    reviewer: Reviewer,
) -> CompletedOutput | ErrorOutput:
    """运行完整工作流并只返回对外结果。

    伪代码：
        用病历和revision_count=0创建初始State
        调用编译后的图
        图结束后返回final_output
    """

    graph = build_grading_graph(extractor, reviewer)
    final_state = graph.invoke(
        {
            "medical_record": medical_record,
            "revision_count": 0,
        }
    )
    return final_state["final_output"]


def analyze_medical_record(
    medical_record: str,
    extractor: Extractor,
    reviewer: Reviewer,
) -> dict:
    """运行工作流并额外返回医生可核对、可编辑的事实与审核意见。

    完整伪代码：
        验证病历非空
        执行既有提取、审核、规则引擎图
        从最终状态读取原有输出、事实表和审核意见
        返回三者；不修改 grade_medical_record 的公开输出
    """

    if not isinstance(medical_record, str) or not medical_record.strip():
        raise ValueError("病历内容不能为空")
    final_state = build_grading_graph(extractor, reviewer).invoke(
        {"medical_record": medical_record, "revision_count": 0}
    )
    return {
        **final_state["final_output"],
        "facts": final_state["extracted_facts"],
        "review": final_state["review_result"],
    }
