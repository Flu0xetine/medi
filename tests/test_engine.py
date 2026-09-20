"""2.0 多结果规则引擎测试。"""

import json
import sys
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ae_grading import FIELD_SPECS, classify


SAFE_VALUES = {
    "incidental_finding": False, "asymptomatic": False, "age_years": 80,
    "cancer_history": False, "chronic_cardiopulmonary_disease": False,
    "spesi_systolic_bp_mmhg": 100, "heart_rate_bpm": 109, "spo2_percent": 90,
    "highest_thrombus_location": "subsegmental_only", "rv_abnormal": False,
    "cardiac_biomarker_abnormal": False, "hypotension_systolic_bp_mmhg": 90,
    "sbp_below_90_duration_minutes": 15, "systolic_bp_drop_mmhg": 40,
    "sbp_drop_gt_40_duration_minutes": 15, "hypotension_resolved_after_fluid": False,
    "hypoperfusion_or_end_organ_damage": True, "lactate_mmol_l": 2,
    "acute_kidney_dysfunction": False, "urine_output_ml_kg_h": 0.5,
    "altered_mental_status": False, "cardiac_index_l_min_m2": 2.2,
    "mean_arterial_pressure_mmhg": 60,
    "recurrent_or_persistent_hypotension": False, "cardiogenic_shock": False,
    "refractory_cardiogenic_shock": False, "cardiac_arrest": False,
    "no_rosc_after_30_minutes": False, "respiratory_rate_bpm": 29,
    "oxygen_required": False, "nasal_cannula_flow_l_min": 6,
    "face_mask_oxygen": False, "noninvasive_ventilation": False,
    "invasive_mechanical_ventilation": False,
}


def missing_fact() -> dict:
    return {"value": None, "mentioned": False, "evidence": None}


def present_fact(value) -> dict:
    return {"value": value, "mentioned": True, "evidence": "测试病历证据"}


def case_json(*missing: str, **values) -> str:
    """创建确定性基线，并按需把指定字段改为真正缺失。"""

    case = {name: present_fact(value) for name, value in SAFE_VALUES.items()}
    for name in missing:
        case[name] = missing_fact()
    for name, value in values.items():
        case[name] = present_fact(value)
    return json.dumps(case, ensure_ascii=False)


def outputs(payload: str) -> set[tuple[str, bool]]:
    return {(item["grade"], item["has_r"]) for item in classify(payload)["results"]}


class JsonSchemaTests(unittest.TestCase):
    def test_schema_validation_is_preserved(self) -> None:
        with self.assertRaisesRegex(TypeError, "JSON字符串"):
            classify({})  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "合法JSON"):
            classify("{invalid}")
        with self.assertRaisesRegex(ValueError, "缺少输入变量"):
            classify("{}")

    def test_unmentioned_fact_must_be_null(self) -> None:
        case = json.loads(case_json())
        case["age_years"] = {"value": 85, "mentioned": False, "evidence": None}
        with self.assertRaisesRegex(ValueError, "必须为null"):
            classify(json.dumps(case))

    def test_removed_scai_field_is_rejected_as_unknown(self) -> None:
        case = json.loads(case_json())
        case["scai_shock_stage"] = present_fact("B")
        with self.assertRaisesRegex(ValueError, "未知输入变量"):
            classify(json.dumps(case))


