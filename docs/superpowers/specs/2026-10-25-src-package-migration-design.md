# `src/medi` 代码架构与入口迁移设计

## 意图

让维护者与 AI 从一个明确的 Python 包入口找到事实契约、临床规则、工作流和本地网页，并让安装后的命令可从项目根目录以外调用。此次只改变代码组织和开发接口，不修改分级结论、字段定义、提取提示词、事实 JSON、结果 JSON 或审核重试语义。

## 已选方案与其他方案

- **原地拆分**：保留 `ae_grading/`、`ae_workflow/`、`web_app/`，只把大模块拆小。迁移成本最低，但仍有三个顶层包及两个独立脚本，安装入口不统一。
- **先迁目录、保留旧接口**：改为 `src/medi/`，旧包和脚本作为兼容层保留一版。调用方不易中断，但两套路径会增加 AI 检索噪声和维护负担。
- **统一新包和入口（已选）**：迁到 `src/medi/`，旧包和根目录脚本删除，所有代码、测试、文档改用新路径。结构最清楚，但旧 Python 导入和旧命令会中断；用户明确选择一次性切换。

## 目标与边界

目标：

1. 只有 `medi` 一个发行包入口；`grading`、`workflow`、`web` 在包内分层，依赖方向为 `workflow → grading`、`web → grading`，规则层不依赖模型或网页。
2. 配置、模型调用、提示词、审核结果校验各有清楚的归属；字段注册表仍是运行时字段元数据和提取提示词的唯一来源。
3. 安装后使用 `medi grade <病历文件>` 或 `medi web`；也支持 `python -m medi ...`。README、架构文档、AGENTS 和测试只指向新入口。
4. 文档、代码、测试三者同步；保留用户当前所有未提交修改，不借目录迁移改临床规则。

非目标：不增加字段、复发状态、临床公式、审核策略、模型供应商、生产安全功能或新的持久化层；不顺手改 UI 设计。原始病历和 API 密钥仍不得纳入仓库。

不可接受的结果：同一事实 JSON 的 `classify` 结果变化、LLM 实际提示词内容变化、HTTP API 契约变化，或搬迁时丢失用户未提交改动。

## 目标目录与职责

```text
medi/
├── src/medi/
│   ├── __init__.py
│   ├── __main__.py               # python -m medi
│   ├── cli.py                    # medi grade / medi web
│   ├── grading/
│   │   ├── __init__.py           # classify、FIELD_SPECS
│   │   ├── engine.py
│   │   ├── field_registry.py
│   │   ├── models.py
│   │   ├── parser.py
│   │   ├── pesi.py
│   │   └── possibilities.py
│   ├── workflow/
│   │   ├── __init__.py           # grade_medical_record 等公开接口
│   │   ├── agents.py
│   │   ├── state.py
│   │   ├── graph.py
│   │   └── deepseek/
│   │       ├── __init__.py       # 对外导出适配器与工厂
│   │       ├── client.py         # API 调用与环境变量
│   │       ├── prompts.py        # 从字段注册表构造提取/审核提示词
│   │       ├── validation.py     # 审核 JSON 校验
│   │       └── agents.py         # Extractor、Reviewer
│   └── web/
│       ├── __init__.py
│       ├── config.py             # 页面标签、分组、随机范围和预设
│       ├── server.py             # 本地 HTTP API
│       └── static/index.html
├── cases/                         # 虚构示例病例，保留在仓库根目录
├── docs/
├── tests/
└── pyproject.toml
```

`possibilities.py` 和 `pesi.py` 的临床求值逻辑本次整体迁移，不为了“文件更小”而拆开相互依赖的状态压缩过程。`web/config.py` 只拥有页面展示属性；数值类型、单位和枚举的事实定义仍以 `grading/field_registry.py` 为准，测试继续检查两者一致。

## 对外接口与运行行为

- Python：新公开路径为 `medi.grading.classify`、`medi.grading.FIELD_SPECS`、`medi.workflow.grade_medical_record`、`medi.workflow.build_grading_graph` 和 `medi.workflow.deepseek.create_deepseek_agents`。旧 `ae_grading`、`ae_workflow`、`web_app` 路径不再支持。
- 命令：`pyproject.toml` 声明 `[project.scripts] medi = "medi.cli:main"`；`python -m medi` 调用同一个解析器。`medi grade <path>` 使用原有 UTF-8 文件读取、模型参数、JSON 标准输出及成功/失败退出码；`medi web --host ... --port ...` 启动原有本地测试服务。
- 发行元数据：保留现有 distribution 名称 `ae-grading-engine` 和规则版本号；本次仅重命名可导入包及命令，不额外制造一次发布身份迁移。这是实施设计的选择，并非用户要求保留旧名称。
- 病例文件：新安装命令不推断源码仓库位置；`grade` 要求明确文件路径，或用 `-` 从标准输入读取。README 用 `medi grade cases/case3.txt` 作为示例。取消旧脚本无参时自动读取 `case3.txt` 的便捷行为，避免从项目外运行时错误地依赖源码目录。这是唯一有意调整的命令行交互，不改变规则和工作流输出。
- 环境配置：`medi grade` 读取当前工作目录的 `.env`，现有进程环境变量优先；从其他目录运行时可在那里放 `.env`，或直接设置 `DEEPSEEK_API_KEY`。不再隐式查找源码仓库里的 `.env`。这是为了让安装后的命令与源文件位置无关，也是实施设计的选择。
- HTTP：`GET /`、`GET /api/config`、`POST /api/classify` 路径及响应不变。静态 HTML 纳入 Python wheel 的 package data，安装后不依赖源码目录读取页面。
- 出错仍输出既有 `{"status": "error", "error": ...}` JSON 和退出码 1；不要把病历、密钥或模型响应写入日志。

## 实施与验证约束

1. 先记录迁移前基线：完整单元测试、代表性分级输入/输出、提示词构造结果、网页配置和 HTTP 响应。基线来自当前真实项目目录，包括其未提交修改。
2. 将现有模块内容迁入新包，先只改内部导入和打包路径；删除旧顶层包和根目录脚本时逐个核对源/目标内容，禁止覆盖或重置用户改动。
3. 再将 DeepSeek 文件按传输、提示词、审核校验、Agent 分开，保持实际发出的字符串内容及公开类型一致；临床规则模块只迁移，不改公式。
4. 更新 setuptools 的 `src` 包发现、package data 和控制台入口；在项目虚拟环境里执行可编辑安装后验证新命令及 `python -m medi`。检查构建后的 wheel 确实包含网页 HTML。
5. 更新测试的导入及静态资源定位，新增入口/打包/行为回归测试；更新 README、AGENTS、文档导航、ARCHITECTURE 和规范中的代码路径，不改规范的临床内容。
6. 最终运行完整单元测试、命令行及网页本地冒烟测试、`git diff --check`；对照迁移前代表性输出和提示词。只报告本次造成的差异，已有无关失败单独说明。

## 留给实施者决定的细节

- 新包内部的私有函数名和拆分顺序，以最小行为变更为准。
- 是否为内部提示词和 JSON 校验增加独立单元测试文件，可依现有测试组织决定。
- 迁移所用的安全复制或补丁步骤，但不得重置、覆盖或提交用户现有未提交内容。

本设计只覆盖架构迁移。实施前需用户审核；若用户希望保留旧脚本的默认病例行为或旧路径，先修改本设计再实施。
