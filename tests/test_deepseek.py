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

from ae_workflow.deepseek import DeepSeekClient, DeepSeekReviewer


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
