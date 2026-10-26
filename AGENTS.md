# 项目修改约定

本项目将病历事实提取与确定性分级分开。修改前先读 [文档导航](docs/README.md)，再按任务阅读相关规范、代码和测试；不要仅凭 README 或历史需求推断现行规则。

## 模块入口

- `src/medi/grading/`：事实校验、字段注册表、PESI 与确定性分级；公开入口为 `medi.grading.classify`。
- `src/medi/workflow/`：提取、审核及 LangGraph 编排；DeepSeek 适配器位于 `workflow/deepseek/`。
- `src/medi/web/`：FastAPI 本地医生工作台、PDF 文本/OCR 提取及规则实验页；统一运行入口为 `medi grade` 与 `medi web`（也可用 `python -m medi`）。
- `tests/`：规则、提示词、工作流和网页的回归测试；`cases/` 存放示例病例。

## 事实来源与修改边界

- 分级公式、优先级、缺失值及结果契约：`docs/规则引擎规范.md`。字段类型、单位、默认值及实际发送给 LLM 的提示词：`src/medi/grading/field_registry.py`；`docs/字段策略.md` 用于人工审核，不作为运行配置。
- 事实 JSON 的运行时校验：`src/medi/grading/models.py` 与 `src/medi/grading/parser.py`；系统边界和模块职责：`docs/ARCHITECTURE.md`。
- `docs/参考资料/` 是学习资料，`docs/归档/` 是历史记录；两者都不能覆盖现行规范。
- 不自行补全或改变有歧义的临床规则。涉及规则或字段契约的修改，先确认预期，再同步代码、现行文档和测试；不要靠修改提示词假装规则引擎已经改变。
- 保留已有未提交修改，不覆盖无关文件；不得提交真实病历、密钥或 `.env` 内容。

## 验证

在项目根目录运行 `.venv/bin/python -m unittest discover -s tests -q`。文档路径调整后还需检查相对链接、运行入口和 `git diff --check`。
