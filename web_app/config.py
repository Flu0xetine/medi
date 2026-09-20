"""网页字段、随机范围和预置病例配置。"""

from __future__ import annotations


FIELD_CONFIG = {
    "A / B / C 与 sPESI": [
        ("incidental_finding", "偶然发现", "boolean", None),
        ("asymptomatic", "无症状", "boolean", None),
        ("age_years", "年龄", "number", (18, 100, 1, "岁")),
        ("cancer_history", "癌症病史", "boolean", None),
        ("chronic_cardiopulmonary_disease", "慢性心肺疾病", "boolean", None),
        ("spesi_systolic_bp_mmhg", "sPESI 收缩压", "number", (70, 150, 1, "mmHg")),
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
    "D1 — 短暂或补液后恢复的低血压": [
        ("hypotension_systolic_bp_mmhg", "低血压事件收缩压", "number", (60, 110, 1, "mmHg")),
        ("sbp_below_90_duration_minutes", "SBP＜90 持续时间", "number", (1, 30, 1, "分钟")),
        ("systolic_bp_drop_mmhg", "收缩压下降幅度", "number", (0, 80, 1, "mmHg")),
        ("sbp_drop_gt_40_duration_minutes", "SBP下降＞40 持续时间", "number", (1, 30, 1, "分钟")),
        ("hypotension_resolved_after_fluid", "补液后低血压恢复", "boolean", None),
        ("hypoperfusion_or_end_organ_damage", "存在低灌注或终末器官损伤", "boolean", None),
    ],
    "D2 — 低灌注指标": [
        ("lactate_mmol_l", "乳酸", "number", (0.5, 8.0, 0.1, "mmol/L")),
        ("acute_kidney_dysfunction", "急性肾功能不全", "boolean", None),
        ("urine_output_ml_kg_h", "尿量", "number", (0.1, 1.5, 0.1, "mL/kg/h")),
        ("altered_mental_status", "精神状态改变", "boolean", None),
        ("cardiac_index_l_min_m2", "心脏指数 CI", "number", (1.0, 4.0, 0.1, "L/min/m²")),
        ("mean_arterial_pressure_mmhg", "平均动脉压 MAP", "number", (40, 100, 1, "mmHg")),
    ],
    "E — 心源性休克与心脏骤停": [
        ("recurrent_or_persistent_hypotension", "反复或持续低血压", "boolean", None),
        ("cardiogenic_shock", "心源性休克", "boolean", None),
        ("refractory_cardiogenic_shock", "难治性心源性休克", "boolean", None),
        ("cardiac_arrest", "心脏骤停", "boolean", None),
        ("no_rosc_after_30_minutes", "复苏30分钟后仍无自主循环", "boolean", None),
    ],
    "R — 呼吸分型": [
        ("respiratory_rate_bpm", "呼吸频率", "number", (10, 45, 1, "次/分")),
        ("oxygen_required", "需要吸氧", "boolean", None),
        ("nasal_cannula_flow_l_min", "鼻导管吸氧流量", "number", (0, 15, 0.5, "L/min")),
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
        "hypotension_systolic_bp_mmhg": 85,
        "sbp_below_90_duration_minutes": 10,
        "hypoperfusion_or_end_organ_damage": False,
        "face_mask_oxygen": True,
    },
    "D2-R": {"lactate_mmol_l": 3.5, "face_mask_oxygen": True},
    "E2-R": {
        "cardiac_arrest": True,
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
            if field_type == "number":
                minimum, maximum, step, unit = options
                item.update(min=minimum, max=maximum, step=step, unit=unit)
            elif field_type == "enum":
                item["options"] = options
            items.append(item)
        groups.append({"name": group_name, "fields": items})
    return {"groups": groups, "presets": PRESETS}
