# 项目文档导航

从根目录 [README](../README.md) 了解安装与运行；修改项目前先读 [AGENTS.md](../AGENTS.md)。按任务选择以下现行文档，再核对对应代码和测试。

## 现行规范与架构

- [规则引擎规范](规则引擎规范.md)：分级公式、优先级、缺失值和输出契约。
- [字段策略](字段策略.md)：字段用途、来源、默认值、提取提示词及待确认事项；这是人工审核表，实际运行配置在 `src/medi/grading/field_registry.py`。
- [结构化事实提取规范](结构化事实提取规范.md)：事实对象、证据、单位和审核要求。
- [工作流编排规范](工作流编排规范.md)：LangGraph 节点、修正次数和异常语义。
- [系统架构](ARCHITECTURE.md)：模块职责、数据流、系统边界及事实来源。

文档与运行时行为不一致时，先确认预期语义，再同步修正文档、代码和测试；不要把参考资料或归档记录当成现行规则。

## 参考资料

- [LangGraph 学习笔记](参考资料/LangGraph学习笔记.md)：通用学习材料，不作为项目工作流或产品规范。

## 开发设计

- [布尔缺失默认值设计](superpowers/specs/2026-10-26-false-defaults-design.md)与[实施计划](superpowers/plans/2026-10-26-false-defaults.md)：已启用字段策略中的 `false` 默认值；现行语义以规则引擎规范与注册表为准。
- [医生工作台设计](superpowers/specs/2026-10-26-doctor-workbench-design.md)与[实施计划](superpowers/plans/2026-10-26-doctor-workbench.md)：Web 工作流与 PDF/OCR 接入记录，不覆盖现行临床规则。
- [`src/medi` 迁移设计](superpowers/specs/2026-10-25-src-package-migration-design.md)与[实施计划](superpowers/plans/2026-10-25-src-package-migration.md)：架构迁移的决策记录，不覆盖现行临床规范。
- [D1 前置复发判定设计](superpowers/specs/2026-10-25-d1-recurrence-gate-design.md)与[实施计划](superpowers/plans/2026-10-25-d1-recurrence-gate.md)：本次字段及规则变更的实施记录；现行行为以规范和代码为准。

## 归档

- [2.2.0 需求与验收](归档/2.2.0-需求与验收.md)：实施前讨论与历史验收草案；现行行为以本页列出的规范为准。
