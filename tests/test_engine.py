"""下一版多结果规则引擎测试。"""

import json
import sys
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from medi.grading import FIELD_SPECS, classify
from medi.grading.models import ExtractedFacts


SAFE_VALUES = {
    "incidental_finding": False, "asymptomatic": False, "age_years": 80,
    "cancer_history": False, "male_sex": False, "heart_failure_history": False,
    "chronic_lung_disease": False, "body_temperature_c": 36,
    "systolic_bp_mmhg": 100, "diastolic_bp_mmhg": 80,
    "heart_rate_bpm": 109, "spo2_percent": 90,
    "highest_thrombus_location": "subsegmental_only", "rv_abnormal": False,
    "cardiac_biomarker_abnormal": False,
    "sbp_below_90_duration_minutes": 15, "systolic_bp_drop_mmhg": 40,
    "sbp_drop_gt_40_duration_minutes": 15, "hypotension_recovered": False,
    "hypotension_recurred_after_recovery": False,
    "vasopressor_used": False, "fluid_treatment_given": False,
    "lactate_mmol_l": 2, "acute_kidney_dysfunction": False,
    "altered_mental_status": False, "cold_clammy_extremities": False,
    "recurrent_or_persistent_hypotension": False,
    "refractory_cardiogenic_shock": False,
    "no_rosc_after_30_minutes": False, "respiratory_rate_bpm": 29,
    "oxygen_required": False, "nasal_cannula_over_6_l_min": False,
    "face_mask_oxygen": False, "noninvasive_ventilation": False,
    "invasive_mechanical_ventilation": False,
}

DEFAULT_FALSE_FIELDS = frozenset((
    "vasopressor_used", "fluid_treatment_given", "altered_mental_status",
    "acute_kidney_dysfunction", "cancer_history", "heart_failure_history",
    "chronic_lung_disease", "oxygen_required", "nasal_cannula_over_6_l_min",
    "face_mask_oxygen", "noninvasive_ventilation", "invasive_mechanical_ventilation",
))


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

    def test_pydantic_uses_strict_field_types(self) -> None:
        boolean_case = json.loads(case_json())
        boolean_case["incidental_finding"] = present_fact(1)
        with self.assertRaisesRegex(ValueError, "必须是boolean"):
            classify(json.dumps(boolean_case))

        number_case = json.loads(case_json())
        number_case["age_years"] = present_fact(True)
        with self.assertRaisesRegex(ValueError, "必须是number"):
            classify(json.dumps(number_case))

    def test_pydantic_rejects_blank_evidence(self) -> None:
        case = json.loads(case_json())
        case["age_years"] = {"value": 80, "mentioned": True, "evidence": "   "}
        with self.assertRaisesRegex(ValueError, "非空字符串"):
            classify(json.dumps(case))

    def test_explicit_absence_false_accepts_null_evidence_only_for_opted_in_fields(self) -> None:
        for name, spec in FIELD_SPECS.items():
            if not spec.absence_false:
                continue
            with self.subTest(name=name):
                case = json.loads(case_json())
                case[name] = {"value": False, "mentioned": True, "evidence": None}
                self.assertTrue(classify(json.dumps(case))["results"])
        case = json.loads(case_json())
        case["oxygen_required"] = {"value": False, "mentioned": True, "evidence": None}
        case["oxygen_required"]["value"] = True
        with self.assertRaisesRegex(ValueError, "evidence"):
            classify(json.dumps(case))
        case["oxygen_required"]["value"] = False
        case["male_sex"] = {"value": False, "mentioned": True, "evidence": None}
        with self.assertRaisesRegex(ValueError, "evidence"):
            classify(json.dumps(case))
        case["male_sex"] = present_fact(False)
        case["oxygen_required"]["evidence"] = " "
        with self.assertRaisesRegex(ValueError, "evidence"):
            classify(json.dumps(case))

    def test_pydantic_schema_contains_all_engine_fields(self) -> None:
        schema = ExtractedFacts.model_json_schema()
        self.assertEqual(set(schema["properties"]), set(FIELD_SPECS))
        self.assertEqual(set(schema["required"]), set(FIELD_SPECS))
        self.assertFalse(schema["additionalProperties"])

    def test_recurrence_fact_is_required_and_strict_boolean(self) -> None:
        """新增事实必须进入严格 JSON 契约，而不是只存在于提示词。"""

        name = "hypotension_recurred_after_recovery"
        self.assertIn(name, FIELD_SPECS)
        self.assertIn(name, ExtractedFacts.model_fields)
        case = json.loads(case_json())
        case.pop(name)
        with self.assertRaisesRegex(ValueError, name):
            classify(json.dumps(case))
        case[name] = present_fact(1)
        with self.assertRaisesRegex(ValueError, "必须是boolean"):
            classify(json.dumps(case))
        case[name] = missing_fact()
        self.assertIsNone(ExtractedFacts.model_validate(case).get(name))


