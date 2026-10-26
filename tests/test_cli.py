"""统一命令行入口的行为契约；不触发真实模型请求。"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from medi.cli import main


class CliTests(unittest.TestCase):
    def test_grade_requires_an_explicit_record_path(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(["grade"])
        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(output.getvalue()), {
            "status": "error",
            "error": "请提供病历文件路径，或使用 - 从标准输入读取",
        })

    def test_grade_reads_file_and_emits_completed_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            record = Path(temp) / "record.txt"
            record.write_text("测试病历", encoding="utf-8")
            output = io.StringIO()
            extractor, reviewer = object(), object()
            with (
                patch("medi.cli.create_deepseek_agents", return_value=(extractor, reviewer)) as make,
                patch("medi.cli.grade_medical_record", return_value={"status": "completed", "results": []}) as grade,
                redirect_stdout(output),
            ):
                exit_code = main(["grade", str(record), "--model", "test-model"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(json.loads(output.getvalue()), {"status": "completed", "results": []})
        make.assert_called_once_with(model="test-model")
        grade.assert_called_once_with("测试病历", extractor, reviewer)

    def test_grade_empty_stdin_is_error_json(self) -> None:
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO("  ")), redirect_stdout(output):
            exit_code = main(["grade", "-"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(output.getvalue()), {
            "status": "error", "error": "病历内容不能为空",
        })

    def test_grade_exception_is_error_json(self) -> None:
        output = io.StringIO()
        with (
            patch("sys.stdin", io.StringIO("测试病历")),
            patch("medi.cli.create_deepseek_agents", side_effect=ValueError("密钥无效")),
            redirect_stdout(output),
        ):
            exit_code = main(["grade", "-"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(output.getvalue()), {
            "status": "error", "error": "密钥无效",
        })

    def test_grade_loads_dotenv_from_current_directory_without_overriding_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workdir = Path(temp)
            (workdir / ".env").write_text("DEEPSEEK_API_KEY=from-file\n", encoding="utf-8")
            (workdir / "record.txt").write_text("测试病历", encoding="utf-8")
            previous_cwd = Path.cwd()
            seen_keys: list[str | None] = []

            def fake_agents(*, model: str | None):
                seen_keys.append(os.environ.get("DEEPSEEK_API_KEY"))
                return object(), object()

            try:
                os.chdir(workdir)
                with (
                    patch.dict(os.environ, {"DEEPSEEK_API_KEY": "from-env"}),
                    patch("medi.cli.create_deepseek_agents", side_effect=fake_agents),
                    patch("medi.cli.grade_medical_record", return_value={"status": "completed", "results": []}),
                    redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(main(["grade", "record.txt"]), 0)
                with (
                    patch.dict(os.environ, {}, clear=True),
                    patch("medi.cli.create_deepseek_agents", side_effect=fake_agents),
                    patch("medi.cli.grade_medical_record", return_value={"status": "completed", "results": []}),
                    redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(main(["grade", "record.txt"]), 0)
            finally:
                os.chdir(previous_cwd)

        self.assertEqual(seen_keys, ["from-env", "from-file"])

    def test_web_forwards_host_and_port(self) -> None:
        with patch("medi.cli.run_web") as run:
            self.assertEqual(main(["web", "--host", "localhost", "--port", "9001"]), 0)
        run.assert_called_once_with("localhost", 9001)

    def test_python_module_help_works_outside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, "-m", "medi", "--help"],
                cwd=temp,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("grade", result.stdout)
        self.assertIn("web", result.stdout)


if __name__ == "__main__":
    unittest.main()
