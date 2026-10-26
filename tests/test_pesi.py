"""PESI 权重、边界及共享事实相关性的回归测试。"""

import itertools
import json
import random
import unittest

from medi.grading.models import ExtractedFacts
from medi.grading.pesi import score_bounds
from test_engine import DEFAULT_FALSE_FIELDS, SAFE_VALUES, case_json, outputs


class PesiTests(unittest.TestCase):
    def test_all_weights_and_thresholds(self):
        # 预期分值独立于生产代码中的权重表。
        items = (
            ("male_sex", False, True, 10),
            ("cancer_history", False, True, 30),
            ("heart_failure_history", False, True, 10),
            ("chronic_lung_disease", False, True, 10),
            ("heart_rate_bpm", 109, 110, 20),
            ("systolic_bp_mmhg", 100, 99, 30),
            ("respiratory_rate_bpm", 29, 30, 20),
            ("body_temperature_c", 36, 35.9, 20),
            ("altered_mental_status", False, True, 60),
            ("spo2_percent", 90, 89, 20),
        )
        all_positive = {"age_years": 50}
        for field, negative, positive, points in items:
            for value, extra in ((negative, 0), (positive, points)):
                with self.subTest(field=field, value=value):
                    facts = ExtractedFacts.model_validate_json(
                        case_json(age_years=50, **{field: value})
                    )
                    self.assertEqual(score_bounds(facts), (50 + extra, 50 + extra))
            all_positive[field] = positive
        facts = ExtractedFacts.model_validate_json(case_json(**all_positive))
        self.assertEqual(score_bounds(facts), (280, 280))

    def test_85_boundary_and_weighted_sum(self):
        cases = (
            ({"age_years": 85}, "C1"),
            ({"age_years": 85.5}, "C1"),
            ({"age_years": 86}, "C1"),
            ({"age_years": 75, "male_sex": True}, "C1"),
            ({"age_years": 76, "male_sex": True}, "C1"),
            ({"age_years": 45, "male_sex": True, "cancer_history": True}, "C1"),
            ({"age_years": 46, "male_sex": True, "cancer_history": True}, "C1"),
        )
        for values, grade in cases:
            with self.subTest(values=values):
                self.assertEqual(outputs(case_json(**values)), {(grade, False)})

    def test_missing_age_cannot_remove_known_points(self):
        self.assertEqual(
            outputs(case_json(
                "age_years", cancer_history=True, male_sex=True,
                heart_failure_history=True, chronic_lung_disease=True,
                systolic_bp_mmhg=99, heart_rate_bpm=110,
            )),
            {("C1", False)},
        )

    def test_missing_weight_and_low_age_do_not_always_create_c(self):
        self.assertEqual(outputs(case_json("male_sex", age_years=70)), {("B1", False)})
        self.assertEqual(outputs(case_json("male_sex", age_years=80)),
                         {("B1", False), ("C1", False)})

    def test_respiratory_rate_and_spo2_correlations(self):
        for missing in (("respiratory_rate_bpm",), ("spo2_percent",),
                        ("respiratory_rate_bpm", "spo2_percent")):
            with self.subTest(missing=missing):
                self.assertEqual(outputs(case_json(*missing, age_years=80)),
                                 {("B1", False), ("C1", True)})

    def test_mental_status_default_false_and_explicit_true(self):
        self.assertEqual(outputs(case_json("altered_mental_status", age_years=80)),
                         {("B1", False)})
        self.assertEqual(outputs(case_json(altered_mental_status=True, age_years=30)),
                         {("D2", False)})

    def test_age_domain(self):
        from medi.grading import classify
        for age in (-1, float("inf"), float("nan")):
            with self.subTest(age=age), self.assertRaises(ValueError):
                classify(case_json(age_years=age))

    def test_symbolic_results_match_brute_force_oracle(self):
        """用独立逐状态计算验证压缩算法；覆盖跨D2、PESI、R的相关性。"""
        domains = {
            "male_sex": (False, True),
            "cancer_history": (False, True),
            "heart_failure_history": (False, True),
            "chronic_lung_disease": (False, True),
            "heart_rate_bpm": (109, 110),
            "systolic_bp_mmhg": (100, 99),
            "respiratory_rate_bpm": (29, 30),
            "body_temperature_c": (36, 35.9),
            "altered_mental_status": (False, True),
            "spo2_percent": (90, 89),
            "oxygen_required": (False, True),
        }
        rng = random.Random(20260921)
        for _ in range(40):
            values = dict(SAFE_VALUES)
            values["age_years"] = rng.choice((0, 30, 65, 75, 80, 85, 86))
            values.update({field: rng.choice(domain) for field, domain in domains.items()})
            missing = rng.sample(list(domains), 5)
            payload = json.loads(case_json(**values))
            for field in missing:
                payload[field] = {"value": None, "mentioned": False, "evidence": None}
            expected = set()
            completion_domains = {
                **domains,
                # 缺失的收缩压可跨越低血压、MAP 和 PESI 三处边界；
                # 已知值仍由上方的随机样本限定为 99/100，避免无关病例组合。
                "systolic_bp_mmhg": (0, 85, 90, 99, 100),
            }
            # 默认值字段的原始事实仍缺失，但规则只允许默认的 false 状态。
            effective_domains = (
                (False,) if field in DEFAULT_FALSE_FIELDS else completion_domains[field]
                for field in missing
            )
            for completion in itertools.product(*effective_domains):
                v = values | dict(zip(missing, completion))
                hypotension = v["systolic_bp_mmhg"] < 90
                hypoperfusion = (
                    v["altered_mental_status"]
                    or (v["systolic_bp_mmhg"] + 2 * v["diastolic_bp_mmhg"]) / 3 < 60
                )
                if hypotension and hypoperfusion:
                    expected.add(("D2", False))
                    continue
                if hypotension:
                    expected.add(("D0", False))
                    continue
                if hypoperfusion:
                    expected.add(("D2", False))
                    continue
                score = (
                    v["age_years"] + 10 * v["male_sex"] + 30 * v["cancer_history"]
                    + 10 * v["heart_failure_history"] + 10 * v["chronic_lung_disease"]
                    + 20 * (v["heart_rate_bpm"] >= 110)
                    + 30 * (v["systolic_bp_mmhg"] < 100)
                    + 20 * (v["respiratory_rate_bpm"] >= 30)
                    + 20 * (v["body_temperature_c"] < 36)
                    + 60 * v["altered_mental_status"] + 20 * (v["spo2_percent"] < 90)
                )
                has_r = v["spo2_percent"] < 90 or v["respiratory_rate_bpm"] >= 30 or v["oxygen_required"]
                expected.add(("C1", has_r) if score >= 85 else ("B1", False))
            self.assertEqual(outputs(json.dumps(payload)), expected)
