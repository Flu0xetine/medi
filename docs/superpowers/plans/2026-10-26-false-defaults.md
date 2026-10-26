# Boolean Missing Defaults Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 启用字段策略已列出的 11 个待实施 `false` 默认值，使缺失事实按默认值而非真假展开。

**Architecture:** 保持原始缺失三元组；只在 `FIELD_SPECS` 设置 `missing_default=False`，复用 `ExtractedFacts.get()` 和现有规则求值器。同步当前规范及回归测试。

**Tech Stack:** Python、Pydantic、unittest、Markdown。

**Spec:** [布尔缺失默认值设计](../specs/2026-10-26-false-defaults-design.md)

## Global Constraints

- 在 `/Users/fluoxetined/Documents/ChatGPT/medi` 实施，保留现有未提交修改。
- 不改变 LLM 提示词、事实 JSON Schema、分级公式或输出格式。
- 不提交真实病历或密钥；本任务不修复模型输出非法三元组的独立问题。

## Review Focus

- 缺失但有默认值时，只按 `false` 判断，不再产生相反结果。
- 明确 `true` 必须覆盖默认值。
- 缺失且无默认值的字段仍枚举可达状态。
- 原始 `mentioned=false`、`value=null`、`evidence=null` 不被改写。

---

### Task 1: 默认值与行为回归

**Files:** `src/medi/grading/field_registry.py`、`tests/test_engine.py`、`tests/test_deepseek.py`。

**Interfaces:** `FIELD_SPECS[name].missing_default`；`ExtractedFacts.get(name)`；`classify(payload)`。

- [x] 编写失败测试：12 个默认值集合、缺失治疗/低灌注/PESI/R 收窄、明确值优先、无默认值继续展开。
- [x] 运行聚焦测试并确认新断言按预期失败。
- [x] 在注册表启用 11 个默认值；聚焦测试及全量测试通过，必要时调整旧的无默认值预期测试。

### Task 2: 文档与最终核验

**Files:** `docs/字段策略.md`、`docs/规则引擎规范.md`、`README.md`、`docs/ARCHITECTURE.md`。

- [x] 去除“仅鼻导管启用”的过时表述，写清默认值作用于计算而不改写原始事实。
- [x] 运行 `.venv/bin/python -m unittest discover -s tests -q`、`git diff --check`，检查文档与注册表集合一致。

不计划提交：指定目录已有用户未提交修改。
