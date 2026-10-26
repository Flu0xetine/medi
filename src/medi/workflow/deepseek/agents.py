"""基于共享 DeepSeek 客户端的提取与审核 Agent。"""

from __future__ import annotations

from typing import Any

from ..agents import ExtractionRequest, ReviewRequest
from ..state import ReviewResult
from .client import DeepSeekClient
from .prompts import (
    extraction_system_prompt,
    extraction_user_prompt,
    review_system_prompt,
    review_user_prompt,
)
from .validation import validate_review_result


class DeepSeekExtractor:
    """用 DeepSeek 从病历中提取规则引擎需要的完整事实表。"""

    def __init__(self, api: DeepSeekClient) -> None:
        self.api = api

    def __call__(self, request: ExtractionRequest) -> dict[str, Any]:
        """生成完整提取请求并解析 JSON 事实表。

        完整伪代码：
            从注册表构造系统字段契约
            附加原始病历、上一版事实和审核反馈（若有）
            调用共享客户端的 JSON 模式
            返回模型生成的完整事实表
        """

        return self.api.json_completion(
            extraction_system_prompt(), extraction_user_prompt(request)
        )


class DeepSeekReviewer:
    """用 DeepSeek 对照原始病历审核提取结果。"""

    def __init__(self, api: DeepSeekClient) -> None:
        self.api = api

    def __call__(self, request: ReviewRequest) -> ReviewResult:
        """请求审核并严格校验 approved/issue 结构。

        完整伪代码：
            构造与提取层共用字段契约的审核提示词
            将原始病历和完整事实表传给共享客户端
            校验审核 JSON 必须是结构正确的结论与问题列表
            返回已验证的审核结果
        """

        raw = self.api.json_completion(
            review_system_prompt(), review_user_prompt(request)
        )
        return validate_review_result(raw)


def create_deepseek_agents(
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[DeepSeekExtractor, DeepSeekReviewer]:
    """使用同一个 API 客户端创建真正的提取 Agent 和审核 Agent。"""

    api = DeepSeekClient(api_key=api_key, model=model)
    return DeepSeekExtractor(api), DeepSeekReviewer(api)
