"""网页配置和静态页面测试。"""

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
import pymupdf

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from medi.grading import FIELD_SPECS
from medi.grading.decision_tree import DecisionPath, DecisionStep, resolve_path
from medi.web.config import FIELD_CONFIG, PRESETS, frontend_config
from medi.web.server import create_app
from tests.test_workflow import complete_facts, SequenceExtractor, SequenceReviewer


class WebAppTests(unittest.TestCase):
    def test_http_root_serves_static_page_from_package(self) -> None:
        client = TestClient(create_app())
        self.assertEqual(client.get("/").status_code, 200)
        self.assertIn('id="medical-record"', client.get("/").text)
        self.assertIn('id="case-form"', client.get("/lab").text)

    def test_pdf_upload_and_invalid_file(self) -> None:
        client = TestClient(create_app())
        document = pymupdf.open()
        document.new_page().insert_text((72, 72), "Record 123")
        response = client.post("/api/pdf-text", files={"file": ("record.pdf", document.tobytes(), "application/pdf")})
        self.assertEqual(response.status_code, 200)
        self.assertIn("Record 123", response.json()["text"])
        self.assertEqual(client.post("/api/pdf-text", files={"file": ("bad.pdf", b"bad", "application/pdf")}).status_code, 400)

    def test_analyze_then_reclassify_without_model(self) -> None:
        calls = []
        def agents():
            calls.append(1)
            return SequenceExtractor([complete_facts(age_years=86)]), SequenceReviewer([True])
        client = TestClient(create_app(agent_factory=agents))
        response = client.post("/api/analyze", json={"medical_record": "病例文字"})
        self.assertEqual(response.status_code, 200)
        analysis = response.json()
        self.assertTrue(analysis["review"]["approved"])
        self.assertIn("age_years", analysis["facts"])
        edited = analysis["facts"]
        edited["age_years"] = {"value": 80, "mentioned": True, "evidence": "人工修订"}
        regraded = client.post("/api/reclassify", json={"facts": edited})
        self.assertEqual(regraded.status_code, 200)
        self.assertTrue(regraded.json()["results"])
        self.assertEqual(len(calls), 1)

    def test_analyze_validation_and_legacy_classify(self) -> None:
        client = TestClient(create_app())
        self.assertEqual(client.post("/api/analyze", json={"medical_record": "  "}).status_code, 400)
        self.assertEqual(client.post("/api/classify", content=json.dumps({})).status_code, 400)
        response = client.post("/api/classify", content=json.dumps(complete_facts()))
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.json())

    def test_decision_tree_and_trace_api_keep_old_results_contract(self) -> None:
        client = TestClient(create_app())
        tree = client.get("/api/decision-tree")
        self.assertEqual(tree.status_code, 200)
        self.assertEqual(tree.json()["tree"]["id"], "a")
        self.assertEqual(client.get("/static/doctor.html").status_code, 200)

        facts = complete_facts(age_years=85)
        old = client.post("/api/reclassify", json={"facts": facts})
        traced = client.post("/api/decision-trace", json={"facts": facts})
        self.assertEqual(traced.status_code, 200)
        self.assertEqual(traced.json()["results"], old.json()["results"])
        self.assertNotIn("paths", old.json())
        self.assertNotIn("paths", client.post("/api/classify", content=json.dumps(facts)).json())
        for path in traced.json()["paths"]:
            steps = tuple(DecisionStep(step["node"], step["outcome"])
                          for step in path["steps"])
            self.assertEqual(resolve_path(DecisionPath(path["grade"], path["has_r"], steps)),
                             (path["grade"], path["has_r"]))

    def test_decision_trace_rejects_incomplete_facts(self) -> None:
        response = TestClient(create_app()).post("/api/decision-trace", json={"facts": {}})
        self.assertEqual(response.status_code, 400)
        self.assertIn("缺少输入变量", response.json()["detail"])

    def test_doctor_page_has_review_and_regrade_surfaces(self) -> None:
        page = TestClient(create_app()).get("/").text
        for required in (
            'id="medical-record"', 'id="pdf-file"', 'id="analyze-button"',
            'id="fact-editor"', 'id="regrade-button"', 'id="grade-display"', 'id="rule-tree"',
            'id="tree-result-filter"', 'id="tree-path-filter"',
            "/api/pdf-text", "/api/analyze", "/api/decision-tree",
            "/api/decision-trace", "未提及", "DeepSeek", "可达路径，而非已证实",
            "确定", "可能", 'src="/static/rule_tree.js"',
            "analysisVersion", "version!==analysisVersion",
        ):
            with self.subTest(required=required):
                self.assertTrue(required in page, required)
        self.assertIn('    </div>\n    <section id="facts-panel"', page)
        self.assertIn('#fact-editor { display:grid; grid-template-columns:repeat(2,minmax(0,1fr))', page)

    def test_doctor_page_exposes_tree_zoom_controls(self) -> None:
        page = TestClient(create_app()).get("/").text
        for control in ("tree-zoom-out", "tree-zoom-in", "tree-zoom-fit", "tree-zoom-reset", "tree-zoom-level", "tree-stage"):
            self.assertIn(f'id="{control}"', page)

    def test_doctor_page_exposes_tree_fullscreen_control(self) -> None:
        page = TestClient(create_app()).get("/").text
        self.assertIn('id="rule-tree-panel"', page)
        self.assertIn('id="tree-fullscreen"', page)
        self.assertIn('aria-label="全屏查看判断树"', page)

    def test_config_marks_absence_false_fields_for_editing(self) -> None:
        groups = frontend_config()["groups"]
        fields = {item["name"]: item for group in groups for item in group["fields"]}
        self.assertTrue(fields["oxygen_required"]["absence_false"])
        self.assertFalse(fields["male_sex"]["absence_false"])

    def test_review_issues_are_rendered_as_separate_items(self) -> None:
        page = TestClient(create_app()).get("/").text
        self.assertIn('document.createElement(\'li\')', page)
        self.assertNotIn(".map(issue=>` ${issue.field}: ${issue.reason}`).join('')", page)

    def test_rule_tree_assets_are_served_locally(self) -> None:
        client = TestClient(create_app())
        script = client.get("/static/rule_tree.js")
        style = client.get("/static/rule_tree.css")
        self.assertEqual(script.status_code, 200)
        self.assertEqual(style.status_code, 200)
        self.assertIn("RuleTree", script.text)
        self.assertIn(".tree-branch", style.text)
        self.assertIn(".tree-branches { display:flex;", style.text)
        self.assertIn("align-items:flex-start", style.text)
        self.assertIn(".tree-subtree { display:flex; flex-direction:column; align-items:flex-start", style.text)
        self.assertIn(".tree-branch { position:relative; display:flex; flex-direction:column; align-items:flex-start", style.text)
        self.assertIn(".tree-stage", style.text)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_rule_tree_zoom_keeps_scaled_canvas_scrollable(self) -> None:
        result = subprocess.run(
            ["node", "tests/test_rule_tree_zoom.js"], cwd=PROJECT_ROOT,
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_delayed_tree_load_restores_selected_path(self) -> None:
        result = subprocess.run(
            ["node", "tests/test_rule_tree_ui.js"], cwd=PROJECT_ROOT,
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_tree_layout_balances_large_sibling_subtrees(self) -> None:
        result = subprocess.run(
            ["node", "tests/test_rule_tree_layout.js"], cwd=PROJECT_ROOT,
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_reclassify_rejects_incomplete_facts(self) -> None:
        response = TestClient(create_app()).post("/api/reclassify", json={"facts": {}})
        self.assertEqual(response.status_code, 400)
        self.assertIn("缺少输入变量", response.json()["detail"])

    def test_invalid_model_facts_are_not_success_response(self) -> None:
        def agents():
            return SequenceExtractor([{}]), SequenceReviewer([True])
        response = TestClient(create_app(agent_factory=agents)).post(
            "/api/analyze", json={"medical_record": "病例文字"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("缺少输入变量", response.json()["detail"])

    def test_ui_contains_every_engine_field_once(self) -> None:
        names = [field[0] for group in FIELD_CONFIG.values() for field in group]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set(FIELD_SPECS))

    def test_recurrence_fact_is_available_for_manual_cases(self) -> None:
        group = next(group for group in frontend_config()["groups"]
                     if group["name"] == "第一分流与短暂低血压")
        fields = {field["name"]: field for field in group["fields"]}
        self.assertEqual(fields["hypotension_recurred_after_recovery"]["type"], "boolean")

    def test_ui_field_types_and_units_match_registry(self) -> None:
        for group in frontend_config()["groups"]:
            for field in group["fields"]:
                with self.subTest(field=field["name"]):
                    spec = FIELD_SPECS[field["name"]]
                    self.assertEqual(field["type"], spec.value_type)
                    if spec.value_type == "number":
                        self.assertEqual(field["unit"], spec.unit)
                    elif spec.value_type == "enum":
                        self.assertEqual(set(field["options"]), set(spec.allowed_values))

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
        html = (PROJECT_ROOT / "src" / "medi" / "web" / "static" / "index.html").read_text()
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
        html = (PROJECT_ROOT / "src" / "medi" / "web" / "static" / "index.html").read_text()
        self.assertNotIn('type="checkbox"', html)
        self.assertIn('未选择（病历未提及）', html)


if __name__ == "__main__":
    unittest.main()
