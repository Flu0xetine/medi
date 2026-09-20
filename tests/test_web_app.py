"""网页配置和静态页面测试。"""

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ae_grading import FIELD_SPECS
from web_app.config import FIELD_CONFIG, PRESETS, frontend_config


class WebAppTests(unittest.TestCase):
    def test_ui_contains_every_engine_field_once(self) -> None:
        names = [field[0] for group in FIELD_CONFIG.values() for field in group]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set(FIELD_SPECS))

    def test_every_numeric_field_has_random_range(self) -> None:
        for group in frontend_config()["groups"]:
            for field in group["fields"]:
                if field["type"] == "number":
                    with self.subTest(field=field["name"]):
                        self.assertLess(field["min"], field["max"])
                        self.assertGreater(field["step"], 0)
                        self.assertTrue(field["unit"])

    def test_presets_only_reference_known_fields(self) -> None:
        for preset, values in PRESETS.items():
            with self.subTest(preset=preset):
                self.assertFalse(set(values) - set(FIELD_SPECS))

    def test_static_page_has_required_surfaces(self) -> None:
        html = (PROJECT_ROOT / "web_app" / "static" / "index.html").read_text()
        for expected in (
            'id="case-form"',
            'id="classify-button"',
            'id="grade-display"',
            'id="json-preview"',
            'class="random-button"',
            'class="field-json"',
            'class="field-clear"',
        ):
            self.assertIn(expected, html)

    def test_fields_do_not_require_mentioned_checkbox(self) -> None:
        html = (PROJECT_ROOT / "web_app" / "static" / "index.html").read_text()
        self.assertNotIn('type="checkbox"', html)
        self.assertIn('未选择（病历未提及）', html)


if __name__ == "__main__":
    unittest.main()
