"""LangGraph 分级工作流测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ae_grading import FIELD_SPECS
from ae_workflow import build_grading_graph, grade_medical_record


def complete_facts(**present_values) -> dict:
    """生成所有条件均明确的确定性测试事实表。"""

    safe_numbers = {
        "age_years": 80, "spesi_systolic_bp_mmhg": 100, "heart_rate_bpm": 109,
        "spo2_percent": 90, "hypotension_systolic_bp_mmhg": 90,
        "sbp_below_90_duration_minutes": 15, "systolic_bp_drop_mmhg": 40,
        "sbp_drop_gt_40_duration_minutes": 15, "lactate_mmol_l": 2,
        "urine_output_ml_kg_h": 0.5, "cardiac_index_l_min_m2": 2.2,
        "mean_arterial_pressure_mmhg": 60, "respiratory_rate_bpm": 29,
        "nasal_cannula_flow_l_min": 6,
    }
    values = {}
    for name, spec in FIELD_SPECS.items():
        if spec.value_type == "boolean":
            values[name] = False
        elif spec.value_type == "enum":
            values[name] = spec.allowed_values[0]
        else:
            values[name] = safe_numbers[name]
    # 明确存在低灌注可稳定排除 D1 基线路径。
    values["hypoperfusion_or_end_organ_damage"] = True
    values.update(present_values)
    facts = {}
    for name, value in values.items():
        facts[name] = {
            "value": value,
            "mentioned": True,
            "evidence": f"{name}的测试证据",
        }
    return facts


class SequenceExtractor:
    """按顺序返回预设事实表的假提取 Agent。"""

    def __init__(self, outputs: list[dict]) -> None:
        self.outputs = outputs
        self.requests: list[dict] = []

    def __call__(self, request: dict) -> dict:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.outputs) - 1)
        return self.outputs[index]


class SequenceReviewer:
    """按顺序返回预设结论的假审核 Agent。"""

    def __init__(self, approvals: list[bool]) -> None:
        self.approvals = approvals
        self.requests: list[dict] = []

    def __call__(self, request: dict) -> dict:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.approvals) - 1)
        approved = self.approvals[index]
        return {
            "approved": approved,
            "issues": []
            if approved
            else [
                {
                    "field": "age_years",
                    "issue_type": "test_issue",
                    "reason": "测试审核问题",
                    "suggestion": "请重新核对",
                }
            ],
        }


class WorkflowTests(unittest.TestCase):
    def test_approved_extraction_goes_directly_to_engine(self) -> None:
        extractor = SequenceExtractor([complete_facts(age_years=81)])
        reviewer = SequenceReviewer([True])

        result = grade_medical_record("测试病历", extractor, reviewer)

        self.assertEqual(
            result,
            {"status": "completed", "results": [{"grade": "C1", "has_r": False}]},
        )
        self.assertEqual(len(extractor.requests), 1)
        self.assertEqual(len(reviewer.requests), 1)

    def test_rejected_extraction_can_be_revised_three_times(self) -> None:
        extractor = SequenceExtractor([complete_facts()] * 4)
        reviewer = SequenceReviewer([False] * 4)

        graph = build_grading_graph(extractor, reviewer)
        final_state = graph.invoke(
            {"medical_record": "测试病历", "revision_count": 0}
        )

        # 首次提取 + 三次修正，共调用提取和审核各四次。
        self.assertEqual(len(extractor.requests), 4)
        self.assertEqual(len(reviewer.requests), 4)
        self.assertEqual(final_state["revision_count"], 3)
        # 最终审核仍未通过，但规则引擎成功，所以直接输出等级。
        self.assertEqual(
            final_state["final_output"],
            {"status": "completed", "results": [{"grade": "B1", "has_r": False}]},
        )

    def test_revision_receives_previous_facts_and_review_feedback(self) -> None:
        first = complete_facts(age_years=36)
        corrected = complete_facts(age_years=63)
        extractor = SequenceExtractor([first, corrected])
        reviewer = SequenceReviewer([False, True])

        result = grade_medical_record("患者63岁", extractor, reviewer)

        self.assertEqual(result["status"], "completed")
        revision_request = extractor.requests[1]
        self.assertEqual(revision_request["previous_facts"], first)
        self.assertFalse(revision_request["review_feedback"]["approved"])
        self.assertEqual(revision_request["revision_count"], 1)

    def test_engine_error_is_returned_directly(self) -> None:
        extractor = SequenceExtractor([{}])
        reviewer = SequenceReviewer([True])

        result = grade_medical_record("测试病历", extractor, reviewer)

        self.assertEqual(result["status"], "error")
        self.assertIn("缺少输入变量", result["error"])


if __name__ == "__main__":
    unittest.main()
