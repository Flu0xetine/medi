"""LLM JSON输入的解析和固定Schema校验。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .models import ExtractedFacts, Fact


@dataclass(frozen=True)
class FieldSpec:
    """单个输入变量的类型约束。"""

    value_type: str  # number、boolean或enum
    allowed_values: tuple[str, ...] = ()  # 枚举允许值


# 固定输入变量表；英文名旁的中文注释说明临床含义。
FIELD_SPECS: dict[str, FieldSpec] = {
    # A/B/C及sPESI
    "incidental_finding": FieldSpec("boolean"),  # 是否偶然发现
    "asymptomatic": FieldSpec("boolean"),  # 是否无症状
    "age_years": FieldSpec("number"),  # 年龄（岁）
    "cancer_history": FieldSpec("boolean"),  # 癌症病史
    "chronic_cardiopulmonary_disease": FieldSpec("boolean"),  # 慢性心肺疾病
    "spesi_systolic_bp_mmhg": FieldSpec("number"),  # sPESI收缩压
    "heart_rate_bpm": FieldSpec("number"),  # 心率
    "spo2_percent": FieldSpec("number"),  # 血氧饱和度
    "highest_thrombus_location": FieldSpec(
        "enum", ("subsegmental_only", "non_subsegmental")
    ),  # 最高血栓位置
    "rv_abnormal": FieldSpec("boolean"),  # 右心室异常
    "cardiac_biomarker_abnormal": FieldSpec("boolean"),  # 心脏标志物异常
    # D1
    "hypotension_systolic_bp_mmhg": FieldSpec("number"),  # 低血压事件SBP
    "sbp_below_90_duration_minutes": FieldSpec("number"),  # SBP<90持续时间
    "systolic_bp_drop_mmhg": FieldSpec("number"),  # SBP下降幅度
    "sbp_drop_gt_40_duration_minutes": FieldSpec("number"),  # 下降>40持续时间
    "hypotension_resolved_after_fluid": FieldSpec("boolean"),  # 补液后恢复
    "hypoperfusion_or_end_organ_damage": FieldSpec("boolean"),  # 低灌注/器官损伤
    # D2
    "lactate_mmol_l": FieldSpec("number"),  # 乳酸
    "acute_kidney_dysfunction": FieldSpec("boolean"),  # 急性肾功能不全
    "urine_output_ml_kg_h": FieldSpec("number"),  # 尿量
    "altered_mental_status": FieldSpec("boolean"),  # 精神状态改变
    "cardiac_index_l_min_m2": FieldSpec("number"),  # 心脏指数CI
    "mean_arterial_pressure_mmhg": FieldSpec("number"),  # 平均动脉压MAP
    # E级
    "recurrent_or_persistent_hypotension": FieldSpec("boolean"),  # 反复/持续低血压
    "cardiogenic_shock": FieldSpec("boolean"),  # 心源性休克
    "refractory_cardiogenic_shock": FieldSpec("boolean"),  # 难治性心源性休克
    "cardiac_arrest": FieldSpec("boolean"),  # 心脏骤停
    "no_rosc_after_30_minutes": FieldSpec("boolean"),  # 复苏30分钟仍无ROSC
    # 呼吸分型
    "respiratory_rate_bpm": FieldSpec("number"),  # 呼吸频率
    "oxygen_required": FieldSpec("boolean"),  # 需要吸氧
    "nasal_cannula_flow_l_min": FieldSpec("number"),  # 鼻导管流量
    "face_mask_oxygen": FieldSpec("boolean"),  # 面罩吸氧
    "noninvasive_ventilation": FieldSpec("boolean"),  # 无创机械通气
    "invasive_mechanical_ventilation": FieldSpec("boolean"),  # 有创机械通气
}


def _validate_value(name: str, value: Any, spec: FieldSpec) -> None:
    if spec.value_type == "boolean" and not isinstance(value, bool):
        raise ValueError(f"{name}.value 必须是boolean")
    if spec.value_type == "number" and (
        isinstance(value, bool) or not isinstance(value, (int, float))
    ):
        raise ValueError(f"{name}.value 必须是number")
    if spec.value_type == "enum" and value not in spec.allowed_values:
        allowed = ", ".join(spec.allowed_values)
        raise ValueError(f"{name}.value 必须是以下值之一: {allowed}")


def parse_json_input(payload: str) -> ExtractedFacts:
    """把LLM输出的JSON字符串解析为规则引擎事实。"""

    if not isinstance(payload, str):
        raise TypeError("规则引擎输入必须是JSON字符串")
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"输入不是合法JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError("JSON顶层必须是对象")

    expected = set(FIELD_SPECS)
    received = set(data)
    missing = sorted(expected - received)
    extra = sorted(received - expected)
    if missing:
        raise ValueError(f"缺少输入变量: {', '.join(missing)}")
    if extra:
        raise ValueError(f"存在未知输入变量: {', '.join(extra)}")

    parsed: dict[str, Fact] = {}
    for name, spec in FIELD_SPECS.items():
        raw_fact = data[name]
        if not isinstance(raw_fact, dict):
            raise ValueError(f"{name} 必须是事实对象")
        if set(raw_fact) != {"value", "mentioned", "evidence"}:
            raise ValueError(f"{name} 必须且只能包含value、mentioned、evidence")

        mentioned = raw_fact["mentioned"]
        value = raw_fact["value"]
        evidence = raw_fact["evidence"]
        if not isinstance(mentioned, bool):
            raise ValueError(f"{name}.mentioned 必须是boolean")
        if mentioned:
            if value is None:
                raise ValueError(f"{name} 已提及时value不能为null")
            if not isinstance(evidence, str) or not evidence.strip():
                raise ValueError(f"{name} 已提及时evidence必须是非空字符串")
            _validate_value(name, value, spec)
        elif value is not None or evidence is not None:
            raise ValueError(f"{name} 未提及时value和evidence必须为null")

        parsed[name] = Fact(value=value, mentioned=mentioned, evidence=evidence)
    return ExtractedFacts(parsed)
