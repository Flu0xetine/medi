"""规则树、路径完整性与确定性标注的回归测试。"""

import json
import time
import unittest

from medi.grading import FIELD_SPECS, classify
from medi.grading.decision_tree import (
    DecisionPath,
    DecisionStep,
    resolve_path,
    rule_tree,
    serialize_paths,
)
from medi.grading.engine import classify_with_trace
from tests.test_engine import case_json, missing_fact


def route(grade: str, has_r: bool, *steps: tuple[str, str]) -> DecisionPath:
    return DecisionPath(grade, has_r, tuple(DecisionStep(*step) for step in steps))


class DecisionTreeTests(unittest.TestCase):
    def test_complete_tree_has_every_terminal_result(self) -> None:
        tree = rule_tree()
        self.assertEqual(tree["id"], "a")
        leaves = []
        nodes = set()

        def visit(node: dict) -> None:
            if "result" in node:
                leaves.append((node["result"]["grade"], node["result"]["has_r"]))
                return
            nodes.add(node["id"])
            for branch in node["branches"]:
                self.assertTrue(branch["label"])
                visit(branch["child"])

        visit(tree)
        self.assertEqual(len(leaves), 21)
        self.assertEqual(set(leaves), {
            ("A", False), ("E2", False), ("E2", True),
            ("E1", False), ("E1", True), ("D2", False), ("D2", True),
            ("D1", False), ("D1", True), ("D0", False),
            ("C1", False), ("C1", True), ("C2", False), ("C2", True),
            ("C3", False), ("C3", True), ("B1", False), ("B2", False),
        })
        self.assertEqual(nodes, {
            "a", "e2", "h", "l_h", "l_no_h", "recurrent",
            "transient_or_recovered", "relapse", "pesi", "c_status",
            "b_location", "e_r", "d_r", "c_r",
        })

    def test_d2_has_two_distinct_valid_routes(self) -> None:
        through_hypotension = route(
            "D2", False, ("a", "no"), ("e2", "no"), ("h", "yes"),
            ("l_h", "yes"), ("recurrent", "no"), ("d_r", "no"),
        )
        through_perfusion = route(
            "D2", False, ("a", "no"), ("e2", "no"), ("h", "no"),
            ("l_no_h", "yes"), ("d_r", "no"),
        )
        self.assertEqual(resolve_path(through_hypotension), ("D2", False))
        self.assertEqual(resolve_path(through_perfusion), ("D2", False))

    def test_mismatched_or_incomplete_path_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            resolve_path(route("D1", False, ("a", "yes")))
        with self.assertRaises(ValueError):
            resolve_path(route("A", False, ("a", "unknown")))
        with self.assertRaises(ValueError):
            resolve_path(route("A", False, ("a", "yes"), ("e2", "no")))

    def test_certainty_uses_all_paths_with_same_prefix(self) -> None:
        a = route("A", False, ("a", "yes"))
        e2 = route("E2", False, ("a", "no"), ("e2", "yes"), ("e_r", "no"))
        actual = serialize_paths((e2, a, e2))
        self.assertEqual(actual, serialize_paths((a, e2)))
        self.assertEqual(len(actual), 2)
        by_grade = {item["grade"]: item for item in actual}
        self.assertEqual(by_grade["A"]["certainty"], "possible")
        self.assertEqual(by_grade["A"]["steps"][0]["certainty"], "possible")
        self.assertEqual([step["certainty"] for step in by_grade["E2"]["steps"]],
                         ["possible", "certain", "certain"])

    def test_tree_response_is_an_independent_copy(self) -> None:
        first = rule_tree()
        first["label"] = "edited"
        self.assertNotEqual(rule_tree()["label"], "edited")

    def test_decision_labels_include_numeric_threshold_units(self) -> None:
        labels = {}

        def collect(node: dict) -> None:
            if "id" not in node:
                return
            labels.setdefault(node["id"], node["label"])
            for branch in node["branches"]:
                collect(branch["child"])

        collect(rule_tree())
        self.assertIn("90 mmHg", labels["h"])
        self.assertIn("40 mmHg", labels["h"])
        self.assertIn("15 分钟", labels["transient_or_recovered"])
        self.assertIn("30 次/分", labels["c_r"])


