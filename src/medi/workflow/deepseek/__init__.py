"""DeepSeek 提取、审核适配器的公开入口。"""

from .agents import DeepSeekExtractor, DeepSeekReviewer, create_deepseek_agents
from .client import DEEPSEEK_BASE_URL, DEFAULT_MODEL, DeepSeekClient
from .prompts import FIELD_DESCRIPTIONS

__all__ = [
    "DEEPSEEK_BASE_URL",
    "DEFAULT_MODEL",
    "DeepSeekClient",
    "DeepSeekExtractor",
    "DeepSeekReviewer",
    "FIELD_DESCRIPTIONS",
    "create_deepseek_agents",
]
