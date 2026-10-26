"""LLM JSON 输入解析，以及 Pydantic 错误到公开错误信息的转换。"""

from __future__ import annotations

from pydantic import ValidationError

from .field_registry import FIELD_SPECS, FieldSpec
from .models import ExtractedFacts


if set(FIELD_SPECS) != set(ExtractedFacts.model_fields):
    raise RuntimeError("FIELD_SPECS 与 Pydantic 输入模型字段不一致")


def _public_validation_message(exc: ValidationError) -> str:
    """把 Pydantic 细粒度错误转换成稳定、面向调用方的中文错误。

    完整伪代码：
        读取全部 Pydantic errors
        如果 JSON 语法错误：返回合法 JSON 错误
        收集顶层缺失字段；存在则一次性报告
        收集顶层未知字段；存在则一次性报告
        否则定位第一个出错字段和事实属性
        根据错误类型输出事实结构、类型或证据错误
        未识别的错误使用统一 Schema 错误兜底
    """

    errors = exc.errors(include_url=False)
    if any(error["type"] == "json_invalid" for error in errors):
        return "输入不是合法JSON"
    if any(error["type"] == "model_type" for error in errors):
        return "JSON顶层必须是对象"

    missing = sorted(
        str(error["loc"][0])
        for error in errors
        if error["type"] == "missing" and len(error["loc"]) == 1
    )
    if missing:
        return f"缺少输入变量: {', '.join(missing)}"

    extra = sorted(
        str(error["loc"][0])
        for error in errors
        if error["type"] == "extra_forbidden" and len(error["loc"]) == 1
    )
    if extra:
        return f"存在未知输入变量: {', '.join(extra)}"

    first = errors[0]
    location = first["loc"]
    field = str(location[0]) if location else "输入"
    if field == "输入" and first["type"] == "value_error":
        message = first["msg"]
        for name in FIELD_SPECS:
            if message.startswith(f"Value error, {name}.evidence "):
                return f"{name} 已知时evidence必须是非空字符串"
    if "value" in location:
        attribute = "value"
    elif "evidence" in location or (
        first["type"] == "value_error" and "evidence" in first["msg"]
    ):
        attribute = "evidence"
    else:
        attribute = ""
    error_type = first["type"]
    if field == "age_years" and error_type in {"greater_than_equal", "finite_number"}:
        return "age_years.value 必须为有限的非负年龄"

    if error_type in {"union_tag_invalid", "union_tag_not_found"}:
        return f"{field}.mentioned 必须是boolean"
    if error_type == "none_required":
        return f"{field} 缺失时value和evidence必须为null"
    if error_type == "value_error" and attribute == "evidence":
        return f"{field} 已知时evidence必须是非空字符串"
    if attribute == "value":
        spec = FIELD_SPECS[field]
        if spec.value_type == "enum":
            return f"{field}.value 必须是以下值之一: {', '.join(spec.allowed_values)}"
        return f"{field}.value 必须是{spec.value_type}"
    if attribute == "evidence":
        return f"{field}.evidence 必须是字符串"
    return f"输入不符合规则引擎Schema: {field}"


def parse_json_input(payload: str) -> ExtractedFacts:
    """把 JSON 字符串解析为不可变的 Pydantic 事实模型。"""

    if not isinstance(payload, str):
        raise TypeError("规则引擎输入必须是JSON字符串")
    try:
        return ExtractedFacts.model_validate_json(payload, strict=True)
    except ValidationError as exc:
        raise ValueError(_public_validation_message(exc)) from exc