class DeterministicCompatibilityTests(unittest.TestCase):
    def assert_only(self, expected: tuple[str, bool], **values) -> None:
        self.assertEqual(outputs(case_json(**values)), {expected})

    def test_priority_and_major_rules(self) -> None:
        self.assert_only(("E2", False), refractory_cardiogenic_shock=True)
        self.assert_only(("E2", True), no_rosc_after_30_minutes=True, invasive_mechanical_ventilation=True)
        self.assert_only(("E1", False), systolic_bp_mmhg=85, recurrent_or_persistent_hypotension=True, lactate_mmol_l=3)
        self.assert_only(("D2", False), lactate_mmol_l=2.1)
        self.assert_only(("D1", False), systolic_bp_mmhg=85, sbp_below_90_duration_minutes=10, hypotension_recovered=True)
        self.assert_only(("A", False), incidental_finding=True, asymptomatic=True)

    def test_boundaries_and_subgrades(self) -> None:
        self.assert_only(("B1", False))
        self.assert_only(("B2", False), highest_thrombus_location="non_subsegmental")
        self.assert_only(("C1", False), age_years=85)
        self.assert_only(("C2", False), age_years=85, rv_abnormal=True)
        self.assert_only(("C3", False), age_years=85, rv_abnormal=True, cardiac_biomarker_abnormal=True)
        self.assert_only(("C1", True), age_years=85, respiratory_rate_bpm=30)

    def test_priority_remains_deterministic(self) -> None:
        self.assert_only(("E2", False), refractory_cardiogenic_shock=True, recurrent_or_persistent_hypotension=True, systolic_bp_mmhg=85, lactate_mmol_l=3)

    def test_a_is_exclusive_and_has_priority_over_edbc(self) -> None:
        self.assert_only(
            ("A", False),
            incidental_finding=True,
            asymptomatic=True,
            refractory_cardiogenic_shock=True,
            lactate_mmol_l=3,
        )

    def test_new_flow_branches_and_thresholds(self) -> None:
        self.assert_only(("D0", False), vasopressor_used=True)
        self.assert_only(("D0", False), fluid_treatment_given=True, face_mask_oxygen=True)
        self.assert_only(("D2", False), fluid_treatment_given=True, lactate_mmol_l=3)
        self.assert_only(("D2", False), diastolic_bp_mmhg=39)
        self.assert_only(("D2", False), acute_kidney_dysfunction=True)
        self.assert_only(("D2", False), cold_clammy_extremities=True)
        self.assert_only(("D2", False), systolic_bp_mmhg=85,
                         cold_clammy_extremities=True, recurrent_or_persistent_hypotension=False)
        self.assert_only(("D2", False), systolic_bp_mmhg=85,
                         lactate_mmol_l=3, recurrent_or_persistent_hypotension=False)
        self.assert_only(("D1", False), systolic_bp_drop_mmhg=41, sbp_drop_gt_40_duration_minutes=14, hypotension_recovered=True)
        self.assert_only(("D1", False), systolic_bp_mmhg=85, sbp_below_90_duration_minutes=15, hypotension_recovered=True)
        self.assert_only(("D1", False), systolic_bp_mmhg=85, sbp_below_90_duration_minutes=10, hypotension_recovered=False)
        self.assert_only(("D0", False), systolic_bp_mmhg=85, sbp_below_90_duration_minutes=15, hypotension_recovered=False)
        self.assert_only(("D0", False), systolic_bp_mmhg=85, sbp_below_90_duration_minutes=10, systolic_bp_drop_mmhg=41, sbp_drop_gt_40_duration_minutes=20, hypotension_recovered=False)
        self.assert_only(("D1", False), vasopressor_used=True, hypotension_recovered=True)
        self.assert_only(("E1", False), fluid_treatment_given=True, lactate_mmol_l=3,
                         recurrent_or_persistent_hypotension=True)

    def test_threshold_equalities_do_not_trigger(self) -> None:
        self.assert_only(("C1", False), age_years=85, lactate_mmol_l=2,
                         systolic_bp_mmhg=90, diastolic_bp_mmhg=45,
                         systolic_bp_drop_mmhg=40)

    def test_confirmed_relapse_excludes_short_episode_from_d1(self) -> None:
        self.assert_only(
            ("D0", False), systolic_bp_mmhg=85,
            sbp_below_90_duration_minutes=10,
            hypotension_recovered=False,
            hypotension_recurred_after_recovery=True,
            face_mask_oxygen=True,
        )

    def test_confirmed_relapse_excludes_recovered_candidate_from_d1(self) -> None:
        self.assert_only(
            ("D0", False), systolic_bp_mmhg=85,
            sbp_below_90_duration_minutes=15,
            hypotension_recovered=True,
            hypotension_recurred_after_recovery=True,
        )

    def test_no_relapse_preserves_d1_with_d_r(self) -> None:
        self.assert_only(
            ("D1", True), systolic_bp_mmhg=85,
            sbp_below_90_duration_minutes=10,
            hypotension_recurred_after_recovery=False,
            face_mask_oxygen=True,
        )

    def test_relapse_fact_does_not_affect_e1_d2_or_existing_d0(self) -> None:
        self.assert_only(("D0", False), vasopressor_used=True,
                         hypotension_recurred_after_recovery=True)
        self.assert_only(("D2", False), systolic_bp_mmhg=85, lactate_mmol_l=3,
                         hypotension_recurred_after_recovery=True)
        self.assert_only(("E1", False), systolic_bp_mmhg=85, lactate_mmol_l=3,
                         recurrent_or_persistent_hypotension=True,
                         hypotension_recurred_after_recovery=False)

    def test_old_fields_are_rejected(self) -> None:
        case = json.loads(case_json())
        case["cardiogenic_shock"] = present_fact(False)
        with self.assertRaisesRegex(ValueError, "未知输入变量"):
            classify(json.dumps(case))

        case = json.loads(case_json())
        case["cardiac_arrest"] = present_fact(True)
        with self.assertRaisesRegex(ValueError, "未知输入变量"):
            classify(json.dumps(case))


