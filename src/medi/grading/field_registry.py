"""LLM 原始事实字段注册表：类型、缺失策略和提取说明的单一代码入口。

程序计算条件（如 PESI、低血压）不属于提取字段，不在本表中重复定义。
Pydantic 模型仍负责校验实际 JSON；本表供提示词、错误信息和界面契约使用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ValueType = Literal["number", "boolean", "enum"]
DefaultValue = bool | int | float | str | None


@dataclass(frozen=True)
class FieldSpec:
    """一个由 LLM 提取的原始事实字段。"""

    value_type: ValueType
    extraction_hint: str
    unit: str | None = None
    allowed_values: tuple[str, ...] = ()
    missing_default: DefaultValue = None  # 未配置默认值时，规则保留全部可能状态。
    shared_rule_keys: tuple[str, ...] = ()
    absence_false: bool = False  # 字段提示词明确规定“未提及/未记载”即为 false。


SHARED_EXTRACTION_RULES: dict[str, str] = {
    "paired_blood_pressure": (
        "收缩压和舒张压必须来自同一次血压测量；"
        "不得拼接不同时点或不同事件的数据。"
        "某一项没有可靠数值时，该项保持缺失。"
    ),
}


# 完整伪代码：
#   逐字段声明类型、单位、允许值、缺失默认值和专属提取说明
#   如多个字段共用提取约束，记录共享规则键，不重复复制说明
#   提示词生成器先列共享规则，再列全部字段说明
#   输入解析器依据 Pydantic Schema 校验 JSON，并核对字段集合与本表一致
FIELD_SPECS: dict[str, FieldSpec] = {
    "incidental_finding": FieldSpec("boolean", "true:根据病历中本次PE的发现经过，发现并非因为临床怀疑/排除/进一步评估PE而进行影像学检查时发现，而是在因其他疾病/其他临床目的进行的CT或其他影像学检查中偶然发现。（如：患者为了检查肺癌进行CT检查意外发现肺栓塞。）\nfalse：因怀疑/排除/进一步评估PE而进行影像学检查时发现（如：下肢静脉超声提示有血栓/低氧血症，为了排除PE，而进行的CTPA检查。）"),
    "asymptomatic": FieldSpec("boolean", "true: 病历资料中PE疑诊/确诊时患者未出现以下任一症状：呼吸困难、喘憋、气短、喘不上气、活动后气促、胸闷伴气短、呼吸费力；胸痛、胸部疼痛、胸闷痛，尤其胸膜性胸痛、吸气时加重的胸痛；咯血、痰中带血、血痰；晕厥、昏厥、晕倒、近乎晕厥、黑蒙、差点晕倒；头晕、头昏、濒死感等；\nfalse：出现以上任一阳性体征；"),
    "age_years": FieldSpec("number", "提取年龄，PESI 按每岁 1 分计算；未记载年龄不估计。", unit="岁"),
    "cancer_history": FieldSpec("boolean", "true:既往史中描述患者有癌症病史；\nfalse:既往史中未描述患者有癌症病史；", missing_default=False, absence_false=True),
    "male_sex": FieldSpec("boolean", "病历明确记载为男性时为 true，明确记载为女性时为 false；未记载性别时保持未提及。"),
    "heart_failure_history": FieldSpec("boolean", "true:患者既往有以下任一疾病：心力衰竭，心功能不全，心功能Ⅰ级、心功能Ⅱ级、心功能Ⅲ级、心功能Ⅳ级\nfalse:未出现以上阳性体征；", missing_default=False),
    "chronic_lung_disease": FieldSpec("boolean", "true:患者既往有任一以下疾病：慢性阻塞性肺疾病（COPD）、慢性支气管炎、慢性肺气肿、支气管哮喘、过敏性哮喘、非过敏性哮喘、职业性哮喘、咳嗽变异性哮喘、支气管扩张症、慢性闭塞性细支气管炎、间质性肺疾病、特发性肺纤维化、慢性非特异性间质性肺炎、结缔组织病相关间质性肺病、慢性/纤维化型过敏性肺炎、肺结节病、慢性药物性肺损伤、慢性放射性肺损伤、矽肺、煤工尘肺、石棉肺、其他尘肺、慢性铍病、囊性纤维化伴肺病；原发性纤毛运动障碍伴慢性气道病变；支气管肺发育不良遗留肺病、慢性呼吸衰竭、长期家庭氧疗；\nfalse:未出现以上阳性体征；", missing_default=False),
    "body_temperature_c": FieldSpec("number", "提取体温，统一换算为摄氏度。", unit="°C"),
    "systolic_bp_mmhg": FieldSpec(
        "number", "提取收缩压；低血压、PESI 和 MAP 共用同一数值，须与舒张压来自同一次测量。\n注：采用急性肺栓塞确诊后最早测量的血压值（例如：住院期间急性肺栓塞危急值中测量的血压值）",
        unit="mmHg", shared_rule_keys=("paired_blood_pressure",),
    ),
    "diastolic_bp_mmhg": FieldSpec(
        "number", "提取与上述收缩压同一次测量的舒张压；不拼接不同时点的血压。", unit="mmHg",
        shared_rule_keys=("paired_blood_pressure",),
    ),
    "heart_rate_bpm": FieldSpec("number", "提取用于本次评估的心率；不要把呼吸频率当作心率。（注：尽量选择和血压测量同一基线的心率，如果无即选择急性肺栓塞确诊后最早测量的心率，如：住院期间危急值中的心率）", unit="次/分"),
    "spo2_percent": FieldSpec("number", "提取血氧饱和度；PESI 与 C-R 必须使用同一事实。(注：氧浓度为吸氧下测得的需要备注)", unit="%"),
    "highest_thrombus_location": FieldSpec(
        "enum", "仅亚段为 subsegmental_only；存在非亚段为 non_subsegmental，即使同时有亚段血栓也取后者。",
        allowed_values=("subsegmental_only", "non_subsegmental"),
    ),
    "rv_abnormal": FieldSpec("boolean", "true:病历资料（病历文本资料、CTPA报告、超声心动图）中提示患者右心室增大（右心增大/右心房增大/右心饱满不算）；或者右心室收缩功能减低；或者右心室游离壁运动减弱\nfalse: 病历资料（病历文本资料、CTPA报告、超声心动图）中未提及患者右心室增大，未提及右心室收缩功能减低；未提及右心室游离壁运动减弱", absence_false=True),
    "cardiac_biomarker_abnormal": FieldSpec("boolean", "true:出现以下任一阳性指标：心肌肌钙蛋白I≥0.03ng/ml；年龄＜55岁NT-proBNP≥356pg/ml，55-69岁NT-proBNP≥526pg/ml，≥70岁NT-proBNP≥647pg/ml；；年龄＜55岁BNP≥83pg/ml，55-69岁BNP≥146pg/ml，≥70岁BNP≥200pg/ml；\nfalse: 本次评估窗口内，至少有一项cTnI/BNP/NT-proBNP检验结果可用于按本规则判定，且该结果未达到相应阳性阈值；即使其他心肌标志物未检验，也输出 false。"),
    "vasopressor_used": FieldSpec("boolean", "true:患者由于急性肺栓塞使用升压药（例如：去甲肾上腺素、多巴胺、肾上腺素、多巴酚丁胺）升压治疗；\nfalse:患者在急性肺栓塞病程中并未使用升压药", missing_default=False),
    "fluid_treatment_given": FieldSpec("boolean", "true: 患者由于急性肺栓塞采取补液治疗；false:患者在急性肺栓塞病程中未采取过补液治疗；", missing_default=False),
    "sbp_below_90_duration_minutes": FieldSpec("number", "提取同一低血压事件中 SBP <90 mmHg 的持续时间；未记载时间不推算。若测得的收缩压；未出现小于90mmHg的情况，输出null", unit="分钟"),
    "systolic_bp_drop_mmhg": FieldSpec("number", "急性肺栓塞确诊前后血压的下降值（比如：患者入院时血压132/93mmHg，住院期间危急值结果回报：急性肺栓塞，血压90/73mmHg，即血压下降值为132-90=42", unit="mmHg"),
    "sbp_drop_gt_40_duration_minutes": FieldSpec("number", "提取同一事件中 SBP 下降 >40 mmHg 的持续时间；未记载时间不推算。若测得的血压值；未出现下降超过40的情况，输出null", unit="分钟"),
    "hypotension_recovered": FieldSpec(
        "boolean",
        "true: 已明确发生低血压，持续时间 <15 分钟后自行恢复，且后续未再发生低血压；或补液/升压药治疗后即恢复，且后续未再发生低血压。\n"
        "false: 已明确发生低血压，但不满足上述任一条件；恢复后再次发生低血压，即使每次持续时间均短于15分钟，也输出 false。\n"
        "未提及：未发生低血压，或虽发生低血压但恢复时点、后续是否复发无法判断。",
    ),
    "hypotension_recurred_after_recovery": FieldSpec(
        "boolean",
        "true:病历明确记录患者发生低血压，且低血压曾经恢复(包括自行恢复或经补液、升压药等治疗后恢复)，随后再次发生低血压。\n"
        "false:病历明确记录患者发生低血压，且低血压曾经恢复(包括自行恢复或经补液、升压药等治疗后恢复)，随后未再发生低血压。或者患者未曾发生过低血压。\n"
        "未提及:缺乏足够信息判断恢复后是否再次发生低血压。",
    ),
    "lactate_mmol_l": FieldSpec("number", "乳酸值在检验报告“血气分析”中提取.", unit="mmol/L"),
    "acute_kidney_dysfunction": FieldSpec("boolean", "true:病历资料中明确患者存在急性肾损伤或急性肾功能不全；或尿量小于0.5ml/kg/h（出入量会记录患者的尿量，护理记录单会记录患者体重；未记录出入量不予输出）\nfalse:未出现以上阳性指标；", missing_default=False),
    "altered_mental_status": FieldSpec("boolean", "true:病历资料中提示患者出现以下任一症状：意识模糊/意识混乱；嗜睡；反应迟钝；定向力障碍；注意力下降；谵妄；躁动/异常兴奋；言语/行为异常；昏睡/难以唤醒；昏迷；晕厥；（注：精神状态一般不算）\nfalse:未出现以上阳性指标；", missing_default=False),
    "cold_clammy_extremities": FieldSpec("boolean", "true: 病历明确记载存在四肢湿冷、肢端湿冷、末梢湿冷、皮肤湿冷，或明确记载“冷汗伴肢端湿冷”\nfalse：未出现上述记载；", absence_false=True),
    "recurrent_or_persistent_hypotension": FieldSpec("boolean", "true:低血压没有自行恢复，也没有在补液/使用升压药后得到稳定纠正，反复或者持续低血压，需要持续循环支持；\nfalse:患者未出现低血压，或低血压自行恢复，或者在补液/升压药后得到稳定纠正，并未反复或者持续低血压；"),
    "refractory_cardiogenic_shock": FieldSpec("boolean", "true:在心源性休克的基础上，经过补液或升压药治疗后，组织低灌注仍持续或恶化，需要不断升级循环支持（升压药加量/增加升压药种类/机械循环支持），仍无法维持足够的器官灌注；\nfalse：患者未出现低血压；或者低血压经过初始/常规治疗后，组织灌注得到恢复并保持稳定，未发生恶化，无需进一步升级循环支持"),
    "no_rosc_after_30_minutes": FieldSpec(
        "boolean", "true:心脏骤停复苏30分钟后未恢复自主循环；（如：病历记录患者10时50分持续胸外按压，12时55分恢复为窦性心律，超过半小时仍未恢复自主循环，即为true。）\nfalse:未出现心脏骤停，或者心脏骤停复苏30分钟内恢复自主循环；",
    ),
    "respiratory_rate_bpm": FieldSpec("number", "提取呼吸频率；PESI 与 C-R 必须使用同一事实。", unit="次/分"),
    "oxygen_required": FieldSpec("boolean", "true:病历资料中提示患者氧气吸入；\nfalse:病历资料中未提及患者吸氧；", missing_default=False, absence_false=True),
    "nasal_cannula_over_6_l_min": FieldSpec(
        "boolean", "判断是否存在大于 6 L/min 的鼻导管吸氧；恰好 6 L/min 为否;若病历中提及患者鼻导管吸氧，未说明氧流量，默认2L/min。",
        missing_default=False,
    ),
    "face_mask_oxygen": FieldSpec("boolean", "true:病历资料中提示患者使用面罩吸氧；false:病历资料中未提示患者使用面罩吸氧；", missing_default=False, absence_false=True),
    "noninvasive_ventilation": FieldSpec("boolean", "true:病历资料中提示患者使用无创机械通气；false:病历资料中未提示患者使用无创机械通气；", missing_default=False, absence_false=True),
    "invasive_mechanical_ventilation": FieldSpec("boolean", "true:病历资料中提示患者使用有创机械通气；false:病历资料中未提示患者使用有创机械通气；", missing_default=False, absence_false=True),
}


def validate_registry() -> None:
    """尽早发现缺失说明、错误枚举和未定义的共享规则。"""

    for name, spec in FIELD_SPECS.items():
        if not spec.extraction_hint.strip():
            raise RuntimeError(f"{name} 缺少提取说明")
        if (spec.value_type == "enum") != bool(spec.allowed_values):
            raise RuntimeError(f"{name} 枚举允许值与字段类型不一致")
        default = spec.missing_default
        if default is not None:
            valid_default = (
                type(default) is bool if spec.value_type == "boolean"
                else type(default) in (int, float) if spec.value_type == "number"
                else default in spec.allowed_values
            )
            if not valid_default:
                raise RuntimeError(f"{name} 未提及时默认值与字段类型不一致")
        if any(key not in SHARED_EXTRACTION_RULES for key in spec.shared_rule_keys):
            raise RuntimeError(f"{name} 引用了未定义的共享提取规则")
        if spec.absence_false and spec.value_type != "boolean":
            raise RuntimeError(f"{name} 未提及判 false 仅适用于布尔字段")


validate_registry()
