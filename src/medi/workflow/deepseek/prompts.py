"""从字段注册表生成提取和审核共用的提示词。"""

from __future__ import annotations

import json
from typing import Any

from medi.grading import FIELD_SPECS
from medi.grading.field_registry import SHARED_EXTRACTION_RULES

from ..agents import ExtractionRequest, ReviewRequest


# 保留公开名称供调用方和测试使用，但内容只从注册表生成，不再维护第二份说明。
FIELD_DESCRIPTIONS = {
    name: spec.extraction_hint for name, spec in FIELD_SPECS.items()
}


def _field_contract() -> str:
    """从注册表生成提取与审核共同使用的字段契约。

    完整伪代码：
        收集全部字段引用的共享规则，只显示一次
        逐字段输出名称、类型、允许值、单位和专属提取说明
        将同一份契约用于提取 Agent 和审核 Agent
    """

    used_rules = {
        key for spec in FIELD_SPECS.values() for key in spec.shared_rule_keys
    }
    lines = ["共享提取规则："]
    lines.extend(
        f"- {key}：{rule}"
        for key, rule in SHARED_EXTRACTION_RULES.items() if key in used_rules
    )
    lines.append("字段清单：")
    for name, spec in FIELD_SPECS.items():
        type_text = spec.value_type
        if spec.allowed_values:
            type_text += f"，允许值：{', '.join(spec.allowed_values)}"
        if spec.unit:
            type_text += f"，单位：{spec.unit}"
        lines.append(f"- {name}（{type_text}）：{spec.extraction_hint}")
    return "\n".join(lines)


def _missing_fact_template() -> dict[str, Any]:
    """创建完整示例；仅为明确允许的字段示范无原文判否。"""

    return {
        name: (
            {"value": False, "mentioned": True, "evidence": None}
            if spec.absence_false else
            {"value": None, "mentioned": False, "evidence": None}
        )
        for name, spec in FIELD_SPECS.items()
    }


def _absence_false_contract() -> str:
    """列出可凭字段提示词的缺席条件判 false 的显式例外。"""

    names = ", ".join(name for name, spec in FIELD_SPECS.items() if spec.absence_false)
    return (
        "仅限明确配置的字段：" + names + "。若病历未记载其提示词所述阳性情况，"
        "按字段提示词输出 value=false、mentioned=true、evidence=null；"
        "如有可引用的原文依据，evidence 仍应引用原文。其他字段未提及仍输出缺失事实。"
    )


def extraction_system_prompt() -> str:
    """生成提取 Agent 的完整系统提示词。"""

    return f"""
你是病历结构化信息提取 Agent。你只负责忠实提取事实，不计算A–E等级。
必须只输出一个合法 JSON 对象，不要输出Markdown或解释文字。

每个字段必须严格使用以下事实结构：
病历明确提到：{{"value": 实际值, "mentioned": true, "evidence": "支持该值的病历原文"}}
病历未提到：{{"value": null, "mentioned": false, "evidence": null}}（下述字段例外除外）

{_absence_false_contract()}

规则：
1. 必须输出清单中的全部字段，不能增加未知字段。
2. 缺失信息不得推测；缺失项仍要输出。
3. 明确阴性使用value=false、mentioned=true，并引用原文。
4. evidence必须是支持该值的病历原文，不得自行编造。
5. 数值必须转换为字段规定的标准单位。
6. 如果这是修正请求，仍然返回一份新的完整事实表，不能只返回修改字段。

{_field_contract()}

完整 JSON 结构示例（仅演示未记载情形下的格式，不代表实际病历；若原文支持阳性或明确阴性，须按原文填写）：
{json.dumps(_missing_fact_template(), ensure_ascii=False)}
""".strip()


def extraction_user_prompt(request: ExtractionRequest) -> str:
    """加入病历、上一版事实和审核反馈，形成一次提取请求。"""

    user_parts = [f"原始病历：\n{request['medical_record']}"]
    if "previous_facts" in request:
        user_parts.append(
            "上一版完整事实表：\n"
            + json.dumps(request["previous_facts"], ensure_ascii=False)
        )
    if "review_feedback" in request:
        user_parts.append(
            "审核意见：\n"
            + json.dumps(request["review_feedback"], ensure_ascii=False)
        )
    user_parts.append("请输出修正后的完整 JSON 事实表。")
    return "\n\n".join(user_parts)


def review_system_prompt() -> str:
    """生成审核 Agent 的完整系统提示词。"""

    return f"""
你是独立的病历事实审核 Agent。你不计算A–E等级，也不直接修改事实表。
请对照原始病历，严格审核提取结果，并只输出合法 JSON 对象。

重点检查：
1. 是否遗漏病历明确记录的评分变量。
2. value是否与evidence及原始病历一致。
3. 是否正确识别否定、既往史、当前状态和时间点。
4. 数值是否抄写正确，单位换算是否符合字段定义。
5. 未提及项是否为value=null、mentioned=false、evidence=null。
6. 明确阴性是否为value=false、mentioned=true且有原文证据。
7. 是否包含全部固定字段，且没有未知字段。

{_absence_false_contract()}
审核这类空证据的 false 时，检查字段是否在例外清单中、病历是否确实没有相应阳性记载；不得仅因 evidence=null 判为错误。


{_field_contract()}

只能输出以下 JSON 结构：
{{
  "approved": true或false,
  "issues": [
    {{
      "field": "字段名；整体结构问题可写__structure__",
      "issue_type": "问题类型",
      "reason": "具体原因",
      "suggestion": "如何重新核对"
    }}
  ]
}}

如果approved=true，issues必须是空数组；如果存在任何问题，approved必须为false。
""".strip()


def review_user_prompt(request: ReviewRequest) -> str:
    """将病历与待审核事实表送入同一次审核请求。"""

    return (
        f"原始病历：\n{request['medical_record']}\n\n"
        "待审核的完整事实表：\n"
        f"{json.dumps(request['extracted_facts'], ensure_ascii=False)}\n\n"
        "请输出 JSON 审核结果。"
    )