class DeterministicCompatibilityTests(unittest.TestCase):
    def assert_only(self, expected: tuple[str, bool], **values) -> None:
        self.assertEqual(outputs(case_json(**values)), {expected})

    def test_priority_and_major_rules(self) -> None:
        self.assert_only(("E2", False), refractory_cardiogenic_shock=True)
        self.assert_only(("E2", True), cardiac_arrest=True, no_rosc_after_30_minutes=True, invasive_mechanical_ventilation=True)
        self.assert_only(("E1", False), recurrent_or_persistent_hypotension=True, cardiogenic_shock=True)
        self.assert_only(("D2", False), lactate_mmol_l=2.1)
        self.assert_only(("D1", False), hypotension_systolic_bp_mmhg=85, sbp_below_90_duration_minutes=10, hypoperfusion_or_end_organ_damage=False)
        self.assert_only(("A", False), incidental_finding=True, asymptomatic=True)

    def test_boundaries_and_subgrades(self) -> None:
        self.assert_only(("B1", False))
        self.assert_only(("B2", False), highest_thrombus_location="non_subsegmental")
        self.assert_only(("C1", False), age_years=81)
        self.assert_only(("C2", False), age_years=81, rv_abnormal=True)
        self.assert_only(("C3", False), age_years=81, rv_abnormal=True, cardiac_biomarker_abnormal=True)
        self.assert_only(("C1", True), age_years=81, respiratory_rate_bpm=30)

    def test_priority_remains_deterministic(self) -> None:
        self.assert_only(("E2", False), refractory_cardiogenic_shock=True, recurrent_or_persistent_hypotension=True, cardiogenic_shock=True, lactate_mmol_l=3)

    def test_a_is_exclusive_and_has_priority_over_edbc(self) -> None:
        self.assert_only(
            ("A", False),
            incidental_finding=True,
            asymptomatic=True,
            refractory_cardiogenic_shock=True,
            lactate_mmol_l=3,
        )


class MissingValuePossibilityTests(unittest.TestCase):
    def test_missing_age_branches_only_at_spesi_boundary(self) -> None:
        self.assertEqual(outputs(case_json("age_years")), {("B1", False), ("C1", False)})

    def test_missing_d2_fields_collapse_to_two_rule_states(self) -> None:
        fields = ("lactate_mmol_l", "acute_kidney_dysfunction", "urine_output_ml_kg_h", "altered_mental_status", "cardiac_index_l_min_m2", "mean_arterial_pressure_mmhg")
        self.assertEqual(outputs(case_json(*fields)), {("D2", False), ("B1", False)})

    def test_explicit_true_d2_eliminates_false_branch(self) -> None:
        self.assertEqual(outputs(case_json("acute_kidney_dysfunction", lactate_mmol_l=3)), {("D2", False)})

    def test_missing_location_returns_concrete_b_subgrades(self) -> None:
        self.assertEqual(outputs(case_json("highest_thrombus_location")), {("B1", False), ("B2", False)})

    def test_missing_r_returns_both_r_states_for_d(self) -> None:
        self.assertEqual(outputs(case_json("face_mask_oxygen", lactate_mmol_l=3)), {("D2", False), ("D2", True)})

    def test_spo2_correlation_does_not_create_impossible_c_without_r(self) -> None:
        self.assertEqual(outputs(case_json("spo2_percent")), {("B1", False), ("C1", True)})

    def test_missing_rv_and_biomarker_produce_three_not_four_subgrades(self) -> None:
        self.assertEqual(outputs(case_json("rv_abnormal", "cardiac_biomarker_abnormal", age_years=81)), {("C1", False), ("C2", False), ("C3", False)})

    def test_all_missing_produces_17_distinct_outputs_quickly(self) -> None:
        payload = json.dumps({name: missing_fact() for name in FIELD_SPECS})
        started = time.perf_counter()
        result = classify(payload)["results"]
        elapsed = time.perf_counter() - started
        self.assertEqual(len(result), 17)
        self.assertEqual(len({(item["grade"], item["has_r"]) for item in result}), 17)
        self.assertLess(elapsed, 0.1)

    def test_result_order_is_stable(self) -> None:
        payload = json.dumps({name: missing_fact() for name in FIELD_SPECS})
        grades = [(item["grade"], item["has_r"]) for item in classify(payload)["results"]]
        self.assertEqual(grades[:3], [("A", False), ("E2", False), ("E2", True)])
        self.assertLess(grades.index(("C1", False)), grades.index(("B1", False)))

    def test_missing_a_condition_keeps_a_and_edbc_paths(self) -> None:
        self.assertEqual(
            outputs(case_json("asymptomatic", incidental_finding=True, lactate_mmol_l=3)),
            {("A", False), ("D2", False)},
        )


if __name__ == "__main__":
    unittest.main()
