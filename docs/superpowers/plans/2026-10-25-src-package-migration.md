# `src/medi` Package Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将三个旧顶层包和两个运行脚本统一迁入可安装的 `src/medi` 包与 `medi` 命令，保持临床与 JSON 行为不变。

**Architecture:** `medi.grading` 保持确定性规则，`medi.workflow` 负责提取/审核编排，`medi.web` 提供本地测试 HTTP 服务。DeepSeek 适配器按 API、提示词、审核校验和 Agent 分层。旧导入和脚本不保留。

**Tech Stack:** Python >=3.10, setuptools, unittest, Pydantic, LangGraph, OpenAI SDK, python-dotenv.

**Spec:** `docs/superpowers/specs/2026-10-25-src-package-migration-design.md`

## Global Constraints

- 在 `/Users/fluoxetined/Documents/ChatGPT/medi` 实施，保留现有未提交内容；不要为迁移覆盖、重置或提交用户修改。
- 临床结果、字段名、运行时默认值、提示词文本、事实 JSON、结果 JSON、审核重试和 HTTP API 均不改变。
- 删除旧导入与根目录运行脚本，公开新入口 `medi.grading`、`medi.workflow`、`medi.workflow.deepseek`、`medi grade`、`medi web`。
- distribution 保持 `ae-grading-engine`；`.env` 从进程当前目录加载且不覆盖已有环境变量。
- `medi grade` 要求路径或 `-` 标准输入，不隐式读取示例病例。

## Review Focus

- 从项目根目录之外运行已安装命令：能读取显式病例路径及当前目录 `.env`；在 Task 3 测试。
- 缺失或空病历输入：仍返回错误 JSON 和退出码 1；在 Task 3 测试。
- 网页安装包内的静态 HTML：构建后的 wheel 包含它，HTTP GET 可读取；在 Task 4 测试。
- 旧包消失后的全量测试：不得通过残留导入偶然成功；在 Task 2 和 Task 5 检查。
- 提示词在模块拆分后字节级不变：在 Task 1 记录基线，Task 4 对照。

---

### Task 1: 锁定迁移前基线

**Files:**
- Create: `tests/test_migration_contract.py`
- Read: `ae_grading/`, `ae_workflow/`, `web_app/`, `tests/`

**Interfaces:**
- Consumes: `ae_grading.classify`, `ae_workflow.deepseek._field_contract`, `web_app.config.frontend_config`。
- Produces: 不依赖模型 API 的输入输出和提示词回归测试，迁移后改用新路径。

- [x] 沿用现有代表性分级和网页字段测试；用 fake API 新增提取与审核系统提示词指纹测试，并在拆分后做系统／用户提示词全文对照。
- [x] 运行 `.venv/bin/python -m unittest discover -s tests -q`，迁移前 55 个测试通过。

### Task 2: 迁入单一 `src/medi` 包

**Files:**
- Move: `ae_grading/*` → `src/medi/grading/*`
- Move: `ae_workflow/*` → `src/medi/workflow/*`（先保留 `deepseek.py` 单文件）
- Move: `web_app/*` → `src/medi/web/*`
- Create: `src/medi/__init__.py`
- Modify: `pyproject.toml`, `tests/test_*.py`

**Interfaces:**
- Produces: `medi.grading.classify(payload: str)`, `medi.grading.FIELD_SPECS`, `medi.workflow.grade_medical_record(...)`, `medi.web.server.run(...)`。

- [x] 先将测试改为新导入、增加断言新包存在；运行测试，因 `medi` 尚不存在而失败。
- [x] 无损移动当前源文件，改内部绝对导入；规则算法内容不动；配置 setuptools 从 `src` 发现包。
- [x] 在 `.venv` 执行可编辑安装；运行全部测试并检查旧包导入。

### Task 3: 建立统一 CLI

**Files:**
- Create: `src/medi/cli.py`, `src/medi/__main__.py`, `tests/test_cli.py`
- Delete after parity check: `run_deepseek.py`, `run_web.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `medi.cli.main(argv: list[str] | None = None) -> int`；`medi grade <path|-> [--model ...]`、`medi web [--host ...] [--port ...]`。

- [x] 先写 CLI 测试：`grade` 缺少路径、空标准输入、成功/异常 JSON 与退出码、cwd `.env` 优先级、`web` 参数转发，以及 `python -m medi --help`；观察预期失败。
- [x] 实现 argparse 子命令、显式路径/标准输入、当前目录 `.env` 加载、JSON 错误契约；旧脚本删除；设置控制台入口。
- [x] 跑 CLI 测试和完整测试；在项目外 cwd 调用 `.venv/bin/medi --help` 并核对错误路径。

### Task 4: 拆分 DeepSeek 适配器并验证资源打包

**Files:**
- Split: `src/medi/workflow/deepseek.py` → `src/medi/workflow/deepseek/{__init__,client,prompts,validation,agents}.py`
- Modify: `pyproject.toml`, `tests/test_deepseek.py`, `tests/test_web_app.py`

**Interfaces:**
- Produces: `medi.workflow.deepseek.create_deepseek_agents`, `DeepSeekClient`, `DeepSeekExtractor`, `DeepSeekReviewer`；页面 `/` 仍返回现有 HTML。

- [x] 新增拆分后提示词构造与审核校验测试，确认迁移前失败；现有 fake client 测试继续覆盖 API 行为，并新增 GET `/` 测试。wheel 资源采用实际构建与隔离安装冒烟验证。
- [x] 按职责拆分原文件，复用同一字段注册表，保留提示词字符串；将 HTML 声明为 package data。
- [x] 运行 DeepSeek/Web 测试、构建 wheel 并检查其中静态资源，再运行完整测试。

### Task 5: 文档切换与最终验证

**Files:**
- Modify: `README.md`, `AGENTS.md`, `docs/README.md`, `docs/ARCHITECTURE.md`, `docs/字段策略.md`, `docs/结构化事实提取规范.md`, `docs/规则引擎规范.md`, `docs/工作流编排规范.md`
- Modify: tests as needed for final package paths.

**Interfaces:**
- Produces: 只指向新包/命令的现行文档，不改临床规则文本。

- [x] 更换旧路径和命令示例，说明 `pip install -e .`、显式病例参数、cwd `.env`；检查文档链接和旧标识残留。
- [x] 运行 `.venv/bin/python -m unittest discover -s tests -q`、`medi --help`、`medi grade` 错误冒烟、网页 API 冒烟、wheel 资源检查、`git diff --check`。
- [x] 对照 Task 1 基线，检查结果和提示词一致；报告所有本次改动及既有无关问题，不自行修改临床逻辑。

备注：本项目当前工作区含大量用户未提交修改，因此本计划不执行自动提交；每阶段以测试和 diff 核查作为回退点。
