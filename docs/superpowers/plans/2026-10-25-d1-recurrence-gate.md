# D1 Recurrence Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the relapse-after-recovery fact and prevent an otherwise-D1 case with confirmed relapse from being graded D1.

**Architecture:** Keep the existing transient/recovered candidate calculation. Add one Boolean fact at the extraction boundary and one gate immediately before adding D1; keep all other branches and the output contract unchanged.

**Tech Stack:** Python 3, Pydantic, unittest, Markdown.

**Spec:** [D1 前置复发判定设计](../specs/2026-10-25-d1-recurrence-gate-design.md)

## Global Constraints

- Work in the user-designated checkout `/Users/fluoxetined/Documents/ChatGPT/medi`; preserve all existing dirty files and do not commit unrelated changes.
- Preserve the old `hypotension_recovered` hint and all non-D1 branches.
- New fact missing default: `None`; missing on a D1-candidate path permits both D1 and D0.
- D0 always has `has_r=false`; D1 keeps the D-R calculation.

## Review Focus

- Confirmed relapse with a short episode yields D0 only.
- Confirmed relapse despite the old recovered flag being `true` yields D0 only.
- Missing relapse on an otherwise-D1 path yields D1 and D0, with R only on D1.
- Existing D0 and E1/D2 paths ignore the new field.
- Strict input validation requires the 35th field and rejects non-Boolean known values.

---

### Task 1: Raw fact contract and extraction

**Files:** `src/medi/grading/field_registry.py`, `src/medi/grading/models.py`, `src/medi/web/config.py`, `tests/test_engine.py`, `tests/test_deepseek.py`, `tests/test_web_app.py`.

**Interfaces:** Add `hypotension_recurred_after_recovery: BooleanFact` to `ExtractedFacts` and matching `FieldSpec` with the user's exact true/false/missing hint; the web exposes the same name.

- [ ] Write tests for complete 35-field input, required-field/type validation, extraction hint, and web field exposure.
- [ ] Run focused tests and confirm RED due to the missing field.
- [ ] Add the registered fact, Schema field, and web config; replace the migration-only extraction-prompt checksum with a behavior test.
- [ ] Run focused tests and confirm GREEN.

### Task 2: D1 gate and documentation

**Files:** `src/medi/grading/possibilities.py`, `tests/test_engine.py`, `docs/规则引擎规范.md`, `docs/字段策略.md`, `docs/结构化事实提取规范.md`, `README.md`.

**Interfaces:** The existing transient/recovered candidate BoolSet is followed by the new relapse BoolSet; only a candidate D1 with relapse `false` becomes D1, while relapse `true` becomes D0.

- [ ] Add tests for all five Review Focus cases, including R and missing values; confirm RED from the unchanged gate.
- [ ] Implement the gate and complete pseudocode comments; confirm focused tests GREEN.
- [ ] Synchronize diagrams, formulas, field counts, extraction requirements, and references in current docs.
- [ ] Run `.venv/bin/python -m unittest discover -s tests -q` and `git diff --check`; review the final diff without overwriting prior user changes.

No commits are planned: this checkout already contains substantial uncommitted user work that must remain intact.