class TraceIntegrationTests(unittest.TestCase):
    def test_paths_and_old_results_agree_for_major_branches(self) -> None:
        payloads = (
            case_json(incidental_finding=True, asymptomatic=True,
                      refractory_cardiogenic_shock=True),
            case_json(refractory_cardiogenic_shock=True,
                      invasive_mechanical_ventilation=True),
            case_json(systolic_bp_mmhg=85, lactate_mmol_l=3,
                      recurrent_or_persistent_hypotension=True),
            case_json(systolic_bp_mmhg=85, sbp_below_90_duration_minutes=10,
                      hypotension_recurred_after_recovery=True),
            case_json(vasopressor_used=True),
            case_json(age_years=84),
            case_json(age_years=85, rv_abnormal=True,
                      cardiac_biomarker_abnormal=True, oxygen_required=True),
            case_json(highest_thrombus_location="non_subsegmental"),
        )
        for payload in payloads:
            with self.subTest(payload=payload):
                traced = classify_with_trace(payload)
                self.assertEqual(traced["results"], classify(payload)["results"])
                self.assertEqual(
                    {(path["grade"], path["has_r"]) for path in traced["paths"]},
                    {(result["grade"], result["has_r"]) for result in traced["results"]},
                )
                for path in traced["paths"]:
                    steps = tuple(DecisionStep(step["node"], step["outcome"])
                                  for step in path["steps"])
                    self.assertEqual(resolve_path(DecisionPath(path["grade"], path["has_r"], steps)),
                                     (path["grade"], path["has_r"]))

    def test_d2_keeps_both_hypotension_and_no_hypotension_routes(self) -> None:
        traced = classify_with_trace(case_json("systolic_bp_mmhg", lactate_mmol_l=3))
        d2 = [path for path in traced["paths"] if path["grade"] == "D2"]
        self.assertEqual(len(d2), 2)
        self.assertEqual({next(step["outcome"] for step in path["steps"]
                               if step["node"] == "h") for path in d2}, {"yes", "no"})

    def test_d1_recurrence_and_candidate_failures_are_distinct(self) -> None:
        failed = classify_with_trace(case_json(vasopressor_used=True))
        self.assertEqual(failed["paths"][0]["grade"], "D0")
        self.assertIn({"node": "transient_or_recovered", "outcome": "no", "certainty": "certain"},
                      failed["paths"][0]["steps"])
        relapsed = classify_with_trace(case_json(
            systolic_bp_mmhg=85, sbp_below_90_duration_minutes=10,
            hypotension_recurred_after_recovery=True,
        ))
        self.assertEqual(relapsed["paths"][0]["grade"], "D0")
        self.assertIn({"node": "relapse", "outcome": "yes", "certainty": "certain"},
                      relapsed["paths"][0]["steps"])

    def test_missing_values_and_defaults_have_correct_branch_certainty(self) -> None:
        missing_a = classify_with_trace(case_json("asymptomatic", incidental_finding=True))
        self.assertEqual({path["steps"][0]["certainty"] for path in missing_a["paths"]},
                         {"possible"})
        missing_age = classify_with_trace(case_json("age_years"))
        self.assertEqual({path["grade"] for path in missing_age["paths"]}, {"B1", "C1"})
        self.assertEqual({next(step["certainty"] for step in path["steps"]
                               if step["node"] == "pesi") for path in missing_age["paths"]},
                         {"possible"})
        defaulted = classify_with_trace(case_json("vasopressor_used"))
        self.assertEqual({next(step["certainty"] for step in path["steps"]
                               if step["node"] == "h") for path in defaulted["paths"]},
                         {"certain"})

    def test_shared_spo2_only_yields_consistent_pesi_r_paths(self) -> None:
        traced = classify_with_trace(case_json("spo2_percent"))
        self.assertEqual({(path["grade"], path["has_r"]) for path in traced["paths"]},
                         {("B1", False), ("C1", True)})
        self.assertFalse(any(path["grade"] == "C1" and not path["has_r"]
                             for path in traced["paths"]))

    def test_all_missing_paths_remain_compressed(self) -> None:
        payload = json.dumps({name: missing_fact() for name in FIELD_SPECS})
        started = time.perf_counter()
        traced = classify_with_trace(payload)
        self.assertLess(time.perf_counter() - started, 1)
        self.assertLess(len(traced["paths"]), 100)
        self.assertEqual({(path["grade"], path["has_r"]) for path in traced["paths"]},
                         {(item["grade"], item["has_r"]) for item in classify(payload)["results"]})


if __name__ == "__main__":
    unittest.main()
