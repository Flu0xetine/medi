# Doctor Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the local web server with FastAPI and add a doctor-facing PDF/text-to-grade workflow with editable facts and a visual grade flow.

**Architecture:** Keep deterministic grading unchanged. Add a PDF text adapter, expose a workflow result with facts through a FastAPI app, and render a new single-page workbench; preserve the legacy rule lab at `/lab`.

**Tech Stack:** Python, FastAPI, Uvicorn, PyMuPDF/Tesseract OCR, native HTML/CSS/JavaScript, unittest.

**Spec:** [Doctor Workbench Design](../specs/2026-10-26-doctor-workbench-design.md)

**Ruling:** PDF 上传后直接分析，依据用户最后明确要求“提取完直接生成”；病历文本仍可修改并重新分析。带大面积扫描图像但仅有页眉文字的页面也需 OCR，防止静默漏读。

## Global Constraints

- Work in `/Users/fluoxetined/Documents/ChatGPT/medi` and preserve all existing dirty changes.
- No clinical grading formula, field prompt, or JSON fact contract changes.
- No durable storage of patient data; retain existing local-only default bind address.
- Do not claim clinical deployability; external DeepSeek transmission and absent protections remain explicit.

## Review Focus

- Text and scanned PDF ingestion, empty/malformed/oversized PDFs, and absent OCR language data.
- Model errors and invalid facts produce clear API errors, not false results.
- Doctor editing retains strict fact schema and reclassifies without LLM calls.
- Multiple possible results remain visible and the flow view does not imply a single certain path.
- Existing rule-lab API and `medi web` command remain usable.

---

### Task 1: PDF ingestion and workflow output

**Files:** `pyproject.toml`, `src/medi/web/pdf_text.py`, `src/medi/workflow/graph.py`, `src/medi/workflow/__init__.py`, `tests/test_pdf_text.py`, `tests/test_workflow.py`.

**Interfaces:** `extract_pdf_text(data: bytes) -> str`; `analyze_medical_record(record, extractor, reviewer) -> dict` returning facts, review, and results.

- [x] Write failing tests for digital PDF, OCR fallback, upload limits, and workflow facts/review exposure.
- [x] Run focused tests and observe the intended failures.
- [x] Implement the adapters without changing `grade_medical_record` output; run focused tests to green.

### Task 2: FastAPI endpoints and compatibility

**Files:** `src/medi/web/server.py`, `src/medi/cli.py`, `tests/test_web_app.py`.

**Interfaces:** `create_app(...) -> FastAPI`, `GET /`, `GET /lab`, `GET /api/config`, `POST /api/classify`, `POST /api/pdf-text`, `POST /api/analyze`, `POST /api/reclassify`.

- [x] Write failing API tests for both pages, existing classify contract, PDF upload, analyze, edit/reclassify, and errors.
- [x] Run focused tests; implement endpoints and `medi web` Uvicorn launch; rerun tests.

### Task 3: Doctor workbench and docs

**Files:** `src/medi/web/static/doctor.html`, `src/medi/web/static/index.html`, `README.md`, `docs/ARCHITECTURE.md`, `docs/README.md`, `tests/test_web_app.py`.

- [x] Write page behavior/surface tests.
- [x] Implement native page with text/PDF input, editable facts, result cards and active-grade flow overview.
- [x] Document prototype limitations and new routes; run full tests and `git diff --check`.

No commits are planned because the designated checkout contains prior uncommitted user changes.
