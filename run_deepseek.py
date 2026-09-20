"""使用真实 DeepSeek Agent 对一份病历执行完整分级流程。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from ae_workflow import grade_medical_record
from ae_workflow.deepseek import create_deepseek_agents


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RECORD = "cases/case3.txt"


def read_medical_record(path: str | None) -> str:
    """从文件读取病历，也允许通过标准输入传入病历。"""

    if path:
        record_path = Path(path)
        # Cursor 从其他工作目录启动时，相对路径仍相对于项目根目录解析。
        if not record_path.is_absolute():
            record_path = PROJECT_ROOT / record_path
        medical_record = record_path.read_text(encoding="utf-8")
    elif sys.stdin.isatty():
        raise ValueError("请提供病历文件路径，或通过标准输入传入病历")
    else:
        medical_record = sys.stdin.read()

    if not medical_record.strip():
        raise ValueError("病历内容不能为空")
    return medical_record


def main() -> int:
    """创建真实 DeepSeek Agent，运行 LangGraph 并打印最终 JSON。"""

    # 从项目根目录的.env读取DEEPSEEK_API_KEY；已有环境变量不会被覆盖。
    load_dotenv()

    parser = argparse.ArgumentParser(description="使用DeepSeek执行A–E病历分级")
    parser.add_argument(
        "record",
        nargs="?",
        default=DEFAULT_RECORD,
        help=f"UTF-8病历文本文件；不填写时默认使用{DEFAULT_RECORD}",
    )
    parser.add_argument(
        "--model",
        help="DeepSeek模型名；默认读取DEEPSEEK_MODEL或使用deepseek-v4-flash",
    )
    args = parser.parse_args()

    try:
        medical_record = read_medical_record(args.record)
        extractor, reviewer = create_deepseek_agents(model=args.model)
        result = grade_medical_record(medical_record, extractor, reviewer)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "completed" else 1
    except Exception as exc:
        print(
            json.dumps(
                {"status": "error", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
