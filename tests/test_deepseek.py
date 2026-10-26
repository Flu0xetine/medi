"""DeepSeek 适配器的本地测试；不会发送网络请求或消耗 API 额度。"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from medi.grading import FIELD_SPECS
from medi.grading.field_registry import SHARED_EXTRACTION_RULES
from medi.workflow.deepseek import (
    DeepSeekClient, DeepSeekExtractor, DeepSeekReviewer, FIELD_DESCRIPTIONS,
)
from medi.workflow.deepseek.prompts import extraction_system_prompt, review_system_prompt
from medi.workflow.deepseek.validation import validate_review_result


class RecordingCompletions:
    """记录SDK调用参数，并返回预先准备的DeepSeek式响应。"""

    def __init__(self, response_json: dict) -> None:
        self.response_json = response_json
        self.last_request: dict | None = None

    def create(self, **kwargs):
        self.last_request = kwargs
        message = SimpleNamespace(content=json.dumps(self.response_json))
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class RecordingClient:
    def __init__(self, response_json: dict) -> None:
        completions = RecordingCompletions(response_json)
        self.chat = SimpleNamespace(completions=completions)


class DeepSeekAdapterTests(unittest.TestCase):
    def test_prompts_describe_absence_false_without_source_quote(self) -> None:
        for prompt in (extraction_system_prompt(), review_system_prompt()):
            self.assertIn("value=false、mentioned=true、evidence=null", prompt)
            self.assertIn("仅限明确配置的字段", prompt)
        prompt = extraction_system_prompt()
        self.assertIn('"oxygen_required": {"value": false, "mentioned": true, "evidence": null}', prompt)
        self.assertIn('"male_sex": {"value": null, "mentioned": false, "evidence": null}', prompt)
    def test_sex_hint_does_not_assert_sex_is_always_recorded(self) -> None:
        self.assertNotIn("性别一定会明确记载", extraction_system_prompt())

    def test_extractor_uses_shared_prompt_builder(self) -> None:
        client = RecordingClient({})
        DeepSeekExtractor(DeepSeekClient(client=client))({"medical_record": "测试病历"})
        sent = client.chat.completions.last_request["messages"][0]["content"]
        self.assertEqual(sent, extraction_system_prompt())

    def test_review_validation_rejects_empty_issues_when_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "issues不能为空"):
            validate_review_result({"approved": False, "issues": []})

    def test_prompt_descriptions_match_runtime_fields(self) -> None:
        self.assertEqual(set(FIELD_DESCRIPTIONS), set(FIELD_SPECS))
        self.assertTrue(all(
            FIELD_DESCRIPTIONS[name] == spec.extraction_hint
            for name, spec in FIELD_SPECS.items()
        ))

    def test_revised_boolean_hints_do_not_request_null_values(self) -> None:
        """布尔值缺失由通用事实契约表达，不由字段提示词输出 null。"""

        for name in ("hypotension_recovered", "rv_abnormal", "cardiac_biomarker_abnormal"):
            with self.subTest(field=name):
                self.assertNotIn("null", FIELD_DESCRIPTIONS[name].lower())
        self.assertIn("未提及右心室游离壁运动减弱", FIELD_DESCRIPTIONS["rv_abnormal"])
        self.assertIn("氧气吸入", FIELD_DESCRIPTIONS["oxygen_required"])

    def test_extraction_prompt_marks_recurrent_hypotension_as_not_recovered(self) -> None:
        """提取请求须说明恢复后复发时，可恢复事实为 false。"""

        client = RecordingClient({})
        DeepSeekExtractor(DeepSeekClient(client=client))({"medical_record": "测试病历"})  # type: ignore[arg-type]
        system_prompt = client.chat.completions.last_request["messages"][0]["content"]
        self.assertIn("恢复后再次发生低血压", system_prompt)
        self.assertIn("即使每次持续时间均短于15分钟", system_prompt)

    def test_recurrence_fact_hint_is_shared_by_extractor_and_reviewer(self) -> None:
        name = "hypotension_recurred_after_recovery"
        self.assertIn(name, FIELD_SPECS)
        hint = FIELD_SPECS[name].extraction_hint
        self.assertIn("随后再次发生低血压", hint)
        self.assertIn("随后未再发生低血压", hint)
        self.assertIn("或者患者未曾发生过低血压", hint)
        self.assertIn("缺乏足够信息判断恢复后是否再次发生低血压", hint)
        self.assertNotIn("null", hint.lower())
        self.assertIsNone(FIELD_SPECS[name].missing_default)
        self.assertIn(hint, extraction_system_prompt())
        self.assertIn(hint, review_system_prompt())

    def test_extractor_and_reviewer_share_registry_contract(self) -> None:
        """提示词只从注册表生成，共同提取规则各出现一次。"""

        for response, invoke in (
            ({}, lambda api: DeepSeekExtractor(api)({"medical_record": "测试病历"})),
            ({"approved": True, "issues": []}, lambda api: DeepSeekReviewer(api)({
                "medical_record": "测试病历", "extracted_facts": {}, "revision_count": 0,
            })),
        ):
            with self.subTest(response=response):
                client = RecordingClient(response)
                invoke(DeepSeekClient(client=client))  # type: ignore[arg-type]
                system_prompt = client.chat.completions.last_request["messages"][0]["content"]
                self.assertEqual(system_prompt.count(SHARED_EXTRACTION_RULES["paired_blood_pressure"]), 1)
                for name, spec in FIELD_SPECS.items():
                    self.assertIn(f"- {name}（", system_prompt)
                    self.assertIn(spec.extraction_hint, system_prompt)

    def test_json_mode_and_deepseek_model_are_sent_to_sdk(self) -> None:
        client = RecordingClient({"ok": True})
        api = DeepSeekClient(client=client)  # type: ignore[arg-type]

        result = api.json_completion("输出JSON", "测试")

        request = client.chat.completions.last_request
        self.assertEqual(result, {"ok": True})
        self.assertEqual(request["model"], "deepseek-v4-flash")
        self.assertEqual(request["response_format"], {"type": "json_object"})
        self.assertFalse(request["stream"])

    def test_reviewer_validates_structured_review_result(self) -> None:
        client = RecordingClient({"approved": True, "issues": []})
        reviewer = DeepSeekReviewer(
            DeepSeekClient(client=client)  # type: ignore[arg-type]
        )

        result = reviewer(
            {
                "medical_record": "测试病历",
                "extracted_facts": {},
                "revision_count": 0,
            }
        )

        self.assertEqual(result, {"approved": True, "issues": []})


if __name__ == "__main__":
    unittest.main()
