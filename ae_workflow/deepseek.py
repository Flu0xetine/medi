"""真正调用 DeepSeek API 的提取 Agent 与审核 Agent。

DeepSeek 提供 OpenAI 兼容接口，所以这里使用官方 openai Python SDK，
但把 base_url 指向 DeepSeek。API Key 只从环境变量读取。
"""

from __future__ import annotations

import json
import os
from typing import Any, cast

from openai import OpenAI

from ae_grading import FIELD_SPECS

from .agents import ExtractionRequest, ReviewRequest
from .state import ReviewIssue, ReviewResult


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


# 这些说明来自 docs/规则引擎规范.md 的输入变量字典。
# Agent 必须理解每个字段的医学含义，而不能只看到英文变量名。
FIELD_DESCRIPTIONS = {
    "incidental_finding": "是否偶然发现；布尔值",
    "asymptomatic": "是否无症状；布尔值",
    "age_years": "年龄，标准单位：岁；数值",
    "cancer_history": "是否有癌症病史；布尔值",
    "chronic_cardiopulmonary_disease": "是否有慢性心肺疾病；布尔值",
    "spesi_systolic_bp_mmhg": "sPESI评估使用的收缩压，单位mmHg；不要与D1低血压事件血压混用",
    "heart_rate_bpm": "心率，单位次/分",
    "spo2_percent": "血氧饱和度，0至100，单位%",
    "highest_thrombus_location": "最高血栓解剖位置；仅允许subsegmental_only或non_subsegmental；两者同时存在时取non_subsegmental",
    "rv_abnormal": "右心室是否异常；根据病历判断布尔值",
    "cardiac_biomarker_abnormal": "是否至少一种相关心脏生物标志物异常；布尔值",
    "hypotension_systolic_bp_mmhg": "本次低血压事件中用于D1判断的收缩压，单位mmHg",
    "sbp_below_90_duration_minutes": "SBP持续低于90 mmHg的时间，单位分钟",
    "systolic_bp_drop_mmhg": "本次事件中SBP较原来血压的下降幅度，单位mmHg",
    "sbp_drop_gt_40_duration_minutes": "SBP较原来下降超过40 mmHg的持续时间，单位分钟",
    "hypotension_resolved_after_fluid": "达到低血压标准后是否在补液后恢复；仅给予补液不能算恢复",
    "hypoperfusion_or_end_organ_damage": "是否存在低灌注或终末器官损伤；布尔值",
    "lactate_mmol_l": "乳酸，单位mmol/L",
    "acute_kidney_dysfunction": "是否存在急性肾功能不全；布尔值",
    "urine_output_ml_kg_h": "每公斤体重每小时尿量，单位mL/kg/h",
    "altered_mental_status": "是否存在精神状态改变；布尔值，不分析病因",
    "cardiac_index_l_min_m2": "心脏指数CI，单位L/min/m²",
    "mean_arterial_pressure_mmhg": "平均动脉压MAP，单位mmHg",
    "recurrent_or_persistent_hypotension": "是否存在反复或持续低血压；布尔值",
    "cardiogenic_shock": "是否存在心源性休克；布尔值",
    "refractory_cardiogenic_shock": "是否存在难治性心源性休克；布尔值",
    "cardiac_arrest": "是否发生心脏骤停；布尔值",
    "no_rosc_after_30_minutes": "心脏骤停复苏30分钟后是否仍未恢复自主循环；布尔值",
    "respiratory_rate_bpm": "呼吸频率，单位次/分",
    "oxygen_required": "是否需要吸氧；布尔值",
    "nasal_cannula_flow_l_min": "鼻导管吸氧流量，单位L/min",
    "face_mask_oxygen": "是否使用面罩吸氧；布尔值",
    "noninvasive_ventilation": "是否使用无创机械通气；布尔值",
    "invasive_mechanical_ventilation": "是否使用有创机械通气；布尔值",
}


def _field_contract() -> str:
    """生成人和模型都容易阅读的固定字段清单。"""

    lines = []
    for name, spec in FIELD_SPECS.items():
        type_text = spec.value_type
        if spec.allowed_values:
            type_text += f"，允许值：{', '.join(spec.allowed_values)}"
        lines.append(f"- {name}（{type_text}）：{FIELD_DESCRIPTIONS[name]}")
    return "\n".join(lines)


def _missing_fact_template() -> dict[str, Any]:
    """创建包含全部字段的缺失事实模板，供模型模仿 JSON 结构。"""

    return {
        name: {"value": None, "mentioned": False, "evidence": None}
        for name in FIELD_SPECS
    }


