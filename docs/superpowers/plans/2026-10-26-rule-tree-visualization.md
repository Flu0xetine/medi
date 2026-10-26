# Rule Tree Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在医生工作台展示完整规则判断树，并高亮每个结果的确定或可能可达路径。

**Architecture:** 规则引擎在原有压缩求值过程中同时收集节点分支序列；静态树和路径 ID 由规则层统一定义并校验。旧分类接口保持原样，新增工作台专用树/轨迹接口；网页只渲染后端路径，不重新判断临床条件。

**Tech Stack:** Python 3.10+、Pydantic、FastAPI、原生 HTML/CSS/JavaScript、unittest。

**Spec:** `docs/superpowers/specs/2026-10-26-rule-tree-visualization-design.md`

## Global Constraints

- 不改 2.2.0 等级、PESI、默认值、R、输入 Schema 或现有 `classify`/工作流/API 输出格式。
- 缺失事实的多路径与共享字段取值必须沿用现有求值器，不在浏览器重算。
- 同一前序步骤下唯一出口用实线标“确定”；多出口用虚线标“可能”。筛选路径后仍以完整轨迹集合判定确定性；默认值可使出口确定。
- 完整树始终可查看；A、B、D0 叶子固定 `has_r=false`；新增网页资源不依赖 CDN。
- 修改真实项目目录 `/Users/fluoxetined/Documents/ChatGPT/medi`，保留其中已有未提交修改。

## Review Focus

- 同一 D2 结果可从 `H=true,L=true` 和 `H=false,L=true` 到达：Task 2 测试两条路径均被保留，Task 1 测试两条均可落在树叶。
- `spo2_percent` 同时影响 PESI 与 C-R：Task 2 测试不会生成不可达的 C 且 R=false 组合。
- 筛选一条假设路径后不应把它误标为确定：Task 2 测试后端 certainty 固定，Task 4 测试前端只筛选显示、不重新计算 certainty。
- 人工连续修改事实时旧 HTTP 响应不能覆盖新结果：Task 4 测试/检查版本号保护与清空旧高亮。
- 全字段缺失时轨迹不能膨胀成原始字段组合：Task 2 测试路径数上界与响应时间。

---

## File Responsibilities

- `src/medi/grading/decision_tree.py`（新）：声明可序列化的完整树、`DecisionStep`/`DecisionPath`，校验路径终点，并按完整路径集合标注分支确定性。
- `src/medi/grading/possibilities.py`：在原有分类分支附带记录路径；旧 `classify_possible` 保持原行为。
- `src/medi/grading/engine.py`：新增 `classify_with_trace(payload: str)`，旧 `classify` 不变。
- `src/medi/web/server.py`：提供树与轨迹 API，提供本地静态资源。
- `src/medi/web/static/doctor.html`：全宽树容器、选择器、异步调用与版本控制。
- `src/medi/web/static/rule_tree.js`、`rule_tree.css`（新）：只负责树的 DOM 与样式，不计算临床规则。
- `pyproject.toml`：将新增静态资源纳入 wheel。
- `tests/test_decision_tree.py`（新）、`tests/test_web_app.py`：逻辑、契约与网页回归。
- `docs/ARCHITECTURE.md`：区分旧公开结果与工作台专用解释接口。

### Task 1: 规则树数据与路径契约

**Files:** Create `src/medi/grading/decision_tree.py`, `tests/test_decision_tree.py`.

**Interfaces:**
- Produces: `DecisionStep(node: str, outcome: str)`、`DecisionPath(grade: str, has_r: bool, steps: tuple[DecisionStep, ...])`（不可变、可哈希）。
- Produces: `rule_tree() -> dict[str, object]`（返回可 JSON 序列化的独立副本）；`resolve_path(path: DecisionPath) -> tuple[str, bool]`（按树逐步走到叶子，不匹配抛 `ValueError`）；`serialize_paths(paths: Iterable[DecisionPath]) -> list[dict[str, object]]`（稳定排序并基于全部路径标注每步 `certainty: "certain"|"possible"` 和整条路径的 certainty）。
- 节点 ID：`a,e2,h,l_h,l_no_h,recurrent,transient_or_recovered,relapse,pesi,c_status,b_location,e_r,d_r,c_r`；布尔分支 `yes/no`，C 分支 `C1/C2/C3`，B 分支 `B1/B2`。

- [ ] 写失败测试：树从 A 起，包含规范第 4 节全部判断与 21 个终点；D2 两个入口可分别解析；非法步骤或终点不匹配会报错；同前缀双出口为 `possible`，唯一出口为 `certain`，且传入路径次序不影响输出。
- [ ] 运行 `.venv/bin/python -m unittest tests.test_decision_tree -q`，确认测试因接口缺失失败。
- [ ] 实现树、路径解析和确定性序列化；在复杂函数注释中写完整伪代码。
- [ ] 重跑该测试，确认通过。