class MissingValuePossibilityTests(unittest.TestCase):
    def test_documented_defaults_affect_effective_values_not_source_facts(self) -> None:
        self.assertEqual(
            {name for name, spec in FIELD_SPECS.items() if spec.missing_default is not None},
            DEFAULT_FALSE_FIELDS,
        )
        facts = ExtractedFacts.model_validate({name: missing_fact() for name in FIELD_SPECS})
        for name in DEFAULT_FALSE_FIELDS:
            with self.subTest(field=name):
                self.assertEqual(getattr(facts, name).model_dump(), missing_fact())
                self.assertIs(facts.get(name), False)
        self.assertIsNone(facts.get("age_years"))

    def test_explicit_true_overrides_each_false_default(self) -> None:
        for name in DEFAULT_FALSE_FIELDS:
            with self.subTest(field=name):
                case = json.loads(case_json(name))
                case[name] = present_fact(True)
                self.assertIs(ExtractedFacts.model_validate(case).get(name), True)

    def test_missing_configured_defaults_do_not_expand_rule_paths(self) -> None:
        self.assertEqual(outputs(case_json("vasopressor_used")), {("B1", False)})
        self.assertEqual(outputs(case_json("fluid_treatment_given")), {("B1", False)})
        self.assertEqual(outputs(case_json("acute_kidney_dysfunction")), {("B1", False)})
        self.assertEqual(outputs(case_json("altered_mental_status")), {("B1", False)})
        self.assertEqual(outputs(case_json("cancer_history")), {("B1", False)})
        self.assertEqual(outputs(case_json("oxygen_required", age_years=85)), {("C1", False)})
        self.assertEqual(outputs(case_json("face_mask_oxygen", lactate_mmol_l=3)), {("D2", False)})
        self.assertEqual(outputs(case_json("noninvasive_ventilation", refractory_cardiogenic_shock=True)), {("E2", False)})

    def test_missing_relapse_keeps_d1_and_d0_with_separate_r(self) -> None:
        self.assertEqual(
            outputs(case_json(
                "hypotension_recurred_after_recovery",
                systolic_bp_mmhg=85,
                sbp_below_90_duration_minutes=10,
                face_mask_oxygen=True,
            )),
            {("D1", True), ("D0", False)},
        )

    def test_missing_relapse_does_not_create_d1_without_candidate(self) -> None:
        self.assertEqual(
            outputs(case_json("hypotension_recurred_after_recovery", vasopressor_used=True)),
            {("D0", False)},
        )

    def test_registry_default_applies_without_rewriting_missing_fact(self) -> None:
        age_spec = FIELD_SPECS["age_years"]
        with patch.dict(FIELD_SPECS, {"age_years": replace(age_spec, missing_default=85)}):
            facts = ExtractedFacts.model_validate_json(case_json("age_years"))
            self.assertIsNone(facts.age_years.value)
            self.assertFalse(facts.age_years.mentioned)
            self.assertEqual(facts.get("age_years"), 85)
            self.assertEqual(outputs(case_json("age_years")), {("C1", False)})
            self.assertEqual(outputs(case_json(age_years=80)), {("B1", False)})

    def test_missing_complete_arrest_condition_keeps_e2_and_lower_path(self) -> None:
        self.assertEqual(outputs(case_json("no_rosc_after_30_minutes")),
                         {("E2", False), ("B1", False)})

    def test_missing_age_branches_only_at_pesi_boundary(self) -> None:
        self.assertEqual(outputs(case_json("age_years")), {("B1", False), ("C1", False)})

    def test_missing_d2_fields_collapse_to_two_rule_states(self) -> None:
        fields = ("lactate_mmol_l", "acute_kidney_dysfunction", "altered_mental_status",
                  "diastolic_bp_mmhg", "cold_clammy_extremities")
        self.assertEqual(outputs(case_json(*fields)), {("D2", False), ("B1", False)})

    def test_missing_treatment_uses_false_default(self) -> None:
        self.assertEqual(outputs(case_json("vasopressor_used")),
                         {("B1", False)})

    def test_missing_hypotension_and_duration_share_one_path(self) -> None:
        self.assertEqual(outputs(case_json("systolic_bp_mmhg",
                                           sbp_below_90_duration_minutes=10,
                                           hypotension_recovered=True)),
                         {("D2", False), ("D1", False), ("C1", False), ("B1", False)})
        self.assertEqual(outputs(case_json("sbp_below_90_duration_minutes",
                                           systolic_bp_mmhg=85,
                                           hypotension_recovered=True)),
                         {("D1", False)})

    def test_explicit_true_d2_eliminates_false_branch(self) -> None:
        self.assertEqual(outputs(case_json("acute_kidney_dysfunction", lactate_mmol_l=3)), {("D2", False)})

    def test_missing_location_returns_concrete_b_subgrades(self) -> None:
        self.assertEqual(outputs(case_json("highest_thrombus_location")), {("B1", False), ("B2", False)})

    def test_missing_nondefault_r_fact_keeps_both_c_r_states(self) -> None:
        self.assertEqual(outputs(case_json("spo2_percent", age_years=85)), {("C1", False), ("C1", True)})

    def test_d_r_uses_boolean_nasal_cannula_threshold(self) -> None:
        self.assertEqual(outputs(case_json(lactate_mmol_l=3,
                                           nasal_cannula_over_6_l_min=True)),
                         {("D2", True)})
        self.assertEqual(outputs(case_json("nasal_cannula_over_6_l_min",
                                           lactate_mmol_l=3)),
                         {("D2", False)})

    def test_spo2_correlation_does_not_create_impossible_c_without_r(self) -> None:
        self.assertEqual(outputs(case_json("spo2_percent")), {("B1", False), ("C1", True)})

    def test_missing_rv_and_biomarker_produce_three_not_four_subgrades(self) -> None:
        self.assertEqual(outputs(case_json("rv_abnormal", "cardiac_biomarker_abnormal", age_years=86)), {("C1", False), ("C2", False), ("C3", False)})

    def test_all_missing_produces_only_default_consistent_outputs_quickly(self) -> None:
        payload = json.dumps({name: missing_fact() for name in FIELD_SPECS})
        started = time.perf_counter()
        result = classify(payload)["results"]
        elapsed = time.perf_counter() - started
        actual = {(item["grade"], item["has_r"]) for item in result}
        expected = {
            ("A", False), ("E2", False), ("E1", False), ("D2", False),
            ("D1", False), ("D0", False), ("B1", False), ("B2", False),
            ("C1", False), ("C1", True), ("C2", False), ("C2", True),
            ("C3", False), ("C3", True),
        }
        self.assertEqual(actual, expected)
        self.assertEqual(len(result), len(expected))
        self.assertLess(elapsed, 0.1)

    def test_result_order_is_stable(self) -> None:
        payload = json.dumps({name: missing_fact() for name in FIELD_SPECS})
        grades = [(item["grade"], item["has_r"]) for item in classify(payload)["results"]]
        self.assertEqual(grades[:3], [("A", False), ("E2", False), ("E1", False)])
        self.assertLess(grades.index(("C1", False)), grades.index(("B1", False)))

    def test_missing_a_condition_keeps_a_and_edbc_paths(self) -> None:
        self.assertEqual(
            outputs(case_json("asymptomatic", incidental_finding=True, lactate_mmol_l=3)),
            {("A", False), ("D2", False)},
        )


if __name__ == "__main__":
    unittest.main()