def _read_json_content(response: Any) -> dict[str, Any]:
    """读取 DeepSeek JSON 模式返回值，并拒绝空响应或非对象 JSON。"""

    content = response.choices[0].message.content
    if not content:
        raise ValueError("DeepSeek返回了空内容")
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"DeepSeek返回的内容不是合法JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("DeepSeek返回的JSON顶层必须是对象")
    return data


class DeepSeekClient:
    """共享 DeepSeek API 客户端及 JSON 调用配置。"""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        client: OpenAI | None = None,
    ) -> None:
        key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if client is None and not key:
            raise ValueError("未设置DEEPSEEK_API_KEY环境变量")
        if client is None:
            try:
                key.encode("ascii")
            except UnicodeEncodeError as exc:
                raise ValueError(
                    "DEEPSEEK_API_KEY包含中文或其他非ASCII字符；"
                    "请把.env中的占位文字替换为DeepSeek控制台生成的真实API密钥"
                ) from exc
            if key.startswith("在这里") or any(character.isspace() for character in key):
                raise ValueError(
                    "DEEPSEEK_API_KEY仍是占位内容或含有空格；"
                    "请在.env中填写真实API密钥"
                )

        self.model = model or os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL)
        self.client = client or OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)

    def json_completion(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """调用 DeepSeek Chat Completions，并要求返回 JSON 对象。"""

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=16_000,
            temperature=0,
            stream=False,
            extra_body={"thinking": {"type": "disabled"}},
        )
        return _read_json_content(response)


class DeepSeekExtractor:
    """用 DeepSeek 从病历中提取规则引擎需要的完整事实表。"""

    def __init__(self, api: DeepSeekClient) -> None:
        self.api = api

    def __call__(self, request: ExtractionRequest) -> dict[str, Any]:
        """执行提取。

        伪代码：
            读取原始病历
            如果存在上一版事实和审核意见，也一并提供
            要求DeepSeek输出包含全部固定字段的JSON事实表
            解析JSON并返回完整事实表
        """

        system_prompt = f"""
你是病历结构化信息提取 Agent。你只负责忠实提取事实，不计算A–E等级。
必须只输出一个合法 JSON 对象，不要输出Markdown或解释文字。

每个字段必须严格使用以下事实结构：
病历明确提到：{{"value": 实际值, "mentioned": true, "evidence": "支持该值的病历原文"}}
病历未提到：{{"value": null, "mentioned": false, "evidence": null}}

规则：
1. 必须输出清单中的全部字段，不能增加未知字段。
2. 缺失信息不得推测；缺失项仍要输出。
3. 明确阴性使用value=false、mentioned=true，并引用原文。
4. evidence必须是支持该值的病历原文，不得自行编造。
5. 数值必须转换为字段规定的标准单位。
6. 如果这是修正请求，仍然返回一份新的完整事实表，不能只返回修改字段。

字段清单：
{_field_contract()}

完整 JSON 结构示例（其中缺失值只是结构示范，不代表实际病历）：
{json.dumps(_missing_fact_template(), ensure_ascii=False)}
""".strip()

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

        return self.api.json_completion(system_prompt, "\n\n".join(user_parts))


class DeepSeekReviewer:
    """用 DeepSeek 对照原始病历审核提取结果。"""

    def __init__(self, api: DeepSeekClient) -> None:
        self.api = api

    def __call__(self, request: ReviewRequest) -> ReviewResult:
        """执行审核。

        伪代码：
            对照原始病历检查完整事实表
            检查遗漏、误读、数值、单位、证据和字段结构
            只输出approved与issues组成的JSON
        """

        system_prompt = f"""
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

字段清单：
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

        user_prompt = (
            f"原始病历：\n{request['medical_record']}\n\n"
            "待审核的完整事实表：\n"
            f"{json.dumps(request['extracted_facts'], ensure_ascii=False)}\n\n"
            "请输出 JSON 审核结果。"
        )
        raw = self.api.json_completion(system_prompt, user_prompt)
        return _validate_review_result(raw)


def _validate_review_result(raw: dict[str, Any]) -> ReviewResult:
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


def create_deepseek_agents(
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[DeepSeekExtractor, DeepSeekReviewer]:
    """使用同一个 API 客户端创建真正的提取 Agent 和审核 Agent。"""

    api = DeepSeekClient(api_key=api_key, model=model)
    return DeepSeekExtractor(api), DeepSeekReviewer(api)
