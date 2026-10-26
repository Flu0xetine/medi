"""安装后统一使用的病历分级与本地网页命令。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from .web.server import run as run_web
from .workflow import grade_medical_record
from .workflow.deepseek import create_deepseek_agents


def _read_medical_record(source: str) -> str:
    """读取明确指定的文件，或在 `-` 时读取标准输入。"""

    record = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    if not record.strip():
        raise ValueError("病历内容不能为空")
    return record


def _grade(record_path: str | None, model: str | None) -> int:
    """运行病历工作流并将完成或错误状态打印成 JSON。

    完整伪代码：
        从当前工作目录读取 .env，但不覆盖已存在的环境变量
        从显式路径或标准输入读取非空病历
        创建提取和审核 Agent，执行工作流
        将结果以 UTF-8 JSON 打印到标准输出
        完成时返回 0，工作流错误或异常时返回 1
    """

    try:
        if record_path is None:
            raise ValueError("请提供病历文件路径，或使用 - 从标准输入读取")
        load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
        medical_record = _read_medical_record(record_path)
        extractor, reviewer = create_deepseek_agents(model=model)
        result = grade_medical_record(medical_record, extractor, reviewer)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "completed" else 1
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


def main(argv: list[str] | None = None) -> int:
    """解析统一子命令并转给相应执行器。

    完整伪代码：
        要求选择 grade 或 web 子命令
        grade 必须收到病例路径，允许 `-` 读取标准输入
        web 使用可选的 host 和 port 启动本地服务器
        返回子命令的进程退出码
    """

    parser = argparse.ArgumentParser(description="A–E 病历分级工具")
    commands = parser.add_subparsers(dest="command", required=True)

    grade_parser = commands.add_parser("grade", help="对 UTF-8 病历执行完整分级工作流")
    grade_parser.add_argument("record", nargs="?", help="病历文件路径；使用 - 从标准输入读取")
    grade_parser.add_argument("--model", help="DeepSeek 模型名；默认读取环境配置")

    web_parser = commands.add_parser("web", help="启动本地医生工作台与规则实验页")
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8765)

    args = parser.parse_args(argv)
    if args.command == "grade":
        return _grade(args.record, args.model)
    run_web(args.host, args.port)
    return 0
