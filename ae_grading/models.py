"""规则引擎内部使用的简单数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Fact:
    """LLM从病历中提取的一项事实。"""

    value: Any  # 事实值：数值、布尔值、枚举字符串或None
    mentioned: bool  # 病历中是否提到该事实
    evidence: str | None  # 支持该值的病历原文

    @property
    def usable_value(self) -> Any:
        """已提及时返回事实值，否则返回None。"""

        return self.value if self.mentioned else None


@dataclass(frozen=True)
class ExtractedFacts:
    """通过JSON校验后的全部病历事实。"""

    facts: dict[str, Fact]

    def get(self, name: str) -> Any:
        """取得规则计算使用的值；未提及时为None。"""

        return self.facts[name].usable_value


@dataclass(frozen=True)
class ClassificationResult:
    """一个可能的分级结果。"""

    grade: str  # 不含R的最终等级
    has_r: bool  # 是否带呼吸分型R

    def to_dict(self) -> dict[str, object]:
        """转换为可直接JSON序列化的字典。"""

        return {"grade": self.grade, "has_r": self.has_r}


@dataclass(frozen=True)
class ClassificationResults:
    """2.0 公开结果：所有可由缺失事实产生的不同分级。"""

    results: tuple[ClassificationResult, ...]

    def to_dict(self) -> dict[str, object]:
        """按稳定顺序输出去重后的结果列表。"""

        return {"results": [result.to_dict() for result in self.results]}