### Task 2: 在规则计算中收集真实可达路径

**Files:** Modify `src/medi/grading/possibilities.py`, `src/medi/grading/engine.py`; extend `tests/test_decision_tree.py`.

**Interfaces:**
- Consumes Task 1 的 `DecisionStep`、`DecisionPath`、`serialize_paths`、`resolve_path`。
- Produces: `classify_possible_with_paths(facts: ExtractedFacts) -> tuple[ClassificationResults, tuple[DecisionPath, ...]]`；`classify_with_trace(payload: str) -> dict[str, object]` 返回 `{"results": [...], "paths": [...]}`。
- 旧 `classify_possible` 与 `classify` 仍只返回已有结果，不修改导出结构。

- [ ] 写失败测试：A/E2 优先、D2 双入口、D1 候选失败与复发排除、B/C 子级和 R 真假逐条生成可解析路径；每条路径叶子与结果相同，路径结果集合等于旧 `classify`。缺失 A/PESI/R 显示可能分叉，缺失但默认 false 的字段不产生可能分叉；SpO₂/PESI/C-R 共享约束不产生虚假轨迹。全缺失路径数保持有限（小于 100）且 1 秒内完成。
- [ ] 运行 `.venv/bin/python -m unittest tests.test_decision_tree -q`，确认新增测试失败。
- [ ] 给现有分支附带不可变步骤元组，在 `_add` 收集 `(grade,has_r,steps)`；D0 的候选失败与复发成功分别记录，R 的 yes/no 在结果加入时记录；先去重再标 certainty。不要从结果反推路径。
- [ ] 重跑 `tests.test_decision_tree`、`tests.test_engine`，确认通过。

### Task 3: 工作台专用 API

**Files:** Modify `src/medi/web/server.py`, `tests/test_web_app.py`.

**Interfaces:**
- Consumes `rule_tree()`、`classify_with_trace(payload)`。
- Produces `GET /api/decision-tree -> {"tree": ...}`、`POST /api/decision-trace`（请求 `{"facts": 完整事实对象}`，响应 `{"results": [...], "paths": [...]}`）；输入错误 HTTP 400。

- [ ] 写失败 API 测试：无密钥也能取树；有效病例的结果与 `/api/reclassify` 完全一致，路径可达；缺字段返回 400；旧 `/api/classify`、`/api/reclassify` 不新增 `paths`。
- [ ] 运行 `.venv/bin/python -m unittest tests.test_web_app -q`，确认新测试失败。
- [ ] 实现接口与静态资源路由；只捕获输入错误，避免吞掉编程错误。
- [ ] 重跑网页测试，确认通过。

### Task 4: 全宽交互式判断树

**Files:** Modify `src/medi/web/static/doctor.html`, `pyproject.toml`, `tests/test_web_app.py`; create `src/medi/web/static/rule_tree.js`, `src/medi/web/static/rule_tree.css`.

**Interfaces:**
- Consumes Task 3 的树/轨迹响应；`rule_tree.js` 暴露 `RuleTree.create(container, tree)`，返回有 `setPaths(paths)`、`setFilter(grade, hasR, pathIndex)`、`clearHighlights()` 的视图对象。
- 只用后端传入的 `certainty` 控制 `.certain`（实线）和 `.possible`（虚线）；筛选操作绝不重算 certainty。

- [ ] 写失败网页测试：页面含全宽 `id="rule-tree"`、全部/结果/单路径选择器、确定/可能图例及清楚的“可达而非已证实”说明；新增资源 HTTP 200；页面加载树，分析/修订调用轨迹 API，旧结果请求不会覆盖最新树。
- [ ] 运行 `.venv/bin/python -m unittest tests.test_web_app -q`，确认新增断言失败。
- [ ] 写树视图和响应式样式，修改页面调用；无结果、输入错误、分析期间清除高亮但保留完整树。资源加入 package-data。
- [ ] 重跑网页测试；执行 `node --check src/medi/web/static/rule_tree.js`，确认通过；浏览器中检查滚动、路径选择、键盘操作和实线/虚线图例。

### Task 5: 文档与最终验证

**Files:** Modify `docs/ARCHITECTURE.md`; extend `tests/test_decision_tree.py` if verification finds gaps.

**Interfaces:** No new runtime interface.

- [ ] 更新架构文档的结果边界和已知限制：旧公开结果仍无路径；本地工作台新接口有可达路径和条件于前序判断的确定性。
- [ ] 运行 `.venv/bin/python -m unittest discover -s tests -q`、`node --check src/medi/web/static/rule_tree.js`、`git diff --check`，记录实际结果。
- [ ] 对照设计文档逐项核对：完整树、分支高亮、结果筛选、确定/可能语义、旧契约不变、无 CDN、原有未提交修改保留。
