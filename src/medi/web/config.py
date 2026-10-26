"""网页字段、随机范围和预置病例配置。"""

from __future__ import annotations

from medi.grading.field_registry import FIELD_SPECS


FIELD_CONFIG = {
    "A / B / C 与 PESI": [
        ("incidental_finding", "偶然发现", "boolean", None),
        ("asymptomatic", "无症状", "boolean", None),
        ("age_years", "年龄", "number", (18, 100, 1, "岁")),
        ("cancer_history", "癌症病史", "boolean", None),
        ("male_sex", "男性", "boolean", None),
        ("heart_failure_history", "心力衰竭病史", "boolean", None),
        ("chronic_lung_disease", "慢性肺部疾病", "boolean", None),
        ("body_temperature_c", "体温", "number", (34, 42, 0.1, "°C")),
        ("systolic_bp_mmhg", "收缩压（低血压 / PESI / MAP 共用）", "number", (60, 150, 1, "mmHg")),
        ("diastolic_bp_mmhg", "同次测量舒张压（计算 MAP）", "number", (30, 110, 1, "mmHg")),
        ("heart_rate_bpm", "心率", "number", (50, 160, 1, "次/分")),
        ("spo2_percent", "血氧饱和度", "number", (75, 100, 1, "%")),
        (
            "highest_thrombus_location",
            "最高血栓解剖位置",
            "enum",
            {
                "subsegmental_only": "仅亚段血栓",
                "non_subsegmental": "存在非亚段血栓",
            },
        ),
        ("rv_abnormal", "右心室异常", "boolean", None),
        ("cardiac_biomarker_abnormal", "心脏生物标志物异常", "boolean", None),
    ],
    "第一分流与短暂低血压": [
        ("vasopressor_used", "使用升压药", "boolean", None),
        ("fluid_treatment_given", "已给予补液治疗", "boolean", None),
        ("sbp_below_90_duration_minutes", "SBP＜90 持续时间", "number", (1, 30, 1, "分钟")),
        ("systolic_bp_drop_mmhg", "收缩压下降幅度", "number", (0, 80, 1, "mmHg")),
        ("sbp_drop_gt_40_duration_minutes", "SBP下降＞40 持续时间", "number", (1, 30, 1, "分钟")),
        ("hypotension_recovered", "低血压已恢复", "boolean", None),
        ("hypotension_recurred_after_recovery", "低血压恢复后复发", "boolean", None),
    ],
    "低灌注五项指标": [
        ("lactate_mmol_l", "乳酸", "number", (0.5, 8.0, 0.1, "mmol/L")),
        ("acute_kidney_dysfunction", "急性肾功能不全", "boolean", None),
        ("altered_mental_status", "精神状态改变（D2 / PESI）", "boolean", None),
        ("cold_clammy_extremities", "四肢湿冷", "boolean", None),
    ],
    "E — 反复/持续低血压与心脏骤停": [
        ("recurrent_or_persistent_hypotension", "反复或持续低血压", "boolean", None),
        ("refractory_cardiogenic_shock", "难治性心源性休克", "boolean", None),
        ("no_rosc_after_30_minutes", "心脏骤停经30分钟复苏仍无自主循环", "boolean", None),
    ],
    "R — 呼吸分型": [
        ("respiratory_rate_bpm", "呼吸频率（PESI / R）", "number", (10, 45, 1, "次/分")),
        ("oxygen_required", "需要吸氧", "boolean", None),
        ("nasal_cannula_over_6_l_min", "鼻导管吸氧流量大于 6 L/min", "boolean", None),
        ("face_mask_oxygen", "面罩吸氧", "boolean", None),
        ("noninvasive_ventilation", "无创机械通气", "boolean", None),
        ("invasive_mechanical_ventilation", "有创机械通气", "boolean", None),
    ],
}


PRESETS = {
    "A 级": {"incidental_finding": True, "asymptomatic": True},
    "B1 级": {"highest_thrombus_location": "subsegmental_only"},
    "C3-R": {
        "age_years": 85,
        "spo2_percent": 88,
        "rv_abnormal": True,
        "cardiac_biomarker_abnormal": True,
    },
    "D1-R": {
        "systolic_bp_mmhg": 85,
        "sbp_below_90_duration_minutes": 10,
        "hypotension_recovered": True,
        "face_mask_oxygen": True,
    },
    "D2-R": {"lactate_mmol_l": 3.5, "face_mask_oxygen": True},
    "E2-R": {
        "no_rosc_after_30_minutes": True,
        "invasive_mechanical_ventilation": True,
    },
}


def frontend_config() -> dict:
    """转换为浏览器可直接消费的配置。"""

    groups = []
    for group_name, fields in FIELD_CONFIG.items():
        items = []
        for name, label, field_type, options in fields:
            item = {"name": name, "label": label, "type": field_type}
            item["absence_false"] = FIELD_SPECS[name].absence_false
            if field_type == "number":
                minimum, maximum, step, unit = options
                item.update(min=minimum, max=maximum, step=step, unit=unit)
            elif field_type == "enum":
                item["options"] = options
            items.append(item)
        groups.append({"name": group_name, "fields": items})
    return {"groups": groups, "presets": PRESETS}
