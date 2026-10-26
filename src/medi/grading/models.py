"""Pydantic 数据模型：输入事实、规则输入和公开分类结果。"""

from __future__ import annotations

from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, model_validator

from .field_registry import FIELD_SPECS


ValueT = TypeVar("ValueT")
NumberValue = StrictInt | StrictFloat
AgeValue = Annotated[NumberValue, Field(ge=0, allow_inf_nan=False)]
ThrombusLocation = Literal["subsegmental_only", "non_subsegmental"]
Grade = Literal["A", "E2", "E1", "D2", "D1", "D0", "C1", "C2", "C3", "B1", "B2"]


class _StrictModel(BaseModel):
    """所有规则模型的共同约束：不可变且拒绝未知字段。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class MissingFact(_StrictModel):
    """病历缺失事实；三个字段的组合由类型系统固定。"""

    value: None
    mentioned: Literal[False]
    evidence: None

    @property
    def usable_value(self) -> None:
        return None


class KnownFact(_StrictModel, Generic[ValueT]):
    """病历已知事实；具体 value 类型由使用它的字段决定。"""

    value: ValueT
    mentioned: Literal[True]
    evidence: str | None

    @model_validator(mode="after")
    def evidence_must_contain_text(self) -> "KnownFact[ValueT]":
        """拒绝空字符串和纯空白证据，但保留原始证据文本。"""

        if self.evidence is not None and not self.evidence.strip():
            raise ValueError("已知事实的evidence必须是非空字符串")
        return self

    @property
    def usable_value(self) -> ValueT:
        return self.value


# mentioned 是判别字段。Pydantic 只校验匹配的事实分支，避免产生大量无关错误。
BooleanFact = Annotated[
    MissingFact | KnownFact[StrictBool],
    Field(discriminator="mentioned"),
]
NumberFact = Annotated[
    MissingFact | KnownFact[NumberValue],
    Field(discriminator="mentioned"),
]
LocationFact = Annotated[
    MissingFact | KnownFact[ThrombusLocation],
    Field(discriminator="mentioned"),
]
AgeFact = Annotated[
    MissingFact | KnownFact[AgeValue],
    Field(discriminator="mentioned"),
]


class ExtractedFacts(_StrictModel):
    """规则引擎的完整输入 Schema。

    完整伪代码：
        对顶层对象执行严格字段校验
        对每个字段读取 mentioned
        如果 mentioned=false：要求 value=null 且 evidence=null
        如果 mentioned=true：按字段声明校验 value；仅允许配置过的缺席判 false 字段无原文证据
        拒绝缺失字段和未知字段
        返回不可变的结构化事实模型
    """

    # A、B、C 与 PESI
    incidental_finding: BooleanFact
    asymptomatic: BooleanFact
    age_years: AgeFact
    cancer_history: BooleanFact
    male_sex: BooleanFact
    heart_failure_history: BooleanFact
    chronic_lung_disease: BooleanFact
    body_temperature_c: NumberFact
    systolic_bp_mmhg: NumberFact
    diastolic_bp_mmhg: NumberFact
    heart_rate_bpm: NumberFact
    spo2_percent: NumberFact
    highest_thrombus_location: LocationFact
    rv_abnormal: BooleanFact
    cardiac_biomarker_abnormal: BooleanFact

    # 新流程的第一分流、低血压事件和 D1 短暂恢复条件
    vasopressor_used: BooleanFact
    fluid_treatment_given: BooleanFact
    sbp_below_90_duration_minutes: NumberFact
    systolic_bp_drop_mmhg: NumberFact
    sbp_drop_gt_40_duration_minutes: NumberFact
    hypotension_recovered: BooleanFact
    hypotension_recurred_after_recovery: BooleanFact

    # 低灌注五项；精神状态同时用于 PESI
    lactate_mmol_l: NumberFact
    acute_kidney_dysfunction: BooleanFact
    altered_mental_status: BooleanFact
    cold_clammy_extremities: BooleanFact

    # E
    recurrent_or_persistent_hypotension: BooleanFact
    refractory_cardiogenic_shock: BooleanFact
    no_rosc_after_30_minutes: BooleanFact

    # 呼吸分型 R
    respiratory_rate_bpm: NumberFact
    oxygen_required: BooleanFact
    nasal_cannula_over_6_l_min: BooleanFact
    face_mask_oxygen: BooleanFact
    noninvasive_ventilation: BooleanFact
    invasive_mechanical_ventilation: BooleanFact

    @model_validator(mode="after")
    def validate_null_evidence(self) -> "ExtractedFacts":
        """仅允许提示词规定“未提及即 false”的字段以空证据表达该判断。

        完整伪代码：
            遍历字段注册表
            如果字段被标记为已提及且证据为空：
                检查该字段允许缺席判 false 且当前值恰为 false
                不满足则报出具体字段的证据错误
            返回原始事实，不应用规则默认值
        """

        for name, spec in FIELD_SPECS.items():
            fact = getattr(self, name)
            if fact.mentioned and fact.evidence is None:
                if not (spec.absence_false and fact.value is False):
                    raise ValueError(f"{name}.evidence 已知时必须是非空字符串")
        return self

    def get(self, name: str) -> Any:
        """返回规则可使用的值；缺失时才应用注册表默认值。

        完整伪代码：
            读取原始事实对象
            若病历已提及，直接返回原始值
            若病历未提及，返回注册表中的默认值
            不修改原始事实对象和其证据状态
        """

        fact = getattr(self, name)
        return fact.usable_value if fact.mentioned else FIELD_SPECS[name].missing_default


class ClassificationResult(_StrictModel):
    """一个可能的分级结果。"""

    grade: Grade
    has_r: StrictBool


class ClassificationResults(_StrictModel):
    """2.0 公开结果：所有可由缺失事实产生的不同分级。"""

    results: tuple[ClassificationResult, ...]

    def to_dict(self) -> dict[str, object]:
        """转换为保持稳定顺序的 JSON 可序列化字典。"""

        return self.model_dump(mode="json")
