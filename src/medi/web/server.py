"""本地医生工作台与规则实验页的 FastAPI 入口。"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from medi.grading import classify
from medi.grading.decision_tree import rule_tree
from medi.grading.engine import classify_with_trace
from medi.workflow import analyze_medical_record
from medi.workflow.deepseek import create_deepseek_agents

from .config import frontend_config
from .pdf_text import MAX_PDF_BYTES, PDFTextError, extract_pdf_text

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(agent_factory: Callable = create_deepseek_agents) -> FastAPI:
    """装配路由；延迟创建 LLM Agent，页面与手工规则不依赖密钥。

    完整伪代码：
        注册医生页、规则实验页和字段配置读取
        将手工 JSON 交给原规则引擎
        将 PDF 交给文本/OCR 适配器，并返回可编辑文本
        将病历文本交给提取-审核-规则工作流，返回事实及全部等级
        将人工修改后的事实直接交给规则引擎，不调用 LLM
        工作台按需取得完整判断树和与事实一致的可能路径
        所有输入错误转换为清晰的响应
    """

    app = FastAPI(title="Medi 本地医生工作台")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def doctor_page() -> str:
        return (STATIC_DIR / "doctor.html").read_text(encoding="utf-8")

    @app.get("/lab", response_class=HTMLResponse)
    def rule_lab() -> str:
        return (STATIC_DIR / "index.html").read_text(encoding="utf-8")

    @app.get("/api/config")
    def config() -> dict:
        return frontend_config()

    @app.get("/api/decision-tree")
    def decision_tree() -> dict:
        return {"tree": rule_tree()}

    @app.post("/api/classify")
    async def classify_payload(request: Request):
        try:
            return classify((await request.body()).decode("utf-8"))
        except (UnicodeError, TypeError, ValueError) as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.post("/api/pdf-text")
    async def pdf_text(file: UploadFile = File(...)) -> dict:
        try:
            data = await file.read(MAX_PDF_BYTES + 1)
            return {"text": await run_in_threadpool(extract_pdf_text, data)}
        except PDFTextError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            await file.close()

    @app.post("/api/analyze")
    def analyze(payload: dict) -> dict:
        record = payload.get("medical_record")
        if not isinstance(record, str) or not record.strip():
            raise HTTPException(status_code=400, detail="病历内容不能为空")
        try:
            extractor, reviewer = agent_factory()
            result = analyze_medical_record(record, extractor, reviewer)
            if result["status"] == "error":
                raise HTTPException(status_code=400, detail=result["error"])
            return result
        except HTTPException:
            raise
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"病历提取或审核失败：{exc}") from exc

    @app.post("/api/reclassify")
    async def reclassify(payload: dict) -> dict:
        try:
            return classify(json.dumps(payload.get("facts"), ensure_ascii=False))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/decision-trace")
    async def decision_trace(payload: dict) -> dict:
        """工作台独立接口；不改变原有分类接口的 JSON 契约。"""

        try:
            return classify_with_trace(json.dumps(payload.get("facts"), ensure_ascii=False))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


app = create_app()


def run(host: str = "127.0.0.1", port: int = 8765) -> None:
    """从项目当前目录读取配置，再启动本地服务。"""

    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
    uvicorn.run(app, host=host, port=port)
